#!/usr/bin/env bash
# lib/import-parse.sh — Universal account/card file parser + macOS drag-and-drop & smart file picker

ACCOUNTS_EMAIL=()
ACCOUNTS_PASS=()
ACCOUNTS_2FA=()
ACCOUNTS_RECOVERY=()
ACCOUNTS_CARD_NUM=()
ACCOUNTS_CARD_EXP=()
ACCOUNTS_CARD_CVV=()
EMBEDDED_CARD_COUNT=0

CARDS_NUMBER=()
CARDS_EXPIRY=()
CARDS_CVV=()

# Normalize macOS Terminal drag-and-drop paths, ~ expansion, quotes & backslash escapes
normalize_path_input() {
    local p="${1:-}"
    # Trim leading/trailing spaces
    p="${p#"${p%%[![:space:]]*}"}"
    p="${p%"${p##*[![:space:]]}"}"
    # Strip matching outer quotes
    if [[ "$p" == \"*\" && "$p" == *\" ]]; then
        p="${p#\"}"; p="${p%\"}"
    elif [[ "$p" == \'*\' && "$p" == *\' ]]; then
        p="${p#\'}"; p="${p%\'}"
    else
        # Unescape Finder drag-and-drop backslashes (\ , \(, \), \[, \], \&, etc.) via pure bash
        p="${p//\\ / }"
        p="${p//\\(/(}"
        p="${p//\\)/)}"
        p="${p//\\[/[}"
        p="${p//\\]/]}"
        p="${p//\\&/&}"
        p="${p//\\#/#}"
        p="${p//\\;/;}"
        p="${p//\\\~/$HOME}"
    fi
    # Expand leading ~/
    if [[ "$p" == "~/"* ]]; then
        p="$HOME/${p#\~/}"
    fi
    echo "$p"
}

# Discover candidate .txt/.csv files in project dir & ~/Downloads for quick numbered selection
discover_data_files() {
    local kind="${1:-any}"  # account | card | any
    local candidates=()
    local f base
    for f in "$SCRIPT_DIR"/*.txt "$SCRIPT_DIR"/*.csv "$SCRIPT_DIR/.."/*.txt "$SCRIPT_DIR/.."/*.csv "$HOME/Downloads"/*.txt "$HOME/Downloads"/*.csv; do
        [[ -f "$f" ]] || continue
        base=$(basename "$f")
        case "$base" in
            results_*|README*|requirements.txt|使用说明*|CMakeLists*) continue ;;
        esac
        candidates+=("$f")
        [[ ${#candidates[@]} -ge 10 ]] && break
    done
    if (( ${#candidates[@]} > 0 )); then
        printf '%s\n' "${candidates[@]}"
    fi
}

_trim_ws() {
    local s="${1:-}"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

# Parse account file (supports ----, |, tab, CSV with quotes, colon-in-password, 4-char TOTP groups, and embedded cards)
parse_account_file() {
    local file
    file=$(normalize_path_input "${1:-}")
    [[ -n "$file" && -f "$file" ]] || die "账号文件不存在: $file"

    ACCOUNTS_EMAIL=()
    ACCOUNTS_PASS=()
    ACCOUNTS_2FA=()
    ACCOUNTS_RECOVERY=()
    ACCOUNTS_CARD_NUM=()
    ACCOUNTS_CARD_EXP=()
    ACCOUNTS_CARD_CVV=()
    EMBEDDED_CARD_COUNT=0

    # Primary parser: share hardened gtool_core.batch_runner.parse_accounts_text (handles CSV quotes, colons in passwords, space-grouped 2FA, expiry validation)
    if command -v python3 >/dev/null 2>&1 && [[ -f "$SCRIPT_DIR/gtool_core/batch_runner.py" ]]; then
        while IFS=$'\x1f' read -r email pass tfa recovery c_num c_exp c_cvv; do
            [[ -z "$email" ]] && continue
            ACCOUNTS_EMAIL+=("$email")
            ACCOUNTS_PASS+=("$pass")
            ACCOUNTS_2FA+=("$tfa")
            ACCOUNTS_RECOVERY+=("$recovery")
            ACCOUNTS_CARD_NUM+=("$c_num")
            ACCOUNTS_CARD_EXP+=("$c_exp")
            ACCOUNTS_CARD_CVV+=("$c_cvv")
            [[ -n "$c_num" ]] && EMBEDDED_CARD_COUNT=$((EMBEDDED_CARD_COUNT + 1))
        done < <(python3 - "$SCRIPT_DIR" "$file" << 'PYACCT'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from gtool_core.batch_runner import parse_accounts_text
raw = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="ignore")
for a in parse_accounts_text(raw):
    c = a.get("card") or {}
    fields = [
        a.get("email", ""),
        a.get("password", ""),
        a.get("totp", ""),
        a.get("recovery", ""),
        c.get("number", ""),
        c.get("expiry", ""),
        c.get("cvv", ""),
    ]
    print("\x1f".join(x.replace("\x1f", "").replace("\n", "").replace("\r", "") for x in fields))
PYACCT
)
        local emb_note=""
        (( EMBEDDED_CARD_COUNT > 0 )) && emb_note=" (含内嵌卡片 ${EMBEDDED_CARD_COUNT} 张)"
        ok "成功加载 ${#ACCOUNTS_EMAIL[@]} 个账号 ← $(basename "$file")${emb_note}"
        return 0
    fi

    local lineno=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        lineno=$((lineno + 1))
        line="${line%$'\r'}"
        line=$(_trim_ws "$line")
        [[ -z "$line" || "$line" == \#* ]] && continue

        # Skip optional CSV header line
        if [[ $lineno -eq 1 ]] && $_GREP -iqE '^(email|account|user|邮箱|账号)[,|	-]' <<< "$line"; then
            continue
        fi

        local parts=()
        if [[ "$line" == *"----"* ]]; then
            IFS=$'\x01' read -ra parts <<< "$(printf '%s' "$line" | sed 's/----/\x01/g')"
        elif [[ "$line" == *"|"* ]]; then
            IFS='|' read -ra parts <<< "$line"
        elif [[ "$line" == *$'\t'* ]]; then
            IFS=$'\t' read -ra parts <<< "$line"
        elif [[ "$line" == *","* ]]; then
            IFS=',' read -ra parts <<< "$line"
        elif [[ "$line" == *":"* ]]; then
            parts=("${line%%:*}" "${line#*:}")
        else
            IFS=' ' read -ra parts <<< "$line"
        fi

        local nfields=${#parts[@]}
        local email="" pass="" tfa="" recovery="" c_num="" c_exp="" c_cvv=""

        email=$(_trim_ws "${parts[0]:-}")
        pass=$(_trim_ws "${parts[1]:-}")

        if [[ -z "$email" || -z "$pass" || "$email" != *"@"* ]]; then
            warn "第 $lineno 行缺少有效邮箱或密码，已跳过"
            continue
        fi

        if (( nfields == 3 )); then
            local f3
            f3=$(_trim_ws "${parts[2]:-}")
            if [[ "$f3" == *"@"* ]]; then
                recovery="$f3"
            else
                tfa="$f3"
            fi
        elif (( nfields >= 4 )); then
            local f3 f4
            f3=$(_trim_ws "${parts[2]:-}")
            f4=$(_trim_ws "${parts[3]:-}")
            if [[ "$f3" == *"@"* && "$f4" != *"@"* ]]; then
                recovery="$f3"
                tfa="$f4"
            else
                tfa="$f3"
                recovery="$f4"
            fi

            if (( nfields >= 7 )); then
                local raw_cnum raw_cexp raw_ccvv
                raw_cnum=$(printf '%s' "${parts[4]:-}" | tr -cd '0-9')
                raw_cexp=$(printf '%s' "${parts[5]:-}" | tr -cd '0-9/')
                raw_ccvv=$(printf '%s' "${parts[6]:-}" | tr -cd '0-9')
                if [[ "$raw_cexp" =~ ^([0-9]{2})([0-9]{2})$ ]]; then
                    raw_cexp="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
                fi
                if (( ${#raw_cnum} >= 13 && ${#raw_cnum} <= 19 && ${#raw_ccvv} >= 3 && ${#raw_ccvv} <= 4 )); then
                    c_num="$raw_cnum"
                    c_exp="$raw_cexp"
                    c_cvv="$raw_ccvv"
                    EMBEDDED_CARD_COUNT=$((EMBEDDED_CARD_COUNT + 1))
                fi
            fi
        fi

        ACCOUNTS_EMAIL+=("$email")
        ACCOUNTS_PASS+=("$pass")
        ACCOUNTS_2FA+=("$tfa")
        ACCOUNTS_RECOVERY+=("$recovery")
        ACCOUNTS_CARD_NUM+=("$c_num")
        ACCOUNTS_CARD_EXP+=("$c_exp")
        ACCOUNTS_CARD_CVV+=("$c_cvv")
    done < "$file"

    local emb_note=""
    (( EMBEDDED_CARD_COUNT > 0 )) && emb_note=" (含内嵌卡片 ${EMBEDDED_CARD_COUNT} 张)"
    ok "成功加载 ${#ACCOUNTS_EMAIL[@]} 个账号 ← $(basename "$file")${emb_note}"
}

# Parse card file: number-date-cvv, number|date|cvv, CSV, space-separated, etc.
parse_card_file() {
    local file
    file=$(normalize_path_input "${1:-}")
    [[ -n "$file" && -f "$file" ]] || die "卡片文件不存在: $file"

    CARDS_NUMBER=()
    CARDS_EXPIRY=()
    CARDS_CVV=()

    if command -v python3 >/dev/null 2>&1 && [[ -f "$SCRIPT_DIR/gtool_core/batch_runner.py" ]]; then
        while IFS=$'\x1f' read -r num exp cvv; do
            [[ -z "$num" ]] && continue
            CARDS_NUMBER+=("$num")
            CARDS_EXPIRY+=("$exp")
            CARDS_CVV+=("$cvv")
        done < <(python3 - "$SCRIPT_DIR" "$file" << 'PYCARD'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from gtool_core.batch_runner import parse_cards_text
raw = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="ignore")
for c in parse_cards_text(raw):
    print(f"{c['number']}\x1f{c['expiry']}\x1f{c['cvv']}")
PYCARD
)
        ok "成功加载 ${#CARDS_NUMBER[@]} 张卡片 ← $(basename "$file")"
        return 0
    fi

    local lineno=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        lineno=$((lineno + 1))
        line="${line%$'\r'}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" || "$line" == \#* ]] && continue

        if [[ $lineno -eq 1 ]] && $_GREP -iqE '^(card|number|pan|卡号)' <<< "$line"; then
            continue
        fi

        local num="" exp="" cvv=""

        # Space-delimited 3 tokens: "5450200010222396 06/29 457"
        if [[ "$line" =~ ^([0-9]{13,19})[[:space:]]+([0-9/\-]{4,5})[[:space:]]+([0-9]{3,4})$ ]]; then
            num="${BASH_REMATCH[1]}"
            exp="${BASH_REMATCH[2]//-//}"
            cvv="${BASH_REMATCH[3]}"
        else
            local clean parts=()
            clean=$(printf '%s' "$line" | tr -d ' ')
            if [[ "$clean" == *"|"* ]]; then
                IFS='|' read -ra parts <<< "$clean"
                num="${parts[0]:-}"; exp="${parts[1]:-}"; cvv="${parts[2]:-}"
            elif [[ "$clean" == *","* ]]; then
                IFS=',' read -ra parts <<< "$clean"
                num="${parts[0]:-}"; exp="${parts[1]:-}"; cvv="${parts[2]:-}"
            elif [[ "$clean" == *"----"* ]]; then
                IFS=$'\x01' read -ra parts <<< "$(printf '%s' "$clean" | sed 's/----/\x01/g')"
                num="${parts[0]:-}"; exp="${parts[1]:-}"; cvv="${parts[2]:-}"
            elif [[ "$clean" =~ ^([0-9]{13,19})-([0-9/]{4,5})-([0-9]{3,4})$ ]]; then
                num="${BASH_REMATCH[1]}"; exp="${BASH_REMATCH[2]}"; cvv="${BASH_REMATCH[3]}"
            else
                IFS='-' read -ra parts <<< "$clean"
                local n=${#parts[@]}
                if (( n >= 3 )); then
                    cvv="${parts[$((n-1))]:-}"
                    exp="${parts[$((n-2))]:-}"
                    num=""
                    local k
                    for (( k=0; k<n-2; k++ )); do num+="${parts[$k]:-}"; done
                elif (( n == 2 )); then
                    num="${parts[0]:-}"; cvv="${parts[1]:-}"
                else
                    num="${parts[0]:-}"
                fi
            fi
        fi

        num=$(printf '%s' "$num" | tr -cd '0-9')
        exp=$(printf '%s' "$exp" | tr '-' '/' | tr -cd '0-9/')
        if [[ "$exp" =~ ^([0-9]{2})([0-9]{2})$ ]]; then
            exp="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
        elif [[ "$exp" =~ ^([0-9]{1,2})/([0-9]{2}|20[0-9]{2})$ ]]; then
            local mm="${BASH_REMATCH[1]}" yy="${BASH_REMATCH[2]}"
            (( ${#mm} == 1 )) && mm="0${mm}"
            (( ${#yy} == 4 )) && yy="${yy:2:2}"
            exp="${mm}/${yy}"
        elif [[ "$exp" =~ ^20([0-9]{2})/([0-9]{1,2})$ ]]; then
            local yy="${BASH_REMATCH[1]}" mm="${BASH_REMATCH[2]}"
            (( ${#mm} == 1 )) && mm="0${mm}"
            exp="${mm}/${yy}"
        fi
        cvv=$(printf '%s' "$cvv" | tr -cd '0-9')

        if (( ${#num} < 13 || ${#num} > 19 )); then
            warn "第 $lineno 行卡号长度异常 (${#num}位)，已跳过"
            continue
        fi
        if ! [[ "$exp" =~ ^(0[1-9]|1[0-2])/[0-9]{2}$ ]]; then
            warn "第 $lineno 行有效期格式异常 ($exp)，已跳过"
            continue
        fi
        if (( ${#cvv} < 3 || ${#cvv} > 4 )); then
            warn "第 $lineno 行 CVV 长度异常 (${#cvv}位)，已跳过"
            continue
        fi

        CARDS_NUMBER+=("$num")
        CARDS_EXPIRY+=("$exp")
        CARDS_CVV+=("$cvv")
    done < "$file"

    ok "成功加载 ${#CARDS_NUMBER[@]} 张卡片 ← $(basename "$file")"
}

validate_imports() {
    if [[ ${#ACCOUNTS_EMAIL[@]} -eq 0 ]]; then die "未加载到有效账号"; fi
    if [[ ${#CARDS_NUMBER[@]} -eq 0 && $EMBEDDED_CARD_COUNT -eq 0 ]]; then
        die "未加载到有效卡片"
    fi
    ok "校验通过: ${#ACCOUNTS_EMAIL[@]} 个账号, $(( ${#CARDS_NUMBER[@]} + EMBEDDED_CARD_COUNT )) 张可用卡"
}
