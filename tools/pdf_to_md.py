# -*- coding: utf-8 -*-
"""
OvisOCR2 PDF/PNG 转 Markdown 工具（增强版）

功能：
- 将 PDF 文档或 PNG/JPG 图片转换为 Markdown 格式
- 支持物理题目、讲义、答案等多种文档类型
- 自动处理公式（LaTeX）、表格（HTML）、图片（裁剪保存）
- 支持跨页表格智能合并
- 支持批量处理和断点续传

作者：AI Assistant
版本：2.0.0
"""

import os
import re
import sys
import json
import time
import hashlib
import argparse
import logging
import traceback
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

# 导入依赖
try:
    import pymupdf
except ImportError:
    try:
        import fitz
        pymupdf = fitz
    except ImportError:
        print("[错误] 请安装 PyMuPDF: pip install pymupdf")
        sys.exit(1)

from PIL import Image
from vllm import LLM, SamplingParams

# ============================================================
# 版本信息
# ============================================================
__version__ = "2.0.0"
__author__ = "AI Assistant"

# ============================================================
# 默认配置
# ============================================================
DEFAULT_CONFIG = {
    # 模型配置
    "model": {
        "path": "./OvisOCR2",
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.85,
        "max_model_len": 32768,
        "dtype": "auto",
        "trust_remote_code": True,
        "gdn_prefill_backend": "triton",
    },
    # OCR 配置
    "ocr": {
        "min_pixels": 448 * 448,
        "max_pixels": 2880 * 2880,
        "max_tokens": 16384,
        "temperature": 0.0,
        "enable_thinking": False,
    },
    # 图片处理
    "image": {
        "max_size": 2000,
        "quality": 95,
        "format": "jpg",
    },
    # PDF 配置
    "pdf": {
        "dpi": 300,
        "batch_size": 4,
    },
    # 输出配置
    "output": {
        "merge_tables": True,
        "filter_images": False,
        "save_raw": False,
        "include_metadata": True,
    },
    # 日志配置
    "logging": {
        "level": "INFO",
        "file": None,
        "format": "%(asctime)s - %(levelname)s - %(message)s",
    },
}

# 模型 Prompt
PROMPT_TEMPLATE = (
    '\nExtract all readable content from the image in natural human reading '
    'order and output the result as a single Markdown document. For charts or '
    'images, represent them using an HTML image tag: <'
    'img src="images/bbox_{left}_{top}_{right}_{bottom}.jpg" />, where left, '
    'top, right, bottom are bounding box coordinates scaled to [0, 1000). '
    'Format formulas as LaTeX. Format tables as HTML: <table>...</table>. '
    'Transcribe all other text as standard Markdown. Preserve the original '
    'text without translation or paraphrasing.'
)

# 图片标签正则
BBOX_IMAGE_PATTERN = re.compile(
    r'<img\s+src="images/bbox_(\d+)_(\d+)_(\d+)_(\d+)\.jpg"\s*/>'
)

# 表格标签
TABLE_START = "<table"
TABLE_END = "</table>"


# ============================================================
# 日志设置
# ============================================================
def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """设置日志系统"""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper())

    formatter = logging.Formatter(
        log_config.get("format", "%(asctime)s - %(levelname)s - %(message)s")
    )

    logger = logging.getLogger("ovis_ocr")
    logger.setLevel(level)

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    log_file = log_config.get("file")
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ============================================================
# 工具函数
# ============================================================
def generate_file_hash(file_path: Path) -> str:
    """生成文件哈希值（用于断点续传）"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()

    if config_path and Path(config_path).exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            # 深度合并配置
            for key, value in user_config.items():
                if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                    config[key].update(value)
                else:
                    config[key] = value
        except Exception as e:
            print(f"[警告] 配置文件加载失败: {e}")

    return config


def merge_configs(base: Dict, override: Dict) -> Dict:
    """深度合并配置"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def preprocess_image(image: Image.Image, max_size: int = 2000) -> Image.Image:
    """预处理图片：缩小过大的图片"""
    if max_size <= 0:
        return image

    w, h = image.size
    if max(w, h) > max_size:
        if w > h:
            new_w = max_size
            new_h = int(h * max_size / w)
        else:
            new_h = max_size
            new_w = int(w * max_size / h)

        image = image.resize((new_w, new_h), Image.LANCZOS)
        logging.getLogger("ovis_ocr").debug(
            f"图片缩小: {w}x{h} -> {new_w}x{new_h}"
        )

    return image


