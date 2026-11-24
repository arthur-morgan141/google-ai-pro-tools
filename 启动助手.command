#!/usr/bin/env bash
# 启动助手.command — macOS 双击即用全彩方向键可视化控制台
# 博客：https://blog.caowo.de/  |  发卡网（仅提供 GPT 代充）：https://faka.cdkey.si/
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export LANG="${LANG:-zh_CN.UTF-8}"
export LC_ALL="${LC_ALL:-zh_CN.UTF-8}"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

# Auto-adjust Terminal window size to 122x34 so tables & dashboards never wrap
printf '\033[8;34;122t' 2>/dev/null || true
printf '\033]0;Google AI Trial Studio · 博客 blog.caowo.de | 发卡网 faka.cdkey.si\007'
clear

"$DIR/trial.sh"

echo ""
echo "  📖 技术博客          : https://blog.caowo.de/"
echo "  🛒 发卡网 (GPT 代充) : https://faka.cdkey.si/"
echo ""
read -rp "  按回车键关闭窗口..." _ || true
