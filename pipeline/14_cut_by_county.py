#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
14 按县切片浙江省 GIS 图层

从环境变量读取目标县名 + 输出目录，按 hydraulic.qgis_config.COUNTY_SLICE_SOURCES
配置遍历 5 类要素（县界 / 河流 / 水库点 / 大中型水库 / 小水电），
按属性过滤或 mask 空间裁剪，统一重投影到 EPSG:4326，写出 GeoJSON。

环境变量:
    COUNTY_NAME: 完整县名（如 "天台县"）
    OUTPUT_DIR:  输出目录（如 /Users/tianli/Work/shared/resources/gis/derived/county-slices/台州市/天台县）

输出 5 个文件:
    县界.geojson / 河流.geojson / 水库点.geojson / 大中型水库.geojson / 小水电.geojson

使用方式:
    bash scripts/cut_county.sh 天台县 /tmp/tiantai_test
"""

# ============ 路径设置（QGIS控制台兼容）============
import sys
from pathlib import Path

def _setup_paths():
    """设置模块搜索路径，兼容QGIS控制台和命令行执行"""
    known_paths = [
        Path(__file__).resolve().parent.parent if '__file__' in dir() else None,
        Path.home() / 'Dev/tools/hydro-qgis',
    ]

    script_dir = None
    for p in known_paths:
        if p is not None and p.exists():
            script_dir = p
            break

    if script_dir is None:
        print("⚠️ 无法确定脚本目录，模块导入可能失败")
        return

    lib_dir = script_dir / 'lib'
    util_dir = script_dir / '_util'
    pipeline_dir = script_dir / 'pipeline'
    for path in [str(lib_dir), str(util_dir), str(pipeline_dir)]:
        if path not in sys.path:
            sys.path.insert(0, path)

_setup_paths()
# ============ 路径设置结束 ============

import os
import re

# 检测是否在 QGIS GUI 内（__console__）还是 headless 命令行
_HEADLESS = (__name__ == '__main__')

if _HEADLESS:
    # Headless 模式：手动初始化 QgsApplication
    from qgis.core import QgsApplication
    _qgs = QgsApplication([], False)
    _qgs.initQgis()
    # 加载 processing 算法
    import sys as _sys
    _qgis_prefix = os.environ.get('QGIS_PREFIX_PATH', '')
    if _qgis_prefix:
        _plugins_dir = os.path.join(
            os.path.dirname(_qgis_prefix), 'Resources', 'python', 'plugins'
        )
        if os.path.isdir(_plugins_dir) and _plugins_dir not in _sys.path:
            _sys.path.insert(0, _plugins_dir)
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception as _e:
        print(f"⚠️ Processing 初始化失败: {_e}")

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsVectorFileWriter, QgsFeatureRequest,
)
from qgis import processing

from qgis_util import (
    reproject_layer_if_needed,
    print_banner, print_step, print_success, print_error, print_info,
)

from hydraulic.qgis_config import (
    COUNTY_SLICE_SOURCES,
    COUNTY_SLICE_CITY_OVERRIDES,
    COUNTY_SLICE_OUTPUT_CRS,
    COUNTY_SLICE_MASK_SOURCE,
    COUNTY_SLICE_MASK_FILTER,
)
from hydraulic.config import get_city_from_county


# ============ 工具函数 ============

def derive_short_county(county_name: str) -> str:
    """从完整县名派生短名（去掉 县/市/区/旗 后缀）

    天台县 -> 天台
    余杭区 -> 余杭
    嘉善县 -> 嘉善
    海宁市 -> 海宁
    """
    return re.sub(r'(县|市|区|旗)$', '', county_name)


def load_source_layer(source_path: str, source_crs: str, layer_name: str):
    """加载源 layer 并显式设置 CRS（不靠自动探测）"""
    layer = QgsVectorLayer(source_path, layer_name, 'ogr')
    if not layer.isValid():
        print_error(f"无法加载源图层: {source_path}")
        return None

    # 显式设置 CRS（覆盖文件元数据）
    crs = QgsCoordinateReferenceSystem(source_crs)
    layer.setCrs(crs)

    print_info(f"源: {source_path}", indent=2)
    print_info(f"CRS (forced): {source_crs}", indent=2)
    print_info(f"要素总数: {layer.featureCount()}", indent=2)
    return layer


def build_county_mask(county_name: str):
    """根据县名 dissolve 县界 polygon 作为 mask layer（EPSG:4490 源 → 输出 4326）"""
    print_info(f"构建县 mask: {county_name}", indent=2)
    mask_filter = COUNTY_SLICE_MASK_FILTER.format(county=county_name)

    # 加载行政边界并强制 CRS
    mask_layer = load_source_layer(COUNTY_SLICE_MASK_SOURCE, "EPSG:4490", "county_mask_raw")
    if not mask_layer:
        return None

    # 用属性过滤拿到该县所有乡镇
    mask_layer.setSubsetString(mask_filter)
    print_info(f"mask filter: {mask_filter}", indent=2)
    print_info(f"匹配乡镇/街道数: {mask_layer.featureCount()}", indent=2)

    if mask_layer.featureCount() == 0:
        print_error(f"县名 '{county_name}' 在行政边界中无匹配，请确认名称")
        return None

    # dissolve 成单个 polygon
    dissolved = processing.run("native:dissolve", {
        'INPUT': mask_layer,
        'FIELD': [],
        'OUTPUT': 'memory:'
    })['OUTPUT']

    # 重投影到 4326
    dissolved_4326 = reproject_layer_if_needed(dissolved, COUNTY_SLICE_OUTPUT_CRS, "county_mask")
    return dissolved_4326


def write_geojson(layer, out_path: str, target_crs: str):
    """写 GeoJSON，显式 dest_crs，写入 crs 字段（RFC7946=NO），坐标 6 位精度"""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GeoJSON"
    options.fileEncoding = "UTF-8"
    options.destinationCrs = QgsCoordinateReferenceSystem(target_crs)
    options.layerOptions = [
        "RFC7946=NO",          # 保留 crs 字段
        "COORDINATE_PRECISION=6",
        "WRITE_NAME=NO",
    ]

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        out_path,
        QgsProject.instance().transformContext(),
        options
    )

    if error[0] == QgsVectorFileWriter.NoError:
        return True
    else:
        print_error(f"写入失败: {error[1]}")
        return False


def process_one(name: str, cfg: dict, county_name: str, county_short: str,
                output_dir: Path, mask_layer):
    """处理单个要素类，输出一个 geojson 文件"""
    print_step(name, f"{cfg['method']}")

    src = load_source_layer(cfg['source'], cfg['source_crs'], f"{name}_src")
    if not src:
        return False

    method = cfg['method']

    if method == 'attr_filter':
        expr = cfg['attr_filter'].format(county=county_name, county_short=county_short)
        print_info(f"过滤表达式: {expr}", indent=2)
        filtered = processing.run("native:extractbyexpression", {
            'INPUT': src,
            'EXPRESSION': expr,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        result = filtered

    elif method == 'spatial_clip':
        if mask_layer is None:
            print_error("spatial_clip 需要 mask layer，但 mask 构建失败")
            return False
        # clip 前先把源重投影到 mask 的 CRS（4326）
        src_4326 = reproject_layer_if_needed(src, COUNTY_SLICE_OUTPUT_CRS, name)
        # 修复无效几何（河流图层有 self-intersect 等问题）
        try:
            src_fixed = processing.run("native:fixgeometries", {
                'INPUT': src_4326,
                'OUTPUT': 'memory:'
            })['OUTPUT']
            print_info(f"几何修复后: {src_fixed.featureCount()} 要素", indent=2)
        except Exception as e:
            print_info(f"几何修复跳过: {e}", indent=2)
            src_fixed = src_4326
        clipped = processing.run("native:clip", {
            'INPUT': src_fixed,
            'OVERLAY': mask_layer,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        result = clipped

    else:
        print_error(f"未知 method: {method}")
        return False

    print_info(f"过滤/裁剪后要素数: {result.featureCount()}", indent=2)

    if result.featureCount() == 0:
        print_error(f"{name} 无要素，跳过写出")
        return False

    # 重投影到目标 CRS（attr_filter 路径仍需处理）
    result = reproject_layer_if_needed(result, COUNTY_SLICE_OUTPUT_CRS, name)

    out_path = output_dir / f"{name}.geojson"
    # 文件已存在则先删（GeoJSON writer 不覆盖）
    if out_path.exists():
        out_path.unlink()

    ok = write_geojson(result, str(out_path), COUNTY_SLICE_OUTPUT_CRS)
    if ok:
        size_kb = out_path.stat().st_size / 1024
        print_success(
            f"{name}.geojson 写出成功 - {result.featureCount()} 要素, {size_kb:.1f} KB"
        )
        print_info(f"路径: {out_path}", indent=2)
    return ok


# ============ 主入口 ============

def main():
    print_banner("县级 GIS 切片器")

    county_name = os.environ.get('COUNTY_NAME', '').strip()
    output_dir_str = os.environ.get('OUTPUT_DIR', '').strip()

    if not county_name or not output_dir_str:
        print_error("缺少环境变量 COUNTY_NAME 或 OUTPUT_DIR")
        return 1

    output_dir = Path(output_dir_str)
    output_dir.mkdir(parents=True, exist_ok=True)

    county_short = derive_short_county(county_name)

    # 解析所属市 → 选择源配置（city-override 命中则整体替换）
    city = get_city_from_county(county_name) or ""
    if city in COUNTY_SLICE_CITY_OVERRIDES:
        effective_sources = COUNTY_SLICE_CITY_OVERRIDES[city]
        source_mode = f"city-override [{city}]"
    else:
        effective_sources = COUNTY_SLICE_SOURCES
        source_mode = "default (全省 5 类源)"

    print_info(f"县名: {county_name} (短名: {county_short})", indent=1)
    print_info(f"所属市: {city or '?'} → 源模式: {source_mode}", indent=1)
    print_info(f"输出目录: {output_dir}", indent=1)
    print_info(f"输出 CRS: {COUNTY_SLICE_OUTPUT_CRS}", indent=1)
    print_info(f"待切要素: {list(effective_sources.keys())}", indent=1)

    # 1. 构建县 mask（spatial_clip 用）
    print_step("MASK", "构建县级 mask polygon")
    mask_layer = build_county_mask(county_name)
    if mask_layer is None:
        print_error("mask 构建失败，spatial_clip 类要素将跳过")

    # 2. 遍历有效要素（默认 5 类 / city-override 时按城市表）
    results = {}
    for name, cfg in effective_sources.items():
        try:
            results[name] = process_one(
                name, cfg, county_name, county_short, output_dir, mask_layer
            )
        except Exception as e:
            print_error(f"{name} 处理异常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # 3. 总结
    print_banner("切片完成")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    return 0 if all(results.values()) else 1


# ========== 脚本入口 ==========

if __name__ == '__console__' or __name__ == '__main__':
    try:
        rc = main()
    except Exception as e:
        print_error(f"主流程异常: {e}")
        import traceback
        traceback.print_exc()
        rc = 2

    # 写退出码到文件供 wrapper 检查
    rc_file = os.environ.get('CUT_COUNTY_RC_FILE')
    if rc_file:
        try:
            with open(rc_file, 'w') as f:
                f.write(str(rc))
        except Exception:
            pass

    # GUI 模式自动退出 / headless 直接 sys.exit
    if _HEADLESS:
        try:
            _qgs.exitQgis()
        except Exception:
            pass
        sys.exit(rc)
    else:
        try:
            from qgis.PyQt.QtCore import QTimer
            from qgis.PyQt.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(500, app.quit)
        except Exception:
            pass
