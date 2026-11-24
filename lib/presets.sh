#!/usr/bin/env bash
# lib/presets.sh — Curated One-Click Presets, Live Interactive Frida Engine (`-q -t inf`) & Cockpit

LIVE_FRIDA_PID="${LIVE_FRIDA_PID:-}"
LIVE_ATTACHED_G1_PID="${LIVE_ATTACHED_G1_PID:-}"
LIVE_CMD_PATH="/data/data/com.google.android.apps.subscriptions.red/cache/.gtool_cmd"
LIVE_EXT_CMD_PATH="/sdcard/Android/data/com.google.android.apps.subscriptions.red/cache/.gtool_cmd"
LIVE_TMP_JS="${LIVE_TMP_JS:-}"
LIVE_LOG_FILE="${LIVE_LOG_FILE:-}"
LIVE_SEEN_LINES=0

PRESET_SKU=""
PRESET_OFFER=""
PRESET_STACK="false"
PRESET_IS_PAID="false"
PRESET_LABEL=""

_write_live_ipc_cmd() {
    local raw_cmd="${1:-}"
    [[ -z "$raw_cmd" || -z "${DEVICE:-}" ]] && return 1
    local sq_cmd
    sq_cmd=$(_sh_sq "$raw_cmd")
    "$ADB" -s "$DEVICE" shell "mkdir -p '/sdcard/Android/data/com.google.android.apps.subscriptions.red/cache' 2>/dev/null; printf '%s\n' $sq_cmd > '$LIVE_EXT_CMD_PATH' 2>/dev/null || true" >/dev/null 2>&1 || true
    "$ADB" -s "$DEVICE" shell "if [ \"\$(id -u 2>/dev/null)\" = '0' ]; then printf '%s\n' $sq_cmd > '$LIVE_CMD_PATH' && chmod 666 '$LIVE_CMD_PATH'; elif [ -u /system/xbin/su ]; then /system/xbin/su 0 sh -c \"printf '%s\n' $sq_cmd > '$LIVE_CMD_PATH' && chmod 666 '$LIVE_CMD_PATH'\" 2>/dev/null || /system/xbin/su -c \"printf '%s\n' $sq_cmd > '$LIVE_CMD_PATH'\" 2>/dev/null; else su 0 sh -c \"printf '%s\n' $sq_cmd > '$LIVE_CMD_PATH'\" 2>/dev/null || su -c \"printf '%s\n' $sq_cmd > '$LIVE_CMD_PATH'\" 2>/dev/null; fi" >/dev/null 2>&1 || true
}

_cleanup_live_frida() {
    if [[ -n "${LIVE_FRIDA_PID:-}" ]]; then
        if [[ -n "${DEVICE:-}" ]]; then
            _write_live_ipc_cmd "QUIT" || true
            sleep 0.15
        fi
        kill "$LIVE_FRIDA_PID" >/dev/null 2>&1 || true
        LIVE_FRIDA_PID=""
        LIVE_ATTACHED_G1_PID=""
    fi
    [[ -n "${LIVE_TMP_JS:-}" ]] && rm -f "$LIVE_TMP_JS" 2>/dev/null || true
    [[ -n "${LIVE_LOG_FILE:-}" ]] && rm -f "$LIVE_LOG_FILE" 2>/dev/null || true
    LIVE_TMP_JS=""
    LIVE_LOG_FILE=""
}
register_cleanup "_cleanup_live_frida"

