#!/usr/bin/env bash
# 网页可视化控制台.command — macOS 双击直达浏览器图形化驾驶舱
# 博客：https://blog.caowo.de/  |  发卡网（仅提供 GPT 代充）：https://faka.cdkey.si/
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export LANG="${LANG:-zh_CN.UTF-8}"
export LC_ALL="${LC_ALL:-zh_CN.UTF-8}"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

printf '\033[8;28;110t' 2>/dev/null || true
printf '\033]0;Google AI Trial Web Studio · blog.caowo.de | faka.cdkey.si\007'
clear

"$DIR/trial.sh" --web

echo ""
echo "  📖 技术博客          : https://blog.caowo.de/"
echo "  🛒 发卡网 (GPT 代充) : https://faka.cdkey.si/"
echo ""
read -rp "  按回车键关闭窗口..." _ || true
