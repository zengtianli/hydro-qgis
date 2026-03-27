#!/usr/bin/env python3
"""
QGIS 图层字段规格定义

定义所有 QGIS 图层的输入/输出字段，用于：
1. 文档生成 - 自动在脚本 docstring 中显示字段说明
2. 运行时验证 - 检查输入图层是否包含必需字段
"""

# ============ 输入图层字段规格 ============

INPUT_LAYER_FIELDS = {
    'hdzxx': {
        'name': '河流中心线',
        'type': 'LineString',
        'required_fields': [],
        'optional_fields': ['*'],
        'description': '河流中心线图层，任意字段均可',
    },

    'dm': {
        'name': '断面',
        'type': 'Point',
        'required_fields': ['左岸', '右岸', '最低点'],
        'optional_fields': [],
        'description': '断面高程数据点，包含左右岸和河底高程',
        'field_details': {
            '左岸': '左岸高程 (m)',
            '右岸': '右岸高程 (m)',
            '最低点': '河底高程 (m)',
        },
    },

    'df': {
        'name': '堤防线',
        'type': 'LineString',
        'required_fields': ['zya'],
        'optional_fields': ['dikeName', 'polderCode'],
        'description': '堤防线图层',
        'field_details': {
            'zya': '岸别 (L=左岸, R=右岸)',
            'dikeName': '堤防名称',
            'polderCode': '圩区编码',
        },
    },

    'river_cut_points': {
        'name': '河段切割点',
        'type': 'Point',
        'required_fields': ['LC'],
        'optional_fields': [],
        'description': '用于切割堤防的切割点 (LC=50,150,250...)',
        'field_details': {
            'LC': '里程 (m)，从河流起点计算',
        },
    },

    'river_center_points': {
        'name': '河段中心点',
        'type': 'Point',
        'required_fields': ['LC'],
        'optional_fields': [],
        'description': '河段中心点 (LC=0,100,200...)',
        'field_details': {
            'LC': '里程 (m)，从河流起点计算',
        },
    },

    'river_center_points_zya': {
        'name': '河段中心点（带高程）',
        'type': 'Point',
        'required_fields': ['LC', 'zagc', 'yagc'],
        'optional_fields': ['hdgc'],
        'description': '河段中心点，包含左右岸高程（由 01.5 脚本生成）',
        'field_details': {
            'LC': '里程 (m)',
            'zagc': '左岸高程 (m)',
            'yagc': '右岸高程 (m)',
            'hdgc': '河底高程 (m)',
        },
    },

    'dike_sections': {
        'name': '堤段',
        'type': 'LineString',
        'required_fields': ['zya'],
        'optional_fields': ['dikeName', 'polderCode', 'LC'],
        'description': '切割后的堤段（由 02 脚本生成）',
        'field_details': {
            'zya': '岸别 (L=左岸, R=右岸)',
            'dikeName': '堤防名称（继承自 df）',
            'polderCode': '圩区编码（继承自 df）',
            'LC': '里程 (m)',
        },
    },

    'dike_sections_with_elevation': {
        'name': '堤段（带高程）',
        'type': 'LineString',
        'required_fields': ['zya', 'ddgc', '所属市', '所属县'],
        'optional_fields': ['LC', 'dikeName'],
        'description': '带高程和行政区划的堤段（由 03 脚本生成）',
        'field_details': {
            'zya': '岸别 (L=左岸, R=右岸)',
            'ddgc': '堤顶高程 (m)',
            '所属市': '所属地级市',
            '所属县': '所属县/区',
            'LC': '里程 (m)',
        },
    },

    'dd': {
        'name': '堤段（标准24字段）',
        'type': 'LineString',
        'required_fields': ['river_code', 'river_name'],
        'optional_fields': [],
        'description': '标准化后的堤段图层（24个字段，由 04 脚本生成）',
        'field_details': {
            'river_code': '河流编码 (如 HX, SX, GZX)',
            'river_name': '河流名称 (如 华溪, 熟溪)',
        },
    },

    'city_county': {
        'name': '市县区划',
        'type': 'Polygon',
        'required_fields': ['CITY', 'COUNTY'],
        'optional_fields': [],
        'description': '市县行政区划面图层',
        'field_details': {
            'CITY': '地级市名称',
            'COUNTY': '县/区名称',
        },
    },
}


# ============ 输出图层字段规格 ============

