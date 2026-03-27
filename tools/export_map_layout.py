#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地图出图脚本 - 自动创建带图例、比例尺、指北针的地图布局

📌 说明：
   自动生成专业的地图布局，包含所有必要元素
   
功能：
1. 创建打印布局（Print Layout）
2. 添加地图主体
3. 添加图例（Legend）- 自动包含所有可见图层
4. 添加比例尺（Scale Bar）
5. 添加指北针（North Arrow）
6. 添加标题和其他文本
7. 导出为PNG/PDF/JPG格式

输出：
- 高质量地图图片（默认300 DPI）
- 可配置页面大小（A4/A3/A2等）
- 可配置输出格式（PNG/PDF/JPG）

💡 使用方法：
   1. 在QGIS中调整好地图视图（缩放、平移到合适位置）
   2. 修改配置参数（标题、输出路径等）
   3. 运行此脚本
   4. 在指定路径找到输出的地图

⚙️  配置参数：
   - MAP_TITLE: 地图标题
   - OUTPUT_PATH: 输出文件路径
   - OUTPUT_FORMAT: 输出格式（png/pdf/jpg）
   - PAGE_SIZE: 页面大小（A4/A3/A2/A1/A0）
   - DPI: 输出分辨率（默认300）
   - ORIENTATION: 页面方向（landscape横向/portrait纵向）
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path
from datetime import datetime

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
    QgsProject, QgsLayoutItemMap, QgsLayoutItemLegend, 
    QgsLayoutItemScaleBar, QgsLayoutItemPicture, QgsLayoutItemLabel,
    QgsPrintLayout, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutExporter, QgsLayoutItemShape, QgsReadWriteContext,
    QgsLayoutMeasurement
)
from qgis.PyQt.QtCore import QRectF, QPointF, QSizeF
from qgis.PyQt.QtGui import QFont, QColor

# 导入工具函数库
from qgis_util import (
    print_step,
    print_success,
    print_error,
    print_warning,
    safe_execute
)

# ============ 配置参数 ============

# 地图标题
MAP_TITLE = "景宁县区域分析图"

# 副标题（可选，留空则不显示）
MAP_SUBTITLE = ""

# 输出文件路径（会自动添加时间戳）
OUTPUT_DIR = Path.home() / "Desktop"  # 默认保存到桌面
OUTPUT_FILENAME = "map_export"         # 文件名（不含扩展名）

# 输出格式
OUTPUT_FORMAT = "png"  # 可选: png, pdf, jpg

# 页面设置
PAGE_SIZE = "A3"       # 可选: A4, A3, A2, A1, A0, Custom
ORIENTATION = "landscape"  # landscape(横向) 或 portrait(纵向)

# 自定义页面大小（仅当PAGE_SIZE="Custom"时生效，单位：毫米）
CUSTOM_WIDTH = 420
CUSTOM_HEIGHT = 297

# 分辨率
DPI = 300  # 打印用建议300，屏幕显示用150即可

# 图例设置
SHOW_LEGEND = True      # 是否显示图例
LEGEND_TITLE = "图例"   # 图例标题

# 比例尺设置
SHOW_SCALE_BAR = True   # 是否显示比例尺
SCALE_BAR_UNITS = "m"   # 单位: m(米), km(千米), ft(英尺)

# 指北针设置
SHOW_NORTH_ARROW = True  # 是否显示指北针

# 文本设置
SHOW_DATE = True        # 是否显示日期
SHOW_CREDITS = True     # 是否显示制图信息
CREDITS_TEXT = "数据来源: QGIS"

# 边距（毫米）
MARGIN_TOP = 10
MARGIN_BOTTOM = 10
MARGIN_LEFT = 10
MARGIN_RIGHT = 10

# ============ 页面尺寸定义（毫米） ============
PAGE_SIZES = {
    'A0': (841, 1189),
    'A1': (594, 841),
    'A2': (420, 594),
    'A3': (297, 420),
    'A4': (210, 297),
    'A5': (148, 210),
}

# ============ 主函数 ============

