#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtool_core/i18n.py — Full Multi-Language Engine (简体中文, English, العربية RTL, Русский, Español)."""

from __future__ import annotations

import locale
import os
import time
from typing import Any, Dict, List, Optional

from .platform_env import BLOG_URL, FAKA_URL, IS_WIN

SUPPORTED_LANGS = ("zh", "en", "ar", "ru", "es")

LANG_META: Dict[str, Dict[str, str]] = {
    "zh": {"label": "简体中文", "short": "中文", "dir": "ltr"},
    "en": {"label": "English", "short": "EN", "dir": "ltr"},
    "ar": {"label": "العربية", "short": "AR", "dir": "rtl"},
    "ru": {"label": "Русский", "short": "RU", "dir": "ltr"},
    "es": {"label": "Español", "short": "ES", "dir": "ltr"},
}


def normalize_lang(code: Optional[str]) -> str:
    if not code:
        return "zh"
    c = code.strip().lower().replace("-", "_")
    for prefix in SUPPORTED_LANGS:
        if c == prefix or c.startswith(prefix + "_"):
            return prefix
    return "zh"


def detect_system_lang() -> str:
    env_override = os.environ.get("GTOOL_LANG", "").strip()
    if env_override:
        return normalize_lang(env_override)

    candidates: List[str] = []
    if IS_WIN:
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            wloc = locale.windows_locale.get(lcid, "")
            if wloc:
                candidates.append(wloc)
        except Exception:
            pass

    for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(k, "").strip()
        if v:
            candidates.append(v)

    try:
        loc_tuple = locale.getlocale()
        if loc_tuple and loc_tuple[0]:
            candidates.append(loc_tuple[0])
    except Exception:
        pass

    for raw in candidates:
        low = raw.lower()
        for prefix in SUPPORTED_LANGS:
            if low == prefix or low.startswith(prefix + "_") or low.startswith(prefix + "-"):
                return prefix
    return "zh"


# ---------- Localized Presets (Concise & Clean for De-cluttered UI) ----------

PRESET_TEXTS: Dict[str, Dict[str, Dict[str, str]]] = {
    "pro12": {
        "zh": {"title": "Pro 5TB · 免费 12 个月", "desc": "第 1 步首开 1 年 $0 试用，后续可继续叠加至 24 个月", "badge": "推荐首开"},
        "en": {"title": "Pro 5TB · 12 Months Free", "desc": "Step 1: 1-year $0 trial, stackable up to 24 months", "badge": "Step 1"},
        "ar": {"title": "Pro 5TB · مجاناً لمدة 12 شهراً", "desc": "الخطوة 1: تجربة مجانية لمدة سنة ($0)، قابلة للتمديد حتى 24 شهراً", "badge": "الخطوة 1"},
        "ru": {"title": "Pro 5TB · 12 мес. бесплатно", "desc": "Шаг 1: год за $0, далее можно продлить до 24 месяцев", "badge": "Шаг 1"},
        "es": {"title": "Pro 5TB · 12 meses gratis", "desc": "Paso 1: 1 año a $0, acumulable hasta 24 meses", "badge": "Paso 1"},
    },
    "stack1": {
        "zh": {"title": "Pro 5TB · 叠加 +6 个月 (→18月)", "desc": "第 2 步免费折算顺延，累计约 546 天（需第 1 步未关续费）", "badge": "叠加第2步"},
        "en": {"title": "Pro 5TB · Stack +6 Mo (→18m)", "desc": "Step 2: Prorate & extend free period to ~546 days", "badge": "Step 2"},
        "ar": {"title": "Pro 5TB · تمديد +6 أشهر (← 18 شهراً)", "desc": "الخطوة 2: تمديد الفترة المجانية إلى حوالي 546 يوماً ($0)", "badge": "الخطوة 2"},
        "ru": {"title": "Pro 5TB · Плюс +6 мес. (→18 мес.)", "desc": "Шаг 2: бесплатное продление подписки примерно до 546 дней", "badge": "Шаг 2"},
        "es": {"title": "Pro 5TB · Sumar +6 meses (→18m)", "desc": "Paso 2: extiende el periodo gratuito a ~546 días ($0)", "badge": "Paso 2"},
    },
    "stack2": {
        "zh": {"title": "Pro 5TB · 叠加 +6 个月 (→24月)", "desc": "第 3 步再次顺延 +6 个月，累计白嫖约 730 天", "badge": "叠加第3步"},
        "en": {"title": "Pro 5TB · Stack +6 Mo (→24m)", "desc": "Step 3: Extend again to ~730 days total free access", "badge": "Step 3"},
        "ar": {"title": "Pro 5TB · تمديد +6 أشهر (← 24 شهراً)", "desc": "الخطوة 3: تمديد إضافي للوصول إلى ~730 يوماً مجاناً", "badge": "الخطوة 3"},
        "ru": {"title": "Pro 5TB · Плюс +6 мес. (→24 мес.)", "desc": "Шаг 3: финальное продление бесплатного периода до ~730 дней", "badge": "Шаг 3"},
        "es": {"title": "Pro 5TB · Sumar +6 meses (→24m)", "desc": "Paso 3: extiende hasta ~730 días gratis en total", "badge": "Paso 3"},
    },
    "pro6c": {
        "zh": {"title": "Pro 5TB · 备用叠加包 +6 个月", "desc": "ss-2026 备用通道，主包已消耗或不可用时补位", "badge": "备用通道"},
        "en": {"title": "Pro 5TB · Backup +6 Mo (ss-2026)", "desc": "Fallback +6m free stack offer if primary offer was used", "badge": "Backup"},
        "ar": {"title": "Pro 5TB · باقة احتياطية +6 أشهر", "desc": "عرض تمديد بديل (ss-2026) عند عدم توفر العرض الأساسي", "badge": "احتياطي"},
        "ru": {"title": "Pro 5TB · Резерв +6 мес. (ss-2026)", "desc": "Запасной оффер продления на +6 мес., если основной недоступен", "badge": "Резерв"},
        "es": {"title": "Pro 5TB · Respaldo +6 meses", "desc": "Oferta alternativa ss-2026 si la principal no está disponible", "badge": "Respaldo"},
    },
    "pro3": {
        "zh": {"title": "Pro 5TB · 免费 3 个月", "desc": "独立 3 个月 $0 免费试用，适合快速单开体验", "badge": "独立3月"},
        "en": {"title": "Pro 5TB · 3 Months Free", "desc": "Standalone 3-month $0 trial (g1.play.2tb.ai)", "badge": "3 Mo Free"},
        "ar": {"title": "Pro 5TB · مجاناً لمدة 3 أشهر", "desc": "تجربة مجانية مستقلة لمدة 3 أشهر بتكلفة $0", "badge": "3 أشهر"},
        "ru": {"title": "Pro 5TB · 3 мес. бесплатно", "desc": "Отдельный пробный период на 3 месяца за $0", "badge": "3 мес."},
        "es": {"title": "Pro 5TB · 3 meses gratis", "desc": "Prueba gratuita independiente de 3 meses a $0", "badge": "3 meses"},
    },
    "prem6": {
        "zh": {"title": "Google One 2TB · 免费 6 个月", "desc": "11月新挖掘独立 $0 试用池 (g1.2tb.subs_variant)，Pro 无资格时兜底", "badge": "新发现6月"},
        "en": {"title": "Google One 2TB · 6 Months Free", "desc": "Newly discovered independent $0 2TB trial pool (fallback)", "badge": "New 6 Mo"},
        "ar": {"title": "Google One 2TB · مجاناً لمدة 6 أشهر", "desc": "عرض تجريبي مجاني مستقل لمدة 6 أشهر لسعة 2TB ($0)", "badge": "6 أشهر مجاناً"},
        "ru": {"title": "Google One 2TB · 6 мес. бесплатно", "desc": "Новый отдельный $0 триал 2TB, если AI Pro недоступен", "badge": "6 мес. $0"},
        "es": {"title": "Google One 2TB · 6 meses gratis", "desc": "Nuevo grupo independiente de prueba $0 de 2TB por 6 meses", "badge": "Nuevo 6m"},
    },
    "auto": {
        "zh": {"title": "智能匹配最长 $0 免费方案", "desc": "自动扫描当前账号全部资格，挑出免费期最长的方案", "badge": "自动优选"},
        "en": {"title": "Auto-Pick Longest $0 Trial", "desc": "Scans all SKUs and launches the longest $0 trial available", "badge": "Smart Auto"},
        "ar": {"title": "اختيار أطول تجربة مجانية تلقائياً", "desc": "فحص جميع الباقات وفتح أطول عرض مجاني متاح لحسابك ($0)", "badge": "تلقائي ذكي"},
        "ru": {"title": "Автовыбор лучшего $0 триала", "desc": "Сканирует все SKU и выбирает самый долгий бесплатный вариант", "badge": "Автовыбор"},
        "es": {"title": "Auto-elegir mejor prueba $0", "desc": "Escanea todos los planes y abre la prueba gratuita más larga", "badge": "Auto"},
    },
    "p_yr90": {
        "zh": {"title": "Pro 5TB · 连续 12 个月 1折", "desc": "11月王炸神车！整年 12 期每期约 $1.99，每月可领 $10 Cloud 赠金", "badge": "$1.99/月×12"},
        "en": {"title": "Pro 5TB · 90% Off Full Year (12 Mo)", "desc": "Nov 2026 gem: ~$1.99/mo for 12 mos + $10/mo Cloud API credit", "badge": "$1.99/mo×12"},
        "ar": {"title": "Pro 5TB · خصم 90% لمدة 12 شهراً", "desc": "حوالي $1.99/شهر لمدة سنة كاملة مع رصيد سحابي $10 شهرياً", "badge": "$1.99/شهر×12"},
        "ru": {"title": "Pro 5TB · Скидка 90% на 12 мес.", "desc": "Хит ноября: ~$1.99/мес. весь год + $10/мес. бонус Google Cloud", "badge": "$1.99/мес×12"},
        "es": {"title": "Pro 5TB · 90% Dto. por 12 meses", "desc": "~$1.99/mes durante 12 meses + $10/mes en crédito Cloud API", "badge": "$1.99/m×12"},
    },
    "p_3m90": {
        "zh": {"title": "Pro 5TB · 前 3 个月 1折", "desc": "首 3 期每期仅约 $1.99（原价 $19.99），无免费资格老号救星", "badge": "$1.99/月×3"},
        "en": {"title": "Pro 5TB · 90% Off 3 Months", "desc": "~$1.99/mo for 3 mos (reg. $19.99), ideal for accounts without $0 trial", "badge": "$1.99/mo×3"},
        "ar": {"title": "Pro 5TB · خصم 90% لأول 3 أشهر", "desc": "حوالي $1.99/شهر لأول 3 أشهر للحسابات غير المؤهلة للتجربة المجانية", "badge": "$1.99/شهر×3"},
        "ru": {"title": "Pro 5TB · Скидка 90% на 3 мес.", "desc": "~$1.99/мес. на 3 мес. (вместо $19.99), отлично для старых аккаунтов", "badge": "$1.99/мес×3"},
        "es": {"title": "Pro 5TB · 90% Dto. por 3 meses", "desc": "~$1.99/mes por 3 meses (antes $19.99), ideal sin prueba $0", "badge": "$1.99/m×3"},
    },
    "u1": {
        "zh": {"title": "Ultra 30TB (20x) · 首月 1折", "desc": "11月最新存活 Ultra 1折！首月 $19.99 立领 $100 API 赠金 + 2000 算力", "badge": "$19.99 首月"},
        "en": {"title": "Ultra 30TB (20x) · 90% Off 1st Mo", "desc": "Live Nov 90%-off Ultra: $19.99 1st mo + $100 Cloud credit & 2,000 CCUs", "badge": "$19.99 1st mo"},
        "ar": {"title": "Ultra 30TB (20x) · خصم 90% للشهر الأول", "desc": "$19.99 للشهر الأول مع رصيد سحابي $100 و2000 وحدة Colab", "badge": "$19.99 أول شهر"},
        "ru": {"title": "Ultra 30TB (20x) · Скидка 90% (1-й мес.)", "desc": "$19.99 за 1-й мес. + $100 бонус Cloud API и 2000 единиц Colab", "badge": "$19.99 1-й мес"},
        "es": {"title": "Ultra 30TB (20x) · 90% Dto. 1.er mes", "desc": "$19.99 el 1.er mes + $100 crédito Cloud API y 2000 CCUs Colab", "badge": "$19.99 1m"},
    },
    "u2": {
        "zh": {"title": "Ultra 30TB (20x) · 前 3 月 2折", "desc": "原 3 月 1 折下线后的主力车，前 3 月 $39.99/月（内置防原价保护）", "badge": "$39.99/月"},
        "en": {"title": "Ultra 30TB (20x) · 80% Off 3 Mo", "desc": "Primary multi-month Ultra promo: $39.99/mo for 3 mos (reg. $199.99)", "badge": "$39.99/mo"},
        "ar": {"title": "Ultra 30TB (20x) · خصم 80% لـ 3 أشهر", "desc": "$39.99/شهر لأول 3 أشهر (بدلاً من $199.99، مع حماية من السعر الكامل)", "badge": "$39.99/شهر"},
        "ru": {"title": "Ultra 30TB (20x) · Скидка 80% (3 мес.)", "desc": "$39.99/мес. первые 3 мес. (вместо $199.99, защита от полной цены)", "badge": "$39.99/мес."},
        "es": {"title": "Ultra 30TB (20x) · 80% Dto. 3 meses", "desc": "$39.99/mes por 3 meses (antes $199.99, con protección anti-precio base)", "badge": "$39.99/mes"},
    },
    "u4": {
        "zh": {"title": "Ultra 30TB (20x) · 前 3 月 2.5折", "desc": "首 3 月 $49.99/月（1折/2折无资格时的 30TB 备选特惠档）", "badge": "$49.99/月"},
        "en": {"title": "Ultra 30TB (20x) · 75% Off 3 Mo", "desc": "$49.99/mo for 3 mos (fallback 30TB promo tier)", "badge": "$49.99/mo"},
        "ar": {"title": "Ultra 30TB (20x) · خصم 75% لـ 3 أشهر", "desc": "$49.99/شهر لأول 3 أشهر (بديل باقة 30TB عند عدم توفر خصم 80%)", "badge": "$49.99/شهر"},
        "ru": {"title": "Ultra 30TB (20x) · Скидка 75% (3 мес.)", "desc": "$49.99/мес. на 3 мес. (резервная скидка на 30TB)", "badge": "$49.99/мес."},
        "es": {"title": "Ultra 30TB (20x) · 75% Dto. 3 meses", "desc": "$49.99/mes por 3 meses (alternativa para Ultra 30TB)", "badge": "$49.99/mes"},
    },
}


