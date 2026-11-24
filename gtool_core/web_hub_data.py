#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/web_hub_data.py — Official Google Web Ecosystem Portals, Hidden Perks, OR-* Diagnostics & ?sc= Shelf Codec."""

from __future__ import annotations

import base64
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_WEB_DOMAINS = (
    "one.google.com",
    "payments.google.com",
    "play.google.com",
    "families.google.com",
    "myaccount.google.com",
    "aistudio.google.com",
    "developers.google.com",
    "colab.research.google.com",
    "antigravity.google",
    "labs.google",
    "flow.google",
    "www.flowmusic.app",
    "flowmusic.app",
    "playground.google",
    "notebooklm.google.com",
    "gemini.google.com",
    "home.google.com",
    "store.google.com",
    "www.youtube.com",
    "youtube.com",
    "support.google.com",
    "blog.caowo.de",
    "faka.cdkey.si",
)

# Official Google One ?sc= Protobuf Shelf IDs discovered on one.google.com/about/google-ai-plans/
# Wire layout: 22 02 10 01 52 06 0a 04 08 <tier_varint> 10 <mode_varint>
SHELF_TIERS: Dict[int, str] = {
    7: "Google AI Ultra (20TB 5x / 30TB 20x · Gemini 4 Carbon)",
    23: "Google AI Plus (400GB / 2TB · Gemini 4 Hydrogen)",
    36: "Google AI Pro (5TB · Gemini 4 Neon)",
}


def _encode_varint(val: int) -> bytes:
    if val < 0:
        raise ValueError("varint must be non-negative")
    out = bytearray()
    while val > 0x7F:
        out.append((val & 0x7F) | 0x80)
        val >>= 7
    out.append(val & 0x7F)
    return bytes(out)


def _decode_varint(buf: bytes, idx: int) -> Tuple[int, int]:
    shift = 0
    result = 0
    while idx < len(buf):
        b = buf[idx]
        idx += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, idx
        shift += 7
    raise ValueError("truncated varint")


def encode_shelf_sc(tier_id: int, cadence_mode: int = 3) -> str:
    """Build official URL-safe Base64 ?sc= Protobuf parameter for https://one.google.com/ai?sc=..."""
    inner = b"\x08" + _encode_varint(int(tier_id)) + b"\x10" + _encode_varint(int(cadence_mode))
    field_10_sub = b"\x0a" + _encode_varint(len(inner)) + inner
    msg = b"\x22\x02\x10\x01\x52" + _encode_varint(len(field_10_sub)) + field_10_sub
    return base64.urlsafe_b64encode(msg).decode("ascii").rstrip("=")


def inspect_ear_checkout_url(raw_url_or_ear: str) -> Dict[str, Any]:
    """Read-only forensic decoder for tokenized.play.google.com/eacquire/multiline?ear=... links.
    Audits target SKUs, add-ons, proration mode, and static BotGuard/User-Agent fingerprint leaks in ear[4][0].
    """
    import json
    import re

    txt = (raw_url_or_ear or "").strip()
    ear_str = txt
    if "ear=" in txt or "://" in txt:
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(txt).query)
        ear_str = (qs.get("ear") or [""])[0]
    if not ear_str:
        return {"ok": False, "error": "Missing ear parameter"}
    try:
        ear = json.loads(ear_str)
    except Exception as exc:
        return {"ok": False, "error": f"Invalid ear JSON: {exc}"}
    if not isinstance(ear, list):
        return {"ok": False, "error": "ear root is not a JSON array"}

    skus: List[str] = []
    offer_token_count = 0
    try:
        items_group = ear[13][0] if len(ear) > 13 and isinstance(ear[13], list) and ear[13] else []
        for item in items_group:
            if isinstance(item, list) and item:
                head = item[0]
                if isinstance(head, list) and head:
                    skus.append(str(head[0]))
                if len(item) > 5 and isinstance(item[5], list):
                    offer_token_count += len([t for t in item[5] if t])
    except Exception:
        pass

    proration_mode = None
    has_sub_id = False
    if len(ear) > 8 and isinstance(ear[8], list):
        if len(ear[8]) > 1:
            proration_mode = ear[8][1]
        if len(ear[8]) > 5 and isinstance(ear[8][5], list) and ear[8][5]:
            has_sub_id = True

    fp_leak = False
    embedded_ua = ""
    has_botguard_sig = False
    if len(ear) > 4 and isinstance(ear[4], list) and ear[4] and isinstance(ear[4][0], str):
        b64 = ear[4][0]
        pad = b64 + ("=" * ((4 - len(b64) % 4) % 4))
        try:
            dec4 = base64.b64decode(pad).decode("utf-8", errors="replace")
            if "Rs2." in dec4 or ":::s" in dec4:
                has_botguard_sig = True
                fp_leak = True
            m_ua = re.search(r"Mozilla/5\.0 \([^)]+\)[^\"]*", dec4)
            if m_ua:
                embedded_ua = m_ua.group(0)[:78]
                fp_leak = True
        except Exception:
            pass

    return {
        "ok": True,
        "kind": "ear",
        "skus": skus,
        "offer_token_count": offer_token_count,
        "proration_mode": proration_mode,
        "has_sub_id": has_sub_id,
        "fp_leak": fp_leak,
        "has_botguard_sig": has_botguard_sig,
        "embedded_ua": embedded_ua,
    }


