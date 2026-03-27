SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../pipeline" && pwd)"
PROJECT_FILE="${QGIS_DEFAULT_PROJECT:-$HOME/Downloads/zdwp/2025风险图/熟溪/shuxi.qgz}"

cd "$SCRIPT_DIR" && \
PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}" \
/Applications/QGIS.app/Contents/MacOS/QGIS \
--project "$PROJECT_FILE" \
--code "02_cut_dike_sections.py"
