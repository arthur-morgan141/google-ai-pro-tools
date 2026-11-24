#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/platform_env.py — Cross-platform (macOS / Windows / Linux) auto-adaptation & bootstrap.

Automatically discovers or provisions:
  - UTF-8 & ANSI VT100 console support on Windows CMD / PowerShell / Terminal & macOS
  - ADB executable (MuMu Mac/Win, Windows Registry, multi-drive C..G, SDK, PATH, or auto-download platform-tools)
  - MuMu controller (mumutool on macOS, MuMuManager.exe on Windows) for exact instance discovery & 1-click boot
  - Host Frida CLI (PATH, Python Scripts dir, user base, Homebrew, or auto pip install with mirror fallback)
  - Device frida-server (auto-matching Android CPU ABI & host Frida major version, auto-download via lzma)
  - Device BillingClient module.apk (auto-push bundled 2.0MB BillingClient 7.1.1 APK)
"""

from __future__ import annotations

import json
import lzma
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import site
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_DIR / ".cache"
CONF_PATH = PROJECT_DIR / ".gtool_prefs.json"

SYS_NAME = platform.system()  # "Darwin" | "Windows" | "Linux"
IS_MAC = SYS_NAME == "Darwin"
IS_WIN = SYS_NAME == "Windows"
IS_LINUX = SYS_NAME == "Linux"
ARCH_NAME = platform.machine()

GOOGLE_ONE_PKG = "com.google.android.apps.subscriptions.red"
VENDING_PKG = "com.android.vending"
GMS_PKG = "com.google.android.gms"

BLOG_URL = "https://blog.caowo.de/"
FAKA_URL = "https://faka.cdkey.si/"

STANDARD_SKUS = {
    # $0 Free Trial & 24-Month Stackable Pools (Verified Live Nov 2026)
    "g1.2tb.ai.subs_variant",
    "g1.play.2tb.ai",
    "g1.2tb.subs_variant",
    # AI Pro 5TB 1折~5折特惠与年付/学生档 (Verified Live Nov 2026)
    "g1.2tb.ai.12months_ip_90p",
    "g1.2tb.ai.3months_ip_90p.acq",
    "g1.2tb.ai.1month_ip_90p.acq",
    "g1.2tb.ai.12months_ip_75p",
    "g1.2tb.ai.3months_ip_75p.acq",
    "g1.2tb.ai.12months_ip_50p",
    "g1.2tb.ai.3months_ip_50p",
    "g1.play.2tb.ai.student",
    "g1.2tb.ai.annual",
    "g1.2tb.ai",
    # AI Ultra 30TB (20x) & 20TB (5x) 特惠与旗舰档 (Verified Live Nov 2026)
    "g1.ai.ultra.1month_ip_90p.acq",
    "g1.ai.ultra.3months_ip_80p.acq",
    "g1.ai.ultra.3months_ip_80p",
    "g1.ai.ultra.3months_ip_75p.acq",
    "g1.ai.pro.3months_ip_50p",
    "g1.ai.ultra.2months_ip_50p.acq",
    "g1.play.ai.pro",
    "g1.ai.pro",
    "g1.play.20tb",
    "g1.20tb",
    # Google One 基础与低价特惠档
    "g1.100gb.3months_ip_75p",
    "g1.2tb.3months_ip_75p",
    "g1.30gb",
    "g1.100gb",
    "g1.200gb",
    "g1.2tb",
}

MODULE_LOCAL = PROJECT_DIR / "module.apk"
MODULE_REMOTE = "/data/local/tmp/module.apk"
FRIDA_SERVER_REMOTE = "/data/local/tmp/frida-server"
FRIDA_JS_LOCAL = PROJECT_DIR / "frida-auto-trial.js"

# Suppress flashing console windows when invoking subprocesses on Windows
WIN_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0


def init_console_environment() -> None:
    """Configure UTF-8 I/O and enable ANSI VT100 sequences on Windows & macOS."""
    if IS_WIN:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
            # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004) on stdout & stderr
            for handle_id in (-11, -12):
                h = kernel32.GetStdHandle(handle_id)
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            pass
    else:
        os.environ["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

    for stream_name in ("stdout", "stderr"):
        st = getattr(sys, stream_name, None)
        if st and hasattr(st, "reconfigure"):
            try:
                st.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def os_display_label() -> str:
    if IS_MAC:
        ver = platform.mac_ver()[0] or ""
        return f"macOS {ver} ({ARCH_NAME})".strip()
    if IS_WIN:
        rel = platform.release()
        return f"Windows {rel} ({ARCH_NAME})"
    return f"{SYS_NAME} ({ARCH_NAME})"


# ---------- Personalization Preferences ----------

DEFAULT_PREFS: Dict[str, Any] = {
    "lang": "",                  # auto-detected ("zh" | "en" | "ar" | "ru" | "es")
    "user_name": "Ethan",
    "persona": "geek",           # geek | minimal | coach
    "motto": "auto",
    "sound": True,
    "desktop_notify": False,
    "fast_anim": True,
    "batch_reset": "smart",      # smart | reinstall
    "auto_cancel": True,
    "postal_mode": "classic",    # classic (92101/89101/33131) | taxfree (97201/19801/03101)
    "last_action": None,         # dict: {mode, sku, offer_id, stack, label, is_paid}
    "last_accounts_file": "",
    "last_cards_file": "",
}

ROTATING_TIPS = [
    "安全红线：非 $0 方案只拉起收银台弹窗，绝不自动点击订阅，杜绝误扣款",
    "白嫖秘籍：Pro 5TB 支持 [12月首开 → +6月叠加 → +6月叠加] 最高顺延至 24 个月",
    "踩坑锦囊：付款成功但未显示新容量？点击「查单 & 补单同步」一键执行 Acknowledge",
    "官方站点：技术博客 https://blog.caowo.de/ | GPT 代充发卡网 https://faka.cdkey.si/",
    "风控常识：Google Play 强校验卡头前 6 位 BIN 国家与账号锁区一致，跨区报错请换同区卡",
    "双端无缝：支持 macOS (.dmg) 与 Windows (.exe) 一键启动，缺失环境自动补全",
]


def load_prefs() -> Dict[str, Any]:
    prefs = dict(DEFAULT_PREFS)
    if CONF_PATH.exists():
        try:
            data = json.loads(CONF_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                prefs.update(data)
        except Exception:
            pass
    if not prefs.get("lang"):
        from .i18n import detect_system_lang
        prefs["lang"] = detect_system_lang()
    return prefs


def save_prefs(prefs: Dict[str, Any]) -> None:
    try:
        tmp = CONF_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        if not IS_WIN:
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
        os.replace(tmp, CONF_PATH)
    except Exception:
        pass


def time_greeting(user_name: str = "") -> str:
    hour = time.localtime().tm_hour
    who = f" {user_name}" if user_name else ""
    if 5 <= hour < 12:
        return f"早安{who} ☀️ 新的一天，引擎已就绪"
    if 12 <= hour < 18:
        return f"下午好{who} ☕ 设备链路畅通，随时发车"
    if 18 <= hour < 23:
        return f"晚上好{who} 🌙 智能领航就位，省时直达"
    return f"夜深了{who} 🌌 夜猫模式运行中，注意休息"


def active_motto(prefs: Dict[str, Any]) -> str:
    m = str(prefs.get("motto") or "auto").strip()
    if m and m != "auto":
        return m
    idx = int(time.time() // 10) % len(ROTATING_TIPS)
    return ROTATING_TIPS[idx]


def notify_user(prefs: Dict[str, Any], kind: str = "info", message: str = "") -> None:
    """Cross-platform sound & desktop notification (macOS + Windows)."""
    if prefs.get("sound", True):
        if IS_MAC:
            snd_map = {
                "success": "/System/Library/Sounds/Glass.aiff",
                "attention": "/System/Library/Sounds/Hero.aiff",
                "error": "/System/Library/Sounds/Funk.aiff",
                "warn": "/System/Library/Sounds/Pop.aiff",
                "info": "/System/Library/Sounds/Tink.aiff",
            }
            snd = snd_map.get(kind, snd_map["info"])
            if Path(snd).exists() and shutil.which("afplay"):
                try:
                    subprocess.Popen(
                        ["afplay", snd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
        elif IS_WIN:
            try:
                import winsound
                beep_type = 0x40 if kind in ("success", "info") else 0x30
                winsound.MessageBeep(beep_type)
            except Exception:
                pass

    if prefs.get("desktop_notify", False) and message and IS_MAC and shutil.which("osascript"):
        try:
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    'on run argv\ndisplay notification (item 1 of argv) with title "Google Trial Studio"\nend run',
                    str(message),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


# ---------- Windows Registry Helper for Emulator Discovery ----------

def _win_registry_mumu_dirs() -> List[Path]:
    if not IS_WIN:
        return []
    found: List[Path] = []
    try:
        import winreg
        reg_roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, subkey in reg_roots:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    count = winreg.QueryInfoKey(k)[0]
                    for i in range(count):
                        try:
                            name = winreg.EnumKey(k, i)
                            if not any(tag in name.lower() for tag in ("mumu", "nemu", "netease", "ldplayer", "nox")):
                                continue
                            with winreg.OpenKey(k, name) as sk:
                                for val_name in ("InstallLocation", "UninstallString", "DisplayIcon"):
                                    try:
                                        val, _ = winreg.QueryValueEx(sk, val_name)
                                        if val:
                                            clean = str(val).strip('"').split(",")[0]
                                            p = Path(clean)
                                            found.append(p if p.is_dir() else p.parent)
                                    except OSError:
                                        pass
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:
        pass
    return found


# ---------- ADB Auto-Discovery & Auto-Download ----------

def _candidate_adb_paths() -> List[Path]:
    cands: List[Path] = []
    env_adb = os.environ.get("ADB_PATH", "").strip()
    if env_adb:
        cands.append(Path(env_adb))

    exe_name = "adb.exe" if IS_WIN else "adb"
    cands.append(PROJECT_DIR / "platform-tools" / exe_name)

    if IS_MAC:
        home = Path.home()
        mac_paths = [
            Path("/Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"),
            home / "Applications/MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb",
            Path("/Applications/MuMuPlayer.app/Contents/MacOS/tools/adb"),
            home / "Applications/MuMuPlayer.app/Contents/MacOS/tools/adb",
            Path("/Applications/MuMuPlayerPro.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"),
            Path("/Applications/MuMu Player.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"),
            Path("/opt/homebrew/bin/adb"),
            Path("/usr/local/bin/adb"),
            home / "Library/Android/sdk/platform-tools/adb",
            Path("/usr/local/share/android-sdk/platform-tools/adb"),
        ]
        cands.extend(mac_paths)
    elif IS_WIN:
        # 1. Registry-discovered install directories
        for d in _win_registry_mumu_dirs():
            cands.extend([
                d / "adb.exe",
                d / "shell" / "adb.exe",
                d / "nx_main" / "adb.exe",
                d / "nx_device" / "12.0" / "shell" / "adb.exe",
                d.parent / "shell" / "adb.exe",
                d.parent / "nx_device" / "12.0" / "shell" / "adb.exe",
            ])
        # 2. Multi-drive scan (C: through G:)
        rel_win = [
            r"Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
            r"Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe",
            r"Program Files\Netease\MuMu\nx_main\adb.exe",
            r"Program Files (x86)\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"Program Files\Netease\MuMu\emulator\nemu\vmonitor\bin\adb_server.exe",
            r"LDPlayer\LDPlayer9\adb.exe",
            r"Program Files\Nox\bin\nox_adb.exe",
            r"Program Files\BlueStacks_nxt\HD-Adb.exe",
        ]
        for drv in ("C", "D", "E", "F", "G"):
            root = Path(f"{drv}:\\")
            if root.exists():
                for rp in rel_win:
                    cands.append(root / rp)
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            cands.append(Path(local_app) / "Android/Sdk/platform-tools/adb.exe")
    else:
        cands.extend([
            Path.home() / "Android/Sdk/platform-tools/adb",
            Path("/usr/bin/adb"),
            Path("/usr/local/bin/adb"),
        ])

    which_adb = shutil.which(exe_name) or shutil.which("adb")
    if which_adb:
        cands.append(Path(which_adb))

    return cands


def find_or_download_adb(auto_download: bool = True, log_fn: Callable[[str], None] = print) -> Optional[str]:
    for p in _candidate_adb_paths():
        try:
            if p.exists() and p.is_file():
                r = subprocess.run(
                    [str(p), "version"],
                    capture_output=True,
                    timeout=5,
                    creationflags=WIN_NO_WINDOW,
                )
                if r.returncode == 0:
                    return str(p)
        except Exception:
            continue

    if not auto_download:
        return None

    os_slug = "windows" if IS_WIN else ("darwin" if IS_MAC else "linux")
    url = f"https://dl.google.com/android/repository/platform-tools-latest-{os_slug}.zip"
    log_fn(f"[*] 未检测到本地 adb，正在自动为您下载官方 Android platform-tools ({os_slug})...")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_tmp = CACHE_DIR / f"platform-tools-{os_slug}.zip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(zip_tmp, "wb") as fo:
            shutil.copyfileobj(resp, fo)
        with zipfile.ZipFile(zip_tmp) as zf:
            dest_root = PROJECT_DIR.resolve()
            for member in zf.infolist():
                target_path = (dest_root / member.filename).resolve()
                if target_path != dest_root and dest_root not in target_path.parents:
                    raise ValueError(f"Unsafe zip member path: {member.filename}")
            zf.extractall(dest_root)
        zip_tmp.unlink(missing_ok=True)
        exe_name = "adb.exe" if IS_WIN else "adb"
        pt_dir = PROJECT_DIR / "platform-tools"
        adb_bin = pt_dir / exe_name
        if adb_bin.exists():
            if not IS_WIN:
                for bin_f in pt_dir.iterdir():
                    if bin_f.is_file():
                        try:
                            bin_f.chmod(0o755)
                        except OSError:
                            pass
            log_fn(f"[+] platform-tools 自动部署完成: {adb_bin}")
            return str(adb_bin)
    except Exception as exc:
        log_fn(f"[-] 自动下载 platform-tools 失败: {exc}")
    return None


# ---------- MuMu Instance Controller (macOS mumutool + Windows MuMuManager.exe) ----------

def find_mumu_controller(adb_path: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Returns (executable_path, kind) where kind is 'mumutool' (macOS) or 'mumumanager' (Windows)."""
    env_mumu = os.environ.get("MUMUTOOL_PATH", "").strip()
    if env_mumu and Path(env_mumu).exists():
        return env_mumu, ("mumumanager" if IS_WIN else "mumutool")

    if IS_MAC:
        mac_cands = [
            Path("/Applications/MuMuPlayer.app/Contents/MacOS/mumutool"),
            Path.home() / "Applications/MuMuPlayer.app/Contents/MacOS/mumutool",
            Path("/Applications/MuMuPlayerPro.app/Contents/MacOS/mumutool"),
            Path("/Applications/MuMu Player.app/Contents/MacOS/mumutool"),
        ]
        for m in mac_cands:
            if m.exists():
                return str(m), "mumutool"
        w = shutil.which("mumutool")
        if w:
            return w, "mumutool"

    elif IS_WIN:
        win_cands: List[Path] = []
        if adb_path:
            ap = Path(adb_path).parent
            win_cands.extend([
                ap / "MuMuManager.exe",
                ap.parent / "shell" / "MuMuManager.exe",
                ap.parent / "nx_main" / "MuMuManager.exe",
            ])
        for d in _win_registry_mumu_dirs():
            win_cands.extend([
                d / "MuMuManager.exe",
                d / "shell" / "MuMuManager.exe",
                d / "nx_main" / "MuMuManager.exe",
            ])
        for drv in ("C", "D", "E", "F", "G"):
            root = Path(f"{drv}:\\")
            if root.exists():
                win_cands.extend([
                    root / r"Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
                    root / r"Program Files\Netease\MuMuPlayerGlobal-12.0\shell\MuMuManager.exe",
                    root / r"Program Files\Netease\MuMu\nx_main\MuMuManager.exe",
                    root / r"Program Files (x86)\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
                ])
        for m in win_cands:
            if m.exists():
                return str(m), "mumumanager"

    return None, ""


