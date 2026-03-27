#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QGIS工具函数库
提供图层验证、管理、坐标系处理等通用功能

功能模块：
1. 图层验证模块 - 验证输入输出图层的字段完整性
2. 图层获取模块 - 根据名称或组获取图层
3. 图层管理模块 - 移动图层到指定组
4. 坐标系处理模块 - 检查和重投影坐标系
5. 日志输出模块 - 统一的日志格式化输出
6. 几何处理模块 - 修复几何、移除Z坐标等
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsWkbTypes
)
from qgis import processing
import traceback
from functools import wraps


# ============================================================
# 1. 图层验证模块
# ============================================================

def validate_input_fields(layer, layer_name, required_fields):
    """
    验证输入图层是否包含必需字段
    
    参数:
        layer: 输入图层 (QgsVectorLayer)
        layer_name: 图层名称（用于显示）
        required_fields: 必需字段列表或字典
    
    返回:
        (bool, list): (是否通过验证, 缺失字段列表)
    
    示例:
        >>> is_valid, missing = validate_input_fields(layer, 'my_layer', ['LC', 'zagc'])
        >>> if not is_valid:
        >>>     print(f"缺失字段: {missing}")
    """
    if layer is None:
        print(f"  ❌ 图层 '{layer_name}' 不存在")
        return False, []
    
    available_fields = [f.name() for f in layer.fields()]
    
    # 如果是字典，取值
    if isinstance(required_fields, dict):
        required_fields = list(required_fields.values())
    
    missing_fields = [f for f in required_fields if f not in available_fields]
    
    if missing_fields:
        print(f"\n  ❌ 图层 '{layer_name}' 缺少必需字段:")
        for field in missing_fields:
            print(f"     - {field}")
        print(f"\n  📋 可用字段: {', '.join(available_fields)}")
        return False, missing_fields
    
    return True, []


def validate_output_fields(layer, layer_name, required_fields):
    """
    验证输出图层是否包含必需字段
    
    参数:
        layer: 输出图层 (QgsVectorLayer)
        layer_name: 图层名称（用于显示）
        required_fields: 必需字段列表
    
    返回:
        (bool, list): (是否通过验证, 缺失字段列表)
    
    示例:
        >>> is_valid, missing = validate_output_fields(output_layer, 'result', ['LC', 'ddgc'])
    """
    if layer is None or not layer.isValid():
        print(f"  ❌ 输出图层 '{layer_name}' 无效")
        return False, []
    
    available_fields = [f.name() for f in layer.fields()]
    missing_fields = [f for f in required_fields if f not in available_fields]
    
    if missing_fields:
        print(f"\n  ❌ 输出图层 '{layer_name}' 缺少必需字段:")
        for field in missing_fields:
            print(f"     - {field}")
        return False, missing_fields
    
    # 验证是否有数据
    if layer.featureCount() == 0:
        print(f"  ⚠️  警告: 输出图层 '{layer_name}' 没有要素")
        return False, []
    
    return True, []


def check_required_fields(layer, required_fields):
    """
    简化版字段检查（不打印详细信息）
    
    参数:
        layer: 图层对象
        required_fields: 必需字段列表
    
    返回:
        bool: 是否包含所有必需字段
    """
    if layer is None:
        return False
    
    available_fields = [f.name() for f in layer.fields()]
    
    if isinstance(required_fields, dict):
        required_fields = list(required_fields.values())
    
    return all(f in available_fields for f in required_fields)


# ============================================================
# 2. 图层获取模块
# ============================================================