OUTPUT_LAYER_FIELDS = {
    'river_center_points': {
        'name': '河段中心点',
        'type': 'Point',
        'inherit_from': 'hdzxx',
        'add_fields': ['LC'],
        'description': '河段中心点 (LC=0,100,200...)',
        'field_details': {
            'LC': '里程 (m)，从河流起点计算',
        },
    },

    'river_cut_points': {
        'name': '河段切割点',
        'type': 'Point',
        'inherit_from': 'hdzxx',
        'add_fields': ['LC'],
        'description': '河段切割点 (LC=50,150,250...)',
        'field_details': {
            'LC': '里程 (m)，偏移50m',
        },
    },

    'dm_LC': {
        'name': '断面（带LC）',
        'type': 'Point',
        'inherit_from': 'dm',
        'add_fields': ['LC', 'longitude', 'latitude'],
        'description': '断面数据 + 里程 + 经纬度',
        'field_details': {
            'LC': '里程 (m)，从最近中心点获取',
            'longitude': '经度 (度)',
            'latitude': '纬度 (度)',
        },
    },

    'river_center_points_zya': {
        'name': '河段中心点（带高程）',
        'type': 'Point',
        'inherit_from': 'river_center_points',
        'add_fields': ['zagc', 'yagc', 'hdgc'],
        'description': '河段中心点 + 左右岸高程（从断面插值）',
        'field_details': {
            'zagc': '左岸高程 (m)，从断面插值',
            'yagc': '右岸高程 (m)，从断面插值',
            'hdgc': '河底高程 (m)，从断面插值',
        },
    },

    'dike_sections': {
        'name': '堤段',
        'type': 'LineString',
        'inherit_from': 'df',
        'add_fields': [],
        'description': '切割后的堤段，继承堤防所有属性',
    },

    'dike_sections_with_elevation': {
        'name': '堤段（带高程）',
        'type': 'LineString',
        'inherit_from': 'dike_sections',
        'add_fields': ['ddgc', '所属市', '所属县'],
        'description': '堤段 + 堤顶高程 + 行政区划',
        'field_details': {
            'ddgc': '堤顶高程 (m)，根据 zya 选择 zagc/yagc',
            '所属市': '地级市名称（空间连接）',
            '所属县': '县/区名称（空间连接）',
        },
    },

    'dd': {
        'name': '堤段（标准24字段）',
        'type': 'LineString',
        'inherit_from': None,
        'standard_fields': [
            'wkt_geom', 'OBJECTID', 'dike_code', 'dike_name', 'zya',
            'polder_name', 'polder_id', '所属市', '所属县', '所属镇',
            'river_name', 'LC', 'river_code', 'regioncode',
            'ds_name', 'ds_code', 'lgtd', 'lttd',
            'drz', 'grz', 'wrz', 'ddgc', 'ds_length', 'Shape_length',
        ],
        'description': '标准化堤段图层（24个字段）',
        'field_details': {
            'wkt_geom': 'WKT 几何字符串',
            'OBJECTID': '对象ID（自动生成）',
            'dike_code': '堤防编码（自动生成，如 hxdf0001）',
            'dike_name': '堤防名称',
            'zya': '岸别 (L/R)',
            'polder_name': '圩区名称（自动生成）',
            'polder_id': '圩区编码',
            '所属市': '地级市',
            '所属县': '县/区',
            '所属镇': '乡镇',
            'river_name': '河流名称',
            'LC': '里程 (m)',
            'river_code': '河流编码',
            'regioncode': '区域编码',
            'ds_name': '堤段名称（自动生成）',
            'ds_code': '堤段编码（自动生成）',
            'lgtd': '经度 (度，自动计算)',
            'lttd': '纬度 (度，自动计算)',
            'drz': '设计堤顶高程 (NULL)',
            'grz': '规划堤顶高程 (NULL)',
            'wrz': '现状堤顶高程 (NULL)',
            'ddgc': '堤顶高程 (m)',
            'ds_length': '堤段长度 (m，自动计算)',
            'Shape_length': '几何长度 (m，自动计算)',
        },
    },

    'dd_fix': {
        'name': '堤段（修正河流名称）',
        'type': 'LineString',
        'inherit_from': 'dd',
        'add_fields': [],
        'description': '修正 river_name 与 river_code 对应关系',
    },

    'df_with_elevation_lc': {
        'name': '堤防线（带高程和LC）',
        'type': 'LineString',
        'inherit_from': 'df',
        'add_fields': ['qdlc', 'zdlc', 'qdgc', 'zdgc'],
        'description': '堤防线 + 起点终点的LC和高程',
        'field_details': {
            'qdlc': '起点LC (m)',
            'zdlc': '终点LC (m)',
            'qdgc': '起点高程 (m)，根据 zya 选择 zagc/yagc',
            'zdgc': '终点高程 (m)，根据 zya 选择 zagc/yagc',
        },
    },
}


# ============ 辅助函数 ============

def get_input_fields(layer_name):
    """获取输入图层的字段规格"""
    return INPUT_LAYER_FIELDS.get(layer_name)


def get_output_fields(layer_name):
    """获取输出图层的字段规格"""
    return OUTPUT_LAYER_FIELDS.get(layer_name)


def format_layer_docstring(layer_name, is_input=True):
    """格式化图层字段为 docstring 格式"""
    fields = INPUT_LAYER_FIELDS.get(layer_name) if is_input else OUTPUT_LAYER_FIELDS.get(layer_name)
    if not fields:
        return f"  - {layer_name}: 未定义字段规格"

    lines = [f"  - {layer_name}: {fields['name']}"]

    if is_input:
        if fields.get('required_fields'):
            lines.append(f"    必需字段: {', '.join(fields['required_fields'])}")
    else:
        if fields.get('add_fields'):
            lines.append(f"    新增字段: {', '.join(fields['add_fields'])}")
        if fields.get('standard_fields'):
            lines.append(f"    标准字段: {len(fields['standard_fields'])} 个")

    if fields.get('field_details'):
        for field, desc in fields['field_details'].items():
            lines.append(f"      · {field}: {desc}")

    return '\n'.join(lines)


def validate_input_layer(layer, layer_name):
    """
    验证输入图层是否包含必需字段

    Returns:
        (is_valid, missing_fields) 元组
    """
    spec = INPUT_LAYER_FIELDS.get(layer_name)
    if not spec:
        return True, []

    required = spec.get('required_fields', [])
    if not required:
        return True, []

    layer_fields = [f.name() for f in layer.fields()]
    missing = [f for f in required if f not in layer_fields]

    return len(missing) == 0, missing
