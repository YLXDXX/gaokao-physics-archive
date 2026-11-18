# tools/ocr_pipeline

统一 OCR 识别转换包：**OvisOCR3 + PaddleOCR-VL**，保留 Markdown 与版面源数据
（bbox / category / content），支持分批、断点续跑、Paddle 分块与自动启停。

完整说明见项目根目录 **`OCR识别转换流程说明.md`**。

## 最短入口

```bash
# 单份（含 Ovis，使用 ovis_ocr 环境）
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline run \
    -i <PDF> -o <处理目录> --auto-serve

# 批量（中断后重复同一命令即可续跑）
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline batch \
    --root 课程材料处理 --auto-serve

# 状态 / 计划
python3 -m tools.ocr_pipeline status --root 课程材料处理
python3 -m tools.ocr_pipeline plan   --root 课程材料处理

# 用已保存的 bbox 高清重裁（不重跑 OCR）
python3 -m tools.ocr_pipeline crops -d <处理目录> --dpi 600
```

## 测试

```bash
python3 -m unittest tools.test_ocr_pipeline -v
```