# ===== Resolve Preset Code (1..12 or Alias) =====
resolve_preset_choice() {
    local raw_arg="${1:-}"
    [[ -z "$raw_arg" ]] && return 1
    local key
    key=$(printf '%s' "$raw_arg" | tr '[:lower:]' '[:upper:]')
    PRESET_SKU=""
    PRESET_OFFER=""
    PRESET_STACK="false"
    PRESET_IS_PAID="false"
    PRESET_LABEL=""

    case "$key" in
        1|P1|PRO12)
            PRESET_SKU="g1.2tb.ai.subs_variant"
            PRESET_OFFER="12months-eft"
            PRESET_STACK="false"
            PRESET_IS_PAID="false"
            PRESET_LABEL="Pro 5TB · 免费 12 个月 (首开第1步)"
            ;;
        2|P2|PRO6|STACK1)
            PRESET_SKU="g1.2tb.ai.subs_variant"
            PRESET_OFFER="6months-eft"
            PRESET_STACK="true"
            PRESET_IS_PAID="false"
            PRESET_LABEL="Pro 5TB · 免费叠加 +6 个月 (第2步→累计18月)"
            ;;
        3|P3|PRO6B|STACK2)
            PRESET_SKU="g1.2tb.ai.subs_variant"
            PRESET_OFFER="6months-eft-2"
            PRESET_STACK="true"
            PRESET_IS_PAID="false"
            PRESET_LABEL="Pro 5TB · 免费叠加 +6 个月 (第3步→累计24月)"
            ;;
        4|P4|PRO6C|STACK3)
            PRESET_SKU="g1.2tb.ai.subs_variant"
            PRESET_OFFER="6months-eft-ss-2026"
            PRESET_STACK="true"
            PRESET_IS_PAID="false"
            PRESET_LABEL="Pro 5TB · 免费备用叠加 +6 个月 (ss-2026)"
            ;;
        5|P5|PRO3)
            PRESET_SKU="g1.play.2tb.ai"
            PRESET_OFFER="eft-3mo"
            PRESET_STACK="false"
            PRESET_IS_PAID="false"
            PRESET_LABEL="Pro 5TB · 免费 3 个月 (独立单开)"
            ;;
        6|PREM6|2TB6)
            PRESET_SKU="g1.2tb.subs_variant"
            PRESET_OFFER="6months-eft"
            PRESET_STACK="false"
            PRESET_IS_PAID="false"
            PRESET_LABEL="Google One 2TB · 免费 6 个月 (独立备用池)"
            ;;
        7|P6|AUTO)
            PRESET_SKU="auto"
            PRESET_OFFER=""
            PRESET_STACK="false"
            PRESET_IS_PAID="false"
            PRESET_LABEL="全档位自动优选最长 \$0 免费试用"
            ;;
        8|P_YR90|PRO1Y90)
            PRESET_SKU="g1.2tb.ai.12months_ip_90p"
            PRESET_OFFER="__PROMO__"
            PRESET_STACK="false"
            PRESET_IS_PAID="true"
            PRESET_LABEL="Pro 5TB · 连续 12 个月 1折 (\$1.99/月)"
            ;;
        9|P_3M90|PRO3M90)
            PRESET_SKU="g1.2tb.ai.3months_ip_90p.acq"
            PRESET_OFFER="__PROMO__"
            PRESET_STACK="false"
            PRESET_IS_PAID="true"
            PRESET_LABEL="Pro 5TB · 前 3 个月 1折 (\$1.99/月)"
            ;;
        10|U1|ULTRA30|30TB)
            PRESET_SKU="g1.ai.ultra.1month_ip_90p.acq"
            PRESET_OFFER="__PROMO__"
            PRESET_STACK="false"
            PRESET_IS_PAID="true"
            PRESET_LABEL="Ultra 30TB (20x) · 首月 1折 (\$19.99)"
            ;;
        11|U2|U3|ULTRA20|20TB)
            PRESET_SKU="g1.ai.ultra.3months_ip_80p.acq"
            PRESET_OFFER="__PROMO__"
            PRESET_STACK="false"
            PRESET_IS_PAID="true"
            PRESET_LABEL="Ultra 30TB (20x) · 前 3 月 2折 (\$39.99/月)"
            ;;
        12|U4|ULTRA30_25)
            PRESET_SKU="g1.ai.ultra.3months_ip_75p.acq"
            PRESET_OFFER="__PROMO__"
            PRESET_STACK="false"
            PRESET_IS_PAID="true"
            PRESET_LABEL="Ultra 30TB (20x) · 前 3 月 2.5折 (\$49.99/月)"
            ;;
        *)
            return 1
            ;;
    esac
    return 0
}

