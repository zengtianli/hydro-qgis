# Hydro QGIS

水利 QGIS 空间处理管线 — 河流断面生成、堤防裁剪、GIS 数据处理

## Structure

- `pipeline/` — 编号式处理步骤（01-13）
- `tools/` — 独立工具脚本
- `_util/` — 通用工具函数
- `scripts/` — Shell 编排脚本
- `lib/hydraulic/` — 水利编码与 QGIS 配置

## Usage

```bash
pip install -r requirements.txt
python pipeline/01_generate_river_points.py
```