def clean_truncated_repeats(
    text: str,
    min_text_len: int = 8000,
    max_period: int = 200,
    min_period: int = 1,
    min_repeat_chars: int = 100,
    min_repeat_times: int = 5
) -> str:
    """
    清理模型可能产生的截断重复文本
    """
    n = len(text)
    if n < min_text_len:
        return text

    max_period = min(max_period, n - 1)
    for unit_len in range(min_period, max_period + 1):
        if text[n - 1] != text[n - 1 - unit_len]:
            continue

        match_len = 1
        idx = n - 2
        while idx >= unit_len and text[idx] == text[idx - unit_len]:
            match_len += 1
            idx -= 1

        total_len = match_len + unit_len
        repeat_times = total_len // unit_len
        tail_len = total_len % unit_len

        if repeat_times >= min_repeat_times and total_len >= min_repeat_chars:
            return text[: n - total_len + unit_len] + text[n - tail_len:]

    return text


def detect_model_path() -> Optional[str]:
    """自动检测模型路径"""
    # 1. 当前目录下的 OvisOCR2
    candidates = [
        Path.cwd() / "OvisOCR2",
        Path.cwd(),
        Path.home() / ".cache" / "OvisOCR2",
    ]

    for path in candidates:
        if (path / "config.json").is_file():
            return str(path.resolve())

    # 2. 环境变量
    env_path = os.environ.get("OVIS_MODEL_PATH")
    if env_path and (Path(env_path) / "config.json").is_file():
        return str(Path(env_path).resolve())

    return None


# ============================================================
# PDF 处理器
# ============================================================
class PDFProcessor:
    """PDF 页面渲染器"""

    @staticmethod
    def render_pages(
        pdf_path: Path,
        dpi: int = 300,
        max_size: int = 2000
    ) -> List[Image.Image]:
        """将 PDF 每页渲染为 PIL Image"""
        logger = logging.getLogger("ovis_ocr")
        logger.info(f"打开 PDF: {pdf_path}")

        doc = pymupdf.open(pdf_path)
        images = []

        zoom = dpi / 72
        mat = pymupdf.Matrix(zoom, zoom)

        for page_num, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # 预处理
            if max_size > 0:
                img = preprocess_image(img, max_size)

            images.append(img)
            logger.debug(f"渲染第 {page_num + 1}/{len(doc)} 页: {img.size}")

        doc.close()
        return images


