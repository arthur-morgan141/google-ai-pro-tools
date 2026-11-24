#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/device_ops.py — Cross-platform ADB UI automation, diagnostics, screen mirror & account/card ops."""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import random
import re
import shutil
import sqlite3
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .platform_env import (
    GOOGLE_ONE_PKG,
    MODULE_REMOTE,
    VENDING_PKG,
    adb_root_exec,
    adb_run,
    ensure_device_frida_and_module,
    ensure_host_frida_cli,
    find_or_download_adb,
    get_frida_cli_version,
    launch_mumu_instance,
    list_mumu_instances,
    os_display_label,
)

POSTAL_CLASSIC = ["92101", "89101", "33131"]
POSTAL_TAXFREE = ["97201", "97204", "19801", "03101"]

NEXT_LABELS = ("Next", "下一步", "NEXT", "下一个", "Siguiente", "다음", "次へ")
AGREE_LABELS = ("I agree", "我同意", "Accept", "ACCEPT", "接受", "Agree", "同意")
SKIP_LABELS = ("Skip", "跳过", "Not now", "以后再说", "No thanks", "不用了")
REMOVE_LABELS = ("Remove account", "移除帐号", "移除账号", "Remove", "删除账号")


class HumanGate:
    """Thread-safe human-in-the-loop pause gate shared by Console TUI & Web Console."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self.waiting: bool = False
        self.message: str = ""
        self.action: str = "continue"  # "continue" | "skip" | "abort"

    def request_assist(
        self,
        msg: str,
        on_prompt: Optional[Callable[[str], Optional[str]]] = None,
        timeout: int = 600,
    ) -> str:
        with self._lock:
            self.waiting = True
            self.message = msg
            self.action = "continue"
            self._event.clear()

        # If running in interactive console mode with a synchronous callback, use it directly
        if on_prompt is not None:
            res = on_prompt(msg)
            with self._lock:
                self.waiting = False
                self.message = ""
                self.action = res or "continue"
                return self.action

        # Otherwise wait for Web UI / async trigger
        end_ts = time.time() + timeout
        while time.time() < end_ts:
            if self._event.wait(timeout=0.5):
                break
        with self._lock:
            self.waiting = False
            self.message = ""
            return self.action

    def resolve(self, action: str = "continue") -> None:
        with self._lock:
            self.action = action
            self.waiting = False
            self.message = ""
            self._event.set()


def generate_totp(secret: str, log_fn: Optional[Callable[[str], None]] = None) -> str:
    clean = re.sub(r"[^A-Za-z2-7]", "", (secret or "").upper())
    if not clean:
        return ""
    rem = 30 - (int(time.time()) % 30)
    if rem <= 3:
        if log_fn:
            log_fn(f"[*] 2FA 动态码将在 {rem}s 后轮换，自动等待新周期防过期...")
        time.sleep(rem)
    clean += "=" * ((8 - len(clean) % 8) % 8)
    key = base64.b32decode(clean)
    ctr = struct.pack(">Q", int(time.time()) // 30)
    mac = hmac.new(key, ctr, hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off : off + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def parse_ui_xml(raw_xml: str) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for m in re.finditer(r"<node\b([^>]*?)(?:/)?>", raw_xml):
        attrs = m.group(1)
        bm = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', attrs)
        if not bm:
            continue
        x1, y1, x2, y2 = map(int, bm.groups())

        def _attr(name: str) -> str:
            am = re.search(rf'\b{name}="([^"]*)"', attrs)
            return am.group(1) if am else ""

        nodes.append(
            {
                "text": _attr("text"),
                "desc": _attr("content-desc"),
                "cls": _attr("class"),
                "res_id": _attr("resource-id"),
                "clickable": _attr("clickable") == "true",
                "checked": _attr("checked") == "true",
                "password": _attr("password") == "true",
                "rect": (x1, y1, x2, y2),
                "cx": (x1 + x2) // 2,
                "cy": (y1 + y2) // 2,
                "area": max(1, (x2 - x1) * (y2 - y1)),
            }
        )
    return nodes


def find_cta_button(nodes: List[Dict[str, Any]], *labels: str) -> Optional[Tuple[int, int]]:
    """Accurately locate a CTA button, handling non-clickable text inside clickable parents
    and avoiding long disclaimer/description paragraphs."""
    # 1. Exact text/desc on Button widget
    for lb in labels:
        for n in nodes:
            if "Button" in n["cls"] and (n["text"] == lb or n["desc"] == lb):
                return (n["cx"], n["cy"])
    # 2. Exact text/desc on any clickable node
    for lb in labels:
        for n in nodes:
            if n["clickable"] and (n["text"] == lb or n["desc"] == lb):
                return (n["cx"], n["cy"])
    # 3. Exact text node -> tightest enclosing clickable container (prefer lower screen CTA)
    for lb in labels:
        matches = [n for n in nodes if n["text"] == lb or n["desc"] == lb]
        matches.sort(key=lambda item: item["rect"][1], reverse=True)
        for tn in matches:
            tx1, ty1, tx2, ty2 = tn["rect"]
            parents = [
                p
                for p in nodes
                if p["clickable"]
                and p["rect"][0] <= tx1
                and p["rect"][1] <= ty1
                and p["rect"][2] >= tx2
                and p["rect"][3] >= ty2
            ]
            if parents:
                parents.sort(key=lambda p: p["area"])
                return (parents[0]["cx"], parents[0]["cy"])
            return (tn["cx"], tn["cy"])
    return None


def find_containing(nodes: List[Dict[str, Any]], *substrings: str) -> Optional[Tuple[int, int]]:
    for sub in substrings:
        sub_l = sub.lower()
        for n in nodes:
            label = f"{n['text']} {n['desc']}".lower()
            if sub_l in label and (n["cx"] or n["cy"]):
                return (n["cx"], n["cy"])
    return None


def classify_checkout_xml(raw_xml: str) -> str:
    """STRICT $0 safety classifier for Google Play checkout bottom sheet.
    Returns: 'INELIGIBLE' | 'NON_ZERO' | 'ZERO_OK' | 'ALREADY_OWNED' | 'OFFLINE' | 'WAIT'
    """
    texts = [m.group(1) for m in re.finditer(r'\b(?:text|content-desc)="([^"]+)"', raw_xml)]
    blob = " | ".join(texts)

    if re.search(r"不符合免费试用条件|not eligible", blob, re.I):
        return "INELIGIBLE"
    if re.search(r"您已订阅|already subscribed", blob, re.I):
        return "ALREADY_OWNED"
    if re.search(r"未连接到互联网|No internet connection", blob, re.I):
        return "OFFLINE"
    if not re.search(r"订阅|Subscribe", blob, re.I):
        return "WAIT"

    curr_pre = r"(?:US\$|HK\$|NT\$|CA\$|A\$|S\$|R\$|JP¥|¥|\$|£|€|₩|₹)"
    curr_suf = r"(?:USD|GBP|EUR|HKD|JPY|CAD|AUD|SGD|TWD|KRW|INR|CHF)"
    nonzero_amt = r"(?:[1-9][\d.,]*|0[.,]\d*[1-9]\d*)"

    # Zero-cost check: strictly forbid fractional non-zero amounts like $0.99 or €0,49 via (?![.,]?\d)
    has_zero = bool(
        re.search(rf"{curr_pre}\s*0(?:[.,]00)?(?![.,]?\d)", blob)
        or re.search(rf"(?<![\d.,])0(?:[.,]00)?(?![.,]?\d)\s*{curr_suf}\b", blob)
        or re.search(r"免费试用|Free trial|無料トライアル|(?:即将扣款|今日|Today)[^|]{0,12}(?:\|\s*)?[¥$£€₩₹]?\s*0(?:[.,]00)?(?![.,]?\d)", blob, re.I)
    )
    immediate_paid = bool(
        re.search(
            rf"(?:开始日期：今天|Starting today|Due today|今日应付|即将扣款\s*今天)\s*(?:\|\s*)?(?:{curr_pre}\s*{nonzero_amt}|{nonzero_amt}\s*{curr_suf})",
            blob,
            re.I,
        )
    )
    any_nonzero = bool(
        re.search(rf"{curr_pre}\s*{nonzero_amt}|\b{nonzero_amt}\s*{curr_suf}\b", blob)
    )

    if immediate_paid:
        return "NON_ZERO"
    if has_zero:
        return "ZERO_OK"
    if any_nonzero:
        return "NON_ZERO"
    return "WAIT"


class DeviceController:
    """High-speed cross-platform controller for MuMu / Android devices."""

    def __init__(self, log_fn: Callable[[str], None] = print, human_gate: Optional[HumanGate] = None) -> None:
        self.log = log_fn
        self.human_gate = human_gate or HumanGate()
        self.adb: Optional[str] = find_or_download_adb(auto_download=False, log_fn=log_fn)
        self.frida_cli: Optional[str] = ensure_host_frida_cli(auto_install=False, log_fn=log_fn)
        self.serial: str = ""
        self.instance_name: str = ""
        self.screen_size: Tuple[int, int] = (1440, 2560)
        self._anim_saved: Optional[Tuple[str, str, str]] = None

    def ensure_host_tools(self) -> bool:
        if not self.adb:
            self.adb = find_or_download_adb(auto_download=True, log_fn=self.log)
        if not self.adb:
            return False
        if not self.frida_cli:
            self.frida_cli = ensure_host_frida_cli(auto_install=True, log_fn=self.log)
        return bool(self.frida_cli)

    def sh(self, *args: str, timeout: int = 25, binary: bool = False) -> Any:
        if not self.adb:
            raise RuntimeError("ADB 尚未就绪")
        return adb_run(self.adb, self.serial, *args, timeout=timeout, binary=binary)

    def shell(self, cmd: str, timeout: int = 20) -> str:
        return str(self.sh("shell", cmd, timeout=timeout, binary=False))

    # ---------- Fast Telemetry Radar ----------

    def probe_radar(self) -> Dict[str, Any]:
        mumu_list = list_mumu_instances(self.adb)
        running_mumu = [m for m in mumu_list if m["running"] and m["adb_port"]]

        info: Dict[str, Any] = {
            "os": os_display_label(),
            "adb_path": self.adb or "",
            "frida_cli": self.frida_cli or "",
            "frida_ver": get_frida_cli_version(self.frida_cli) if self.frida_cli else "",
            "mumu_instances": mumu_list,
            "connected": False,
            "serial": self.serial,
            "instance_name": self.instance_name,
            "model": "",
            "android_ver": "",
            "abi": "",
            "accounts": [],
            "frida_running": False,
            "module_ready": False,
            "vending_running": False,
            "g1_installed": False,
            "g1_running": False,
            "net_validated": False,
            "subscriptions": [],
        }

        if not self.adb:
            return info

        target_serial = self.serial
        target_name = self.instance_name

        if not target_serial:
            if running_mumu:
                target_serial = f"127.0.0.1:{running_mumu[0]['adb_port']}"
                target_name = running_mumu[0]["name"]
                try:
                    adb_run(self.adb, "", "connect", target_serial, timeout=4)
                except Exception:
                    pass
            else:
                # If mumutool knows all instances are stopped, check already-attached USB devices only
                devs_out = adb_run(self.adb, "", "devices", timeout=4)
                devs = [ln.split("\t")[0] for ln in devs_out.splitlines()[1:] if "\tdevice" in ln]
                if devs:
                    target_serial = devs[0]
                elif not mumu_list:
                    # Non-MuMu setup: quick check common ports
                    for p in (16384, 16416, 7555, 62001):
                        adb_run(self.adb, "", "connect", f"127.0.0.1:{p}", timeout=2)
                    devs_out = adb_run(self.adb, "", "devices", timeout=4)
                    devs = [ln.split("\t")[0] for ln in devs_out.splitlines()[1:] if "\tdevice" in ln]
                    if devs:
                        target_serial = devs[0]

        if not target_serial:
            return info

        try:
            st = adb_run(self.adb, target_serial, "get-state", timeout=3)
            if "device" not in st:
                return info
        except Exception:
            return info

        self.serial = target_serial
        if target_name:
            self.instance_name = target_name
        else:
            for m in running_mumu:
                if f"127.0.0.1:{m['adb_port']}" == target_serial:
                    self.instance_name = m["name"]
                    break

        info["connected"] = True
        info["serial"] = self.serial
        info["instance_name"] = self.instance_name

        # Single combined shell probe (< 0.25s!)
        probe_cmd = (
            "echo MODEL=$(getprop ro.product.model); "
            "echo REL=$(getprop ro.build.version.release); "
            "echo ABI=$(getprop ro.product.cpu.abi); "
            "echo WMSZ=$(wm size 2>/dev/null | tail -1); "
            "echo FRIDA=$(pidof frida-server 2>/dev/null || ps -A | grep frida-server | awk '{print $2}'); "
            f"[ -s '{MODULE_REMOTE}' ] && echo MOD=1 || echo MOD=0; "
            f"echo VEND=$(pidof {VENDING_PKG} 2>/dev/null); "
            f"echo G1P=$(pidof {GOOGLE_ONE_PKG} 2>/dev/null); "
            f"pm path {GOOGLE_ONE_PKG} >/dev/null 2>&1 && echo G1I=1 || echo G1I=0; "
            "dumpsys connectivity 2>/dev/null | grep -q VALIDATED && echo NET=1 || echo NET=0; "
            "dumpsys account 2>/dev/null | sed -n 's/.*Account *{name=\\([^,]*\\), *type=com\\.google.*/ACCT=\\1/p' | sort -u"
        )
        raw = self.shell(probe_cmd, timeout=8)
        accts: List[str] = []
        for line in raw.splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if k == "MODEL":
                info["model"] = v
            elif k == "REL":
                info["android_ver"] = v
            elif k == "ABI":
                info["abi"] = v
            elif k == "WMSZ":
                msz = re.search(r"(\d{3,5})x(\d{3,5})", v)
                if msz:
                    self.screen_size = (int(msz.group(1)), int(msz.group(2)))
            elif k == "FRIDA":
                info["frida_running"] = bool(v)
            elif k == "MOD":
                info["module_ready"] = v == "1"
            elif k == "VEND":
                info["vending_running"] = bool(v)
            elif k == "G1P":
                info["g1_running"] = bool(v)
            elif k == "G1I":
                info["g1_installed"] = v == "1"
            elif k == "NET":
                info["net_validated"] = v == "1"
            elif k == "ACCT" and v:
                accts.append(v)
        info["accounts"] = accts
        info["subscriptions"] = self.read_play_subscriptions()
        return info

    def refresh_screen_size(self) -> Tuple[int, int]:
        try:
            wm = self.shell("wm size 2>/dev/null | tail -1", timeout=4)
            m = re.search(r"(\d{3,5})x(\d{3,5})", wm)
            if m:
                self.screen_size = (int(m.group(1)), int(m.group(2)))
        except Exception:
            pass
        return self.screen_size

    def connect_or_boot_device(self, preferred_port: Optional[int] = None, allow_boot_idx: Optional[int] = None) -> bool:
        if not self.ensure_host_tools():
            return False
        assert self.adb is not None

        if preferred_port:
            target = f"127.0.0.1:{preferred_port}"
            adb_run(self.adb, "", "connect", target, timeout=5)
            if "device" in adb_run(self.adb, target, "get-state", timeout=4):
                self.serial = target
                self.refresh_screen_size()
                return True

        if self.serial and "device" in adb_run(self.adb, self.serial, "get-state", timeout=3):
            return True

        mumu_list = list_mumu_instances(self.adb)
        running = [m for m in mumu_list if m["running"] and m["adb_port"]]
        if running:
            self.serial = f"127.0.0.1:{running[0]['adb_port']}"
            self.instance_name = running[0]["name"]
            adb_run(self.adb, "", "connect", self.serial, timeout=5)
            if "device" in adb_run(self.adb, self.serial, "get-state", timeout=4):
                self.refresh_screen_size()
                return True

        if allow_boot_idx is not None:
            return self.boot_mumu_and_wait(allow_boot_idx)

        # Fallback scan common emulator ports (MuMu, LDPlayer, Nox, BlueStacks)
        for port in (16384, 16416, 16448, 16480, 7555, 5555, 62001, 21503):
            adb_run(self.adb, "", "connect", f"127.0.0.1:{port}", timeout=3)
        devs_out = adb_run(self.adb, "", "devices", timeout=5)
        devs = [ln.split("\t")[0] for ln in devs_out.splitlines()[1:] if "\tdevice" in ln]
        if devs:
            self.serial = devs[0]
            self.refresh_screen_size()
            return True
        return False

    def boot_mumu_and_wait(self, index: int, timeout_sec: int = 55) -> bool:
        if not self.adb:
            self.ensure_host_tools()
        assert self.adb is not None
        self.log(f"[*] 正在一键唤醒 MuMu 模拟器实例 #{index}...")
        if not launch_mumu_instance(index, self.adb):
            self.log("[-] 调用 MuMu 启动器失败，请手动打开模拟器")
            return False

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            time.sleep(1.2)
            for m in list_mumu_instances(self.adb):
                if m["index"] == index and m["running"] and m["adb_port"]:
                    cand = f"127.0.0.1:{m['adb_port']}"
                    adb_run(self.adb, "", "connect", cand, timeout=4)
                    boot_done = adb_run(self.adb, cand, "shell", "getprop sys.boot_completed", timeout=4).strip()
                    if boot_done == "1":
                        self.serial = cand
                        self.instance_name = m["name"]
                        self.log(f"[+] MuMu 实例【{m['name']}】已启动就绪 ({cand})")
                        return True
        self.log("[-] 等待模拟器开机就绪超时")
        return False

    # ---------- Play Store Subscription DB Reader (SQLite WAL + su Root Aware!) ----------

    def read_play_subscriptions(self) -> List[Dict[str, Any]]:
        if not self.adb or not self.serial:
            return []
        local_dir = Path(tempfile.mkdtemp(prefix=f"gtool_lib_{os.getpid()}_"))
        remote_dir = f"/data/local/tmp/.gtool_db_{os.getpid()}"
        try:
            # Copy library.db AND library.db-wal / library.db-shm together so uncheckpointed WAL rows are visible!
            copy_cmd = (
                f"rm -rf {remote_dir} && mkdir -p {remote_dir} && "
                f"cp /data/data/{VENDING_PKG}/databases/library.db* {remote_dir}/ 2>/dev/null && "
                f"chmod -R 755 {remote_dir} && [ -s {remote_dir}/library.db ] && echo COPY_OK"
            )
            cp_out = adb_root_exec(self.adb, self.serial, copy_cmd, timeout=8)
            if "COPY_OK" not in cp_out:
                return []

            for suffix in ("", "-wal", "-shm"):
                adb_run(self.adb, self.serial, "pull", f"{remote_dir}/library.db{suffix}", str(local_dir / f"library.db{suffix}"), timeout=8)
            adb_root_exec(self.adb, self.serial, f"rm -rf {remote_dir}", timeout=5)

            local_db = local_dir / "library.db"
            if not local_db.exists() or local_db.stat().st_size < 100:
                return []

            records: List[Dict[str, Any]] = []
            now_ms = int(time.time() * 1000)
            con = sqlite3.connect(str(local_db))
            rows = con.execute(
                "SELECT account, doc_id, subs_valid_until_time, inapp_purchase_data "
                "FROM ownership WHERE doc_id LIKE '%g1.%' OR inapp_purchase_data LIKE '%g1.%'"
            ).fetchall()
            con.close()
            for acc, doc_id, valid, data in rows:
                j = json.loads(data) if data else {}
                v_ms = int(valid or 0)
                days_left = max(0, int(round((v_ms - now_ms) / 86400_000))) if v_ms > now_ms else 0
                exp_date = (
                    datetime.datetime.fromtimestamp(v_ms / 1000).strftime("%Y-%m-%d")
                    if v_ms > 0
                    else ""
                )
                records.append(
                    {
                        "account": acc or "",
                        "doc_id": doc_id or "",
                        "valid_until_ms": v_ms,
                        "expiry_date": exp_date,
                        "days_left": days_left,
                        "is_active": v_ms > now_ms,
                        "acknowledged": bool(j.get("acknowledged", True)),
                        "auto_renewing": bool(j.get("autoRenewing", False)),
                        "order_id": str(j.get("orderId") or ""),
                        "purchase_token": str(j.get("purchaseToken") or ""),
                    }
                )
            records.sort(key=lambda r: (1 if r["is_active"] else 0, r["valid_until_ms"]), reverse=True)
            return records
        except Exception:
            return []
        finally:
            shutil.rmtree(local_dir, ignore_errors=True)

    def best_stack_token(self, sku_hint: str = "subs_variant") -> str:
        subs = self.read_play_subscriptions()
        for r in subs:
            if r["is_active"] and r["purchase_token"] and (sku_hint in r["doc_id"] or "g1." in r["doc_id"]):
                return r["purchase_token"]
        for r in subs:
            if r["purchase_token"]:
                return r["purchase_token"]
        return ""

    # ---------- Doctor & Self-Healing ----------

    def run_doctor(self, auto_fix: bool = True, local_port: int = 27043) -> Dict[str, Any]:
        steps: List[Dict[str, str]] = []

        def _rec(name: str, status: str, detail: str) -> None:
            steps.append({"name": name, "status": status, "detail": detail})
            prefix = "[+]" if status == "ok" else ("[!] " if status == "warn" else "[-]")
            self.log(f"{prefix} {name}: {detail}")

        _rec("运行系统", "ok", os_display_label())
        if not self.ensure_host_tools():
            _rec("宿主机工具", "error", "ADB 或 Frida CLI 未就绪")
            return {"ok": False, "steps": steps}

        assert self.adb and self.frida_cli
        _rec("ADB & Frida", "ok", f"ADB={Path(self.adb).name}, Frida={get_frida_cli_version(self.frida_cli)}")

        if not self.connect_or_boot_device():
            _rec("模拟器连接", "error", "未检测到运行中的模拟器")
            return {"ok": False, "steps": steps}

        model = self.shell("getprop ro.product.model")
        abi = self.shell("getprop ro.product.cpu.abi")
        _rec("设备在线", "ok", f"{self.instance_name or 'Android'} ({self.serial}, {model}, {abi})")

        if auto_fix:
            # Ensure MuMu background service keep-alive so Play Store & DroidGuardService bindings aren't skipped
            if "true" in self.shell("getprop ro.build.version.nemux").lower():
                if self.shell("getprop app_keep_alive").strip().lower() == "false":
                    adb_root_exec(self.adb, self.serial, "setprop app_keep_alive true", timeout=5)
                    _rec("MuMu 后台保活", "ok", "已开启 app_keep_alive=true，防止 Play/DroidGuard 服务被跳过")
            # Clean interfering device VPNs/dead proxies if needed
            for vpn_pkg in ("com.github.metacubex.clash.meta", "com.github.kr328.clash"):
                if "yes" in self.shell(f"pm list packages | grep -q {vpn_pkg} && echo yes || true"):
                    self.shell(f"am force-stop {vpn_pkg}")
                    _rec("VPN 干扰清理", "warn", f"已关闭会劫持 Play 结算的端内 {vpn_pkg}")

        frida_ok = ensure_device_frida_and_module(self.adb, self.serial, self.frida_cli, local_port=local_port, log_fn=self.log)
        _rec("注入引擎 & 计费模块", "ok" if frida_ok else "error", "frida-server 运行中且 module.apk 已就位" if frida_ok else "部署失败")

        self.ensure_vending_ready()
        _rec("Play 商店服务", "ok", "com.android.vending 在线")

        # Check Play HTTPS connectivity
        proxy = self.shell("settings get global http_proxy")
        http_res = self.shell("curl -sI -o /dev/null -w '%{http_code} %{time_total}' --connect-timeout 5 https://play.google.com 2>/dev/null || echo '000 0'")
        parts = http_res.split()
        code = parts[0] if parts else "000"
        cost = parts[1] if len(parts) > 1 else "0"

        if code in ("200", "301", "302", "303"):
            if auto_fix:
                net_val = self.shell("dumpsys connectivity | grep -q VALIDATED && echo yes || echo no")
                if "yes" not in net_val:
                    self.shell("settings put global captive_portal_detection_enabled 0; settings put global captive_portal_mode 0")
            _rec("Google Play 网络", "ok", f"HTTPS 直连正常 (HTTP {code}, {cost}s)")
        else:
            if auto_fix and proxy and proxy not in ("null", ":0"):
                self.shell("settings put global http_proxy :0")
                code2 = self.shell("curl -sI -o /dev/null -w '%{http_code}' --connect-timeout 5 https://play.google.com 2>/dev/null || echo '000'")
                if code2 in ("200", "301", "302"):
                    _rec("Google Play 网络", "ok", f"自动清除残留代理 ({proxy}) 后恢复正常 (HTTP {code2})")
                else:
                    _rec("Google Play 网络", "error", f"无法访问 play.google.com (HTTP {code2})")
            else:
                _rec("Google Play 网络", "error", f"访问 play.google.com 异常 (HTTP {code})")

        accts = self.list_google_accounts()
        _rec("Google 账号", "ok" if accts else "warn", ", ".join(accts) if accts else "当前设备未登录 Google 账号")
        return {"ok": frida_ok, "steps": steps, "accounts": accts, "subscriptions": self.read_play_subscriptions()}

    # ---------- Screen Mirror & Resolution-Adaptive Remote Control ----------

    def capture_screenshot_png(self) -> bytes:
        if not self.adb or not self.serial:
            return b""
        data: bytes = self.sh("exec-out", "screencap", "-p", timeout=10, binary=True)
        if data.startswith(b"\x89PNG\r\r\n\x1a\n"):
            data = data.replace(b"\r\r\n", b"\r\n")
        if len(data) <= 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            # Fallback for older Windows adb builds where exec-out is unsupported
            remote_cap = f"/data/local/tmp/.gtool_cap_{os.getpid()}.png"
            local_cap = Path(tempfile.gettempdir()) / f"gtool_cap_{os.getpid()}.png"
            try:
                self.shell(f"screencap -p {remote_cap}", timeout=8)
                adb_run(self.adb, self.serial, "pull", remote_cap, str(local_cap), timeout=8)
                self.shell(f"rm -f {remote_cap}", timeout=4)
                if local_cap.exists():
                    data = local_cap.read_bytes()
            except Exception:
                pass
            finally:
                local_cap.unlink(missing_ok=True)

        if len(data) > 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            if 200 <= w <= 8000 and 200 <= h <= 8000:
                self.screen_size = (w, h)
            return data
        return b""

    def tap_normalized(self, nx: float, ny: float) -> Tuple[int, int]:
        w, h = self.screen_size
        x = max(0, min(w - 1, int(round(nx * w))))
        y = max(0, min(h - 1, int(round(ny * h))))
        self.shell(f"input tap {x} {y}")
        return x, y

    def swipe_normalized(self, nx1: float, ny1: float, nx2: float, ny2: float, dur_ms: int = 280) -> None:
        w, h = self.screen_size
        x1, y1 = int(round(nx1 * w)), int(round(ny1 * h))
        x2, y2 = int(round(nx2 * w)), int(round(ny2 * h))
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {dur_ms}")

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {int(x)} {int(y)}")

    def press_key(self, key: str) -> None:
        clean_key = str(key or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", clean_key):
            return
        self.shell(f"input keyevent {clean_key}")

    def ensure_screen_on(self) -> None:
        pw = self.shell("dumpsys power | grep 'Display Power'")
        if "state=ON" not in pw:
            self.press_key("KEYCODE_WAKEUP")
            time.sleep(0.4)
            self.swipe_normalized(0.5, 0.72, 0.5, 0.30, 220)
            time.sleep(0.3)

    def set_fast_animations(self, enable: bool = True) -> None:
        if enable and self._anim_saved is None:
            w = self.shell("settings get global window_animation_scale") or "0.5"
            t = self.shell("settings get global transition_animation_scale") or "0.5"
            d = self.shell("settings get global animator_duration_scale") or "0.5"
            self._anim_saved = (w, t, d)
            self.shell("settings put global window_animation_scale 0; settings put global transition_animation_scale 0; settings put global animator_duration_scale 0")
        elif not enable and self._anim_saved is not None:
            w, t, d = [v if v and v != "null" else "0.5" for v in self._anim_saved]
            self.shell(f"settings put global window_animation_scale {w}; settings put global transition_animation_scale {t}; settings put global animator_duration_scale {d}")
            self._anim_saved = None

    def ensure_vending_ready(self) -> None:
        if self.adb and self.serial and "true" in self.shell("getprop ro.build.version.nemux").lower():
            if self.shell("getprop app_keep_alive").strip().lower() == "false":
                adb_root_exec(self.adb, self.serial, "setprop app_keep_alive true", timeout=4)
        if self.shell(f"pidof {VENDING_PKG}"):
            return
        self.shell(f"monkey -p {VENDING_PKG} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1")
        for _ in range(12):
            time.sleep(0.35)
            if self.shell(f"pidof {VENDING_PKG}"):
                self.press_key("KEYCODE_HOME")
                return

    def current_google_one_pid(self) -> int:
        raw = self.shell(
            f"pidof -s {GOOGLE_ONE_PKG} 2>/dev/null || pidof {GOOGLE_ONE_PKG} 2>/dev/null || "
            f"ps -A 2>/dev/null | awk '$NF==\"{GOOGLE_ONE_PKG}\"{{print $2; exit}}'",
            timeout=5,
        ).split()
        return int(raw[0]) if raw and raw[0].isdigit() else 0

    def bring_google_one_foreground(self) -> int:
        self.ensure_screen_on()
        focus = self.shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'", timeout=5)
        if VENDING_PKG in focus or "ProxyBillingActivity" in focus:
            # Cleanly dismiss any lingering Play checkout sheet so Play never rejects with code=5 Duplicate purchase
            self.press_key("KEYCODE_BACK")
            time.sleep(0.65)
            focus = self.shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'", timeout=5)
        if GOOGLE_ONE_PKG not in focus:
            self.shell(
                f"am start -n {GOOGLE_ONE_PKG}/com.google.android.apps.subscriptions.red.LauncherActivity >/dev/null 2>&1 "
                f"|| monkey -p {GOOGLE_ONE_PKG} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1",
                timeout=6,
            )
            for _ in range(10):
                time.sleep(0.2)
                focus2 = self.shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'", timeout=4)
                if GOOGLE_ONE_PKG in focus2:
                    break
        return self.current_google_one_pid()

    def ensure_google_one_pid(self, force_restart: bool = False) -> int:
        if not force_restart:
            pid = self.current_google_one_pid()
            if pid > 0:
                pid2 = self.bring_google_one_foreground()
                if pid2 > 0:
                    return pid2

        if force_restart:
            self.shell(f"am force-stop {GOOGLE_ONE_PKG}")
            time.sleep(0.3)

        # Verify ADB shell responsiveness before checking pm path (prevents false uninstall detection on TCP reconnect)
        if "ADB_OK" not in self.shell("echo ADB_OK"):
            if self.serial.startswith("127.0.0.1:") and self.adb:
                adb_run(self.adb, "", "connect", self.serial, timeout=5)
                time.sleep(0.4)
            if "ADB_OK" not in self.shell("echo ADB_OK"):
                return 0

        if "package:" not in self.shell(f"pm path {GOOGLE_ONE_PKG}"):
            if not self.install_google_one():
                return 0

        self.ensure_screen_on()
        self.shell(
            f"am start -n {GOOGLE_ONE_PKG}/com.google.android.apps.subscriptions.red.LauncherActivity >/dev/null 2>&1 "
            f"|| monkey -p {GOOGLE_ONE_PKG} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1"
        )
        for i in range(25):
            time.sleep(0.25)
            pid = self.current_google_one_pid()
            if pid > 0:
                focus = self.shell("dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'", timeout=4)
                if GOOGLE_ONE_PKG in focus or i >= 6:
                    time.sleep(0.35)
                    return pid
        return 0

    # ---------- Fast UI Dump & Text Input ----------

    def dump_xml_and_nodes(self) -> Tuple[str, List[Dict[str, Any]]]:
        raw = self.shell("uiautomator dump --compressed /data/local/tmp/ui.xml >/dev/null 2>&1 && cat /data/local/tmp/ui.xml", timeout=15)
        if "<hierarchy" not in raw:
            raw = self.shell("uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1 && cat /data/local/tmp/ui.xml", timeout=15)
        return raw, parse_ui_xml(raw)

    @staticmethod
    def _sh_single_quote(s: str) -> str:
        return "'" + s.replace("'", "'\"'\"'") + "'"

    def type_text(self, text: str) -> None:
        parts = text.split("@")
        for idx, seg in enumerate(parts):
            if seg:
                esc = seg.replace(" ", "%s")
                self.shell(f"input text {self._sh_single_quote(esc)}")
            if idx < len(parts) - 1:
                self.press_key("77")  # KEYCODE_AT

    def type_secret(self, secret: str) -> None:
        buf = ""
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._,;:!?/=+-")
        for ch in secret:
            if ch in safe_chars:
                buf += ch
            else:
                if buf:
                    self.shell(f"input text {self._sh_single_quote(buf)}")
                    time.sleep(0.04)
                    buf = ""
                if ch == " ":
                    self.press_key("62")
                elif ch == "@":
                    self.press_key("77")
                else:
                    self.shell(f"input text {self._sh_single_quote(ch)}")
                time.sleep(0.04)
        if buf:
            self.shell(f"input text {self._sh_single_quote(buf)}")
            time.sleep(0.04)

    # ---------- Account Lifecycle ----------

    def list_google_accounts(self) -> List[str]:
        out = self.shell("dumpsys account")
        found = sorted(set(re.findall(r"Account\s*\{name=([^,]+),\s*type=com\.google\b", out)))
        return found

    def switch_play_account(self, email: str) -> None:
        self.shell(f"am force-stop {VENDING_PKG}")
        sq_em = self._sh_single_quote(email)
        self.shell(f"am start -n {VENDING_PKG}/com.google.android.finsky.activities.MainActivity --es authAccount {sq_em} >/dev/null 2>&1")
        time.sleep(1.2)

    def remove_all_accounts(self) -> bool:
        for email in self.list_google_accounts():
            self.log(f"[*] 正在移除旧账号: {email}")
            self.shell("am start --activity-clear-task -a android.settings.SYNC_SETTINGS >/dev/null 2>&1")
            time.sleep(0.8)
            _, nodes = self.dump_xml_and_nodes()
            pt = find_containing(nodes, email)
            if not pt:
                pt_g = find_containing(nodes, "Google", "google.com")
                if pt_g:
                    self.tap(*pt_g)
                    time.sleep(0.8)
                    _, nodes = self.dump_xml_and_nodes()
                    pt = find_containing(nodes, email)
            if not pt:
                return False
            self.tap(*pt)
            time.sleep(0.7)
            self.swipe_normalized(0.5, 0.65, 0.5, 0.22, 300)
            time.sleep(0.3)
            _, nodes = self.dump_xml_and_nodes()
            rm_pt = find_cta_button(nodes, *REMOVE_LABELS) or find_containing(nodes, *REMOVE_LABELS)
            if not rm_pt:
                more_pt = find_containing(nodes, "More options", "更多选项", "⋮")
                if more_pt:
                    self.tap(*more_pt)
                    time.sleep(0.6)
                    _, nodes = self.dump_xml_and_nodes()
                    rm_pt = find_containing(nodes, *REMOVE_LABELS)
            if not rm_pt:
                return False
            self.tap(*rm_pt)
            time.sleep(0.6)
            _, nodes = self.dump_xml_and_nodes()
            btn1 = next(((n["cx"], n["cy"]) for n in nodes if "button1" in n["res_id"]), None)
            conf_pt = btn1 or find_cta_button(nodes, "移除帐号", "移除账号", "Remove account", "OK", "确定")
            if conf_pt:
                self.tap(*conf_pt)
            time.sleep(0.8)
            self.press_key("KEYCODE_HOME")
        return len(self.list_google_accounts()) == 0

    def add_google_account(
        self,
        email: str,
        password: str,
        totp_secret: str = "",
        recovery_email: str = "",
        human_cb: Optional[Callable[[str], Optional[str]]] = None,
    ) -> bool:
        if any(a.lower() == email.lower() for a in self.list_google_accounts()):
            return True

        self.ensure_screen_on()
        self.shell("am start -a android.settings.ADD_ACCOUNT_SETTINGS --es account_types com.google >/dev/null 2>&1")
        time.sleep(1.0)
        raw, nodes = self.dump_xml_and_nodes()
        if "com.google.android.gms" not in raw:
            g_pt = find_containing(nodes, "Google")
            if g_pt:
                self.tap(*g_pt)
                time.sleep(2.0)

        # Wait for email EditText
        edit_pt = None
        for _ in range(25):
            raw, nodes = self.dump_xml_and_nodes()
            edit_pt = next(((n["cx"], n["cy"]) for n in nodes if "EditText" in n["cls"] or "identifierId" in n["res_id"]), None)
            if edit_pt:
                break
            time.sleep(0.5)
        if not edit_pt:
            self.log("[-] 登录页加载超时")
            return False

        # Enter email with read-back verification (from ultra0.py, prevents swallowed @/chars!)
        for attempt in range(3):
            self.tap(*edit_pt)
            time.sleep(0.25)
            if attempt > 0:
                self.press_key("123")
                for _ in range(45):
                    self.press_key("67")
            self.type_text(email)
            time.sleep(0.4)
            _, chk_nodes = self.dump_xml_and_nodes()
            typed_blob = " ".join(n["text"] for n in chk_nodes if n["text"])
            if email.lower() in typed_blob.lower() or attempt == 2:
                break

        nxt = find_cta_button(chk_nodes, *NEXT_LABELS) or find_containing(chk_nodes, *NEXT_LABELS)
        if nxt:
            self.tap(*nxt)
        else:
            self.press_key("66")
        time.sleep(1.0)

        # Wait for password input
        pw_pt = None
        for _ in range(20):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"找不到此账号|Couldn.t find your Google", raw, re.I):
                self.log(f"[-] Google 提示账号不存在: {email}")
                return False
            pw_pt = next(((n["cx"], n["cy"]) for n in nodes if n["password"] or "EditText" in n["cls"]), None)
            if pw_pt and re.search(r'password="true"|输入您的密码|Enter your password', raw, re.I):
                break
            time.sleep(0.5)

        if pw_pt:
            self.tap(*pw_pt)
            time.sleep(0.25)
            self.type_secret(password)
            time.sleep(0.35)
            _, nodes = self.dump_xml_and_nodes()
            nxt = find_cta_button(nodes, *NEXT_LABELS) or find_containing(nodes, *NEXT_LABELS)
            if nxt:
                self.tap(*nxt)
            else:
                self.press_key("66")
            time.sleep(1.0)

        # Handle 2FA / recovery / ToS / setup dialogs
        deadline = time.time() + 80
        while time.time() < deadline:
            if any(a.lower() == email.lower() for a in self.list_google_accounts()):
                self.press_key("KEYCODE_HOME")
                return True

            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"密码不正确|Wrong password", raw, re.I):
                self.log(f"[-] 密码不正确: {email}")
                return False

            # 2FA
            if re.search(r"2.step verification|两步验证|enter.*code|输入验证码|authenticator", raw, re.I):
                if totp_secret:
                    code = generate_totp(totp_secret, self.log)
                    ed = next(
                        ((n["cx"], n["cy"]) for n in nodes if "EditText" in n["cls"]),
                        (int(self.screen_size[0] * 0.5), int(self.screen_size[1] * 0.34)),
                    )
                    self.tap(*ed)
                    time.sleep(0.25)
                    self.type_text(code)
                    time.sleep(0.35)
                    _, nodes = self.dump_xml_and_nodes()
                    v_pt = find_cta_button(nodes, *NEXT_LABELS, "Verify", "验证") or find_containing(nodes, *NEXT_LABELS)
                    if v_pt:
                        self.tap(*v_pt)
                    else:
                        self.press_key("66")
                    time.sleep(1.2)
                    continue
                act = self.human_gate.request_assist(f"账号 {email} 需要输入两步验证码，请在模拟器手动完成后继续", human_cb)
                if act != "continue":
                    return False
                continue

            # Recovery email challenge
            if recovery_email and re.search(r"确认您的辅助邮箱|Confirm your recovery email|选择.*登录方式", raw, re.I):
                rec_pt = find_containing(nodes, "确认您的辅助邮箱", "Confirm your recovery email")
                if rec_pt:
                    self.tap(*rec_pt)
                else:
                    self.tap_normalized(0.5, 0.535)
                time.sleep(1.4)
                _, rnodes = self.dump_xml_and_nodes()
                ed = next(((n["cx"], n["cy"]) for n in rnodes if "EditText" in n["cls"]), None)
                if ed:
                    self.tap(*ed)
                    time.sleep(0.25)
                    self.type_text(recovery_email)
                    time.sleep(0.35)
                    _, rnodes = self.dump_xml_and_nodes()
                    n_pt = find_cta_button(rnodes, *NEXT_LABELS) or find_containing(rnodes, *NEXT_LABELS)
                    if n_pt:
                        self.tap(*n_pt)
                    else:
                        self.press_key("66")
                    time.sleep(1.5)
                    continue

            # Anti-bot / phone challenge -> strictly pause for human (never auto-solve CAPTCHAs)
            if re.search(r"证明您不是自动程序|请输入电话号码|confirm you.re not a robot|验证身份", raw, re.I):
                act = self.human_gate.request_assist(f"账号 {email} 触发 Google 身份/安全验证，请在模拟器手动处理后继续", human_cb)
                if act != "continue":
                    return False
                deadline = time.time() + 60
                continue

            # Agreement & setup dialogs
            btn = (
                find_cta_button(nodes, *AGREE_LABELS, "不开启", "Don't turn on", "关闭", "Close", *SKIP_LABELS)
                or find_containing(nodes, *SKIP_LABELS, "接受", "Accept")
            )
            if btn:
                self.tap(*btn)
                time.sleep(0.8)
                continue

            if re.search(r"More|更多", raw, re.I):
                self.swipe_normalized(0.5, 0.65, 0.5, 0.22, 300)
                time.sleep(0.5)
                continue

            time.sleep(0.8)
        return False

    # ---------- Card Binding, Google One Prep, Checkout & Cancellation ----------

    @staticmethod
    def _has_card_last4(raw_xml: str, last4: str) -> bool:
        return bool(last4 and re.search(rf"(?:mastercard|visa|amex|discover|jcb|••|\*\*\*\*|card)[^<\"]*-?{re.escape(last4)}", raw_xml, re.I))

    def bind_card_playstore(self, number: str, expiry: str, cvv: str, postal_mode: str = "classic") -> bool:
        last4 = number[-4:]
        self.shell(
            f"am start -a android.intent.action.VIEW -p {VENDING_PKG} -d 'https://play.google.com/store/paymentmethods' >/dev/null 2>&1 "
            "|| am start -a android.intent.action.VIEW -d 'https://play.google.com/store/paymentmethods' >/dev/null 2>&1"
        )
        time.sleep(1.4)

        raw = ""
        nodes: List[Dict[str, Any]] = []
        for _ in range(15):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"Payment methods|付款方式|支付方式", raw, re.I):
                break
            time.sleep(0.5)

        if self._has_card_last4(raw, last4):
            self.press_key("KEYCODE_HOME")
            return True

        add_pt = find_containing(nodes, "添加卡", "Add card", "添加信用卡或借记卡", "Add credit or debit card", "Add payment method")
        if not add_pt:
            return False
        self.tap(*add_pt)
        time.sleep(1.2)

        for _ in range(15):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"卡号|Card number|所有字段", raw, re.I):
                break
            if re.search(r"Credit or debit|信用卡或借记卡", raw, re.I):
                c_pt = find_containing(nodes, "Credit or debit", "信用卡或借记卡")
                if c_pt:
                    self.tap(*c_pt)
                    time.sleep(1.0)
            time.sleep(0.6)

        inputs = [n for n in nodes if "EditText" in n["cls"] or "AutoCompleteTextView" in n["cls"]]
        num_pt = find_containing(nodes, "卡号", "Card number") or ((inputs[0]["cx"], inputs[0]["cy"]) if inputs else None)
        if not num_pt:
            return False
        self.tap(*num_pt)
        time.sleep(0.25)
        self.type_text(re.sub(r"\D", "", number))
        time.sleep(0.4)

        _, nodes = self.dump_xml_and_nodes()
        inputs = [n for n in nodes if "EditText" in n["cls"] or "AutoCompleteTextView" in n["cls"]]
        exp_pt = find_containing(nodes, "失效日期", "MM/YY", "有效期", "Expiry") or ((inputs[1]["cx"], inputs[1]["cy"]) if len(inputs) > 1 else None)
        if exp_pt:
            self.tap(*exp_pt)
            time.sleep(0.2)
        else:
            self.press_key("KEYCODE_TAB")
        # Type pure 4 digits MMYY so Play Store's MM/YY TextWatcher + LengthFilter(5) never produces "06//2"!
        exp_digits = re.sub(r"\D", "", expiry)
        self.type_text(exp_digits if len(exp_digits) == 4 else expiry)
        time.sleep(0.35)

        cvv_pt = find_containing(nodes, "CVV", "CVC", "安全码", "Security code") or ((inputs[2]["cx"], inputs[2]["cy"]) if len(inputs) > 2 else None)
        if cvv_pt:
            self.tap(*cvv_pt)
            time.sleep(0.2)
        else:
            self.press_key("KEYCODE_TAB")
        self.type_text(re.sub(r"\D", "", cvv))
        time.sleep(0.35)

        self.swipe_normalized(0.5, 0.65, 0.5, 0.30, 300)
        time.sleep(0.4)
        _, nodes = self.dump_xml_and_nodes()
        zip_pt = find_containing(nodes, "账单邮寄地址", "邮政编码", "postal", "ZIP")
        chosen_zip = random.choice(POSTAL_TAXFREE if postal_mode == "taxfree" else POSTAL_CLASSIC)
        if zip_pt:
            self.tap(*zip_pt)
            time.sleep(0.25)
            self.type_text(chosen_zip)
            time.sleep(0.35)

        _, nodes = self.dump_xml_and_nodes()
        sv = find_cta_button(nodes, "保存卡", "Save card", "Save", "保存", "确认") or find_containing(nodes, "保存卡", "Save card", "保存")
        if sv:
            self.tap(*sv)
        else:
            self.press_key("66")
        time.sleep(2.2)

        for _ in range(14):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"卡号无效|invalid card|declined|已被拒绝|更正此卡信息|无法添加", raw, re.I):
                self.log(f"[-] Google Play 拒绝了该卡片或卡信息无效 (••••{last4})")
                self.press_key("KEYCODE_BACK")
                return False
            if self._has_card_last4(raw, last4):
                self.press_key("KEYCODE_HOME")
                return True
            if re.search(r"postal|邮编|ZIP", raw, re.I):
                z_pt = find_containing(nodes, "ZIP", "Postal", "邮编", "邮政编码")
                if z_pt:
                    self.tap(*z_pt)
                    time.sleep(0.2)
                    self.type_text(chosen_zip)
                    time.sleep(0.3)
                s_pt = find_cta_button(nodes, "Save", "保存", "继续", "Continue", "确定", "OK")
                if s_pt:
                    self.tap(*s_pt)
                    time.sleep(0.9)
                    continue
            ok_pt = find_cta_button(nodes, "确定", "OK", "完成", "Done")
            if ok_pt:
                self.tap(*ok_pt)
            time.sleep(0.8)

        # Final authoritative check on paymentmethods list
        self.shell(f"am start -a android.intent.action.VIEW -p {VENDING_PKG} -d 'https://play.google.com/store/paymentmethods' >/dev/null 2>&1")
        time.sleep(1.5)
        raw, _ = self.dump_xml_and_nodes()
        self.press_key("KEYCODE_HOME")
        return self._has_card_last4(raw, last4)

    def install_google_one(self) -> bool:
        if "package:" in self.shell(f"pm path {GOOGLE_ONE_PKG}"):
            return True
        self.log("[*] 正在从 Google Play 安装 Google One...")
        self.shell(
            f"am start -a android.intent.action.VIEW -p {VENDING_PKG} -d 'market://details?id={GOOGLE_ONE_PKG}' >/dev/null 2>&1 "
            f"|| am start -a android.intent.action.VIEW -d 'market://details?id={GOOGLE_ONE_PKG}' >/dev/null 2>&1"
        )
        time.sleep(2.2)
        raw, nodes = self.dump_xml_and_nodes()
        if re.search(r"仅此一次|Just once", raw, re.I):
            j_pt = find_containing(nodes, "仅此一次", "Just once")
            if j_pt:
                self.tap(*j_pt)
                time.sleep(2.0)
                raw, nodes = self.dump_xml_and_nodes()
        ins_pt = find_cta_button(nodes, "安装", "Install")
        if not ins_pt:
            return False
        self.tap(*ins_pt)
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2.0)
            if "package:" in self.shell(f"pm path {GOOGLE_ONE_PKG}"):
                self.press_key("KEYCODE_BACK")
                return True
        return False

    def prepare_google_one(self, email: str, mode: str = "smart") -> bool:
        if mode == "reinstall":
            self.shell(f"pm uninstall {GOOGLE_ONE_PKG}")
            return self.install_google_one()
        if "package:" in self.shell(f"pm path {GOOGLE_ONE_PKG}"):
            self.shell(f"pm clear {GOOGLE_ONE_PKG}")
            self.switch_play_account(email)
            return True
        return self.install_google_one()

    def confirm_checkout_sheet(
        self,
        expect_free: bool = True,
        human_cb: Optional[Callable[[str], Optional[str]]] = None,
    ) -> Tuple[bool, str]:
        if not expect_free:
            act = self.human_gate.request_assist("付费促销收银台已拉起：请在模拟器亲自核对价格并点击「订阅」完成后继续", human_cb)
            return (act == "continue", "MANUAL_PAID" if act == "continue" else "SKIPPED")

        deadline = time.time() + 18
        while time.time() < deadline:
            raw, nodes = self.dump_xml_and_nodes()
            verdict = classify_checkout_xml(raw)
            if verdict == "INELIGIBLE":
                pt = find_containing(nodes, "知道了", "OK", "Got it", "关闭", "Close")
                if pt:
                    self.tap(*pt)
                else:
                    self.press_key("KEYCODE_BACK")
                return False, "INELIGIBLE"
            if verdict == "ALREADY_OWNED":
                self.press_key("KEYCODE_BACK")
                return False, "ITEM_ALREADY_OWNED"
            if verdict == "NON_ZERO":
                self.press_key("KEYCODE_BACK")
                return False, "PRICE_NOT_ZERO_BLOCKED"
            if verdict == "OFFLINE":
                pt = find_containing(nodes, "重试", "Retry")
                if pt:
                    self.tap(*pt)
                time.sleep(1.2)
                continue
            if verdict == "ZERO_OK":
                sub_pt = find_cta_button(nodes, "订阅", "Subscribe")
                if sub_pt:
                    self.tap(*sub_pt)
                    time.sleep(0.8)
                    return True, "SUBSCRIBED_TAPPED"
            time.sleep(0.6)
        return False, "CHECKOUT_TIMEOUT"

    def handle_billing_password(
        self,
        password: str,
        is_activated_fn: Optional[Callable[[], bool]] = None,
    ) -> bool:
        for _ in range(20):
            time.sleep(0.6)
            if is_activated_fn and is_activated_fn():
                return True
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"付款成功|已订阅|payment.*success|subscribed|身份验证设置|备用付款", raw, re.I):
                return True
            use_pw = find_containing(nodes, "使用密码", "Use password")
            if use_pw:
                self.tap(*use_pw)
                time.sleep(0.5)
                raw, nodes = self.dump_xml_and_nodes()
            pw_node = next((n for n in nodes if n["password"]), None)
            if pw_node:
                self.tap(pw_node["cx"], pw_node["cy"])
                time.sleep(0.25)
                self.type_secret(password)
                time.sleep(0.35)
                _, nodes = self.dump_xml_and_nodes()
                v_pt = find_cta_button(nodes, "验证", "Verify", "确定", "OK", "确认", "Confirm") or find_containing(nodes, "验证", "Verify")
                if v_pt:
                    self.tap(*v_pt)
                else:
                    self.press_key("66")
                return True
        return False

    def handle_post_payment(self, is_activated_fn: Optional[Callable[[], bool]] = None) -> None:
        deadline = time.time() + 20
        while time.time() < deadline:
            activated = bool(is_activated_fn and is_activated_fn())
            if not activated:
                lc = self.sh("logcat", "-d", "-s", "AutoTrial:I", timeout=6)
                activated = "=== TRIAL_ACTIVATED ===" in lc
            raw, nodes = self.dump_xml_and_nodes()
            if activated:
                pt = find_containing(nodes, "不用了", "No thanks", "以后再说", "完成", "Done", "确定", "OK")
                if pt:
                    self.tap(*pt)
                return
            if re.search(r"身份验证设置|authentication.*settings|购物身份验证", raw, re.I):
                no_pt = find_cta_button(nodes, "不用了", "No thanks") or find_containing(nodes, "不用了", "No thanks")
                if no_pt:
                    self.tap(*no_pt)
                    time.sleep(0.5)
                    _, nodes = self.dump_xml_and_nodes()
                ok_pt = find_cta_button(nodes, "确定", "OK", "Done")
                if ok_pt:
                    self.tap(*ok_pt)
                time.sleep(0.6)
                continue
            if re.search(r"备用付款|backup.*payment|开启备用|Play 积分|Play Points", raw, re.I):
                pt = find_containing(nodes, "以后再说", "不用了", "Not now", "No thanks")
                if pt:
                    self.tap(*pt)
                else:
                    self.press_key("KEYCODE_BACK")
                time.sleep(0.6)
                continue
            if re.search(r"付款成功|payment.*success|已订阅|subscribed", raw, re.I):
                pt = find_containing(nodes, "完成", "Done", "OK", "确定", "知道了")
                if pt:
                    self.tap(*pt)
                return
            time.sleep(0.6)

    def cancel_subscription(self) -> bool:
        self.log("[*] 正在打开 Play 订阅管理页并取消自动续费...")
        self.shell(
            f"am start -a android.intent.action.VIEW -p {VENDING_PKG} -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1 "
            "|| am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1"
        )
        time.sleep(1.5)

        raw = ""
        nodes: List[Dict[str, Any]] = []
        for _ in range(18):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"Google One|Google AI|订阅|Subscriptions", raw, re.I):
                break
            time.sleep(0.5)

        entry = find_containing(nodes, "Google One", "Google AI")
        if not entry:
            self.log("[-] 未在订阅列表找到活跃的 Google One / Google AI 条目")
            return False
        self.tap(*entry)
        time.sleep(1.0)

        for _ in range(12):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"已取消|Canceled|cancelled|重新订阅|Resubscribe", raw, re.I):
                self.log("[+] 订阅已处于取消自动续费状态")
                return True
            if re.search(r"取消订阅|Cancel subscription", raw, re.I):
                break
            time.sleep(0.5)

        cx_pt = find_cta_button(nodes, "取消订阅", "Cancel subscription") or find_containing(nodes, "取消订阅", "Cancel subscription")
        if not cx_pt:
            return False
        self.tap(*cx_pt)
        time.sleep(1.0)

        for _ in range(5):
            raw, nodes = self.dump_xml_and_nodes()
            if re.search(r"已取消|Canceled|cancelled|重新订阅|Resubscribe", raw, re.I):
                self.press_key("KEYCODE_BACK")
                self.log("[+] 自动续费已成功取消，免费期权益完整保留！")
                return True
            if re.search(r"暂停付款|Pause payments|不用了，谢谢|No thanks", raw, re.I):
                pt = find_cta_button(nodes, "不用了，谢谢", "No thanks", "继续", "Continue") or find_containing(nodes, "不用了，谢谢", "No thanks")
                if pt:
                    self.tap(*pt)
                    time.sleep(0.8)
                    continue
            if re.search(r"原因|reason|拒绝回答|Prefer not to answer", raw, re.I):
                r_pt = find_containing(nodes, "拒绝回答", "Prefer not to answer", "其他", "Other")
                if r_pt:
                    self.tap(*r_pt)
                    time.sleep(0.6)
                    _, nodes = self.dump_xml_and_nodes()
                c_pt = find_cta_button(nodes, "继续", "Continue", "取消订阅", "Cancel subscription")
                if c_pt:
                    self.tap(*c_pt)
                    time.sleep(0.8)
                    continue
            final_pt = find_cta_button(nodes, "取消订阅", "Cancel subscription")
            if final_pt:
                self.tap(*final_pt)
                time.sleep(1.0)
        raw, _ = self.dump_xml_and_nodes()
        return bool(re.search(r"已取消|Canceled|cancelled|重新订阅|Resubscribe", raw, re.I))
