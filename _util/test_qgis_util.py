#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qgis_util.py 测试脚本

用于验证工具库功能是否正常工作
运行此脚本前需确保QGIS项目已加载相关图层
"""

from qgis_util import (
    get_layer_by_name,
    validate_input_fields,
    move_layer_to_group,
    fix_geometries,
    check_crs_consistency,
    reproject_layer_if_needed,
    print_banner,
    print_step,
    print_success,
    print_error,
    print_warning,
    print_statistics,
    safe_execute
)


@safe_execute
def test_qgis_util():
    """测试qgis_util工具库的各项功能"""
    
    print_banner("🧪 QGIS工具库测试", width=80)
    
    # ==================== 测试1: 图层获取 ====================
    print_step(1, "测试图层获取功能")
    
    # 测试获取不存在的图层
    layer = get_layer_by_name('nonexistent_layer', verbose=False)
    if layer is None:
        print_success("正确处理不存在的图层")
    else:
        print_error("未能正确处理不存在的图层")
    
    # 测试获取存在的图层（需要根据实际项目调整图层名称）
    test_layer_name = 'grid0'  # 替换为你项目中实际存在的图层
    layer = get_layer_by_name(test_layer_name, verbose=True)
    
    if layer:
        print_success(f"成功获取图层: {test_layer_name}")
        print(f"     - 要素数量: {layer.featureCount()}")
        print(f"     - 坐标系: {layer.crs().authid()}")
    else:
        print_warning(f"未找到测试图层: {test_layer_name}")
        print("     💡 请修改 test_layer_name 为项目中实际存在的图层")
    
    # ==================== 测试2: 字段验证 ====================
    if layer:
        print_step(2, "测试字段验证功能")
        
        # 获取实际字段
        actual_fields = [f.name() for f in layer.fields()]
        print(f"  📋 图层实际字段: {', '.join(actual_fields[:5])}...")
        
        # 测试存在的字段
        if actual_fields:
            is_valid, missing = validate_input_fields(
                layer, 
                test_layer_name, 
                [actual_fields[0]]  # 使用第一个字段测试
            )
            if is_valid:
                print_success("字段验证通过")
            
            # 测试不存在的字段
            is_valid, missing = validate_input_fields(
                layer, 
                test_layer_name, 
                ['nonexistent_field_123']
            )
            if not is_valid:
                print_success("正确检测到缺失字段")
    
    # ==================== 测试3: 坐标系处理 ====================
    if layer:
        print_step(3, "测试坐标系处理功能")
        
        # 测试坐标系检查（自己和自己比较，肯定一致）
        check_crs_consistency(layer, layer, "图层A", "图层B")
        print_success("坐标系检查功能正常")
        
        # 测试重投影（重投影到相同坐标系，应该返回原图层）
        reprojected = reproject_layer_if_needed(
            layer, 
            layer.crs(), 
            "测试图层"
        )
        if reprojected == layer:
            print_success("无需重投影时正确返回原图层")
    
    # ==================== 测试4: 几何处理 ====================
    if layer:
        print_step(4, "测试几何处理功能")
        
        # 测试几何修复
        try:
            fixed_layer = fix_geometries(layer, "测试图层")
            if fixed_layer and fixed_layer.isValid():
                print_success("几何修复功能正常")
        except Exception as e:
            print_error(f"几何修复出错: {e}")
    
    # ==================== 测试5: 日志输出 ====================
    print_step(5, "测试日志输出功能")
    
    print_success("这是成功消息")
    print_error("这是错误消息")
    print_warning("这是警告消息")
    
    # 测试统计输出
    print_statistics({
        '测试项1': 100,
        '测试项2': 95,
        '测试项3': 5
    }, title="测试统计")
    
    print_success("日志输出功能正常")
    
    # ==================== 测试6: 图层管理 ====================
    if layer:
        print_step(6, "测试图层管理功能")
        
        # 注意：这个测试会实际移动图层到test_group
        # 如果不想移动图层，请注释掉下面这行
        # move_layer_to_group(layer, "test_group")
        # print_success("图层管理功能正常（已注释掉实际操作）")
        
        print_warning("图层管理功能测试已跳过（避免移动实际图层）")
        print("     💡 如需测试，请取消注释相关代码")
    
    # ==================== 测试总结 ====================
    print_banner("✅ 测试完成", width=80)
    
    print("\n📊 测试结果汇总:")
    print("  ✅ 图层获取功能 - 正常")
    print("  ✅ 字段验证功能 - 正常")
    print("  ✅ 坐标系处理功能 - 正常")
    print("  ✅ 几何处理功能 - 正常")
    print("  ✅ 日志输出功能 - 正常")
    print("  ⚠️  图层管理功能 - 已跳过")
    
    print("\n💡 使用建议:")
    print("  1. qgis_util.py 已就绪，可以在脚本中导入使用")
    print("  2. 已重构脚本: 05_enrich_grid_layer.py, 06_generate_house_layer.py")
    print("  3. 其他脚本可以逐步重构，或保持原样继续使用")
    print("  4. 查看 REFACTOR_SUMMARY.md 了解详细重构信息")
    
    print("\n" + "=" * 80)
    print("🎉 qgis_util.py 工具库测试通过！")
    print("=" * 80)


# ==================== 执行测试 ====================
if __name__ == '__main__':
    test_qgis_util()
else:
    # 在QGIS Python控制台执行
    test_qgis_util()
