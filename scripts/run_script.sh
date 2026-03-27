#!/bin/bash
#
# QGIS脚本命令行执行器
# 用法: ./run_script.sh <脚本名> [项目文件路径]
#
# 示例:
#   ./run_script.sh 01_generate_river_points.py
#   ./run_script.sh 01_generate_river_points.py /path/to/project.qgz
#

set -e  # 遇到错误立即退出

# ============ 配置区 ============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../pipeline" && pwd)"
DEFAULT_PROJECT="${QGIS_DEFAULT_PROJECT:-$HOME/Downloads/zdwp/2025风险图/熟溪/shuxi.qgz}"
QGIS_BIN="/Applications/QGIS.app/Contents/MacOS/QGIS"

# ============ 参数解析 ============
if [ -z "$1" ]; then
    echo "❌ 错误: 请提供脚本名称"
    echo ""
    echo "用法: $0 <脚本名> [项目文件]"
    echo ""
    echo "示例:"
    echo "  $0 01_generate_river_points.py"
    echo "  $0 02_cut_dike_sections.py"
    exit 1
fi

SCRIPT_NAME="$1"
SCRIPT_PATH="${SCRIPT_DIR}/${SCRIPT_NAME}"

# 检查脚本是否存在
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "❌ 错误: 找不到脚本 '${SCRIPT_PATH}'"
    exit 1
fi

# 使用指定的项目文件或默认项目
if [ -n "$2" ]; then
    PROJECT_FILE="$2"
else
    PROJECT_FILE="$DEFAULT_PROJECT"
fi

# 检查项目文件是否存在
if [ ! -f "$PROJECT_FILE" ]; then
    echo "❌ 错误: 找不到项目文件 '${PROJECT_FILE}'"
    exit 1
fi

# ============ 执行脚本 ============
echo "════════════════════════════════════════════════════════"
echo "🚀 QGIS脚本执行器"
echo "════════════════════════════════════════════════════════"
echo "📜 脚本: ${SCRIPT_NAME}"
echo "📁 项目: ${PROJECT_FILE}"
echo "⏰ 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════"
echo ""

# 设置Python路径并执行
cd "$SCRIPT_DIR"
PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}" \
"${QGIS_BIN}" \
    --project "${PROJECT_FILE}" \
    --code "${SCRIPT_PATH}" \
    --nologo \
    --noversioncheck

EXIT_CODE=$?

echo ""
echo "════════════════════════════════════════════════════════"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 脚本执行完成 (退出码: ${EXIT_CODE})"
else
    echo "❌ 脚本执行失败 (退出码: ${EXIT_CODE})"
fi
echo "════════════════════════════════════════════════════════"

exit $EXIT_CODE

