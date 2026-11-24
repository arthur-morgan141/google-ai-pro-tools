#!/usr/bin/env bash
# auto-trial.sh — Fast Google AI Pro / Ultra Trial & Promo Launcher (CLI + Core Library)
# 博客：https://blog.caowo.de/
# 发卡网（仅提供 GPT 代充）：https://faka.cdkey.si/
#
# Usage:
#   ./auto-trial.sh --browse                                    # interactive live browse & 0.2s launch
#   ./auto-trial.sh --list                                      # list all available $0 free trials
#   ./auto-trial.sh --product pro12 --dur 12mo                  # Pro 5TB, 12-month free trial
#   ./auto-trial.sh --product pro12 --offer 6months-eft --stack # Pro 5TB +6mo free stacking upgrade
#   ./auto-trial.sh --sku g1.ai.ultra.3months_ip_90p.acq        # Ultra 30TB 1折 $19.99/mo promo
#   ./auto-trial.sh --ack                                       # query & acknowledge purchases (补单同步)
#   ./auto-trial.sh --port 16416 --list                         # specify MuMu ADB port

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    for _b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
        [[ -x "$_b" ]] && exec "$_b" "$0" "$@"
    done
fi

set -euo pipefail

# ===== Paths =====
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRIDA_SCRIPT="${FRIDA_SCRIPT:-$SCRIPT_DIR/frida-auto-trial.js}"
FRIDA_DEVICE_PORT=27042
FRIDA_LOCAL_PORT=27043
GOOGLE_ONE_PKG="com.google.android.apps.subscriptions.red"

MODULE_APK_LOCAL="${MODULE_APK_LOCAL:-$SCRIPT_DIR/module.apk}"
MODULE_APK_DEVICE="${MODULE_APK_DEVICE:-/data/local/tmp/module.apk}"
FRIDA_SERVER_PATH="${FRIDA_SERVER_PATH:-/data/local/tmp/frida-server}"

# ===== Defaults =====
MODE="activate"
TARGET="auto"
DURATION="longest"
DEVICE=""
DEVICE_PORT=""
SELECTED_INDEX=-1
TARGET_SKU="${TARGET_SKU:-}"
TARGET_OFFER_ID="${TARGET_OFFER_ID:-}"
STACK_ENABLED="${STACK_ENABLED:-false}"
OLD_PURCHASE_TOKEN="${OLD_PURCHASE_TOKEN:-}"
STACK_PRORATION_MODE="${STACK_PRORATION_MODE:-5}"
FRIDA_RESULT=""
FRIDA_SYNC_COUNT=0
FRIDA_SYNC_ACKED=0
FRIDA_PID=""
_ONESHOT_TMP_SCRIPT=""
_ONESHOT_LOG_FILE=""

# Safe color fallbacks before lib/theme-ui.sh is loaded
C_RESET="${C_RESET:-}"
C_BOLD="${C_BOLD:-}"
C_DIM="${C_DIM:-}"
C_RED="${C_RED:-}"
C_GREEN="${C_GREEN:-}"
C_YELLOW="${C_YELLOW:-}"
C_BLUE="${C_BLUE:-}"
C_CYAN="${C_CYAN:-}"
C_MAGENTA="${C_MAGENTA:-}"
C_GRAY="${C_GRAY:-}"
C_WHITE="${C_WHITE:-}"

# Offer storage
declare -a OFFER_INDEX=()
declare -a OFFER_PRODUCT=()
declare -a OFFER_NAME=()
declare -a OFFER_OFFERID=()
declare -a OFFER_PRICE=()
declare -a OFFER_PERIOD=()
declare -a OFFER_TYPE=()
declare -a OFFER_TRIAL_PERIOD=()
declare -a OFFER_RENEW_PRICE=()
declare -a OFFER_CYCLES=()
OFFER_COUNT=0

# ===== Auto-detect ADB =====
find_adb() {
    if [[ -n "${ADB_PATH:-}" ]] && [[ -x "$ADB_PATH" ]]; then
        echo "$ADB_PATH"; return
    fi
    if command -v adb >/dev/null 2>&1; then
        command -v adb; return
    fi
    local candidates=(
        "/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
        "$HOME/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
        "/Applications/MuMuPlayer.app/Contents/MacOS/tools/adb"
        "$HOME/Applications/MuMuPlayer.app/Contents/MacOS/tools/adb"
        "/Applications/MuMuPlayerPro.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
        "/Applications/MuMu Player.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
        "/Applications/MuMuPlayerPro.app/Contents/MacOS/tools/adb"
        "/Applications/MuMu Player.app/Contents/MacOS/tools/adb"
        "/opt/homebrew/bin/adb"
        "/usr/local/bin/adb"
        "$HOME/Library/Android/sdk/platform-tools/adb"
        "/usr/local/share/android-sdk/platform-tools/adb"
        "$HOME/Android/Sdk/platform-tools/adb"
        "${LOCALAPPDATA:-_}/Android/Sdk/platform-tools/adb.exe"
        "${PROGRAMFILES:-_}/Android/android-sdk/platform-tools/adb.exe"
    )
    local c
    for c in "${candidates[@]}"; do
        [[ -x "$c" ]] && { echo "$c"; return; }
    done
    return 1
}
ADB="$(find_adb)" || { echo "[-] 未找到 adb，请安装 Android platform-tools 或启动 MuMu 模拟器后重试" >&2; exit 1; }

