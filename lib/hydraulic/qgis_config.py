#!/usr/bin/env python3
"""
QGIS 脚本统一配置

包含坐标系、字段映射、图层名称、处理参数等 QGIS 专用配置。
河流/流域映射从 hydraulic.config 统一获取。
"""

from .config import (
    CHINESE_TO_PINYIN,
    COUNTY_TO_CITY,
    RIVER_CODE_MAPPING,
    RIVER_NAME_TO_CODE,
    RIVER_TO_BASIN,
    get_city_from_county,
    get_river_name,
)

# ============ 坐标系配置 ============

TARGET_CRS = 'EPSG:4549'  # CGCS2000 / 3-degree Gauss-Kruger CM 120E
GEO_CRS = 'EPSG:4490'    # CGCS2000 地理坐标系


# ============ 默认值配置 ============

DEFAULT_TOWN = '未知'
DEFAULT_POLDER = 'UNKNOWN'
DEFAULT_GRID_ID = 0
DEFAULT_CITY = '未知市'
DEFAULT_COUNTY = '未知县'


# ============ 字段映射配置 ============

FIELD_MAPPING = {
    'dikeName': 'dike_name',
    'polderCode': 'polder_id',
    'subCode': 'river_code',
    'adcdCode': 'regioncode',
    'dsLength': 'ds_length',
    'SHAPE_Leng': 'Shape_length',
    'CITY': '所属市',
    'COUNTY': '所属县',
    'adcdName': '所属镇',
    'NAME': 'town',
    'code': 'polderId',
}

DM_ELEVATION_FIELDS = {
    'left_elev': '左岸',
    'right_elev': '右岸',
    'bottom_elev': '最低点',
}


# ============ 图层名称约定 ============

INPUT_LAYERS = {
    'river_center': 'hdzxx',
    'cross_section': 'dm',
    'dike': 'df',
    'grid': 'grid0',
    'town': 'town',
    'env': 'env',
    'house': 'house',
    'road': 'road',
    'vegetation': 'vegetation',
    'city_county': 'city_county',
}

OUTPUT_LAYERS = {
    'river_center_points': 'river_center_points',
    'river_cut_points': 'river_cut_points',
    'dm_lc': 'dm_LC',
    'river_center_zya': 'river_center_points_zya',
    'dike_sections': 'dike_sections',
    'dike_with_elevation': 'dike_sections_with_elevation',
    'dd': 'dd',
    'dd_fix': 'dd_fix',
    'grid_enriched': 'grid_enriched',
    'house_output': 'house_output',
    'road_output': 'road_output',
    'vegetation_output': 'vegetation_output',
    'baohu_output': 'baohu_output',
    'baohu': 'baohu',
}

LAYER_GROUPS = {
    'input': 'input',
    'process': 'process',
    'final': 'final',
    'standard': 'standard',
}


# ============ 处理参数配置 ============

RIVER_POINT_CONFIG = {
    'interval': 100,
    'offset': 50,
}

DIKE_CUT_CONFIG = {
    'max_distance': 500,
    'extend_start': 0,
    'extend_end': 2,
}

ELEVATION_CONFIG = {
    'max_distance': 500,
    'secondary_max_distance': 2000,
}

DM_LC_CONFIG = {
    'max_distance': 200,
}

DS_START_NUMBER = 20250001

BAOHU_CONFIG = {
    'grid_group': 'final',
}


# ============ 字段对齐配置 ============

ALIGN_LAYER_NAME_MAPPING = {
    'house_output': 'house',
    'road_output': 'road',
    'vegetation_output': 'vegetation',
    'grid_enriched': 'grid',
}

ALIGN_FIELD_NAME_MAPPING = {
    'grid': {'elevation': 'Bathymetry'},
    'vegetation': {'elevation': 'Bathymetry'},
    'road': {'length': 'Shape_Leng'},
    'house': {'elevation': 'Bathymetry'},
}

