#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/billing_engine.py — Persistent Frida BillingClient session (`-q -t inf`), real-time streaming SKU output & 24m Wizard."""

from __future__ import annotations

import atexit
import json
import os
import queue
import re
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .device_ops import DeviceController
from .platform_env import (
    FRIDA_JS_LOCAL,
    GOOGLE_ONE_PKG,
    MODULE_REMOTE,
    STANDARD_SKUS,
    WIN_NO_WINDOW,
    adb_root_exec,
    adb_run,
    ensure_device_frida_and_module,
)

CMD_FILE_REMOTE = f"/data/data/{GOOGLE_ONE_PKG}/cache/.gtool_cmd"
EXT_CMD_FILE_REMOTE = f"/sdcard/Android/data/{GOOGLE_ONE_PKG}/cache/.gtool_cmd"

PRESETS: List[Dict[str, Any]] = [
    {
        "code": "1",
        "alias": "pro12",
        "group": "free",
        "title": "Pro 5TB · 免费 12 个月 (第1步首开)",
        "desc": "0 元首开 1 年 AI Pro 5TB，后续可继续叠加 +6/+6 至 24 个月",
        "sku": "g1.2tb.ai.subs_variant",
        "offer_id": "12months-eft",
        "stack": False,
        "is_paid": False,
        "badge": "★ 推荐首开",
    },
    {
        "code": "2",
        "alias": "stack1",
        "group": "free",
        "title": "Pro 5TB · 免费叠加 +6 个月 (第2步→18月)",
        "desc": "读取第1步活跃 token 走 CHARGE_FULL_PRICE 折算顺延至约 546 天",
        "sku": "g1.2tb.ai.subs_variant",
        "offer_id": "6months-eft",
        "stack": True,
        "is_paid": False,
        "badge": "⚡ 叠加第2步",
    },
    {
        "code": "3",
        "alias": "stack2",
        "group": "free",
        "title": "Pro 5TB · 免费叠加 +6 个月 (第3步→24月)",
        "desc": "在第2步成功基础上再次顺延 +6 个月，累计白嫖约 730 天",
        "sku": "g1.2tb.ai.subs_variant",
        "offer_id": "6months-eft-2",
        "stack": True,
        "is_paid": False,
        "badge": "⚡ 叠加第3步",
    },
    {
        "code": "4",
        "alias": "pro6c",
        "group": "free",
        "title": "Pro 5TB · 免费备用包 +6 个月 (ss-2026)",
        "desc": "备用叠加 Offer (6months-eft-ss-2026)，主包用过或不可用时补位",
        "sku": "g1.2tb.ai.subs_variant",
        "offer_id": "6months-eft-ss-2026",
        "stack": True,
        "is_paid": False,
        "badge": "备用叠加",
    },
    {
        "code": "5",
        "alias": "pro3",
        "group": "free",
        "title": "Pro 5TB · 免费 3 个月 (独立单开)",
        "desc": "经典 g1.play.2tb.ai 独立 3 个月 $0 试用，适合单开",
        "sku": "g1.play.2tb.ai",
        "offer_id": "eft-3mo",
        "stack": False,
        "is_paid": False,
        "badge": "单开3月",
    },
    {
        "code": "6",
        "alias": "prem6",
        "group": "free",
        "title": "Google One 2TB · 免费 6 个月 (独立备用池)",
        "desc": "11月新挖掘 g1.2tb.subs_variant 独立 $0 试用池，AI Pro 无资格时可兜底白嫖",
        "sku": "g1.2tb.subs_variant",
        "offer_id": "6months-eft",
        "stack": False,
        "is_paid": False,
        "badge": "★ 新发现6月",
    },
    {
        "code": "7",
        "alias": "auto",
        "group": "free",
        "title": "智能优选当前账号最长 $0 免费试用",
        "desc": "实时扫描全档位，自动挑出当前账号免费时长最长的 0 元方案",
        "sku": "auto",
        "offer_id": "",
        "stack": False,
        "is_paid": False,
        "badge": "全自动匹配",
    },
    {
        "code": "8",
        "alias": "p_yr90",
        "group": "promo",
        "title": "Pro 5TB · 连续 12 个月 1折 ($1.99/月)",
        "desc": "11月王炸神车！整年 12 期每期仅约 $1.99，每月可领 $10 Cloud API 赠金（老号可用）",
        "sku": "g1.2tb.ai.12months_ip_90p",
        "offer_id": "__PROMO__",
        "stack": False,
        "is_paid": True,
        "badge": "🔥 整年1折王炸",
    },
    {
        "code": "9",
        "alias": "p_3m90",
        "group": "promo",
        "title": "Pro 5TB · 前 3 个月 1折 ($1.99/月)",
        "desc": "首 3 期每期仅约 $1.99（原价 $19.99/月），适合无 $0 试用资格的老号低成本上车",
        "sku": "g1.2tb.ai.3months_ip_90p.acq",
        "offer_id": "__PROMO__",
        "stack": False,
        "is_paid": True,
        "badge": "🔥 前3月1折",
    },
    {
        "code": "10",
        "alias": "u1",
        "group": "promo",
        "title": "Ultra 30TB (20x) · 首月 1折 ($19.99)",
        "desc": "11月最新存活 Ultra 1折！首月 $19.99 立领 $100 Cloud API 赠金 + 2000 Colab 算力",
        "sku": "g1.ai.ultra.1month_ip_90p.acq",
        "offer_id": "__PROMO__",
        "stack": False,
        "is_paid": True,
        "badge": "🔥 首月1折",
    },
    {
        "code": "11",
        "alias": "u2",
        "group": "promo",
        "title": "Ultra 30TB (20x) · 前 3 月 2折 ($39.99/月)",
        "desc": "原 3 月 1 折下线后的主力长效车，前 3 月 2 折畅享 Gemini 4 Carbon 与 YouTube 家庭版",
        "sku": "g1.ai.ultra.3months_ip_80p.acq",
        "offer_id": "__PROMO__",
        "stack": False,
        "is_paid": True,
        "badge": "⚡ 3月2折主力",
    },
    {
        "code": "12",
        "alias": "u4",
        "group": "promo",
        "title": "Ultra 30TB (20x) · 前 3 月 2.5折 ($49.99/月)",
        "desc": "1折/2折无资格时的 Ultra 30TB 备选特惠档（已内置防误拉原价保护）",
        "sku": "g1.ai.ultra.3months_ip_75p.acq",
        "offer_id": "__PROMO__",
        "stack": False,
        "is_paid": True,
        "badge": "2.5折备选",
    },
]


