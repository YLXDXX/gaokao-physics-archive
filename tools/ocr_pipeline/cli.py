"""命令行入口：run / batch / status / plan / crops / serve / probe。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .config import load_config
from .ovis3 import crop_saved_pages
from .pdf import probe_pdf
from .pipeline import (
    DEFAULT_STAGES,
    Job,
    discover_jobs,
    plan_rows,
    print_status,
    run_stages,
    status_rows,
)
from .utils import PROJECT_ROOT, ensure_dir, setup_logger, tmp_root


def _add_logging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", "-c", default=None, help="JSON 配置文件")
    parser.add_argument("--log-file", default=None, help="日志文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument("--quiet", "-q", action="store_true", help="仅错误")


def _add_common(parser: argparse.ArgumentParser, *, include_dpi: bool = True) -> None:
    _add_logging(parser)
    parser.add_argument("--model-path", default=None, help="OvisOCR3 模型目录")
    parser.add_argument("--gpu-memory", type=float, default=None, help="vLLM GPU 显存比例")
    parser.add_argument("--tensor-parallel", type=int, default=None, help="张量并行数")
    parser.add_argument("--max-model-len", type=int, default=None, help="最大上下文长度")
    parser.add_argument("--no-enforce-eager", action="store_true", help="启用 CUDA Graph（更慢的初始化）")
    parser.add_argument("--skip-compile", action="store_true", help="跳过 torch.compile（仅测试）")
    parser.add_argument("--ovis-mode", choices=["structured", "markdown", "both", "layout"], default=None,
                        help="Ovis 输出模式（默认 structured）")
    parser.add_argument("--ovis-batch-size", type=int, default=None, help="Ovis 批大小（默认 1，稳妥断点）")
    parser.add_argument("--page-timeout", type=float, default=None, help="单页/单批推理超时秒数")
    if include_dpi:
        parser.add_argument("--dpi", type=int, default=None, help="PDF 渲染 DPI（默认 300）")
    parser.add_argument("--crop-dpi", type=int, default=None, help="视觉块裁剪 DPI（默认 300）")
    parser.add_argument("--crop-format", choices=["png", "jpg"], default=None, help="视觉块裁剪格式")
    parser.add_argument("--no-block-crops", action="store_true", help="不保存 structured 视觉块裁剪")
    parser.add_argument("--paddle-host", default=None, help="Paddle 服务地址")
    parser.add_argument("--paddle-port", type=int, default=None, help="Paddle 服务端口")
    parser.add_argument("--paddle-timeout", type=float, default=None, help="Paddle 请求超时秒数")
    parser.add_argument("--paddle-page-chunk", type=int, default=None, help="Paddle 单次请求页数（默认 20）")
    parser.add_argument("--no-paddle-restructure", action="store_true", help="禁用 Paddle 跨页重构")


def _add_discovery(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", action="append", default=[], help="处理根目录（可重复）")
    parser.add_argument("--jobs-file", default=None, help="作业清单 JSON/TSV（pdf<TAB>out）")
    parser.add_argument("--pair", action="append", default=[], help="显式作业 PDF::OUT（可重复）")
    parser.add_argument("--source-root", default=None, help="按目录镜像新建作业：源 PDF 根")
    parser.add_argument("--output-root", default=None, help="按目录镜像新建作业：输出根")
    parser.add_argument("--base-root", action="append", default=[], help="源 PDF 基准根（可重复）")
    parser.add_argument("--only", default=None, help="仅处理路径含该关键词者")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 份")


def _add_run_controls(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stages",
        default=None,
        help="逗号分隔阶段（默认取配置；内置默认 " + ",".join(DEFAULT_STAGES) + "）",
    )
    parser.add_argument("--force", action="store_true", help="全部阶段重跑")
    parser.add_argument("--force-stage", action="append", default=[], help="仅重跑指定阶段（可重复）")
    parser.add_argument("--dry-run", action="store_true", help="只列出计划，不执行")
    parser.add_argument("--auto-serve", action="store_true", help="自动启停 PaddleOCR-VL 服务")
    parser.add_argument("--fail-fast", action="store_true", help="遇错立即停止（默认继续其它作业）")
    parser.add_argument("--no-lock", action="store_true", help="禁用处理目录锁")


def _stages(args: argparse.Namespace, config: Dict[str, Any]) -> List[str]:
    configured = config["pipeline"].get("stages") or DEFAULT_STAGES
    if isinstance(configured, str):
        default_raw = configured
    else:
        default_raw = ",".join(map(str, configured))
    raw = getattr(args, "stages", None) or default_raw
    return [s.strip() for s in raw.split(",") if s.strip()]


def build_config(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config(getattr(args, "config", None))
    if getattr(args, "model_path", None):
        config["model"]["path"] = args.model_path
    if getattr(args, "gpu_memory", None) is not None:
        config["model"]["gpu_memory_utilization"] = args.gpu_memory
    if getattr(args, "tensor_parallel", None) is not None:
        config["model"]["tensor_parallel_size"] = args.tensor_parallel
    if getattr(args, "max_model_len", None) is not None:
        config["model"]["max_model_len"] = args.max_model_len
    if getattr(args, "no_enforce_eager", False):
        config["model"]["enforce_eager"] = False
    if getattr(args, "skip_compile", False):
        config["model"]["skip_compile"] = True
    if getattr(args, "ovis_mode", None):
        config["ovis"]["prompt_mode"] = args.ovis_mode
    if getattr(args, "ovis_batch_size", None) is not None:
        config["ovis"]["batch_size"] = args.ovis_batch_size
    if getattr(args, "page_timeout", None) is not None:
        config["ovis"]["page_timeout"] = args.page_timeout
    if getattr(args, "dpi", None) is not None:
        config["pdf"]["dpi"] = args.dpi
    if getattr(args, "crop_dpi", None) is not None:
        config["ovis"]["crop_dpi"] = args.crop_dpi
    if getattr(args, "crop_format", None):
        config["ovis"]["crop_format"] = args.crop_format
    if getattr(args, "no_block_crops", False):
        config["ovis"]["save_block_crops"] = False
    if getattr(args, "paddle_host", None):
        config["paddle"]["host"] = args.paddle_host
    if getattr(args, "paddle_port", None) is not None:
        config["paddle"]["port"] = args.paddle_port
    if getattr(args, "paddle_timeout", None) is not None:
        config["paddle"]["timeout"] = args.paddle_timeout
    if getattr(args, "paddle_page_chunk", None) is not None:
        config["paddle"]["page_chunk"] = args.paddle_page_chunk
    if getattr(args, "no_paddle_restructure", False):
        config["paddle"]["restructure"] = False
    if getattr(args, "no_lock", False):
        config["pipeline"]["lock"] = False
    return config


def _logger(args: argparse.Namespace, config: Dict[str, Any], prefix: str):
    log_dir = Path(config["logging"].get("dir") or (tmp_root() / "logs"))
    ensure_dir(log_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_file) if getattr(args, "log_file", None) else log_dir / f"{prefix}_{stamp}.log"
    logger = setup_logger(
        log_file,
        level=config["logging"].get("level", "INFO"),
        quiet=getattr(args, "quiet", False),
        verbose=getattr(args, "verbose", False),
    )
    return logger, log_file, stamp


def _report_path(log_dir: Path, stamp: str, prefix: str) -> Path:
    return log_dir / f"{prefix}_{stamp}.json"


def cmd_run(args: argparse.Namespace) -> int:
    config = build_config(args)
    logger, log_file, stamp = _logger(args, config, "run")
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        logger.error("输入文件不存在：%s", input_path)
        return 2
    out = Path(args.output).expanduser().resolve() if args.output else input_path.parent / input_path.stem
    if input_path.suffix.lower() != ".pdf":
        logger.error("run 仅处理 PDF：%s", input_path)
        return 2
    jobs = [Job(input_path, out)]
    stages = _stages(args, config)
    report = run_stages(
        jobs, stages,
        config=config, logger=logger,
        force=args.force, force_stages=args.force_stage,
        dry_run=args.dry_run, auto_serve=args.auto_serve,
        fail_fast=args.fail_fast,
        report_path=None if args.dry_run else _report_path(log_file.parent, stamp, "run"),
    )
    if args.dry_run:
        return 0
    failed = report["summary"]["failed_jobs"]
    print(f"完成：{out}")
    print(f"日志：{log_file}")
    print(f"报告：{_report_path(log_file.parent, stamp, 'run')}")
    return 1 if failed else 0


def cmd_batch(args: argparse.Namespace) -> int:
    config = build_config(args)
    logger, log_file, stamp = _logger(args, config, "batch")
    jobs = discover_jobs(
        config=config,
        jobs_file=args.jobs_file,
        roots=args.root,
        source_root=args.source_root,
        output_root=args.output_root,
        base_roots=args.base_root,
        only=args.only,
        limit=args.limit,
        extra_pairs=args.pair,
    )
    if not jobs:
        logger.error("没有匹配的作业；请检查 --root/--jobs-file/--pair")
        return 1
    stages = _stages(args, config)
    report = run_stages(
        jobs, stages,
        config=config, logger=logger,
        force=args.force, force_stages=args.force_stage,
        dry_run=args.dry_run, auto_serve=args.auto_serve,
        fail_fast=args.fail_fast,
        report_path=None if args.dry_run else _report_path(log_file.parent, stamp, "batch"),
    )
    failed = report["summary"]["failed_jobs"]
    print(f"作业 {len(jobs)} 个；失败 {len(failed)} 个")
    if not args.dry_run:
        print(f"日志：{log_file}")
        print(f"报告：{_report_path(log_file.parent, stamp, 'batch')}")
    if failed:
        print("失败作业：")
        for item in failed[:50]:
            print("  " + item)
    return 1 if failed else 0


def cmd_status(args: argparse.Namespace) -> int:
    config = build_config(args)
    jobs = discover_jobs(
        config=config,
        jobs_file=args.jobs_file,
        roots=args.root,
        source_root=args.source_root,
        output_root=args.output_root,
        base_roots=args.base_root,
        only=args.only,
        limit=args.limit,
        extra_pairs=args.pair,
    )
    rows = status_rows(jobs, config)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_status(rows)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    config = build_config(args)
    jobs = discover_jobs(
        config=config,
        jobs_file=args.jobs_file,
        roots=args.root,
        source_root=args.source_root,
        output_root=args.output_root,
        base_roots=args.base_root,
        only=args.only,
        limit=args.limit,
        extra_pairs=args.pair,
    )
    stages = _stages(args, config)
    rows = plan_rows(jobs, stages)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            pdf = row["pdf"] or "（未定位源PDF）"
            print(f"{pdf}  ->  {row['out']}  [{','.join(stages)}] {row['note']}")
        print(f"\n共 {len(rows)} 个作业。")
    return 0


def cmd_crops(args: argparse.Namespace) -> int:
    config = build_config(args)
    logger, _, _ = _logger(args, config, "crops")
    proc_dir = Path(args.dir).expanduser().resolve()
    if not proc_dir.is_dir():
        logger.error("处理目录不存在：%s", proc_dir)
        return 2
    pdf = Path(args.pdf).expanduser().resolve() if args.pdf else None
    if pdf is None:
        from .pdf import locate_source_pdf

        pdf = locate_source_pdf(
            proc_dir,
            base_roots=[PROJECT_ROOT / p for p in config["pipeline"]["base_roots"]],
        )
    if pdf is None or not pdf.is_file():
        logger.error("找不到源 PDF；请用 --pdf 指定")
        return 2
    try:
        result = crop_saved_pages(
            proc_dir,
            pdf,
            dpi=args.dpi,
            fmt=args.format,
            categories=args.category or None,
            out_dir=Path(args.out).expanduser().resolve() if args.out else None,
            logger=logger,
        )
    except Exception as exc:
        logger.error("重裁失败：%s", exc)
        return 1
    print(f"重裁完成：{result['output']}（{result['count']} 张）")
    if result["errors"]:
        print(f"警告 {len(result['errors'])} 条，详见 manifest.json")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    config = build_config(args)
    logger, _, _ = _logger(args, config, "serve")
    from .paddle import PaddleService

    service = PaddleService(config, logger)
    if args.action == "status":
        print("运行中" if service.healthy() else "未运行")
        return 0
    if args.action == "start":
        return 0 if service.start() else 1
    if args.action == "stop":
        service.stop()
        print("已请求停止")
        return 0
    return 2


def cmd_probe(args: argparse.Namespace) -> int:
    config = build_config(args)
    info = probe_pdf(
        Path(args.input).expanduser().resolve(),
        text_probe_pages=config["pdf"]["text_probe_pages"],
        text_min_chars=config["pdf"]["text_min_chars"],
    )
    print(json.dumps(info.as_dict(), ensure_ascii=False, indent=2))
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr_pipeline",
        description="OvisOCR3 + PaddleOCR-VL 分阶段、可断点续跑的 PDF 识别转换流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 -m tools.ocr_pipeline run -i "课程基础材料/.../x.pdf" -o "课程材料处理/.../x"
  python3 -m tools.ocr_pipeline batch --root 课程材料处理 --auto-serve --force-stage ovis
  python3 -m tools.ocr_pipeline status --root 课程材料处理
  python3 -m tools.ocr_pipeline crops -d "课程材料处理/.../x" --dpi 600
  python3 -m tools.ocr_pipeline serve start
        """,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="处理单个 PDF")
    p.add_argument("-i", "--input", required=True, help="源 PDF")
    p.add_argument("-o", "--output", required=True, help="处理目录")
    _add_common(p)
    _add_run_controls(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("batch", help="批量处理（可分阶段、断点续跑）")
    _add_common(p)
    _add_discovery(p)
    _add_run_controls(p)
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("status", help="统计处理目录完成情况")
    _add_logging(p)
    _add_discovery(p)
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("plan", help="只列出作业计划")
    _add_logging(p)
    _add_discovery(p)
    p.add_argument("--stages", default=None, help="计划执行的阶段（默认取配置）")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("crops", help="按已保存的 Ovis structured bbox 从原 PDF 高清重裁")
    p.add_argument("-d", "--dir", required=True, help="处理目录")
    p.add_argument("--pdf", default=None, help="源 PDF（默认自动定位）")
    p.add_argument("--dpi", type=int, default=300, help="渲染 DPI（默认 300）")
    p.add_argument("--format", choices=["png", "jpg"], default="png", help="输出格式")
    p.add_argument("--category", action="append", default=[], help="只裁这些类别（可重复）")
    p.add_argument("--out", default=None, help="输出目录（默认 <处理目录>/ocr_crops_<dpi>）")
    _add_logging(p)
    p.set_defaults(func=cmd_crops)

    p = sub.add_parser("serve", help="启停/查看 PaddleOCR-VL 服务")
    p.add_argument("action", choices=["start", "stop", "status"])
    _add_logging(p)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("probe", help="探测 PDF 页数/文字版/扫描版")
    p.add_argument("-i", "--input", required=True, help="源 PDF")
    _add_logging(p)
    p.set_defaults(func=cmd_probe)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("已中断；下次运行同一命令即可断点续跑。", file=sys.stderr)
        return 130
    except Exception as exc:  # pragma: no cover - 顶层兜底
        if os.environ.get("OCR_DEBUG"):
            raise
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
