#!/usr/bin/env bash
# trial.sh — 统一跨平台智能启动入口 (默认启用 Python 可视化领航版，--shell 可切回经典纯 Bash 版)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--shell" ]]; then
    shift
    exec "$SCRIPT_DIR/batch-trial.sh" "$@"
fi

_PY_CANDIDATES=(
    "$SCRIPT_DIR/runtime/python/bin/python3"
    /opt/homebrew/bin/python3
    /usr/local/bin/python3
    "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
)
_WHICH_PY="$(command -v python3 2>/dev/null || true)"
if [[ -n "$_WHICH_PY" && "$_WHICH_PY" != "/usr/bin/python3" ]]; then
    _PY_CANDIDATES+=("$_WHICH_PY")
fi
# Avoid triggering Apple Xcode CLT installation popup on clean Macs without CLT
if ! command -v xcode-select >/dev/null 2>&1 || xcode-select -p >/dev/null 2>&1; then
    _PY_CANDIDATES+=("/usr/bin/python3")
fi

for _py in "${_PY_CANDIDATES[@]}"; do
    if [[ -n "$_py" && -x "$_py" ]] && "$_py" -c 'import sys; assert sys.version_info >= (3, 9)' >/dev/null 2>&1; then
        exec "$_py" "$SCRIPT_DIR/gtool.py" "$@"
    fi
done

exec "$SCRIPT_DIR/batch-trial.sh" "$@"
