#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/tui_app.py — Cross-platform (macOS / Windows) Arrow-Key Visual Console TUI."""

from __future__ import annotations

import os
import select
import sys
import time
import unicodedata
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .batch_runner import (
    BatchJobRunner,
    discover_candidate_files,
    load_completed_emails,
    normalize_user_path,
    parse_accounts_text,
    parse_cards_text,
)
from .billing_engine import (
    PRESETS,
    LiveBillingSession,
    analyze_pro_stacking_wizard,
    resolve_preset,
)
from .device_ops import DeviceController
from .i18n import (
    LANG_META,
    SUPPORTED_LANGS,
    TUI_STRINGS,
    active_motto_i18n,
    localize_offer,
    localize_presets,
    localize_wizard,
    normalize_lang,
    time_greeting_i18n,
)
from .platform_env import (
    BLOG_URL,
    FAKA_URL,
    IS_WIN,
    PROJECT_DIR,
    active_motto,
    load_prefs,
    notify_user,
    save_prefs,
    time_greeting,
)


# ---------- ANSI Styling ----------

class Style:
    ENABLED = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    RST = "\033[0m" if ENABLED else ""
    BLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""
    RED = "\033[38;5;203m" if ENABLED else ""
    GRN = "\033[38;5;84m" if ENABLED else ""
    YLW = "\033[38;5;221m" if ENABLED else ""
    BLU = "\033[38;5;75m" if ENABLED else ""
    CYN = "\033[38;5;87m" if ENABLED else ""
    MAG = "\033[38;5;177m" if ENABLED else ""
    GRY = "\033[38;5;244m" if ENABLED else ""
    SEL_BG = "\033[48;5;24;97;1m" if ENABLED else ""


def _char_width(ch: str) -> int:
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def disp_width(text: str) -> int:
    # Strip ANSI sequences before measuring display width
    clean = ""
    in_esc = False
    for ch in text:
        if ch == "\033":
            in_esc = True
            continue
        if in_esc:
            if ch.isalpha():
                in_esc = False
            continue
        clean += ch
    w = 0
    for ch in clean:
        w += _char_width(ch)
    return w


def pad_cjk(text: str, width: int) -> str:
    cur = disp_width(text)
    if cur > width:
        out = ""
        w = 0
        for ch in text:
            cw = _char_width(ch)
            if w + cw > max(1, width - 2):
                out += ".."
                w += 2
                break
            out += ch
            w += cw
        return out + " " * max(0, width - w)
    return text + " " * (width - cur)


def clear_screen() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# ---------- Cross-Platform Single-Key Reader (Windows msvcrt + Unix termios) ----------

def is_interactive_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


_PENDING_UNIX_BYTES = bytearray()


def _read_fd_byte(fd: int) -> bytes:
    if _PENDING_UNIX_BYTES:
        b = bytes([_PENDING_UNIX_BYTES[0]])
        del _PENDING_UNIX_BYTES[0]
        return b
    return os.read(fd, 1)


def read_key() -> str:
    """Read a single keystroke across Windows & macOS/Linux.
    Returns: 'UP', 'DOWN', 'LEFT', 'RIGHT', 'ENTER', 'ESC', 'TAB', 'BACKSPACE', or character string.
    """
    if not is_interactive_tty():
        line = sys.stdin.readline()
        if not line:
            return "q"
        s = line.strip()
        return "ENTER" if s == "" else s

    if IS_WIN:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            k2 = msvcrt.getwch()
            return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}.get(k2, "")
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\x1b":
            return "ESC"
        if ch == "\t":
            return "TAB"
        if ch == "\x08":
            return "BACKSPACE"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    else:
        import termios
        import tty
        sys.stdout.flush()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd, when=termios.TCSANOW)
            b1 = _read_fd_byte(fd)
            if not b1:
                return "q"
            if b1 == b"\x03":
                raise KeyboardInterrupt
            if b1 == b"\x04":
                return "q"
            if b1 in (b"\r", b"\n"):
                return "ENTER"
            if b1 == b"\t":
                return "TAB"
            if b1 in (b"\x7f", b"\x08"):
                return "BACKSPACE"
            if b1 == b"\x1b":
                if _PENDING_UNIX_BYTES or select.select([fd], [], [], 0.04)[0]:
                    b2 = _read_fd_byte(fd)
                    if b2 in (b"[", b"O"):
                        if _PENDING_UNIX_BYTES or select.select([fd], [], [], 0.04)[0]:
                            b3 = _read_fd_byte(fd)
                            return {b"A": "UP", b"B": "DOWN", b"C": "RIGHT", b"D": "LEFT"}.get(b3, "ESC")
                    else:
                        # Not an ANSI CSI/SS3 sequence — push byte back so next read_key() receives it!
                        _PENDING_UNIX_BYTES.insert(0, b2[0])
                return "ESC"
            buf = bytearray(b1)
            if b1[0] >= 0x80:
                for _ in range(3):
                    if not (_PENDING_UNIX_BYTES or select.select([fd], [], [], 0.01)[0]):
                        break
                    buf.extend(_read_fd_byte(fd))
            return bytes(buf).decode("utf-8", errors="ignore")
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)


def prompt_line(prompt_text: str, secret: bool = False) -> str:
    try:
        if secret and is_interactive_tty():
            import getpass
            return getpass.getpass(prompt_text)
        return input(prompt_text)
    except (EOFError, KeyboardInterrupt):
        return ""


# ---------- Reusable Arrow-Key Menu Selector ----------