def get_layer_by_name(layer_name, verbose=True, auto_load_from_process=True):
    """
    根据名称获取图层，如果不存在则尝试从process目录自动加载
    
    参数:
        layer_name: 图层名称
        verbose: 是否打印详细信息
        auto_load_from_process: 是否自动从process目录加载
    
    返回:
        QgsVectorLayer 或 None
    
    示例:
        >>> layer = get_layer_by_name('my_layer')
        >>> if layer:
        >>>     print(f"找到图层: {layer.featureCount()} 个要素")
    """
    from pathlib import Path
    
    layers = QgsProject.instance().mapLayersByName(layer_name)
    
    if layers:
        return layers[0]
    
    # 尝试从process目录自动加载
    if auto_load_from_process:
        process_dir = get_process_dir()
        if process_dir:
            geojson_path = Path(process_dir) / f"{layer_name}.geojson"
            if geojson_path.exists():
                if verbose:
                    print(f"  📂 从process目录自动加载: {layer_name}")
                layer = QgsVectorLayer(str(geojson_path), layer_name, 'ogr')
                if layer.isValid():
                    # 添加到项目的process组
                    project = QgsProject.instance()
                    group = ensure_group_exists("process")
                    project.addMapLayer(layer, False)
                    group.addLayer(layer)
                    if verbose:
                        print(f"  ✅ 自动加载成功: {layer.featureCount()} 个要素")
                    return layer
    
    if verbose:
        print(f"  ❌ 错误: 找不到图层 '{layer_name}'")
    return None


def get_layer_from_group(layer_name, group_name, verbose=True):
    """
    从指定组中获取图层
    
    参数:
        layer_name: 图层名称
        group_name: 组名称
        verbose: 是否打印详细信息
    
    返回:
        QgsVectorLayer 或 None
    
    示例:
        >>> layer = get_layer_from_group('grid', 'final')
    """
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    
    # 查找组
    group = root.findGroup(group_name)
    if not group:
        if verbose:
            print(f"  ⚠️  未找到组: '{group_name}'")
        return None
    
    # 在组中查找图层
    for child in group.children():
        if child.nodeType() == 1:  # 1 = Layer
            layer = child.layer()
            if layer and layer.name() == layer_name:
                return layer
    
    if verbose:
        print(f"  ⚠️  在组 '{group_name}' 中未找到图层 '{layer_name}'")
    return None


def get_layers_in_group(group_name):
    """
    获取指定组内的所有图层
    
    参数:
        group_name: 组名称
    
    返回:
        dict: {layer_name: QgsVectorLayer}
    
    示例:
        >>> layers = get_layers_in_group('input')
        >>> print(f"找到 {len(layers)} 个图层")
    """
    root = QgsProject.instance().layerTreeRoot()
    
    # 查找组
    group = None
    for child in root.children():
        if child.nodeType() == 0 and child.name() == group_name:  # 0 = Group
            group = child
            break
    
    if not group:
        return {}
    
    # 获取组内所有图层
    layers = {}
    for child in group.children():
        if child.nodeType() == 1:  # 1 = Layer
            layer = child.layer()
            if layer and isinstance(layer, QgsVectorLayer):
                layers[layer.name()] = layer
    
    return layers


# ============================================================
# 3. 图层管理模块
# ============================================================

def move_layer_to_group(layer, group_name):
    """
    将图层移动到指定组
    
    参数:
        layer: 图层对象 (QgsVectorLayer)
        group_name: 目标组名称
    
    示例:
        >>> move_layer_to_group(my_layer, 'process')
    """
    if not layer:
        return
    
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    
    # 查找或创建目标组
    target_group = root.findGroup(group_name)
    if not target_group:
        target_group = root.insertGroup(0, group_name)
    
    # 查找图层在树中的位置
    layer_node = root.findLayer(layer.id())
    if layer_node:
        # 克隆节点到目标组
        cloned_node = layer_node.clone()
        target_group.insertChildNode(0, cloned_node)
        # 移除原节点
        parent = layer_node.parent()
        if parent:
            parent.removeChildNode(layer_node)


def ensure_group_exists(group_name):
    """
    确保指定组存在，不存在则创建
    
    参数:
        group_name: 组名称
    
    返回:
        QgsLayerTreeGroup: 组对象
    
    示例:
        >>> group = ensure_group_exists('output')
    """
    root = QgsProject.instance().layerTreeRoot()
    
    group = root.findGroup(group_name)
    if not group:
        group = root.insertGroup(0, group_name)
    
    return group