_EXTRA_PRESET_ALIASES: Dict[str, str] = {
    "p1": "pro12",
    "p2": "stack1",
    "pro6": "stack1",
    "p3": "stack2",
    "pro6b": "stack2",
    "p4": "pro6c",
    "stack3": "pro6c",
    "p5": "pro3",
    "p6": "auto",
    "2tb6": "prem6",
    "pro1y90": "p_yr90",
    "pro3m90": "p_3m90",
    "ultra30": "u1",
    "30tb": "u1",
    "ultra20": "u2",
    "20tb": "u2",
    "u3": "u2",
    "ultra20_2": "u2",
    "ultra30_25": "u4",
    "0": "u4",
}


def evaluate_preset_eligibility(preset: Dict[str, Any], offers: List[Dict[str, Any]]) -> Dict[str, str]:
    """Check live eligibility & localized price for a preset against scanned BillingClient offers."""
    if not offers:
        return {"elig": "unknown", "live_price": ""}
    sku = preset.get("sku", "")
    oid = preset.get("offer_id", "")
    if sku == "auto":
        trials = [o for o in offers if o.get("type") == "TRIAL"]
        return {"elig": "available" if trials else "ineligible", "live_price": "$0" if trials else ""}
    for o in offers:
        if o.get("product") != sku:
            continue
        if oid == "__PROMO__":
            if o.get("type") in ("PROMO", "TRIAL"):
                return {"elig": "available", "live_price": str(o.get("price") or "")}
        elif oid:
            if o.get("offer_id") == oid or (oid.startswith("eft-3mo") and str(o.get("offer_id", "")).startswith("eft-3mo")):
                return {"elig": "available", "live_price": "$0" if o.get("type") == "TRIAL" else str(o.get("price") or "")}
        else:
            return {"elig": "available", "live_price": str(o.get("price") or "")}
    return {"elig": "ineligible", "live_price": ""}


