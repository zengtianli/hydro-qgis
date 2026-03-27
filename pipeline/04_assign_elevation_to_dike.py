"""
04 河段中心点属性赋值给堤段（一对一匹配）+ 市县信息空间连接

功能:
1. 根据距离和岸别，将河段中心点的属性匹配到堤段
2. 一对一匹配：每个中心点对应左岸1个堤段 + 右岸1个堆段
3. 根据堤段岸别(zya)自动选择正确的高程:
   - L(左岸) → zagc(左岸堤顶高程)
   - R(右岸) → yagc(右岸堤顶高程)
4. 支持二次匹配，确保所有堤段都能获得高程数据
5. 通过空间连接(Join by Location)从市县图层赋值CITY和COUNTY字段

输入图层:
  - dike_sections: 堤段
    必需字段: zya
      · zya: 岸别 (L=左岸, R=右岸)

  - river_center_points_zya: 河段中心点（带高程）
    必需字段: LC, zagc, yagc
      · LC: 里程 (m)
      · zagc: 左岸高程 (m)
      · yagc: 右岸高程 (m)
    可选字段: hdgc（河底高程）

  - city_county: 市县区划【可选】
    必需字段: CITY, COUNTY
      · CITY: 地级市名称
      · COUNTY: 县/区名称

输出图层:
  - dike_sections_with_elevation: 堤段（带高程）
    继承字段: dike_sections 全部字段
    新增字段: LC, ddgc, 所属市, 所属县
      · LC: 里程 (m)
      · ddgc: 堤顶高程 (m)，根据 zya 选择 zagc/yagc
      · 所属市: 地级市名称（空间连接）
      · 所属县: 县/区名称（空间连接）
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
    QgsDistanceArea, QgsPointXY, QgsGeometry, QgsWkbTypes,
    QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant
import processing

# 导入工具函数库
from qgis_util import (
    validate_input_fields,
    validate_output_fields,
    move_layer_to_group,
    ensure_group_exists,
    get_layer_by_name,
    save_and_reload_layer
)

# 导入公共配置
from hydraulic.qgis_config import (
    OUTPUT_LAYERS,
    INPUT_LAYERS,
    ELEVATION_CONFIG
)

# ============ 配置参数 ============

# 输入图层名称
DIKE_LAYER_NAME = OUTPUT_LAYERS['dike_sections']           # 堤段图层
POINT_LAYER_NAME = OUTPUT_LAYERS['river_center_zya']       # 河段中心点图层（带高程）
CITY_COUNTY_LAYER_NAME = INPUT_LAYERS['city_county']       # 市县区划图层

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['dike_with_elevation']

# 字段映射
DIKE_BANK_FIELD = 'zya'              # 堤段岸别字段 (L/R)
DIKE_ELEVATION_FIELD = 'ddgc'        # 堤段堤顶高程字段（输出字段）
DIKE_LC_FIELD = 'LC'                 # 堤段里程字段

# 河段中心点字段
POINT_LC_FIELD = 'LC'                # 中心点里程字段
POINT_LEFT_ELEVATION = 'zagc'        # 左岸堤顶高程字段（或 zddgc）
POINT_RIGHT_ELEVATION = 'yagc'       # 右岸堤顶高程字段（或 yddgc）
POINT_BOTTOM_ELEVATION = 'hdgc'      # 河底高程字段（可选）

# 市县区划字段
CITY_FIELD = 'CITY'                  # 市字段
COUNTY_FIELD = 'COUNTY'              # 县字段

# 要从中心点传递到堤段的其他字段（可选）
ADDITIONAL_FIELDS = []  # 例如: ['river_name']

# 最大搜索距离 - 从公共配置读取
MAX_DISTANCE = ELEVATION_CONFIG['max_distance']                     # 一次匹配最大距离(米)
SECONDARY_MAX_DISTANCE = ELEVATION_CONFIG['secondary_max_distance']  # 二次匹配最大距离(米)

# ============ 主函数 ============



def calculate_distance(geom1, geom2, distance_calc):
    """计算两个几何对象之间的距离"""
    if geom1.type() == QgsWkbTypes.PointGeometry:
        pt1 = geom1.asPoint()
    else:
        pt1 = geom1.centroid().asPoint()
    
    if geom2.type() == QgsWkbTypes.PointGeometry:
        pt2 = geom2.asPoint()
    else:
        pt2 = geom2.centroid().asPoint()
    
    return distance_calc.measureLine(pt1, pt2)


def get_elevation_from_point(point_feat, bank_type):
    """
    根据岸别从中心点获取正确的高程
    
    参数:
        point_feat: 河段中心点要素
        bank_type: 岸别 ('L' 或 'R')
    
    返回:
        高程值
    """
    if bank_type == 'L':
        # 左岸，取左岸高程
        return point_feat[POINT_LEFT_ELEVATION]
    elif bank_type == 'R':
        # 右岸，取右岸高程
        return point_feat[POINT_RIGHT_ELEVATION]
    else:
        print(f"  ⚠️  警告: 未知岸别 '{bank_type}'，返回None")
        return None


def assign_elevation_to_dike():
    """执行河段中心点到堤段的属性赋值"""
    
    print("\n" + "=" * 80)
    print("🔄 河段中心点属性赋值给堤段（一对一匹配）")
    print("=" * 80)
    
    # ========== 1. 加载图层 ==========
    print(f"\n【步骤1】加载输入图层")
    
    dike_layer = get_layer_by_name(DIKE_LAYER_NAME)
    point_layer = get_layer_by_name(POINT_LAYER_NAME)
    city_county_layer = get_layer_by_name(CITY_COUNTY_LAYER_NAME)
    
    if not dike_layer or not point_layer:
        print("\n  ❌ 错误: 无法获取必需图层，请检查图层名称")
        return None
    
    print(f"  ✅ 堤段图层: {dike_layer.name()}")
    print(f"     - 要素数量: {dike_layer.featureCount()}")
    print(f"     - 坐标系: {dike_layer.crs().authid()}")
    
    print(f"  ✅ 中心点图层: {point_layer.name()}")
    print(f"     - 要素数量: {point_layer.featureCount()}")
    print(f"     - 坐标系: {point_layer.crs().authid()}")
    
    # 验证输入图层必需字段
    print(f"\n  🔍 验证输入图层字段...")
    
    # 验证堤段图层
    is_valid, missing = validate_input_fields(dike_layer, DIKE_LAYER_NAME, [DIKE_BANK_FIELD])
    if not is_valid:
        print(f"  💡 请确保堤段图层包含岸别字段 '{DIKE_BANK_FIELD}'")
        return None
    
    # 验证中心点图层
    required_point_fields = [POINT_LC_FIELD, POINT_LEFT_ELEVATION, POINT_RIGHT_ELEVATION]
    is_valid, missing = validate_input_fields(point_layer, POINT_LAYER_NAME, required_point_fields)
    if not is_valid:
        print(f"  💡 请先运行 generate_river_points.py 生成包含高程的中心点")
        return None
    
    print(f"  ✅ 输入图层字段验证通过")
    
    # 市县图层是可选的
    if city_county_layer:
        print(f"  ✅ 市县区划图层: {city_county_layer.name()}")
        print(f"     - 要素数量: {city_county_layer.featureCount()}")
        print(f"     - 坐标系: {city_county_layer.crs().authid()}")
        
        # 将市县图层移动到 input 组
        move_layer_to_group(city_county_layer, "input")
        print(f"     📁 已移动到 'input' 组")
    else:
        print(f"  ⚠️  警告: 未找到市县区划图层 '{CITY_COUNTY_LAYER_NAME}'，跳过CITY/COUNTY赋值")
    
    # ========== 检查坐标系一致性 ==========
    if dike_layer.crs().authid() != point_layer.crs().authid():
        print(f"\n  ⚠️  警告: 坐标系不一致！")
        print(f"     - 堤段: {dike_layer.crs().authid()}")
        print(f"     - 中心点: {point_layer.crs().authid()}")
        print(f"     → 自动重投影到投影坐标系 EPSG:4549...")
        
        # 使用 processing 重投影到统一坐标系
        target_crs = QgsCoordinateReferenceSystem('EPSG:4549')
        
        # 重投影堤段图层（如果不是目标坐标系）
        if dike_layer.crs().authid() != 'EPSG:4549':
            print(f"     → 重投影堤段图层...")
            reprojected_dike = processing.run("native:reprojectlayer", {
                'INPUT': dike_layer,
                'TARGET_CRS': target_crs,
                'OUTPUT': 'memory:'
            })['OUTPUT']
            dike_layer = reprojected_dike
            print(f"        ✅ 堤段已重投影到 EPSG:4549")
        
        # 重投影中心点图层（如果不是目标坐标系）
        if point_layer.crs().authid() != 'EPSG:4549':
            print(f"     → 重投影中心点图层...")
            reprojected_point = processing.run("native:reprojectlayer", {
                'INPUT': point_layer,
                'TARGET_CRS': target_crs,
                'OUTPUT': 'memory:'
            })['OUTPUT']
            point_layer = reprojected_point
            print(f"        ✅ 中心点已重投影到 EPSG:4549")
        
        print(f"     ✅ 坐标系已统一为: {target_crs.authid()}")
    
    # ========== 1.5 空间连接市县信息 ==========
    city_county_dict = {}  # {堤段ID: {'CITY': xxx, 'COUNTY': xxx}}
    
    if city_county_layer:
        print(f"\n【步骤1.5】从市县图层获取行政区划信息")
        print(f"  🔄 执行空间连接 (Join by Location)...")
        
        # 使用空间连接获取市县信息
        try:
            join_result = processing.run("native:joinattributesbylocation", {
                'INPUT': dike_layer,
                'JOIN': city_county_layer,
                'PREDICATE': [0],  # 0 = intersects (相交)
                'JOIN_FIELDS': [CITY_FIELD, COUNTY_FIELD],
                'METHOD': 0,  # 0 = 取第一个匹配的要素
                'DISCARD_NONMATCHING': False,
                'PREFIX': '',
                'OUTPUT': 'memory:'
            })
            
            joined_layer = join_result['OUTPUT']
            
            # 提取市县信息到字典
            joined_fields = [f.name() for f in joined_layer.fields()]
            has_city = CITY_FIELD in joined_fields
            has_county = COUNTY_FIELD in joined_fields
            
            if has_city or has_county:
                for feat in joined_layer.getFeatures():
                    dike_id = feat.id()
                    city_county_dict[dike_id] = {
                        'CITY': feat[CITY_FIELD] if has_city else None,
                        'COUNTY': feat[COUNTY_FIELD] if has_county else None
                    }
                
                print(f"  ✅ 已获取 {len(city_county_dict)} 个堤段的市县信息")
                
                # 统计有效数据
                valid_city = sum(1 for v in city_county_dict.values() if v['CITY'])
                valid_county = sum(1 for v in city_county_dict.values() if v['COUNTY'])
                print(f"     - CITY 有效值: {valid_city}")
                print(f"     - COUNTY 有效值: {valid_county}")
            else:
                print(f"  ⚠️  警告: 市县图层中未找到字段 '{CITY_FIELD}' 或 '{COUNTY_FIELD}'")
                
        except Exception as e:
            print(f"  ⚠️  警告: 空间连接失败: {str(e)}")
            print(f"     将跳过CITY/COUNTY赋值")
    
    # 检查字段
    dike_fields = [f.name() for f in dike_layer.fields()]
    point_fields = [f.name() for f in point_layer.fields()]
    
    print(f"\n  🔍 字段检查:")
    print(f"     - 堤段岸别字段 '{DIKE_BANK_FIELD}': {'✅' if DIKE_BANK_FIELD in dike_fields else '❌'}")
    print(f"     - 中心点左岸高程 '{POINT_LEFT_ELEVATION}': {'✅' if POINT_LEFT_ELEVATION in point_fields else '❌'}")
    print(f"     - 中心点右岸高程 '{POINT_RIGHT_ELEVATION}': {'✅' if POINT_RIGHT_ELEVATION in point_fields else '❌'}")
    
    # 验证必需字段
    missing_fields = []
    if DIKE_BANK_FIELD not in dike_fields:
        missing_fields.append(f"堤段图层缺少 '{DIKE_BANK_FIELD}'")
    if POINT_LEFT_ELEVATION not in point_fields:
        missing_fields.append(f"中心点图层缺少 '{POINT_LEFT_ELEVATION}'")
    if POINT_RIGHT_ELEVATION not in point_fields:
        missing_fields.append(f"中心点图层缺少 '{POINT_RIGHT_ELEVATION}'")
    
    if missing_fields:
        print(f"\n  ❌ 错误: {', '.join(missing_fields)}")
        return None
    
    # ========== 2. 初始化距离计算器 ==========
    distance_calc = QgsDistanceArea()
    distance_calc.setSourceCrs(dike_layer.crs(), QgsProject.instance().transformContext())
    distance_calc.setEllipsoid('WGS84')
    
    # ========== 3. 按岸别分组堤段 ==========
    print(f"\n【步骤2】按岸别分组堤段")
    
    left_dikes = []   # 左岸堤段
    right_dikes = []  # 右岸堤段
    other_dikes = []  # 其他（岸别不明）
    
    for feat in dike_layer.getFeatures():
        bank = feat[DIKE_BANK_FIELD]
        if bank == 'L':
            left_dikes.append(feat)
        elif bank == 'R':
            right_dikes.append(feat)
        else:
            other_dikes.append(feat)
    
    print(f"  ✅ 左岸堤段: {len(left_dikes)} 条")
    print(f"  ✅ 右岸堤段: {len(right_dikes)} 条")
    if other_dikes:
        print(f"  ⚠️  其他堤段: {len(other_dikes)} 条（岸别不是L或R）")
    
    # ========== 4. 计算距离矩阵 ==========
    print(f"\n【步骤3】计算距离矩阵")
    print(f"  🔄 搜索范围: {MAX_DISTANCE}米（一次匹配）, {SECONDARY_MAX_DISTANCE}米（二次匹配）")
    
    point_features = list(point_layer.getFeatures())
    
    def build_distance_matrix(dike_list, bank_name):
        """为指定岸别构建距离矩阵"""
        distance_matrix = []  # [(距离, 堤段feature, 点feature), ...]
        all_distances = {}    # {堤段ID: [(距离, 点feature), ...]}
        
        for dike_feat in dike_list:
            dike_id = dike_feat.id()
            dike_geom = dike_feat.geometry()
            all_distances[dike_id] = []
            
            for point_feat in point_features:
                point_geom = point_feat.geometry()
                distance = calculate_distance(dike_geom, point_geom, distance_calc)
                
                # 保存所有距离（用于二次匹配）
                if distance <= SECONDARY_MAX_DISTANCE:
                    all_distances[dike_id].append((distance, point_feat))
                
                # 只有在一次匹配范围内的才加入矩阵
                if distance <= MAX_DISTANCE:
                    distance_matrix.append((distance, dike_feat, point_feat))
            
            # 对每个堤段的点按距离排序
            all_distances[dike_id].sort(key=lambda x: x[0])
        
        return distance_matrix, all_distances
    
    # 分别为左右岸构建距离矩阵
    left_matrix, left_all_distances = build_distance_matrix(left_dikes, "左岸")
    right_matrix, right_all_distances = build_distance_matrix(right_dikes, "右岸")
    
    print(f"  ✅ 左岸候选匹配: {len(left_matrix)} 对")
    print(f"  ✅ 右岸候选匹配: {len(right_matrix)} 对")
    
    # ========== 5. 执行一对一匹配 ==========
    print(f"\n【步骤4】执行一对一匹配")
    
    def one_to_one_match(distance_matrix, all_distances, bank_name):
        """执行一对一匹配"""
        # 按距离排序
        distance_matrix.sort(key=lambda x: x[0])
        
        matched_dikes = set()
        matched_points = set()
        matches = {}  # {堤段ID: (距离, 点feature)}
        
        # 一次匹配
        for distance, dike_feat, point_feat in distance_matrix:
            dike_id = dike_feat.id()
            point_id = point_feat.id()
            
            if dike_id not in matched_dikes and point_id not in matched_points:
                matches[dike_id] = (distance, point_feat, 'primary')
                matched_dikes.add(dike_id)
                matched_points.add(point_id)
        
        print(f"    {bank_name}一次匹配: {len(matches)} 对")
        
        # 二次匹配：为未匹配的堤段找最近的点
        unmatched_count = len(all_distances) - len(matched_dikes)
        if unmatched_count > 0:
            print(f"    {bank_name}未匹配: {unmatched_count} 个，执行二次匹配...")
            secondary_matched = 0
            
            for dike_id, distances in all_distances.items():
                if dike_id not in matched_dikes and distances:
                    closest_distance, closest_point = distances[0]
                    matches[dike_id] = (closest_distance, closest_point, 'secondary')
                    matched_dikes.add(dike_id)
                    secondary_matched += 1
            
            print(f"    {bank_name}二次匹配: {secondary_matched} 对")
        
        return matches
    
    left_matches = one_to_one_match(left_matrix, left_all_distances, "左岸")
    right_matches = one_to_one_match(right_matrix, right_all_distances, "右岸")
    
    print(f"\n  ✅ 总匹配数: {len(left_matches) + len(right_matches)} / {dike_layer.featureCount()}")
    
    # ========== 6. 创建输出图层 ==========
    print(f"\n【步骤5】创建输出图层")
    
    geom_type = QgsWkbTypes.displayString(dike_layer.wkbType())
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={dike_layer.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    output_provider = output_layer.dataProvider()
    
    if not output_layer.isValid():
        print("  ❌ 错误: 无法创建输出图层")
        return None
    
    # 复制堤段图层的所有字段
    output_provider.addAttributes(dike_layer.fields().toList())
    
    # 添加匹配信息字段
    new_fields = [
        QgsField("match_dist", QVariant.Double),       # 匹配距离
        QgsField("match_point_lc", QVariant.Int),      # 匹配的中心点LC
        QgsField("match_type", QVariant.String, len=20), # primary/secondary
    ]
    
    # 添加LC字段（如果不存在）
    if DIKE_LC_FIELD not in dike_fields:
        new_fields.append(QgsField(DIKE_LC_FIELD, QVariant.Int))
        print(f"  ➕ 添加里程字段: {DIKE_LC_FIELD}")
    else:
        print(f"  → 里程字段已存在，将覆盖: {DIKE_LC_FIELD}")
    
    # 添加高程字段（如果不存在）
    if DIKE_ELEVATION_FIELD not in dike_fields:
        new_fields.append(QgsField(DIKE_ELEVATION_FIELD, QVariant.Double))
        print(f"  ➕ 添加堤顶高程字段: {DIKE_ELEVATION_FIELD}")
    else:
        print(f"  → 堤顶高程字段已存在，将覆盖: {DIKE_ELEVATION_FIELD}")
    
    # 添加河底高程字段（可选）
    if POINT_BOTTOM_ELEVATION in point_fields:
        if POINT_BOTTOM_ELEVATION not in dike_fields:
            new_fields.append(QgsField(POINT_BOTTOM_ELEVATION, QVariant.Double))
            print(f"  ➕ 添加河底高程字段: {POINT_BOTTOM_ELEVATION}")
    
    # 添加CITY和COUNTY字段（如果有市县数据）
    if city_county_dict:
        if CITY_FIELD not in dike_fields:
            new_fields.append(QgsField(CITY_FIELD, QVariant.String, len=50))
            print(f"  ➕ 添加市字段: {CITY_FIELD}")
        else:
            print(f"  → 市字段已存在，将覆盖: {CITY_FIELD}")
        
        if COUNTY_FIELD not in dike_fields:
            new_fields.append(QgsField(COUNTY_FIELD, QVariant.String, len=50))
            print(f"  ➕ 添加县字段: {COUNTY_FIELD}")
        else:
            print(f"  → 县字段已存在，将覆盖: {COUNTY_FIELD}")
    
    output_provider.addAttributes(new_fields)
    output_layer.updateFields()
    
    # ========== 7. 写入要素并赋值 ==========
    print(f"\n【步骤6】写入要素并赋值高程")
    
    output_features = []
    left_assigned = 0
    right_assigned = 0
    unmatched = 0
    
    # 合并匹配结果
    all_matches = {}
    all_matches.update(left_matches)
    all_matches.update(right_matches)
    
    for dike_feat in dike_layer.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(dike_feat.geometry())
        
        # 复制堤段所有属性
        for field in dike_layer.fields():
            new_feat[field.name()] = dike_feat[field.name()]
        
        dike_id = dike_feat.id()
        bank_type = dike_feat[DIKE_BANK_FIELD]
        
        # 赋值匹配信息和高程
        if dike_id in all_matches:
            distance, point_feat, match_type = all_matches[dike_id]
            
            # 匹配信息
            new_feat['match_dist'] = distance
            new_feat['match_point_lc'] = point_feat[POINT_LC_FIELD] if POINT_LC_FIELD in point_fields else None
            new_feat['match_type'] = match_type
            
            # 赋值里程（从中心点）
            if POINT_LC_FIELD in point_fields:
                new_feat[DIKE_LC_FIELD] = point_feat[POINT_LC_FIELD]
            
            # 根据岸别选择正确的高程
            elevation = get_elevation_from_point(point_feat, bank_type)
            new_feat[DIKE_ELEVATION_FIELD] = elevation
            
            # 河底高程（可选）
            if POINT_BOTTOM_ELEVATION in point_fields:
                new_feat[POINT_BOTTOM_ELEVATION] = point_feat[POINT_BOTTOM_ELEVATION]
            
            # 统计
            if bank_type == 'L':
                left_assigned += 1
            elif bank_type == 'R':
                right_assigned += 1
        else:
            new_feat['match_dist'] = None
            new_feat['match_point_lc'] = None
            new_feat['match_type'] = 'unmatched'
            new_feat[DIKE_LC_FIELD] = None
            new_feat[DIKE_ELEVATION_FIELD] = None
            unmatched += 1
        
        # 赋值市县信息（如果有）
        if city_county_dict and dike_id in city_county_dict:
            new_feat[CITY_FIELD] = city_county_dict[dike_id]['CITY']
            new_feat[COUNTY_FIELD] = city_county_dict[dike_id]['COUNTY']
        
        output_features.append(new_feat)
    
    output_provider.addFeatures(output_features)
    
    print(f"  ✅ 左岸赋值: {left_assigned} 条")
    print(f"  ✅ 右岸赋值: {right_assigned} 条")
    if unmatched > 0:
        print(f"  ⚠️  未匹配: {unmatched} 条")
    
    # ========== 8. 添加到项目（process组）==========
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    
    # 查找或创建 process 组
    process_group = ensure_group_exists("process")
    
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    print(f"\n  🗺️  图层已添加到QGIS项目: {OUTPUT_LAYER_NAME} (process组)")
    
    # ========== 9. 验证输出图层 ==========
    print("\n" + "=" * 80)
    print("🔍 验证输出图层")
    print("=" * 80)
    
    required_output_fields = [DIKE_ELEVATION_FIELD, DIKE_LC_FIELD, 'match_dist', 'match_point_lc', 'match_type']
    if city_county_dict:
        required_output_fields.extend([CITY_FIELD, COUNTY_FIELD])
    
    is_valid, missing = validate_output_fields(output_layer, OUTPUT_LAYER_NAME, required_output_fields)
    if is_valid:
        print(f"  ✅ {OUTPUT_LAYER_NAME}: 字段验证通过")
        print(f"     - 包含字段: {', '.join(required_output_fields)}")
    else:
        print(f"  ⚠️  {OUTPUT_LAYER_NAME}: 字段验证失败")
    
    # ========== 保存图层并重新加载 ==========
    print("\n" + "=" * 80)
    print("💾 保存图层到文件并重新加载")
    print("=" * 80)
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    # ========== 10. 统计信息 ==========
    print("\n" + "=" * 80)
    print("✅ 脚本执行完成！")
    print("=" * 80)
    
    print(f"\n📊 匹配统计:")
    
    # 左岸统计
    if left_matches:
        left_distances = [m[0] for m in left_matches.values()]
        print(f"\n  左岸 ({len(left_matches)} 条):")
        print(f"     - 最小距离: {min(left_distances):.2f} 米")
        print(f"     - 最大距离: {max(left_distances):.2f} 米")
        print(f"     - 平均距离: {sum(left_distances)/len(left_distances):.2f} 米")
    
    # 右岸统计
    if right_matches:
        right_distances = [m[0] for m in right_matches.values()]
        print(f"\n  右岸 ({len(right_matches)} 条):")
        print(f"     - 最小距离: {min(right_distances):.2f} 米")
        print(f"     - 最大距离: {max(right_distances):.2f} 米")
        print(f"     - 平均距离: {sum(right_distances)/len(right_distances):.2f} 米")
    
    # 中心点使用统计
    point_usage = {}
    for _, point_feat, _ in all_matches.values():
        point_id = point_feat.id()
        point_usage[point_id] = point_usage.get(point_id, 0) + 1
    
    shared_points = {pid: count for pid, count in point_usage.items() if count > 1}
    print(f"\n  📍 中心点使用情况:")
    print(f"     - 总中心点数: {point_layer.featureCount()}")
    print(f"     - 已使用: {len(point_usage)} 个")
    print(f"     - 共享点（被2个堤段使用）: {len(shared_points)} 个")
    
    # 市县信息统计
    if city_county_dict:
        city_count = sum(1 for v in city_county_dict.values() if v.get('CITY'))
        county_count = sum(1 for v in city_county_dict.values() if v.get('COUNTY'))
        print(f"\n  🏙️  市县信息统计:")
        print(f"     - 已赋值CITY: {city_count} 条堤段")
        print(f"     - 已赋值COUNTY: {county_count} 条堤段")
    
    print(f"\n💡 使用提示:")
    print(f"   - 输出图层已包含高程数据")
    print(f"   - match_type = 'primary': 一对一精确匹配")
    print(f"   - match_type = 'secondary': 二次匹配（共享中心点）")
    print(f"   - 可通过 {DIKE_BANK_FIELD} 字段筛选左岸(L)或右岸(R)")
    if city_county_dict:
        print(f"   - 已添加 {CITY_FIELD} 和 {COUNTY_FIELD} 字段")
    print(f"   - 可右键导出为GeoJSON/Shapefile等格式")
    
    print("=" * 80)
    print("🎉 脚本运行成功结束\n")
    
    return output_layer


# ============ 执行 ============

try:
    print("\n" + "=" * 80)
    print("🔄 河段中心点属性赋值脚本开始执行...")
    print("=" * 80)
    result = assign_elevation_to_dike()
    
    if result:
        print("\n✅ 脚本执行成功！请查看新生成的图层。")
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


