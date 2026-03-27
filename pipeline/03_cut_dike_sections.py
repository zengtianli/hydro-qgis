"""
03 堤防切割脚本 - 自动分别处理左右岸堤防切割

功能:
1. 自动筛选左右岸堤防（根据zya字段）
2. 分别对左右岸进行最近邻匹配和切割
3. 生成切割线并自动延长端点（确保能切到堤防）
4. 合并左右岸堤段为一个完整图层

输入图层:
  - river_cut_points: 河段切割点
    必需字段: LC
      · LC: 里程 (m)，偏移50m (50, 150, 250...)

  - df: 堤防线
    必需字段: zya
      · zya: 岸别 (L=左岸, R=右岸)
    可选字段: dikeName, polderCode 等（会继承到输出）

输出图层:
  - cut_lines_left: 左岸切割线（可视化排查用）
  - cut_lines_right: 右岸切割线（可视化排查用）
  - dike_sections: 堤段
    继承字段: df 全部字段
    说明: 左右岸合并，每个堤段对应一个100m河段

工作流程:
左岸处理:
  - 步骤1: 筛选左岸堤防 (zya='L')
  - 步骤2: 最近邻匹配 - 切割点 → 左岸堤防最近点
  - 步骤3: 生成左岸切割线
  - 步骤4: 延长切割线（堤防端2米）
  - 步骤5: 切割左岸堤防 → 左岸堤段

右岸处理:
  - 步骤1-5: 同上，处理右岸 (zya='R')

最后合并:
  - 合并左右岸堤段为一个完整图层

优势:
- 自动分离左右岸处理，避免切割线交叉干扰
- 一次运行完成所有切割，无需手动分两次操作
- 切割线自动延长，确保切割成功
- 输出完整的堤段图层，保留岸别信息
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
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsPointXY, QgsField, QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant
from qgis import processing

# 导入工具函数库
from qgis_util import (
    validate_input_fields,
    validate_output_fields,
    move_layer_to_group,
    ensure_group_exists,
    save_and_reload_layer
)

# 导入公共配置
from hydraulic.qgis_config import (
    INPUT_LAYERS,
    OUTPUT_LAYERS,
    DIKE_CUT_CONFIG
)

# ============ 配置参数 ============

# 输入图层名称
RIVER_CUT_POINTS = OUTPUT_LAYERS['river_cut_points']  # 河段切割点图层
DIKE_LAYER = INPUT_LAYERS['dike']                     # 堤防线图层

# 输出图层名称
OUTPUT_CUT_LINES_LEFT = 'cut_lines_left'    # 左岸切割线图层（可视化）
OUTPUT_CUT_LINES_RIGHT = 'cut_lines_right'  # 右岸切割线图层（可视化）
OUTPUT_DIKE_SECTIONS = OUTPUT_LAYERS['dike_sections']  # 堤段图层（最终成果）

# 堤防岸别字段
DIKE_BANK_FIELD = 'zya'  # 岸别字段名（L=左岸，R=右岸）

# 最近邻匹配参数 - 从公共配置读取
MAX_DISTANCE = DIKE_CUT_CONFIG['max_distance']      # 最大搜索距离(米)
EXTEND_START = DIKE_CUT_CONFIG['extend_start']      # 起点延长距离(米)
EXTEND_END = DIKE_CUT_CONFIG['extend_end']          # 终点延长距离(米)

# ============ 辅助函数 ============

def process_single_bank(cut_points_layer, dike_layer, bank_type, bank_name):
    """
    处理单个岸别的堤防切割
    
    参数:
        cut_points_layer: 切割点图层
        dike_layer: 堤防图层
        bank_type: 岸别类型 ('L' 或 'R')
        bank_name: 岸别名称（用于显示，如"左岸"）
    
    返回:
        (切割线图层, 堤段图层)
    """
    print(f"\n{'='*60}")
    print(f"🔄 处理{bank_name}堤防")
    print(f"{'='*60}")
    
    # 1. 筛选指定岸别的堤防
    print(f"\n  【步骤1】筛选{bank_name}堤防")
    print(f"  🔍 筛选条件: {DIKE_BANK_FIELD} = '{bank_type}'")
    
    filtered_dike = processing.run("native:extractbyattribute", {
        'INPUT': dike_layer,
        'FIELD': DIKE_BANK_FIELD,
        'OPERATOR': 0,  # =
        'VALUE': bank_type,
        'OUTPUT': 'memory:'
    })
    
    filtered_dike_layer = filtered_dike['OUTPUT']
    dike_count = filtered_dike_layer.featureCount()
    
    if dike_count == 0:
        print(f"  ⚠️  未找到{bank_name}堤防，跳过")
        return None, None
    
    print(f"  ✅ 筛选完成: {dike_count} 条{bank_name}堤防")
    
    # 2. 最近邻匹配
    print(f"\n  【步骤2】最近邻匹配（切割点 → {bank_name}堤防）")
    print(f"     - 最大距离: {MAX_DISTANCE} 米")
    
    joined_result = processing.run("native:joinbynearest", {
        'INPUT': cut_points_layer,
        'INPUT_2': filtered_dike_layer,
        'FIELDS_TO_COPY': [],
        'PREFIX': '',
        'MAX_DISTANCE': MAX_DISTANCE,
        'OUTPUT': 'memory:'
    })
    
    joined_layer = joined_result['OUTPUT']
    matched_count = joined_layer.featureCount()
    print(f"  ✅ 匹配完成: {matched_count} 个匹配点")
    
    # 检查匹配结果
    if matched_count == 0:
        print(f"  ❌ 警告: 未找到任何匹配点！")
        print(f"     可能原因:")
        print(f"     1. 切割点和堤防空间位置相距超过 {MAX_DISTANCE} 米")
        print(f"     2. 坐标系不一致（已检查）")
        print(f"     3. 图层数据为空或几何无效")
        print(f"     建议: 在QGIS中目视检查切割点和{bank_name}堤防的位置关系")
    
    # 3. 生成切割线
    print(f"\n  【步骤3】生成{bank_name}切割线")
    cut_lines_layer = create_cut_lines(joined_layer, bank_name)
    
    if not cut_lines_layer:
        print(f"  ❌ {bank_name}切割线创建失败")
        return None, None
    
    # 4. 延长切割线
    print(f"\n  【步骤4】延长{bank_name}切割线")
    print(f"     - 起点: {EXTEND_START}米, 终点: {EXTEND_END}米")
    
    extend_result = processing.run("native:extendlines", {
        'INPUT': cut_lines_layer,
        'START_DISTANCE': EXTEND_START,
        'END_DISTANCE': EXTEND_END,
        'OUTPUT': 'memory:'
    })
    
    extended_lines_layer = extend_result['OUTPUT']
    print(f"  ✅ 延长完成: {extended_lines_layer.featureCount()} 条切割线")
    
    # 5. 切割堤防
    print(f"\n  【步骤5】切割{bank_name}堤防")
    
    split_result = processing.run("native:splitwithlines", {
        'INPUT': filtered_dike_layer,
        'LINES': extended_lines_layer,
        'OUTPUT': 'memory:'
    })
    
    dike_sections = split_result['OUTPUT']
    print(f"  ✅ 切割完成:")
    print(f"     - 原始堤防: {dike_count} 条")
    print(f"     - 切割后堤段: {dike_sections.featureCount()} 条")
    
    # 统计堤段长度
    lengths = [feat.geometry().length() for feat in dike_sections.getFeatures() if feat.geometry()]
    if lengths:
        print(f"     - 平均长度: {sum(lengths)/len(lengths):.2f} 米")
    
    return cut_lines_layer, dike_sections


def create_cut_lines(joined_layer, bank_name=""):
    """
    根据最近邻匹配结果，生成切割线图层
    
    参数:
        joined_layer: 最近邻匹配后的图层，包含切割点坐标和堤防最近点坐标
        bank_name: 岸别名称（用于显示）
    
    返回:
        切割线图层 (QgsVectorLayer)
    """
    print(f"  🔄 生成{bank_name}切割线...")
    
    # 获取坐标系
    crs = joined_layer.crs().authid()
    
    # 创建线图层（使用临时名称，后续会重命名）
    line_layer = QgsVectorLayer(f'LineString?crs={crs}', f'cut_lines_{bank_name}', 'memory')
    provider = line_layer.dataProvider()
    
    # 添加字段
    provider.addAttributes([
        QgsField('LC', QVariant.Int),           # 里程
        QgsField('distance', QVariant.Double),  # 切割点到堤防的距离
        QgsField('cut_id', QVariant.Int)        # 切割点ID
    ])
    line_layer.updateFields()
    
    # 创建线要素
    line_features = []
    skipped = 0
    
    for i, feat in enumerate(joined_layer.getFeatures()):
        try:
            # 获取切割点坐标 (feature_x, feature_y)
            feature_x = feat['feature_x']
            feature_y = feat['feature_y']
            
            # 获取堤防最近点坐标 (nearest_x, nearest_y)
            nearest_x = feat['nearest_x']
            nearest_y = feat['nearest_y']
            
            # 检查坐标有效性
            if None in [feature_x, feature_y, nearest_x, nearest_y]:
                skipped += 1
                continue
            
            # 创建线几何
            start_point = QgsPointXY(float(feature_x), float(feature_y))
            end_point = QgsPointXY(float(nearest_x), float(nearest_y))
            
            line_feat = QgsFeature()
            line_feat.setGeometry(QgsGeometry.fromPolylineXY([start_point, end_point]))
            
            # 设置属性
            lc = feat['LC'] if 'LC' in feat.fields().names() else None
            distance = feat['distance'] if 'distance' in feat.fields().names() else None
            
            line_feat.setAttributes([lc, distance, i+1])
            line_features.append(line_feat)
            
        except Exception as e:
            print(f"  ⚠️  警告: 处理要素 {i+1} 时出错: {e}")
            skipped += 1
            continue
    
    # 添加要素到图层
    if line_features:
        provider.addFeatures(line_features)
        line_layer.updateExtents()
        print(f"  ✅ 成功创建 {len(line_features)} 条切割线")
        if skipped > 0:
            print(f"     ⚠️  跳过 {skipped} 个无效要素")
    else:
        print(f"  ❌ 未能创建任何切割线")
        return None
    
    # 统计距离
    distances = [feat['distance'] for feat in line_layer.getFeatures() if feat['distance'] is not None]
    if distances:
        print(f"  📊 切割线统计:")
        print(f"     - 距离范围: {min(distances):.2f} ~ {max(distances):.2f} 米")
        print(f"     - 平均距离: {sum(distances)/len(distances):.2f} 米")
    
    return line_layer


def main():
    """主流程 - 自动分别处理左右岸堤防"""
    print("\n" + "=" * 80)
    print("🔪 堤防切割工具 - 自动处理左右岸")
    print("=" * 80)
    print(f"⏰ 脚本启动时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========== 加载输入图层 ==========
    print(f"\n【初始化】加载输入图层")
    
    # 加载切割点图层
    print(f"  🔍 查找切割点图层: {RIVER_CUT_POINTS}")
    cut_points_layers = QgsProject.instance().mapLayersByName(RIVER_CUT_POINTS)
    
    if not cut_points_layers:
        print(f"  ❌ 错误: 找不到图层 '{RIVER_CUT_POINTS}'")
        print(f"  💡 请先运行 generate_river_points.py 生成切割点")
        return
    
    cut_points_layer = cut_points_layers[0]
    cut_count = cut_points_layer.featureCount()
    print(f"  ✅ 切割点图层: {cut_count} 个点")
    print(f"     - 坐标系: {cut_points_layer.crs().authid()}")
    
    # 获取切割点的范围
    extent = cut_points_layer.extent()
    print(f"     - 范围: X[{extent.xMinimum():.2f}, {extent.xMaximum():.2f}], Y[{extent.yMinimum():.2f}, {extent.yMaximum():.2f}]")
    
    # 验证切割点图层必需字段
    print(f"\n  🔍 验证切割点图层字段...")
    is_valid, missing = validate_input_fields(cut_points_layer, RIVER_CUT_POINTS, ['LC'])
    if not is_valid:
        print(f"  💡 请先运行 generate_river_points.py 生成切割点")
        return
    print(f"  ✅ 切割点图层字段验证通过")
    
    # 加载堤防图层
    print(f"\n  🔍 查找堤防图层: {DIKE_LAYER}")
    dike_layers = QgsProject.instance().mapLayersByName(DIKE_LAYER)
    
    if not dike_layers:
        print(f"  ❌ 错误: 找不到图层 '{DIKE_LAYER}'")
        print(f"  💡 请确认堤防图层已加载到QGIS项目")
        return
    
    dike_layer = dike_layers[0]
    dike_count = dike_layer.featureCount()
    print(f"  ✅ 堤防图层: {dike_count} 条堤防")
    print(f"     - 坐标系: {dike_layer.crs().authid()}")
    
    # 获取堤防的范围
    dike_extent = dike_layer.extent()
    print(f"     - 范围: X[{dike_extent.xMinimum():.2f}, {dike_extent.xMaximum():.2f}], Y[{dike_extent.yMinimum():.2f}, {dike_extent.yMaximum():.2f}]")
    
    # 将堤防图层移动到 input 组
    move_layer_to_group(dike_layer, "input")
    print(f"     📁 已移动到 'input' 组")
    
    # ========== 检查坐标系一致性 ==========
    cut_crs = cut_points_layer.crs().authid()
    dike_crs = dike_layer.crs().authid()
    
    print(f"\n  🔍 坐标系检查:")
    print(f"     - 切割点: {cut_crs}")
    print(f"     - 堤防: {dike_crs}")
    
    if cut_crs != dike_crs:
        print(f"\n  ⚠️  警告: 坐标系不一致！")
        print(f"     → 自动重投影堤防图层到 {cut_crs}...")
        
        # 重投影堤防图层到切割点的坐标系
        reproject_result = processing.run("native:reprojectlayer", {
            'INPUT': dike_layer,
            'TARGET_CRS': cut_points_layer.crs(),
            'OUTPUT': 'memory:'
        })
        dike_layer = reproject_result['OUTPUT']
        print(f"     ✅ 重投影完成: {dike_layer.crs().authid()}")
    else:
        print(f"     ✅ 坐标系一致")
    
    # ========== 检查空间范围是否重叠 ==========
    print(f"\n  🔍 检查空间范围重叠:")
    cut_extent = cut_points_layer.extent()
    dike_extent_check = dike_layer.extent()
    
    # 检查范围是否相交
    if cut_extent.intersects(dike_extent_check):
        print(f"     ✅ 切割点和堤防的空间范围有重叠")
        # 计算重叠范围
        intersect_extent = cut_extent.intersect(dike_extent_check)
        print(f"     - 重叠范围: X[{intersect_extent.xMinimum():.2f}, {intersect_extent.xMaximum():.2f}]")
        print(f"                 Y[{intersect_extent.yMinimum():.2f}, {intersect_extent.yMaximum():.2f}]")
    else:
        print(f"     ❌ 警告: 切割点和堤防的空间范围不重叠！")
        print(f"     - 可能导致最近邻匹配失败")
        print(f"     - 请在QGIS中目视检查两个图层的位置")
    
    # 验证堤防图层必需字段
    print(f"\n  🔍 验证堤防图层字段...")
    is_valid, missing = validate_input_fields(dike_layer, DIKE_LAYER, [DIKE_BANK_FIELD])
    if not is_valid:
        print(f"  💡 请确保堤防图层包含岸别字段 '{DIKE_BANK_FIELD}'")
        return
    print(f"  ✅ 堤防图层字段验证通过")
    
    # ========== 分别处理左右岸 ==========
    print(f"\n" + "=" * 80)
    print("🚀 开始分别处理左右岸堤防")
    print("=" * 80)
    
    # 处理左岸
    cut_lines_left, sections_left = process_single_bank(
        cut_points_layer, dike_layer, 'L', '左岸'
    )
    
    # 处理右岸
    cut_lines_right, sections_right = process_single_bank(
        cut_points_layer, dike_layer, 'R', '右岸'
    )
    
    # ========== 合并左右岸堤段 ==========
    print(f"\n" + "=" * 80)
    print("📦 合并左右岸堤段")
    print("=" * 80)
    
    layers_to_merge = []
    if sections_left:
        layers_to_merge.append(sections_left)
        print(f"  ✅ 左岸堤段: {sections_left.featureCount()} 条")
    else:
        print(f"  ⚠️  左岸堤段: 无")
    
    if sections_right:
        layers_to_merge.append(sections_right)
        print(f"  ✅ 右岸堤段: {sections_right.featureCount()} 条")
    else:
        print(f"  ⚠️  右岸堤段: 无")
    
    if not layers_to_merge:
        print(f"\n  ❌ 错误: 左右岸都没有生成堤段")
        return
    
    # 合并图层
    print(f"\n  🔄 合并图层...")
    if len(layers_to_merge) == 1:
        # 只有一个岸别有数据
        merged_sections = layers_to_merge[0]
        print(f"  ⚠️  只有一个岸别有数据，不需要合并")
    else:
        # 合并左右岸
        merge_result = processing.run("native:mergevectorlayers", {
            'LAYERS': layers_to_merge,
            'OUTPUT': 'memory:'
        })
        merged_sections = merge_result['OUTPUT']
    
    merged_sections.setName(OUTPUT_DIKE_SECTIONS)
    print(f"  ✅ 合并完成: {merged_sections.featureCount()} 条堤段")
    
    # 统计堤段长度
    lengths = [feat.geometry().length() for feat in merged_sections.getFeatures() if feat.geometry()]
    if lengths:
        print(f"\n  📊 堤段统计:")
        print(f"     - 总数量: {len(lengths)} 条")
        print(f"     - 最小长度: {min(lengths):.2f} 米")
        print(f"     - 最大长度: {max(lengths):.2f} 米")
        print(f"     - 平均长度: {sum(lengths)/len(lengths):.2f} 米")
        print(f"     - 总长度: {sum(lengths):.2f} 米")
    
    # ========== 添加图层到项目 ==========
    print(f"\n" + "=" * 80)
    print("🗺️  添加图层到QGIS项目")
    print("=" * 80)
    
    # 查找或创建 process 组
    project = QgsProject.instance()
    process_group = ensure_group_exists("process")
    
    # 添加切割线图层到process组
    if cut_lines_left:
        cut_lines_left.setName(OUTPUT_CUT_LINES_LEFT)
        project.addMapLayer(cut_lines_left, False)
        process_group.addLayer(cut_lines_left)
        print(f"  ✅ 左岸切割线: {cut_lines_left.featureCount()} 条 (process组)")
    
    if cut_lines_right:
        cut_lines_right.setName(OUTPUT_CUT_LINES_RIGHT)
        project.addMapLayer(cut_lines_right, False)
        process_group.addLayer(cut_lines_right)
        print(f"  ✅ 右岸切割线: {cut_lines_right.featureCount()} 条 (process组)")
    
    # 添加堤段图层到process组
    project.addMapLayer(merged_sections, False)
    process_group.addLayer(merged_sections)
    print(f"  ✅ 堤段图层: {merged_sections.featureCount()} 条 (process组)")
    
    # ========== 验证输出图层 ==========
    print("\n" + "=" * 80)
    print("🔍 验证输出图层")
    print("=" * 80)
    
    all_valid = True
    
    # 验证堤段图层（必须包含岸别字段）
    print(f"\n  🔍 验证输出图层字段...")
    is_valid, missing = validate_output_fields(merged_sections, OUTPUT_DIKE_SECTIONS, [DIKE_BANK_FIELD])
    if is_valid:
        print(f"  ✅ {OUTPUT_DIKE_SECTIONS}: 字段验证通过")
    else:
        print(f"  ❌ {OUTPUT_DIKE_SECTIONS}: 字段验证失败")
        all_valid = False
    
    if all_valid:
        print(f"\n  ✅ 所有输出图层验证通过！")
    else:
        print(f"\n  ⚠️  输出图层验证失败，请检查")
    
    # ========== 保存图层并重新加载 ==========
    print("\n" + "=" * 80)
    print("💾 保存图层到文件并重新加载")
    print("=" * 80)
    if cut_lines_left and cut_lines_left.isValid():
        cut_lines_left = save_and_reload_layer(cut_lines_left)
    if cut_lines_right and cut_lines_right.isValid():
        cut_lines_right = save_and_reload_layer(cut_lines_right)
    if merged_sections and merged_sections.isValid():
        merged_sections = save_and_reload_layer(merged_sections)
    
    # ========== 输出总结 ==========
    print("\n" + "=" * 80)
    print("✅ 脚本执行完成！")
    print("=" * 80)
    print(f"⏰ 完成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n📊 生成结果:")
    
    if cut_lines_left:
        print(f"\n  🔵 左岸切割线: {OUTPUT_CUT_LINES_LEFT}")
        print(f"     - 线数量: {cut_lines_left.featureCount()}")
        print(f"     - 图层状态: ✅ 已添加到项目")
    
    if cut_lines_right:
        print(f"\n  🔵 右岸切割线: {OUTPUT_CUT_LINES_RIGHT}")
        print(f"     - 线数量: {cut_lines_right.featureCount()}")
        print(f"     - 图层状态: ✅ 已添加到项目")
    
    print(f"\n  🟢 堤段图层: {OUTPUT_DIKE_SECTIONS} ⭐")
    print(f"     - 总堤段数: {merged_sections.featureCount()}")
    if sections_left:
        print(f"     - 左岸堤段: {sections_left.featureCount()} 条")
    if sections_right:
        print(f"     - 右岸堤段: {sections_right.featureCount()} 条")
    if lengths:
        print(f"     - 平均长度: {sum(lengths)/len(lengths):.2f} 米")
    # 获取字段列表
    field_names = [field.name() for field in merged_sections.fields()]
    print(f"     - 继承字段: {len(field_names)} 个原堤防字段（包含{DIKE_BANK_FIELD}岸别）")
    print(f"     - 图层状态: ✅ 已添加到项目")
    
    print(f"\n💡 使用提示:")
    print(f"   1. 左右岸已自动分别处理，避免切割线交叉干扰")
    print(f"   2. 切割线已自动延长{EXTEND_END}米（堤防端），确保能切到堤防")
    print(f"   3. 可以通过{DIKE_BANK_FIELD}字段筛选左岸(L)或右岸(R)堤段")
    print(f"   4. 如果切割失败，可以调整以下参数:")
    print(f"      - MAX_DISTANCE (当前{MAX_DISTANCE}米): 增大搜索范围")
    print(f"      - EXTEND_END (当前{EXTEND_END}米): 增大延长距离")
    print(f"   5. 下一步: 使用河段中心点赋值高程给堤段")
    print(f"   6. 可右键图层导出为GeoJSON/Shapefile等格式")
    
    print(f"\n📋 后续处理建议:")
    print(f"   - 使用 fill_start_end_attributes.py 赋值堤段的起点/终点高程和里程")
    print(f"   - 通过空间连接将 river_center_points_zya 的高程数据赋给堤段")
    
    # 检查异常情况
    if lengths and max(lengths) > 300:
        print(f"\n⚠️  注意: 存在长度超过300米的堤段")
        print(f"   - 最大长度: {max(lengths):.2f} 米")
        print(f"   - 可能原因: 切割点分布不均匀或切割失败")
        print(f"   - 建议: 检查切割线图层")
    
    print("=" * 80)
    print("🎉 脚本运行成功结束\n")


# ============ 执行 ============

# 直接执行（适用于exec()环境）
try:
    print("\n" + "=" * 80)
    print("🔪 堤防切割脚本开始执行...")
    print("=" * 80)
    main()
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

