#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蒙版图层生成脚本 - 创建差异化透明度的蒙版效果

📌 说明：
   创建两个蒙版图层，实现区域内外不同透明度的视觉效果
   
功能：
1. 对内部区域（如县）应用高透明度白色蒙版（50%）
2. 对外部区域（扣除内部）应用低透明度白色蒙版（10%）
3. 自动进行空间差集运算（外部 - 内部）
4. 自动设置图层样式（颜色、透明度）
5. 图层命名清晰，方便管理

输入图层：
- 内部区域图层：例如 jingning（景宁县）
- 外部区域图层：
  * "all" - 使用整个地图画布范围（推荐）
  * 或指定具体图层名，例如 "county"（丽水市）

输出图层：
- [内部区域]_mask: 白色蒙版，透明度50%
- all_excluding_[内部]_mask: 白色蒙版，透明度10%（如果外部="all"）
- [外部区域]_excluding_[内部]_mask: 白色蒙版，透明度10%（如果指定外部图层）

💡 使用场景：
   - 地图可视化中突出显示某个区域
   - 创建关注区域的视觉层次
   - 数据演示时强调特定范围

⚙️  配置参数：
   - INNER_LAYER: 内部区域图层名称（高透明度）
   - OUTER_LAYER: 外部区域图层名称（低透明度）
   - INNER_OPACITY: 内部区域透明度 (0-100, 默认50)
   - OUTER_OPACITY: 外部区域透明度 (0-100, 默认10)
   - MASK_COLOR: 蒙版颜色 (默认白色)

📝 示例效果（OUTER_LAYER = "all"）：
   ┌─────────────────────────────────────┐
   │  整个地图范围 (白色10%透明)         │
   │                                     │
   │    ┌─────────────────┐              │
   │    │  Jingning       │              │
   │    │  (白色50%透明)  │ ← 突出显示  │
   │    │                 │              │
   │    └─────────────────┘              │
   │                                     │
   │  ← 其他区域被白色蒙版遮挡           │
   └─────────────────────────────────────┘
   
   视觉效果：Jingning区域更透明，能更清楚看到底图
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
    lib_dir = script_dir.parent / 'lib'
    for path in [str(script_dir), str(lib_dir)]:
        if path not in sys.path:
            sys.path.insert(0, path)

_setup_paths()
# ============ 路径设置结束 ============

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsSymbol, QgsFillSymbol,
    QgsSimpleFillSymbolLayer, QgsWkbTypes
)
from qgis.PyQt.QtGui import QColor
import processing

# 导入工具函数库
from qgis_util import (
    move_layer_to_group,
    get_layer_by_name,
    ensure_group_exists,
    fix_geometries,
    reproject_layer_if_needed,
    check_crs_consistency,
    print_step,
    print_success,
    print_error,
    print_warning,
    safe_execute
)

# ============ 配置参数 ============

# 输入图层名称
INNER_LAYER = "wucheng"        # 内部区域（高透明度）
OUTER_LAYER = "all"             # 外部区域（低透明度）
                                # "all" = 整个地图画布范围（推荐）
                                # 或指定具体图层名如 "county"

# 透明度设置 (0-100)
# 100 = 完全不透明，0 = 完全透明
INNER_OPACITY = 60              # 内部区域透明度（更透明，突出显示）
OUTER_OPACITY = 80              # 外部区域透明度（更不透明，弱化显示）

# 蒙版颜色 (RGB)
MASK_COLOR = (255, 255, 255)    # 白色，可以改为其他颜色如 (0, 0, 0) 黑色

# 输出图层名称（自动生成）
INNER_MASK_NAME = f"{INNER_LAYER}_mask"
OUTER_MASK_NAME = f"{'all' if OUTER_LAYER.lower() == 'all' else OUTER_LAYER}_excluding_{INNER_LAYER}_mask"

# 输出组名称
OUTPUT_GROUP = "mask_layers"

# ============ 辅助函数 ============

def apply_mask_style(layer, opacity, color=(255, 255, 255)):
    """
    为图层应用蒙版样式
    
    参数:
        layer: QGIS矢量图层
        opacity: 透明度 (0-100)
        color: RGB颜色元组，默认白色
    """
    # 创建简单填充符号
    symbol = QgsFillSymbol.createSimple({
        'color': f'{color[0]},{color[1]},{color[2]},{int(255 * opacity / 100)}',  # RGBA
        'outline_style': 'no',  # 无边框
    })
    
    # 应用符号
    layer.renderer().setSymbol(symbol)
    layer.triggerRepaint()
    
    print(f"  ✅ 已应用样式: RGB{color}, 透明度{opacity}%")


# ============ 主函数 ============

