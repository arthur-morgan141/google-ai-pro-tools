#!/usr/bin/env bash
# lib/doctor.sh — Instant Device Radar, Environment/Network Doctor, Purchase Sync & Stacking Token Reader

RADAR_CONNECTED="false"
RADAR_DEVICE=""
RADAR_INSTANCE_NAME=""
RADAR_OTHER_INSTANCES=""
RADAR_MODEL=""
RADAR_ACCOUNTS=""
RADAR_FRIDA_PID=""
RADAR_MODULE_OK="no"
RADAR_VENDING_PID=""
RADAR_G1_INSTALLED="no"
RADAR_G1_PID=""
RADAR_NET_OK="no"

# Fast (<0.3s) non-intrusive status probe for the startup dashboard
quick_device_radar() {
    RADAR_CONNECTED="false"
    RADAR_DEVICE=""
    RADAR_INSTANCE_NAME=""
    RADAR_OTHER_INSTANCES=""
    RADAR_MODEL=""
    RADAR_ACCOUNTS=""
    RADAR_FRIDA_PID=""
    RADAR_MODULE_OK="no"
    RADAR_VENDING_PID=""
    RADAR_G1_INSTALLED="no"
    RADAR_G1_PID=""
    RADAR_NET_OK="no"

    [[ -z "${ADB:-}" || ! -x "${ADB:-}" ]] && return 0

    local dev=""
    # 1. Fast exact discovery via mumutool (20ms, zero blind port timeouts!)
    if [[ -n "${MUMUTOOL:-}" && -x "$MUMUTOOL" && -z "${DEVICE:-}" && -z "${DEVICE_PORT:-}" ]]; then
        local mjson
        mjson=$("$MUMUTOOL" info all 2>/dev/null || echo "")
        if [[ -n "$mjson" ]]; then
            local m_parsed
            m_parsed=$(python3 -c '
import json, sys
try:
    res = json.loads(sys.stdin.read()).get("return", {}).get("results", [])
    runs = [r for r in res if r.get("state") == "running" and r.get("adb_port")]
    others = []
    primary_idx = runs[0]["index"] if runs else -1
    for r in res:
        if r.get("index") == primary_idx:
            continue
        st = "运行中" if r.get("state") == "running" else "已休眠"
        nm = r.get("name") or "MuMu"
        others.append(f"{nm}({st})")
    joined = ", ".join(others)
    if runs:
        port = runs[0]["adb_port"]
        rname = runs[0].get("name") or ""
        print(f"127.0.0.1:{port}|{rname}|{joined}")
    else:
        print(f"||{joined}")
except Exception:
    pass
' <<< "$mjson")
            local mp_dev mp_name mp_others
            IFS='|' read -r mp_dev mp_name mp_others <<< "$m_parsed"
            RADAR_OTHER_INSTANCES="${mp_others:-}"
            if [[ -n "$mp_dev" ]]; then
                "$ADB" connect "$mp_dev" >/dev/null 2>&1 || true
                dev="$mp_dev"
                RADAR_INSTANCE_NAME="$mp_name"
                MUMU_INSTANCE_NAME="$mp_name"
            else
                # All MuMu instances stopped — return immediately in 20ms without scanning closed ports!
                dev=$("$ADB" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')
                [[ -z "$dev" ]] && return 0
            fi
        fi
    fi

    if [[ -z "$dev" ]]; then
        if [[ -n "${DEVICE:-}" ]]; then
            dev="$DEVICE"
            RADAR_INSTANCE_NAME="${MUMU_INSTANCE_NAME:-}"
        elif [[ -n "${DEVICE_PORT:-}" ]]; then
            "$ADB" connect "127.0.0.1:$DEVICE_PORT" >/dev/null 2>&1 || true
            dev="127.0.0.1:$DEVICE_PORT"
        else
            dev=$("$ADB" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')
            if [[ -z "$dev" ]]; then
                local p
                for p in 16384 16416 16448 7555; do
                    if "$ADB" connect "127.0.0.1:$p" 2>/dev/null | $_GREP -q "connected"; then
                        dev="127.0.0.1:$p"
                        break
                    fi
                done
            fi
        fi
    fi

    [[ -z "$dev" ]] && return 0
    if ! "$ADB" -s "$dev" get-state >/dev/null 2>&1; then
        return 0
    fi

    DEVICE="$dev"
    RADAR_CONNECTED="true"
    RADAR_DEVICE="$dev"

    # Single combined shell query for maximum speed!
    local raw
    raw=$("$ADB" -s "$dev" shell '
        echo "MODEL=$(getprop ro.product.model)"
        echo "FRIDA=$(pidof frida-server 2>/dev/null | awk "{print \$1}")"
        [ -s "'"$MODULE_APK_DEVICE"'" ] && echo "MOD=yes" || echo "MOD=no"
        echo "VEND=$(pidof com.android.vending 2>/dev/null | awk "{print \$1}")"
        echo "G1PID=$(pidof '"$GOOGLE_ONE_PKG"' 2>/dev/null | awk "{print \$1}")"
        pm path '"$GOOGLE_ONE_PKG"' >/dev/null 2>&1 && echo "G1PKG=yes" || echo "G1PKG=no"
        dumpsys connectivity 2>/dev/null | grep -q "VALIDATED" && echo "NET=yes" || echo "NET=no"
        dumpsys account 2>/dev/null | sed -n "s/.*Account *{name=\([^,]*\), *type=com\.google.*/ACCT=\1/p" | sort -u
    ' 2>/dev/null | tr -d '\r' || true)

    local accts=()
    while IFS='=' read -r k v; do
        case "$k" in
            MODEL) RADAR_MODEL="$v" ;;
            FRIDA) RADAR_FRIDA_PID="$v" ;;
            MOD)   RADAR_MODULE_OK="$v" ;;
            VEND)  RADAR_VENDING_PID="$v" ;;
            G1PID) RADAR_G1_PID="$v" ;;
            G1PKG) RADAR_G1_INSTALLED="$v" ;;
            NET)   RADAR_NET_OK="$v" ;;
            ACCT)  [[ -n "$v" ]] && accts+=("$v") ;;
        esac
    done <<< "$raw"

    if (( ${#accts[@]} > 0 )); then
        local IFS=", "
        RADAR_ACCOUNTS="${accts[*]}"
    fi
}

# Scan & manage MuMu instances / ADB devices interactively
select_device_interactive() {
    if [[ -n "${MUMUTOOL:-}" && -x "$MUMUTOOL" ]]; then
        local mjson
        mjson=$("$MUMUTOOL" info all 2>/dev/null || echo "")
        if [[ -n "$mjson" ]]; then
            local entries=()
            while IFS= read -r row; do
                [[ -n "$row" ]] && entries+=("$row")
            done < <(python3 -c '
import json, sys
try:
    for r in json.loads(sys.stdin.read()).get("return", {}).get("results", []):
        idx = r.get("index", 0)
        st = r.get("state", "stopped")
        port = r.get("adb_port", 0)
        nm = r.get("name", f"MuMu-{idx}")
        print(f"{idx}|{st}|{port}|{nm}")
except Exception:
    pass
' <<< "$mjson")

            if (( ${#entries[@]} > 0 )); then
                echo ""
                echo "  📱 本地 MuMu 模拟器实例列表："
                local k
                for k in "${!entries[@]}"; do
                    local ei est eport ename
                    IFS='|' read -r ei est eport ename <<< "${entries[$k]}"
                    if [[ "$est" == "running" ]]; then
                        printf "    ${C_BOLD}%d)${C_RESET} ${C_GREEN}● 运行中${C_RESET}  %-20s  端口: 127.0.0.1:%-6s (index=%s)\n" "$((k+1))" "$ename" "$eport" "$ei"
                    else
                        printf "    ${C_BOLD}%d)${C_RESET} ${C_DIM}○ 已关闭${C_RESET}  %-20s  选择即可一键启动      (index=%s)\n" "$((k+1))" "$ename" "$ei"
                    fi
                done
                echo ""
                local pick=""
                read -rp "  输入序号切换或启动实例 [1-${#entries[@]}, Enter=取消]: " pick
                [[ -z "$pick" ]] && return 0
                if [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#entries[@]} )); then
                    local ei est eport ename
                    IFS='|' read -r ei est eport ename <<< "${entries[$((pick-1))]}"
                    _cleanup_live_frida 2>/dev/null || true
                    if [[ "$est" == "running" && "$eport" != "0" ]]; then
                        DEVICE="127.0.0.1:$eport"
                        DEVICE_PORT="$eport"
                        MUMU_INSTANCE_NAME="$ename"
                        "$ADB" connect "$DEVICE" >/dev/null 2>&1 || true
                        ok "已切换至【$ename】($DEVICE)"
                        return 0
                    else
                        DEVICE=""
                        DEVICE_PORT=""
                        step_begin "正在唤醒【$ename】(index=$ei)..."
                        "$MUMUTOOL" open "$ei" >/dev/null 2>&1 || true
                        local w
                        for ((w=0; w<45; w++)); do
                            sleep 1
                            local b_port
                            b_port=$("$MUMUTOOL" info "$ei" 2>/dev/null | python3 -c '
import json, sys
try:
    j = json.loads(sys.stdin.read()).get("return", {})
    if "results" in j and j["results"]: j = j["results"][0]
    if j.get("state") == "running" and j.get("adb_port"): print(j["adb_port"])
except Exception: pass
')
                            if [[ -n "$b_port" ]]; then
                                "$ADB" connect "127.0.0.1:$b_port" >/dev/null 2>&1 || true
                                local bc_done
                                bc_done=$("$ADB" -s "127.0.0.1:$b_port" shell "getprop sys.boot_completed" 2>/dev/null | tr -d '\r\n' || echo "")
                                if [[ "$bc_done" == "1" ]]; then
                                    DEVICE="127.0.0.1:$b_port"
                                    DEVICE_PORT="$b_port"
                                    MUMU_INSTANCE_NAME="$ename"
                                    step_end "【$ename】已启动就绪 ($DEVICE)"
                                    return 0
                                fi
                            fi
                        done
                        err "启动超时，请稍后再试"
                        return 1
                    fi
                fi
                return 1
            fi
        fi
    fi

    log "正在扫描所有可用的 Android 设备..."
    local p
    for p in 16384 16416 16448 16480 16512 7555; do
        "$ADB" connect "127.0.0.1:$p" >/dev/null 2>&1 || true
    done

    local devs=()
    while IFS= read -r d; do
        [[ -n "$d" ]] && devs+=("$d")
    done < <("$ADB" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1}')

    if (( ${#devs[@]} == 0 )); then
        err "未检测到任何在线模拟器，请先启动 MuMu 模拟器"
        return 1
    elif (( ${#devs[@]} == 1 )); then
        DEVICE="${devs[0]}"
        ok "已锁定唯一在线设备: $DEVICE"
        return 0
    fi

    echo ""
    echo "  检测到多台在线设备："
    local i
    for i in "${!devs[@]}"; do
        local d="${devs[$i]}"
        local m acct
        m=$("$ADB" -s "$d" shell "getprop ro.product.model" 2>/dev/null | tr -d '\r\n')
        acct=$("$ADB" -s "$d" shell "dumpsys account" 2>/dev/null | sed -n 's/.*Account *{name=\([^,]*\), *type=com\.google.*/\1/p' | sort -u | head -1 | tr -d '\r\n')
        printf "    ${C_BOLD}%d)${C_RESET} %-20s  型号: %-12s  账号: %s\n" "$((i+1))" "$d" "${m:-unknown}" "${acct:-未登录}"
    done
    echo ""
    local pick
    read -rp "  请选择目标设备序号 [1-${#devs[@]}, 默认 1]: " pick
    pick="${pick:-1}"
    if [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#devs[@]} )); then
        DEVICE="${devs[$((pick-1))]}"
        DEVICE_PORT="${DEVICE#127.0.0.1:}"
        ok "已切换至设备: $DEVICE"
        return 0
    fi
    err "选择无效"
    return 1
}

# Read active purchaseToken from Play Store's library.db (WAL + su root aware, for --stack 12+6+6m!)
_pull_play_library_dir() {
    local local_dir="${1:-}"
    [[ -z "$local_dir" ]] && return 1
    local remote_dir="/data/local/tmp/.gtool_db_$$"
    (umask 077; mkdir -p "$local_dir")
    chmod 700 "$local_dir" 2>/dev/null || true
    local cp_res
    cp_res=$(adb_root_shell "rm -rf $remote_dir && mkdir -p $remote_dir && cp /data/data/com.android.vending/databases/library.db* $remote_dir/ 2>/dev/null && chmod -R 755 $remote_dir && [ -s $remote_dir/library.db ] && echo COPY_OK" || true)
    if [[ "$cp_res" != *"COPY_OK"* ]]; then
        adb_root_shell "rm -rf $remote_dir" >/dev/null 2>&1 || true
        return 1
    fi
    local sfx
    for sfx in "" "-wal" "-shm"; do
        "$ADB" -s "$DEVICE" pull "${remote_dir}/library.db${sfx}" "${local_dir}/library.db${sfx}" >/dev/null 2>&1 || true
    done
    adb_root_shell "rm -rf $remote_dir" >/dev/null 2>&1 || true
    [[ -s "${local_dir}/library.db" ]]
}

read_play_library_token() {
    local sku_hint="${1:-g1.}"
    local local_dir="/tmp/.gtool_libdir_$$"
    if ! _pull_play_library_dir "$local_dir"; then
        rm -rf "$local_dir" 2>/dev/null || true
        return 1
    fi

    local token
    token=$(python3 - "${local_dir}/library.db" "$sku_hint" << 'PYEOF' 2>/dev/null || true
import sqlite3, json, sys, time

db_path, hint = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db_path)
cur = con.cursor()
rows = cur.execute(
    "SELECT account, doc_id, subs_valid_until_time, inapp_purchase_data FROM ownership WHERE doc_id LIKE ?",
    (f"%{hint}%",)
).fetchall()
now_ms = int(time.time() * 1000)
picked = None
for account, doc_id, valid, data in rows:
    if not data:
        continue
    try:
        j = json.loads(data)
    except Exception:
        continue
    tk = j.get("purchaseToken")
    if not tk:
        continue
    v_ms = int(valid or 0)
    alive = v_ms > now_ms
    auto_renew = bool(j.get("autoRenewing", True))
    score = (1 if alive else 0, 1 if auto_renew else 0, v_ms)
    if picked is None or score > picked[0]:
        picked = (score, tk, account, doc_id, v_ms, auto_renew)
con.close()
if picked:
    print(picked[1])
PYEOF
)
    rm -rf "$local_dir" 2>/dev/null || true
    [[ -n "$token" ]] && { echo "$token"; return 0; }
    return 1
}

# Print formatted Play Store subscription ownership summary from library.db (+ WAL)
print_play_library_subscriptions() {
    local local_dir="/tmp/.gtool_libdir_$$"
    if ! _pull_play_library_dir "$local_dir"; then
        rm -rf "$local_dir" 2>/dev/null || true
        return 0
    fi

    python3 - "${local_dir}/library.db" << 'PYEOF' 2>/dev/null || true
import sqlite3, json, sys, time, datetime

con = sqlite3.connect(sys.argv[1])
rows = con.execute(
    "SELECT account, doc_id, subs_valid_until_time, inapp_purchase_data FROM ownership WHERE doc_id LIKE '%g1.%' OR inapp_purchase_data LIKE '%g1.%'"
).fetchall()
con.close()

if not rows:
    print("    (Play 本地库未见 g1.* 订阅记录 — 当前账号干净，适合首开或特惠促销)")
    sys.exit(0)

now_ms = int(time.time() * 1000)
for acc, doc_id, valid, data in rows:
    j = json.loads(data) if data else {}
    v_ms = int(valid or 0)
    exp_str = datetime.datetime.fromtimestamp(v_ms / 1000).strftime("%Y-%m-%d") if v_ms > 0 else "N/A"
    alive = "🟢 有效" if v_ms > now_ms else "⚪ 已过期"
    ack = "✓已确认" if j.get("acknowledged") else "⚠️未确认(需补单)"
    renew = "自动续费开" if j.get("autoRenewing") else "已关续费"
    order = j.get("orderId", "N/A")
    print(f"    • {acc} | {doc_id} | {alive} 至 {exp_str} | {ack} | {renew} | 单号:{order}")
PYEOF
    rm -rf "$local_dir" 2>/dev/null || true
}

# Comprehensive Environment & Network Doctor (non-destructive unless auto_fix=true)
run_doctor() {
    local auto_fix="${1:-true}"
    echo ""
    echo "${C_BOLD}${C_CYAN}╭──────────────────────────────────────────────────────────────────╮${C_RESET}"
    echo "${C_BOLD}${C_CYAN}│              🩺  设备、Frida 与网络环境全链路体检                │${C_RESET}"
    echo "${C_BOLD}${C_CYAN}╰──────────────────────────────────────────────────────────────────╯${C_RESET}"
    echo ""

    # 1. Host tools
    log "1/6 检查宿主机工具链..."
    ok "Bash 版本: ${BASH_VERSION}"
    ok "ADB 路径 : $ADB"
    if command -v frida >/dev/null 2>&1; then
        ok "Frida CLI: $(frida --version 2>/dev/null)"
    else
        err "宿主机未安装 frida-tools (请运行: pip3 install frida-tools)"
        return 1
    fi
    check_totp_tools
    [[ -n "$TOTP_TOOL" ]] && ok "2FA 引擎 : $TOTP_TOOL"

    # 2. Emulator connection
    echo ""
    log "2/6 检查模拟器连接..."
    detect_device
    local model abi sdk_ver
    model=$(adb_shell "getprop ro.product.model")
    abi=$(adb_shell "getprop ro.product.cpu.abi")
    sdk_ver=$(adb_shell "getprop ro.build.version.release")
    ok "已连接设备: $DEVICE ($model, Android $sdk_ver, $abi)"

    # 3. Root & frida-server + module.apk
    echo ""
    log "3/6 检查 Root、frida-server 与 Billing 模块..."
    local uid_info
    uid_info=$(adb_shell "id")
    if [[ "$uid_info" != *"uid=0"* ]]; then
        local su_info
        su_info=$(adb_shell "su -c id 2>/dev/null || su 0 id 2>/dev/null || true")
        if [[ "$su_info" == *"uid=0"* ]]; then
            uid_info="$su_info"
        else
            "$ADB" -s "$DEVICE" root >/dev/null 2>&1 || true
            sleep 1
            [[ "$DEVICE" == 127.0.0.1:* ]] && "$ADB" connect "$DEVICE" >/dev/null 2>&1 || true
            uid_info=$(adb_shell "id")
        fi
    fi
    if [[ "$uid_info" == *"uid=0"* ]]; then
        ok "ADB Root 权限已就绪"
    else
        warn "当前 adbd 非 root ($uid_info)，如遇权限受限请在 MuMu 设置中开启 ROOT"
    fi

    setup_frida

    # 4. Play Store & Google One status
    echo ""
    log "4/6 检查 Google Play 商店与 Google One..."
    ensure_vending_ready
    if adb_shell "pm path $GOOGLE_ONE_PKG" | $_GREP -q "package:"; then
        ok "Google One 已安装 ($GOOGLE_ONE_PKG)"
    else
        warn "设备上尚未安装 Google One（快捷或批量时可自动从 Play 商店安装）"
    fi

    # 5. Network & Proxy diagnostics
    echo ""
    log "5/6 检查模拟器网络连通性与代理状态..."
    local proxy cap_mode net_valid
    proxy=$(adb_shell "settings get global http_proxy")
    cap_mode=$(adb_shell "settings get global captive_portal_mode")
    net_valid=$(adb_shell "dumpsys connectivity | grep -q VALIDATED && echo yes || echo no")

    if [[ -n "$proxy" && "$proxy" != "null" && "$proxy" != ":0" ]]; then
        warn "检测到系统全局 HTTP 代理: $proxy"
    else
        ok "全局 HTTP 代理干净 (未设置残留死代理)"
    fi

    local http_check
    http_check=$(adb_shell "curl -sI -o /dev/null -w '%{http_code} %{time_total}' --connect-timeout 5 https://play.google.com 2>/dev/null || echo '000 0'")
    local http_code="${http_check%% *}"
    local http_time="${http_check##* }"

    if [[ "$http_code" =~ ^(200|301|302|303)$ ]]; then
        ok "Google Play HTTPS 直连正常 (HTTP $http_code, 耗时 ${http_time}s)"
        if [[ "$net_valid" != "yes" && "$auto_fix" == "true" ]]; then
            log "网络实际畅通但系统连通性标记未刷新，正在关闭误报 Captive Portal 检测..."
            adb_shell "settings put global captive_portal_detection_enabled 0; settings put global captive_portal_mode 0" >/dev/null || true
            ok "已消除「未连接到互联网」误报状态"
        fi
    else
        err "模拟器访问 https://play.google.com 异常 (HTTP $http_code)"
        if [[ "$auto_fix" == "true" && -n "$proxy" && "$proxy" != "null" && "$proxy" != ":0" ]]; then
            log "正在清理失效的全局代理 $proxy 并重试..."
            adb_shell "settings put global http_proxy :0" >/dev/null || true
            http_check=$(adb_shell "curl -sI -o /dev/null -w '%{http_code}' --connect-timeout 5 https://play.google.com 2>/dev/null || echo '000'")
            if [[ "$http_check" =~ ^(200|301|302)$ ]]; then
                ok "清理残留代理后 Google Play 网络已恢复正常 (HTTP $http_check)！"
            fi
        else
            hint "请检查宿主机代理/TUN 分流或重启一次 MuMu 模拟器"
        fi
    fi

    # 6. Accounts & Play Subscriptions
    echo ""
    log "6/6 当前登录账号与 Play 订阅状态快照..."
    local accts a=""
    accts=$(list_google_accounts)
    if [[ -z "$accts" ]]; then
        warn "当前设备未登录任何 Google 账号"
    else
        while IFS= read -r a; do
            [[ -n "$a" ]] && ok "已登录账号: $a"
        done <<< "$accts"
    fi
    print_play_library_subscriptions

    echo ""
    ok "体检全部完成！ 📖 技术博客: https://blog.caowo.de/ | 🛒 发卡网(GPT代充): https://faka.cdkey.si/"
}

# Ensure Play Store daemon is alive so BillingClient RPC never hangs
ensure_vending_ready() {
    local vpid
    vpid=$(adb_shell "pidof com.android.vending" | awk '{print $1}')
    if [[ -n "$vpid" ]]; then
        ok "Play 商店服务在线 (PID $vpid)"
        return 0
    fi
    log "正在唤醒 Play 商店后台服务..."
    adb_shell "monkey -p com.android.vending -c android.intent.category.LAUNCHER 1" >/dev/null 2>&1 || true
    local i
    for ((i=0; i<12; i++)); do
        sleep 0.4
        vpid=$(adb_shell "pidof com.android.vending" | awk '{print $1}')
        if [[ -n "$vpid" ]]; then
            go_home
            ok "Play 商店服务已唤醒 (PID $vpid)"
            return 0
        fi
    done
    warn "Play 商店启动较慢，若拉起收银台超时请手动点开一次 Play 商店"
}

# One-click Query + Acknowledge + Refresh Entitlement ("付款成功但订阅未到账" 救星!)
sync_and_acknowledge_purchases() {
    echo ""
    echo "${C_BOLD}${C_CYAN}╭──────────────────────────────────────────────────────────────────╮${C_RESET}"
    echo "${C_BOLD}${C_CYAN}│        🔄  Play 已购订单核验 · 自动补单 Acknowledge · 同步容量   │${C_RESET}"
    echo "${C_BOLD}${C_CYAN}╰──────────────────────────────────────────────────────────────────╯${C_RESET}"
    echo ""

    detect_device
    setup_frida
    ensure_vending_ready

    local cur_acct
    cur_acct=$(list_google_accounts | head -1 || true)
    [[ -n "$cur_acct" ]] && log "当前账号: $cur_acct"

    log "本地 Play 库 (library.db) 记录："
    print_play_library_subscriptions
    echo ""

    step_begin "通过 BillingClient 查询实时订阅并执行补单确认 (acknowledgePurchase)"
    local pid
    pid=$(ensure_google_one_pid "false")
    run_frida_oneshot "$pid" "query_purchases"

    echo ""
    if [[ "${FRIDA_SYNC_COUNT:-0}" -gt 0 ]]; then
        ok "实时查到 ${FRIDA_SYNC_COUNT} 笔有效订阅，本次新补单确认 ${FRIDA_SYNC_ACKED:-0} 笔！"
        log "正在重启刷新 Google One 以同步云端存储空间与 AI 权益..."
        adb_shell "am force-stop $GOOGLE_ONE_PKG" >/dev/null 2>&1 || true
        sleep 0.5
        adb_shell "monkey -p $GOOGLE_ONE_PKG 1" >/dev/null 2>&1 || true
        sleep 1.5
        ok "Google One 已重新拉起，请在模拟器查看容量或点开 Play 订阅页核实！"
        notify_event "success" "订阅补单与权益刷新已完成"
    else
        warn "BillingClient 实时查询返回 0 笔活跃订阅。"
        hint "若银行卡刚显示扣款但此处为 0，通常是收银台网络中断导致交易仅停留在预授权（Google Play 会在数小时至数日原路退回），可在模拟器访问 pay.google.com 查看交易状态。"
    fi

    echo ""
    local open_sub=""
    read -rp "  是否现在在模拟器打开 Play 订阅管理页核对？(y/N): " open_sub || true
    if [[ "$open_sub" == "y" || "$open_sub" == "Y" ]]; then
        adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions'" >/dev/null
        ok "已在模拟器打开 Play 订阅管理页"
    fi
}
