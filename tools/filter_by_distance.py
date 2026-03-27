"""
根据距离筛选要素

功能：
筛选出目标图层中，距离参考图层一定范围内的要素

示例：
筛选出距离河流(hlsc) 100米以内的水库(skgc)

输入图层:
  - hlsc: 河流图层（线）
  - skgc: 水库工程图层（点）

输出图层:
  - skgc_near_hlsc: 距离河流100m内的水库

使用方法:
  1. 修改下方配置区
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
    lib_dir = script_dir.parent / 'lib'
    for path in [str(script_dir), str(lib_dir)]:
        if path not in sys.path:
            sys.path.insert(0, path)

_setup_paths()
# ============ 路径设置结束 ============

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsWkbTypes
)
from qgis import processing

# ============ 配置区 ============

# 参考图层（用于计算距离的图层，如河流）
REFERENCE_LAYER_NAME = 'hlsc1'

# 目标图层（要筛选的图层，如水库）
TARGET_LAYER_NAME = 'skgc2'

# 搜索距离（米）
BUFFER_DISTANCE = 0.1

# 输出图层名（留空则自动生成）
OUTPUT_LAYER_NAME = ''

# ============ 主函数 ============

def filter_by_distance():
    """根据距离筛选要素"""
    
    print(f"\n[filter_by_distance] 根据距离筛选要素")
    print(f"  参考图层: {REFERENCE_LAYER_NAME}")
    print(f"  目标图层: {TARGET_LAYER_NAME}")
    print(f"  搜索距离: {BUFFER_DISTANCE}m")
    
    # 1. 加载图层
    print(f"\n[1] 加载图层")
    
    ref_layers = QgsProject.instance().mapLayersByName(REFERENCE_LAYER_NAME)
    if not ref_layers:
        print(f"  错误: 找不到参考图层 '{REFERENCE_LAYER_NAME}'")
        return None
    ref_layer = ref_layers[0]
    print(f"  参考: {REFERENCE_LAYER_NAME}, {ref_layer.featureCount()} 个要素, {ref_layer.crs().authid()}")
    
    target_layers = QgsProject.instance().mapLayersByName(TARGET_LAYER_NAME)
    if not target_layers:
        print(f"  错误: 找不到目标图层 '{TARGET_LAYER_NAME}'")
        return None
    target_layer = target_layers[0]
    print(f"  目标: {TARGET_LAYER_NAME}, {target_layer.featureCount()} 个要素, {target_layer.crs().authid()}")
    
    # 2. 创建缓冲区
    print(f"\n[2] 创建 {BUFFER_DISTANCE}m 缓冲区")
    
    # 检查坐标系，如果是地理坐标系需要重投影
    ref_for_buffer = ref_layer
    if ref_layer.crs().isGeographic():
        print(f"  地理坐标系，重投影到 EPSG:4549...")
        reproject_result = processing.run("native:reprojectlayer", {
            'INPUT': ref_layer,
            'TARGET_CRS': 'EPSG:4549',
            'OUTPUT': 'memory:'
        })
        ref_for_buffer = reproject_result['OUTPUT']
    
    buffer_result = processing.run("native:buffer", {
        'INPUT': ref_for_buffer,
        'DISTANCE': BUFFER_DISTANCE,
        'SEGMENTS': 8,
        'END_CAP_STYLE': 0,  # Round
        'JOIN_STYLE': 0,     # Round
        'MITER_LIMIT': 2,
        'DISSOLVE': True,    # 合并所有缓冲区
        'OUTPUT': 'memory:'
    })
    buffer_layer = buffer_result['OUTPUT']
    print(f"  缓冲区创建完成")
    
    # 3. 空间筛选
    print(f"\n[3] 空间筛选")
    
    # 确保目标图层与缓冲区坐标系一致
    target_for_filter = target_layer
    if target_layer.crs().authid() != buffer_layer.crs().authid():
        print(f"  重投影目标图层...")
        reproject_result = processing.run("native:reprojectlayer", {
            'INPUT': target_layer,
            'TARGET_CRS': buffer_layer.crs(),
            'OUTPUT': 'memory:'
        })
        target_for_filter = reproject_result['OUTPUT']
    
    # 使用 extractbylocation 筛选相交的要素
    extract_result = processing.run("native:extractbylocation", {
        'INPUT': target_for_filter,
        'PREDICATE': [0],  # 0 = intersects (相交)
        'INTERSECT': buffer_layer,
        'OUTPUT': 'memory:'
    })
    filtered_layer = extract_result['OUTPUT']
    
    filtered_count = filtered_layer.featureCount()
    original_count = target_layer.featureCount()
    print(f"  筛选结果: {filtered_count}/{original_count} 个要素")
    
    # 4. 重投影回原坐标系（如果需要）
    if target_layer.crs().authid() != filtered_layer.crs().authid():
        print(f"\n[4] 重投影回 {target_layer.crs().authid()}")
        reproject_result = processing.run("native:reprojectlayer", {
            'INPUT': filtered_layer,
            'TARGET_CRS': target_layer.crs(),
            'OUTPUT': 'memory:'
        })
        filtered_layer = reproject_result['OUTPUT']
    
    # 5. 设置图层名并添加到项目
    output_name = OUTPUT_LAYER_NAME or f"{TARGET_LAYER_NAME}_near_{REFERENCE_LAYER_NAME}"
    
    # 创建最终输出图层
    geom_type = QgsWkbTypes.displayString(target_layer.wkbType())
    final_layer = QgsVectorLayer(
        f"{geom_type}?crs={target_layer.crs().authid()}",
        output_name,
        "memory"
    )
    provider = final_layer.dataProvider()
    provider.addAttributes(target_layer.fields().toList())
    final_layer.updateFields()
    
    # 复制要素
    features = []
    for feat in filtered_layer.getFeatures():
        new_feat = QgsFeature(final_layer.fields())
        new_feat.setGeometry(feat.geometry())
        for field in final_layer.fields():
            if field.name() in [f.name() for f in filtered_layer.fields()]:
                new_feat[field.name()] = feat[field.name()]
        features.append(new_feat)
    provider.addFeatures(features)
    final_layer.updateExtents()
    
    print(f"\n[5] 添加到项目")
    
    # 移除旧图层
    existing = QgsProject.instance().mapLayersByName(output_name)
    for old in existing:
        QgsProject.instance().removeMapLayer(old)
    
    QgsProject.instance().addMapLayer(final_layer)
    print(f"  输出: {output_name}")
    print(f"  要素数: {final_layer.featureCount()}")
    
    return final_layer


# ============ 脚本入口 ============

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 50)
    print("filter_by_distance - 距离筛选")
    print("=" * 50)
    
    try:
        result = filter_by_distance()
        if result:
            print("\n[完成]")
        else:
            print("\n[失败]")
    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

