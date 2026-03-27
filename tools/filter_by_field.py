"""
根据字段值筛选要素

功能：
筛选出字段值包含指定关键词的要素

示例：
筛选出 skgc 图层中 SZS 字段包含 "金华" 或 "衢州" 的要素

使用方法:
  1. 修改下方配置区
  2. 在 QGIS Python 控制台运行
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path

def _setup_paths():
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
        return
    lib_dir = script_dir.parent / 'lib'
    for path in [str(script_dir), str(lib_dir)]:
        if path not in sys.path:
            sys.path.insert(0, path)

_setup_paths()
# ============ 路径设置结束 ============

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsWkbTypes
)

# ============ 配置区 ============

# 输入图层名
INPUT_LAYER_NAME = 'skgc1'

# 筛选字段名
FILTER_FIELD = 'SZS'

# 筛选关键词（包含任一即保留）
FILTER_KEYWORDS = ['金华', '衢州']

# 输出图层名（留空则自动生成）
OUTPUT_LAYER_NAME = ''

# ============ 主函数 ============

def filter_by_field():
    """根据字段值筛选要素"""
    
    keywords_str = '_'.join(FILTER_KEYWORDS)
    print(f"\n[filter_by_field] 筛选 {FILTER_FIELD} 包含 {FILTER_KEYWORDS}")
    
    # 1. 加载图层
    print(f"\n[1] 加载图层")
    layers = QgsProject.instance().mapLayersByName(INPUT_LAYER_NAME)
    if not layers:
        print(f"  错误: 找不到图层 '{INPUT_LAYER_NAME}'")
        return None
    
    input_layer = layers[0]
    print(f"  {INPUT_LAYER_NAME}: {input_layer.featureCount()} 个要素")
    
    # 检查字段
    field_names = [f.name() for f in input_layer.fields()]
    if FILTER_FIELD not in field_names:
        print(f"  错误: 缺少字段 '{FILTER_FIELD}'")
        print(f"  可用字段: {', '.join(field_names)}")
        return None
    
    # 2. 筛选
    print(f"\n[2] 筛选")
    
    output_name = OUTPUT_LAYER_NAME or f"{INPUT_LAYER_NAME}_{keywords_str}"
    geom_type = QgsWkbTypes.displayString(input_layer.wkbType())
    
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={input_layer.crs().authid()}",
        output_name,
        "memory"
    )
    provider = output_layer.dataProvider()
    provider.addAttributes(input_layer.fields().toList())
    output_layer.updateFields()
    
    # 筛选要素
    features = []
    for feat in input_layer.getFeatures():
        field_value = feat[FILTER_FIELD]
        if field_value:
            value_str = str(field_value)
            if any(kw in value_str for kw in FILTER_KEYWORDS):
                new_feat = QgsFeature(output_layer.fields())
                new_feat.setGeometry(feat.geometry())
                for field in input_layer.fields():
                    new_feat[field.name()] = feat[field.name()]
                features.append(new_feat)
    
    provider.addFeatures(features)
    output_layer.updateExtents()
    
    print(f"  筛选结果: {len(features)}/{input_layer.featureCount()} 个要素")
    
    # 3. 添加到项目
    print(f"\n[3] 添加到项目")
    
    existing = QgsProject.instance().mapLayersByName(output_name)
    for old in existing:
        QgsProject.instance().removeMapLayer(old)
    
    QgsProject.instance().addMapLayer(output_layer)
    print(f"  输出: {output_name}")
    
    return output_layer


# ============ 脚本入口 ============

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 50)
    print("filter_by_field - 字段筛选")
    print("=" * 50)
    
    try:
        result = filter_by_field()
        if result:
            print("\n[完成]")
        else:
            print("\n[失败]")
    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