@safe_execute
def create_mask_layers():
    """创建蒙版图层"""
    
    print("\n" + "=" * 80)
    print("🎭 蒙版图层生成 - 差异化透明度效果")
    print("=" * 80)
    
    # ========== 1. 加载图层 ==========
    print_step(1, "加载输入图层")
    
    # 加载内部区域图层
    inner_layer = get_layer_by_name(INNER_LAYER)
    if not inner_layer:
        print_error(f"找不到内部区域图层 '{INNER_LAYER}'")
        return None
    
    # 验证是否为面图层
    if inner_layer.geometryType() != 2:
        print_error(f"'{INNER_LAYER}' 不是面图层")
        return None
    
    move_layer_to_group(inner_layer, "input")
    print_success(f"内部区域: {inner_layer.featureCount()}个面 | {inner_layer.crs().authid()}")
    
    # 加载外部区域图层（支持 "all" 选项）
    use_full_canvas = (OUTER_LAYER.lower() == "all" or OUTER_LAYER is None)
    
    if use_full_canvas:
        print(f"\n  💡 外部区域设置为 'all'，将使用整个地图画布范围")
        
        # 创建覆盖整个画布的矩形
        from qgis.core import QgsRectangle, QgsFeature, QgsGeometry
        
        # 获取内部图层的范围，然后扩大
        inner_extent = inner_layer.extent()
        
        # 扩大边界（扩大到原范围的3倍）
        center_x = (inner_extent.xMinimum() + inner_extent.xMaximum()) / 2
        center_y = (inner_extent.yMinimum() + inner_extent.yMaximum()) / 2
        width = inner_extent.width() * 3
        height = inner_extent.height() * 3
        
        canvas_extent = QgsRectangle(
            center_x - width / 2,
            center_y - height / 2,
            center_x + width / 2,
            center_y + height / 2
        )
        
        # 创建矩形面图层
        geom_type = "Polygon"
        outer_layer = QgsVectorLayer(
            f"{geom_type}?crs={inner_layer.crs().authid()}",
            "canvas_extent",
            "memory"
        )
        
        outer_provider = outer_layer.dataProvider()
        outer_layer.updateFields()
        
        # 创建矩形要素
        canvas_feature = QgsFeature()
        canvas_feature.setGeometry(QgsGeometry.fromRect(canvas_extent))
        outer_provider.addFeatures([canvas_feature])
        
        print_success(f"外部区域: 画布范围 {canvas_extent.width():.0f}×{canvas_extent.height():.0f}m | {outer_layer.crs().authid()}")
        
    else:
        # 使用指定的图层
        outer_layer = get_layer_by_name(OUTER_LAYER)
        if not outer_layer:
            print_error(f"找不到外部区域图层 '{OUTER_LAYER}'")
            print(f"\n  💡 提示: 如果想使用整个地图范围，可以设置:")
            print(f"     OUTER_LAYER = \"all\"")
            return None
        
        # 验证是否为面图层
        if outer_layer.geometryType() != 2:
            print_error(f"'{OUTER_LAYER}' 不是面图层")
            return None
        
        move_layer_to_group(outer_layer, "input")
        print_success(f"外部区域: {outer_layer.featureCount()}个面 | {outer_layer.crs().authid()}")
    
    # ========== 2. 坐标系检查与重投影 ==========
    print_step(2, "坐标系检查")
    check_crs_consistency(inner_layer, outer_layer, "内部区域", "外部区域")
    inner_layer = reproject_layer_if_needed(inner_layer, outer_layer.crs(), "内部区域")
    
    # ========== 3. 几何修复 ==========
    print_step(3, "修复几何")
    inner_layer = fix_geometries(inner_layer, "内部区域")
    outer_layer = fix_geometries(outer_layer, "外部区域")
    
    # ========== 4. 创建内部区域蒙版（直接复制） ==========
    print_step(4, f"创建内部区域蒙版 [{INNER_OPACITY}%透明度]")
    
    print(f"  🔄 复制 {INNER_LAYER} 图层...")
    
    # 创建内存图层
    geom_type = QgsWkbTypes.displayString(inner_layer.wkbType())
    inner_mask = QgsVectorLayer(
        f"{geom_type}?crs={inner_layer.crs().authid()}",
        INNER_MASK_NAME,
        "memory"
    )
    
    # 复制要素
    inner_mask.dataProvider().addAttributes(inner_layer.fields().toList())
    inner_mask.updateFields()
    inner_mask.dataProvider().addFeatures(list(inner_layer.getFeatures()))
    
    # 应用蒙版样式
    apply_mask_style(inner_mask, INNER_OPACITY, MASK_COLOR)
    
    print_success(f"内部蒙版创建完成: {inner_mask.featureCount()}个要素")
    
    # ========== 5. 创建外部区域蒙版（差集运算） ==========
    print_step(5, f"创建外部区域蒙版 [{OUTER_OPACITY}%透明度]")
    
    print(f"  🔄 计算空间差集: {OUTER_LAYER} - {INNER_LAYER}...")
    
    # 执行差集运算
    difference_result = processing.run("native:difference", {
        'INPUT': outer_layer,
        'OVERLAY': inner_layer,
        'OUTPUT': 'memory:'
    })
    
    outer_mask = difference_result['OUTPUT']
    outer_mask.setName(OUTER_MASK_NAME)
    
    # 应用蒙版样式
    apply_mask_style(outer_mask, OUTER_OPACITY, MASK_COLOR)
    
    print_success(f"外部蒙版创建完成: {outer_mask.featureCount()}个要素")
    
    # ========== 6. 添加到项目 ==========
    print_step(6, "添加到QGIS项目")
    
    project = QgsProject.instance()
    mask_group = ensure_group_exists(OUTPUT_GROUP)
    
    # 移除旧的蒙版图层
    for layer_name in [INNER_MASK_NAME, OUTER_MASK_NAME]:
        existing = project.mapLayersByName(layer_name)
        if existing:
            project.removeMapLayer(existing[0])
            print(f"  🗑️  已移除旧图层: {layer_name}")
    
    # 添加新图层（先添加外部，再添加内部，这样内部在上层）
    project.addMapLayer(outer_mask, False)
    mask_group.addLayer(outer_mask)
    print_success(f"已添加: {OUTER_MASK_NAME}")
    
    project.addMapLayer(inner_mask, False)
    mask_group.addLayer(inner_mask)
    print_success(f"已添加: {INNER_MASK_NAME}")
    
    # ========== 7. 统计信息 ==========
    print_step(7, "蒙版效果说明")
    
    # 计算面积
    inner_area = sum(f.geometry().area() for f in inner_mask.getFeatures()) / 1_000_000  # 转为km²
    outer_area = sum(f.geometry().area() for f in outer_mask.getFeatures()) / 1_000_000
    
    print(f"  📊 区域统计:")
    print(f"     • 内部区域({INNER_LAYER}): {inner_area:.2f} km² | 白色蒙版 {INNER_OPACITY}%透明")
    outer_desc = "整个地图范围(扣除后)" if use_full_canvas else f"{OUTER_LAYER}(扣除后)"
    print(f"     • 外部区域({outer_desc}): {outer_area:.2f} km² | 白色蒙版 {OUTER_OPACITY}%透明")
    print(f"     • 透明度差异: {abs(INNER_OPACITY - OUTER_OPACITY)}% (突出显示效果)")
    
    print(f"\n  🎨 视觉效果:")
    if INNER_OPACITY > OUTER_OPACITY:
        print(f"     • {INNER_LAYER} 更透明，底图更清晰（关注区域）")
        outer_desc2 = "其他区域" if use_full_canvas else OUTER_LAYER
        print(f"     • {outer_desc2} 更不透明，底图被遮挡（背景区域）")
    else:
        print(f"     • {INNER_LAYER} 更不透明（强调区域）")
        outer_desc2 = "其他区域" if use_full_canvas else OUTER_LAYER
        print(f"     • {outer_desc2} 更透明（弱化区域）")
    
    print(f"\n  💡 使用提示:")
    print(f"     1. 蒙版图层在 '{OUTPUT_GROUP}' 组中")
    print(f"     2. 确保底图图层在蒙版下方")
    print(f"     3. 可在图层面板中调整透明度")
    print(f"     4. 可右键图层 → 样式 → 修改颜色")
    
    # ========== 8. 完成 ==========
    print("\n" + "=" * 80)
    print(f"✅ 蒙版图层创建完成！")
    print(f"   输出组: {OUTPUT_GROUP}")
    print(f"   图层:")
    print(f"     • {INNER_MASK_NAME} (透明度 {INNER_OPACITY}%)")
    print(f"     • {OUTER_MASK_NAME} (透明度 {OUTER_OPACITY}%)")
    print("=" * 80)
    
    return {
        'inner_mask': inner_mask,
        'outer_mask': outer_mask
    }


