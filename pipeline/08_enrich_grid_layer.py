#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
08 Grid图层增强脚本 - 通用版

📌 说明：
   这是一个通用脚本，适用于所有河流（华溪、熟溪、白溪等）
   只需修改脚本顶部的配置参数（图层名称、字段名称）即可使用

功能：
1. 通过空间连接，从乡镇图层添加town字段
2. 通过空间连接，从保护片图层添加polderId字段
3. 自动生成grid_id（网格序号）
4. 自动计算area（面积，单位：平方米）
5. 处理空值（NaN/NULL），确保所有字段都有有效值
6. 验证字段完整性，输出详细统计信息

输入图层（将自动移到input组）:
- grid0 / grid: 基础网格图层
- town: 乡镇图层（需包含NAME或town字段）
- env: 保护片图层（需包含code字段）

输出图层（自动移到process组）:
- grid_enriched: 增强后的网格图层

📊 输出图层 grid_enriched 的字段说明：
   
   ┌──────────────┬──────────────┬────────────────────────────┐
   │ 字段名       │ 类型         │ 说明                        │
   ├──────────────┼──────────────┼────────────────────────────┤
   │ grid_id      │ Integer      │ 网格唯一序号（从1开始）      │
   │ area         │ Double       │ 网格面积（单位：平方米）     │
   │ town         │ String(50)   │ 所属乡镇（从town图层关联）   │
   │ polderId     │ String(50)   │ 所属保护片ID（从env图层关联）│
   │ Bathymetry   │ Double       │ 水深数据（原grid图层字段）   │
   └──────────────┴──────────────┴────────────────────────────┘
   
   注：原grid图层中的其他字段也会被保留

💡 使用方法：
   1. 确保QGIS中已加载grid0、town、env三个图层
   2. 根据实际图层字段，修改配置部分的字段映射
   3. 在QGIS Python控制台运行此脚本
   4. 查看process组中的grid_enriched输出图层

⚙️  配置参数（在脚本中修改）：
   - GRID_LAYER: 网格图层名称
   - TOWN_LAYER: 乡镇图层名称
   - ENV_LAYER: 保护片图层名称
   - TOWN_FIELD: 乡镇图层中的字段名（将映射为town）
   - ENV_FIELD: 保护片图层中的字段名（将映射为polderId）
   - DEFAULT_TOWN: town字段的默认值（空间连接失败时使用）
   - DEFAULT_POLDER: polderId字段的默认值（空间连接失败时使用）

🔍 字段验证：
   脚本会自动检查并报告：
   - 每个字段的有效值数量
   - 使用默认值的数量
   - NULL/空值的数量
   - 如果超过50%使用默认值，会发出警告

📝 示例输出：
   grid_id | area    | town   | polderId | Bathymetry | 
   --------|---------|--------|----------|------------|
   1       | 521.21  | 白鹤乡 | sx0001   | 146.0926   |
   2       | 528.28  | 白鹤乡 | sx0001   | 144.1908   |
   3       | 528.42  | 白鹤乡 | sx0001   | 138.9771   |
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
    print_banner,
    print_step,
    save_and_reload_layer,
    print_success,
    print_error,
    print_warning,
    safe_execute
)

# 导入公共配置
from hydraulic.qgis_config import (
    INPUT_LAYERS,
    OUTPUT_LAYERS,
    DEFAULT_TOWN,
    DEFAULT_POLDER,
    TARGET_CRS,
    FIELD_MAPPING
)

# ============ 配置参数 ============

# 输入图层名称
GRID_LAYER = INPUT_LAYERS['grid']           # 网格图层
TOWN_LAYER = INPUT_LAYERS['town']           # 乡镇图层
ENV_LAYER = INPUT_LAYERS['env']             # 保护片图层

# 字段映射 - 从公共配置读取
TOWN_FIELD = 'NAME'           # 乡镇图层的字段名（映射为town）
ENV_FIELD = 'code'            # 保护片图层的字段名（映射为polderId）

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['grid_enriched']

# ============ 主函数 ============

