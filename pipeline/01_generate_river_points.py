#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01 河段中心点和切割点生成脚本
根据河流中心线生成等间隔的中心点和切割点

功能:
1. 自动检测坐标系统，地理坐标系会自动重投影为EPSG:4549
2. 生成河段中心点 (LC = 0, 100, 200...)
3. 生成河段切割点 (LC = 50, 150, 250...)
4. 输出2个QGIS内存图层（中心点、切割点）

输入图层:
  - hdzxx: 河流中心线
    必需字段: 无特殊要求
    说明: 任意线要素图层均可

输出图层:
  - river_center_points: 河段中心点
    继承字段: hdzxx 全部字段
    新增字段: LC
      · LC: 里程 (m)，从河流起点计算 (0, 100, 200...)

  - river_cut_points: 河段切割点
    继承字段: hdzxx 全部字段
    新增字段: LC
      · LC: 里程 (m)，偏移50m (50, 150, 250...)

工作流程:
- 步骤1: 加载河流中心线图层，检测并重投影坐标系
- 步骤2: 沿线生成河段中心点（间隔100m，继承原图层属性+LC）
- 步骤3: 沿线生成河段切割点（间隔100m，偏移50m）
- 步骤4: 创建内存图层并添加到QGIS项目（2个图层）

注意: 断面LC赋值已移至独立脚本 01.5_assign_lc_to_cross_sections.py
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path

def _setup_paths():
    """设置模块搜索路径，兼容QGIS控制台和命令行执行"""
    # 已知的脚本目录路径
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

    # 添加路径到 sys.path
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
    QgsProject, QgsVectorLayer, QgsFeature, QgsField
)
from qgis.PyQt.QtCore import QVariant

# 导入工具函数库
from qgis_util import (
    validate_output_fields,
    move_layer_to_group,
    ensure_group_exists,
    reproject_layer_if_needed,
    save_and_reload_layer,
    get_process_dir
)

# 导入公共配置
from hydraulic.qgis_config import (
    TARGET_CRS,
    RIVER_POINT_CONFIG,
    INPUT_LAYERS,
    OUTPUT_LAYERS
)

# ============ 配置参数 ============

# 输入河流中心线图层名称
INPUT_LAYER_NAME = INPUT_LAYERS['river_center']  # 可修改为实际图层名称

# 输出图层名称
OUTPUT_CENTER_LAYER_NAME = OUTPUT_LAYERS['river_center_points']
OUTPUT_CUT_LAYER_NAME = OUTPUT_LAYERS['river_cut_points']

# 间隔距离(米) - 从公共配置读取
INTERVAL = RIVER_POINT_CONFIG['interval']  # 中心点间隔
OFFSET = RIVER_POINT_CONFIG['offset']      # 切割点偏移量

# ============ 主函数 ============

def generate_points_along_line(layer, interval, offset=0):
    """
    沿线生成等间隔点，继承原图层属性并添加LC字段
    
    参数:
        layer: 输入线图层
        interval: 间隔距离(米)
        offset: 起始偏移量(米)
    
    返回:
        (点要素列表, 原图层字段列表)
    """
    points = []
    feature_count = 0
    
    # 获取原图层的字段
    source_fields = layer.fields()
    
    for feature in layer.getFeatures():
        feature_count += 1
        geom = feature.geometry()
        line_length = geom.length()
        
        print(f"     处理要素 {feature_count}: 长度={line_length:.2f}m", end='')
        
        # 从offset开始，按interval间隔生成点
        distance = offset
        lc = int(offset)  # LC从offset开始
        point_count = 0
        
        while distance <= line_length:
            point = geom.interpolate(distance)
            if point:
                # 创建点要素，继承原要素的所有属性
                point_feature = QgsFeature()
                point_feature.setGeometry(point)
                
                # 复制原要素的所有属性，然后添加LC
                attrs = feature.attributes() + [lc]
                point_feature.setAttributes(attrs)
                
                points.append(point_feature)
                point_count += 1
                
            distance += interval
            lc += interval
        
        print(f" → 生成 {point_count} 个点")
    
    return points, source_fields


def create_point_layer(points, layer_name, source_fields, crs='EPSG:4549'):
    """
    创建点图层并添加到QGIS项目
    
    参数:
        points: 点要素列表
        layer_name: 图层名称
        source_fields: 原图层字段列表
        crs: 坐标系统
    
    返回:
        内存图层对象
    """
    print(f"     🔧 创建图层: {layer_name}")
    
    # 创建内存图层
    point_layer = QgsVectorLayer(f'Point?crs={crs}', layer_name, 'memory')
    print(f"     📋 图层有效性: {point_layer.isValid()}")
    
    provider = point_layer.dataProvider()
    
    # 添加原图层的所有字段
    fields_to_add = []
    for field in source_fields:
        fields_to_add.append(field)
    
    # 添加LC字段
    fields_to_add.append(QgsField('LC', QVariant.Int))
    
    print(f"     📝 继承原图层 {len(source_fields)} 个字段 + LC")
    
    provider.addAttributes(fields_to_add)
    point_layer.updateFields()
    
    # 添加要素
    print(f"     ➕ 添加 {len(points)} 个点要素...")
    provider.addFeatures(points)
    point_layer.updateExtents()
    print(f"     ✅ 要素添加完成，实际数量: {point_layer.featureCount()}")
    
    # 添加到QGIS项目（添加到process组）
    project = QgsProject.instance()
    
    # 查找或创建 process 组
    process_group = ensure_group_exists("process")
    
    project.addMapLayer(point_layer, False)
    process_group.addLayer(point_layer)
    print(f"     🗺️  已添加到QGIS项目 (process组)")
    
    return point_layer