find_mumutool() {
    if [[ -n "${MUMUTOOL_PATH:-}" ]] && [[ -x "$MUMUTOOL_PATH" ]]; then
        echo "$MUMUTOOL_PATH"; return
    fi
    if command -v mumutool >/dev/null 2>&1; then
        command -v mumutool; return
    fi
    local mc=(
        "/Applications/MuMuPlayer.app/Contents/MacOS/mumutool"
        "$HOME/Applications/MuMuPlayer.app/Contents/MacOS/mumutool"
        "/Applications/MuMuPlayerPro.app/Contents/MacOS/mumutool"
        "/Applications/MuMu Player.app/Contents/MacOS/mumutool"
    )
    local m
    for m in "${mc[@]}"; do
        [[ -x "$m" ]] && { echo "$m"; return; }
    done
    return 1
}
MUMUTOOL="$(find_mumutool 2>/dev/null || echo "")"
MUMU_INSTANCE_NAME=""

# Basic logging fallbacks (overridden with rich colors when lib/theme-ui.sh is loaded)
if ! declare -F log >/dev/null 2>&1; then
    log()  { echo "[*] $*"; }
    ok()   { echo "[+] $*"; }
    warn() { echo "[!] $*" >&2; }
    err()  { echo "[-] $*" >&2; }
    step_begin() { log "$*"; }
    step_end()   { ok "$*"; }
fi
die() { err "$*"; exit 1; }

_require_auto_arg() {
    [[ $# -ge 2 && -n "${2:-}" ]] || die "参数 ${1:-} 缺少取值"
}

_parse_auto_trial_args() {
    while [[ $# -gt 0 ]]; do
        case "${1:-}" in
            --list)            MODE="list"; shift ;;
            --browse)          MODE="browse"; shift ;;
            --ack|--sync)      MODE="query_purchases"; shift ;;
            --product)         _require_auto_arg "$@"; TARGET="${2:-}"; shift 2 ;;
            --sku)             _require_auto_arg "$@"; TARGET_SKU="${2:-}"; MODE="launch_sku"; shift 2 ;;
            --offer)           _require_auto_arg "$@"; TARGET_OFFER_ID="${2:-}"; shift 2 ;;
            --stack)           STACK_ENABLED="true"; shift ;;
            --old-token)       _require_auto_arg "$@"; OLD_PURCHASE_TOKEN="${2:-}"; STACK_ENABLED="true"; shift 2 ;;
            --dur|--duration)  _require_auto_arg "$@"; DURATION="${2:-}"; shift 2 ;;
            --port)            _require_auto_arg "$@"; DEVICE_PORT="${2:-}"; shift 2 ;;
            --adb)             _require_auto_arg "$@"; ADB="${2:-}"; shift 2 ;;
            --script)          _require_auto_arg "$@"; FRIDA_SCRIPT="${2:-}"; shift 2 ;;
            -h|--help)
                sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
                exit 0 ;;
            *) echo "Unknown option: ${1:-}" >&2; exit 1 ;;
        esac
    done
}

resolve_product_alias() {
    case "$TARGET" in
        20x|20X|ultra20x)   TARGET="g1.play.ai.pro" ;;
        5x|5X|ultra5x)      TARGET="g1.play.20tb" ;;
        pro|Pro|PRO|pro3)   TARGET="g1.play.2tb.ai" ;;
        pro12|Pro12|PRO12)  TARGET="g1.2tb.ai.subs_variant" ;;
        auto|g1.*)          ;;
        *) die "未知产品别名: $TARGET (可选: pro12, pro, 5x, 20x, auto 或完整 g1.* 商品 ID)" ;;
    esac
}

