#!/usr/bin/env bash
# lib/theme-ui.sh — Personalized UI, ANSI theme, persona prompts, timers & preferences

GTOOL_CONF="${GTOOL_CONF:-$SCRIPT_DIR/.gtool.conf}"

# ===== Default Personalization Settings =====
GTOOL_USER_NAME="${GTOOL_USER_NAME:-Ethan}"
GTOOL_PERSONA="${GTOOL_PERSONA:-geek}"          # geek | minimal | coach
GTOOL_MOTTO="${GTOOL_MOTTO:-auto}"              # "auto" = smart rotating tips, or custom string
GTOOL_SOUND="${GTOOL_SOUND:-on}"                # on | off
GTOOL_DESKTOP_NOTIFY="${GTOOL_DESKTOP_NOTIFY:-off}" # on | off
GTOOL_FAST_ANIM="${GTOOL_FAST_ANIM:-on}"        # on | off (0x animation scale during UI automation)
GTOOL_BATCH_RESET="${GTOOL_BATCH_RESET:-smart}" # smart (pm clear + Play switch) | reinstall (Play download)
GTOOL_AUTO_CANCEL="${GTOOL_AUTO_CANCEL:-on}"    # on | off (auto-cancel renewal after batch trial)
GTOOL_POSTAL_MODE="${GTOOL_POSTAL_MODE:-classic}" # classic (92101/89101/33131) | taxfree (97201/19801/03101)

# Last-used action memory (non-sensitive metadata only)
GTOOL_LAST_MODE=""
GTOOL_LAST_SKU=""
GTOOL_LAST_OFFER=""
GTOOL_LAST_STACK="false"
GTOOL_LAST_LABEL=""
GTOOL_LAST_ACCOUNTS=""
GTOOL_LAST_CARDS=""

# ===== ANSI Color Palette (auto-disables when non-TTY or NO_COLOR set) =====
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_DIM=$'\033[2m'
    C_RED=$'\033[38;5;203m'
    C_GREEN=$'\033[38;5;84m'
    C_YELLOW=$'\033[38;5;221m'
    C_BLUE=$'\033[38;5;75m'
    C_CYAN=$'\033[38;5;87m'
    C_MAGENTA=$'\033[38;5;177m'
    C_GRAY=$'\033[38;5;245m'
    C_WHITE=$'\033[97m'
    BG_BADGE_FREE=$'\033[48;5;28;97;1m'
    BG_BADGE_PROMO=$'\033[48;5;136;97;1m'
    BG_BADGE_PAID=$'\033[48;5;240;97m'
else
    C_RESET="" C_BOLD="" C_DIM="" C_RED="" C_GREEN="" C_YELLOW=""
    C_BLUE="" C_CYAN="" C_MAGENTA="" C_GRAY="" C_WHITE=""
    BG_BADGE_FREE="" BG_BADGE_PROMO="" BG_BADGE_PAID=""
fi

# ===== Load & Save Preferences =====
load_gtool_conf() {
    if [[ -f "$GTOOL_CONF" ]]; then
        # shellcheck disable=SC1090
        source "$GTOOL_CONF" 2>/dev/null || true
    fi
}

save_gtool_conf() {
    local tmp_conf="${GTOOL_CONF}.tmp"
    (umask 077; cat > "$tmp_conf" <<EOF
# Google Trial Tool — 个性化配置文件 (自动生成，不含任何账号密码或卡号)
GTOOL_USER_NAME=$(printf '%q' "$GTOOL_USER_NAME")
GTOOL_PERSONA=$(printf '%q' "$GTOOL_PERSONA")
GTOOL_MOTTO=$(printf '%q' "$GTOOL_MOTTO")
GTOOL_SOUND=$(printf '%q' "$GTOOL_SOUND")
GTOOL_DESKTOP_NOTIFY=$(printf '%q' "$GTOOL_DESKTOP_NOTIFY")
GTOOL_FAST_ANIM=$(printf '%q' "$GTOOL_FAST_ANIM")
GTOOL_BATCH_RESET=$(printf '%q' "$GTOOL_BATCH_RESET")
GTOOL_AUTO_CANCEL=$(printf '%q' "$GTOOL_AUTO_CANCEL")
GTOOL_POSTAL_MODE=$(printf '%q' "$GTOOL_POSTAL_MODE")
GTOOL_LAST_MODE=$(printf '%q' "$GTOOL_LAST_MODE")
GTOOL_LAST_SKU=$(printf '%q' "$GTOOL_LAST_SKU")
GTOOL_LAST_OFFER=$(printf '%q' "$GTOOL_LAST_OFFER")
GTOOL_LAST_STACK=$(printf '%q' "$GTOOL_LAST_STACK")
GTOOL_LAST_LABEL=$(printf '%q' "$GTOOL_LAST_LABEL")
GTOOL_LAST_ACCOUNTS=$(printf '%q' "$GTOOL_LAST_ACCOUNTS")
GTOOL_LAST_CARDS=$(printf '%q' "$GTOOL_LAST_CARDS")
EOF
    ) && chmod 600 "$tmp_conf" 2>/dev/null && mv -f "$tmp_conf" "$GTOOL_CONF"
}

