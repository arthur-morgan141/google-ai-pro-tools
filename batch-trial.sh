#!/usr/bin/env bash
# batch-trial.sh — Google AI Pro / Ultra 个性化全能启动器 (快捷预设 + 实时扫描 + 智能批量 + 诊断补单)
# 博客：https://blog.caowo.de/
# 发卡网（仅提供 GPT 代充）：https://faka.cdkey.si/
#
# 安全红线：注意不能发生真实大额扣款！非 $0 方案绝不自动点击订阅确认。

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    for _b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
        [[ -x "$_b" ]] && exec "$_b" "$0" "$@"
    done
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load theme & preferences BEFORE auto-trial.sh so colored loggers take effect everywhere
source "$SCRIPT_DIR/lib/theme-ui.sh"
load_gtool_conf

# Load core Frida & ADB helpers + modular libraries
source "$SCRIPT_DIR/auto-trial.sh"
source "$SCRIPT_DIR/lib/ui-helpers.sh"
source "$SCRIPT_DIR/lib/import-parse.sh"
source "$SCRIPT_DIR/lib/totp.sh"
source "$SCRIPT_DIR/lib/account-mgmt.sh"
source "$SCRIPT_DIR/lib/card-mgmt.sh"
source "$SCRIPT_DIR/lib/doctor.sh"
source "$SCRIPT_DIR/lib/presets.sh"

register_cleanup "stop_frida_oneshot"

# ===== Runtime CLI State =====
CLI_ACTION=""          # "" (interactive hub) | "quick" | "preset" | "batch" | "doctor" | "ack" | "cancel"
CLI_PRESET=""
ACCOUNT_FILE=""
CARD_FILE=""
CARD_MODE="rotate"     # rotate | single | embedded
RESULTS_LOG=""
RESUME_LOG=""
DRY_RUN=false
START_FROM=1
MAX_CONSECUTIVE_FAILS=5
COOLDOWN=3             # seconds between accounts

_require_batch_arg() {
    [[ $# -ge 2 && -n "${2:-}" ]] || die "参数 ${1:-} 缺少取值"
}

_parse_batch_args() {
    while [[ $# -gt 0 ]]; do
        case "${1:-}" in
            --quick|--browse)    CLI_ACTION="quick"; shift ;;
            --preset)            _require_batch_arg "$@"; CLI_ACTION="preset"; CLI_PRESET="${2:-}"; shift 2 ;;
            --doctor|--check)    CLI_ACTION="doctor"; shift ;;
            --ack|--sync)        CLI_ACTION="ack"; shift ;;
            --cancel)            CLI_ACTION="cancel"; shift ;;
            --batch)             CLI_ACTION="batch"; shift ;;
            --accounts)          _require_batch_arg "$@"; ACCOUNT_FILE="${2:-}"; shift 2 ;;
            --cards)             _require_batch_arg "$@"; CARD_FILE="${2:-}"; shift 2 ;;
            --card-mode)         _require_batch_arg "$@"; CARD_MODE="${2:-}"; shift 2 ;;
            --port)              _require_batch_arg "$@"; DEVICE_PORT="${2:-}"; shift 2 ;;
            --resume)            _require_batch_arg "$@"; RESUME_LOG="${2:-}"; shift 2 ;;
            --start-from)        _require_batch_arg "$@"; START_FROM="${2:-1}"; shift 2 ;;
            --max-failures)      _require_batch_arg "$@"; MAX_CONSECUTIVE_FAILS="${2:-5}"; shift 2 ;;
            --dry-run)           DRY_RUN=true; shift ;;
            --cooldown)          _require_batch_arg "$@"; COOLDOWN="${2:-3}"; shift 2 ;;
            --sku)               _require_batch_arg "$@"; TARGET_SKU="${2:-}"; shift 2 ;;
            --offer)             _require_batch_arg "$@"; TARGET_OFFER_ID="${2:-}"; shift 2 ;;
            --stack)             STACK_ENABLED="true"; shift ;;
            -h|--help)           _batch_usage; exit 0 ;;
            *)                   err "未知参数: ${1:-}"; _batch_usage; exit 1 ;;
        esac
    done
}

_batch_usage() {
    cat <<'EOF'
Google AI Pro / Ultra Trial Assistant — 全能交互启动器
📖 技术博客         : https://blog.caowo.de/
🛒 发卡网 (GPT代充) : https://faka.cdkey.si/

交互启动 (推荐):
  ./trial.sh                         打开个性化态势面板与主控菜单
  bash batch-trial.sh                同上（完全兼容）
  双击 启动助手.command              macOS 桌面一键启动

快捷单号命令:
  ./trial.sh --quick                 实时扫描当前账号所有方案并秒拉收银台
  ./trial.sh --preset pro12          一键拉起 Pro 5TB 12个月免费试用
  ./trial.sh --preset stack1         一键拉起 Pro 5TB +6个月免费叠加 (第2步→18月)
  ./trial.sh --preset stack2         一键拉起 Pro 5TB +6个月免费叠加 (第3步→24月)
  ./trial.sh --preset u1             一键拉起 Ultra 30TB 前3月1折 ($19.99/月)
  ./trial.sh --preset u2             一键拉起 Ultra 20TB 前3月1折 ($9.99/月)
  ./trial.sh --sku <SKU> [--stack]   按指定商品 ID 直接拉起收银台

诊断、补单与订阅管理:
  ./trial.sh --doctor                环境、Frida、Play商店与网络深度自检修复
  ./trial.sh --ack                   查询已购订阅并执行 Acknowledge 补单同步容量
  ./trial.sh --cancel                自动取消当前账号 Google One 订阅续费

批量跑号参数:
  --accounts <file>                  账号文件路径 (支持 ---- / | / CSV / 内嵌卡)
  --cards <file>                     卡片文件路径 (支持 号-MM/YY-CVV / 空格 / CSV)
  --card-mode <rotate|single>        卡片轮换或固定首张卡 [默认: rotate]
  --resume <logfile>                 断点续跑：跳过日志中已 OK 的账号
  --start-from <n>                   从第 n 个账号开始执行
  --port <port>                      指定 MuMu ADB 端口
  --dry-run                          仅校验解析账号与卡片文件，不执行设备操作
EOF
}

_already_done() {
    local email="${1:-}"
    [[ -z "$email" || -z "$RESUME_LOG" || ! -f "$RESUME_LOG" ]] && return 1
    $_GREP -q "^OK ${email} " "$RESUME_LOG" 2>/dev/null
}