def decode_shelf_sc(sc_or_url: str) -> Dict[str, Any]:
    """Decode an official ?sc= Base64 Protobuf string OR inspect an eacquire/multiline?ear=... URL."""
    raw_in = (sc_or_url or "").strip()
    if not raw_in:
        return {"ok": False, "error": "empty"}
    if "eacquire/multiline" in raw_in or "ear=" in raw_in or raw_in.startswith("[null,"):
        return inspect_ear_checkout_url(raw_in)
    if "://" in raw_in or "sc=" in raw_in:
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(raw_in).query)
        raw_in = (qs.get("sc") or [raw_in])[0]
    padded = raw_in + ("=" * ((4 - len(raw_in) % 4) % 4))
    try:
        buf = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        return {"ok": False, "error": f"invalid base64: {exc}"}

    tier_id: Optional[int] = None
    cadence_mode: Optional[int] = None
    try:
        # Locate inner 0a <len> 08 <tier> 10 <mode>
        pos = buf.find(b"\x52")
        if pos >= 0 and pos + 4 < len(buf):
            _, idx = _decode_varint(buf, pos + 1)
            if idx < len(buf) and buf[idx] == 0x0A:
                _, idx = _decode_varint(buf, idx + 1)
                while idx < len(buf):
                    tag, idx = _decode_varint(buf, idx)
                    field_no, wire = tag >> 3, tag & 0x07
                    if wire != 0:
                        break
                    val, idx = _decode_varint(buf, idx)
                    if field_no == 1:
                        tier_id = val
                    elif field_no == 2:
                        cadence_mode = val
    except Exception:
        pass

    return {
        "ok": True,
        "sc": raw_in,
        "hex": buf.hex(" "),
        "byte_len": len(buf),
        "tier_id": tier_id,
        "tier_name": SHELF_TIERS.get(tier_id or -1, f"Unknown Shelf Tier ({tier_id})"),
        "cadence_mode": cadence_mode,
        "url": f"https://one.google.com/ai?sc={urllib.parse.quote(raw_in)}&hl=en-US",
    }


def is_allowed_external_url(url: str) -> bool:
    try:
        sp = urllib.parse.urlsplit((url or "").strip())
        if sp.scheme != "https":
            return False
        host = (sp.hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in ALLOWED_WEB_DOMAINS)
    except Exception:
        return False