show_presets_menu() {
    local cb="${C_BOLD:-}" cc="${C_CYAN:-}" cg="${C_GREEN:-}" cy="${C_YELLOW:-}" cd="${C_DIM:-}" cr="${C_RESET:-}"
    echo ""
    echo "${cb}${cc}╭──────────────────────────────────────────────────────────────────────────╮${cr}"
    echo "${cb}${cc}│                🚀  精选实时存活方案一键直达 (2026.11)                     │${cr}"
    echo "${cb}${cc}├──────────────────────────────────────────────────────────────────────────┤${cr}"
    echo "│  ${cg}${cb}【🟢 \$0 免费试用 & 24个月叠加专区】${cr}                                      │"
    echo "│    ${cb}1)${cr} Pro 5TB · 免费 12 个月         ${cd}[首开第1步 | 12months-eft]${cr}   ${cg}★推荐${cr} │"
    echo "│    ${cb}2)${cr} Pro 5TB · 免费叠加 +6 个月     ${cd}[第2步→18月 | --stack]${cr}             │"
    echo "│    ${cb}3)${cr} Pro 5TB · 免费叠加 +6 个月     ${cd}[第3步→24月 | --stack]${cr}             │"
    echo "│    ${cb}4)${cr} Pro 5TB · 免费备用包 +6 个月   ${cd}[备用顺延 | ss-2026 --stack]${cr}       │"
    echo "│    ${cb}5)${cr} Pro 5TB · 免费 3 个月          ${cd}[独立单开 | g1.play.2tb.ai]${cr}        │"
    echo "│    ${cb}6)${cr} Google One 2TB · 免费 6 个月   ${cd}[新发现独立试用池 | 6months-eft]${cr}   │"
    echo "│    ${cb}7)${cr} 自动扫描当前账号最长免费试用   ${cd}[全档位智能匹配 \$0 Offer]${cr}          │"
    echo "├──────────────────────────────────────────────────────────────────────────┤"
    echo "│  ${cy}${cb}【🟡 1折~2.5折特惠神车专区 (仅拉起收银台，绝不自动点扣款)】${cr}             │"
    echo "│    ${cb}8)${cr} Pro 5TB · 连续 12 个月 1折     ${cy}\$1.99/月${cr}  ${cd}(整年12期 | 领\$120赠金)${cr}${cy}★王炸${cr}│"
    echo "│    ${cb}9)${cr} Pro 5TB · 前 3 个月 1折        ${cy}\$1.99/月${cr}  ${cd}(老号救星 | 领\$30赠金)${cr}     │"
    echo "│   ${cb}10)${cr} Ultra 30TB (20x) · 首月 1折    ${cy}\$19.99${cr}    ${cd}(首月特惠 | 领\$100赠金)${cr}${cy}★最新${cr}│"
    echo "│   ${cb}11)${cr} Ultra 30TB (20x) · 前3月 2折   ${cy}\$39.99/月${cr} ${cd}(原价\$199.99 | 3月主力)${cr}    │"
    echo "│   ${cb}12)${cr} Ultra 30TB (20x) · 前3月 2.5折 ${cy}\$49.99/月${cr} ${cd}(原价\$199.99 | 备选特惠)${cr}   │"
    echo "${cb}${cc}├──────────────────────────────────────────────────────────────────────────┤${cr}"
    echo "│  📖 博客: ${cc}https://blog.caowo.de/${cr}  🛒 GPT代充发卡网: ${cy}https://faka.cdkey.si/${cr} │"
    echo "${cb}${cc}╰──────────────────────────────────────────────────────────────────────────╯${cr}"
    echo ""
}

_patch_live_frida_js() {
    local dst="${1:-}"
    (umask 077; : > "$dst")
    python3 - "$FRIDA_SCRIPT" "$dst" "$MODULE_APK_DEVICE" << 'PYLIVE'
import json, re, sys
src_p, dst_p, mod_apk = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src_p, "r", encoding="utf-8") as f:
    src = f.read()
src = re.sub(r"^var MODE\s*=.*$", lambda _m: 'var MODE = "interactive";', src, count=1, flags=re.M)
src = re.sub(r"^var MODULE_APK\s*=.*$", lambda _m: f"var MODULE_APK = {json.dumps(mod_apk)};", src, count=1, flags=re.M)
with open(dst_p, "w", encoding="utf-8") as f:
    f.write(src)
PYLIVE
}

