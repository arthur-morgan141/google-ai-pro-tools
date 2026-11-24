#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/web_app.py — Streamlined, Minimalist, Multilingual (ZH/EN/AR-RTL/RU/ES) Desktop & Web Studio."""

from __future__ import annotations

import collections
import http.cookies
import json
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, List, Optional

from .batch_runner import BatchJobRunner, parse_accounts_text, parse_cards_text
from .billing_engine import (
    PRESETS,
    LiveBillingSession,
    analyze_pro_stacking_wizard,
    evaluate_preset_eligibility,
    resolve_preset,
)
from .device_ops import DeviceController
from .i18n import (
    LANG_META,
    SUPPORTED_LANGS,
    WEB_UI_DICT,
    active_motto_i18n,
    humanize_launch_error,
    localize_offer,
    localize_presets,
    localize_wizard,
    normalize_lang,
    time_greeting_i18n,
)
from .platform_env import BLOG_URL, FAKA_URL, load_prefs, notify_user, save_prefs
from .web_hub_data import (
    decode_shelf_sc,
    get_localized_web_hub,
    is_allowed_external_url,
)

MAX_JSON_BYTES = 5 * 1024 * 1024  # 5 MB cap


class WebStudioState:
    def __init__(self, token: Optional[str] = None, bound_port: int = 0) -> None:
        self.auth_token: str = (token or "").strip() or secrets.token_hex(16)
        self.bound_port: int = bound_port
        self.logs: Deque[str] = collections.deque(maxlen=250)
        self.lock = threading.Lock()
        self.prefs = load_prefs()
        self.dev = DeviceController(log_fn=self.add_log)
        self.billing = LiveBillingSession(self.dev, log_fn=self.add_log)
        self.batch = BatchJobRunner(self.dev, self.prefs, log_fn=self.add_log)
        self.add_log("[+] Studio ready on 127.0.0.1 (Session Auth & Rebinding Guard enabled)")

    def add_log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with self.lock:
            self.logs.append(line)
        print(line, flush=True)

    def get_logs(self) -> List[str]:
        with self.lock:
            return list(self.logs)