def list_mumu_instances(adb_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return normalized list of MuMu instances across macOS & Windows:
    [{index: int, name: str, running: bool, adb_port: int}]
    """
    ctrl, kind = find_mumu_controller(adb_path)
    if not ctrl:
        return []

    cmd = [ctrl, "info", "all"] if kind == "mumutool" else [ctrl, "info", "-v", "all"]
    data: Any = None
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            creationflags=WIN_NO_WINDOW,
        )
        raw = (r.stdout or "").strip()
        if raw and raw.startswith("{"):
            data = json.loads(raw)
    except Exception:
        data = None

    if data is None:
        # macOS fallback when MuMuPlayer.app daemon is closed (`mumutool` returns `Error: invalidPort`)
        if IS_MAC and kind == "mumutool":
            bundles_dir = Path.home() / "Library/Application Support/com.netease.mumu.nemux/bundles"
            if bundles_dir.exists():
                fb_items: List[Dict[str, Any]] = []
                for mad in sorted(bundles_dir.glob("mumu_*_*.mad")):
                    m = re.match(r"^mumu_(\d+)_", mad.name)
                    if m:
                        idx = int(m.group(1))
                        fb_items.append({"index": idx, "name": f"MuMu-{idx}", "running": False, "adb_port": 0})
                return fb_items
        return []

    items: List[Dict[str, Any]] = []

    def _norm(entry: Dict[str, Any], fallback_idx: int = 0) -> Dict[str, Any]:
        idx = int(entry.get("index", fallback_idx))
        name = str(entry.get("name") or f"MuMu-{idx}")
        st = str(entry.get("state") or entry.get("player_state") or "").lower()
        is_started = bool(entry.get("is_process_started")) or bool(entry.get("is_android_started"))
        running = (st in ("running", "start_finished")) or is_started
        port = int(entry.get("adb_port") or 0)
        return {"index": idx, "name": name, "running": running, "adb_port": port}

    # Shape 1: macOS mumutool {"return": {"results": [...]}}
    if isinstance(data, dict) and "return" in data and isinstance(data["return"], dict):
        res = data["return"].get("results", [])
        if isinstance(res, list):
            for i, e in enumerate(res):
                if isinstance(e, dict):
                    items.append(_norm(e, i))
        elif isinstance(data["return"], dict) and "index" in data["return"]:
            items.append(_norm(data["return"], 0))
    # Shape 2: Windows MuMuManager single VM dict {"index": 0, "name": ..., "is_process_started": ...}
    elif isinstance(data, dict) and ("index" in data or "is_process_started" in data or "player_state" in data):
        items.append(_norm(data, int(data.get("index", 0))))
    # Shape 3: Windows MuMuManager multi-VM dict {"0": {...}, "1": {...}}
    elif isinstance(data, dict):
        for k, v in sorted(data.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 999):
            if isinstance(v, dict):
                items.append(_norm(v, int(k) if str(k).isdigit() else 0))

    return items


def launch_mumu_instance(index: int, adb_path: Optional[str] = None) -> bool:
    ctrl, kind = find_mumu_controller(adb_path)
    if not ctrl:
        return False
    if IS_MAC and kind == "mumutool":
        try:
            chk = subprocess.run([ctrl, "info", "all"], capture_output=True, text=True, timeout=5)
            if "invalidPort" in (chk.stdout or "") + (chk.stderr or "") or chk.returncode != 0:
                app_bundle = Path(ctrl).resolve().parent.parent.parent
                if app_bundle.suffix == ".app" and app_bundle.exists():
                    subprocess.run(["open", "-g", "-a", str(app_bundle)], capture_output=True, timeout=8)
                else:
                    subprocess.run(["open", "-g", "-a", "/Applications/MuMuPlayer.app"], capture_output=True, timeout=8)
                for _ in range(16):
                    time.sleep(0.8)
                    c2 = subprocess.run([ctrl, "info", "all"], capture_output=True, text=True, timeout=4)
                    if '"return"' in (c2.stdout or ""):
                        time.sleep(0.8)
                        break
        except Exception:
            pass
    cmd = [ctrl, "open", str(index)] if kind == "mumutool" else [ctrl, "control", "-v", str(index), "launch"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=WIN_NO_WINDOW)
        if IS_MAC and kind == "mumutool":
            time.sleep(1.0)
            st = subprocess.run([ctrl, "info", str(index)], capture_output=True, text=True, timeout=5)
            if '"stopped"' in (st.stdout or ""):
                subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


# ---------- Host Frida CLI Auto-Discovery & Auto-Install ----------

def find_frida_cli() -> Optional[str]:
    exe_names = ["frida.exe", "frida"] if IS_WIN else ["frida"]

    # 1. Check current Python environment's Scripts / bin directory first!
    search_dirs: List[Path] = []
    try:
        sp = sysconfig.get_path("scripts")
        if sp:
            search_dirs.append(Path(sp))
    except Exception:
        pass

    py_dir = Path(sys.executable).resolve().parent
    search_dirs.extend([py_dir, py_dir / "Scripts", py_dir / "bin"])

    try:
        ub = site.getuserbase()
        if ub:
            ub_path = Path(ub)
            search_dirs.extend([
                ub_path / "bin",
                ub_path / "Scripts",
                ub_path / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts",
            ])
    except Exception:
        pass

    if IS_MAC:
        search_dirs.extend([Path("/opt/homebrew/bin"), Path("/usr/local/bin")])
    elif IS_WIN:
        appdata = os.environ.get("APPDATA", "")
        localapp = os.environ.get("LOCALAPPDATA", "")
        for base in (appdata, localapp):
            if base:
                for p in Path(base).glob("Python/Python*/Scripts"):
                    search_dirs.append(p)
                for p in Path(base).glob("Programs/Python/Python*/Scripts"):
                    search_dirs.append(p)

    for d in search_dirs:
        for nm in exe_names:
            cand = d / nm
            if cand.exists() and cand.is_file():
                return str(cand)

    for nm in exe_names:
        w = shutil.which(nm)
        if w:
            return w

    return None


def get_frida_cli_version(frida_cli: str) -> str:
    try:
        r = subprocess.run(
            [frida_cli, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=WIN_NO_WINDOW,
        )
        return (r.stdout or r.stderr or "").strip().splitlines()[0].strip()
    except Exception:
        return ""


def ensure_host_frida_cli(auto_install: bool = True, log_fn: Callable[[str], None] = print) -> Optional[str]:
    cli = find_frida_cli()
    if cli:
        return cli
    if not auto_install:
        return None

    log_fn("[*] 未检测到宿主机 frida-tools，正在自动安装 (自动兼容官方源与国内镜像)...")
    pip_attempts = [
        [sys.executable, "-m", "pip", "install", "--upgrade", "frida-tools"],
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "frida-tools"],
        [sys.executable, "-m", "pip", "install", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "frida-tools"],
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "frida-tools"],
    ]
    for cmd in pip_attempts:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, creationflags=WIN_NO_WINDOW)
            if r.returncode == 0:
                cli = find_frida_cli()
                if cli:
                    log_fn(f"[+] frida-tools 自动安装完成: {cli} ({get_frida_cli_version(cli)})")
                    return cli
        except Exception:
            continue

    log_fn("[-] 自动安装 frida-tools 失败，请手动执行: pip install frida-tools")
    return None


# ---------- Device frida-server & module.apk Auto-Provisioning ----------

def adb_run(
    adb: str,
    serial: str,
    *args: str,
    timeout: int = 25,
    binary: bool = False,
) -> Any:
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=WIN_NO_WINDOW)
    if binary:
        return p.stdout
    return (p.stdout or b"").decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").strip()


def adb_root_exec(adb: str, serial: str, root_sh_cmd: str, timeout: int = 12) -> str:
    """Execute a shell command on device as root (supports uid=0 adbd, /system/xbin/su setuid on MuMu, su 0 sh -c, and su -c)."""
    uid_out = adb_run(adb, serial, "shell", "id", timeout=6)
    if "uid=0" in uid_out:
        return adb_run(adb, serial, "shell", root_sh_cmd, timeout=timeout)
    esc = root_sh_cmd.replace("'", "'\"'\"'")
    wrapped = (
        f"if [ -u /system/xbin/su ]; then "
        f"/system/xbin/su 0 sh -c '{esc}' 2>/dev/null || /system/xbin/su -c '{esc}' 2>/dev/null; "
        f"else "
        f"su 0 sh -c '{esc}' 2>/dev/null || su -c '{esc}' 2>/dev/null || /system/xbin/su -c '{esc}' 2>/dev/null; "
        f"fi"
    )
    return adb_run(adb, serial, "shell", wrapped, timeout=timeout)


def ensure_device_frida_and_module(
    adb: str,
    serial: str,
    frida_cli: str,
    local_port: int = 27043,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """Ensure port forwarding, version-aligned frida-server, and BillingClient module.apk on device."""
    if serial.startswith("127.0.0.1:"):
        adb_run(adb, "", "connect", serial, timeout=5)

    host_ver = get_frida_cli_version(frida_cli)
    host_major = host_ver.split(".")[0] if host_ver else ""

    # Check if frida-server is already running AND verify its major version matches host Frida CLI!
    fs_pid = adb_run(adb, serial, "shell", "pidof frida-server 2>/dev/null || ps -A | grep frida-server | awk '{print $2}'", timeout=8).split()
    need_download = False

    has_bin = adb_run(adb, serial, "shell", f"[ -f '{FRIDA_SERVER_REMOTE}' ] && echo yes || echo no", timeout=8)
    dev_ver = ""
    dev_major = ""
    if "yes" in has_bin:
        dev_ver = adb_run(adb, serial, "shell", f"'{FRIDA_SERVER_REMOTE}' --version 2>/dev/null || true", timeout=8)
        if not dev_ver:
            dev_ver = adb_root_exec(adb, serial, f"chmod 755 '{FRIDA_SERVER_REMOTE}' && '{FRIDA_SERVER_REMOTE}' --version", timeout=8)
        dev_major = dev_ver.splitlines()[0].split(".")[0].strip() if dev_ver else ""

    if host_major and dev_major and host_major != dev_major:
        log_fn(f"[!] 设备端 frida-server ({dev_ver.splitlines()[0]}) 与本机 Frida ({host_ver}) 版本跨代，正在自动替换对齐...")
        if fs_pid:
            adb_root_exec(adb, serial, "killall -9 frida-server 2>/dev/null || pkill -9 frida-server 2>/dev/null || true", timeout=8)
            time.sleep(0.4)
            fs_pid = []
        need_download = True
    elif not fs_pid and "yes" not in has_bin:
        need_download = True

    if not fs_pid:
        # Check if we have uid=0 or working `su`; only try `adb root` as a last resort and reconnect TCP!
        uid_out = adb_run(adb, serial, "shell", "id", timeout=8)
        if "uid=0" not in uid_out:
            su_uid = adb_root_exec(adb, serial, "id", timeout=8)
            if "uid=0" not in su_uid:
                try:
                    adb_run(adb, serial, "root", timeout=10)
                    time.sleep(1.0)
                    if serial.startswith("127.0.0.1:"):
                        for _ in range(6):
                            adb_run(adb, "", "connect", serial, timeout=4)
                            if "device" in adb_run(adb, serial, "get-state", timeout=3):
                                break
                            time.sleep(0.4)
                except Exception:
                    pass

    if need_download and host_ver:
        abi = adb_run(adb, serial, "shell", "getprop ro.product.cpu.abi", timeout=8).strip() or "x86_64"
        arch = {
            "arm64-v8a": "arm64",
            "armeabi-v7a": "arm",
            "armeabi": "arm",
            "x86_64": "x86_64",
            "x86": "x86",
        }.get(abi, "arm64")

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_bin = CACHE_DIR / f"frida-server-{host_ver}-android-{arch}"
        if not cached_bin.exists():
            asset = f"frida-server-{host_ver}-android-{arch}.xz"
            urls = [
                f"https://github.com/frida/frida/releases/download/{host_ver}/{asset}",
                f"https://ghfast.top/https://github.com/frida/frida/releases/download/{host_ver}/{asset}",
            ]
            xz_tmp = CACHE_DIR / f"{asset}.tmp"
            downloaded = False
            for u in urls:
                try:
                    log_fn(f"[*] 正在下载匹配的设备端组件 {asset} (架构 {abi})...")
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=180) as resp, open(xz_tmp, "wb") as fo:
                        shutil.copyfileobj(resp, fo)
                    with lzma.open(xz_tmp, "rb") as fi, open(cached_bin, "wb") as fo:
                        shutil.copyfileobj(fi, fo)
                    xz_tmp.unlink(missing_ok=True)
                    downloaded = True
                    break
                except Exception as exc:
                    log_fn(f"[!] 线路尝试未通 ({exc})，切换备用源...")
                    xz_tmp.unlink(missing_ok=True)
            if not downloaded:
                log_fn(f"[-] 下载 frida-server 失败，请检查网络或手动放置到 {FRIDA_SERVER_REMOTE}")
                return False

        log_fn("[*] 正在推送 frida-server 到模拟器...")
        adb_run(adb, serial, "push", str(cached_bin), FRIDA_SERVER_REMOTE, timeout=90)
        adb_run(adb, serial, "shell", f"chmod 755 '{FRIDA_SERVER_REMOTE}'", timeout=8)

    if not fs_pid:
        log_fn("[*] 正在启动模拟器端 frida-server...")
        adb_root_exec(adb, serial, f"chmod 755 '{FRIDA_SERVER_REMOTE}' && nohup '{FRIDA_SERVER_REMOTE}' -D >/dev/null 2>&1 &", timeout=10)
        for _ in range(15):
            time.sleep(0.25)
            chk = adb_run(adb, serial, "shell", "pidof frida-server 2>/dev/null || ps -A | grep frida-server", timeout=8)
            if chk.strip():
                fs_pid = [chk.split()[0]]
                break
        if not fs_pid:
            log_fn("[-] frida-server 启动失败，请确认模拟器已开启 ROOT 权限")
            return False

    # Always establish TCP port forward AFTER any potential adbd reconnect
    adb_run(adb, serial, "forward", f"tcp:{local_port}", "tcp:27042", timeout=10)

    # Ensure BillingClient module.apk on device
    mod_ok = adb_run(adb, serial, "shell", f"[ -s '{MODULE_REMOTE}' ] && echo yes || echo no", timeout=8)
    if "yes" not in mod_ok:
        if not MODULE_LOCAL.exists():
            log_fn(f"[-] 本地缺少计费模块 {MODULE_LOCAL}")
            return False
        log_fn("[*] 首次初始化：正在推送 BillingClient 计费模块 (module.apk)...")
        adb_run(adb, serial, "push", str(MODULE_LOCAL), MODULE_REMOTE, timeout=60)
        adb_run(adb, serial, "shell", f"chmod 644 '{MODULE_REMOTE}'", timeout=8)

    return True