# ===== Smart Checkout Confirmation (STRICT $0 Safety Guard!) =====
# Returns 0 when Subscribe button tapped (or manual paid confirmed), 1 on ineligible/error
confirm_checkout_sheet() {
    local expect_free="${1:-true}"
    log "正在检查收银台金额与试用资格..."

    if [[ "$expect_free" != "true" ]]; then
        # HARD SAFETY RULE: NEVER auto-tap Subscribe on paid/promo plans!
        wait_human_assist "付费方案收银台已弹出，请您亲自核对价格并在模拟器点击「订阅」" || return 1
        return 0
    fi

    local deadline=$((SECONDS + 18))
    while [[ $SECONDS -lt $deadline ]]; do
        local xml_file xml_content
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")

        # 1. Check ineligible dialog
        if $_GREP -iqE "不符合免费试用条件|not eligible for.*free trial" <<< "$xml_content"; then
            err "Google Play 提示：该账号不符合免费试用条件 (严谨拦截，绝不误点付费订阅)"
            tap_in_xml "$xml_file" "知道了" "OK" "Got it" "关闭" "Close" 2>/dev/null || press_back
            FRIDA_RESULT="INELIGIBLE"
            return 1
        fi

        # 2. Check already subscribed
        if $_GREP -iqE "您已订阅|already subscribed" <<< "$xml_content"; then
            warn "该账号已拥有此订阅"
            press_back
            FRIDA_RESULT="ITEM_ALREADY_OWNED"
            return 1
        fi

        # 3. Check transient offline warning on sheet
        if $_GREP -iqE "未连接到互联网|No internet connection" <<< "$xml_content"; then
            warn "收银台提示网络瞬断，尝试点击重试..."
            tap_in_xml "$xml_file" "重试" "Retry" 2>/dev/null || true
            sleep 1.5
            continue
        fi

        # 4. Verify $0 due today before tapping Subscribe CTA button!
        if $_GREP -iqE "订阅|Subscribe" <<< "$xml_content"; then
            local zero_ok
            zero_ok=$(python3 - "$xml_file" << 'PYEOF' 2>/dev/null || echo "WAIT"
import re, sys

with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
    raw = f.read()

texts = [m.group(1) for m in re.finditer(r'\b(?:text|content-desc)="([^"]+)"', raw)]
blob = " | ".join(texts)

if re.search(r"不符合免费试用条件|not eligible", blob, re.I):
    print("INELIGIBLE")
    sys.exit(0)

_CURR = r"(?:US\$|HK\$|NT\$|CA\$|A\$|S\$|NZ\$|JP¥|CN¥|¥|\$|£|€|₩|₹|₫|฿|₱|RM|CHF|R\$)"
_CODE = r"(?:USD|GBP|EUR|HKD|JPY|CAD|AUD|SGD|TWD|KRW|INR)"

# Look for explicit zero-cost trial indicators (negative lookahead prevents matching $0 inside $0.99!)
has_zero = bool(
    re.search(rf"{_CURR}\s*0(?:[.,]00)?(?![.,]?\d)", blob)
    or re.search(rf"(?<![.,\d])0(?:[.,]00)?(?![.,]?\d)\s*{_CODE}\b", blob)
    or re.search(r"(?:免费试用|Free trial|無料トライアル)", blob, re.I)
    or re.search(
        r"(?:即将扣款|今日应付|今日|Today|Due today)[^|]{0,14}(?:\|\s*)?(?:US\$|HK\$|NT\$|CA\$|JP¥|¥|\$|£|€)?\s*0(?:[.,]00)?(?![.,]?\d)",
        blob,
        re.I,
    )
)

# Check if "开始日期：今天 / Starting today" is immediately followed by any positive price (including sub-dollar $0.99!)
immediate_paid = bool(
    re.search(
        rf"(?:开始日期[：:]\s*今天|Starting today|Due today|今日应付|即将扣款\s*今天)\s*(?:\|\s*)?(?:{_CURR}\s*(?:[1-9][\d.,]*|0[.,]\d*[1-9]\d*)|(?:[1-9][\d.,]*|0[.,]\d*[1-9]\d*)\s*{_CODE}\b)",
        blob,
        re.I,
    )
)

# Check if any non-zero price (including 0.01..0.99) is rendered on the Subscribe sheet while zero is absent
any_nonzero_price = bool(
    re.search(
        rf"{_CURR}\s*(?:[1-9][\d.,]*|0[.,]\d*[1-9]\d*)|(?<!\d)(?:[1-9][\d.,]*|0[.,]\d*[1-9]\d*)\s*{_CODE}\b",
        blob,
    )
)

if immediate_paid:
    print("NON_ZERO")
elif has_zero:
    print("ZERO_OK")
elif any_nonzero_price:
    print("NON_ZERO")
else:
    print("WAIT")
PYEOF
)
            case "$zero_ok" in
                INELIGIBLE)
                    err "检测到不符合免费试用条件，已拦截点击"
                    press_back
                    FRIDA_RESULT="INELIGIBLE"
                    return 1
                    ;;
                NON_ZERO)
                    err "安全拦截：收银台今日应付金额不为 0，拒绝自动点击订阅！"
                    press_back
                    FRIDA_RESULT="PRICE_NOT_ZERO_BLOCKED"
                    return 1
                    ;;
                ZERO_OK)
                    ok "已核实今日扣款为 \$0 免费试用，正在点击「订阅」按钮..."
                    if tap_button_in_xml "$xml_file" "订阅" "Subscribe"; then
                        sleep 0.8
                        return 0
                    fi
                    ;;
            esac
        fi

        sleep 0.6
    done

    warn "未能自动确认收银台 \$0 按钮，请检查模拟器界面"
    return 1
}