def main():
    """主流程"""
    print("\n" + "=" * 80)
    print("🚀 河段中心点和切割点生成器 - 开始执行")
    print("=" * 80)
    print(f"⏰ 脚本启动时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 初始化变量
    is_geographic = False
    center_points = []
    cut_points = []
    center_layer = None
    cut_layer = None
    
    # 1. 获取输入图层
    print(f"\n【步骤1】加载输入图层")
    print(f"  🔍 查找图层: {INPUT_LAYER_NAME}")
    
    # 列出所有可用图层
    all_layers = QgsProject.instance().mapLayers()
    print(f"  📋 项目中共有 {len(all_layers)} 个图层")
    
    layer = QgsProject.instance().mapLayersByName(INPUT_LAYER_NAME)
    
    if not layer:
        print(f"\n  ❌ 错误: 找不到图层 '{INPUT_LAYER_NAME}'")
        print(f"  💡 请确认图层名称是否正确，大小写敏感")
        return
    
    layer = layer[0]
    print(f"\n  ✅ 图层加载成功")
    print(f"     - 图层名称: {layer.name()}")
    print(f"     - 要素数量: {layer.featureCount()}")
    
    # 将输入图层移动到 input 组
    move_layer_to_group(layer, "input")
    print(f"     📁 已移动到 'input' 组")
    
    crs = layer.crs()
    crs_id = crs.authid()
    is_geographic = crs.isGeographic()
    print(f"     - 坐标系统: {crs_id}")
    print(f"     - 坐标类型: {'地理坐标系(度)' if is_geographic else '投影坐标系(米)'}")
    print(f"     - 几何类型: {layer.geometryType()}")
    
    # 如果是地理坐标系，自动重投影
    if is_geographic:
        total_length = sum(f.geometry().length() for f in layer.getFeatures())
        print(f"     - 原始长度: {total_length:.6f} 度")
        print(f"\n  🔄 检测到地理坐标系，自动重投影为{TARGET_CRS}...")
        
        layer = reproject_layer_if_needed(layer, TARGET_CRS, "河流中心线")
        
        total_length = sum(f.geometry().length() for f in layer.getFeatures())
        print(f"     - 新总长度: {total_length:.2f} 米 ({total_length/1000:.2f} 公里)")
    else:
        total_length = sum(f.geometry().length() for f in layer.getFeatures())
        print(f"     - 总长度: {total_length:.2f} 米 ({total_length/1000:.2f} 公里)")
    
    # 2. 生成河段中心点 (LC = 0, 100, 200, 300...)
    print(f"\n【步骤2】生成河段中心点")
    print(f"  ⚙️  参数: 间隔={INTERVAL}m, 偏移=0m")
    print(f"  🔄 正在生成点...")
    
    center_points, source_fields = generate_points_along_line(layer, INTERVAL, offset=0)
    
    print(f"  ✅ 生成完成: {len(center_points)} 个中心点")
    if center_points:
        # LC在属性列表的最后一个位置
        print(f"     - 第1个点 LC: {center_points[0].attributes()[-1]}")
        print(f"     - 第2个点 LC: {center_points[1].attributes()[-1] if len(center_points) > 1 else 'N/A'}")
        print(f"     - 最后1个点 LC: {center_points[-1].attributes()[-1]}")
    
    # 3. 生成河段切割点 (LC = 50, 150, 250, 350...)
    print(f"\n【步骤3】生成河段切割点")
    print(f"  ⚙️  参数: 间隔={INTERVAL}m, 偏移={OFFSET}m")
    print(f"  🔄 正在生成点...")
    
    cut_points, _ = generate_points_along_line(layer, INTERVAL, offset=OFFSET)
    
    print(f"  ✅ 生成完成: {len(cut_points)} 个切割点")
    if cut_points:
        # LC在属性列表的最后一个位置
        print(f"     - 第1个点 LC: {cut_points[0].attributes()[-1]}")
        print(f"     - 第2个点 LC: {cut_points[1].attributes()[-1] if len(cut_points) > 1 else 'N/A'}")
        print(f"     - 最后1个点 LC: {cut_points[-1].attributes()[-1]}")
    
    # 4. 添加图层到QGIS项目
    print(f"\n【步骤4】添加图层到QGIS项目")
    print(f"  🔄 创建内存图层...")
    
    # 使用处理后图层的坐标系统
    output_crs = layer.crs().authid()
    
    # 创建河段中心点图层（带LC）
    center_layer = create_point_layer(center_points, OUTPUT_CENTER_LAYER_NAME, source_fields, output_crs)
    
    # 创建河段切割点图层（带LC）
    cut_layer = create_point_layer(cut_points, OUTPUT_CUT_LAYER_NAME, source_fields, output_crs)
    
    # 5. 验证输出图层
    print("\n【步骤5】验证输出图层")
    print(f"\n  🔍 验证输出图层字段完整性...")
    
    all_valid = True
    
    # 验证河段中心点图层
    is_valid, missing = validate_output_fields(center_layer, OUTPUT_CENTER_LAYER_NAME, ['LC'])
    if is_valid:
        print(f"  ✅ {OUTPUT_CENTER_LAYER_NAME}: 字段验证通过")
    else:
        print(f"  ❌ {OUTPUT_CENTER_LAYER_NAME}: 字段验证失败")
        all_valid = False
    
    # 验证河段切割点图层
    is_valid, missing = validate_output_fields(cut_layer, OUTPUT_CUT_LAYER_NAME, ['LC'])
    if is_valid:
        print(f"  ✅ {OUTPUT_CUT_LAYER_NAME}: 字段验证通过")
    else:
        print(f"  ❌ {OUTPUT_CUT_LAYER_NAME}: 字段验证失败")
        all_valid = False
    
    if all_valid:
        print(f"\n  ✅ 所有输出图层验证通过！")
    else:
        print(f"\n  ⚠️  部分输出图层验证失败，请检查")
    
    # 6. 输出验证信息
    print("\n" + "=" * 80)
    print("✅ 脚本执行完成！")
    # 5. 保存图层并重新加载（持久化）
    print(f"\n【步骤5】保存图层到文件并重新加载")
    if center_layer and center_layer.isValid():
        center_layer = save_and_reload_layer(center_layer)
    if cut_layer and cut_layer.isValid():
        cut_layer = save_and_reload_layer(cut_layer)
    
    print("=" * 80)
    print(f"⏰ 完成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n📊 生成结果:")
    print(f"\n  🔵 河段中心点图层: {OUTPUT_CENTER_LAYER_NAME}")
    print(f"     - 点数量: {len(center_points)}")
    if center_points:
        first_lc = center_points[0].attributes()[-1]
        last_lc = center_points[-1].attributes()[-1]
        print(f"     - LC范围: {first_lc} ~ {last_lc} 米")
        print(f"     - 包含字段: 原图层字段 + LC")
    else:
        print(f"     - LC范围: (无点)")
    print(f"     - 图层状态: {'✅ 已添加到项目' if center_layer and center_layer.isValid() else '❌ 无效'}")
    
    print(f"\n  🟢 河段切割点图层: {OUTPUT_CUT_LAYER_NAME}")
    print(f"     - 点数量: {len(cut_points)}")
    if cut_points:
        first_lc = cut_points[0].attributes()[-1]
        last_lc = cut_points[-1].attributes()[-1]
        print(f"     - LC范围: {first_lc} ~ {last_lc} 米")
        print(f"     - 包含字段: 原图层字段 + LC")
    else:
        print(f"     - LC范围: (无点)")
    print(f"     - 图层状态: {'✅ 已添加到项目' if cut_layer and cut_layer.isValid() else '❌ 无效'}")
    
    print(f"\n  📐 点位示意图:")
    print(f"     ├──50──┼─100─┼──150──┼─200─┼──250──┼─300─┤")
    print(f"     切割点  中心点  切割点  中心点  切割点  中心点")
    
    print(f"\n💡 使用提示:")
    print(f"   - 内存图层已添加到QGIS图层面板 (process组)")
    print(f"   - 可右键图层导出为GeoJSON/Shapefile等格式")
    print(f"   - 中心点用于赋值高程和后续计算")
    print(f"   - 切割点用于切割堤防线，生成堤段")
    
    print(f"\n📋 下一步:")
    print(f"   1. 运行 01.5_assign_lc_to_cross_sections.py 给断面赋值LC")
    print(f"   2. 运行 02_cut_dike_sections.py 切割堤防")
    print(f"   3. 运行 03_assign_elevation_to_dike.py 赋值高程")
    
    # 检查并提示数据问题
    if len(center_points) < 10:
        print(f"\n⚠️  注意事项:")
        print(f"   - 生成的点数量较少({len(center_points)}个)，请检查:")
        print(f"     • 是否选择了正确的河流中心线图层")
        print(f"     • 河流长度是否足够(至少1000米)")
        print(f"     • 图层要素是否完整")
    
    print("=" * 80)
    print("🎉 脚本运行成功结束\n")


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🚀 脚本开始执行...")
    print("=" * 80)
    
    try:
        main()
        
        # 保存项目
        print("\n" + "=" * 80)
        print("💾 保存项目...")
        project = QgsProject.instance()
        if project.write():
            print("✅ 项目保存成功")
        else:
            print("⚠️ 项目保存失败")
        print("=" * 80)
        
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