def remove_layer_from_project(layer_name):
    """
    从项目中移除指定名称的图层
    
    参数:
        layer_name: 图层名称
    
    返回:
        bool: 是否成功移除
    
    示例:
        >>> removed = remove_layer_from_project('temp_layer')
    """
    project = QgsProject.instance()
    layers = project.mapLayersByName(layer_name)
    
    if layers:
        for layer in layers:
            project.removeMapLayer(layer)
        return True
    
    return False


# ============================================================
# 4. 坐标系处理模块
# ============================================================

def check_crs_consistency(layer1, layer2, layer1_name="图层1", layer2_name="图层2"):
    """
    检查两个图层的坐标系是否一致
    
    参数:
        layer1: 第一个图层
        layer2: 第二个图层
        layer1_name: 第一个图层名称（用于显示）
        layer2_name: 第二个图层名称（用于显示）
    
    返回:
        bool: 坐标系是否一致
    
    示例:
        >>> if not check_crs_consistency(layer1, layer2, 'house', 'grid'):
        >>>     print("需要重投影")
    """
    crs1 = layer1.crs().authid()
    crs2 = layer2.crs().authid()
    
    print(f"  🔍 坐标系检查:")
    print(f"     - {layer1_name}: {crs1}")
    print(f"     - {layer2_name}: {crs2}")
    
    if crs1 != crs2:
        print(f"  ⚠️  警告: 坐标系不一致！")
        return False
    else:
        print(f"  ✅ 坐标系一致")
        return True


def reproject_layer_if_needed(layer, target_crs, layer_name="图层"):
    """
    如果需要，重投影图层到目标坐标系
    
    参数:
        layer: 输入图层
        target_crs: 目标坐标系 (QgsCoordinateReferenceSystem 或 str如'EPSG:4549')
        layer_name: 图层名称（用于显示）
    
    返回:
        QgsVectorLayer: 重投影后的图层（如果需要）或原图层
    
    示例:
        >>> layer = reproject_layer_if_needed(layer, 'EPSG:4549', 'my_layer')
    """
    if isinstance(target_crs, str):
        target_crs = QgsCoordinateReferenceSystem(target_crs)
    elif hasattr(target_crs, 'crs'):  # 如果是图层对象
        target_crs = target_crs.crs()
    
    source_crs = layer.crs().authid()
    target_crs_id = target_crs.authid()
    
    if source_crs == target_crs_id:
        return layer
    
    print(f"  🔄 重投影 {layer_name}: {source_crs} → {target_crs_id}...")
    
    result = processing.run("native:reprojectlayer", {
        'INPUT': layer,
        'TARGET_CRS': target_crs,
        'OUTPUT': 'memory:'
    })
    
    print(f"  ✅ 重投影完成")
    return result['OUTPUT']


def fix_geometries(layer, layer_name="图层"):
    """
    修复图层的无效几何
    
    参数:
        layer: 输入图层
        layer_name: 图层名称（用于显示）
    
    返回:
        QgsVectorLayer: 修复后的图层
    
    示例:
        >>> layer = fix_geometries(layer, 'house')
    """
    print(f"  🔄 修复 {layer_name} 的几何...")
    
    result = processing.run("native:fixgeometries", {
        'INPUT': layer,
        'OUTPUT': 'memory:'
    })
    
    print(f"  ✅ 几何修复完成: {result['OUTPUT'].featureCount()} 个要素")
    return result['OUTPUT']


def drop_z_values_if_needed(layer, layer_name="图层"):
    """
    如果图层包含Z坐标，移除它（降维到2D）
    
    参数:
        layer: 输入图层
        layer_name: 图层名称（用于显示）
    
    返回:
        QgsVectorLayer: 处理后的图层
    
    示例:
        >>> layer = drop_z_values_if_needed(layer, 'road')
    """
    has_z = QgsWkbTypes.hasZ(layer.wkbType())
    
    if not has_z:
        return layer
    
    print(f"  🔄 移除 {layer_name} 的Z坐标（降维到2D）...")
    
    result = processing.run("native:dropmzvalues", {
        'INPUT': layer,
        'DROP_M_VALUES': False,
        'DROP_Z_VALUES': True,
        'OUTPUT': 'memory:'
    })
    
    print(f"  ✅ Z坐标已移除: {QgsWkbTypes.displayString(result['OUTPUT'].wkbType())}")
    return result['OUTPUT']


