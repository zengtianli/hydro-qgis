"""
13 字段对齐脚本 - 通用版

📌 说明：
   这是一个通用脚本，适用于所有河流（华溪、熟溪、白溪等）
   根据standard组的字段定义，标准化process组的输出图层

功能：
1. 读取standard组中的图层作为字段模板
2. 调整process组中对应图层的字段顺序和内容
3. 删除多余字段，添加缺失字段（自动填充NULL值或计算值）
4. 自动计算Shape_Leng和Shape_Area字段（如果standard中有这些字段）
5. 确保字段顺序与standard完全一致
6. 对齐后的图层自动移到final组

输入图层（从两个组读取）：
- standard组：标准模板图层（grid, house, road, vegetation）
- process组：待标准化图层（grid_enriched, house_output, road_output, vegetation_output）

输出图层（自动移到final组）：
- final/grid: 标准化后的grid图层
- final/house: 标准化后的house图层
- final/road: 标准化后的road图层
- final/vegetation: 标准化后的vegetation图层

📊 字段对齐规则：
   
   ┌────────────────────┬────────────────────────────────────┐
   │ 情况               │ 处理方式                            │
   ├────────────────────┼────────────────────────────────────┤
   │ standard有，       │ 添加字段并填充NULL                  │
   │ process没有        │ （Shape_*字段会自动计算）           │
   ├────────────────────┼────────────────────────────────────┤
   │ process有，        │ 删除该字段                          │
   │ standard没有       │                                    │
   ├────────────────────┼────────────────────────────────────┤
   │ 两者都有           │ 保留并复制数据                      │
   ├────────────────────┼────────────────────────────────────┤
   │ 字段类型不匹配     │ 尝试转换，失败则填充NULL            │
   └────────────────────┴────────────────────────────────────┘

💡 使用方法：
   1. 确保QGIS中已有standard和process两个图层组
   2. standard组包含标准模板图层（grid, house, road, vegetation）
   3. process组包含待标准化图层（grid_enriched, house_output等）
   4. 根据需要修改LAYER_NAME_MAPPING和FIELD_NAME_MAPPING配置
   5. 在QGIS Python控制台运行此脚本
   6. 查看final组中的标准化输出图层

⚙️  配置参数（在脚本中修改）：
   - SOURCE_GROUP: 标准模板组名（默认: 'standard'）
   - TARGET_GROUP: 需要调整的组名（默认: 'process'）
   - LAYER_NAME_MAPPING: process图层到standard图层的名称映射
   - FIELD_NAME_MAPPING: 字段名称映射（如elevation←Bathymetry）
   - PROCESS_LAYERS: 指定处理的图层（空列表=处理所有）

🔍 特殊处理：
   - Shape_Leng字段：自动计算周长/长度（米）
   - Shape_Area字段：自动计算面积（平方米）
   - elevation字段：可从Bathymetry字段映射
   - 字段顺序严格按照standard组定义

📝 示例输出（grid图层）：
   标准字段：Bathymetry, grid_id, area, polderId, town, Shape_Leng, Shape_Area
   
   处理前(grid_enriched)： grid_id, area, town, polderId, Bathymetry
   处理后(final/grid)：    Bathymetry, grid_id, area, polderId, town, Shape_Leng✓, Shape_Area✓
   
   ✓ = 自动计算的字段
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
    QgsGeometry
)
from qgis.PyQt.QtCore import QVariant
import processing

# 导入工具函数库
from qgis_util import ensure_group_exists, save_and_reload_layer

# 导入公共配置
from hydraulic.qgis_config import (
    ALIGN_SOURCE_GROUP,
    ALIGN_TARGET_GROUP,
    ALIGN_LAYER_NAME_MAPPING,
    ALIGN_FIELD_NAME_MAPPING,
)

# ========== 配置区 ==========

# 源组名称（标准模板）
SOURCE_GROUP = ALIGN_SOURCE_GROUP

# 目标组名称（需要调整的）
TARGET_GROUP = ALIGN_TARGET_GROUP

# 需要处理的图层（留空则处理所有同名图层）
PROCESS_LAYERS = []  # 或指定 ['road', 'house', 'vegetation', 'grid']

# Process组到Standard组的名称映射
LAYER_NAME_MAPPING = ALIGN_LAYER_NAME_MAPPING

# 字段名称映射（当standard字段名与process字段名不同时）
FIELD_NAME_MAPPING = ALIGN_FIELD_NAME_MAPPING

# 字段映射策略
FIELD_STRATEGY = {
    'missing_in_target': 'add_null',      # standard有但output没有 → 添加NULL值
    'extra_in_target': 'remove',           # output有但standard没有 → 删除
    'type_mismatch': 'convert_or_null'     # 类型不匹配 → 尝试转换，失败则NULL
}

# 是否备份原图层（False=不备份，直接替换）
BACKUP_ORIGINAL = False

# ========== 工具函数 ==========

def get_layer_group(group_name):
    """
    获取指定名称的图层组
    
    Args:
        group_name: 组名称
        
    Returns:
        QgsLayerTreeGroup 或 None
    """
    root = QgsProject.instance().layerTreeRoot()
    
    for child in root.children():
        if child.nodeType() == 0 and child.name() == group_name:  # 0 = Group
            return child
    
    return None


def get_layers_in_group(group):
    """
    获取组内的所有图层
    
    Args:
        group: QgsLayerTreeGroup
        
    Returns:
        dict: {layer_name: QgsVectorLayer}
    """
    layers = {}
    
    for child in group.children():
        if child.nodeType() == 1:  # 1 = Layer
            layer = child.layer()
            if layer and isinstance(layer, QgsVectorLayer):
                layers[layer.name()] = layer
    
    return layers


def get_field_info(layer):
    """
    获取图层的字段信息
    
    Args:
        layer: QgsVectorLayer
        
    Returns:
        list: [(field_name, field_type, field_length, field_precision), ...]
    """
    field_info = []
    
    for field in layer.fields():
        field_info.append({
            'name': field.name(),
            'type': field.type(),
            'type_name': field.typeName(),
            'length': field.length(),
            'precision': field.precision()
        })
    
    return field_info


def convert_field_value(value, target_type):
    """
    尝试转换字段值到目标类型
    
    Args:
        value: 原始值
        target_type: QVariant类型
        
    Returns:
        转换后的值，失败返回None
    """
    if value is None:
        return None
    
    try:
        if target_type == QVariant.Int:
            return int(value) if value != '' else None
        elif target_type == QVariant.Double:
            return float(value) if value != '' else None
        elif target_type == QVariant.String:
            return str(value) if value is not None else ''
        elif target_type == QVariant.Bool:
            if isinstance(value, str):
                return value.lower() in ['true', '1', 'yes']
            return bool(value)
        else:
            return value
    except (ValueError, TypeError):
        return None


def create_aligned_layer(source_layer, target_layer, standard_fields, layer_name=None):
    """
    创建字段对齐后的新图层
    
    Args:
        source_layer: 标准图层（提供字段定义）
        target_layer: 目标图层（提供数据）
        standard_fields: 标准字段列表
        layer_name: 图层名称（用于查找字段映射）
        
    Returns:
        QgsVectorLayer: 新的对齐图层
    """
    # 创建新图层
    geom_type = QgsWkbTypes.displayString(target_layer.wkbType())
    crs = target_layer.crs().authid()
    
    new_layer = QgsVectorLayer(
        f"{geom_type}?crs={crs}",
        target_layer.name(),
        "memory"
    )
    
    new_provider = new_layer.dataProvider()
    
    # 添加标准字段（按顺序）
    fields_to_add = []
    for field_info in standard_fields:
        qgs_field = QgsField(
            field_info['name'],
            field_info['type']
        )
        qgs_field.setLength(field_info['length'])
        qgs_field.setPrecision(field_info['precision'])
        fields_to_add.append(qgs_field)
    
    new_provider.addAttributes(fields_to_add)
    new_layer.updateFields()
    
    # 构建字段映射（target_field_name → field_object）
    target_field_map = {}
    for field in target_layer.fields():
        target_field_map[field.name()] = field
    
    # 获取当前图层的字段名称映射配置
    field_mapping = FIELD_NAME_MAPPING.get(layer_name, {}) if layer_name else {}
    
    # 复制数据
    new_features = []
    
    for feat in target_layer.getFeatures():
        new_feat = QgsFeature(new_layer.fields())
        new_feat.setGeometry(feat.geometry())
        
        # 按标准字段顺序填充数据
        geom = feat.geometry()
        
        for i, field_info in enumerate(standard_fields):
            standard_field_name = field_info['name']
            
            # 特殊处理：自动计算Shape_Leng和Shape_Area字段
            if standard_field_name == 'Shape_Leng':
                # 计算周长/长度（米）
                if geom and not geom.isNull():
                    length = geom.length()
                    new_feat[standard_field_name] = round(length, 10)
                else:
                    new_feat[standard_field_name] = 0.0
                continue
            
            if standard_field_name == 'Shape_Area':
                # 计算面积（平方米）
                if geom and not geom.isNull():
                    area = geom.area()
                    new_feat[standard_field_name] = round(area, 10)
                else:
                    new_feat[standard_field_name] = 0.0
                continue
            
            # 确定从target图层的哪个字段获取数据
            # 1. 先检查是否有字段名称映射
            source_field_name = field_mapping.get(standard_field_name, standard_field_name)
            
            if source_field_name in target_field_map:
                # 字段存在于target（可能是映射后的名称），复制值
                old_value = feat[source_field_name]
                
                # 检查类型是否匹配
                old_type = target_field_map[source_field_name].type()
                new_type = field_info['type']
                
                if old_type == new_type:
                    new_feat[standard_field_name] = old_value
                else:
                    # 类型不匹配，尝试转换
                    converted_value = convert_field_value(old_value, new_type)
                    new_feat[standard_field_name] = converted_value
            else:
                # 字段不存在于target，填充NULL
                new_feat[standard_field_name] = None
        
        new_features.append(new_feat)
    
    new_provider.addFeatures(new_features)
    new_layer.updateExtents()
    
    return new_layer


# ========== 主函数 ==========

def align_output_fields():
    """
    主函数：对齐output组的字段
    
    Returns:
        dict: 处理结果统计
    """
    
    print("=" * 80)
    print("📋 字段对齐脚本 - 根据standard组调整process组")
    print("=" * 80)
    
    # ========== 1. 加载图层组 ==========
    print(f"\n【步骤1】加载图层组")
    
    source_group = get_layer_group(SOURCE_GROUP)
    if not source_group:
        print(f"  ❌ 错误: 无法找到 '{SOURCE_GROUP}' 组")
        print(f"     请确保QGIS项目中存在该组")
        return None
    
    print(f"  ✅ 找到标准组: {SOURCE_GROUP}")
    
    target_group = get_layer_group(TARGET_GROUP)
    if not target_group:
        print(f"  ❌ 错误: 无法找到 '{TARGET_GROUP}' 组")
        print(f"     请确保QGIS项目中存在该组")
        return None
    
    print(f"  ✅ 找到目标组: {TARGET_GROUP}")
    
    # ========== 2. 获取图层列表 ==========
    print(f"\n【步骤2】扫描图层")
    
    source_layers = get_layers_in_group(source_group)
    target_layers = get_layers_in_group(target_group)
    
    print(f"  📁 Standard组图层: {', '.join(source_layers.keys())}")
    print(f"  📁 Process组图层: {', '.join(target_layers.keys())}")
    
    # 找到匹配的图层对（支持名称映射）
    layer_pairs = []
    
    for standard_name in source_layers.keys():
        # 如果指定了PROCESS_LAYERS，检查是否在列表中
        if PROCESS_LAYERS and standard_name not in PROCESS_LAYERS:
            continue
        
        # 查找对应的process图层名称
        process_name = None
        
        # 1. 先查找映射表
        for proc_name, std_name in LAYER_NAME_MAPPING.items():
            if std_name == standard_name and proc_name in target_layers:
                process_name = proc_name
                break
        
        # 2. 如果映射表没找到，尝试直接匹配
        if not process_name and standard_name in target_layers:
            process_name = standard_name
        
        # 如果找到了对应的process图层
        if process_name:
            source_layer = source_layers[standard_name]
            target_layer = target_layers[process_name]
            
            source_field_count = len(source_layer.fields())
            target_field_count = len(target_layer.fields())
            
            layer_pairs.append({
                'standard_name': standard_name,     # standard组的名称
                'process_name': process_name,       # process组的名称
                'source': source_layer,
                'target': target_layer,
                'source_field_count': source_field_count,
                'target_field_count': target_field_count
            })
    
    if not layer_pairs:
        print(f"\n  ❌ 错误: 没有找到匹配的图层对")
        print(f"     请检查LAYER_NAME_MAPPING配置或图层名称")
        print(f"\n  💡 提示:")
        print(f"     Standard组: {', '.join(source_layers.keys())}")
        print(f"     Process组: {', '.join(target_layers.keys())}")
        print(f"     当前映射: {LAYER_NAME_MAPPING}")
        return None
    
    print(f"\n【发现的图层对】")
    for pair in layer_pairs:
        std_name = pair['standard_name']
        proc_name = pair['process_name']
        src_count = pair['source_field_count']
        tgt_count = pair['target_field_count']
        
        if src_count == tgt_count:
            status = "[字段数相同，检查顺序]"
        elif src_count < tgt_count:
            status = f"[需删除 {tgt_count - src_count} 个字段]"
        else:
            status = f"[需添加 {src_count - tgt_count} 个字段]"
        
        if std_name == proc_name:
            print(f"  ✅ {std_name}: standard ({src_count} fields) → process ({tgt_count} fields) {status}")
        else:
            print(f"  ✅ {std_name} ← {proc_name}: standard ({src_count} fields) → process ({tgt_count} fields) {status}")
    
    # ========== 3. 处理每个图层对 ==========
    print(f"\n【步骤3】处理图层")
    
    stats = {
        'processed': 0,
        'total_features': 0,
        'fields_added': 0,
        'fields_removed': 0,
        'type_conversions': 0
    }
    
    for pair in layer_pairs:
        standard_name = pair['standard_name']
        process_name = pair['process_name']
        source_layer = pair['source']
        target_layer = pair['target']
        
        print(f"\n{'=' * 80}")
        if standard_name == process_name:
            print(f"🔄 处理图层: {standard_name}")
        else:
            print(f"🔄 处理图层: {standard_name} (来自 {process_name})")
        print(f"{'=' * 80}")
        
        # 获取标准字段
        standard_fields = get_field_info(source_layer)
        standard_field_names = [f['name'] for f in standard_fields]
        
        print(f"  📝 Standard字段 ({len(standard_fields)} 个):")
        print(f"     {', '.join(standard_field_names)}")
        
        # 获取目标字段
        target_fields = get_field_info(target_layer)
        target_field_names = [f['name'] for f in target_fields]
        
        print(f"  📝 Process字段 ({len(target_fields)} 个):")
        print(f"     {', '.join(target_field_names)}")
        
        # 分析差异
        fields_to_add = [f for f in standard_field_names if f not in target_field_names]
        fields_to_remove = [f for f in target_field_names if f not in standard_field_names]
        fields_to_keep = [f for f in standard_field_names if f in target_field_names]
        
        # 识别需要自动计算的字段
        auto_calc_fields = [f for f in fields_to_add if f in ['Shape_Leng', 'Shape_Area']]
        
        print(f"\n  🔍 字段分析:")
        if fields_to_add:
            # 区分自动计算字段和NULL字段
            null_fields = [f for f in fields_to_add if f not in auto_calc_fields]
            if auto_calc_fields:
                print(f"     ➕ 需要添加(自动计算): {', '.join(auto_calc_fields)} ({len(auto_calc_fields)} 个)")
            if null_fields:
                print(f"     ➕ 需要添加(NULL值): {', '.join(null_fields)} ({len(null_fields)} 个)")
            stats['fields_added'] += len(fields_to_add)
        if fields_to_remove:
            print(f"     ➖ 需要删除: {', '.join(fields_to_remove)} ({len(fields_to_remove)} 个)")
            stats['fields_removed'] += len(fields_to_remove)
        if fields_to_keep:
            print(f"     ✅ 保留字段: {', '.join(fields_to_keep)} ({len(fields_to_keep)} 个)")
        
        # 检查类型不匹配
        type_mismatches = []
        for field_name in fields_to_keep:
            src_field = next(f for f in standard_fields if f['name'] == field_name)
            tgt_field = next(f for f in target_fields if f['name'] == field_name)
            
            if src_field['type'] != tgt_field['type']:
                type_mismatches.append({
                    'field': field_name,
                    'source_type': src_field['type_name'],
                    'target_type': tgt_field['type_name']
                })
        
        if type_mismatches:
            print(f"\n  ⚠️  类型不匹配:")
            for mismatch in type_mismatches:
                print(f"     - {mismatch['field']}: {mismatch['target_type']} → {mismatch['source_type']}")
                stats['type_conversions'] += 1
        
        # 创建对齐后的新图层（传入standard_name用于字段映射）
        print(f"\n  🔧 创建对齐图层...")
        new_layer = create_aligned_layer(source_layer, target_layer, standard_fields, layer_name=standard_name)
        
        # 设置最终图层名称
        new_layer.setName(standard_name)
        
        # 显示字段映射信息
        if standard_name in FIELD_NAME_MAPPING:
            print(f"\n  🔄 字段名称映射:")
            for std_field, src_field in FIELD_NAME_MAPPING[standard_name].items():
                print(f"     - {std_field} ← {src_field}")
        
        print(f"  ✅ 新图层创建完成")
        print(f"     - 图层名称: {standard_name}")
        print(f"     - 要素数: {new_layer.featureCount()}")
        print(f"     - 字段数: {len(new_layer.fields())}")
        print(f"     - 字段顺序: {', '.join([f.name() for f in new_layer.fields()])}")
        
        stats['total_features'] += new_layer.featureCount()
        
        # 添加到final组（保留process组的原始图层）
        print(f"\n  🔄 添加到final组...")
        
        # 保留process组的旧图层，不删除
        print(f"     💡 保留 process 组的原始图层: {process_name}")
        
        # 查找或创建 final 组
        root = QgsProject.instance().layerTreeRoot()
        final_group = ensure_group_exists("final")
        
        # 使用standard的名称作为最终名称
        new_layer.setName(standard_name)
        
        # 移除final组中可能存在的同名旧图层
        existing_final_layers = QgsProject.instance().mapLayersByName(standard_name)
        for existing_layer in existing_final_layers:
            # 检查是否在final组中
            layer_node = root.findLayer(existing_layer.id())
            if layer_node and layer_node.parent() and layer_node.parent().name() == "final":
                QgsProject.instance().removeMapLayer(existing_layer)
                print(f"     🗑️  已移除final组中的旧图层: {standard_name}")
        
        # 添加新图层到final组
        QgsProject.instance().addMapLayer(new_layer, False)
        final_group.addLayer(new_layer)
        
        print(f"  ✅ 图层已添加到final组: {standard_name}")
        print(f"     📌 process组中的 {process_name} 已保留作为中间结果")
        
        # 保存图层到文件并重新加载
        print(f"\n  💾 保存图层到文件并重新加载")
        if new_layer and new_layer.isValid():
            new_layer = save_and_reload_layer(new_layer, group_name="final")
        
        stats['processed'] += 1
    
    # ========== 4. 输出统计 ==========
    print(f"\n" + "=" * 80)
    print(f"📊 处理完成统计")
    print("=" * 80)
    
    print(f"\n【处理结果】")
    print(f"  • 处理图层数: {stats['processed']}")
    print(f"  • 总要素数: {stats['total_features']}")
    print(f"  • 添加字段: {stats['fields_added']} 个")
    print(f"  • 删除字段: {stats['fields_removed']} 个")
    print(f"  • 类型转换: {stats['type_conversions']} 个")
    
    print(f"\n【Final组最终状态】")
    for pair in layer_pairs:
        standard_name = pair['standard_name']
        process_name = pair['process_name']
        
        final_layers = QgsProject.instance().mapLayersByName(standard_name)
        if final_layers:
            final_layer = final_layers[0]
            field_names = [f.name() for f in final_layer.fields()]
            
            # 标注自动计算的字段
            annotated_fields = []
            for fname in field_names:
                if fname in ['Shape_Leng', 'Shape_Area']:
                    annotated_fields.append(f"{fname}✓")
                else:
                    annotated_fields.append(fname)
            
            if standard_name == process_name:
                print(f"  ✅ {standard_name}:")
            else:
                print(f"  ✅ {standard_name} (原名: {process_name}):")
            print(f"     - 字段数: {len(field_names)}")
            print(f"     - 字段顺序: {', '.join(annotated_fields)}")
            
            # 检查自动计算字段是否有数据
            auto_calc_fields = [f for f in field_names if f in ['Shape_Leng', 'Shape_Area']]
            if auto_calc_fields:
                # 抽样检查第一个要素
                first_feat = next(final_layer.getFeatures(), None)
                if first_feat:
                    calc_values = []
                    for field in auto_calc_fields:
                        value = first_feat[field]
                        if value is not None and value != 0:
                            calc_values.append(f"{field}={value:.2f}")
                    if calc_values:
                        print(f"     - 自动计算字段示例: {', '.join(calc_values)}")
    
    print(f"\n" + "=" * 80)
    print(f"✅ 字段对齐完成！")
    print(f"   Process组图层已按照standard组的字段定义对齐")
    print(f"   对齐后的图层已添加到final组")
    print(f"   Process组的原始图层已保留作为中间结果")
    print(f"\n💡 特殊处理说明:")
    print(f"   ✓ = 自动计算的字段（Shape_Leng/Shape_Area）")
    print(f"   Shape_Leng: 周长/长度（米）")
    print(f"   Shape_Area: 面积（平方米）")
    print("=" * 80)
    
    return stats


# ========== 执行 ==========

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("📋 字段对齐脚本开始执行...")
        print("=" * 80)
        
        result = align_output_fields()
        
        if result:
            print("\n✅ 脚本执行成功！请查看final组的标准化图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ 字段对齐完成！\n\n"
                    msg += f"📊 处理统计:\n"
                    msg += f"  • 处理图层数: {result['processed']}\n"
                    msg += f"  • 总要素数: {result['total_features']}\n"
                    msg += f"  • 添加字段: {result['fields_added']} 个\n"
                    msg += f"  • 删除字段: {result['fields_removed']} 个\n\n"
                    msg += f"📁 标准化后的图层已保存到final组\n"
                    msg += f"📌 Process组的原始图层已保留\n\n"
                    msg += f"💡 Shape_Leng和Shape_Area字段已自动计算"
                    
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

# 自动运行（无论是直接执行还是通过exec执行）
if __name__ == '__main__':
    main()
else:
    # 通过exec执行时也自动运行
    main()