def resolve_preset(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip().lower()
    q = _EXTRA_PRESET_ALIASES.get(q, q)
    for p in PRESETS:
        if q in (p["code"].lower(), p["alias"].lower()):
            return dict(p)
    return None


def _pick_local_port(preferred: int = 27043) -> int:
    for p in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return preferred


def _parse_iso_months(iso: str) -> float:
    fixed = {"P1W": 0.25, "P1M": 1.0, "P2M": 2.0, "P3M": 3.0, "P6M": 6.0, "P1Y": 12.0, "P12M": 12.0}
    if not iso:
        return 0.0
    if iso in fixed:
        return fixed[iso]
    days = 0.0
    for pat, mult in ((r"(\d+)Y", 365.0), (r"(\d+)M", 30.4), (r"(\d+)W", 7.0), (r"(\d+)D", 1.0)):
        m = re.search(pat, iso)
        if m:
            days += int(m.group(1)) * mult
    return round(days / 30.4, 1) if days > 0 else 0.0


def format_offer_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    dur_map = {"P1W": "7天", "P1M": "1月", "P2M": "2月", "P3M": "3月", "P6M": "6月", "P1Y": "12月", "P12M": "12月"}
    per_map = {"P1M": "/月", "P2M": "/2月", "P3M": "/季", "P6M": "/半年", "P1Y": "/年", "P12M": "/年"}
    tp = raw.get("type", "BASE")
    trp = raw.get("trial_period", "")
    pr = raw.get("price", "")
    pe = raw.get("period", "")
    rn = raw.get("renew_price", "")
    cy = str(raw.get("intro_cycles", "0"))
    pe_lbl = per_map.get(pe, f"/{pe}" if pe else "")

    if tp == "TRIAL":
        if trp in dur_map:
            d_lbl = dur_map[trp]
        else:
            mo = _parse_iso_months(trp)
            d_lbl = f"{int(round(mo))}月" if mo >= 1 else (trp or "试用")
        badge = f"★ 免费{d_lbl}"
        pricing = f"首期 $0 → {pr}{pe_lbl}"
    elif tp == "PROMO":
        c_str = f"前{cy}期" if cy and cy != "0" else "首期"
        badge = "⚡ 特惠促销"
        pricing = f"{c_str} {pr} → {rn}{pe_lbl}" if rn else f"{pr}{pe_lbl}"
    else:
        badge = "标准付费"
        pricing = f"{pr}{pe_lbl}"

    out = dict(raw)
    out["badge"] = badge
    out["pricing_summary"] = pricing
    return out


def analyze_pro_stacking_wizard(
    subscriptions: List[Dict[str, Any]],
    offers: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    active_sub = next((s for s in subscriptions if s.get("is_active")), None)
    avail_offer_ids = {
        o["offer_id"]
        for o in (offers or [])
        if o.get("product") == "g1.2tb.ai.subs_variant" and o.get("type") == "TRIAL"
    }

    if not active_sub:
        return {
            "stage": 0,
            "days_left": 0,
            "expiry_date": "",
            "headline": "当前无活跃订阅 · 可开启第 1 步（免费 12 个月）或直接上车 Ultra 1折",
            "warning": "",
            "recommended_preset": "pro12",
            "recommended_label": "执行第 1 步：Pro 5TB 免费 12 个月首开",
            "steps": [
                {"step": 1, "name": "12月首开", "state": "current"},
                {"step": 2, "name": "+6月叠加(18m)", "state": "todo"},
                {"step": 3, "name": "+6月叠加(24m)", "state": "todo"},
                {"step": 4, "name": "关续费锁死", "state": "todo"},
            ],
        }

    days = int(active_sub.get("days_left") or 0)
    exp = active_sub.get("expiry_date") or ""
    acked = bool(active_sub.get("acknowledged", True))
    renew = bool(active_sub.get("auto_renewing", True))

    if not acked:
        return {
            "stage": 1,
            "days_left": days,
            "expiry_date": exp,
            "headline": f"检测到未完成 Acknowledge 确认的订单（剩余 {days} 天）",
            "warning": "请先执行【查单 & 补单确认同步】，确认到账后再继续叠加！",
            "recommended_preset": "ack",
            "recommended_label": "立即执行补单确认同步",
            "steps": [
                {"step": 1, "name": "12月首开", "state": "done"},
                {"step": 2, "name": "补单确认", "state": "current"},
                {"step": 3, "name": "+6月叠加", "state": "todo"},
                {"step": 4, "name": "关续费锁死", "state": "todo"},
            ],
        }

    if days >= 620:
        if renew:
            return {
                "stage": 3,
                "days_left": days,
                "expiry_date": exp,
                "headline": f"已叠满约 {days} 天（至 {exp}）！仅剩最后一步关闭自动续费",
                "warning": "",
                "recommended_preset": "cancel",
                "recommended_label": "一键取消自动续费（保留全部免费天数）",
                "steps": [
                    {"step": 1, "name": "12月首开", "state": "done"},
                    {"step": 2, "name": "+6月(18m)", "state": "done"},
                    {"step": 3, "name": "+6月(24m)", "state": "done"},
                    {"step": 4, "name": "关续费锁死", "state": "current"},
                ],
            }
        return {
            "stage": 4,
            "days_left": days,
            "expiry_date": exp,
            "headline": f"🎉 完美毕业！已锁定 {days} 天免费权益（至 {exp}）且已关闭续费",
            "warning": "",
            "recommended_preset": "",
            "recommended_label": "全部完成",
            "steps": [
                {"step": 1, "name": "12月首开", "state": "done"},
                {"step": 2, "name": "+6月(18m)", "state": "done"},
                {"step": 3, "name": "+6月(24m)", "state": "done"},
                {"step": 4, "name": "关续费锁死", "state": "done"},
            ],
        }

    if not renew:
        return {
            "stage": 1 if days < 430 else 2,
            "days_left": days,
            "expiry_date": exp,
            "headline": f"当前剩余 {days} 天（至 {exp}），但已提前关闭自动续费",
            "warning": "Google Play 规定「已取消续费」的订阅不走折算顺延！若想继续叠加 +6 个月，请先在 Play 订阅页点「重新订阅」恢复续费开关。",
            "recommended_preset": "",
            "recommended_label": "",
            "steps": [
                {"step": 1, "name": "12月首开", "state": "done"},
                {"step": 2, "name": "+6月(18m)", "state": "done" if days >= 430 else "current"},
                {"step": 3, "name": "+6月(24m)", "state": "current" if days >= 430 else "todo"},
                {"step": 4, "name": "关续费锁死", "state": "todo"},
            ],
        }

    if days < 430:
        next_preset = "stack1"
        if avail_offer_ids and "6months-eft" not in avail_offer_ids:
            next_preset = "stack2" if "6months-eft-2" in avail_offer_ids else "pro6c"
        return {
            "stage": 1,
            "days_left": days,
            "expiry_date": exp,
            "headline": f"第 1 步已完成（当前 {days} 天，至 {exp}）· 推荐继续叠加第 2 步 (+6个月)",
            "warning": "",
            "recommended_preset": next_preset,
            "recommended_label": "执行第 2 步：免费叠加 +6 个月 (→18个月)",
            "steps": [
                {"step": 1, "name": "12月首开", "state": "done"},
                {"step": 2, "name": "+6月(18m)", "state": "current"},
                {"step": 3, "name": "+6月(24m)", "state": "todo"},
                {"step": 4, "name": "关续费锁死", "state": "todo"},
            ],
        }

    next_preset = "stack2"
    if avail_offer_ids and "6months-eft-2" not in avail_offer_ids and "6months-eft-ss-2026" in avail_offer_ids:
        next_preset = "pro6c"
    return {
        "stage": 2,
        "days_left": days,
        "expiry_date": exp,
        "headline": f"第 2 步已完成（当前 {days} 天，至 {exp}）· 推荐冲刺第 3 步 (+6个月→24个月)",
        "warning": "",
        "recommended_preset": next_preset,
        "recommended_label": "执行第 3 步：免费叠加 +6 个月 (→24个月)",
        "steps": [
            {"step": 1, "name": "12月首开", "state": "done"},
            {"step": 2, "name": "+6月(18m)", "state": "done"},
            {"step": 3, "name": "+6月(24m)", "state": "current"},
            {"step": 4, "name": "关续费锁死", "state": "todo"},
        ],
    }


def patch_frida_js(
    mode: str = "interactive",
    target_product: str = "auto",
    prefer_duration: str = "longest",
    selected_index: int = -1,
    target_sku: str = "",
    target_offer_id: str = "",
    stack_enabled: bool = False,
    old_token: str = "",
    extra_skus: Optional[List[str]] = None,
) -> str:
    src = FRIDA_JS_LOCAL.read_text(encoding="utf-8")
    replacements = {
        "MODE": json.dumps(mode),
        "TARGET_PRODUCT": json.dumps(target_product),
        "PREFER_DURATION": json.dumps(prefer_duration),
        "SELECTED_OFFER_INDEX": str(int(selected_index)),
        "TARGET_SKU": json.dumps(target_sku),
        "TARGET_OFFER_ID": json.dumps(target_offer_id),
        "STACK_ENABLED": "true" if stack_enabled else "false",
        "OLD_PURCHASE_TOKEN": json.dumps(old_token),
        "MODULE_APK": json.dumps(MODULE_REMOTE),
    }
    for var_name, js_val in replacements.items():
        src = re.sub(
            rf"^var {var_name}\s*=\s*.*;",
            lambda _m, k=var_name, v=js_val: f"var {k} = {v};",
            src,
            count=1,
            flags=re.M,
        )

    if extra_skus:
        for s in reversed(extra_skus):
            if s and s != "auto" and re.fullmatch(r"[A-Za-z0-9._-]+", s):
                src = src.replace("var PRODUCTS = [", f'var PRODUCTS = [\n            {json.dumps(s)},', 1)
    return src


class LiveBillingSession:
    """Persistent single-session Frida controller (`frida -q -t inf`) with real-time stdout streaming."""

    def __init__(self, dev: DeviceController, log_fn: Callable[[str], None] = print) -> None:
        self.dev = dev
        self.log = log_fn
        self.proc: Optional[subprocess.Popen[str]] = None
        self.tmp_js: Optional[Path] = None
        self.local_port: int = _pick_local_port(27043)
        self._msg_queue: "queue.Queue[str]" = queue.Queue()
        self.offers: List[Dict[str, Any]] = []
        self.missed_skus: List[str] = []
        self.queried_skus: Set[str] = set()
        self.scan_trace: List[str] = []
        self.last_event: str = ""
        self._event_history: List[str] = []
        self.last_purchases: List[Dict[str, Any]] = []
        self.sync_summary: Dict[str, int] = {"count": 0, "acked": 0}
        self._lock = threading.Lock()
        self._drain_lock = threading.Lock()
        self._op_lock = threading.RLock()
        self.attached_serial: str = ""
        self.attached_pid: int = 0
        self.stream_scan_output: bool = True
        atexit.register(self.close)

    def is_alive(self) -> bool:
        return (
            self.proc is not None
            and self.proc.poll() is None
            and self.attached_serial == self.dev.serial
        )

    def _write_ipc_cmd(self, cmd_line: str, timeout: int = 5) -> None:
        safe = re.sub(r"[\r\n']", "", cmd_line)
        # Dual-channel IPC write:
        # 1) External cache dir works as standard uid=2000(shell) without needing su/root
        try:
            self.dev.shell(
                f"mkdir -p '/sdcard/Android/data/{GOOGLE_ONE_PKG}/cache' 2>/dev/null; "
                f"printf '%s\\n' '{safe}' > '{EXT_CMD_FILE_REMOTE}' 2>/dev/null || true",
                timeout=timeout,
            )
        except Exception:
            pass
        # 2) App internal cache dir via root exec (/system/xbin/su / su / uid=0) with 0666 permissions
        if self.dev.adb and self.dev.serial:
            try:
                adb_root_exec(
                    self.dev.adb,
                    self.dev.serial,
                    f"mkdir -p '/data/data/{GOOGLE_ONE_PKG}/cache' && "
                    f"printf '%s\\n' '{safe}' > '{CMD_FILE_REMOTE}' && chmod 666 '{CMD_FILE_REMOTE}'",
                    timeout=timeout,
                )
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                try:
                    self._write_ipc_cmd("QUIT", timeout=3)
                    time.sleep(0.15)
                except Exception:
                    pass
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=2)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self.proc = None
            self.attached_pid = 0
            if self.tmp_js and self.tmp_js.exists():
                self.tmp_js.unlink(missing_ok=True)
            self.tmp_js = None

    def _stdout_worker(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for raw_line in proc.stdout:
                ln = raw_line.strip()
                if ln:
                    self._msg_queue.put(ln)
        except Exception:
            pass

    def start_or_reuse(self, force_restart_app: bool = False, extra_skus: Optional[List[str]] = None) -> bool:
        with self._op_lock:
            return self._start_or_reuse_locked(force_restart_app=force_restart_app, extra_skus=extra_skus)

    def _start_or_reuse_locked(self, force_restart_app: bool = False, extra_skus: Optional[List[str]] = None) -> bool:
        clean_extra = [s for s in (extra_skus or []) if s and s != "auto" and re.fullmatch(r"[A-Za-z0-9._-]+", s)]
        needed_extra = [s for s in clean_extra if s not in self.queried_skus]
        if not force_restart_app and not needed_extra and self.is_alive() and self.offers:
            return True

        self.close()
        if not self.dev.connect_or_boot_device():
            self.log("[-] 未能连接模拟器")
            return False
        assert self.dev.adb and self.dev.frida_cli

        if not ensure_device_frida_and_module(
            self.dev.adb, self.dev.serial, self.dev.frida_cli, local_port=self.local_port, log_fn=self.log
        ):
            return False

        accts = self.dev.list_google_accounts()
        if not accts:
            self.log("[-] 当前模拟器未登录任何 Google 账号，请先登录账号（或使用批量流水线自动切号登录）")
            return False

        self.dev.ensure_vending_ready()
        pid = self.dev.ensure_google_one_pid(force_restart=force_restart_app)
        if not pid:
            self.log("[-] 无法启动 Google One 进程")
            return False

        js_code = patch_frida_js(mode="interactive", extra_skus=clean_extra or None)
        fd_tmp, tf_str = tempfile.mkstemp(prefix="gtool_live_", suffix=".js")
        os.close(fd_tmp)
        tf = Path(tf_str)
        tf.write_text(js_code, encoding="utf-8")
        self.tmp_js = tf

        # Clear stale queue & history under drain lock
        with self._drain_lock:
            while not self._msg_queue.empty():
                try:
                    self._msg_queue.get_nowait()
                except queue.Empty:
                    break
            self.offers = []
            self.missed_skus = []
            self.queried_skus = set(STANDARD_SKUS) | set(clean_extra)
            self.scan_trace = []
            self.last_event = ""
            self._event_history = []
            start_cursor = 0

        t0 = time.time()
        self.log(f"[*] 正在注入常驻计费引擎 → Google One (PID {pid})...")
        # CRITICAL: `-q -t inf` runs Frida in non-REPL quiet daemon mode so stdin EOF never exits!
        self.proc = subprocess.Popen(
            [
                self.dev.frida_cli,
                "-q",
                "-t",
                "inf",
                "-H",
                f"127.0.0.1:{self.local_port}",
                "-p",
                str(pid),
                "-l",
                str(tf),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=WIN_NO_WINDOW,
        )
        self.attached_serial = self.dev.serial
        self.attached_pid = pid
        threading.Thread(target=self._stdout_worker, args=(self.proc,), daemon=True).start()

        if not self._wait_for(("INTERACTIVE_READY",), timeout=22.0, start_cursor=start_cursor):
            if not force_restart_app:
                self.log("[!] 首次会话初始化未响应，正在冷重启 Google One 并重试...")
                return self._start_or_reuse_locked(force_restart_app=True, extra_skus=clean_extra or None)
            self.close()
            return False

        elapsed = time.time() - t0
        trials_n = sum(1 for o in self.offers if o["type"] == "TRIAL")
        self.log(f"[+] ✓ 扫描完成 ({elapsed:.2f}s)：共发现 {len(self.offers)} 个可用方案（其中 {trials_n} 个 $0 免费试用）")
        return True

    def _emit_trace(self, line: str) -> None:
        self.scan_trace.append(line)
        if self.stream_scan_output:
            self.log(line)

    def drain_events(self) -> List[str]:
        with self._drain_lock:
            events = self._drain_events_unlocked()
            if events:
                self._event_history.extend(events)
            return events

    def _drain_events_unlocked(self) -> List[str]:
        events: List[str] = []
        while True:
            try:
                raw_line = self._msg_queue.get_nowait()
            except queue.Empty:
                break

            if not raw_line.startswith("[AT] "):
                # Raw Frida error / attach diagnostic line!
                if any(k in raw_line.lower() for k in ("error", "failed", "unable", "exception", "terminated")):
                    self.log(f"[-] Frida 诊断: {raw_line}")
                continue

            msg = raw_line[5:].strip()
            if not msg:
                continue

            if msg.startswith("DEX_LOADED"):
                self._emit_trace("[*] ✓ BillingClient 模块已挂载，正在握手 Google Play 服务...")
            elif msg == "BillingClient connected":
                self._emit_trace("[+] ✓ Google Play 计费服务握手成功！")
            elif msg.startswith("SCAN_START|"):
                sp = msg.split("|")
                cnt = sp[1] if len(sp) > 1 else "20"
                waves_n = sp[2] if len(sp) > 2 else "4"
                self._emit_trace(f"[*] ⚡ 启动动态 SKU 扫描：共 {cnt} 个目标商品（分 {waves_n} 波实时探测）...")
            elif msg.startswith("WAVE_START|"):
                # WAVE_START|waveNum|waveTotal|label|count
                sp = msg.split("|")
                if len(sp) >= 5:
                    self._emit_trace(f"[*] ── [第 {sp[1]}/{sp[2]} 波] {sp[3]} ({sp[4]} 个 SKU) ──")
            elif msg.startswith("SCAN_HIT|"):
                # SCAN_HIT|seqIdx|totalSkus|pid|pname|oCount|briefSummary
                sp = msg.split("|")
                if len(sp) >= 6:
                    seq_s = f"{int(sp[1]):02d}/{int(sp[2]):02d}" if sp[1].isdigit() and sp[2].isdigit() else f"{sp[1]}/{sp[2]}"
                    brief = f" [{sp[6]}]" if len(sp) > 6 and sp[6] else ""
                    self._emit_trace(f"[+]   [{seq_s}] ✓ 命中 {sp[3]} ({sp[4]}) → {sp[5]} 个方案{brief}")
                elif len(sp) >= 4:
                    self._emit_trace(f"[+]   ✓ 命中 {sp[1]} ({sp[2]}) → {sp[3]} 个方案")
            elif msg.startswith("SKU_MISS|"):
                # SKU_MISS|seqIdx|totalSkus|pid|pname
                sp = msg.split("|")
                if len(sp) >= 5:
                    seq_s = f"{int(sp[1]):02d}/{int(sp[2]):02d}" if sp[1].isdigit() and sp[2].isdigit() else f"{sp[1]}/{sp[2]}"
                    self._emit_trace(f"[*]   [{seq_s}] · 未开放 {sp[3]} ({sp[4]})")
            elif re.match(r"^\[\d+\]\s+Phase\d+:", msg):
                # Store detailed PricingPhase breakdown in scan_trace (viewable via [L]) without flooding 30-row screen
                self.scan_trace.append(f"          {msg}")
            elif msg.startswith("SCAN_MISS|"):
                sp = msg.split("|")
                if len(sp) >= 3:
                    self.missed_skus = [x for x in sp[2].split(",") if x]
            elif msg.startswith("SCAN_SUMMARY|"):
                # SCAN_SUMMARY|queried=20|products=X|offers=Y|trials=Z
                kv = dict(item.split("=", 1) for item in msg.split("|")[1:] if "=" in item)
                self._emit_trace(
                    f"[+] ═══ 动态探测汇总：共扫 {kv.get('queried', '?')} 个 SKU · "
                    f"命中 {kv.get('products', '0')} 个商品 · "
                    f"解析 {kv.get('offers', '0')} 个方案 (★ $0 免费试用 {kv.get('trials', '0')} 个) ═══"
                )
            elif msg.startswith("BROWSE_BEGIN"):
                self.offers = []
            elif msg.startswith("OFFER_ITEM|"):
                parts = msg.split("|")
                if len(parts) >= 9:
                    raw = {
                        "index": int(parts[1]) if parts[1].isdigit() else len(self.offers),
                        "product": parts[2],
                        "name": parts[3],
                        "offer_id": parts[4],
                        "price": parts[5],
                        "period": parts[6],
                        "type": parts[7],
                        "trial_period": parts[8],
                        "renew_price": parts[9] if len(parts) > 9 else "",
                        "intro_cycles": parts[10] if len(parts) > 10 else "0",
                    }
                    self.offers.append(format_offer_item(raw))
            elif msg.startswith("CMD_RECV "):
                events.append("CMD_RECV")
            elif msg.startswith("=== INTERACTIVE_READY"):
                self.last_event = "INTERACTIVE_READY"
                events.append("INTERACTIVE_READY")
            elif msg.startswith("BILLING_FLOW_LAUNCHED"):
                if "code=0" in msg:
                    self.last_event = "BILLING_FLOW_LAUNCHED"
                    events.append("BILLING_FLOW_LAUNCHED")
                else:
                    self.last_event = f"LAUNCH_FAILED:{msg}"
                    events.append(self.last_event)
            elif msg.startswith("PURCHASE_RECORD|"):
                p = msg.split("|")
                if len(p) >= 7:
                    self.last_purchases.append(
                        {
                            "order_id": p[1],
                            "products": p[2],
                            "state": p[3],
                            "acknowledged": p[4] == "true",
                            "auto_renewing": p[5] == "true",
                            "token_head": p[6],
                        }
                    )
            elif msg.startswith("=== PURCHASES_SYNC_DONE"):
                mc = re.search(r"count=(\d+)", msg)
                ma = re.search(r"acked=(\d+)", msg)
                self.sync_summary = {
                    "count": int(mc.group(1)) if mc else 0,
                    "acked": int(ma.group(1)) if ma else 0,
                }
                self.last_event = "PURCHASES_SYNC_DONE"
                events.append("PURCHASES_SYNC_DONE")
            elif msg.startswith("WARN_STACK_CANCELLED"):
                self.log("[!] ⚠️ 检测到旧订阅已关闭自动续费！Google Play 对已取消续费的订阅可能不走折算顺延，请先在订阅页点「重新订阅」恢复续费开关。")
            elif msg.startswith("=== PURCHASE_ACKNOWLEDGED"):
                self.log(f"[+] 已自动执行 Play 订单确认 (Acknowledge): {msg}")
            elif msg == "=== TRIAL_ACTIVATED ===":
                self.last_event = "TRIAL_ACTIVATED"
                events.append("TRIAL_ACTIVATED")
                self.log("[+] 🎉 收到订阅激活成功回调！")
            elif msg == "=== PURCHASE_PENDING ===":
                self.last_event = "PURCHASE_PENDING"
                events.append("PURCHASE_PENDING")
            elif msg == "=== USER_CANCELLED ===":
                self.last_event = "USER_CANCELLED"
                events.append("USER_CANCELLED")
            elif msg == "=== ITEM_ALREADY_OWNED ===":
                self.last_event = "ITEM_ALREADY_OWNED"
                events.append("ITEM_ALREADY_OWNED")
            elif any(
                msg.startswith(err_tag)
                for err_tag in (
                    "=== PROMO_INELIGIBLE",
                    "=== SKU_NOT_FOUND",
                    "=== SELECT_FAILED",
                    "=== NO_ACTIVITY",
                    "=== CONNECT_FAILED",
                    "=== QUERY_FAILED",
                    "=== STACK_NO_ACTIVE_SUB",
                    "=== STACK_QUERY_ERROR",
                    "=== LAUNCH_ERROR",
                    "=== PURCHASE_FAILED",
                )
            ):
                self.last_event = msg
                events.append(msg)
                self.log(f"[-] {msg}")
        return events

    def _wait_for(self, target_prefixes: Tuple[str, ...], timeout: float = 15.0, start_cursor: Optional[int] = None) -> bool:
        with self._drain_lock:
            idx = len(self._event_history) if start_cursor is None else start_cursor
        end_t = time.time() + timeout
        while time.time() < end_t:
            self.drain_events()
            with self._drain_lock:
                while idx < len(self._event_history):
                    ev = self._event_history[idx]
                    idx += 1
                    if any(ev.startswith(tp) for tp in target_prefixes):
                        return True
                    if any(
                        bad in ev
                        for bad in (
                            "PROMO_INELIGIBLE",
                            "LAUNCH_FAILED",
                            "SELECT_FAILED",
                            "CONNECT_FAILED",
                            "QUERY_FAILED",
                            "LAUNCH_ERROR",
                            "STACK_QUERY_ERROR",
                            "SKU_NOT_FOUND",
                            "NO_ACTIVITY",
                            "NO_ACTIVE_SUB",
                        )
                    ):
                        return False
            if self.proc is not None and self.proc.poll() is not None:
                self.drain_events()
                with self._drain_lock:
                    while idx < len(self._event_history):
                        ev = self._event_history[idx]
                        idx += 1
                        if any(ev.startswith(tp) for tp in target_prefixes):
                            return True
                return False
            time.sleep(0.08)
        return False

    def _direct_oneshot_launch(self, cmd_line: str) -> Tuple[bool, str]:
        """Zero-file-IPC direct one-shot fallback when persistent background poller is frozen or unreachable."""
        parts = cmd_line.split("|")
        op = parts[0]
        sku = parts[1] if len(parts) > 1 else ""
        oid = parts[2] if len(parts) > 2 else ""
        old_tok = parts[3] if len(parts) > 3 else ""

        self.close()
        if not self.dev.adb or not self.dev.frida_cli:
            return False, "ENGINE_NOT_READY"
        adb_run(self.dev.adb, self.dev.serial, "forward", f"tcp:{self.local_port}", "tcp:27042", timeout=6)
        pid = self.dev.ensure_google_one_pid(force_restart=False)
        if pid <= 0:
            pid = self.dev.ensure_google_one_pid(force_restart=True)
        if pid <= 0:
            return False, "NO_ACTIVITY"

        use_stack = op == "STACK_OFFER"
        if op == "LAUNCH_OFFER":
            js_code = patch_frida_js(
                mode="launch_offer",
                target_product=sku,
                target_sku=sku,
                target_offer_id=oid,
                stack_enabled=False,
                extra_skus=[sku] if sku else None,
            )
        else:
            js_code = patch_frida_js(
                mode="launch_sku",
                target_product=sku,
                target_sku=sku,
                target_offer_id=oid,
                stack_enabled=use_stack,
                old_token=old_tok,
                extra_skus=[sku] if sku else None,
            )

        fd_tmp, tf_str = tempfile.mkstemp(prefix="gtool_direct_", suffix=".js")
        os.close(fd_tmp)
        tf = Path(tf_str)
        tf.write_text(js_code, encoding="utf-8")

        p = subprocess.Popen(
            [
                self.dev.frida_cli,
                "-q",
                "-t",
                "16",
                "-H",
                f"127.0.0.1:{self.local_port}",
                "-p",
                str(pid),
                "-l",
                str(tf),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=WIN_NO_WINDOW,
        )
        q: "queue.Queue[str]" = queue.Queue()
        threading.Thread(
            target=lambda: [q.put(ln.strip()) for ln in (p.stdout or []) if ln.strip()],
            daemon=True,
        ).start()

        final_ev = "TIMEOUT"
        ok = False
        deadline = time.time() + 14.0
        try:
            while time.time() < deadline:
                try:
                    ln = q.get(timeout=0.1)
                except queue.Empty:
                    if p.poll() is not None:
                        break
                    continue
                if not ln.startswith("[AT] "):
                    continue
                msg = ln[5:].strip()
                if msg.startswith("BILLING_FLOW_LAUNCHED"):
                    if "code=0" in msg:
                        ok = True
                        final_ev = "BILLING_FLOW_LAUNCHED"
                    else:
                        final_ev = f"LAUNCH_FAILED:{msg}"
                    break
                if msg == "=== TRIAL_ACTIVATED ===":
                    ok = True
                    final_ev = "TRIAL_ACTIVATED"
                    break
                if any(
                    msg.startswith(t)
                    for t in (
                        "=== PROMO_INELIGIBLE",
                        "=== SKU_NOT_FOUND",
                        "=== SELECT_FAILED",
                        "=== NO_ACTIVITY",
                        "=== CONNECT_FAILED",
                        "=== STACK_NO_ACTIVE_SUB",
                        "=== LAUNCH_ERROR",
                    )
                ):
                    final_ev = msg
                    break
        finally:
            try:
                p.terminate()
                p.wait(timeout=1.5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            tf.unlink(missing_ok=True)
        return ok, final_ev

    def send_command(self, cmd_line: str, wait_prefixes: Tuple[str, ...], timeout: float = 12.0) -> Tuple[bool, str]:
        with self._op_lock:
            is_launch_op = cmd_line.startswith(("LAUNCH_", "STACK_"))
            if is_launch_op:
                live_pid = self.dev.bring_google_one_foreground()
            else:
                live_pid = self.dev.current_google_one_pid()

            if not self.is_alive() or live_pid <= 0 or (self.attached_pid and live_pid != self.attached_pid):
                if self.attached_pid and live_pid > 0 and live_pid != self.attached_pid:
                    self.log(f"[*] 检测到 Google One 进程已重开 (PID {self.attached_pid} → {live_pid})，自动重连会话...")
                if not self.start_or_reuse(force_restart_app=False):
                    if is_launch_op:
                        self.log("[!] 常驻会话重连受阻，自动切换零文件直连通道拉起...")
                        return self._direct_oneshot_launch(cmd_line)
                    return False, "SESSION_START_FAILED"

            if self.dev.adb and self.dev.serial:
                adb_run(self.dev.adb, self.dev.serial, "forward", f"tcp:{self.local_port}", "tcp:27042", timeout=5)

            if cmd_line == "REFRESH":
                self.scan_trace = []

            self.drain_events()
            with self._drain_lock:
                cursor = len(self._event_history)
                self.last_event = ""

            self._write_ipc_cmd(cmd_line, timeout=5)

            # Fast-ack phase (2.2s): verify the resident poller received CMD_RECV (or already finished!)
            ack_targets = ("CMD_RECV",) + tuple(wait_prefixes)
            got_ack = self._wait_for(ack_targets, timeout=min(2.2, timeout), start_cursor=cursor)
            if not got_ack:
                if self.last_event and any(
                    k in self.last_event
                    for k in ("PROMO_INELIGIBLE", "SELECT_FAILED", "SKU_NOT_FOUND", "NO_ACTIVE_SUB", "LAUNCH_FAILED", "LAUNCH_ERROR")
                ):
                    return False, self.last_event
                if is_launch_op:
                    self.log("[!] 常驻轮询通道响应超时 (可能受后台冻结或目录权限隔离影响)，自动切换零 IPC 直连极速拉起...")
                    return self._direct_oneshot_launch(cmd_line)
                if cmd_line == "REFRESH":
                    self.log("[*] 常驻会话已休眠，正在重新连接刷新...")
                    ok_re = self.start_or_reuse(force_restart_app=True)
                    return ok_re, ("INTERACTIVE_READY" if ok_re else "TIMEOUT")
                return False, "TIMEOUT"

            # Check if wait_prefixes was already satisfied during the fast-ack window
            with self._drain_lock:
                for ev in self._event_history[cursor:]:
                    if any(ev.startswith(tp) for tp in wait_prefixes):
                        return True, self.last_event or ev

            rem = max(3.0, timeout - 2.2)
            ok = self._wait_for(wait_prefixes, timeout=rem, start_cursor=cursor)
            if not ok and not self.last_event and is_launch_op:
                self.log("[!] 首次拉起未返回回执，自动执行直连重试...")
                return self._direct_oneshot_launch(cmd_line)
            return ok, self.last_event or ("OK" if ok else "TIMEOUT")

    def launch_preset_or_sku(
        self,
        sku: str,
        offer_id: str = "",
        stack: bool = False,
    ) -> Tuple[bool, str]:
        if sku and sku != "auto" and not re.fullmatch(r"[A-Za-z0-9._-]+", sku):
            self.log(f"[-] 非法商品 SKU 格式: {sku}")
            return False, "INVALID_SKU"
        if offer_id and not re.fullmatch(r"[A-Za-z0-9._-]+", offer_id):
            self.log(f"[-] 非法 Offer ID 格式: {offer_id}")
            return False, "INVALID_OFFER_ID"
        extra = [sku] if (sku and sku != "auto" and sku not in STANDARD_SKUS) else None
        if not self.start_or_reuse(extra_skus=extra):
            if sku and sku != "auto":
                return self._direct_oneshot_launch(
                    f"STACK_OFFER|{sku}|{offer_id}||5"
                    if stack
                    else (f"LAUNCH_SKU|{sku}|__PROMO__" if offer_id == "__PROMO__" else (f"LAUNCH_OFFER|{sku}|{offer_id}" if offer_id else f"LAUNCH_SKU|{sku}|"))
                )
            return False, "ENGINE_NOT_READY"

        t0 = time.time()
        if stack:
            old_tok = self.dev.best_stack_token("subs_variant") or self.dev.best_stack_token("g1.")
            if old_tok:
                self.log(f"[+] 已读取活跃订阅 token ({old_tok[:16]}...)，执行折算顺延叠加...")
            cmd = f"STACK_OFFER|{sku}|{offer_id}|{old_tok}|5"
        elif sku == "auto":
            trials = [o for o in self.offers if o["type"] == "TRIAL"]
            if not trials:
                return False, "NO_TRIALS_AVAILABLE"
            best = max(trials, key=lambda o: _parse_iso_months(o.get("trial_period", "")))
            cmd = f"LAUNCH_OFFER|{best['product']}|{best['offer_id']}"
        elif offer_id == "__PROMO__":
            cmd = f"LAUNCH_SKU|{sku}|__PROMO__"
        elif offer_id:
            cmd = f"LAUNCH_OFFER|{sku}|{offer_id}"
        else:
            cmd = f"LAUNCH_SKU|{sku}|"

        ok, ev = self.send_command(cmd, ("BILLING_FLOW_LAUNCHED", "TRIAL_ACTIVATED"), timeout=12.0)
        dt = time.time() - t0
        if ok:
            self.log(f"[+] ⚡ 收银台已在模拟器弹出 ({dt:.2f}s)")
        return ok, ev

    def sync_and_acknowledge(self) -> Dict[str, Any]:
        if not self.start_or_reuse():
            return {"ok": False, "count": 0, "acked": 0, "purchases": []}
        self.last_purchases = []
        self.sync_summary = {"count": 0, "acked": 0}
        ok, _ = self.send_command("QUERY_PURCHASES", ("PURCHASES_SYNC_DONE",), timeout=15.0)
        if self.sync_summary["count"] > 0:
            self.log("[*] 正在重启刷新 Google One 以立即同步新订阅空间与 AI 权益...")
            self.close()
            self.dev.shell(f"am force-stop {GOOGLE_ONE_PKG}")
            time.sleep(0.4)
            self.dev.shell(f"monkey -p {GOOGLE_ONE_PKG} 1 >/dev/null 2>&1")
            time.sleep(1.2)
        return {
            "ok": ok,
            "count": self.sync_summary["count"],
            "acked": self.sync_summary["acked"],
            "purchases": list(self.last_purchases),
            "db_subscriptions": self.dev.read_play_subscriptions(),
        }
