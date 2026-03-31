# hydro-qgis — 13 步水利 GIS 管线处理工具

## Quick Reference

| 项目 | 路径/值 |
|------|---------|
| 项目根 | `/Users/tianli/Dev/hydro-qgis/` |
| Web 入口 | `app.py` (Streamlit) |
| Pipeline 脚本 | `pipeline/01_*.py` → `pipeline/13_*.py` |
| 批量工具 | `pipeline/99_batch_export_layers.py` |
| 公用库 | `_util/qgis_util.py` |
| Shell 编排 | `scripts/run_pipeline.sh`（全流程）、`scripts/run_script.sh`（单步） |

## 常用命令

```bash
cd /Users/tianli/Dev/hydro-qgis

# 启动 Web UI
streamlit run app.py

# 全流程运行
bash scripts/run_pipeline.sh

# 单步运行（示例：step 04）
bash scripts/run_script.sh pipeline/04_assign_elevation_to_dike.py

# 直接执行单个 pipeline 脚本
python3 pipeline/01_generate_river_points.py

# 配置检查
python3 tools/check_config.py
python3 tools/check_mask_config.py
```

## Pipeline 步骤

| 步骤 | 文件 | 功能 |
|------|------|------|
| 01 | `generate_river_points.py` | 生成河道点 |
| 02 | `assign_lc_to_cross_sections.py` | 断面赋里程 |
| 03 | `cut_dike_sections.py` | 堤防分段裁剪 |
| 04 | `assign_elevation_to_dike.py` | 堤顶高程赋值 |
| 05 | `align_dike_fields.py` | 堤防字段对齐 |
| 06 | `fix_river_name.py` | 河名修正 |
| 07 | `copy_dd_endpoints_to_df.py` | 端点复制 |
| 08–13 | `enrich/house/road/veg/baohu/align` | 专题图层生成 |
| 99 | `batch_export_layers.py` | 批量导出 |

## 目录结构

```
pipeline/   # 13 步有序脚本，可独立运行
tools/      # 独立实用工具（导出、过滤、掩膜等）
_util/      # 公共库：qgis_util.py + listener
scripts/    # Shell 编排入口
lib/        # 水利领域公共模块（链接自 ~/Dev/scripts/lib/hydraulic）
docs/       # 截图文档
```

## 开发规范

- 新增 pipeline 步骤：在 `pipeline/` 下按 `NN_功能名.py` 命名，导入 `_util/qgis_util.py`
- 新增独立工具：放 `tools/`，无需编号
- 项目配置：`_project.yaml`（输入图层路径、字段映射等）
- 运行环境需 QGIS Python 绑定（`qgis.core`），本地调试用 `_util/test_qgis_util.py`
