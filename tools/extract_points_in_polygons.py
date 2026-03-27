#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点在面内提取脚本 - 通用版

📌 说明：
   提取点图层A中落在面图层B内部的所有点，生成新的点图层

功能：
1. 空间关系判断：检查点是否在面内（within/intersects）
2. 提取符合条件的点要素
3. 可选：是否继承面图层的属性
4. 自动修复几何错误
5. 坐标系不一致时自动重投影

输入图层：
- 点图层A: 原始点图层
- 面图层B: 参考面图层（边界）

输出图层：
- 输出点图层: 落在面内的点（可选择是否继承面属性）

💡 使用方法：
   1. 确保QGIS中已加载点图层和面图层
   2. 修改配置部分的图层名称
   3. 选择是否需要继承面图层的属性
   4. 在QGIS Python控制台运行此脚本
   5. 查看process组中的输出图层

⚙️  配置参数：
   - POINT_LAYER: 点图层名称
   - POLYGON_LAYER: 面图层名称
   - OUTPUT_LAYER_NAME: 输出图层名称
   - INHERIT_ATTRIBUTES: 是否继承面图层属性（True/False）
   - SPATIAL_PREDICATE: 空间关系类型（默认0=intersects，6=within）

🔍 空间关系类型说明：
   0 = intersects (相交) - 点与面有任何重叠
   6 = within (包含) - 点完全在面内部
   
📝 示例：
   场景1：提取保护区内的所有监测点
   - 点图层A: monitoring_points（监测点）
   - 面图层B: protected_area（保护区范围）
   - 输出: 保护区内的监测点
   
   场景2：提取某县范围内的所有POI
   - 点图层A: poi_points（兴趣点）
   - 面图层B: county_boundary（县界）
   - 输出: 县内POI点
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
    QgsProject, QgsVectorLayer, QgsWkbTypes
)
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
    safe_execute
)

# ============ 配置参数 ============

# 输入图层名称（请根据实际情况修改）
POINT_LAYER = "res"          # 点图层A的名称
POLYGON_LAYER = "wucheng"      # 面图层B的名称

# 输出图层名称
OUTPUT_LAYER_NAME = "points_in_polygons2"

# 是否继承面图层的属性
# True: 输出点会包含所在面的属性（通过空间连接）
# False: 输出点只保留原点图层的属性
INHERIT_ATTRIBUTES = False

# 空间关系类型
# 0 = intersects (相交，推荐)
# 6 = within (完全包含)
SPATIAL_PREDICATE = [0]  # 可以是列表，如 [0, 6] 表示多种关系

# ============ 主函数 ============