# ============================================================
# OvisOCR2 处理器
# ============================================================
class OvisOCRProcessor:
    """OvisOCR2 模型处理器"""

    def __init__(self, model: LLM, config: Dict[str, Any]):
        self.model = model
        self.config = config
        self.logger = logging.getLogger("ovis_ocr")

        # 初始化 prompt
        tokenizer = self.model.get_tokenizer()
        self.final_prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": [
                {"type": "image"},
                {"type": "text", "text": PROMPT_TEMPLATE}
            ]}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=config["ocr"]["enable_thinking"]
        )

        # 采样参数
        self.sampling_params = SamplingParams(
            max_tokens=config["ocr"]["max_tokens"],
            temperature=config["ocr"]["temperature"]
        )

    def build_input(self, image: Image.Image) -> Dict:
        """构建 vLLM 输入"""
        return {
            "prompt": self.final_prompt,
            "multi_modal_data": {"image": image},
            "mm_processor_kwargs": {
                "images_kwargs": {
                    "min_pixels": self.config["ocr"]["min_pixels"],
                    "max_pixels": self.config["ocr"]["max_pixels"],
                }
            }
        }

    def process_batch(
        self,
        images: List[Image.Image],
        start_page: int = 1
    ) -> List[Tuple[str, List[str]]]:
        """批量处理图片"""
        vllm_inputs = [self.build_input(img) for img in images]

        self.logger.info(
            f"处理第 {start_page}-{start_page + len(images) - 1} 页..."
        )

        outputs = self.model.generate(vllm_inputs, self.sampling_params)

        results = []
        for output in outputs:
            text = output.outputs[0].text.strip()
            cleaned = clean_truncated_repeats(text)

            # 提取图片标签
            img_tags = BBOX_IMAGE_PATTERN.findall(cleaned)
            results.append((cleaned, img_tags))

        return results

    def extract_and_save_images(
        self,
        markdown: str,
        page_image: Image.Image,
        page_num: int,
        output_dir: Path,
        image_config: Dict
    ) -> Tuple[str, List[Path]]:
        """提取图片标签，裁剪并保存"""
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        saved_images = []

        def replace_func(match):
            left, top, right, bottom = match.groups()
            width, height = page_image.size

            # 坐标转换
            x1 = max(0, min(width, round(int(left) * width / 1000)))
            y1 = max(0, min(height, round(int(top) * height / 1000)))
            x2 = max(0, min(width, round(int(right) * width / 1000)))
            y2 = max(0, min(height, round(int(bottom) * height / 1000)))

            if x2 <= x1 or y2 <= y1:
                return match.group(0)

            # 生成文件名
            ext = image_config.get("format", "jpg")
            img_filename = f"page_{page_num}_bbox_{left}_{top}_{right}_{bottom}.{ext}"
            img_path = images_dir / img_filename

            try:
                # 裁剪并保存
                cropped = page_image.crop((x1, y1, x2, y2)).convert("RGB")
                cropped.save(
                    img_path,
                    quality=image_config.get("quality", 95)
                )
                saved_images.append(img_path)

                # 返回新的 Markdown 标签
                return f'<img src="images/{img_filename}" />'
            except Exception as e:
                self.logger.error(f"保存图片 {img_filename} 失败: {e}")
                return match.group(0)

        # 替换所有匹配项
        new_markdown = BBOX_IMAGE_PATTERN.sub(replace_func, markdown)

        return new_markdown, saved_images


# ============================================================
# 跨页表格合并器
# ============================================================
class TableMerger:
    """跨页表格合并器"""

    @staticmethod
    def merge(markdowns: List[str], logger=None) -> str:
        """
        智能合并跨页表格

        策略：
        1. 检测相邻页面是否分别为表格的结束和开始
        2. 合并 HTML 表格标签
        3. 处理其他跨页内容
        """
        if not markdowns:
            return ""

        if logger is None:
            logger = logging.getLogger("ovis_ocr")

        merged = markdowns[0]
        merge_count = 0

        for i in range(1, len(markdowns)):
            next_md = markdowns[i]

            # 检测跨页表格
            if (merged.rstrip().endswith(TABLE_END) and
                next_md.lstrip().startswith(TABLE_START)):
                # 移除中间的标签
                merged = (
                    merged.rstrip()[:-len(TABLE_END)] +
                    next_md.lstrip()[len(TABLE_START):]
                )
                merge_count += 1
                logger.info(f"合并跨页表格 (页 {i} -> {i+1})")
            else:
                # 检测跨页段落（简单的文本拼接）
                merged += "\n\n" + next_md

        if merge_count > 0:
            logger.info(f"共合并 {merge_count} 个跨页表格")

        return merged