def visual_menu_select(
    header_fn: Callable[[], None],
    items: List[Dict[str, Any]],
    footer_hint: str = "↑/↓ 移动光标  ·  Enter 确认  ·  数字/字母快捷键直达  ·  W 打开网页可视化面板  ·  Q 返回/退出",
    initial_idx: int = 0,
    allow_esc_quit: bool = True,
) -> str:
    """Render an interactive arrow-key menu in TTY mode, or clean numbered prompt in non-TTY mode."""
    if not items:
        return "q"

    if not is_interactive_tty():
        header_fn()
        for it in items:
            print(f"  [{it['key']}] {it['label']}  {Style.DIM}{it.get('sub', '')}{Style.RST}")
        ans = prompt_line("\n  请选择编号或快捷键: ").strip()
        return ans or items[0]["key"]

    sel = max(0, min(len(items) - 1, initial_idx))
    hotkey_map = {str(it["key"]).lower(): i for i, it in enumerate(items)}

    while True:
        clear_screen()
        header_fn()

        for i, it in enumerate(items):
            key_badge = f"[{it['key']}]"
            if i == sel:
                line_txt = f" ❯ {key_badge:<4} {it['label']}"
                print(f"  {Style.SEL_BG}{pad_cjk(line_txt, 72)}{Style.RST}")
            else:
                color = it.get("color", Style.CYN)
                sub = f"  {Style.DIM}{it['sub']}{Style.RST}" if it.get("sub") else ""
                print(f"    {color}{Style.BLD}{key_badge:<4}{Style.RST} {it['label']}{sub}")

        cur_desc = items[sel].get("desc") or items[sel].get("sub") or ""
        print("")
        print(f"  {Style.CYN}╭─ 📝 当前选中说明 ─────────────────────────────────────────────────────╮{Style.RST}")
        print(f"  {Style.CYN}│{Style.RST} {pad_cjk(cur_desc, 70)} {Style.CYN}│{Style.RST}")
        print(f"  {Style.CYN}╰────────────────────────────────────────────────────────────────────────╯{Style.RST}")
        print(f"  {Style.DIM}{footer_hint}{Style.RST}")

        k = read_key()
        kl = k.lower()
        if k == "UP" or kl == "k":
            sel = (sel - 1) % len(items)
        elif k == "DOWN" or kl == "j":
            sel = (sel + 1) % len(items)
        elif k == "ENTER":
            return str(items[sel]["key"])
        elif k in ("ESC", "BACKSPACE"):
            if allow_esc_quit:
                return "q"
        elif kl == "q":
            return "q"
        elif kl in ("w", "r", "d", "h", "b", "l"):
            if kl in hotkey_map:
                return str(items[hotkey_map[kl]]["key"])
            return kl
        elif kl in hotkey_map:
            return str(items[hotkey_map[kl]]["key"])


# ---------- Visual Console Application ----------