@safe_execute
def extract_points_in_polygons():
    """提取面图层内的点"""
    
    print("\n" + "=" * 80)
    print("📍 点在面内提取 - 空间关系筛选")
    print("=" * 80)
    
    # ========== 1. 加载图层 ==========
    print_step(1, "加载输入图层")
    
    # 加载点图层
    point_layer = get_layer_by_name(POINT_LAYER)
    if not point_layer:
        print_error(f"找不到点图层 '{POINT_LAYER}'，请确保QGIS中已加载该图层")
        return None
    
    # 验证是否为点图层
    geom_type = point_layer.geometryType()
    if geom_type != 0:  # 0 = Point
        type_name = ['点', '线', '面'][geom_type]
        print_error(f"图层 '{POINT_LAYER}' 不是点图层（当前类型: {type_name}）")
        return None
    
    point_fields = [f.name() for f in point_layer.fields()]
    move_layer_to_group(point_layer, "input")
    print_success(f"点图层: {point_layer.featureCount()}个点 | 坐标系: {point_layer.crs().authid()} | 字段数: {len(point_fields)} | 已移至input组")
    
    # 加载面图层
    polygon_layer = get_layer_by_name(POLYGON_LAYER)
    if not polygon_layer:
        print_error(f"找不到面图层 '{POLYGON_LAYER}'，请确保QGIS中已加载该图层")
        return None
    
    # 验证是否为面图层
    geom_type = polygon_layer.geometryType()
    if geom_type != 2:  # 2 = Polygon
        type_name = ['点', '线', '面'][geom_type]
        print_error(f"图层 '{POLYGON_LAYER}' 不是面图层（当前类型: {type_name}）")
        return None
    
    polygon_fields = [f.name() for f in polygon_layer.fields()]
    move_layer_to_group(polygon_layer, "input")
    print_success(f"面图层: {polygon_layer.featureCount()}个面 | 坐标系: {polygon_layer.crs().authid()} | 字段数: {len(polygon_fields)} | 已移至input组")
    
    # ========== 2. 坐标系检查与重投影 ==========
    print_step(2, "坐标系检查")
    check_crs_consistency(point_layer, polygon_layer, "点图层", "面图层")
    point_layer = reproject_layer_if_needed(point_layer, polygon_layer.crs(), "点图层")
    
    # ========== 3. 几何修复 ==========
    print_step(3, "修复几何")
    point_layer = fix_geometries(point_layer, "点图层")
    polygon_layer = fix_geometries(polygon_layer, "面图层")
    
    # ========== 4. 空间关系判断与提取 ==========
    predicate_names = {
        0: "相交(intersects)",
        1: "包含(contains)",
        2: "不相交(disjoint)",
        3: "等于(equals)",
        4: "接触(touches)",
        5: "重叠(overlaps)",
        6: "包含于(within)",
        7: "交叉(crosses)"
    }
    
    predicate_desc = ", ".join([predicate_names.get(p, str(p)) for p in SPATIAL_PREDICATE])
    print_step(4, f"空间关系判断与提取 [{predicate_desc}]")
    
    if INHERIT_ATTRIBUTES:
        # 方法1: 使用空间连接（会继承面属性）
        print(f"  🔄 使用空间连接方式（会继承面图层属性）...")
        result = processing.run("native:joinattributesbylocation", {
            'INPUT': point_layer,
            'JOIN': polygon_layer,
            'PREDICATE': SPATIAL_PREDICATE,
            'JOIN_FIELDS': [],  # 空列表表示继承所有字段
            'METHOD': 0,  # 0 = 创建单独要素（一对多）
            'DISCARD_NONMATCHING': True,  # 丢弃不匹配的点
            'PREFIX': 'poly_',  # 面图层字段添加前缀避免冲突
            'OUTPUT': 'memory:'
        })
        output_layer = result['OUTPUT']
        
    else:
        # 方法2: 使用按位置提取（不继承面属性）
        print(f"  🔄 使用按位置提取方式（仅保留点图层属性）...")
        result = processing.run("native:extractbylocation", {
            'INPUT': point_layer,
            'PREDICATE': SPATIAL_PREDICATE,
            'INTERSECT': polygon_layer,
            'OUTPUT': 'memory:'
        })
        output_layer = result['OUTPUT']
    
    extracted_count = output_layer.featureCount()
    original_count = point_layer.featureCount()
    percentage = (extracted_count / original_count * 100) if original_count > 0 else 0
    
    print_success(f"提取完成: {extracted_count}/{original_count} 个点 ({percentage:.1f}%)")
    
    # ========== 5. 设置输出图层名称 ==========
    output_layer.setName(OUTPUT_LAYER_NAME)
    
    # ========== 6. 添加到项目（process组） ==========
    print_step(5, "添加到QGIS项目")
    
    project = QgsProject.instance()
    process_group = ensure_group_exists("process")
    
    # 移除同名旧图层
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    if existing_layers:
        project.removeMapLayer(existing_layers[0])
        print(f"  🗑️  已移除旧图层: {OUTPUT_LAYER_NAME}")
    
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    print_success(f"图层已添加: {OUTPUT_LAYER_NAME} (process组)")
    
    # ========== 7. 输出统计 ==========
    print_step(6, "统计信息")
    
    output_fields = [f.name() for f in output_layer.fields()]
    print(f"  📊 输出统计:")
    print(f"     • 原始点数: {original_count}")
    print(f"     • 面内点数: {extracted_count}")
    print(f"     • 提取比例: {percentage:.1f}%")
    print(f"     • 字段数量: {len(output_fields)}")
    
    if INHERIT_ATTRIBUTES:
        # 显示继承的面属性字段
        inherited_fields = [f for f in output_fields if f.startswith('poly_')]
        if inherited_fields:
            print(f"     • 继承字段: {len(inherited_fields)}个 (前缀: poly_)")
            print(f"       示例: {', '.join(inherited_fields[:5])}{'...' if len(inherited_fields) > 5 else ''}")
    
    # ========== 8. 完成 ==========
    print("\n" + "=" * 80)
    print(f"✅ 点在面内提取完成！")
    print(f"   输出: {OUTPUT_LAYER_NAME} (process组)")
    print(f"   结果: {extracted_count}/{original_count} 个点 ({percentage:.1f}%)")
    if INHERIT_ATTRIBUTES:
        print(f"   说明: 已继承面图层属性（前缀poly_）")
    else:
        print(f"   说明: 仅保留原点图层属性")
    print("=" * 80)
    
    return output_layer


# ============ 执行 ============

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("📍 点在面内提取脚本开始执行...")
        print("=" * 80)
        print(f"\n⚙️  当前配置:")
        print(f"   • 点图层: {POINT_LAYER}")
        print(f"   • 面图层: {POLYGON_LAYER}")
        print(f"   • 输出名称: {OUTPUT_LAYER_NAME}")
        print(f"   • 继承面属性: {'是' if INHERIT_ATTRIBUTES else '否'}")
        print(f"   • 空间关系: {SPATIAL_PREDICATE}")
        
        result = extract_points_in_polygons()
        
        if result:
            print("\n✅ 脚本执行成功！请查看新生成的图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ 点在面内提取完成！\n\n"
                    msg += f"📊 输出图层: {OUTPUT_LAYER_NAME}\n"
                    msg += f"📁 位置: process组\n\n"
                    msg += f"提取的点数: {result.featureCount()} 个\n\n"
                    if INHERIT_ATTRIBUTES:
                        msg += "已继承面图层属性（前缀: poly_）"
                    else:
                        msg += "仅保留原点图层属性"
                    
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