@safe_execute
def create_map_layout():
    """创建地图布局并导出"""
    
    print("\n" + "=" * 80)
    print("🗺️  地图出图 - 自动创建布局")
    print("=" * 80)
    
    project = QgsProject.instance()
    
    # ========== 1. 确定页面尺寸 ==========
    print_step(1, "设置页面尺寸")
    
    if PAGE_SIZE.upper() == 'CUSTOM':
        page_width = CUSTOM_WIDTH
        page_height = CUSTOM_HEIGHT
        print(f"  📄 自定义尺寸: {page_width}×{page_height}mm")
    elif PAGE_SIZE.upper() in PAGE_SIZES:
        width, height = PAGE_SIZES[PAGE_SIZE.upper()]
        if ORIENTATION == 'landscape':
            page_width = max(width, height)
            page_height = min(width, height)
        else:
            page_width = min(width, height)
            page_height = max(width, height)
        print(f"  📄 {PAGE_SIZE} {ORIENTATION}: {page_width}×{page_height}mm")
    else:
        print_error(f"未知的页面尺寸: {PAGE_SIZE}")
        return None
    
    print_success(f"页面尺寸已设置")
    
    # ========== 2. 创建布局 ==========
    print_step(2, "创建打印布局")
    
    # 生成唯一的布局名称
    layout_name = f"map_layout_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 删除同名旧布局
    manager = project.layoutManager()
    old_layout = manager.layoutByName(layout_name)
    if old_layout:
        manager.removeLayout(old_layout)
    
    # 创建新布局
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(layout_name)
    manager.addLayout(layout)
    
    # 设置页面大小
    page_collection = layout.pageCollection()
    page_collection.page(0).setPageSize(QgsLayoutSize(page_width, page_height, QgsUnitTypes.LayoutMillimeters))
    
    print_success(f"布局已创建: {layout_name}")
    
    # ========== 3. 添加地图主体 ==========
    print_step(3, "添加地图主体")
    
    # 计算地图区域（留出边距）
    map_x = MARGIN_LEFT
    map_y = MARGIN_TOP
    map_width = page_width - MARGIN_LEFT - MARGIN_RIGHT
    map_height = page_height - MARGIN_TOP - MARGIN_BOTTOM
    
    # 为标题、图例等预留空间
    title_height = 15 if MAP_TITLE else 0
    bottom_height = 20  # 为比例尺、指北针等预留空间
    
    map_y += title_height
    map_height -= (title_height + bottom_height)
    
    # 创建地图对象
    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(map_width * 0.75, map_height, QgsUnitTypes.LayoutMillimeters))
    
    # 设置地图范围（使用当前画布范围）
    from qgis.utils import iface
    if iface:
        canvas = iface.mapCanvas()
        map_item.setExtent(canvas.extent())
        map_item.setCrs(canvas.mapSettings().destinationCrs())
    
    layout.addLayoutItem(map_item)
    
    print_success(f"地图已添加: {map_width * 0.75:.1f}×{map_height:.1f}mm")
    
    # ========== 4. 添加标题 ==========
    if MAP_TITLE:
        print_step(4, "添加标题")
        
        title_label = QgsLayoutItemLabel(layout)
        title_label.setText(MAP_TITLE)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.adjustSizeToText()
        
        # 居中标题
        title_label.attemptMove(QgsLayoutPoint(
            (page_width - title_label.sizeWithUnits().width()) / 2,
            5,
            QgsUnitTypes.LayoutMillimeters
        ))
        
        layout.addLayoutItem(title_label)
        print_success("标题已添加")
    
    # ========== 5. 添加图例 ==========
    if SHOW_LEGEND:
        print_step(5, "添加图例")
        
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle(LEGEND_TITLE)
        
        # 设置图例位置（右侧）
        legend_x = map_x + map_width * 0.77
        legend_y = map_y
        legend.attemptMove(QgsLayoutPoint(legend_x, legend_y, QgsUnitTypes.LayoutMillimeters))
        
        # 设置图例样式
        legend.setBackgroundEnabled(True)
        legend.setBackgroundColor(QColor(255, 255, 255, 200))
        legend.setFrameEnabled(True)
        legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.5, QgsUnitTypes.LayoutMillimeters))
        
        # 设置字体（使用兼容性更好的方法）
        try:
            # QGIS 3.x 的样式枚举
            from qgis.core import QgsLegendStyle
            title_font = QFont("Arial", 10, QFont.Bold)
            legend.setStyleFont(QgsLegendStyle.Title, title_font)
            
            item_font = QFont("Arial", 8)
            legend.setStyleFont(QgsLegendStyle.Group, item_font)
            legend.setStyleFont(QgsLegendStyle.Subgroup, item_font)
            legend.setStyleFont(QgsLegendStyle.SymbolLabel, item_font)
        except:
            # 如果字体设置失败，使用默认字体
            pass
        
        # 链接到地图
        legend.setLinkedMap(map_item)
        
        # 自动更新
        legend.setAutoUpdateModel(True)
        
        layout.addLayoutItem(legend)
        print_success("图例已添加")
    
    # ========== 6. 添加比例尺 ==========
    if SHOW_SCALE_BAR:
        print_step(6, "添加比例尺")
        
        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setStyle('Single Box')  # 单框样式
        scalebar.setLinkedMap(map_item)
        
        # 设置单位
        if SCALE_BAR_UNITS == 'km':
            scalebar.setUnits(QgsUnitTypes.DistanceKilometers)
            scalebar.setUnitLabel('km')
        elif SCALE_BAR_UNITS == 'ft':
            scalebar.setUnits(QgsUnitTypes.DistanceFeet)
            scalebar.setUnitLabel('ft')
        else:
            scalebar.setUnits(QgsUnitTypes.DistanceMeters)
            scalebar.setUnitLabel('m')
        
        # 设置位置（地图左下角）
        scalebar_x = map_x + 10
        scalebar_y = map_y + map_height - 15
        scalebar.attemptMove(QgsLayoutPoint(scalebar_x, scalebar_y, QgsUnitTypes.LayoutMillimeters))
        
        # 设置样式
        scalebar.setNumberOfSegments(4)
        scalebar.setHeight(3)
        scalebar.setFont(QFont("Arial", 8))
        
        layout.addLayoutItem(scalebar)
        print_success("比例尺已添加")
    
    # ========== 7. 添加指北针 ==========
    if SHOW_NORTH_ARROW:
        print_step(7, "添加指北针")
        
        north_arrow = QgsLayoutItemPicture(layout)
        
        # 使用QGIS内置的指北针图标
        # 尝试几个常见的指北针SVG路径
        svg_paths = [
            '/usr/share/qgis/svg/arrows/NorthArrow_04.svg',
            '/Applications/QGIS.app/Contents/Resources/svg/arrows/NorthArrow_04.svg',
            'base64:...'  # 可以使用base64编码的SVG
        ]
        
        # 尝试找到可用的SVG
        for svg_path in svg_paths:
            if Path(svg_path).exists():
                north_arrow.setPicturePath(svg_path)
                break
        else:
            # 如果找不到，使用默认符号
            print_warning("未找到指北针SVG，将使用默认样式")
        
        # 设置位置（地图右下角）
        arrow_size = 15
        arrow_x = map_x + map_width * 0.75 - arrow_size - 10
        arrow_y = map_y + map_height - arrow_size - 5
        north_arrow.attemptMove(QgsLayoutPoint(arrow_x, arrow_y, QgsUnitTypes.LayoutMillimeters))
        north_arrow.attemptResize(QgsLayoutSize(arrow_size, arrow_size, QgsUnitTypes.LayoutMillimeters))
        
        # 链接到地图（自动旋转）
        north_arrow.setLinkedMap(map_item)
        north_arrow.setNorthMode(QgsLayoutItemPicture.GridNorth)
        
        layout.addLayoutItem(north_arrow)
        print_success("指北针已添加")
    
    # ========== 8. 添加日期和制图信息 ==========
    bottom_y = page_height - MARGIN_BOTTOM - 5
    
    if SHOW_DATE:
        date_label = QgsLayoutItemLabel(layout)
        date_label.setText(f"制图日期: {datetime.now().strftime('%Y-%m-%d')}")
        date_label.setFont(QFont("Arial", 7))
        date_label.adjustSizeToText()
        date_label.attemptMove(QgsLayoutPoint(MARGIN_LEFT, bottom_y, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(date_label)
    
    if SHOW_CREDITS:
        credits_label = QgsLayoutItemLabel(layout)
        credits_label.setText(CREDITS_TEXT)
        credits_label.setFont(QFont("Arial", 7))
        credits_label.adjustSizeToText()
        credits_label.attemptMove(QgsLayoutPoint(
            page_width - MARGIN_RIGHT - credits_label.sizeWithUnits().width(),
            bottom_y,
            QgsUnitTypes.LayoutMillimeters
        ))
        layout.addLayoutItem(credits_label)
    
    # ========== 9. 导出地图 ==========
    print_step(8, "导出地图")
    
    # 生成输出文件路径
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = OUTPUT_DIR / f"{OUTPUT_FILENAME}_{timestamp}.{OUTPUT_FORMAT}"
    
    # 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 创建导出器
    exporter = QgsLayoutExporter(layout)
    
    # 根据格式导出
    if OUTPUT_FORMAT.lower() == 'pdf':
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = DPI
        result = exporter.exportToPdf(str(output_file), settings)
    elif OUTPUT_FORMAT.lower() == 'jpg':
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = DPI
        result = exporter.exportToImage(str(output_file), settings)
    else:  # png (default)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = DPI
        result = exporter.exportToImage(str(output_file), settings)
    
    # 检查导出结果
    if result == QgsLayoutExporter.Success:
        print_success(f"地图已导出: {output_file}")
        print(f"  📊 文件大小: {output_file.stat().st_size / 1024:.1f} KB")
        print(f"  🎨 分辨率: {DPI} DPI")
        print(f"  📐 尺寸: {page_width}×{page_height}mm")
    else:
        print_error(f"导出失败: {result}")
        return None
    
    # ========== 10. 完成 ==========
    print("\n" + "=" * 80)
    print("✅ 地图出图完成！")
    print("=" * 80)
    print(f"\n📁 输出文件:")
    print(f"   {output_file}")
    print(f"\n📊 布局信息:")
    print(f"   • 布局名称: {layout_name}")
    print(f"   • 页面尺寸: {PAGE_SIZE} {ORIENTATION}")
    print(f"   • 输出格式: {OUTPUT_FORMAT.upper()}")
    print(f"   • 分辨率: {DPI} DPI")
    print(f"\n🎨 包含元素:")
    if MAP_TITLE:
        print(f"   ✓ 标题: {MAP_TITLE}")
    if SHOW_LEGEND:
        print(f"   ✓ 图例")
    if SHOW_SCALE_BAR:
        print(f"   ✓ 比例尺")
    if SHOW_NORTH_ARROW:
        print(f"   ✓ 指北针")
    if SHOW_DATE:
        print(f"   ✓ 日期")
    print("=" * 80)
    
    return {
        'layout': layout,
        'output_file': output_file
    }


# ============ 执行 ============

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("🗺️  地图出图脚本开始执行...")
        print("=" * 80)
        print(f"\n⚙️  当前配置:")
        print(f"   • 标题: {MAP_TITLE}")
        print(f"   • 页面: {PAGE_SIZE} {ORIENTATION}")
        print(f"   • 格式: {OUTPUT_FORMAT.upper()} ({DPI} DPI)")
        print(f"   • 输出: {OUTPUT_DIR / f'{OUTPUT_FILENAME}_*.{OUTPUT_FORMAT}'}")
        print(f"   • 图例: {'是' if SHOW_LEGEND else '否'}")
        print(f"   • 比例尺: {'是' if SHOW_SCALE_BAR else '否'}")
        print(f"   • 指北针: {'是' if SHOW_NORTH_ARROW else '否'}")
        
        result = create_map_layout()
        
        if result:
            print("\n✅ 脚本执行成功！")
            print(f"\n💡 提示: 文件已保存到")
            print(f"   {result['output_file']}")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    import subprocess
                    
                    msg = f"✅ 地图导出成功！\n\n"
                    msg += f"📁 文件路径:\n{result['output_file']}\n\n"
                    msg += f"📊 格式: {OUTPUT_FORMAT.upper()} ({DPI} DPI)\n"
                    msg += f"📐 尺寸: {PAGE_SIZE} {ORIENTATION}"
                    
                    reply = QMessageBox.information(
                        None, 
                        "导出完成", 
                        msg,
                        QMessageBox.Open | QMessageBox.Ok,
                        QMessageBox.Ok
                    )
                    
                    # 如果点击打开，则打开文件所在文件夹
                    if reply == QMessageBox.Open:
                        subprocess.run(['open', '-R', str(result['output_file'])])
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