# ===== 1. Fast Device Detection (mumutool exact port + auto-boot + ADB fallback) =====
detect_device() {
    if [[ -n "$DEVICE_PORT" ]]; then
        DEVICE="127.0.0.1:$DEVICE_PORT"
        "$ADB" connect "$DEVICE" >/dev/null 2>&1 || true
        "$ADB" -s "$DEVICE" get-state >/dev/null 2>&1 || die "无法连接指定端口设备: $DEVICE"
        ok "已连接指定设备: $DEVICE"
        return
    fi

    if [[ -n "${DEVICE:-}" ]] && "$ADB" -s "$DEVICE" get-state >/dev/null 2>&1; then
        return
    fi

    # Ultra-fast path via mumutool (20ms exact instance & port discovery!)
    if [[ -n "${MUMUTOOL:-}" && -x "$MUMUTOOL" ]]; then
        local mumu_json
        mumu_json=$("$MUMUTOOL" info all 2>/dev/null || echo "")
        if [[ -n "$mumu_json" ]]; then
            local running_list=() stopped_list=()
            while IFS='|' read -r kind idx port name; do
                [[ -z "$kind" ]] && continue
                if [[ "$kind" == "RUN" ]]; then
                    running_list+=("${idx}|${port}|${name}")
                elif [[ "$kind" == "STOP" ]]; then
                    stopped_list+=("${idx}|0|${name}")
                fi
            done < <(python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
    for item in d.get("return", {}).get("results", []):
        st = item.get("state", "")
        idx = item.get("index", 0)
        port = item.get("adb_port", 0)
        nm = item.get("name", f"MuMu-{idx}")
        if st == "running" and port:
            print(f"RUN|{idx}|{port}|{nm}")
        else:
            print(f"STOP|{idx}|0|{nm}")
except Exception:
    pass
' <<< "$mumu_json")

            if (( ${#running_list[@]} == 1 )); then
                local r_idx r_port r_name
                IFS='|' read -r r_idx r_port r_name <<< "${running_list[0]}"
                DEVICE="127.0.0.1:$r_port"
                MUMU_INSTANCE_NAME="$r_name"
                "$ADB" connect "$DEVICE" >/dev/null 2>&1 || true
                if "$ADB" -s "$DEVICE" get-state >/dev/null 2>&1; then
                    ok "已连接 MuMu 实例【$r_name】($DEVICE)"
                    return
                fi
            elif (( ${#running_list[@]} > 1 )); then
                local pick_i=0
                if [[ -t 0 ]]; then
                    echo ""
                    echo "  检测到多台正在运行的 MuMu 实例："
                    local k
                    for k in "${!running_list[@]}"; do
                        local ri rp rn
                        IFS='|' read -r ri rp rn <<< "${running_list[$k]}"
                        printf "    %d) %s (127.0.0.1:%s)\n" "$((k+1))" "$rn" "$rp"
                    done
                    local ans=""
                    read -rp "  请选择要操作的模拟器 [1-${#running_list[@]}, 默认 1]: " ans
                    ans="${ans:-1}"
                    [[ "$ans" =~ ^[0-9]+$ ]] && (( ans >= 1 && ans <= ${#running_list[@]} )) && pick_i=$((ans - 1))
                fi
                local r_idx r_port r_name
                IFS='|' read -r r_idx r_port r_name <<< "${running_list[$pick_i]}"
                DEVICE="127.0.0.1:$r_port"
                MUMU_INSTANCE_NAME="$r_name"
                "$ADB" connect "$DEVICE" >/dev/null 2>&1 || true
                ok "已锁定 MuMu 实例【$r_name】($DEVICE)"
                return
            elif (( ${#stopped_list[@]} > 0 )) && [[ -t 0 ]]; then
                echo ""
                warn "当前没有正在运行的模拟器，但检测到以下本地 MuMu 实例："
                local k
                for k in "${!stopped_list[@]}"; do
                    local si _sp sn
                    IFS='|' read -r si _sp sn <<< "${stopped_list[$k]}"
                    printf "    [%s] %s (未启动)\n" "$si" "$sn"
                done
                local boot_idx=""
                local def_idx="${stopped_list[0]%%|*}"
                read -rp "  是否立即为您一键启动模拟器？输入实例编号 [${def_idx}] (q=取消): " boot_idx
                boot_idx="${boot_idx:-$def_idx}"
                if [[ "$boot_idx" =~ ^[0-9]+$ ]]; then
                    step_begin "正在唤醒 MuMu 实例 #$boot_idx，请稍候..."
                    "$MUMUTOOL" open "$boot_idx" >/dev/null 2>&1 || true
                    local w
                    for ((w=0; w<45; w++)); do
                        sleep 1
                        local b_info b_port b_name
                        b_info=$("$MUMUTOOL" info "$boot_idx" 2>/dev/null || echo "")
                        IFS='|' read -r b_port b_name <<< "$(python3 -c '
import json, sys
try:
    j = json.loads(sys.stdin.read()).get("return", {})
    if "results" in j and j["results"]:
        j = j["results"][0]
    if j.get("state") == "running" and j.get("adb_port"):
        port = j["adb_port"]
        nm = j.get("name") or "MuMu"
        print(f"{port}|{nm}")
except Exception:
    pass
' <<< "$b_info")"
                        if [[ -n "${b_port:-}" ]]; then
                            "$ADB" connect "127.0.0.1:$b_port" >/dev/null 2>&1 || true
                            local boot_ok
                            boot_ok=$("$ADB" -s "127.0.0.1:$b_port" shell "getprop sys.boot_completed" 2>/dev/null | tr -d '\r\n' || echo "")
                            if [[ "$boot_ok" == "1" ]]; then
                                DEVICE="127.0.0.1:$b_port"
                                MUMU_INSTANCE_NAME="$b_name"
                                step_end "MuMu 实例【$b_name】启动并就绪 ($DEVICE)"
                                return
                            fi
                        fi
                    done
                    die "等待 MuMu 实例启动完成超时，请确认窗口已就绪后重试"
                fi
            fi
        fi
    fi

    # Fallback: check already-connected ADB devices
    local connected_dev
    connected_dev=$("$ADB" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')
    if [[ -n "$connected_dev" ]]; then
        DEVICE="$connected_dev"
        ok "已连接在线设备: $DEVICE"
        return
    fi

    log "正在扫描常见模拟器 ADB 端口..."
    local port
    for port in 16384 16416 16448 16480 16512 7555; do
        if "$ADB" connect "127.0.0.1:$port" 2>/dev/null | grep -q "connected"; then
            if "$ADB" -s "127.0.0.1:$port" get-state >/dev/null 2>&1; then
                DEVICE="127.0.0.1:$port"
                ok "已发现并连接模拟器: $DEVICE"
                return
            fi
        fi
    done

    die "未检测到运行中的模拟器，请先启动 MuMu 模拟器或使用 --port <端口>"
}

# ===== 2. Fast Frida & Module Setup (auto-pushes module.apk if missing!) =====
setup_frida() {
    "$ADB" -s "$DEVICE" forward "tcp:$FRIDA_LOCAL_PORT" "tcp:$FRIDA_DEVICE_PORT" >/dev/null 2>&1 || true

    local fs_pid
    fs_pid=$("$ADB" -s "$DEVICE" shell "pidof frida-server" 2>/dev/null | awk '{print $1}' | tr -d '\r\n' || true)
    if [[ -z "$fs_pid" ]]; then
        if ! "$ADB" -s "$DEVICE" shell "[ -x '$FRIDA_SERVER_PATH' ]" >/dev/null 2>&1; then
            if "$ADB" -s "$DEVICE" shell "[ -f '$FRIDA_SERVER_PATH' ]" >/dev/null 2>&1; then
                "$ADB" -s "$DEVICE" shell "chmod 755 '$FRIDA_SERVER_PATH'" >/dev/null 2>&1 || true
            else
                die "设备上未找到 $FRIDA_SERVER_PATH，请先推送对应架构的 frida-server"
            fi
        fi
        log "正在启动设备端 frida-server..."
        local dev_uid
        dev_uid=$("$ADB" -s "$DEVICE" shell "id" 2>/dev/null || true)
        if [[ "$dev_uid" == *"uid=0"* ]]; then
            "$ADB" -s "$DEVICE" shell "nohup $FRIDA_SERVER_PATH -D >/dev/null 2>&1 &" >/dev/null 2>&1 || true
        else
            "$ADB" -s "$DEVICE" shell "su -c 'nohup $FRIDA_SERVER_PATH -D >/dev/null 2>&1 &'" >/dev/null 2>&1 || \
                "$ADB" -s "$DEVICE" shell "nohup $FRIDA_SERVER_PATH -D >/dev/null 2>&1 &" >/dev/null 2>&1 || true
        fi
        local t
        for ((t=0; t<15; t++)); do
            sleep 0.2
            fs_pid=$("$ADB" -s "$DEVICE" shell "pidof frida-server" 2>/dev/null | awk '{print $1}' | tr -d '\r\n' || true)
            [[ -n "$fs_pid" ]] && break
        done
        [[ -n "$fs_pid" ]] || die "无法启动 frida-server ($FRIDA_SERVER_PATH)"
    fi
    ok "frida-server 运行中 (PID $fs_pid)"

    # Auto-push BillingClient module.apk if missing on device!
    if ! "$ADB" -s "$DEVICE" shell "[ -s '$MODULE_APK_DEVICE' ]" >/dev/null 2>&1; then
        if [[ -s "$MODULE_APK_LOCAL" ]]; then
            log "首次初始化：自动推送计费模块 module.apk 到模拟器..."
            "$ADB" -s "$DEVICE" push "$MODULE_APK_LOCAL" "$MODULE_APK_DEVICE" >/dev/null
            "$ADB" -s "$DEVICE" shell "chmod 644 '$MODULE_APK_DEVICE'" >/dev/null 2>&1 || true
            ok "module.apk 自动推送完成"
        else
            die "设备上缺少 $MODULE_APK_DEVICE 且本地未找到 $MODULE_APK_LOCAL"
        fi
    fi
}

# ===== 3. Smart Warm/Cold Google One Launcher (0.2s when warm, ~1.2s when cold!) =====
ensure_google_one_pid() {
    local force_restart="${1:-false}"
    local pid=""

    if [[ "$force_restart" != "true" ]]; then
        pid=$("$ADB" -s "$DEVICE" shell "pidof $GOOGLE_ONE_PKG" 2>/dev/null | awk '{print $1}' | tr -d '\r\n' || true)
        if [[ -n "$pid" ]]; then
            # Bring Google One Activity to foreground if currently in background
            local focus
            focus=$("$ADB" -s "$DEVICE" shell "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'" 2>/dev/null || true)
            if [[ "$focus" != *"$GOOGLE_ONE_PKG"* ]]; then
                "$ADB" -s "$DEVICE" shell "monkey -p $GOOGLE_ONE_PKG 1" >/dev/null 2>&1 || true
                sleep 0.6
            fi
            pid=$("$ADB" -s "$DEVICE" shell "pidof $GOOGLE_ONE_PKG" 2>/dev/null | awk '{print $1}' | tr -d '\r\n' || true)
            if [[ -n "$pid" ]]; then
                ok "复用运行中的 Google One (PID: $pid)" >&2
                echo "$pid"
                return 0
            fi
        fi
    fi

    if [[ "$force_restart" == "true" ]]; then
        log "正在重置并拉起 Google One..." >&2
        "$ADB" -s "$DEVICE" shell "am force-stop $GOOGLE_ONE_PKG" >/dev/null 2>&1 || true
        sleep 0.3
    else
        log "正在启动 Google One..." >&2
    fi

    # Check Google One installed
    if ! "$ADB" -s "$DEVICE" shell "pm path $GOOGLE_ONE_PKG" 2>/dev/null | grep -q "package:"; then
        die "设备上未安装 Google One ($GOOGLE_ONE_PKG)"
    fi

    "$ADB" -s "$DEVICE" shell "monkey -p $GOOGLE_ONE_PKG 1" >/dev/null 2>&1 || true

    local i
    for ((i=0; i<24; i++)); do
        sleep 0.25
        pid=$("$ADB" -s "$DEVICE" shell "pidof $GOOGLE_ONE_PKG" 2>/dev/null | awk '{print $1}' | tr -d '\r\n' || true)
        if [[ -n "$pid" ]]; then
            # Wait briefly for main Activity creation
            local focus_ok
            focus_ok=$("$ADB" -s "$DEVICE" shell "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'" 2>/dev/null || true)
            if [[ "$focus_ok" == *"$GOOGLE_ONE_PKG"* ]] || (( i >= 6 )); then
                sleep 0.35
                ok "Google One 已就绪 (PID: $pid)" >&2
                echo "$pid"
                return 0
            fi
        fi
    done

    die "Google One 启动超时，请确认模拟器未卡死"
}

# Backward-compatible wrapper
get_pid() {
    ensure_google_one_pid "${1:-false}"
}

# ===== 4. Fast Frida Runner (`frida -q -t inf` with real-time dynamic stream!) =====
run_frida_oneshot() {
    local pid="${1:-}"
    local frida_mode="${2:-$MODE}"
    local frida_index="${3:-$SELECTED_INDEX}"
    local keep_alive_on_launch="${4:-false}"
    [[ -n "$pid" ]] || { err "缺少 Google One 进程 PID"; FRIDA_RESULT="NO_PID"; return 1; }

    local tmp_script="/tmp/.frida-run-$$.js"
    local oneshot_log="/tmp/.frida-oneshot-$$.log"
    (umask 077; : > "$oneshot_log"; : > "$tmp_script")

    python3 - "$FRIDA_SCRIPT" "$tmp_script" \
        "$frida_mode" "$TARGET" "$DURATION" "$frida_index" \
        "$TARGET_SKU" "$TARGET_OFFER_ID" "$STACK_ENABLED" \
        "$OLD_PURCHASE_TOKEN" "$STACK_PRORATION_MODE" "$MODULE_APK_DEVICE" << 'PYPATCH'
import json, re, sys

src_path, dst_path = sys.argv[1], sys.argv[2]
mode, target, dur, idx_s, sku, oid, stack_s, old_tok, pror_s, mod_apk = sys.argv[3:13]
idx_val = int(idx_s) if re.fullmatch(r"-?\d+", idx_s) else -1
pror_val = int(pror_s) if re.fullmatch(r"\d+", pror_s) else 5
stack_bool = (stack_s.lower() == "true")

with open(src_path, "r", encoding="utf-8") as f:
    src = f.read()

repls = {
    "MODE": json.dumps(mode),
    "TARGET_PRODUCT": json.dumps(target),
    "PREFER_DURATION": json.dumps(dur),
    "SELECTED_OFFER_INDEX": str(idx_val),
    "TARGET_SKU": json.dumps(sku),
    "TARGET_OFFER_ID": json.dumps(oid),
    "STACK_ENABLED": "true" if stack_bool else "false",
    "OLD_PURCHASE_TOKEN": json.dumps(old_tok),
    "STACK_PRORATION_MODE": str(pror_val),
    "MODULE_APK": json.dumps(mod_apk),
}
for k, v in repls.items():
    src = re.sub(rf"^var {k}\s*=.*$", lambda _m, k=k, v=v: f"var {k} = {v};", src, count=1, flags=re.M)

with open(dst_path, "w", encoding="utf-8") as f:
    f.write(src)
PYPATCH

    "$ADB" -s "$DEVICE" logcat -c 2>/dev/null || true

    frida -q -t inf -H "127.0.0.1:$FRIDA_LOCAL_PORT" -p "$pid" -l "$tmp_script" \
        </dev/null >"$oneshot_log" 2>&1 &
    FRIDA_PID=$!

    local ticks=0
    local max_ticks=250  # 25s at 0.1s resolution
    local got_terminal=false
    local seen_lines=0
    FRIDA_RESULT=""
    FRIDA_SYNC_COUNT=0
    FRIDA_SYNC_ACKED=0

    while (( ticks < max_ticks )); do
        sleep 0.1
        ticks=$((ticks + 1))

        [[ -f "$oneshot_log" ]] || continue
        local total_lines
        total_lines=$(wc -l < "$oneshot_log" | tr -d ' ')
        if (( total_lines <= seen_lines )); then
            if [[ -n "${FRIDA_PID:-}" ]] && ! kill -0 "$FRIDA_PID" 2>/dev/null; then
                break
            fi
            continue
        fi
        local new_output
        new_output=$(tail -n +"$((seen_lines + 1))" "$oneshot_log")
        seen_lines=$total_lines

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
                    log "✓ BillingClient 模块加载完成，正在连接 Google Play 计费服务..." >&2 ;;
                "BillingClient connected")
                    ok "BillingClient 已连接" >&2 ;;
                SCAN_START\|*)
                    local _ss cnt wcnt
                    IFS='|' read -r _ss cnt wcnt <<< "$msg"
                    log "⚡ 启动动态 SKU 扫描：共 ${cnt:-20} 个目标商品（分 ${wcnt:-4} 波探测）..." >&2 ;;
                WAVE_START\|*)
                    local _ws w_cur w_tot w_lbl w_n
                    IFS='|' read -r _ws w_cur w_tot w_lbl w_n <<< "$msg"
                    log "── [第 ${w_cur:-1}/${w_tot:-4} 波] ${w_lbl:-SKU组} (${w_n:-0} 个 SKU) ──" >&2 ;;
                SCAN_HIT\|*)
                    local _sh h_seq h_tot h_pid h_name h_cnt h_brief
                    IFS='|' read -r _sh h_seq h_tot h_pid h_name h_cnt h_brief <<< "$msg"
                    local b_sfx=""
                    [[ -n "${h_brief:-}" ]] && b_sfx=" [${h_brief}]"
                    printf "  %s[+]   [%02d/%02d] ✓ 命中 %s (%s) → %s 个方案%s%s\n" \
                        "${C_GREEN:-}" "${h_seq:-0}" "${h_tot:-0}" "${h_pid:-}" "${h_name:-}" "${h_cnt:-0}" "$b_sfx" "${C_RESET:-}" >&2 ;;
                SKU_MISS\|*)
                    local _km m_seq m_tot m_pid m_name
                    IFS='|' read -r _km m_seq m_tot m_pid m_name <<< "$msg"
                    printf "  %s[*]   [%02d/%02d] · 未开放 %s (%s)%s\n" \
                        "${C_DIM:-}" "${m_seq:-0}" "${m_tot:-0}" "${m_pid:-}" "${m_name:-}" "${C_RESET:-}" >&2 ;;
                SCAN_SUMMARY\|*)
                    ok "═══ 动态探测汇总：${msg#SCAN_SUMMARY|} ═══" >&2 ;;
                "  TRIAL "*)
                    ok "$msg" ;;
                TRIALS_FOUND*)
                    [[ "$frida_mode" == "list" ]] && { echo ""; log "$msg"; } ;;
                SELECTED*|SKU_SELECTED*|STACK_SELECTED*)
                    ok "$msg" >&2 ;;
                STACK_APPLIED*)
                    ok "叠加升级参数已生效: ${msg#STACK_APPLIED }" >&2 ;;
                BILLING_FLOW_LAUNCHED*)
                    if [[ "$msg" == *"code=0"* ]]; then
                        ok "收银台已成功拉起" >&2
                        FRIDA_RESULT="BILLING_FLOW_LAUNCHED"
                    else
                        err "拉起返回非0状态: $msg"
                        FRIDA_RESULT="=== LAUNCH_FAILED $msg ==="
                    fi
                    got_terminal=true ;;
                PURCHASE_RECORD\|*)
                    local _pr ord prds st ack ar tk
                    IFS='|' read -r _pr ord prds st ack ar tk <<< "$msg"
                    printf "    • 单号: %-24s | 商品: %-26s | 状态:%s | 已确认:%s | 续费:%s\n" \
                        "${ord:-}" "${prds:-}" "${st:-}" "${ack:-}" "${ar:-}" ;;
                "=== PURCHASES_SYNC_DONE"*)
                    FRIDA_SYNC_COUNT=$(echo "$msg" | sed -n 's/.*count=\([0-9]*\).*/\1/p')
                    FRIDA_SYNC_ACKED=$(echo "$msg" | sed -n 's/.*acked=\([0-9]*\).*/\1/p')
                    FRIDA_RESULT="PURCHASES_SYNC_DONE"
                    got_terminal=true ;;
                "=== PURCHASE_ACKNOWLEDGED"*)
                    ok "订单已完成 Acknowledge 确认: $msg" >&2 ;;
                "=== TRIAL_ACTIVATED ===")
                    ok "订阅已激活！" >&2
                    FRIDA_RESULT="TRIAL_ACTIVATED"
                    got_terminal=true ;;
                "=== USER_CANCELLED ===")
                    FRIDA_RESULT="USER_CANCELLED"; got_terminal=true ;;
                "=== ITEM_ALREADY_OWNED ===")
                    FRIDA_RESULT="ITEM_ALREADY_OWNED"; got_terminal=true ;;
                "=== LIST_COMPLETE ===")
                    FRIDA_RESULT="LIST_COMPLETE"; got_terminal=true ;;
                "=== NO_TRIALS ===")
                    FRIDA_RESULT="NO_TRIALS"; got_terminal=true ;;
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
                "=== BROWSE_COMPLETE ===")
                    ok "已读取 $OFFER_COUNT 个可用方案" >&2
                    FRIDA_RESULT="BROWSE_COMPLETE"
                    got_terminal=true ;;
                "=== SKU_NOT_FOUND"*|\
                "=== SELECT_FAILED"*|\
                "=== NO_ACTIVITY"*|\
                "=== CONNECT_FAILED"*|\
                "=== QUERY_FAILED"*|\
                "=== STACK_NO_ACTIVE_SUB"*|\
                "=== PURCHASES_QUERY_FAILED"*|\
                "=== LAUNCH_ERROR"*|\
                "=== PURCHASE_FAILED"*)
                    err "$msg"
                    FRIDA_RESULT="$msg"
                    got_terminal=true ;;
            esac
        done <<< "$new_output"

        $got_terminal && break
    done

    if ! $got_terminal; then
        err "等待计费回调超时 (25s)"
        FRIDA_RESULT="TIMEOUT"
    fi

    # CRITICAL FIX: Only kill Frida if caller does NOT need PurchasesUpdatedListener alive!
    if [[ "$keep_alive_on_launch" != "true" || "$FRIDA_RESULT" != "BILLING_FLOW_LAUNCHED" ]]; then
        kill "$FRIDA_PID" >/dev/null 2>&1 || true
        FRIDA_PID=""
        rm -f "$tmp_script" "$oneshot_log" 2>/dev/null || true
    else
        # Keep FRIDA_PID & tmp_script alive until caller calls stop_frida_oneshot!
        _ONESHOT_TMP_SCRIPT="$tmp_script"
        _ONESHOT_LOG_FILE="$oneshot_log"
    fi
}

