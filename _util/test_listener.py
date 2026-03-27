#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本 - 验证QGIS监听器是否正常工作
这是一个简单的测试脚本，可用于验证Terminal→QGIS通信机制

使用方法：
  在Terminal运行: ./qgis-run test_listener.py
"""

from qgis.core import QgsProject
from datetime import datetime

print("=" * 80)
print("🧪 QGIS监听器测试脚本")
print("=" * 80)
print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"当前项目: {QgsProject.instance().fileName() or '未保存的项目'}")
print("")

# 获取项目信息
project = QgsProject.instance()
layers = project.mapLayers()

print(f"项目图层数量: {len(layers)}")
print("")

if layers:
    print("图层列表:")
    for layer_id, layer in list(layers.items())[:5]:  # 只显示前5个
        print(f"  - {layer.name()} ({layer.featureCount()} features)")
    if len(layers) > 5:
        print(f"  ... 还有 {len(layers) - 5} 个图层")
else:
    print("⚠️  项目中没有图层")

print("")
print("=" * 80)
print("✅ 测试完成！如果你在Terminal看到这个输出，说明监听器工作正常！")
print("=" * 80)

