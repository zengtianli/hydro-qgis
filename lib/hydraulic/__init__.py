#!/usr/bin/env python3
"""
水利领域专用库

提供河流/流域编码映射、编码规范化工具等水利业务功能。
QGIS 相关配置通过 hydraulic.qgis_config 和 hydraulic.qgis_fields 访问。
"""

from .code_utils import (
    extract_dike_number,
    generate_dike_code,
    get_basin_code,
    get_basin_name,
    get_river_code,
    natural_sort_key,
    normalize_code,
)
from .config import (
    BASIN_NAME_TO_CODE,
    BASIN_NAME_TO_CODE_LONG,
    CHINESE_TO_PINYIN,
    COUNTY_TO_CITY,
    DISTRICT_NAME_TO_CODE,
    # 河流映射
    RIVER_CODE_MAPPING,
    RIVER_NAME_TO_CODE,
    RIVER_TO_BASIN,
)

__all__ = [
    # Config
    'RIVER_CODE_MAPPING',
    'RIVER_NAME_TO_CODE',
    'CHINESE_TO_PINYIN',
    'RIVER_TO_BASIN',
    'BASIN_NAME_TO_CODE',
    'BASIN_NAME_TO_CODE_LONG',
    'DISTRICT_NAME_TO_CODE',
    'COUNTY_TO_CITY',

    # Code Utils
    'normalize_code',
    'get_river_code',
    'get_basin_code',
    'get_basin_name',
    'generate_dike_code',
    'extract_dike_number',
    'natural_sort_key',
]