def humanize_launch_error(ev: str, lang: str = "zh") -> str:
    """Translate raw BillingClient / session error tags into clear, actionable user guidance."""
    lg = normalize_lang(lang)
    raw = str(ev or "").strip()
    table = {
        "PROMO_INELIGIBLE": {
            "zh": "当前账号无此折扣资格（仅剩原价档，已自动拦截防误扣款）",
            "en": "Account not eligible for this promo (blocked full-price fallback)",
            "ar": "الحساب غير مؤهل لهذا الخصم (تم حظر السعر الكامل لحمايتك)",
            "ru": "Аккаунт не подходит для акции (полная цена заблокирована)",
            "es": "Cuenta no elegible para este descuento (precio completo bloqueado)",
        },
        "SELECT_FAILED": {
            "zh": "当前账号未返回该试用方案（已领过或锁区不符，请点「方案扫描」查看可用项）",
            "en": "Offer unavailable for this account (already used or region mismatch)",
            "ar": "العرض غير متاح لهذا الحساب (مستخدم مسبقاً أو اختلاف المنطقة)",
            "ru": "Оффер недоступен для аккаунта (уже использован или другой регион)",
            "es": "Oferta no disponible para esta cuenta (ya usada o región distinta)",
        },
        "SKU_NOT_FOUND": {
            "zh": "当前账号无法拉取该商品（已有冲突订阅或地区未开放）",
            "en": "SKU not available on this account (existing subscription or region)",
            "ar": "الباقة غير متوفرة لهذا الحساب (اشتراك حالي أو قيد المنطقة)",
            "ru": "SKU недоступен на этом аккаунте (есть подписка или ограничение региона)",
            "es": "SKU no disponible en esta cuenta (suscripción activa o región)",
        },
        "NO_TRIALS_AVAILABLE": {
            "zh": "当前账号无任何 $0 免费试用资格，可尝试下方 1折 特惠方案",
            "en": "No $0 trials available on this account; try a 90%-off promo tier",
            "ar": "لا توجد عروض مجانية ($0) لهذا الحساب؛ جرّب عروض الخصم 90%",
            "ru": "Нет доступных $0 триалов; попробуйте тарифы со скидкой 90%",
            "es": "Sin pruebas de $0 en esta cuenta; prueba las ofertas con 90% dto.",
        },
        "STACK_NO_ACTIVE_SUB": {
            "zh": "未检测到活跃首开订阅，请先完成第 1 步（12个月首开）再点叠加",
            "en": "No active base subscription found; complete Step 1 before stacking",
            "ar": "لا يوجد اشتراك نشط؛ أكمل الخطوة 1 أولاً قبل التمديد",
            "ru": "Нет активной подписки; сначала выполните Шаг 1 перед продлением",
            "es": "Sin suscripción activa; completa el Paso 1 antes de acumular",
        },
        "NO_ACTIVITY": {
            "zh": "Google One 前台窗口未就绪，请等待应用界面打开后重试",
            "en": "Google One foreground window not ready; retry once opened",
            "ar": "نافذة Google One غير جاهزة في المقدمة؛ أعد المحاولة",
            "ru": "Окно Google One еще не готово; повторите попытку",
            "es": "La ventana de Google One no está lista; inténtalo de nuevo",
        },
        "ENGINE_NOT_READY": {
            "zh": "计费引擎未就绪，请先点右上角「环境自检」确认模拟器 Root 与网络",
            "en": "Billing engine not ready; run Doctor to check Root & Play network",
            "ar": "محرك الفوترة غير جاهز؛ شغّل الفحص للتأكد من صلاحيات Root والشبكة",
            "ru": "Движок не готов; запустите Проверку (Root и сеть Google Play)",
            "es": "Motor no listo; ejecuta Diagnóstico para revisar Root y red",
        },
        "TIMEOUT": {
            "zh": "等待 Google Play 响应超时，请确认模拟器已开启 Root 且节点可直连 Play",
            "en": "Timed out waiting for Google Play; check emulator Root & Play network",
            "ar": "انتهت مهلة انتظار Google Play؛ تحقق من صلاحيات Root والشبكة",
            "ru": "Таймаут ответа Google Play; проверьте Root и доступ к сети Play",
            "es": "Tiempo agotado esperando a Google Play; revisa Root y conexión",
        },
    }
    for key, trans in table.items():
        if key in raw:
            return trans.get(lg) or trans["en"]
    return raw


def localize_presets(presets: List[Dict[str, Any]], lang: str) -> List[Dict[str, Any]]:
    lg = normalize_lang(lang)
    out: List[Dict[str, Any]] = []
    for p in presets:
        item = dict(p)
        t = PRESET_TEXTS.get(p["alias"], {}).get(lg) or PRESET_TEXTS.get(p["alias"], {}).get("en")
        if t:
            item["title"] = t["title"]
            item["desc"] = t["desc"]
            item["badge"] = t["badge"]
        out.append(item)
    return out