remember_last_action() {
    GTOOL_LAST_MODE="${1:-}"
    GTOOL_LAST_SKU="${2:-}"
    GTOOL_LAST_OFFER="${3:-}"
    GTOOL_LAST_STACK="${4:-false}"
    GTOOL_LAST_LABEL="${5:-}"
    save_gtool_conf
}

# ===== Persona-Aware Logging & Prompts =====
_STEP_START_MS=0

now_ms() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import time; print(int(time.time()*1000))' 2>/dev/null || echo $((SECONDS * 1000))
    else
        echo $((SECONDS * 1000))
    fi
}

step_begin() {
    _STEP_START_MS=$(now_ms)
    local title="$*"
    case "$GTOOL_PERSONA" in
        minimal)
            printf "%s▸ %s...%s\n" "$C_CYAN" "$title" "$C_RESET" >&2
            ;;
        coach)
            printf "%s%s▶ 正在执行：%s%s\n" "$C_BOLD" "$C_CYAN" "$title" "$C_RESET" >&2
            ;;
        *)
            printf "%s⚡ %s%s\n" "$C_CYAN" "$title" "$C_RESET" >&2
            ;;
    esac
}

step_end() {
    local now end_delta
    now=$(now_ms)
    if [[ $_STEP_START_MS -gt 0 && $now -ge $_STEP_START_MS ]]; then
        local diff=$((now - _STEP_START_MS))
        end_delta=$(awk "BEGIN {printf \"%.2fs\", $diff/1000}")
    else
        end_delta="done"
    fi
    _STEP_START_MS=0
    printf "%s✓ %s %s(%s)%s\n" "$C_GREEN" "$*" "$C_DIM" "$end_delta" "$C_RESET" >&2
}

log() {
    printf "%s[*]%s %s\n" "$C_BLUE" "$C_RESET" "$*"
}

ok() {
    printf "%s[+]%s %s\n" "$C_GREEN" "$C_RESET" "$*"
}

warn() {
    printf "%s[!]%s %s\n" "$C_YELLOW" "$C_RESET" "$*" >&2
}

err() {
    printf "%s[-]%s %s\n" "$C_RED" "$C_RESET" "$*" >&2
}

hint() {
    if [[ "$GTOOL_PERSONA" != "minimal" ]]; then
        printf "  %s💡 %s%s\n" "$C_DIM" "$*" "$C_RESET"
    fi
}

coach_tip() {
    if [[ "$GTOOL_PERSONA" == "coach" ]]; then
        printf "  %s🧭 向导提示：%s%s\n" "$C_YELLOW" "$*" "$C_RESET"
    fi
}

# ===== Sound & Desktop Notifications =====
notify_event() {
    local kind="${1:-info}"   # success | warn | error | attention
    local msg="${2:-}"

    if [[ "$GTOOL_SOUND" == "on" ]]; then
        if [[ -d "/System/Library/Sounds" ]] && command -v afplay >/dev/null 2>&1; then
            local snd="/System/Library/Sounds/Tink.aiff"
            case "$kind" in
                success)   snd="/System/Library/Sounds/Glass.aiff" ;;
                attention) snd="/System/Library/Sounds/Hero.aiff" ;;
                error)     snd="/System/Library/Sounds/Funk.aiff" ;;
                warn)      snd="/System/Library/Sounds/Pop.aiff" ;;
            esac
            [[ -f "$snd" ]] && (afplay "$snd" >/dev/null 2>&1 &) || true
        else
            printf '\a' || true
        fi
    fi

    if [[ "$GTOOL_DESKTOP_NOTIFY" == "on" && -n "$msg" ]] && command -v osascript >/dev/null 2>&1; then
        (osascript -e 'on run argv
display notification (item 1 of argv) with title "Google Trial Assistant"
end run' "$msg" >/dev/null 2>&1 &) || true
    fi
}