WEB_HTML = r"""<!DOCTYPE html>
<html lang="zh" dir="ltr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Google AI Trial Studio</title>
<style>
:root {
  --bg: #0b0f19;
  --surface: #131929;
  --surface2: #192236;
  --surface-hover: #1f2a42;
  --border: rgba(148, 163, 184, 0.14);
  --border-strong: rgba(56, 189, 248, 0.42);
  --text: #f1f5f9;
  --muted: #94a3b8;
  --primary: #2563eb;
  --primary-hover: #3b82f6;
  --cyan: #38bdf8;
  --green: #10b981;
  --amber: #f59e0b;
  --red: #ef4444;
  --radius: 12px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Arabic", "Segoe UI", "PingFang SC", "Microsoft YaHei", Tahoma, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.shell {
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px 22px 28px;
  transition: max-width .2s ease;
}
.shell.with-screen { max-width: 1320px; }

/* Header: Clean single row */
.header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 18px;
}
.brand-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.logo-dot {
  width: 32px; height: 32px; border-radius: 9px;
  background: linear-gradient(135deg, #2563eb, #06b6d4);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 16px; flex-shrink: 0;
}
.brand-title { font-size: 16.5px; font-weight: 700; letter-spacing: -0.01em; }
.status-chip {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 12.5px; padding: 5px 11px; border-radius: 999px;
  background: var(--surface); border: 1px solid var(--border); color: var(--muted);
}
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--amber); flex-shrink: 0; }
.status-chip.online { color: var(--text); }
.status-chip.online .status-dot { background: var(--green); box-shadow: 0 0 8px rgba(16,185,129,.55); }

.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

button, select, input, textarea {
  font-family: inherit;
  font-size: 13px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 7px 12px;
  outline: none;
  transition: background .15s, border-color .15s;
}
button { cursor: pointer; font-weight: 500; display: inline-flex; align-items: center; justify-content: center; gap: 5px; white-space: nowrap; flex-shrink: 0; }
button:hover, select:hover { background: var(--surface-hover); border-color: rgba(148,163,184,0.3); }
input:focus, textarea:focus, select:focus { border-color: var(--cyan); }

button.btn-primary { background: var(--primary); border-color: rgba(96,165,250,.4); color: #fff; font-weight: 600; }
button.btn-primary:hover { background: var(--primary-hover); }
button.btn-success { background: #059669; border-color: rgba(52,211,153,.4); color: #fff; font-weight: 600; }
button.btn-success:hover { background: #10b981; }
button.btn-amber { background: rgba(245,158,11,.14); border-color: rgba(245,158,11,.4); color: #fcd34d; font-weight: 600; }
button.btn-danger { background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.35); color: #fca5a5; }
button.btn-ghost { background: transparent; border-color: transparent; color: var(--muted); }
button.btn-ghost:hover { background: var(--surface); color: var(--text); border-color: var(--border); }
button.active-toggle { border-color: var(--cyan); color: var(--cyan); background: rgba(56,189,248,.1); }

/* Navigation Tabs */
.nav-tabs {
  display: inline-flex;
  gap: 4px;
  background: var(--surface);
  padding: 4px;
  border-radius: 11px;
  border: 1px solid var(--border);
  margin-bottom: 18px;
  flex-wrap: wrap;
}
.nav-tab {
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  border: none;
  background: transparent;
}
.nav-tab:hover { color: var(--text); background: rgba(255,255,255,.03); }
.nav-tab.active { background: var(--surface2); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.3); }

/* Workspace Layout (1 column default, 2 columns only when Screen Drawer is open) */
.workspace { display: grid; grid-template-columns: 1fr; gap: 18px; align-items: start; }
.workspace.split { grid-template-columns: 1fr 330px; }
@media (max-width: 960px) { .workspace.split { grid-template-columns: 1fr; } }

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
}

/* Smart Wizard Strip */
.wizard-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  background: linear-gradient(135deg, rgba(37,99,235,0.12), rgba(16,185,129,0.08));
  border: 1px solid rgba(56,189,248,0.24);
  border-radius: var(--radius);
  padding: 15px 18px;
  margin-bottom: 16px;
}
.wiz-main { flex: 1; min-width: 240px; }
.wiz-headline { font-size: 14px; font-weight: 600; color: var(--text); }
.wiz-warn { font-size: 12.5px; color: #fcd34d; margin-top: 5px; display: none; }
.wiz-steps { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 9px; }
.wstep {
  font-size: 11.5px; padding: 3px 9px; border-radius: 999px;
  background: rgba(15,23,42,.55); border: 1px solid var(--border); color: var(--muted);
}
.wstep.done { border-color: rgba(16,185,129,.45); color: #6ee7b7; }
.wstep.current { border-color: rgba(245,158,11,.55); color: #fcd34d; font-weight: 600; }

/* Segmented Preset Filter */
.seg-row {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 14px;
}
.seg-group {
  display: inline-flex; background: var(--bg); padding: 3px;
  border-radius: 9px; border: 1px solid var(--border); gap: 3px;
}
.seg-btn {
  padding: 5px 13px; border-radius: 7px; font-size: 12.5px; font-weight: 600;
  border: none; background: transparent; color: var(--muted); cursor: pointer;
}
.seg-btn.active { background: var(--surface2); color: var(--text); }

/* Clean 2-Column Preset Cards */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.plan-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 15px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 12px;
  transition: border-color .15s, transform .15s;
}
.plan-card:hover { border-color: rgba(148,163,184,0.32); }
.plan-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.plan-title { font-size: 14px; font-weight: 600; }
.plan-desc { font-size: 12.5px; color: var(--muted); margin-top: 5px; line-height: 1.45; }
.tag {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 6px;
  white-space: nowrap; flex-shrink: 0;
}
.tag.free { background: rgba(16,185,129,.14); color: #6ee7b7; }
.tag.promo { background: rgba(245,158,11,.15); color: #fcd34d; }

.util-strip {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border);
}

/* Tables */
.table-wrap { overflow-x: auto; margin-top: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: start; padding: 9px 10px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 600; font-size: 12px; }
tr:hover td { background: rgba(255,255,255,.02); }

/* Batch Dropzones */
.batch-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 720px) { .batch-grid { grid-template-columns: 1fr; } }
.drop-box {
  background: var(--surface2); border: 1px dashed rgba(148,163,184,.28);
  border-radius: 10px; padding: 12px;
}
.drop-hdr { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
textarea { width: 100%; min-height: 96px; background: var(--bg); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; resize: vertical; }
.progress-track { height: 8px; background: var(--bg); border-radius: 999px; overflow: hidden; margin: 12px 0 6px; }
.progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, var(--primary), var(--green)); transition: width .25s; }

/* Settings & Collapsible FAQ */
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 10px; }
@media (max-width: 720px) { .settings-grid { grid-template-columns: 1fr; } }
.field-lbl { font-size: 12.5px; color: var(--muted); display: block; margin-bottom: 5px; }
.chk-row { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; }
details.faq-item {
  background: var(--surface2); border: 1px solid var(--border); border-radius: 10px;
  padding: 11px 14px; margin-top: 8px;
}
details.faq-item summary { cursor: pointer; font-weight: 600; font-size: 13.5px; list-style: none; display: flex; justify-content: space-between; align-items: center; }
details.faq-item summary::-webkit-details-marker { display: none; }
details.faq-item summary::after { content: "+"; color: var(--muted); font-size: 16px; }
details.faq-item[open] summary::after { content: "−"; }
details.faq-item p { font-size: 12.5px; color: var(--muted); margin-top: 8px; white-space: pre-line; line-height: 1.6; }

/* Collapsible Screen Remote Drawer */
.screen-drawer { display: none; }
.screen-drawer.open { display: block; }
.screen-frame {
  position: relative; background: #050811; border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; min-height: 360px;
  display: flex; align-items: center; justify-content: center; cursor: crosshair; margin: 10px 0;
}
.screen-frame img { width: 100%; height: auto; display: block; user-select: none; }
.tap-dot {
  position: absolute; width: 18px; height: 18px; border: 2px solid var(--cyan);
  border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none;
  animation: pulse .45s ease-out forwards;
}
@keyframes pulse { from { opacity: 1; scale: 0.5; } to { opacity: 0; scale: 1.8; } }

/* Human Assist Alert */
.human-box {
  background: rgba(245,158,11,.13); border: 1px solid rgba(245,158,11,.45);
  border-radius: var(--radius); padding: 13px 16px; margin-bottom: 16px; display: none;
}

/* Sleek Collapsible Bottom Log Bar & Footer */
.log-bar-wrap { margin-top: 18px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.log-bar-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 8px 14px; font-size: 12px; color: var(--muted); cursor: pointer;
}
.log-bar-head:hover { background: var(--surface2); color: var(--text); }
.log-latest { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.log-drawer {
  display: none; background: #070a12; border-top: 1px solid var(--border);
  padding: 10px 14px; height: 170px; overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11.5px; color: #cbd5e1; white-space: pre-wrap; line-height: 1.5;
}
.log-drawer.open { display: block; }

.footer-links {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 16px;
  font-size: 12px; color: var(--muted); margin-top: 16px;
}
.footer-links a { color: var(--muted); text-decoration: none; transition: color .15s; }
.footer-links a:hover { color: var(--cyan); }

.toast {
  position: fixed; inset-inline-end: 20px; bottom: 20px; z-index: 9999;
  max-width: 400px; padding: 10px 15px; border-radius: 10px;
  background: var(--surface2); border: 1px solid var(--border-strong); color: var(--text);
  box-shadow: 0 10px 28px rgba(0,0,0,.45); font-size: 13px; display: none;
}
.ltr-tok { direction: ltr; unicode-bidi: isolate; }
</style>
</head>
<body>

<div id="toastBox" class="toast"></div>

<div class="shell" id="appShell">
  <!-- Minimalist Single-Row Header -->
  <header class="header">
    <div class="brand-row">
      <span class="logo-dot">✦</span>
      <span class="brand-title" id="i_app_title">Google AI Trial Studio</span>
      <div class="status-chip" id="statusChip">
        <span class="status-dot"></span>
        <span id="statusText">—</span>
      </div>
      <select id="mumuSelect" style="display:none;padding:5px 9px;font-size:12px;" onchange="switchOrBootMumu()"></select>
      <button id="connectBtn" style="display:none;padding:5px 10px;font-size:12px;" onclick="switchOrBootMumu()"></button>
    </div>

    <div class="toolbar">
      <button id="screenToggleBtn" onclick="toggleScreenDrawer()">📱 <span id="i_btn_screen">屏幕遥控</span></button>
      <button onclick="runDoctor()">🩺 <span id="i_btn_doctor">环境自愈</span></button>
      <button class="btn-ghost" onclick="refreshStatus()" title="Refresh">↻</button>
      <select id="langSelect" onchange="onLangChange(this.value)" aria-label="Language"></select>
    </div>
  </header>

  <!-- Manual Verification Gate Banner (only visible when triggered) -->
  <div id="humanBanner" class="human-box">
    <div style="font-size:13.5px;"><strong id="i_human_title">需要人工协助：</strong> <span id="humanMsg"></span></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px;">
      <button class="btn-success" onclick="resolveHuman('continue')" id="i_human_cont">已完成，继续</button>
      <button class="btn-amber" onclick="resolveHuman('skip')" id="i_human_skip">跳过此号</button>
      <button class="btn-danger" onclick="resolveHuman('abort')" id="i_human_abort">中止任务</button>
    </div>
  </div>

  <!-- 5 Calm, Clean Tabs -->
  <nav class="nav-tabs">
    <button class="nav-tab active" data-tab="quick" onclick="switchTab('quick', this)" id="i_tab_quick">一键开通</button>
    <button class="nav-tab" data-tab="scan" onclick="switchTab('scan', this)" id="i_tab_scan">方案扫描</button>
    <button class="nav-tab" data-tab="batch" onclick="switchTab('batch', this)" id="i_tab_batch">批量跑号</button>
    <button class="nav-tab" data-tab="webhub" onclick="switchTab('webhub', this)">🌐 <span id="i_tab_webhub">网页生态</span></button>
    <button class="nav-tab" data-tab="settings" onclick="switchTab('settings', this)" id="i_tab_settings">设置与自查</button>
  </nav>

  <div class="workspace" id="workspaceGrid">
    <!-- Main Content Column -->
    <div>
      <!-- TAB 1: Quick Start (Clean Segmented View) -->
      <section id="tab-quick" class="panel">
        <div class="wizard-bar">
          <div class="wiz-main">
            <div class="wiz-headline" id="wizHeadline">...</div>
            <div class="wiz-warn" id="wizWarn"></div>
            <div class="wiz-steps" id="wizStepper"></div>
          </div>
          <div id="wizActionWrap"></div>
        </div>

        <div class="seg-row">
          <div class="seg-group">
            <button class="seg-btn active" id="segBtnFree" onclick="setPresetSeg('free')"><span id="i_seg_free">免费试用 ($0)</span></button>
            <button class="seg-btn" id="segBtnPromo" onclick="setPresetSeg('promo')"><span id="i_seg_promo">Ultra 特惠折扣</span></button>
            <button class="seg-btn" id="segBtnCustom" onclick="setPresetSeg('custom')"><span id="i_seg_custom">自定义 SKU</span></button>
          </div>
          <span class="tag free" id="subDaysBadge"></span>
        </div>

        <div id="customSkuPane" style="display:none;padding:14px 0 6px;">
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <input id="customSkuInput" class="ltr-tok" style="flex:1;min-width:240px;" placeholder="g1.2tb.ai.subs_variant"/>
            <button class="btn-primary" onclick="launchCustomSku()" id="i_btn_custom_go">查询并拉起</button>
          </div>
        </div>

        <div class="cards-grid" id="presetGrid"></div>

        <div class="util-strip">
          <button onclick="runAck()">🔄 <span id="i_util_ack">查单 & 补单同步</span></button>
          <button onclick="openPlaySubs()">📋 <span id="i_util_subs">打开 Play 订阅页</span></button>
          <button class="btn-danger" onclick="cancelSub()">🛡️ <span id="i_util_cancel">取消自动续费</span></button>
        </div>
      </section>

      <!-- TAB 2: Live Offer Scanner -->
      <section id="tab-scan" class="panel" style="display:none;">
        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;">
          <div class="seg-group">
            <button class="seg-btn active" data-flt="ALL" onclick="setOfferFilter('ALL', this)" id="i_scan_all">全部</button>
            <button class="seg-btn" data-flt="TRIAL" onclick="setOfferFilter('TRIAL', this)" id="i_scan_trial">$0 免费</button>
            <button class="seg-btn" data-flt="PROMO" onclick="setOfferFilter('PROMO', this)" id="i_scan_promo">特惠促销</button>
            <button class="seg-btn" data-flt="BASE" onclick="setOfferFilter('BASE', this)" id="i_scan_base">标准价</button>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <input id="offerSearch" oninput="renderOffers()" style="width:190px;"/>
            <input id="extraProbeSkus" class="ltr-tok" placeholder="g1.2tb.ai.6months_ip_50p, ..." style="width:220px;" title="Custom extra SKUs to probe"/>
            <button class="btn-primary" onclick="scanOffers()">⚡ <span id="i_btn_scan_now">立即扫描</span></button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th id="i_col_plan">套餐名称</th>
                <th id="i_col_tag">标签</th>
                <th id="i_col_price">计费明细</th>
                <th>Offer ID</th>
                <th id="i_col_action">操作</th>
              </tr>
            </thead>
            <tbody id="offerTbody"></tbody>
          </table>
        </div>
      </section>

      <!-- TAB 3: Batch Runner -->
      <section id="tab-batch" class="panel" style="display:none;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <span id="batchPreviewStat" style="font-size:13px;color:var(--muted);"></span>
          <span class="tag free" id="i_batch_safety">非 $0 自动拦截防扣款</span>
        </div>
        <div class="batch-grid">
          <div class="drop-box" ondragover="event.preventDefault()" ondrop="handleDrop(event,'acctText')">
            <div class="drop-hdr">
              <span id="i_batch_accts_lbl">账号列表</span>
              <label style="cursor:pointer;color:var(--cyan);">
                <span id="i_batch_import_1">导入文件</span>
                <input type="file" accept=".txt,.csv" onchange="loadFile(event,'acctText')" style="display:none;"/>
              </label>
            </div>
            <textarea id="acctText" class="ltr-tok" oninput="previewBatch()" placeholder="email----password----2fa----recovery"></textarea>
          </div>
          <div class="drop-box" ondragover="event.preventDefault()" ondrop="handleDrop(event,'cardText')">
            <div class="drop-hdr">
              <span id="i_batch_cards_lbl">卡片列表</span>
              <label style="cursor:pointer;color:var(--cyan);">
                <span id="i_batch_import_2">导入文件</span>
                <input type="file" accept=".txt,.csv" onchange="loadFile(event,'cardText')" style="display:none;"/>
              </label>
            </div>
            <textarea id="cardText" class="ltr-tok" oninput="previewBatch()" placeholder="5450200010222396-06/29-457"></textarea>
          </div>
        </div>

        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:12px;">
          <select id="batchPresetSel"></select>
          <select id="batchCardMode">
            <option value="rotate" id="i_card_rotate">卡片轮换</option>
            <option value="single" id="i_card_single">固定首卡</option>
          </select>
          <button class="btn-success" onclick="startBatch()">▶ <span id="i_btn_batch_start">启动批量</span></button>
          <button class="btn-danger" onclick="stopBatch()">⏹ <span id="i_btn_batch_stop">停止</span></button>
        </div>

        <div class="progress-track"><div class="progress-fill" id="batchBar"></div></div>
        <p id="batchRunStat" style="font-size:12px;color:var(--muted);"></p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th id="i_col_email">账号</th>
                <th id="i_col_status">状态</th>
                <th id="i_col_detail">详情</th>
                <th id="i_col_time">耗时</th>
              </tr>
            </thead>
            <tbody id="batchResBody"></tbody>
          </table>
        </div>
      </section>

      <!-- TAB 4: Settings & Clean Accordion FAQ -->
      <section id="tab-settings" class="panel" style="display:none;">
        <h3 style="font-size:14.5px;margin-bottom:4px;" id="i_set_profile">基础与自动化偏好</h3>
        <div class="settings-grid">
          <div>
            <span class="field-lbl" id="i_lbl_name">称呼昵称</span>
            <input id="pfName" style="width:100%;"/>
          </div>
          <div>
            <span class="field-lbl" id="i_lbl_reset">批量重置方式</span>
            <select id="pfReset" style="width:100%;">
              <option value="smart" id="i_opt_smart">极速清数据秒切</option>
              <option value="reinstall" id="i_opt_reinstall">卸载重装</option>
            </select>
          </div>
          <div>
            <span class="field-lbl" id="i_lbl_postal">绑卡美国邮编池</span>
            <select id="pfPostal" style="width:100%;">
              <option value="classic" id="i_opt_classic">常规州 (92101 / 89101)</option>
              <option value="taxfree" id="i_opt_taxfree">免税州 (97201 / 19801)</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;justify-content:center;gap:8px;">
            <label class="chk-row"><input type="checkbox" id="pfSound"/> <span id="i_lbl_sound">启用提示音</span></label>
            <label class="chk-row"><input type="checkbox" id="pfAnim"/> <span id="i_lbl_anim">模拟器 0 动画加速</span></label>
            <label class="chk-row"><input type="checkbox" id="pfCancel"/> <span id="i_lbl_autocancel">试用开通后自动取消续费</span></label>
          </div>
        </div>
        <div style="margin-top:14px;">
          <button class="btn-primary" onclick="savePrefs()" id="i_btn_save_prefs">保存设置</button>
        </div>

        <hr style="border:none;border-top:1px solid var(--border);margin:20px 0 14px;"/>
        <h3 style="font-size:14.5px;margin-bottom:6px;" id="i_faq_title">常见问题与网络环境自查</h3>
        <div id="faqList"></div>
      </section>

      <!-- TAB 5: Google Web Ecosystem Hub & Hidden Perks -->
      <section id="tab-webhub" class="panel" style="display:none;">
        <div class="wizard-bar" style="margin-bottom:14px;">
          <div class="wiz-main">
            <div class="wiz-headline" id="i_wh_headline">Google 网页版订阅总控 · 隐藏回血权益与付款风控中心</div>
            <div style="font-size:12.5px;color:var(--muted);margin-top:4px;" id="i_wh_sub"></div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <span style="font-size:12px;color:var(--muted);" id="i_wh_acct_lbl">账号槽位</span>
            <select id="whAcctSlot" onchange="renderWebHub()" class="ltr-tok" style="padding:5px 10px;">
              <option value="0">authuser = 0 (u/0)</option>
              <option value="1">authuser = 1 (u/1)</option>
              <option value="2">authuser = 2 (u/2)</option>
              <option value="3">authuser = 3 (u/3)</option>
              <option value="4">authuser = 4 (u/4)</option>
              <option value="5">authuser = 5 (u/5)</option>
            </select>
            <select id="whLocaleSel" onchange="renderWebHub()" class="ltr-tok" style="padding:5px 10px;">
              <option value="en-US">hl=en-US</option>
              <option value="zh-CN">hl=zh-CN</option>
              <option value="zh-TW">hl=zh-TW</option>
              <option value="ja">hl=ja</option>
              <option value="ar">hl=ar</option>
              <option value="ru">hl=ru</option>
              <option value="es">hl=es</option>
            </select>
          </div>
        </div>

        <div class="seg-row">
          <div class="seg-group">
            <button class="seg-btn active" id="whSegPortals" onclick="setWebHubSeg('portals')"><span id="i_wh_seg_portals">订阅与货架</span></button>
            <button class="seg-btn" id="whSegPerks" onclick="setWebHubSeg('perks')"><span id="i_wh_seg_perks">隐藏回血权益</span></button>
            <button class="seg-btn" id="whSegRisk" onclick="setWebHubSeg('risk')"><span id="i_wh_seg_risk">付款资料与家庭组</span></button>
          </div>
        </div>

        <div class="cards-grid" id="webHubGrid"></div>

        <div style="margin-top:14px;padding:11px 14px;border-radius:10px;background:var(--surface2);border:1px solid var(--border);font-size:12.5px;color:var(--muted);line-height:1.6;" id="i_wh_family_note"></div>

        <div class="batch-grid" style="margin-top:14px;">
          <div class="drop-box" style="border-style:solid;">
            <div style="font-size:13px;font-weight:600;margin-bottom:8px;" id="i_wh_or_title">payments.google.com 报错码 (OR-*) 速查诊断</div>
            <input id="whOrInput" class="ltr-tok" style="width:100%;" oninput="filterOrCodes()" placeholder="OR-HDT-01 / OR-CCSEH-21 / OR-FGEMF-20"/>
            <div id="whOrResult" style="font-size:12px;color:var(--muted);margin-top:8px;line-height:1.55;"></div>
          </div>
          <div class="drop-box" style="border-style:solid;">
            <div style="font-size:13px;font-weight:600;margin-bottom:8px;" id="i_wh_sc_title">one.google.com 官方 ?sc= 货架参数解码器</div>
            <div style="display:flex;gap:6px;">
              <input id="whScInput" class="ltr-tok" style="flex:1;" value="IgIQAVIGCgQIBxAD"/>
              <button class="btn-primary" onclick="decodeScInput()" id="i_wh_btn_decode">解析参数</button>
            </div>
            <div id="whScResult" class="ltr-tok" style="font-size:12px;color:var(--muted);margin-top:8px;line-height:1.55;"></div>
          </div>
        </div>
      </section>
    </div>

    <!-- Collapsible Screen Remote Drawer (Hidden by default so UI stays super clean!) -->
    <aside class="panel screen-drawer" id="screenDrawer">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
        <span style="font-size:13px;font-weight:600;" id="i_scr_title">模拟器实时画面</span>
        <label style="font-size:12px;color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;gap:5px;">
          <input type="checkbox" id="autoMirror" onchange="toggleMirror()"/> <span id="i_scr_live">自动刷新</span>
        </label>
      </div>
      <div class="screen-frame" id="screenBox" onclick="onScreenClick(event)">
        <span id="screenPlaceholder" style="color:var(--muted);font-size:12px;padding:18px;text-align:center;"></span>
        <img id="screenImg" style="display:none;" alt="Screen"/>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
        <button onclick="refreshScreen()">📸 <span id="i_btn_scr_shot">刷新画面</span></button>
        <button onclick="promptPasswordFill()">🔑 <span id="i_btn_scr_pw">代填密码</span></button>
        <button onclick="sendKey('KEYCODE_BACK')">◀ <span id="i_btn_scr_back">返回</span></button>
        <button onclick="sendKey('KEYCODE_HOME')">● <span id="i_btn_scr_home">桌面</span></button>
      </div>
    </aside>
  </div>

  <!-- Sleek Collapsible Activity Log Bar -->
  <div class="log-bar-wrap">
    <div class="log-bar-head" onclick="toggleLogs()">
      <strong id="i_logs_toggle">运行日志</strong>
      <span class="log-latest ltr-tok" id="logLatest"></span>
      <span id="logArrow">▾</span>
    </div>
    <div class="log-drawer ltr-tok" id="logBox"></div>
  </div>

  <!-- Understated Single-Line Official Links Footer -->
  <footer class="footer-links">
    <a href="https://blog.caowo.de/" onclick="event.preventDefault();openExternalUrl('https://blog.caowo.de/')" rel="noopener">📖 <span id="i_ad_blog">技术博客</span> · <span class="ltr-tok">blog.caowo.de</span></a>
    <span>·</span>
    <a href="https://faka.cdkey.si/" onclick="event.preventDefault();openExternalUrl('https://faka.cdkey.si/')" rel="noopener">🛒 <span id="i_ad_faka">GPT 代充发卡网（仅提供 ChatGPT 代充）</span> · <span class="ltr-tok">faka.cdkey.si</span></a>
  </footer>
</div>

<script>
const STUDIO_TOKEN = __STUDIO_TOKEN__;
const I18N_ALL = __I18N_JSON__;
const LANG_META = __LANG_META_JSON__;
const WEB_HUB_ALL = __WEB_HUB_JSON__;

let curLang = __INIT_LANG__;
let curPresetSeg = 'free';
let curWebHubSeg = 'portals';
let curOfferFilter = 'ALL';
let cachedOffers = [];
let presetsList = [];
let lastParsedBatch = null;
let mirrorTimer = null;
let toastTimer = null;

function T(key, vars) {
  const dict = I18N_ALL[curLang] || I18N_ALL.en;
  let val = (dict && dict[key] !== undefined) ? dict[key] : (I18N_ALL.en[key] || key);
  if (vars && typeof val === 'string') {
    Object.keys(vars).forEach(k => { val = val.replaceAll('{' + k + '}', vars[k]); });
  }
  return val;
}

function escHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showToast(msg, borderCol='var(--border-strong)') {
  const b = document.getElementById('toastBox');
  b.textContent = msg;
  b.style.borderColor = borderCol;
  b.style.display = 'block';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { b.style.display = 'none'; }, 4200);
}

async function api(path, body=null) {
  const headers = {'X-Studio-Token': STUDIO_TOKEN};
  const opts = {headers};
  if (body !== null) {
    headers['Content-Type'] = 'application/json';
    opts.method = 'POST';
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(path, opts);
  return await r.json();
}

function initLangSelect() {
  const sel = document.getElementById('langSelect');
  sel.innerHTML = '';
  Object.keys(LANG_META).forEach(code => {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = '🌐 ' + LANG_META[code].label;
    if (code === curLang) opt.selected = true;
    sel.appendChild(opt);
  });
}

function applyStaticI18n() {
  const meta = LANG_META[curLang] || LANG_META.zh;
  document.documentElement.lang = curLang;
  document.documentElement.dir = meta.dir;
  document.title = T('app_title');

  const ids = [
    'app_title', 'btn_screen', 'btn_doctor',
    'tab_quick', 'tab_scan', 'tab_batch', 'tab_settings',
    'seg_free', 'seg_promo', 'seg_custom', 'btn_custom_go',
    'util_ack', 'util_subs', 'util_cancel',
    'scan_all', 'scan_trial', 'scan_promo', 'scan_base', 'btn_scan_now',
    'col_plan', 'col_tag', 'col_price', 'col_action',
    'batch_safety', 'batch_accts_lbl', 'batch_cards_lbl',
    'card_rotate', 'card_single', 'btn_batch_start', 'btn_batch_stop',
    'col_email', 'col_status', 'col_detail', 'col_time',
    'scr_title', 'scr_live', 'btn_scr_shot', 'btn_scr_back', 'btn_scr_home', 'btn_scr_pw',
    'set_profile', 'lbl_name', 'lbl_reset', 'opt_smart', 'opt_reinstall',
    'lbl_postal', 'opt_classic', 'opt_taxfree',
    'lbl_sound', 'lbl_anim', 'lbl_autocancel', 'btn_save_prefs', 'faq_title',
    'human_title', 'human_cont', 'human_skip', 'human_abort',
    'logs_toggle', 'ad_blog', 'ad_faka'
  ];
  ids.forEach(k => {
    const el = document.getElementById('i_' + k);
    if (el) el.textContent = T(k);
  });

  document.getElementById('i_batch_import_1').textContent = T('batch_import_file');
  document.getElementById('i_batch_import_2').textContent = T('batch_import_file');
  document.getElementById('connectBtn').textContent = '⚡ ' + T('btn_connect');
  document.getElementById('customSkuInput').placeholder = T('custom_placeholder');
  document.getElementById('offerSearch').placeholder = T('scan_search');
  document.getElementById('screenPlaceholder').textContent = T('scr_hint');
  if (!document.getElementById('logLatest').dataset.hasLog) {
    document.getElementById('logLatest').textContent = T('logs_ready');
  }
  if (!lastParsedBatch) {
    document.getElementById('batchPreviewStat').textContent = T('batch_stat_idle');
  } else {
    document.getElementById('batchPreviewStat').textContent = T('batch_stat_parsed', lastParsedBatch);
  }

  const faqDiv = document.getElementById('faqList');
  const faqs = T('faqs') || [];
  faqDiv.innerHTML = faqs.map(item =>
    `<details class="faq-item"><summary>${escHtml(item.q)}</summary><p>${escHtml(item.a)}</p></details>`
  ).join('');

  renderPresets();
  renderOffers();
  applyWebHubI18n();
}

function getWebHubPack() {
  return WEB_HUB_ALL[curLang] || WEB_HUB_ALL.en || WEB_HUB_ALL.zh;
}

function applyWebHubI18n() {
  const pack = getWebHubPack();
  if (!pack || !pack.ui) return;
  const u = pack.ui;
  const mapIds = [
    'tab_webhub', 'wh_headline', 'wh_sub', 'wh_acct_lbl',
    'wh_seg_portals', 'wh_seg_perks', 'wh_seg_risk',
    'wh_or_title', 'wh_sc_title', 'wh_btn_decode', 'wh_family_note'
  ];
  mapIds.forEach(k => {
    const el = document.getElementById('i_' + k);
    if (el && u[k]) el.textContent = u[k];
  });
  const orInp = document.getElementById('whOrInput');
  if (orInp && u.wh_or_ph) orInp.placeholder = u.wh_or_ph;
  const scInp = document.getElementById('whScInput');
  if (scInp && u.wh_sc_ph) scInp.placeholder = u.wh_sc_ph;
  renderWebHub();
  filterOrCodes();
  decodeScInput();
}

function setWebHubSeg(seg) {
  curWebHubSeg = seg;
  document.getElementById('whSegPortals').classList.toggle('active', seg === 'portals');
  document.getElementById('whSegPerks').classList.toggle('active', seg === 'perks');
  document.getElementById('whSegRisk').classList.toggle('active', seg === 'risk');
  renderWebHub();
}

async function openExternalUrl(url) {
  const r = await api('/api/open_url', {url});
  if (!r.ok) {
    window.open(url, '_blank', 'noopener');
  }
}

function renderWebHub() {
  const pack = getWebHubPack();
  const grid = document.getElementById('webHubGrid');
  if (!pack || !grid) return;
  const uSlot = (document.getElementById('whAcctSlot') || {}).value || '0';
  const hlVal = (document.getElementById('whLocaleSel') || {}).value || 'en-US';
  const btnLbl = (pack.ui && pack.ui.wh_btn_open) || 'Open';
  const items = (pack.cards || []).filter(c => c.group === curWebHubSeg);
  grid.innerHTML = items.map(c => {
    const finalUrl = c.url_tpl.replaceAll('{u}', encodeURIComponent(uSlot)).replaceAll('{hl}', encodeURIComponent(hlVal));
    let hostLabel = '';
    try { hostLabel = new URL(finalUrl).hostname; } catch (e) { hostLabel = ''; }
    return `<div class="plan-card">
      <div>
        <div class="plan-top">
          <div class="plan-title">${escHtml(c.title)}</div>
          <span class="tag ${c.tag_cls || 'free'} ltr-tok">${escHtml(c.badge)}</span>
        </div>
        <div class="plan-desc" style="margin-top:6px;">${escHtml(c.desc)}</div>
      </div>
      <div class="plan-foot">
        <span class="plan-sku ltr-tok">${escHtml(hostLabel)}</span>
        <button class="btn-primary" style="padding:6px 12px;font-size:12.5px;" data-ext-url="${escHtml(finalUrl)}" onclick="openExternalUrl(this.getAttribute('data-ext-url'))">↗ ${escHtml(btnLbl)}</button>
      </div>
    </div>`;
  }).join('');
}

function filterOrCodes() {
  const pack = getWebHubPack();
  const box = document.getElementById('whOrResult');
  if (!pack || !box) return;
  const q = ((document.getElementById('whOrInput') || {}).value || '').trim().toUpperCase();
  const list = pack.or_errors || [];
  const hits = !q ? list.slice(0, 2) : list.filter(it =>
    it.codes.some(c => c.toUpperCase().includes(q) || q.includes(c.toUpperCase())) || it.detail.toUpperCase().includes(q)
  );
  if (!hits.length) {
    box.textContent = '—';
    return;
  }
  box.innerHTML = hits.map(it =>
    `<div style="margin-bottom:6px;"><strong class="ltr-tok" style="color:var(--cyan);">${escHtml(it.codes.join(' / '))}</strong>: ${escHtml(it.detail)}</div>`
  ).join('');
}

async function decodeScInput() {
  const inp = document.getElementById('whScInput');
  const out = document.getElementById('whScResult');
  if (!inp || !out) return;
  const raw = inp.value.trim();
  if (!raw) { out.textContent = ''; return; }
  const r = await api('/api/webhub/decode_sc', {sc: raw});
  if (!r || !r.ok) {
    out.textContent = (r && r.error) || 'Invalid ?sc= or ear link';
    return;
  }
  if (r.kind === 'ear') {
    const skuHtml = (r.skus && r.skus.length) ? escHtml(r.skus.join(' + ')) : 'None';
    const warnHtml = r.fp_leak
      ? `<div style="color:#fcd34d;margin-top:4px;">⚠️ Static Fingerprint Leak in ear[4][0]: BotGuard=${r.has_botguard_sig ? 'Yes' : 'No'} · UA="${escHtml(r.embedded_ua)}" (Shared links trigger cluster correlation!)</div>`
      : `<div style="color:#6ee7b7;margin-top:4px;">✓ No static ear[4][0] fingerprint detected</div>`;
    out.innerHTML = `<div><strong>eacquire/multiline</strong> · SKUs: <span style="color:#38bdf8;">${skuHtml}</span> · Mode: <code>${escHtml(r.proration_mode)}</code></div>` + warnHtml;
    return;
  }
  out.innerHTML = `<div><strong>Tier #${escHtml(r.tier_id)}</strong> → <span style="color:#6ee7b7;">${escHtml(r.tier_name)}</span></div>` +
    `<div style="margin-top:3px;opacity:.85;">Protobuf (${r.byte_len}B): <code>${escHtml(r.hex)}</code></div>`;
}

async function onLangChange(newLang) {
  curLang = newLang;
  applyStaticI18n();
  await api('/api/prefs', {lang: newLang});
  await refreshStatus();
  if (cachedOffers.length) {
    const r = await api('/api/offers/localized');
    if (r.offers) { cachedOffers = r.offers; renderOffers(); }
  }
}

function switchTab(name, btnEl) {
  ['quick', 'scan', 'batch', 'webhub', 'settings'].forEach(t => {
    const el = document.getElementById('tab-' + t);
    if (el) el.style.display = (t === name) ? 'block' : 'none';
  });
  document.querySelectorAll('.nav-tab').forEach(x => x.classList.remove('active'));
  btnEl.classList.add('active');
}

function toggleScreenDrawer() {
  const dr = document.getElementById('screenDrawer');
  const open = !dr.classList.contains('open');
  dr.classList.toggle('open', open);
  document.getElementById('workspaceGrid').classList.toggle('split', open);
  document.getElementById('appShell').classList.toggle('with-screen', open);
  document.getElementById('screenToggleBtn').classList.toggle('active-toggle', open);
  if (open && document.getElementById('screenImg').style.display === 'none') {
    refreshScreen();
  }
}

function toggleLogs() {
  const lb = document.getElementById('logBox');
  const open = !lb.classList.contains('open');
  lb.classList.toggle('open', open);
  document.getElementById('logArrow').textContent = open ? '▴' : '▾';
  if (open) lb.scrollTop = lb.scrollHeight;
}

function setPresetSeg(seg) {
  curPresetSeg = seg;
  document.getElementById('segBtnFree').classList.toggle('active', seg === 'free');
  document.getElementById('segBtnPromo').classList.toggle('active', seg === 'promo');
  document.getElementById('segBtnCustom').classList.toggle('active', seg === 'custom');
  document.getElementById('customSkuPane').style.display = (seg === 'custom') ? 'block' : 'none';
  document.getElementById('presetGrid').style.display = (seg === 'custom') ? 'none' : 'grid';
  renderPresets();
}

let prefsLoadedOnce = false;
async function refreshStatus() {
  const d = await api('/api/status?lang=' + encodeURIComponent(curLang));
  if (d.lang && d.lang !== curLang && !prefsLoadedOnce) {
    curLang = d.lang;
    document.getElementById('langSelect').value = curLang;
    applyStaticI18n();
  }

  const chip = document.getElementById('statusChip');
  const stTxt = document.getElementById('statusText');
  const acct = (d.radar.accounts && d.radar.accounts[0]) || T('no_account');
  if (d.radar.connected) {
    chip.className = 'status-chip online';
    const devLbl = d.radar.instance_name || d.radar.serial;
    stTxt.textContent = `${devLbl} · ${acct}`;
  } else {
    chip.className = 'status-chip';
    stTxt.textContent = T('dev_disconnected');
  }

  const sel = document.getElementById('mumuSelect');
  const cBtn = document.getElementById('connectBtn');
  sel.innerHTML = '';
  if (d.radar.mumu_instances && d.radar.mumu_instances.length > 0) {
    d.radar.mumu_instances.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.index;
      opt.textContent = (m.running ? '● ' : '○ ') + m.name + (m.adb_port ? ` (:${m.adb_port})` : '');
      if (`127.0.0.1:${m.adb_port}` === d.radar.serial) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.style.display = (d.radar.mumu_instances.length > 1 || !d.radar.connected) ? 'inline-block' : 'none';
    cBtn.style.display = (!d.radar.connected) ? 'inline-flex' : 'none';
  } else {
    sel.style.display = 'none';
    cBtn.style.display = 'none';
  }

  const w = d.wizard;
  document.getElementById('wizHeadline').textContent = w.headline;
  document.getElementById('subDaysBadge').textContent = w.days_left ? T('days_left_fmt', {days: w.days_left}) : T('no_active_sub');
  const ww = document.getElementById('wizWarn');
  if (w.warning) { ww.style.display = 'block'; ww.textContent = '⚠️ ' + w.warning; } else { ww.style.display = 'none'; }

  const arrow = (LANG_META[curLang] && LANG_META[curLang].dir === 'rtl') ? '←' : '→';
  document.getElementById('wizStepper').innerHTML = (w.steps || []).map(s => {
    const cls = ['done', 'current'].includes(s.state) ? s.state : '';
    const mark = s.state === 'done' ? '✓ ' : (s.state === 'current' ? '● ' : '');
    return `<span class="wstep ${cls}">${mark}${escHtml(s.name)}</span>`;
  }).join(`<span style="color:var(--muted);font-size:11px;">${arrow}</span>`);

  document.getElementById('wizActionWrap').innerHTML = w.recommended_preset
    ? `<button class="btn-success" data-code="${escHtml(w.recommended_preset)}" onclick="runWizardAction(this.getAttribute('data-code'))">⚡ ${escHtml(w.recommended_label)}</button>`
    : '';

  if (d.presets) {
    presetsList = d.presets;
    renderPresets();
  }
  loadPrefsIntoForm(d.prefs);
}

function renderPresets() {
  const g = document.getElementById('presetGrid');
  const bs = document.getElementById('batchPresetSel');
  const prevBatch = bs.value;
  g.innerHTML = '';
  bs.innerHTML = '';

  presetsList.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.alias;
    opt.textContent = p.title;
    bs.appendChild(opt);
  });
  if (prevBatch && [...bs.options].some(o => o.value === prevBatch)) bs.value = prevBatch;

  const visible = presetsList.filter(p => p.group === curPresetSeg);
  visible.forEach(p => {
    const card = document.createElement('div');
    card.className = 'plan-card';
    const safeTitle = escHtml(p.title);
    const safeAlias = escHtml(p.alias);
    const tagCls = p.is_paid ? 'promo' : 'free';
    const btnCls = p.is_paid ? 'btn-amber' : 'btn-primary';
    const subCode = (p.offer_id && p.offer_id !== '__PROMO__') ? p.offer_id : p.sku;
    let eligHtml = '';
    if (p.elig === 'available') {
      const lp = p.live_price ? ` · ${escHtml(p.live_price)}` : '';
      eligHtml = `<span style="color:#6ee7b7;font-weight:600;">✓${lp}</span> · `;
    } else if (p.elig === 'ineligible') {
      card.style.opacity = '0.68';
      eligHtml = `<span style="color:#f87171;">✗</span> · `;
    }
    card.innerHTML = `
      <div>
        <div class="plan-top">
          <div class="plan-title">${safeTitle}</div>
          <span class="tag ${tagCls}">${escHtml(p.badge)}</span>
        </div>
        <div class="plan-desc">${escHtml(p.desc)}</div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
        <span class="ltr-tok" style="font-size:11px;color:var(--muted);">${eligHtml}${escHtml(subCode)}</span>
        <button class="${btnCls}" data-alias="${safeAlias}" data-paid="${!!p.is_paid}" data-title="${safeTitle}"
          onclick="launchPreset(this.getAttribute('data-alias'), this.getAttribute('data-paid')==='true', this.getAttribute('data-title'))">
          ⚡ ${escHtml(T('btn_launch'))}
        </button>
      </div>`;
    g.appendChild(card);
  });
}

async function runWizardAction(code) {
  if (code === 'ack') return runAck();
  if (code === 'cancel') return cancelSub();
  const p = presetsList.find(x => x.alias === code);
  if (p) launchPreset(p.alias, p.is_paid, p.title);
}

async function launchPreset(alias, isPaid, title) {
  if (isPaid && !confirm(T('confirm_paid', {title}))) return;
  showToast(T('toast_launching', {title}));
  const r = await api('/api/checkout/launch', {preset: alias, lang: curLang});
  if (r.ok) {
    showToast(T('toast_launched', {title}), 'var(--green)');
  } else {
    showToast(T('toast_failed', {err: r.human_error || r.event || r.error || 'Error'}), 'var(--red)');
  }
  if (document.getElementById('screenDrawer').classList.contains('open')) setTimeout(refreshScreen, 750);
}

async function launchCustomSku() {
  const sku = document.getElementById('customSkuInput').value.trim();
  if (!sku) return;
  showToast(T('toast_launching', {title: sku}));
  const r = await api('/api/checkout/launch', {sku, lang: curLang});
  if (r.ok) {
    showToast(T('toast_launched', {title: sku}), 'var(--green)');
  } else {
    showToast(T('toast_failed', {err: r.human_error || r.event || r.error || 'Error'}), 'var(--red)');
  }
}

function setOfferFilter(flt, btnEl) {
  curOfferFilter = flt;
  btnEl.parentElement.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');
  renderOffers();
}

async function scanOffers() {
  document.getElementById('offerTbody').innerHTML = `<tr><td colspan="6" style="color:var(--muted);">${escHtml(T('scan_running'))}</td></tr>`;
  const extraRaw = (document.getElementById('extraProbeSkus')?.value || '').trim();
  const extra_skus = extraRaw ? extraRaw.split(/[\s,;]+/).filter(Boolean) : [];
  const r = await api('/api/offers/scan', {lang: curLang, extra_skus});
  cachedOffers = r.offers || [];
  renderOffers();
  refreshStatus();
}

function renderOffers() {
  const tb = document.getElementById('offerTbody');
  if (!cachedOffers.length) {
    tb.innerHTML = `<tr><td colspan="6" style="color:var(--muted);">${escHtml(T('scan_idle'))}</td></tr>`;
    return;
  }
  const q = (document.getElementById('offerSearch').value || '').trim().toLowerCase();
  const rows = cachedOffers.filter(o =>
    (curOfferFilter === 'ALL' || o.type === curOfferFilter) &&
    (!q || o.name.toLowerCase().includes(q) || o.offer_id.toLowerCase().includes(q) || o.product.toLowerCase().includes(q))
  );
  if (!rows.length) {
    tb.innerHTML = `<tr><td colspan="6" style="color:var(--muted);">${escHtml(T('scan_empty'))}</td></tr>`;
    return;
  }
  tb.innerHTML = rows.map((o, idx) => {
    const tagCls = o.type === 'TRIAL' ? 'free' : (o.type === 'PROMO' ? 'promo' : '');
    const btnCls = o.type === 'TRIAL' ? 'btn-success' : 'btn-amber';
    const safeProd = escHtml(o.product);
    const safeOid = escHtml(o.offer_id);
    const safeName = escHtml(o.name);
    return `<tr>
      <td>${idx + 1}</td>
      <td style="font-weight:600;">${safeName}</td>
      <td><span class="tag ${tagCls}">${escHtml(o.badge)}</span></td>
      <td class="ltr-tok">${escHtml(o.pricing_summary)}</td>
      <td><code class="ltr-tok" style="font-size:11.5px;color:var(--muted);">${safeOid}</code></td>
      <td><button class="${btnCls}" style="padding:5px 10px;font-size:12px;" data-sku="${safeProd}" data-oid="${safeOid}" data-paid="${o.type!=='TRIAL'}" data-name="${safeName}" onclick="launchOfferBtn(this)">⚡ ${escHtml(T('btn_instant'))}</button></td>
    </tr>`;
  }).join('');
}

async function launchOfferBtn(btn) {
  const sku = btn.getAttribute('data-sku');
  const offer_id = btn.getAttribute('data-oid');
  const isPaid = btn.getAttribute('data-paid') === 'true';
  const name = btn.getAttribute('data-name');
  if (isPaid && !confirm(T('confirm_paid', {title: name}))) return;
  showToast(T('toast_launching', {title: name}));
  const r = await api('/api/checkout/launch', {sku, offer_id, lang: curLang});
  if (r.ok) {
    showToast(T('toast_launched', {title: name}), 'var(--green)');
  } else {
    showToast(T('toast_failed', {err: r.human_error || r.event || r.error || 'Error'}), 'var(--red)');
  }
}

function refreshScreen() {
  const img = document.getElementById('screenImg');
  img.onload = () => {
    img.style.display = 'block';
    document.getElementById('screenPlaceholder').style.display = 'none';
  };
  img.src = '/api/screen.png?k=' + encodeURIComponent(STUDIO_TOKEN) + '&t=' + Date.now();
}

function toggleMirror() {
  if (document.getElementById('autoMirror').checked) {
    refreshScreen();
    mirrorTimer = setInterval(refreshScreen, 1500);
  } else if (mirrorTimer) {
    clearInterval(mirrorTimer);
    mirrorTimer = null;
  }
}

async function onScreenClick(ev) {
  const img = document.getElementById('screenImg');
  if (img.style.display === 'none') { refreshScreen(); return; }
  const rect = img.getBoundingClientRect();
  const nx = (ev.clientX - rect.left) / rect.width;
  const ny = (ev.clientY - rect.top) / rect.height;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return;

  const boxRect = document.getElementById('screenBox').getBoundingClientRect();
  const dot = document.createElement('div');
  dot.className = 'tap-dot';
  dot.style.left = (ev.clientX - boxRect.left) + 'px';
  dot.style.top = (ev.clientY - boxRect.top) + 'px';
  document.getElementById('screenBox').appendChild(dot);
  setTimeout(() => dot.remove(), 500);

  await api('/api/screen/tap', {nx, ny});
  setTimeout(refreshScreen, 550);
}

async function sendKey(key) { await api('/api/screen/key', {key}); setTimeout(refreshScreen, 450); }
async function openPlaySubs() { await api('/api/subscription/open', {}); }
async function cancelSub() {
  if (!confirm(T('confirm_cancel'))) return;
  await api('/api/subscription/cancel', {});
  refreshStatus();
}
async function promptPasswordFill() {
  const pw = prompt(T('prompt_pw'));
  if (!pw) return;
  await api('/api/checkout/password', {password: pw});
  if (document.getElementById('screenDrawer').classList.contains('open')) setTimeout(refreshScreen, 800);
}
async function runDoctor() {
  await api('/api/doctor', {});
  showToast(T('toast_doctor'), 'var(--green)');
  refreshStatus();
}
async function runAck() {
  const r = await api('/api/purchases/ack', {});
  showToast(T('toast_ack', {c: r.count || 0, a: r.acked || 0}), 'var(--green)');
  refreshStatus();
}
async function switchOrBootMumu() {
  const sel = document.getElementById('mumuSelect');
  const idx = sel.options.length ? parseInt(sel.value, 10) : 0;
  if (isNaN(idx) || idx < 0) return refreshStatus();
  await api('/api/mumu/action', {index: idx});
  refreshStatus();
}

function handleDrop(ev, targetId) {
  ev.preventDefault();
  const f = ev.dataTransfer.files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = e => { document.getElementById(targetId).value = e.target.result; previewBatch(); };
  rd.readAsText(f);
}
function loadFile(ev, targetId) {
  const f = ev.target.files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = e => { document.getElementById(targetId).value = e.target.result; previewBatch(); };
  rd.readAsText(f);
}

async function previewBatch() {
  const r = await api('/api/batch/preview', {
    accounts_text: document.getElementById('acctText').value,
    cards_text: document.getElementById('cardText').value,
  });
  lastParsedBatch = {a: r.accounts_count, e: r.embedded_cards, c: r.cards_count};
  document.getElementById('batchPreviewStat').textContent = T('batch_stat_parsed', lastParsedBatch);
}

async function startBatch() {
  const r = await api('/api/batch/start', {
    accounts_text: document.getElementById('acctText').value,
    cards_text: document.getElementById('cardText').value,
    preset: document.getElementById('batchPresetSel').value,
    card_mode: document.getElementById('batchCardMode').value,
  });
  if (!r.ok) showToast(r.error || 'Error', 'var(--red)');
}
async function stopBatch() { await api('/api/batch/stop', {}); }
async function resolveHuman(action) { await api('/api/batch/human_continue', {action}); }

function loadPrefsIntoForm(p) {
  if (prefsLoadedOnce || !p) return;
  prefsLoadedOnce = true;
  document.getElementById('pfName').value = p.user_name || '';
  document.getElementById('pfReset').value = p.batch_reset || 'smart';
  document.getElementById('pfPostal').value = p.postal_mode || 'classic';
  document.getElementById('pfSound').checked = !!p.sound;
  document.getElementById('pfAnim').checked = !!p.fast_anim;
  document.getElementById('pfCancel').checked = !!p.auto_cancel;
}

async function savePrefs() {
  await api('/api/prefs', {
    lang: curLang,
    user_name: document.getElementById('pfName').value.trim(),
    batch_reset: document.getElementById('pfReset').value,
    postal_mode: document.getElementById('pfPostal').value,
    sound: document.getElementById('pfSound').checked,
    fast_anim: document.getElementById('pfAnim').checked,
    auto_cancel: document.getElementById('pfCancel').checked,
  });
  prefsLoadedOnce = false;
  showToast(T('toast_saved'), 'var(--green)');
  refreshStatus();
}

async function pollLogsAndBatch() {
  try {
    const d = await api('/api/poll');
    const logs = d.logs || [];
    if (logs.length) {
      const latest = document.getElementById('logLatest');
      latest.textContent = logs[logs.length - 1];
      latest.dataset.hasLog = '1';
      const lb = document.getElementById('logBox');
      const atBottom = lb.scrollHeight - lb.scrollTop - lb.clientHeight < 40;
      lb.textContent = logs.join('\n');
      if (atBottom && lb.classList.contains('open')) lb.scrollTop = lb.scrollHeight;
    }

    const b = d.batch;
    const hb = document.getElementById('humanBanner');
    if (b.human_waiting) {
      hb.style.display = 'block';
      document.getElementById('humanMsg').textContent = b.human_message;
    } else {
      hb.style.display = 'none';
    }
    if (b.total > 0) {
      const pct = Math.min(100, Math.round((b.current_index / b.total) * 100));
      document.getElementById('batchBar').style.width = pct + '%';
      document.getElementById('batchRunStat').textContent =
        `${b.running ? '⚡' : '✓'} (${b.current_index}/${b.total}) · OK:${b.ok} · Fail:${b.fail} · Skip:${b.skip} ${b.current_email ? '· ' + b.current_email : ''}`;
      document.getElementById('batchResBody').innerHTML = (b.results || []).map(r =>
        `<tr><td class="ltr-tok">${escHtml(r.email)}</td><td>${escHtml(r.status)}</td><td>${escHtml(r.detail)}</td><td>${escHtml(r.sec)}s</td></tr>`
      ).join('');
    }
  } catch (e) {}
}

initLangSelect();
applyStaticI18n();
refreshStatus();
setInterval(pollLogsAndBatch, 1000);
</script>
</body>
</html>
"""


