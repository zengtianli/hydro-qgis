#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05 堤段字段对齐脚本

功能：
1. 按照标准字段顺序（24个字段）重新组织堤段数据
2. 从原始图层中提取对应字段的数据
3. 自动生成缺失字段（dike_code, polder_name, river_name, ds_name, ds_code）
4. 自动计算几何字段（ds_length, Shape_length, lgtd, lttd）
5. drz, grz, wrz 保持为空（NULL）

输入图层:
  - dike_sections_with_elevation: 堤段（带高程）
    必需字段: zya, ddgc, 所属市, 所属县
      · zya: 岸别 (L=左岸, R=右岸)
      · ddgc: 堤顶高程 (m)
      · 所属市: 地级市名称
      · 所属县: 县/区名称
    可选字段: dikeName, polderCode, LC, adcdName, adcdCode 等

输出图层:
  - dd: 堤段（标准24字段）
    标准字段 (24个):
      · wkt_geom: WKT 几何字符串
      · OBJECTID: 对象ID（自动生成）
      · dike_code: 堤防编码（自动生成，如 hxdf0001）
      · dike_name: 堤防名称
      · zya: 岸别 (L/R)
      · polder_name: 圩区名称（自动生成）
      · polder_id: 圩区编码
      · 所属市: 地级市
      · 所属县: 县/区
      · 所属镇: 乡镇
      · river_name: 河流名称
      · LC: 里程 (m)
      · river_code: 河流编码
      · regioncode: 区域编码
      · ds_name: 堤段名称（自动生成）
      · ds_code: 堤段编码（自动生成）
      · lgtd: 经度 (度，自动计算)
      · lttd: 纬度 (度，自动计算)
      · drz: 设计堤顶高程 (NULL)
      · grz: 规划堤顶高程 (NULL)
      · wrz: 现状堤顶高程 (NULL)
      · ddgc: 堤顶高程 (m)
      · ds_length: 堤段长度 (m，自动计算)
      · Shape_length: 几何长度 (m，自动计算)

自动生成规则：
- dike_code: 从 dike_name 生成（华溪堤防0001 → hxdf0001）
- polder_name: 从 polder_id 生成（hx0001 → 华溪0001）
- river_name: 从 polder_id 生成（hx0001 → 华溪）
- ds_name/ds_code: 递增编号（20250001, 20250002, ...）

注意事项：
- 如果输入图层是投影坐标系（如EPSG:4549），会自动转换为地理坐标系（EPSG:4490）
- 经纬度输出单位为度（例如：119.75346571, 28.83264377）
- 长度输出单位为米
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path

def _setup_paths():
    """设置模块搜索路径，兼容QGIS控制台和命令行执行"""
    known_paths = [
        Path(__file__).resolve().parent.parent if '__file__' in dir() else None,
        Path.home() / 'Dev/scripts/projects/qgis',
    ]
    script_dir = None
    for p in known_paths:
        if p is not None and p.exists():
            script_dir = p
            break
    if script_dir is None:
        print("⚠️ 无法确定脚本目录，模块导入可能失败")
        return
    assets_lib = script_dir.parent.parent / 'lib'  # lib/
    if str(assets_lib) not in sys.path:
        sys.path.insert(0, str(assets_lib))
    lib_dir = script_dir.parent / 'lib'
    for path in [str(script_dir), str(lib_dir)]:
        if path not in sys.path:
            sys.path.insert(0, path)

_setup_paths()
# ============ 路径设置结束 ============

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsField, 
    QgsWkbTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform
)
from qgis.PyQt.QtCore import QVariant
import re

# 导入工具函数
from qgis_util import ensure_group_exists, save_and_reload_layer

# 导入公共配置
from hydraulic.qgis_config import (
    OUTPUT_LAYERS,
    STANDARD_DIKE_FIELDS,
    FIELD_MAPPING,
    NULL_FIELDS,
    RIVER_NAME_TO_CODE,
    CHINESE_TO_PINYIN,
    DS_START_NUMBER,
    GEO_CRS
)

# ============ 配置区域 ============

# 输入图层名称
INPUT_LAYER_NAME = OUTPUT_LAYERS['dike_with_elevation']  # 修改为实际输入图层名称

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['dd']

# 标准字段定义（从公共配置读取）
STANDARD_FIELDS = STANDARD_DIKE_FIELDS

# 河流代码映射（编码→名称，用于解析polder_id）
# 例如: {"hx": "华溪", "sx": "熟溪", ...}
RIVER_CODE_MAPPING = {v: k for k, v in RIVER_NAME_TO_CODE.items()}