# ===== Time-Aware Greeting & Rotating Tips =====
_time_greeting() {
    local hour
    hour=$(date +%H 2>/dev/null || echo "12")
    hour=$((10#$hour))
    local who="${GTOOL_USER_NAME:+ $GTOOL_USER_NAME}"
    if (( hour >= 5 && hour < 12 )); then
        echo "早安${who} ☀️ 新的一天，祝把把丝滑秒过"
    elif (( hour >= 12 && hour < 18 )); then
        echo "下午好${who} ☕ 设备状态已就位，随时发车"
    elif (( hour >= 18 && hour < 23 )); then
        echo "晚上好${who} 🌙 引擎预热完毕，省时直达"
    else
        echo "夜深了${who} 🌌 夜猫模式开启，注意休息"
    fi
}

_active_motto() {
    if [[ -n "$GTOOL_MOTTO" && "$GTOOL_MOTTO" != "auto" ]]; then
        echo "$GTOOL_MOTTO"
        return
    fi
    local tips=(
        "安全红线：非 \$0 方案脚本只拉起收银台绝不自动点确认，严防误扣款"
        "白嫖秘籍：Pro 5TB 支持 [12月首开 → +6月叠加 → +6月叠加] 最高顺延 24 个月"
        "官方站点：技术博客 https://blog.caowo.de/ | GPT 代充发卡网 https://faka.cdkey.si/"
        "踩坑锦囊：付款成功但未显示容量？主菜单选 [4] → [2] 一键补单确认同步即可到账"
        "风控常识：Google Play 会校验卡头 BIN 国家与账号锁区一致，跨区报错请换同区卡"
        "丝滑操控：收银台拉起后无需重跑脚本，按 [r] 0.2秒重拉、[x] 一键取消续费"
    )
    local idx=$((RANDOM % ${#tips[@]}))
    echo "${tips[$idx]}"
}

# ===== Progress Bar Helper =====
render_progress_bar() {
    local current="${1:-0}"
    local total="${2:-1}"
    local width=24
    (( total <= 0 )) && total=1
    local filled=$(( current * width / total ))
    (( filled > width )) && filled=$width
    local empty=$(( width - filled ))
    local pct=$(( current * 100 / total ))
    local bar_f="" bar_e="" i
    for ((i=0; i<filled; i++)); do bar_f+="█"; done
    for ((i=0; i<empty; i++)); do bar_e+="░"; done
    printf "%s[%s%s]%s %3d%% (%d/%d)" "$C_CYAN" "$bar_f" "${C_GRAY}${bar_e}${C_CYAN}" "$C_RESET" "$pct" "$current" "$total"
}

# ===== Interactive Personalization Menu =====
customize_preferences_menu() {
    while true; do
        echo ""
        echo "${C_BOLD}${C_CYAN}╭──────────────────────────────────────────────────────────────────╮${C_RESET}"
        echo "${C_BOLD}${C_CYAN}│              ⚙️  个性化启动与交互提示词设置中心                   │${C_RESET}"
        echo "${C_BOLD}${C_CYAN}╰──────────────────────────────────────────────────────────────────╯${C_RESET}"
        echo ""
        printf "  ${C_BOLD}1.${C_RESET} 称呼昵称 (Operator Name)   : ${C_GREEN}%s${C_RESET}\n" "${GTOOL_USER_NAME:-未设置}"
        printf "  ${C_BOLD}2.${C_RESET} 提示词风格 (Persona Style) : ${C_GREEN}%s${C_RESET}  ${C_DIM}(geek=极客领航 | minimal=极简疾速 | coach=贴心向导)${C_RESET}\n" "$GTOOL_PERSONA"
        printf "  ${C_BOLD}3.${C_RESET} 启动个性签名/提示语        : ${C_GREEN}%s${C_RESET}  ${C_DIM}(auto=智能轮播锦囊)${C_RESET}\n" "$GTOOL_MOTTO"
        printf "  ${C_BOLD}4.${C_RESET} 音效提醒 (Sound Alert)     : ${C_GREEN}%s${C_RESET}  ${C_DIM}(成功/报错/待确认时播放提示音)${C_RESET}\n" "$GTOOL_SOUND"
        printf "  ${C_BOLD}5.${C_RESET} macOS 桌面横幅通知         : ${C_GREEN}%s${C_RESET}\n" "$GTOOL_DESKTOP_NOTIFY"
        printf "  ${C_BOLD}6.${C_RESET} 模拟器 0 动画极速加速      : ${C_GREEN}%s${C_RESET}  ${C_DIM}(大幅降低 uiautomator 等待耗时)${C_RESET}\n" "$GTOOL_FAST_ANIM"
        printf "  ${C_BOLD}7.${C_RESET} 批量模式 Google One 重置   : ${C_GREEN}%s${C_RESET}  ${C_DIM}(smart=清数据秒切[省45s] | reinstall=卸载重下)${C_RESET}\n" "$GTOOL_BATCH_RESET"
        printf "  ${C_BOLD}8.${C_RESET} 批量激活后自动取消续费     : ${C_GREEN}%s${C_RESET}\n" "$GTOOL_AUTO_CANCEL"
        printf "  ${C_BOLD}9.${C_RESET} 绑卡默认邮编策略           : ${C_GREEN}%s${C_RESET}  ${C_DIM}(classic=92101/89101/33131 | taxfree=免税州97201等)${C_RESET}\n" "$GTOOL_POSTAL_MODE"
        echo ""
        local p_choice="" v="" s="" m=""
        read -rp "  输入编号修改设置 (Enter/q 保存返回): " p_choice || p_choice="q"
        case "$p_choice" in
            ""|q|Q|0)
                save_gtool_conf
                ok "个性化设置已保存至 $GTOOL_CONF"
                return 0
                ;;
            1)
                read -rp "  输入新的称呼昵称 [${GTOOL_USER_NAME}]: " v || true
                [[ -n "$v" ]] && GTOOL_USER_NAME="$v"
                ;;
            2)
                echo "    1) geek    — 极客领航（默认：清晰步骤耗时 + 关键状态反馈）"
                echo "    2) minimal — 极简疾速（最少文字，适合高频老手）"
                echo "    3) coach   — 贴心向导（附带每步防坑提示与操作引导）"
                read -rp "  选择风格 [1-3]: " s || true
                case "$s" in
                    1|geek)    GTOOL_PERSONA="geek" ;;
                    2|minimal) GTOOL_PERSONA="minimal" ;;
                    3|coach)   GTOOL_PERSONA="coach" ;;
                esac
                ;;
            3)
                read -rp "  输入自定义启动标语 (输入 auto 恢复智能锦囊轮播): " m || true
                [[ -n "$m" ]] && GTOOL_MOTTO="$m"
                ;;
            4)
                [[ "$GTOOL_SOUND" == "on" ]] && GTOOL_SOUND="off" || GTOOL_SOUND="on"
                notify_event "success"
                ;;
            5)
                [[ "$GTOOL_DESKTOP_NOTIFY" == "on" ]] && GTOOL_DESKTOP_NOTIFY="off" || GTOOL_DESKTOP_NOTIFY="on"
                ;;
            6)
                [[ "$GTOOL_FAST_ANIM" == "on" ]] && GTOOL_FAST_ANIM="off" || GTOOL_FAST_ANIM="on"
                ;;
            7)
                [[ "$GTOOL_BATCH_RESET" == "smart" ]] && GTOOL_BATCH_RESET="reinstall" || GTOOL_BATCH_RESET="smart"
                ;;
            8)
                [[ "$GTOOL_AUTO_CANCEL" == "on" ]] && GTOOL_AUTO_CANCEL="off" || GTOOL_AUTO_CANCEL="on"
                ;;
            9)
                [[ "$GTOOL_POSTAL_MODE" == "classic" ]] && GTOOL_POSTAL_MODE="taxfree" || GTOOL_POSTAL_MODE="classic"
                ;;
            *)
                warn "无效选项: $p_choice"
                ;;
        esac
        save_gtool_conf
    done
}