def _make_handler(state: WebStudioState):
    class StudioHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _check_host_and_origin(self) -> bool:
            raw_host = (self.headers.get("Host") or "").strip().lower()
            if not raw_host:
                return False
            try:
                hp = urllib.parse.urlsplit(f"http://{raw_host}")
                hname = (hp.hostname or "").lower()
                hport = hp.port
            except Exception:
                return False
            if hname not in ("127.0.0.1", "localhost", "::1"):
                return False
            if hport is not None and state.bound_port and hport != state.bound_port:
                return False

            origin = (self.headers.get("Origin") or "").strip()
            if origin:
                try:
                    op = urllib.parse.urlsplit(origin)
                    if (op.hostname or "").lower() not in ("127.0.0.1", "localhost", "::1"):
                        return False
                except Exception:
                    return False
            return True

        def _extract_token(self, parsed: urllib.parse.SplitResult) -> str:
            hdr_tok = (self.headers.get("X-Studio-Token") or "").strip()
            if hdr_tok:
                return hdr_tok
            qs = urllib.parse.parse_qs(parsed.query)
            q_tok = (qs.get("k", [""])[0] or "").strip()
            if q_tok:
                return q_tok
            raw_cookie = self.headers.get("Cookie") or ""
            if raw_cookie:
                try:
                    jar = http.cookies.SimpleCookie()
                    jar.load(raw_cookie)
                    if "gtool_sid" in jar:
                        return jar["gtool_sid"].value.strip()
                except Exception:
                    pass
            return ""

        def _is_authorized(self, parsed: urllib.parse.SplitResult) -> bool:
            tok = self._extract_token(parsed)
            return bool(tok) and secrets.compare_digest(tok, state.auth_token)

        def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> Optional[Dict[str, Any]]:
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            if length > MAX_JSON_BYTES:
                return None
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                parsed_obj = json.loads(body)
                return parsed_obj if isinstance(parsed_obj, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:
            if not self._check_host_and_origin():
                self._send_json({"ok": False, "error": "Forbidden host"}, status=403)
                return

            parsed = urllib.parse.urlsplit(self.path)
            route = parsed.path

            if not self._is_authorized(parsed):
                if route == "/":
                    msg = (
                        "<!DOCTYPE html><html lang='en'><meta charset='utf-8'/>"
                        "<body style='background:#0b0f19;color:#f1f5f9;font-family:sans-serif;padding:40px;'>"
                        "<h2>🔒 401 Unauthorized</h2>"
                        "<p>Please open the full URL with the session token (<code>/?k=...</code>) printed in your terminal.</p>"
                        "</body></html>"
                    ).encode("utf-8")
                    self.send_response(HTTPStatus.UNAUTHORIZED)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                else:
                    self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
                return

            if route == "/":
                init_lang = normalize_lang(state.prefs.get("lang"))
                web_hub_map = {lg: get_localized_web_hub(lg) for lg in SUPPORTED_LANGS}
                rendered = (
                    WEB_HTML.replace("__STUDIO_TOKEN__", json.dumps(state.auth_token))
                    .replace("__I18N_JSON__", json.dumps(WEB_UI_DICT, ensure_ascii=False))
                    .replace("__LANG_META_JSON__", json.dumps(LANG_META, ensure_ascii=False))
                    .replace("__WEB_HUB_JSON__", json.dumps(web_hub_map, ensure_ascii=False))
                    .replace("__INIT_LANG__", json.dumps(init_lang))
                )
                raw = rendered.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header(
                    "Set-Cookie",
                    f"gtool_sid={state.auth_token}; HttpOnly; SameSite=Strict; Path=/",
                )
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

            if route == "/api/screen.png":
                if not state.dev.serial:
                    state.dev.connect_or_boot_device()
                png = state.dev.capture_screenshot_png()
                if not png:
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.end_headers()
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
                return

            if route == "/api/status":
                qs = urllib.parse.parse_qs(parsed.query)
                req_lang = normalize_lang((qs.get("lang", [""])[0] or state.prefs.get("lang")))
                rd = state.dev.probe_radar()
                wiz_raw = analyze_pro_stacking_wizard(rd.get("subscriptions", []), state.billing.offers or None)
                wiz_loc = localize_wizard(wiz_raw, req_lang)
                presets_loc = []
                for p in localize_presets(PRESETS, req_lang):
                    p_copy = dict(p)
                    p_copy.update(evaluate_preset_eligibility(p_copy, state.billing.offers))
                    presets_loc.append(p_copy)
                self._send_json({
                    "lang": normalize_lang(state.prefs.get("lang")),
                    "radar": rd,
                    "wizard": wiz_loc,
                    "presets": presets_loc,
                    "prefs": state.prefs,
                    "greeting": time_greeting_i18n(state.prefs.get("user_name", ""), req_lang),
                    "motto": active_motto_i18n(state.prefs, req_lang),
                })
                return

            if route == "/api/offers/localized":
                lg = normalize_lang(state.prefs.get("lang"))
                self._send_json({
                    "offers": [localize_offer(o, lg) for o in state.billing.offers],
                })
                return

            if route == "/api/poll":
                if state.billing.is_alive():
                    state.billing.drain_events()
                self._send_json({
                    "logs": state.get_logs(),
                    "batch": state.batch.snapshot(),
                })
                return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def do_POST(self) -> None:
            if not self._check_host_and_origin():
                self._send_json({"ok": False, "error": "Forbidden host"}, status=403)
                return

            parsed = urllib.parse.urlsplit(self.path)
            if not self._is_authorized(parsed):
                self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
                return

            route = parsed.path
            body = self._read_json()
            if body is None:
                self._send_json({"ok": False, "error": "Payload too large"}, status=413)
                return

            if route == "/api/doctor":
                res = state.dev.run_doctor(auto_fix=True, local_port=state.billing.local_port)
                self._send_json(res)
                return

            if route == "/api/open_url":
                target_url = str(body.get("url", "") or "").strip()
                if not is_allowed_external_url(target_url):
                    self._send_json({"ok": False, "error": "URL host not in allowed whitelist"}, status=400)
                    return
                opened = webbrowser.open(target_url)
                state.add_log(f"[+] Opened Web Portal: {target_url}")
                self._send_json({"ok": bool(opened)})
                return

            if route == "/api/webhub/decode_sc":
                raw_sc = str(body.get("sc", "") or "")
                self._send_json(decode_shelf_sc(raw_sc))
                return

            if route == "/api/mumu/action":
                try:
                    idx = int(body.get("index", 0))
                except (TypeError, ValueError):
                    self._send_json({"ok": False, "error": "Invalid index"}, status=400)
                    return
                state.billing.close()
                state.dev.ensure_host_tools()
                from .platform_env import list_mumu_instances
                m_list = list_mumu_instances(state.dev.adb)
                target = next((m for m in m_list if m["index"] == idx), None)
                ok = False
                if target and target["running"] and target["adb_port"]:
                    state.dev.serial = f"127.0.0.1:{target['adb_port']}"
                    state.dev.instance_name = target["name"]
                    ok = state.dev.connect_or_boot_device(preferred_port=target["adb_port"])
                    state.add_log(f"[+] Switched to MuMu [{target['name']}] ({state.dev.serial})")
                else:
                    state.dev.serial = ""
                    ok = state.dev.boot_mumu_and_wait(idx)
                self._send_json({"ok": ok})
                return

            if route == "/api/offers/scan":
                lg = normalize_lang(str(body.get("lang") or state.prefs.get("lang") or "zh"))
                raw_extra = body.get("extra_skus")
                extra_list = [str(s).strip() for s in raw_extra if str(s).strip()] if isinstance(raw_extra, list) else None
                was_alive = state.billing.is_alive()
                ok = state.billing.start_or_reuse(force_restart_app=False, extra_skus=extra_list)
                if ok and was_alive and not extra_list:
                    ok, _ = state.billing.send_command("REFRESH", ("INTERACTIVE_READY", "BROWSE_COMPLETE"), timeout=12.0)
                self._send_json({
                    "ok": ok,
                    "offers": [localize_offer(o, lg) for o in state.billing.offers],
                    "missed_skus": state.billing.missed_skus,
                    "scan_trace": state.billing.scan_trace,
                })
                return

            if route == "/api/checkout/launch":
                lg = normalize_lang(str(body.get("lang") or state.prefs.get("lang") or "zh"))
                preset_key = str(body.get("preset", "") or "")
                if preset_key:
                    p = resolve_preset(preset_key)
                    if not p:
                        self._send_json({"ok": False, "error": "Unknown preset", "human_error": "Unknown preset"})
                        return
                    ok, ev = state.billing.launch_preset_or_sku(p["sku"], p["offer_id"], stack=p["stack"])
                    state.prefs["last_action"] = {
                        "mode": "preset", "sku": p["sku"], "offer_id": p["offer_id"],
                        "stack": p["stack"], "is_paid": p["is_paid"], "label": p["title"],
                    }
                    save_prefs(state.prefs)
                    notify_user(state.prefs, "info" if ok else "error", p["title"])
                    self._send_json({"ok": ok, "event": ev, "human_error": "" if ok else humanize_launch_error(ev, lg)})
                    return

                sku = str(body.get("sku", "") or "").strip()
                offer_id = str(body.get("offer_id", "") or "").strip()
                stack = bool(body.get("stack", False))
                ok, ev = state.billing.launch_preset_or_sku(sku, offer_id, stack=stack)
                self._send_json({"ok": ok, "event": ev, "human_error": "" if ok else humanize_launch_error(ev, lg)})
                return

            if route == "/api/checkout/password":
                pw = str(body.get("password", "") or "")
                ok = state.dev.handle_billing_password(pw) if pw else False
                if ok:
                    state.dev.handle_post_payment()
                self._send_json({"ok": ok})
                return

            if route == "/api/purchases/ack":
                res = state.billing.sync_and_acknowledge()
                self._send_json(res)
                return

            if route == "/api/subscription/open":
                state.dev.connect_or_boot_device()
                state.dev.shell(
                    "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1 "
                    "|| am start -a android.intent.action.VIEW -d 'https://play.google.com/store/account/subscriptions' >/dev/null 2>&1"
                )
                self._send_json({"ok": True})
                return

            if route == "/api/subscription/cancel":
                state.dev.connect_or_boot_device()
                ok = state.dev.cancel_subscription()
                self._send_json({"ok": ok})
                return

            if route == "/api/screen/tap":
                try:
                    nx = float(body.get("nx", 0.5))
                    ny = float(body.get("ny", 0.5))
                except (TypeError, ValueError):
                    self._send_json({"ok": False, "error": "Invalid coordinates"}, status=400)
                    return
                x, y = state.dev.tap_normalized(nx, ny)
                state.add_log(f"[*] Tap: ({x}, {y})")
                self._send_json({"ok": True, "x": x, "y": y})
                return

            if route == "/api/screen/key":
                key = str(body.get("key", "KEYCODE_BACK"))
                state.dev.press_key(key)
                self._send_json({"ok": True})
                return

            if route == "/api/batch/preview":
                accts = parse_accounts_text(str(body.get("accounts_text", "") or ""))
                cards = parse_cards_text(str(body.get("cards_text", "") or ""))
                emb = sum(1 for a in accts if a.get("card"))
                self._send_json({
                    "accounts_count": len(accts),
                    "cards_count": len(cards),
                    "embedded_cards": emb,
                })
                return

            if route == "/api/batch/start":
                if state.batch.running:
                    self._send_json({"ok": False, "error": "Batch already running"})
                    return
                accts = parse_accounts_text(str(body.get("accounts_text", "") or ""))
                cards = parse_cards_text(str(body.get("cards_text", "") or ""))
                if not accts:
                    self._send_json({"ok": False, "error": "No valid accounts found"})
                    return
                if not cards and any(not a.get("card") for a in accts):
                    self._send_json({"ok": False, "error": "Cards required for accounts without embedded cards"})
                    return
                p = resolve_preset(str(body.get("preset", "pro12") or "pro12")) or PRESETS[0]
                state.billing.close()
                started = state.batch.start_async(
                    accounts=accts,
                    cards=cards,
                    sku=p["sku"],
                    offer_id=p["offer_id"],
                    stack=p["stack"],
                    is_paid=p["is_paid"],
                    plan_label=p["title"],
                    card_mode=str(body.get("card_mode", "rotate") or "rotate"),
                    human_cb=None,
                )
                self._send_json({"ok": started})
                return

            if route == "/api/batch/stop":
                state.batch.request_stop()
                self._send_json({"ok": True})
                return

            if route == "/api/batch/human_continue":
                state.dev.human_gate.resolve(str(body.get("action", "continue")))
                self._send_json({"ok": True})
                return

            if route == "/api/prefs":
                if "lang" in body and body["lang"] in SUPPORTED_LANGS:
                    state.prefs["lang"] = body["lang"]
                for k in ("user_name", "persona", "motto", "batch_reset", "postal_mode", "sound", "fast_anim", "auto_cancel"):
                    if k in body:
                        state.prefs[k] = body[k]
                save_prefs(state.prefs)
                self._send_json({"ok": True, "prefs": state.prefs})
                return

            self._send_json({"ok": False, "error": "Not found"}, status=404)

    return StudioHandler


def _find_free_web_port(start: int = 8765) -> int:
    for p in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_web_studio(port: Optional[int] = None, open_browser: bool = True, token: Optional[str] = None) -> int:
    actual_port = port or _find_free_web_port(8765)
    state = WebStudioState(token=token, bound_port=actual_port)
    server = QuietThreadingHTTPServer(("127.0.0.1", actual_port), _make_handler(state))
    actual_port = int(server.server_address[1])
    state.bound_port = actual_port
    url = f"http://127.0.0.1:{actual_port}/?k={state.auth_token}"

    print("\n╔══════════════════════════════════════════════════════════════════════════╗")
    print("║        🌐  Google AI Trial Web Studio · Multilingual Clean UI            ║")
    print("╠══════════════════════════════════════════════════════════════════════════╣")
    print(f"║  URL      : {url:<60} ║")
    print(f"║  Blog     : {BLOG_URL:<60} ║")
    print(f"║  GPT Shop : {FAKA_URL:<60} ║")
    print("║  Security : 127.0.0.1 Loopback + Session Token + Host Rebinding Guard    ║")
    print("╚══════════════════════════════════════════════════════════════════════════╝\n")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Web Studio...")
    finally:
        state.billing.close()
        server.server_close()
    return 0