# ============================================================
# 断点续传管理器
# ============================================================
class CheckpointManager:
    """断点续传管理器"""

    def __init__(self, output_dir: Path):
        self.checkpoint_file = output_dir / ".checkpoint.json"
        self.output_dir = output_dir

    def load(self) -> Optional[Dict]:
        """加载断点"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r") as f:
                    return json.load(f)
            except:
                pass
        return None

    def save(self, data: Dict):
        """保存断点"""
        with open(self.checkpoint_file, "w") as f:
            json.dump(data, f, indent=2)

    def clear(self):
        """清除断点"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()


# ============================================================
# 主处理器
# ============================================================
class MainProcessor:
    """主处理器"""

    def __init__(self, config: Dict[str, Any], args: argparse.Namespace):
        self.config = config
        self.args = args
        self.logger = logging.getLogger("ovis_ocr")
        self.model = None
        self.processor = None

    def load_model(self) -> bool:
        """加载模型"""
        model_path = self.args.model_path or detect_model_path()
        if not model_path:
            self.logger.error("未找到模型文件")
            return False

        self.logger.info(f"加载模型: {model_path}")
        start_time = time.time()

        # 构建模型参数
        model_kwargs = {
            "model": model_path,
            "tensor_parallel_size": self.config["model"]["tensor_parallel_size"],
            "gpu_memory_utilization": self.config["model"]["gpu_memory_utilization"],
            "max_model_len": self.config["model"]["max_model_len"],
            "trust_remote_code": self.config["model"]["trust_remote_code"],
            "gdn_prefill_backend": self.config["model"]["gdn_prefill_backend"],
        }

        # 性能优化选项
        if self.args.enforce_eager:
            model_kwargs["enforce_eager"] = True
            self.logger.info("启用 enforce_eager (跳过 CUDA Graph)")

        if self.args.skip_compile:
            model_kwargs["compilation_config"] = {"mode": "NONE"}
            self.logger.info("跳过 torch.compile")

        try:
            self.model = LLM(**model_kwargs)
            load_time = time.time() - start_time
            self.logger.info(f"模型加载完成 ({load_time:.1f}s)")

            # 创建处理器
            self.processor = OvisOCRProcessor(self.model, self.config)
            return True

        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            if self.args.debug:
                traceback.print_exc()
            return False

    def process_single_image(self, image_path: Path) -> bool:
        """处理单张图片"""
        output_dir = Path(self.args.output) if self.args.output else image_path.parent / f"{image_path.stem}_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"处理图片: {image_path}")

        try:
            # 加载图片
            img = Image.open(image_path).convert("RGB")
            self.logger.info(f"原始尺寸: {img.size}")

            # 预处理
            if self.config["image"]["max_size"] > 0:
                img = preprocess_image(img, self.config["image"]["max_size"])

            # 处理
            results = self.processor.process_batch([img])
            markdown, img_tags = results[0]

            # 保存图片
            processed_md, saved_imgs = self.processor.extract_and_save_images(
                markdown, img, 1, output_dir, self.config["image"]
            )

            # 保存 Markdown
            md_path = output_dir / "output.md"
            md_path.write_text(processed_md, encoding="utf-8")

            self.logger.info(f"完成！输出: {md_path}")
            self.logger.info(f"提取图片数: {len(saved_imgs)}")

            # 显示预览
            if self.args.preview:
                self._show_preview(processed_md)

            return True

        except Exception as e:
            self.logger.error(f"处理失败: {e}")
            if self.args.debug:
                traceback.print_exc()
            return False

    def process_pdf(self, pdf_path: Path) -> bool:
        """处理 PDF 文件"""
        output_dir = Path(self.args.output) if self.args.output else pdf_path.parent / pdf_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        # 断点续传
        checkpoint = CheckpointManager(output_dir)

        # 渲染 PDF
        self.logger.info(f"处理 PDF: {pdf_path}")
        try:
            page_images = PDFProcessor.render_pages(
                pdf_path,
                self.config["pdf"]["dpi"],
                self.config["image"]["max_size"]
            )
        except Exception as e:
            self.logger.error(f"PDF 渲染失败: {e}")
            return False

        total_pages = len(page_images)
        self.logger.info(f"共 {total_pages} 页")

        # 检查断点
        cp_data = checkpoint.load()
        start_page = 0
        all_markdowns = []

        if cp_data and self.args.resume:
            file_hash = generate_file_hash(pdf_path)
            if cp_data.get("file_hash") == file_hash:
                start_page = cp_data.get("last_page", 0)
                all_markdowns = cp_data.get("results", [])
                self.logger.info(f"从第 {start_page + 1} 页继续")

        # 批处理
        batch_size = self.config["pdf"]["batch_size"]
        batch_size = self.args.batch_size or batch_size

        all_saved_images = []

        for i in range(start_page, total_pages, batch_size):
            batch_imgs = page_images[i : i + batch_size]
            batch_start = i + 1

            try:
                # 生成
                results = self.processor.process_batch(batch_imgs, batch_start)

                # 后处理
                for idx, (markdown, img_tags) in enumerate(results):
                    page_num = batch_start + idx
                    page_img = batch_imgs[idx]

                    # 提取图片
                    processed_md, saved_imgs = self.processor.extract_and_save_images(
                        markdown, page_img, page_num, output_dir, self.config["image"]
                    )

                    all_markdowns.append(processed_md)
                    all_saved_images.extend(saved_imgs)

                    self.logger.info(f"  第 {page_num} 页完成")

                # 保存断点
                checkpoint.save({
                    "file_hash": generate_file_hash(pdf_path),
                    "last_page": i + batch_size,
                    "results": all_markdowns,
                    "timestamp": datetime.now().isoformat()
                })

            except Exception as e:
                self.logger.error(f"批处理失败 (第 {batch_start} 页起): {e}")
                if self.args.debug:
                    traceback.print_exc()

                # 添加错误占位符
                for _ in range(len(batch_imgs)):
                    all_markdowns.append(f"<!-- 第 {batch_start + _} 页处理失败 -->")

        # 合并跨页表格
        if self.config["output"]["merge_tables"]:
            self.logger.info("合并跨页表格...")
            final_markdown = TableMerger.merge(all_markdowns, self.logger)
        else:
            final_markdown = "\n\n".join(all_markdowns)

        # 添加元数据
        if self.config["output"]["include_metadata"]:
            metadata = self._generate_metadata(pdf_path, total_pages)
            final_markdown = metadata + "\n\n" + final_markdown

        # 保存最终文档
        md_path = output_dir / "output.md"
        md_path.write_text(final_markdown, encoding="utf-8")

        # 保存原始输出（如果需要）
        if self.config["output"]["save_raw"]:
            raw_dir = output_dir / "raw"
            raw_dir.mkdir(exist_ok=True)
            for i, md in enumerate(all_markdowns):
                (raw_dir / f"page_{i+1}.md").write_text(md, encoding="utf-8")

        # 清除断点
        checkpoint.clear()

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"处理完成！")
        self.logger.info(f"  输入: {pdf_path}")
        self.logger.info(f"  输出: {output_dir}")
        self.logger.info(f"  Markdown: {md_path}")
        self.logger.info(f"  图片目录: {output_dir / 'images'}")
        self.logger.info(f"  图片总数: {len(all_saved_images)}")
        self.logger.info(f"{'='*60}")

        # 显示预览
        if self.args.preview:
            self._show_preview(final_markdown)

        return True

    def _generate_metadata(self, input_path: Path, pages: int) -> str:
        """生成文档元数据"""
        return f"""---
title: "{input_path.stem}"
source: "{input_path.name}"
pages: {pages}
processed_at: "{datetime.now().isoformat()}"
model: "OvisOCR2"
version: "{__version__}"
---
"""

    def _show_preview(self, markdown: str, length: int = 500):
        """显示预览"""
        print("\n" + "=" * 60)
        print("Markdown 预览:")
        print("=" * 60)
        print(markdown[:length])
        if len(markdown) > length:
            print(f"... (共 {len(markdown)} 字符)")
        print("=" * 60)


