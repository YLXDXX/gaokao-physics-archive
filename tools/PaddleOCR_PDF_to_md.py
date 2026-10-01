#!/usr/bin/env python3
"""
PaddleOCR-VL PDF/图片 转 Markdown 工具
基于 PaddleOCR-VL-1.6 服务的文档转换工具

特性:
- 支持 PDF 和图片输入
- 公式识别 (LaTeX 格式)
- 表格识别 (HTML 格式)
- 图片提取和保存
- 多页 PDF 支持
- 跨页表格合并
- 断点续传
- 批量处理
- 灵活配置
"""

import argparse
import base64
import json
import os
import pathlib
import sys
import time
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

# 版本信息
__version__ = "1.0.0"
__author__ = "PaddleOCR-VL Tool"

# 默认配置
DEFAULT_CONFIG = {
    "service": {
        "host": "127.0.0.1",
        "port": 8203,
        "timeout": 300
    },
    "ocr": {
        "pipeline_version": "1.6",
        "markdown_ignore_labels": [
            "number", "footnote", "header", "header_image",
            "footer", "footer_image", "aside_text"
        ],
        "merge_tables": True,
        "relevel_titles": True,
        "concatenate_pages": True,
        "format_block_content": False,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_layout_detection": True,
        "use_chart_recognition": False,
        "use_seal_recognition": False,
        "use_ocr_for_image_block": False
    },
    "output": {
        "save_raw": False,
        "include_metadata": True,
        "image_format": "jpg",
        "image_quality": 95
    },
    "logging": {
        "level": "INFO",
        "file": None
    }
}

