"""
10 Road图层生成脚本 - 通用版

📌 说明：
   这是一个通用脚本，适用于所有河流（华溪、熟溪、白溪等）
   只需修改脚本顶部的配置参数（图层名称）即可使用

功能：
1. 自动处理坐标系不一致（重投影到网格坐标系）
2. 自动移除Z/M坐标（降维到2D）
3. 将原始道路图层按grid_enriched进行空间裁剪（Clip）
4. 通过空间连接继承网格的所有属性（grid_id, area, polderId, town, Bathymetry等）
5. 自动计算道路长度（Shape_Leng）
6. 自动修复几何错误
7. 处理空值，确保所有字段都有有效值
8. 验证字段完整性，输出详细统计信息
9. 空间范围检查和调试信息

输入图层（将自动移到input组）：
- road: 原始道路图层（线）
- grid_enriched: 增强后的网格图层（包含grid_id, area, polderId, town等）

输出图层（自动移到process组）：
- road_output: 带网格属性的道路图层

📊 输出图层 road_output 的字段说明：
   
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
   │ Shape_Leng   │ Double       │ 道路长度，单位米（自动计算） │
   └──────────────┴──────────────┴────────────────────────────┘
   
   注：原road图层和grid图层的其他字段也会被保留

💡 使用方法：
   1. 确保QGIS中已加载road和grid_enriched两个图层
   2. 根据实际图层名称，修改配置部分的ROAD_LAYER和GRID_LAYER
   3. 在QGIS Python控制台运行此脚本
   4. 查看process组中的road_output输出图层

⚙️  配置参数（在脚本中修改）：
   - ROAD_LAYER: 原始道路图层名称
   - GRID_LAYER: 增强网格图层名称（grid_enriched）
   - OUTPUT_LAYER_NAME: 输出图层名称
   - TARGET_CRS: 目标投影坐标系（用于长度计算）
   - REQUIRED_GRID_FIELDS: 必需的网格字段

🔍 特殊说明：
   - 使用Clip算法裁剪道路，再用空间连接添加网格属性
   - 如果道路跨越多个网格，会被切分为多个要素
   - area字段是网格面积
   - 坐标系不一致时会自动重投影
   - 自动移除Z/M坐标（3D → 2D），避免空间运算失败
   - 包含范围检查，确保道路和网格有重叠

📝 示例输出：
   grid_id | area     | town   | polderId | Shape_Leng
   --------|----------|--------|----------|------------
   1       | 521.21   | 白鹤乡 | sx0001   | 125.45
   2       | 528.28   | 白鹤乡 | sx0001   | 98.32
   3       | 528.42   | 白鹤乡 | sx0001   | 156.78
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path
from collections import defaultdict

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
    QgsWkbTypes, QgsGeometry, QgsDistanceArea, QgsPointXY
)
from qgis.PyQt.QtCore import QVariant
import processing

# 导入工具函数库
from qgis_util import (
    move_layer_to_group,
    get_layer_by_name,
    ensure_group_exists,
    fix_geometries,
    drop_z_values_if_needed,
    reproject_layer_if_needed,
    check_crs_consistency,
    save_and_reload_layer
)

# 导入公共配置
from hydraulic.qgis_config import (
    INPUT_LAYERS,
    OUTPUT_LAYERS,
    TARGET_CRS
)

# ========== 配置区 ==========

# 输入图层名称
ROAD_LAYER = INPUT_LAYERS['road']
GRID_LAYER = OUTPUT_LAYERS['grid_enriched']

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['road_output']

# Grid必需字段（用于验证）
REQUIRED_GRID_FIELDS = ['grid_id', 'area', 'polderId', 'town']

# ========== 主函数 ==========

def generate_road_layer():
    """
    主函数：生成road_output图层
    
    Returns:
        QgsVectorLayer: 生成的road_output图层，如果失败则返回None
    """
    
    print("=" * 80)
    print("🛣️  Road图层生成 - 空间裁剪添加网格属性")
    print("=" * 80)
    
    # ========== 1. 加载输入图层 ==========
    print(f"\n【步骤1】加载输入图层")
    
    # 加载道路图层
    road_layer = get_layer_by_name(ROAD_LAYER)
    if not road_layer:
        print(f"  ❌ 错误: 无法找到道路图层 '{ROAD_LAYER}'，请确保QGIS中已加载该图层")
        return None
    road_fields = [f.name() for f in road_layer.fields()]
    move_layer_to_group(road_layer, "input")
    print(f"  ✅ 道路: {road_layer.featureCount()}条 | 坐标系: {road_layer.crs().authid()} | 字段: {', '.join(road_fields[:3])}... | 已移至input组")
    
    # 加载网格图层
    grid_layer = get_layer_by_name(GRID_LAYER)
    if not grid_layer:
        print(f"  ❌ 错误: 无法找到网格图层 '{GRID_LAYER}'，请先运行enrich_grid_layer.py生成该图层")
        return None
    grid_fields = [f.name() for f in grid_layer.fields()]
    missing_fields = [f for f in REQUIRED_GRID_FIELDS if f not in grid_fields]
    if missing_fields:
        print(f"  ❌ 错误: 网格图层缺少必需字段: {', '.join(missing_fields)}")
        return None
    print(f"  ✅ 网格: {grid_layer.featureCount()}个 | 坐标系: {grid_layer.crs().authid()} | 将继承网格所有字段到道路图层")
    
    check_crs_consistency(road_layer, grid_layer, "道路", "网格")
    road_layer = reproject_layer_if_needed(road_layer, grid_layer.crs(), "道路")
    road_layer = drop_z_values_if_needed(road_layer, "道路")
    road_layer = fix_geometries(road_layer, "道路")
    
    road_extent = road_layer.extent()
    grid_extent = grid_layer.extent()
    overlap_status = "✅范围有重叠" if road_extent.intersects(grid_extent) else "❌警告:范围不重叠"
    print(f"  📍 空间范围检查 | {overlap_status}")
    
    # ========== 2. 空间裁剪（Clip） ==========
    print(f"\n【步骤2】空间裁剪 - Road ⊆ Grid")
    print(f"  🔄 使用网格裁剪道路（Clip）...")
    print(f"     - 道路图层: {road_layer.featureCount()} 条道路")
    print(f"     - 网格图层: {grid_layer.featureCount()} 个网格")
    
    try:
        clip_result = processing.run("native:clip", {
            'INPUT': road_layer,
            'OVERLAY': grid_layer,
            'OUTPUT': 'memory:'
        })
        
        clipped_layer = clip_result['OUTPUT']
        print(f"  ✅ 裁剪完成: {clipped_layer.featureCount()} 条道路段")
        
    except Exception as e:
        print(f"\n  ❌ 裁剪失败: {e}")
        return None
    
    # ========== 3. 空间连接 - 添加网格属性 ==========
    print(f"\n【步骤3】空间连接 - 添加网格属性")
    print(f"  🔄 Join Road × Grid (按位置)...")
    
    try:
        join_result = processing.run("native:joinattributesbylocation", {
            'INPUT': clipped_layer,
            'JOIN': grid_layer,
            'PREDICATE': [0],  # 0 = intersects
            'JOIN_FIELDS': [],  # 空列表 = 复制所有字段
            'METHOD': 1,  # 1 = 只取第一个匹配，避免一对多重复
            'DISCARD_NONMATCHING': False,
            'PREFIX': '',
            'OUTPUT': 'memory:'
        })
        
        joined_layer = join_result['OUTPUT']
        print(f"  ✅ 连接完成: {joined_layer.featureCount()} 条道路段")
        
    except Exception as e:
        print(f"\n  ❌ 连接失败: {e}")
        return None
    
    # ========== 4. 创建输出图层 ==========
    print(f"\n【步骤4】创建输出图层")
    print(f"  🔄 构建 {OUTPUT_LAYER_NAME} 图层...")
    
    # 获取joined_layer的字段
    joined_fields = joined_layer.fields()
    
    # 创建输出图层（继承所有字段）
    output_layer = QgsVectorLayer(
        f"LineString?crs={joined_layer.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    
    output_provider = output_layer.dataProvider()
    
    # 复制所有字段
    output_provider.addAttributes(joined_fields.toList())
    
    # 添加 Shape_Leng 字段（如果不存在）
    if 'Shape_Leng' not in [f.name() for f in joined_fields]:
        output_provider.addAttributes([
            QgsField('Shape_Leng', QVariant.Double, len=20, prec=6)
        ])
    
    output_layer.updateFields()
    
    print(f"  ✅ 输出图层结构创建完成")
    print(f"     - 总字段数: {len(output_layer.fields())}")
    print(f"     - 字段列表: {', '.join([f.name() for f in output_layer.fields()])}")
    
    # ========== 5. 填充数据 + 计算长度 ==========
    print(f"\n【步骤5】填充数据并计算长度")
    print(f"  🔄 处理 {joined_layer.featureCount()} 条道路段...")
    
    # 统计信息
    stats = {
        'total': 0,
        'with_grid': 0,
        'without_grid': 0,
        'total_length': 0.0
    }
    
    grid_road_count = defaultdict(int)
    
    output_features = []
    
    for feat in joined_layer.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        geom = feat.geometry()
        
        if geom is None or geom.isEmpty():
            continue
        
        new_feat.setGeometry(geom)
        
        # 复制所有属性
        for field in joined_layer.fields():
            field_name = field.name()
            value = feat[field_name]
            
            # 处理NULL值
            if value is None or (isinstance(value, str) and value.strip() == ''):
                if field_name == 'grid_id':
                    value = 0
                elif field_name == 'polderId':
                    value = 'UNKNOWN'
                elif field_name == 'town':
                    value = '未知'
                elif field_name == 'area':
                    value = 0.0
            
            new_feat[field_name] = value
        
        # 计算长度（米）
        length = geom.length()  # 在投影坐标系中，单位是米
        new_feat['Shape_Leng'] = round(length, 6)
        
        output_features.append(new_feat)
        
        # 统计
        stats['total'] += 1
        stats['total_length'] += length
        
        grid_id = new_feat['grid_id']
        if grid_id and grid_id != 0:
            stats['with_grid'] += 1
            grid_road_count[grid_id] += 1
        else:
            stats['without_grid'] += 1
    
    # 批量添加要素
    output_provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    print(f"  ✅ 数据填充完成")
    
    # ========== 6. 添加到项目（process组）+ 统计 ==========
    print(f"\n【步骤6】添加到QGIS项目")
    
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    
    # 查找或创建 process 组
    process_group = ensure_group_exists("process")
    
    # 移除旧图层（如果存在）
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    if existing_layers:
        project.removeMapLayer(existing_layers[0])
        print(f"  🗑️  已移除旧的 {OUTPUT_LAYER_NAME} 图层")
    
    # 添加新图层到process组
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    print(f"  ✅ 已添加 {OUTPUT_LAYER_NAME} 图层到项目 (process组)")
    
    # ========== 7. 输出统计信息 ==========
    print(f"\n" + "=" * 80)
    print(f"📊 统计信息")
    print("=" * 80)
    
    print(f"\n【道路统计】")
    print(f"  • 总道路段数: {stats['total']}")
    print(f"  • 已匹配网格: {stats['with_grid']}")
    print(f"  • 未匹配网格: {stats['without_grid']}")
    print(f"  • 总道路长度: {stats['total_length']:.2f} 米 ({stats['total_length']/1000:.2f} 公里)")
    
    if stats['total'] > 0:
        print(f"  • 平均道路段长度: {stats['total_length']/stats['total']:.2f} 米")
    
    print(f"\n【网格覆盖】")
    print(f"  • 包含道路的网格数: {len(grid_road_count)}")
    
    if len(grid_road_count) > 0:
        avg_roads_per_grid = sum(grid_road_count.values()) / len(grid_road_count)
        max_roads_grid = max(grid_road_count.items(), key=lambda x: x[1])
        
        print(f"  • 平均每网格道路段数: {avg_roads_per_grid:.2f}")
        print(f"  • 最多道路段的网格: grid_id={max_roads_grid[0]}, {max_roads_grid[1]} 条道路段")
    
    # 检查可能需要注意的情况
    print(f"\n【数据质量检查】")
    if stats['without_grid'] > 0:
        print(f"  ⚠️  有 {stats['without_grid']} 条道路段未匹配到网格")
        print(f"     → 可能的原因:")
        print(f"        1. 道路在网格范围外")
        print(f"        2. 空间连接失败")
        print(f"        3. 几何问题")
    else:
        print(f"  ✅ 所有道路段都已匹配到网格")
    
    # 输出字段信息
    print(f"\n【输出字段】")
    for field in output_layer.fields():
        print(f"  • {field.name()}: {field.typeName()}")
    
    print(f"\n" + "=" * 80)
    print(f"✅ Road图层生成完成！")
    print(f"   输出图层: {OUTPUT_LAYER_NAME}")
    print(f"   要素数量: {output_layer.featureCount()}")
    print(f"   坐标系: {output_layer.crs().authid()}")
    print("=" * 80)
    
    # 保存图层并重新加载
    print(f"\n💾 保存图层到文件并重新加载")
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    return output_layer


# ========== 执行 ==========

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("🛣️  Road图层生成脚本开始执行...")
        print("=" * 80)
        result = generate_road_layer()
        
        if result:
            print("\n✅ 脚本执行成功！请查看新生成的图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ Road图层生成完成！\n\n"
                    msg += f"📊 输出图层: {OUTPUT_LAYER_NAME}\n"
                    msg += f"📁 位置: process组\n\n"
                    msg += f"生成的道路段数: {result.featureCount()} 条\n\n"
                    msg += "已添加字段:\n"
                    msg += "  • grid_id (所属网格ID)\n"
                    msg += "  • area (所属网格面积)\n"
                    msg += "  • town (所属乡镇)\n"
                    msg += "  • polderId (所属保护片ID)\n"
                    msg += "  • Shape_Leng (道路长度)"
                    
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

