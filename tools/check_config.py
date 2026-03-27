#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置检查工具 - 验证图层是否存在
在运行主脚本之前，先用这个脚本检查配置
"""

from qgis.core import QgsProject
import sys
from pathlib import Path

# 路径设置
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    SCRIPT_DIR = Path.home() / 'Dev/scripts/projects/qgis'

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# ============ 配置参数（与主脚本一致） ============
POINT_LAYER = "points"          # 修改为你的点图层名称
POLYGON_LAYER = "polygons"      # 修改为你的面图层名称
OUTPUT_LAYER_NAME = "points_in_polygons"

# ============ 检查函数 ============

def check_configuration():
    """检查配置是否正确"""
    
    print("\n" + "=" * 80)
    print("🔍 配置检查工具")
    print("=" * 80)
    
    print(f"\n📋 当前配置:")
    print(f"   • 点图层: {POINT_LAYER}")
    print(f"   • 面图层: {POLYGON_LAYER}")
    print(f"   • 输出名称: {OUTPUT_LAYER_NAME}")
    
    # 获取当前项目中的所有图层
    project = QgsProject.instance()
    all_layers = project.mapLayers()
    
    if not all_layers:
        print("\n❌ 错误: QGIS项目中没有加载任何图层！")
        print("   请先在QGIS中加载你的数据。")
        return False
    
    print(f"\n📊 QGIS项目中的所有图层({len(all_layers)}个):")
    layer_names = []
    point_layers = []
    polygon_layers = []
    
    for layer_id, layer in all_layers.items():
        layer_name = layer.name()
        layer_names.append(layer_name)
        
        # 获取几何类型
        geom_type = layer.geometryType()
        type_name = ['点', '线', '面'][geom_type] if geom_type in [0, 1, 2] else '未知'
        
        print(f"   • {layer_name} ({type_name})")
        
        if geom_type == 0:  # 点
            point_layers.append(layer_name)
        elif geom_type == 2:  # 面
            polygon_layers.append(layer_name)
    
    # 检查点图层
    print(f"\n🔍 检查点图层: {POINT_LAYER}")
    if POINT_LAYER in layer_names:
        layer = project.mapLayersByName(POINT_LAYER)[0]
        geom_type = layer.geometryType()
        if geom_type == 0:
            print(f"   ✅ 找到点图层，包含 {layer.featureCount()} 个点")
            print(f"   📋 字段: {', '.join([f.name() for f in layer.fields()][:5])}...")
        else:
            type_name = ['点', '线', '面'][geom_type]
            print(f"   ⚠️  警告: 找到图层，但不是点图层（当前类型: {type_name}）")
            print(f"   💡 可用的点图层: {', '.join(point_layers) if point_layers else '无'}")
            return False
    else:
        print(f"   ❌ 找不到图层: {POINT_LAYER}")
        print(f"   💡 可用的点图层: {', '.join(point_layers) if point_layers else '无'}")
        if point_layers:
            print(f"\n   建议修改配置为:")
            print(f"   POINT_LAYER = \"{point_layers[0]}\"")
        return False
    
    # 检查面图层
    print(f"\n🔍 检查面图层: {POLYGON_LAYER}")
    if POLYGON_LAYER in layer_names:
        layer = project.mapLayersByName(POLYGON_LAYER)[0]
        geom_type = layer.geometryType()
        if geom_type == 2:
            print(f"   ✅ 找到面图层，包含 {layer.featureCount()} 个面")
            print(f"   📋 字段: {', '.join([f.name() for f in layer.fields()][:5])}...")
        else:
            type_name = ['点', '线', '面'][geom_type]
            print(f"   ⚠️  警告: 找到图层，但不是面图层（当前类型: {type_name}）")
            print(f"   💡 可用的面图层: {', '.join(polygon_layers) if polygon_layers else '无'}")
            return False
    else:
        print(f"   ❌ 找不到图层: {POLYGON_LAYER}")
        print(f"   💡 可用的面图层: {', '.join(polygon_layers) if polygon_layers else '无'}")
        if polygon_layers:
            print(f"\n   建议修改配置为:")
            print(f"   POLYGON_LAYER = \"{polygon_layers[0]}\"")
        return False
    
    # 检查坐标系
    point_layer = project.mapLayersByName(POINT_LAYER)[0]
    polygon_layer = project.mapLayersByName(POLYGON_LAYER)[0]
    
    point_crs = point_layer.crs().authid()
    polygon_crs = polygon_layer.crs().authid()
    
    print(f"\n🗺️  坐标系检查:")
    print(f"   • 点图层: {point_crs}")
    print(f"   • 面图层: {polygon_crs}")
    
    if point_crs != polygon_crs:
        print(f"   ⚠️  坐标系不一致，但脚本会自动重投影")
    else:
        print(f"   ✅ 坐标系一致")
    
    # 检查输出图层名
    print(f"\n📝 输出图层名称: {OUTPUT_LAYER_NAME}")
    if OUTPUT_LAYER_NAME in layer_names:
        print(f"   ⚠️  已存在同名图层，运行时会自动覆盖")
    else:
        print(f"   ✅ 输出名称可用")
    
    # 总结
    print("\n" + "=" * 80)
    print("✅ 配置检查通过！可以运行主脚本了。")
    print("=" * 80)
    print("\n💡 下一步:")
    print("   在QGIS Python控制台运行:")
    print("   exec(open(str(Path.home() / 'Dev/scripts/projects/qgis/tools/extract_points_in_polygons.py')).read())")
    print("=" * 80 + "\n")
    
    return True


# ============ 执行 ============

if __name__ == '__main__' or __name__ == '__console__':
    try:
        check_configuration()
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 检查过程出错！")
        print("=" * 80)
        print(f"\n错误信息: {str(e)}")
        import traceback
        traceback.print_exc()
        print("=" * 80)

