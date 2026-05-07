#!/bin/bash
#
# 县级 GIS 切片 wrapper
# 用法: bash scripts/cut_county.sh <县名> <输出目录>
#
# 示例:
#   bash scripts/cut_county.sh 天台县 /Users/tianli/Dev/Work/resources/gis/derived/county-slices/台州市/天台县
#   bash scripts/cut_county.sh 余杭区 /tmp/yuhang_test
#

set -e

# ============ 配置 ============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$(cd "${SCRIPT_DIR}/../pipeline" && pwd)"
CUT_SCRIPT="${PIPELINE_DIR}/14_cut_by_county.py"

# QGIS 二进制（用户机器是 QGIS-final-4_0_2.app）
QGIS_APP="/Applications/QGIS-final-4_0_2.app"
if [ ! -d "$QGIS_APP" ]; then
    QGIS_APP="/Applications/QGIS.app"
fi
QGIS_BIN="${QGIS_APP}/Contents/MacOS/QGIS-final-4_0_2"
[ -x "$QGIS_BIN" ] || QGIS_BIN="${QGIS_APP}/Contents/MacOS/QGIS"

# 优先用 QGIS bundled python 跑 headless（避免 GUI --code 模式的 stdout 缓冲问题）
QGIS_PYTHON="${QGIS_APP}/Contents/MacOS/python"
[ -x "$QGIS_PYTHON" ] || QGIS_PYTHON=""

# ============ 参数解析 ============
if [ -z "$1" ] || [ -z "$2" ]; then
    cat <<USAGE
❌ 错误: 参数不足

用法: $0 <县名> <输出目录>

示例:
  $0 天台县 /Users/tianli/Dev/Work/resources/gis/derived/county-slices/台州市/天台县
  $0 余杭区 /tmp/yuhang_test

输出 5 个 geojson:
  县界 / 河流 / 水库点 / 大中型水库 / 小水电
USAGE
    exit 1
fi

COUNTY_NAME="$1"
OUTPUT_DIR="$2"

# 校验脚本与 QGIS
if [ ! -f "$CUT_SCRIPT" ]; then
    echo "❌ 错误: 找不到切片脚本 ${CUT_SCRIPT}"
    exit 1
fi

if [ ! -x "$QGIS_BIN" ]; then
    echo "❌ 错误: 找不到 QGIS 二进制（尝试过 QGIS-final-4_0_2 和 QGIS）"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# ============ 退出码文件 ============
RC_FILE="$(mktemp -t cut_county_rc.XXXXXX)"
trap 'rm -f "$RC_FILE"' EXIT

# ============ 执行 ============
echo "════════════════════════════════════════════════════════"
echo "🚀 县级 GIS 切片器"
echo "════════════════════════════════════════════════════════"
echo "📍 县名: ${COUNTY_NAME}"
echo "📁 输出: ${OUTPUT_DIR}"
echo "🛠  QGIS: ${QGIS_BIN}"
echo "📜 脚本: ${CUT_SCRIPT}"
echo "⏰ 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════"
echo ""

export COUNTY_NAME OUTPUT_DIR
export CUT_COUNTY_RC_FILE="$RC_FILE"
export PYTHONPATH="${PIPELINE_DIR}:${PIPELINE_DIR}/../lib:${PIPELINE_DIR}/../_util:${PYTHONPATH}"

# QGIS bundled python 路径
export PYTHONHOME="${QGIS_APP}/Contents/Frameworks/Python.framework/Versions/Current"
export QGIS_PREFIX_PATH="${QGIS_APP}/Contents/MacOS"
export DYLD_FRAMEWORK_PATH="${QGIS_APP}/Contents/Frameworks"
export PROJ_LIB="${QGIS_APP}/Contents/Resources/qgis/proj"
export GDAL_DATA="${QGIS_APP}/Contents/Resources/qgis/gdal"

# QGIS 内置 python lib + processing 插件目录
QGIS_PY_LIB="${QGIS_APP}/Contents/Resources/qgis/python"
QGIS_PY_PLUGINS="${QGIS_APP}/Contents/Resources/qgis/python/plugins"
[ -d "$QGIS_PY_LIB" ] && export PYTHONPATH="${QGIS_PY_LIB}:${PYTHONPATH}"
[ -d "$QGIS_PY_PLUGINS" ] && export PYTHONPATH="${QGIS_PY_PLUGINS}:${PYTHONPATH}"

if [ -n "$QGIS_PYTHON" ]; then
    echo "🐍 用 QGIS bundled python (headless): $QGIS_PYTHON"
    "$QGIS_PYTHON" "$CUT_SCRIPT"
    QGIS_RC=$?
else
    echo "🖥  fallback 走 QGIS GUI --code 模式"
    "$QGIS_BIN" --code "$CUT_SCRIPT" --nologo --noversioncheck
    QGIS_RC=$?
fi

# 读 python 脚本写的退出码
PY_RC=0
if [ -f "$RC_FILE" ]; then
    PY_RC=$(cat "$RC_FILE" 2>/dev/null || echo 0)
fi

# ============ 验证输出 ============
echo ""
echo "════════════════════════════════════════════════════════"
echo "📊 输出文件清单"
echo "════════════════════════════════════════════════════════"

ALL_OK=1
shopt -s nullglob
GEOJSONS=("${OUTPUT_DIR}"/*.geojson)
shopt -u nullglob
if [ ${#GEOJSONS[@]} -eq 0 ]; then
    echo "  ❌ no .geojson 输出"
    ALL_OK=0
fi
for f in "${GEOJSONS[@]}"; do
    name="$(basename "$f" .geojson)"
    size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null)
    feat=$(/opt/homebrew/bin/python3 -c "
import json,sys
try:
    with open('$f','r') as fp:
        d=json.load(fp)
    print(len(d.get('features',[])))
except Exception as e:
    print(f'?({e})')
" 2>/dev/null || echo "?")
    printf "  ✅ %-12s  %8d bytes  features=%s\n" "$name" "$size" "$feat"
done

echo "════════════════════════════════════════════════════════"
if [ "$ALL_OK" = "1" ] && [ "$PY_RC" = "0" ]; then
    echo "✅ 全部输出存在 (qgis_rc=${QGIS_RC} py_rc=${PY_RC})"
    exit 0
else
    echo "⚠️  部分输出缺失或脚本报错 (qgis_rc=${QGIS_RC} py_rc=${PY_RC})"
    exit 1
fi
