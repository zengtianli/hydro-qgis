#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02 断面LC赋值 + 中心点高程插值脚本

功能：
1. 给 dm 断面赋值LC → 生成 dm_LC
2. 从 dm_LC 读取高程，通过插值赋值给 river_center_points → 生成 river_center_points_zya

输入图层:
  - dm: 断面
    必需字段: 左岸, 右岸, 最低点
      · 左岸: 左岸高程 (m)
      · 右岸: 右岸高程 (m)
      · 最低点: 河底高程 (m)

  - river_center_points: 河段中心点
    必需字段: LC
      · LC: 里程 (m)

输出图层:
  - dm_LC: 断面（带LC）
    继承字段: dm 全部字段
    新增字段: LC, longitude, latitude
      · LC: 里程 (m)，从最近中心点获取
      · longitude: 经度 (度)
      · latitude: 纬度 (度)

  - river_center_points_zya: 河段中心点（带高程）
    继承字段: river_center_points 全部字段
    新增字段: zagc, yagc, hdgc
      · zagc: 左岸高程 (m)，从断面插值
      · yagc: 右岸高程 (m)，从断面插值
      · hdgc: 河底高程 (m)，从断面插值

工作流程：
- 步骤1: 加载 dm 断面图层
- 步骤2: 加载 river_center_points 中心点图层
- 步骤3: 给dm赋值LC → 生成 dm_LC（dm数量不变）
- 步骤4: 从dm_LC读取高程，插值赋值给river_center_points
- 步骤5: 生成 river_center_points_zya（原字段 + zagc/yagc/hdgc）
- 步骤6: 添加两个图层到QGIS项目

优势：
- 保证dm数量一致：dm(52) → dm_LC(52)
- 中心点增加高程信息，可用于后续堤防赋值（03、04.6 脚本）
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
    QgsWkbTypes, QgsDistanceArea
)
from qgis.PyQt.QtCore import QVariant

# 导入工具函数库
from qgis_util import (
    ensure_group_exists,
    move_layer_to_group,
    save_and_reload_layer
)

# 导入公共配置
from hydraulic.qgis_config import (
    INPUT_LAYERS,
    OUTPUT_LAYERS,
    DM_ELEVATION_FIELDS,
    DM_LC_CONFIG
)

# ============ 配置参数 ============

# 输入图层名称
INPUT_DM_LAYER = INPUT_LAYERS['cross_section']           # 断面图层
INPUT_CENTER_POINTS_LAYER = OUTPUT_LAYERS['river_center_points']  # 河段中心点图层

# 输出图层名称
OUTPUT_DM_LC_LAYER = OUTPUT_LAYERS['dm_lc']              # 断面+LC图层
OUTPUT_CENTER_ZYA_LAYER = OUTPUT_LAYERS['river_center_zya']  # 中心点+高程图层

# 最大匹配距离（米）- 从公共配置读取
MAX_DISTANCE = DM_LC_CONFIG['max_distance']

# ============ 辅助函数 ============

def get_line_center_coordinate(geometry):
    """
    从线几何对象中提取中点坐标
    
    Args:
        geometry: QgsGeometry 对象（LineString 或 MultiLineString）
        
    Returns:
        (longitude, latitude) 或 (None, None)
    """
    if not geometry or geometry.isNull():
        return None, None
    
    try:
        # 使用 interpolate 方法获取线的中点
        center_point = geometry.interpolate(geometry.length() / 2).asPoint()
        return center_point.x(), center_point.y()
    except:
        return None, None


# ============ 主函数 ============