# ===== Start Persistent Live Frida Session (`frida -q -t inf` with real-time stdout stream!) =====
start_live_frida_session() {
    local cur_g1_pid
    cur_g1_pid=$(adb_shell "pidof -s $GOOGLE_ONE_PKG 2>/dev/null || pidof $GOOGLE_ONE_PKG 2>/dev/null" | awk '{print $1}')
    if [[ -n "${LIVE_FRIDA_PID:-}" ]] && kill -0 "$LIVE_FRIDA_PID" 2>/dev/null && [[ -n "$cur_g1_pid" && "$cur_g1_pid" == "${LIVE_ATTACHED_G1_PID:-}" ]]; then
        return 0
    fi

    _cleanup_live_frida
    local pid
    pid=$(ensure_google_one_pid "false")
    [[ -z "$pid" ]] && die "无法启动 Google One 进程"
    LIVE_ATTACHED_G1_PID="$pid"

    LIVE_TMP_JS="/tmp/.frida-live-$$.js"
    LIVE_LOG_FILE="/tmp/.frida-stream-$$.log"
    (umask 077; : > "$LIVE_LOG_FILE")
    LIVE_SEEN_LINES=0

    _patch_live_frida_js "$LIVE_TMP_JS"

    step_begin "注入常驻计费引擎并动态扫描全部可用 SKU"
    # CRITICAL: `-q -t inf` prevents Frida REPL from immediately exiting on /dev/null EOF!
    frida -q -t inf -H "127.0.0.1:$FRIDA_LOCAL_PORT" -p "$pid" -l "$LIVE_TMP_JS" \
        </dev/null >"$LIVE_LOG_FILE" 2>&1 &
    LIVE_FRIDA_PID=$!

    if ! _wait_live_frida_event "INTERACTIVE_READY" 22; then
        warn "首次注入未完成，正在冷重启 Google One 并重试..."
        _cleanup_live_frida
        pid=$(ensure_google_one_pid "true")
        LIVE_TMP_JS="/tmp/.frida-live-$$.js"
        LIVE_LOG_FILE="/tmp/.frida-stream-$$.log"
        (umask 077; : > "$LIVE_LOG_FILE")
        LIVE_SEEN_LINES=0
        _patch_live_frida_js "$LIVE_TMP_JS"
        frida -q -t inf -H "127.0.0.1:$FRIDA_LOCAL_PORT" -p "$pid" -l "$LIVE_TMP_JS" \
            </dev/null >"$LIVE_LOG_FILE" 2>&1 &
        LIVE_FRIDA_PID=$!
        _wait_live_frida_event "INTERACTIVE_READY" 22 || {
            _cleanup_live_frida
            return 1
        }
    fi
    step_end "计费引擎就绪，共发现 $OFFER_COUNT 个可用方案"
    return 0
}

_wait_live_frida_event() {
    local target_kind="${1:-INTERACTIVE_READY}"
    local timeout_sec="${2:-20}"
    local ticks=$(( timeout_sec * 10 ))
    local t=0
    FRIDA_RESULT=""

    while (( t < ticks )); do
        sleep 0.1
        t=$((t + 1))
        _drain_live_stream
        case "$target_kind" in
            INTERACTIVE_READY)
                [[ "$FRIDA_RESULT" == "INTERACTIVE_READY" ]] && return 0
                [[ "$FRIDA_RESULT" == *"FAILED"* || "$FRIDA_RESULT" == *"ERROR"* ]] && return 1
                ;;
            LAUNCH_RESULT)
                case "$FRIDA_RESULT" in
                    BILLING_FLOW_LAUNCHED|TRIAL_ACTIVATED) return 0 ;;
                    *"PROMO_INELIGIBLE"*|*"FAILED"*|*"ERROR"*|*"NOT_FOUND"*|*"NO_ACTIVITY"*|*"NO_ACTIVE_SUB"*) return 1 ;;
                esac
                ;;
            SYNC_DONE)
                [[ "$FRIDA_RESULT" == "PURCHASES_SYNC_DONE" ]] && return 0
                [[ "$FRIDA_RESULT" == *"FAILED"* ]] && return 1
                ;;
        esac
        if [[ -n "${LIVE_FRIDA_PID:-}" ]] && ! kill -0 "$LIVE_FRIDA_PID" 2>/dev/null; then
            _drain_live_stream
            return 1
        fi
    done
    return 1
}

