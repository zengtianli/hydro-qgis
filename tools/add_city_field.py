"""
根据县区字段生成地级市字段

功能：
根据 ADCD 字段（县区名称）自动生成 CITY 字段（地级市名称）

输入图层:
  - 任意图层
    必需字段: ADCD (或指定的县区字段)
      · ADCD: 县区名称，如 "德清县" 或 "德清县,临安区"

输出图层:
  - 原图层名_with_city
    新增字段: CITY
      · CITY: 地级市名称，如 "湖州市" 或 "湖州市,杭州市"

使用方法:
  1. 修改下方配置区的 INPUT_LAYER_NAME 和 COUNTY_FIELD
  2. 在 QGIS Python 控制台运行
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path

def _setup_paths():
    """设置模块搜索路径"""
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
        print("警告: 无法确定脚本目录")
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
    QgsProject, QgsVectorLayer, QgsFeature, QgsField, QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

from hydraulic.qgis_config import get_city_from_county

# ============ 配置区 ============

# 输入图层名称
INPUT_LAYER_NAME = 'hlsc'  # 修改为你的图层名

# 县区字段名
COUNTY_FIELD = 'ADCD'  # 修改为你的县区字段名

# 输出字段名
CITY_FIELD = 'CITY'

# 输出图层名（留空则自动生成）
OUTPUT_LAYER_NAME = ''

# 筛选配置（可选）
FILTER_CITIES = ['金华', '衢州']  # 筛选包含这些城市的要素，留空则不筛选
FILTER_OUTPUT_NAME = ''  # 筛选输出图层名，留空则自动生成

# ============ 主函数 ============

def add_city_field():
    """为图层添加 CITY 字段"""
    
    print(f"\n[add_city_field] 根据县区生成地级市字段")
    
    # 1. 加载图层
    print(f"\n[1] 加载图层")
    layers = QgsProject.instance().mapLayersByName(INPUT_LAYER_NAME)
    if not layers:
        print(f"  错误: 找不到图层 '{INPUT_LAYER_NAME}'")
        return None
    
    input_layer = layers[0]
    print(f"  图层: {INPUT_LAYER_NAME}, {input_layer.featureCount()} 个要素")
    
    # 检查字段
    field_names = [f.name() for f in input_layer.fields()]
    if COUNTY_FIELD not in field_names:
        print(f"  错误: 图层缺少字段 '{COUNTY_FIELD}'")
        print(f"  可用字段: {', '.join(field_names)}")
        return None
    
    # 2. 创建输出图层
    print(f"\n[2] 创建输出图层")
    
    geom_type = QgsWkbTypes.displayString(input_layer.wkbType())
    output_name = OUTPUT_LAYER_NAME or f"{INPUT_LAYER_NAME}_with_city"
    
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={input_layer.crs().authid()}",
        output_name,
        "memory"
    )
    provider = output_layer.dataProvider()
    
    # 复制原字段
    provider.addAttributes(input_layer.fields().toList())
    
    # 添加 CITY 字段（如果不存在）
    if CITY_FIELD not in field_names:
        provider.addAttributes([QgsField(CITY_FIELD, QVariant.String, len=100)])
    
    output_layer.updateFields()
    
    # 3. 填充数据
    print(f"\n[3] 填充数据")
    
    output_features = []
    matched = 0
    unmatched = 0
    
    for feat in input_layer.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(feat.geometry())
        
        # 复制原字段
        for field in input_layer.fields():
            new_feat[field.name()] = feat[field.name()]
        
        # 生成 CITY
        county_value = feat[COUNTY_FIELD]
        if county_value:
            city = get_city_from_county(str(county_value))
            if city:
                new_feat[CITY_FIELD] = city
                matched += 1
            else:
                new_feat[CITY_FIELD] = None
                unmatched += 1
        else:
            new_feat[CITY_FIELD] = None
            unmatched += 1
        
        output_features.append(new_feat)
    
    provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    print(f"  匹配成功: {matched}")
    print(f"  未匹配: {unmatched}")
    
    # 4. 添加到项目
    print(f"\n[4] 添加到项目")
    
    # 移除旧图层
    existing = QgsProject.instance().mapLayersByName(output_name)
    for old in existing:
        QgsProject.instance().removeMapLayer(old)
    
    QgsProject.instance().addMapLayer(output_layer)
    print(f"  输出: {output_name}")
    
    # 5. 显示示例
    print(f"\n[5] 数据示例 (前5条)")
    count = 0
    for feat in output_layer.getFeatures():
        if count >= 5:
            break
        county = feat[COUNTY_FIELD] or 'NULL'
        city = feat[CITY_FIELD] or 'NULL'
        # 截断显示
        if len(str(county)) > 30:
            county = str(county)[:30] + '...'
        print(f"  {county} -> {city}")
        count += 1
    
    # 6. 筛选（可选）
    filtered_layer = None
    if FILTER_CITIES:
        print(f"\n[6] 筛选包含 {FILTER_CITIES} 的要素")
        filtered_layer = filter_by_city(output_layer, FILTER_CITIES)
    
    return output_layer, filtered_layer


def filter_by_city(input_layer, cities):
    """筛选包含指定城市的要素"""
    
    # 生成输出名
    city_suffix = '_'.join([c.replace('市', '') for c in cities])
    filter_name = FILTER_OUTPUT_NAME or f"{INPUT_LAYER_NAME}_with_city_{city_suffix}"
    
    # 创建输出图层
    geom_type = QgsWkbTypes.displayString(input_layer.wkbType())
    filtered_layer = QgsVectorLayer(
        f"{geom_type}?crs={input_layer.crs().authid()}",
        filter_name,
        "memory"
    )
    provider = filtered_layer.dataProvider()
    provider.addAttributes(input_layer.fields().toList())
    filtered_layer.updateFields()
    
    # 筛选要素
    filtered_features = []
    for feat in input_layer.getFeatures():
        city_value = feat[CITY_FIELD]
        if city_value:
            city_str = str(city_value)
            # 检查是否包含任一城市
            if any(c in city_str for c in cities):
                new_feat = QgsFeature(filtered_layer.fields())
                new_feat.setGeometry(feat.geometry())
                for field in input_layer.fields():
                    new_feat[field.name()] = feat[field.name()]
                filtered_features.append(new_feat)
    
    provider.addFeatures(filtered_features)
    filtered_layer.updateExtents()
    
    print(f"  筛选结果: {len(filtered_features)} 个要素")
    
    # 移除旧图层
    existing = QgsProject.instance().mapLayersByName(filter_name)
    for old in existing:
        QgsProject.instance().removeMapLayer(old)
    
    QgsProject.instance().addMapLayer(filtered_layer)
    print(f"  输出: {filter_name}")
    
    return filtered_layer


# ============ 脚本入口 ============

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 50)
    print("add_city_field - 县区转地级市")
    print("=" * 50)
    
    try:
        result, filtered = add_city_field()
        if result:
            print("\n[完成]")
        else:
            print("\n[失败]")
    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