def interpolate_elevation_for_centers(center_layer, dm_lc_layer):
    """
    从dm_LC读取高程，通过线性插值赋值给中心点
    
    参数:
        center_layer: river_center_points图层（带LC）
        dm_lc_layer: dm_LC图层（带LC和高程）
    
    返回:
        river_center_points_zya图层（带高程）
    """
    print(f"\n【步骤4】从dm_LC读取高程，插值赋值给中心点")
    
    # 获取高程字段名
    left_field = DM_ELEVATION_FIELDS['left_elev']
    right_field = DM_ELEVATION_FIELDS['right_elev']
    bottom_field = DM_ELEVATION_FIELDS['bottom_elev']
    
    # 检查dm_LC是否有LC字段
    dm_field_names = [f.name() for f in dm_lc_layer.fields()]
    if 'LC' not in dm_field_names:
        print(f"  ❌ 错误: dm_LC缺少LC字段")
        return None
    
    # 检查高程字段
    print(f"  🔍 检查dm_LC高程字段...")
    missing_fields = []
    if left_field not in dm_field_names:
        missing_fields.append(left_field)
    if right_field not in dm_field_names:
        missing_fields.append(right_field)
    if bottom_field not in dm_field_names:
        missing_fields.append(bottom_field)
    
    if missing_fields:
        print(f"  ❌ 错误: dm_LC缺少高程字段: {', '.join(missing_fields)}")
        return None
    
    print(f"  ✅ 高程字段检查通过")
    
    # 从dm_LC读取断面数据，按LC排序
    print(f"  📊 从dm_LC读取断面数据...")
    cross_sections = []
    
    for feat in dm_lc_layer.getFeatures():
        lc = feat['LC']
        if lc is not None:
            cross_sections.append({
                'lc': lc,
                'left_elev': feat[left_field],
                'right_elev': feat[right_field],
                'bottom_elev': feat[bottom_field]
            })
    
    if not cross_sections:
        print(f"  ❌ 错误: dm_LC中没有有效断面数据")
        return None
    
    # 按LC排序
    cross_sections.sort(key=lambda x: x['lc'])
    
    print(f"     - 断面数量: {len(cross_sections)} 个")
    print(f"     - LC范围: {cross_sections[0]['lc']} ~ {cross_sections[-1]['lc']} 米")
    print(f"     - 示例断面LC: {[cs['lc'] for cs in cross_sections[:5]]}")
    
    # 创建输出图层
    print(f"\n  🔧 创建river_center_points_zya图层...")
    geom_type = QgsWkbTypes.displayString(center_layer.wkbType())
    zya_layer = QgsVectorLayer(
        f"{geom_type}?crs={center_layer.crs().authid()}",
        OUTPUT_CENTER_ZYA_LAYER,
        "memory"
    )
    
    # 复制原图层所有字段 + 添加高程字段
    provider = zya_layer.dataProvider()
    fields_to_add = list(center_layer.fields())
    fields_to_add.append(QgsField('zagc', QVariant.Double))  # 左岸高程
    fields_to_add.append(QgsField('yagc', QVariant.Double))  # 右岸高程
    fields_to_add.append(QgsField('hdgc', QVariant.Double))  # 河底高程
    
    provider.addAttributes(fields_to_add)
    zya_layer.updateFields()
    
    print(f"     - 继承字段: {len(center_layer.fields())} 个")
    print(f"     - 新增字段: zagc(左岸) + yagc(右岸) + hdgc(河底)")
    
    # 线性插值函数
    def linear_interpolate(lc, cs_list):
        """根据LC值进行线性插值"""
        # 精确匹配
        for cs in cs_list:
            if abs(cs['lc'] - lc) < 0.01:
                return cs['left_elev'], cs['right_elev'], cs['bottom_elev']
        
        # 如果LC小于最小断面里程，使用最小断面的值
        if lc <= cs_list[0]['lc']:
            cs = cs_list[0]
            return cs['left_elev'], cs['right_elev'], cs['bottom_elev']
        
        # 如果LC大于最大断面里程，使用最大断面的值
        if lc >= cs_list[-1]['lc']:
            cs = cs_list[-1]
            return cs['left_elev'], cs['right_elev'], cs['bottom_elev']
        
        # 线性插值：找到LC两侧的断面
        for i in range(len(cs_list) - 1):
            cs1 = cs_list[i]
            cs2 = cs_list[i + 1]
            
            if cs1['lc'] <= lc <= cs2['lc']:
                # 计算插值比例
                ratio = (lc - cs1['lc']) / (cs2['lc'] - cs1['lc'])
                
                # 线性插值计算高程
                left = cs1['left_elev'] + ratio * (cs2['left_elev'] - cs1['left_elev']) if cs1['left_elev'] is not None and cs2['left_elev'] is not None else None
                right = cs1['right_elev'] + ratio * (cs2['right_elev'] - cs1['right_elev']) if cs1['right_elev'] is not None and cs2['right_elev'] is not None else None
                bottom = cs1['bottom_elev'] + ratio * (cs2['bottom_elev'] - cs1['bottom_elev']) if cs1['bottom_elev'] is not None and cs2['bottom_elev'] is not None else None
                
                return left, right, bottom
        
        return None, None, None
    
    # 对每个中心点进行插值
    print(f"\n  🔄 对 {center_layer.featureCount()} 个中心点进行插值...")
    output_features = []
    exact_match = 0
    interpolated = 0
    
    for feat in center_layer.getFeatures():
        lc = feat['LC']
        if lc is None:
            continue
        
        # 插值计算高程
        left_elev, right_elev, bottom_elev = linear_interpolate(lc, cross_sections)
        
        # 统计匹配类型
        is_exact = any(abs(cs['lc'] - lc) < 0.01 for cs in cross_sections)
        if is_exact:
            exact_match += 1
        else:
            interpolated += 1
        
        # 创建新要素
        new_feat = QgsFeature(zya_layer.fields())
        new_feat.setGeometry(feat.geometry())
        
        # 复制原属性
        for field in center_layer.fields():
            new_feat[field.name()] = feat[field.name()]
        
        # 添加高程
        new_feat['zagc'] = left_elev
        new_feat['yagc'] = right_elev
        new_feat['hdgc'] = bottom_elev
        
        output_features.append(new_feat)
    
    provider.addFeatures(output_features)
    zya_layer.updateExtents()
    
    print(f"  ✅ 插值完成:")
    print(f"     - 精确匹配: {exact_match} 个点")
    print(f"     - 线性插值: {interpolated} 个点")
    print(f"     - 总计: {len(output_features)} 个点")
    
    # 显示示例
    if output_features:
        print(f"\n  📋 插值示例（前3个）:")
        for i in range(min(3, len(output_features))):
            feat = output_features[i]
            lc = feat['LC']
            left = feat['zagc']
            right = feat['yagc']
            bottom = feat['hdgc']
            
            left_str = f"{left:.2f}m" if left is not None else 'N/A'
            right_str = f"{right:.2f}m" if right is not None else 'N/A'
            bottom_str = f"{bottom:.2f}m" if bottom is not None else 'N/A'
            
            print(f"     点{i+1}: LC={lc}m, 左岸={left_str}, 右岸={right_str}, 河底={bottom_str}")
    
    return zya_layer