_drain_live_stream() {
    [[ -z "${LIVE_LOG_FILE:-}" || ! -f "$LIVE_LOG_FILE" ]] && return 0
    local total_lines
    total_lines=$(wc -l < "$LIVE_LOG_FILE" | tr -d ' ')
    (( total_lines <= LIVE_SEEN_LINES )) && return 0

    local new_output
    new_output=$(tail -n +"$((LIVE_SEEN_LINES + 1))" "$LIVE_LOG_FILE")
    LIVE_SEEN_LINES=$total_lines

    while IFS= read -r raw_line; do
        raw_line="${raw_line%$'\r'}"
        [[ -z "$raw_line" ]] && continue
        if [[ "$raw_line" != "[AT] "* ]]; then
            case "$raw_line" in
                *Error*|*error*|*Failed*|*failed*|*Unable*|*Exception*)
                    err "Frida 诊断: $raw_line" ;;
            esac
            continue
        fi

        local msg="${raw_line#\[AT\] }"
        case "$msg" in
            DEX_LOADED*)
                log "✓ BillingClient 模块加载完成，正在连接 Google Play 计费服务..." ;;
            "BillingClient connected")
                ok "Google Play 计费服务握手成功！" ;;
            SCAN_START\|*)
                local _ss cnt wcnt
                IFS='|' read -r _ss cnt wcnt <<< "$msg"
                log "⚡ 启动动态 SKU 扫描：共 ${cnt:-20} 个目标商品（分 ${wcnt:-4} 波实时探测）..." ;;
            WAVE_START\|*)
                local _ws w_cur w_tot w_lbl w_n
                IFS='|' read -r _ws w_cur w_tot w_lbl w_n <<< "$msg"
                log "── [第 ${w_cur:-1}/${w_tot:-4} 波] ${w_lbl:-SKU组} (${w_n:-0} 个 SKU) ──" ;;
            SCAN_HIT\|*)
                local _sh h_seq h_tot h_pid h_name h_cnt h_brief
                IFS='|' read -r _sh h_seq h_tot h_pid h_name h_cnt h_brief <<< "$msg"
                local b_sfx=""
                [[ -n "${h_brief:-}" ]] && b_sfx=" [${h_brief}]"
                printf "  %s[+]   [%02d/%02d] ✓ 命中 %s (%s) → %s 个方案%s%s\n" \
                    "${C_GREEN:-}" "${h_seq:-0}" "${h_tot:-0}" "${h_pid:-}" "${h_name:-}" "${h_cnt:-0}" "$b_sfx" "${C_RESET:-}" ;;
            SKU_MISS\|*)
                local _km m_seq m_tot m_pid m_name
                IFS='|' read -r _km m_seq m_tot m_pid m_name <<< "$msg"
                printf "  %s[*]   [%02d/%02d] · 未开放 %s (%s)%s\n" \
                    "${C_DIM:-}" "${m_seq:-0}" "${m_tot:-0}" "${m_pid:-}" "${m_name:-}" "${C_RESET:-}" ;;
            SCAN_SUMMARY\|*)
                ok "═══ 动态探测汇总：${msg#SCAN_SUMMARY|} ═══" ;;
            BROWSE_BEGIN*)
                OFFER_COUNT=0
                OFFER_INDEX=(); OFFER_PRODUCT=(); OFFER_NAME=()
                OFFER_OFFERID=(); OFFER_PRICE=(); OFFER_PERIOD=()
                OFFER_TYPE=(); OFFER_TRIAL_PERIOD=(); OFFER_RENEW_PRICE=(); OFFER_CYCLES=() ;;
            OFFER_ITEM\|*)
                local _tag idx prod pname oid price period otype tperiod rprice icycles _rest
                IFS='|' read -r _tag idx prod pname oid price period otype tperiod rprice icycles _rest <<< "$msg"
                OFFER_INDEX+=("${idx:-0}")
                OFFER_PRODUCT+=("${prod:-}")
                OFFER_NAME+=("${pname:-}")
                OFFER_OFFERID+=("${oid:-base}")
                OFFER_PRICE+=("${price:-}")
                OFFER_PERIOD+=("${period:-}")
                OFFER_TYPE+=("${otype:-BASE}")
                OFFER_TRIAL_PERIOD+=("${tperiod:-}")
                OFFER_RENEW_PRICE+=("${rprice:-}")
                OFFER_CYCLES+=("${icycles:-0}")
                OFFER_COUNT=$((OFFER_COUNT + 1)) ;;
            "=== INTERACTIVE_READY"*)
                FRIDA_RESULT="INTERACTIVE_READY" ;;
            SELECTED*|SKU_SELECTED*|STACK_SELECTED*)
                ok "$msg" ;;
            STACK_APPLIED*)
                ok "已挂载叠加升级参数: ${msg#STACK_APPLIED }" ;;
            BILLING_FLOW_LAUNCHED*)
                if [[ "$msg" == *"code=0"* ]]; then
                    FRIDA_RESULT="BILLING_FLOW_LAUNCHED"
                else
                    FRIDA_RESULT="=== LAUNCH_FAILED $msg ==="
                fi ;;
            PURCHASE_DETAIL\|*)
                log "收到交易回执: ${msg#PURCHASE_DETAIL|}" ;;
            WARN_STACK_CANCELLED*)
                warn "⚠️ 当前旧订阅已关闭自动续费！Google Play 可能拒绝折算顺延，请先在订阅页点「重新订阅」恢复续费开关。" ;;
            "=== PURCHASE_ACKNOWLEDGED"*)
                ok "已自动完成 Play 订单确认 (Acknowledge): $msg" ;;
            "=== TRIAL_ACTIVATED ===")
                echo ""
                ok "🎉 订阅已成功激活并完成确认！"
                notify_event "success" "Google One 订阅已成功激活！"
                FRIDA_RESULT="TRIAL_ACTIVATED" ;;
            "=== PURCHASE_PENDING ===")
                warn "订单处于 Play 异步待确认状态 (PENDING)"
                FRIDA_RESULT="PURCHASE_PENDING" ;;
            "=== USER_CANCELLED ===")
                warn "用户在收银台取消了支付"
                FRIDA_RESULT="USER_CANCELLED" ;;
            "=== ITEM_ALREADY_OWNED ===")
                warn "当前账号已拥有该订阅 (ITEM_ALREADY_OWNED)"
                FRIDA_RESULT="ITEM_ALREADY_OWNED" ;;
            PURCHASE_RECORD\|*)
                local _pr ord prds st ack ar tk
                IFS='|' read -r _pr ord prds st ack ar tk <<< "$msg"
                printf "    • 单号: %-24s | 商品: %-26s | 状态:%s | 已确认:%s | 续费:%s\n" \
                    "${ord:-}" "${prds:-}" "${st:-}" "${ack:-}" "${ar:-}" ;;
            "=== PURCHASES_SYNC_DONE"*)
                FRIDA_SYNC_COUNT=$(echo "$msg" | sed -n 's/.*count=\([0-9]*\).*/\1/p')
                FRIDA_SYNC_ACKED=$(echo "$msg" | sed -n 's/.*acked=\([0-9]*\).*/\1/p')
                FRIDA_RESULT="PURCHASES_SYNC_DONE" ;;
            "=== PROMO_INELIGIBLE"*|\
            "=== SKU_NOT_FOUND"*|\
            "=== SELECT_FAILED"*|\
            "=== NO_ACTIVITY"*|\
            "=== CONNECT_FAILED"*|\
            "=== QUERY_FAILED"*|\
            "=== STACK_NO_ACTIVE_SUB"*|\
            "=== LAUNCH_ERROR"*|\
            "=== PURCHASE_FAILED"*)
                err "$msg"
                FRIDA_RESULT="$msg" ;;
        esac
    done <<< "$new_output"
}

