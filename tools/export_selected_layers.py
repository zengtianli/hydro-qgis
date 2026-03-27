"""
批量导出QGIS中选中的图层
- 支持多种格式：GeoJSON, Shapefile, GeoPackage
- 可选择是否重投影
- 自动获取当前选中的图层
"""
import processing
from qgis.core import QgsProject, QgsVectorFileWriter
from qgis.utils import iface
import os
from datetime import datetime

# ============ 配置 ============
# 输出目录（如果为None，则使用当前QGIS项目所在目录的exported_layers子目录）
OUTPUT_DIR = None

# 输出格式：'GeoJSON', 'ESRI Shapefile', 'GPKG' (GeoPackage)
# OUTPUT_FORMAT = 'ESRI Shapefile'
OUTPUT_FORMAT = 'GeoJSON'
# 是否重投影（如果为None，保持原坐标系）
# 常用选项: 'EPSG:4490' (CGCS2000), 'EPSG:4326' (WGS84), 'EPSG:3857' (Web墨卡托)
TARGET_CRS = 'EPSG:4490'

# 文件扩展名映射
FORMAT_EXTENSIONS = {
    'GeoJSON': '.geojson',
    'ESRI Shapefile': '.shp',
    'GPKG': '.gpkg'
}
# ==============================

def get_output_directory():
    """获取输出目录"""
    if OUTPUT_DIR:
        return OUTPUT_DIR
    
    # 使用QGIS项目所在目录
    project = QgsProject.instance()
    project_path = project.fileName()
    
    if project_path:
        project_dir = os.path.dirname(project_path)
        output_dir = os.path.join(project_dir, 'exported_layers')
    else:
        # 如果没有保存项目，使用用户主目录
        output_dir = os.path.expanduser('~/qgis_exported_layers')
    
    # 添加时间戳子目录
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(output_dir, timestamp)
    
    return output_dir

def get_selected_layers():
    """获取图层面板中选中的图层"""
    if not iface:
        print("❌ 错误: 无法访问QGIS界面，请在QGIS中运行此脚本")
        return []
    
    # 获取图层树视图
    layer_tree_view = iface.layerTreeView()
    
    # 获取选中的图层节点
    selected_nodes = layer_tree_view.selectedNodes()
    
    # 提取图层对象
    selected_layers = []
    for node in selected_nodes:
        if hasattr(node, 'layer') and node.layer():
            selected_layers.append(node.layer())
    
    return selected_layers

def export_layer(layer, output_dir, output_format, target_crs):
    """导出单个图层"""
    layer_name = layer.name()
    
    # 清理文件名（移除非法字符）
    safe_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_name = safe_name.replace(' ', '_')
    
    # 获取文件扩展名
    extension = FORMAT_EXTENSIONS.get(output_format, '.geojson')
    
    # 输出文件路径
    output_file = os.path.join(output_dir, f"{safe_name}{extension}")
    
    print(f"\n{'='*60}")
    print(f"🔄 处理: {layer_name}")
    print(f"{'='*60}")
    print(f"   📥 图层类型: {layer.type().name if hasattr(layer.type(), 'name') else layer.type()}")
    print(f"   📊 要素数: {layer.featureCount()}")
    print(f"   🗺️  原坐标系: {layer.crs().authid()}")
    
    try:
        # 如果需要重投影
        if target_crs and layer.crs().authid() != target_crs:
            print(f"   🔄 重投影到: {target_crs}")
            
            # 使用processing工具重投影
            result = processing.run("native:reprojectlayer", {
                'INPUT': layer,
                'TARGET_CRS': target_crs,
                'OUTPUT': output_file
            })
            
            print(f"   ✅ 导出成功（已重投影）")
        else:
            # 不需要重投影，直接导出
            if target_crs:
                print(f"   ℹ️  坐标系已是 {target_crs}，跳过重投影")
            else:
                print(f"   ℹ️  保持原坐标系")
            
            # 根据格式选择导出方法
            if output_format == 'GeoJSON':
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = 'GeoJSON'
                error = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer,
                    output_file,
                    QgsProject.instance().transformContext(),
                    options
                )
                
                if error[0] == QgsVectorFileWriter.NoError:
                    print(f"   ✅ 导出成功")
                else:
                    raise Exception(f"导出失败: {error}")
            
            elif output_format == 'ESRI Shapefile':
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = 'ESRI Shapefile'
                error = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer,
                    output_file,
                    QgsProject.instance().transformContext(),
                    options
                )
                
                if error[0] == QgsVectorFileWriter.NoError:
                    print(f"   ✅ 导出成功")
                else:
                    raise Exception(f"导出失败: {error}")
            
            elif output_format == 'GPKG':
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = 'GPKG'
                options.layerName = safe_name
                error = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer,
                    output_file,
                    QgsProject.instance().transformContext(),
                    options
                )
                
                if error[0] == QgsVectorFileWriter.NoError:
                    print(f"   ✅ 导出成功")
                else:
                    raise Exception(f"导出失败: {error}")
        
        print(f"   📂 路径: {output_file}")
        
        # 检查文件大小
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            if file_size < 1024:
                print(f"   📦 文件大小: {file_size} B")
            elif file_size < 1024 * 1024:
                print(f"   📦 文件大小: {file_size / 1024:.2f} KB")
            else:
                print(f"   📦 文件大小: {file_size / 1024 / 1024:.2f} MB")
        
        return True, output_file
        
    except Exception as e:
        print(f"   ❌ 导出失败: {e}")
        return False, None

