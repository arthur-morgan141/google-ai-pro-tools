#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/batch_runner.py — Universal account/card parser & multi-account batch pipeline."""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .billing_engine import LiveBillingSession
from .device_ops import DeviceController
from .platform_env import PROJECT_DIR, notify_user


def normalize_user_path(raw: str) -> str:
    s = (raw or "").strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    else:
        # Unescape macOS Finder drag-and-drop backslashes (WITHOUT touching Windows C:\ paths!)
        if not re.match(r"^[A-Za-z]:\\", s):
            for esc, plain in ((r"\ ", " "), (r"\(", "("), (r"\)", ")"), (r"\[", "["), (r"\]", "]"), (r"\&", "&")):
                s = s.replace(esc, plain)
    if s.startswith("~/") or s.startswith("~\\"):
        s = str(Path.home() / s[2:])
    return s


def discover_candidate_files() -> List[Path]:
    dirs = [
        PROJECT_DIR,
        PROJECT_DIR.parent,
        PROJECT_DIR.parent / "03-测试样例与历史归档",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ]
    skip_prefixes = ("results_", "readme", "requirements", "使用说明")
    out: List[Path] = []
    seen: Set[Path] = set()
    for d in dirs:
        if not d.exists():
            continue
        for ext in ("*.txt", "*.csv"):
            for f in sorted(d.glob(ext), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
                if f.name.lower().startswith(skip_prefixes):
                    continue
                rp = f.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(f)
                if len(out) >= 12:
                    return out
    return out


def normalize_card_expiry(raw_exp: str) -> str:
    """Normalize expiry variants ('6/29', '0629', '06/2029', '2029-06', '062029') into 'MM/YY'."""
    s = (raw_exp or "").strip().replace("-", "/").replace(".", "/")
    m = re.match(r"^20(\d{2})/(\d{1,2})$", s)
    if m:
        yy, mm = m.group(1), int(m.group(2))
        return f"{mm:02d}/{yy}" if 1 <= mm <= 12 else ""
    m = re.match(r"^(\d{1,2})/(?:20)?(\d{2})$", s)
    if m:
        mm, yy = int(m.group(1)), m.group(2)
        return f"{mm:02d}/{yy}" if 1 <= mm <= 12 else ""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 4:
        mm, yy = int(digits[:2]), digits[2:]
        return f"{mm:02d}/{yy}" if 1 <= mm <= 12 else ""
    if len(digits) == 6 and digits[2:4] == "20":
        mm, yy = int(digits[:2]), digits[4:]
        return f"{mm:02d}/{yy}" if 1 <= mm <= 12 else ""
    if len(digits) == 6 and digits[:2] == "20":
        yy, mm = digits[2:4], int(digits[4:])
        return f"{mm:02d}/{yy}" if 1 <= mm <= 12 else ""
    return ""


def _looks_like_totp(val: str) -> bool:
    cleaned = re.sub(r"[\s-]", "", val or "")
    return len(cleaned) >= 12 and bool(re.fullmatch(r"[A-Za-z2-7]+=*", cleaned))


def parse_accounts_text(text: str) -> List[Dict[str, Any]]:
    accounts: List[Dict[str, Any]] = []
    for idx, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if idx == 1 and re.match(r"^(email|account|user|邮箱|账号)\s*[,|\t:-]", line, re.I):
            continue

        if "----" in line:
            parts = [p.strip() for p in line.split("----")]
        elif "|" in line:
            parts = [p.strip() for p in line.split("|")]
        elif "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif "," in line and "@" in line.split(",", 1)[0] and " " not in line.split(",", 1)[0].strip():
            parts = [p.strip() for p in next(csv.reader(io.StringIO(line)))]
        elif ":" in line and "@" in line.split(":", 1)[0] and " " not in line.split(":", 1)[0].strip():
            raw_cols = [p.strip() for p in line.split(":")]
            # Protect passwords containing ':' (e.g. user@gmail.com:MyPass:123!)
            if len(raw_cols) >= 3 and not ("@" in raw_cols[-1] or _looks_like_totp(raw_cols[-1])):
                parts = [raw_cols[0], ":".join(raw_cols[1:])]
            elif len(raw_cols) >= 4 and ("@" in raw_cols[-1] or _looks_like_totp(raw_cols[-1])) and not ("@" in raw_cols[-2] or _looks_like_totp(raw_cols[-2])):
                parts = [raw_cols[0], ":".join(raw_cols[1:-1]), raw_cols[-1]]
            else:
                parts = raw_cols
        else:
            ws_parts = line.split()
            # Rejoin Google Authenticator 4-char space-separated Base32 groups: "email pass JBSW Y3DP EHPK 3PXP"
            if len(ws_parts) > 3 and all(re.fullmatch(r"[A-Za-z2-7]{4}", tok) for tok in ws_parts[2:]):
                parts = [ws_parts[0], ws_parts[1], "".join(ws_parts[2:])]
            else:
                parts = ws_parts

        if len(parts) < 2:
            continue
        email, password = parts[0], parts[1]
        if "@" not in email or not password:
            continue

        totp = ""
        recovery = ""
        card: Optional[Dict[str, str]] = None

        if len(parts) == 3:
            if "@" in parts[2]:
                recovery = parts[2]
            else:
                totp = parts[2]
        elif len(parts) >= 4:
            if "@" in parts[2] and "@" not in parts[3]:
                recovery, totp = parts[2], parts[3]
            else:
                totp, recovery = parts[2], parts[3]

            if len(parts) >= 7:
                c_num = re.sub(r"\D", "", parts[4])
                c_exp = normalize_card_expiry(parts[5])
                c_cvv = re.sub(r"\D", "", parts[6])
                if 13 <= len(c_num) <= 19 and c_exp and 3 <= len(c_cvv) <= 4:
                    card = {"number": c_num, "expiry": c_exp, "cvv": c_cvv}

        if totp:
            totp = re.sub(r"[\s-]+", "", totp).upper()

        accounts.append(
            {
                "email": email,
                "password": password,
                "totp": totp,
                "recovery": recovery,
                "card": card,
            }
        )
    return accounts


def parse_cards_text(text: str) -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    for idx, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if idx == 1 and re.match(r"^(card|number|pan|卡号)", line, re.I):
            continue

        m_sp = re.match(r"^(\d{13,19})\s+([0-9/\-.]{3,7})\s+(\d{3,4})$", line)
        if m_sp:
            num, exp_raw, cvv = m_sp.group(1), m_sp.group(2), m_sp.group(3)
        else:
            clean = line.replace(" ", "")
            if "|" in clean:
                segs = clean.split("|")
            elif "," in clean:
                segs = clean.split(",")
            elif "----" in clean:
                segs = clean.split("----")
            else:
                segs = clean.split("-")
                if len(segs) > 3:
                    segs = ["".join(segs[:-2]), segs[-2], segs[-1]]
            if len(segs) < 3:
                continue
            num, exp_raw, cvv = segs[0], segs[1], segs[2]

        num = re.sub(r"\D", "", num)
        exp = normalize_card_expiry(exp_raw)
        cvv = re.sub(r"\D", "", cvv)

        if 13 <= len(num) <= 19 and exp and 3 <= len(cvv) <= 4:
            cards.append({"number": num, "expiry": exp, "cvv": cvv})
    return cards


def load_completed_emails(resume_log: Optional[Path]) -> Set[str]:
    done: Set[str] = set()
    if not resume_log or not resume_log.exists():
        return done
    for line in resume_log.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("OK "):
            parts = line.split()
            if len(parts) >= 2:
                done.add(parts[1].lower())
    return done


class BatchJobRunner:
    """Thread-safe batch pipeline runner usable by both Console TUI and Web Console."""

    def __init__(
        self,
        dev: DeviceController,
        prefs: Dict[str, Any],
        log_fn: Callable[[str], None] = print,
    ) -> None:
        self.dev = dev
        self.prefs = prefs
        self.log = log_fn
        self.running: bool = False
        self.stop_requested: bool = False
        self.total: int = 0
        self.current_index: int = 0
        self.current_email: str = ""
        self.results: List[Dict[str, Any]] = []
        self.results_log_path: str = ""
        self._thread: Optional[threading.Thread] = None

    def snapshot(self) -> Dict[str, Any]:
        ok_n = sum(1 for r in self.results if r["status"] == "OK")
        fail_n = sum(1 for r in self.results if r["status"] in ("FAIL", "INELIGIBLE"))
        skip_n = sum(1 for r in self.results if r["status"] in ("SKIP", "ALREADY_OWNED"))
        return {
            "running": self.running,
            "total": self.total,
            "current_index": self.current_index,
            "current_email": self.current_email,
            "ok": ok_n,
            "fail": fail_n,
            "skip": skip_n,
            "results": list(self.results),
            "results_log": self.results_log_path,
            "human_waiting": self.dev.human_gate.waiting,
            "human_message": self.dev.human_gate.message,
        }

    def request_stop(self) -> None:
        self.stop_requested = True
        if self.dev.human_gate.waiting:
            self.dev.human_gate.resolve("abort")

    def run_sync(
        self,
        accounts: List[Dict[str, Any]],
        cards: List[Dict[str, str]],
        sku: str,
        offer_id: str = "",
        stack: bool = False,
        is_paid: bool = False,
        plan_label: str = "",
        card_mode: str = "rotate",
        resume_emails: Optional[Set[str]] = None,
        start_from: int = 1,
        max_consecutive_fails: int = 5,
        cooldown: float = 2.0,
        human_cb: Optional[Callable[[str], Optional[str]]] = None,
    ) -> List[Dict[str, Any]]:
        self.running = True
        self.stop_requested = False
        self.total = len(accounts)
        self.current_index = 0
        self.results = []
        done_set = resume_emails or set()

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = PROJECT_DIR / f"results_{ts}.log"
        report_dir = PROJECT_DIR / "reports"
        report_dir.mkdir(exist_ok=True)
        self.results_log_path = str(log_file)
        log_file.write_text(f"# Batch started {ts} | plan={plan_label or sku}\n", encoding="utf-8")
        try:
            os.chmod(log_file, 0o600)
        except OSError:
            pass

        if not self.dev.connect_or_boot_device():
            self.log("[-] 批量启动失败：未连接到模拟器")
            self.running = False
            return []

        if self.prefs.get("fast_anim", True):
            self.dev.set_fast_animations(True)

        billing = LiveBillingSession(self.dev, log_fn=self.log)
        card_idx = 0
        consecutive_fails = 0

        try:
            for idx, acct in enumerate(accounts, 1):
                if self.stop_requested:
                    self.log("[!] 收到停止指令，批量流水线已安全中止")
                    break

                email = acct["email"]
                self.current_index = idx
                self.current_email = email
                t0 = time.time()

                if idx < max(1, start_from):
                    continue

                if email.lower() in done_set:
                    self.log(f"[*] [{idx}/{self.total}] 跳过已完成账号: {email}")
                    self.results.append({"email": email, "status": "SKIP", "detail": "resumed", "sec": 0})
                    continue

                if consecutive_fails >= max(1, max_consecutive_fails):
                    self.log(f"[-] 连续失败达 {consecutive_fails} 次，自动熔断中止以防触发 Google 风控！")
                    break

                card = acct.get("card") or (cards[card_idx] if cards else None)
                if not card:
                    self.log(f"[-] 跳过 {email}: 无可用卡片")
                    self.results.append({"email": email, "status": "SKIP", "detail": "no_card", "sec": 0})
                    continue

                self.log(f"\n━━━ [{idx}/{self.total}] {email} | 卡 ••••{card['number'][-4:]} | {plan_label or sku} ━━━")

                # 1. Account switch
                billing.close()
                cur_accts = self.dev.list_google_accounts()
                if len(cur_accts) == 1 and cur_accts[0].lower() == email.lower():
                    self.log(f"[+] 目标账号已在设备上: {email}")
                else:
                    if not self.dev.remove_all_accounts():
                        self._record(log_file, report_dir, email, "SKIP", "remove_account_failed", t0)
                        consecutive_fails += 1
                        continue
                    if not self.dev.add_google_account(
                        email, acct["password"], acct.get("totp", ""), acct.get("recovery", ""), human_cb=human_cb
                    ):
                        self._record(log_file, report_dir, email, "SKIP", "add_account_failed", t0)
                        consecutive_fails += 1
                        continue

                # 2. Card bind & Google One prep
                if not self.dev.bind_card_playstore(
                    card["number"], card["expiry"], card["cvv"], postal_mode=self.prefs.get("postal_mode", "classic")
                ):
                    self._record(log_file, report_dir, email, "SKIP", "card_bind_failed", t0)
                    consecutive_fails += 1
                    continue

                reset_mode = self.prefs.get("batch_reset", "smart")
                if not self.dev.prepare_google_one(email, mode=reset_mode):
                    self._record(log_file, report_dir, email, "SKIP", "app_prep_failed", t0)
                    consecutive_fails += 1
                    continue

                # 3. Launch Checkout via persistent Frida session (keeps listener alive!)
                if not billing.start_or_reuse(force_restart_app=True, extra_skus=[sku] if sku != "auto" else None):
                    self._record(log_file, report_dir, email, "FAIL", "frida_attach_failed", t0)
                    consecutive_fails += 1
                    continue

                launched, ev = billing.launch_preset_or_sku(sku, offer_id, stack=stack)
                if not launched and reset_mode == "smart":
                    self.log("[!] 极速模式下未读到方案，回退 Play 商店完整重装绑定重试...")
                    billing.close()
                    if self.dev.prepare_google_one(email, mode="reinstall") and billing.start_or_reuse(force_restart_app=True):
                        launched, ev = billing.launch_preset_or_sku(sku, offer_id, stack=stack)

                if not launched:
                    status_tag = "ALREADY_OWNED" if "ALREADY_OWNED" in ev else ("INELIGIBLE" if "NO_TRIALS" in ev else "FAIL")
                    self._record(log_file, report_dir, email, status_tag, ev, t0)
                    if status_tag == "FAIL":
                        consecutive_fails += 1
                    continue

                # 4. Confirm $0 sheet + password + post-payment + live Frida callback!
                ok_sheet, reason = self.dev.confirm_checkout_sheet(expect_free=(not is_paid), human_cb=human_cb)
                if not ok_sheet:
                    status_tag = "INELIGIBLE" if reason == "INELIGIBLE" else ("ALREADY_OWNED" if reason == "ITEM_ALREADY_OWNED" else "FAIL")
                    self._record(log_file, report_dir, email, status_tag, reason, t0)
                    billing.close()
                    continue

                def _check_live_act() -> bool:
                    billing.drain_events()
                    return billing.last_event == "TRIAL_ACTIVATED"

                self.dev.handle_billing_password(acct["password"], is_activated_fn=_check_live_act)
                self.dev.handle_post_payment(is_activated_fn=_check_live_act)

                # Drain live Frida events for up to 20s to catch TRIAL_ACTIVATED + automatic acknowledgePurchase!
                activated = False
                end_wait = time.time() + 20
                while time.time() < end_wait:
                    billing.drain_events()
                    if billing.last_event == "TRIAL_ACTIVATED":
                        activated = True
                        time.sleep(0.4)
                        billing.drain_events()
                        break
                    if billing.last_event in ("ITEM_ALREADY_OWNED", "USER_CANCELLED") or "PURCHASE_FAILED" in billing.last_event:
                        break
                    time.sleep(0.4)

                billing.close()

                if activated:
                    if self.prefs.get("auto_cancel", True) and not stack:
                        self.dev.cancel_subscription()
                    self._record(log_file, report_dir, email, "OK", plan_label or sku, t0)
                    consecutive_fails = 0
                    notify_user(self.prefs, "success", f"激活成功: {email}")
                else:
                    final_ev = billing.last_event or "CALLBACK_TIMEOUT"
                    self._record(log_file, report_dir, email, "FAIL", final_ev, t0)
                    consecutive_fails += 1

                if card_mode == "rotate" and cards and not acct.get("card"):
                    card_idx = (card_idx + 1) % len(cards)

                self.dev.press_key("KEYCODE_HOME")
                time.sleep(max(0.5, float(cooldown)))
        finally:
            billing.close()
            self.dev.set_fast_animations(False)
            self.running = False
            notify_user(self.prefs, "attention", "批量任务执行完毕")

        return self.results

    def start_async(self, **kwargs: Any) -> bool:
        if self.running:
            return False
        self._thread = threading.Thread(target=self.run_sync, kwargs=kwargs, daemon=True)
        self._thread.start()
        return True

    def _record(self, log_file: Path, report_dir: Path, email: str, status: str, detail: str, t0: float) -> None:
        sec = int(round(time.time() - t0))
        rec = {"email": email, "status": status, "detail": detail, "sec": sec, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.results.append(rec)
        with open(log_file, "a", encoding="utf-8") as fo:
            fo.write(f"{status} {email} {detail} ({sec}s)\n")
        safe_name = re.sub(r"[^A-Za-z0-9_.+-]", "_", email.split("@")[0])
        rep_file = report_dir / f"{safe_name}.json"
        rep_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(rep_file, 0o600)
        except OSError:
            pass
        tag = "[+]" if status == "OK" else ("[!]" if status in ("SKIP", "INELIGIBLE", "ALREADY_OWNED") else "[-]")
        self.log(f"{tag} 结果: {email} → {status} ({detail}, {sec}s)")
