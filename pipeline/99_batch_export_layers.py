"""
批量导出QGIS图层为GeoJSON或Shapefile

功能:
1. 批量导出指定的QGIS图层
2. 支持导出为GeoJSON、Shapefile、GeoPackage等格式
3. 自动创建输出目录
4. 支持坐标系转换
5. 提供详细的导出进度和结果统计

使用方法:
1. 在QGIS中加载需要导出的图层
2. 修改配置参数中的图层名称列表
3. 在QGIS Python控制台运行此脚本

配置说明:
- LAYER_NAMES: 要导出的图层名称列表
- OUTPUT_FORMAT: 输出格式 ('GeoJSON', 'ESRI Shapefile', 'GPKG')
- OUTPUT_DIR: 输出目录路径
- TARGET_CRS: 目标坐标系（可选，None表示保持原坐标系）
"""

import os
from pathlib import Path
from qgis.core import (
    QgsProject, QgsVectorFileWriter, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsVectorLayer
)
from qgis.PyQt.QtCore import QVariant
import processing

# ============ 配置参数 ============

# 导出模式选择
EXPORT_BY_GROUP = True  # True: 按组导出, False: 按图层名称列表导出

# 要导出的组名（当 EXPORT_BY_GROUP=True 时使用）
GROUP_NAME = 'final'  # 例如: 'final', 'process', 'input', 'standard'

# 要导出的图层名称列表（当 EXPORT_BY_GROUP=False 时使用）
LAYER_NAMES = [
    'house',
    'grid',
    'road',
    'vegetation'
    # 'dike_sections_with_elevation',
    # 'river_center_points',
    # 'river_cut_points',
    # 添加更多图层名称...
]

# 输出格式选择
OUTPUT_FORMAT = 'GeoJSON'  # 可选: 'GeoJSON', 'ESRI Shapefile', 'GPKG'

# 输出目录（相对于当前工作目录或绝对路径）
OUTPUT_DIR = str(Path.home() / 'Downloads/zdwp/2025风险图/exported_layers/final/')

# 目标坐标系（可选）
TARGET_CRS = None  # 例如: 'EPSG:4326', 'EPSG:4549', None表示保持原坐标系

# 文件名前缀（可选）
FILE_PREFIX = ''  # 例如: 'hx_', 'export_'

# 是否覆盖已存在的文件
OVERWRITE_EXISTING = True

# ============ 格式配置 ============

FORMAT_CONFIG = {
    'GeoJSON': {
        'driver': 'GeoJSON',
        'extension': '.geojson',
        'options': ['COORDINATE_PRECISION=6']
    },
    'ESRI Shapefile': {
        'driver': 'ESRI Shapefile',
        'extension': '.shp',
        'options': ['ENCODING=UTF-8']
    },
    'GPKG': {
        'driver': 'GPKG',
        'extension': '.gpkg',
        'options': []
    }
}

# ============ 主函数 ============

def get_layer_by_name(layer_name):
    """根据名称获取图层"""
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        return None
    return layers[0]


def get_layer_group(group_name):
    """根据名称获取图层组"""
    root = QgsProject.instance().layerTreeRoot()
    return root.findGroup(group_name)


def get_layers_in_group(group_name):
    """
    获取指定组内的所有图层
    
    Args:
        group_name: 组名称
    
    Returns:
        dict: {图层名称: 图层对象}
    """
    group = get_layer_group(group_name)
    if not group:
        return {}
    
    layers_dict = {}
    
    # 遍历组内的所有节点
    for child in group.children():
        if hasattr(child, 'layer'):
            layer = child.layer()
            if layer and layer.type() == 0:  # 0 = VectorLayer
                layers_dict[layer.name()] = layer
    
    return layers_dict