# ============================================================
# 5. 日志输出模块
# ============================================================

def print_banner(title, width=80):
    """
    打印横幅标题
    
    参数:
        title: 标题文本
        width: 横幅宽度
    
    示例:
        >>> print_banner("数据处理开始")
    """
    print("\n" + "=" * width)
    print(title)
    print("=" * width)


def print_step(step_num, description):
    """
    打印步骤标题
    
    参数:
        step_num: 步骤编号（可以是数字或字符串）
        description: 步骤描述
    
    示例:
        >>> print_step(1, "加载输入图层")
    """
    print(f"\n【步骤{step_num}】{description}")


def print_success(message):
    """
    打印成功消息
    
    参数:
        message: 消息内容
    
    示例:
        >>> print_success("图层创建完成")
    """
    print(f"  ✅ {message}")


def print_error(message):
    """
    打印错误消息
    
    参数:
        message: 消息内容
    
    示例:
        >>> print_error("图层不存在")
    """
    print(f"  ❌ 错误: {message}")


def print_warning(message):
    """
    打印警告消息
    
    参数:
        message: 消息内容
    
    示例:
        >>> print_warning("坐标系不一致")
    """
    print(f"  ⚠️  警告: {message}")


def print_info(message, indent=2):
    """
    打印信息消息
    
    参数:
        message: 消息内容
        indent: 缩进级别
    
    示例:
        >>> print_info("要素数量: 100")
    """
    prefix = "  " * indent
    print(f"{prefix}- {message}")


def print_statistics(stats_dict, title="统计信息"):
    """
    打印统计信息
    
    参数:
        stats_dict: 统计数据字典
        title: 标题
    
    示例:
        >>> print_statistics({'总数': 100, '成功': 95, '失败': 5})
    """
    print(f"\n  📊 {title}:")
    for key, value in stats_dict.items():
        print(f"     - {key}: {value}")


# ============================================================
# 6. 异常处理装饰器
# ============================================================