# ---------- Localized Offer Item Formatting ----------

def localize_offer(raw: Dict[str, Any], lang: str) -> Dict[str, Any]:
    lg = normalize_lang(lang)
    dur_tables = {
        "zh": {"P1W": "7天", "P1M": "1月", "P2M": "2月", "P3M": "3月", "P13W1D": "3月", "P6M": "6月", "P1Y": "12月", "P12M": "12月"},
        "en": {"P1W": "7d", "P1M": "1mo", "P2M": "2mo", "P3M": "3mo", "P13W1D": "3mo", "P6M": "6mo", "P1Y": "12mo", "P12M": "12mo"},
        "ar": {"P1W": "7 أيام", "P1M": "شهر", "P2M": "شهران", "P3M": "3 أشهر", "P13W1D": "3 أشهر", "P6M": "6 أشهر", "P1Y": "12 شهراً", "P12M": "12 شهراً"},
        "ru": {"P1W": "7 дн.", "P1M": "1 мес.", "P2M": "2 мес.", "P3M": "3 мес.", "P13W1D": "3 мес.", "P6M": "6 мес.", "P1Y": "12 мес.", "P12M": "12 мес."},
        "es": {"P1W": "7d", "P1M": "1m", "P2M": "2m", "P3M": "3m", "P13W1D": "3m", "P6M": "6m", "P1Y": "12m", "P12M": "12m"},
    }
    per_tables = {
        "zh": {"P1M": "/月", "P3M": "/季", "P6M": "/半年", "P1Y": "/年", "P12M": "/年"},
        "en": {"P1M": "/mo", "P3M": "/qtr", "P6M": "/6mo", "P1Y": "/yr", "P12M": "/yr"},
        "ar": {"P1M": "/شهر", "P3M": "/ربع سنة", "P6M": "/6 أشهر", "P1Y": "/سنة", "P12M": "/سنة"},
        "ru": {"P1M": "/мес.", "P3M": "/кв.", "P6M": "/полгода", "P1Y": "/год", "P12M": "/год"},
        "es": {"P1M": "/mes", "P3M": "/trim", "P6M": "/6m", "P1Y": "/año", "P12M": "/año"},
    }
    dur_map = dur_tables.get(lg, dur_tables["en"])
    per_map = per_tables.get(lg, per_tables["en"])

    tp = raw.get("type", "BASE")
    trp = raw.get("trial_period", "")
    pr = raw.get("price", "")
    pe = raw.get("period", "")
    rn = raw.get("renew_price", "")
    cy = str(raw.get("intro_cycles", "0"))
    pe_lbl = per_map.get(pe, f"/{pe}" if pe else "")

    if tp == "TRIAL":
        d_lbl = dur_map.get(trp, trp or "Trial")
        badge = {
            "zh": f"★ 免费 {d_lbl}",
            "en": f"★ Free {d_lbl}",
            "ar": f"★ مجاناً {d_lbl}",
            "ru": f"★ Триал {d_lbl}",
            "es": f"★ Gratis {d_lbl}",
        }[lg]
        pricing = f"$0 → {pr}{pe_lbl}"
    elif tp == "PROMO":
        badge = {
            "zh": "⚡ 特惠促销",
            "en": "⚡ Promo",
            "ar": "⚡ عرض مخفض",
            "ru": "⚡ Промо",
            "es": "⚡ Promo",
        }[lg]
        c_prefix = {
            "zh": f"前{cy}期 " if cy and cy != "0" else "",
            "en": f"{cy}x " if cy and cy != "0" else "",
            "ar": f"{cy}× " if cy and cy != "0" else "",
            "ru": f"{cy}× " if cy and cy != "0" else "",
            "es": f"{cy}x " if cy and cy != "0" else "",
        }[lg]
        pricing = f"{c_prefix}{pr} → {rn}{pe_lbl}" if rn else f"{pr}{pe_lbl}"
    else:
        badge = {
            "zh": "标准价",
            "en": "Standard",
            "ar": "سعر عادي",
            "ru": "Базовый",
            "es": "Estándar",
        }[lg]
        pricing = f"{pr}{pe_lbl}"

    out = dict(raw)
    out["badge"] = badge
    out["pricing_summary"] = pricing
    return out


# ---------- Localized Wizard ----------

def localize_wizard(wiz: Dict[str, Any], lang: str) -> Dict[str, Any]:
    lg = normalize_lang(lang)
    if lg == "zh":
        return wiz

    out = dict(wiz)
    days = int(wiz.get("days_left") or 0)
    exp = wiz.get("expiry_date") or ""
    rec = wiz.get("recommended_preset") or ""
    stage = int(wiz.get("stage") or 0)

    step_names = {
        "en": ["12m Start", "+6m (18m)", "+6m (24m)", "Cancel Auto-Pay"],
        "ar": ["12 شهراً مجاناً", "+6 أشهر (18)", "+6 أشهر (24)", "إلغاء التجديد"],
        "ru": ["12 мес. старт", "+6 мес. (18)", "+6 мес. (24)", "Отмена автооплаты"],
        "es": ["12m Inicio", "+6m (18m)", "+6m (24m)", "Cancelar renovación"],
    }[lg]
    ack_step = {"en": "Sync Order", "ar": "تأكيد الطلب", "ru": "Синхр. заказа", "es": "Sincronizar"}[lg]

    new_steps = []
    for i, st in enumerate(wiz.get("steps", [])):
        s_copy = dict(st)
        if rec == "ack" and i == 1:
            s_copy["name"] = ack_step
        elif i < len(step_names):
            s_copy["name"] = step_names[i]
        new_steps.append(s_copy)
    out["steps"] = new_steps

    if stage == 0:
        out["headline"] = {
            "en": "No active plan · Ready for Step 1 (12 Months Free) or Ultra 90% Off",
            "ar": "لا يوجد اشتراك نشط · جاهز للخطوة 1 (12 شهراً مجاناً) أو عرض Ultra بخصم 90%",
            "ru": "Нет активной подписки · Доступен Шаг 1 (12 мес. за $0) или Ultra со скидкой 90%",
            "es": "Sin suscripción activa · Listo para el Paso 1 (12 meses gratis) o Ultra 90% dto.",
        }[lg]
        out["recommended_label"] = {
            "en": "Start Step 1: 12 Months Free",
            "ar": "ابدأ الخطوة 1: 12 شهراً مجاناً",
            "ru": "Запустить Шаг 1: 12 мес. бесплатно",
            "es": "Iniciar Paso 1: 12 meses gratis",
        }[lg]
    elif rec == "ack":
        out["headline"] = {
            "en": f"Unacknowledged order detected ({days} days left)",
            "ar": f"تم اكتشاف طلب غير مؤكد (متبقي {days} يوماً)",
            "ru": f"Обнаружен неподтвержденный заказ (осталось {days} дн.)",
            "es": f"Pedido pendiente de confirmación ({days} días restantes)",
        }[lg]
        out["warning"] = {
            "en": "Click 'Sync Order' first to confirm your entitlement before stacking.",
            "ar": "يرجى النقر على «مزامنة وتأكيد الطلب» أولاً قبل المتابعة بالتمديد.",
            "ru": "Сначала нажмите «Синхр. заказа» (Acknowledge) перед следующим продлением.",
            "es": "Pulsa «Sincronizar pedido» primero antes de acumular más meses.",
        }[lg]
        out["recommended_label"] = {
            "en": "Sync & Acknowledge Now",
            "ar": "مزامنة وتأكيد الطلب الآن",
            "ru": "Синхронизировать заказ",
            "es": "Sincronizar pedido ahora",
        }[lg]
    elif stage == 3:
        out["headline"] = {
            "en": f"Stacked ~{days} days (until {exp}) · Final step: Cancel auto-renewal",
            "ar": f"تم تجميع ~{days} يوماً (حتى {exp}) · الخطوة الأخيرة: إلغاء التجديد التلقائي",
            "ru": f"Накоплено ~{days} дн. (до {exp}) · Финальный шаг: отключить автопродление",
            "es": f"Acumulados ~{days} días (hasta {exp}) · Último paso: cancelar renovación",
        }[lg]
        out["recommended_label"] = {
            "en": "Cancel Auto-Renewal (Keep Free Days)",
            "ar": "إلغاء التجديد التلقائي (مع الاحتفاظ بالأيام المجانية)",
            "ru": "Отменить автопродление (сохранив дни)",
            "es": "Cancelar renovación automática",
        }[lg]
    elif stage == 4:
        out["headline"] = {
            "en": f"All set! {days} free days locked (until {exp}) & auto-renewal is off",
            "ar": f"اكتمل بنجاح! تم تأمين {days} يوماً مجانياً (حتى {exp}) وإيقاف التجديد التلقائي",
            "ru": f"Готово! Закреплено {days} бесплатных дней (до {exp}), автопродление отключено",
            "es": f"¡Completado! {days} días gratis asegurados (hasta {exp}) sin renovación",
        }[lg]
        out["recommended_label"] = ""
    elif wiz.get("warning"):
        out["headline"] = {
            "en": f"{days} days remaining (until {exp}), but auto-renewal was turned off early",
            "ar": f"متبقي {days} يوماً (حتى {exp})، ولكن تم إيقاف التجديد التلقائي مبكراً",
            "ru": f"Осталось {days} дн. (до {exp}), но автопродление было отключено раньше времени",
            "es": f"Quedan {days} días (hasta {exp}), pero se canceló la renovación antes de tiempo",
        }[lg]
        out["warning"] = {
            "en": "Canceled plans cannot prorate! Tap 'Resubscribe' in Play Subscriptions first, stack to 24m, then cancel.",
            "ar": "الاشتراكات الملغاة لا تقبل التمديد! اضغط «إعادة الاشتراك» في متجر Play أولاً، مدّد إلى 24 شهراً، ثم ألغِ التجديد.",
            "ru": "Отмененная подписка не суммируется! Нажмите «Возобновить» в Google Play, продлите до 24 мес., затем отмените.",
            "es": "Reactiva la suscripción en Google Play primero, acumula 24 meses y luego cancela.",
        }[lg]
    elif stage == 1:
        out["headline"] = {
            "en": f"Step 1 active ({days}d left, until {exp}) · Ready for Step 2 (+6 Months)",
            "ar": f"الخطوة 1 نشطة ({days} يوماً حتى {exp}) · جاهز للخطوة 2 (+6 أشهر)",
            "ru": f"Шаг 1 активен ({days} дн., до {exp}) · Готово к Шагу 2 (+6 мес.)",
            "es": f"Paso 1 activo ({days}d hasta {exp}) · Listo para Paso 2 (+6 meses)",
        }[lg]
        out["recommended_label"] = {
            "en": "Run Step 2: Stack +6 Months (→18m)",
            "ar": "تنفيذ الخطوة 2: تمديد +6 أشهر (← 18 شهراً)",
            "ru": "Шаг 2: Продлить +6 мес. (→18 мес.)",
            "es": "Paso 2: Sumar +6 meses (→18m)",
        }[lg]
    elif stage == 2:
        out["headline"] = {
            "en": f"Step 2 active ({days}d left, until {exp}) · Ready for Step 3 (+6m → 24m)",
            "ar": f"الخطوة 2 نشطة ({days} يوماً حتى {exp}) · جاهز للخطوة 3 (+6 أشهر ← 24 شهراً)",
            "ru": f"Шаг 2 активен ({days} дн., до {exp}) · Готово к Шагу 3 (+6 мес. → 24 мес.)",
            "es": f"Paso 2 activo ({days}d hasta {exp}) · Listo para Paso 3 (+6m → 24m)",
        }[lg]
        out["recommended_label"] = {
            "en": "Run Step 3: Stack +6 Months (→24m)",
            "ar": "تنفيذ الخطوة 3: تمديد +6 أشهر (← 24 شهراً)",
            "ru": "Шаг 3: Продлить +6 мес. (→24 мес.)",
            "es": "Paso 3: Sumar +6 meses (→24m)",
        }[lg]
    return out


