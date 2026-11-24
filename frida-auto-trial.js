// frida-auto-trial.js — Google One: real-time SKU scanner, instant IPC launch, stacking & auto-acknowledge
// 博客：https://blog.caowo.de/
// 发卡网：https://faka.cdkey.si/
//
// Compatible with Frida 16.x & Frida 17.x CLI:
//   frida -q -t inf -H 127.0.0.1:<PORT> -p <PID> -l frida-auto-trial.js

// ===== CONFIG (patched by gtool.py / auto-trial.sh / batch-trial.sh) =====
var MODE = "activate";
var TARGET_PRODUCT = "auto";
var PREFER_DURATION = "longest";
var SELECTED_OFFER_INDEX = -1;
var TARGET_SKU = "";
var TARGET_OFFER_ID = "";
var STACK_ENABLED = false;
var OLD_PURCHASE_TOKEN = "";
var STACK_PRORATION_MODE = 5; // 5 = CHARGE_FULL_PRICE
var MODULE_APK = "/data/local/tmp/module.apk";
// ===== END CONFIG =====

var __keepAliveTimer = null;
var __cmdPollTimer = null;
var __bootAttempts = 0;

function bootAutoTrial() {
    Java.perform(function() {
        var TAG = "AutoTrial";
        Java.classFactory.loader = null;
        var Log = Java.use("android.util.Log");

        function emit(msg) {
            var s = String(msg);
            try { console.log("[AT] " + s); } catch (e) {}
            try { Log.i(TAG, s); } catch (e2) {}
        }
        function emitErr(msg) {
            var s = String(msg);
            try { console.log("[AT] " + s); } catch (e) {}
            try { Log.e(TAG, s); } catch (e2) {}
        }

        var AT = Java.use("android.app.ActivityThread");
        var app = AT.currentApplication();
        if (!app) {
            __bootAttempts++;
            if (__bootAttempts <= 20) {
                emit("BOOT_WAIT Waiting for Google One Application context (" + __bootAttempts + "/20)...");
                setTimeout(bootAutoTrial, 250);
                return;
            }
            emitErr("=== CONNECT_FAILED code=-1 msg=Application context null ===");
            return;
        }

        var context = app.getApplicationContext();
        var Activity = Java.use("android.app.Activity");
        var ArrayList = Java.use("java.util.ArrayList");
        var List = Java.use("java.util.List");
        var Handler = Java.use("android.os.Handler");
        var Looper = Java.use("android.os.Looper");
        var JavaFile = Java.use("java.io.File");
        var FileInputStream = Java.use("java.io.FileInputStream");
        var FileOutputStream = Java.use("java.io.FileOutputStream");
        var InputStreamReader = Java.use("java.io.InputStreamReader");
        var BufferedReader = Java.use("java.io.BufferedReader");

        var cacheDir = context.getCacheDir().getAbsolutePath();
        var cmdFilePath = cacheDir + "/.gtool_cmd";
        var cmdFile = JavaFile.$new(cmdFilePath);
        var extCmdFile = null;
        try {
            var extCache = context.getExternalCacheDir();
            if (extCache != null) {
                extCmdFile = JavaFile.$new(extCache.getAbsolutePath() + "/.gtool_cmd");
            }
        } catch (ece) {}

        function initIpcFile(f) {
            if (!f) return;
            try {
                var parent = f.getParentFile();
                if (parent && !parent.exists()) parent.mkdirs();
                if (!f.exists()) {
                    f.createNewFile();
                } else if (f.length() > 0) {
                    FileOutputStream.$new(f, false).close();
                }
                f.setReadable(true, false);
                f.setWritable(true, false);
            } catch (ie) {}
        }
        initIpcFile(cmdFile);
        initIpcFile(extCmdFile);

        emit("=== AUTO_TRIAL_START mode=" + MODE + " target=" + TARGET_PRODUCT + " prefer=" + PREFER_DURATION + " sku=" + TARGET_SKU + " offer=" + TARGET_OFFER_ID + " stack=" + STACK_ENABLED + " ===");

        var dexLoader = null;
        var BillingClient, QueryProductDetailsParams, QpdProduct, BillingFlowParams, BfpProductDetailsParams;
        var PurchasesUpdatedListener, BillingClientStateListener, ProductDetailsResponseListener;
        var ProductDetails, SubscriptionOfferDetails, PricingPhase, Purchase;

        try {
            var DexClassLoader = Java.use("dalvik.system.DexClassLoader");
            dexLoader = DexClassLoader.$new(
                MODULE_APK,
                context.getCodeCacheDir().getAbsolutePath(),
                null,
                context.getClassLoader()
            );
            Java.classFactory.loader = dexLoader;

            BillingClient = Java.use("com.android.billingclient.api.BillingClient");
            QueryProductDetailsParams = Java.use("com.android.billingclient.api.QueryProductDetailsParams");
            QpdProduct = Java.use("com.android.billingclient.api.QueryProductDetailsParams$Product");
            BillingFlowParams = Java.use("com.android.billingclient.api.BillingFlowParams");
            BfpProductDetailsParams = Java.use("com.android.billingclient.api.BillingFlowParams$ProductDetailsParams");
            PurchasesUpdatedListener = Java.use("com.android.billingclient.api.PurchasesUpdatedListener");
            BillingClientStateListener = Java.use("com.android.billingclient.api.BillingClientStateListener");
            ProductDetailsResponseListener = Java.use("com.android.billingclient.api.ProductDetailsResponseListener");
            ProductDetails = Java.use("com.android.billingclient.api.ProductDetails");
            SubscriptionOfferDetails = Java.use("com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails");
            PricingPhase = Java.use("com.android.billingclient.api.ProductDetails$PricingPhase");
            Purchase = Java.use("com.android.billingclient.api.Purchase");
            emit("DEX_LOADED BillingClient classes loaded from " + MODULE_APK);
        } catch (de) {
            emitErr("=== CONNECT_FAILED code=-2 msg=DexClassLoader failed: " + de + " ===");
            return;
        }

        var PRODUCTS = [
            // Wave 1: $0 Free Trial & 24-Month Stackable Pools (Verified Live Nov 2026)
            "g1.2tb.ai.subs_variant",           // AI Pro 5TB (12m + 6m×3 free trial & stackable)
            "g1.play.2tb.ai",                   // AI Pro 5TB (3m free trial)
            "g1.2tb.subs_variant",              // Google One 2TB (6m & 3m independent $0 trial pool)
            // Wave 2: AI Pro 5TB 1折~5折特惠神车 (Verified Live Nov 2026)
            "g1.2tb.ai.12months_ip_90p",        // AI Pro 5TB 连续12个月1折 ($1.99/£1.89 × 12mo)
            "g1.2tb.ai.3months_ip_90p.acq",     // AI Pro 5TB 前3月1折 ($1.99/£1.89 × 3mo)
            "g1.2tb.ai.1month_ip_90p.acq",      // AI Pro 5TB 首月1折 ($1.99/£1.89 × 1mo)
            "g1.2tb.ai.12months_ip_75p",        // AI Pro 5TB 连续12个月2.5折 ($4.99/£4.79 × 12mo)
            "g1.2tb.ai.3months_ip_75p.acq",     // AI Pro 5TB 前3月2.5折 ($4.99/£4.79 × 3mo)
            "g1.2tb.ai.12months_ip_50p",        // AI Pro 5TB 连续12个月5折 ($9.99/£9.49 × 12mo)
            "g1.2tb.ai.3months_ip_50p",         // AI Pro 5TB 前3月5折
            "g1.play.2tb.ai.student",           // AI Pro 5TB 学生特惠档
            "g1.2tb.ai.annual",                 // AI Pro 5TB 年付档
            "g1.2tb.ai",                        // AI Pro 5TB 标准月付
            // Wave 3: AI Ultra 30TB (20x) & 20TB (5x) 特惠与旗舰 (Verified Live Nov 2026)
            "g1.ai.ultra.1month_ip_90p.acq",    // Ultra 30TB (20x) 首月1折 ($19.99/£18.99)
            "g1.ai.ultra.3months_ip_80p.acq",   // Ultra 30TB (20x) 前3月2折 ($39.99/£37.99 × 3mo)
            "g1.ai.ultra.3months_ip_80p",       // Ultra 30TB (20x) 前3月2折 (非acq)
            "g1.ai.ultra.3months_ip_75p.acq",   // Ultra 30TB (20x) 前3月2.5折 ($49.99/£47.49 × 3mo)
            "g1.ai.pro.3months_ip_50p",         // Ultra 30TB (20x) 前3月5折
            "g1.ai.ultra.2months_ip_50p.acq",   // Ultra 30TB (20x) 前2月5折
            "g1.play.ai.pro",                   // Ultra 30TB (20x) Play 旗舰
            "g1.ai.pro",                        // Ultra 30TB (20x) 标准旗舰
            "g1.play.20tb",                     // Ultra 20TB (5x) Play 档
            "g1.20tb",                          // Ultra 20TB (5x) 标准档
            // Wave 4: Google One 低价入门与基础容量组
            "g1.100gb.3months_ip_75p",          // 100GB 前3月2.5折 ($0.49/£0.39)
            "g1.2tb.3months_ip_75p",            // 2TB 前3月2.5折 ($2.49/£1.99)
            "g1.30gb",                          // Lite 30GB
            "g1.100gb",                         // Basic 100GB
            "g1.200gb",                         // Standard 200GB
            "g1.2tb"                            // Premium 2TB
        ];

        function ensureProductListed(sku) {
            if (!sku || sku === "auto") return;
            for (var i = 0; i < PRODUCTS.length; i++) {
                if (PRODUCTS[i] === sku) return;
            }
            PRODUCTS.unshift(sku);
        }
        ensureProductListed(TARGET_SKU);
        ensureProductListed(TARGET_PRODUCT);

        var PRODUCT_NAMES = {
            "g1.2tb.ai.subs_variant": "AI Pro 5TB (试用/叠加池)",
            "g1.play.2tb.ai": "AI Pro 5TB (Play 3月池)",
            "g1.2tb.subs_variant": "Google One 2TB (独立试用池)",
            "g1.2tb.ai.12months_ip_90p": "AI Pro 5TB (整年12月1折)",
            "g1.2tb.ai.3months_ip_90p.acq": "AI Pro 5TB (前3月1折)",
            "g1.2tb.ai.1month_ip_90p.acq": "AI Pro 5TB (首月1折)",
            "g1.2tb.ai.12months_ip_75p": "AI Pro 5TB (整年12月2.5折)",
            "g1.2tb.ai.3months_ip_75p.acq": "AI Pro 5TB (前3月2.5折)",
            "g1.2tb.ai.12months_ip_50p": "AI Pro 5TB (整年12月5折)",
            "g1.2tb.ai.3months_ip_50p": "AI Pro 5TB (前3月5折)",
            "g1.play.2tb.ai.student": "AI Pro 5TB (学生专享)",
            "g1.2tb.ai.annual": "AI Pro 5TB (年付版)",
            "g1.2tb.ai": "AI Pro 5TB (标准月付)",
            "g1.ai.ultra.1month_ip_90p.acq": "Ultra 30TB 20x (首月1折)",
            "g1.ai.ultra.3months_ip_80p.acq": "Ultra 30TB 20x (前3月2折)",
            "g1.ai.ultra.3months_ip_80p": "Ultra 30TB 20x (前3月2折·通用)",
            "g1.ai.ultra.3months_ip_75p.acq": "Ultra 30TB 20x (前3月2.5折)",
            "g1.ai.pro.3months_ip_50p": "Ultra 30TB 20x (前3月5折)",
            "g1.ai.ultra.2months_ip_50p.acq": "Ultra 30TB 20x (前2月5折)",
            "g1.play.ai.pro": "AI Ultra 30TB (20x)",
            "g1.ai.pro": "AI Ultra 30TB (Base)",
            "g1.play.20tb": "AI Ultra 20TB (5x)",
            "g1.20tb": "20TB Storage",
            "g1.100gb.3months_ip_75p": "100GB (前3月2.5折)",
            "g1.2tb.3months_ip_75p": "2TB (前3月2.5折)",
            "g1.30gb": "Lite 30GB",
            "g1.100gb": "Basic 100GB",
            "g1.200gb": "Standard 200GB",
            "g1.2tb": "Premium 2TB"
        };

        var DUR = { "P1W": 0.25, "P1M": 1, "P2M": 2, "P3M": 3, "P6M": 6, "P1Y": 12, "P12M": 12 };
        var DUR_LABEL = { "P1W": "7天", "P1M": "1个月", "P2M": "2个月", "P3M": "3个月", "P6M": "6个月", "P1Y": "12个月", "P12M": "12个月" };
        var ALIAS = { "1mo": "P1M", "3mo": "P3M", "6mo": "P6M", "12mo": "P1Y" };

        function parseIsoDurationMonths(iso) {
            if (!iso) return 0;
            if (DUR[iso] !== undefined) return DUR[iso];
            var totalDays = 0;
            var my = /(\d+)Y/.exec(iso);
            var mm = /(\d+)M/.exec(iso);
            var mw = /(\d+)W/.exec(iso);
            var md = /(\d+)D/.exec(iso);
            if (my) totalDays += parseInt(my[1], 10) * 365;
            if (mm) totalDays += parseInt(mm[1], 10) * 30.4;
            if (mw) totalDays += parseInt(mw[1], 10) * 7;
            if (md) totalDays += parseInt(md[1], 10);
            if (totalDays <= 0) return 0;
            return Math.round((totalDays / 30.4) * 10) / 10;
        }

        var cachedOffers = [];
        var cachedTrials = [];
        var lastQueriedSkus = [];
        var isScanning = false;
        var bc = null;
        var bcConnected = false;
        var pendingReadyCallbacks = [];
        var uidSeq = Date.now() % 1000000;
        function nextClassName(prefix) {
            uidSeq++;
            return "com.frida.auto." + prefix + uidSeq;
        }

        function acknowledgeIfNeeded(pu, onDone) {
            try {
                Java.classFactory.loader = dexLoader;
                var state = pu.getPurchaseState();
                var acked = pu.isAcknowledged();
                var orderId = String(pu.getOrderId() || "pending");
                if (state === 1 && !acked) {
                    var AckParams = Java.use("com.android.billingclient.api.AcknowledgePurchaseParams");
                    var AckListener = Java.use("com.android.billingclient.api.AcknowledgePurchaseResponseListener");
                    var ackCb = Java.registerClass({
                        name: nextClassName("ACK"),
                        implements: [AckListener],
                        methods: {
                            onAcknowledgePurchaseResponse: function(ackBr) {
                                var ac = ackBr.getResponseCode();
                                emit("=== PURCHASE_ACKNOWLEDGED code=" + ac + " order=" + orderId + " ===");
                                if (onDone) onDone(ac === 0);
                            }
                        }
                    }).$new();
                    var ap = AckParams.newBuilder().setPurchaseToken(String(pu.getPurchaseToken())).build();
                    bc.acknowledgePurchase(ap, ackCb);
                } else {
                    if (onDone) onDone(false);
                }
            } catch (ae) {
                emit("WARN Acknowledge: " + ae);
                if (onDone) onDone(false);
            }
        }

        var purchaseListener = Java.registerClass({
            name: nextClassName("PL"),
            implements: [PurchasesUpdatedListener],
            methods: {
                onPurchasesUpdated: function(br, purchases) {
                    var code = br.getResponseCode();
                    if (code === 0 && purchases != null) {
                        Java.classFactory.loader = dexLoader;
                        var pl = Java.cast(purchases, List);
                        var hasPending = false;
                        var hasPurchased = false;
                        for (var i = 0; i < pl.size(); i++) {
                            var pu = Java.cast(pl.get(i), Purchase);
                            var pState = pu.getPurchaseState();
                            var pAck = pu.isAcknowledged();
                            var pOrder = String(pu.getOrderId() || "");
                            var pProds = String(pu.getProducts());
                            emit("PURCHASE_DETAIL|" + pOrder + "|" + pProds + "|state=" + pState + "|ack=" + pAck);
                            if (pState === 2) {
                                hasPending = true;
                            } else if (pState === 1) {
                                hasPurchased = true;
                                acknowledgeIfNeeded(pu, null);
                            }
                        }
                        if (hasPurchased) {
                            emit("=== TRIAL_ACTIVATED ===");
                        } else if (hasPending) {
                            emit("=== PURCHASE_PENDING ===");
                        } else {
                            emitErr("=== PURCHASE_FAILED code=-3 msg=No purchased state in callback ===");
                        }
                    } else if (code === 1) {
                        emit("=== USER_CANCELLED ===");
                    } else if (code === 7) {
                        emit("=== ITEM_ALREADY_OWNED ===");
                    } else {
                        emitErr("=== PURCHASE_FAILED code=" + code + " msg=" + br.getDebugMessage() + " ===");
                    }
                }
            }
        }).$new();

        var builder = BillingClient.newBuilder(context).setListener(purchaseListener);
        try {
            builder = builder.enablePendingPurchases();
        } catch (pe) {
            try {
                var PPP = Java.use("com.android.billingclient.api.PendingPurchasesParams");
                builder = builder.enablePendingPurchases(PPP.newBuilder().enableOneTimeProducts().build());
            } catch (pe2) {}
        }
        bc = builder.build();

        function queryAndAcknowledgePurchases() {
            try {
                Java.classFactory.loader = dexLoader;
                var QP = Java.use("com.android.billingclient.api.QueryPurchasesParams");
                var PRL = Java.use("com.android.billingclient.api.PurchasesResponseListener");
                var prl = Java.registerClass({
                    name: nextClassName("PRL"),
                    implements: [PRL],
                    methods: {
                        onQueryPurchasesResponse: function(br, purchases) {
                            Java.classFactory.loader = dexLoader;
                            var rc = br.getResponseCode();
                            if (rc !== 0 || purchases == null) {
                                emitErr("=== PURCHASES_QUERY_FAILED code=" + rc + " ===");
                                return;
                            }
                            var pl = Java.cast(purchases, List);
                            var total = pl.size();
                            emit("PURCHASES_COUNT " + total);
                            if (total === 0) {
                                emit("=== PURCHASES_SYNC_DONE count=0 acked=0 ===");
                                return;
                            }
                            var remaining = total;
                            var newlyAcked = 0;
                            for (var i = 0; i < total; i++) {
                                var pu = Java.cast(pl.get(i), Purchase);
                                var orderId = String(pu.getOrderId() || "N/A");
                                var prods = String(pu.getProducts());
                                var state = pu.getPurchaseState();
                                var acked = pu.isAcknowledged();
                                var autoRenew = pu.isAutoRenewing();
                                var tokHead = String(pu.getPurchaseToken()).substring(0, 20);
                                emit("PURCHASE_RECORD|" + orderId + "|" + prods + "|" + state + "|" + acked + "|" + autoRenew + "|" + tokHead);
                                acknowledgeIfNeeded(pu, function(didAck) {
                                    if (didAck) newlyAcked++;
                                    remaining--;
                                    if (remaining <= 0) {
                                        emit("=== PURCHASES_SYNC_DONE count=" + total + " acked=" + newlyAcked + " ===");
                                    }
                                });
                            }
                        }
                    }
                }).$new();
                var qp = QP.newBuilder().setProductType("subs").build();
                bc.queryPurchasesAsync(qp, prl);
            } catch (qe) {
                emitErr("=== PURCHASES_QUERY_FAILED err=" + qe + " ===");
            }
        }

        var __bootDone = false;
        var stateListener = Java.registerClass({
            name: nextClassName("SL"),
            implements: [BillingClientStateListener],
            methods: {
                onBillingSetupFinished: function(result) {
                    if (result.getResponseCode() !== 0) {
                        bcConnected = false;
                        pendingReadyCallbacks = [];
                        emitErr("=== CONNECT_FAILED code=" + result.getResponseCode() + " msg=" + result.getDebugMessage() + " ===");
                        return;
                    }
                    bcConnected = true;
                    emit("BillingClient connected");

                    Java.classFactory.loader = null;
                    var mainHandler = Handler.$new(Looper.getMainLooper());
                    Java.classFactory.loader = dexLoader;

                    var cbs = pendingReadyCallbacks.slice(0);
                    pendingReadyCallbacks = [];
                    var needInitial = !__bootDone;
                    __bootDone = true;

                    var Runnable = Java.use("java.lang.Runnable");
                    var initRunnable = Java.registerClass({
                        name: nextClassName("IR"),
                        implements: [Runnable],
                        methods: {
                            run: function() {
                                if (cbs.length > 0) {
                                    for (var ci = 0; ci < cbs.length; ci++) {
                                        try { cbs[ci](); } catch (cbe) {}
                                    }
                                } else if (needInitial) {
                                    if (MODE === "query_purchases") {
                                        queryAndAcknowledgePurchases();
                                    } else {
                                        doQuery();
                                    }
                                }
                            }
                        }
                    }).$new();
                    mainHandler.post(initRunnable);
                },
                onBillingServiceDisconnected: function() {
                    bcConnected = false;
                    emit("BillingClient disconnected");
                }
            }
        }).$new();

        function ensureBillingReady(cb) {
            var ready = bcConnected;
            try {
                Java.classFactory.loader = dexLoader;
                if (bc && !bc.isReady()) ready = false;
            } catch (re) {}
            if (ready) {
                cb();
                return;
            }
            emit("Reconnecting BillingClient before action...");
            pendingReadyCallbacks.push(cb);
            try {
                Java.classFactory.loader = dexLoader;
                bc.startConnection(stateListener);
            } catch (se) {
                pendingReadyCallbacks = [];
                emitErr("=== CONNECT_FAILED code=-3 msg=" + se + " ===");
            }
        }

        function buildScanWaves(queryList) {
            var unique = [];
            var seen = {};
            for (var i = 0; i < queryList.length; i++) {
                var s = queryList[i];
                if (s && !seen[s]) {
                    seen[s] = true;
                    unique.push(s);
                }
            }
            if (unique.length <= 2) {
                return [{ label: "定向目标 SKU 探测", skus: unique }];
            }

            var gFree = {
                "g1.2tb.ai.subs_variant": 1, "g1.play.2tb.ai": 1, "g1.2tb.subs_variant": 1
            };
            var gProPromo = {
                "g1.2tb.ai.12months_ip_90p": 1, "g1.2tb.ai.3months_ip_90p.acq": 1,
                "g1.2tb.ai.1month_ip_90p.acq": 1, "g1.2tb.ai.12months_ip_75p": 1,
                "g1.2tb.ai.3months_ip_75p.acq": 1, "g1.2tb.ai.12months_ip_50p": 1,
                "g1.2tb.ai.3months_ip_50p": 1, "g1.play.2tb.ai.student": 1,
                "g1.2tb.ai.annual": 1, "g1.2tb.ai": 1
            };
            var gUltra = {
                "g1.ai.ultra.1month_ip_90p.acq": 1, "g1.ai.ultra.3months_ip_80p.acq": 1,
                "g1.ai.ultra.3months_ip_80p": 1, "g1.ai.ultra.3months_ip_75p.acq": 1,
                "g1.ai.pro.3months_ip_50p": 1, "g1.ai.ultra.2months_ip_50p.acq": 1,
                "g1.play.ai.pro": 1, "g1.ai.pro": 1, "g1.play.20tb": 1, "g1.20tb": 1
            };
            var gBasic = {
                "g1.100gb.3months_ip_75p": 1, "g1.2tb.3months_ip_75p": 1,
                "g1.30gb": 1, "g1.100gb": 1, "g1.200gb": 1, "g1.2tb": 1
            };

            var wCustom = [], w1 = [], w2 = [], w3 = [], w4 = [];
            for (var j = 0; j < unique.length; j++) {
                var sku = unique[j];
                if (gFree[sku]) w1.push(sku);
                else if (gProPromo[sku]) w2.push(sku);
                else if (gUltra[sku]) w3.push(sku);
                else if (gBasic[sku]) w4.push(sku);
                else wCustom.push(sku);
            }

            var waves = [];
            if (wCustom.length > 0) waves.push({ label: "自定义扩展 SKU 探测组", skus: wCustom });
            if (w1.length > 0) waves.push({ label: "免费试用与24月叠加池 ($0 Trial)", skus: w1 });
            if (w2.length > 0) waves.push({ label: "AI Pro 5TB 1折~5折与学生年付组", skus: w2 });
            if (w3.length > 0) waves.push({ label: "AI Ultra 30TB/20TB 特惠与旗舰组", skus: w3 });
            if (w4.length > 0) waves.push({ label: "Google One 低价入门与基础容量组", skus: w4 });
            return waves;
        }

        function doQuery() {
            if (isScanning) {
                emit("WARN Scan already in progress, skipping duplicate trigger");
                return;
            }
            isScanning = true;
            Java.classFactory.loader = dexLoader;

            var rawList = PRODUCTS;
            if (MODE === "launch_sku" && TARGET_SKU !== "") {
                rawList = [TARGET_SKU];
            } else if (MODE === "launch_offer" && TARGET_PRODUCT !== "" && TARGET_PRODUCT !== "auto") {
                rawList = [TARGET_PRODUCT];
            }
            var waves = buildScanWaves(rawList);
            var flatList = [];
            for (var w = 0; w < waves.length; w++) {
                for (var s = 0; s < waves[w].skus.length; s++) flatList.push(waves[w].skus[s]);
            }
            lastQueriedSkus = flatList;
            var totalSkus = flatList.length;

            emit("SCAN_START|" + totalSkus + "|" + waves.length);

            var accOffers = [];
            var accTrials = [];
            var hitMap = {};
            var hitProductsCount = 0;
            var seqCounter = 0;

            function runWave(waveIdx) {
                if (waveIdx >= waves.length) {
                    isScanning = false;
                    finishScan(accOffers, accTrials, hitMap, hitProductsCount, totalSkus);
                    return;
                }

                var wave = waves[waveIdx];
                emit("WAVE_START|" + (waveIdx + 1) + "|" + waves.length + "|" + wave.label + "|" + wave.skus.length);

                Java.classFactory.loader = dexLoader;
                var prodList = ArrayList.$new();
                for (var i = 0; i < wave.skus.length; i++) {
                    prodList.add(QpdProduct.newBuilder()
                        .setProductId(wave.skus[i]).setProductType("subs").build());
                }
                var params = QueryProductDetailsParams.newBuilder().setProductList(prodList).build();

                var pdl = Java.registerClass({
                    name: nextClassName("PDL"),
                    implements: [ProductDetailsResponseListener],
                    methods: {
                        onProductDetailsResponse: function(br, pdList) {
                            Java.classFactory.loader = dexLoader;
                            if (br.getResponseCode() !== 0) {
                                isScanning = false;
                                emitErr("=== QUERY_FAILED code=" + br.getResponseCode() + " msg=" + br.getDebugMessage() + " ===");
                                return;
                            }

                            var byId = {};
                            if (pdList != null) {
                                var list = Java.cast(pdList, List);
                                for (var m = 0; m < list.size(); m++) {
                                    var pdItem = Java.cast(list.get(m), ProductDetails);
                                    byId[String(pdItem.getProductId())] = pdItem;
                                }
                            }

                            for (var q = 0; q < wave.skus.length; q++) {
                                seqCounter++;
                                var qSku = wave.skus[q];
                                var qName = PRODUCT_NAMES[qSku] || qSku;
                                var pd = byId[qSku];
                                if (!pd) {
                                    emit("SKU_MISS|" + seqCounter + "|" + totalSkus + "|" + qSku + "|" + qName);
                                    continue;
                                }
                                hitMap[qSku] = true;
                                hitProductsCount++;
                                parseSingleProduct(pd, seqCounter, totalSkus, accOffers, accTrials);
                            }

                            Java.classFactory.loader = null;
                            var nextH = Handler.$new(Looper.getMainLooper());
                            Java.classFactory.loader = dexLoader;
                            var NextWaveRunnable = Java.registerClass({
                                name: nextClassName("NW"),
                                implements: [Java.use("java.lang.Runnable")],
                                methods: { run: function() { runWave(waveIdx + 1); } }
                            }).$new();
                            nextH.post(NextWaveRunnable);
                        }
                    }
                }).$new();
                bc.queryProductDetailsAsync(params, pdl);
            }

            runWave(0);
        }

        function emitBrowseList(allOffers) {
            emit("BROWSE_BEGIN " + allOffers.length);
            for (var i = 0; i < allOffers.length; i++) {
                var e = allOffers[i];
                emit("OFFER_ITEM|" + e.index + "|" + e.product + "|" + e.productName
                    + "|" + e.offerId + "|" + e.price + "|" + e.period
                    + "|" + e.offerType + "|" + (e.trialPeriod || "")
                    + "|" + (e.renewPrice || "") + "|" + (e.introCycles || 0));
            }
            emit("=== BROWSE_COMPLETE ===");
        }

        function parseSingleProduct(pd, seqIdx, totalSkus, allOffers, trials) {
            Java.classFactory.loader = dexLoader;
            var pid = String(pd.getProductId());
            var pname = PRODUCT_NAMES[pid] || String(pd.getName() || pid);
            var title = String(pd.getTitle() || pname);

            var offers = pd.getSubscriptionOfferDetails();
            var oCount = (offers != null) ? Java.cast(offers, List).size() : 0;

            var briefTags = [];
            if (offers != null && oCount > 0) {
                var preOl = Java.cast(offers, List);
                var preSize = preOl.size();
                for (var bj = 0; bj < preSize; bj++) {
                    var bo = Java.cast(preOl.get(bj), SubscriptionOfferDetails);
                    var boid = bo.getOfferId();
                    var bphList = Java.cast(bo.getPricingPhases().getPricingPhaseList(), List);
                    if (bphList.size() > 0) {
                        var bph0 = Java.cast(bphList.get(0), PricingPhase);
                        var bm0 = parseInt(String(bph0.getPriceAmountMicros()), 10) || 0;
                        if (bm0 === 0 && bphList.size() > 1) {
                            briefTags.push("★0元:" + (boid != null ? String(boid) : String(bph0.getBillingPeriod())));
                        } else if (bphList.size() > 1 && boid != null) {
                            briefTags.push("⚡" + String(bph0.getFormattedPrice()) + "(" + String(boid) + ")");
                        } else if (briefTags.length === 0) {
                            briefTags.push(String(bph0.getFormattedPrice()));
                        }
                    }
                }
            }
            var briefSummary = briefTags.slice(0, 3).join(", ") + (briefTags.length > 3 ? " ..." : "");

            emit("SCAN_HIT|" + seqIdx + "|" + totalSkus + "|" + pid + "|" + pname + "|" + oCount + "|" + briefSummary);
            emit("PRODUCT " + pid + " — " + title);

            if (offers == null || oCount === 0) {
                emit("  (no offers)");
                return;
            }
            var ol = Java.cast(offers, List);

            for (var j = 0; j < ol.size(); j++) {
                var o = Java.cast(ol.get(j), SubscriptionOfferDetails);
                var oid = o.getOfferId();
                var phases = Java.cast(o.getPricingPhases().getPricingPhaseList(), List);

                var tags = Java.cast(o.getOfferTags(), List);
                var tagStr = "";
                for (var t = 0; t < tags.size(); t++) tagStr += (t > 0 ? "," : "") + tags.get(t);

                var hasTrial = false;
                var isPromo = false;
                var trialPeriod = "";
                var firstPrice = "";
                var firstMicros = 0;
                var firstPeriod = "";
                var firstCycles = 0;
                var renewPrice = "";
                var renewMicros = 0;
                var renewPeriod = "";

                for (var k = 0; k < phases.size(); k++) {
                    var ph = Java.cast(phases.get(k), PricingPhase);
                    var microsStr = String(ph.getPriceAmountMicros());
                    var microsNum = parseInt(microsStr, 10) || 0;
                    var free = (microsStr === "0" || microsNum === 0);
                    var period = String(ph.getBillingPeriod());
                    var cycles = ph.getBillingCycleCount();

                    emit("  [" + j + "] Phase" + k + ": " + ph.getFormattedPrice()
                        + " × " + period + " (" + cycles + " cycles)"
                        + (free ? " ★FREE★" : "")
                        + (k === 0 && oid != null ? " id=" + oid : "")
                        + (tagStr && k === 0 ? " tags=[" + tagStr + "]" : ""));

                    if (k === 0) {
                        firstPrice = String(ph.getFormattedPrice());
                        firstMicros = microsNum;
                        firstPeriod = period;
                        firstCycles = cycles;
                        if (free && phases.size() > 1) {
                            hasTrial = true;
                            trialPeriod = period;
                        }
                    } else {
                        renewPrice = String(ph.getFormattedPrice());
                        renewMicros = microsNum;
                        renewPeriod = period;
                    }
                }

                if (!hasTrial && phases.size() > 1 && firstMicros > 0 && (renewMicros === 0 || firstMicros < renewMicros)) {
                    isPromo = true;
                }

                var displayPrice = hasTrial ? renewPrice : firstPrice;
                var displayPeriod = hasTrial ? (renewPeriod || firstPeriod) : firstPeriod;
                var offerType = hasTrial ? "TRIAL" : (isPromo ? "PROMO" : "BASE");

                var entry = {
                    index: allOffers.length,
                    product: pid,
                    productName: pname,
                    offerId: oid != null ? String(oid) : "base",
                    price: displayPrice || firstPrice,
                    firstMicros: firstMicros,
                    period: displayPeriod,
                    periodLabel: DUR_LABEL[hasTrial ? trialPeriod : displayPeriod] || (hasTrial ? trialPeriod : displayPeriod),
                    months: parseIsoDurationMonths(hasTrial ? trialPeriod : displayPeriod),
                    isTrial: hasTrial,
                    isPromo: isPromo,
                    offerType: offerType,
                    trialPeriod: trialPeriod,
                    renewPrice: renewPrice,
                    introCycles: firstCycles,
                    pd: pd,
                    offer: o
                };
                allOffers.push(entry);
                if (hasTrial) trials.push(entry);
            }
        }

        function finishScan(allOffers, trials, hitMap, hitProductsCount, totalSkus) {
            emit("Products found: " + hitProductsCount);
            var missed = [];
            for (var mIdx = 0; mIdx < lastQueriedSkus.length; mIdx++) {
                var qSku = lastQueriedSkus[mIdx];
                if (!hitMap[qSku]) missed.push(qSku);
            }
            if (missed.length > 0) {
                emit("SCAN_MISS|" + missed.length + "|" + missed.join(","));
            }
            emit("SCAN_SUMMARY|queried=" + totalSkus + "|products=" + hitProductsCount + "|offers=" + allOffers.length + "|trials=" + trials.length);

            cachedOffers = allOffers;
            cachedTrials = trials;

            if (MODE === "browse") {
                emitBrowseList(allOffers);
                return;
            }

            if (MODE === "interactive") {
                emitBrowseList(allOffers);
                emit("=== INTERACTIVE_READY cmd=" + cmdFilePath + " ===");
                startCommandPoller();
                return;
            }

            if (MODE === "launch_index" && SELECTED_OFFER_INDEX >= 0) {
                if (SELECTED_OFFER_INDEX >= allOffers.length) {
                    emitErr("=== SELECT_FAILED index=" + SELECTED_OFFER_INDEX + " out of range ===");
                    return;
                }
                var selIdx = allOffers[SELECTED_OFFER_INDEX];
                emit("SELECTED " + selIdx.product + " / " + selIdx.offerId + " " + selIdx.price + " (" + selIdx.offerType + ")");
                dispatchLaunch(selIdx, STACK_ENABLED, OLD_PURCHASE_TOKEN, STACK_PRORATION_MODE);
                return;
            }

            if (MODE === "launch_offer") {
                var foundOffer = findOfferByProductAndId(allOffers, TARGET_PRODUCT, TARGET_OFFER_ID);
                if (!foundOffer) {
                    emitErr("=== SELECT_FAILED product=" + TARGET_PRODUCT + " offer=" + TARGET_OFFER_ID + " ===");
                    return;
                }
                emit("SELECTED " + foundOffer.product + " / " + foundOffer.offerId + " " + foundOffer.price + " (" + foundOffer.offerType + ")");
                dispatchLaunch(foundOffer, STACK_ENABLED, OLD_PURCHASE_TOKEN, STACK_PRORATION_MODE);
                return;
            }

            if (MODE === "launch_sku" && TARGET_SKU !== "") {
                var skuChosen = selectBestForSku(allOffers, TARGET_SKU, TARGET_OFFER_ID);
                if (skuChosen === "__PROMO_INELIGIBLE__") {
                    emitErr("=== PROMO_INELIGIBLE sku=" + TARGET_SKU + " ===");
                    return;
                }
                if (!skuChosen) {
                    emitErr("=== SKU_NOT_FOUND sku=" + TARGET_SKU + " offer=" + TARGET_OFFER_ID + " ===");
                    return;
                }
                emit("SKU_SELECTED " + skuChosen.product + " / " + skuChosen.offerId + " " + skuChosen.price + " (" + skuChosen.offerType + ")");
                dispatchLaunch(skuChosen, STACK_ENABLED, OLD_PURCHASE_TOKEN, STACK_PRORATION_MODE);
                return;
            }

            emit("TRIALS_FOUND " + trials.length);
            for (var tIdx = 0; tIdx < trials.length; tIdx++) {
                var tr = trials[tIdx];
                emit("  TRIAL " + tr.product + " / " + tr.offerId + " — " + tr.months + " months free");
            }
            if (trials.length === 0 || MODE === "list") {
                emit("=== " + (trials.length === 0 ? "NO_TRIALS" : "LIST_COMPLETE") + " ===");
                return;
            }

            var candidates = [];
            for (var cIdx = 0; cIdx < trials.length; cIdx++) {
                if (TARGET_PRODUCT === "auto" || trials[cIdx].product === TARGET_PRODUCT) {
                    candidates.push(trials[cIdx]);
                }
            }
            if (candidates.length === 0) {
                emitErr("No trials for target=" + TARGET_PRODUCT);
                emit("=== SELECT_FAILED ===");
                return;
            }

            var selected = null;
            if (TARGET_OFFER_ID !== "") {
                for (var oIdx = 0; oIdx < candidates.length; oIdx++) {
                    if (candidates[oIdx].offerId === TARGET_OFFER_ID) {
                        selected = candidates[oIdx];
                        break;
                    }
                }
            }
            if (!selected) {
                if (PREFER_DURATION === "longest") {
                    selected = candidates[0];
                    for (var m2 = 1; m2 < candidates.length; m2++) {
                        if (candidates[m2].months > selected.months) selected = candidates[m2];
                    }
                } else {
                    var wantPeriod = ALIAS[PREFER_DURATION] || PREFER_DURATION;
                    for (var dIdx = 0; dIdx < candidates.length; dIdx++) {
                        if (candidates[dIdx].trialPeriod === wantPeriod ||
                            (wantPeriod === "P1Y" && candidates[dIdx].trialPeriod === "P12M")) {
                            selected = candidates[dIdx];
                            break;
                        }
                    }
                    if (!selected) {
                        selected = candidates[0];
                        for (var fIdx = 1; fIdx < candidates.length; fIdx++) {
                            if (candidates[fIdx].months > selected.months) selected = candidates[fIdx];
                        }
                    }
                }
            }

            emit("SELECTED " + selected.product + " / " + selected.offerId + " (" + selected.months + " months)");
            dispatchLaunch(selected, STACK_ENABLED, OLD_PURCHASE_TOKEN, STACK_PRORATION_MODE);
        }

        function findOfferByProductAndId(allOffers, prod, oid) {
            for (var i = 0; i < allOffers.length; i++) {
                if (allOffers[i].product === prod && (!oid || oid === "" || allOffers[i].offerId === oid)) {
                    return allOffers[i];
                }
            }
            if (oid && oid.indexOf("eft-3mo") === 0) {
                for (var j = 0; j < allOffers.length; j++) {
                    if (allOffers[j].product === prod && allOffers[j].offerId.indexOf("eft-3mo") === 0) {
                        return allOffers[j];
                    }
                }
            }
            return null;
        }

        function selectBestForSku(allOffers, sku, wantOfferId) {
            var promoOnly = (wantOfferId === "__PROMO__");
            var skuMatches = [];
            for (var i = 0; i < allOffers.length; i++) {
                if (allOffers[i].product === sku) {
                    if (!promoOnly && wantOfferId && wantOfferId !== "" && allOffers[i].offerId === wantOfferId) {
                        return allOffers[i];
                    }
                    skuMatches.push(allOffers[i]);
                }
            }
            if (!promoOnly && wantOfferId && wantOfferId.indexOf("eft-3mo") === 0) {
                for (var m = 0; m < skuMatches.length; m++) {
                    if (skuMatches[m].offerId.indexOf("eft-3mo") === 0) return skuMatches[m];
                }
            }
            if (!promoOnly && wantOfferId && wantOfferId !== "") return null;
            if (skuMatches.length === 0) return null;

            if (promoOnly) {
                var promoList = [];
                for (var p = 0; p < skuMatches.length; p++) {
                    if (skuMatches[p].offerType === "PROMO" || skuMatches[p].offerType === "TRIAL") {
                        promoList.push(skuMatches[p]);
                    }
                }
                if (promoList.length === 0) return "__PROMO_INELIGIBLE__";
                skuMatches = promoList;
            }

            var best = skuMatches[0];
            for (var k = 1; k < skuMatches.length; k++) {
                if (skuMatches[k].firstMicros < best.firstMicros) {
                    best = skuMatches[k];
                } else if (skuMatches[k].firstMicros === best.firstMicros && skuMatches[k].months > best.months) {
                    best = skuMatches[k];
                }
            }
            return best;
        }

        function readAndClearCmdFile(f) {
            if (!f) return null;
            try {
                if (!f.exists() || f.length() <= 0) return null;
                var line = null;
                var fis = FileInputStream.$new(f);
                var br = BufferedReader.$new(InputStreamReader.$new(fis, "UTF-8"));
                try {
                    line = br.readLine();
                } finally {
                    try { br.close(); } catch (c1) {}
                    try { fis.close(); } catch (c2) {}
                }
                var fos = FileOutputStream.$new(f, false);
                try { fos.close(); } catch (c3) {}
                return line ? String(line).trim() : null;
            } catch (re) {
                return null;
            }
        }

        function startCommandPoller() {
            if (__cmdPollTimer !== null) return;
            __cmdPollTimer = setInterval(function() {
                Java.perform(function() {
                    try {
                        Java.classFactory.loader = null;
                        var cmdLine = readAndClearCmdFile(extCmdFile);
                        if (!cmdLine) cmdLine = readAndClearCmdFile(cmdFile);
                        if (!cmdLine || cmdLine === "") return;

                        emit("CMD_RECV " + cmdLine);
                        var parts = cmdLine.split("|");
                        var op = parts[0];

                        if (op === "PING") {
                            emit("=== PONG ===");
                        } else if (op === "REFRESH") {
                            ensureBillingReady(function() { doQuery(); });
                        } else if (op === "QUERY_PURCHASES") {
                            ensureBillingReady(function() { queryAndAcknowledgePurchases(); });
                        } else if (op === "LAUNCH_INDEX") {
                            var idx = parseInt(parts[1], 10);
                            if (isNaN(idx) || idx < 0 || idx >= cachedOffers.length) {
                                emitErr("=== SELECT_FAILED index=" + parts[1] + " ===");
                            } else {
                                var sel = cachedOffers[idx];
                                emit("SELECTED " + sel.product + " / " + sel.offerId + " " + sel.price + " (" + sel.offerType + ")");
                                ensureBillingReady(function() { dispatchLaunch(sel, false, "", 5); });
                            }
                        } else if (op === "LAUNCH_OFFER") {
                            var prod = parts[1] || "";
                            var oid = parts[2] || "";
                            var found = findOfferByProductAndId(cachedOffers, prod, oid);
                            if (!found) {
                                emitErr("=== SELECT_FAILED product=" + prod + " offer=" + oid + " ===");
                            } else {
                                emit("SELECTED " + found.product + " / " + found.offerId + " " + found.price + " (" + found.offerType + ")");
                                ensureBillingReady(function() { dispatchLaunch(found, false, "", 5); });
                            }
                        } else if (op === "LAUNCH_SKU") {
                            var sku = parts[1] || "";
                            var wOid = parts[2] || "";
                            var chosen = selectBestForSku(cachedOffers, sku, wOid);
                            if (chosen === "__PROMO_INELIGIBLE__") {
                                emitErr("=== PROMO_INELIGIBLE sku=" + sku + " ===");
                            } else if (!chosen) {
                                emitErr("=== SKU_NOT_FOUND sku=" + sku + " offer=" + wOid + " ===");
                            } else {
                                emit("SKU_SELECTED " + chosen.product + " / " + chosen.offerId + " " + chosen.price + " (" + chosen.offerType + ")");
                                ensureBillingReady(function() { dispatchLaunch(chosen, false, "", 5); });
                            }
                        } else if (op === "STACK_OFFER") {
                            var sProd = parts[1] || "";
                            var sOid = parts[2] || "";
                            var sOldTok = parts[3] || "";
                            var sMode = parseInt(parts[4] || "5", 10) || 5;
                            var sChosen = selectBestForSku(cachedOffers, sProd, sOid);
                            if (sChosen === "__PROMO_INELIGIBLE__") {
                                emitErr("=== PROMO_INELIGIBLE sku=" + sProd + " ===");
                            } else if (!sChosen) {
                                emitErr("=== SKU_NOT_FOUND sku=" + sProd + " offer=" + sOid + " ===");
                            } else {
                                emit("STACK_SELECTED " + sChosen.product + " / " + sChosen.offerId + " mode=" + sMode);
                                ensureBillingReady(function() { dispatchLaunch(sChosen, true, sOldTok, sMode); });
                            }
                        } else if (op === "QUIT") {
                            try { bc.endConnection(); } catch (ee) {}
                            emit("=== SESSION_CLOSED ===");
                            clearInterval(__cmdPollTimer);
                            __cmdPollTimer = null;
                        }
                    } catch (pe) {
                        emitErr("CMD_ERR " + pe);
                    }
                });
            }, 150);
        }

        function findActiveActivity() {
            var act = null;
            try {
                Java.classFactory.loader = null;
                var athread = AT.currentActivityThread();
                var acts = athread.mActivities.value;
                var ait = acts.values().iterator();
                var fallbackAct = null;
                while (ait.hasNext()) {
                    var rec = ait.next();
                    var af = rec.getClass().getDeclaredField("activity");
                    af.setAccessible(true);
                    var aObj = af.get(rec);
                    if (!aObj) continue;
                    var a = Java.cast(aObj, Activity);
                    if (!a.isFinishing() && !a.isDestroyed()) {
                        try {
                            var pf = rec.getClass().getDeclaredField("paused");
                            pf.setAccessible(true);
                            if (!pf.getBoolean(rec)) {
                                act = a;
                                break;
                            }
                        } catch (pe) {}
                        if (!fallbackAct) fallbackAct = a;
                    }
                }
                if (!act) act = fallbackAct;
            } catch (e) {}
            if (!act) {
                try {
                    Java.classFactory.loader = null;
                    Java.choose("android.app.Activity", {
                        onMatch: function(a) {
                            try {
                                if (!act && !a.isFinishing() && !a.isDestroyed()) act = a;
                            } catch (ie) {}
                        },
                        onComplete: function() {}
                    });
                } catch (ce) {}
            }
            Java.classFactory.loader = dexLoader;
            return act;
        }

        function dispatchLaunch(selected, useStack, providedOldToken, prorationMode) {
            if (useStack && (!providedOldToken || providedOldToken === "")) {
                emit("Querying active purchaseToken for stacking...");
                try {
                    Java.classFactory.loader = dexLoader;
                    var QP = Java.use("com.android.billingclient.api.QueryPurchasesParams");
                    var PRL = Java.use("com.android.billingclient.api.PurchasesResponseListener");
                    var stackPrl = Java.registerClass({
                        name: nextClassName("SPRL"),
                        implements: [PRL],
                        methods: {
                            onQueryPurchasesResponse: function(br, purchases) {
                                Java.classFactory.loader = dexLoader;
                                var oldTok = "";
                                if (br.getResponseCode() === 0 && purchases != null) {
                                    var pl = Java.cast(purchases, List);
                                    var pickedPu = null;
                                    for (var pi = 0; pi < pl.size(); pi++) {
                                        var candPu = Java.cast(pl.get(pi), Purchase);
                                        var cState = candPu.getPurchaseState();
                                        var cProds = String(candPu.getProducts());
                                        if (cState === 1 && cProds.indexOf("g1.") >= 0) {
                                            if (!pickedPu || candPu.isAutoRenewing()) {
                                                pickedPu = candPu;
                                                if (candPu.isAutoRenewing()) break;
                                            }
                                        }
                                    }
                                    if (!pickedPu && pl.size() > 0) {
                                        pickedPu = Java.cast(pl.get(0), Purchase);
                                    }
                                    if (pickedPu) {
                                        oldTok = String(pickedPu.getPurchaseToken());
                                        if (!pickedPu.isAutoRenewing()) {
                                            emit("WARN_STACK_CANCELLED autoRenewing=false");
                                        }
                                        emit("STACK_TOKEN_FOUND " + oldTok.substring(0, 18) + "... autoRenew=" + pickedPu.isAutoRenewing());
                                    }
                                }
                                if (!oldTok) {
                                    emitErr("=== STACK_NO_ACTIVE_SUB ===");
                                    return;
                                }
                                launchBillingForOffer(selected, oldTok, prorationMode);
                            }
                        }
                    }).$new();
                    bc.queryPurchasesAsync(QP.newBuilder().setProductType("subs").build(), stackPrl);
                    return;
                } catch (se) {
                    emitErr("=== STACK_QUERY_ERROR " + se + " ===");
                    return;
                }
            }
            launchBillingForOffer(selected, useStack ? providedOldToken : "", prorationMode);
        }

        function launchBillingForOffer(selected, oldToken, prorationMode, actAttempt) {
            var tryNum = actAttempt || 0;
            var act = findActiveActivity();
            if (!act) {
                if (tryNum < 12) {
                    setTimeout(function() {
                        Java.perform(function() {
                            launchBillingForOffer(selected, oldToken, prorationMode, tryNum + 1);
                        });
                    }, 200);
                    return;
                }
                emitErr("=== NO_ACTIVITY ===");
                return;
            }

            var focused = false;
            try { focused = act.hasWindowFocus(); } catch (fe) {}
            var delayMs = focused ? 150 : 600;
            emit("Launching billing flow (focused=" + focused + ", delay=" + delayMs + "ms)...");

            var finalPd = selected.pd;
            var finalToken = String(selected.offer.getOfferToken());
            var finalOldToken = oldToken ? String(oldToken) : "";
            var finalMode = prorationMode || 5;

            Java.classFactory.loader = null;
            var launchHandler = Handler.$new(Looper.getMainLooper());
            Java.classFactory.loader = dexLoader;

            var LaunchRunnable = Java.registerClass({
                name: nextClassName("LR"),
                implements: [Java.use("java.lang.Runnable")],
                methods: {
                    run: function() {
                        try {
                            var uiAct = findActiveActivity() || act;
                            Java.classFactory.loader = dexLoader;

                            var pdp = BfpProductDetailsParams.newBuilder()
                                .setProductDetails(finalPd)
                                .setOfferToken(finalToken)
                                .build();
                            var pdpList = ArrayList.$new();
                            pdpList.add(pdp);

                            var flowBuilder = BillingFlowParams.newBuilder()
                                .setProductDetailsParamsList(pdpList);

                            if (finalOldToken !== "") {
                                var SUP = Java.use("com.android.billingclient.api.BillingFlowParams$SubscriptionUpdateParams");
                                var sb = SUP.newBuilder().setOldPurchaseToken(finalOldToken);
                                var modeApplied = "none";
                                try {
                                    sb = sb.setSubscriptionReplacementMode(finalMode);
                                    modeApplied = "setSubscriptionReplacementMode(" + finalMode + ")";
                                } catch (m1) {
                                    try {
                                        sb = sb.setReplaceProrationMode(finalMode);
                                        modeApplied = "setReplaceProrationMode(" + finalMode + ")";
                                    } catch (m2) {
                                        try {
                                            sb = sb.setReplaceSkusProrationMode(finalMode);
                                            modeApplied = "setReplaceSkusProrationMode(" + finalMode + ")";
                                        } catch (m3) {}
                                    }
                                }
                                emit("STACK_APPLIED method=" + modeApplied + " token=" + finalOldToken.substring(0, 16) + "...");
                                flowBuilder = flowBuilder.setSubscriptionUpdateParams(sb.build());
                            }

                            var r = bc.launchBillingFlow(Java.cast(uiAct, Activity), flowBuilder.build());
                            emit("BILLING_FLOW_LAUNCHED code=" + r.getResponseCode() + " msg=" + r.getDebugMessage());
                        } catch (e) {
                            emitErr("=== LAUNCH_ERROR " + e + " ===");
                        }
                    }
                }
            }).$new();
            launchHandler.postDelayed(LaunchRunnable, delayMs);
        }

        bc.startConnection(stateListener);
    });
}

bootAutoTrial();
__keepAliveTimer = setInterval(function() {}, 1000);
