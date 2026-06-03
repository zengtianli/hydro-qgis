#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
15 县域「水库工程位置分布图」成品出图引擎（参数化 · 全省可批量）

复刻范例「附图2 磐安县水库工程位置分布图」：灰度晕渲地形底图 + 县外盖灰蒙版 +
县界 + 河流水系(蓝面) + 水库工程(蓝点+名注) + 可选源头水库(红五角星) +
指北针 / 比例尺 / 图例 / 标题，QgsPrintLayout 导出 PNG(300dpi) + PDF。

两段式:
  A 段 prep（纯 GDAL，无需 QGIS）: 从 SSOT 派生 4 个 EPSG:4549 图层
     county/reservoirs/rivers/mask（县界 dissolve / 水库 SZX filter / 河流 clip / 蒙版 difference）
  B 段 render（PyQGIS headless）: 4 图层 + 晕渲栅格 → 样式 → 布局 → 导出

数据口径全部走 shared/resources SSOT（不读原始 xlsx / 不读 per-county gdb）:
  县界  = gis/raw/boundaries/行政境界（乡镇）.shp  按 COUNTY dissolve
  水库  = gis/raw/reservoirs/水库.geojson          按 SZX filter（GCMC=工程名）
  河流  = gis/raw/hydrography/河流手册_865最终.shp  按县界 clip
  晕渲  = gis/basemaps/terrain/zhejiang_hillshade_4549.tif（Copernicus GLO-30 → gdaldem，全省一次性）

用法:
  # prep + render（QGIS python）
  /Applications/QGIS-LTR.app/Contents/MacOS/bin/python3 pipeline/15_export_county_map.py \
      --county 磐安县 --hillshade gis/basemaps/terrain/panan_hillshade_4549.tif \
      --source-reservoir-xy 120.4504,28.9737 --fig-no 2
  # 仅 prep（任意 python3，验证 SSOT 口径）
  python3 pipeline/15_export_county_map.py --county 磐安县 --prep-only
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# ---- gdal CLI（晕渲/prep 用，独立于 QGIS）----
GDAL_BIN = "/opt/homebrew/bin"
OGR2OGR = f"{GDAL_BIN}/ogr2ogr"

# ---- SSOT 口径（与 hydraulic.qgis_config.RESOURCES_GIS_ROOT 对齐）----
RESOURCES_GIS = Path("/Users/tianli/Work/shared/resources/gis")
SRC_BOUNDARIES = RESOURCES_GIS / "raw/boundaries/行政境界（乡镇）.shp"
SRC_BOUNDARIES_LAYER = "行政境界（乡镇）"      # shp 内 layer 名 = 文件 stem
SRC_RESERVOIRS = RESOURCES_GIS / "raw/reservoirs/水库.geojson"     # EPSG:4326, SZX=县, GCMC=名
SRC_RIVERS = RESOURCES_GIS / "raw/hydrography/河流手册_865最终.shp"  # EPSG:4490, 面状
WORK_CRS = "EPSG:4549"     # CGCS2000 / GK CM120E（投影·米，晕渲与出图统一带）
MASK_MARGIN_M = 3000       # 地图范围外扩（米）= 出图默认视野
MASK_OUTER_M = 100000      # 蒙版外框外扩（米）= 远大于视野，怎么拉框都盖住县外

# 底图 = 官方天地图影像 img_w（服务端 token，headless 批量稳定）。
# 逐县用 GDAL 抓该县范围为本地 tif（QGIS headless 缺 WMS provider，故不直连 WMS）。
PAGE_W, PAGE_H = 210, 297   # A4 纵向 mm
BASEMAP_RES_M = 15          # 天地图影像抓取分辨率（米/像素）

_TDT_WMS_XML = """<GDAL_WMS>
  <Service name="TMS">
    <ServerUrl>https://t0.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&amp;REQUEST=GetTile&amp;VERSION=1.0.0&amp;LAYER=img&amp;STYLE=default&amp;TILEMATRIXSET=w&amp;FORMAT=tiles&amp;TILEMATRIX=${{z}}&amp;TILEROW=${{y}}&amp;TILECOL=${{x}}&amp;tk={tk}</ServerUrl>
  </Service>
  <DataWindow><UpperLeftX>-20037508.34</UpperLeftX><UpperLeftY>20037508.34</UpperLeftY>
    <LowerRightX>20037508.34</LowerRightX><LowerRightY>-20037508.34</LowerRightY>
    <TileLevel>18</TileLevel><TileCountX>1</TileCountX><TileCountY>1</TileCountY><YOrigin>top</YOrigin></DataWindow>
  <Projection>EPSG:3857</Projection><BlockSizeX>256</BlockSizeX><BlockSizeY>256</BlockSizeY>
  <BandsCount>3</BandsCount><Cache/><MaxConnections>4</MaxConnections>
</GDAL_WMS>"""


