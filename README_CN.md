        # hydro-qgis

        [English](README.md) | **中文**

        13 步 QGIS 水利工程 GIS 流水线——横断面生成、堤防裁剪与空间处理。

        [![Python 3.9+](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge)](https://python.org)
        [![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

        ---

        ![hydro-qgis demo](docs/screenshots/demo.svg)

        ---

        ## 功能一览

        | 功能 | 说明 |
        |------|------|
        | **河道横断面生成** | 从中心线和 DEM 自动生成横断面 |
| **堤防裁剪** | 沿堤线裁剪空间要素 |
| **13 步编号流水线** | 顺序脚本，每步可独立运行 |
| **工具函数库** | 可复用的水利专项 QGIS 辅助函数 |
| **Shell 编排脚本** | 通过 Shell 脚本运行完整流水线或单步 |

        ## 安装

        ```bash
        git clone https://github.com/zengtianli/hydro-qgis.git
cd hydro-qgis
pip install -r requirements.txt
        ```

        ## 快速开始

        ```bash
        streamlit run app.py
        ```

        ## 环境要求

        - Python 3.9+
        - 详见 requirements.txt

        ## License

        MIT