# ============================================================
# 参数解析
# ============================================================
def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="pdf_to_md.py",
        description="OvisOCR2 PDF/PNG 转 Markdown 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s --input document.pdf
  %(prog)s --input image.png --test
  %(prog)s --input doc.pdf --dpi 200 --batch-size 2
  %(prog)s --input img.png --test --enforce-eager --preview

配置文件示例 (config.json):
{
    "model": {"gpu_memory_utilization": 0.9},
    "pdf": {"dpi": 200, "batch_size": 2},
    "image": {"max_size": 1500}
}
        """
    )

    # 版本信息
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    # 输入/输出参数
    io_group = parser.add_argument_group("输入/输出", "输入输出相关配置")
    io_group.add_argument(
        "--input", "-i",
        required=True,
        help="输入文件路径 (PDF/PNG/JPG)"
    )
    io_group.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (默认: 自动生成)"
    )
    io_group.add_argument(
        "--config", "-c",
        default=None,
        help="配置文件路径 (JSON格式)"
    )

    # 模式参数
    mode_group = parser.add_argument_group("处理模式", "处理模式选择")
    mode_group.add_argument(
        "--test",
        action="store_true",
        help="测试模式: 处理单张图片"
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="干运行: 只显示配置，不实际处理"
    )

    # 模型参数
    model_group = parser.add_argument_group("模型配置", "模型相关参数")
    model_group.add_argument(
        "--model-path",
        default=None,
        help="模型路径 (默认: 自动检测)"
    )
    model_group.add_argument(
        "--gpu-memory",
        type=float,
        default=None,
        help="GPU 内存利用率 (0.0-1.0, 默认: 0.85)"
    )
    model_group.add_argument(
        "--tensor-parallel",
        type=int,
        default=None,
        help="GPU 并行数 (默认: 1)"
    )
    model_group.add_argument(
        "--max-model-len",
        type=int,
        default=None,
        help="最大上下文长度 (默认: 32768)"
    )

    # 性能优化参数
    perf_group = parser.add_argument_group("性能优化", "性能相关参数")
    perf_group.add_argument(
        "--enforce-eager",
        action="store_true",
        help="跳过 CUDA Graph (加速初始化，但推理稍慢)"
    )
    perf_group.add_argument(
        "--skip-compile",
        action="store_true",
        help="跳过 torch.compile (最快初始化，仅测试用)"
    )
    perf_group.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="批处理大小 (默认: 4)"
    )

    # 图片处理参数
    img_group = parser.add_argument_group("图片处理", "图片处理参数")
    img_group.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="PDF 渲染 DPI (默认: 300)"
    )
    img_group.add_argument(
        "--max-image-size",
        type=int,
        default=None,
        help="图片最大尺寸 (默认: 2000, 0=不限制)"
    )
    img_group.add_argument(
        "--image-quality",
        type=int,
        default=None,
        help="输出图片质量 (1-100, 默认: 95)"
    )

    # OCR 参数
    ocr_group = parser.add_argument_group("OCR 配置", "OCR 识别参数")
    ocr_group.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="最大生成长度 (默认: 16384)"
    )
    ocr_group.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="生成温度 (默认: 0.0)"
    )
    ocr_group.add_argument(
        "--min-pixels",
        type=int,
        default=None,
        help="最小像素数 (默认: 200704)"
    )
    ocr_group.add_argument(
        "--max-pixels",
        type=int,
        default=None,
        help="最大像素数 (默认: 8294400)"
    )

    # 输出控制
    out_group = parser.add_argument_group("输出控制", "输出格式控制")
    out_group.add_argument(
        "--no-merge-tables",
        action="store_true",
        help="禁用跨页表格合并"
    )
    out_group.add_argument(
        "--filter-images",
        action="store_true",
        help="过滤图片标签 (不保存图片)"
    )
    out_group.add_argument(
        "--save-raw",
        action="store_true",
        help="保存原始每页输出"
    )
    out_group.add_argument(
        "--no-metadata",
        action="store_true",
        help="不添加元数据头"
    )

    # 断点续传
    resume_group = parser.add_argument_group("断点续传", "断点续传功能")
    resume_group.add_argument(
        "--resume",
        action="store_true",
        help="从断点继续处理"
    )

    # 日志和调试
    debug_group = parser.add_argument_group("日志和调试", "日志和调试选项")
    debug_group.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出模式"
    )
    debug_group.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式 (只输出错误)"
    )
    debug_group.add_argument(
        "--debug",
        action="store_true",
        help="调试模式 (显示详细错误信息)"
    )
    debug_group.add_argument(
        "--log-file",
        default=None,
        help="日志文件路径"
    )
    debug_group.add_argument(
        "--preview",
        action="store_true",
        help="显示结果预览"
    )

    return parser


# ============================================================
# 主函数
# ============================================================
def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 应用命令行参数覆盖
    if args.gpu_memory is not None:
        config["model"]["gpu_memory_utilization"] = args.gpu_memory
    if args.tensor_parallel is not None:
        config["model"]["tensor_parallel_size"] = args.tensor_parallel
    if args.max_model_len is not None:
        config["model"]["max_model_len"] = args.max_model_len

    if args.batch_size is not None:
        config["pdf"]["batch_size"] = args.batch_size
    if args.dpi is not None:
        config["pdf"]["dpi"] = args.dpi

    if args.max_image_size is not None:
        config["image"]["max_size"] = args.max_image_size
    if args.image_quality is not None:
        config["image"]["quality"] = args.image_quality

    if args.max_tokens is not None:
        config["ocr"]["max_tokens"] = args.max_tokens
    if args.temperature is not None:
        config["ocr"]["temperature"] = args.temperature
    if args.min_pixels is not None:
        config["ocr"]["min_pixels"] = args.min_pixels
    if args.max_pixels is not None:
        config["ocr"]["max_pixels"] = args.max_pixels

    if args.no_merge_tables:
        config["output"]["merge_tables"] = False
    if args.filter_images:
        config["output"]["filter_images"] = True
    if args.save_raw:
        config["output"]["save_raw"] = True
    if args.no_metadata:
        config["output"]["include_metadata"] = False

    # 日志级别
    if args.quiet:
        config["logging"]["level"] = "ERROR"
    elif args.verbose:
        config["logging"]["level"] = "DEBUG"
    elif args.debug:
        config["logging"]["level"] = "DEBUG"

    if args.log_file:
        config["logging"]["file"] = args.log_file

    # 设置日志
    logger = setup_logging(config)

    # 显示配置
    if args.dry_run or args.verbose:
        logger.info("当前配置:")
        logger.info(json.dumps(config, indent=2, ensure_ascii=False))
        if args.dry_run:
            logger.info("干运行模式，不实际处理")
            return

    # 检查输入文件
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        logger.error(f"输入文件不存在: {input_path}")
        sys.exit(1)

    # 创建处理器
    processor = MainProcessor(config, args)

    # 加载模型
    if not processor.load_model():
        sys.exit(1)

    # 根据模式处理
    if args.test:
        # 测试模式
        if input_path.suffix.lower() not in ['.png', '.jpg', '.jpeg']:
            logger.error("测试模式仅支持图片文件 (PNG/JPG)")
            sys.exit(1)
        success = processor.process_single_image(input_path)
    else:
        # PDF 模式
        if input_path.suffix.lower() != '.pdf':
            logger.error("非测试模式仅支持 PDF 文件")
            logger.error("如需处理图片，请使用 --test 参数")
            sys.exit(1)
        success = processor.process_pdf(input_path)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