stop_frida_oneshot() {
    [[ -n "${FRIDA_PID:-}" ]] && kill "$FRIDA_PID" >/dev/null 2>&1 || true
    FRIDA_PID=""
    [[ -n "${_ONESHOT_TMP_SCRIPT:-}" ]] && rm -f "$_ONESHOT_TMP_SCRIPT" 2>/dev/null || true
    [[ -n "${_ONESHOT_LOG_FILE:-}" ]] && rm -f "$_ONESHOT_LOG_FILE" 2>/dev/null || true
    _ONESHOT_TMP_SCRIPT=""
    _ONESHOT_LOG_FILE=""
}

# Backward-compatible run_frida alias
run_frida() {
    run_frida_oneshot "${1:-}" "$MODE" "$SELECTED_INDEX" "false"
}

# ===== CJK-Aligned Offer Table Renderer =====
display_offer_menu() {
    if (( OFFER_COUNT <= 0 )); then
        warn "当前未扫描到可展示的订阅方案"
        return 0
    fi
    python3 - << 'PYEOF' \
        "$OFFER_COUNT" \
        "$(printf '%s\x1f' ${OFFER_NAME[@]+"${OFFER_NAME[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_TYPE[@]+"${OFFER_TYPE[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_TRIAL_PERIOD[@]+"${OFFER_TRIAL_PERIOD[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_PRICE[@]+"${OFFER_PRICE[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_PERIOD[@]+"${OFFER_PERIOD[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_RENEW_PRICE[@]+"${OFFER_RENEW_PRICE[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_CYCLES[@]+"${OFFER_CYCLES[@]}"})" \
        "$(printf '%s\x1f' ${OFFER_OFFERID[@]+"${OFFER_OFFERID[@]}"})"
import sys, unicodedata, os

count = int(sys.argv[1])
def split_arg(idx):
    s = sys.argv[idx] if idx < len(sys.argv) else ""
    return s.split("\x1f")[:-1] if s else []

names = split_arg(2)
types = split_arg(3)
tperiods = split_arg(4)
prices = split_arg(5)
periods = split_arg(6)
renews = split_arg(7)
cycles = split_arg(8)
oids = split_arg(9)

tty = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
C_RST = "\033[0m" if tty else ""
C_BLD = "\033[1m" if tty else ""
C_CYN = "\033[38;5;87m" if tty else ""
C_GRN = "\033[38;5;84m" if tty else ""
C_YLW = "\033[38;5;221m" if tty else ""
C_DIM = "\033[2m" if tty else ""

def disp_width(s):
    w = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w

def pad(s, target):
    cur = disp_width(s)
    if cur > target:
        out = ""
        w = 0
        for ch in s:
            cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if w + cw > target - 2:
                out += ".."
                w += 2
                break
            out += ch
            w += cw
        return out + " " * max(0, target - w)
    return s + " " * (target - cur)

dur_map = {"P1W": "7天", "P1M": "1月", "P3M": "3月", "P6M": "6月", "P1Y": "12月", "P12M": "12月"}
per_map = {"P1M": "/月", "P3M": "/季", "P6M": "/半年", "P1Y": "/年", "P12M": "/年"}

print("")
print(f"{C_BLD}{C_CYN}╭────┬──────────────────────────┬──────────────┬──────────────────────────────┬────────────────────╮{C_RST}")
print(f"{C_BLD}{C_CYN}│ {pad('#',2)} │ {pad('套餐方案 Plan',24)} │ {pad('类型标签',12)} │ {pad('计费明细 Pricing',28)} │ {pad('Offer ID',18)} │{C_RST}")
print(f"{C_BLD}{C_CYN}├────┼──────────────────────────┼──────────────┼──────────────────────────────┼────────────────────┤{C_RST}")

for i in range(count):
    nm = names[i] if i < len(names) else ""
    tp = types[i] if i < len(types) else "BASE"
    trp = tperiods[i] if i < len(tperiods) else ""
    pr = prices[i] if i < len(prices) else ""
    pe = periods[i] if i < len(periods) else ""
    rn = renews[i] if i < len(renews) else ""
    cy = cycles[i] if i < len(cycles) else "0"
    oid = oids[i] if i < len(oids) else "base"

    pe_lbl = per_map.get(pe, f"/{pe}" if pe else "")

    if tp == "TRIAL":
        d_lbl = dur_map.get(trp, trp or "试用")
        badge_raw = f"★ 免费{d_lbl}"
        price_raw = f"首期 $0 → {pr}{pe_lbl}"
        row_color = C_GRN
    elif tp == "PROMO":
        c_str = f"前{cy}期" if cy and cy != "0" else "首期"
        badge_raw = f"⚡ 特惠促销"
        price_raw = f"{c_str} {pr} → {rn}{pe_lbl}" if rn else f"{pr}{pe_lbl}"
        row_color = C_YLW
    else:
        badge_raw = "标准付费"
        price_raw = f"{pr}{pe_lbl}"
        row_color = C_DIM

    c_num = pad(str(i + 1), 2)
    c_nm = pad(nm, 24)
    c_bg = pad(badge_raw, 12)
    c_pr = pad(price_raw, 28)
    c_id = pad(oid, 18)
    print(f"│ {C_BLD}{c_num}{C_RST} │ {row_color}{c_nm}{C_RST} │ {row_color}{c_bg}{C_RST} │ {row_color}{c_pr}{C_RST} │ {C_DIM}{c_id}{C_RST} │")

print(f"{C_BLD}{C_CYN}╰────┴──────────────────────────┴──────────────┴──────────────────────────────┴────────────────────╯{C_RST}")
print("")
PYEOF
}

_auto_trial_cleanup() {
    stop_frida_oneshot
}

# ===== CLI Entry Point (when auto-trial.sh is executed directly) =====
main() {
    trap _auto_trial_cleanup EXIT
    _parse_auto_trial_args "$@"
    [[ "$MODE" != "launch_sku" && "$MODE" != "query_purchases" ]] && resolve_product_alias

    # Load optional rich UI helpers when run standalone
    [[ -f "$SCRIPT_DIR/lib/theme-ui.sh" ]] && source "$SCRIPT_DIR/lib/theme-ui.sh" && load_gtool_conf
    [[ -f "$SCRIPT_DIR/lib/ui-helpers.sh" ]] && source "$SCRIPT_DIR/lib/ui-helpers.sh"
    [[ -f "$SCRIPT_DIR/lib/account-mgmt.sh" ]] && source "$SCRIPT_DIR/lib/account-mgmt.sh"
    [[ -f "$SCRIPT_DIR/lib/doctor.sh" ]] && source "$SCRIPT_DIR/lib/doctor.sh"
    [[ -f "$SCRIPT_DIR/lib/presets.sh" ]] && source "$SCRIPT_DIR/lib/presets.sh"

    echo ""
    echo "${C_BOLD:-}=== Google AI Pro / Ultra Trial Assistant ===${C_RESET:-}"
    echo "📖 技术博客：https://blog.caowo.de/  |  🛒 发卡网（仅提供 GPT 代充）：https://faka.cdkey.si/"
    echo ""

    if [[ "$MODE" == "query_purchases" ]]; then
        sync_and_acknowledge_purchases
        return 0
    fi

    detect_device
    setup_frida
    ensure_vending_ready

    [[ ! -f "$FRIDA_SCRIPT" ]] && die "未找到 Frida 脚本: $FRIDA_SCRIPT"

    if [[ "$MODE" == "browse" ]]; then
        start_live_frida_session || die "计费引擎初始化失败"
        [[ $OFFER_COUNT -eq 0 ]] && die "当前账号未返回任何可用订阅方案"
        while true; do
            display_offer_menu
            local choice=""
            read -rp "  输入方案序号立即拉起 (1-$OFFER_COUNT, q=退出): " choice || choice="q"
            [[ "$choice" == "q" || "$choice" == "Q" ]] && break
            if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= OFFER_COUNT )); then
                local s_idx=$((choice - 1))
                local s_prod="${OFFER_PRODUCT[$s_idx]}"
                local s_oid="${OFFER_OFFERID[$s_idx]}"
                local s_name="${OFFER_NAME[$s_idx]}"
                local s_type="${OFFER_TYPE[$s_idx]}"
                local s_price="${OFFER_PRICE[$s_idx]}"
                local is_paid="false"
                if [[ "$s_type" != "TRIAL" ]]; then
                    is_paid="true"
                    echo ""
                    echo "  ⚠️  注意：这是付费方案 ($s_type: $s_price)，非 \$0 免费试用！"
                    local confirm=""
                    read -rp "  确认拉起收银台？(yes/no): " confirm || confirm="no"
                    [[ "$confirm" != "yes" && "$confirm" != "y" ]] && continue
                fi
                local rc=0
                interactive_checkout_cockpit "LAUNCH_OFFER|${s_prod}|${s_oid}" "#$choice $s_name ($s_oid)" "$is_paid" || rc=$?
                [[ $rc -eq 2 ]] && continue
                break
            else
                err "请输入 1 到 $OFFER_COUNT 之间的序号"
            fi
        done
        return 0
    fi

    if [[ "$STACK_ENABLED" == "true" && -z "$OLD_PURCHASE_TOKEN" ]]; then
        OLD_PURCHASE_TOKEN=$(read_play_library_token "subs_variant" || read_play_library_token "g1." || echo "")
    fi

    local pid
    pid=$(ensure_google_one_pid "false")
    run_frida_oneshot "$pid" "$MODE" "$SELECTED_INDEX" "true"

    if [[ "$FRIDA_RESULT" == "BILLING_FLOW_LAUNCHED" ]]; then
        echo ""
        ok "收银台已弹出！脚本正保持后台监听以自动完成订单确认 (Acknowledge)..."
        echo "  请在模拟器完成确认（按 Ctrl+C 或 Enter 结束监听）"
        read -r -t 120 _ || true
        stop_frida_oneshot
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
