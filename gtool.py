#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool.py — Google AI Pro / Ultra Trial Studio (macOS & Windows 自适应全可视化主入口).

用法:
  python3 gtool.py                        # 进入全彩方向键控制台可视化界面 (按 W 可随时打开网页版)
  python3 gtool.py --web                  # 启动本地浏览器图形化驾驶舱 (含实时模拟器屏幕镜像+触控)
  python3 gtool.py --doctor               # 跨平台环境、ADB、Frida、模块与网络全自动体检自愈
  python3 gtool.py --preset pro12         # 一键拉起 Pro 5TB 免费 12 个月 (第1步)
  python3 gtool.py --preset stack1        # 一键拉起 Pro 5TB 免费叠加 +6 个月 (第2步→18月)
  python3 gtool.py --preset stack2        # 一键拉起 Pro 5TB 免费叠加 +6 个月 (第3步→24月)
  python3 gtool.py --preset u1            # 一键拉起 Ultra 30TB 前3月 1折 ($19.99/月)
  python3 gtool.py --sku <SKU> [--stack]  # 按指定商品 ID 拉起收银台
  python3 gtool.py --ack                  # 查单 & 补单确认同步容量 (解决付款成功未到账)
  python3 gtool.py --cancel               # 一键取消当前账号自动续费
  python3 gtool.py --accounts a.txt --cards c.txt [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gtool_core.batch_runner import (
    BatchJobRunner,
    load_completed_emails,
    normalize_user_path,
    parse_accounts_text,
    parse_cards_text,
)
from gtool_core.billing_engine import resolve_preset
from gtool_core.platform_env import BLOG_URL, FAKA_URL, init_console_environment, load_prefs
from gtool_core.tui_app import ConsoleStudioApp
from gtool_core.web_app import run_web_studio


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="gtool.py",
        description=f"Google AI Pro / Ultra Trial Studio — macOS / Windows 自适应可视化助手 | 博客: {BLOG_URL} | 发卡网(GPT代充): {FAKA_URL}",
        epilog=f"📖 技术博客: {BLOG_URL}   |   🛒 发卡网 (仅提供 GPT 代充): {FAKA_URL}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--web", action="store_true", help="启动本地浏览器图形化驾驶舱 (实时画面镜像 + 卡片下单 + 拖拽跑号)")
    ap.add_argument("--web-port", type=int, default=None, help="指定本地 Web 控制台端口 (默认自动选择 8765+)")
    ap.add_argument("--web-token", default="", help=argparse.SUPPRESS)
    ap.add_argument("--no-open", action="store_true", help="配合 --web 使用：启动服务但不自动弹出浏览器")
    ap.add_argument("--lang", default="", choices=["", "zh", "en", "ar", "ru", "es"], help="界面语言 Interface Language (zh/en/ar/ru/es)")
    ap.add_argument("--doctor", "--check", dest="doctor", action="store_true", help="执行全链路环境自动适配、下载补齐与网络自愈")
    ap.add_argument("--quick", "--browse", dest="quick", action="store_true", help="直接进入当前账号全量方案扫描浏览器")
    ap.add_argument("--preset", default="", help="一键执行精选预设: pro12 / stack1(pro6) / stack2(pro6b) / pro6c / pro3 / auto / u1 / u2 / u3 / u4")
    ap.add_argument("--sku", default="", help="指定单个商品 ID (SKU) 直接查询并拉起收银台")
    ap.add_argument("--offer", default="", help="配合 --sku 指定精确 Offer ID")
    ap.add_argument("--stack", action="store_true", help="启用订阅升级折算顺延叠加模式 (CHARGE_FULL_PRICE)")
    ap.add_argument("--ack", "--sync", dest="ack", action="store_true", help="查询已购订阅并执行 Acknowledge 补单同步")
    ap.add_argument("--cancel", action="store_true", help="自动前往 Play 订阅管理页取消当前账号续费")
    ap.add_argument("--port", type=int, default=None, help="指定模拟器 ADB 端口 (如 16384 / 16416)")
    ap.add_argument("--accounts", default="", help="批量模式：账号文件路径")
    ap.add_argument("--cards", default="", help="批量模式：卡片文件路径")
    ap.add_argument("--card-mode", default="rotate", choices=["rotate", "single"], help="卡片分配模式")
    ap.add_argument("--resume", default="", help="断点续跑日志路径")
    ap.add_argument("--start-from", type=int, default=1, help="批量模式：从第 N 个账号开始执行")
    ap.add_argument("--max-failures", type=int, default=5, help="批量模式：连续失败熔断上限 [默认: 5]")
    ap.add_argument("--cooldown", type=float, default=2.0, help="批量模式：账号间冷却秒数 [默认: 2.0]")
    ap.add_argument("--dry-run", action="store_true", help="仅解析校验账号与卡片文件，不连接模拟器")
    return ap


