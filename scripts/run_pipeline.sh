#!/bin/bash
# QGIS脚本批量运行工具
# 使用方法：./run_pipeline.sh [选项]
# 选项：all(全部) / 1-10(指定步骤) / 1-5(范围)

set -e  # 遇到错误立即退出

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../pipeline" && pwd)"
QGIS_APP="/Applications/QGIS.app/Contents/MacOS/QGIS"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查QGIS是否存在
if [ ! -f "$QGIS_APP" ]; then
    echo -e "${RED}❌ 错误: 找不到QGIS应用${NC}"
    echo "请修改脚本中的QGIS_APP路径"
    exit 1
fi

# 脚本列表（按执行顺序）
declare -a SCRIPTS=(
    "01_generate_river_points.py|生成河段中心点和切割点"
    "01.5_assign_lc_to_cross_sections.py|断面LC赋值+中心点高程插值"
    "02_cut_dike_sections.py|切割堤防生成堤段"
    "03_assign_elevation_to_dike.py|堤段赋值高程和市县信息"
    "04_align_dike_fields.py|对齐堤段字段（24字段）"
    "04.5_fix_river_name.py|修正河流名称（可选）"
    "05_enrich_grid_layer.py|增强网格图层"
    "06_generate_house_layer.py|生成房屋图层"
    "07_generate_road_layer.py|生成道路图层"
    "08_generate_vegetation_layer.py|生成植被图层"
    "09_align_output_fields.py|对齐输出字段"
    "10_generate_baohu_layer.py|生成保护对象层"
)

# 运行单个脚本
run_script() {
    local script_file=$1
    local description=$2
    local step_num=$3
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📍 步骤 ${step_num}: ${description}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "🔄 执行脚本: ${script_file}"
    echo ""
    
    # 执行脚本
    if "$QGIS_APP" --code "${SCRIPT_DIR}/${script_file}" --nologo --noversioncheck 2>&1 | tee /tmp/qgis_output.log; then
        echo ""
        echo -e "${GREEN}✅ 步骤 ${step_num} 完成${NC}"
        echo ""
        return 0
    else
        echo ""
        echo -e "${RED}❌ 步骤 ${step_num} 失败！${NC}"
        echo -e "${YELLOW}请检查错误信息并修复后重新运行${NC}"
        return 1
    fi
}

# 解析参数
parse_range() {
    local arg=$1
    
    if [ "$arg" == "all" ] || [ -z "$arg" ]; then
        echo "1-${#SCRIPTS[@]}"
    elif [[ $arg =~ ^[0-9]+$ ]]; then
        echo "$arg-$arg"
    elif [[ $arg =~ ^[0-9]+-[0-9]+$ ]]; then
        echo "$arg"
    else
        echo "error"
    fi
}

# 主函数
main() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         🚀 QGIS脚本批量运行工具 v1.0                       ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "📁 脚本目录: ${SCRIPT_DIR}"
    echo -e "🖥️  QGIS路径: ${QGIS_APP}"
    echo ""
    
    # 解析运行范围
    local range=$(parse_range "$1")
    
    if [ "$range" == "error" ]; then
        echo -e "${RED}❌ 错误: 无效的参数 '$1'${NC}"
        echo ""
        echo "使用方法："
        echo "  ./run_pipeline.sh           # 运行全部脚本"
        echo "  ./run_pipeline.sh all       # 运行全部脚本"
        echo "  ./run_pipeline.sh 1         # 运行第1个脚本"
        echo "  ./run_pipeline.sh 1-5       # 运行第1-5个脚本"
        echo ""
        exit 1
    fi
    
    # 提取开始和结束索引
    local start=$(echo $range | cut -d'-' -f1)
    local end=$(echo $range | cut -d'-' -f2)
    
    # 验证范围
    if [ $start -lt 1 ] || [ $start -gt ${#SCRIPTS[@]} ] || [ $end -lt 1 ] || [ $end -gt ${#SCRIPTS[@]} ]; then
        echo -e "${RED}❌ 错误: 脚本编号超出范围 (1-${#SCRIPTS[@]})${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}📋 将执行脚本 ${start}-${end}：${NC}"
    for i in $(seq $start $end); do
        local script_info="${SCRIPTS[$((i-1))]}"
        local script_file=$(echo "$script_info" | cut -d'|' -f1)
        local description=$(echo "$script_info" | cut -d'|' -f2)
        echo -e "   ${i}. ${description}"
    done
    echo ""
    
    # 确认执行
    read -p "是否继续？[Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
        echo -e "${YELLOW}❌ 已取消执行${NC}"
        exit 0
    fi
    
    echo ""
    echo -e "${GREEN}🚀 开始执行...${NC}"
    echo ""
    
    # 记录开始时间
    local start_time=$(date +%s)
    local success_count=0
    local fail_count=0
    
    # 执行脚本
    for i in $(seq $start $end); do
        local script_info="${SCRIPTS[$((i-1))]}"
        local script_file=$(echo "$script_info" | cut -d'|' -f1)
        local description=$(echo "$script_info" | cut -d'|' -f2)
        
        if run_script "$script_file" "$description" "$i"; then
            success_count=$((success_count + 1))
        else
            fail_count=$((fail_count + 1))
            echo -e "${RED}❌ 脚本执行失败，停止后续脚本${NC}"
            break
        fi
        
        # 短暂延迟，让QGIS完成保存
        sleep 2
    done
    
    # 记录结束时间
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # 输出总结
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    📊 执行总结                               ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "✅ 成功: ${GREEN}${success_count}${NC} 个脚本"
    echo -e "❌ 失败: ${RED}${fail_count}${NC} 个脚本"
    echo -e "⏱️  耗时: ${duration} 秒"
    echo ""
    
    if [ $fail_count -eq 0 ]; then
        echo -e "${GREEN}🎉 所有脚本执行成功！${NC}"
        echo ""
        echo -e "${YELLOW}💡 提示：${NC}"
        echo "   - 打开QGIS查看生成的图层（input/process/final组）"
        echo "   - 图层已自动保存到QGIS项目中"
        echo "   - 可使用 99_batch_export_layers.py 导出结果"
        echo ""
    else
        echo -e "${RED}⚠️  部分脚本执行失败，请检查错误信息${NC}"
        echo ""
    fi
}

# 显示可用脚本列表
show_list() {
    echo "可用脚本列表："
    echo ""
    for i in "${!SCRIPTS[@]}"; do
        local script_info="${SCRIPTS[$i]}"
        local script_file=$(echo "$script_info" | cut -d'|' -f1)
        local description=$(echo "$script_info" | cut -d'|' -f2)
        echo "  $((i+1)). ${script_file}"
        echo "     ${description}"
        echo ""
    done
}

# 命令行参数处理
case "$1" in
    -h|--help)
        echo "QGIS脚本批量运行工具"
        echo ""
        echo "使用方法："
        echo "  ./run_pipeline.sh [选项]"
        echo ""
        echo "选项："
        echo "  (空)          运行全部脚本"
        echo "  all           运行全部脚本"
        echo "  N             运行第N个脚本（如：1）"
        echo "  N-M           运行第N到M个脚本（如：1-5）"
        echo "  -l, --list    显示所有可用脚本"
        echo "  -h, --help    显示帮助信息"
        echo ""
        exit 0
        ;;
    -l|--list)
        show_list
        exit 0
        ;;
    *)
        main "$1"
        ;;
esac

