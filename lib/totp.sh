#!/usr/bin/env bash
# lib/totp.sh — TOTP 2FA code generator with Base32 normalization & anti-expiry window guard

TOTP_TOOL=""

check_totp_tools() {
    if command -v oathtool >/dev/null 2>&1; then
        TOTP_TOOL="oathtool"
    elif command -v python3 >/dev/null 2>&1; then
        TOTP_TOOL="python3"
    else
        err "WARNING: 未检测到 TOTP 工具 (需要 python3 或 oathtool)，含 2FA 账号将等待人工输入。"
        TOTP_TOOL=""
    fi
}

generate_totp() {
    local raw_secret="${1:-}"
    [[ -z "$raw_secret" ]] && { err "未提供 2FA 密钥"; return 1; }

    [[ -z "$TOTP_TOOL" ]] && check_totp_tools

    # Strip spaces, dashes, and invalid chars; uppercase
    local secret
    secret=$(printf '%s' "$raw_secret" | tr '[:lower:]' '[:upper:]' | tr -cd 'A-Z2-7')
    [[ -z "$secret" ]] && { err "2FA 密钥格式无效"; return 1; }

    # Anti-expiry guard: if <= 3s remain in current 30s TOTP window, wait for fresh code
    local now rem
    now=$(date +%s)
    rem=$(( 30 - (now % 30) ))
    if (( rem <= 3 )); then
        echo "[*] 2FA 动态码将在 ${rem}s 后刷新，等待新周期避免提交过期..." >&2
        sleep "$rem"
    fi

    if [[ "$TOTP_TOOL" == "oathtool" ]]; then
        oathtool --totp --base32 "$secret" 2>/dev/null && return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        python3 -I -c "
import hmac, hashlib, struct, time, base64, sys
s = sys.argv[1]
s += '=' * ((8 - len(s) % 8) % 8)
key = base64.b32decode(s)
t = struct.pack('>Q', int(time.time()) // 30)
h = hmac.new(key, t, hashlib.sha1).digest()
o = h[-1] & 15
code = (struct.unpack('>I', h[o:o+4])[0] & 0x7fffffff) % 1000000
print(f'{code:06d}')
" "$secret" 2>/dev/null
    else
        err "无可用 TOTP 生成工具"
        return 1
    fi
}
