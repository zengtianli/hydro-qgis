"""
12 保护对象点图层生成脚本 - 通用版

📌 说明：
   这是一个通用脚本，适用于所有河流（华溪、熟溪、白溪等）
   只需修改脚本顶部的配置参数（图层名称）即可使用

功能：
1. 将原始保护对象点图层与final组的grid进行空间连接
2. 只保留在grid范围内的点（交集）
3. 点继承grid的所有属性（grid_id, polderId, town, elevation等）
4. 自动处理坐标系不一致
5. 处理空值，确保所有字段都有有效值
6. 验证字段完整性，输出详细统计信息

输入图层（将自动移到input组）：
- baohu: 原始保护对象点图层（点）
- grid: final组中的标准化网格图层（从09脚本生成）

输出图层（自动移到final组）：
- baohu: 带网格属性的保护对象点图层

📊 输出图层 baohu 的字段说明：
   
   核心字段（继承自grid）：
   ┌──────────────┬──────────────┬────────────────────────────┐
   │ 字段名       │ 类型         │ 说明                        │
   ├──────────────┼──────────────┼────────────────────────────┤
   │ grid_id      │ Integer      │ 所属网格ID（从grid继承）     │
   │ polderId     │ String(50)   │ 所属保护片ID（从grid继承）   │
   │ town         │ String(50)   │ 所属乡镇（从grid继承）       │
   │ elevation    │ Double       │ 高程（从grid继承）           │
   │ area         │ Double       │ 所属网格面积m²（从grid继承） │
   └──────────────┴──────────────┴────────────────────────────┘
   
   注：原baohu图层和grid图层的其他字段也会被保留

💡 使用方法：
   1. 确保QGIS中已加载baohu图层
   2. 确保final组中存在grid图层（运行09脚本生成）
   3. 根据实际图层名称，修改配置部分的参数
   4. 在QGIS Python控制台运行此脚本
   5. 查看final组中的baohu输出图层

⚙️  配置参数（在脚本中修改）：
   - BAOHU_LAYER: 原始保护对象点图层名称
   - GRID_LAYER: 网格图层名称（在final组中）
   - GRID_GROUP: 网格图层所在组名（默认'final'）
   - OUTPUT_LAYER_NAME: 输出图层名称
   - DEFAULT_GRID_ID: grid_id字段的默认值
   - DEFAULT_POLDER: polderId字段的默认值
   - DEFAULT_TOWN: town字段的默认值

🔍 特殊说明：
   - 使用空间连接（Join by Location），只保留在网格内的点
   - DISCARD_NONMATCHING=True，网格外的点会被过滤掉
   - 坐标系不一致时会自动重投影
   - 从final组中获取grid图层（09脚本的输出）

📝 示例输出：
   grid_id | polderId | town   | elevation | 坐标
   --------|----------|--------|-----------|----------------
   1       | sx0001   | 白鹤乡 | 145.32    | (120.xx, 28.xx)
   2       | sx0001   | 白鹤乡 | 138.56    | (120.xx, 28.xx)
   3       | sx0001   | 白鹤乡 | 152.89    | (120.xx, 28.xx)
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
from qgis_util import (
    move_layer_to_group,
    get_layer_from_group,
    get_layer_by_name,
    ensure_group_exists,
    reproject_layer_if_needed,
    check_crs_consistency,
    save_and_reload_layer
)

# 导入公共配置
from hydraulic.qgis_config import (
    INPUT_LAYERS,
    OUTPUT_LAYERS,
    BAOHU_CONFIG,
    DEFAULT_GRID_ID,
    DEFAULT_POLDER,
    DEFAULT_TOWN,
)

# ============ 配置参数 ============

# 输入图层名称
BAOHU_LAYER = 'baohu'        # 保护对象点图层（没有在INPUT_LAYERS中定义，使用原名）
GRID_LAYER = 'grid'          # 网格图层（在final组中）
GRID_GROUP = BAOHU_CONFIG['grid_group']  # 网格图层所在组

# 输出图层名称
OUTPUT_LAYER_NAME = OUTPUT_LAYERS['baohu']

# ============ 主函数 ============

def generate_baohu_layer():
    """执行保护对象图层生成"""
    
    print("=" * 80)
    print("🛡️  保护对象图层生成 - 空间连接添加网格属性")
    print("=" * 80)
    
    # ========== 1. 加载输入图层 ==========
    print(f"\n【步骤1】加载输入图层")
    
    # 加载保护对象点图层
    baohu_layers = QgsProject.instance().mapLayersByName(BAOHU_LAYER)
    if not baohu_layers:
        print(f"  ❌ 错误: 无法找到图层 '{BAOHU_LAYER}'，请确保QGIS中已加载该图层")
        return None
    
    baohu_layer = baohu_layers[0]
    baohu_fields = [f.name() for f in baohu_layer.fields()]
    move_layer_to_group(baohu_layer, "input")
    print(f"  ✅ 保护对象点: {baohu_layer.featureCount()}个 | 坐标系: {baohu_layer.crs().authid()} | 字段: {', '.join(baohu_fields)} | 已移至input组")
    
    # 加载Grid图层（从final组）
    grid_layer = get_layer_from_group(GRID_LAYER, GRID_GROUP)
    if not grid_layer:
        grid_layers = QgsProject.instance().mapLayersByName(GRID_LAYER)
        if grid_layers:
            grid_layer = grid_layers[0]
            print(f"  ⚠️  在项目中找到 {GRID_LAYER}，但不在 {GRID_GROUP} 组")
        else:
            print(f"  ❌ 错误: 无法找到图层 '{GRID_LAYER}'，请先运行 09_align_output_fields.py")
            return None
    
    grid_fields = [f.name() for f in grid_layer.fields()]
    missing_fields = [f for f in ['polderId'] if f not in grid_fields]
    if missing_fields:
        print(f"  ⚠️  网格图层缺少字段 {', '.join(missing_fields)}，将继续处理")
    print(f"  ✅ 网格: {grid_layer.featureCount()}个 | 坐标系: {grid_layer.crs().authid()} | 将继承网格所有字段到保护对象点")
    
    check_crs_consistency(baohu_layer, grid_layer, "保护对象", "网格")
    baohu_layer = reproject_layer_if_needed(baohu_layer, grid_layer.crs(), "保护对象")
    
    # ========== 2. 空间连接 - 只保留交集的点 ==========
    print(f"\n【步骤2】空间连接 | 🔄 Join by Location | 保护对象点: {baohu_layer.featureCount()}个 | 网格: {grid_layer.featureCount()}个 | 只保留交集")
    
    try:
        join_result = processing.run("native:joinattributesbylocation", {
            'INPUT': baohu_layer,
            'JOIN': grid_layer,
            'PREDICATE': [0],  # 0 = intersects (相交)
            'JOIN_FIELDS': [],  # 空列表 = 复制grid的所有字段
            'METHOD': 0,  # 0 = 创建单独要素（一对一）
            'DISCARD_NONMATCHING': True,  # 重要：丢弃不匹配的点（只保留交集）
            'PREFIX': '',
            'OUTPUT': 'memory:'
        })
        
        joined_layer = join_result['OUTPUT']
        filtered_count = baohu_layer.featureCount() - joined_layer.featureCount()
        status = f"过滤{filtered_count}个网格外点" if filtered_count > 0 else "所有点都在网格内"
        print(f"  ✅ 连接完成: {joined_layer.featureCount()}个点 | {status}")
        
    except Exception as e:
        print(f"\n  ❌ 连接失败: {e}")
        return None
    
    # ========== 3. 创建输出图层 ==========
    geom_type = QgsWkbTypes.displayString(joined_layer.wkbType())
    output_layer = QgsVectorLayer(f"{geom_type}?crs={joined_layer.crs().authid()}", OUTPUT_LAYER_NAME, "memory")
    output_provider = output_layer.dataProvider()
    output_provider.addAttributes(joined_layer.fields().toList())
    output_layer.updateFields()
    
    key_fields = ['grid_id', 'polderId', 'town', 'elevation', 'area']
    shown_fields = [f for f in key_fields if f in [field.name() for field in output_layer.fields()]]
    print(f"\n【步骤3】创建输出图层 | ✅ {len(output_layer.fields())}个字段 | 关键字段: {', '.join(shown_fields)}")
    
    # ========== 4. 填充数据 ==========
    output_features = []
    null_count = {
        'grid_id': 0,
        'polderId': 0,
        'town': 0
    }
    
    for feat in joined_layer.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(feat.geometry())
        
        # 复制所有字段
        for field in joined_layer.fields():
            field_name = field.name()
            value = feat[field_name]
            
            # 处理NULL值
            if value is None or (isinstance(value, str) and value.strip() == ''):
                if field_name == 'grid_id':
                    value = DEFAULT_GRID_ID
                    null_count['grid_id'] += 1
                elif field_name == 'polderId':
                    value = DEFAULT_POLDER
                    null_count['polderId'] += 1
                elif field_name == 'town':
                    value = DEFAULT_TOWN
                    null_count['town'] += 1
            
            new_feat[field_name] = value
        
        output_features.append(new_feat)
    
    output_provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    null_info = ' | '.join([f"{fname}空值{cnt}个(填充为{DEFAULT_GRID_ID if fname=='grid_id' else DEFAULT_POLDER if fname=='polderId' else DEFAULT_TOWN})" 
                            for fname, cnt in null_count.items() if cnt > 0])
    print(f"\n【步骤4】填充数据 | ✅ {len(output_features)}个保护对象点" + (f" | {null_info}" if null_info else ""))
    
    # ========== 5. 添加到项目（process组） ==========
    project = QgsProject.instance()
    process_group = ensure_group_exists("process")
    existing_layers = project.mapLayersByName(OUTPUT_LAYER_NAME)
    for old_layer in existing_layers:
        project.removeMapLayer(old_layer)
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    print(f"\n【步骤5】添加到QGIS项目 | ✅ {OUTPUT_LAYER_NAME} 已添加到 process 组")
    
    # ========== 6. 数据验证 ==========
    field_names = [f.name() for f in output_layer.fields()]
    polders = [feat['polderId'] for feat in output_layer.getFeatures() if 'polderId' in field_names and feat['polderId']]
    towns = [feat['town'] for feat in output_layer.getFeatures() if 'town' in field_names and feat['town']]
    elevs = [feat['elevation'] for feat in output_layer.getFeatures() if 'elevation' in field_names and feat['elevation']]
    
    stats = f"总点数: {output_layer.featureCount()}"
    if polders:
        stats += f" | 保护片: {len(set(polders))}个({', '.join(sorted(set(polders))[:3])}...)"
    if towns:
        stats += f" | 乡镇: {len(set(towns))}个"
    if elevs:
        stats += f" | 高程: {min(elevs):.2f}~{max(elevs):.2f}m"
    print(f"\n【步骤6】数据验证 | ✅ {stats}")
    
    # ========== 7. 完成 ==========
    print("\n" + "=" * 80)
    print(f"✅ 保护对象图层生成完成！ | 输出: {OUTPUT_LAYER_NAME}(process组) | 已继承grid所有属性(polderId/town/elevation/grid_id等)")
    print("=" * 80)
    
    # 保存图层并重新加载
    print(f"\n💾 保存图层到文件并重新加载")
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    return output_layer


# ============ 执行 ============

def main():
    """主执行函数"""
    try:
        print("\n" + "=" * 80)
        print("🛡️  保护对象图层生成脚本开始执行...")
        print("=" * 80)
        result = generate_baohu_layer()
        
        if result:
            print("\n✅ 脚本执行成功！请查看新生成的图层。")
            
            # 显示成功消息框
            try:
                from qgis.utils import iface
                if iface:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    
                    msg = f"✅ 保护对象图层生成完成！\n\n"
                    msg += f"📊 输出图层: {OUTPUT_LAYER_NAME}\n"
                    msg += f"📁 位置: final组\n\n"
                    msg += f"生成的保护对象点数: {result.featureCount()} 个\n\n"
                    msg += "已添加字段:\n"
                    msg += "  • grid_id (所属网格ID)\n"
                    msg += "  • polderId (所属保护片ID)\n"
                    msg += "  • town (所属乡镇)\n"
                    msg += "  • elevation (高程)\n"
                    msg += "  • area (所属网格面积)"
                    
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

