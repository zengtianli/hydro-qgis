#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蒙版配置检查工具 - 验证图层是否存在并预览效果
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
INNER_LAYER = "jingning"        # 内部区域
OUTER_LAYER = "all"             # 外部区域："all" 或具体图层名
INNER_OPACITY = 50              # 内部透明度
OUTER_OPACITY = 10              # 外部透明度

# ============ 检查函数 ============

def check_mask_configuration():
    """检查蒙版配置"""
    
    print("\n" + "=" * 80)
    print("🔍 蒙版配置检查工具")
    print("=" * 80)
    
    print(f"\n📋 当前配置:")
    print(f"   • 内部区域: {INNER_LAYER} (透明度 {INNER_OPACITY}%)")
    outer_display = "整个地图画布范围" if OUTER_LAYER.lower() == "all" else OUTER_LAYER
    print(f"   • 外部区域: {outer_display} (透明度 {OUTER_OPACITY}%)")
    
    # 获取当前项目中的所有图层
    project = QgsProject.instance()
    all_layers = project.mapLayers()
    
    if not all_layers:
        print("\n❌ 错误: QGIS项目中没有加载任何图层！")
        print("   请先在QGIS中加载你的数据。")
        return False
    
    print(f"\n📊 QGIS项目中的所有图层({len(all_layers)}个):")
    layer_names = []
    polygon_layers = []
    
    for layer_id, layer in all_layers.items():
        layer_name = layer.name()
        layer_names.append(layer_name)
        
        # 获取几何类型
        geom_type = layer.geometryType()
        type_name = ['点', '线', '面'][geom_type] if geom_type in [0, 1, 2] else '未知'
        
        print(f"   • {layer_name} ({type_name})")
        
        if geom_type == 2:  # 面
            polygon_layers.append(layer_name)
    
    # 检查内部区域图层
    print(f"\n🔍 检查内部区域图层: {INNER_LAYER}")
    inner_ok = False
    if INNER_LAYER in layer_names:
        layer = project.mapLayersByName(INNER_LAYER)[0]
        geom_type = layer.geometryType()
        if geom_type == 2:
            area = sum(f.geometry().area() for f in layer.getFeatures()) / 1_000_000
            print(f"   ✅ 找到面图层，包含 {layer.featureCount()} 个面")
            print(f"   📐 总面积: {area:.2f} km²")
            print(f"   🎨 将应用白色蒙版，透明度 {INNER_OPACITY}%")
            inner_ok = True
        else:
            type_name = ['点', '线', '面'][geom_type]
            print(f"   ⚠️  警告: 找到图层，但不是面图层（当前类型: {type_name}）")
            print(f"   💡 可用的面图层: {', '.join(polygon_layers) if polygon_layers else '无'}")
    else:
        print(f"   ❌ 找不到图层: {INNER_LAYER}")
        print(f"   💡 可用的面图层: {', '.join(polygon_layers) if polygon_layers else '无'}")
        if polygon_layers:
            print(f"\n   建议修改配置为:")
            print(f"   INNER_LAYER = \"{polygon_layers[0]}\"")
    
    # 检查外部区域图层
    use_full_canvas = (OUTER_LAYER.lower() == "all" or OUTER_LAYER is None)
    
    print(f"\n🔍 检查外部区域图层: {OUTER_LAYER}")
    outer_ok = False
    
    if use_full_canvas:
        print(f"   💡 外部区域设置为 'all'，将使用整个地图画布范围")
        print(f"   ✅ 自动创建覆盖整个地图的蒙版")
        print(f"   🎨 将应用白色蒙版（扣除{INNER_LAYER}后），透明度 {OUTER_OPACITY}%")
        outer_ok = True
    elif OUTER_LAYER in layer_names:
        layer = project.mapLayersByName(OUTER_LAYER)[0]
        geom_type = layer.geometryType()
        if geom_type == 2:
            area = sum(f.geometry().area() for f in layer.getFeatures()) / 1_000_000
            print(f"   ✅ 找到面图层，包含 {layer.featureCount()} 个面")
            print(f"   📐 总面积: {area:.2f} km²")
            print(f"   🎨 将应用白色蒙版（扣除内部后），透明度 {OUTER_OPACITY}%")
            outer_ok = True
        else:
            type_name = ['点', '线', '面'][geom_type]
            print(f"   ⚠️  警告: 找到图层，但不是面图层（当前类型: {type_name}）")
            print(f"   💡 可用的面图层: {', '.join(polygon_layers) if polygon_layers else '无'}")
    else:
        print(f"   ❌ 找不到图层: {OUTER_LAYER}")
        print(f"   💡 可用的面图层: {', '.join(polygon_layers) if polygon_layers else '无'}")
        if polygon_layers:
            print(f"\n   建议修改配置为:")
            print(f"   OUTER_LAYER = \"{polygon_layers[0]}\"")
    
    if not (inner_ok and outer_ok):
        return False
    
    # 检查坐标系
    inner_layer = project.mapLayersByName(INNER_LAYER)[0]
    inner_crs = inner_layer.crs().authid()
    
    print(f"\n🗺️  坐标系检查:")
    print(f"   • 内部区域: {inner_crs}")
    
    if not use_full_canvas:
        outer_layer = project.mapLayersByName(OUTER_LAYER)[0]
        outer_crs = outer_layer.crs().authid()
        print(f"   • 外部区域: {outer_crs}")
        
        if inner_crs != outer_crs:
            print(f"   ⚠️  坐标系不一致，但脚本会自动重投影")
        else:
            print(f"   ✅ 坐标系一致")
    else:
        print(f"   • 外部区域: 将使用与内部区域相同的坐标系({inner_crs})")
        print(f"   ✅ 坐标系自动匹配")
    
    # 检查空间关系（简单检查边界框）
    print(f"\n📍 空间关系检查:")
    inner_bbox = inner_layer.extent()
    
    print(f"   • {INNER_LAYER} 范围: ({inner_bbox.xMinimum():.2f}, {inner_bbox.yMinimum():.2f}) - ({inner_bbox.xMaximum():.2f}, {inner_bbox.yMaximum():.2f})")
    
    if not use_full_canvas:
        outer_bbox = outer_layer.extent()
        print(f"   • {OUTER_LAYER} 范围: ({outer_bbox.xMinimum():.2f}, {outer_bbox.yMinimum():.2f}) - ({outer_bbox.xMaximum():.2f}, {outer_bbox.yMaximum():.2f})")
        
        if outer_bbox.contains(inner_bbox):
            print(f"   ✅ {INNER_LAYER} 在 {OUTER_LAYER} 范围内")
        else:
            print(f"   ⚠️  警告: {INNER_LAYER} 可能不完全在 {OUTER_LAYER} 内")
            print(f"   说明: 这可能影响蒙版效果，但不会导致错误")
    else:
        # 计算扩大后的范围
        center_x = (inner_bbox.xMinimum() + inner_bbox.xMaximum()) / 2
        center_y = (inner_bbox.yMinimum() + inner_bbox.yMaximum()) / 2
        width = inner_bbox.width() * 3
        height = inner_bbox.height() * 3
        print(f"   • 外部蒙版范围: 将扩大为 {width:.0f}×{height:.0f}m (3倍于内部区域)")
        print(f"   ✅ 足够覆盖整个地图区域")
    
    # 预览效果
    print(f"\n🎨 蒙版效果预览:")
    outer_label = "整个地图范围" if use_full_canvas else OUTER_LAYER
    print(f"   ┌─────────────────────────────────────────┐")
    print(f"   │  {outer_label} (白色{OUTER_OPACITY}%透明)    ")
    print(f"   │                                         │")
    print(f"   │    ┌───────────────────────┐            │")
    print(f"   │    │  {INNER_LAYER}          ")
    print(f"   │    │  (白色{INNER_OPACITY}%透明)        ")
    print(f"   │    └───────────────────────┘            │")
    print(f"   │                                         │")
    print(f"   └─────────────────────────────────────────┘")
    
    if INNER_OPACITY > OUTER_OPACITY:
        print(f"\n   💡 视觉效果: {INNER_LAYER} 更透明（突出显示）")
        if use_full_canvas:
            print(f"   💡 地图其他所有区域都被白色蒙版遮挡")
    else:
        print(f"\n   💡 视觉效果: {INNER_LAYER} 更不透明（强调显示）")
    
    # 总结
    print("\n" + "=" * 80)
    print("✅ 配置检查通过！可以运行蒙版生成脚本了。")
    print("=" * 80)
    print("\n💡 下一步:")
    print("   在QGIS Python控制台运行:")
    print("   exec(open(str(Path.home() / 'Dev/scripts/projects/qgis/tools/create_mask_layers.py')).read())")
    print("=" * 80 + "\n")
    
    return True


# ============ 执行 ============

if __name__ == '__main__' or __name__ == '__console__':
    try:
        check_mask_configuration()
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 检查过程出错！")
        print("=" * 80)
        print(f"\n错误信息: {str(e)}")
        import traceback
        traceback.print_exc()
        print("=" * 80)