send_live_frida_cmd() {
    local cmd_str="${1:-}"
    [[ -z "$cmd_str" ]] && return 1
    FRIDA_RESULT=""
    local fg_check
    fg_check=$(adb_shell "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'" || true)
    if [[ "$fg_check" != *"$GOOGLE_ONE_PKG"* ]]; then
        adb_shell "monkey -p $GOOGLE_ONE_PKG 1" >/dev/null 2>&1 || true
        sleep 0.5
    fi
    local now_pid
    now_pid=$(adb_shell "pidof -s $GOOGLE_ONE_PKG 2>/dev/null || pidof $GOOGLE_ONE_PKG 2>/dev/null" | awk '{print $1}')
    if [[ -z "${LIVE_FRIDA_PID:-}" ]] || ! kill -0 "$LIVE_FRIDA_PID" 2>/dev/null || [[ -n "$now_pid" && "$now_pid" != "${LIVE_ATTACHED_G1_PID:-}" ]]; then
        log "检测到 Google One 进程切换，正在自动重连会话..."
        start_live_frida_session || return 1
    fi
    _write_live_ipc_cmd "$cmd_str"
}

interactive_checkout_cockpit() {
    local launch_cmd="${1:-}"
    local plan_label="${2:-所选方案}"
    local is_paid="${3:-false}"

    while true; do
        step_begin "拉起收银台 → $plan_label"
        send_live_frida_cmd "$launch_cmd"
        if _wait_live_frida_event "LAUNCH_RESULT" 12; then
            step_end "Google Play 收银台已弹出"
            notify_event "info" "收银台已拉起：$plan_label"
            if [[ "$is_paid" == "true" ]]; then
                echo "  ${C_YELLOW:-}⚠️  付费促销方案：请在模拟器核对首期特惠价后手动点「订阅」（第90天前记得取消续费）${C_RESET:-}"
            else
                coach_tip "请在模拟器确认金额显示为 0 元（免费试用）后再点击订阅"
            fi
        else
            err "拉起未成功: ${FRIDA_RESULT:-超时}"
            if [[ "${FRIDA_RESULT:-}" == *"SKU_NOT_FOUND"* ]]; then
                hint "该账号无法查到此档位：通常因为账号已有订阅（特惠档要求无订阅）或账号锁区不匹配"
            elif [[ "${FRIDA_RESULT:-}" == *"STACK_NO_ACTIVE_SUB"* ]]; then
                hint "叠加模式要求当前账号已有处于活跃状态的 Pro 订阅（请先完成第1步 12个月首开）"
            fi
        fi

        sleep 0.3
        _drain_live_stream

        echo ""
        echo "${C_BOLD:-}${C_CYAN:-}  ┌────────────────────── 🎛️  收银台实时控制台 ──────────────────────┐${C_RESET:-}"
        echo "  │  ${C_BOLD:-}[Enter / r]${C_RESET:-} ⚡ 0.2秒重新拉起当前收银台   ${C_BOLD:-}[p]${C_RESET:-} 🔑 自动代填密码确认 │"
        echo "  │  ${C_BOLD:-}[a]${C_RESET:-} 🔄 查单 & 补单确认同步容量           ${C_BOLD:-}[s]${C_RESET:-} 📋 打开Play订阅页   │"
        echo "  │  ${C_BOLD:-}[x]${C_RESET:-} 🛡️ 一键取消自动续费(防扣款)          ${C_BOLD:-}[b]${C_RESET:-} 🔙 换选其他方案     │"
        echo "  │  ${C_BOLD:-}[q]${C_RESET:-} 👋 完成并退出                                                │"
        echo "${C_BOLD:-}${C_CYAN:-}  └──────────────────────────────────────────────────────────────────┘${C_RESET:-}"

        local act_key=""
        read -rp "  指令 [Enter=重拉 / p / a / s / x / b / q]: " act_key || act_key="q"
        _drain_live_stream

        case "$act_key" in
            ""|r|R)
                if [[ -z "${LIVE_FRIDA_PID:-}" ]] || ! kill -0 "$LIVE_FRIDA_PID" 2>/dev/null; then
                    log "正在自动恢复计费会话..."
                    start_live_frida_session || return 1
                fi
                continue
                ;;
            p|P)
                local pw=""
                read -rsp "  输入当前 Google 账号密码 (输入不回显): " pw || true
                echo ""
                if [[ -n "$pw" ]]; then
                    handle_billing_password "$pw" || true
                    handle_post_payment || true
                    sleep 0.5
                    _drain_live_stream
                fi
                ;;
            a|A)
                log "正在实时查询并执行 Acknowledge 补单确认..."
                send_live_frida_cmd "QUERY_PURCHASES"
                _wait_live_frida_event "SYNC_DONE" 12 || true
                log "刷新 Google One 应用状态..."
                _cleanup_live_frida
                adb_shell "am force-stop $GOOGLE_ONE_PKG" >/dev/null 2>&1 || true
                sleep 0.4
                adb_shell "monkey -p $GOOGLE_ONE_PKG 1" >/dev/null 2>&1 || true
                sleep 1.2
                ok "已刷新 Google One，重新挂载交互引擎..."
                start_live_frida_session || true
                ;;
            s|S)
                adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions'" >/dev/null
                ok "已在模拟器打开 Play 订阅管理页（核对下次扣款日期是否顺延）"
                local sub_ret=""
                read -rp "  核对完毕后按 [Enter] 返回控制台 (或 q 退出): " sub_ret || sub_ret="q"
                [[ "$sub_ret" == "q" || "$sub_ret" == "Q" ]] && return 0
                ;;
            x|X)
                cancel_subscription || warn "自动取消未确认，正在为您停留订阅页以便手动核实"
                local cx_ret=""
                read -rp "  按 [Enter] 返回控制台 (或 q 退出): " cx_ret || cx_ret="q"
                [[ "$cx_ret" == "q" || "$cx_ret" == "Q" ]] && return 0
                ;;
            b|B)
                return 2
                ;;
            q|Q)
                _cleanup_live_frida
                return 0
                ;;
            *)
                warn "未识别指令: $act_key"
                ;;
        esac
    done
}