# ===== Handle Billing Password Dialog (cached XML, fast poll) =====
handle_billing_password() {
    local password="${1:-}"
    [[ -z "$password" ]] && return 1
    log "监控 Google Play 密码验证框..."

    local i
    for ((i=0; i<22; i++)); do
        sleep 0.6
        local xml_file xml_content
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")

        # Purchase already completed without password?
        if $_GREP -iqE "付款成功|已订阅|payment.*success|subscribed|身份验证设置|备用付款" <<< "$xml_content"; then
            log "无需输入密码，已进入支付后流程"
            return 0
        fi

        local pw_node
        pw_node=$(echo "$xml_content" | $_GREP -oE '<node[^>]*password="true"[^>]*>' | head -1 || true)
        if [[ -z "$pw_node" ]] && echo "$xml_content" | $_GREP -iqE "confirm your identity|verify it.s you|确认您的身份|验证您的身份|忘记了密码|输入您的密码"; then
            sleep 0.4
            xml_file=$(dump_ui)
            xml_content=$(<"$xml_file")
            pw_node=$(echo "$xml_content" | $_GREP -oE '<node[^>]*password="true"[^>]*>' | head -1 || true)
        fi

        if [[ -n "$pw_node" ]]; then
            log "检测到密码验证弹窗，正在自动安全输入..."
            local pw_bounds
            pw_bounds=$(echo "$pw_node" | $_GREP -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' | sed 's/bounds="//;s/"//' || true)
            if [[ -n "$pw_bounds" ]]; then
                tap_bounds "$pw_bounds"
            else
                local eb
                eb=$(find_edit_text "$xml_file" 0 2>/dev/null || true)
                [[ -n "$eb" ]] && tap_bounds "$eb"
            fi
            sleep 0.25
            type_secret "$password"
            sleep 0.35

            if ! tap_button "验证" "Verify" "确定" "OK" "确认" "Confirm"; then
                tap_containing "Verify" "验证" "OK" "确定" "Confirm" "确认" 2>/dev/null || press_enter
            fi
            ok "密码已自动填入并提交确认"
            return 0
        fi
    done

    warn "未检测到密码弹窗（可能已免密通过或仍在加载）"
    return 1
}

# ===== Handle Post-Payment Dialogs (zero redundant dumps!) =====
handle_post_payment() {
    local deadline=$((SECONDS + 24))
    while [[ $SECONDS -lt $deadline ]]; do
        # Check if Frida already reported TRIAL_ACTIVATED!
        local lc
        lc=$("$ADB" -s "$DEVICE" logcat -d -s 'AutoTrial:I' 2>/dev/null || true)
        if [[ "$lc" == *"=== TRIAL_ACTIVATED ==="* ]]; then
            # Still dismiss any final UI confirmation once if visible, then return fast!
            local qxml
            qxml=$(dump_ui)
            tap_in_xml "$qxml" "不用了" "No thanks" "以后再说" "完成" "Done" "确定" "OK" "知道了" 2>/dev/null || true
            return 0
        fi

        local xml_file xml_content
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")

        # Auth settings dialog ("要启用购物身份验证设置吗？")
        if $_GREP -iq "身份验证设置\|authentication.*settings\|require.*authentication\|购物身份验证" <<< "$xml_content"; then
            log "处理购物身份验证设置弹窗（选择「不用了」）..."
            tap_exact_in_xml "$xml_file" "不用了" 2>/dev/null || tap_in_xml "$xml_file" "No thanks" "Not now" 2>/dev/null || true
            sleep 0.5
            tap_button "确定" "OK" "Done" 2>/dev/null || tap_exact "确定" 2>/dev/null || true
            sleep 0.6
            continue
        fi

        # Backup payment dialog ("开启备用付款方式？")
        if $_GREP -iq "备用付款\|backup.*payment\|add.*backup\|开启备用" <<< "$xml_content"; then
            log "关闭备用付款方式提示..."
            tap_in_xml "$xml_file" "以后再说" "不用了" "Not now" "No thanks" 2>/dev/null || press_back
            sleep 0.6
            continue
        fi

        # Play Points / promo dialog
        if $_GREP -iq "Play 积分\|Play Points" <<< "$xml_content"; then
            tap_in_xml "$xml_file" "以后再说" "Not now" 2>/dev/null || press_back
            sleep 0.6
            continue
        fi

        # Payment success / Subscribed confirmation
        if $_GREP -iq "付款成功\|payment.*success\|payment complete\|已订阅\|subscribed\|subscription.*active" <<< "$xml_content"; then
            tap_in_xml "$xml_file" "完成" "Done" "OK" "确定" "Got it" "知道了" 2>/dev/null || true
            sleep 0.5
            return 0
        fi

        sleep 0.6
    done
}

# ===== Cancel Subscription to Prevent Future Auto-Renewal =====
cancel_subscription() {
    step_begin "正在自动取消订阅续费（保留免费期权益，到期不扣款）"

    adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions'" >/dev/null
    sleep 1.4

    if ! wait_for_element 15 "订阅" "Subscriptions" "活跃" "Active" "Google One" "Google AI"; then
        err "未能加载 Play 订阅管理页"
        press_back
        return 1
    fi

    if ! tap_in_xml "$LAST_UI_FILE" "Google One" "Google AI"; then
        if ! tap_containing "Google One" "Google AI"; then
            err "订阅列表中未找到 Google One / Google AI 条目"
            press_back
            return 1
        fi
    fi
    sleep 1.0

    if ! wait_for_element 10 "取消订阅" "Cancel subscription"; then
        # Maybe already cancelled?
        local cxml
        cxml=$(<"${LAST_UI_FILE:-/dev/null}" 2>/dev/null || echo "")
        if $_GREP -iqE "已取消|Canceled|cancelled|将于.*到期|Expires" <<< "$cxml"; then
            step_end "该订阅已处于取消续费状态"
            press_back; press_back
            return 0
        fi
        err "未找到「取消订阅」按钮"
        press_back; press_back
        return 1
    fi

    tap_button_in_xml "$LAST_UI_FILE" "取消订阅" "Cancel subscription" || \
        tap_in_xml "$LAST_UI_FILE" "取消订阅" "Cancel subscription"
    sleep 1.0

    # Handle intermediate "暂停订阅 / 继续取消" retention offer if shown
    local xml_file xml_content
    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if $_GREP -iqE "暂停付款|Pause payments|继续取消|Continue|不用了，谢谢|No thanks" <<< "$xml_content"; then
        tap_button_in_xml "$xml_file" "不用了，谢谢" "No thanks" "继续" "Continue" "取消订阅" 2>/dev/null || \
            tap_in_xml "$xml_file" "不用了，谢谢" "No thanks" "继续" "Continue" 2>/dev/null || true
        sleep 1.0
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
    fi

    # Select cancellation reason if asked
    if $_GREP -iqE "原因|reason|拒绝回答|Prefer not to answer" <<< "$xml_content"; then
        if ! tap_in_xml "$xml_file" "拒绝回答" "Prefer not to answer" "其他" "Other" 2>/dev/null; then
            tap_in_xml "$xml_file" "请选择取消订阅的原因" "Select a reason" 2>/dev/null || true
            sleep 0.7
            tap_containing "拒绝回答" "Prefer not to answer" "其他" "Other" 2>/dev/null || true
        fi
        sleep 0.7
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
        tap_button_in_xml "$xml_file" "继续" "Continue" 2>/dev/null && {
            sleep 0.8
            xml_file=$(dump_ui)
            xml_content=$(<"$xml_file")
        }
    fi

    # Final confirm "取消订阅" CTA at bottom right
    if ! tap_button_in_xml "$xml_file" "取消订阅" "Cancel subscription"; then
        local cancel_bounds
        cancel_bounds=$(echo "$xml_content" | $_GREP -oE '<node[^>]*clickable="true"[^>]*bounds="\[[6-9][0-9][0-9],[0-9]+\]\[[0-9]+,[0-9]+\]"' | tail -1 | $_GREP -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' | sed 's/bounds="//;s/"//' || true)
        if [[ -n "$cancel_bounds" ]]; then
            tap_bounds "$cancel_bounds"
        else
            adb_tap_rel 73 95
        fi
    fi
    sleep 1.0

    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if $_GREP -iqE "已取消|Canceled|cancelled|将于|重新订阅|Resubscribe" <<< "$xml_content"; then
        step_end "自动续费已取消，免费期权益照常保留"
        press_back; press_back
        return 0
    fi

    err "未能自动确认取消状态，已保存截图供核查"
    take_screenshot "cancel_verify"
    press_back; press_back
    return 1
}

# ===== Wait for Final Purchase Callback from Live Frida =====
wait_for_final_result() {
    local timeout="${1:-35}"
    local ticks=$(( timeout * 2 ))
    local t=0

    while (( t < ticks )); do
        local output
        output=$("$ADB" -s "$DEVICE" logcat -d -s 'AutoTrial:I' 'AutoTrial:E' 2>/dev/null \
            | sed 's/^.*AutoTrial *: *//' || true)
        if [[ -n "$output" ]]; then
            if $_GREP -q "=== TRIAL_ACTIVATED ===" <<< "$output"; then
                # Give 0.4s for automatic acknowledgePurchase callback to complete too!
                sleep 0.4
                echo "TRIAL_ACTIVATED"
                return 0
            fi
            if $_GREP -q "=== PURCHASE_PENDING ===" <<< "$output"; then
                echo "PURCHASE_PENDING"; return 0
            fi
            if $_GREP -q "=== ITEM_ALREADY_OWNED ===" <<< "$output"; then
                echo "ITEM_ALREADY_OWNED"; return 0
            fi
            if $_GREP -q "=== USER_CANCELLED ===" <<< "$output"; then
                echo "USER_CANCELLED"; return 0
            fi
            local pfail
            pfail=$(echo "$output" | $_GREP "=== PURCHASE_FAILED" | tail -1 || true)
            if [[ -n "$pfail" ]]; then
                echo "$pfail"; return 0
            fi
        fi
        sleep 0.5
        t=$((t + 1))
    done

    echo "TIMEOUT"
    return 1
}

# ===== Install Google One from Play Store (when needed) =====
install_google_one() {
    if adb_shell "pm path $GOOGLE_ONE_PKG" | $_GREP -q "package:"; then
        ok "Google One 已安装"
        return 0
    fi

    step_begin "从 Google Play 商店安装 Google One"
    adb_shell "pm clear-cache com.android.vending" 2>/dev/null || true
    adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'market://details?id=$GOOGLE_ONE_PKG' || am start -a android.intent.action.VIEW -d 'market://details?id=$GOOGLE_ONE_PKG'" >/dev/null
    sleep 2.0

    local xml_file xml_content
    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if $_GREP -iq "仅此一次\|Just once\|始终\|Always" <<< "$xml_content"; then
        tap_in_xml "$xml_file" "仅此一次" "Just once" 2>/dev/null || true
        sleep 2.0
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
    fi

    if $_GREP -iq "Play Pass\|以后再说" <<< "$xml_content"; then
        tap_in_xml "$xml_file" "以后再说" "Not now" "No thanks" 2>/dev/null || true
        sleep 1.2
        xml_file=$(dump_ui)
    fi

    local installed=false
    if tap_button_in_xml "$xml_file" "安装" "Install"; then
        installed=true
    else
        log "直达详情页未见安装钮，切换 Play 商店搜索安装..."
        adb_shell "am start -n com.android.vending/.AssetBrowserActivity" >/dev/null
        sleep 2.0
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
        if $_GREP -iq "仅此一次\|Just once" <<< "$xml_content"; then
            tap_in_xml "$xml_file" "仅此一次" "Just once" 2>/dev/null || true
            sleep 2.0
            xml_file=$(dump_ui)
        fi
        if tap_in_xml "$xml_file" "搜索应用和游戏" "Search for apps" "Search" 2>/dev/null; then
            sleep 0.6
            type_text "Google One"
            sleep 0.4
            press_enter
            sleep 3.0
            if tap_button "安装" "Install"; then
                installed=true
            fi
        fi
    fi

    if ! $installed; then
        err "未能点击 Play 商店「安装」按钮"
        take_screenshot "install_no_btn"
        press_back
        return 1
    fi

    log "正在等待 Google One 下载并安装完成..."
    local deadline=$((SECONDS + 120))
    while [[ $SECONDS -lt $deadline ]]; do
        sleep 2.0
        if adb_shell "pm path $GOOGLE_ONE_PKG" | $_GREP -q "package:"; then
            step_end "Google One 安装成功"
            press_back
            return 0
        fi
    done

    err "Google One 下载安装超时"
    press_back
    return 1
}

# Smart Google One preparation per account (saves ~45s when smart mode is enabled!)
prepare_google_one_for_account() {
    local email="${1:-}"
    if [[ "${GTOOL_BATCH_RESET:-smart}" == "reinstall" ]]; then
        adb_shell "pm uninstall $GOOGLE_ONE_PKG" >/dev/null 2>&1 || true
        sleep 0.5
        install_google_one
        return $?
    fi

    # Smart fast mode: if installed, wipe app data (0.2s!) + switch Play Store active account!
    if adb_shell "pm path $GOOGLE_ONE_PKG" | $_GREP -q "package:"; then
        step_begin "极速重置 Google One 数据并同步 Play 账号"
        adb_shell "pm clear $GOOGLE_ONE_PKG" >/dev/null 2>&1 || true
        switch_play_account "$email"
        step_end "极速切号与数据清理完成 (省去 60MB 重复下载)"
        return 0
    else
        install_google_one
        return $?
    fi
}

# ===== Interactive Smart File Picker =====
_prompt_file_smart() {
    local var_name="${1:-}"
    local label="${2:-文件路径}"
    local default_path="${3:-}"
    [[ -n "$var_name" ]] || return 1
    local current="${!var_name:-}"

    if [[ -n "$current" ]]; then
        current=$(normalize_path_input "$current")
        if [[ -f "$current" ]]; then
            eval "$var_name=$(printf '%q' "$current")"
            return 0
        fi
    fi

    local discovered=()
    while IFS= read -r f; do
        [[ -n "$f" ]] && discovered+=("$f")
    done < <(discover_data_files)

    if (( ${#discovered[@]} > 0 )); then
        echo "  ${C_DIM}📂 自动发现附近的候选文件（可直接输入编号，或拖入任意文件）：${C_RESET}"
        local idx
        for idx in "${!discovered[@]}"; do
            local dp="${discovered[$idx]}"
            local short_dp="${dp/#$HOME/\~}"
            printf "    ${C_CYAN}[%d]${C_RESET} %s\n" "$((idx+1))" "$short_dp"
        done
    fi

    while true; do
        local prompt_str="  ${label}"
        if [[ -n "$default_path" && -f "$default_path" ]]; then
            prompt_str+=" [${default_path/#$HOME/\~}]"
        fi
        prompt_str+=": "

        local input=""
        read -rp "$prompt_str" input
        if [[ -z "$input" && -n "$default_path" && -f "$default_path" ]]; then
            input="$default_path"
        elif [[ "$input" =~ ^[0-9]+$ ]] && (( input >= 1 && input <= ${#discovered[@]} )); then
            input="${discovered[$((input-1))]}"
        fi

        input=$(normalize_path_input "$input")
        if [[ -z "$input" ]]; then
            err "请输入有效路径、候选编号，或直接将文件拖入终端窗口"
            continue
        fi
        if [[ ! -f "$input" ]]; then
            err "文件不存在: $input"
            continue
        fi
        eval "$var_name=$(printf '%q' "$input")"
        return 0
    done
}

# ===== Mode 2: Live Scan & Instant Launch on Current Device =====
quick_browse_main() {
    detect_device
    setup_frida
    ensure_vending_ready

    local cur_account
    cur_account=$(list_google_accounts | head -1 || true)
    if [[ -z "$cur_account" ]]; then
        err "当前模拟器未登录任何 Google 账号，请先在模拟器登录账号"
        read -rp "  按回车返回..." _ || true
        return 1
    fi

    echo ""
    ok "当前设备: $DEVICE  |  当前账号: ${C_BOLD}$cur_account${C_RESET}"
    coach_tip "常驻计费会话：输入序号后 0.2 秒弹出收银台，无需二次重启 Google One！"

    if [[ -n "$TARGET_SKU" ]]; then
        remember_last_action "sku" "$TARGET_SKU" "$TARGET_OFFER_ID" "$STACK_ENABLED" "SKU: $TARGET_SKU"
        if ! start_live_frida_session; then
            err "计费引擎启动未成功，请检查上方诊断信息"
            read -rp "  按回车返回..." _ || true
            return 1
        fi
        local cmd="LAUNCH_SKU|${TARGET_SKU}|${TARGET_OFFER_ID}"
        if [[ "$STACK_ENABLED" == "true" ]]; then
            local otok=""
            otok=$(read_play_library_token "subs_variant" || read_play_library_token "g1." || echo "")
            cmd="STACK_OFFER|${TARGET_SKU}|${TARGET_OFFER_ID}|${otok}|5"
        fi
        interactive_checkout_cockpit "$cmd" "$TARGET_SKU" "true" || true
        return 0
    fi

    if [[ -n "${LIVE_FRIDA_PID:-}" ]] && kill -0 "$LIVE_FRIDA_PID" 2>/dev/null; then
        log "常驻引擎在线，正在实时重扫当前账号全部 SKU..."
        send_live_frida_cmd "REFRESH"
        _wait_live_frida_event "INTERACTIVE_READY" 18 || true
    elif ! start_live_frida_session; then
        err "计费引擎扫描未成功，请查看上方诊断信息（可在工具箱 [4] 执行一键体检自愈）"
        read -rp "  按回车返回主菜单..." _ || true
        return 1
    fi

    if (( OFFER_COUNT == 0 )); then
        warn "Google Play 返回了 0 个可用订阅方案（请确认已点开过一次 Play 商店同意条款且网络畅通）"
        local retry_ans=""
        read -rp "  输入 r 自动唤醒 Play 商店并重新扫描，或按回车返回: " retry_ans || true
        if [[ "$retry_ans" == "r" || "$retry_ans" == "R" ]]; then
            switch_play_account "$cur_account"
            _cleanup_live_frida
            start_live_frida_session || true
        fi
        if (( OFFER_COUNT == 0 )); then
            return 1
        fi
    fi

    while true; do
        display_offer_menu
        local choice=""
        read -rp "  输入方案序号立即拉起 (1-$OFFER_COUNT, r=重新扫描, q=返回): " choice || choice="q"
        case "$choice" in
            q|Q)
                _cleanup_live_frida
                return 0
                ;;
            r|R)
                log "⚡ 正在重新动态扫描全部 SKU..."
                send_live_frida_cmd "REFRESH"
                _wait_live_frida_event "INTERACTIVE_READY" 18 || true
                continue
                ;;
        esac

        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= OFFER_COUNT )); then
            local sel_idx=$((choice - 1))
            local sel_prod="${OFFER_PRODUCT[$sel_idx]}"
            local sel_oid="${OFFER_OFFERID[$sel_idx]}"
            local sel_name="${OFFER_NAME[$sel_idx]}"
            local sel_type="${OFFER_TYPE[$sel_idx]}"
            local sel_price="${OFFER_PRICE[$sel_idx]}"
            local is_paid="false"

            if [[ "$sel_type" != "TRIAL" ]]; then
                is_paid="true"
                echo ""
                echo "  ${C_YELLOW}⚠️  注意：您选中的是付费订阅方案 ($sel_type: $sel_price)，不是 \$0 免费试用！${C_RESET}"
                local confirm=""
                read -rp "  确认拉起收银台？(Enter/y=确认, n=重选): " confirm || confirm="n"
                [[ "$confirm" == "n" || "$confirm" == "N" ]] && continue
            fi

            remember_last_action "offer" "$sel_prod" "$sel_oid" "false" "$sel_name ($sel_oid)"
            local rc=0
            interactive_checkout_cockpit "LAUNCH_OFFER|${sel_prod}|${sel_oid}" "#$choice $sel_name ($sel_oid)" "$is_paid" || rc=$?
            if [[ $rc -eq 2 ]]; then
                continue
            fi
            return 0
        else
            warn "请输入 1 到 $OFFER_COUNT 之间的有效数字"
        fi
    done
}

# ===== Mode 3: Smart Automated Batch Pipeline =====
batch_pipeline_main() {
    echo ""
    echo "${C_BOLD}${C_CYAN}╭──────────────────────────────────────────────────────────────────────╮${C_RESET}"
    echo "${C_BOLD}${C_CYAN}│           📦  多账号全自动批量激活流水线 (Smart Batch Mode)          │${C_RESET}"
    echo "${C_BOLD}${C_CYAN}├──────────────────────────────────────────────────────────────────────┤${C_RESET}"
    echo "│  支持格式：email----pass[----2fa][----recovery][----card-exp-cvv]    │"
    echo "│  安全保障：非 \$0 试用严格拦截自动点击；激活后可自动取消续费防扣款    │"
    echo "│  技术博客: https://blog.caowo.de/ | GPT代充: https://faka.cdkey.si/  │"
    echo "${C_BOLD}${C_CYAN}╰──────────────────────────────────────────────────────────────────────╯${C_RESET}"
    echo ""

    # Step 1: Account file
    echo "${C_BOLD}── Step 1/5: 选择账号文件 ──${C_RESET}"
    _prompt_file_smart ACCOUNT_FILE "账号文件路径或编号" "${GTOOL_LAST_ACCOUNTS:-}"
    parse_account_file "$ACCOUNT_FILE"
    GTOOL_LAST_ACCOUNTS="$ACCOUNT_FILE"
    save_gtool_conf
    echo ""

    # Step 2: Confirm parsed accounts
    echo "${C_BOLD}── Step 2/5: 核对账号解析结果 (${#ACCOUNTS_EMAIL[@]} 个) ──${C_RESET}"
    local preview_max=${#ACCOUNTS_EMAIL[@]}
    (( preview_max > 15 )) && preview_max=15
    echo "  ┌─────┬──────────────────────────────────┬──────┬──────────┬────────┐"
    echo "  │  #  │ Email                            │ 2FA  │ 辅助邮箱 │ 内嵌卡 │"
    echo "  ├─────┼──────────────────────────────────┼──────┼──────────┼────────┤"
    local i
    for ((i=0; i<preview_max; i++)); do
        local em="${ACCOUNTS_EMAIL[$i]}"
        local f2="—" frec="—" fcard="—"
        [[ -n "${ACCOUNTS_2FA[$i]}" ]] && f2="✓"
        [[ -n "${ACCOUNTS_RECOVERY[$i]}" ]] && frec="✓"
        [[ -n "${ACCOUNTS_CARD_NUM[$i]}" ]] && fcard="✓"
        printf "  │ %3d │ %-32s │  %s   │    %s     │   %s    │\n" "$((i+1))" "${em:0:32}" "$f2" "$frec" "$fcard"
    done
    if (( ${#ACCOUNTS_EMAIL[@]} > preview_max )); then
        printf "  │ ... │ 其余 %d 个账号已省略预览          │      │          │        │\n" "$(( ${#ACCOUNTS_EMAIL[@]} - preview_max ))"
    fi
    echo "  └─────┴──────────────────────────────────┴──────┴──────────┴────────┘"
    local fmt_ok=""
    read -rp "  解析格式无误？(Enter=继续, q=取消): " fmt_ok || fmt_ok="q"
    [[ "$fmt_ok" == "q" || "$fmt_ok" == "Q" ]] && return 0
    echo ""

    # Step 3: Card file (optional if all accounts already carry embedded cards!)
    echo "${C_BOLD}── Step 3/5: 配置付款卡片 ──${C_RESET}"
    if (( EMBEDDED_CARD_COUNT == ${#ACCOUNTS_EMAIL[@]} )) && [[ -z "$CARD_FILE" ]]; then
        ok "检测到所有账号均已内嵌专属卡片，默认采用账号内嵌卡！"
        CARD_MODE="embedded"
    else
        _prompt_file_smart CARD_FILE "卡片文件路径或编号" "${GTOOL_LAST_CARDS:-}"
        parse_card_file "$CARD_FILE"
        GTOOL_LAST_CARDS="$CARD_FILE"
        save_gtool_conf
    fi
    validate_imports
    check_totp_tools
    echo ""

    if $DRY_RUN; then
        ok "DRY RUN 预览校验通过：共 ${#ACCOUNTS_EMAIL[@]} 个账号，未执行任何模拟器操作。"
        return 0
    fi

    # Auto-detect resumable log if RESUME_LOG not explicitly set
    if [[ -z "$RESUME_LOG" ]]; then
        local latest_log
        latest_log=$(ls -1t "$SCRIPT_DIR"/results_*.log 2>/dev/null | head -1 || true)
        if [[ -n "$latest_log" ]] && $_GREP -q "^OK " "$latest_log" 2>/dev/null; then
            local done_n
            done_n=$($_GREP -c "^OK " "$latest_log" 2>/dev/null || echo 0)
            local r_ans=""
            read -rp "  检测到上次记录 $(basename "$latest_log") (已成功 $done_n 个)，是否断点续跑跳过已成功账号？[Y/n]: " r_ans || true
            if [[ "$r_ans" != "n" && "$r_ans" != "N" ]]; then
                RESUME_LOG="$latest_log"
                ok "已启用断点续跑: $RESUME_LOG"
            fi
        fi
    fi

    # Step 4: Card Mode & Reset Strategy
    if [[ "$CARD_MODE" != "embedded" ]] && (( ${#CARDS_NUMBER[@]} > 1 )); then
        echo "${C_BOLD}── Step 4/5: 卡片分配方式 ──${C_RESET}"
        echo "  1) rotate — 轮换分配，每个账号依次使用下一张卡 (默认)"
        echo "  2) single — 固定使用第 1 张卡"
        local cm_ans=""
        read -rp "  选择 [1]: " cm_ans || true
        [[ "$cm_ans" == "2" || "$cm_ans" == "single" ]] && CARD_MODE="single" || CARD_MODE="rotate"
        echo ""
    fi

    # Step 5: Connect device & select target plan
    echo "${C_BOLD}── Step 5/5: 连接模拟器与选择目标套餐 ──${C_RESET}"
    detect_device
    setup_frida
    ensure_vending_ready
    enable_fast_animations

    local sel_name="" sel_type="TRIAL" sel_price="\$0" batch_launch_mode="launch_offer"

    if [[ -n "$TARGET_SKU" ]]; then
        sel_name="$TARGET_SKU"
        sel_type="PROMO"
        sel_price="(以收银台为准)"
        batch_launch_mode="launch_sku"
    else
        echo ""
        echo "  请选择批量执行的目标方案确定方式："
        echo "    ${C_BOLD}1)${C_RESET} ⚡ 直接从热门预设中选择（无需先切第1个号查询，省时 40 秒！）"
        echo "    ${C_BOLD}2)${C_RESET} 🔍 先登录第 1 个账号实时扫描所有可用方案再选择"
        local plan_way=""
        read -rp "  选择 [1]: " plan_way || true
        if [[ "${plan_way:-1}" != "2" ]]; then
            show_presets_menu
            local p_pick=""
            read -rp "  输入预设编号 (1-10): " p_pick
            resolve_preset_choice "$p_pick" || die "无效的预设编号: $p_pick"
            sel_name="$PRESET_LABEL"
            STACK_ENABLED="$PRESET_STACK"
            if [[ "$PRESET_IS_PAID" == "true" ]]; then
                sel_type="PROMO"
                sel_price="(特惠付费，每号暂停由人工点确认)"
                TARGET_SKU="$PRESET_SKU"
                TARGET_OFFER_ID="$PRESET_OFFER"
                batch_launch_mode="launch_sku"
            elif [[ "$PRESET_SKU" == "auto" ]]; then
                sel_type="TRIAL"
                TARGET="auto"
                DURATION="longest"
                batch_launch_mode="activate"
            else
                sel_type="TRIAL"
                TARGET="$PRESET_SKU"
                TARGET_OFFER_ID="$PRESET_OFFER"
                batch_launch_mode="launch_offer"
            fi
        else
            # Switch to first account to browse exact live offers
            local first_email="${ACCOUNTS_EMAIL[0]}"
            local first_pass="${ACCOUNTS_PASS[0]}"
            local first_totp="${ACCOUNTS_2FA[0]}"
            export RECOVERY_EMAIL="${ACCOUNTS_RECOVERY[0]:-}"

            log "正在登录第 1 个账号 ($first_email) 以扫描可用套餐..."
            remove_all_accounts || die "无法移除旧账号，请先检查模拟器设置"
            add_google_account "$first_email" "$first_pass" "$first_totp" || die "第 1 个账号登录失败"
            prepare_google_one_for_account "$first_email" || die "Google One 准备失败"

            local b_pid
            b_pid=$(ensure_google_one_pid "true")
            run_frida_oneshot "$b_pid" "browse" "-1" "false"
            [[ "$FRIDA_RESULT" != "BROWSE_COMPLETE" || $OFFER_COUNT -eq 0 ]] && die "未能获取方案列表: $FRIDA_RESULT"

            display_offer_menu
            local choice=""
            while true; do
                read -rp "  输入方案序号 (1-$OFFER_COUNT, q=取消): " choice
                [[ "$choice" == "q" || "$choice" == "Q" ]] && return 0
                if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= OFFER_COUNT )); then
                    break
                fi
                warn "请输入 1-$OFFER_COUNT"
            done
            SELECTED_INDEX=$((choice - 1))
            sel_name="${OFFER_NAME[$SELECTED_INDEX]}"
            sel_type="${OFFER_TYPE[$SELECTED_INDEX]}"
            sel_price="${OFFER_PRICE[$SELECTED_INDEX]}"
            TARGET="${OFFER_PRODUCT[$SELECTED_INDEX]}"
            TARGET_OFFER_ID="${OFFER_OFFERID[$SELECTED_INDEX]}"
            batch_launch_mode="launch_offer"
        fi
    fi

    if [[ "$sel_type" != "TRIAL" ]]; then
        echo ""
        echo "  ${C_YELLOW}⚠️  注意：当前所选为付费方案【$sel_name】！${C_RESET}"
        echo "  ${C_YELLOW}⚠️  为严防误扣款，每个账号拉起收银台后都会暂停由您手动点击订阅。${C_RESET}"
        local paid_ok=""
        read -rp "  确认继续批量执行？(yes/no): " paid_ok || paid_ok="no"
        [[ "$paid_ok" != "yes" ]] && return 0
    fi

    echo ""
    echo "${C_BOLD}${C_CYAN}╭────────────────────────── 🚀 准备发车确认 ──────────────────────────╮${C_RESET}"
    printf "│  账号总数 : %-6d         卡片模式 : %-28s │\n" "${#ACCOUNTS_EMAIL[@]}" "$CARD_MODE"
    printf "│  目标方案 : %-52s │\n" "${sel_name:0:52}"
    printf "│  重置策略 : %-14s 自动取消 : %-28s │\n" "$GTOOL_BATCH_RESET" "$GTOOL_AUTO_CANCEL"
    echo "${C_BOLD}${C_CYAN}╰─────────────────────────────────────────────────────────────────────╯${C_RESET}"
    local go_btn=""
    read -rp "  按 [Enter] 立即开始批量流水线 (q=取消): " go_btn || go_btn="q"
    [[ "$go_btn" == "q" || "$go_btn" == "Q" ]] && return 0

    RESULTS_LOG="$SCRIPT_DIR/results_$(date +%Y%m%d_%H%M%S).log"
    (umask 077; echo "# Batch started $(date) | plan=$sel_name" > "$RESULTS_LOG")
    chmod 600 "$RESULTS_LOG" 2>/dev/null || true
    log "实时结果日志: $RESULTS_LOG"

    local card_index=0 success_count=0 fail_count=0 skip_count=0 consecutive_fails=0
    local batch_start_ts=$SECONDS
    local total_accts=${#ACCOUNTS_EMAIL[@]}
    local i

    for ((i=0; i<total_accts; i++)); do
        local acct_num=$((i + 1))
        local email="${ACCOUNTS_EMAIL[$i]}"
        local password="${ACCOUNTS_PASS[$i]}"
        local totp_secret="${ACCOUNTS_2FA[$i]}"
        export RECOVERY_EMAIL="${ACCOUNTS_RECOVERY[$i]:-}"

        (( acct_num < START_FROM )) && continue

        if _already_done "$email"; then
            log "跳过已完成账号: $email"
            skip_count=$((skip_count + 1))
            continue
        fi

        local card_num="" card_exp="" card_cvv=""
        if [[ -n "${ACCOUNTS_CARD_NUM[$i]:-}" ]]; then
            card_num="${ACCOUNTS_CARD_NUM[$i]}"
            card_exp="${ACCOUNTS_CARD_EXP[$i]}"
            card_cvv="${ACCOUNTS_CARD_CVV[$i]}"
        else
            card_num="${CARDS_NUMBER[$card_index]}"
            card_exp="${CARDS_EXPIRY[$card_index]}"
            card_cvv="${CARDS_CVV[$card_index]}"
        fi

        echo ""
        echo "${C_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
        printf "  %s\n" "$(render_progress_bar "$acct_num" "$total_accts")"
        echo "  👤 账号: ${C_BOLD}$email${C_RESET}  |  💳 卡片: ••••${card_num: -4}  |  🎯 方案: $sel_name"
        echo "${C_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"

        if (( consecutive_fails >= MAX_CONSECUTIVE_FAILS )); then
            err "连续失败达到上限 ($consecutive_fails 次)，自动熔断中止以防触发风控！"
            echo "ABORT consecutive_failures=$consecutive_fails" >> "$RESULTS_LOG"
            notify_event "error" "批量任务因连续失败已自动熔断"
            break
        fi

        if ! "$ADB" -s "$DEVICE" get-state >/dev/null 2>&1; then
            "$ADB" connect "$DEVICE" >/dev/null 2>&1 || true
            if ! "$ADB" -s "$DEVICE" get-state >/dev/null 2>&1; then
                err "ADB 连接已断开，任务中止"
                echo "ABORT adb_lost" >> "$RESULTS_LOG"
                notify_event "error" "模拟器 ADB 连接断开"
                break
            fi
        fi

        local acct_t0=$SECONDS
        ensure_screen_on

        # Phase 1: Account Setup
        if is_account_on_device "$email" && [[ $(list_google_accounts | wc -l | tr -d ' ') -eq 1 ]]; then
            ok "目标账号已在设备上，直接复用"
        else
            if ! remove_all_accounts; then
                err "跳过 $email: 旧账号清理失败"
                echo "SKIP $email remove_account_failed" >> "$RESULTS_LOG"
                skip_count=$((skip_count + 1)); consecutive_fails=$((consecutive_fails + 1))
                go_home; sleep "$COOLDOWN"; continue
            fi
            if ! add_google_account "$email" "$password" "$totp_secret"; then
                err "跳过 $email: 登录失败"
                echo "SKIP $email add_account_failed" >> "$RESULTS_LOG"
                skip_count=$((skip_count + 1)); consecutive_fails=$((consecutive_fails + 1))
                take_screenshot "fail_add_${email%%@*}"
                go_home; sleep "$COOLDOWN"; continue
            fi
        fi
        consecutive_fails=0

        # Phase 2: Card Bind & Google One Setup
        if ! bind_card_playstore "$card_num" "$card_exp" "$card_cvv"; then
            err "跳过 $email: 绑卡失败"
            echo "SKIP $email card_bind_failed" >> "$RESULTS_LOG"
            skip_count=$((skip_count + 1)); consecutive_fails=$((consecutive_fails + 1))
            go_home; sleep "$COOLDOWN"; continue
        fi

        if ! prepare_google_one_for_account "$email"; then
            err "跳过 $email: Google One 准备失败"
            echo "SKIP $email app_setup_failed" >> "$RESULTS_LOG"
            skip_count=$((skip_count + 1)); consecutive_fails=$((consecutive_fails + 1))
            go_home; sleep "$COOLDOWN"; continue
        fi

        # Phase 3: Launch Checkout & Keep Frida Listener Alive!
        if [[ "$STACK_ENABLED" == "true" ]]; then
            OLD_PURCHASE_TOKEN=$(read_play_library_token "subs_variant" || read_play_library_token "g1." || echo "")
        fi

        local pid
        pid=$(ensure_google_one_pid "true") || {
            err "跳过 $email: Google One 未能启动"
            echo "SKIP $email no_pid" >> "$RESULTS_LOG"
            skip_count=$((skip_count + 1)); consecutive_fails=$((consecutive_fails + 1))
            sleep "$COOLDOWN"; continue
        }

        run_frida_oneshot "$pid" "$batch_launch_mode" "$SELECTED_INDEX" "true"
        local frida_result="$FRIDA_RESULT"

        # Fallback: if smart pm-clear mode got SELECT_FAILED/NO_TRIALS because Play Store hasn't linked app yet, reinstall once
        if [[ "$GTOOL_BATCH_RESET" == "smart" && ( "$frida_result" == *"SELECT_FAILED"* || "$frida_result" == "NO_TRIALS" ) ]]; then
            warn "极速模式下未读到方案，尝试通过 Play 商店完整绑定重装一次..."
            stop_frida_oneshot
            adb_shell "pm uninstall $GOOGLE_ONE_PKG" >/dev/null 2>&1 || true
            if install_google_one; then
                pid=$(ensure_google_one_pid "true")
                run_frida_oneshot "$pid" "$batch_launch_mode" "$SELECTED_INDEX" "true"
                frida_result="$FRIDA_RESULT"
            fi
        fi

        if [[ "$frida_result" == "BILLING_FLOW_LAUNCHED" ]]; then
            local expect_free="true"
            [[ "$sel_type" != "TRIAL" ]] && expect_free="false"

            if confirm_checkout_sheet "$expect_free"; then
                handle_billing_password "$password" || true
                handle_post_payment || true
                frida_result=$(wait_for_final_result 35 || echo "$FRIDA_RESULT")
            else
                frida_result="${FRIDA_RESULT:-CHECKOUT_ABORTED}"
            fi
        fi
        stop_frida_oneshot

        local acct_elapsed=$((SECONDS - acct_t0))

        # Phase 4: Record & Optional Auto-Cancel
        case "$frida_result" in
            TRIAL_ACTIVATED)
                ok "🎉 激活成功: $email (本号耗时 ${acct_elapsed}s)"
                if [[ "${GTOOL_AUTO_CANCEL:-on}" == "on" && "$STACK_ENABLED" != "true" ]]; then
                    cancel_subscription || warn "自动取消续费未确认，请后续留意检查: $email"
                fi
                echo "OK $email $sel_name (${acct_elapsed}s)" >> "$RESULTS_LOG"
                success_count=$((success_count + 1))
                consecutive_fails=0
                notify_event "success" "成功激活: $email"
                ;;
            ITEM_ALREADY_OWNED)
                warn "账号已有订阅: $email"
                echo "ALREADY_OWNED $email" >> "$RESULTS_LOG"
                skip_count=$((skip_count + 1))
                consecutive_fails=0
                ;;
            INELIGIBLE|NO_TRIALS)
                warn "账号不符合试用资格: $email ($frida_result)"
                echo "INELIGIBLE $email $frida_result" >> "$RESULTS_LOG"
                fail_count=$((fail_count + 1))
                consecutive_fails=0
                ;;
            *)
                err "执行未完成: $email — $frida_result"
                echo "FAIL $email $frida_result" >> "$RESULTS_LOG"
                fail_count=$((fail_count + 1))
                consecutive_fails=$((consecutive_fails + 1))
                take_screenshot "fail_${email%%@*}"
                ;;
        esac

        if [[ "$CARD_MODE" == "rotate" && ${#CARDS_NUMBER[@]} -gt 0 ]]; then
            card_index=$(( (card_index + 1) % ${#CARDS_NUMBER[@]} ))
        fi

        go_home
        sleep "$COOLDOWN"
    done

    local total_elapsed=$((SECONDS - batch_start_ts))
    echo ""
    echo "${C_BOLD}${C_GREEN}╭────────────────────────── 📊 批量任务汇总 ──────────────────────────╮${C_RESET}"
    printf "│  总计账号 : %-6d   成功激活 : %-6d   失败 : %-6d   跳过 : %-4d │\n" \
        "$total_accts" "$success_count" "$fail_count" "$skip_count"
    printf "│  总计耗时 : %dm %02ds                                                  │\n" \
        "$((total_elapsed / 60))" "$((total_elapsed % 60))"
    printf "│  结果文件 : %-55s │\n" "$(basename "$RESULTS_LOG")"
    echo "${C_BOLD}${C_GREEN}╰─────────────────────────────────────────────────────────────────────╯${C_RESET}"
    notify_event "attention" "批量任务已完成：成功 $success_count / 总计 $total_accts"
}

# ===== Mode 4: Toolbox Submenu =====
toolbox_menu() {
    while true; do
        echo ""
        echo "${C_BOLD}${C_CYAN}╭──────────────────────────────────────────────────────────────────╮${C_RESET}"
        echo "${C_BOLD}${C_CYAN}│              🛠️  设备诊断 · 补单同步 · 订阅管理箱                 │${C_RESET}"
        echo "${C_BOLD}${C_CYAN}╰──────────────────────────────────────────────────────────────────╯${C_RESET}"
        echo ""
        echo "  ${C_BOLD}1.${C_RESET} 🩺 环境、Frida 与网络深度体检 + 自动修复"
        echo "  ${C_BOLD}2.${C_RESET} 🔄 查单 & 补单确认同步容量 ${C_YELLOW}(专治「付款成功但订阅没到账」)${C_RESET}"
        echo "  ${C_BOLD}3.${C_RESET} 🛡️ 自动取消当前账号 Google One 续费"
        echo "  ${C_BOLD}4.${C_RESET} 📋 在模拟器直接打开 Play 订阅管理页"
        echo "  ${C_BOLD}5.${C_RESET} 💳 为当前账号快速绑定一张测试卡"
        echo "  ${C_BOLD}6.${C_RESET} 🔀 MuMu 多开实例管理 (切换连接 / 一键启动休眠实例)"
        echo ""
        local tb_ans=""
        read -rp "  选择工具 [1-6, Enter/q 返回主菜单]: " tb_ans || return 0
        case "$tb_ans" in
            ""|q|Q|0) return 0 ;;
            1) run_doctor "true" ;;
            2) sync_and_acknowledge_purchases ;;
            3) detect_device; cancel_subscription || true ;;
            4)
                detect_device
                adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions'" >/dev/null
                ok "已在模拟器打开 Play 订阅管理页"
                ;;
            5)
                detect_device
                local raw_card=""
                read -rp "  输入卡信息 (格式: 卡号-MM/YY-CVV): " raw_card
                if [[ -n "$raw_card" ]]; then
                    local tmp_cf="/tmp/.gtool-onecard-$$.txt"
                    (umask 077; printf '%s\n' "$raw_card" > "$tmp_cf")
                    parse_card_file "$tmp_cf"
                    rm -f "$tmp_cf"
                    if (( ${#CARDS_NUMBER[@]} > 0 )); then
                        bind_card_playstore "${CARDS_NUMBER[0]}" "${CARDS_EXPIRY[0]}" "${CARDS_CVV[0]}" || true
                    fi
                fi
                ;;
            6) select_device_interactive || true ;;
            *) warn "无效选项: $tb_ans" ;;
        esac
    done
}

# ===== Personalized Startup Dashboard =====
show_startup_dashboard() {
    quick_device_radar

    local greet motto
    greet=$(_time_greeting)
    motto=$(_active_motto)

    local dev_badge acct_badge comp_badge
    if [[ "$RADAR_CONNECTED" == "true" ]]; then
        local inst_str="${RADAR_INSTANCE_NAME:+【${RADAR_INSTANCE_NAME}】 }"
        local sib_str="${RADAR_OTHER_INSTANCES:+  | 另备: ${RADAR_OTHER_INSTANCES}}"
        dev_badge="${C_GREEN}● 在线${C_RESET} ${C_BOLD}${inst_str}${C_RESET}${RADAR_DEVICE} ${C_DIM}(${RADAR_MODEL:-Android}${sib_str})${C_RESET}"
        acct_badge="${RADAR_ACCOUNTS:-${C_YELLOW}未登录 Google 账号${C_RESET}}"
        local f_st m_st v_st n_st
        [[ -n "$RADAR_FRIDA_PID" ]] && f_st="${C_GREEN}Frida●就绪${C_RESET}" || f_st="${C_YELLOW}Frida○待启动${C_RESET}"
        [[ "$RADAR_MODULE_OK" == "yes" ]] && m_st="${C_GREEN}模块●就位${C_RESET}" || m_st="${C_YELLOW}模块○自动推送${C_RESET}"
        [[ -n "$RADAR_VENDING_PID" ]] && v_st="${C_GREEN}Play●在线${C_RESET}" || v_st="${C_YELLOW}Play○休眠${C_RESET}"
        [[ "$RADAR_NET_OK" == "yes" ]] && n_st="${C_GREEN}网络●畅通${C_RESET}" || n_st="${C_YELLOW}网络○待检${C_RESET}"
        comp_badge="$f_st  $m_st  $v_st  $n_st"
    else
        local standbys="${RADAR_OTHER_INSTANCES:+ (${RADAR_OTHER_INSTANCES} — 选任意模式可一键唤醒)}"
        dev_badge="${C_YELLOW}○ 模拟器未启动${C_RESET}${C_DIM}${standbys:- (执行时自动扫描连接)}${C_RESET}"
        acct_badge="${C_DIM}—${C_RESET}"
        comp_badge="${C_DIM}等待连接或唤醒 MuMu 模拟器...${C_RESET}"
    fi

    echo ""
    echo "${C_BOLD}${C_CYAN}╔══════════════════════════════════════════════════════════════════════════╗${C_RESET}"
    echo "${C_BOLD}${C_CYAN}║         🚀  Google AI Pro / Ultra Trial Assistant  ·  丝滑领航版         ║${C_RESET}"
    echo "${C_BOLD}${C_CYAN}╠══════════════════════════════════════════════════════════════════════════╣${C_RESET}"
    echo "${C_BOLD}${C_CYAN}║${C_RESET} 📖 博客: ${C_YELLOW}${C_BOLD}https://blog.caowo.de/${C_RESET}  🛒 GPT代充: ${C_GREEN}${C_BOLD}https://faka.cdkey.si/${C_RESET}      ${C_BOLD}${C_CYAN}║${C_RESET}"
    echo "${C_BOLD}${C_CYAN}╚══════════════════════════════════════════════════════════════════════════╝${C_RESET}"
    printf "  %s%s%s\n" "$C_BOLD" "$greet" "$C_RESET"
    printf "  %s💬 %s%s\n" "$C_DIM" "$motto" "$C_RESET"
    echo ""
    echo "  ${C_BOLD}📡 实时态势感知${C_RESET}"
    printf "     模拟器 : %s\n" "$dev_badge"
    printf "     当前号 : %s\n" "$acct_badge"
    printf "     组件链 : %s\n" "$comp_badge"
    echo ""
    echo "  ${C_BOLD}🧭 请选择工作模式${C_RESET}"
    if [[ -n "${GTOOL_LAST_LABEL:-}" ]]; then
        printf "    ${C_GREEN}${C_BOLD}[0]${C_RESET} ⚡ ${C_BOLD}一键复刻上次操作${C_RESET} → ${C_GREEN}%s${C_RESET}\n" "$GTOOL_LAST_LABEL"
    fi
    echo "    ${C_CYAN}${C_BOLD}[1]${C_RESET} 🚀 ${C_BOLD}热门方案一键直达${C_RESET}   ${C_DIM}(Pro免费12月 / 24月叠加 / Ultra 30TB 1折等)${C_RESET}"
    echo "    ${C_CYAN}${C_BOLD}[2]${C_RESET} 🔍 ${C_BOLD}实时扫描全量方案${C_RESET}   ${C_DIM}(当前设备查全部试用+促销档，选号 0.2 秒弹窗)${C_RESET}"
    echo "    ${C_CYAN}${C_BOLD}[3]${C_RESET} 📦 ${C_BOLD}多号全自动批量跑${C_RESET}   ${C_DIM}(导入账号+卡片 → 自动切号/绑卡/开通/防扣费取消)${C_RESET}"
    echo "    ${C_CYAN}${C_BOLD}[4]${C_RESET} 🛠️  ${C_BOLD}诊断与补单工具箱${C_RESET}   ${C_DIM}(网络体检修复 / 付款未到账补单 / 一键取消续费)${C_RESET}"
    echo "    ${C_CYAN}${C_BOLD}[5]${C_RESET} ⚙️  ${C_BOLD}个性化与提示词设置${C_RESET} ${C_DIM}(定制称呼 / 引导风格 / 音效通知 / 极速策略)${C_RESET}"
    echo "    ${C_YELLOW}${C_BOLD}[6]${C_RESET} 🌐 ${C_BOLD}技术博客 & GPT代充发卡网${C_RESET} ${C_DIM}(blog.caowo.de | faka.cdkey.si)${C_RESET}"
    echo "    ${C_DIM}[q] 退出${C_RESET}"
    echo ""
}

replay_last_action() {
    case "${GTOOL_LAST_MODE:-}" in
        preset|sku|offer)
            detect_device
            setup_frida
            ensure_vending_ready
            start_live_frida_session || return 1
            local cmd="" is_paid="false"
            if [[ "${GTOOL_LAST_STACK:-false}" == "true" ]]; then
                local otok=""
                otok=$(read_play_library_token "subs_variant" || read_play_library_token "g1." || echo "")
                cmd="STACK_OFFER|${GTOOL_LAST_SKU}|${GTOOL_LAST_OFFER}|${otok}|5"
            elif [[ "${GTOOL_LAST_MODE}" == "offer" ]]; then
                cmd="LAUNCH_OFFER|${GTOOL_LAST_SKU}|${GTOOL_LAST_OFFER}"
                [[ "$GTOOL_LAST_SKU" == *"ip_"* ]] && is_paid="true"
            elif [[ "${GTOOL_LAST_SKU}" == "auto" ]]; then
                launch_preset_interactive "auto"
                return $?
            else
                cmd="LAUNCH_SKU|${GTOOL_LAST_SKU}|${GTOOL_LAST_OFFER}"
                [[ "$GTOOL_LAST_SKU" == *"ip_"* ]] && is_paid="true"
            fi
            interactive_checkout_cockpit "$cmd" "${GTOOL_LAST_LABEL:-上次方案}" "$is_paid" || true
            ;;
        *)
            warn "暂无可重放的历史操作"
            ;;
    esac
}

# ===== Main Entry Orchestrator =====
batch_main() {
    _parse_batch_args "$@"

    # Direct non-menu CLI routes
    if [[ "$CLI_ACTION" == "doctor" ]]; then
        run_doctor "true"
        return 0
    elif [[ "$CLI_ACTION" == "ack" ]]; then
        sync_and_acknowledge_purchases
        return 0
    elif [[ "$CLI_ACTION" == "cancel" ]]; then
        detect_device
        cancel_subscription
        return $?
    elif [[ "$CLI_ACTION" == "preset" ]]; then
        launch_preset_interactive "$CLI_PRESET"
        return $?
    elif [[ "$CLI_ACTION" == "quick" ]] || [[ -n "$TARGET_SKU" && -z "$ACCOUNT_FILE" && "$CLI_ACTION" != "batch" ]]; then
        quick_browse_main
        return $?
    elif [[ "$CLI_ACTION" == "batch" || -n "$ACCOUNT_FILE" || -n "$CARD_FILE" || "$DRY_RUN" == "true" ]]; then
        batch_pipeline_main
        return $?
    fi

    # Interactive Hub Loop
    while true; do
        show_startup_dashboard
        local hub_choice=""
        if [[ -n "${GTOOL_LAST_LABEL:-}" ]]; then
            read -rp "  选择操作 [0-6 / q]: " hub_choice || hub_choice="q"
        else
            read -rp "  选择操作 [1-6 / q]: " hub_choice || hub_choice="q"
        fi

        case "$hub_choice" in
            0)
                if [[ -n "${GTOOL_LAST_LABEL:-}" ]]; then
                    replay_last_action
                else
                    warn "暂无历史操作记录，请先选择 1-3"
                fi
                ;;
            1)
                show_presets_menu
                local p_sel=""
                read -rp "  输入预设方案编号 (1-10, Enter 返回): " p_sel
                [[ -n "$p_sel" ]] && { launch_preset_interactive "$p_sel" || true; }
                ;;
            2)
                quick_browse_main || true
                ;;
            3)
                batch_pipeline_main || true
                ;;
            4)
                toolbox_menu || true
                ;;
            5)
                customize_preferences_menu || true
                ;;
            6|b|B)
                echo ""
                echo "  📖 技术博客          : ${C_CYAN}https://blog.caowo.de/${C_RESET}"
                echo "  🛒 发卡网 (GPT 代充) : ${C_YELLOW}https://faka.cdkey.si/${C_RESET}"
                if command -v open >/dev/null 2>&1; then
                    open "https://blog.caowo.de/" >/dev/null 2>&1 || true
                    open "https://faka.cdkey.si/" >/dev/null 2>&1 || true
                    ok "已在默认浏览器为您打开技术博客与 GPT 代充发卡网！"
                elif command -v xdg-open >/dev/null 2>&1; then
                    xdg-open "https://faka.cdkey.si/" >/dev/null 2>&1 || true
                fi
                read -rp "  按回车返回主菜单..." _ || true
                ;;
            q|Q|exit)
                echo ""
                ok "已安全退出，祝 ${GTOOL_USER_NAME:-你} 玩得开心 👋"
                echo "  📖 技术博客: https://blog.caowo.de/  |  🛒 发卡网(GPT代充): https://faka.cdkey.si/"
                return 0
                ;;
            *)
                # Convenience: allow typing preset alias like "u1" or "pro12" right from main prompt!
                if resolve_preset_choice "$hub_choice" 2>/dev/null; then
                    launch_preset_interactive "$hub_choice" || true
                else
                    warn "请输入菜单编号 (1-6) 或预设代号 (如 pro12 / u1)，退出请按 q"
                fi
                ;;
        esac
    done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    batch_main "$@"
fi