WEB_HUB_UI: Dict[str, Dict[str, str]] = {
    "zh": {
        "tab_webhub": "网页生态",
        "wh_headline": "Google 网页版订阅总控 · 隐藏回血权益与付款风控中心",
        "wh_sub": "支持多账号 authuser 秒切，直达 one.google.com 隐藏货架、领每月最高 $100 Cloud 赠金与 2000 Colab 算力",
        "wh_acct_lbl": "账号槽位",
        "wh_seg_portals": "订阅与货架",
        "wh_seg_perks": "隐藏回血权益",
        "wh_seg_risk": "付款资料与家庭组",
        "wh_btn_open": "打开网页",
        "wh_or_title": "payments.google.com 报错码 (OR-*) 速查诊断",
        "wh_or_ph": "输入报错码，如 OR-HDT-01 / OR-CCSEH-21 / OR-FGEMF-20...",
        "wh_sc_title": "one.google.com 官方 ?sc= 货架参数解码 / 生成器",
        "wh_sc_ph": "粘贴 ?sc= 参数或完整链接（如 IgIQAVIGCgQIBxAD）",
        "wh_btn_decode": "解析参数",
        "wh_family_note": "💡 母号 vs 家庭组铁律：20TB/30TB 存储、Gemini 4 Carbon、Antigravity(含 Claude Sonnet) 与 Flow 池化额度支持 5 名家庭成员共享；但每月 $10/$40/$100 Cloud API 赠金与 200/2000 Colab 算力仅限主号管理员独享，且 YouTube 家庭版必须由家庭管理员本人直购 Ultra 才可共享。",
    },
    "en": {
        "tab_webhub": "Web Hub",
        "wh_headline": "Google Web Portals · Hidden Perks & Payments Diagnostics",
        "wh_sub": "Switch authuser slots cleanly, open hidden ?sc= shelves, and claim up to $100/mo Cloud credits & 2,000 Colab CCUs",
        "wh_acct_lbl": "Account Slot",
        "wh_seg_portals": "Plans & Shelves",
        "wh_seg_perks": "Hidden Perks",
        "wh_seg_risk": "Payments & Family",
        "wh_btn_open": "Open Portal",
        "wh_or_title": "Google Payments Error Code (OR-*) Instant Doctor",
        "wh_or_ph": "Type error code, e.g. OR-HDT-01 / OR-CCSEH-21 / OR-FGEMF-20...",
        "wh_sc_title": "Official one.google.com ?sc= Shelf Protobuf Decoder",
        "wh_sc_ph": "Paste ?sc= token or URL (e.g. IgIQAVIGCgQIBxAD)",
        "wh_btn_decode": "Decode",
        "wh_family_note": "💡 Family Sharing Rule: Storage (5–30TB), Gemini 4 Carbon, Antigravity (incl. Claude Sonnet on Ultra) & pooled Flow credits share with 5 members; $10/$40/$100 Cloud API credits & 200/2,000 Colab CCUs stay strictly on the Plan Manager, and YouTube Premium Family requires the Family Manager to purchase Ultra directly.",
    },
    "ar": {
        "tab_webhub": "مركز الويب",
        "wh_headline": "مركز خدمات Google على الويب · المزايا المخفية وتشخيص الدفع",
        "wh_sub": "التبديل السريع بين الحسابات، فتح روابط الباقات المباشرة، واستلام رصيد السحابة حتى $100 شهرياً ووحدات Colab",
        "wh_acct_lbl": "ترتيب الحساب",
        "wh_seg_portals": "الباقات والعروض",
        "wh_seg_perks": "المزايا الإضافية",
        "wh_seg_risk": "الدفع والعائلة",
        "wh_btn_open": "فتح الرابط",
        "wh_or_title": "تشخيص رموز أخطاء الدفع (OR-*)",
        "wh_or_ph": "أدخل رمز الخطأ مثل OR-HDT-01 أو OR-FGEMF-20...",
        "wh_sc_title": "محلل معرّف العرض الرسمي (?sc=) في Google One",
        "wh_sc_ph": "الصق رمز sc أو الرابط مثل IgIQAVIGCgQIBxAD",
        "wh_btn_decode": "تحليل",
        "wh_family_note": "💡 قاعدة مشاركة العائلة: السعة التخزينية وGemini 4 Carbon وAntigravity تُشارك مع 5 أفراد؛ أما رصيد Google Cloud الشهري ($10/$40/$100) ووحدات Colab فهي حصرية لمدير الخطة فقط.",
    },
    "ru": {
        "tab_webhub": "Веб-центр",
        "wh_headline": "Веб-экосистема Google · Скрытые бонусы и диагностика платежей",
        "wh_sub": "Быстрое переключение authuser, прямые полки ?sc=, получение до $100/мес. Cloud кредитов и 2000 CCU Colab",
        "wh_acct_lbl": "Слот аккаунта",
        "wh_seg_portals": "Полки и тарифы",
        "wh_seg_perks": "Скрытые бонусы",
        "wh_seg_risk": "Оплата и Семья",
        "wh_btn_open": "Открыть",
        "wh_or_title": "Справочник ошибок Google Payments (OR-*)",
        "wh_or_ph": "Введите код ошибки, напр. OR-HDT-01 / OR-CCSEH-21...",
        "wh_sc_title": "Декодер параметров полки ?sc= (Protobuf)",
        "wh_sc_ph": "Вставьте ?sc= или URL (напр. IgIQAVIGCgQIBxAD)",
        "wh_btn_decode": "Декодировать",
        "wh_family_note": "💡 Правило семейной группы: Хранилище, Gemini 4 Carbon, Antigravity (вкл. Claude Sonnet в Ultra) делятся на 5 участников; кредиты Cloud ($10/$40/$100) и Colab (200/2000 CCU) доступны только организатору плана.",
    },
    "es": {
        "tab_webhub": "Centro Web",
        "wh_headline": "Ecosistema Web de Google · Beneficios Ocultos y Pagos",
        "wh_sub": "Cambio rápido de cuenta authuser, enlaces ?sc= directos y reclamo de hasta $100/mes en Cloud y 2000 CCU en Colab",
        "wh_acct_lbl": "Cuenta (Slot)",
        "wh_seg_portals": "Planes y Ofertas",
        "wh_seg_perks": "Beneficios Extra",
        "wh_seg_risk": "Pagos y Familia",
        "wh_btn_open": "Abrir Web",
        "wh_or_title": "Diagnóstico de errores Google Payments (OR-*)",
        "wh_or_ph": "Escribe el código, ej. OR-HDT-01 / OR-CCSEH-21...",
        "wh_sc_title": "Decodificador oficial de parámetro ?sc= (Protobuf)",
        "wh_sc_ph": "Pega el token ?sc= o URL (ej. IgIQAVIGCgQIBxAD)",
        "wh_btn_decode": "Analizar",
        "wh_family_note": "💡 Regla Familiar: El almacenamiento, Gemini 4 Carbon y Antigravity (incl. Claude Sonnet en Ultra) se comparten con 5 miembros; los créditos Cloud ($10/$40/$100) y Colab (200/2000 CCU) son exclusivos del administrador.",
    },
}