class ConsoleStudioApp:
    def __init__(self, launch_web_cb: Optional[Callable[[], None]] = None) -> None:
        self.prefs = load_prefs()
        self.dev = DeviceController(log_fn=self.log)
        self.billing = LiveBillingSession(self.dev, log_fn=self.log)
        self.launch_web_cb = launch_web_cb
        self.radar_cache: Optional[Dict[str, Any]] = None
        self.radar_ts: float = 0.0

    def log(self, msg: str) -> None:
        if msg.startswith("[+]"):
            print(f"{Style.GRN}{msg}{Style.RST}", flush=True)
        elif msg.startswith("[-]"):
            print(f"{Style.RED}{msg}{Style.RST}", flush=True)
        elif msg.startswith("[!]"):
            print(f"{Style.YLW}{msg}{Style.RST}", flush=True)
        else:
            print(f"{Style.BLU}{msg}{Style.RST}", flush=True)

    def human_console_prompt(self, msg: str) -> str:
        notify_user(self.prefs, "attention", msg)
        print(f"\n  {Style.YLW}{Style.BLD}⏸  需要人工协助：{msg}{Style.RST}")
        ans = prompt_line("  请在模拟器完成操作后按 [Enter] 继续（输入 s 跳过此账号，q 中止）: ").strip().lower()
        if ans == "s":
            return "skip"
        if ans == "q":
            return "abort"
        return "continue"

    def refresh_radar(self, force: bool = False) -> Dict[str, Any]:
        if force or self.radar_cache is None or (time.time() - self.radar_ts > 8.0):
            self.radar_cache = self.dev.probe_radar()
            self.radar_ts = time.time()
        return self.radar_cache

    def _lang(self) -> str:
        return normalize_lang(self.prefs.get("lang"))

    def _tr(self, key: str) -> str:
        lg = self._lang()
        return TUI_STRINGS.get(lg, TUI_STRINGS["en"]).get(key, TUI_STRINGS["en"].get(key, key))

    def _render_dashboard_header(self) -> None:
        rd = self.refresh_radar(force=False)
        lg = self._lang()
        greet = time_greeting_i18n(self.prefs.get("user_name", ""), lg)
        motto = active_motto_i18n(self.prefs, lg)
        lang_badge = LANG_META.get(lg, LANG_META["zh"])["label"]

        title_inner = pad_cjk(f"  🚀  {self._tr('banner_title')}", 72)
        blog_l = self._tr("ad_blog_lbl")
        faka_l = self._tr("ad_faka_lbl")
        ad_plain = f"📖 {blog_l}: {BLOG_URL}  🛒 {faka_l}: {FAKA_URL}"
        ad_pad = " " * max(0, 72 - disp_width(ad_plain))
        print(f"{Style.BLD}{Style.CYN}╔══════════════════════════════════════════════════════════════════════════╗{Style.RST}")
        print(f"{Style.BLD}{Style.CYN}║ {title_inner} ║{Style.RST}")
        print(f"{Style.BLD}{Style.CYN}╠══════════════════════════════════════════════════════════════════════════╣{Style.RST}")
        print(
            f"{Style.BLD}{Style.CYN}║{Style.RST} 📖 {blog_l}: {Style.YLW}{Style.BLD}{BLOG_URL}{Style.RST}"
            f"  🛒 {faka_l}: {Style.GRN}{Style.BLD}{FAKA_URL}{Style.RST}{ad_pad} {Style.BLD}{Style.CYN}║{Style.RST}"
        )
        print(f"{Style.BLD}{Style.CYN}╚══════════════════════════════════════════════════════════════════════════╝{Style.RST}")
        print(f"  {Style.BLD}{greet}{Style.RST}   {Style.DIM}[💻 {rd['os']} · 🌐 {lang_badge}]{Style.RST}")
        print(f"  {Style.DIM}💬 {motto}{Style.RST}\n")

        # Device & Component Status Bar
        if rd["connected"]:
            inst = f"[{rd['instance_name']}] " if rd.get("instance_name") else ""
            dev_line = f"{Style.GRN}● {self._tr('online')}{Style.RST} {Style.BLD}{inst}{Style.RST}{rd['serial']} {Style.DIM}({rd['model'] or 'Android'}){Style.RST}"
            acct_line = ", ".join(rd["accounts"]) if rd["accounts"] else f"{Style.YLW}{self._tr('no_google')}{Style.RST}"
            leds = [
                f"{Style.GRN}Frida●OK{Style.RST}" if rd["frida_running"] else f"{Style.YLW}Frida○Auto{Style.RST}",
                f"{Style.GRN}APK●OK{Style.RST}" if rd["module_ready"] else f"{Style.YLW}APK○Auto{Style.RST}",
                f"{Style.GRN}Play●OK{Style.RST}" if rd["vending_running"] else f"{Style.YLW}Play○Idle{Style.RST}",
                f"{Style.GRN}Net●OK{Style.RST}" if rd["net_validated"] else f"{Style.YLW}Net○Check{Style.RST}",
            ]
            comp_line = "  ".join(leds)
        else:
            dev_line = f"{Style.YLW}○ {self._tr('waiting')}{Style.RST}"
            acct_line = f"{Style.DIM}—{Style.RST}"
            comp_line = f"{Style.DIM}macOS / Windows Auto-Bootstrap Ready{Style.RST}"

        print(f"  {Style.BLD}📡 {self._tr('radar_title')}{Style.RST}  {Style.DIM}{self._tr('radar_refresh_hint')}{Style.RST}")
        print(f"     {self._tr('lbl_emu')} : {dev_line}")
        print(f"     {self._tr('lbl_acct')} : {acct_line}")
        print(f"     {self._tr('lbl_chain')} : {comp_line}")

        if rd["connected"] and rd["accounts"]:
            wiz = localize_wizard(
                analyze_pro_stacking_wizard(rd.get("subscriptions", []), self.billing.offers or None),
                lg,
            )
            nodes_str = []
            for st in wiz["steps"]:
                if st["state"] == "done":
                    nodes_str.append(f"{Style.GRN}[✓ {st['name']}]{Style.RST}")
                elif st["state"] == "current":
                    nodes_str.append(f"{Style.YLW}{Style.BLD}[● {st['name']}]{Style.RST}")
                else:
                    nodes_str.append(f"{Style.DIM}[○ {st['name']}]{Style.RST}")
            stepper = f" {Style.DIM}→{Style.RST} ".join(nodes_str)
            print(f"     {self._tr('lbl_wizard')} : {stepper}")
            print(f"     {self._tr('lbl_advice')} : {Style.CYN}{wiz['headline']}{Style.RST}")
            if wiz["warning"]:
                print(f"     ⚠️       : {Style.YLW}{wiz['warning']}{Style.RST}")
        print("")

    # ---------- Ensure Device Connected (with 1-click MuMu boot prompt!) ----------

    def _ensure_device_interactive(self) -> bool:
        if not self.dev.ensure_host_tools():
            prompt_line("\n  按回车返回...")
            return False
        if self.dev.connect_or_boot_device():
            return True

        mumu_list = list_mumu_instances_safe(self.dev.adb)
        if mumu_list:
            print(f"\n  {Style.YLW}[!] 当前没有正在运行的模拟器，检测到本地 MuMu 实例：{Style.RST}")
            for i, m in enumerate(mumu_list, 1):
                print(f"    [{i}] {m['name']} (index={m['index']})")
            ans = prompt_line(f"  是否立即一键唤醒模拟器？输入序号 [1-{len(mumu_list)}，默认 1，q 取消]: ").strip() or "1"
            if ans.isdigit() and 1 <= int(ans) <= len(mumu_list):
                target_idx = mumu_list[int(ans) - 1]["index"]
                ok = self.dev.boot_mumu_and_wait(target_idx)
                self.refresh_radar(force=True)
                return ok
        else:
            self.log("[-] 未检测到运行中的模拟器，请先启动 MuMu / 雷电模拟器或连接 USB 安卓设备")
            prompt_line("\n  按回车返回...")
        return False

    # ---------- Main Loop ----------

    def _language_screen(self) -> None:
        items = []
        cur = self._lang()
        for idx, code in enumerate(SUPPORTED_LANGS, 1):
            meta = LANG_META[code]
            mark = " ★" if code == cur else ""
            items.append({
                "key": str(idx),
                "code": code,
                "label": f"{meta['label']} ({code.upper()}){mark}",
                "sub": "RTL" if meta["dir"] == "rtl" else "LTR",
                "desc": f"Switch interface language to {meta['label']}",
                "color": Style.GRN if code == cur else Style.CYN,
            })

        def _hdr() -> None:
            print(f"{Style.BLD}{Style.CYN}╭──────────────────── 🌍  Language / اللغة / Язык / 语言 ────────────────────╮{Style.RST}\n")

        pick = visual_menu_select(_hdr, items, footer_hint="↑/↓ Select · Enter Apply · Q Back")
        if pick.isdigit() and 1 <= int(pick) <= len(SUPPORTED_LANGS):
            chosen_lang = SUPPORTED_LANGS[int(pick) - 1]
            self.prefs["lang"] = chosen_lang
            save_prefs(self.prefs)

    def run(self) -> int:
        try:
            while True:
                rd = self.refresh_radar(force=False)
                lg = self._lang()
                wiz = (
                    localize_wizard(analyze_pro_stacking_wizard(rd.get("subscriptions", []), self.billing.offers or None), lg)
                    if rd["connected"]
                    else None
                )
                last_act = self.prefs.get("last_action")

                menu_items: List[Dict[str, Any]] = []
                if last_act and last_act.get("label"):
                    menu_items.append({
                        "key": "0",
                        "label": f"{self._tr('replay')}{last_act['label']}",
                        "sub": "",
                        "desc": f"SKU: {last_act.get('sku', '')}",
                        "color": Style.GRN,
                    })
                if wiz and wiz.get("recommended_preset"):
                    menu_items.append({
                        "key": "s",
                        "label": f"{self._tr('wiz_go')}{wiz['recommended_label']}",
                        "sub": "",
                        "desc": wiz["headline"],
                        "color": Style.YLW,
                    })

                menu_items.extend([
                    {"key": "1", "label": self._tr("m1"), "sub": self._tr("m1_sub"), "desc": self._tr("m1_sub")},
                    {"key": "2", "label": self._tr("m2"), "sub": self._tr("m2_sub"), "desc": self._tr("m2_sub")},
                    {"key": "3", "label": self._tr("m3"), "sub": self._tr("m3_sub"), "desc": self._tr("m3_sub")},
                    {"key": "w", "label": self._tr("mw"), "sub": self._tr("mw_sub"), "desc": self._tr("mw_sub"), "color": Style.MAG},
                    {"key": "4", "label": self._tr("m4"), "sub": self._tr("m4_sub"), "desc": self._tr("m4_sub")},
                    {"key": "5", "label": self._tr("m5"), "sub": self._tr("m5_sub"), "desc": self._tr("m5_sub")},
                    {"key": "l", "label": self._tr("ml"), "sub": LANG_META[lg]["label"], "desc": self._tr("ml"), "color": Style.GRN},
                    {"key": "h", "label": self._tr("mh"), "sub": "", "desc": self._tr("mh"), "color": Style.CYN},
                    {"key": "b", "label": self._tr("mb"), "sub": f"{BLOG_URL} · {FAKA_URL}", "desc": f"{BLOG_URL} | {FAKA_URL}", "color": Style.YLW},
                    {"key": "q", "label": self._tr("mq"), "sub": "", "desc": self._tr("mq"), "color": Style.GRY},
                ])

                choice = visual_menu_select(
                    self._render_dashboard_header,
                    menu_items,
                    footer_hint=self._tr("footer"),
                    allow_esc_quit=False,
                )
                if choice == "q":
                    self.billing.close()
                    clear_screen()
                    print(f"\n{Style.GRN}[+] Bye, {self.prefs.get('user_name') or 'User'} 👋{Style.RST}")
                    print(f"{Style.CYN}    📖 Blog     : {BLOG_URL}{Style.RST}")
                    print(f"{Style.YLW}    🛒 GPT Shop : {FAKA_URL}{Style.RST}\n")
                    return 0
                if choice == "r":
                    self.refresh_radar(force=True)
                    continue
                if choice == "l":
                    self._language_screen()
                    continue
                if choice == "0" and last_act:
                    self._execute_plan_and_cockpit(
                        sku=last_act["sku"],
                        offer_id=last_act.get("offer_id", ""),
                        stack=bool(last_act.get("stack", False)),
                        is_paid=bool(last_act.get("is_paid", False)),
                        label=last_act["label"],
                    )
                elif choice == "s" and wiz and wiz.get("recommended_preset"):
                    rec_code = wiz["recommended_preset"]
                    if rec_code == "ack":
                        self._run_ack_flow()
                    elif rec_code == "cancel":
                        if self._ensure_device_interactive():
                            self.dev.cancel_subscription()
                            self.refresh_radar(force=True)
                            prompt_line("\n  按回车返回主菜单...")
                    else:
                        p = resolve_preset(rec_code)
                        if p:
                            self._confirm_and_launch_preset(p)
                elif choice == "1":
                    self._presets_screen()
                elif choice == "2":
                    self._live_browser_screen()
                elif choice == "3":
                    self._batch_screen()
                elif choice == "w":
                    if self.launch_web_cb:
                        self.billing.close()
                        self.launch_web_cb()
                        self.refresh_radar(force=True)
                elif choice == "4" or choice == "d":
                    self._toolbox_screen()
                elif choice == "5":
                    self._prefs_screen()
                elif choice == "h":
                    self._help_guide_screen()
                elif choice == "b":
                    self._links_screen()
        except KeyboardInterrupt:
            self.billing.close()
            print(f"\n{Style.YLW}[!] 已中断退出{Style.RST}")
            return 0

    # ---------- Screen 1: Presets ----------

    def _presets_screen(self) -> None:
        items = []
        hotkeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "x", "z"]
        preset_by_key: Dict[str, Dict[str, Any]] = {}
        for idx, p in enumerate(localize_presets(PRESETS, self._lang())):
            color = Style.GRN if not p["is_paid"] else Style.YLW
            hotkey = hotkeys[idx] if idx < len(hotkeys) else str(idx + 1)
            preset_by_key[hotkey] = p
            items.append({
                "key": hotkey,
                "preset": p,
                "label": f"{p['title']}  [{p['badge']}]",
                "sub": "",
                "desc": f"SKU: {p['sku']} | {p['desc']}",
                "color": color,
            })
        items.append({
            "key": "c",
            "label": "🔎 输入自定义 SKU 查询并拉起 (集成 query_sku)",
            "sub": "",
            "desc": "手动输入任意 g1.* 商品 ID，实时查询其隐藏 Offer 并拉起收银台",
            "color": Style.CYN,
        })

        def _hdr() -> None:
            print(f"{Style.BLD}{Style.CYN}╭──────────────────────────────────────────────────────────────────────────╮{Style.RST}")
            print(f"{Style.BLD}{Style.CYN}│               🚀  精选实时存活方案直达 (↑/↓ 选择 · Enter 发车)            │{Style.RST}")
            print(f"{Style.BLD}{Style.CYN}╰──────────────────────────────────────────────────────────────────────────╯{Style.RST}")
            print(f"  {Style.DIM}📖 技术博客: {BLOG_URL}   |   🛒 发卡网(GPT代充): {FAKA_URL}{Style.RST}\n")

        pick = visual_menu_select(_hdr, items, footer_hint="↑/↓ 选择方案 (1-9/0/X/Z 直达)  ·  Enter 立即拉起收银台  ·  Q/ESC 返回主菜单")
        if pick == "q":
            return
        if pick == "c":
            sku_in = prompt_line("\n  请输入要查询/拉起的商品 ID (例如 g1.2tb.ai.12months_ip_90p): ").strip()
            if sku_in:
                self._execute_plan_and_cockpit(sku=sku_in, offer_id="", stack=False, is_paid=("ip_" in sku_in), label=f"自定义 SKU: {sku_in}")
            return
        p_obj = preset_by_key.get(pick) or resolve_preset(pick)
        if p_obj:
            self._confirm_and_launch_preset(p_obj)

    def _confirm_and_launch_preset(self, p: Dict[str, Any]) -> None:
        if p["is_paid"]:
            clear_screen()
            print(f"\n  {Style.YLW}{Style.BLD}⚠️  付费特惠方案提醒：{p['title']}{Style.RST}")
            print(f"  {Style.DIM}说明：{p['desc']}{Style.RST}")
            print(f"  {Style.GRN}安全承诺：脚本只为您拉起 Google Play 收银台，绝不自动点击订阅扣款！{Style.RST}\n")
            ans = prompt_line("  确认拉起该方案收银台？(Enter/y 确认，q 取消): ").strip().lower()
            if ans in ("q", "n", "no"):
                return
        self._execute_plan_and_cockpit(
            sku=p["sku"],
            offer_id=p["offer_id"],
            stack=p["stack"],
            is_paid=p["is_paid"],
            label=p["title"],
        )

    # ---------- Screen 2: Live Offer Browser with Category Tabs ----------

    def _live_browser_screen(self) -> None:
        clear_screen()
        print(f"\n{Style.BLD}{Style.CYN}⚡ 正在连接模拟器并动态扫描全部可用 SKU...{Style.RST}\n")
        if not self._ensure_device_interactive():
            return

        if self.billing.is_alive():
            print(f"{Style.CYN}[*] 会话已就绪，正在实时刷新当前账号最新 SKU 列表...{Style.RST}")
            self.billing.send_command("REFRESH", ("INTERACTIVE_READY", "BROWSE_COMPLETE"), timeout=12.0)
        elif not self.billing.start_or_reuse():
            print(f"\n{Style.RED}[-] 计费引擎未能完成扫描，请查看上方实时诊断日志（可进 [4] 运行一键体检自愈）。{Style.RST}")
            prompt_line("\n  按回车返回主菜单...")
            return

        if not self.billing.offers:
            print(f"\n{Style.YLW}[!] Google Play 返回了 0 个可用方案。常见原因：{Style.RST}")
            print("    1. 新登账号尚未在模拟器点开过一次「Google Play 商店」同意条款（打开 Play 商店刷出首页即可）")
            print("    2. 模拟器当前网络节点无法访问 Google Play 结算服务")
            ans = prompt_line("\n  输入 r 自动唤醒 Play 商店并重新扫描，或按回车返回: ").strip().lower()
            if ans == "r":
                accts = self.dev.list_google_accounts()
                if accts:
                    self.dev.switch_play_account(accts[0])
                self.billing.start_or_reuse(force_restart_app=True)
            if not self.billing.offers:
                return

        # Brief pause so user can read the dynamic SKU streaming output before interactive table renders
        if is_interactive_tty():
            time.sleep(0.55)

        tabs = [("ALL", "全部方案"), ("TRIAL", "🟢 仅看 $0 免费"), ("PROMO", "🟡 仅看特惠促销"), ("BASE", "⚪ 标准付费")]
        tab_idx = 0
        sel = 0

        while True:
            cur_tab, _ = tabs[tab_idx]
            filtered = [o for o in self.billing.offers if cur_tab == "ALL" or o["type"] == cur_tab]
            if sel >= len(filtered):
                sel = max(0, len(filtered) - 1)

            if not is_interactive_tty():
                for i, o in enumerate(filtered, 1):
                    print(f"  {i:2d}. {o['name']} | {o['badge']} | {o['pricing_summary']} | {o['offer_id']}")
                ans = prompt_line("\n  输入序号拉起 (q 返回): ").strip()
                if ans.lower() == "q" or not ans.isdigit():
                    return
                idx_n = int(ans) - 1
                if 0 <= idx_n < len(filtered):
                    chosen = filtered[idx_n]
                    self._launch_offer_dict(chosen)
                return

            clear_screen()
            tab_bar = "  ".join(
                f"{Style.SEL_BG} {lbl} {Style.RST}" if i == tab_idx else f"{Style.DIM}[{lbl}]{Style.RST}"
                for i, (_, lbl) in enumerate(tabs)
            )
            hit_skus = []
            for o in self.billing.offers:
                if o["product"] not in hit_skus:
                    hit_skus.append(o["product"])
            miss_cnt = len(self.billing.missed_skus)
            trial_cnt = sum(1 for o in self.billing.offers if o["type"] == "TRIAL")
            promo_cnt = sum(1 for o in self.billing.offers if o["type"] == "PROMO")
            hit_preview = ", ".join(hit_skus[:5]) + (f" +{len(hit_skus)-5}" if len(hit_skus) > 5 else "")
            print(f"{Style.BLD}{Style.CYN}╭──── 🔍 实时全量方案浏览器 (命中 {len(hit_skus)} 个 SKU / {len(self.billing.offers)} 个方案 · 未开放 {miss_cnt} 个 SKU) ────╮{Style.RST}")
            print(f"  {Style.GRN}✓ 已命中 SKU:{Style.RST} {hit_preview or '无'}  {Style.DIM}| 免费:{trial_cnt} 特惠:{promo_cnt} (按 L 看逐条探测明细){Style.RST}")
            print(f"  分类筛选: {tab_bar}\n")
            print(f"  {Style.BLD}{pad_cjk('#', 4)} {pad_cjk('套餐名称', 24)} {pad_cjk('类型', 12)} {pad_cjk('计费明细', 28)} {pad_cjk('Offer ID', 18)}{Style.RST}")
            print(f"  {Style.DIM}{'─'*90}{Style.RST}")

            if not filtered:
                print(f"\n    {Style.YLW}(当前分类下暂无方案，按 Tab 或 ←/→ 切换查看其他分类){Style.RST}\n")
            else:
                start = max(0, min(sel - 6, max(0, len(filtered) - 14)))
                end = min(len(filtered), start + 14)
                for vis_i in range(start, end):
                    o = filtered[vis_i]
                    row_str = (
                        f"{pad_cjk(str(vis_i+1), 4)} "
                        f"{pad_cjk(o['name'], 24)} "
                        f"{pad_cjk(o['badge'], 12)} "
                        f"{pad_cjk(o['pricing_summary'], 28)} "
                        f"{pad_cjk(o['offer_id'], 18)}"
                    )
                    if vis_i == sel:
                        print(f"  {Style.SEL_BG}❯ {row_str}{Style.RST}")
                    else:
                        rc = Style.GRN if o["type"] == "TRIAL" else (Style.YLW if o["type"] == "PROMO" else Style.DIM)
                        print(f"    {rc}{row_str}{Style.RST}")

            print(f"\n  {Style.DIM}↑/↓ 选择  ·  Tab/←/→ 分类  ·  Enter 0.2s拉起  ·  L 查看SKU扫描明细  ·  R 重扫  ·  Q 返回{Style.RST}")
            k = read_key()
            kl = k.lower()
            if k == "UP" or kl == "k":
                if filtered:
                    sel = (sel - 1) % len(filtered)
            elif k == "DOWN" or kl == "j":
                if filtered:
                    sel = (sel + 1) % len(filtered)
            elif k in ("TAB", "RIGHT"):
                tab_idx = (tab_idx + 1) % len(tabs)
                sel = 0
            elif k == "LEFT":
                tab_idx = (tab_idx - 1) % len(tabs)
                sel = 0
            elif kl == "l":
                clear_screen()
                print(f"{Style.BLD}{Style.CYN}=== 📋 本次 SKU 实时探测完整明细 ==={Style.RST}\n")
                for tl in self.billing.scan_trace:
                    self.log(tl)
                prompt_line("\n  按回车返回方案表格...")
            elif kl == "r":
                clear_screen()
                print(f"\n{Style.CYN}⚡ 正在重新动态扫描全部 SKU...{Style.RST}\n")
                self.billing.send_command("REFRESH", ("INTERACTIVE_READY", "BROWSE_COMPLETE"), timeout=12.0)
                time.sleep(0.5)
            elif k == "ENTER" and filtered:
                chosen = filtered[sel]
                rc = self._launch_offer_dict(chosen)
                if rc != "BACK_TO_LIST":
                    return
            elif k in ("ESC", "BACKSPACE") or kl == "q":
                return

    def _launch_offer_dict(self, o: Dict[str, Any]) -> str:
        is_paid = o["type"] != "TRIAL"
        if is_paid:
            clear_screen()
            print(f"\n  {Style.YLW}{Style.BLD}⚠️  注意：您选中的是付费订阅方案 ({o['name']} · {o['pricing_summary']})！{Style.RST}")
            ans = prompt_line("  确认拉起收银台？(Enter/y 确认，n 返回重选): ").strip().lower()
            if ans in ("n", "no", "q"):
                return "BACK_TO_LIST"
        return self._execute_plan_and_cockpit(
            sku=o["product"],
            offer_id=o["offer_id"],
            stack=False,
            is_paid=is_paid,
            label=f"{o['name']} ({o['offer_id']})",
        )

    # ---------- Post-Launch Interactive Cockpit ----------

    def _execute_plan_and_cockpit(
        self,
        sku: str,
        offer_id: str,
        stack: bool,
        is_paid: bool,
        label: str,
    ) -> str:
        clear_screen()
        print(f"\n{Style.CYN}⚡ 正在准备并拉起收银台：{label}{Style.RST}\n")
        if not self._ensure_device_interactive():
            return "DONE"

        self.prefs["last_action"] = {
            "mode": "preset",
            "sku": sku,
            "offer_id": offer_id,
            "stack": stack,
            "is_paid": is_paid,
            "label": label,
        }
        save_prefs(self.prefs)

        while True:
            ok, ev = self.billing.launch_preset_or_sku(sku, offer_id, stack=stack)
            if ok:
                notify_user(self.prefs, "info", f"收银台已弹出: {label}")
                if stack:
                    print(f"  {Style.GRN}✓ 叠加收银台核对口诀：请确认显示「今日应付 $0」且包含「546天/730天折算顺延」字样后再点订阅！{Style.RST}")
                elif is_paid:
                    print(f"  {Style.YLW}⚠️ 付费特惠提示：请在模拟器核对首期折扣价无误后手动点「订阅」（第 90 天前记得取消续费）{Style.RST}")
            else:
                from .i18n import humanize_launch_error
                friendly = humanize_launch_error(ev, self._lang())
                notify_user(self.prefs, "error", f"拉起未成功: {friendly}")
                print(f"  {Style.YLW}💡 诊断说明：{friendly}{Style.RST}")

            time.sleep(0.3)
            self.billing.drain_events()

            print(f"\n{Style.BLD}{Style.CYN}  ╭────────────────────── 🎛️  收银台实时控制台 ──────────────────────╮{Style.RST}")
            print(f"  │  {Style.BLD}[Enter / R]{Style.RST} ⚡ 0.2秒重新拉起当前收银台   {Style.BLD}[P]{Style.RST} 🔑 自动代填密码确认 │")
            print(f"  │  {Style.BLD}[A]{Style.RST} 🔄 查单 & 补单确认同步容量           {Style.BLD}[S]{Style.RST} 📋 打开Play订阅页   │")
            print(f"  │  {Style.BLD}[X]{Style.RST} 🛡️ 一键取消自动续费(防扣款)          {Style.BLD}[B]{Style.RST} 🔙 返回重选其他方案 │")
            print(f"  │  {Style.BLD}[Q]{Style.RST} 👋 完成并返回主菜单                                          │")
            print(f"{Style.BLD}{Style.CYN}  ╰──────────────────────────────────────────────────────────────────╯{Style.RST}")

            cmd_k = prompt_line("  指令 [Enter=重拉 / p / a / s / x / b / q]: ").strip().lower()
            self.billing.drain_events()

            if cmd_k in ("", "r"):
                continue
            if cmd_k == "p":
                pw = prompt_line("  输入当前 Google 账号密码 (不回显): ", secret=True)
                if pw:
                    self.dev.handle_billing_password(pw)
                    self.dev.handle_post_payment()
                    self.billing.drain_events()
                    self.refresh_radar(force=True)
            elif cmd_k == "a":
                res = self.billing.sync_and_acknowledge()
                print(f"  {Style.GRN}[+] 实时查到 {res['count']} 笔活跃订阅，新补单确认 {res['acked']} 笔！{Style.RST}")
                self.refresh_radar(force=True)
                prompt_line("  按回车继续...")
            elif cmd_k == "s":
                self.dev.shell(
                    "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1 "
                    "|| am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1"
                )
                print(f"  {Style.GRN}[+] 已在模拟器打开 Play 订阅管理页{Style.RST}")
                prompt_line("  核对完毕后按回车返回控制台...")
            elif cmd_k == "x":
                self.dev.cancel_subscription()
                self.refresh_radar(force=True)
                prompt_line("  按回车返回控制台...")
            elif cmd_k == "b":
                return "BACK_TO_LIST"
            elif cmd_k == "q":
                self.refresh_radar(force=True)
                return "DONE"

    # ---------- Screen 3: Smart Batch Pipeline ----------

    def _batch_screen(self) -> None:
        clear_screen()
        print(f"{Style.BLD}{Style.CYN}╭──────────────────────────────────────────────────────────────────────╮{Style.RST}")
        print(f"{Style.BLD}{Style.CYN}│        📦  多账号全自动批量流水线 (支持拖拽 / 自动扫描 / 续跑)       │{Style.RST}")
        print(f"{Style.BLD}{Style.CYN}╰──────────────────────────────────────────────────────────────────────╯{Style.RST}")
        print(f"  {Style.DIM}📖 技术博客: {BLOG_URL}   |   🛒 发卡网(GPT代充): {FAKA_URL}{Style.RST}\n")

        cands = discover_candidate_files()
        if cands:
            print(f"  {Style.DIM}📂 自动发现附近的文本/表格文件（可直接输入编号，或拖入任意文件）：{Style.RST}")
            for i, f in enumerate(cands, 1):
                print(f"    {Style.CYN}[{i}]{Style.RST} {f}")
            print("")

        def _pick_file(prompt_lbl: str, default_p: str) -> Optional[Path]:
            d_hint = f" [{default_p}]" if default_p and Path(default_p).exists() else ""
            raw = prompt_line(f"  {prompt_lbl}{d_hint}: ").strip()
            if not raw and default_p and Path(default_p).exists():
                return Path(default_p)
            if raw.lower() == "q":
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(cands):
                return cands[int(raw) - 1]
            p = Path(normalize_user_path(raw))
            return p if p.exists() else None

        acct_path = _pick_file("Step 1/4 选择账号文件 (q 取消)", self.prefs.get("last_accounts_file", ""))
        if not acct_path:
            return
        accounts = parse_accounts_text(acct_path.read_text(encoding="utf-8", errors="ignore"))
        if not accounts:
            self.log("[-] 未解析到有效账号")
            prompt_line("\n  按回车返回...")
            return
        self.prefs["last_accounts_file"] = str(acct_path)
        save_prefs(self.prefs)

        emb_cards = sum(1 for a in accounts if a.get("card"))
        print(f"\n  {Style.GRN}[+] 已加载 {len(accounts)} 个账号{f' (内嵌卡 {emb_cards} 张)' if emb_cards else ''}{Style.RST}")
        for i, a in enumerate(accounts[:10], 1):
            flags = [k for k, v in (("2FA", a["totp"]), ("辅助邮", a["recovery"]), ("内嵌卡", a["card"])) if v]
            print(f"    {i:2d}. {a['email']:<34} {'+'.join(flags) or '仅密码'}")

        cards: List[Dict[str, str]] = []
        if emb_cards < len(accounts):
            card_path = _pick_file("\n  Step 2/4 选择卡片文件 (q 取消)", self.prefs.get("last_cards_file", ""))
            if not card_path:
                return
            cards = parse_cards_text(card_path.read_text(encoding="utf-8", errors="ignore"))
            if not cards:
                self.log("[-] 未解析到有效卡片")
                prompt_line("\n  按回车返回...")
                return
            self.prefs["last_cards_file"] = str(card_path)
            save_prefs(self.prefs)
            print(f"  {Style.GRN}[+] 已加载 {len(cards)} 张卡片{Style.RST}")

        print("\n  Step 3/4 选择目标套餐预设：")
        for p in PRESETS:
            print(f"    [{p['code']}] {p['title']}")
        p_raw = prompt_line("  输入预设编号 [默认 1 = Pro 5TB 免费12个月]: ").strip() or "1"
        p_sel = resolve_preset(p_raw) or PRESETS[0]

        # Check resumable log
        done_emails = set()
        logs = sorted(PROJECT_DIR.glob("results_*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        if logs:
            prev_done = load_completed_emails(logs[0])
            if prev_done:
                r_ans = prompt_line(f"\n  检测到上次记录 {logs[0].name} (已成功 {len(prev_done)} 个)，是否跳过已成功账号？[Y/n]: ").strip().lower()
                if r_ans not in ("n", "no"):
                    done_emails = prev_done

        go = prompt_line(f"\n  Step 4/4 即将对 {len(accounts)} 个账号执行【{p_sel['title']}】，按 Enter 发车 (q 取消): ").strip().lower()
        if go == "q":
            return

        self.billing.close()
        runner = BatchJobRunner(self.dev, self.prefs, log_fn=self.log)
        results = runner.run_sync(
            accounts=accounts,
            cards=cards,
            sku=p_sel["sku"],
            offer_id=p_sel["offer_id"],
            stack=p_sel["stack"],
            is_paid=p_sel["is_paid"],
            plan_label=p_sel["title"],
            resume_emails=done_emails,
            human_cb=self.human_console_prompt,
        )
        ok_c = sum(1 for r in results if r["status"] == "OK")
        print(f"\n  {Style.GRN}{Style.BLD}═══ 批量完成：成功 {ok_c} / 总计 {len(accounts)} | 日志: {runner.results_log_path} ═══{Style.RST}")
        self.refresh_radar(force=True)
        prompt_line("\n  按回车返回主菜单...")

    # ---------- Screen 4: Toolbox & Doctor ----------

    def _run_ack_flow(self) -> None:
        clear_screen()
        print(f"\n{Style.CYN}🔄 正在执行 Play 已购订单核验、自动 Acknowledge 补单与容量刷新...{Style.RST}\n")
        if not self._ensure_device_interactive():
            return
        res = self.billing.sync_and_acknowledge()
        print(f"\n  {Style.GRN}[+] BillingClient 实时查到 {res['count']} 笔有效订阅，新补单确认 {res['acked']} 笔！{Style.RST}")
        if res["count"] == 0:
            print(f"  {Style.YLW}💡 若银行卡刚显示扣款但此处为 0 笔：说明收银台网络中断导致交易仅停留在预授权未成单，Google Play 会自动原路退回。{Style.RST}")
        self.refresh_radar(force=True)
        prompt_line("\n  按回车返回...")

    def _toolbox_screen(self) -> None:
        while True:
            items = [
                {"key": "1", "label": "🩺 环境 · Frida · Play商店 · 网络全链路体检自愈", "desc": "自动修复版本对齐、推送模块、唤醒Play商店、清理残留死代理与误报断网"},
                {"key": "2", "label": "🔄 查单 & 补单确认同步容量 (专治付款成功未到账)", "desc": "调用 queryPurchasesAsync + acknowledgePurchase 并刷新 Google One"},
                {"key": "3", "label": "🛡️ 一键自动取消当前账号续费 (保留免费期权益)", "desc": "自动前往 Play 订阅管理页完成取消续费流程"},
                {"key": "4", "label": "📋 在模拟器直接打开 Play 订阅管理页", "desc": "快速核对下次付款日期是否已顺延至 12/18/24 个月后"},
                {"key": "5", "label": "🔀 MuMu 多开实例管理 (切换在线实例 / 一键启动休眠实例)", "desc": "跨平台支持 macOS mumutool 与 Windows MuMuManager.exe"},
            ]

            def _hdr() -> None:
                print(f"{Style.BLD}{Style.CYN}╭────────────────────── 🛠️  诊断 · 补单 · 实例管理箱 ──────────────────────╮{Style.RST}\n")

            pick = visual_menu_select(_hdr, items)
            if pick == "q":
                return
            if pick == "1":
                clear_screen()
                print(f"\n{Style.CYN}🩺 正在执行全链路环境与网络体检自愈...{Style.RST}\n")
                self.dev.run_doctor(auto_fix=True, local_port=self.billing.local_port)
                self.refresh_radar(force=True)
                prompt_line("\n  体检完毕，按回车返回...")
            elif pick == "2":
                self._run_ack_flow()
            elif pick == "3":
                clear_screen()
                if self._ensure_device_interactive():
                    self.dev.cancel_subscription()
                    self.refresh_radar(force=True)
                    prompt_line("\n  按回车返回...")
            elif pick == "4":
                if self._ensure_device_interactive():
                    self.dev.shell(
                        "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1 "
                        "|| am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1"
                    )
                    self.log("[+] 已在模拟器打开 Play 订阅管理页")
                    time.sleep(0.8)
            elif pick == "5":
                clear_screen()
                self.dev.ensure_host_tools()
                m_list = list_mumu_instances_safe(self.dev.adb)
                if not m_list:
                    self.log("[!] 未检测到 MuMu 多开管理器，当前已使用通用 ADB 连接")
                    prompt_line("\n  按回车返回...")
                    continue
                print("\n  📱 本地 MuMu 实例列表：")
                for i, m in enumerate(m_list, 1):
                    st = f"{Style.GRN}● 运行中 (127.0.0.1:{m['adb_port']}){Style.RST}" if m["running"] else f"{Style.DIM}○ 已休眠 (选此项一键启动){Style.RST}"
                    print(f"    [{i}] {m['name']:<22} {st}")
                ans = prompt_line(f"\n  输入序号切换或唤醒 [1-{len(m_list)}，Enter 返回]: ").strip()
                if ans.isdigit() and 1 <= int(ans) <= len(m_list):
                    chosen = m_list[int(ans) - 1]
                    self.billing.close()
                    if chosen["running"] and chosen["adb_port"]:
                        self.dev.serial = f"127.0.0.1:{chosen['adb_port']}"
                        self.dev.instance_name = chosen["name"]
                        self.dev.connect_or_boot_device(preferred_port=chosen["adb_port"])
                    else:
                        self.dev.serial = ""
                        self.dev.boot_mumu_and_wait(chosen["index"])
                    self.refresh_radar(force=True)

    # ---------- Screen 5: Personalization Settings ----------

    def _prefs_screen(self) -> None:
        while True:
            items = [
                {"key": "1", "label": f"称呼昵称       : {self.prefs.get('user_name')}", "desc": "修改启动问候语中的专属称呼"},
                {"key": "2", "label": f"提示词引导风格 : {self.prefs.get('persona')}", "desc": "点击切换 geek (极客领航) / minimal (极简疾速) / coach (贴心向导)"},
                {"key": "3", "label": f"启动个性签名   : {self.prefs.get('motto')}", "desc": "设置为 auto 则智能轮播防坑锦囊，也可输入您的专属标语"},
                {"key": "4", "label": f"系统提示音效   : {'开启' if self.prefs.get('sound') else '关闭'}", "desc": "macOS 播放清脆系统音效，Windows 播放系统提示音"},
                {"key": "5", "label": f"0 动画极速模式 : {'开启' if self.prefs.get('fast_anim') else '关闭'}", "desc": "批量自动化期间临时关闭模拟器过渡动画，大幅缩短 UI 等待"},
                {"key": "6", "label": f"批量重置策略   : {self.prefs.get('batch_reset')}", "desc": "smart=pm clear 秒切账号(每号省45秒) / reinstall=卸载重下"},
                {"key": "7", "label": f"激活后自动取消 : {'开启' if self.prefs.get('auto_cancel') else '关闭'}", "desc": "批量开通免费试用后立即自动取消续费，防止到期遗忘扣款"},
                {"key": "8", "label": f"绑卡邮编策略   : {self.prefs.get('postal_mode')}", "desc": "classic=92101/89101/33131 / taxfree=美国免税州邮编 97201 等"},
            ]

            def _hdr() -> None:
                print(f"{Style.BLD}{Style.CYN}╭────────────────────── ⚙️  个性化与提示词定制中心 ──────────────────────╮{Style.RST}\n")

            pick = visual_menu_select(_hdr, items, footer_hint="↑/↓ 选择设置项  ·  Enter 切换/编辑  ·  Q 保存并返回")
            if pick == "q":
                save_prefs(self.prefs)
                return
            if pick == "1":
                v = prompt_line(f"\n  输入新的称呼昵称 [{self.prefs.get('user_name')}]: ").strip()
                if v:
                    self.prefs["user_name"] = v
            elif pick == "2":
                order = ["geek", "minimal", "coach"]
                cur = self.prefs.get("persona", "geek")
                self.prefs["persona"] = order[(order.index(cur) + 1) % len(order)] if cur in order else "geek"
            elif pick == "3":
                v = prompt_line("\n  输入自定义标语 (输入 auto 恢复智能锦囊轮播): ").strip()
                if v:
                    self.prefs["motto"] = v
            elif pick == "4":
                self.prefs["sound"] = not self.prefs.get("sound", True)
                notify_user(self.prefs, "success")
            elif pick == "5":
                self.prefs["fast_anim"] = not self.prefs.get("fast_anim", True)
            elif pick == "6":
                self.prefs["batch_reset"] = "reinstall" if self.prefs.get("batch_reset") == "smart" else "smart"
            elif pick == "7":
                self.prefs["auto_cancel"] = not self.prefs.get("auto_cancel", True)
            elif pick == "8":
                self.prefs["postal_mode"] = "taxfree" if self.prefs.get("postal_mode") == "classic" else "classic"
            save_prefs(self.prefs)

    def _help_guide_screen(self) -> None:
        guide_path = PROJECT_DIR / "常见问题与网络环境自查手册.md"
        clear_screen()
        print(f"{Style.BLD}{Style.CYN}╔══════════════════════════════════════════════════════════════════════════╗{Style.RST}")
        print(f"{Style.BLD}{Style.CYN}║             📖  常见问题 · 网络与代理环境自查速览                        ║{Style.RST}")
        print(f"{Style.BLD}{Style.CYN}╚══════════════════════════════════════════════════════════════════════════╝{Style.RST}\n")
        if guide_path.exists():
            lines = guide_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            for ln in lines[:48]:
                if ln.startswith("## "):
                    print(f"\n{Style.BLD}{Style.CYN}{ln}{Style.RST}")
                elif ln.startswith("### "):
                    print(f"{Style.BLD}{Style.YLW}{ln}{Style.RST}")
                else:
                    print(f"  {ln}")
            if len(lines) > 48:
                print(f"\n  {Style.DIM}... (完整手册共 {len(lines)} 行，保存在: {guide_path}){Style.RST}")
        else:
            print("  1. 宿主机请开启代理软件 TUN 模式（Windows 需管理员权限运行 Clash/v2rayN）")
            print("  2. 若模拟器断网或误报离线，请在主菜单 [4] → [1] 运行「一键体检自愈」自动清除残留死代理")
            print("  3. Pro 叠加第 2/3 步前切勿提前取消自动续费，全部叠满 24 个月后再取消续费")
        ans = prompt_line("\n  输入 d 立即执行网络一键体检自愈，或按回车返回主菜单: ").strip().lower()
        if ans == "d":
            clear_screen()
            self.dev.run_doctor(auto_fix=True, local_port=self.billing.local_port)
            self.refresh_radar(force=True)
            prompt_line("\n  体检完毕，按回车返回主菜单...")

    def _links_screen(self) -> None:
        items = [
            {
                "key": "1",
                "label": f"📖 打开技术博客 ({BLOG_URL})",
                "sub": "技术文章与实用教程分享",
                "desc": f"立即在系统默认浏览器打开 {BLOG_URL}",
                "color": Style.CYN,
            },
            {
                "key": "2",
                "label": f"🛒 打开发卡网 — 仅提供 GPT 代充 ({FAKA_URL})",
                "sub": "专营 ChatGPT / GPT 代充服务（无其他业务）",
                "desc": f"立即在系统默认浏览器打开 {FAKA_URL}",
                "color": Style.GRN,
            },
            {
                "key": "3",
                "label": "🚀 同时打开博客与 GPT 代充发卡网",
                "sub": "",
                "desc": "一键在浏览器同时打开技术博客与发卡网",
                "color": Style.YLW,
            },
        ]

        def _hdr() -> None:
            print(f"{Style.BLD}{Style.CYN}╭──────────────────── 🌐  技术博客 & GPT代充发卡网直达 ────────────────────╮{Style.RST}")
            print(f"  📖 技术博客          : {Style.CYN}{Style.BLD}{BLOG_URL}{Style.RST}")
            print(f"  🛒 发卡网 (GPT 代充) : {Style.YLW}{Style.BLD}{FAKA_URL}{Style.RST}\n")

        pick = visual_menu_select(_hdr, items, footer_hint="↑/↓ 选择  ·  Enter 在浏览器打开  ·  Q 返回主菜单")
        if pick == "1":
            webbrowser.open(BLOG_URL)
        elif pick == "2":
            webbrowser.open(FAKA_URL)
        elif pick == "3":
            webbrowser.open(BLOG_URL)
            webbrowser.open(FAKA_URL)


def list_mumu_instances_safe(adb_path: Optional[str]) -> List[Dict[str, Any]]:
    from .platform_env import list_mumu_instances
    return list_mumu_instances(adb_path)