def main():
    """主流程"""
    
    print("\n" + "=" * 80)
    print("🎯 断面LC赋值 + 中心点高程插值脚本")
    print("=" * 80)
    print(f"⏰ 脚本启动时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========== 步骤1: 加载断面图层 ==========
    print(f"\n【步骤1】加载断面图层")
    print(f"  🔍 查找图层: {INPUT_DM_LAYER}")
    
    dm_layers = QgsProject.instance().mapLayersByName(INPUT_DM_LAYER)
    if not dm_layers:
        print(f"  ❌ 错误: 找不到图层 '{INPUT_DM_LAYER}'")
        return None
    
    dm_layer = dm_layers[0]
    original_dm_count = dm_layer.featureCount()
    print(f"  ✅ 找到图层: {dm_layer.name()}")
    print(f"     - 断面数量: {original_dm_count}")
    print(f"     - 坐标系: {dm_layer.crs().authid()}")
    
    # 显示字段
    dm_field_names = [f.name() for f in dm_layer.fields()]
    print(f"     - 字段列表: {', '.join(dm_field_names)}")
    
    # 检查高程字段
    left_field = DM_ELEVATION_FIELDS['left_elev']
    right_field = DM_ELEVATION_FIELDS['right_elev']
    bottom_field = DM_ELEVATION_FIELDS['bottom_elev']
    
    missing_elev_fields = []
    if left_field not in dm_field_names:
        missing_elev_fields.append(left_field)
    if right_field not in dm_field_names:
        missing_elev_fields.append(right_field)
    if bottom_field not in dm_field_names:
        missing_elev_fields.append(bottom_field)
    
    if missing_elev_fields:
        print(f"  ❌ 错误: dm缺少高程字段: {', '.join(missing_elev_fields)}")
        return None
    
    print(f"  ✅ 高程字段检查通过")
    
    # 移动到input组
    move_layer_to_group(dm_layer, "input")
    print(f"     📁 已移动到 'input' 组")
    
    # ========== 步骤2: 加载中心点图层 ==========
    print(f"\n【步骤2】加载河段中心点图层")
    print(f"  🔍 查找图层: {INPUT_CENTER_POINTS_LAYER}")
    
    center_layers = QgsProject.instance().mapLayersByName(INPUT_CENTER_POINTS_LAYER)
    if not center_layers:
        print(f"  ❌ 错误: 找不到图层 '{INPUT_CENTER_POINTS_LAYER}'")
        return None
    
    center_layer = center_layers[0]
    original_center_count = center_layer.featureCount()
    print(f"  ✅ 找到图层: {center_layer.name()}")
    print(f"     - 中心点数量: {original_center_count}")
    
    # 检查LC字段
    center_field_names = [f.name() for f in center_layer.fields()]
    if 'LC' not in center_field_names:
        print(f"  ❌ 错误: 中心点图层缺少 'LC' 字段")
        print(f"     - 可用字段: {', '.join(center_field_names)}")
        return None
    print(f"  ✅ LC字段检查通过")
    
    # 检查坐标系是否一致
    if dm_layer.crs().authid() != center_layer.crs().authid():
        print(f"  ⚠️  警告: 坐标系不一致")
        print(f"     - 断面: {dm_layer.crs().authid()}")
        print(f"     - 中心点: {center_layer.crs().authid()}")
        print(f"  ℹ️  将自动进行坐标转换")
    
    # ========== 步骤3: 给dm赋值LC → dm_LC ==========
    print(f"\n【步骤3】给dm赋值LC → 生成dm_LC")
    
    # 创建dm_LC图层（复制dm结构）
    print(f"  🔧 创建dm_LC图层...")
    geom_type = QgsWkbTypes.displayString(dm_layer.wkbType())
    dm_lc_layer = QgsVectorLayer(
        f"{geom_type}?crs={dm_layer.crs().authid()}",
        OUTPUT_DM_LC_LAYER,
        "memory"
    )
    
    # 复制所有字段 + 添加LC、经纬度字段
    provider = dm_lc_layer.dataProvider()
    fields_to_add = list(dm_layer.fields())
    
    # 检查是否已有LC字段
    if 'LC' not in dm_field_names:
        fields_to_add.append(QgsField('LC', QVariant.Int))
        print(f"  ➕ 添加LC字段")
    else:
        print(f"  ℹ️  LC字段已存在，将覆盖原值")
    
    # 添加经纬度字段
    fields_to_add.append(QgsField('longitude', QVariant.Double))  # 经度
    fields_to_add.append(QgsField('latitude', QVariant.Double))   # 纬度
    print(f"  ➕ 添加经纬度字段 (longitude, latitude)")
    
    provider.addAttributes(fields_to_add)
    dm_lc_layer.updateFields()
    
    # 获取所有中心点及其LC值
    print(f"  📊 读取中心点数据...")
    center_points_data = []
    for feat in center_layer.getFeatures():
        geom = feat.geometry()
        if geom and not geom.isNull():
            point = geom.asPoint()
            lc = feat['LC']
            if lc is not None:
                center_points_data.append({'point': point, 'lc': lc})
    
    print(f"     - 有效中心点: {len(center_points_data)} 个")
    
    if not center_points_data:
        print(f"  ❌ 错误: 没有有效的中心点数据")
        return None
    
    # 距离计算器（支持不同坐标系）
    distance_calc = QgsDistanceArea()
    distance_calc.setSourceCrs(dm_layer.crs(), QgsProject.instance().transformContext())
    
    # 如果坐标系不一致，创建坐标转换器
    from qgis.core import QgsCoordinateTransform
    coord_transform = None
    if dm_layer.crs().authid() != center_layer.crs().authid():
        coord_transform = QgsCoordinateTransform(
            center_layer.crs(),
            dm_layer.crs(),
            QgsProject.instance()
        )
        print(f"  🔄 创建坐标转换器: {center_layer.crs().authid()} → {dm_layer.crs().authid()}")
    
    # 遍历每个断面，找最近的中心点
    print(f"  🔄 匹配 {original_dm_count} 个断面（LC + 经纬度）...")
    output_dm_features = []
    matched_count = 0
    unmatched_count = 0
    coord_success = 0
    coord_fail = 0
    
    for idx, dm_feat in enumerate(dm_layer.getFeatures(), 1):
        dm_geom = dm_feat.geometry()
        if not dm_geom or dm_geom.isNull():
            continue
        
        # 获取几何的质心（适用于点、线、面）
        dm_centroid = dm_geom.centroid()
        if not dm_centroid or dm_centroid.isNull():
            continue
        dm_point = dm_centroid.asPoint()
        
        # 找最近的中心点
        min_distance = float('inf')
        nearest_lc = None
        
        for cp_data in center_points_data:
            cp_point = cp_data['point']
            
            # 如果坐标系不一致，转换中心点坐标到dm坐标系
            if coord_transform:
                cp_point = coord_transform.transform(cp_point)
            
            dist = distance_calc.measureLine(dm_point, cp_point)
            if dist < min_distance:
                min_distance = dist
                nearest_lc = cp_data['lc']
        
        # 创建新要素
        new_feat = QgsFeature(dm_lc_layer.fields())
        new_feat.setGeometry(dm_geom)
        
        # 复制原属性
        for field in dm_layer.fields():
            new_feat[field.name()] = dm_feat[field.name()]
        
        # 添加LC
        if nearest_lc is not None and min_distance < MAX_DISTANCE:
            new_feat['LC'] = nearest_lc
            matched_count += 1
        else:
            unmatched_count += 1
            if unmatched_count <= 3:
                print(f"     ⚠️  断面 {idx}: 未找到匹配 (最近距离={min_distance:.1f}m)")
        
        # 提取经纬度（从线的中点）
        lon, lat = get_line_center_coordinate(dm_geom)
        if lon is not None and lat is not None:
            new_feat['longitude'] = lon
            new_feat['latitude'] = lat
            coord_success += 1
        else:
            new_feat['longitude'] = None
            new_feat['latitude'] = None
            coord_fail += 1
        
        output_dm_features.append(new_feat)
        
        # 显示进度
        if idx % 10 == 0 or idx == original_dm_count:
            print(f"     进度: {idx}/{original_dm_count}")
    
    provider.addFeatures(output_dm_features)
    dm_lc_layer.updateExtents()
    
    dm_lc_count = dm_lc_layer.featureCount()
    print(f"  ✅ 匹配完成")
    print(f"     - 输出断面数: {dm_lc_count}")
    print(f"     - LC成功匹配: {matched_count} 个")
    if unmatched_count > 0:
        print(f"     - LC未匹配: {unmatched_count} 个")
    print(f"     - 经纬度提取成功: {coord_success} 个")
    if coord_fail > 0:
        print(f"     - 经纬度提取失败: {coord_fail} 个")
    
    # 检查数量一致性
    print(f"\n  📊 数量一致性检查:")
    print(f"     - 输入dm: {original_dm_count} 个")
    print(f"     - 输出dm_LC: {dm_lc_count} 个")
    
    if dm_lc_count == original_dm_count:
        print(f"     ✅ 数量完全一致，无重复！")
    else:
        print(f"     ⚠️  警告: 数量不一致！差值: {abs(dm_lc_count - original_dm_count)}")
    
    # ========== 步骤4-5: 高程插值 ==========
    zya_layer = interpolate_elevation_for_centers(center_layer, dm_lc_layer)
    
    if not zya_layer:
        print(f"\n  ❌ 错误: 高程插值失败")
        return None
    
    # ========== 步骤6: 添加到项目 ==========
    print(f"\n【步骤5】添加图层到QGIS项目")
    
    project = QgsProject.instance()
    
    # 移除旧的dm_LC图层（如果存在）
    existing_dm_lc = project.mapLayersByName(OUTPUT_DM_LC_LAYER)
    if existing_dm_lc:
        project.removeMapLayer(existing_dm_lc[0])
        print(f"  🗑️  已移除旧图层: {OUTPUT_DM_LC_LAYER}")
    
    # 移除旧的river_center_points_zya图层（如果存在）
    existing_zya = project.mapLayersByName(OUTPUT_CENTER_ZYA_LAYER)
    if existing_zya:
        project.removeMapLayer(existing_zya[0])
        print(f"  🗑️  已移除旧图层: {OUTPUT_CENTER_ZYA_LAYER}")
    
    # 查找或创建 process 组
    process_group = ensure_group_exists("process")
    
    # 添加dm_LC到process组
    project.addMapLayer(dm_lc_layer, False)
    process_group.addLayer(dm_lc_layer)
    print(f"  ✅ 已添加图层: {OUTPUT_DM_LC_LAYER} (process组)")
    
    # 添加river_center_points_zya到process组
    project.addMapLayer(zya_layer, False)
    process_group.addLayer(zya_layer)
    print(f"  ✅ 已添加图层: {OUTPUT_CENTER_ZYA_LAYER} (process组)")
    
    # ========== 保存图层并重新加载 ==========
    print(f"\n【步骤7】保存图层到文件并重新加载")
    if dm_lc_layer and dm_lc_layer.isValid():
        dm_lc_layer = save_and_reload_layer(dm_lc_layer)
    if zya_layer and zya_layer.isValid():
        zya_layer = save_and_reload_layer(zya_layer)
    
    # ========== 输出总结 ==========
    print("\n" + "=" * 80)
    print("✅ 断面LC赋值 + 中心点高程插值 完成！")
    print("=" * 80)
    print(f"⏰ 完成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n📊 生成结果:")
    
    print(f"\n  🟡 输出图层1: {OUTPUT_DM_LC_LAYER}")
    print(f"     - 断面数量: {dm_lc_count}")
    print(f"     - 数量对比: dm({original_dm_count}) → dm_LC({dm_lc_count})")
    if dm_lc_count == original_dm_count:
        print(f"     - ✅ 数量一致")
    print(f"     - 包含字段: 原断面字段 + LC + longitude + latitude")
    print(f"     - 图层状态: ✅ 已添加到项目")
    
    print(f"\n  🟢 输出图层2: {OUTPUT_CENTER_ZYA_LAYER} ⭐")
    print(f"     - 中心点数量: {zya_layer.featureCount()}")
    print(f"     - 包含字段: 原中心点字段 + zagc(左岸) + yagc(右岸) + hdgc(河底)")
    print(f"     - 图层状态: ✅ 已添加到项目")
    
    print(f"\n💡 使用提示:")
    print(f"   - dm_LC 和 river_center_points_zya 已添加到QGIS (process组)")
    print(f"   - 原 dm 和 river_center_points 图层保持不变")
    print(f"   - 后续脚本请使用 river_center_points_zya 代替 river_center_points")
    print(f"   - 可右键图层导出为GeoJSON/Shapefile等格式")
    
    print(f"\n📋 下一步:")
    print(f"   1. 运行 02_cut_dike_sections.py 切割堤防")
    print(f"   2. 运行 03_assign_elevation_to_dike.py 赋值高程（使用river_center_points_zya）")
    print(f"   3. 运行 04_align_dike_fields.py 对齐字段")
    
    print("=" * 80)
    print("🎉 脚本运行成功结束\n")
    
    return dm_lc_layer, zya_layer


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🎯 断面LC赋值 + 中心点高程插值脚本开始执行...")
    print("=" * 80)
    
    try:
        result = main()
        if result:
            print("\n" + "=" * 80)
            print("✓ 脚本执行成功！")
            print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print("✗ 脚本执行失败，请检查错误信息。")
            print("=" * 80)
    except Exception as e:
        print("\n" + "=" * 80)
        print("✗ 执行出错！")
        print("=" * 80)
        print(f"\n错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print(f"\n详细堆栈:")
        import traceback
        traceback.print_exc()
        print("=" * 80)