launch_preset_interactive() {
    local preset_code="${1:-}"
    resolve_preset_choice "$preset_code" || {
        err "未知预设编号: $preset_code"
        return 1
    }

    detect_device
    setup_frida
    ensure_vending_ready

    local cur_acct
    cur_acct=$(list_google_accounts | head -1 || true)
    [[ -z "$cur_acct" ]] && die "模拟器上未登录任何 Google 账号，请先登录账号或使用批量模式"
    ok "当前设备账号: $cur_acct"

    if [[ "$PRESET_IS_PAID" == "true" ]]; then
        echo ""
        echo "  ${C_YELLOW:-}⚠️  注意：您选择的是付费促销方案【$PRESET_LABEL】${C_RESET:-}"
        echo "  ${C_DIM:-}脚本仅为您拉起收银台弹窗，不会替您点击订阅扣款。${C_RESET:-}"
        local p_ok=""
        read -rp "  确认拉起该方案？(Enter=继续 / q=取消): " p_ok || p_ok="q"
        [[ "$p_ok" == "q" || "$p_ok" == "Q" ]] && return 0
    fi

    remember_last_action "preset" "$PRESET_SKU" "$PRESET_OFFER" "$PRESET_STACK" "$PRESET_LABEL"

    if ! start_live_frida_session; then
        err "计费引擎启动未成功，请查看上方诊断信息"
        read -rp "  按回车返回..." _ || true
        return 1
    fi

    local cmd=""
    if [[ "$PRESET_STACK" == "true" ]]; then
        log "正在从 Play 本地库读取当前活跃订阅的 purchaseToken 以进行叠加..."
        local old_tok=""
        old_tok=$(read_play_library_token "subs_variant" || read_play_library_token "g1." || echo "")
        if [[ -n "$old_tok" ]]; then
            ok "成功提取活跃 purchaseToken (${old_tok:0:16}...)，启用 CHARGE_FULL_PRICE 折算顺延"
        else
            warn "library.db 未读到 token，将交由 BillingClient.queryPurchasesAsync 动态获取"
        fi
        cmd="STACK_OFFER|${PRESET_SKU}|${PRESET_OFFER}|${old_tok}|5"
    elif [[ "$PRESET_SKU" == "auto" ]]; then
        local best_idx=-1 best_m=-1 k
        for ((k=0; k<OFFER_COUNT; k++)); do
            if [[ "${OFFER_TYPE[$k]}" == "TRIAL" ]]; then
                local m=1
                case "${OFFER_TRIAL_PERIOD[$k]}" in
                    P1Y|P12M) m=12 ;; P6M) m=6 ;; P3M) m=3 ;; P1M) m=1 ;;
                esac
                if (( m > best_m )); then
                    best_m=$m
                    best_idx=$k
                fi
            fi
        done
        if (( best_idx < 0 )); then
            err "当前账号未发现任何可用的 \$0 免费试用方案！"
            read -rp "  按回车返回..." _ || true
            return 1
        fi
        cmd="LAUNCH_OFFER|${OFFER_PRODUCT[$best_idx]}|${OFFER_OFFERID[$best_idx]}"
        PRESET_LABEL="${OFFER_NAME[$best_idx]} (${OFFER_OFFERID[$best_idx]})"
    else
        cmd="LAUNCH_SKU|${PRESET_SKU}|${PRESET_OFFER}"
    fi

    interactive_checkout_cockpit "$cmd" "$PRESET_LABEL" "$PRESET_IS_PAID"
}