def create_output_directory(output_dir):
    """创建输出目录"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        return True
    except Exception as e:
        print(f"  ❌ 创建目录失败: {e}")
        return False


def get_output_filename(layer_name, output_dir, extension):
    """生成输出文件名"""
    # 清理图层名称，移除特殊字符
    clean_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    clean_name = clean_name.replace(' ', '_')
    
    # 添加前缀
    filename = f"{FILE_PREFIX}{clean_name}{extension}"
    
    return os.path.join(output_dir, filename)


def export_layer(layer, output_path, format_config, target_crs=None):
    """
    导出单个图层
    
    参数:
        layer: QGIS图层对象
        output_path: 输出文件路径
        format_config: 格式配置
        target_crs: 目标坐标系
    
    返回:
        (是否成功, 错误信息)
    """
    try:
        # 准备导出参数
        driver = format_config['driver']
        options = format_config['options']
        
        # 坐标系转换
        transform_context = QgsProject.instance().transformContext()
        
        if target_crs and target_crs != layer.crs().authid():
            # 需要坐标系转换
            dest_crs = QgsCoordinateReferenceSystem(target_crs)
            if not dest_crs.isValid():
                return False, f"无效的目标坐标系: {target_crs}"
        else:
            # 使用原坐标系
            dest_crs = layer.crs()
        
        # 执行导出
        error = QgsVectorFileWriter.writeAsVectorFormat(
            layer,                    # 图层
            output_path,             # 输出路径
            'UTF-8',                 # 编码
            dest_crs,                # 目标坐标系
            driver,                  # 驱动程序
            layerOptions=options     # 选项
        )
        
        if error[0] == QgsVectorFileWriter.NoError:
            return True, None
        else:
            return False, f"导出错误: {error[1]}"
            
    except Exception as e:
        return False, f"导出异常: {str(e)}"


def batch_export_layers():
    """批量导出图层"""
    
    print("\n" + "=" * 80)
    print("📦 批量导出QGIS图层")
    print("=" * 80)
    print(f"⏰ 开始时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========== 验证配置 ==========
    print(f"\n【配置检查】")
    
    if OUTPUT_FORMAT not in FORMAT_CONFIG:
        print(f"  ❌ 错误: 不支持的输出格式 '{OUTPUT_FORMAT}'")
        print(f"  💡 支持的格式: {', '.join(FORMAT_CONFIG.keys())}")
        return
    
    format_config = FORMAT_CONFIG[OUTPUT_FORMAT]
    print(f"  ✅ 输出格式: {OUTPUT_FORMAT}")
    print(f"  ✅ 文件扩展名: {format_config['extension']}")
    
    # 根据导出模式显示配置
    if EXPORT_BY_GROUP:
        print(f"  ✅ 导出模式: 按组导出")
        print(f"  ✅ 目标组: {GROUP_NAME}")
    else:
        print(f"  ✅ 导出模式: 按图层名称列表")
        print(f"  ✅ 图层数量: {len(LAYER_NAMES)}")
    
    print(f"  ✅ 输出目录: {OUTPUT_DIR}")
    
    if TARGET_CRS:
        print(f"  ✅ 目标坐标系: {TARGET_CRS}")
    else:
        print(f"  ✅ 坐标系: 保持原坐标系")
    
    # ========== 创建输出目录 ==========
    print(f"\n【准备工作】")
    print(f"  🔄 创建输出目录...")
    
    if not create_output_directory(OUTPUT_DIR):
        return
    
    output_dir_abs = os.path.abspath(OUTPUT_DIR)
    print(f"  ✅ 输出目录: {output_dir_abs}")
    
    # ========== 获取要导出的图层 ==========
    print(f"\n【图层检查】")
    
    available_layers = {}
    missing_layers = []
    
    # 获取项目中所有图层
    all_project_layers = QgsProject.instance().mapLayers()
    print(f"  📋 项目中共有 {len(all_project_layers)} 个图层")
    
    # 根据导出模式获取图层
    if EXPORT_BY_GROUP:
        # 按组导出
        print(f"\n  🔍 查找组: {GROUP_NAME}")
        group = get_layer_group(GROUP_NAME)
        
        if not group:
            print(f"  ❌ 错误: 找不到组 '{GROUP_NAME}'")
            print(f"\n  💡 可用的组:")
            root = QgsProject.instance().layerTreeRoot()
            for child in root.children():
                if child.nodeType() == 0:  # 0 = GroupNode
                    print(f"     - {child.name()}")
            return
        
        print(f"  ✅ 找到组: {GROUP_NAME}")
        available_layers = get_layers_in_group(GROUP_NAME)
        
        if not available_layers:
            print(f"  ❌ 错误: 组 '{GROUP_NAME}' 中没有图层")
            return
        
        print(f"\n  📦 组内图层列表:")
        for layer_name, layer in available_layers.items():
            print(f"  ✅ {layer_name}: {layer.featureCount()} 个要素, {layer.crs().authid()}")
    
    else:
        # 按图层名称列表导出
        print(f"\n  🔍 查找指定图层...")
        for layer_name in LAYER_NAMES:
            layer = get_layer_by_name(layer_name)
            if layer:
                available_layers[layer_name] = layer
                print(f"  ✅ {layer_name}: {layer.featureCount()} 个要素, {layer.crs().authid()}")
            else:
                missing_layers.append(layer_name)
                print(f"  ❌ {layer_name}: 图层不存在")
        
        if missing_layers:
            print(f"\n  ⚠️  缺失图层: {', '.join(missing_layers)}")
            print(f"  💡 可用图层名称:")
            for layer_id, layer_obj in list(all_project_layers.items())[:10]:
                print(f"     - {layer_obj.name()}")
            if len(all_project_layers) > 10:
                print(f"     ... 还有 {len(all_project_layers) - 10} 个")
        
        if not available_layers:
            print(f"\n  ❌ 错误: 没有找到任何可导出的图层")
            return
    
    # ========== 开始导出 ==========
    print(f"\n" + "=" * 80)
    print(f"🚀 开始批量导出 ({len(available_layers)} 个图层)")
    print("=" * 80)
    
    success_count = 0
    failed_exports = []
    export_details = []
    
    for i, (layer_name, layer) in enumerate(available_layers.items(), 1):
        print(f"\n【{i}/{len(available_layers)}】导出图层: {layer_name}")
        
        # 生成输出文件路径
        output_path = get_output_filename(
            layer_name, 
            OUTPUT_DIR, 
            format_config['extension']
        )
        
        print(f"  📁 输出文件: {os.path.basename(output_path)}")
        print(f"  📊 要素数量: {layer.featureCount()}")
        print(f"  🗺️  原坐标系: {layer.crs().authid()}")
        
        # 检查文件是否已存在
        if os.path.exists(output_path) and not OVERWRITE_EXISTING:
            print(f"  ⚠️  文件已存在，跳过")
            failed_exports.append((layer_name, "文件已存在"))
            continue
        
        # 执行导出
        print(f"  🔄 正在导出...")
        success, error_msg = export_layer(
            layer, 
            output_path, 
            format_config, 
            TARGET_CRS
        )
        
        if success:
            # 检查文件大小
            file_size = os.path.getsize(output_path)
            file_size_mb = file_size / (1024 * 1024)
            
            print(f"  ✅ 导出成功")
            print(f"     - 文件大小: {file_size_mb:.2f} MB")
            
            success_count += 1
            export_details.append({
                'name': layer_name,
                'path': output_path,
                'size_mb': file_size_mb,
                'features': layer.featureCount(),
                'crs': layer.crs().authid()
            })
        else:
            print(f"  ❌ 导出失败: {error_msg}")
            failed_exports.append((layer_name, error_msg))
    
    # ========== 导出总结 ==========
    print("\n" + "=" * 80)
    print("✅ 批量导出完成！")
    print("=" * 80)
    print(f"⏰ 完成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n📊 导出统计:")
    print(f"  ✅ 成功: {success_count} 个图层")
    print(f"  ❌ 失败: {len(failed_exports)} 个图层")
    print(f"  📁 输出目录: {output_dir_abs}")
    
    # 成功导出的详情
    if export_details:
        print(f"\n📋 成功导出的文件:")
        total_size = 0
        for detail in export_details:
            print(f"  ✅ {detail['name']}")
            print(f"     - 文件: {os.path.basename(detail['path'])}")
            print(f"     - 大小: {detail['size_mb']:.2f} MB")
            print(f"     - 要素: {detail['features']} 个")
            print(f"     - 坐标系: {detail['crs']}")
            total_size += detail['size_mb']
        
        print(f"\n  📦 总文件大小: {total_size:.2f} MB")
    
    # 失败的详情
    if failed_exports:
        print(f"\n❌ 导出失败的图层:")
        for layer_name, error_msg in failed_exports:
            print(f"  ❌ {layer_name}: {error_msg}")
    
    # 使用提示
    print(f"\n💡 使用提示:")
    if EXPORT_BY_GROUP:
        print(f"  - 导出来源: {GROUP_NAME} 组")
    else:
        print(f"  - 导出来源: 指定图层列表")
    print(f"  - 导出格式: {OUTPUT_FORMAT}")
    if TARGET_CRS:
        print(f"  - 坐标系已转换为: {TARGET_CRS}")
    else:
        print(f"  - 坐标系: 保持原图层坐标系")
    print(f"  - 可以在文件管理器中查看: {output_dir_abs}")
    
    # 后续建议
    if success_count > 0:
        print(f"\n📂 文件位置:")
        print(f"  {output_dir_abs}")
        
        if OUTPUT_FORMAT == 'GeoJSON':
            print(f"\n🔧 GeoJSON使用建议:")
            print(f"  - 可直接在Web地图中使用")
            print(f"  - 支持UTF-8编码，中文显示正常")
            print(f"  - 文件较小，传输方便")
        elif OUTPUT_FORMAT == 'ESRI Shapefile':
            print(f"\n🔧 Shapefile使用建议:")
            print(f"  - 兼容性最好，支持所有GIS软件")
            print(f"  - 注意字段名长度限制（10字符）")
            print(f"  - 包含多个文件(.shp, .shx, .dbf, .prj等)")
    
    print("=" * 80)
    print("🎉 脚本运行完成\n")


# ============ 快速配置函数 ============

def export_to_geojson(layer_names, output_dir='./geojson_export'):
    """快速导出为GeoJSON（按图层名称列表）"""
    global LAYER_NAMES, OUTPUT_FORMAT, OUTPUT_DIR, EXPORT_BY_GROUP
    EXPORT_BY_GROUP = False
    LAYER_NAMES = layer_names
    OUTPUT_FORMAT = 'GeoJSON'
    OUTPUT_DIR = output_dir
    batch_export_layers()


def export_to_shapefile(layer_names, output_dir='./shapefile_export'):
    """快速导出为Shapefile（按图层名称列表）"""
    global LAYER_NAMES, OUTPUT_FORMAT, OUTPUT_DIR, EXPORT_BY_GROUP
    EXPORT_BY_GROUP = False
    LAYER_NAMES = layer_names
    OUTPUT_FORMAT = 'ESRI Shapefile'
    OUTPUT_DIR = output_dir
    batch_export_layers()


def export_group_to_geojson(group_name, output_dir='./geojson_export'):
    """快速导出组为GeoJSON（按组导出）"""
    global GROUP_NAME, OUTPUT_FORMAT, OUTPUT_DIR, EXPORT_BY_GROUP
    EXPORT_BY_GROUP = True
    GROUP_NAME = group_name
    OUTPUT_FORMAT = 'GeoJSON'
    OUTPUT_DIR = output_dir
    batch_export_layers()


def export_group_to_shapefile(group_name, output_dir='./shapefile_export'):
    """快速导出组为Shapefile（按组导出）"""
    global GROUP_NAME, OUTPUT_FORMAT, OUTPUT_DIR, EXPORT_BY_GROUP
    EXPORT_BY_GROUP = True
    GROUP_NAME = group_name
    OUTPUT_FORMAT = 'ESRI Shapefile'
    OUTPUT_DIR = output_dir
    batch_export_layers()


# ============ 执行 ============

try:
    print("\n" + "📦" * 40)
    print("批量导出脚本开始执行...")
    print("📦" * 40)
    batch_export_layers()
except Exception as e:
    print("\n" + "❌" * 40)
    print("脚本执行出错！")
    print("❌" * 40)
    print(f"\n错误类型: {type(e).__name__}")
    print(f"错误信息: {str(e)}")
    print(f"\n详细堆栈:")
    import traceback
    traceback.print_exc()
    print("\n" + "❌" * 40)


# ============ 使用示例 ============

"""
使用示例:

# 方法1: 按组导出（推荐）
EXPORT_BY_GROUP = True
GROUP_NAME = 'final'  # 导出final组的所有图层
OUTPUT_FORMAT = 'GeoJSON'
OUTPUT_DIR = './exported_layers'

# 方法2: 按图层名称列表导出
EXPORT_BY_GROUP = False
LAYER_NAMES = ['house', 'grid', 'dike_sections']
OUTPUT_FORMAT = 'GeoJSON'
OUTPUT_DIR = './exported_layers'

# 方法3: 使用快速函数 - 按组导出
export_group_to_geojson('final', './final_export')
export_group_to_shapefile('process', './process_export')

# 方法4: 使用快速函数 - 按图层列表导出
export_to_geojson(['house', 'grid'])
export_to_shapefile(['dike_sections', 'river_center_points'])

# 方法5: 在QGIS Python控制台中
exec(open('/path/to/99_batch_export_layers.py').read())

# 示例：导出final组的所有图层为GeoJSON
EXPORT_BY_GROUP = True
GROUP_NAME = 'final'
OUTPUT_FORMAT = 'GeoJSON'
OUTPUT_DIR = str(Path.home() / 'Downloads/zdwp/2025风险图/final_export')
"""