def _tianditu_token() -> str:
    tk = os.environ.get("TIANDITU_TK", "")
    if tk:
        return tk
    pe = Path.home() / ".personal_env"
    if pe.exists():
        m = re.search(r'TIANDITU_TK="?([a-f0-9]+)"?', pe.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1)
    return ""


def fit_to_aspect(bbox, aspect: float, margin: float = MASK_MARGIN_M):
    """县 bbox + margin → 撑成指定页面宽高比 aspect(=w/h)（地图满版不变形）。返回 (xmin,ymin,xmax,ymax)。"""
    xmin, ymin, xmax, ymax = bbox
    xmin -= margin; ymin -= margin; xmax += margin; ymax += margin
    w, h = xmax - xmin, ymax - ymin
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    if w / h > aspect:                 # 太宽 → 撑高
        h = w / aspect
    else:                              # 太高 → 撑宽
        w = h * aspect
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


DEFAULT_HILLSHADE = RESOURCES_GIS / "basemaps/terrain/zhejiang_hillshade_4549.tif"
DEFAULT_OUT_ROOT = Path("/Users/tianli/Work/shared/resources/output/maps")


def short_county(name: str) -> str:
    return re.sub(r"(县|市|区|旗)$", "", name)


def _run(cmd: list, desc: str):
    print(f"  · {desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    ✗ 失败: {r.stderr.strip()[:400]}")
        raise RuntimeError(f"{desc} 失败")
    tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
    if tail[0]:
        print(f"    {tail[0][:120]}")


def feature_count(path: Path) -> int:
    from json import loads
    r = subprocess.run([f"{GDAL_BIN}/ogrinfo", "-ro", "-al", "-so", "-json", str(path)],
                       capture_output=True, text=True)
    try:
        j = loads(r.stdout)
        return j["layers"][0]["featureCount"]
    except Exception:
        return -1


def layer_extent(path: Path):
    """返回 geojson 的 [xmin, ymin, xmax, ymax]（其原生 CRS = WORK_CRS）。"""
    from json import loads
    r = subprocess.run([f"{GDAL_BIN}/ogrinfo", "-ro", "-al", "-so", "-json", str(path)],
                       capture_output=True, text=True)
    j = loads(r.stdout)
    return j["layers"][0]["geometryFields"][0]["extent"]


def fetch_basemap(bbox, work: Path, res: int = BASEMAP_RES_M):
    """GDAL 抓官方天地图影像（bbox in WORK_CRS）→ 本地 tif。无 token / 失败 → None。"""
    tk = _tianditu_token()
    if not tk:
        print("  ⚠ 未找到 TIANDITU_TK（~/.personal_env 或 env），跳过天地图底图")
        return None
    xml = work / "_tdt.xml"
    xml.write_text(_TDT_WMS_XML.format(tk=tk), encoding="utf-8")  # Python 写, 无 noclobber 问题
    out = work / "basemap_tdt.tif"
    if out.exists():
        out.unlink()
    xmin, ymin, xmax, ymax = bbox
    cmd = [f"{GDAL_BIN}/gdalwarp", "-t_srs", WORK_CRS,
           "-te", str(xmin), str(ymin), str(xmax), str(ymax), "-tr", str(res), str(res),
           "-r", "bilinear", "--config", "GDAL_HTTP_MAX_RETRY", "3",
           "--config", "GDAL_HTTP_RETRY_DELAY", "2", "-overwrite",
           "-co", "COMPRESS=JPEG", "-co", "PHOTOMETRIC=YCBCR", "-co", "TILED=YES",
           str(xml), str(out)]
    print("  · 抓天地图影像（县范围）")
    subprocess.run(cmd, capture_output=True, text=True)
    if not out.exists():
        print("    ✗ 天地图抓取失败")
        return None
    return out


