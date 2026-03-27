#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06 河流名称修正脚本

功能：
修正 river_name 和 river_code 不对齐的问题

问题示例：
- river_code=GZX, river_name=熟溪 ❌（错误）
- river_code=GZX, river_name=古竹溪 ✅（正确）

河流代码映射关系：
- HX  → 华溪
- SX  → 熟溪
- WX  → 乌溪  
- GZX → 古竹溪
- BX  → 白溪

输入图层:
  - dd: 堤段（标准24字段）
    必需字段: river_code, river_name
      · river_code: 河流编码 (如 HX, SX, GZX)
      · river_name: 河流名称（可能错误，需修正）

输出图层:
  - dd_fix: 堤段（修正河流名称）
    继承字段: dd 全部字段
    修正字段: river_name
      · river_name: 根据 river_code 自动修正

使用说明：
1. 确保项目中存在 dd 图层
2. 运行脚本，自动根据 river_code 修正 river_name
3. 生成新的 dd_fix 图层（添加到 final 组）
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
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

# 导入公共配置
from hydraulic.qgis_config import (
    OUTPUT_LAYERS,
    RIVER_CODE_MAPPING  # 河流代码到名称的映射
)

# 导入保存函数
from qgis_util import save_and_reload_layer

# ============ 配置区域 ============

# 输入图层名称
INPUT_LAYER_NAME = OUTPUT_LAYERS['dd']

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['dd_fix']

# 河流代码到中文名称的映射（从公共配置读取）
RIVER_CODE_TO_NAME = RIVER_CODE_MAPPING

# ============ 辅助函数 ============

def ensure_group_exists(group_name):
    """确保组存在，如果不存在则创建"""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = root.findGroup(group_name)
    if not group:
        group = root.insertGroup(0, group_name)
    return group


def get_layer_by_name(layer_name):
    """根据名称获取图层"""
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        print(f"❌ 错误：找不到图层 '{layer_name}'")
        return None
    return layers[0]