# ============ 执行 ============

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("🎭 蒙版图层生成脚本开始执行...")
        print("=" * 80)
        print(f"\n⚙️  当前配置:")
        print(f"   • 内部区域: {INNER_LAYER} (透明度 {INNER_OPACITY}%)")
        outer_display = "整个地图画布范围" if OUTER_LAYER.lower() == "all" else OUTER_LAYER
        print(f"   • 外部区域: {outer_display} (透明度 {OUTER_OPACITY}%)")
        print(f"   • 蒙版颜色: RGB{MASK_COLOR}")
        print(f"   • 输出组: {OUTPUT_GROUP}")
        
        result = create_mask_layers()
        
        if result:
            print("\n✅ 脚本执行成功！请查看生成的蒙版图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ 蒙版图层创建完成！\n\n"
                    msg += f"📁 位置: {OUTPUT_GROUP} 组\n\n"
                    msg += f"生成的图层:\n"
                    msg += f"  • {INNER_MASK_NAME}\n"
                    msg += f"    (透明度 {INNER_OPACITY}%)\n\n"
                    msg += f"  • {OUTER_MASK_NAME}\n"
                    msg += f"    (透明度 {OUTER_OPACITY}%)\n\n"
                    msg += f"💡 确保底图在蒙版下方以查看效果"
                    
                    QMessageBox.information(None, "处理完成", msg)
            except:
                pass
        else:
            print("\n❌ 脚本执行失败，请检查错误信息。")
            
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 脚本执行出错！")
        print("=" * 80)
        print(f"\n错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print(f"\n详细堆栈:")
        import traceback
        traceback.print_exc()
        print("=" * 80)

# 自动运行
if __name__ == '__main__' or __name__ == '__console__':
    main()