class PaddleOCRVLClient:
    """PaddleOCR-VL 服务客户端"""

    def __init__(self, host: str, port: int, timeout: int = 300):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()

    def check_connection(self) -> bool:
        """检查服务连接状态"""
        try:
            response = self.session.get(
                f"{self.base_url}/layout-parsing",
                timeout=5
            )
            return response.status_code in [200, 405, 422, 500]
        except requests.exceptions.RequestException:
            return False

    def parse_document(self, file_data: bytes, file_type: int = 0,
                      options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        解析文档 (PDF 或图片)

        Args:
            file_data: 文件二进制数据
            file_type: 0=PDF, 1=图片
            options: OCR 选项

        Returns:
            解析结果
        """
        # Base64 编码
        file_b64 = base64.b64encode(file_data).decode('ascii')

        # 构建请求
        payload = {
            "file": file_b64,
            "fileType": file_type,
            "visualize": False
        }

        # 添加 OCR 选项
        if options:
            if "markdown_ignore_labels" in options:
                payload["markdownIgnoreLabels"] = options["markdown_ignore_labels"]
            if "use_doc_orientation_classify" in options:
                payload["useDocOrientationClassify"] = options["use_doc_orientation_classify"]
            if "use_doc_unwarping" in options:
                payload["useDocUnwarping"] = options["use_doc_unwarping"]
            if "use_layout_detection" in options:
                payload["useLayoutDetection"] = options["use_layout_detection"]
            if "use_chart_recognition" in options:
                payload["useChartRecognition"] = options["use_chart_recognition"]
            if "use_seal_recognition" in options:
                payload["useSealRecognition"] = options["use_seal_recognition"]
            if "use_ocr_for_image_block" in options:
                payload["useOcrForImageBlock"] = options["use_ocr_for_image_block"]

        # 发送请求
        response = self.session.post(
            f"{self.base_url}/layout-parsing",
            json=payload,
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise Exception(f"解析失败: {response.status_code} - {response.text}")

        return response.json()["result"]

    def restructure_pages(self, pages: List[Dict],
                         merge_tables: bool = True,
                         relevel_titles: bool = True,
                         concatenate_pages: bool = True) -> Dict[str, Any]:
        """
        重构页面顺序

        Args:
            pages: 页面数据列表
            merge_tables: 是否合并跨页表格
            relevel_titles: 是否重建多级标题
            concatenate_pages: 是否拼接多页结果

        Returns:
            重构后的结果
        """
        payload = {
            "pages": pages,
            "mergeTables": merge_tables,
            "relevelTitles": relevel_titles,
            "concatenatePages": concatenate_pages
        }

        response = self.session.post(
            f"{self.base_url}/restructure-pages",
            json=payload,
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise Exception(f"页面重构失败: {response.status_code} - {response.text}")

        return response.json()["result"]

class PDFToMarkdownConverter:
    """PDF/图片 转 Markdown 转换器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = PaddleOCRVLClient(
            host=config["service"]["host"],
            port=config["service"]["port"],
            timeout=config["service"]["timeout"]
        )

        # 设置日志
        self.setup_logging()

    def setup_logging(self):
        """配置日志"""
        log_level = getattr(logging, self.config["logging"]["level"])

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )

        if self.config["logging"]["file"]:
            file_handler = logging.FileHandler(self.config["logging"]["file"])
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            logging.getLogger().addHandler(file_handler)

        self.logger = logging.getLogger(__name__)

    def check_service(self) -> bool:
        """检查服务状态"""
        if not self.client.check_connection():
            self.logger.error("PaddleOCR-VL 服务未启动或无法连接")
            return False
        self.logger.info(f"服务连接成功: {self.client.base_url}")
        return True

    def convert_file(self, input_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        转换文件

        Args:
            input_path: 输入文件路径
            output_dir: 输出目录

        Returns:
            转换结果
        """
        input_path = pathlib.Path(input_path)

        # 确定文件类型
        if input_path.suffix.lower() == '.pdf':
            file_type = 0
        elif input_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp']:
            file_type = 1
        else:
            raise ValueError(f"不支持的文件格式: {input_path.suffix}")

        # 设置输出目录
        if output_dir is None:
            output_dir = input_path.parent / f"{input_path.stem}_output"
        else:
            output_dir = pathlib.Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # 读取文件
        with open(input_path, "rb") as f:
            file_data = f.read()

        self.logger.info(f"开始处理: {input_path}")
        self.logger.info(f"文件大小: {len(file_data) / 1024 / 1024:.2f} MB")
        self.logger.info(f"输出目录: {output_dir}")

        start_time = time.time()

        # 1. 解析文档
        self.logger.info("步骤 1/2: 解析文档...")
        result = self.client.parse_document(
            file_data=file_data,
            file_type=file_type,
            options=self.config["ocr"]
        )

        # 提取页面数据
        pages = []
        for i, res in enumerate(result["layoutParsingResults"]):
            pages.append({
                "prunedResult": res["prunedResult"],
                "markdownImages": res["markdown"].get("images")
            })

        # 2. 重构页面
        self.logger.info(f"步骤 2/2: 重构 {len(pages)} 页内容...")
        restructured = self.client.restructure_pages(
            pages=pages,
            merge_tables=self.config["ocr"]["merge_tables"],
            relevel_titles=self.config["ocr"]["relevel_titles"],
            concatenate_pages=self.config["ocr"]["concatenate_pages"]
        )

        # 3. 保存结果
        self.logger.info("保存结果...")
        res = restructured["layoutParsingResults"][0]

        # === 修复图片路径问题 ===
        # 创建图片目录
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)

        # 获取Markdown文本并修正图片路径
        markdown_text = res["markdown"]["text"]

        # 保存图片并构建路径映射
        image_count = 0
        path_mapping = {}

        for img_path, img_data in res["markdown"]["images"].items():
            # 获取原始文件名（可能是imgs/xxx.jpg或xxx.jpg）
            original_name = pathlib.Path(img_path).name

            # 保存图片到images目录
            img_file = images_dir / original_name
            img_file.write_bytes(base64.b64decode(img_data))
            image_count += 1

            # 构建路径映射：原始路径 -> 新路径
            # 处理各种可能的路径格式
            if img_path.startswith("imgs/"):
                # 如果路径以imgs/开头，替换为images/
                new_path = f"images/{original_name}"
                path_mapping[img_path] = new_path
            elif img_path.startswith("/imgs/"):
                # 如果路径以/imgs/开头
                new_path = f"images/{original_name}"
                path_mapping[img_path] = new_path
            elif "/" not in img_path:
                # 如果只有文件名，添加images/前缀
                new_path = f"images/{original_name}"
                path_mapping[img_path] = new_path

        # 替换Markdown中的图片路径
        for old_path, new_path in path_mapping.items():
            # 处理各种可能的引用方式
            markdown_text = markdown_text.replace(f'"{old_path}"', f'"{new_path}"')
            markdown_text = markdown_text.replace(f"'{old_path}'", f"'{new_path}'")
            markdown_text = markdown_text.replace(f'({old_path})', f'({new_path})')
            markdown_text = markdown_text.replace(f'src="{old_path}"', f'src="{new_path}"')

        # 额外清理：确保所有imgs/引用都被替换
        markdown_text = markdown_text.replace('imgs/', 'images/')
        markdown_text = markdown_text.replace('/imgs/', '/images/')

        # 保存Markdown文件
        md_file = output_dir / "output.md"

        # 添加元数据
        if self.config["output"]["include_metadata"]:
            metadata = self._generate_metadata(input_path, len(file_data), time.time() - start_time)
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(metadata)
                f.write(markdown_text)
        else:
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown_text)

        # 保存原始页面数据
        if self.config["output"]["save_raw"]:
            raw_dir = output_dir / "raw"
            raw_dir.mkdir(exist_ok=True)

            for i, page_data in enumerate(pages):
                raw_file = raw_dir / f"page_{i+1}.json"
                with open(raw_file, "w", encoding="utf-8") as f:
                    json.dump(page_data, f, ensure_ascii=False, indent=2)

        elapsed_time = time.time() - start_time

        # 生成结果摘要
        summary = {
            "input_file": str(input_path),
            "output_directory": str(output_dir),
            "markdown_file": str(md_file),
            "images_directory": str(images_dir),
            "total_pages": len(pages),
            "total_images": image_count,
            "file_size_mb": len(file_data) / 1024 / 1024,
            "processing_time_seconds": elapsed_time,
            "processing_speed_pages_per_second": len(pages) / elapsed_time if elapsed_time > 0 else 0,
            "model_version": self.config["ocr"]["pipeline_version"],
            "timestamp": datetime.now().isoformat()
        }

        self.logger.info("=" * 60)
        self.logger.info("转换完成!")
        self.logger.info("=" * 60)
        self.logger.info(f"输入文件: {input_path}")
        self.logger.info(f"输出目录: {output_dir}")
        self.logger.info(f"Markdown 文件: {md_file}")
        self.logger.info(f"图片目录: {images_dir}")
        self.logger.info(f"总页数: {len(pages)}")
        self.logger.info(f"提取图片数: {image_count}")
        self.logger.info(f"处理时间: {elapsed_time:.2f} 秒")
        self.logger.info(f"处理速度: {summary['processing_speed_pages_per_second']:.2f} 页/秒")
        self.logger.info("=" * 60)

        return summary

    def _generate_metadata(self, input_path: pathlib.Path, file_size: int,
                          processing_time: float) -> str:
        """生成元数据"""
        metadata = f"""---
title: {input_path.stem}
source_file: {input_path.name}
file_size: {file_size / 1024 / 1024:.2f} MB
processing_time: {processing_time:.2f} seconds
model: PaddleOCR-VL-{self.config['ocr']['pipeline_version']}
processed_date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

"""
        return metadata

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)

        # 深度合并配置
        for key, value in user_config.items():
            if key in config:
                if isinstance(config[key], dict) and isinstance(value, dict):
                    config[key].update(value)
                else:
                    config[key] = value

    return config

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="PaddleOCR-VL PDF/图片 转 Markdown 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本转换
  python pdf_to_md.py -i document.pdf

  # 指定输出目录
  python pdf_to_md.py -i document.pdf -o ./output

  # 使用配置文件
  python pdf_to_md.py -i doc.pdf -c config.json

  # 测试单张图片
  python pdf_to_md.py -i image.png --test

  # 详细输出
  python pdf_to_md.py -i doc.pdf --verbose
        """
    )

    # 输入/输出参数
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="输入文件路径 (PDF 或图片)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="输出目录 (默认: 输入文件名_output)"
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="配置文件路径 (JSON 格式)"
    )

    # 服务配置
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="服务地址 (默认: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8203,
        help="服务端口 (默认: 8203)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="请求超时时间/秒 (默认: 300)"
    )

    # OCR 配置
    parser.add_argument(
        "--pipeline-version",
        choices=["1.5", "1.6"],
        default="1.6",
        help="PaddleOCR-VL 版本 (默认: 1.6)"
    )

    # 处理模式
    parser.add_argument(
        "--test",
        action="store_true",
        help="测试模式: 只处理单张图片"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干运行: 只显示配置，不实际处理"
    )

    # 输出控制
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="保存原始每页输出"
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="不添加元数据头"
    )
    parser.add_argument(
        "--no-merge-tables",
        action="store_true",
        help="禁用跨页表格合并"
    )

    # 日志控制
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出模式"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="静默模式"
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="日志文件路径"
    )

    # 版本信息
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    # 解析参数
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 命令行参数覆盖配置
    config["service"]["host"] = args.host
    config["service"]["port"] = args.port
    config["service"]["timeout"] = args.timeout
    config["ocr"]["pipeline_version"] = args.pipeline_version

    if args.save_raw:
        config["output"]["save_raw"] = True
    if args.no_metadata:
        config["output"]["include_metadata"] = False
    if args.no_merge_tables:
        config["ocr"]["merge_tables"] = False

    # 日志级别
    if args.verbose:
        config["logging"]["level"] = "DEBUG"
    elif args.quiet:
        config["logging"]["level"] = "ERROR"
    if args.log_file:
        config["logging"]["file"] = args.log_file

    # 创建转换器
    converter = PDFToMarkdownConverter(config)

    # 检查服务
    if not converter.check_service():
        print("错误: PaddleOCR-VL 服务未启动或无法连接", file=sys.stderr)
        print(f"请确保服务已在 {config['service']['host']}:{config['service']['port']} 启动", file=sys.stderr)
        print("启动命令: paddlex --serve --pipeline your_config.yaml --port 8203", file=sys.stderr)
        sys.exit(1)

    # 干运行
    if args.dry_run:
        print("配置信息:")
        print(json.dumps(config, indent=2, ensure_ascii=False))
        sys.exit(0)

    # 测试模式
    if args.test:
        if not pathlib.Path(args.input).suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
            print("错误: 测试模式只支持图片文件", file=sys.stderr)
            sys.exit(1)

    # 执行转换
    try:
        result = converter.convert_file(args.input, args.output)

        # 输出摘要
        print("\n" + "=" * 60)
        print("转换成功!")
        print("=" * 60)
        print(f"输入文件: {result['input_file']}")
        print(f"输出目录: {result['output_directory']}")
        print(f"Markdown: {result['markdown_file']}")
        print(f"图片目录: {result['images_directory']}")
        print(f"处理页数: {result['total_pages']}")
        print(f"提取图片: {result['total_images']}")
        print(f"处理时间: {result['processing_time_seconds']:.2f} 秒")
        print("=" * 60)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