# 需要自动生成的字段
AUTO_GENERATE_FIELDS = ['dike_code', 'polder_name', 'river_name', 'ds_name', 'ds_code']

# ============ 辅助函数 ============

def validate_output_fields(layer, layer_name, required_fields):
    """验证输出图层是否包含所有必需字段"""
    if layer is None or not layer.isValid():
        print(f"  ❌ 输出图层 '{layer_name}' 无效")
        return False, []
    
    available_fields = [f.name() for f in layer.fields()]
    missing_fields = [f for f in required_fields if f not in available_fields]
    
    if missing_fields:
        print(f"\n  ❌ 输出图层 '{layer_name}' 缺少必需字段:")
        for field in missing_fields:
            print(f"     - {field}")
        return False, missing_fields
    
    if layer.featureCount() == 0:
        print(f"  ⚠️  警告: 输出图层 '{layer_name}' 没有要素")
        return False, []
    
    return True, []


# ============ 主程序 ============

def get_layer_by_name(layer_name):
    """根据名称获取图层"""
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        print(f"❌ 错误：找不到图层 '{layer_name}'")
        return None
    return layers[0]


def parse_polder_id_to_name(polder_id):
    """
    从 polder_id 生成 polder_name
    例如: hx0001 → 华溪0001
    """
    if not polder_id or str(polder_id).strip() == "":
        return None
    
    polder_id = str(polder_id).strip().lower()
    
    # 匹配模式: 字母部分 + 数字部分
    match = re.match(r'^([a-zA-Z]+)(\d+)$', polder_id)
    if not match:
        return None
    
    code_prefix = match.group(1).lower()  # 如 "hx"
    number_part = match.group(2)  # 如 "0001"
    
    # 查找对应的中文名称
    if code_prefix in RIVER_CODE_MAPPING:
        chinese_name = RIVER_CODE_MAPPING[code_prefix]
        return f"{chinese_name}{number_part}"
    else:
        return None


def parse_polder_id_to_river_name(polder_id):
    """
    从 polder_id 生成 river_name
    例如: hx0001 → 华溪
    """
    if not polder_id or str(polder_id).strip() == "":
        return None
    
    polder_id = str(polder_id).strip().lower()
    
    # 匹配模式: 字母部分 + 数字部分
    match = re.match(r'^([a-zA-Z]+)(\d+)$', polder_id)
    if not match:
        return None
    
    code_prefix = match.group(1).lower()  # 如 "hx"
    
    # 查找对应的中文名称
    if code_prefix in RIVER_CODE_MAPPING:
        return RIVER_CODE_MAPPING[code_prefix]
    else:
        return None


def parse_dike_name_to_code(dike_name):
    """
    从 dike_name 生成 dike_code
    例如: 华溪堤防0001 → hxdf0001
    
    处理逻辑:
    1. 提取数字部分
    2. 提取中文部分，按词语查找拼音首字母
    3. 拼接：拼音首字母 + 数字
    """
    if not dike_name or str(dike_name).strip() == "":
        return None
    
    dike_name = str(dike_name).strip()
    
    # 提取数字部分（末尾的连续数字）
    number_match = re.search(r'(\d+)$', dike_name)
    if not number_match:
        return None
    
    number_part = number_match.group(1)
    chinese_part = dike_name[:number_match.start()]
    
    # 将中文部分转换为拼音首字母
    pinyin_parts = []
    
    # 尝试匹配词语（从长到短）
    i = 0
    while i < len(chinese_part):
        matched = False
        # 尝试从当前位置匹配最长的词语
        for length in range(min(4, len(chinese_part) - i), 0, -1):
            word = chinese_part[i:i+length]
            if word in CHINESE_TO_PINYIN:
                pinyin_parts.append(CHINESE_TO_PINYIN[word])
                i += length
                matched = True
                break
        
        if not matched:
            # 如果没有匹配到，跳过这个字符
            i += 1
    
    if not pinyin_parts:
        return None
    
    # 拼接结果
    dike_code = ''.join(pinyin_parts) + number_part
    return dike_code.lower()