def enrich_grid_layer():
    """执行Grid图层增强"""
    
    print("\n" + "=" * 80)
    print("🌐 Grid图层增强 - 空间连接添加town和polderId")
    print("=" * 80)
    
    # ========== 1. 加载图层 ==========
    print(f"\n【步骤1】加载输入图层")
    
    # 加载Grid图层
    print(f"  🔍 查找网格图层: {GRID_LAYER}")
    grid_layer = get_layer_by_name(GRID_LAYER)
    
    if not grid_layer:
        print(f"  ❌ 错误: 找不到图层 '{GRID_LAYER}'")
        return None
    
    print(f"  ✅ 网格图层: {grid_layer.featureCount()} 个网格")
    print(f"     - 坐标系: {grid_layer.crs().authid()}")
    print(f"     - 字段列表: {[f.name() for f in grid_layer.fields()]}")
    
    # 将grid移动到input组
    move_layer_to_group(grid_layer, "input")
    print(f"     📁 已移动到 'input' 组")
    
    # 加载Town图层
    print(f"\n  🔍 查找乡镇图层: {TOWN_LAYER}")
    town_layer = get_layer_by_name(TOWN_LAYER)
    
    if not town_layer:
        print(f"  ❌ 错误: 找不到图层 '{TOWN_LAYER}'")
        return None
    
    print(f"  ✅ 乡镇图层: {town_layer.featureCount()} 个乡镇")
    print(f"     - 字段列表: {[f.name() for f in town_layer.fields()]}")
    
    # 检查TOWN_FIELD是否存在
    town_fields = [f.name() for f in town_layer.fields()]
    if TOWN_FIELD not in town_fields:
        print(f"  ⚠️  警告: 乡镇图层中找不到字段 '{TOWN_FIELD}'")
        print(f"     可用字段: {town_fields}")
        print(f"     请修改脚本中的TOWN_FIELD配置")
        return None
    
    # 显示示例数据
    sample_feat = next(town_layer.getFeatures())
    print(f"     - 示例{TOWN_FIELD}值: '{sample_feat[TOWN_FIELD]}'")
    
    # 将town移动到input组
    move_layer_to_group(town_layer, "input")
    print(f"     📁 已移动到 'input' 组")
    
    # 加载Env图层
    print(f"\n  🔍 查找保护片图层: {ENV_LAYER}")
    env_layer = get_layer_by_name(ENV_LAYER)
    
    if not env_layer:
        print(f"  ❌ 错误: 找不到图层 '{ENV_LAYER}'")
        return None
    
    print(f"  ✅ 保护片图层: {env_layer.featureCount()} 个保护片")
    print(f"     - 字段列表: {[f.name() for f in env_layer.fields()]}")
    
    # 检查ENV_FIELD是否存在
    env_fields = [f.name() for f in env_layer.fields()]
    if ENV_FIELD not in env_fields:
        print(f"  ⚠️  警告: 保护片图层中找不到字段 '{ENV_FIELD}'")
        print(f"     可用字段: {env_fields}")
        print(f"     请修改脚本中的ENV_FIELD配置")
        return None
    
    # 显示示例数据
    sample_feat = next(env_layer.getFeatures())
    print(f"     - 示例{ENV_FIELD}值: '{sample_feat[ENV_FIELD]}'")
    
    # 将env移动到input组
    move_layer_to_group(env_layer, "input")
    print(f"     📁 已移动到 'input' 组")
    
    # ========== 2. 修复几何 ==========
    print_step(2, "修复无效几何")
    grid_layer = fix_geometries(grid_layer, "网格")
    
    # ========== 3. 空间连接 - 添加town ==========
    print(f"\n【步骤3】空间连接 - 添加town字段")
    print(f"  🔄 Join Grid × Town...")
    
    join_town_result = processing.run("native:joinattributesbylocation", {
        'INPUT': grid_layer,
        'JOIN': town_layer,
        'PREDICATE': [0],  # 0 = intersects
        'JOIN_FIELDS': [TOWN_FIELD],
        'METHOD': 1,  # 只取第一个匹配的记录，避免一对多重复
        'DISCARD_NONMATCHING': False,
        'PREFIX': '',
        'OUTPUT': 'memory:'
    })
    
    grid_with_town = join_town_result['OUTPUT']
    print(f"  ✅ 连接完成")
    
    # 检查连接后的字段
    print(f"\n  🔍 检查town连接结果:")
    print(f"     - 输出要素数: {grid_with_town.featureCount()}")
    print(f"     - 字段列表: {[f.name() for f in grid_with_town.fields()]}")
    
    # 检查town字段的值
    town_values = []
    for feat in grid_with_town.getFeatures():
        if TOWN_FIELD in [f.name() for f in grid_with_town.fields()]:
            town_values.append(feat[TOWN_FIELD])
    
    valid_count = sum(1 for v in town_values if v is not None and str(v).strip() != '')
    print(f"     - {TOWN_FIELD}字段有效值: {valid_count}/{len(town_values)}")
    if valid_count > 0:
        print(f"     - 示例值: {[v for v in town_values if v is not None and str(v).strip() != ''][:3]}")
    
    # ========== 4. 空间连接 - 添加polderId ==========
    print(f"\n【步骤4】空间连接 - 添加polderId字段")
    print(f"  🔄 Join Grid × Env...")
    
    join_env_result = processing.run("native:joinattributesbylocation", {
        'INPUT': grid_with_town,
        'JOIN': env_layer,
        'PREDICATE': [0],  # 0 = intersects
        'JOIN_FIELDS': [ENV_FIELD],
        'METHOD': 1,  # 只取第一个匹配的记录，避免一对多重复
        'DISCARD_NONMATCHING': False,
        'PREFIX': '',
        'OUTPUT': 'memory:'
    })
    
    grid_with_all = join_env_result['OUTPUT']
    print(f"  ✅ 连接完成")
    
    # 检查连接后的字段
    print(f"\n  🔍 检查polderId连接结果:")
    print(f"     - 输出要素数: {grid_with_all.featureCount()}")
    print(f"     - 字段列表: {[f.name() for f in grid_with_all.fields()]}")
    
    # 检查polderId字段的值
    polder_values = []
    for feat in grid_with_all.getFeatures():
        if ENV_FIELD in [f.name() for f in grid_with_all.fields()]:
            polder_values.append(feat[ENV_FIELD])
    
    valid_count = sum(1 for v in polder_values if v is not None and str(v).strip() != '')
    print(f"     - {ENV_FIELD}字段有效值: {valid_count}/{len(polder_values)}")
    if valid_count > 0:
        print(f"     - 示例值: {[v for v in polder_values if v is not None and str(v).strip() != ''][:3]}")
    
    # ========== 5. 创建输出图层 ==========
    print(f"\n【步骤5】创建输出图层")
    
    # 获取原始grid图层的字段名（用于后续过滤）
    original_grid_fields = [f.name() for f in grid_layer.fields()]
    print(f"  📋 原grid图层字段: {original_grid_fields}")
    
    geom_type = QgsWkbTypes.displayString(grid_with_all.wkbType())
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={grid_with_all.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    output_provider = output_layer.dataProvider()
    
    # 添加核心字段
    output_provider.addAttributes([
        QgsField('grid_id', QVariant.Int),
        QgsField('area', QVariant.Double),
        QgsField('town', QVariant.String, len=50),
        QgsField('polderId', QVariant.String, len=50)
    ])
    
    # 复制原始grid图层的字段（排除空间连接添加的字段）
    excluded_fields = set()  # 记录被排除的字段
    copied_fields = []  # 记录被复制的字段
    
    # 只复制原grid图层中的字段，排除从town和env连接来的字段
    for field in grid_with_all.fields():
        field_name = field.name()
        # 只保留原grid图层的字段，排除核心字段和连接字段
        if field_name in original_grid_fields and field_name not in ['grid_id', 'area', 'town', 'polderId', TOWN_FIELD, ENV_FIELD]:
            output_provider.addAttributes([field])
            copied_fields.append(field_name)
        elif field_name in [TOWN_FIELD, ENV_FIELD]:
            excluded_fields.add(field_name)
    
    output_layer.updateFields()
    
    print(f"  ✅ 输出图层创建完成")
    print(f"  📋 输出字段（共{len(output_layer.fields())}个）:")
    print(f"     - 核心字段(4): grid_id, area, town, polderId")
    if copied_fields:
        print(f"     - 原grid字段({len(copied_fields)}): {', '.join(copied_fields)}")
    if excluded_fields:
        print(f"  🚫 已排除连接字段: {', '.join(excluded_fields)}")
    
    # ========== 6. 填充数据 ==========
    print(f"\n【步骤6】填充数据")
    
    # 检查源图层可用字段
    available_fields = [f.name() for f in grid_with_all.fields()]
    print(f"  📋 源图层可用字段: {available_fields}")
    
    has_town_field = TOWN_FIELD in available_fields
    has_env_field = ENV_FIELD in available_fields
    
    print(f"  🔍 字段检查:")
    print(f"     - {TOWN_FIELD}字段存在: {'✅' if has_town_field else '❌'}")
    print(f"     - {ENV_FIELD}字段存在: {'✅' if has_env_field else '❌'}")
    
    output_features = []
    town_fill_count = 0
    polder_fill_count = 0
    town_default_count = 0
    polder_default_count = 0
    
    for idx, feat in enumerate(grid_with_all.getFeatures(), 1):
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(feat.geometry())
        
        # 生成grid_id
        new_feat['grid_id'] = idx
        
        # 计算面积
        geom = feat.geometry()
        if geom and not geom.isNull():
            area = geom.area()
        else:
            area = 0.0
        new_feat['area'] = round(area, 2)
        
        # town字段
        town_value = None
        if has_town_field:
            town_value = feat[TOWN_FIELD]
        
        if town_value is None or (isinstance(town_value, str) and town_value.strip() == ''):
            town_value = DEFAULT_TOWN
            town_default_count += 1
        else:
            town_fill_count += 1
            
        new_feat['town'] = town_value
        
        # polderId字段
        polder_value = None
        if has_env_field:
            polder_value = feat[ENV_FIELD]
        
        if polder_value is None or (isinstance(polder_value, str) and polder_value.strip() == ''):
            polder_value = DEFAULT_POLDER
            polder_default_count += 1
        else:
            polder_fill_count += 1
            
        new_feat['polderId'] = polder_value
        
        # 复制原grid图层的其他字段（排除连接字段）
        for field in grid_with_all.fields():
            field_name = field.name()
            # 只复制原grid图层的字段，排除TOWN_FIELD和ENV_FIELD
            if (field_name in original_grid_fields and 
                field_name not in ['grid_id', 'area', 'town', 'polderId', TOWN_FIELD, ENV_FIELD] and
                field_name in new_feat.fields().names()):
                new_feat[field_name] = feat[field_name]
        
        output_features.append(new_feat)
    
    output_provider.addFeatures(output_features)
    
    print(f"\n  ✅ 数据填充完成: {len(output_features)} 个网格")
    print(f"  📊 town字段统计:")
    print(f"     - 成功关联: {town_fill_count} 个")
    print(f"     - 使用默认值: {town_default_count} 个")
    print(f"  📊 polderId字段统计:")
    print(f"     - 成功关联: {polder_fill_count} 个")
    print(f"     - 使用默认值: {polder_default_count} 个")
    
    # ========== 7. 添加到项目（process组） ==========
    project = QgsProject.instance()
    
    # 查找或创建 process 组
    process_group = ensure_group_exists("process")
    
    # 移除旧图层
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    if existing_layers:
        project.removeMapLayer(existing_layers[0])
    
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    print(f"\n  🗺️  图层已添加到QGIS项目: {OUTPUT_LAYER_NAME} (process组)")
    
    # ========== 7.5. 最终验证 ==========
    print(f"\n【验证】检查输出图层字段值")
    
    # 验证字段列表
    output_field_names = [f.name() for f in output_layer.fields()]
    print(f"  📋 最终输出字段列表: {output_field_names}")
    
    # 确认连接字段已被排除
    if TOWN_FIELD in output_field_names:
        print(f"  ⚠️  警告: 发现连接字段 '{TOWN_FIELD}' 未被排除！")
    else:
        print(f"  ✅ 连接字段 '{TOWN_FIELD}' 已成功排除")
        
    if ENV_FIELD in output_field_names:
        print(f"  ⚠️  警告: 发现连接字段 '{ENV_FIELD}' 未被排除！")
    else:
        print(f"  ✅ 连接字段 '{ENV_FIELD}' 已成功排除")
    
    # 检查输出图层的前5个要素
    print(f"\n  🔍 抽样检查前5个网格的字段值:")
    for idx, feat in enumerate(output_layer.getFeatures(), 1):
        if idx > 5:
            break
        print(f"\n     网格 #{feat['grid_id']}:")
        print(f"       - town: '{feat['town']}'")
        print(f"       - polderId: '{feat['polderId']}'")
        print(f"       - area: {feat['area']:.2f} m²")
    
    # 统计空值
    null_town = 0
    null_polder = 0
    default_town = 0
    default_polder = 0
    
    for feat in output_layer.getFeatures():
        town_val = feat['town']
        polder_val = feat['polderId']
        
        if town_val is None or town_val == '':
            null_town += 1
        elif town_val == DEFAULT_TOWN:
            default_town += 1
            
        if polder_val is None or polder_val == '':
            null_polder += 1
        elif polder_val == DEFAULT_POLDER:
            default_polder += 1
    
    print(f"\n  📊 字段完整性检查:")
    print(f"     town字段:")
    print(f"       - NULL/空值: {null_town} 个")
    print(f"       - 默认值({DEFAULT_TOWN}): {default_town} 个")
    print(f"       - 有效值: {output_layer.featureCount() - null_town - default_town} 个")
    print(f"     polderId字段:")
    print(f"       - NULL/空值: {null_polder} 个")
    print(f"       - 默认值({DEFAULT_POLDER}): {default_polder} 个")
    print(f"       - 有效值: {output_layer.featureCount() - null_polder - default_polder} 个")
    
    # 警告信息
    if null_town > 0:
        print(f"\n  ⚠️  警告: 发现 {null_town} 个网格的town字段为空！")
    if null_polder > 0:
        print(f"  ⚠️  警告: 发现 {null_polder} 个网格的polderId字段为空！")
    if default_town > output_layer.featureCount() * 0.5:
        print(f"  ⚠️  警告: 超过50%的网格使用town默认值，可能空间连接未成功！")
    if default_polder > output_layer.featureCount() * 0.5:
        print(f"  ⚠️  警告: 超过50%的网格使用polderId默认值，可能空间连接未成功！")
    
    # ========== 8. 输出统计 ==========
    print("\n" + "=" * 80)
    print("✅ Grid图层增强完成！")
    print("=" * 80)
    
    print(f"\n📊 统计信息:")
    print(f"  • 总网格数: {output_layer.featureCount()}")
    
    # 统计town
    towns = [feat['town'] for feat in output_layer.getFeatures() if feat['town'] is not None]
    unique_towns = set(towns)
    print(f"  • 涉及乡镇: {len(unique_towns)} 个")
    print(f"     {', '.join(list(unique_towns)[:5])}{'...' if len(unique_towns) > 5 else ''}")
    
    # 统计polder
    polders = [feat['polderId'] for feat in output_layer.getFeatures() if feat['polderId'] is not None and feat['polderId'] != DEFAULT_POLDER]
    unique_polders = set(polders)
    print(f"  • 涉及保护片: {len(unique_polders)} 个")
    
    # 统计面积
    areas = [feat['area'] for feat in output_layer.getFeatures() if feat['area'] is not None]
    if areas:
        print(f"\n  • 网格面积范围: {min(areas):.2f} ~ {max(areas):.2f} m²")
        print(f"  • 平均网格面积: {sum(areas)/len(areas):.2f} m²")
        print(f"  • 总面积: {sum(areas):.2f} m² ({sum(areas)/1000000:.2f} km²)")
    
    print(f"\n📋 输出字段说明:")
    print(f"   核心字段(4个):")
    print(f"     • grid_id: 网格序号")
    print(f"     • area: 面积(m²)")
    print(f"     • town: 乡镇名称")
    print(f"     • polderId: 保护片ID")
    if copied_fields:
        print(f"   原grid字段({len(copied_fields)}个): {', '.join(copied_fields)}")
    
    print(f"\n💡 使用提示:")
    print(f"   - 输出图层: {OUTPUT_LAYER_NAME}")
    print(f"   - 图层位置: process组")
    print(f"   - 已排除连接字段: {TOWN_FIELD}, {ENV_FIELD}")
    print(f"   - 下一步: 使用此图层进行house/road/vegetation的空间相交")
    
    # 保存图层到文件
    print("\n" + "=" * 80)
    print("💾 保存图层到文件")
    print("=" * 80)
    
    # 保存图层并重新加载
    print(f"\n💾 保存图层到文件并重新加载")
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    print("=" * 80)
    print("🎉 脚本运行成功结束\n")
    
    return output_layer


# ============ 执行 ============

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("🌐 Grid图层增强脚本开始执行...")
        print("=" * 80)
        result = enrich_grid_layer()
        
        if result:
            print("\n✅ 脚本执行成功！请查看新生成的图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ Grid图层增强完成！\n\n"
                    msg += f"📊 输出图层: {OUTPUT_LAYER_NAME}\n"
                    msg += f"📁 位置: process组\n\n"
                    msg += f"生成的网格数: {result.featureCount()} 个\n\n"
                    msg += "已添加字段:\n"
                    msg += "  • grid_id (网格序号)\n"
                    msg += "  • area (面积)\n"
                    msg += "  • town (乡镇)\n"
                    msg += "  • polderId (保护片ID)"
                    
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
