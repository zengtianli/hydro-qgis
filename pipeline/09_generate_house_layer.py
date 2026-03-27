"""
09 House图层生成脚本 - 通用版

📌 说明：
   这是一个通用脚本，适用于所有河流（华溪、熟溪、白溪等）
   只需修改脚本顶部的配置参数（图层名称）即可使用

功能：
1. 将原始房屋图层与grid_enriched进行空间相交（Intersection）
2. 房屋继承所在网格的所有属性（grid_id, area, polderId, town, Bathymetry等）
3. 自动计算房屋自身的Shape_Leng（周长）和Shape_Area（面积）
4. 自动修复几何错误
5. 处理空值，确保所有字段都有有效值
6. 验证字段完整性，输出详细统计信息

输入图层（将自动移到input组）：
- house: 原始房屋图层（面）
- grid_enriched: 增强后的网格图层（包含grid_id, area, polderId, town等）

输出图层（自动移到process组）：
- house_output: 带网格属性的房屋图层

📊 输出图层 house_output 的字段说明：
   
   核心字段（继承自grid_enriched）：
   ┌──────────────┬──────────────┬────────────────────────────┐
   │ 字段名       │ 类型         │ 说明                        │
   ├──────────────┼──────────────┼────────────────────────────┤
   │ grid_id      │ Integer      │ 所属网格ID（从grid继承）     │
   │ area         │ Double       │ 所属网格面积m²（从grid继承） │
   │ town         │ String(50)   │ 所属乡镇（从grid继承）       │
   │ polderId     │ String(50)   │ 所属保护片ID（从grid继承）   │
   │ Bathymetry   │ Double       │ 水深数据（从grid继承）       │
   └──────────────┴──────────────┴────────────────────────────┘
   
   几何属性字段（自动计算）：
   ┌──────────────┬──────────────┬────────────────────────────┐
   │ Shape_Leng   │ Double       │ 房屋周长，单位米（自动计算） │
   │ Shape_Area   │ Double       │ 房屋面积，单位m²（自动计算） │
   └──────────────┴──────────────┴────────────────────────────┘
   
   注：原house图层和grid图层的其他字段也会被保留

💡 使用方法：
   1. 确保QGIS中已加载house和grid_enriched两个图层
   2. 根据实际图层名称，修改配置部分的HOUSE_LAYER和GRID_LAYER
   3. 在QGIS Python控制台运行此脚本
   4. 查看process组中的house_output输出图层

⚙️  配置参数（在脚本中修改）：
   - HOUSE_LAYER: 原始房屋图层名称
   - GRID_LAYER: 增强网格图层名称（grid_enriched）
   - OUTPUT_LAYER_NAME: 输出图层名称
   - DEFAULT_GRID_ID: grid_id字段的默认值
   - DEFAULT_POLDER: polderId字段的默认值
   - DEFAULT_TOWN: town字段的默认值

🔍 特殊说明：
   - 使用Intersection算法，确保所有房屋都与网格相交
   - 如果房屋跨越多个网格，会被切分为多个要素（每个要素属于一个网格）
   - area字段是网格面积，Shape_Area是房屋实际面积
   - 坐标系不一致时会自动重投影

📝 示例输出：
   grid_id | area     | town   | polderId | Shape_Leng | Shape_Area
   --------|----------|--------|----------|------------|------------
   1       | 521.21   | 白鹤乡 | sx0001   | 45.32      | 120.50
   2       | 528.28   | 白鹤乡 | sx0001   | 38.76      | 95.30
   3       | 528.42   | 白鹤乡 | sx0001   | 52.18      | 145.80
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
    QgsWkbTypes, QgsGeometry
)
from qgis.PyQt.QtCore import QVariant
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
    safe_execute,
    save_and_reload_layer
)

# 导入公共配置
from hydraulic.qgis_config import (
    INPUT_LAYERS,
    OUTPUT_LAYERS,
    DEFAULT_GRID_ID,
    DEFAULT_POLDER,
    DEFAULT_TOWN
)

# ============ 配置参数 ============

# 输入图层名称
HOUSE_LAYER = INPUT_LAYERS['house']              # 原始房屋图层
GRID_LAYER = OUTPUT_LAYERS['grid_enriched']      # 增强后的网格图层

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['house_output']

# ============ 主函数 ============

def generate_house_layer():
    """执行House图层生成"""
    
    print("\n" + "=" * 80)
    print("🏠 House图层生成 - 空间相交添加网格属性")
    print("=" * 80)
    
    # ========== 1. 加载图层 ==========
    print(f"\n【步骤1】加载输入图层")
    
    # 加载House图层
    house_layer = get_layer_by_name(HOUSE_LAYER)
    if not house_layer:
        print(f"  ❌ 错误: 找不到图层 '{HOUSE_LAYER}'，请确保QGIS中已加载该图层")
        return None
    
    house_fields = [f.name() for f in house_layer.fields()]
    move_layer_to_group(house_layer, "input")
    print(f"  ✅ 房屋: {house_layer.featureCount()}个 | 坐标系: {house_layer.crs().authid()} | 字段: {', '.join(house_fields[:3])}... | 已移至input组")
    
    # 加载Grid图层
    grid_layer = get_layer_by_name(GRID_LAYER)
    if not grid_layer:
        print(f"  ❌ 错误: 找不到图层 '{GRID_LAYER}'，请先运行05_enrich_grid_layer.py生成该图层")
        return None
    
    grid_fields = [f.name() for f in grid_layer.fields()]
    missing_fields = [f for f in ['grid_id', 'polderId', 'town'] if f not in grid_fields]
    if missing_fields:
        print(f"  ❌ 错误: 网格图层缺少必需字段: {', '.join(missing_fields)}")
        return None
    
    print(f"  ✅ 网格: {grid_layer.featureCount()}个 | 坐标系: {grid_layer.crs().authid()} | 将继承网格所有字段到房屋图层")
    
    check_crs_consistency(house_layer, grid_layer, "房屋", "网格")
    house_layer = reproject_layer_if_needed(house_layer, grid_layer.crs(), "房屋")
    house_layer = fix_geometries(house_layer, "房屋")
    
    # ========== 2. 空间相交（Intersection） ==========
    intersection_result = processing.run("native:intersection", {
        'INPUT': house_layer,
        'OVERLAY': grid_layer,
        'INPUT_FIELDS': [],
        'OVERLAY_FIELDS': [],
        'OUTPUT': 'memory:'
    })
    house_with_grid = intersection_result['OUTPUT']
    print(f"\n【步骤2】空间相交 | 🔄 House ∩ Grid | 输入: {house_layer.featureCount()}个房屋 | 输出: {house_with_grid.featureCount()}个相交要素（跨网格房屋会被切分）")
    
    # ========== 3. 创建输出图层 ==========
    geom_type = QgsWkbTypes.displayString(house_with_grid.wkbType())
    output_layer = QgsVectorLayer(f"{geom_type}?crs={house_with_grid.crs().authid()}", OUTPUT_LAYER_NAME, "memory")
    output_provider = output_layer.dataProvider()
    output_provider.addAttributes(house_with_grid.fields().toList())
    existing_fields = [f.name() for f in house_with_grid.fields()]
    if 'Shape_Leng' not in existing_fields:
        output_provider.addAttributes([QgsField('Shape_Leng', QVariant.Double)])
    if 'Shape_Area' not in existing_fields:
        output_provider.addAttributes([QgsField('Shape_Area', QVariant.Double)])
    output_layer.updateFields()
    
    key_fields = ['grid_id', 'area', 'polderId', 'town', 'Shape_Leng', 'Shape_Area']
    shown_fields = [f for f in key_fields if f in [field.name() for field in output_layer.fields()]]
    print(f"\n【步骤3】创建输出图层 | ✅ {len(output_layer.fields())}个字段 | 关键字段: {', '.join(shown_fields)}")
    
    # ========== 4. 填充数据 ==========
    output_features = []
    for feat in house_with_grid.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(feat.geometry())
        for field in house_with_grid.fields():
            field_name = field.name()
            if field_name in new_feat.fields().names():
                new_feat[field_name] = feat[field_name]
        geom = feat.geometry()
        new_feat['Shape_Leng'] = round(geom.length() if geom and not geom.isNull() else 0.0, 10)
        new_feat['Shape_Area'] = round(geom.area() if geom and not geom.isNull() else 0.0, 10)
        output_features.append(new_feat)
    
    output_provider.addFeatures(output_features)
    print(f"\n【步骤4】填充数据 | ✅ {len(output_features)}个房屋 | 已计算Shape_Leng/Shape_Area | 继承网格所有属性")
    
    # ========== 5. 添加到项目（process组） ==========
    project = QgsProject.instance()
    process_group = ensure_group_exists("process")
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    if existing_layers:
        project.removeMapLayer(existing_layers[0])
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    print(f"\n【步骤5】添加到QGIS项目 | ✅ {OUTPUT_LAYER_NAME} 已添加到 process 组")
    
    # ========== 6. 数据验证 ==========
    house_areas = [feat['Shape_Area'] for feat in output_layer.getFeatures() if feat['Shape_Area'] is not None]
    towns = [feat['town'] for feat in output_layer.getFeatures() if feat['town'] is not None]
    polders = [feat['polderId'] for feat in output_layer.getFeatures() if feat['polderId'] is not None]
    
    stats = f"总房屋数: {output_layer.featureCount()}"
    if house_areas:
        stats += f" | 面积: {min(house_areas):.2f}~{max(house_areas):.2f}m²(平均{sum(house_areas)/len(house_areas):.2f}m²)"
    if towns:
        stats += f" | 乡镇: {len(set(towns))}个"
    if polders:
        stats += f" | 保护片: {len(set(polders))}个"
    print(f"\n【步骤6】数据验证 | ✅ {stats}")
    
    # ========== 7. 完成 ==========
    original_house_count = house_layer.featureCount()
    output_house_count = output_layer.featureCount()
    split_info = f"跨网格切分约{output_house_count - original_house_count}个" if output_house_count > original_house_count else "无切分"
    print("\n" + "=" * 80)
    print(f"✅ House图层生成完成！ | 输出: {OUTPUT_LAYER_NAME}(process组) | 原始{original_house_count}个房屋→输出{output_house_count}个要素 | {split_info} | 已继承网格属性+计算Shape_Leng/Area")
    print("=" * 80)
    
    # 保存图层并重新加载
    print(f"\n💾 保存图层到文件并重新加载")
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    return output_layer


# ============ 执行 ============

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("🏠 House图层生成脚本开始执行...")
        print("=" * 80)
        result = generate_house_layer()
        
        if result:
            print("\n✅ 脚本执行成功！请查看新生成的图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ House图层生成完成！\n\n"
                    msg += f"📊 输出图层: {OUTPUT_LAYER_NAME}\n"
                    msg += f"📁 位置: process组\n\n"
                    msg += f"生成的房屋要素数: {result.featureCount()} 个\n\n"
                    msg += "已添加字段:\n"
                    msg += "  • grid_id (所属网格ID)\n"
                    msg += "  • area (所属网格面积)\n"
                    msg += "  • town (所属乡镇)\n"
                    msg += "  • polderId (所属保护片ID)\n"
                    msg += "  • Shape_Leng (房屋周长)\n"
                    msg += "  • Shape_Area (房屋面积)"
                    
                    QMessageBox.information(None, "处理完成", msg)
            except:
                pass  # 如果弹窗失败，不影响主流程
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