# ============ A 段: prep（GDAL，无需 QGIS）============
def prep_layers(county: str, work: Path, approved_names: list | None = None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    out = {k: work / f"{k}.geojson" for k in ("county", "reservoirs", "rivers", "mask")}
    for p in out.values():
        if p.exists():
            p.unlink()  # GeoJSON 驱动不覆盖，必先删

    print(f"[prep] {county} → {work}")

    # ① 县界: 乡镇境界 dissolve by COUNTY → 4549
    _run([OGR2OGR, "-t_srs", WORK_CRS, "-nln", "county", "-nlt", "MULTIPOLYGON",
          str(out["county"]), str(SRC_BOUNDARIES), "-dialect", "sqlite",
          "-sql", f'SELECT ST_Union(geometry) AS geometry, COUNTY '
                  f'FROM "{SRC_BOUNDARIES_LAYER}" WHERE COUNTY=\'{county}\' GROUP BY COUNTY'],
         "县界 dissolve")
    if feature_count(out["county"]) < 1:
        raise SystemExit(f"✗ SSOT 乡镇境界无 COUNTY='{county}'（检查县名是否带'县/市/区'后缀）")

    # ② 水库点: SZX filter → 4549
    _run([OGR2OGR, "-t_srs", WORK_CRS, "-nln", "reservoirs",
          str(out["reservoirs"]), str(SRC_RESERVOIRS), "-where", f"SZX='{county}'"],
         "水库点 SZX filter")

    # ③ 河流: 河流手册865 clip 到县界 → 4549
    _run([OGR2OGR, "-t_srs", WORK_CRS, "-nln", "rivers",
          str(out["rivers"]), str(SRC_RIVERS), "-clipsrc", str(out["county"])],
         "河流 clip")

    # ④ 蒙版: (县bbox+margin) − 县域 → 4549
    _run([OGR2OGR, "-t_srs", WORK_CRS, "-nln", "mask", "-nlt", "MULTIPOLYGON",
          str(out["mask"]), str(out["county"]), "-dialect", "sqlite",
          "-sql", f"SELECT ST_Difference(ST_Buffer(ST_Envelope(geometry), {MASK_OUTER_M}), "
                  f"geometry) AS geometry FROM county"],
         "蒙版 difference")

    # ⑤ 核定水库（红星）= 县水库按 GCMC 名筛出的子集
    out["approved"] = None
    if approved_names:
        ap = work / "approved.geojson"
        if ap.exists():
            ap.unlink()
        names = "','".join(n.strip() for n in approved_names if n.strip())
        _run([OGR2OGR, "-nln", "approved", str(ap), str(out["reservoirs"]),
              "-where", f"GCMC IN ('{names}')"], "核定水库 按名筛")
        n_ap = feature_count(ap)
        if n_ap < len(approved_names):
            print(f"    ⚠ 核定水库命中 {n_ap}/{len(approved_names)}（核对名是否与 SSOT GCMC 一致）")
        out["approved"] = ap if n_ap > 0 else None

    # ⑥ 双版面出图范围（竖 0.707 / 横 1.414）+ 天地图影像（抓两者并集，一次覆盖两版）
    cbbox = layer_extent(out["county"])
    ext_p = fit_to_aspect(cbbox, PAGE_W / PAGE_H)   # 竖
    ext_l = fit_to_aspect(cbbox, PAGE_H / PAGE_W)   # 横
    out["extent_portrait"] = ext_p
    out["extent_landscape"] = ext_l
    union = (min(ext_p[0], ext_l[0]), min(ext_p[1], ext_l[1]),
             max(ext_p[2], ext_l[2]), max(ext_p[3], ext_l[3]))
    out["basemap"] = fetch_basemap(union, work)

    print(f"[prep] ✓ 县界1 / 水库{feature_count(out['reservoirs'])} / "
          f"河流{feature_count(out['rivers'])} / 蒙版1 / "
          f"核定{feature_count(out['approved']) if out.get('approved') else 0} / "
          f"天地图{'✓' if out.get('basemap') else '✗'}")
    return out


# ============ B 段: render（PyQGIS headless）============
def render(county: str, layers: dict, hillshade: Path, out_png: Path,
           fig_no: str = "2", dem: Path | None = None):
    """一次 QGIS 会话出【竖 + 横】两版（out_png 派生 _竖/_横 后缀）。"""
    # —— QGIS bundle 环境（proj.db 必须先于 initQgis 设好，否则 EPSG:4549 不解析、矢量层全废）——
    prefix = os.environ.get("QGIS_PREFIX_PATH") or _detect_qgis_prefix()
    _res = os.path.join(os.path.dirname(prefix), "Resources", "qgis")
    for _pd in (os.path.join(_res, "proj"), "/opt/homebrew/share/proj"):
        if os.path.isdir(_pd):
            os.environ["PROJ_DATA"] = _pd
            os.environ["PROJ_LIB"] = _pd
            break
    os.environ.setdefault("GTIFF_SRS_SOURCE", "EPSG")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qgis.core import (
        QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer,
        QgsCoordinateReferenceSystem, QgsRectangle, QgsFillSymbol, QgsMarkerSymbol,
        QgsSingleSymbolRenderer, QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemPage,
        QgsLayoutItemScaleBar, QgsLayoutItemLegend, QgsLayoutItemLabel, QgsLayoutItemPicture,
        QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsLayoutExporter,
        QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer,
    )
    from qgis.PyQt.QtGui import QColor, QFont, QPainter
    from qgis.PyQt.QtCore import QPointF

    QgsApplication.setPrefixPath(prefix, True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        proj = QgsProject.instance()
        proj.setCrs(QgsCoordinateReferenceSystem(WORK_CRS))

        def vlayer(key, name):
            lyr = QgsVectorLayer(str(layers[key]), name, "ogr")
            if not lyr.isValid():
                raise RuntimeError(f"图层无效: {layers[key]}")
            lyr.setCrs(QgsCoordinateReferenceSystem(WORK_CRS))
            return lyr

        # —— 底图 = 官方天地图影像（prep 已抓为本地 tif）——
        # 县外用蒙版盖淡、县内露真影像（用户最终方案）。无 tif 时回退灰度晕渲。
        crs = QgsCoordinateReferenceSystem(WORK_CRS)
        terrain = []
        bm = layers.get("basemap")
        if bm and Path(bm).exists():
            base = QgsRasterLayer(str(bm), "天地图影像")
            base.setCrs(crs)
            if base.isValid():
                terrain = [base]
        if not terrain:
            print("  ⚠ 无天地图底图 tif，回退灰度晕渲")
            hs = QgsRasterLayer(str(hillshade), "晕渲")
            if hs.isValid():
                hs.setCrs(crs)
                terrain = [hs]
        county_l = vlayer("county", "县界")
        rivers_l = vlayer("rivers", "河流水系")
        mask_l = vlayer("mask", "蒙版")
        resv_l = vlayer("reservoirs", "水库工程")

        # —— 样式 ——
        rivers_l.setRenderer(QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple({"color": "108,172,214", "outline_color": "54,127,184",
                                        "outline_width": "0.2"})))
        mask_l.setRenderer(QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple({"color": "255,255,255,205", "outline_style": "no"})))
        county_l.setRenderer(QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "90,70,55",
                                        "outline_width": "0.35"})))
        resv_l.setRenderer(QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "31,119,180",
                                          "outline_color": "255,255,255",
                                          "outline_width": "0.3", "size": "2.4"})))
        # 水库名标注 GCMC
        pal = QgsPalLayerSettings()
        pal.fieldName = "GCMC"
        pal.enabled = True
        fmt = QgsTextFormat()
        fmt.setFont(QFont("PingFang SC"))
        fmt.setSize(7)
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.8)
        buf.setColor(QColor("white"))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)
        try:
            pal.placement = QgsPalLayerSettings.Placement.AroundPoint
        except AttributeError:
            pal.placement = QgsPalLayerSettings.AroundPoint
        resv_l.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        resv_l.setLabelsEnabled(True)

        # 核定水库（红五角星 + 红字）= prep 已按 GCMC 名筛出的 approved.geojson（县水库子集）
        src_l = None
        ap = layers.get("approved")
        if ap and Path(ap).exists():
            src_l = QgsVectorLayer(str(ap), "核定水库", "ogr")
            src_l.setCrs(crs)
            src_l.setRenderer(QgsSingleSymbolRenderer(
                QgsMarkerSymbol.createSimple({"name": "star", "color": "227,26,28",
                                              "outline_color": "120,0,0",
                                              "outline_width": "0.3", "size": "5.5"})))
            spal = QgsPalLayerSettings()
            spal.fieldName = "GCMC"
            spal.enabled = True
            sfmt = QgsTextFormat()
            sfmt.setFont(QFont("PingFang SC"))
            sfmt.setSize(8)
            sfmt.setColor(QColor(180, 0, 0))
            sbuf = QgsTextBufferSettings()
            sbuf.setEnabled(True)
            sbuf.setSize(0.9)
            sbuf.setColor(QColor("white"))
            sfmt.setBuffer(sbuf)
            spal.setFormat(sfmt)
            src_l.setLabeling(QgsVectorLayerSimpleLabeling(spal))
            src_l.setLabelsEnabled(True)

        # —— 入工程 —— QGIS 约定: 图层列表【首=最上层】。顶→底:
        # 源头红星 → 水库蓝点 → 县界线 → 河流蓝面 → 县外盖灰蒙版 → 绿色地形(晕渲+分层)
        draw = [l for l in (src_l, resv_l, county_l, rivers_l, mask_l) if l] + terrain
        for lyr in draw:
            proj.addMapLayer(lyr, False)
        root = proj.layerTreeRoot()
        for lyr in draw:
            root.addLayer(lyr)

        # —— 双版面：竖(0.707) + 横(1.414)，各出一张，满版 A4 ——
        # 版式：左上指北针 / 左下4项图例 / 右下比例尺 / 无标题(Word 当图注)。位置随页宽高 pw/ph 自适应。
        def build_and_export(orientation: str, suffix: str):
            landscape = (orientation == "landscape")
            pw, ph = (PAGE_H, PAGE_W) if landscape else (PAGE_W, PAGE_H)
            fb = layers.get("extent_landscape" if landscape else "extent_portrait")
            if fb:
                ext = QgsRectangle(fb[0], fb[1], fb[2], fb[3])
            else:
                ext = county_l.extent()
                ext.grow(MASK_MARGIN_M)

            layout = QgsPrintLayout(proj)
            layout.initializeDefaults()
            layout.pageCollection().page(0).setPageSize(
                QgsLayoutSize(pw, ph, QgsUnitTypes.LayoutMillimeters))

            m = QgsLayoutItemMap(layout)
            m.attemptMove(QgsLayoutPoint(0, 0, QgsUnitTypes.LayoutMillimeters))
            m.attemptResize(QgsLayoutSize(pw, ph, QgsUnitTypes.LayoutMillimeters))  # 满版出血
            m.setCrs(QgsCoordinateReferenceSystem(WORK_CRS))
            m.setExtent(ext)
            m.setFrameEnabled(False)
            m.setKeepLayerSet(True)
            m.setLayers(draw)
            layout.addLayoutItem(m)

            sb = QgsLayoutItemScaleBar(layout)         # 比例尺 右下
            sb.setStyle("Single Box")
            sb.setLinkedMap(m)
            sb.setUnits(QgsUnitTypes.DistanceKilometers)
            sb.setUnitsPerSegment(2.5)
            sb.setNumberOfSegments(5)
            sb.setNumberOfSegmentsLeft(0)
            sb.setUnitLabel("km")
            sb.update()
            sb.attemptMove(QgsLayoutPoint(pw - 70, ph - 14, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(sb)

            arrow = None                               # 指北针 左上
            for cand in ("NorthArrow_11.svg", "NorthArrow_02.svg"):
                p = os.path.join(os.path.dirname(prefix), "Resources", "qgis", "svg", "arrows", cand)
                if os.path.isfile(p):
                    arrow = p
                    break
            arrow = arrow or _find_north_arrow_svg()
            if arrow:
                na = QgsLayoutItemPicture(layout)
                na.setMode(QgsLayoutItemPicture.FormatSVG)
                na.setPicturePath(arrow)
                na.attemptResize(QgsLayoutSize(13, 24, QgsUnitTypes.LayoutMillimeters))
                na.attemptMove(QgsLayoutPoint(4, 4, QgsUnitTypes.LayoutMillimeters))
                layout.addLayoutItem(na)

            lg = QgsLayoutItemLegend(layout)           # 图例 左下（核定水库/水库工程/县界/河流水系）
            lg.setLinkedMap(m)
            lg.setAutoUpdateModel(False)
            lg.setBackgroundEnabled(True)
            lg.setBackgroundColor(QColor(255, 255, 255))
            keep = ("核定水库", "水库工程", "县界", "河流水系")
            rootg = lg.model().rootGroup()
            for child in list(rootg.children()):
                nm = child.name() if hasattr(child, "name") else ""
                if nm not in keep:
                    rootg.removeChildNode(child)
            lg.adjustBoxSize()
            lg.attemptMove(QgsLayoutPoint(2, ph - 39, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(lg)

            layout.setName(f"{county}水库工程位置分布图_{suffix}")
            proj.layoutManager().addLayout(layout)

            op = out_png.with_name(f"{out_png.stem}_{suffix}{out_png.suffix}")
            op.parent.mkdir(parents=True, exist_ok=True)
            exporter = QgsLayoutExporter(layout)
            img = QgsLayoutExporter.ImageExportSettings()
            img.dpi = 300
            img.generateWorldFile = False
            exporter.exportToImage(str(op), img)
            exporter.exportToPdf(str(op.with_suffix(".pdf")), QgsLayoutExporter.PdfExportSettings())
            print(f"[render] ✓ {op}")

        for orient, suffix in (("portrait", "竖"), ("landscape", "横")):
            build_and_export(orient, suffix)

        # 存 QGIS 工程（含竖+横两布局，GUI 调整用）
        qgz = Path(layers["county"]).parent / f"{county}_水库工程位置分布图.qgz"
        proj.write(str(qgz))
        print(f"[render] ✓ QGIS 工程: {qgz}")
    finally:
        qgs.exitQgis()


def _detect_qgis_prefix() -> str:
    import glob
    for app in sorted(glob.glob("/Applications/QGIS*.app"), reverse=True):
        c = f"{app}/Contents/MacOS"
        if os.path.isdir(c):
            return c
    raise SystemExit("✗ 找不到 QGIS.app；用 QGIS.app/Contents/MacOS/python 跑本脚本")


def _find_north_arrow_svg():
    from qgis.core import QgsApplication
    for base in QgsApplication.svgPaths():
        for rel in ("arrows/NorthArrow_02.svg", "arrows/NorthArrow_04.svg",
                    "wind_roses/WindRose_01.svg"):
            p = os.path.join(base, rel)
            if os.path.isfile(p):
                return p
    return None


def main():
    ap = argparse.ArgumentParser(description="县域水库工程位置分布图出图引擎")
    ap.add_argument("--county", required=True, help="完整县名，如 磐安县")
    ap.add_argument("--hillshade", default=str(DEFAULT_HILLSHADE), help="晕渲栅格 tif（4549）")
    ap.add_argument("--dem", default=None, help="DEM tif（4549）→ 绿色分层设色底图；缺省则灰度晕渲")
    ap.add_argument("--out", default=None, help="输出 PNG 路径（默认 output/maps/<县>_水库工程位置分布图.png）")
    ap.add_argument("--work", default=None, help="prep 中间层目录（默认 gis/basemaps/maps_work/<县>）")
    ap.add_argument("--fig-no", default="2", help="附图编号，默认 2")
    ap.add_argument("--approved", default=None,
                    help="核定水库红星：按 GCMC 名，逗号分隔，如 '岩弄口水库,狮子口水库'")
    ap.add_argument("--prep-only", action="store_true", help="只 prep 不出图（无需 QGIS）")
    a = ap.parse_args()

    approved = [n for n in a.approved.split(",")] if a.approved else None
    work = Path(a.work) if a.work else RESOURCES_GIS / "basemaps/maps_work" / a.county
    layers = prep_layers(a.county, work, approved_names=approved)
    if a.prep_only:
        print("[done] prep-only")
        return

    out_png = Path(a.out) if a.out else DEFAULT_OUT_ROOT / f"{a.county}_水库工程位置分布图.png"
    dem = Path(a.dem).resolve() if a.dem else None
    render(a.county, layers, Path(a.hillshade).resolve(), out_png,
           fig_no=a.fig_no, dem=dem)


if __name__ == "__main__":
    main()