def find_source_field(standard_field_name, source_fields):
    """
    查找源图层中对应的字段名
    
    优先级：
    1. 完全匹配（区分大小写）
    2. 映射表查找
    3. 不区分大小写匹配
    
    返回：源字段名，如果找不到返回 None
    """
    # 1. 完全匹配
    if standard_field_name in source_fields:
        return standard_field_name
    
    # 2. 映射表查找
    for src, std in FIELD_MAPPING.items():
        if std == standard_field_name and src in source_fields:
            return src
    
    # 3. 不区分大小写匹配
    standard_lower = standard_field_name.lower()
    for src_field in source_fields:
        if src_field.lower() == standard_lower:
            return src_field
    
    return None


def align_dike_fields():
    """对齐堤段字段"""
    
    print("=" * 80)
    print("🔧 堤段字段对齐脚本")
    print("=" * 80)
    
    # 1. 获取输入图层
    print(f"\n【步骤1】加载输入图层")
    input_layer = get_layer_by_name(INPUT_LAYER_NAME)
    if not input_layer:
        return None
    
    print(f"  ✅ 输入图层：{input_layer.name()}")
    print(f"  ✅ 要素数量：{input_layer.featureCount()}")
    print(f"  ✅ 坐标系：{input_layer.crs().authid()}")
    
    # 1.5 准备坐标转换（投影坐标系 → 地理坐标系）
    source_crs = input_layer.crs()
    target_crs = QgsCoordinateReferenceSystem(GEO_CRS)  # CGCS2000 地理坐标系
    coord_transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
    
    is_geographic = source_crs.isGeographic()
    print(f"  📍 坐标系类型：{'地理坐标系（经纬度）' if is_geographic else '投影坐标系（米）'}")
    if not is_geographic:
        print(f"  🔄 将转换为地理坐标系：{target_crs.authid()} (CGCS2000)")
    else:
        print(f"  ℹ️  已是地理坐标系，无需转换")
    
    # 显示原始字段
    source_fields = [field.name() for field in input_layer.fields()]
    print(f"  📋 原始字段数：{len(source_fields)}")
    print(f"     {', '.join(source_fields[:10])}{'...' if len(source_fields) > 10 else ''}")
    
    # 2. 创建输出图层
    print(f"\n【步骤2】创建输出图层")
    geom_type = QgsWkbTypes.displayString(input_layer.wkbType())
    
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={input_layer.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    
    if not output_layer.isValid():
        print("❌ 错误：无法创建输出图层！")
        return None
    
    output_provider = output_layer.dataProvider()
    
    # 3. 添加标准字段
    print(f"\n【步骤3】添加标准字段")
    print(f"  🔄 创建 {len(STANDARD_FIELDS)} 个标准字段...")
    
    qgs_fields = []
    for field_name, field_type, field_len, field_prec, field_desc in STANDARD_FIELDS:
        if field_name == 'wkt_geom':
            # wkt_geom 不作为属性字段，跳过
            continue
        
        qgs_field = QgsField(field_name, field_type)
        if field_len > 0:
            qgs_field.setLength(field_len)
        if field_prec > 0:
            qgs_field.setPrecision(field_prec)
        qgs_fields.append(qgs_field)
    
    output_provider.addAttributes(qgs_fields)
    output_layer.updateFields()
    
    print(f"  ✅ 已添加 {len(qgs_fields)} 个字段")
    
    # 4. 建立字段映射
    print(f"\n【步骤4】建立字段映射")
    field_map = {}  # 标准字段名 → 源字段名
    missing_fields = []
    
    for field_name, _, _, _, _ in STANDARD_FIELDS:
        if field_name == 'wkt_geom':
            continue
        
        if field_name in NULL_FIELDS:
            # 空值字段，不映射
            field_map[field_name] = None
            continue
        
        source_field = find_source_field(field_name, source_fields)
        if source_field:
            field_map[field_name] = source_field
        else:
            field_map[field_name] = None
            missing_fields.append(field_name)
    
    # 显示映射结果
    print(f"\n  📊 字段映射统计:")
    mapped_count = sum(1 for v in field_map.values() if v is not None)
    print(f"     ✅ 成功映射: {mapped_count} 个")
    print(f"     ⚠️  缺失字段: {len(missing_fields)} 个")
    print(f"     🔴 空值字段: {len(NULL_FIELDS)} 个 (drz, grz, wrz)")
    
    if missing_fields:
        print(f"\n  ⚠️  以下字段在源图层中找不到，将自动生成或填充 NULL:")
        for field in missing_fields:
            if field in AUTO_GENERATE_FIELDS:
                print(f"     - {field} (将自动生成)")
            else:
                print(f"     - {field} (填充 NULL)")
    
    # 显示部分映射关系
    print(f"\n  📋 字段映射示例（前10个）:")
    for i, (std_field, src_field) in enumerate(list(field_map.items())[:10]):
        if src_field:
            if src_field == std_field:
                print(f"     {i+1}. {std_field} ← {src_field}")
            else:
                print(f"     {i+1}. {std_field} ← {src_field} (映射)")
        else:
            if std_field in NULL_FIELDS:
                print(f"     {i+1}. {std_field} ← NULL (空值字段)")
            elif std_field in AUTO_GENERATE_FIELDS:
                print(f"     {i+1}. {std_field} ← 自动生成")
            else:
                print(f"     {i+1}. {std_field} ← NULL (缺失)")
    
    # 5. 处理要素数据
    print(f"\n【步骤5】处理要素数据")
    print(f"  🔄 转换 {input_layer.featureCount()} 个要素...")
    
    output_features = []
    ds_number = DS_START_NUMBER
    
    # 统计自动生成的字段数量
    auto_gen_stats = {
        'dike_code': 0,
        'polder_name': 0,
        'river_name': 0,
        'ds_name': 0,
        'ds_code': 0
    }
    
    # 统计坐标转换
    coord_transform_count = 0
    
    for idx, input_feat in enumerate(input_layer.getFeatures(), 1):
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(input_feat.geometry())
        
        # 按照字段映射复制数据
        for std_field, src_field in field_map.items():
            if src_field:
                # 从源图层复制值
                value = input_feat[src_field]
                new_feat[std_field] = value
            else:
                # 填充 NULL
                new_feat[std_field] = None
        
        # ========== 自动生成字段 ==========
        
        # 0. 生成 dike_code（从 dike_name）
        if 'dike_code' in field_map and field_map['dike_code'] is None:
            dike_name = new_feat['dike_name']
            if dike_name and str(dike_name).strip():
                generated_code = parse_dike_name_to_code(dike_name)
                if generated_code:
                    new_feat['dike_code'] = generated_code
                    auto_gen_stats['dike_code'] += 1
        
        # 1. 生成 polder_name（从 polder_id）
        if 'polder_name' in field_map and field_map['polder_name'] is None:
            polder_id = new_feat['polder_id']
            if polder_id and str(polder_id).strip():
                generated_name = parse_polder_id_to_name(polder_id)
                if generated_name:
                    new_feat['polder_name'] = generated_name
                    auto_gen_stats['polder_name'] += 1
        
        # 2. 生成 river_name（从 polder_id）
        if 'river_name' in field_map and field_map['river_name'] is None:
            polder_id = new_feat['polder_id']
            if polder_id and str(polder_id).strip():
                generated_river_name = parse_polder_id_to_river_name(polder_id)
                if generated_river_name:
                    new_feat['river_name'] = generated_river_name
                    auto_gen_stats['river_name'] += 1
        
        # 3. 生成 ds_name 和 ds_code（递增编号）
        if ('ds_name' in field_map and field_map['ds_name'] is None) or \
           ('ds_code' in field_map and field_map['ds_code'] is None):
            ds_value = str(ds_number)
            new_feat['ds_name'] = ds_value
            new_feat['ds_code'] = ds_value
            ds_number += 1
            auto_gen_stats['ds_name'] += 1
            auto_gen_stats['ds_code'] += 1
        
        # ========== 4. 自动计算几何字段 ==========
        geom = new_feat.geometry()
        
        # 计算长度（ds_length 和 Shape_length）
        if geom and not geom.isNull():
            # 计算长度（单位：米）
            length = geom.length()
            new_feat['ds_length'] = round(length, 6)
            new_feat['Shape_length'] = round(length, 12)
            
            # 计算中心点坐标（lgtd, lttd）- 需要转换为经纬度
            centroid = geom.centroid()
            if centroid and not centroid.isNull():
                center_point = centroid.asPoint()
                
                # 如果是投影坐标系，需要转换为地理坐标系（经纬度）
                if not is_geographic:
                    try:
                        # 转换坐标
                        transformed_point = coord_transform.transform(center_point)
                        new_feat['lgtd'] = round(transformed_point.x(), 8)  # 经度（度）
                        new_feat['lttd'] = round(transformed_point.y(), 8)  # 纬度（度）
                        coord_transform_count += 1
                    except Exception as e:
                        # 转换失败，记录原坐标
                        new_feat['lgtd'] = round(center_point.x(), 8)
                        new_feat['lttd'] = round(center_point.y(), 8)
                        if idx <= 5:  # 只显示前5个错误
                            print(f"    ⚠️  要素 {idx} 坐标转换失败: {str(e)}")
                else:
                    # 已经是地理坐标系，直接使用
                    new_feat['lgtd'] = round(center_point.x(), 8)  # 经度（度）
                    new_feat['lttd'] = round(center_point.y(), 8)  # 纬度（度）
        
        output_features.append(new_feat)
        
        # 显示进度
        if idx % 100 == 0 or idx == input_layer.featureCount():
            print(f"     进度: {idx}/{input_layer.featureCount()}")
    
    output_provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    print(f"  ✅ 已转换 {len(output_features)} 个要素")
    
    # 显示自动生成统计
    if any(auto_gen_stats.values()):
        print(f"\n  📊 自动生成字段统计:")
        for field_name, count in auto_gen_stats.items():
            if count > 0:
                if field_name == 'dike_code':
                    print(f"     • {field_name}: {count} 个 (从 dike_name 生成)")
                elif field_name == 'polder_name':
                    print(f"     • {field_name}: {count} 个 (从 polder_id 生成)")
                elif field_name == 'river_name':
                    print(f"     • {field_name}: {count} 个 (从 polder_id 生成)")
                elif field_name in ['ds_name', 'ds_code']:
                    print(f"     • {field_name}: {count} 个 (从 {DS_START_NUMBER} 到 {ds_number-1})")
    
    # 显示坐标转换统计
    if coord_transform_count > 0:
        print(f"\n  🌍 坐标转换统计:")
        print(f"     • 已转换 {coord_transform_count} 个中心点坐标")
        print(f"     • 从 {source_crs.authid()} (投影坐标) → {target_crs.authid()} (经纬度)")
    
    # 6. 添加到项目（final组）
    print(f"\n【步骤6】添加到QGIS项目")
    
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    
    # 移除旧图层（如果存在）
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    if existing_layers:
        project.removeMapLayer(existing_layers[0])
        print(f"  🗑️  已移除旧图层: {OUTPUT_LAYER_NAME}")
    
    # 查找或创建 final 组
    final_group = ensure_group_exists("final")
    
    # 添加到final组
    project.addMapLayer(output_layer, False)
    final_group.addLayer(output_layer)
    print(f"  ✅ 已添加新图层: {OUTPUT_LAYER_NAME} (final组) ⭐")
    
    # 7. 验证结果
    print(f"\n【步骤7】验证结果")
    print(f"\n  📋 输出图层信息:")
    print(f"     - 图层名称: {output_layer.name()}")
    print(f"     - 要素数量: {output_layer.featureCount()}")
    print(f"     - 字段数量: {len(output_layer.fields())}")
    print(f"     - 坐标系: {output_layer.crs().authid()}")
    
    # 显示字段列表
    print(f"\n  📋 标准字段列表（{len(output_layer.fields())} 个）:")
    for i, field in enumerate(output_layer.fields(), 1):
        type_name = field.typeName()
        print(f"     {i:2}. {field.name():<20} ({type_name})")
    
    # 显示前3条数据示例
    print(f"\n  📊 数据示例（前3条）:")
    print(f"  {'序号':<5} {'dike_code':<15} {'dike_name':<20} {'polder_id':<12} {'river_name':<10} {'ds_name':<12}")
    print("  " + "-" * 90)
    
    for idx, feat in enumerate(output_layer.getFeatures(), 1):
        if idx <= 3:
            dike_code = feat["dike_code"] or "-"
            dike_name = feat["dike_name"] or "-"
            polder_id = feat["polder_id"] or "-"
            river_name = feat["river_name"] or "-"
            ds_name = feat["ds_name"] or "-"
            
            print(f"  {idx:<5} {str(dike_code):<15} {str(dike_name):<20} {str(polder_id):<12} {str(river_name):<10} {str(ds_name):<12}")
    
    if output_layer.featureCount() > 3:
        print("  ...")
    
    # 8. 验证输出图层
    print("\n【步骤8】验证输出图层")
    
    # 提取标准字段名称（排除wkt_geom）
    required_output_fields = [field_name for field_name, _, _, _, _ in STANDARD_FIELDS if field_name != 'wkt_geom']
    
    print(f"\n  🔍 验证输出图层字段完整性...")
    print(f"     - 应包含字段数: {len(required_output_fields)}")
    
    is_valid, missing = validate_output_fields(output_layer, OUTPUT_LAYER_NAME, required_output_fields)
    
    if is_valid:
        print(f"  ✅ {OUTPUT_LAYER_NAME}: 所有24个标准字段验证通过")
        # 验证字段顺序
        actual_fields = [f.name() for f in output_layer.fields()]
        print(f"\n  📋 字段顺序检查:")
        for i, (expected, actual) in enumerate(zip(required_output_fields, actual_fields[:len(required_output_fields)]), 1):
            if expected == actual:
                print(f"     {i:2}. ✅ {expected}")
            else:
                print(f"     {i:2}. ⚠️  期望: {expected}, 实际: {actual}")
    else:
        print(f"  ❌ {OUTPUT_LAYER_NAME}: 字段验证失败")
        if missing:
            print(f"     缺失字段: {', '.join(missing)}")
    
    # 保存图层并重新加载
    print("\n" + "=" * 80)
    print("💾 保存图层到文件并重新加载")
    print("=" * 80)
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    # 9. 输出总结
    print("\n" + "=" * 80)
    print("✅ 字段对齐完成！")
    print("=" * 80)
    
    print(f"\n📊 处理统计:")
    print(f"  • 输入要素: {input_layer.featureCount()}")
    print(f"  • 输出要素: {output_layer.featureCount()}")
    print(f"  • 原始字段: {len(source_fields)}")
    print(f"  • 标准字段: {len(output_layer.fields())}")
    print(f"  • 成功映射: {mapped_count}")
    print(f"  • 缺失字段: {len(missing_fields)}")
    print(f"  • 空值字段: {len(NULL_FIELDS)} (drz, grz, wrz)")
    
    if any(auto_gen_stats.values()):
        print(f"\n📊 自动生成统计:")
        for field_name, count in auto_gen_stats.items():
            if count > 0:
                if field_name == 'dike_code':
                    print(f"  • {field_name}: {count} 个 (从 dike_name 生成，如 华溪堤防0001 → hxdf0001)")
                elif field_name == 'polder_name':
                    print(f"  • {field_name}: {count} 个 (从 polder_id 生成，如 hx0001 → 华溪0001)")
                elif field_name == 'river_name':
                    print(f"  • {field_name}: {count} 个 (从 polder_id 生成，如 hx0001 → 华溪)")
                elif field_name in ['ds_name', 'ds_code']:
                    print(f"  • {field_name}: {count} 个 (从 {DS_START_NUMBER} 到 {ds_number-1})")
    
    print(f"\n💡 说明:")
    print(f"  ✓ 字段已按标准顺序排列（24个字段）")
    print(f"  ✓ 数据已从原图层成功复制")
    print(f"  ✓ dike_code 自动从 dike_name 生成（华溪堤防0001 → hxdf0001）")
    print(f"  ✓ polder_name 自动从 polder_id 生成（hx0001 → 华溪0001）")
    print(f"  ✓ river_name 自动从 polder_id 生成（hx0001 → 华溪）")
    print(f"  ✓ ds_name, ds_code 自动递增（{DS_START_NUMBER}, {DS_START_NUMBER+1}, ...）")
    print(f"  ✓ 所属市/县/镇 已从原字段映射")
    print(f"  ✓ drz, grz, wrz 保持为 NULL")
    print(f"  ✓ ds_length, Shape_length 已重新计算（从几何长度，单位：米）")
    print(f"  ✓ lgtd, lttd 已重新计算（从几何中心点，单位：度）")
    if coord_transform_count > 0:
        print(f"  ✓ 坐标系已转换：{source_crs.authid()} → {target_crs.authid()} (经纬度)")
    
    print(f"\n📁 下一步:")
    print(f"  1. 检查自动生成的字段是否正确")
    print(f"  2. 验证 dike_code 的拼音首字母是否正确")
    print(f"  3. 如需添加其他词语，请在 CHINESE_TO_PINYIN 中添加")
    print(f"  4. 如需添加其他河流，请在 RIVER_CODE_MAPPING 中添加")
    print(f"  5. 导出为 GeoJSON/Shapefile")
    
    return output_layer


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🔧 堤段字段对齐脚本开始执行...")
    print("=" * 80)
    
    try:
        result = align_dike_fields()
        if result:
            print("\n" + "=" * 80)
            print("✓ 脚本执行成功！")
            print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print("✗ 脚本执行失败，请检查错误信息。")
            print("=" * 80)
    except Exception as e:
        print("\n" + "=" * 80)
        print("✗ 执行出错！")
        print("=" * 80)
        print(f"\n错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print(f"\n详细堆栈:")
        import traceback
        traceback.print_exc()
        print("=" * 80)
