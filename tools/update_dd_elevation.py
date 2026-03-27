"""
更新 dd 图层高程脚本

功能:
1. 延长 dm 断面线，与 dd 堤段相交，获取 LC（空间相交，更可靠）
2. 根据 dd 的 LC，在 dm 中线性插值高程
3. 根据 zya 选择左岸/右岸高程，更新 ddgc
4. 如果 dd 有 hdgc 字段，同时更新河底高程

输入图层:
  - dd: 堤段图层
    必需字段: LC, zya
    
  - dm: 断面图层（更新后）
    必需字段: 左岸, 右岸, 最低点

输出图层:
  - dd_updated: 更新高程后的堤段图层

使用方法:
  在QGIS Python控制台中执行此脚本
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
        return
    lib_dir = script_dir.parent / 'lib'
    for path in [str(script_dir), str(lib_dir)]:
        if path not in sys.path:
            sys.path.insert(0, path)

_setup_paths()
# ============ 路径设置结束 ============

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsField,
    QgsWkbTypes, QgsDistanceArea, QgsGeometry, QgsPointXY
)
from qgis.PyQt.QtCore import QVariant
from qgis import processing
import math

# ============ 配置参数 ============

# 输入图层名称
INPUT_DD_LAYER = 'dd'           # 堤段图层（有LC、zya）
INPUT_DM_LAYER = 'dm'           # 断面图层（有高程，无LC）

# 输出图层名称
OUTPUT_LAYER_NAME = 'dd_updated'

# dm 高程字段名称
DM_LEFT_FIELD = '左岸高'          # 左岸高程
DM_RIGHT_FIELD = '右岸高'         # 右岸高程
DM_BOTTOM_FIELD = '最低点'      # 河底高程

# dd 字段名称
DD_LC_FIELD = 'LC'              # 里程字段
DD_ZYA_FIELD = 'zya'            # 岸别字段
DD_DDGC_FIELD = 'ddgc'          # 堤顶高程字段
DD_HDGC_FIELD = 'hdgc'          # 河底高程字段（可选）

# dm 延长距离（米）- 两端各延长多少
DM_EXTEND_DISTANCE = 200

# ============ 辅助函数 ============

def get_geometry_center(geometry):
    """获取几何对象的中心点"""
    if geometry.isNull():
        return None
    centroid = geometry.centroid()
    if centroid.isNull():
        return None
    return centroid.asPoint()


def ensure_group_exists(group_name):
    """确保图层组存在"""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = root.findGroup(group_name)
    if not group:
        group = root.insertGroup(0, group_name)
    return group


# ============ 主函数 ============

def update_dd_elevation():
    """更新 dd 图层的高程"""
    
    print("\n" + "=" * 70)
    print("🔄 更新 dd 图层高程")
    print("=" * 70)
    
    # ========== 1. 加载图层 ==========
    print(f"\n【步骤1】加载图层")
    
    # 加载 dd 图层
    dd_layers = QgsProject.instance().mapLayersByName(INPUT_DD_LAYER)
    if not dd_layers:
        print(f"  ❌ 找不到图层: {INPUT_DD_LAYER}")
        return None
    dd_layer = dd_layers[0]
    print(f"  ✅ dd: {dd_layer.featureCount()} 个堤段")
    
    # 加载 dm 图层
    dm_layers = QgsProject.instance().mapLayersByName(INPUT_DM_LAYER)
    if not dm_layers:
        print(f"  ❌ 找不到图层: {INPUT_DM_LAYER}")
        return None
    dm_layer = dm_layers[0]
    print(f"  ✅ dm: {dm_layer.featureCount()} 个断面")
    
    # 检查 dd 必需字段
    dd_fields = [f.name() for f in dd_layer.fields()]
    if DD_LC_FIELD not in dd_fields:
        print(f"  ❌ dd 缺少字段: {DD_LC_FIELD}")
        return None
    if DD_ZYA_FIELD not in dd_fields:
        print(f"  ❌ dd 缺少字段: {DD_ZYA_FIELD}")
        return None
    print(f"  ✅ dd 必需字段检查通过 (LC, zya)")
    
    # 检查 dd 是否有 hdgc 字段
    has_hdgc = DD_HDGC_FIELD in dd_fields
    if has_hdgc:
        print(f"  ✅ dd 有 hdgc 字段，将一并更新")
    else:
        print(f"  ℹ️  dd 无 hdgc 字段，跳过河底高程更新")
    
    # 检查 dm 高程字段
    dm_fields = [f.name() for f in dm_layer.fields()]
    missing_dm_fields = []
    if DM_LEFT_FIELD not in dm_fields:
        missing_dm_fields.append(DM_LEFT_FIELD)
    if DM_RIGHT_FIELD not in dm_fields:
        missing_dm_fields.append(DM_RIGHT_FIELD)
    if DM_BOTTOM_FIELD not in dm_fields:
        missing_dm_fields.append(DM_BOTTOM_FIELD)
    
    if missing_dm_fields:
        print(f"  ❌ dm 缺少字段: {', '.join(missing_dm_fields)}")
        print(f"     可用字段: {', '.join(dm_fields)}")
        return None
    print(f"  ✅ dm 高程字段检查通过 ({DM_LEFT_FIELD}, {DM_RIGHT_FIELD}, {DM_BOTTOM_FIELD})")
    
    # ========== 2. 延长 dm 并与 dd 相交获取 LC ==========
    print(f"\n【步骤2】延长 dm 断面，与 dd 相交获取 LC")
    print(f"  📏 延长距离: 两端各 {DM_EXTEND_DISTANCE} 米")
    
    # 使用 processing 延长 dm 线
    print(f"  🔄 延长断面线...")
    extend_result = processing.run("native:extendlines", {
        'INPUT': dm_layer,
        'START_DISTANCE': DM_EXTEND_DISTANCE,
        'END_DISTANCE': DM_EXTEND_DISTANCE,
        'OUTPUT': 'memory:'
    })
    dm_extend = extend_result['OUTPUT']
    print(f"  ✅ dm_extend: {dm_extend.featureCount()} 条")
    
    # 构建 dd 空间索引
    print(f"  🔄 构建 dd 空间索引...")
    dd_features = {feat.id(): feat for feat in dd_layer.getFeatures()}
    
    # 通过空间相交获取 LC
    print(f"  🔄 空间相交匹配...")
    dm_with_lc = []  # [{lc, left, right, bottom}, ...]
    matched_count = 0
    unmatched_count = 0
    multi_match_count = 0
    
    for dm_ext_feat in dm_extend.getFeatures():
        dm_geom = dm_ext_feat.geometry()
        if dm_geom.isNull():
            unmatched_count += 1
            continue
        
        # 找所有与 dm_extend 相交的 dd
        intersect_lcs = []
        for dd_id, dd_feat in dd_features.items():
            dd_geom = dd_feat.geometry()
            if dd_geom.isNull():
                continue
            
            if dm_geom.intersects(dd_geom):
                lc = dd_feat[DD_LC_FIELD]
                if lc is not None:
                    intersect_lcs.append(lc)
        
        if intersect_lcs:
            # 如果有多个相交，取平均值
            avg_lc = sum(intersect_lcs) / len(intersect_lcs)
            
            if len(intersect_lcs) > 1:
                multi_match_count += 1
            
            dm_with_lc.append({
                'lc': avg_lc,
                'left': dm_ext_feat[DM_LEFT_FIELD],
                'right': dm_ext_feat[DM_RIGHT_FIELD],
                'bottom': dm_ext_feat[DM_BOTTOM_FIELD],
                'match_count': len(intersect_lcs)
            })
            matched_count += 1
        else:
            unmatched_count += 1
    
    print(f"  ✅ dm 匹配成功: {matched_count} 个")
    if multi_match_count > 0:
        print(f"  ℹ️  多重相交（取平均）: {multi_match_count} 个")
    if unmatched_count > 0:
        print(f"  ⚠️  dm 无相交: {unmatched_count} 个")
    
    if not dm_with_lc:
        print(f"  ❌ 没有有效的断面数据")
        return None
    
    # ========== 3. 按 LC 排序并去重 ==========
    print(f"\n【步骤3】整理断面数据")
    
    # 按 LC 分组，同一 LC 取平均高程
    # 使用整数 LC 作为 key（避免浮点数精度问题）
    lc_groups = {}
    for dm_data in dm_with_lc:
        lc = int(round(dm_data['lc']))  # 四舍五入到整数
        if lc not in lc_groups:
            lc_groups[lc] = []
        lc_groups[lc].append(dm_data)
    
    # 计算每个 LC 的平均高程
    cross_sections = []
    for lc, group in lc_groups.items():
        left_avg = sum(d['left'] for d in group if d['left'] is not None) / len([d for d in group if d['left'] is not None]) if any(d['left'] is not None for d in group) else None
        right_avg = sum(d['right'] for d in group if d['right'] is not None) / len([d for d in group if d['right'] is not None]) if any(d['right'] is not None for d in group) else None
        bottom_avg = sum(d['bottom'] for d in group if d['bottom'] is not None) / len([d for d in group if d['bottom'] is not None]) if any(d['bottom'] is not None for d in group) else None
        
        cross_sections.append({
            'lc': lc,
            'left': left_avg,
            'right': right_avg,
            'bottom': bottom_avg
        })
    
    # 按 LC 排序
    cross_sections.sort(key=lambda x: x['lc'])
    
    print(f"  📊 整理后断面: {len(cross_sections)} 个")
    print(f"  📊 LC 范围: {cross_sections[0]['lc']} ~ {cross_sections[-1]['lc']}")
    
    # 显示前3个断面
    print(f"\n  📋 断面示例（前3个）:")
    for i, cs in enumerate(cross_sections[:3]):
        left_str = f"{cs['left']:.2f}" if cs['left'] else "NULL"
        right_str = f"{cs['right']:.2f}" if cs['right'] else "NULL"
        bottom_str = f"{cs['bottom']:.2f}" if cs['bottom'] else "NULL"
        print(f"     LC={cs['lc']}: 左岸={left_str}, 右岸={right_str}, 河底={bottom_str}")
    
    # ========== 4. 插值函数 ==========
    def interpolate_elevation(target_lc, field):
        """
        根据 LC 线性插值高程
        
        Args:
            target_lc: 目标里程
            field: 'left', 'right', 或 'bottom'
        
        Returns:
            插值后的高程，或 None
        """
        if not cross_sections:
            return None
        
        # 边界情况
        if target_lc <= cross_sections[0]['lc']:
            return cross_sections[0][field]
        if target_lc >= cross_sections[-1]['lc']:
            return cross_sections[-1][field]
        
        # 找到两侧断面
        for i in range(len(cross_sections) - 1):
            cs1 = cross_sections[i]
            cs2 = cross_sections[i + 1]
            
            if cs1['lc'] <= target_lc <= cs2['lc']:
                val1 = cs1[field]
                val2 = cs2[field]
                
                if val1 is None or val2 is None:
                    # 如果一侧为空，返回非空的那个
                    return val1 if val2 is None else val2
                
                # 线性插值
                ratio = (target_lc - cs1['lc']) / (cs2['lc'] - cs1['lc'])
                return val1 + ratio * (val2 - val1)
        
        return None
    
    # ========== 5. 创建输出图层 ==========
    print(f"\n【步骤4】创建输出图层并更新高程")
    
    geom_type = QgsWkbTypes.displayString(dd_layer.wkbType())
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={dd_layer.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    
    output_provider = output_layer.dataProvider()
    
    # 复制所有字段
    output_provider.addAttributes(dd_layer.fields().toList())
    output_layer.updateFields()
    
    # ========== 6. 更新高程 ==========
    output_features = []
    updated_ddgc = 0
    updated_hdgc = 0
    skipped = 0
    
    for dd_feat in dd_layer.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(dd_feat.geometry())
        
        # 复制所有属性
        for field in dd_layer.fields():
            new_feat[field.name()] = dd_feat[field.name()]
        
        # 获取 LC 和 zya
        lc = dd_feat[DD_LC_FIELD]
        zya = dd_feat[DD_ZYA_FIELD]
        
        if lc is None:
            skipped += 1
            output_features.append(new_feat)
            continue
        
        # 根据 zya 选择左岸或右岸高程
        if zya == 'L':
            new_ddgc = interpolate_elevation(lc, 'left')
        elif zya == 'R':
            new_ddgc = interpolate_elevation(lc, 'right')
        else:
            new_ddgc = None
        
        # 更新 ddgc
        if new_ddgc is not None:
            new_feat[DD_DDGC_FIELD] = round(new_ddgc, 2)
            updated_ddgc += 1
        
        # 更新 hdgc（如果有）
        if has_hdgc:
            new_hdgc = interpolate_elevation(lc, 'bottom')
            if new_hdgc is not None:
                new_feat[DD_HDGC_FIELD] = round(new_hdgc, 2)
                updated_hdgc += 1
        
        output_features.append(new_feat)
    
    output_provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    print(f"  ✅ ddgc 更新: {updated_ddgc} 条")
    if has_hdgc:
        print(f"  ✅ hdgc 更新: {updated_hdgc} 条")
    if skipped > 0:
        print(f"  ⚠️  跳过（无LC）: {skipped} 条")
    
    # ========== 7. 添加到项目 ==========
    print(f"\n【步骤5】添加到项目")
    
    project = QgsProject.instance()
    
    # 移除旧图层
    existing = project.mapLayersByName(OUTPUT_LAYER_NAME)
    for old in existing:
        project.removeMapLayer(old)
    
    # 添加到 final 组
    final_group = ensure_group_exists("final")
    project.addMapLayer(output_layer, False)
    final_group.addLayer(output_layer)
    
    print(f"  ✅ 已添加: {OUTPUT_LAYER_NAME} (final组)")
    
    # ========== 8. 验证结果 ==========
    print(f"\n【步骤6】验证结果")
    
    # 抽查几条数据
    print(f"\n  📋 更新后数据示例（前5条）:")
    print(f"  {'LC':<8} {'zya':<5} {'ddgc(新)':<12} {'ddgc(旧)':<12}")
    print("  " + "-" * 40)
    
    count = 0
    for new_feat, old_feat in zip(output_layer.getFeatures(), dd_layer.getFeatures()):
        if count >= 5:
            break
        
        lc = new_feat[DD_LC_FIELD]
        zya = new_feat[DD_ZYA_FIELD]
        new_ddgc = new_feat[DD_DDGC_FIELD]
        old_ddgc = old_feat[DD_DDGC_FIELD]
        
        lc_str = str(lc) if lc else "NULL"
        zya_str = str(zya) if zya else "-"
        new_str = f"{new_ddgc:.2f}" if new_ddgc else "NULL"
        old_str = f"{old_ddgc:.2f}" if old_ddgc else "NULL"
        
        print(f"  {lc_str:<8} {zya_str:<5} {new_str:<12} {old_str:<12}")
        count += 1
    
    # ========== 9. 统计 ==========
    print("\n" + "=" * 70)
    print("✅ 更新完成！")
    print("=" * 70)
    
    print(f"\n📊 统计:")
    print(f"  • 输入堤段: {dd_layer.featureCount()}")
    print(f"  • 输入断面: {dm_layer.featureCount()}")
    print(f"  • 有效断面（匹配LC）: {len(cross_sections)}")
    print(f"  • ddgc 更新: {updated_ddgc} 条")
    if has_hdgc:
        print(f"  • hdgc 更新: {updated_hdgc} 条")
    
    print(f"\n💡 说明:")
    print(f"  • 新图层: {OUTPUT_LAYER_NAME} (在 final 组)")
    print(f"  • 原图层 {INPUT_DD_LAYER} 未修改")
    print(f"  • 可右键导出为 GeoJSON/Shapefile")
    
    return output_layer


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🔄 dd 高程更新脚本开始执行...")
    print("=" * 70)
    
    try:
        result = update_dd_elevation()
        
        if result:
            print("\n✅ 脚本执行成功！")
        else:
            print("\n❌ 脚本执行失败，请检查错误信息。")
            
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ 执行出错！")
        print("=" * 70)
        print(f"\n错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        import traceback
        traceback.print_exc()

