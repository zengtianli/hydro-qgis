# hydro-qgis — 13 步水利 GIS 管线处理工具

> 基于 **QGIS Python 绑定** 的空间数据处理 Shell Pipeline。**不是** Streamlit / Web 应用 — 通过 `QGIS.app --code` 在 QGIS 进程内跑脚本。

## Quick Reference

| 项目 | 路径/值 |
|------|---------|
| 项目根 | `/Users/tianli/Dev/labs/hydro-qgis/` |
| Python | `>=3.12`（实际锁 `.python-version=3.13`）+ uv 管理（已弃 conda/miniforge，迁移于 `4e1f895`） |
| 入口（运行时） | `QGIS.app --code pipeline/NN_*.py` 由 shell 编排（**非 streamlit**） |
| Pipeline 脚本 | `pipeline/01_*.py` … `pipeline/13_*.py` + `99_batch_export_layers.py` |
| 公用库 | `_util/qgis_util.py`（QGIS API 封装） + `_util/qgis_listener.py` |
| 领域库 | `lib/hydraulic/`（真目录，含 `qgis_config.py / qgis_fields.py`，**非 symlink**） |
| 项目配置 | `_project.yaml`（type=hydraulic, entry=scripts/run_pipeline.sh） |
| Shell 编排 | `scripts/run_pipeline.sh`（全流程）/ `run_script.sh`（单步）/ `run_11.sh / run_12.sh / run_13.sh`（独立步骤快捷） |

## 常用命令

```bash
cd ~/Dev/labs/hydro-qgis

# 全流程（QGIS 进程内执行所有 pipeline）
bash scripts/run_pipeline.sh           # 全部
bash scripts/run_pipeline.sh 1-5       # 范围
bash scripts/run_pipeline.sh 4         # 单步
bash scripts/run_pipeline.sh -l        # 列脚本

# 单步运行（任意路径）
bash scripts/run_script.sh pipeline/04_assign_elevation_to_dike.py

# tools/ 下独立工具（普通 Python，不需要 QGIS 进程）
uv run python tools/check_config.py
uv run python tools/check_mask_config.py
uv run python tools/extract_points_in_polygons.py

# 依赖同步（uv workspace 外，本 repo 独立 .venv）
uv sync
```

> ⚠️ `scripts/run_pipeline.sh` 内部 `SCRIPTS=` 数组的脚本编号与文件名 **可能与 `pipeline/` 当前实际不一致**（旧版用 `01.5_/04.5_` 现已重新编号 01-13）。改 pipeline 时务必同步更新该数组，或改用 `run_script.sh` 直跑文件名。

## Pipeline 步骤（13 步 + 99）

| 步骤 | 文件 | 功能 |
|------|------|------|
| 01 | `generate_river_points.py` | 生成河道中心点/切割点 |
| 02 | `assign_lc_to_cross_sections.py` | 断面赋里程 + 高程插值 |
| 03 | `cut_dike_sections.py` | 堤防分段裁剪生成堤段 |
| 04 | `assign_elevation_to_dike.py` | 堤段赋高程 + 市县信息 |
| 05 | `align_dike_fields.py` | 堤防 24 字段对齐 |
| 06 | `fix_river_name.py` | 河流名称修正 |
| 07 | `copy_dd_endpoints_to_df.py` | 端点复制（dd → df） |
| 08 | `enrich_grid_layer.py` | 网格图层增强 |
| 09 | `generate_house_layer.py` | 房屋图层生成 |
| 10 | `generate_road_layer.py` | 道路图层生成 |
| 11 | `generate_vegetation_layer.py` | 植被图层生成 |
| 12 | `generate_baohu_layer.py` | 保护对象层生成 |
| 13 | `align_output_fields.py` | 输出字段对齐 |
| 99 | `batch_export_layers.py` | 批量导出全图层 |

## 目录结构

```
pipeline/   # 13 步有序脚本（01-13）+ 99 批量导出，可独立运行
tools/      # 10 个独立实用工具（导出、过滤、掩膜、字段补、布局导出等）
_util/      # 公共库：qgis_util / qgis_listener + 对应 test_*.py
lib/        # hydraulic 领域共享（qgis_config + qgis_fields）
scripts/    # Shell 编排入口（run_pipeline / run_script / run_NN / run.sh）
docs/       # 截图与示例图（README.md 引用源）
_project.yaml  # 站群项目元数据（被 stack.yaml 消费）
```

## tools/ 列表（按需查）

`add_city_field`、`check_config`、`check_mask_config`、`create_mask_layers`、`export_map_layout`、`export_selected_layers`、`extract_points_in_polygons`、`filter_by_distance`、`filter_by_field`、`update_dd_elevation`。无编号约束，命名即用途。

## 开发规范

- **新增 pipeline 步骤**：`pipeline/NN_功能名.py`（NN 两位数字保序），导入 `from _util.qgis_util import *`
- **新增独立工具**：放 `tools/`，无编号；纯 Python（不进 QGIS 进程）则用 `uv run python tools/x.py`
- **领域常量**：字段名 / 配置写 `lib/hydraulic/qgis_fields.py | qgis_config.py`，禁止散落 pipeline
- **依赖管理**：改 deps → 改 `pyproject.toml` → `uv sync`（本 repo 独立 venv，不在 ~/Dev workspace 共享 venv 内）
- **`requirements.txt`** 仅作旧环境兼容兜底，权威以 `pyproject.toml + uv.lock` 为准
- **测试**：`_util/test_qgis_util.py` 走原生 Python（非 QGIS 进程）做轻量调试

## 运行环境

- macOS + `/Applications/QGIS.app/Contents/MacOS/QGIS`（`run_pipeline.sh` 硬编码该路径）
- pipeline 脚本通过 `QGIS --code <script>` 加载，需要 `qgis.core` 绑定（QGIS 自带 Python）
- tools/ 下的非 QGIS 脚本走本 repo 独立 `.venv`（geopandas / shapely / fiona / pandas / openpyxl）

## 路径与迁移

- 数据路径迁移走 `~/Dev/paths.yaml` SSOT，最近一次批量重写见 `08f9712`（apply paths.yaml migrations map）
- 数据源（zdwp 等）已从 `Downloads/` 迁到 `Work/`（`b855d47`）— 引用裸路径前先查 `paths.yaml`