ALIGN_SOURCE_GROUP = 'standard'
ALIGN_TARGET_GROUP = 'process'


# ============ 标准字段定义 ============

# QGIS 专用：需要在 QGIS 环境中才能使用
try:
    from qgis.PyQt.QtCore import QVariant

    STANDARD_DIKE_FIELDS = [
        ("wkt_geom", QVariant.String, 0, 0, "WKT几何"),
        ("OBJECTID", QVariant.Int, 10, 0, "对象ID"),
        ("dike_code", QVariant.String, 50, 0, "堤防编码"),
        ("dike_name", QVariant.String, 100, 0, "堤防名称"),
        ("zya", QVariant.String, 10, 0, "左右岸"),
        ("polder_name", QVariant.String, 100, 0, "圩区名称"),
        ("polder_id", QVariant.String, 50, 0, "圩区编码"),
        ("所属市", QVariant.String, 50, 0, "所属市"),
        ("所属县", QVariant.String, 50, 0, "所属县"),
        ("所属镇", QVariant.String, 50, 0, "所属镇"),
        ("river_name", QVariant.String, 100, 0, "河流名称"),
        ("LC", QVariant.Int, 10, 0, "里程"),
        ("river_code", QVariant.String, 50, 0, "河流编码"),
        ("regioncode", QVariant.String, 50, 0, "区域编码"),
        ("ds_name", QVariant.String, 50, 0, "堤段名称"),
        ("ds_code", QVariant.String, 50, 0, "堤段编码"),
        ("lgtd", QVariant.Double, 20, 8, "经度"),
        ("lttd", QVariant.Double, 20, 8, "纬度"),
        ("drz", QVariant.Double, 20, 6, "堤顶高程（设计）"),
        ("grz", QVariant.Double, 20, 6, "堤顶高程（规划）"),
        ("wrz", QVariant.Double, 20, 6, "堤顶高程（现状）"),
        ("ddgc", QVariant.Double, 20, 6, "堤顶高程"),
        ("ds_length", QVariant.Double, 20, 6, "堤段长度"),
        ("Shape_length", QVariant.Double, 20, 12, "几何长度"),
    ]

    NULL_FIELDS = ['drz', 'grz', 'wrz']

except ImportError:
    # 非 QGIS 环境：提供占位定义
    STANDARD_DIKE_FIELDS = []
    NULL_FIELDS = ['drz', 'grz', 'wrz']


# ============ 辅助函数（QGIS 专用，委托给 config） ============

get_river_code = None  # 使用 hydraulic.code_utils.get_river_code 代替

# 重新导出供 qgis 脚本使用
__all__ = [
    'RIVER_CODE_MAPPING', 'RIVER_NAME_TO_CODE', 'CHINESE_TO_PINYIN',
    'RIVER_TO_BASIN', 'COUNTY_TO_CITY',
    'get_river_name', 'get_city_from_county',
    'TARGET_CRS', 'GEO_CRS',
    'DEFAULT_TOWN', 'DEFAULT_POLDER', 'DEFAULT_GRID_ID',
    'DEFAULT_CITY', 'DEFAULT_COUNTY',
    'FIELD_MAPPING', 'DM_ELEVATION_FIELDS',
    'INPUT_LAYERS', 'OUTPUT_LAYERS', 'LAYER_GROUPS',
    'RIVER_POINT_CONFIG', 'DIKE_CUT_CONFIG', 'ELEVATION_CONFIG',
    'DM_LC_CONFIG', 'DS_START_NUMBER', 'BAOHU_CONFIG',
    'ALIGN_LAYER_NAME_MAPPING', 'ALIGN_FIELD_NAME_MAPPING',
    'ALIGN_SOURCE_GROUP', 'ALIGN_TARGET_GROUP',
    'STANDARD_DIKE_FIELDS', 'NULL_FIELDS',
]