def fix_river_name():
    """修正河流名称"""
    
    print("=" * 80)
    print("🔧 河流名称修正脚本")
    print("=" * 80)
    
    # 1. 获取输入图层
    print(f"\n【步骤1】加载输入图层")
    input_layer = get_layer_by_name(INPUT_LAYER_NAME)
    if not input_layer:
        return None
    
    print(f"  ✅ 输入图层：{input_layer.name()}")
    print(f"  ✅ 要素数量：{input_layer.featureCount()}")
    print(f"  ✅ 坐标系：{input_layer.crs().authid()}")
    
    # 检查必需字段
    field_names = [f.name() for f in input_layer.fields()]
    if 'river_code' not in field_names:
        print(f"  ❌ 错误：图层缺少 river_code 字段")
        return None
    if 'river_name' not in field_names:
        print(f"  ❌ 错误：图层缺少 river_name 字段")
        return None
    
    print(f"  ✅ 必需字段检查通过（river_code, river_name）")
    
    # 2. 创建输出图层（复制所有字段）
    print(f"\n【步骤2】创建输出图层")
    geom_type = QgsWkbTypes.displayString(input_layer.wkbType())
    
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={input_layer.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    
    if not output_layer.isValid():
        print("❌ 错误：无法创建输出图层！")
        return None
    
    # 复制所有字段
    output_provider = output_layer.dataProvider()
    output_provider.addAttributes(input_layer.fields())
    output_layer.updateFields()
    
    print(f"  ✅ 已创建输出图层: {OUTPUT_LAYER_NAME}")
    print(f"  ✅ 已复制 {len(input_layer.fields())} 个字段")
    
    # 3. 统计需要修正的数据
    print(f"\n【步骤3】分析数据")
    
    # 统计 river_code 分布
    river_code_stats = {}
    wrong_mappings = []  # 记录错误的映射
    
    for feat in input_layer.getFeatures():
        river_code = feat['river_code']
        river_name = feat['river_name']
        
        if river_code:
            river_code = str(river_code).strip().upper()
            if river_code not in river_code_stats:
                river_code_stats[river_code] = {
                    'count': 0,
                    'names': {}
                }
            river_code_stats[river_code]['count'] += 1
            
            # 统计该代码对应的名称
            if river_name:
                river_name = str(river_name).strip()
                if river_name not in river_code_stats[river_code]['names']:
                    river_code_stats[river_code]['names'][river_name] = 0
                river_code_stats[river_code]['names'][river_name] += 1
    
    # 显示统计结果
    print(f"\n  📊 river_code 分布统计:")
    for code, stats in sorted(river_code_stats.items()):
        print(f"\n     {code}: {stats['count']} 条")
        for name, count in stats['names'].items():
            expected_name = RIVER_CODE_TO_NAME.get(code, "未知")
            if name != expected_name:
                status = "❌ 错误"
                wrong_mappings.append((code, name, expected_name))
            else:
                status = "✅ 正确"
            print(f"       - {name}: {count} 条 {status}")
            if name != expected_name:
                print(f"         (应该是: {expected_name})")
    
    if wrong_mappings:
        print(f"\n  ⚠️  发现 {len(set(wrong_mappings))} 种错误映射:")
        for code, wrong_name, correct_name in set(wrong_mappings):
            print(f"     - {code}: {wrong_name} → {correct_name}")
    else:
        print(f"\n  ✅ 未发现错误映射")
    
    # 4. 修正数据并复制到输出图层
    print(f"\n【步骤4】修正 river_name 字段")
    print(f"  🔄 处理 {input_layer.featureCount()} 个要素...")
    
    output_features = []
    fixed_count = 0
    unchanged_count = 0
    unknown_code_count = 0
    
    for idx, input_feat in enumerate(input_layer.getFeatures(), 1):
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(input_feat.geometry())
        
        # 复制所有字段
        for field in input_layer.fields():
            field_name = field.name()
            new_feat[field_name] = input_feat[field_name]
        
        # 修正 river_name
        river_code = input_feat['river_code']
        old_river_name = input_feat['river_name']
        
        if river_code:
            river_code = str(river_code).strip().upper()
            
            if river_code in RIVER_CODE_TO_NAME:
                correct_name = RIVER_CODE_TO_NAME[river_code]
                
                # 检查是否需要修正
                if old_river_name != correct_name:
                    new_feat['river_name'] = correct_name
                    fixed_count += 1
                    
                    # 显示前5个修正示例
                    if fixed_count <= 5:
                        print(f"     修正 #{fixed_count}: {river_code}: '{old_river_name}' → '{correct_name}'")
                else:
                    unchanged_count += 1
            else:
                # 未知的 river_code
                unknown_code_count += 1
                if unknown_code_count <= 3:
                    print(f"     ⚠️  未知代码: {river_code} (保持原 river_name: {old_river_name})")
        
        output_features.append(new_feat)
        
        # 显示进度
        if idx % 100 == 0 or idx == input_layer.featureCount():
            print(f"     进度: {idx}/{input_layer.featureCount()}")
    
    output_provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    print(f"  ✅ 已处理 {len(output_features)} 个要素")
    
    # 5. 显示修正统计
    print(f"\n  📊 修正统计:")
    print(f"     ✅ 已修正: {fixed_count} 条")
    print(f"     ✓ 无需修正: {unchanged_count} 条")
    if unknown_code_count > 0:
        print(f"     ⚠️  未知代码: {unknown_code_count} 条（保持原值）")
    
    # 6. 添加到项目（final组）
    print(f"\n【步骤5】添加到QGIS项目")
    
    project = QgsProject.instance()
    
    # 移除旧图层（如果存在）
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    if existing_layers:
        project.removeMapLayer(existing_layers[0])
        print(f"  🗑️  已移除旧图层: {OUTPUT_LAYER_NAME}")
    
    # 查找或创建 final 组
    final_group = ensure_group_exists("final")
    
    # 添加到final组
    project.addMapLayer(output_layer, False)
    final_group.addLayer(output_layer)
    print(f"  ✅ 已添加新图层: {OUTPUT_LAYER_NAME} (final组) ⭐")
    
    # 7. 验证修正结果
    print(f"\n【步骤6】验证修正结果")
    
    # 重新统计修正后的数据
    fixed_river_code_stats = {}
    for feat in output_layer.getFeatures():
        river_code = feat['river_code']
        river_name = feat['river_name']
        
        if river_code:
            river_code = str(river_code).strip().upper()
            if river_code not in fixed_river_code_stats:
                fixed_river_code_stats[river_code] = {
                    'count': 0,
                    'names': set()
                }
            fixed_river_code_stats[river_code]['count'] += 1
            if river_name:
                fixed_river_code_stats[river_code]['names'].add(str(river_name).strip())
    
    print(f"\n  📊 修正后的 river_code 分布:")
    all_correct = True
    for code, stats in sorted(fixed_river_code_stats.items()):
        expected_name = RIVER_CODE_TO_NAME.get(code, "未知")
        actual_names = list(stats['names'])
        
        if len(actual_names) == 1 and actual_names[0] == expected_name:
            print(f"     ✅ {code}: {stats['count']} 条 → {expected_name}")
        else:
            print(f"     ⚠️  {code}: {stats['count']} 条 → {', '.join(actual_names)}")
            if code in RIVER_CODE_TO_NAME:
                print(f"        (期望: {expected_name})")
                all_correct = False
    
    if all_correct:
        print(f"\n  ✅ 所有 river_code 和 river_name 已正确对齐！")
    else:
        print(f"\n  ⚠️  部分数据仍需手动检查")
    
    # 8. 显示数据示例
    print(f"\n  📊 数据示例（前5条）:")
    print(f"  {'序号':<5} {'river_code':<12} {'river_name':<15} {'polder_id':<12} {'dike_name':<25}")
    print("  " + "-" * 75)
    
    for idx, feat in enumerate(output_layer.getFeatures(), 1):
        if idx <= 5:
            river_code = feat["river_code"] or "-"
            river_name = feat["river_name"] or "-"
            polder_id = feat["polder_id"] or "-"
            dike_name = feat["dike_name"] or "-"
            
            # 截断过长的字段
            dike_name_str = str(dike_name)[:23] + ".." if len(str(dike_name)) > 25 else str(dike_name)
            
            print(f"  {idx:<5} {str(river_code):<12} {str(river_name):<15} {str(polder_id):<12} {dike_name_str:<25}")
    
    if output_layer.featureCount() > 5:
        print("  ...")
    
    # 9. 输出总结
    print("\n" + "=" * 80)
    print("✅ 河流名称修正完成！")
    print("=" * 80)
    
    print(f"\n📊 处理总结:")
    print(f"  • 输入要素: {input_layer.featureCount()}")
    print(f"  • 输出要素: {output_layer.featureCount()}")
    print(f"  • 修正数量: {fixed_count} 条")
    print(f"  • 无需修正: {unchanged_count} 条")
    if unknown_code_count > 0:
        print(f"  • 未知代码: {unknown_code_count} 条")
    
    print(f"\n📋 河流代码映射表:")
    for code, name in sorted(RIVER_CODE_TO_NAME.items()):
        count = fixed_river_code_stats.get(code, {}).get('count', 0)
        if count > 0:
            print(f"  • {code:<6} → {name:<10} ({count} 条)")
    
    print(f"\n💡 说明:")
    print(f"  ✓ 已根据 river_code 自动修正 river_name")
    print(f"  ✓ 所有其他字段保持不变")
    print(f"  ✓ 生成新的 {OUTPUT_LAYER_NAME} 图层（memory图层）")
    print(f"  ✓ 原 {INPUT_LAYER_NAME} 图层未被修改")
    
    print(f"\n📁 下一步:")
    print(f"  1. 检查 {OUTPUT_LAYER_NAME} 图层数据是否正确")
    print(f"  2. 如有需要，导出为 GeoJSON/Shapefile")
    print(f"  3. 如发现新的河流代码，请在 RIVER_CODE_TO_NAME 中添加")
    
    # 保存图层并重新加载
    print(f"\n💾 保存图层到文件并重新加载")
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    return output_layer


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🔧 河流名称修正脚本开始执行...")
    print("=" * 80)
    
    try:
        result = fix_river_name()
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
        print(f"错误信息: {e}")
        print(f"\n详细堆栈:")
        import traceback
        traceback.print_exc()
        print("=" * 80)