# ---------- Localized Greetings & Tips ----------

def time_greeting_i18n(user_name: str = "", lang: str = "zh") -> str:
    lg = normalize_lang(lang)
    hour = time.localtime().tm_hour
    who = f" {user_name}" if user_name else ""
    if lg == "zh":
        if 5 <= hour < 12:
            return f"早安{who}"
        if 12 <= hour < 18:
            return f"下午好{who}"
        if 18 <= hour < 23:
            return f"晚上好{who}"
        return f"夜深了{who}"
    if lg == "ar":
        return f"مرحباً{who}" if not (5 <= hour < 12) else f"صباح الخير{who}"
    if lg == "ru":
        if 5 <= hour < 12:
            return f"Доброе утро{who}"
        if 12 <= hour < 18:
            return f"Добрый день{who}"
        return f"Добрый вечер{who}"
    if lg == "es":
        return f"Buenos días{who}" if 5 <= hour < 12 else f"Hola{who}"
    return f"Good morning{who}" if 5 <= hour < 12 else (f"Good afternoon{who}" if 12 <= hour < 18 else f"Good evening{who}")


def active_motto_i18n(prefs: Dict[str, Any], lang: str = "zh") -> str:
    lg = normalize_lang(lang)
    custom = str(prefs.get("motto") or "auto").strip()
    if custom and custom != "auto":
        return custom
    tips_by_lang = {
        "zh": [
            "非 $0 方案仅拉起收银台弹窗，绝不自动点击扣款",
            "Pro 5TB 支持 12月 → +6月 → +6月 顺延至 24 个月",
            f"技术博客 {BLOG_URL} · GPT代充 {FAKA_URL}",
        ],
        "en": [
            "Safety first: Paid promos only open the Play sheet and never auto-click Subscribe",
            "Pro 5TB supports 12m → +6m → +6m free stacking up to 24 months",
            f"Tech Blog: {BLOG_URL} · ChatGPT Top-Up Only: {FAKA_URL}",
        ],
        "ar": [
            "حماية كاملة: العروض المدفوعة تفتح نافذة الدفع فقط ولا تضغط اشتراك تلقائياً أبداً",
            "يدعم Pro 5TB التمديد المجاني 12 شهراً ← +6 ← +6 حتى 24 شهراً",
            f"المدونة: {BLOG_URL} · متجر شحن GPT فقط: {FAKA_URL}",
        ],
        "ru": [
            "Защита от списаний: платные промо только открывают окно Google Play без авто-оплаты",
            "Pro 5TB поддерживает бесплатное суммирование 12 + 6 + 6 до 24 месяцев",
            f"Блог: {BLOG_URL} · Пополнение только ChatGPT/GPT: {FAKA_URL}",
        ],
        "es": [
            "Seguridad total: las promos de pago nunca pulsan Suscribirse automáticamente",
            "Pro 5TB permite acumular 12m + 6m + 6m gratis hasta 24 meses",
            f"Blog: {BLOG_URL} · Solo recarga GPT: {FAKA_URL}",
        ],
    }
    arr = tips_by_lang.get(lg, tips_by_lang["en"])
    return arr[int(time.time() // 12) % len(arr)]


# ---------- Complete Web / Desktop App Dictionary ----------

WEB_UI_DICT: Dict[str, Dict[str, Any]] = {
    "zh": {
        "app_title": "Google AI Trial Studio",
        "dev_connected": "已连接",
        "dev_disconnected": "模拟器未连接",
        "no_account": "未登录账号",
        "btn_connect": "连接/唤醒",
        "btn_screen": "屏幕遥控",
        "btn_doctor": "环境自愈",
        "btn_refresh": "刷新",
        "tab_quick": "一键开通",
        "tab_scan": "方案扫描",
        "tab_batch": "批量跑号",
        "tab_settings": "设置与自查",
        "seg_free": "免费试用 ($0)",
        "seg_promo": "Ultra 特惠折扣",
        "seg_custom": "自定义 SKU",
        "btn_launch": "拉起收银台",
        "custom_placeholder": "输入商品 SKU，例如 g1.2tb.ai.subs_variant",
        "btn_custom_go": "查询并拉起",
        "util_ack": "查单 & 补单同步",
        "util_subs": "打开 Play 订阅页",
        "util_cancel": "取消自动续费",
        "days_left_fmt": "剩余 {days} 天",
        "no_active_sub": "无活跃订阅",
        "scan_all": "全部",
        "scan_trial": "$0 免费",
        "scan_promo": "特惠促销",
        "scan_base": "标准价",
        "scan_search": "搜索名称或 Offer ID...",
        "btn_scan_now": "立即扫描",
        "scan_idle": "点击右上角「立即扫描」读取当前账号全部隐藏与公开方案",
        "scan_running": "正在分 4 波动态探测 20 个隐藏与特惠 SKU...",
        "scan_empty": "未发现匹配方案（请确认模拟器已登录账号并打开过一次 Play 商店）",
        "col_plan": "套餐名称",
        "col_tag": "标签",
        "col_price": "计费明细",
        "col_action": "操作",
        "btn_instant": "0.2s 拉起",
        "batch_safety": "非 $0 自动拦截防扣款",
        "batch_accts_lbl": "账号列表（支持拖入 .txt/.csv 或直接粘贴）",
        "batch_cards_lbl": "卡片列表（若账号内已含卡可留空）",
        "batch_import_file": "导入文件",
        "batch_stat_idle": "等待导入账号与卡片...",
        "batch_stat_parsed": "已识别 {a} 个账号（内嵌卡 {e} 张）· 独立卡 {c} 张",
        "card_rotate": "卡片轮换",
        "card_single": "固定首卡",
        "btn_batch_start": "启动批量",
        "btn_batch_stop": "停止",
        "col_email": "账号",
        "col_status": "状态",
        "col_detail": "详情",
        "col_time": "耗时",
        "scr_title": "模拟器实时画面（点击画面可直接触控）",
        "scr_live": "自动刷新",
        "scr_hint": "点击下方「刷新画面」或开启「自动刷新」查看并操控模拟器屏幕",
        "btn_scr_shot": "刷新画面",
        "btn_scr_back": "返回",
        "btn_scr_home": "桌面",
        "btn_scr_pw": "代填密码",
        "set_profile": "基础与自动化偏好",
        "lbl_name": "称呼昵称",
        "lbl_reset": "批量 Google One 重置方式",
        "opt_smart": "极速清数据秒切 (省45秒/号)",
        "opt_reinstall": "Play 商店卸载重装",
        "lbl_postal": "绑卡默认美国邮编池",
        "opt_classic": "常规州 (92101 / 89101 / 33131)",
        "opt_taxfree": "免税州 (97201 / 19801)",
        "lbl_sound": "启用系统提示音",
        "lbl_anim": "模拟器 0 动画极速模式",
        "lbl_autocancel": "批量开通免费试用后自动取消续费",
        "btn_save_prefs": "保存设置",
        "faq_title": "常见问题与网络环境自查",
        "faqs": [
            {"q": "1. 电脑能翻墙，模拟器里 Play 商店却断网或转圈？", "a": "请在宿主机代理软件（Clash Verge / Surge / v2rayN）开启 TUN 模式（Windows 需以管理员身份运行），切勿同时在模拟器内再开 VPN。若曾设过手动代理残留导致断网，点击顶部「环境自愈」可一键清除死代理并消除离线误报。"},
            {"q": "2. Pro 24个月免费叠加 & Ultra 1折有哪些硬性前提？", "a": "• Pro 第 2/3 步叠加：第 1 步首开后切勿提前关闭自动续费（已取消续费的订阅无法折算顺延）；叠满 24 个月后再点「取消自动续费」。\n• Ultra 1折~2.5折：仅对当前无任何 Google One 活跃订阅的账号开放。"},
            {"q": "3. 付款成功但空间仍显示 15GB 未到账？", "a": "点击「查单 & 补单同步」自动执行 acknowledgePurchase 订单确认并重启刷新 Google One；若实时查单显示 0 笔，说明仅停留在银行预授权未成单，会自动原路退回。"},
            {"q": "4. 绑卡或订阅报 OR-HDT-01 / 不符合条件？", "a": "Google Play 强校验账号锁区与银行卡前 6 位 BIN 国家一致（如美区号配美卡 + 美国邮编），遇 OR-HDT 风控请更换纯净原生节点，避免同 IP 连续重试。"},
        ],
        "human_title": "需要人工协助：",
        "human_cont": "已在模拟器完成，继续",
        "human_skip": "跳过此号",
        "human_abort": "中止任务",
        "logs_toggle": "运行日志",
        "logs_ready": "就绪 · 点击右侧展开查看详细日志",
        "ad_blog": "技术博客",
        "ad_faka": "GPT 代充发卡网（仅提供 ChatGPT 代充）",
        "confirm_paid": "付费特惠方案确认：\n{title}\n\n本工具仅为您拉起收银台弹窗，绝不自动点击订阅扣款。是否继续？",
        "confirm_cancel": "确认前往 Google Play 订阅页自动取消续费？（已获得的免费期权益照常保留）",
        "prompt_pw": "输入当前 Google 账号密码（用于在模拟器收银台安全填入）：",
        "toast_launching": "正在拉起收银台：{title}...",
        "toast_launched": "✓ 收银台已在模拟器弹出：{title}",
        "toast_failed": "未成功拉起：{err}",
        "toast_saved": "✓ 设置已保存",
        "toast_ack": "✓ 补单同步完成：查到 {c} 笔有效订阅，新确认 {a} 笔",
        "toast_doctor": "✓ 环境与网络自愈检查已完成",
    },
    "en": {
        "app_title": "Google AI Trial Studio",
        "dev_connected": "Connected",
        "dev_disconnected": "Emulator Offline",
        "no_account": "Not signed in",
        "btn_connect": "Connect / Wake",
        "btn_screen": "Screen",
        "btn_doctor": "Self-Heal",
        "btn_refresh": "Refresh",
        "tab_quick": "Quick Start",
        "tab_scan": "Offer Scanner",
        "tab_batch": "Batch Auto",
        "tab_settings": "Settings & FAQ",
        "seg_free": "$0 Free Trials",
        "seg_promo": "Ultra Promos",
        "seg_custom": "Custom SKU",
        "btn_launch": "Open Checkout",
        "custom_placeholder": "Enter SKU ID, e.g. g1.2tb.ai.subs_variant",
        "btn_custom_go": "Launch SKU",
        "util_ack": "Sync / Acknowledge Order",
        "util_subs": "Open Play Subscriptions",
        "util_cancel": "Cancel Auto-Renewal",
        "days_left_fmt": "{days}d left",
        "no_active_sub": "No Active Plan",
        "scan_all": "All",
        "scan_trial": "$0 Free",
        "scan_promo": "Promos",
        "scan_base": "Standard",
        "scan_search": "Filter by name or Offer ID...",
        "btn_scan_now": "Scan Now",
        "scan_idle": "Click 'Scan Now' to query all hidden and public offers for the current account",
        "scan_running": "Scanning 20 SKUs across 4 waves...",
        "scan_empty": "No matching offers found (ensure Google Play Store has been opened at least once)",
        "col_plan": "Plan",
        "col_tag": "Type",
        "col_price": "Pricing",
        "col_action": "Action",
        "btn_instant": "0.2s Open",
        "batch_safety": "Strict $0 Guard Enabled",
        "batch_accts_lbl": "Accounts (drag .txt/.csv or paste)",
        "batch_cards_lbl": "Cards (leave empty if embedded in accounts)",
        "batch_import_file": "Choose File",
        "batch_stat_idle": "Waiting for accounts & cards...",
        "batch_stat_parsed": "Parsed {a} accounts ({e} embedded cards) · {c} standalone cards",
        "card_rotate": "Rotate Cards",
        "card_single": "Single First Card",
        "btn_batch_start": "Start Batch",
        "btn_batch_stop": "Stop",
        "col_email": "Account",
        "col_status": "Status",
        "col_detail": "Detail",
        "col_time": "Time",
        "scr_title": "Live Emulator Screen (Click image to tap)",
        "scr_live": "Auto Stream",
        "scr_hint": "Click 'Refresh' or enable 'Auto Stream' to view and tap the emulator screen",
        "btn_scr_shot": "Refresh",
        "btn_scr_back": "Back",
        "btn_scr_home": "Home",
        "btn_scr_pw": "Fill Password",
        "set_profile": "Preferences & Automation",
        "lbl_name": "Display Name",
        "lbl_reset": "Batch App Reset Mode",
        "opt_smart": "Fast pm clear (saves ~45s/acct)",
        "opt_reinstall": "Full Play Store Reinstall",
        "lbl_postal": "Default US Billing ZIP Pool",
        "opt_classic": "Standard (92101 / 89101 / 33131)",
        "opt_taxfree": "Tax-Free States (97201 / 19801)",
        "lbl_sound": "Enable Sound Alerts",
        "lbl_anim": "Zero-Animation Fast UI Mode",
        "lbl_autocancel": "Auto-Cancel Renewal After Batch Trial",
        "btn_save_prefs": "Save Preferences",
        "faq_title": "Troubleshooting & Network Guide",
        "faqs": [
            {"q": "1. Host has internet, why is Google Play offline inside the emulator?", "a": "Enable TUN Mode in your proxy client (run Clash Verge / v2rayN as Administrator on Windows) and avoid running a second VPN inside the emulator. Click 'Self-Heal' at the top to clear stale dead ADB proxies and fix false offline flags."},
            {"q": "2. Requirements for Pro 24-Month Stacking & Ultra 90% Off?", "a": "• Pro Step 2/3 Stacking: Keep auto-renewal ON until you reach 24 months (Google Play does not prorate canceled subscriptions); cancel auto-renewal after Step 3.\n• Ultra 90%–75% Off: Available only on accounts with NO active Google One subscription."},
            {"q": "3. Paid/Subscribed, but storage still shows 15 GB?", "a": "Click 'Sync / Acknowledge Order' to run acknowledgePurchase and refresh Google One. If 0 active orders are returned, checkout stopped at a temporary bank pre-authorization which refunds automatically."},
            {"q": "4. Getting OR-HDT-01 or Not Eligible errors?", "a": "Ensure your Google Pay country matches your card's 6-digit BIN country (e.g. US profile + US card + US ZIP) and switch to a clean residential IP."},
        ],
        "human_title": "Manual Action Needed:",
        "human_cont": "Done in Emulator, Continue",
        "human_skip": "Skip Account",
        "human_abort": "Abort Batch",
        "logs_toggle": "Activity Log",
        "logs_ready": "Ready · Click to expand detailed logs",
        "ad_blog": "Tech Blog",
        "ad_faka": "GPT Top-Up Store (ChatGPT Recharge Only)",
        "confirm_paid": "Paid Promo Confirmation:\n{title}\n\nThis tool ONLY opens the Google Play sheet and will NEVER auto-click Subscribe. Continue?",
        "confirm_cancel": "Open Google Play Subscriptions and cancel auto-renewal now? (Your remaining free days stay active.)",
        "prompt_pw": "Enter Google account password to auto-fill on the verification dialog:",
        "toast_launching": "Opening checkout: {title}...",
        "toast_launched": "✓ Checkout opened on emulator: {title}",
        "toast_failed": "Could not open checkout: {err}",
        "toast_saved": "✓ Preferences saved",
        "toast_ack": "✓ Order sync complete: {c} active sub(s), {a} newly acknowledged",
        "toast_doctor": "✓ Environment & network self-heal completed",
    },
    "ar": {
        "app_title": "استوديو Google AI التجريبي",
        "dev_connected": "متصل",
        "dev_disconnected": "المحاكي غير متصل",
        "no_account": "لا يوجد حساب",
        "btn_connect": "اتصال / تشغيل",
        "btn_screen": "شاشة المحاكي",
        "btn_doctor": "إصلاح تلقائي",
        "btn_refresh": "تحديث",
        "tab_quick": "التفعيل السريع",
        "tab_scan": "فحص العروض",
        "tab_batch": "التشغيل الجماعي",
        "tab_settings": "الإعدادات والدليل",
        "seg_free": "تجارب مجانية ($0)",
        "seg_promo": "عروض Ultra المخفضة",
        "seg_custom": "معرّف SKU مخصص",
        "btn_launch": "فتح نافذة الدفع",
        "custom_placeholder": "أدخل معرّف الباقة مثل g1.2tb.ai.subs_variant",
        "btn_custom_go": "فحص وفتح",
        "util_ack": "مزامنة وتأكيد الطلب",
        "util_subs": "إدارة اشتراكات Play",
        "util_cancel": "إلغاء التجديد التلقائي",
        "days_left_fmt": "متبقي {days} يوماً",
        "no_active_sub": "لا يوجد اشتراك نشط",
        "scan_all": "الكل",
        "scan_trial": "مجاني ($0)",
        "scan_promo": "عروض مخفضة",
        "scan_base": "عادي",
        "scan_search": "بحث بالاسم أو معرّف العرض...",
        "btn_scan_now": "فحص الآن",
        "scan_idle": "اضغط «فحص الآن» لعرض جميع الباقات المخفية والمتاحة للحساب الحالي",
        "scan_running": "جارٍ فحص 20 باقة عبر 4 دفعات...",
        "scan_empty": "لم يتم العثور على عروض (تأكد من تسجيل الدخول وفتح متجر Google Play مرة واحدة)",
        "col_plan": "الباقة",
        "col_tag": "النوع",
        "col_price": "التسعير",
        "col_action": "إجراء",
        "btn_instant": "فتح فوري",
        "batch_safety": "حماية صارمة ضد الخصم غير المجاني",
        "batch_accts_lbl": "قائمة الحسابات (اسحب ملف .txt/.csv أو الصق هنا)",
        "batch_cards_lbl": "قائمة البطاقات (اتركها فارغة إذا كانت مدمجة مع الحساب)",
        "batch_import_file": "اختيار ملف",
        "batch_stat_idle": "بانتظار إدخال الحسابات والبطاقات...",
        "batch_stat_parsed": "تم قراءة {a} حساب ({e} بطاقة مدمجة) · {c} بطاقة مستقلة",
        "card_rotate": "تدوير البطاقات",
        "card_single": "تثبيت البطاقة الأولى",
        "btn_batch_start": "بدء التشغيل",
        "btn_batch_stop": "إيقاف",
        "col_email": "الحساب",
        "col_status": "الحالة",
        "col_detail": "التفاصيل",
        "col_time": "المدة",
        "scr_title": "شاشة المحاكي المباشرة (انقر على الصورة للتحكم)",
        "scr_live": "بث تلقائي",
        "scr_hint": "اضغط «تحديث الصورة» أو فعّل «بث تلقائي» لعرض شاشة المحاكي والتحكم بها",
        "btn_scr_shot": "تحديث الصورة",
        "btn_scr_back": "رجوع",
        "btn_scr_home": "الرئيسية",
        "btn_scr_pw": "إدخال كلمة المرور",
        "set_profile": "التفضيلات وإعدادات الأتمتة",
        "lbl_name": "الاسم المستعار",
        "lbl_reset": "طريقة تهيئة Google One في الوضع الجماعي",
        "opt_smart": "مسح بيانات سريع (يوفر 45 ثانية لكل حساب)",
        "opt_reinstall": "إعادة تثبيت كاملة من المتجر",
        "lbl_postal": "الرمز البريدي الأمريكي الافتراضي",
        "opt_classic": "قياسي (92101 / 89101 / 33131)",
        "opt_taxfree": "ولايات بدون ضرائب (97201 / 19801)",
        "lbl_sound": "تفعيل التنبيهات الصوتية",
        "lbl_anim": "إيقاف حركات النظام لتسريع الواجهة",
        "lbl_autocancel": "إلغاء التجديد التلقائي بعد تفعيل التجربة المجانية",
        "btn_save_prefs": "حفظ الإعدادات",
        "faq_title": "الأسئلة الشائعة وفحص الشبكة",
        "faqs": [
            {"q": "1. الكمبيوتر متصل بالبروكسي، لماذا يظهر متجر Play بدون إنترنت داخل المحاكي؟", "a": "يرجى تفعيل وضع TUN في برنامج البروكسي على جهازك (وتشغيله كمسؤول في Windows)، وتجنب تشغيل VPN إضافي داخل المحاكي. اضغط «إصلاح تلقائي» بالأعلى لمسح إعدادات البروكسي العالقة وإزالة تنبيه انقطاع الإنترنت الكاذب."},
            {"q": "2. شروط تجميع 24 شهراً مجاناً في Pro وعرض خصم 90% في Ultra؟", "a": "• تجميع Pro (الخطوة 2 و3): لا تقم بإلغاء التجديد التلقائي بعد الخطوة 1 حتى تصل إلى 24 شهراً كاملة، ثم ألغِ التجديد.\n• عروض Ultra بخصم 90%: متاحة فقط للحسابات التي لا تملك أي اشتراك Google One نشط حالياً."},
            {"q": "3. تم الدفع ولكن المساحة ما زالت 15GB؟", "a": "اضغط «مزامنة وتأكيد الطلب» لتنفيذ acknowledgePurchase وتحديث تطبيق Google One فوراً."},
            {"q": "4. ظهور خطأ OR-HDT-01 أو عدم الأهلية؟", "a": "تأكد من تطابق دولة ملف الدفع في Google Pay مع دولة إصدار البطاقة (أول 6 أرقام BIN) واستخدم عنوان IP نظيفاً."},
        ],
        "human_title": "مطلوب تدخل يدوي:",
        "human_cont": "أكملت الإجراء، متابعة",
        "human_skip": "تخطي الحساب",
        "human_abort": "إنهاء المهمة",
        "logs_toggle": "سجل العمليات",
        "logs_ready": "جاهز · انقر لعرض السجل التفصيلي",
        "ad_blog": "المدونة التقنية",
        "ad_faka": "متجر شحن GPT (يقدم خدمة شحن ChatGPT فقط)",
        "confirm_paid": "تأكيد باقة مدفوعة مخفضة:\n{title}\n\nتقوم الأداة بفتح نافذة Google Play فقط ولن تضغط على زر الاشتراك تلقائياً أبداً. هل تريد المتابعة؟",
        "confirm_cancel": "هل تريد فتح اشتراكات Google Play وإلغاء التجديد التلقائي الآن؟ (ستبقى الأيام المجانية الحالية فعالة بالكامل)",
        "prompt_pw": "أدخل كلمة مرور حساب Google لإدخالها تلقائياً في نافذة التحقق:",
        "toast_launching": "جارٍ فتح نافذة الدفع: {title}...",
        "toast_launched": "✓ تم فتح نافذة الدفع في المحاكي: {title}",
        "toast_failed": "تعذر الفتح: {err}",
        "toast_saved": "✓ تم حفظ الإعدادات",
        "toast_ack": "✓ اكتملت المزامنة: {c} اشتراك نشط، تم تأكيد {a} جديد",
        "toast_doctor": "✓ اكتمل الفحص والإصلاح التلقائي",
    },
    "ru": {
        "app_title": "Google AI Trial Studio",
        "dev_connected": "Подключено",
        "dev_disconnected": "Эмулятор не подключен",
        "no_account": "Нет аккаунта",
        "btn_connect": "Подключить",
        "btn_screen": "Экран",
        "btn_doctor": "Диагностика",
        "btn_refresh": "Обновить",
        "tab_quick": "Быстрый старт",
        "tab_scan": "Сканер офферов",
        "tab_batch": "Пакетный режим",
        "tab_settings": "Настройки и FAQ",
        "seg_free": "Бесплатные ($0)",
        "seg_promo": "Промо Ultra",
        "seg_custom": "Свой SKU",
        "btn_launch": "Открыть оплату",
        "custom_placeholder": "Введите SKU, напр. g1.2tb.ai.subs_variant",
        "btn_custom_go": "Открыть SKU",
        "util_ack": "Синхр. / Подтвердить заказ",
        "util_subs": "Подписки Google Play",
        "util_cancel": "Отменить автопродление",
        "days_left_fmt": "Осталось {days} дн.",
        "no_active_sub": "Нет подписки",
        "scan_all": "Все",
        "scan_trial": "$0 Триал",
        "scan_promo": "Скидки",
        "scan_base": "Базовые",
        "scan_search": "Поиск по названию или Offer ID...",
        "btn_scan_now": "Сканировать",
        "scan_idle": "Нажмите «Сканировать», чтобы получить все скрытые и доступные тарифы аккаунта",
        "scan_running": "Сканирование 20 SKU в 4 волны...",
        "scan_empty": "Тарифы не найдены (убедитесь, что выполнен вход в аккаунт и открывался Play Маркет)",
        "col_plan": "Тариф",
        "col_tag": "Тип",
        "col_price": "Условия",
        "col_action": "Действие",
        "btn_instant": "Открыть (0.2с)",
        "batch_safety": "Строгая защита от списаний > $0",
        "batch_accts_lbl": "Аккаунты (перетащите .txt/.csv или вставьте текст)",
        "batch_cards_lbl": "Карты (оставьте пустым, если карты встроены в строки аккаунтов)",
        "batch_import_file": "Выбрать файл",
        "batch_stat_idle": "Ожидание списка аккаунтов и карт...",
        "batch_stat_parsed": "Загружено аккаунтов: {a} (встроенных карт: {e}) · отдельных карт: {c}",
        "card_rotate": "Ротация карт",
        "card_single": "Первая карта",
        "btn_batch_start": "Запустить",
        "btn_batch_stop": "Стоп",
        "col_email": "Аккаунт",
        "col_status": "Статус",
        "col_detail": "Детали",
        "col_time": "Время",
        "scr_title": "Экран эмулятора (клик по картинке = нажатие)",
        "scr_live": "Автопоток",
        "scr_hint": "Нажмите «Обновить» или включите «Автопоток» для управления экраном эмулятора",
        "btn_scr_shot": "Обновить",
        "btn_scr_back": "Назад",
        "btn_scr_home": "Домой",
        "btn_scr_pw": "Ввести пароль",
        "set_profile": "Основные настройки и автоматизация",
        "lbl_name": "Имя / Никнейм",
        "lbl_reset": "Сброс Google One в пакетном режиме",
        "opt_smart": "Быстрый pm clear (экономит ~45с/акк)",
        "opt_reinstall": "Полная переустановка из Play Маркета",
        "lbl_postal": "Пул почтовых индексов США (ZIP)",
        "opt_classic": "Стандартный (92101 / 89101 / 33131)",
        "opt_taxfree": "Безналоговые штаты (97201 / 19801)",
        "lbl_sound": "Звуковые уведомления",
        "lbl_anim": "Отключить анимации эмулятора (ускорение UI)",
        "lbl_autocancel": "Автоотмена продления после активации триала",
        "btn_save_prefs": "Сохранить настройки",
        "faq_title": "Частые вопросы и проверка сети",
        "faqs": [
            {"q": "1. На ПК прокси работает, но в эмуляторе Play Маркет пишет «Нет интернета»?", "a": "Включите режим TUN в вашем прокси-клиенте (Clash Verge / v2rayN в Windows запускайте от имени Администратора) и не включайте второй VPN внутри эмулятора. Нажмите «Диагностика» сверху для автоочистки зависшего прокси."},
            {"q": "2. Условия для сборки 24 месяцев Pro и скидки 90% на Ultra?", "a": "• Продление Pro (Шаг 2 и 3): не отключайте автопродление после 1-го шага, пока не соберете все 24 месяца; отменяйте продление только в конце.\n• Скидки Ultra 90%: доступны только на чистых аккаунтах без активных подписок Google One."},
            {"q": "3. Оплата прошла, но хранилище всё ещё 15 ГБ?", "a": "Нажмите «Синхр. / Подтвердить заказ» для вызова acknowledgePurchase и перезапуска Google One."},
            {"q": "4. Ошибка OR-HDT-01 или «Недоступно»?", "a": "Страна платежного профиля Google Pay должна совпадать со страной BIN карты (первые 6 цифр). Используйте чистый резидентский IP."},
        ],
        "human_title": "Требуется действие:",
        "human_cont": "Готово, продолжить",
        "human_skip": "Пропустить аккаунт",
        "human_abort": "Прервать",
        "logs_toggle": "Журнал событий",
        "logs_ready": "Готово · Нажмите, чтобы развернуть журнал",
        "ad_blog": "Техноблог",
        "ad_faka": "Магазин пополнения GPT (только пополнение ChatGPT)",
        "confirm_paid": "Подтверждение платного промо-тарифа:\n{title}\n\nИнструмент ТОЛЬКО откроет шторку оплаты Google Play и НЕ будет нажимать кнопку подписки. Продолжить?",
        "confirm_cancel": "Перейти в подписки Google Play и автоматически отменить продление? (Бесплатный период полностью сохранится.)",
        "prompt_pw": "Введите пароль аккаунта Google для безопасного автоввода в окне подтверждения:",
        "toast_launching": "Открытие окна оплаты: {title}...",
        "toast_launched": "✓ Окно оплаты открыто в эмуляторе: {title}",
        "toast_failed": "Не удалось открыть: {err}",
        "toast_saved": "✓ Настройки сохранены",
        "toast_ack": "✓ Синхронизация завершена: активных {c}, подтверждено {a}",
        "toast_doctor": "✓ Диагностика и восстановление завершены",
    },
    "es": {
        "app_title": "Google AI Trial Studio",
        "dev_connected": "Conectado",
        "dev_disconnected": "Emulador desconectado",
        "no_account": "Sin cuenta",
        "btn_connect": "Conectar",
        "btn_screen": "Pantalla",
        "btn_doctor": "Auto-Reparar",
        "btn_refresh": "Actualizar",
        "tab_quick": "Inicio Rápido",
        "tab_scan": "Escáner",
        "tab_batch": "Lotes Auto",
        "tab_settings": "Ajustes y Ayuda",
        "seg_free": "Pruebas Gratis ($0)",
        "seg_promo": "Promos Ultra",
        "seg_custom": "SKU Personalizado",
        "btn_launch": "Abrir Pago",
        "custom_placeholder": "Introduce SKU, ej. g1.2tb.ai.subs_variant",
        "btn_custom_go": "Abrir SKU",
        "util_ack": "Sincronizar Pedido",
        "util_subs": "Suscripciones Play",
        "util_cancel": "Cancelar Renovación",
        "days_left_fmt": "{days}d restantes",
        "no_active_sub": "Sin plan activo",
        "scan_all": "Todos",
        "scan_trial": "$0 Gratis",
        "scan_promo": "Promos",
        "scan_base": "Estándar",
        "scan_search": "Buscar por nombre u Offer ID...",
        "btn_scan_now": "Escanear",
        "scan_idle": "Pulsa «Escanear» para consultar todas las ofertas ocultas y públicas",
        "scan_running": "Escaneando 20 SKUs en 4 oleadas...",
        "scan_empty": "No se encontraron ofertas (asegúrate de haber abierto Google Play Store una vez)",
        "col_plan": "Plan",
        "col_tag": "Tipo",
        "col_price": "Precio",
        "col_action": "Acción",
        "btn_instant": "Abrir 0.2s",
        "batch_safety": "Protección estricta $0 activada",
        "batch_accts_lbl": "Cuentas (arrastra .txt/.csv o pega aquí)",
        "batch_cards_lbl": "Tarjetas (vacío si van integradas en las cuentas)",
        "batch_import_file": "Elegir archivo",
        "batch_stat_idle": "Esperando cuentas y tarjetas...",
        "batch_stat_parsed": "{a} cuentas ({e} tarjetas integradas) · {c} tarjetas sueltas",
        "card_rotate": "Rotar tarjetas",
        "card_single": "Fijar 1.ª tarjeta",
        "btn_batch_start": "Iniciar lote",
        "btn_batch_stop": "Detener",
        "col_email": "Cuenta",
        "col_status": "Estado",
        "col_detail": "Detalle",
        "col_time": "Tiempo",
        "scr_title": "Pantalla del emulador (clic para tocar)",
        "scr_live": "En vivo",
        "scr_hint": "Pulsa «Actualizar» o activa «En vivo» para ver y controlar el emulador",
        "btn_scr_shot": "Actualizar",
        "btn_scr_back": "Atrás",
        "btn_scr_home": "Inicio",
        "btn_scr_pw": "Rellenar clave",
        "set_profile": "Preferencias y Automatización",
        "lbl_name": "Nombre / Alias",
        "lbl_reset": "Modo de reinicio de Google One",
        "opt_smart": "pm clear rápido (ahorra ~45s/cuenta)",
        "opt_reinstall": "Reinstalar desde Play Store",
        "lbl_postal": "Códigos postales de EE. UU. (ZIP)",
        "opt_classic": "Estándar (92101 / 89101 / 33131)",
        "opt_taxfree": "Estados sin impuestos (97201 / 19801)",
        "lbl_sound": "Sonidos de notificación",
        "lbl_anim": "Modo rápido sin animaciones",
        "lbl_autocancel": "Cancelar renovación tras activar prueba gratis",
        "btn_save_prefs": "Guardar ajustes",
        "faq_title": "Preguntas frecuentes y red",
        "faqs": [
            {"q": "1. ¿Por qué Play Store aparece sin conexión en el emulador?", "a": "Activa el modo TUN en tu proxy del sistema (ejecuta Clash / v2rayN como Administrador en Windows) y no uses otra VPN dentro del emulador. Pulsa «Auto-Reparar» arriba para limpiar proxies residuales."},
            {"q": "2. ¿Requisitos para acumular 24 meses Pro y Ultra 90% dto.?", "a": "• Acumular Pro (Pasos 2 y 3): mantén la renovación activa hasta completar los 24 meses y cancélala al final.\n• Ultra 90% dto.: solo disponible en cuentas sin suscripción activa de Google One."},
            {"q": "3. ¿Pagaste pero sigue mostrando 15 GB?", "a": "Pulsa «Sincronizar Pedido» para confirmar la compra (acknowledgePurchase) y refrescar Google One."},
            {"q": "4. ¿Error OR-HDT-01 o No elegible?", "a": "El país de Google Pay debe coincidir con el país BIN de la tarjeta y un IP limpio de la misma región."},
        ],
        "human_title": "Asistencia manual requerida:",
        "human_cont": "Listo, continuar",
        "human_skip": "Saltar cuenta",
        "human_abort": "Cancelar lote",
        "logs_toggle": "Registro",
        "logs_ready": "Listo · Clic para mostrar registro detallado",
        "ad_blog": "Blog Técnico",
        "ad_faka": "Tienda de Recarga GPT (Solo recarga de ChatGPT)",
        "confirm_paid": "Confirmación de promoción de pago:\n{title}\n\nEsta herramienta SOLO abre Google Play y NUNCA pulsará Suscribirse automáticamente. ¿Continuar?",
        "confirm_cancel": "¿Abrir suscripciones de Google Play y cancelar la renovación automática ahora? (Tus días gratis se conservan.)",
        "prompt_pw": "Introduce la contraseña de la cuenta Google para rellenarla automáticamente:",
        "toast_launching": "Abriendo pasarela: {title}...",
        "toast_launched": "✓ Pasarela abierta en el emulador: {title}",
        "toast_failed": "No se pudo abrir: {err}",
        "toast_saved": "✓ Ajustes guardados",
        "toast_ack": "✓ Sincronizado: {c} suscripción(es) activa(s), {a} confirmada(s)",
        "toast_doctor": "✓ Diagnóstico y reparación completados",
    },
}


# ---------- Console TUI Key Strings ----------

TUI_STRINGS: Dict[str, Dict[str, str]] = {
    "zh": {
        "banner_title": "Google AI Pro / Ultra Trial Studio · 多语言智能领航版",
        "ad_blog_lbl": "博客",
        "ad_faka_lbl": "GPT代充",
        "radar_title": "实时设备态势",
        "radar_refresh_hint": "(按 R 刷新 · 按 L 切换语言)",
        "lbl_emu": "模拟器",
        "lbl_acct": "当前号",
        "lbl_chain": "组件链",
        "lbl_wizard": "叠加链",
        "lbl_advice": "建议",
        "online": "在线",
        "waiting": "待连接",
        "no_google": "未登录 Google 账号",
        "m1": "🚀 热门方案一键直达",
        "m1_sub": "Pro免费12月 / 24月叠加 / Ultra 1折",
        "m2": "🔍 实时扫描全量方案",
        "m2_sub": "分类筛选 · 0.2 秒弹出收银台",
        "m3": "📦 多号全自动批量流水线",
        "m3_sub": "拖拽导入 · 严格 $0 防误扣",
        "mw": "🌐 打开极简图形化面板 (Web Studio)",
        "mw_sub": "清爽卡片视图 + 多语言切换 + 可选屏幕遥控",
        "m4": "🛠️  环境自愈 · 补单同步 · 多开管理",
        "m4_sub": "一键修网络 / 付款未到账补单 / 取消续费",
        "m5": "⚙️  个性化与默认设置",
        "m5_sub": "昵称 / 音效 / 重置策略 / 邮编池",
        "ml": "🌍 切换界面语言 (Language / اللغة / Язык)",
        "mh": "📖 常见问题与网络自查手册",
        "mb": "🔗 访问技术博客 & GPT代充发卡网",
        "mq": "👋 安全退出",
        "replay": "⚡ 一键复刻上次方案 → ",
        "wiz_go": "🧙 智能向导推荐下一步 → ",
        "desc_box": "当前选中说明",
        "footer": "↑/↓ 移动 · Enter 确认 · L 语言 · W 网页版 · R 刷新 · Q 退出",
    },
    "en": {
        "banner_title": "Google AI Pro / Ultra Trial Studio · Multilingual Edition",
        "ad_blog_lbl": "Blog",
        "ad_faka_lbl": "GPT Top-Up",
        "radar_title": "Device Status",
        "radar_refresh_hint": "(Press R to refresh · Press L for Language)",
        "lbl_emu": "Device ",
        "lbl_acct": "Account",
        "lbl_chain": "Modules",
        "lbl_wizard": "24m Map",
        "lbl_advice": "Next   ",
        "online": "Online",
        "waiting": "Standby",
        "no_google": "Not signed in to Google",
        "m1": "🚀 One-Click Curated Plans (Presets)",
        "m1_sub": "Pro 12m Free / 24m Stack / Ultra 90% Off",
        "m2": "🔍 Scan All Live Offers",
        "m2_sub": "Filter & launch checkout in 0.2s",
        "m3": "📦 Smart Multi-Account Batch Runner",
        "m3_sub": "Drag & drop · Strict $0 safety guard",
        "mw": "🌐 Open Clean Graphical Studio (Web UI)",
        "mw_sub": "Minimalist UI + RTL/Multilingual + Screen Remote",
        "m4": "🛠️  Self-Heal · Order Sync · MuMu Manager",
        "m4_sub": "Fix network / Acknowledge order / Cancel renewal",
        "m5": "⚙️  Preferences & Automation Settings",
        "m5_sub": "Name / Sound / Reset mode / US ZIP pool",
        "ml": "🌍 Switch Language (中文 / EN / العربية / RU / ES)",
        "mh": "📖 Troubleshooting & Network Guide",
        "mb": "🔗 Tech Blog & GPT Top-Up Store",
        "mq": "👋 Quit Safely",
        "replay": "⚡ Replay Last Plan → ",
        "wiz_go": "🧙 Smart Next Step → ",
        "desc_box": "Selected Option",
        "footer": "↑/↓ Move · Enter Select · L Language · W Web UI · R Refresh · Q Quit",
    },
    "ar": {
        "banner_title": "Google AI Pro / Ultra Studio · النسخة متعددة اللغات",
        "ad_blog_lbl": "المدونة",
        "ad_faka_lbl": "شحن GPT",
        "radar_title": "حالة المحاكي",
        "radar_refresh_hint": "(اضغط R للتحديث · اضغط L لتغيير اللغة)",
        "lbl_emu": "المحاكي",
        "lbl_acct": "الحساب ",
        "lbl_chain": "المكونات",
        "lbl_wizard": "مسار 24ش",
        "lbl_advice": "النصيحة",
        "online": "متصل",
        "waiting": "غير متصل",
        "no_google": "لم يتم تسجيل الدخول إلى Google",
        "m1": "🚀 الباقات الجاهزة السريعة (Presets)",
        "m1_sub": "Pro مجاناً 12 شهراً / تجميع 24 شهراً / خصم Ultra 90%",
        "m2": "🔍 فحص جميع العروض المتاحة مباشرة",
        "m2_sub": "تصفية وفتح الدفع خلال 0.2 ثانية",
        "m3": "📦 التشغيل التلقائي لمجموعة حسابات",
        "m3_sub": "حماية صارمة للعروض المجانية $0",
        "mw": "🌐 فتح الواجهة الرسومية المبسطة (Web Studio)",
        "mw_sub": "تدعم العربية من اليمين لليسار (RTL) والتحكم بالشاشة",
        "m4": "🛠️  الإصلاح التلقائي · تأكيد الطلب · إدارة المحاكي",
        "m4_sub": "إصلاح الشبكة / مزامنة السعة / إلغاء التجديد",
        "m5": "⚙️  الإعدادات والتفضيلات",
        "m5_sub": "الاسم / الصوت / الرمز البريدي",
        "ml": "🌍 تغيير اللغة (العربية / 中文 / EN / RU / ES)",
        "mh": "📖 دليل الشبكة وحل المشاكل الشائعة",
        "mb": "🔗 المدونة التقنية ومتجر شحن GPT",
        "mq": "👋 خروج آمن",
        "replay": "⚡ إعادة تشغيل آخر باقة ← ",
        "wiz_go": "🧙 الخطوة المقترحة ← ",
        "desc_box": "وصف الخيار المحدد",
        "footer": "↑/↓ تنقل · Enter تأكيد · L اللغة · W واجهة الويب · R تحديث · Q خروج",
    },
    "ru": {
        "banner_title": "Google AI Pro / Ultra Studio · Мультиязычная версия",
        "ad_blog_lbl": "Блог",
        "ad_faka_lbl": "Оплата GPT",
        "radar_title": "Статус системы",
        "radar_refresh_hint": "(R — обновить · L — сменить язык)",
        "lbl_emu": "Эмулятор",
        "lbl_acct": "Аккаунт ",
        "lbl_chain": "Модули  ",
        "lbl_wizard": "План 24м",
        "lbl_advice": "Совет   ",
        "online": "Онлайн",
        "waiting": "Ожидание",
        "no_google": "Вход в Google не выполнен",
        "m1": "🚀 Готовые тарифы в 1 клик (Presets)",
        "m1_sub": "Pro 12 мес. $0 / Сборка 24 мес. / Ultra -90%",
        "m2": "🔍 Сканировать все доступные офферы",
        "m2_sub": "Фильтры и открытие оплаты за 0.2 сек.",
        "m3": "📦 Автоматический пакетный режим (Batch)",
        "m3_sub": "Импорт списков · Строгая защита $0",
        "mw": "🌐 Открыть графическую панель (Web Studio)",
        "mw_sub": "Минималистичный UI + выбор языка + экран эмулятора",
        "m4": "🛠️  Диагностика · Синхр. заказа · MuMu",
        "m4_sub": "Починка сети / Подтверждение оплаты / Отмена продления",
        "m5": "⚙️  Персонализация и настройки",
        "m5_sub": "Имя / Звук / Сброс / Индексы США",
        "ml": "🌍 Сменить язык (Русский / 中文 / EN / العربية / ES)",
        "mh": "📖 Справочник по сети и частым ошибкам",
        "mb": "🔗 Техноблог и магазин пополнения ChatGPT",
        "mq": "👋 Выход",
        "replay": "⚡ Повторить прошлый запуск → ",
        "wiz_go": "🧙 Рекомендуемый шаг → ",
        "desc_box": "Описание выбранного пункта",
        "footer": "↑/↓ Выбор · Enter Ок · L Язык · W Веб-панель · R Обновить · Q Выход",
    },
    "es": {
        "banner_title": "Google AI Pro / Ultra Studio · Edición Multilingüe",
        "ad_blog_lbl": "Blog",
        "ad_faka_lbl": "Recarga GPT",
        "radar_title": "Estado del sistema",
        "radar_refresh_hint": "(R actualizar · L cambiar idioma)",
        "lbl_emu": "Emulador",
        "lbl_acct": "Cuenta  ",
        "lbl_chain": "Módulos ",
        "lbl_wizard": "Ruta 24m",
        "lbl_advice": "Consejo ",
        "online": "En línea",
        "waiting": "En espera",
        "no_google": "Sin sesión de Google",
        "m1": "🚀 Planes rápidos en 1 clic (Presets)",
        "m1_sub": "Pro 12m gratis / 24m / Ultra 90% dto.",
        "m2": "🔍 Escanear todas las ofertas",
        "m2_sub": "Filtra y abre pago en 0.2s",
        "m3": "📦 Modo automático por lotes (Batch)",
        "m3_sub": "Importar cuentas · Protección estricta $0",
        "mw": "🌐 Abrir panel gráfico minimalista (Web UI)",
        "mw_sub": "Interfaz limpia + Multilingüe + Control de pantalla",
        "m4": "🛠️  Auto-reparación · Sincronizar · MuMu",
        "m4_sub": "Red / Confirmar compra / Cancelar renovación",
        "m5": "⚙️  Ajustes y preferencias",
        "m5_sub": "Alias / Sonido / Reinicio / ZIP EE. UU.",
        "ml": "🌍 Cambiar idioma (Español / 中文 / EN / العربية / RU)",
        "mh": "📖 Guía de red y solución de problemas",
        "mb": "🔗 Blog técnico y recarga de ChatGPT",
        "mq": "👋 Salir",
        "replay": "⚡ Repetir último plan → ",
        "wiz_go": "🧙 Siguiente paso sugerido → ",
        "desc_box": "Descripción",
        "footer": "↑/↓ Mover · Enter Elegir · L Idioma · W Panel Web · R Actualizar · Q Salir",
    },
}
