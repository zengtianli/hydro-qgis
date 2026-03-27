"""
07 从堤段(dd)复制起终点里程高程到堤防线(df)

功能:
1. 按 dike_code 分组 dd 堤段
2. 找到每组中 LC 最小和最大的堤段
3. 将对应的里程(LC)和高程(ddgc)赋值给 df：
   - LC 最小的堤段 → df 的起点 (qdlc, qdgc)
   - LC 最大的堤段 → df 的终点 (zdlc, zdgc)
4. 生成新图层 df_with_elevation_lc，添加到 process 组

输入图层:
  - dd: 堤段图层（已更新高程）
    必需字段: dike_code, LC, ddgc
      · dike_code: 堤防编码
      · LC: 里程 (m)
      · ddgc: 堤顶高程 (m)

  - df: 堤防线图层
    必需字段: dikeCode 或 dike_code
      · 堤防编码，用于与 dd 匹配

输出图层:
  - df_with_elevation_lc: 堤防线（带高程和LC）
    继承字段: df 全部字段
    更新字段: qdlc, zdlc, qdgc, zdgc
      · qdlc: 起点LC (m) - 对应 dd 的 LC 最小值
      · zdlc: 终点LC (m) - 对应 dd 的 LC 最大值
      · qdgc: 起点高程 (m) - 对应 LC 最小堤段的 ddgc
      · zdgc: 终点高程 (m) - 对应 LC 最大堤段的 ddgc

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
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QVariant

# 导入保存函数
from qgis_util import save_and_reload_layer

# ============ 配置参数 ============

# 输入图层名称
INPUT_DD_LAYER = 'dd'           # 堤段图层（有 LC、ddgc）
INPUT_DF_LAYER = 'df'           # 堤防线图层

# 输出图层名称
OUTPUT_LAYER_NAME = 'df_with_elevation_lc'

# dd 字段名称
DD_DIKE_CODE_FIELD = 'dike_code'    # 堤防编码
DD_LC_FIELD = 'LC'                   # 里程
DD_DDGC_FIELD = 'ddgc'               # 堤顶高程

# df 字段名称（可能的变体）
DF_DIKE_CODE_FIELDS = ['dikeCode', 'dike_code', 'DIKECODE']  # 按优先级尝试

# 输出字段名称
QDLC_FIELD = 'qdlc'     # 起点LC
ZDLC_FIELD = 'zdlc'     # 终点LC
QDGC_FIELD = 'qdgc'     # 起点高程
ZDGC_FIELD = 'zdgc'     # 终点高程

# ============ 辅助函数 ============

def normalize_code(code):
    """规范化编码（转大写、去空格）"""
    if code is None:
        return ''
    return str(code).strip().upper()


def ensure_group_exists(group_name):
    """确保图层组存在"""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = root.findGroup(group_name)
    if not group:
        group = root.insertGroup(0, group_name)
    return group


def find_field(layer, field_names):
    """在图层中查找字段（按优先级尝试多个名称）"""
    layer_fields = [f.name() for f in layer.fields()]
    for name in field_names:
        if name in layer_fields:
            return name
    return None


# ============ 主函数 ============

def copy_dd_endpoints_to_df():
    """从 dd 复制起终点里程高程到 df"""
    
    print("\n" + "=" * 70)
    print("98 从堤段(dd)复制起终点里程高程到堤防线(df)")
    print("=" * 70)
    
    # ========== 1. 加载图层 ==========
    print(f"\n【步骤1】加载图层")
    
    # 加载 dd 图层
    dd_layers = QgsProject.instance().mapLayersByName(INPUT_DD_LAYER)
    if not dd_layers:
        print(f"  ❌ 找不到图层: {INPUT_DD_LAYER}")
        return None
    dd_layer = dd_layers[0]
    print(f"  ✅ dd: {dd_layer.featureCount()} 条堤段")
    
    # 加载 df 图层
    df_layers = QgsProject.instance().mapLayersByName(INPUT_DF_LAYER)
    if not df_layers:
        print(f"  ❌ 找不到图层: {INPUT_DF_LAYER}")
        return None
    df_layer = df_layers[0]
    print(f"  ✅ df: {df_layer.featureCount()} 条堤防线")
    
    # 检查 dd 必需字段
    dd_fields = [f.name() for f in dd_layer.fields()]
    missing_dd = []
    if DD_LC_FIELD not in dd_fields:
        missing_dd.append(DD_LC_FIELD)
    if DD_DDGC_FIELD not in dd_fields:
        missing_dd.append(DD_DDGC_FIELD)
    if DD_DIKE_CODE_FIELD not in dd_fields:
        missing_dd.append(DD_DIKE_CODE_FIELD)
    
    if missing_dd:
        print(f"  ❌ dd 缺少字段: {', '.join(missing_dd)}")
        print(f"     可用字段: {', '.join(dd_fields)}")
        return None
    print(f"  ✅ dd 字段检查通过")
    
    # 检查 df 堤防编码字段
    df_dike_code_field = find_field(df_layer, DF_DIKE_CODE_FIELDS)
    if not df_dike_code_field:
        print(f"  ❌ df 找不到堤防编码字段")
        print(f"     尝试过: {', '.join(DF_DIKE_CODE_FIELDS)}")
        df_fields = [f.name() for f in df_layer.fields()]
        print(f"     可用字段: {', '.join(df_fields)}")
        return None
    print(f"  ✅ df 使用字段: {df_dike_code_field}")
    
    # ========== 2. 按 dike_code 分组 dd ==========
    print(f"\n【步骤2】按堤防编码分组 dd")
    
    # 构建 dike_code → [(lc, ddgc), ...] 的映射
    dike_groups = {}
    
    for dd_feat in dd_layer.getFeatures():
        dike_code = normalize_code(dd_feat[DD_DIKE_CODE_FIELD])
        lc = dd_feat[DD_LC_FIELD]
        ddgc = dd_feat[DD_DDGC_FIELD]
        
        if not dike_code or lc is None:
            continue
        
        if dike_code not in dike_groups:
            dike_groups[dike_code] = []
        
        dike_groups[dike_code].append({
            'lc': lc,
            'ddgc': ddgc
        })
    
    print(f"  📊 分组结果: {len(dike_groups)} 个堤防")
    
    # 计算每组的起终点
    dike_endpoints = {}
    
    for dike_code, segments in dike_groups.items():
        if not segments:
            continue
        
        # 按 LC 排序
        sorted_segments = sorted(segments, key=lambda x: x['lc'])
        
        # 起点 = LC 最小
        start_seg = sorted_segments[0]
        # 终点 = LC 最大
        end_seg = sorted_segments[-1]
        
        dike_endpoints[dike_code] = {
            'qdlc': start_seg['lc'],
            'qdgc': start_seg['ddgc'],
            'zdlc': end_seg['lc'],
            'zdgc': end_seg['ddgc'],
            'segment_count': len(segments)
        }
    
    # 显示示例
    print(f"\n  📋 堤防起终点示例（前3个）:")
    print(f"  {'堤防编码':<12} {'起点LC':<8} {'终点LC':<8} {'起点高程':<10} {'终点高程':<10} {'堤段数'}")
    print("  " + "-" * 65)
    
    for i, (code, data) in enumerate(list(dike_endpoints.items())[:3]):
        qdlc = data['qdlc']
        zdlc = data['zdlc']
        qdgc = f"{float(data['qdgc']):.2f}" if data['qdgc'] is not None else "NULL"
        zdgc = f"{float(data['zdgc']):.2f}" if data['zdgc'] is not None else "NULL"
        count = data['segment_count']
        print(f"  {code:<12} {qdlc:<8} {zdlc:<8} {qdgc:<10} {zdgc:<10} {count}")
    
    # ========== 3. 创建输出图层 ==========
    print(f"\n【步骤3】创建输出图层")
    
    geom_type = QgsWkbTypes.displayString(df_layer.wkbType())
    output_layer = QgsVectorLayer(
        f"{geom_type}?crs={df_layer.crs().authid()}",
        OUTPUT_LAYER_NAME,
        "memory"
    )
    
    output_provider = output_layer.dataProvider()
    
    # 复制 df 所有字段
    output_provider.addAttributes(df_layer.fields().toList())
    
    # 添加/确保输出字段存在
    existing_fields = [f.name() for f in output_layer.fields()]
    new_fields = []
    
    if QDLC_FIELD not in existing_fields:
        new_fields.append(QgsField(QDLC_FIELD, QVariant.Double, 'double', 15, 2))
    if ZDLC_FIELD not in existing_fields:
        new_fields.append(QgsField(ZDLC_FIELD, QVariant.Double, 'double', 15, 2))
    if QDGC_FIELD not in existing_fields:
        new_fields.append(QgsField(QDGC_FIELD, QVariant.Double, 'double', 15, 2))
    if ZDGC_FIELD not in existing_fields:
        new_fields.append(QgsField(ZDGC_FIELD, QVariant.Double, 'double', 15, 2))
    
    if new_fields:
        output_provider.addAttributes(new_fields)
    
    output_layer.updateFields()
    print(f"  ✅ 输出字段: {QDLC_FIELD}, {ZDLC_FIELD}, {QDGC_FIELD}, {ZDGC_FIELD}")
    
    # ========== 4. 更新 df ==========
    print(f"\n【步骤4】更新堤防线数据")
    
    output_features = []
    matched_count = 0
    unmatched_count = 0
    
    for df_feat in df_layer.getFeatures():
        new_feat = QgsFeature(output_layer.fields())
        new_feat.setGeometry(df_feat.geometry())
        
        # 复制所有属性
        for field in df_layer.fields():
            new_feat[field.name()] = df_feat[field.name()]
        
        # 获取堤防编码
        df_dike_code = normalize_code(df_feat[df_dike_code_field])
        
        # 查找对应的起终点数据
        if df_dike_code in dike_endpoints:
            data = dike_endpoints[df_dike_code]
            new_feat[QDLC_FIELD] = data['qdlc']
            new_feat[ZDLC_FIELD] = data['zdlc']
            if data['qdgc'] is not None:
                new_feat[QDGC_FIELD] = round(data['qdgc'], 2)
            if data['zdgc'] is not None:
                new_feat[ZDGC_FIELD] = round(data['zdgc'], 2)
            matched_count += 1
        else:
            unmatched_count += 1
        
        output_features.append(new_feat)
    
    output_provider.addFeatures(output_features)
    output_layer.updateExtents()
    
    print(f"  ✅ 匹配成功: {matched_count} 条")
    if unmatched_count > 0:
        print(f"  ⚠️  未匹配: {unmatched_count} 条（dd 中无对应堤防）")
    
    # ========== 5. 添加到项目 ==========
    print(f"\n【步骤5】添加到项目")
    
    project = QgsProject.instance()
    
    # 移除旧图层
    existing = project.mapLayersByName(OUTPUT_LAYER_NAME)
    for old in existing:
        project.removeMapLayer(old)
    
    # 添加到 process 组
    process_group = ensure_group_exists("process")
    project.addMapLayer(output_layer, False)
    process_group.addLayer(output_layer)
    
    print(f"  ✅ 已添加: {OUTPUT_LAYER_NAME} (process组)")
    
    # ========== 6. 验证结果 ==========
    print(f"\n【步骤6】验证结果")
    
    print(f"\n  📋 更新后数据示例（前5条）:")
    print(f"  {'堤防编码':<12} {'qdlc':<8} {'zdlc':<8} {'qdgc':<10} {'zdgc':<10}")
    print("  " + "-" * 50)
    
    count = 0
    for feat in output_layer.getFeatures():
        if count >= 5:
            break
        
        dike_code = normalize_code(feat[df_dike_code_field]) if df_dike_code_field in [f.name() for f in output_layer.fields()] else "?"
        qdlc = feat[QDLC_FIELD]
        zdlc = feat[ZDLC_FIELD]
        qdgc = feat[QDGC_FIELD]
        zdgc = feat[ZDGC_FIELD]
        
        qdlc_str = str(int(float(qdlc))) if qdlc is not None else "NULL"
        zdlc_str = str(int(float(zdlc))) if zdlc is not None else "NULL"
        qdgc_str = f"{float(qdgc):.2f}" if qdgc is not None else "NULL"
        zdgc_str = f"{float(zdgc):.2f}" if zdgc is not None else "NULL"
        
        print(f"  {dike_code:<12} {qdlc_str:<8} {zdlc_str:<8} {qdgc_str:<10} {zdgc_str:<10}")
        count += 1
    
    # ========== 7. 统计 ==========
    print("\n" + "=" * 70)
    print("✅ 处理完成！")
    print("=" * 70)
    
    print(f"\n📊 统计:")
    print(f"  • 输入堤段(dd): {dd_layer.featureCount()}")
    print(f"  • 输入堤防线(df): {df_layer.featureCount()}")
    print(f"  • 堤防分组: {len(dike_groups)} 个")
    print(f"  • 匹配成功: {matched_count} 条")
    print(f"  • 未匹配: {unmatched_count} 条")
    
    print(f"\n💡 说明:")
    print(f"  • 新图层: {OUTPUT_LAYER_NAME} (在 process 组)")
    print(f"  • 已更新字段: {QDLC_FIELD}, {ZDLC_FIELD}, {QDGC_FIELD}, {ZDGC_FIELD}")
    
    # 保存图层并重新加载
    print(f"\n💾 保存图层到文件并重新加载")
    if output_layer and output_layer.isValid():
        output_layer = save_and_reload_layer(output_layer)
    
    return output_layer


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    print("\n" + "=" * 70)
    print("98 从堤段(dd)复制起终点里程高程到堤防线(df)")
    print("=" * 70)
    
    try:
        result = copy_dd_endpoints_to_df()
        
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