WEB_PORTALS: List[Dict[str, Any]] = [
    # --- Group: portals (Plans & Shelves) ---
    {
        "id": "shelf_ultra",
        "group": "portals",
        "badge": "Shelf #7 · Ultra",
        "tag_cls": "promo",
        "url_tpl": "https://one.google.com/u/{u}/ai?sc=IgIQAVIGCgQIBxAD&hl={hl}",
        "zh": ("Google AI Ultra 网页直达货架", "直拉 Ultra 5x (20TB) / 20x (30TB) 官方购买与升级货架（含 Gemini 4 Carbon）"),
        "en": ("Google AI Ultra Direct Shelf", "Official ?sc= Shelf #7 for Ultra 5x (20TB) & 20x (30TB) with Gemini 4 Carbon"),
        "ar": ("رف Google AI Ultra المباشر", "الرابط الرسمي لباقة Ultra 5x/20x مع نموذج Gemini 4 Carbon"),
        "ru": ("Прямая полка Google AI Ultra", "Официальная витрина Ultra 5x (20TB) и 20x (30TB) с Gemini 4 Carbon"),
        "es": ("Estante directo Google AI Ultra", "Acceso oficial Shelf #7 para Ultra 5x (20TB) y 20x (30TB)"),
    },
    {
        "id": "shelf_pro",
        "group": "portals",
        "badge": "Shelf #36 · Pro",
        "tag_cls": "free",
        "url_tpl": "https://one.google.com/u/{u}/ai?sc=IgIQAVIGCgQIJBAD&hl={hl}",
        "zh": ("Google AI Pro 5TB 网页货架", "直拉 AI Pro (5TB · $19.99/月) 官方网页端方案卡与当季大促折扣入口"),
        "en": ("Google AI Pro 5TB Direct Shelf", "Official ?sc= Shelf #36 for AI Pro (5TB) & seasonal web discounts"),
        "ar": ("رف Google AI Pro 5TB المباشر", "الرابط الرسمي لباقة AI Pro 5TB والعروض الموسمية"),
        "ru": ("Прямая полка Google AI Pro 5TB", "Официальная витрина AI Pro (5TB) и сезонных веб-скидок"),
        "es": ("Estante directo Google AI Pro 5TB", "Acceso oficial Shelf #36 para AI Pro (5TB) y descuentos web"),
    },
    {
        "id": "shelf_plus",
        "group": "portals",
        "badge": "Shelf #23 · Plus",
        "tag_cls": "free",
        "url_tpl": "https://one.google.com/u/{u}/ai?sc=IgIQAVIGCgQIFxAD&hl={hl}",
        "zh": ("Google AI Plus 轻量货架", "400GB ($4.99/月) 与 2TB ($9.99/月) 入门档，含 Gemini 4 Hydrogen"),
        "en": ("Google AI Plus Direct Shelf", "400GB ($4.99/mo) & 2TB ($9.99/mo) tiers with Gemini 4 Hydrogen"),
        "ar": ("رف Google AI Plus المباشر", "باقات 400GB و2TB الاقتصادية مع Gemini 4 Hydrogen"),
        "ru": ("Прямая полка Google AI Plus", "Тарифы 400 ГБ ($4.99) и 2 ТБ ($9.99) с Gemini 4 Hydrogen"),
        "es": ("Estante directo Google AI Plus", "Planes de 400GB ($4.99) y 2TB ($9.99) con Gemini 4 Hydrogen"),
    },
    {
        "id": "student_offer",
        "group": "portals",
        "badge": "SheerID · 1Yr $0",
        "tag_cls": "free",
        "url_tpl": "https://one.google.com/ai-student?authuser={u}&hl={hl}",
        "zh": ("高校学生 1 年免费 Pro 通道", "个人 Gmail 通过 SheerID 学籍验证享 1 年免费 AI Pro 或 $8.99 含 YT Premium（最长4年）"),
        "en": ("Student 1-Year Free AI Pro", "SheerID verification on personal Gmail: 1yr $0 AI Pro or $8.99 w/ YT Premium"),
        "ar": ("عرض الطلاب: سنة مجانية AI Pro", "توثيق SheerID لحساب Gmail الشخصي للحصول على سنة مجانية"),
        "ru": ("Студенческий оффер: 1 год Pro за $0", "Верификация SheerID на личный Gmail: 1 год бесплатно или $8.99 с YT Premium"),
        "es": ("Oferta Estudiantes: 1 Año Pro Gratis", "Verificación SheerID en Gmail personal: 1 año gratis o $8.99 con YT Premium"),
    },
    {
        "id": "ai_credits",
        "group": "portals",
        "badge": "AI Credits",
        "tag_cls": "promo",
        "url_tpl": "https://one.google.com/u/{u}/ai/credits?hl={hl}",
        "zh": ("Google One AI 额度余额与流水", "查看跨 Gemini / Flow / Antigravity 共享的 AI Credits 余额与成员消耗排行"),
        "en": ("Google One AI Credits Balance", "View pooled AI Credits & family usage breakdown across Gemini, Flow & Antigravity"),
        "ar": ("رصيد نقاط Google AI", "متابعة رصيد نقاط الذكاء الاصطناعي واستهلاك أفراد العائلة"),
        "ru": ("Баланс и история AI Credits", "Остаток и расход AI-кредитов в Gemini, Flow и Antigravity"),
        "es": ("Saldo de Créditos Google AI", "Consulta créditos compartidos en Gemini, Flow y Antigravity"),
    },
    {
        "id": "play_web_subs",
        "group": "portals",
        "badge": "Cancel / Renew",
        "tag_cls": "free",
        "url_tpl": "https://play.google.com/store/account/subscriptions?authuser={u}&hl={hl}",
        "zh": ("Google Play 网页版订阅管理", "核对试用真实到期日、恢复订阅或一键取消自动续费（无需打开模拟器）"),
        "en": ("Google Play Web Subscriptions", "Verify exact trial expiry date, resubscribe, or cancel auto-renewal in browser"),
        "ar": ("إدارة اشتراكات Google Play ويب", "التحقق من تاريخ انتهاء التجربة أو إلغاء التجديد التلقائي من المتصفح"),
        "ru": ("Веб-управление подписками Play", "Проверка точной даты окончания триала и отмена автопродления в браузере"),
        "es": ("Suscripciones Web de Google Play", "Verifica fecha exacta de vencimiento o cancela la renovación sin emulador"),
    },

    # --- Group: perks (Hidden High-Value Perks) ---
    {
        "id": "perk_gcp_credits",
        "group": "perks",
        "badge": "$10 / $40 / $100 mo",
        "tag_cls": "free",
        "url_tpl": "https://developers.google.com/program/my-benefits?authuser={u}&hl={hl}",
        "zh": ("Google Developer Program 领月度赠金", "AI Pro $10/月 · Ultra 5x $40/月 · Ultra 20x $100/月 Cloud/Vertex API 赠金（仅限主号）"),
        "en": ("Claim Monthly Cloud / GenAI Credits", "Pro: $10/mo · Ultra 5x: $40/mo · Ultra 20x: $100/mo via Developer Program (manager only)"),
        "ar": ("استلام رصيد Google Cloud الشهري", "$10 لـ Pro · $40 لـ Ultra 5x · $100 شهرياً لـ Ultra 20x عبر برنامج المطورين"),
        "ru": ("Забрать ежемесячные кредиты Cloud API", "Pro: $10/мес · Ultra 5x: $40/мес · Ultra 20x: $100/мес в Developer Program"),
        "es": ("Reclamar créditos mensuales Cloud API", "Pro: $10/mes · Ultra 5x: $40/mes · Ultra 20x: $100/mes en Developer Program"),
    },
    {
        "id": "perk_aistudio",
        "group": "perks",
        "badge": "AI Studio · API",
        "tag_cls": "free",
        "url_tpl": "https://aistudio.google.com/?authuser={u}",
        "zh": ("Google AI Studio 绑定计费与 API 调试", "挂载已领赠金的 GCP 结算账户，零成本调用 Gemini 高并发 API"),
        "en": ("Google AI Studio & Billing Link", "Attach your credited GCP project to run high-RPM Gemini API workloads"),
        "ar": ("منصة Google AI Studio وربط الفوترة", "ربط مشروع السحابة لاستخدام واجهات Gemini البرمجية مجاناً بالرصيد"),
        "ru": ("Google AI Studio и привязка биллинга", "Подключите GCP-проект с бонусами для работы с Gemini API"),
        "es": ("Google AI Studio y facturación API", "Vincula tu proyecto GCP con crédito mensual para usar Gemini API"),
    },
    {
        "id": "perk_colab",
        "group": "perks",
        "badge": "200 / 2,000 CCU",
        "tag_cls": "free",
        "url_tpl": "https://colab.research.google.com/?authuser={u}",
        "zh": ("Google Colab 高性能 GPU 算力包", "AI Pro 赠 200 CCU/月 · Ultra 赠 1000~2000 CCU/月 + A100/L4 长时后台（仅主号）"),
        "en": ("Google Colab Pro+ GPU Compute Units", "200 CCU/mo (Pro) or 1,000–2,000 CCU/mo (Ultra) + premium GPUs (manager only)"),
        "ar": ("وحدات حوسبة Google Colab GPU", "200 وحدة لـ Pro وحتى 2000 وحدة شهرياً لـ Ultra (للمدير فقط)"),
        "ru": ("Вычислительные единицы Google Colab", "200 CCU/мес (Pro) или до 2000 CCU/мес (Ultra) + A100/L4 GPU"),
        "es": ("Unidades de cómputo Google Colab GPU", "200 CCU/mes (Pro) o hasta 2,000 CCU/mes (Ultra) con GPUs premium"),
    },
    {
        "id": "perk_antigravity",
        "group": "perks",
        "badge": "Claude Sonnet · 5h",
        "tag_cls": "promo",
        "url_tpl": "https://antigravity.google/docs/plans",
        "zh": ("Antigravity 第三方模型 (Claude) 权益", "每 5 小时刷新高优额度；Ultra 独享调用 Claude Sonnet 等第三方模型（可家庭共享）"),
        "en": ("Antigravity Quota & Claude Sonnet", "5-hour refreshing agent quota; Ultra unlocks 3rd-party models incl. Claude Sonnet"),
        "ar": ("مزايا Antigravity ونماذج Claude", "حصة تتجدد كل 5 ساعات؛ باقة Ultra تفتح نماذج الطرف الثالث مثل Claude Sonnet"),
        "ru": ("Квоты Antigravity и доступ к Claude", "Обновление лимитов каждые 5ч; Ultra открывает сторонние модели (Claude Sonnet)"),
        "es": ("Cuotas Antigravity y Claude Sonnet", "Cuota cada 5h; Ultra desbloquea modelos de terceros como Claude Sonnet"),
    },
    {
        "id": "perk_yt_premium",
        "group": "perks",
        "badge": "YT Family / Lite",
        "tag_cls": "promo",
        "url_tpl": "https://www.youtube.com/paid_memberships?authuser={u}",
        "zh": ("YouTube 家庭版 / Lite 激活与防重扣", "Ultra 含 6 人 YT 家庭版（须家庭管理员直购）；Pro 含个人 Lite（转正生效，注意退旧订）"),
        "en": ("YouTube Premium Family / Lite Check", "Ultra includes YT Family (requires Family Manager purchase); cancel old YT subs to avoid double billing"),
        "ar": ("تفعيل YouTube Premium العائلي / Lite", "باقة Ultra تشمل خطة العائلة (يجب الشراء بحساب مدير العائلة)"),
        "ru": ("Проверка YouTube Premium Family / Lite", "Ultra включает семейный YT Premium (покупка с аккаунта главы семьи)"),
        "es": ("Activar YouTube Premium Familiar / Lite", "Ultra incluye plan Familiar (requiere compra directa del administrador familiar)"),
    },
    {
        "id": "perk_genie_flow",
        "group": "perks",
        "badge": "Veo 3.1 & Genie 3",
        "tag_cls": "free",
        "url_tpl": "https://labs.google/fx",
        "zh": ("Project Genie 世界模型 & Flow 影视台", "直达 flow.google (Veo 3.1) 与 Project Genie 实时世界生成（Genie 仅限 Ultra 20x 30TB）"),
        "en": ("Project Genie 3 & Google Flow Studio", "Access flow.google (Veo 3.1), flowmusic.app & Project Genie (Ultra 20x exclusive)"),
        "ar": ("استوديو Google Flow ومشروع Genie", "توليد الفيديو عبر Veo 3.1 والعوالم التفاعلية في Genie (حصري لـ Ultra 20x)"),
        "ru": ("Project Genie 3 и студия Google Flow", "Генерация видео Veo 3.1 и интерактивных миров Genie (эксклюзив Ultra 20x)"),
        "es": ("Project Genie 3 y Google Flow Studio", "Cine IA con Veo 3.1 y mundos interactivos en Genie (exclusivo Ultra 20x)"),
    },
    {
        "id": "perk_benefits_hub",
        "group": "perks",
        "badge": "Home + 10% Back",
        "tag_cls": "free",
        "url_tpl": "https://one.google.com/u/{u}/benefits?hl={hl}",
        "zh": ("Google One 会员福利领取总页", "一键领取 Google Home 安防订阅 ($10/$20 价值)、Health 会员与 Google 商店 10% 返现"),
        "en": ("Google One Member Benefits Claim Hub", "Claim Google Home Premium ($10/$20 value), Health Premium & 10% Google Store credit"),
        "ar": ("صفحة استلام مزايا Google One", "استلام اشتراك Google Home Premium ومكافآت متجر Google بنسبة 10%"),
        "ru": ("Центр получения бонусов Google One", "Активация Google Home Premium ($10/$20), Health и 10% кэшбэка Google Store"),
        "es": ("Centro de Beneficios de Google One", "Reclama Google Home Premium ($10/$20), Health y 10% en Google Store"),
    },

    # --- Group: risk (Payments Profile & Family Group) ---
    {
        "id": "pay_settings",
        "group": "risk",
        "badge": "Profile & Country",
        "tag_cls": "promo",
        "url_tpl": "https://payments.google.com/gp/w/u/{u}/home/settings",
        "zh": ("Google Payments 付款资料与锁区设置", "核验 12 位付款资料 ID、锁区国家/地区、免税州账单地址，或新建/关闭冲突付款资料"),
        "en": ("Google Payments Profile & Country Lock", "Check 12-digit Profile ID, country/currency lock, tax-free address, or close conflicting profiles"),
        "ar": ("إعدادات الملف الشخصي للدفع والبلد", "فحص معرّف ملف الدفع والبلد وعنوان الفوترة أو إغلاق الملفات المتعارضة"),
        "ru": ("Платежный профиль и страна (Payments)", "Проверка ID профиля, страны/валюты, безналогового адреса и закрытие старых профилей"),
        "es": ("Perfil de Pagos y País (Google Pay)", "Verifica ID de perfil, país/moneda, dirección fiscal o cierra perfiles antiguos"),
    },
    {
        "id": "pay_methods",
        "group": "risk",
        "badge": "Cards & Alerts",
        "tag_cls": "promo",
        "url_tpl": "https://payments.google.com/gp/w/u/{u}/home/paymentmethods",
        "zh": ("付款方式管理 & 风控红条解除", "绑卡/删卡主入口，查看右上角铃铛红色验证告警（解除 OR-FGEMF / OR-HDT 锁卡）"),
        "en": ("Payment Methods & Risk Verification", "Add/remove cards and resolve red verification alerts for OR-FGEMF / OR-HDT holds"),
        "ar": ("طرق الدفع وتنبيهات التحقق الأمني", "إضافة أو حذف البطاقات وحل تنبيهات التحقق الحمراء OR-FGEMF / OR-HDT"),
        "ru": ("Способы оплаты и проверка безопасности", "Управление картами и снятие красных предупреждений верификации OR-FGEMF / OR-HDT"),
        "es": ("Métodos de Pago y Alertas de Riesgo", "Añade/elimina tarjetas y resuelve alertas rojas de verificación OR-FGEMF / OR-HDT"),
    },
    {
        "id": "family_portal",
        "group": "risk",
        "badge": "Max 6 · Cooldown",
        "tag_cls": "free",
        "url_tpl": "https://families.google.com/u/{u}/families",
        "zh": ("Google 家庭组席位管理 (6人上限)", "清理未接受的挂起邀请（同样占坑！）；注意换不同家庭组有 12 个月冷却，重进同组不限"),
        "en": ("Google Family Group Manager (6 Cap)", "Revoke pending invites (they count toward the 6-person cap!); 12m cooldown only applies to different families"),
        "ar": ("إدارة مجموعة عائلة Google (حد 6 أفراد)", "إلغاء الدعوات المعلقة لأنها تحجز مقعداً؛ مهلة 12 شهراً تنطبق فقط عند الانتقال لعائلة مختلفة"),
        "ru": ("Семейная группа Google (лимит 6 чел.)", "Удаление зависших приглашений (занимают слот!); кулдаун 12 мес. только при смене семьи"),
        "es": ("Grupo Familiar de Google (Máx. 6)", "Cancela invitaciones pendientes (ocupan cupo); el bloqueo de 12m solo aplica al cambiar de familia"),
    },
    {
        "id": "g1_settings",
        "group": "risk",
        "badge": "Share Toggle",
        "tag_cls": "free",
        "url_tpl": "https://one.google.com/u/{u}/settings?hl={hl}",
        "zh": ("Google One 家庭共享开关与取消页", "开启「与家庭成员共享 Google One」开关，使子号立即获得存储与 AI 权益"),
        "en": ("Google One Family Share Switch", "Enable 'Share Google One with family' so members receive storage & AI access"),
        "ar": ("تفعيل مشاركة Google One مع العائلة", "تشغيل خيار المشاركة مع العائلة لتفعيل السعة ومزايا الذكاء الاصطناعي للأعضاء"),
        "ru": ("Тумблер семейного доступа Google One", "Включите «Делиться подпиской Google One с семьей» для раздачи квот участникам"),
        "es": ("Interruptor de Uso Compartido Familiar", "Activa «Compartir Google One con la familia» para habilitar beneficios en miembros"),
    },
]


