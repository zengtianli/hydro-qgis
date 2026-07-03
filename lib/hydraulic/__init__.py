#!/usr/bin/env python3
"""
水利领域专用库（hydro-qgis 版）

只保留 QGIS 相关配置，通过子模块直接访问：
    from hydraulic.qgis_config import ...
    from hydraulic.qgis_fields import ...

历史的 code_utils / config 模块（河流/流域编码映射）位于
~/Dev/services/hydro-risk/lib/hydraulic/，
本仓库不依赖它们 — 故 __init__.py 不做任何 re-export。
"""