def main():
    """主函数"""
    print("=" * 60)
    print("📦 批量导出选中图层")
    print("=" * 60)
    
    # 获取选中的图层
    selected_layers = get_selected_layers()
    
    if not selected_layers:
        print("❌ 没有选中任何图层！")
        print("\n💡 使用方法:")
        print("   1. 在QGIS图层面板中选中要导出的图层（可多选）")
        print("   2. 在Python控制台中运行此脚本")
        print("=" * 60)
        
        # 显示消息框
        if iface:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(None, "没有选中图层", 
                              "请先在图层面板中选中要导出的图层！\n\n按住 Cmd 可多选图层。")
        return
    
    print(f"\n📋 找到 {len(selected_layers)} 个选中的图层:")
    for i, layer in enumerate(selected_layers, 1):
        print(f"   {i}. {layer.name()} ({layer.featureCount()} 要素)")
    
    # 获取输出目录
    output_dir = get_output_directory()
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"\n✅ 创建输出目录: {output_dir}")
    else:
        print(f"\n📁 输出目录: {output_dir}")
    
    print(f"\n⚙️  配置:")
    print(f"   📄 输出格式: {OUTPUT_FORMAT}")
    if TARGET_CRS:
        print(f"   🗺️  目标坐标系: {TARGET_CRS}")
    else:
        print(f"   🗺️  保持原坐标系")
    
    # 导出图层
    success_count = 0
    fail_count = 0
    exported_files = []
    
    for layer in selected_layers:
        success, output_file = export_layer(layer, output_dir, OUTPUT_FORMAT, TARGET_CRS)
        if success:
            success_count += 1
            exported_files.append(output_file)
        else:
            fail_count += 1
    
    # 总结
    print(f"\n{'='*60}")
    print(f"📊 导出完成！")
    print(f"{'='*60}")
    print(f"✅ 成功: {success_count} 个")
    print(f"❌ 失败: {fail_count} 个")
    print(f"\n📂 输出目录:")
    print(f"   {output_dir}")
    
    if exported_files:
        print(f"\n📋 已导出文件:")
        for file_path in exported_files:
            file_name = os.path.basename(file_path)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                if file_size < 1024 * 1024:
                    size_str = f"{file_size / 1024:.1f} KB"
                else:
                    size_str = f"{file_size / 1024 / 1024:.1f} MB"
                print(f"   • {file_name} ({size_str})")
    
    print("=" * 60)
    
    # 显示成功消息框，并提供打开文件夹选项
    if iface and success_count > 0:
        from qgis.PyQt.QtWidgets import QMessageBox
        
        msg = f"✅ 成功导出 {success_count} 个图层！\n\n"
        msg += f"📂 保存位置:\n{output_dir}\n\n"
        
        if exported_files:
            msg += "已导出文件:\n"
            for file_path in exported_files[:5]:  # 最多显示5个
                file_name = os.path.basename(file_path)
                msg += f"  • {file_name}\n"
            if len(exported_files) > 5:
                msg += f"  ... 还有 {len(exported_files) - 5} 个文件\n"
        
        msg_box = QMessageBox()
        msg_box.setWindowTitle("导出成功")
        msg_box.setText(msg)
        msg_box.setIcon(QMessageBox.Information)
        
        # 添加"打开文件夹"和"确定"按钮
        open_btn = msg_box.addButton("打开文件夹", QMessageBox.ActionRole)
        msg_box.addButton("确定", QMessageBox.AcceptRole)
        
        msg_box.exec_()
        
        # 如果用户点击了"打开文件夹"
        if msg_box.clickedButton() == open_btn:
            import subprocess
            import platform
            
            system = platform.system()
            if system == 'Darwin':  # macOS
                subprocess.run(['open', output_dir])
            elif system == 'Windows':
                subprocess.run(['explorer', output_dir])
            else:  # Linux
                subprocess.run(['xdg-open', output_dir])

# 自动运行（无论是直接执行还是通过exec执行）
if __name__ == '__main__':
    main()
else:
    # 通过exec执行时也自动运行
    main()