OR_ERROR_DB: List[Dict[str, Any]] = [
    {
        "codes": ["OR-HDT-01", "OR-HDT-14", "OR-HDT-16"],
        "zh": "【高危风控拒绝 / 卡号地区或环境不匹配】Google 交易风控拦截了当前绑卡或订阅。处置：① 确认 Google Payments 付款资料国家与卡前 6 位 BIN 发卡国一致；② 切勿同卡短时间跨多个账号高频重试；③ 前往 payments.google.com 彻底删除该卡，切换干净同国住宅 IP 静置后再绑。",
        "en": "[Risk Engine Decline / BIN or IP Mismatch] Google risk control blocked this instrument. Fix: (1) Match Payments Profile country with card 6-digit BIN country; (2) Avoid rapid retries across accounts; (3) Remove card at payments.google.com and retry later from a clean residential IP.",
    },
    {
        "codes": ["OR-CCSEH-05", "OR-CCSEH-21", "OR-CCSEH-22", "OR-CCSEH-32"],
        "zh": "【发卡行拒付 / 预授权拦截】银行端拒绝了 Google 的 $0/$1 绑卡验卡预授权或跨境扣款。处置：检查卡片余额是否至少留有 $1~$2（应对 $1 验卡冻结），确认卡片已开启境外线上循环订阅权限，或更换卡段。",
        "en": "[Issuer Declined / Pre-Auth Blocked] Card issuer rejected Google's $0/$1 verification hold or recurring billing request. Ensure at least $1–$2 balance and enable international online recurring transactions, or use another BIN.",
    },
    {
        "codes": ["OR-FGEMF-20", "OR-FGEMF-71", "OR-RWE-02"],
        "zh": "【需人工身份/持卡验证】触发强客户认证 (SCA) 或账号支付审核挂起。处置：用桌面浏览器打开 payments.google.com 查看右上角红色铃铛「提醒 (Alerts)」，完成微额扣款验证码或账单核验后自动解封。",
        "en": "[Verification Hold / SCA Required] Account payment profile has a pending verification alert. Open payments.google.com -> top-right Alerts bell to complete card verification.",
    },
    {
        "codes": ["OR-BAIH-01", "OR-BAIH-10", "OR-PMSA-03"],
        "zh": "【付款工具受限 / 多付款资料冲突】虚拟预付卡段被拒或账号下存在多个不同国家的付款资料冲突。处置：进入 payments.google.com/settings 检查是否存在旧国家付款资料残留，必要时关闭冲突旧资料或更换实体/主流虚拟卡段。",
        "en": "[Restricted Instrument / Multi-Profile Conflict] Prepaid virtual BIN restricted or multiple country payment profiles conflict. Check payments.google.com/settings for conflicting profiles or try a different payment method.",
    },
    {
        "codes": ["STATUS: 1010", "DELIVERY 2", "DF-DFERH-01"],
        "zh": "【Play 商店服务未保活或条款未确认】① MuMu 模拟器若 app_keep_alive=false 会跳过 DroidGuardService 报 1010（点顶部「环境自愈」自动开启）；② 新切入账号需先打开一次 Play 商店首页点击「接受」条款；③ 残留旧账号装过的包需先卸载重装。",
        "en": "[Play Store DroidGuard Skipped / TOS Pending] (1) Click 'Self-Heal' to set MuMu app_keep_alive=true so DroidGuardService isn't skipped; (2) Accept Play Store first-run Terms of Service; (3) Cleanly reinstall apps owned by removed accounts.",
    },
    {
        "codes": ["STARTER QUOTA", "ANTIGRAVITY 0%", "PROFILE DESYNC"],
        "zh": "【已开 Pro/Ultra 但 Antigravity 卡在 Starter Quota 0% 额度】系多付款资料地区错配 Bug！结账时静默绑到了旧地区资料（如港币 HKD）。处置：前往 payments.google.com/settings 检查是否存在多个不同国家的付款资料，关闭不支持地区的旧资料并确保订阅绑定在美/欧等支持区单一资料下。",
        "en": "[Paid Pro/Ultra Stuck on Antigravity Starter Quota] Caused by coexisting legacy Payment Profiles (e.g. HKD + USD) where subscription bound to an unsupported region. Open payments.google.com/settings, inspect/close conflicting legacy profiles, and ensure billing is on a single supported profile.",
    },
]


def get_localized_web_hub(lang: str) -> Dict[str, Any]:
    lg = lang if lang in WEB_HUB_UI else "en"
    cards = []
    for item in WEB_PORTALS:
        title, desc = item.get(lg) or item["en"]
        cards.append({
            "id": item["id"],
            "group": item["group"],
            "badge": item["badge"],
            "tag_cls": item["tag_cls"],
            "url_tpl": item["url_tpl"],
            "title": title,
            "desc": desc,
        })
    errors = []
    for e in OR_ERROR_DB:
        errors.append({
            "codes": e["codes"],
            "detail": e["zh"] if lg == "zh" else e["en"],
        })
    return {
        "ui": WEB_HUB_UI[lg],
        "cards": cards,
        "or_errors": errors,
        "shelves": [
            {"name": "Ultra", "tier_id": 7, "sc": encode_shelf_sc(7)},
            {"name": "Pro", "tier_id": 36, "sc": encode_shelf_sc(36)},
            {"name": "Plus", "tier_id": 23, "sc": encode_shelf_sc(23)},
        ],
    }
