"""OCR 流水线公共工具：原子写、哈希、日志、重试、超时、坐标换算。"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGGER_NAME = "ocr_pipeline"
VISUAL_CATEGORIES = {
    "image",
    "chart",
    "table",
    "header_image",
    "footer_image",
    "seal",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_root() -> Path:
    """临时目录：优先 OCR_TMPDIR，其次项目内 temp，最后系统临时目录。"""
    candidates = [
        os.environ.get("OCR_TMPDIR"),
        "/tmp/opencode/ocr",
        str(PROJECT_ROOT / "temp" / "ocr"),
        os.path.join(tempfile.gettempdir(), "ocr_pipeline"),
    ]
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            continue
    return Path(tempfile.mkdtemp(prefix="ocr_pipeline_"))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_text_atomic(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json_atomic(path: Path, data: Any, indent: int = 2) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
    write_text_atomic(path, text)


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return default


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = json.loads(json.dumps(base))
    for key, value in (override or {}).items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def safe_rel(path: Path, base: Optional[Path] = None) -> str:
    base = base or PROJECT_ROOT
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except (OSError, ValueError):
        return str(path)


def setup_logger(
    log_file: Optional[Path] = None,
    level: str = "INFO",
    quiet: bool = False,
    verbose: bool = False,
) -> logging.Logger:
    """创建带控制台/文件输出的 logger；重复调用不会重复加 handler。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if verbose:
        level = "DEBUG"
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    if quiet:
        numeric = logging.ERROR

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")

    existing = {getattr(h, "_ocr_tag", "") for h in logger.handlers}
    if "console" not in existing:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.setLevel(numeric)
        ch._ocr_tag = "console"  # type: ignore[attr-defined]
        logger.addHandler(ch)
    else:
        for h in logger.handlers:
            if getattr(h, "_ocr_tag", "") == "console":
                h.setLevel(numeric)

    if log_file:
        log_file = Path(log_file)
        ensure_dir(log_file.parent)
        tag = f"file:{log_file.resolve()}"
        if tag not in existing:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(message)s",
                    "%Y-%m-%d %H:%M:%S",
                )
            )
            fh.setLevel(logging.DEBUG)
            fh._ocr_tag = tag  # type: ignore[attr-defined]
            logger.addHandler(fh)

    for h in logger.handlers:
        if getattr(h, "_ocr_tag", "") == "console":
            h.setLevel(numeric)
    return logger


def retry_call(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[type, ...] = (Exception,),
    logger: Optional[logging.Logger] = None,
    description: str = "",
) -> Any:
    """指数退避重试；最后一次仍失败则原样抛出。"""
    last: Optional[BaseException] = None
    attempts = max(1, int(attempts))
    for i in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as exc:  # type: ignore[misc]
            last = exc
            if i >= attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (i - 1)))
            if logger:
                logger.warning(
                    "%s失败（第 %d/%d 次）：%s；%.1fs 后重试",
                    description or "操作", i, attempts, exc, delay,
                )
            time.sleep(delay)
    assert last is not None
    raise last


class TimeoutExpired(TimeoutError):
    """流水线内部超时（与 subprocess.TimeoutExpired 区分）。"""


@contextlib.contextmanager
def time_limit(seconds: Optional[float], description: str = "操作"):
    """在 Unix 主线程内用 SIGALRM 限制单次调用时长。

    vLLM 的 generate 是阻塞调用；若卡死，SIGALRM 可抛出异常让流水线记录失败并
    继续下一份/下一页。子线程或 Windows 下不启用（调用方应在外层用 timeout）。
    """
    if not seconds or seconds <= 0:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):  # noqa: ANN001
        raise TimeoutExpired(f"{description}超过 {seconds:.0f}s")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def run_cmd(
    cmd: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"命令不存在：{cmd[0]}；请检查系统依赖") from exc
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"命令失败（{proc.returncode}）：{' '.join(map(str, cmd))}\n"
            f"stdout: {proc.stdout[-800:]}\nstderr: {proc.stderr[-800:]}"
        )
    return proc


def parse_bbox(value: Any) -> Optional[List[int]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        out = [int(round(float(v))) for v in value]
    except (TypeError, ValueError):
        return None
    if out[0] > out[2] or out[1] > out[3]:
        return None
    return out


def bbox_1000_to_pixels(
    bbox: Sequence[int], width: int, height: int
) -> Optional[Tuple[int, int, int, int]]:
    """把 [0,1000) 归一化坐标转换为图片像素框；越界自动裁剪。"""
    if width <= 0 or height <= 0:
        return None
    vals = parse_bbox(bbox)
    if vals is None:
        return None
    left, top, right, bottom = vals
    x1 = max(0, min(width, round(left * width / 1000)))
    y1 = max(0, min(height, round(top * height / 1000)))
    x2 = max(0, min(width, round(right * width / 1000)))
    y2 = max(0, min(height, round(bottom * height / 1000)))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def bbox_pixels_to_norm(
    bbox: Sequence[float], width: int, height: int
) -> Optional[List[float]]:
    if width <= 0 or height <= 0 or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = (float(v) for v in bbox)
    return [
        round(x1 / width, 6),
        round(y1 / height, 6),
        round(x2 / width, 6),
        round(y2 / height, 6),
    ]


def bbox_overlap(a: Sequence[float], b: Sequence[float]) -> float:
    """两个像素框的 IoU；用于 Paddle 版面框与识别块对齐。"""
    ax1, ay1, ax2, ay2 = map(float, a)
    bx1, by1, bx2, by2 = map(float, b)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def iter_batches(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    size = max(1, int(size or 1))
    for start in range(0, len(items), size):
        yield items[start : start + size]


class FileLock:
    """基于 flock 的非阻塞目录锁；防止两个进程同时写同一处理目录。"""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> bool:
        ensure_dir(self.path.parent)
        self._fh = self.path.open("a+")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(f"{os.getpid()}\n")
            self._fh.flush()
            return True
        except OSError:
            self._fh.close()
            self._fh = None
            return False

    def release(self) -> None:
        if self._fh:
            with contextlib.suppress(OSError):
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def safe_name(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text.strip())
    text = text.strip("._")
    return (text[:max_len] or "item")


def one_line(text: str, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]