def main(argv: list[str] | None = None) -> int:
    init_console_environment()
    args = build_parser().parse_args(argv)

    if args.lang:
        from gtool_core.platform_env import save_prefs
        p_init = load_prefs()
        p_init["lang"] = args.lang
        save_prefs(p_init)

    if args.web:
        return run_web_studio(
            port=args.web_port,
            open_browser=(not args.no_open),
            token=(args.web_token or None),
        )

    app = ConsoleStudioApp(launch_web_cb=lambda: run_web_studio(port=args.web_port, open_browser=True))
    if args.port:
        app.dev.serial = f"127.0.0.1:{args.port}"

    if args.dry_run or args.accounts:
        print(f"📖 技术博客：{BLOG_URL}  |  🛒 发卡网(GPT代充)：{FAKA_URL}\n")
        if not args.accounts:
            print("[-] 请通过 --accounts 指定账号文件路径")
            return 1
        ap_path = Path(normalize_user_path(args.accounts))
        if not ap_path.exists():
            print(f"[-] 账号文件不存在: {ap_path}")
            return 1
        accts = parse_accounts_text(ap_path.read_text(encoding="utf-8", errors="ignore"))
        emb = sum(1 for a in accts if a.get("card"))
        cards = []
        if args.cards:
            cp_path = Path(normalize_user_path(args.cards))
            if not cp_path.exists():
                print(f"[-] 卡片文件不存在: {cp_path}")
                return 1
            cards = parse_cards_text(cp_path.read_text(encoding="utf-8", errors="ignore"))
        print(f"[+] 解析成功：{len(accts)} 个账号 (内嵌卡 {emb} 张)，独立卡 {len(cards)} 张")
        if args.dry_run:
            for i, a in enumerate(accts, 1):
                flags = [k for k, v in (("2FA", a["totp"]), ("辅助邮", a["recovery"]), ("内嵌卡", a["card"])) if v]
                print(f"  {i:2d}. {a['email']:<34} {'+'.join(flags) or '仅密码'}")
            print("[+] DRY RUN 校验完成，未执行任何模拟器操作。")
            return 0

        p = resolve_preset(args.preset or "pro12")
        sku = args.sku or (p["sku"] if p else "g1.2tb.ai.subs_variant")
        oid = args.offer or (p["offer_id"] if p else "12months-eft")
        stack = args.stack or bool(p and p["stack"])
        is_paid = bool(p and p["is_paid"]) or ("ip_" in sku)
        label = p["title"] if p and not args.sku else sku
        done = load_completed_emails(Path(args.resume)) if args.resume else set()

        runner = BatchJobRunner(app.dev, load_prefs(), log_fn=app.log)
        runner.run_sync(
            accounts=accts,
            cards=cards,
            sku=sku,
            offer_id=oid,
            stack=stack,
            is_paid=is_paid,
            plan_label=label,
            card_mode=args.card_mode,
            resume_emails=done,
            start_from=args.start_from,
            max_consecutive_fails=args.max_failures,
            cooldown=args.cooldown,
            human_cb=app.human_console_prompt,
        )
        return 0

    if any([args.doctor, args.ack, args.cancel, args.preset, args.sku, args.quick]):
        print(f"📖 技术博客：{BLOG_URL}  |  🛒 发卡网(GPT代充)：{FAKA_URL}\n")

    if args.doctor:
        res = app.dev.run_doctor(auto_fix=True, local_port=app.billing.local_port)
        return 0 if res.get("ok") else 1

    if args.ack:
        if not app.dev.connect_or_boot_device(preferred_port=args.port):
            print("[-] 未检测到在线模拟器")
            return 1
        res = app.billing.sync_and_acknowledge()
        app.billing.close()
        print(f"[+] 补单同步完成：查到 {res['count']} 笔有效订阅，本次新确认 {res['acked']} 笔")
        return 0

    if args.cancel:
        if not app.dev.connect_or_boot_device(preferred_port=args.port):
            print("[-] 未检测到在线模拟器")
            return 1
        ok = app.dev.cancel_subscription()
        return 0 if ok else 1

    if args.preset:
        p = resolve_preset(args.preset)
        if not p:
            print(f"[-] 未知预设代号: {args.preset}")
            return 1
        app._confirm_and_launch_preset(p)
        app.billing.close()
        return 0

    if args.sku:
        app._execute_plan_and_cockpit(
            sku=args.sku,
            offer_id=args.offer,
            stack=args.stack,
            is_paid=("ip_" in args.sku),
            label=f"SKU: {args.sku}",
        )
        app.billing.close()
        return 0

    if args.quick:
        app._live_browser_screen()
        app.billing.close()
        return 0

    return app.run()


if __name__ == "__main__":
    sys.exit(main())
