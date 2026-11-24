#!/usr/bin/env bash
# lib/ui-helpers.sh — Fast ADB UI automation primitives with XML caching & zero-animation mode

UI_DUMP_PATH="/data/local/tmp/ui.xml"
UI_LOCAL_TMP="/tmp/.gtool-ui-$$.xml"
LAST_UI_FILE=""
_GREP="${_GREP:-/usr/bin/grep}"
[[ ! -x "$_GREP" ]] && _GREP="grep"

_ORIG_WIN_ANIM=""
_ORIG_TRANS_ANIM=""
_ORIG_DUR_ANIM=""
_ANIM_MODIFIED=false

# ===== Unified Cleanup Registry (prevents trap overwrite bugs) =====
declare -a _CLEANUP_HOOKS=()
register_cleanup() {
    [[ -n "${1:-}" ]] && _CLEANUP_HOOKS+=("${1:-}")
}
_run_all_cleanups() {
    (( ${#_CLEANUP_HOOKS[@]} == 0 )) && return 0
    local hook
    for hook in "${_CLEANUP_HOOKS[@]}"; do
        eval "$hook" 2>/dev/null || true
    done
}
trap _run_all_cleanups EXIT

# ===== Core wrappers =====

adb_shell() {
    "$ADB" -s "$DEVICE" shell "$@" 2>/dev/null | tr -d '\r'
}

adb_root_shell() {
    local cmd="${1:-}"
    [[ -z "$cmd" ]] && return 0
    local uid_out
    uid_out=$(adb_shell "id")
    if [[ "$uid_out" == *"uid=0"* ]]; then
        adb_shell "$cmd"
    else
        local esc="${cmd//\'/\'\"\'\"\'}"
        adb_shell "su -c '$esc' 2>/dev/null || su 0 sh -c '$esc' 2>/dev/null"
    fi
}

_SCREEN_W=0
_SCREEN_H=0
_ensure_screen_dims() {
    if (( _SCREEN_W <= 0 || _SCREEN_H <= 0 )); then
        local wm
        wm=$(adb_shell "wm size 2>/dev/null | tail -1")
        if [[ "$wm" =~ ([0-9]{3,5})x([0-9]{3,5}) ]]; then
            _SCREEN_W="${BASH_REMATCH[1]}"
            _SCREEN_H="${BASH_REMATCH[2]}"
        else
            _SCREEN_W=1080
            _SCREEN_H=2400
        fi
    fi
}

adb_tap_rel() {
    local rx="${1:-50}" ry="${2:-50}"
    _ensure_screen_dims
    local x=$(( _SCREEN_W * rx / 100 ))
    local y=$(( _SCREEN_H * ry / 100 ))
    adb_shell "input tap $x $y"
}

adb_swipe_rel() {
    local rx1="${1:-50}" ry1="${2:-70}" rx2="${3:-50}" ry2="${4:-25}" dur="${5:-280}"
    _ensure_screen_dims
    local x1=$(( _SCREEN_W * rx1 / 100 ))
    local y1=$(( _SCREEN_H * ry1 / 100 ))
    local x2=$(( _SCREEN_W * rx2 / 100 ))
    local y2=$(( _SCREEN_H * ry2 / 100 ))
    adb_shell "input swipe $x1 $y1 $x2 $y2 $dur"
}

# ===== Fast Animation Mode (eliminates UI transition lag & uiautomator waitForIdle delay) =====

enable_fast_animations() {
    [[ "${GTOOL_FAST_ANIM:-on}" != "on" ]] && return 0
    $_ANIM_MODIFIED && return 0
    _ORIG_WIN_ANIM=$(adb_shell "settings get global window_animation_scale" || echo "0.5")
    _ORIG_TRANS_ANIM=$(adb_shell "settings get global transition_animation_scale" || echo "0.5")
    _ORIG_DUR_ANIM=$(adb_shell "settings get global animator_duration_scale" || echo "0.5")
    adb_shell "settings put global window_animation_scale 0; settings put global transition_animation_scale 0; settings put global animator_duration_scale 0" >/dev/null || true
    _ANIM_MODIFIED=true
}

restore_animations() {
    $_ANIM_MODIFIED || return 0
    local w="${_ORIG_WIN_ANIM:-0.5}" t="${_ORIG_TRANS_ANIM:-0.5}" d="${_ORIG_DUR_ANIM:-0.5}"
    [[ "$w" == "null" || -z "$w" ]] && w="0.5"
    [[ "$t" == "null" || -z "$t" ]] && t="0.5"
    [[ "$d" == "null" || -z "$d" ]] && d="0.5"
    adb_shell "settings put global window_animation_scale $w; settings put global transition_animation_scale $t; settings put global animator_duration_scale $d" >/dev/null || true
    _ANIM_MODIFIED=false
}

# ===== Screen management =====

ensure_screen_on() {
    local power_state
    power_state=$(adb_shell "dumpsys power | grep 'Display Power'")
    if [[ "$power_state" != *"state=ON"* ]]; then
        log "唤醒模拟器屏幕..."
        adb_shell "input keyevent KEYCODE_WAKEUP"
        sleep 0.5
        adb_swipe_rel 50 72 50 30 220
        sleep 0.4
    fi
}

# ===== Fast UI dump (single ADB round-trip with compressed hierarchy + fallback) =====

dump_ui() {
    (umask 077; : > "$UI_LOCAL_TMP")
    "$ADB" -s "$DEVICE" shell "uiautomator dump --compressed $UI_DUMP_PATH >/dev/null 2>&1 && cat $UI_DUMP_PATH" 2>/dev/null \
        | tr -d '\r' > "$UI_LOCAL_TMP" || true
    if [[ ! -s "$UI_LOCAL_TMP" ]] || ! $_GREP -q "<hierarchy" "$UI_LOCAL_TMP" 2>/dev/null; then
        adb_shell "uiautomator dump $UI_DUMP_PATH" >/dev/null 2>&1 || true
        "$ADB" -s "$DEVICE" pull "$UI_DUMP_PATH" "$UI_LOCAL_TMP" >/dev/null 2>&1 || true
        chmod 600 "$UI_LOCAL_TMP" 2>/dev/null || true
    fi
    LAST_UI_FILE="$UI_LOCAL_TMP"
    echo "$UI_LOCAL_TMP"
}

# ===== Element lookup on an already-dumped XML file (0ms ADB cost!) =====

find_node_by_text() {
    local xml_file="${1:-}"
    [[ $# -gt 0 ]] && shift
    [[ -z "$xml_file" || ! -s "$xml_file" ]] && return 1
    local content
    content=$(<"$xml_file")
    local text
    for text in "$@"; do
        local escaped
        escaped=$(printf '%s' "$text" | sed 's/[.[\*^$()+?{|\\]/\\&/g')
        local match
        match=$($_GREP -m1 -oE "<node[^>]*(text=\"[^\"]*${escaped}[^\"]*\"|content-desc=\"[^\"]*${escaped}[^\"]*\")[^>]*>" <<< "$content" || true)
        if [[ -n "$match" ]]; then
            $_GREP -m1 -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' <<< "$match" | sed 's/bounds="//;s/"//'
            return 0
        fi
    done
    return 1
}

find_node_by_exact_text() {
    local xml_file="${1:-}"
    local text="${2:-}"
    [[ -z "$xml_file" || ! -s "$xml_file" || -z "$text" ]] && return 1
    local escaped
    escaped=$(printf '%s' "$text" | sed 's/[.[\*^$()+?{|\\]/\\&/g')
    local content
    content=$(<"$xml_file")
    local match
    match=$($_GREP -m1 -oE "<node[^>]*(text=\"${escaped}\"|content-desc=\"${escaped}\")[^>]*>" <<< "$content" || true)
    if [[ -n "$match" ]]; then
        $_GREP -m1 -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' <<< "$match" | sed 's/bounds="//;s/"//'
        return 0
    fi
    return 1
}

# Resolve exact CTA Button bounds (handles non-clickable text inside clickable parent & avoids body text!)
find_button_bounds() {
    local xml_file="${1:-}"
    [[ $# -gt 0 ]] && shift
    [[ -z "$xml_file" || ! -s "$xml_file" ]] && return 1
    python3 - "$xml_file" "$@" << 'PYEOF' 2>/dev/null
import re, sys

xml_path = sys.argv[1]
labels = sys.argv[2:]
if not labels:
    sys.exit(1)

with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
    raw = f.read()

nodes = []
for m in re.finditer(r"<node\b([^>]*?)(/?)>", raw):
    attrs = m.group(1)
    def ga(k):
        am = re.search(rf'\b{k}="([^"]*)"', attrs)
        return am.group(1) if am else ""
    bm = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', attrs)
    if not bm:
        continue
    x1, y1, x2, y2 = map(int, bm.groups())
    nodes.append({
        "text": ga("text"),
        "desc": ga("content-desc"),
        "cls": ga("class"),
        "click": ga("clickable") == "true",
        "bounds": f"[{x1},{y1}][{x2},{y2}]",
        "rect": (x1, y1, x2, y2),
        "area": max(1, (x2 - x1) * (y2 - y1)),
    })

label_set = set(labels)

# 1) Exact match on android.widget.Button
for lb in labels:
    for n in nodes:
        if "Button" in n["cls"] and (n["text"] == lb or n["desc"] == lb):
            print(n["bounds"])
            sys.exit(0)

# 2) Exact match on any clickable node
for lb in labels:
    for n in nodes:
        if n["click"] and (n["text"] == lb or n["desc"] == lb):
            print(n["bounds"])
            sys.exit(0)

# 3) Exact text node -> find tightest enclosing clickable container
for lb in labels:
    exact_nodes = [n for n in nodes if n["text"] == lb or n["desc"] == lb]
    # Prefer lower-screen CTA buttons when multiple exact labels exist
    exact_nodes.sort(key=lambda item: item["rect"][1], reverse=True)
    for tn in exact_nodes:
        tx1, ty1, tx2, ty2 = tn["rect"]
        parents = [
            p for p in nodes
            if p["click"] and p["rect"][0] <= tx1 and p["rect"][1] <= ty1
            and p["rect"][2] >= tx2 and p["rect"][3] >= ty2
        ]
        if parents:
            parents.sort(key=lambda p: p["area"])
            print(parents[0]["bounds"])
            sys.exit(0)
        print(tn["bounds"])
        sys.exit(0)

sys.exit(1)
PYEOF
}

find_edit_text() {
    local xml_file="${1:-}"
    local index="${2:-0}"
    [[ -z "$xml_file" || ! -s "$xml_file" ]] && return 1
    local match
    match=$($_GREP -oE '<node[^>]*class="android\.widget\.EditText"[^>]*>' "$xml_file" | sed -n "$((index+1))p" || true)
    if [[ -n "$match" ]]; then
        $_GREP -m1 -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' <<< "$match" | sed 's/bounds="//;s/"//'
        return 0
    fi
    return 1
}

find_node_by_id() {
    local xml_file="${1:-}"
    local res_id="${2:-}"
    [[ -z "$xml_file" || ! -s "$xml_file" || -z "$res_id" ]] && return 1
    local match
    match=$($_GREP -m1 -oE "<node[^>]*resource-id=\"[^\"]*${res_id}[^\"]*\"[^>]*>" "$xml_file" || true)
    if [[ -n "$match" ]]; then
        $_GREP -m1 -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' <<< "$match" | sed 's/bounds="//;s/"//'
        return 0
    fi
    return 1
}

# ===== Coordinate & Tap Helpers =====

bounds_center() {
    local bounds="${1:-}"
    echo "$bounds" | awk -F'[][ ,]+' '{print int(($2+$4)/2), int(($3+$5)/2)}'
}

tap_bounds() {
    local bounds="${1:-}"
    [[ -z "$bounds" ]] && return 1
    local center x y
    center=$(bounds_center "$bounds")
    x="${center%% *}"
    y="${center##* }"
    adb_shell "input tap $x $y"
}

# Zero-dump cached tap helpers (operate on an already-fetched XML file!)
tap_in_xml() {
    local xml_file="${1:-}"
    [[ $# -gt 0 ]] && shift
    local bounds
    bounds=$(find_node_by_text "$xml_file" "$@") || return 1
    tap_bounds "$bounds"
}

tap_exact_in_xml() {
    local xml_file="${1:-}"
    local text="${2:-}"
    local bounds
    bounds=$(find_node_by_exact_text "$xml_file" "$text") || return 1
    tap_bounds "$bounds"
}

tap_button_in_xml() {
    local xml_file="${1:-}"
    [[ $# -gt 0 ]] && shift
    local bounds
    bounds=$(find_button_bounds "$xml_file" "$@") || return 1
    tap_bounds "$bounds"
}

# Fresh-dump tap helpers (backward-compatible)
tap_containing() {
    local xml_file
    xml_file=$(dump_ui)
    tap_in_xml "$xml_file" "$@"
}

tap_exact() {
    local text="${1:-}"
    local xml_file
    xml_file=$(dump_ui)
    tap_exact_in_xml "$xml_file" "$text"
}

tap_button() {
    local xml_file
    xml_file=$(dump_ui)
    tap_button_in_xml "$xml_file" "$@"
}

tap_edit_text() {
    local index="${1:-0}"
    local xml_file bounds
    xml_file=$(dump_ui)
    bounds=$(find_edit_text "$xml_file" "$index") || return 1
    tap_bounds "$bounds"
}

# ===== Text Input (POSIX single-quote safe on Android /system/bin/sh) =====

_sh_sq() {
    local s="${1:-}"
    printf "'%s'" "${s//\'/\'\"\'\"\'}"
}

type_text() {
    local text="${1:-}"
    [[ -z "$text" ]] && return 0
    if [[ "$text" != *"@"* ]]; then
        local escaped="${text// /%s}"
        adb_shell "input text $(_sh_sq "$escaped")"
        return
    fi
    local remaining="$text"
    while [[ "$remaining" == *"@"* ]]; do
        local before="${remaining%%@*}"
        remaining="${remaining#*@}"
        if [[ -n "$before" ]]; then
            local escaped="${before// /%s}"
            adb_shell "input text $(_sh_sq "$escaped")"
        fi
        adb_shell "input keyevent 77"   # KEYCODE_AT
    done
    if [[ -n "$remaining" ]]; then
        local escaped="${remaining// /%s}"
        adb_shell "input text $(_sh_sq "$escaped")"
    fi
}

type_secret() {
    local text="${1:-}"
    [[ -z "$text" ]] && return 0
    local batch="" i
    for (( i=0; i<${#text}; i++ )); do
        local ch="${text:$i:1}"
        case "$ch" in
            ' '|'@')
                if [[ -n "$batch" ]]; then
                    adb_shell "input text $(_sh_sq "$batch")"
                    sleep 0.04
                    batch=""
                fi
                if [[ "$ch" == ' ' ]]; then
                    adb_shell "input keyevent 62"
                else
                    adb_shell "input keyevent 77"
                fi
                sleep 0.04
                ;;
            [a-zA-Z0-9._,\;:!\?/=+\-])
                batch+="$ch"
                ;;
            *)
                if [[ -n "$batch" ]]; then
                    adb_shell "input text $(_sh_sq "$batch")"
                    sleep 0.04
                    batch=""
                fi
                adb_shell "input text $(_sh_sq "$ch")"
                sleep 0.04
                ;;
        esac
    done
    if [[ -n "$batch" ]]; then
        adb_shell "input text $(_sh_sq "$batch")"
        sleep 0.04
    fi
}

# ===== Fast Poll Helpers (populate LAST_UI_FILE on match!) =====

wait_for_element() {
    local timeout="${1:-10}"
    [[ $# -gt 0 ]] && shift
    local deadline=$((SECONDS + timeout))
    while [[ $SECONDS -lt $deadline ]]; do
        local xml_file
        xml_file=$(dump_ui)
        if find_node_by_text "$xml_file" "$@" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.35
    done
    return 1
}

wait_for_element_gone() {
    local timeout="${1:-10}"
    [[ $# -gt 0 ]] && shift
    local deadline=$((SECONDS + timeout))
    while [[ $SECONDS -lt $deadline ]]; do
        local xml_file
        xml_file=$(dump_ui)
        if ! find_node_by_text "$xml_file" "$@" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.35
    done
    return 1
}

ui_contains_text() {
    local xml_content="${1:-}"
    local text="${2:-}"
    [[ -n "$text" ]] && $_GREP -iq "$text" <<< "$xml_content"
}

# ===== Human-in-the-Loop Gate (for manual verification / challenges — never bypasses CAPTCHAs) =====

wait_human_assist() {
    local prompt_msg="${1:-请手动处理模拟器当前界面}"
    notify_event "attention" "$prompt_msg" 2>/dev/null || true
    echo ""
    echo "  ${C_YELLOW:-}⏸  需要人工协助：${prompt_msg}${C_RESET:-}"
    echo "  ${C_DIM:-}请在 MuMu 模拟器上手动处理该界面，完成后回到终端按 [Enter] 继续（输入 s 跳过当前账号）...${C_RESET:-}"
    local ans=""
    read -rp "  > " ans || ans="s"
    if [[ "$ans" == "s" || "$ans" == "S" ]]; then
        return 1
    fi
    return 0
}

# ===== Navigation & Debug Helpers =====

press_key() {
    local k="${1:-}"
    if [[ -n "$k" && "$k" =~ ^[A-Za-z0-9_]+$ ]]; then
        adb_shell "input keyevent $k" || true
    fi
}
go_home()     { press_key "KEYCODE_HOME"; }
press_back()  { press_key "KEYCODE_BACK"; }
press_enter() { press_key "66"; }

take_screenshot() {
    local name="${1:-screenshot}"
    local safe_name="${name//[^A-Za-z0-9._-]/_}"
    local ts
    ts=$(date +%Y%m%d_%H%M%S)
    adb_shell "screencap -p /data/local/tmp/${safe_name}_${ts}.png"
    log "已保存调试截图: /data/local/tmp/${safe_name}_${ts}.png"
}

_ui_cleanup() {
    rm -f "$UI_LOCAL_TMP" 2>/dev/null || true
    restore_animations 2>/dev/null || true
}
register_cleanup "_ui_cleanup"