def safe_execute(func):
    """
    装饰器：安全执行函数，捕获并打印异常
    
    用法:
        @safe_execute
        def my_function():
            # 你的代码
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print("\n" + "❌" * 40)
            print("脚本执行出错！")
            print("❌" * 40)
            print(f"\n错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print(f"\n详细堆栈:")
            traceback.print_exc()
            print("\n" + "❌" * 40)
            return None
    
    return wrapper


# ============================================================
# 7. 便捷组合函数
# ============================================================

def load_and_validate_layer(layer_name, required_fields=None, group_name=None):
    """
    加载并验证图层（组合函数）
    
    参数:
        layer_name: 图层名称
        required_fields: 必需字段列表（可选）
        group_name: 图层所在组（可选）
    
    返回:
        QgsVectorLayer 或 None
    
    示例:
        >>> layer = load_and_validate_layer('my_layer', ['LC', 'zagc'])
    """
    # 获取图层
    if group_name:
        layer = get_layer_from_group(layer_name, group_name)
    else:
        layer = get_layer_by_name(layer_name)
    
    if not layer:
        return None
    
    # 验证字段
    if required_fields:
        is_valid, missing = validate_input_fields(layer, layer_name, required_fields)
        if not is_valid:
            return None
    
    return layer


def add_layer_to_group(layer, group_name, remove_old=False):
    """
    将图层添加到项目的指定组（组合函数）
    
    参数:
        layer: 图层对象
        group_name: 组名称
        remove_old: 是否移除同名旧图层
    
    示例:
        >>> add_layer_to_group(new_layer, 'output', remove_old=True)
    """
    if not layer:
        return
    
    project = QgsProject.instance()
    
    # 移除旧图层
    if remove_old:
        existing = project.mapLayersByName(layer.name())
        for old_layer in existing:
            project.removeMapLayer(old_layer)
    
    # 确保组存在
    group = ensure_group_exists(group_name)
    
    # 添加图层
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    
    print(f"  ✅ 已添加图层 '{layer.name()}' 到 '{group_name}' 组")


# ============================================================
# 8. 图层保存模块
# ============================================================

def get_process_dir():
    """
    获取process目录路径
    优先从环境变量获取，否则从项目文件路径推断，最后尝试当前工作目录
    
    返回:
        Path: process目录路径，如果无法确定返回None
    """
    import os
    from pathlib import Path
    
    # 方式1: 从环境变量获取
    data_dir = os.environ.get('HUAXI_DATA_DIR', '')
    if data_dir:
        process_dir = Path(data_dir) / 'process'
        process_dir.mkdir(exist_ok=True)
        print(f"  📁 process目录(环境变量): {process_dir}")
        return process_dir
    
    # 方式2: 从项目文件路径推断
    project = QgsProject.instance()
    project_path = project.fileName()
    if project_path:
        process_dir = Path(project_path).parent / 'process'
        process_dir.mkdir(exist_ok=True)
        print(f"  📁 process目录(项目文件): {process_dir}")
        return process_dir
    
    # 方式3: 当前工作目录（如果存在input子目录，认为是数据目录）
    cwd = Path.cwd()
    if (cwd / 'input').exists():
        process_dir = cwd / 'process'
        process_dir.mkdir(exist_ok=True)
        print(f"  📁 process目录(工作目录): {process_dir}")
        return process_dir
    
    print(f"  ⚠️ 无法确定process目录")
    return None


def save_layer_to_file(layer, file_name=None, output_dir=None, file_format='GeoJSON'):
    """
    保存图层到文件
    
    参数:
        layer: 要保存的图层 (QgsVectorLayer)
        file_name: 文件名（不含路径，可选，默认使用图层名）
        output_dir: 输出目录（可选，默认使用process目录）
        file_format: 输出格式，默认'GeoJSON'
    
    返回:
        str: 保存的文件路径，失败返回None
    
    示例:
        >>> save_layer_to_file(my_layer)  # 保存到process/my_layer.geojson
        >>> save_layer_to_file(my_layer, 'custom_name.geojson')
        >>> save_layer_to_file(my_layer, output_dir='/path/to/dir')
    """
    from pathlib import Path
    from qgis.core import QgsVectorFileWriter
    
    if not layer or not layer.isValid():
        print(f"  ❌ 无法保存：图层无效")
        return None
    
    # 确定输出目录
    if output_dir:
        save_dir = Path(output_dir)
    else:
        save_dir = get_process_dir()
    
    if not save_dir:
        print(f"  ⚠️  无法确定保存目录，跳过保存")
        return None
    
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # 确定文件名
    if not file_name:
        file_name = f"{layer.name()}.geojson"
    
    # 确保有正确的扩展名
    if not file_name.endswith('.geojson') and file_format == 'GeoJSON':
        file_name = f"{file_name}.geojson"
    
    file_path = save_dir / file_name
    
    # 保存图层
    print(f"  💾 保存图层: {file_path}")
    
    # 使用QgsVectorFileWriter保存
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = file_format
    options.fileEncoding = 'UTF-8'
    
    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        str(file_path),
        QgsProject.instance().transformContext(),
        options
    )
    
    if error[0] == QgsVectorFileWriter.NoError:
        print(f"  ✅ 保存成功: {file_path.name} ({layer.featureCount()} 个要素)")
        return str(file_path)
    else:
        print(f"  ❌ 保存失败: {error[1]}")
        return None


def save_and_reload_layer(layer, layer_name=None, output_dir=None, group_name="process"):
    """
    保存图层到文件，然后重新加载（非temporary）
    
    参数:
        layer: 内存图层 (QgsVectorLayer)
        layer_name: 图层名称（可选，默认使用原图层名）
        output_dir: 输出目录（可选，默认使用process目录）
        group_name: 添加到的组名，默认"process"
    
    返回:
        QgsVectorLayer: 重新加载的图层（有文件backing）
    
    示例:
        >>> new_layer = save_and_reload_layer(memory_layer)
        >>> new_layer = save_and_reload_layer(memory_layer, 'custom_name', group_name='final')
    """
    if not layer or not layer.isValid():
        print(f"  ❌ 无法处理：图层无效")
        return layer
    
    name = layer_name or layer.name()
    
    # 1. 保存到文件
    file_path = save_layer_to_file(layer, name, output_dir)
    if not file_path:
        print(f"  ⚠️ 保存失败，保留内存图层")
        return layer
    
    # 2. 从文件重新加载
    new_layer = QgsVectorLayer(file_path, name, 'ogr')
    
    if not new_layer.isValid():
        print(f"  ⚠️ 重新加载失败，保留内存图层")
        return layer
    
    # 3. 从项目中移除原内存图层
    project = QgsProject.instance()
    old_layer_in_project = project.mapLayersByName(layer.name())
    for old_lyr in old_layer_in_project:
        if old_lyr.id() == layer.id():
            project.removeMapLayer(old_lyr)
    
    # 4. 添加新图层到项目
    group = ensure_group_exists(group_name)
    project.addMapLayer(new_layer, False)
    group.addLayer(new_layer)
    
    print(f"  ✅ 图层已持久化: {name}")
    return new_layer


def load_or_create_layer(layer_name, create_func, process_dir=None, force_recreate=False):
    """
    从process目录加载图层，如果不存在则创建
    
    参数:
        layer_name: 图层名称
        create_func: 创建图层的函数（无参数，返回QgsVectorLayer）
        process_dir: process目录（可选）
        force_recreate: 是否强制重新创建
    
    返回:
        QgsVectorLayer: 图层对象
    
    示例:
        >>> layer = load_or_create_layer('my_layer', lambda: create_my_layer())
    """
    from pathlib import Path
    
    if not process_dir:
        process_dir = get_process_dir()
    
    if process_dir and not force_recreate:
        file_path = Path(process_dir) / f"{layer_name}.geojson"
        if file_path.exists():
            print(f"  📂 从文件加载: {file_path}")
            layer = QgsVectorLayer(str(file_path), layer_name, 'ogr')
            if layer.isValid():
                print(f"  ✅ 加载成功: {layer.featureCount()} 个要素")
                return layer
            else:
                print(f"  ⚠️  文件存在但加载失败，将重新创建")
    
    # 创建图层
    print(f"  🔧 创建图层: {layer_name}")
    layer = create_func()
    
    # 保存到文件
    if layer and layer.isValid() and process_dir:
        save_layer_to_file(layer, output_dir=process_dir)
    
    return layer


# ============================================================
# 9. 工具函数信息
# ============================================================

def print_util_info():
    """打印工具库信息"""
    info = """
    ╔═══════════════════════════════════════════════════════════╗
    ║           QGIS 工具函数库 (qgis_util.py)                 ║
    ╠═══════════════════════════════════════════════════════════╣
    ║                                                           ║
    ║  📦 模块列表:                                             ║
    ║    1. 图层验证模块 - validate_input/output_fields        ║
    ║    2. 图层获取模块 - get_layer_by_name/from_group       ║
    ║    3. 图层管理模块 - move_layer_to_group                ║
    ║    4. 坐标系处理   - reproject/check_crs/fix_geometries ║
    ║    5. 日志输出     - print_banner/step/success/error    ║
    ║    6. 异常处理     - @safe_execute 装饰器               ║
    ║    7. 组合函数     - load_and_validate_layer            ║
    ║                                                           ║
    ║  📖 使用示例:                                             ║
    ║    from qgis_util import *                               ║
    ║    layer = get_layer_by_name('my_layer')                ║
    ║    validate_input_fields(layer, 'my_layer', ['LC'])     ║
    ║    move_layer_to_group(layer, 'output')                 ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(info)


if __name__ == '__main__':
    print_util_info()
