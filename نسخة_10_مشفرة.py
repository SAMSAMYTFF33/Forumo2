import time
import requests
import random
from bs4 import BeautifulSoup
import threading
import re
import os
import telebot
from telebot import types
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
import concurrent.futures
import uuid

# =============================== ===========
# الإعدادات الأساسية
# ==========================================
# ==========================================
# 🔐 نظام فك تشفير البيانات الحساسة
# ==========================================
from cryptography.fernet import Fernet

_FERNET_KEY = b'9_RHpGIWsbz-1XWWPx96nbtbmS49j9-i7Pn-lgnosy4='
_f = Fernet(_FERNET_KEY)

def _dec(token: str) -> str:
    return _f.decrypt(token.encode()).decode()

_ENC_TELEGRAM_TOKEN = 'gAAAAABqMXpO40nxYr-pqSh1LgO6Zx143gYTR_0haNJ3gneuAm1K8gcSODVr1Q5KbMmqAvmxvLAeuPEE5VVJUcp7NERUyE9zwF5-A0TvNb1jZTnUPeSrOfmGFkjNKEuK1ZTTqdQFVPeb'
_ENC_SUPABASE_URL   = 'gAAAAABqMXpO07rGV7R_AYSABuUyqH0kgpACtN7b4DaTs-xeotLpM0mm3tmtfJAAj6Y4F_8fjwwW9zQelEz7nSDquSNH8Wjrd12Bg_vPsaa5_WAU0aCQyM3LIxTHfuMkXs3qfFABNvs6'
_ENC_SUPABASE_KEY   = 'gAAAAABqMXpOd6Jg-zBwhc-uWcN7oUNHUoJ8uPfvkZ7aOHE1jYMx8sRczo9XfK-kuLVomt8Y63ZcUUOcTSyqomAdAJbjrMikSwShXitZ0xLcy9t4wZF3n4FPrEjp0wiFyjCxPkXqdsgo'
_ENC_PROXY_USER     = 'gAAAAABqMXpOdTNrhgABWIWeJdJxiV_TtaiOZG5rH8C3lmbB00QgdrfWKEgk6ctAwSrVgFy8SvJgg1e2v5UlWxHWd8ELJeBfpw=='
_ENC_PROXY_PASS     = 'gAAAAABqMXpOvH8E0UFdNXy70-Xx0avU0iODBULKUGazkeOWgG1bZB_l6Pm2pSRWuZG9eHv4FX-yyMuVQj9i4iy2FssBnMNT9A=='

TELEGRAM_TOKEN = _dec(_ENC_TELEGRAM_TOKEN)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==========================================
# 🔔 إعدادات التنبيهات الخاصة
# ==========================================
# chat_id الخاص الذي يستقبل تنبيهات CAPTCHA
# غيّره إلى chat_id المطلوب
CAPTCHA_ALERT_CHAT_ID = 8486184645  # ← ضع هنا chat_id الخاص بك

BASE_URL = "https://forumok.com"
LOGIN_URL = "https://forumok.com/login"
TARGET_URL = "https://forumok.com/orders-search/socio"
STATS_URL = "https://forumok.com/publisher-requests/socio/confirmed"
CONFIRMED_URL = "https://forumok.com/publisher-requests/socio/confirmed"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL
}

# ══ مساعد: retry تلقائي لجميع طلبات الشبكة ══
def _safe_get(url, session=None, retries=3, **kwargs):
    req = session or requests
    kwargs.setdefault("timeout", 15)
    for i in range(retries):
        try:
            return req.get(url, **kwargs)
        except requests.exceptions.RequestException:
            if i == retries - 1: raise
            time.sleep(2 * (i + 1))

def _safe_post(url, session=None, retries=3, **kwargs):
    req = session or requests
    kwargs.setdefault("timeout", 15)
    for i in range(retries):
        try:
            return req.post(url, **kwargs)
        except requests.exceptions.RequestException:
            if i == retries - 1: raise
            time.sleep(2 * (i + 1))

# ==========================================
# إعدادات البروكسيات الثابتة للحسابين المستثنيين
# ==========================================
EXEMPT_ACCOUNTS = ["france260026@gmail.com", "rossxpro26@gmail.com"]

ACCOUNT_PROXIES = {
    "france260026@gmail.com": [
        "38.154.203.95:5863", "198.105.121.200:6462", "64.137.96.74:6641",
        "209.127.138.10:5784", "38.154.185.97:6370"
    ],
    "rossxpro26@gmail.com": [
        "84.247.60.125:6095", "142.111.67.146:5611", "191.96.254.138:6185",
        "31.58.9.4:6077", "64.137.10.153:5803"
    ]
}
PROXY_USER = _dec(_ENC_PROXY_USER)
PROXY_PASS = _dec(_ENC_PROXY_PASS)

# ==========================================
# 🔐 روابط ومفاتيح مشروع Supabase
# ==========================================
SUPABASE_URL = _dec(_ENC_SUPABASE_URL)
SUPABASE_KEY = _dec(_ENC_SUPABASE_KEY)

DB_API_URL = f"{SUPABASE_URL}/rest/v1/users_accounts"
DB_AUTO_TASKS_URL = f"{SUPABASE_URL}/rest/v1/auto_tasks"
DB_SETTINGS_URL = f"{SUPABASE_URL}/rest/v1/user_settings"
DB_PROXY_URL = f"{SUPABASE_URL}/rest/v1/proxy_manager"
DB_MULTI_ACCOUNTS_URL = f"{SUPABASE_URL}/rest/v1/multi_accounts"  # جدول الحسابات المتعددة السحابي

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

# ==========================================
# 🌐 نظام إدارة البروكسيات الذكي المتقدم
# ==========================================
PROXY_SOURCE_URL = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text"
PROXIES_PER_ACCOUNT = 20
PROXY_REFRESH_INTERVAL = 30 * 60  # 30 دقيقة

# ── مخزن البروكسيات المخصصة لكل حساب ──
# { email: { "proxies": [...], "current_index": 0, "last_updated": ts } }
dynamic_proxy_store = {}
proxy_store_lock = threading.Lock()
last_proxy_refresh_time = 0

# ── المخزن الاحتياطي الذكي ──
# يحتفظ دائماً بـ (عدد_حسابات_النشطة + 1) × 20 بروكسي جاهزة للتخصيص الفوري
# { "proxies": [...مرتبة حسب latency...], "last_filled": timestamp }
proxy_reserve_pool = {"proxies": [], "last_filled": 0}
reserve_pool_lock = threading.Lock()
_reserve_fill_running = False  # يمنع تشغيل أكثر من عملية تعبئة واحدة في نفس الوقت

# ══ Semaphore: يمنع تشغيل refresh + reserve بالتوازي ══
# قيمة 1 = عملية واحدة فقط تجلب وتختبر البروكسيات في نفس الوقت
_proxy_fetch_semaphore = threading.Semaphore(1)

# ══ Queue مركزي لحفظ البيانات في DB بدل خيط لكل حفظ ══
import queue as _queue_module
_db_save_queue = _queue_module.Queue()

def _db_save_worker():
    """خيط واحد دائم يعالج كل طلبات الحفظ في DB"""
    while True:
        try:
            fn, args = _db_save_queue.get(timeout=5)
            try:
                fn(*args)
            except Exception as e:
                print(f"[DB-QUEUE] خطأ في الحفظ: {e}")
            finally:
                _db_save_queue.task_done()
        except _queue_module.Empty:
            pass

# تشغيل خيط DB المركزي (يُشغَّل بعد تعريف الدوال اللازمة عند الإطلاق)
def enqueue_db_save(fn, *args):
    """إضافة عملية حفظ للقائمة بدل فتح خيط جديد"""
    _db_save_queue.put((fn, args))

def _get_active_dynamic_accounts_count():
    """عدد الحسابات الديناميكية النشطة (غير المستثناة)"""
    with proxy_store_lock:
        return len([e for e in dynamic_proxy_store if e not in EXEMPT_ACCOUNTS])

def _needed_reserve_size():
    """حجم الاحتياطي المطلوب = (حسابات + 1) × 20 — دائماً يكفي لحساب قادم جديد"""
    active = _get_active_dynamic_accounts_count()
    return (active + 1) * PROXIES_PER_ACCOUNT

# ==========================================
# دوال جلب ومعالجة البروكسيات الديناميكية
# ==========================================

def fetch_raw_proxies():
    """جلب قائمة البروكسيات الخام من المصدر"""
    try:
        r = requests.get(PROXY_SOURCE_URL, timeout=20)
        if r.status_code == 200:
            lines = r.text.strip().split("\n")
            proxies = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # تنسيق: protocol://ip:port أو ip:port
                if "://" in line:
                    proxies.append(line)
                else:
                    proxies.append(f"http://{line}")
            print(f"[PROXY] تم جلب {len(proxies)} بروكسي خام")
            return proxies
    except Exception as e:
        print(f"[PROXY] خطأ في جلب البروكسيات: {e}")
    return []

def test_single_proxy(proxy_url):
    """اختبار بروكسي واحد وقياس سرعة الاستجابة مع جلب الدولة والمدينة"""
    try:
        start = time.time()
        r = requests.get(
            "http://ip-api.com/json/?fields=status,country,countryCode,city,regionName,isp,query",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=6,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        latency = round(time.time() - start, 3)
        if r.status_code == 200:
            try:
                data = r.json()
                # ip-api يُرجع IP الحقيقي للبروكسي تلقائياً (query = الـ IP الخارجي)
                ip = data.get("query", "").strip()
                if data.get("status") == "success":
                    country = data.get("country", "Unknown")
                    country_code = data.get("countryCode", "??")
                    city = data.get("city", "")
                    region = data.get("regionName", "")
                    isp = data.get("isp", "")
                else:
                    country, country_code, city, region, isp = "Unknown", "??", "", "", ""
            except Exception:
                ip, country, country_code, city, region, isp = "", "Unknown", "??", "", "", ""
            return {
                "address": proxy_url,
                "latency": latency,
                "ip": ip,
                "country": country,
                "country_code": country_code,
                "city": city,
                "region": region,
                "isp": isp,
                "alive": True
            }
    except Exception:
        pass
    return {"address": proxy_url, "latency": 999.0, "ip": "", "country": "Unknown", "country_code": "??", "city": "", "region": "", "isp": "", "alive": False}

def test_proxies_batch(proxy_list, max_workers=15):
    """اختبار مجموعة بروكسيات بالتوازي"""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(test_single_proxy, p): p for p in proxy_list}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result["alive"]:
                    results.append(result)
            except Exception:
                pass
    # ترتيب حسب السرعة
    results.sort(key=lambda x: x["latency"])
    return results

# ==========================================
# 🧠 نظام المخزن الاحتياطي الذكي
# ==========================================

def _fill_reserve_pool_worker():
    """
    ملء المخزن الاحتياطي في الخلفية.
    يجلب ويختبر بروكسيات كافية ليحتفظ بـ (حسابات+1)×20 جاهزة.
    يُشغَّل تلقائياً عند:
      - بدء التشغيل
      - تسجيل دخول ناجح (لتعويض ما استُهلك)
      - انخفاض الاحتياطي تحت الحد
    """
    global _reserve_fill_running
    # منع التزامن مع refresh_dynamic_proxies
    if not _proxy_fetch_semaphore.acquire(blocking=False):
        print("[RESERVE] عملية جلب أخرى جارية، تم تخطي هذه الدورة")
        return
    with reserve_pool_lock:
        if _reserve_fill_running:
            _proxy_fetch_semaphore.release()
            return
        _reserve_fill_running = True

    try:
        needed = _needed_reserve_size()
        with reserve_pool_lock:
            current_alive = [p for p in proxy_reserve_pool["proxies"] if p.get("status", "active") != "dead"]

        if len(current_alive) >= needed:
            print(f"[RESERVE] الاحتياطي كافٍ: {len(current_alive)}/{needed}")
            with reserve_pool_lock:
                proxy_reserve_pool["proxies"] = current_alive
            return

        deficit = needed - len(current_alive)
        print(f"[RESERVE] الاحتياطي يحتاج {deficit} بروكسي إضافي (المستهدف: {needed})")

        raw_proxies = fetch_raw_proxies()
        if not raw_proxies:
            print("[RESERVE] فشل جلب البروكسيات الخام")
            return

        # استبعاد البروكسيات المستخدمة مسبقاً
        with proxy_store_lock:
            used_addresses = set()
            for store in dynamic_proxy_store.values():
                for p in store.get("proxies", []):
                    used_addresses.add(p["address"])
        with reserve_pool_lock:
            for p in proxy_reserve_pool["proxies"]:
                used_addresses.add(p["address"])

        candidates = [p for p in raw_proxies if p not in used_addresses]
        sample_size = min(len(candidates), deficit * 8)
        if sample_size < deficit:
            # إذا المرشحون قليلون نوسع العينة
            sample_size = min(len(raw_proxies), needed * 6)
            candidates = raw_proxies

        sample = random.sample(candidates, sample_size)
        print(f"[RESERVE] اختبار {sample_size} بروكسي لتعبئة الاحتياطي...")
        new_alive = test_proxies_batch(sample, max_workers=15)

        # دمج مع الموجود وإزالة المكرر
        with reserve_pool_lock:
            combined = current_alive + new_alive
            seen = set()
            unique = []
            for p in combined:
                if p["address"] not in seen:
                    seen.add(p["address"])
                    unique.append(p)
            unique.sort(key=lambda x: x["latency"])
            proxy_reserve_pool["proxies"] = unique
            proxy_reserve_pool["last_filled"] = time.time()
            total = len(unique)

        print(f"[RESERVE] الاحتياطي جاهز: {total} بروكسي (مستهدف: {needed})")

    except Exception as e:
        print(f"[RESERVE] خطأ في ملء الاحتياطي: {e}")
    finally:
        with reserve_pool_lock:
            _reserve_fill_running = False
        _proxy_fetch_semaphore.release()


def trigger_reserve_fill():
    """تشغيل ملء الاحتياطي في خيط خلفي منفصل"""
    threading.Thread(target=_fill_reserve_pool_worker, daemon=True).start()


def _take_from_reserve(count=20):
    """
    أخذ 'count' بروكسي من الاحتياطي للتخصيص لحساب جديد.
    يُرجع قائمة البروكسيات ويحذفها من الاحتياطي.
    بعد الأخذ يطلق تعبئة الاحتياطي تلقائياً في الخلفية.
    """
    with reserve_pool_lock:
        alive = [p for p in proxy_reserve_pool["proxies"] if p.get("status", "active") != "dead"]
        taken = alive[:count]
        proxy_reserve_pool["proxies"] = alive[count:]

    if taken:
        print(f"[RESERVE] تم أخذ {len(taken)} بروكسي من الاحتياطي (متبقٍ: {len(proxy_reserve_pool['proxies'])})")

    # دائماً أعد تعبئة الاحتياطي بعد الأخذ منه
    trigger_reserve_fill()
    return taken


def fair_distribute_proxies(alive_proxies, accounts):
    """
    التوزيع العادل للبروكسيات على الحسابات.
    
    المنطق:
    - أفضل البروكسيات (السريعة جداً) تُوزَّع بالتناوب على جميع الحسابات
      حتى لو كانت قليلة — لا حساب واحد يستأثر بها.
    - بعد توزيع الأفضل، تُكمَّل الـ20 لكل حساب بأسرع المتبقيات.
    
    مثال: 3 حسابات، 6 بروكسيات ممتازة:
      حساب1 يأخذ: #1, #4, ...
      حساب2 يأخذ: #2, #5, ...
      حساب3 يأخذ: #3, #6, ...
    ثم تُكمَّل الـ20 بالبروكسيات التالية ترتيباً.
    
    يُرجع: { email: [قائمة_بروكسيات] }
    """
    if not accounts or not alive_proxies:
        return {}

    n = len(accounts)
    result = {email: [] for email in accounts}

    # المرحلة 1: توزيع بالتناوب (round-robin) للبروكسيات الأسرع
    # نعتبر "ممتازة" أي بروكسي latency <= 1.5 ثانية
    fast_proxies = [p for p in alive_proxies if p.get("latency", 999) <= 1.5]
    slow_proxies = [p for p in alive_proxies if p.get("latency", 999) > 1.5]

    # توزيع السريعة بالتناوب
    for i, proxy in enumerate(fast_proxies):
        email = accounts[i % n]
        if len(result[email]) < PROXIES_PER_ACCOUNT:
            result[email].append(proxy)

    # المرحلة 2: إكمال الـ20 لكل حساب من البروكسيات المتوسطة/البطيئة
    slow_idx = 0
    for email in accounts:
        while len(result[email]) < PROXIES_PER_ACCOUNT and slow_idx < len(slow_proxies):
            result[email].append(slow_proxies[slow_idx])
            slow_idx += 1

    return result


def get_proxy_country(ip):
    """جلب دولة البروكسي (مجاناً)"""
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=country,countryCode", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return data.get("country", "Unknown"), data.get("countryCode", "??")
    except Exception:
        pass
    return "Unknown", "??"

def latency_to_speed_label(latency):
    """تحويل زمن الاستجابة إلى تصنيف نصي"""
    if latency <= 1.0:
        return "🟢 سريع"
    elif latency <= 3.0:
        return "🟡 متوسط"
    else:
        return "🔴 بطيء"

def save_proxies_to_db(proxies_data, assigned_to):
    """حفظ البروكسيات في قاعدة البيانات"""
    try:
        # حذف البروكسيات القديمة لهذا الحساب أولاً
        del_headers = {**DB_HEADERS, "Prefer": "return=minimal"}
        requests.delete(
            f"{DB_PROXY_URL}?assigned_to=eq.{assigned_to}",
            headers=del_headers,
            timeout=10
        )
        # إضافة البروكسيات الجديدة
        for p in proxies_data:
            payload = {
                "proxy_address": p["address"],
                "protocol": p["address"].split("://")[0] if "://" in p["address"] else "http",
                "latency": p.get("latency", 999.0),
                "stability_score": p.get("stability", 80),
                "status": "active",
                "assigned_to": assigned_to,
                "last_checked": datetime.now(timezone.utc).isoformat()
            }
            try:
                requests.post(DB_PROXY_URL, json=payload, headers=DB_HEADERS, timeout=5)
            except Exception:
                pass
    except Exception as e:
        print(f"[PROXY DB] خطأ في الحفظ: {e}")

def load_proxies_from_db(assigned_to):
    """تحميل البروكسيات من قاعدة البيانات لحساب معين"""
    try:
        r = requests.get(
            f"{DB_PROXY_URL}?assigned_to=eq.{assigned_to}&status=eq.active&order=latency.asc",
            headers=DB_HEADERS,
            timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def mark_proxy_dead_in_db(proxy_address):
    """تحديث حالة البروكسي إلى dead في قاعدة البيانات"""
    try:
        requests.patch(
            f"{DB_PROXY_URL}?proxy_address=eq.{requests.utils.quote(proxy_address)}",
            json={"status": "dead"},
            headers={**DB_HEADERS, "Prefer": "return=minimal"},
            timeout=5
        )
    except Exception:
        pass

def refresh_dynamic_proxies():
    """
    العملية الرئيسية: جلب واختبار وتوزيع البروكسيات بالعدل على الحسابات الديناميكية.
    يتم استدعاء هذه الدالة كل 30 دقيقة من الخيط الخلفي.

    الجديد:
    ────────────────────────────────────────
    1. التوزيع العادل: أسرع البروكسيات تُوزَّع بالتناوب (round-robin) لا لحساب واحد.
    2. بعد الانتهاء يُعبَّأ المخزن الاحتياطي تلقائياً لتجهيز الحساب القادم.
    3. Semaphore يمنع التشغيل المتزامن مع reserve_fill.
    ────────────────────────────────────────
    """
    global last_proxy_refresh_time

    # منع التزامن مع _fill_reserve_pool_worker
    if not _proxy_fetch_semaphore.acquire(blocking=False):
        print("[PROXY] عملية جلب أخرى جارية، تأجيل refresh...")
        last_proxy_refresh_time = time.time()
        return

    # تحديد الحسابات الديناميكية (غير المستثناة) من جميع المصادر
    all_dynamic = set()
    for cid in user_data_store:
        em = user_data_store[cid].get("email", "").lower().strip()
        if em and em not in EXEMPT_ACCOUNTS:
            all_dynamic.add(em)
    # أضف أيضاً الحسابات المسجلة في active_accounts
    with active_accounts_lock:
        for accs in active_accounts.values():
            for em in accs:
                if em and em not in EXEMPT_ACCOUNTS:
                    all_dynamic.add(em.lower().strip())

    dynamic_accounts = list(all_dynamic)

    if not dynamic_accounts:
        print("[PROXY] لا توجد حسابات ديناميكية نشطة — تعبئة الاحتياطي فقط")
        last_proxy_refresh_time = time.time()
        trigger_reserve_fill()
        return

    # المطلوب = حسابات × 20 + احتياطي لحساب قادم
    needed_for_accounts = len(dynamic_accounts) * PROXIES_PER_ACCOUNT
    needed_total = needed_for_accounts + PROXIES_PER_ACCOUNT  # +20 للاحتياطي
    print(f"[PROXY] الحسابات: {len(dynamic_accounts)} | المطلوب: {needed_total} بروكسي")

    # جلب البروكسيات الخام
    raw_proxies = fetch_raw_proxies()
    if not raw_proxies:
        print("[PROXY] فشل جلب البروكسيات الخام")
        last_proxy_refresh_time = time.time()
        return

    # اختبار عينة (×4 بدل ×7 لتقليل ضغط الخيوط)
    sample_size = min(len(raw_proxies), needed_total * 4)
    sample = random.sample(raw_proxies, sample_size)

    print(f"[PROXY] اختبار {sample_size} بروكسي...")
    alive_proxies = test_proxies_batch(sample, max_workers=15)
    print(f"[PROXY] {len(alive_proxies)} بروكسي يعمل")

    # إذا لم يكفِ، نجلب دفعة إضافية
    if len(alive_proxies) < needed_total:
        remaining = [p for p in raw_proxies if p not in sample]
        if remaining:
            extra_size = min(len(remaining), needed_total * 4)
            extra = random.sample(remaining, extra_size)
            extra_alive = test_proxies_batch(extra, max_workers=15)
            alive_proxies.extend(extra_alive)
            # إزالة مكررات + إعادة ترتيب
            seen = set()
            unique = []
            for p in alive_proxies:
                if p["address"] not in seen:
                    seen.add(p["address"])
                    unique.append(p)
            unique.sort(key=lambda x: x["latency"])
            alive_proxies = unique

    # ── التوزيع العادل على الحسابات ──
    distribution = fair_distribute_proxies(alive_proxies[:needed_for_accounts], dynamic_accounts)

    with proxy_store_lock:
        for email, account_proxies in distribution.items():
            if not account_proxies:
                continue
            # إضافة stability score
            for i, p in enumerate(account_proxies):
                p["stability"] = max(50, 100 - i * 2)

            dynamic_proxy_store[email] = {
                "proxies": account_proxies,
                "current_index": 0,
                "last_updated": time.time()
            }
            enqueue_db_save(save_proxies_to_db, account_proxies, email)
            fast = sum(1 for p in account_proxies if p.get("latency", 9) <= 1.5)
            print(f"[PROXY] {email}: {len(account_proxies)} بروكسي ({fast} سريع جداً)")

    last_proxy_refresh_time = time.time()
    print("[PROXY] اكتمل تحديث البروكسيات الديناميكية بالتوزيع العادل")
    _proxy_fetch_semaphore.release()

    # ── تعبئة الاحتياطي من البروكسيات المتبقية فوراً ──
    used_in_distribution = set()
    for proxies_list in distribution.values():
        for p in proxies_list:
            used_in_distribution.add(p["address"])
    leftover = [p for p in alive_proxies if p["address"] not in used_in_distribution]
    if leftover:
        with reserve_pool_lock:
            existing = proxy_reserve_pool.get("proxies", [])
            combined = existing + leftover
            seen2 = set()
            unique2 = []
            for p in combined:
                if p["address"] not in seen2:
                    seen2.add(p["address"])
                    unique2.append(p)
            unique2.sort(key=lambda x: x["latency"])
            proxy_reserve_pool["proxies"] = unique2
            proxy_reserve_pool["last_filled"] = time.time()
        print(f"[RESERVE] تم تحديث الاحتياطي: {len(unique2)} بروكسي")
    else:
        # طلب تعبئة من المصدر في الخلفية
        trigger_reserve_fill()

def get_current_proxy_for_account(email):
    """
    إرجاع البروكسي الحالي النشط للحساب الديناميكي.
    في حالة الفشل، يتم التبديل تلقائياً للاحتياطي.
    """
    email_lower = email.lower().strip()

    if email_lower in EXEMPT_ACCOUNTS:
        return None  # الحسابات المستثناة تدار بنظام منفصل

    with proxy_store_lock:
        store = dynamic_proxy_store.get(email_lower)
        if not store or not store["proxies"]:
            return None

        idx = store.get("current_index", 0)
        proxies = store["proxies"]

        # إيجاد أول بروكسي نشط
        for i in range(len(proxies)):
            actual_idx = (idx + i) % len(proxies)
            p = proxies[actual_idx]
            if p.get("status", "active") != "dead":
                store["current_index"] = actual_idx
                return p["address"]

    return None

def failover_proxy_for_account(email, failed_address):
    """
    عند فشل البروكسي الحالي: تحديد الفاشل وتفعيل الاحتياطي فوراً.
    """
    email_lower = email.lower().strip()

    with proxy_store_lock:
        store = dynamic_proxy_store.get(email_lower)
        if not store:
            return None

        proxies = store["proxies"]
        # تحديد البروكسي الفاشل
        for p in proxies:
            if p["address"] == failed_address:
                p["status"] = "dead"
                break

        # التبديل للتالي
        current_idx = store.get("current_index", 0)
        for i in range(1, len(proxies) + 1):
            next_idx = (current_idx + i) % len(proxies)
            if proxies[next_idx].get("status", "active") != "dead":
                store["current_index"] = next_idx
                new_proxy = proxies[next_idx]["address"]
                print(f"[PROXY] Failover لـ {email}: {failed_address} → {new_proxy}")
                # تحديث DB في الخلفية
                enqueue_db_save(mark_proxy_dead_in_db, failed_address)
                return new_proxy

    return None

def get_proxy_info_for_display(email):
    """
    إرجاع معلومات البروكسي الحالي للعرض في الواجهة.
    """
    email_lower = email.lower().strip()

    if email_lower in EXEMPT_ACCOUNTS:
        # معلومات الحساب المستثنى
        proxies = ACCOUNT_PROXIES.get(email_lower, [])
        if proxies:
            return {
                "address": proxies[0],
                "ip": proxies[0].split(":")[0],
                "country": "Static",
                "speed": "🔵 ثابت",
                "type": "static"
            }
        return None

    with proxy_store_lock:
        store = dynamic_proxy_store.get(email_lower)
        if not store or not store["proxies"]:
            return None

        idx = store.get("current_index", 0)
        proxies = store["proxies"]

        for i in range(len(proxies)):
            actual_idx = (idx + i) % len(proxies)
            p = proxies[actual_idx]
            if p.get("status", "active") != "dead":
                addr = p["address"]
                ip = p.get("ip", addr.split("://")[-1].split(":")[0])
                latency = p.get("latency", 999.0)
                speed = latency_to_speed_label(latency)

                # استخراج العنوان بدون البروتوكول
                display_addr = addr.replace("http://", "").replace("https://", "").replace("socks5://", "")

                return {
                    "address": display_addr,
                    "ip": ip,
                    "country": p.get("country", "Unknown"),
                    "country_code": p.get("country_code", "??"),
                    "city": p.get("city", ""),
                    "region": p.get("region", ""),
                    "isp": p.get("isp", ""),
                    "speed": speed,
                    "latency": latency,
                    "type": "dynamic"
                }
    return None

# ==========================================
# متغيرات الحالة العامة
# ==========================================
user_sessions = {}
user_data_store = {}          # chat_id -> {email, password}  (الحساب النشط للعرض فقط)
user_numbered_tasks = {}
user_transient_messages = {}
user_pending_tasks = {}       # chat_id -> [confirmed tasks list]

# مخزن الجلسات المصادقة (email -> requests.Session) — الإصلاح #1
user_auth_sessions = {}
auth_sessions_lock = threading.Lock()

# ─── الحسابات المُسجَّل خروجها (جلستها منتهية) ────────────────────────────────
# { chat_id: set(email_lower, ...) }
# عند التبديل لحساب آخر لا نضيف لهذه القائمة (الجلسة تبقى)
# عند تسجيل الدخول مجدداً نحذفه من هذه القائمة
logged_out_accounts = {}   # chat_id -> set of email_lower
logged_out_lock = threading.Lock()

# ─── حماية من تكرار معالجة الحظر لنفس الحساب ───────────────────────────────
# يمنع إرسال رسالة الحظر أكثر من مرة واحدة لنفس الحساب
_handling_blocked = set()   # set of email_lower
_handling_blocked_lock = threading.Lock()

# ─── حماية من تكرار رسالة تسجيل الخروج لنفس الحساب ────────────────────────
# { (chat_id, email_lower): timestamp } — إرسال واحد كل 60 ثانية على الأقل
_logout_sent_times = {}
_logout_sent_lock = threading.Lock()

# ─── نظام الحسابات المتعددة ─────────────────────────────────────────────────
# active_accounts[chat_id][email] = {email, password}
# جميع الحسابات المحفوظة تعمل في الخلفية بغض النظر عن الحساب النشط للعرض
active_accounts = {}           # chat_id -> {email: {email, password}}
active_accounts_lock = threading.Lock()

# إعدادات مستقلة لكل حساب (مفتاحها email)
acct_notify_status = {}        # email -> bool
acct_all_notify_status = {}    # email -> bool
acct_notify_interval = {}      # email -> int (دقائق)
acct_auto_hunt_status = {}     # email -> bool
acct_hunt_mode = {}            # email -> "GT" | "GTE"
acct_auto_hunt_mode = {}       # تعيين أسرع, نفس hunt_mode
acct_auto_execute_status = {}  # email -> bool
acct_auto_execute_interval = {}# email -> int
# ─────────────────────────────────────────────────────────────────────────────

# المتغيرات القديمة (للحساب النشط - للواجهة فقط)
notify_status = {}
all_notify_status = {}
notify_interval = {}
auto_hunt_status = {}
hunt_mode = {}
last_take_time = {}
TAKE_COOLDOWN = 60

user_notify_tasks = {}
ignored_tasks = {}

auto_execute_status = {}
auto_execute_interval = {}

sent_notifications = {}

def get_email_settings(email):
    """جلب إعدادات حساب معين (email) من المخزن المستقل"""
    e = email.lower().strip()
    return {
        'notify_status': acct_notify_status.get(e, False),
        'all_notify_status': acct_all_notify_status.get(e, False),
        'notify_interval': acct_notify_interval.get(e, 10),
        'auto_hunt_status': acct_auto_hunt_status.get(e, False),
        'hunt_mode': acct_hunt_mode.get(e, 'GTE'),
        'auto_execute_status': acct_auto_execute_status.get(e, False),
        'auto_execute_interval': acct_auto_execute_interval.get(e, 5),
    }

def sync_chat_settings_to_email(chat_id, email):
    """نسخ إعدادات chat_id الحالية إلى مفتاح email المستقل"""
    e = email.lower().strip()
    acct_notify_status[e] = notify_status.get(chat_id, False)
    acct_all_notify_status[e] = all_notify_status.get(chat_id, False)
    acct_notify_interval[e] = notify_interval.get(chat_id, 10)
    acct_auto_hunt_status[e] = auto_hunt_status.get(chat_id, False)
    acct_hunt_mode[e] = hunt_mode.get(chat_id, 'GTE')
    acct_auto_execute_status[e] = auto_execute_status.get(chat_id, False)
    acct_auto_execute_interval[e] = auto_execute_interval.get(chat_id, 5)

def sync_email_settings_to_chat(chat_id, email):
    """نسخ إعدادات email المستقلة إلى متغيرات chat_id (للواجهة)"""
    e = email.lower().strip()
    notify_status[chat_id] = acct_notify_status.get(e, False)
    all_notify_status[chat_id] = acct_all_notify_status.get(e, False)
    notify_interval[chat_id] = acct_notify_interval.get(e, 10)
    auto_hunt_status[chat_id] = acct_auto_hunt_status.get(e, False)
    hunt_mode[chat_id] = acct_hunt_mode.get(e, 'GTE')
    auto_execute_status[chat_id] = acct_auto_execute_status.get(e, False)
    auto_execute_interval[chat_id] = acct_auto_execute_interval.get(e, 5)

def register_account_in_active(chat_id, email, password):
    """تسجيل حساب في قائمة الحسابات النشطة في الخلفية"""
    with active_accounts_lock:
        if chat_id not in active_accounts:
            active_accounts[chat_id] = {}
        active_accounts[chat_id][email.lower().strip()] = {
            'email': email, 'password': password
        }

def get_all_active_accounts_for_chat(chat_id):
    """إرجاع كل الحسابات النشطة لمستخدم معين"""
    with active_accounts_lock:
        return dict(active_accounts.get(chat_id, {}))

def load_all_saved_accounts_to_active(chat_id):
    """تحميل جميع الحسابات المحفوظة لمستخدم وتسجيلها كنشطة"""
    saved = get_saved_multi_accounts(chat_id)
    for acc in saved:
        register_account_in_active(chat_id, acc['email'], acc['password'])

# ==========================================
# ☁️ نظام الحسابات المتعددة السحابي (Supabase)
# الحسابات محفوظة في جدول multi_accounts — لا تضيع عند إعادة تشغيل VPS
# ==========================================

# كاش في الذاكرة لتجنب الطلبات المتكررة
# { chat_id: [{'email': ..., 'password': ...}, ...] }
_multi_accounts_cache = {}
_multi_accounts_cache_lock = threading.Lock()

def _generate_account_fingerprint(chat_id, email):
    """
    توليد بصمة فريدة لحساب معين.
    البصمة مرتبطة بـ chat_id + email — لا تتكرر أبداً ولا تُشارك مع أي حساب آخر.
    """
    unique_seed = f"{chat_id}:{email.strip().lower()}:{uuid.uuid4()}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_seed))

def cloud_get_account_fingerprint(chat_id, email):
    """
    جلب البصمة الموجودة للحساب من Supabase.
    إذا لم تكن موجودة يُرجع None.
    """
    try:
        email_lower = str(email).strip().lower()
        r = requests.get(
            f"{DB_MULTI_ACCOUNTS_URL}?chat_id=eq.{int(chat_id)}&email=eq.{email_lower}&select=fingerprint",
            headers=DB_HEADERS,
            timeout=10
        )
        if r.status_code == 200 and r.json():
            return r.json()[0].get('fingerprint')
    except Exception as e:
        print(f"[FINGERPRINT] خطأ في جلب البصمة: {e}")
    return None

def cloud_save_multi_account(chat_id, email, password):
    """
    حفظ حساب في جدول multi_accounts السحابي مع بصمة فريدة.
    - إذا كان الحساب جديداً: تُولَّد بصمة جديدة فريدة وتُحفظ.
    - إذا كان موجوداً مسبقاً: تُحافظ على البصمة القديمة (لا تتغير أبداً).
    """
    try:
        email_lower = str(email).strip().lower()
        cid = int(chat_id)

        # تحقق من وجود بصمة سابقة في الكاش أو السحابة
        existing_fp = None
        with _multi_accounts_cache_lock:
            if cid in _multi_accounts_cache:
                for acc in _multi_accounts_cache[cid]:
                    if acc['email'].lower() == email_lower:
                        existing_fp = acc.get('fingerprint')
                        break

        if not existing_fp:
            existing_fp = cloud_get_account_fingerprint(chat_id, email)

        # إذا لم توجد بصمة نولّد واحدة جديدة
        fingerprint = existing_fp if existing_fp else _generate_account_fingerprint(chat_id, email)

        payload = {
            "chat_id": cid,
            "email": email_lower,
            "password": str(password),
            "fingerprint": fingerprint,
            "fingerprint_created_at": datetime.now(timezone.utc).isoformat() if not existing_fp else None
        }

        # إذا كانت البصمة موجودة مسبقاً لا نرسل fingerprint_created_at مجدداً
        if existing_fp:
            del payload["fingerprint_created_at"]

        headers = {**DB_HEADERS, "Prefer": "resolution=merge-duplicates"}
        r = requests.post(DB_MULTI_ACCOUNTS_URL, json=payload, headers=headers, timeout=10)
        success = r.status_code in [200, 201]
        if success:
            # تحديث الكاش مع البصمة
            with _multi_accounts_cache_lock:
                if cid not in _multi_accounts_cache:
                    _multi_accounts_cache[cid] = []
                found = False
                for acc in _multi_accounts_cache[cid]:
                    if acc['email'].lower() == email_lower:
                        acc['password'] = password
                        acc['fingerprint'] = fingerprint
                        found = True
                        break
                if not found:
                    _multi_accounts_cache[cid].append({
                        'email': email_lower,
                        'password': password,
                        'fingerprint': fingerprint
                    })
            print(f"[FINGERPRINT] ✅ بصمة الحساب {email_lower}: {fingerprint}")
        return success
    except Exception as e:
        print(f"[MULTI-DB] خطأ في الحفظ: {e}")
        return False

def cloud_get_multi_accounts(chat_id):
    """
    جلب جميع الحسابات المحفوظة لمستخدم معين من Supabase.
    يستخدم الكاش — يُحدَّث عند الحاجة فقط.
    يشمل البصمة الخاصة بكل حساب.
    """
    cid = int(chat_id)
    # جرب الكاش أولاً
    with _multi_accounts_cache_lock:
        if cid in _multi_accounts_cache:
            return list(_multi_accounts_cache[cid])
    # جلب من السحابة
    try:
        r = requests.get(
            f"{DB_MULTI_ACCOUNTS_URL}?chat_id=eq.{cid}&order=id.asc",
            headers=DB_HEADERS,
            timeout=10
        )
        if r.status_code == 200:
            rows = r.json()
            result = [
                {
                    'email': row['email'],
                    'password': row['password'],
                    'fingerprint': row.get('fingerprint', '')
                }
                for row in rows
            ]
            with _multi_accounts_cache_lock:
                _multi_accounts_cache[cid] = result
            return result
    except Exception as e:
        print(f"[MULTI-DB] خطأ في الجلب: {e}")
    return []

def cloud_delete_multi_account(chat_id, email):
    """حذف حساب محدد من multi_accounts (يُحذف مع بصمته نهائياً)"""
    try:
        email_lower = str(email).strip().lower()
        r = requests.delete(
            f"{DB_MULTI_ACCOUNTS_URL}?chat_id=eq.{int(chat_id)}&email=eq.{email_lower}",
            headers={**DB_HEADERS, "Prefer": "return=minimal"},
            timeout=10
        )
        # تحديث الكاش
        with _multi_accounts_cache_lock:
            cid = int(chat_id)
            if cid in _multi_accounts_cache:
                _multi_accounts_cache[cid] = [
                    a for a in _multi_accounts_cache[cid]
                    if a['email'].lower() != email_lower
                ]
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"[MULTI-DB] خطأ في الحذف: {e}")
        return False

def cloud_get_fingerprint_for_account(chat_id, email):
    """
    إرجاع البصمة الخاصة بحساب معين من الكاش أو السحابة.
    هذه البصمة فريدة تماماً ولا تُشارك مع أي حساب آخر.
    """
    email_lower = str(email).strip().lower()
    cid = int(chat_id)
    # جرب الكاش أولاً
    with _multi_accounts_cache_lock:
        if cid in _multi_accounts_cache:
            for acc in _multi_accounts_cache[cid]:
                if acc['email'].lower() == email_lower:
                    fp = acc.get('fingerprint', '')
                    if fp:
                        return fp
    # جلب من السحابة
    return cloud_get_account_fingerprint(chat_id, email)

def cloud_load_all_multi_accounts():
    """
    جلب جميع الحسابات لجميع المستخدمين دفعة واحدة عند بدء التشغيل.
    يُرجع dict: { chat_id(int): [{'email':..,'password':..,'fingerprint':..}, ...] }
    """
    try:
        r = requests.get(
            f"{DB_MULTI_ACCOUNTS_URL}?order=chat_id.asc,id.asc",
            headers=DB_HEADERS,
            timeout=15
        )
        if r.status_code == 200:
            rows = r.json()
            result = {}
            for row in rows:
                cid = int(row['chat_id'])
                if cid not in result:
                    result[cid] = []
                result[cid].append({
                    'email': row['email'],
                    'password': row['password'],
                    'fingerprint': row.get('fingerprint', '')
                })
            # تحديث الكاش الكامل
            with _multi_accounts_cache_lock:
                _multi_accounts_cache.clear()
                _multi_accounts_cache.update(result)
            return result
    except Exception as e:
        print(f"[MULTI-DB] خطأ في جلب الكل: {e}")
    return {}

# ── دوال التوافق — نفس الأسماء القديمة تشير الآن للسحابة ──
def save_multi_account(chat_id, email, password):
    """واجهة توافق — تحفظ في Supabase"""
    return cloud_save_multi_account(chat_id, email, password)

def get_saved_multi_accounts(chat_id):
    """واجهة توافق — تجلب من Supabase (مع كاش)"""
    return cloud_get_multi_accounts(chat_id)

def load_multi_accounts():
    """واجهة توافق — تجلب الكل من Supabase"""
    return cloud_load_all_multi_accounts()

def delete_transient_message(bot, chat_id):
    if chat_id in user_transient_messages:
        try:
            bot.delete_message(chat_id, user_transient_messages[chat_id])
        except Exception:
            pass
        del user_transient_messages[chat_id]

# ==========================================
# 🗄️ عمليات قاعدة البيانات (Supabase)
# ==========================================
def cloud_save_account(chat_id, username, password):
    payload = {"chat_id": int(chat_id), "username": str(username), "password": str(password)}
    try:
        requests.post(DB_API_URL, json=payload, headers=DB_HEADERS, timeout=10)
    except Exception:
        pass

def cloud_get_account(chat_id):
    try:
        url = f"{DB_API_URL}?chat_id=eq.{chat_id}"
        response = requests.get(url, headers=DB_HEADERS, timeout=10)
        if response.status_code == 200 and response.json():
            return response.json()[0]
    except Exception:
        pass
    return None

def cloud_delete_account(chat_id):
    try:
        url = f"{DB_API_URL}?chat_id=eq.{chat_id}"
        payload = {"username": "", "password": ""}
        requests.patch(url, json=payload, headers=DB_HEADERS, timeout=10)
    except Exception:
        pass

def cloud_save_auto_task(chat_id, keyword, work_url, proof_msg):
    payload = {
        "chat_id": int(chat_id),
        "keyword": str(keyword),
        "work_url": str(work_url) if work_url else None,
        "proof_msg": str(proof_msg)
    }
    try:
        r = requests.post(DB_AUTO_TASKS_URL, json=payload, headers=DB_HEADERS, timeout=10)
        return r.status_code in [200, 201]
    except Exception:
        return False

def cloud_get_auto_tasks(chat_id):
    try:
        url = f"{DB_AUTO_TASKS_URL}?chat_id=eq.{int(chat_id)}&order=id.asc"
        response = requests.get(url, headers=DB_HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

def cloud_delete_auto_task(task_id):
    try:
        url = f"{DB_AUTO_TASKS_URL}?id=eq.{task_id}"
        requests.delete(url, headers=DB_HEADERS, timeout=10)
        return True
    except Exception:
        return False

def cloud_update_template(template_id, keyword, work_url, proof_msg):
    payload = {
        "keyword": str(keyword),
        "work_url": str(work_url) if work_url else None,
        "proof_msg": str(proof_msg)
    }
    try:
        url = f"{DB_AUTO_TASKS_URL}?id=eq.{template_id}"
        r = requests.patch(url, json=payload, headers=DB_HEADERS, timeout=10)
        return r.status_code in [200, 204]
    except Exception:
        return False

def cloud_share_templates_by_chat_id(target_chat_id, current_chat_id):
    try:
        current_templates = cloud_get_auto_tasks(current_chat_id)
        if not current_templates:
            return "EMPTY"

        existing_keywords = set()
        target_templates = cloud_get_auto_tasks(target_chat_id)
        for t in target_templates:
            existing_keywords.add(t.get('keyword', '').strip().lower())

        success_count = 0
        original_template_ids = []

        for tmpl in current_templates:
            kw = tmpl['keyword'].strip().lower()
            if kw in existing_keywords:
                continue
            payload = {
                "chat_id": int(target_chat_id),
                "keyword": str(tmpl['keyword']),
                "work_url": str(tmpl.get('work_url')) if tmpl.get('work_url') else None,
                "proof_msg": str(tmpl['proof_msg'])
            }
            r = requests.post(DB_AUTO_TASKS_URL, json=payload, headers=DB_HEADERS, timeout=10)
            if r.status_code in [200, 201]:
                success_count += 1
                existing_keywords.add(kw)
                original_template_ids.append(tmpl['id'])

        if original_template_ids:
            for template_id in original_template_ids:
                try:
                    cloud_delete_auto_task(template_id)
                except Exception:
                    pass

        if success_count == 0:
            return "ALREADY_EXISTS"

        try:
            bot.send_message(current_chat_id, f"✅ تم نقل {success_count} الباقة بنجاح إلى حساب التليجرام {target_chat_id}")
            bot.send_message(target_chat_id, f"📥 تم استلام {success_count} الباقة جديد من حساب التليجرام {current_chat_id}")
        except Exception:
            pass

        return "SUCCESS"
    except Exception as e:
        print(f"❌ خطأ في المشاركة: {e}")
        return "ERROR"

def cloud_save_user_settings(chat_id):
    email = user_data_store.get(chat_id, {}).get('email', '')
    # مزامنة إعدادات chat_id → email المستقل
    if email:
        sync_chat_settings_to_email(chat_id, email)
    payload = {
        "notify_status": bool(notify_status.get(chat_id, False)),
        "notify_interval": int(notify_interval.get(chat_id, 10)),
        "auto_hunt_status": bool(auto_hunt_status.get(chat_id, False)),
        "hunt_mode": str(hunt_mode.get(chat_id, "GTE")),
        "auto_execute_status": bool(auto_execute_status.get(chat_id, False)),
        "auto_execute_interval": int(auto_execute_interval.get(chat_id, 5)),
        "all_notify_status": bool(all_notify_status.get(chat_id, False))
    }
    try:
        url = f"{DB_API_URL}?chat_id=eq.{chat_id}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        response = requests.patch(url, json=payload, headers=headers, timeout=10)
        return response.status_code in [200, 204]
    except Exception:
        return False

def cloud_load_user_settings(chat_id):
    try:
        url = f"{DB_API_URL}?chat_id=eq.{chat_id}&select=notify_status,notify_interval,auto_hunt_status,hunt_mode,auto_execute_status,auto_execute_interval,all_notify_status"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and response.json():
            settings = response.json()[0]
            notify_status[chat_id] = settings.get('notify_status', False)
            all_notify_status[chat_id] = settings.get('all_notify_status', False)
            notify_interval[chat_id] = settings.get('notify_interval', 10)
            auto_hunt_status[chat_id] = settings.get('auto_hunt_status', False)
            hunt_mode[chat_id] = settings.get('hunt_mode', 'GTE')
            auto_execute_status[chat_id] = settings.get('auto_execute_status', False)
            auto_execute_interval[chat_id] = settings.get('auto_execute_interval', 5)
            # مزامنة الإعدادات للحساب النشط الحالي
            email = user_data_store.get(chat_id, {}).get('email', '')
            if email:
                sync_chat_settings_to_email(chat_id, email)
            return True
    except Exception:
        pass
    return False

def _prepare_session_with_proxy(email, password):
    """
    دالة مشتركة: تجهيز البروكسي ثم إنشاء الجلسة المصادقة وحفظها.
    تعمل بأمان في خيط مستقل — تحل مشكلة Python closure bug.
    """
    email_lower = email.lower().strip()
    # 1) جلب/تجهيز البروكسي أولاً (تزامني داخل الخيط)
    _ensure_proxy_for_account(email_lower)
    # 2) إنشاء الجلسة مع البروكسي المجهّز
    sess = get_authenticated_session(email, password)
    if sess:
        with auth_sessions_lock:
            user_auth_sessions[email_lower] = sess
        print(f"[SESSION] جلسة جاهزة وبروكسي نشط: {email_lower}")
    else:
        print(f"[SESSION] فشل تجهيز الجلسة للحساب: {email_lower}")

def check_and_load_session_silently(chat_id):
    if chat_id not in user_data_store:
        saved_acc = cloud_get_account(chat_id)
        if saved_acc:
            settings_loaded = cloud_load_user_settings(chat_id)
            if not settings_loaded:
                notify_status[chat_id] = False
                all_notify_status[chat_id] = False
                notify_interval[chat_id] = 10
                auto_hunt_status[chat_id] = False
                hunt_mode[chat_id] = "GTE"
                auto_execute_status[chat_id] = False
                auto_execute_interval[chat_id] = 5
            if saved_acc.get('username') and saved_acc.get('password'):
                email = saved_acc['username']
                password = saved_acc['password']
                user_data_store[chat_id] = {'email': email, 'password': password}

                email_lower = email.lower().strip()
                with auth_sessions_lock:
                    cached = user_auth_sessions.get(email_lower)
                if not cached:
                    # تجهيز البروكسي والجلسة في خيط خلفي — بدون closure bug
                    threading.Thread(
                        target=_prepare_session_with_proxy,
                        args=(email, password),
                        daemon=True
                    ).start()
                return True
            return False
        return False
    if chat_id not in notify_status:
        cloud_load_user_settings(chat_id)
    return True

def safe_edit_or_send(bot, chat_id, message_id, new_text, reply_markup=None, parse_mode=None):
    try:
        bot.edit_message_text(new_text, chat_id, message_id, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        try:
            bot.send_message(chat_id, new_text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception:
            pass

# ==========================================
# 🚨 كشف وإدارة BLOCKED و CAPTCHA
# ==========================================

def detect_page_state(html_text):
    """
    يفحص نص صفحة HTML ويُرجع:
      - 'blocked'  إذا كان الحساب محظوراً
      - 'captcha'  إذا ظهرت صفحة captcha أو تحقق
      - None       إذا كانت الصفحة عادية
    """
    if not html_text:
        return None

    # ── كشف الحظر: النص الروسي الموجود في صفحة BLOCKED ──
    blocked_signals = [
        "заблокирован",          # الحساب محظور
        "аккаунт заблокирован",  # الحساب محظور (أكثر دقة)
        "account is blocked",
        "account blocked",
    ]
    html_lower = html_text.lower()
    for sig in blocked_signals:
        if sig in html_lower:
            return "blocked"

    # ── كشف CAPTCHA: صفحة تسجيل الدخول بدون زر الخروج ──
    # صفحة CAPTCHA_PAGE تُظهر صفحة رئيسية بدون "Выход" (زر الخروج)
    # وتحتوي على "Вход" (تسجيل الدخول) مما يعني أن الجلسة انهارت
    captcha_signals = [
        "recaptcha",
        "g-recaptcha",
        "captcha",
        "i am not a robot",
        "я не робот",
        "cloudflare",
        "cf-challenge",
        "challenge-form",
    ]
    for sig in captcha_signals:
        if sig in html_lower:
            return "captcha"

    # صفحة الموقع الرئيسية بدون جلسة = captcha/انتهاء جلسة مع وجود صفحة تسجيل الدخول
    # الموقع يعيد توجيه الجلسة المنتهية إلى الصفحة الرئيسية
    if "login-box" in html_lower and "Выход" not in html_text:
        return "captcha"

    return None


def handle_blocked_account(email, chat_id_origin=None):
    """
    عند اكتشاف أن حساباً محظور:
    1. يضمن إرسال رسالة الحظر مرة واحدة فقط لكل حساب (حماية من التكرار)
    2. يحذف الحساب نهائياً من جميع القوائم والجلسات
    """
    email_lower = email.lower().strip()

    # ── حماية من التكرار: إذا كان يُعالَج الآن نتجاهل ──
    with _handling_blocked_lock:
        if email_lower in _handling_blocked:
            print(f"[BLOCKED] {email_lower} — معالجة الحظر جارية بالفعل، تجاهل التكرار")
            return
        _handling_blocked.add(email_lower)

    try:
        account_label = email_lower.split("@")[0]
        print(f"[BLOCKED] ⛔ الحساب {email_lower} محظور — جاري الحذف النهائي")

        # ── 1: إيقاف جميع المهام التلقائية للحساب المحظور ──
        acct_notify_status[email_lower] = False
        acct_all_notify_status[email_lower] = False
        acct_auto_hunt_status[email_lower] = False
        acct_auto_execute_status[email_lower] = False

        # ── 2: مسح الجلسة النشطة ──
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)

        # ── 3: حذف البروكسيات المرتبطة بالحساب ──
        with proxy_store_lock:
            dynamic_proxy_store.pop(email_lower, None)

        # ── 4: تحديد كل chat_ids التي تملك هذا الحساب ──
        affected_chats = []
        with active_accounts_lock:
            for cid, accounts in active_accounts.items():
                if email_lower in accounts:
                    affected_chats.append(cid)

        blocked_msg = (
            f"🚫 **تنبيه: حساب محظور**\n\n"
            f"⛔ الحساب **{account_label}** (`{email_lower}`) تعرّض للحظر من قِبَل الموقع.\n\n"
            f"📌 تم تسجيل الخروج وحذفه تلقائياً.\n"
            f"💡 للاستفسار: `support@forumok.com`"
        )

        for cid in affected_chats:
            try:
                # ── حذف الحساب نهائياً من active_accounts ──
                with active_accounts_lock:
                    if cid in active_accounts:
                        active_accounts[cid].pop(email_lower, None)

                # ── حذف الحساب نهائياً من قاعدة البيانات السحابية ──
                threading.Thread(
                    target=cloud_delete_multi_account,
                    args=(cid, email_lower),
                    daemon=True
                ).start()

                # ── تعليم الحساب كـ"مُسجَّل خروجه" ──
                with logged_out_lock:
                    if cid not in logged_out_accounts:
                        logged_out_accounts[cid] = set()
                    logged_out_accounts[cid].add(email_lower)

                # إذا كان هذا هو الحساب النشط حالياً في الواجهة → امسح بياناته
                active_email = user_data_store.get(cid, {}).get("email", "").lower().strip()
                if active_email == email_lower:
                    for store in [user_data_store, user_sessions, user_numbered_tasks,
                                  notify_status, notify_interval, auto_hunt_status, hunt_mode,
                                  last_take_time, user_notify_tasks, ignored_tasks,
                                  auto_execute_status, auto_execute_interval, all_notify_status]:
                        store.pop(cid, None)

                # ── إرسال رسالة واحدة فقط لكل chat_id ──
                try:
                    bot.send_message(cid, blocked_msg, parse_mode="Markdown")
                except Exception as e:
                    print(f"[BLOCKED] خطأ في إرسال تنبيه blocked لـ {cid}: {e}")

            except Exception as e:
                print(f"[BLOCKED] خطأ في معالجة chat_id {cid}: {e}")

    finally:
        # إزالة الحساب من مجموعة المعالجة بعد 120 ثانية (لو عاد ظهوره مجدداً)
        def _clear_handling():
            time.sleep(120)
            with _handling_blocked_lock:
                _handling_blocked.discard(email_lower)
        threading.Thread(target=_clear_handling, daemon=True).start()


def handle_captcha_detected(email, context=""):
    """
    عند اكتشاف CAPTCHA:
    يرسل رسالة خاصة إلى CAPTCHA_ALERT_CHAT_ID يُخبره بظهور تحقق للحساب.
    context: وصف المكان الذي ظهر فيه CAPTCHA (تسجيل دخول / أثناء العمل)
    """
    email_lower = email.lower().strip()
    account_label = email_lower.split("@")[0]

    print(f"[CAPTCHA] ⚠️ ظهر CAPTCHA للحساب {email_lower} — إرسال تنبيه")

    context_text = f"\n📍 **السياق:** {context}" if context else ""

    captcha_msg = (
        f"🤖 **تنبيه: CAPTCHA ظهر!**\n\n"
        f"🔐 الحساب: **{account_label}** (`{email_lower}`)\n"
        f"{context_text}\n"
        f"⚠️ يجب حل التحقق يدوياً أو تغيير البروكسي.\n\n"
        f"🔄 تم إيقاف العمل التلقائي لهذا الحساب مؤقتاً."
    )

    # إيقاف مؤقت لجميع المهام التلقائية حتى يُحَل CAPTCHA
    acct_notify_status[email_lower] = False
    acct_all_notify_status[email_lower] = False
    acct_auto_hunt_status[email_lower] = False
    acct_auto_execute_status[email_lower] = False

    # مسح الجلسة المنتهية
    with auth_sessions_lock:
        user_auth_sessions.pop(email_lower, None)

    try:
        bot.send_message(CAPTCHA_ALERT_CHAT_ID, captcha_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"[CAPTCHA] خطأ في إرسال تنبيه CAPTCHA: {e}")

# ==========================================
# دوال البروكسي للحسابات المستثناة (ثابتة)
# ==========================================
def get_fastest_proxy_exempt(email):
    """أسرع بروكسي للحسابات المستثناة (5 بروكسيات ثابتة)"""
    proxies = ACCOUNT_PROXIES.get(email.lower().strip())
    if not proxies:
        return None
    fastest_proxy = None
    best_response_time = float('inf')
    for prx in proxies:
        try:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{prx}"
            start_time = time.time()
            r = requests.head(BASE_URL, headers=HEADERS, proxies={"http": proxy_url, "https": proxy_url}, timeout=3)
            elapsed = time.time() - start_time
            if elapsed < best_response_time:
                best_response_time = elapsed
                fastest_proxy = prx
        except Exception:
            continue
    if not fastest_proxy:
        fastest_proxy = random.choice(proxies)
    return fastest_proxy

def get_first_alive_proxy(raw_proxies, batch_size=100, max_wait=25):
    """
    يختبر البروكسيات دفعة واحدة بالتوازي ويُرجع أول بروكسي يعمل فور وجوده.
    max_wait: الحد الأقصى للانتظار بالثواني.
    يُرجع dict البروكسي الأسرع أو None.
    """
    sample = random.sample(raw_proxies, min(len(raw_proxies), batch_size))
    first_result = [None]
    found_event = threading.Event()

    def _test(proxy_url):
        if found_event.is_set():
            return
        result = test_single_proxy(proxy_url)
        if result["alive"] and not found_event.is_set():
            first_result[0] = result
            found_event.set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(_test, p) for p in sample]
        found_event.wait(timeout=max_wait)
        # إلغاء الخيوط المتبقية بأسرع وقت
        for f in futures:
            f.cancel()

    return first_result[0]


def _background_fill_proxies(email_lower, raw_proxies, first_proxy):
    """
    يعمل في الخلفية بعد تسجيل الدخول:
    1. يأخذ من المخزن الاحتياطي أولاً (سريع جداً).
    2. إن لم يكفِ يختبر من raw_proxies.
    3. يضمن أن first_proxy في المقدمة.
    4. بعد الانتهاء يطلق تعبئة الاحتياطي من جديد.
    """
    try:
        # 1. أخذ ما يكفي من الاحتياطي أولاً
        reserve_taken = _take_from_reserve(PROXIES_PER_ACCOUNT)
        alive = list(reserve_taken)

        # 2. إذا لم يكفِ الاحتياطي، اختبر من raw_proxies
        if len(alive) < PROXIES_PER_ACCOUNT and raw_proxies:
            # استبعد ما أخذناه من الاحتياطي
            reserve_addrs = {p["address"] for p in alive}
            candidates = [p for p in raw_proxies if p not in reserve_addrs]
            needed_extra = (PROXIES_PER_ACCOUNT - len(alive)) * 8
            sample_size = min(len(candidates), needed_extra)
            if sample_size > 0:
                sample = random.sample(candidates, sample_size)
                print(f"[PROXY-BG] {email_lower}: اختبار {sample_size} إضافي (الاحتياطي غير كافٍ)...")
                extra_alive = test_proxies_batch(sample, max_workers=15)
                alive.extend(extra_alive)

        # 3. تأكد من أن first_proxy في المقدمة
        if first_proxy:
            addr = first_proxy["address"]
            alive = [p for p in alive if p["address"] != addr]
            alive.insert(0, first_proxy)

        # 4. فرز حسب السرعة وأخذ أفضل 20
        alive.sort(key=lambda x: x["latency"])
        account_proxies = alive[:PROXIES_PER_ACCOUNT]
        for i, p in enumerate(account_proxies):
            p["stability"] = max(50, 100 - i * 2)

        with proxy_store_lock:
            dynamic_proxy_store[email_lower] = {
                "proxies": account_proxies,
                "current_index": 0,
                "last_updated": time.time()
            }
        enqueue_db_save(save_proxies_to_db, account_proxies, email_lower)
        fast = sum(1 for p in account_proxies if p.get("latency", 9) <= 1.5)
        print(f"[PROXY-BG] {email_lower}: {len(account_proxies)} بروكسي جاهز ({fast} سريع جداً)")

        # 5. تعبئة الاحتياطي في الخلفية لتجهيز الحساب القادم
        trigger_reserve_fill()

    except Exception as e:
        print(f"[PROXY-BG] خطأ: {e}")


def _ensure_proxy_for_account(email_lower, blocking=False, timeout=30):
    """
    للاستخدام الخلفي الدوري فقط (تحديث كل 30 دقيقة).
    لتسجيل الدخول استخدم: get_first_alive_proxy + _background_fill_proxies
    """
    if email_lower in EXEMPT_ACCOUNTS:
        return
    with proxy_store_lock:
        already_has = email_lower in dynamic_proxy_store and bool(dynamic_proxy_store[email_lower].get("proxies"))
    if already_has:
        return

    print(f"[PROXY] _ensure (دوري) للحساب: {email_lower}")

    def _do_fetch():
        try:
            raw_proxies = fetch_raw_proxies()
            if not raw_proxies:
                return
            first = get_first_alive_proxy(raw_proxies, batch_size=100, max_wait=20)
            if first:
                with proxy_store_lock:
                    dynamic_proxy_store[email_lower] = {
                        "proxies": [first],
                        "current_index": 0,
                        "last_updated": time.time()
                    }
            _background_fill_proxies(email_lower, raw_proxies, first)
        except Exception as e:
            print(f"[PROXY] خطأ في _ensure: {e}")

    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    if blocking:
        t.join(timeout=timeout)

# ==========================================
# إنشاء الجلسات مع دعم البروكسي الكامل
# ==========================================
def create_session(email=None):
    """
    إنشاء جلسة HTTP مع ربط البروكسي على مستوى الحساب بالكامل.
    - الحسابات المستثناة: بروكسيات ثابتة مع مصادقة.
    - باقي الحسابات: بروكسي ديناميكي حصري بدون مصادقة.
    """
    session = requests.Session()
    if not email:
        return session

    email_lower = email.lower().strip()

    if email_lower in EXEMPT_ACCOUNTS:
        # نظام البروكسي الثابت للحسابين المستثنيين
        fast_proxy = get_fastest_proxy_exempt(email_lower)
        if fast_proxy:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{fast_proxy}"
            session.proxies = {"http": proxy_url, "https": proxy_url}
            print(f"[SESSION] {email_lower} → بروكسي ثابت: {fast_proxy}")
    else:
        # النظام الديناميكي
        proxy_addr = get_current_proxy_for_account(email_lower)
        if proxy_addr:
            session.proxies = {"http": proxy_addr, "https": proxy_addr}
            session._dynamic_proxy_email = email_lower
            session._dynamic_proxy_addr = proxy_addr
            print(f"[SESSION] {email_lower} → بروكسي ديناميكي: {proxy_addr}")

    return session

def _try_login_with_proxy(username, password, proxy_addr, email_lower):
    """محاولة تسجيل دخول واحدة مع بروكسي محدد. تُرجع session أو None أو 'CAPTCHA' أو 'BLOCKED'."""
    try:
        sess = requests.Session()
        if proxy_addr:
            sess.proxies = {"http": proxy_addr, "https": proxy_addr}
            sess._dynamic_proxy_email = email_lower
            sess._dynamic_proxy_addr = proxy_addr
        login_data = {
            "signin[username]": username,
            "signin[password]": password,
            "signin[remember]": "1",
            "signin[refer_url]": "@office_initial"
        }
        sess.get(BASE_URL, headers=HEADERS, timeout=8)
        lr = sess.post(LOGIN_URL, data=login_data, headers=HEADERS, timeout=8)
        if lr.status_code == 200:
            page_state = detect_page_state(lr.text)
            if page_state == "blocked":
                threading.Thread(
                    target=handle_blocked_account, args=(username,), daemon=True
                ).start()
                return "BLOCKED"
            if page_state == "captcha":
                threading.Thread(
                    target=handle_captcha_detected,
                    args=(username, "أثناء تسجيل الدخول"),
                    daemon=True
                ).start()
                return "CAPTCHA"
            if "Выход" in lr.text:
                return sess
    except Exception:
        pass
    return None


def get_authenticated_session(username, password, use_proxy=True):
    """
    نظام تسجيل الدخول المُحسَّن:
    1. إذا توجد جلسة محفوظة صالحة → تُستخدم مباشرة.
    2. إذا توجد بروكسيات محفوظة → يُستخدم الأسرع.
    3. إذا لم تتوجد بروكسيات (حساب جديد) → يجلب ويختبر دفعة كبيرة بالتوازي،
       يُسجَّل الدخول بأول بروكسي يعمل فوراً، ثم يكمل جمع الـ20 في الخلفية.
    """
    email_lower = username.lower().strip()

    # ── 1: جلسة محفوظة ──
    with auth_sessions_lock:
        cached_session = user_auth_sessions.get(email_lower)
    if cached_session:
        try:
            test_r = cached_session.get(BASE_URL, headers=HEADERS, timeout=8)
            page_state = detect_page_state(test_r.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
                with auth_sessions_lock:
                    user_auth_sessions.pop(email_lower, None)
                return None
            if page_state == "captcha":
                threading.Thread(
                    target=handle_captcha_detected,
                    args=(username, "أثناء التحقق من الجلسة المحفوظة"),
                    daemon=True
                ).start()
                with auth_sessions_lock:
                    user_auth_sessions.pop(email_lower, None)
                return None
            if "Выход" in test_r.text:
                return cached_session
        except Exception:
            pass
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)

    # ── حسابات استثنائية: بروكسي ثابت ──
    if email_lower in EXEMPT_ACCOUNTS:
        session = create_session(email=username)
        login_data = {
            "signin[username]": username,
            "signin[password]": password,
            "signin[remember]": "1",
            "signin[refer_url]": "@office_initial"
        }
        try:
            session.get(BASE_URL, headers=HEADERS, timeout=10)
            lr = session.post(LOGIN_URL, data=login_data, headers=HEADERS, timeout=10)
            if lr.status_code == 200 and "Выход" in lr.text:
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = session
                return session
        except Exception:
            pass
        return None

    # ── 2: توجد بروكسيات محفوظة → الأسرع منها ──
    with proxy_store_lock:
        store = dynamic_proxy_store.get(email_lower)
        has_proxies = store and bool(store.get("proxies"))

    if has_proxies:
        with proxy_store_lock:
            alive = [p for p in store["proxies"] if p.get("status", "active") != "dead"]
        if alive:
            alive.sort(key=lambda x: x.get("latency", 999))
            # محاولة مع الأسرع، ثم fallover للتالي
            for proxy_info in alive[:3]:
                sess = _try_login_with_proxy(username, password, proxy_info["address"], email_lower)
                if sess and sess not in ("BLOCKED", "CAPTCHA"):
                    with auth_sessions_lock:
                        user_auth_sessions[email_lower] = sess
                    return sess
                elif sess in ("BLOCKED", "CAPTCHA"):
                    return None  # تم التعامل مع الحالة داخل _try_login_with_proxy
                else:
                    # ضع هذا البروكسي كـ dead
                    proxy_info["status"] = "dead"
                    enqueue_db_save(mark_proxy_dead_in_db, proxy_info["address"])
        # كل البروكسيات المحفوظة فاشلة → احذفها وابدأ من جديد
        with proxy_store_lock:
            dynamic_proxy_store.pop(email_lower, None)

    # ── 3: حساب جديد أو بروكسيات فاشلة → أولاً من الاحتياطي، ثم الجلب ──
    print(f"[SESSION] {email_lower}: محاولة تسجيل الدخول...")

    # أولاً: جرب أخذ بروكسي من الاحتياطي (فوري بدون جلب)
    first_proxy = None
    raw_proxies = []

    with reserve_pool_lock:
        reserve_alive = [p for p in proxy_reserve_pool["proxies"] if p.get("status", "active") != "dead"]

    if reserve_alive:
        first_proxy = reserve_alive[0]
        # احذفه من الاحتياطي مؤقتاً
        with reserve_pool_lock:
            proxy_reserve_pool["proxies"] = [p for p in proxy_reserve_pool["proxies"]
                                              if p["address"] != first_proxy["address"]]
        print(f"[SESSION] {email_lower}: استخدام بروكسي من الاحتياطي: {first_proxy['address']} ({first_proxy.get('latency','?')}s)")
    else:
        # لا احتياطي — جلب ومعالجة سريعة
        print(f"[SESSION] {email_lower}: الاحتياطي فارغ — جلب بروكسيات جديدة...")
        raw_proxies = fetch_raw_proxies()
        if not raw_proxies:
            print(f"[SESSION] {email_lower}: فشل جلب البروكسيات الخام — تسجيل مباشر")
            sess = _try_login_with_proxy(username, password, None, email_lower)
            if sess and sess not in ("BLOCKED", "CAPTCHA"):
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = sess
            return sess if sess not in ("BLOCKED", "CAPTCHA") else None
        first_proxy = get_first_alive_proxy(raw_proxies, batch_size=150, max_wait=25)

    if not first_proxy:
        print(f"[SESSION] {email_lower}: لم يُعثر على بروكسي — تسجيل مباشر")
        sess = _try_login_with_proxy(username, password, None, email_lower)
        if sess and sess not in ("BLOCKED", "CAPTCHA"):
            with auth_sessions_lock:
                user_auth_sessions[email_lower] = sess
        return sess if sess not in ("BLOCKED", "CAPTCHA") else None

    # حفظ أول بروكسي مؤقتاً في المخزن
    with proxy_store_lock:
        dynamic_proxy_store[email_lower] = {
            "proxies": [first_proxy],
            "current_index": 0,
            "last_updated": time.time()
        }

    print(f"[SESSION] {email_lower}: تسجيل الدخول بأول بروكسي سريع: {first_proxy['address']} ({first_proxy.get('latency', '?')}s)")
    sess = _try_login_with_proxy(username, password, first_proxy["address"], email_lower)

    if sess and sess not in ("BLOCKED", "CAPTCHA"):
        with auth_sessions_lock:
            user_auth_sessions[email_lower] = sess
        # في الخلفية: جمع أفضل 20 بروكسي من الاحتياطي + raw_proxies
        threading.Thread(
            target=_background_fill_proxies,
            args=(email_lower, raw_proxies, first_proxy),
            daemon=True
        ).start()
        return sess

    if sess in ("BLOCKED", "CAPTCHA"):
        return None  # تم التعامل مع الحالة داخل _try_login_with_proxy

    # أول بروكسي فشل في تسجيل الدخول → جرب التاليين من الاحتياطي
    print(f"[SESSION] {email_lower}: فشل أول بروكسي في تسجيل الدخول، محاولة بالاحتياطي...")
    first_proxy["status"] = "dead"

    # جرب ثاني بروكسي من الاحتياطي
    backup_proxy = None
    with reserve_pool_lock:
        reserve_now = [p for p in proxy_reserve_pool["proxies"] if p.get("status", "active") != "dead"]
        if reserve_now:
            backup_proxy = reserve_now[0]
            proxy_reserve_pool["proxies"] = reserve_now[1:]

    if not backup_proxy and raw_proxies:
        backup_proxy = get_first_alive_proxy(
            [p for p in raw_proxies if p != first_proxy["address"]],
            batch_size=100, max_wait=20
        )

    if backup_proxy:
        with proxy_store_lock:
            dynamic_proxy_store[email_lower] = {
                "proxies": [backup_proxy],
                "current_index": 0,
                "last_updated": time.time()
            }
        sess2 = _try_login_with_proxy(username, password, backup_proxy["address"], email_lower)
        if sess2 and sess2 not in ("BLOCKED", "CAPTCHA"):
            with auth_sessions_lock:
                user_auth_sessions[email_lower] = sess2
            threading.Thread(
                target=_background_fill_proxies,
                args=(email_lower, raw_proxies, backup_proxy),
                daemon=True
            ).start()
            return sess2
        if sess2 in ("BLOCKED", "CAPTCHA"):
            return None

    # كل المحاولات فشلت
    print(f"[SESSION] {email_lower}: كل المحاولات فشلت")
    # طلب تعبئة احتياطي في الخلفية للمحاولة القادمة
    trigger_reserve_fill()
    return None

# ==========================================
# استخراج البيانات والتنفيذ التلقائي
# ==========================================
def extract_real_price_and_description(session, task_page_url):
    try:
        response = session.get(task_page_url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            desc_text = ""
            desc_div = soup.find("div", style=re.compile(r"overflow-wrap:\s*break-word"))
            if desc_div:
                desc_text = desc_div.get_text(strip=True)
            else:
                for td in soup.find_all("td", align="left"):
                    if td.find("div"):
                        desc_text = td.find("div").get_text(strip=True)
                        break

            price_val = None
            info_table = soup.find("table", id="order-info-requests")
            if info_table:
                rows = info_table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2 and "Оплата" in cells[0].get_text():
                        price_td = cells[1] if len(cells) > 1 else None
                        if price_td:
                            price_text = price_td.get_text(strip=True)
                            price_match = re.search(r"([\d\.,]+)", price_text)
                            if price_match:
                                price_val = float(price_match.group(1).replace(",", "."))
            if price_val is None:
                page_text = soup.get_text()
                pay_match = re.search(r"Оплата\s*([\d\.,]+)", page_text, re.IGNORECASE)
                if pay_match:
                    price_val = float(pay_match.group(1).replace(",", "."))

            return price_val, desc_text
    except Exception:
        pass
    return None, ""

def _fetch_task_details_unified(session, task_page_url):
    """
    ⚡ دالة موحدة: تجلب صفحة المهمة مرة واحدة فقط وتستخرج منها:
      - السعر الحقيقي
      - الوصف
      - مدة التنفيذ
    بدلاً من طلبَين منفصلَين → طلب واحد فقط لكل مهمة.
    """
    try:
        response = session.get(task_page_url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None, "", "2 часа"
        soup = BeautifulSoup(response.text, "html.parser")

        # ── استخراج الوصف ──
        desc_text = ""
        desc_div = soup.find("div", style=re.compile(r"overflow-wrap:\s*break-word"))
        if desc_div:
            desc_text = desc_div.get_text(strip=True)
        else:
            for td in soup.find_all("td", align="left"):
                if td.find("div"):
                    desc_text = td.find("div").get_text(strip=True)
                    break

        # ── استخراج السعر ──
        price_val = None
        info_table = soup.find("table", id="order-info-requests")
        if info_table:
            for row in info_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2 and "Оплата" in cells[0].get_text():
                    price_text = cells[1].get_text(strip=True)
                    price_match = re.search(r"([\d\.,]+)", price_text)
                    if price_match:
                        price_val = float(price_match.group(1).replace(",", "."))
                        break
        if price_val is None:
            pay_match = re.search(r"Оплата\s*([\d\.,]+)", soup.get_text(), re.IGNORECASE)
            if pay_match:
                price_val = float(pay_match.group(1).replace(",", "."))

        # ── استخراج مدة التنفيذ ──
        raw_duration = "2 часа"
        for td in soup.find_all("td"):
            if "Время на выполнение" in td.get_text():
                next_td = td.find_next_sibling("td")
                if next_td:
                    raw_duration = next_td.get_text(strip=True)
                    break
        if raw_duration == "2 часа":
            time_match = re.search(r"Время на выполнение\s*(.*)", soup.get_text())
            if time_match:
                raw_duration = time_match.group(1).strip().split("\n")[0]

        return price_val, desc_text, raw_duration
    except Exception:
        return None, "", "2 часа"

def submit_task_proof_automatically(session, execute_page_url, work_url_val, proof_msg_val):
    try:
        res = session.get(execute_page_url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            form = soup.find("form", action=re.compile(r"addRequest"))
            if form:
                post_action_url = f"{BASE_URL}/publisher-requests-socio/addRequest"
                if form.get('action'):
                    act = form.get('action')
                    post_action_url = act if act.startswith("http") else BASE_URL + act

                post_data = {}
                for hidden_input in form.find_all("input", type="hidden"):
                    if hidden_input.get("name"):
                        post_data[hidden_input.get("name")] = hidden_input.get("value", "")

                post_data["url[]"] = str(work_url_val) if work_url_val else ""
                post_data["msg"] = str(proof_msg_val)

                final_res = session.post(post_action_url, data=post_data, headers=HEADERS, timeout=10)
                if final_res.status_code == 200:
                    return True
    except Exception:
        pass
    return False

def get_platform_from_url(url):
    """استخراج اسم المنصة من رابط المهمة"""
    url_lower = url.lower()
    platforms = {
        "youtube": "🎥 YouTube",
        "vkontakte": "💙 VK",
        "vk": "💙 VK",
        "telegram": "✈️ Telegram",
        "instagram": "📸 Instagram",
        "tiktok": "🎵 TikTok",
        "twitter": "🐦 Twitter",
        "facebook": "👤 Facebook",
        "google": "🔍 Google",
        "yandex": "🔍 Yandex",
        "ok": "🟠 OK",
        "odnoklassniki": "🟠 OK",
        "twitch": "🟣 Twitch",
        "discord": "💬 Discord",
        "reddit": "🟥 Reddit",
    }
    for key, name in platforms.items():
        if f"/{key}/" in url_lower or f"/{key}" == url_lower[-len(key)-1:]:
            return name
    return "🌐 أخرى"

def extract_confirmed_tasks(session):
    tasks = []
    try:
        r = session.get(CONFIRMED_URL, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return tasks, "فشل تحميل الصفحة"

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", id="publisher-requests")
        if not table:
            return tasks, "لم يتم العثور على جدول المهام"

        rows = table.find_all("tr")
        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 7:
                    continue

                time_cell = cells[1]
                time_remaining = re.sub(r'\s+', ' ', time_cell.get_text(strip=True)).strip()
                if not time_remaining:
                    time_remaining = "غير محدد"

                task_cell = cells[3]
                task_name = ""
                task_link = ""
                task_id = ""
                original_task_url = ""
                link_tag = task_cell.find("a")
                if link_tag:
                    task_name = link_tag.get_text(strip=True)
                    task_link = link_tag.get("href", "")
                    if task_link and not task_link.startswith("http"):
                        task_link = BASE_URL + task_link
                    original_task_url = task_link
                    if task_link and "?ok=1" not in task_link:
                        task_link += "?ok=1" if "?" not in task_link else "&ok=1"
                    id_match = re.search(r'/request/(\d+)/', task_link)
                    if id_match:
                        task_id = id_match.group(1)

                # استخراج المنصة من رابط المهمة الأصلي
                platform = get_platform_from_url(original_task_url) if original_task_url else "🌐 أخرى"

                price_cell = cells[5]
                price = price_cell.get_text(strip=True).replace("\xa0", " ")

                report_cell = cells[6]
                report_link = ""
                link_tag = report_cell.find("a")
                if link_tag:
                    report_link = link_tag.get("href", "")
                    if report_link and not report_link.startswith("http"):
                        report_link = BASE_URL + report_link

                if task_name:
                    tasks.append({
                        "name": task_name, "task_id": task_id,
                        "task_link": task_link, "report_link": report_link,
                        "time_remaining": time_remaining, "price": price,
                        "platform": platform, "original_url": original_task_url
                    })
            except Exception:
                continue

        return tasks, "SUCCESS"
    except Exception as e:
        return tasks, f"خطأ: {str(e)}"

def get_task_full_description(session, task_link):
    try:
        r = session.get(task_link, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        task_name = ""
        name_td = soup.find("td", string="Название")
        if name_td:
            name_link = name_td.find_next("td").find("a")
            if name_link:
                task_name = name_link.get_text(strip=True)

        description_html = ""
        description_text = ""
        what_td = soup.find("td", string="Что делать")
        if what_td:
            desc_td = what_td.find_next("td")
            if desc_td:
                desc_div = desc_td.find("div", style=re.compile(r"overflow-wrap"))
                if desc_div:
                    description_html = str(desc_div)
                    description_text = desc_div.get_text(separator="\n", strip=True)

        form_action = ""
        form = soup.find("form", attrs={"name": "message_form"})
        if form:
            form_action = form.get("action", "")

        return {
            "name": task_name,
            "description_html": description_html,
            "description_text": description_text,
            "form_action": form_action
        }
    except Exception:
        return None

def search_text_in_description(description_html, description_text, search_keyword):
    if not search_keyword or not search_keyword.strip():
        return False
    search_lower = search_keyword.strip().lower()
    if description_text and search_lower in description_text.lower():
        return True
    if description_html and search_lower in description_html.lower():
        return True
    return False

def submit_task_report(session, form_action, work_url, proof_msg):
    try:
        if not form_action.startswith("http"):
            form_action = BASE_URL + form_action
        post_data = {
            "request[status]": "completed",
            "request[url]": str(work_url) if work_url else "",
            "request[message]": str(proof_msg)
        }
        r = session.post(form_action, data=post_data, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

# ==========================================
# 💸 نظام السحب
# ==========================================
WITHDRAWAL_URL = "https://forumok.com/billing/withdrawal"
BILLING_PROFILE_URL = "https://forumok.com/profile/billing"

def fetch_withdrawal_page(session):
    """
    جلب صفحة السحب وتحليلها.
    يُرجع dict يحتوي على:
      - status: 'ok' | 'restricted_10days' | 'error'
      - balance: float  (الرصيد المتاح)
      - wallet: str     (عنوان المحفظة الحالي)
      - pay_system: str (نظام الدفع)
      - csrf_token: str
      - user_id: str
    """
    try:
        r = session.get(WITHDRAWAL_URL, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return {"status": "error", "msg": f"فشل تحميل الصفحة ({r.status_code})"}
        soup = BeautifulSoup(r.text, "html.parser")

        # فحص قيد 10 أيام
        notification = soup.find("div", class_="notification")
        if notification and "10" in notification.get_text():
            return {"status": "restricted_10days"}

        # جلب الرصيد من الصفحة الحالية أو من صفحة البحث
        balance_val = 0.0
        page_text = soup.get_text()
        bal_match = re.search(r"Доступно:\s*([\d.,\s]+)\s*р\.", page_text)
        if bal_match:
            raw = bal_match.group(1).strip().replace(" ", "").replace(",", ".")
            try:
                balance_val = float(raw)
            except Exception:
                balance_val = 0.0

        # جلب نظام الدفع + المحفظة من نص الصفحة
        pay_system = ""
        wallet = ""
        ps_td = soup.find("td", string=re.compile(r"Платежная система", re.I))
        if ps_td:
            val_td = ps_td.find_next_sibling("td")
            if val_td:
                pay_system = val_td.get_text(strip=True)
        req_td = soup.find("td", string=re.compile(r"Реквизиты", re.I))
        if req_td:
            val_td = req_td.find_next_sibling("td")
            if val_td:
                wallet = val_td.get_text(strip=True).split("\n")[0].strip()

        # CSRF + user_id
        csrf_input = soup.find("input", {"id": "withdrawal__csrf_token"})
        csrf_token = csrf_input["value"] if csrf_input else ""
        uid_input = soup.find("input", {"id": "withdrawal_user_id"})
        user_id = uid_input["value"] if uid_input else ""

        return {
            "status": "ok",
            "balance": balance_val,
            "wallet": wallet,
            "pay_system": pay_system,
            "csrf_token": csrf_token,
            "user_id": user_id
        }
    except Exception as e:
        return {"status": "error", "msg": str(e)}

def fetch_billing_profile(session):
    """
    جلب صفحة إعدادات البنك (المحفظة + نظام الدفع).
    يُرجع dict: { pay_system, wallet, csrf_token, user_id }
    """
    try:
        r = session.get(BILLING_PROFILE_URL, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        pay_system_select = soup.find("select", {"id": "sf_guard_user_Profile_pay_system"})
        pay_system = ""
        if pay_system_select:
            selected = pay_system_select.find("option", selected=True)
            if selected:
                pay_system = selected.get_text(strip=True)

        wallet_textarea = soup.find("textarea", {"id": "sf_guard_user_Profile_pay_system_requisites"})
        wallet = wallet_textarea.get_text(strip=True) if wallet_textarea else ""

        csrf_input = soup.find("input", {"id": "sf_guard_user__csrf_token"})
        csrf_token = csrf_input["value"] if csrf_input else ""
        uid_input = soup.find("input", {"id": "sf_guard_user_id"})
        user_id = uid_input["value"] if uid_input else ""

        return {
            "pay_system": pay_system,
            "wallet": wallet,
            "csrf_token": csrf_token,
            "user_id": user_id
        }
    except Exception:
        return None

def update_billing_profile(session, pay_system_val, wallet_val, csrf_token, user_id):
    """
    تحديث عنوان المحفظة على الموقع.
    يُرجع True عند النجاح.
    """
    try:
        post_data = {
            "sf_method": "put",
            "sf_guard_user[id]": user_id,
            "sf_guard_user[_csrf_token]": csrf_token,
            "sf_guard_user[Profile][pay_system]": pay_system_val,
            "sf_guard_user[Profile][pay_system_requisites]": wallet_val
        }
        r = session.post(BILLING_PROFILE_URL, data=post_data, headers=HEADERS, timeout=12)
        return r.status_code == 200
    except Exception:
        return False

def get_withdraw_menu(balance=None, wallet=None, pay_system=None):
    """قائمة زر السحب الرئيسية — زر تعديل المحفظة يظهر دائماً"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💸 تنفيذ سحب الآن", callback_data="withdraw_do"))
    # زر تعديل/إضافة المحفظة يظهر دائماً بغض النظر عن الرصيد أو القيد
    if wallet and wallet.strip() and wallet.strip() != "غير محدد":
        markup.add(types.InlineKeyboardButton("✏️ تعديل عنوان المحفظة", callback_data="withdraw_edit_wallet"))
    else:
        markup.add(types.InlineKeyboardButton("➕ إضافة عنوان المحفظة", callback_data="withdraw_edit_wallet"))
    markup.add(types.InlineKeyboardButton("🔄 تحديث البيانات", callback_data="withdraw_menu"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main"))
    return markup

def get_withdraw_menu_limited(wallet=None):
    """قائمة السحب عند وجود قيد (رصيد منخفض أو قيد 10 أيام) — يظهر زر تعديل المحفظة فقط"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    if wallet and wallet.strip() and wallet.strip() != "غير محدد":
        markup.add(types.InlineKeyboardButton("✏️ تعديل عنوان المحفظة", callback_data="withdraw_edit_wallet"))
    else:
        markup.add(types.InlineKeyboardButton("➕ إضافة عنوان المحفظة", callback_data="withdraw_edit_wallet"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main"))
    return markup

def execute_confirmed_tasks_manually(chat_id, creds):
    session = get_authenticated_session(creds['email'], creds['password'])
    if not session:
        return "❌ فشل تجديد الجلسة.", 0

    tasks, status = extract_confirmed_tasks(session)
    if status != "SUCCESS" or not tasks:
        return f"📋 لا توجد مهام مؤكدة." if status == "SUCCESS" else f"❌ {status}", 0

    templates = cloud_get_auto_tasks(chat_id)
    if not templates:
        return "⚠️ لا توجد البقات. أضف باقة أولاً.", 0

    executed = 0
    results = []
    for task in tasks:
        task_info = get_task_full_description(session, task['task_link'])
        if not task_info:
            continue
        for tmpl in templates:
            if search_text_in_description(task_info['description_html'], task_info['description_text'], tmpl['keyword']):
                success = submit_task_report(session, task_info['form_action'], tmpl.get('work_url', ''), tmpl.get('proof_msg', ''))
                if success:
                    executed += 1
                    results.append(f"✅ {task['name']} | 💰 {task['price']}")
                else:
                    results.append(f"❌ {task['name']} | فشل الإرسال")
                time.sleep(10)
                break

    if executed > 0:
        return f"📊 **تم تنفيذ {executed} مهمة**\n\n" + "\n".join(results[:10]), executed
    else:
        return f"⚠️ لم يتم العثور على مهام تطابق البقات.\n\n📋 البقات المتاحة:\n" + "\n".join([f"🔍 {t['keyword'][:50]}" for t in templates]), 0

# ==========================================
# ترجمة الوقت وفحص الجداول
# ==========================================
def translate_and_parse_duration(duration_text):
    total_minutes = 0
    duration_text = duration_text.strip().lower()
    try:
        number_match = re.search(r"(\d+)", duration_text)
        if not number_match:
            return 120, "2 ساعات"
        number = int(number_match.group(1))

        if "день" in duration_text or "дня" in duration_text or "дней" in duration_text:
            total_minutes = number * 24 * 60
        elif "час" in duration_text or "часа" in duration_text or "часов" in duration_text:
            total_minutes = number * 60
        elif "минут" in duration_text or "минуты" in duration_text or "минуту" in duration_text:
            total_minutes = number
        elif "неделя" in duration_text or "недели" in duration_text or "недель" in duration_text:
            total_minutes = number * 7 * 24 * 60
        else:
            total_minutes = number * 60

        if "день" in duration_text or "дня" in duration_text or "дней" in duration_text:
            translated_text = "1 يوم" if number == 1 else f"{number} أيام" if 2 <= number <= 10 else f"{number} يوم"
        elif "час" in duration_text or "часа" in duration_text or "часов" in duration_text:
            translated_text = "1 ساعة" if number == 1 else f"{number} ساعات" if 2 <= number <= 10 else f"{number} ساعة"
        elif "минут" in duration_text or "минуты" in duration_text or "минуту" in duration_text:
            translated_text = "1 دقيقة" if number == 1 else f"{number} دقائق" if 2 <= number <= 10 else f"{number} دقيقة"
        elif "неделя" in duration_text or "недели" in duration_text or "недель" in duration_text:
            translated_text = "1 أسبوع" if number == 1 else f"{number} أسابيع" if 2 <= number <= 10 else f"{number} أسبوع"
        else:
            translated_text = f"{number} ساعات"
    except Exception:
        return 120, "2 ساعات"
    return total_minutes, translated_text

def fetch_publisher_stats(session):
    stats = {"to_execute": "0", "on_check": "0", "completed": "0", "uncompleted": "0"}
    try:
        r = session.get(STATS_URL, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text()
            m = re.search(r"Выполнить\s+(\d+)", page_text)
            if m:
                stats["to_execute"] = m.group(1)
            m = re.search(r"На проверке\s+(\d+)", page_text)
            if m:
                stats["on_check"] = m.group(1)
            m = re.search(r"Выполнено\s+(\d+)", page_text)
            if m:
                stats["completed"] = m.group(1)
            m = re.search(r"Невыполненные\s+(\d+)", page_text)
            if m:
                stats["uncompleted"] = m.group(1)
    except Exception:
        pass
    return stats

def extract_task_duration(session, task_page_url):
    try:
        res = session.get(task_page_url, headers=HEADERS, timeout=7)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for td in soup.find_all("td"):
                if "Время на выполнение" in td.get_text():
                    next_td = td.find_next_sibling("td")
                    if next_td:
                        return next_td.get_text(strip=True)
            page_text = soup.get_text()
            time_match = re.search(r"Время на выполнение\s*(.*)", page_text)
            if time_match:
                return time_match.group(1).strip().split("\n")[0]
    except Exception:
        pass
    return "2 часа"

def get_site_data(username, password, chat_id):
    session = get_authenticated_session(username, password)
    if not session:
        return None, "AUTH_FAILED"
    try:
        r = session.get(TARGET_URL, headers=HEADERS, timeout=10)

        # ── كشف الحظر أو CAPTCHA ──
        page_state = detect_page_state(r.text)
        if page_state == "blocked":
            threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
            return None, "BLOCKED"
        if page_state == "captcha":
            threading.Thread(
                target=handle_captcha_detected,
                args=(username, "أثناء جلب المهام من الموقع"),
                daemon=True
            ).start()
            return None, "CAPTCHA"

        if "Выход" not in r.text:
            return None, "SESSION_EXPIRED"
        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(separator="\n")

        balance = "0.0"
        available_match = re.search(r"Доступно:\s*([\d.,\s]+)\s*р\.", page_text)
        if available_match:
            balance = available_match.group(1).strip()

        # ── جلب الإحصائيات والمهام بالتوازي ──
        stats_future = None
        raw_task_urls = []

        table = soup.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:
                if 'taken-list' in row.get('class', []):
                    continue
                if 'gray-list' in row.get('class', []):
                    continue
                cells = row.find_all("td")
                if len(cells) >= 3:
                    links = cells[-1].find_all("a", href=True)
                    if links:
                        task_page_url = links[0]['href'] if links[0]['href'].startswith("http") else BASE_URL + links[0]['href']
                        if "?ok=1" not in task_page_url:
                            task_page_url += "?ok=1" if "?" not in task_page_url else "&ok=1"
                        raw_task_urls.append(task_page_url)

        # ⚡ جلب تفاصيل جميع المهام + الإحصائيات بالتوازي الكامل
        tasks_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(raw_task_urls) + 1, 20)) as executor:
            # إطلاق طلب الإحصائيات بالتوازي مع طلبات المهام
            stats_future = executor.submit(fetch_publisher_stats, session)

            # إطلاق جميع طلبات المهام دفعة واحدة
            task_futures = {
                executor.submit(_fetch_task_details_unified, session, url): url
                for url in raw_task_urls
            }

            # جمع نتائج المهام
            task_results = {}
            for future in concurrent.futures.as_completed(task_futures):
                url = task_futures[future]
                try:
                    real_price, task_desc, raw_duration = future.result()
                    task_results[url] = (real_price, task_desc, raw_duration)
                except Exception:
                    task_results[url] = (None, "", "2 часа")

            # الحصول على الإحصائيات
            try:
                stats_data = stats_future.result(timeout=5)
            except Exception:
                stats_data = {"to_execute": "0", "on_check": "0", "completed": "0", "uncompleted": "0"}

        # ── بناء قائمة المهام بنفس الترتيب الأصلي ──
        for task_page_url in raw_task_urls:
            real_price, task_desc, raw_duration = task_results.get(task_page_url, (None, "", "2 часа"))
            if real_price is None:
                continue
            task_minutes, arabic_duration = translate_and_parse_duration(raw_duration)

            app_name = "منصة أخرى"
            for platform in ["yandex", "google", "telegram", "youtube", "vkontakte", "vk"]:
                if platform in task_page_url.lower():
                    app_name = "YouTube" if platform == "youtube" else "Telegram" if platform == "telegram" else "Yandex" if platform == "yandex" else "Google" if platform == "google" else "VKontakte"
                    break

            is_restricted = "غير مقيدة"
            restrictions_details = ""
            task_desc_check = task_desc.lower()
            if "россия" in task_desc_check or "russia" in task_desc_check or "только для рф" in task_desc_check:
                is_restricted = "مقيدة"
                restrictions_details = "روسيا"
            elif "гео" in task_desc_check or "страна" in task_desc_check:
                is_restricted = "مقيدة"
                restrictions_details = "محددة جغرافيًا"

            tasks_list.append({
                "price": f"{real_price:.2f}", "task_page": task_page_url,
                "duration": arabic_duration, "minutes": task_minutes,
                "description": task_desc, "app_name": app_name,
                "is_restricted": is_restricted, "restrictions": restrictions_details
            })

        user_numbered_tasks[chat_id] = tasks_list
        return {"balance": balance, "stats": stats_data, "tasks": tasks_list}, "SUCCESS"
    except Exception:
        return None, "ERROR"

def take_task_via_post(session, task_page_url):
    """
    اصطحاب مهمة مع التحقق الحقيقي من نجاح الاصطحاب.
    يتحقق من صفحة المهام المؤكدة بعد الاصطحاب للتأكد من أن المهمة موجودة فعلاً.
    """
    try:
        # ── استخراج order_id من الرابط للتحقق لاحقاً ──
        order_id_for_verify = None
        id_match = re.search(r"/order[_/](\d+)", task_page_url)
        if not id_match:
            id_match = re.search(r"/(\d+)/?$", task_page_url)
        if id_match:
            order_id_for_verify = id_match.group(1)

        response = session.get(task_page_url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return False

        soup = BeautifulSoup(response.text, "html.parser")

        # ── التحقق المبدئي: هل المهمة متاحة للاصطحاب؟ ──
        # إذا كان الرابط يُعيد توجيه لصفحة مختلفة أو يحتوي رسالة "لا توجد مهام" → مهمة وهمية
        page_text = soup.get_text()
        not_available_signals = [
            "нет заданий", "no tasks", "задание недоступно",
            "order not found", "not found", "404"
        ]
        for signal in not_available_signals:
            if signal in page_text.lower():
                print(f"[TAKE] المهمة غير متاحة: {signal}")
                return False

        form = soup.find("form", action=re.compile(r"batch|order_request"))
        if not form:
            # لا يوجد فورم = لا يوجد زر اصطحاب = المهمة غير موجودة أو مصطحبة سابقاً
            print(f"[TAKE] لا يوجد فورم اصطحاب في الصفحة: {task_page_url}")
            return False

        # ── تجهيز بيانات الفورم وإرسال طلب الاصطحاب ──
        post_action_url = f"{BASE_URL}/order_request_socio/batch"
        if form.get('action'):
            act = form.get('action')
            post_action_url = act if act.startswith("http") else BASE_URL + act

        post_data = {"batch_action": "batchConfirm"}
        for hidden_input in form.find_all("input", type="hidden"):
            if hidden_input.get("name"):
                post_data[hidden_input.get("name")] = hidden_input.get("value", "")

        account_checkboxes = form.find_all("input", class_="batch_checkbox")
        account_ids = [cb.get("value") for cb in account_checkboxes if cb.get("value")]
        if account_ids:
            post_data["ids[]"] = account_ids
        elif form.find("input", name="ids[]"):
            post_data["ids[]"] = [form.find("input", name="ids[]").get("value", "")]
        else:
            # لا يوجد ids → لا شيء يمكن اصطحابه
            print(f"[TAKE] لا يوجد ids في الفورم: {task_page_url}")
            return False

        res = session.post(post_action_url, data=post_data, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return False

        # ── التحقق الحقيقي: هل المهمة ظهرت في المهام المؤكدة؟ ──
        time.sleep(1.5)  # انتظار قصير حتى يُحدَّث السيرفر
        try:
            confirmed_r = session.get(CONFIRMED_URL, headers=HEADERS, timeout=10)
            if confirmed_r.status_code == 200:
                confirmed_soup = BeautifulSoup(confirmed_r.text, "html.parser")
                table = confirmed_soup.find("table", id="publisher-requests")
                if table:
                    rows = table.find_all("tr")
                    if rows and len(rows) > 1:
                        # ── طريقة 1: إذا عندنا order_id نتحقق منه مباشرة ──
                        if order_id_for_verify:
                            table_text = confirmed_r.text
                            if order_id_for_verify in table_text:
                                print(f"[TAKE] ✅ تحقق ناجح بـ order_id={order_id_for_verify}")
                                return True
                            # لم نجد الـ id → اصطحاب فاشل
                            print(f"[TAKE] ❌ order_id={order_id_for_verify} غير موجود في المؤكدة")
                            return False
                        else:
                            # ── طريقة 2: نتحقق من وجود صف جديد بمقارنة العدد ──
                            # إذا وصلنا هنا بدون order_id نعتمد على وجود صفوف فعلية
                            data_rows = [r for r in rows if r.find_all("td")]
                            if data_rows:
                                print(f"[TAKE] ✅ يوجد {len(data_rows)} مهمة في المؤكدة — اعتبار الاصطحاب ناجحاً")
                                return True
                            print(f"[TAKE] ❌ جدول المؤكدة فارغ بعد الاصطحاب")
                            return False
                    else:
                        print(f"[TAKE] ❌ جدول المؤكدة فارغ بعد الاصطحاب")
                        return False
                else:
                    # لا يوجد جدول مهام مؤكدة → الاصطحاب لم ينجح
                    print(f"[TAKE] ❌ لا يوجد جدول publisher-requests في صفحة المؤكدة")
                    return False
        except Exception as verify_err:
            print(f"[TAKE] تحذير: فشل التحقق من المؤكدة: {verify_err}")
            # في حالة فشل التحقق فقط → لا نُرسل إشعاراً كاذباً
            return False

    except Exception as e:
        print(f"[TAKE] خطأ عام: {e}")
        pass
    return False

# ==========================================
# 🔥 الواجهات الرسومية
# ==========================================
def get_auth_menu(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if chat_id:
        saved_accounts = get_saved_multi_accounts(chat_id)
        for i, acc in enumerate(saved_accounts, 1):
            email = acc['email']
            label = email.split('@')[0]
            markup.add(types.InlineKeyboardButton(f"⚡ الدخول المباشر: الحساب {i} ({label})", callback_data=f"switch_acc_{i-1}"))
    markup.add(types.InlineKeyboardButton("🔐 تسجيل الدخول بحساب جديد", callback_data="login_start"))
    return markup

def get_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)

    user_label = "غير محدد"
    if chat_id in user_data_store:
        email = user_data_store[chat_id].get('email', '')
        if "@" in email:
            user_label = email.split('@')[0]

    markup.add(types.InlineKeyboardButton(f"👤 الحساب الحالي: {user_label} 🔄", callback_data="switch_account_menu"))

    btn1 = types.InlineKeyboardButton("📋 عرض المهام المتاحة وتحديثها", callback_data="view_tasks")
    btn2 = types.InlineKeyboardButton("🎯 تصيد المهام (إشعارات/اصطحاب)", callback_data="hunt_menu")
    btn3 = types.InlineKeyboardButton("✅ تنفيذ المهام (البقات والأتمتة)", callback_data="exec_menu")
    btn4 = types.InlineKeyboardButton("🌐 حالة البروكسي الحالي", callback_data="proxy_status")
    btn_withdraw = types.InlineKeyboardButton("💸 سحب الرصيد", callback_data="withdraw_menu")
    btn5 = types.InlineKeyboardButton("🚪 تسجيل الخروج من الحساب الحالي", callback_data="logout")

    markup.add(btn1, btn2, btn3, btn4, btn_withdraw, btn5)
    return markup

def get_switch_account_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    saved_accounts = get_saved_multi_accounts(chat_id)
    current_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
    # الحسابات المُسجَّل خروجها لهذا المستخدم
    with logged_out_lock:
        lo_set = set(logged_out_accounts.get(chat_id, set()))
    for i, acc in enumerate(saved_accounts, 1):
        email = acc['email']
        label = email.split('@')[0]
        e = email.lower().strip()
        is_logged_out = e in lo_set
        is_active_display = (e == current_email)

        if is_active_display:
            # الحساب النشط حالياً في الواجهة
            status_icon = "✅"
        elif is_logged_out:
            # جلسته منتهية (تسجيل خروج حقيقي)
            status_icon = "💤"
        else:
            # حساب نشط في الخلفية (تبديل فقط)
            hunt_on = acct_auto_hunt_status.get(e, False)
            status_icon = "⚡" if hunt_on else "🔘"

        markup.add(types.InlineKeyboardButton(
            f"{status_icon} الحساب {i}: {label}",
            callback_data=f"switch_acc_{i-1}"
        ))
        # ملاحظة: أزرار البصمة مخفية من القائمة لكن وظيفتها محفوظة (show_fp_{i-1})
    markup.add(types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="add_new_account"))
    markup.add(types.InlineKeyboardButton("🗑️ حذف حساب", callback_data="delete_account_start"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main"))
    return markup

def get_hunting_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔔 إشعارات دورية", callback_data="notif_menu")
    btn2 = types.InlineKeyboardButton("⚡ اصطحاب للعمل", callback_data="take_work_menu")
    btn3 = types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
    markup.add(btn1, btn2)
    markup.add(btn3)
    return markup

def get_notifications_config_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    is_active = notify_status.get(chat_id, False)
    status_icon = "🟢" if is_active else "🔴"
    is_all_active = all_notify_status.get(chat_id, False)
    all_status_icon = "🟢" if is_all_active else "🔴"

    btn1 = types.InlineKeyboardButton("⚙️ تخصيص فترة التنبيه", callback_data="custom_notify")
    btn2 = types.InlineKeyboardButton(f"إشعارات دورية {status_icon}", callback_data="toggle_notify")
    btn_all = types.InlineKeyboardButton(f"إشعارات كلية {all_status_icon}", callback_data="toggle_all_notify")
    btn3 = types.InlineKeyboardButton("15 دقيقة", callback_data="set_notify_15")
    btn4 = types.InlineKeyboardButton("10 دقائق", callback_data="set_notify_10")
    btn5 = types.InlineKeyboardButton("🔙 رجوع", callback_data="back_hunt")

    markup.add(btn1, btn2)
    markup.add(btn_all)
    markup.add(btn3, btn4)
    markup.add(btn5)
    return markup

def get_take_work_menu(chat_id, email=""):
    markup = types.InlineKeyboardMarkup(row_width=1)
    current_mode = hunt_mode.get(chat_id, "GTE")
    is_active = auto_hunt_status.get(chat_id, False)
    icon_gt = "🟢" if (is_active and current_mode == "GT") else "🔴"
    icon_gte = "🟢" if (is_active and current_mode == "GTE") else "🔴"
    btn1 = types.InlineKeyboardButton(f"تفعيل > 2 ساعات قطعاً {icon_gt}", callback_data="toggle_gt")
    btn2 = types.InlineKeyboardButton(f"تفعيل >= 2 ساعات {icon_gte}", callback_data="toggle_gte")
    markup.add(btn1, btn2)
    btn3 = types.InlineKeyboardButton("👆 اصطحاب يدوي", callback_data="manual_take")
    btn4 = types.InlineKeyboardButton("🔙 رجوع", callback_data="back_hunt")
    markup.add(btn3, btn4)
    return markup

def get_task_execution_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=3)
    is_active = auto_execute_status.get(chat_id, False)
    if is_active:
        status_text = "🟢 تشغيل"
        status_callback = "exec_auto_off"
    else:
        status_text = "🔴 إيقاف"
        status_callback = "exec_auto_on"
    btn_status = types.InlineKeyboardButton(status_text, callback_data=status_callback)
    btn_add = types.InlineKeyboardButton("➕ إضافة الباقة", callback_data="exec_add_template")
    btn_browse = types.InlineKeyboardButton("📂 البقات", callback_data="exec_browse_templates")
    btn_share = types.InlineKeyboardButton("📧 مشاركة", callback_data="exec_share_by_chat_id")
    btn_manual = types.InlineKeyboardButton("⚡ تنفيذ يدوي", callback_data="exec_manual_now")
    current_interval = auto_execute_interval.get(chat_id, 5)
    btn_interval = types.InlineKeyboardButton(f"⏱️ {current_interval} دقيقة", callback_data="exec_set_interval")
    btn_back = types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
    markup.add(btn_status, btn_add, btn_browse)
    markup.add(btn_share, btn_manual, btn_interval)
    markup.add(btn_back)
    return markup

def get_templates_browse_menu(chat_id):
    templates = cloud_get_auto_tasks(chat_id)
    if not templates:
        return None
    markup = types.InlineKeyboardMarkup(row_width=1)
    for tmpl in templates:
        short_keyword = tmpl['keyword'][:30] + "..." if len(tmpl['keyword']) > 30 else tmpl['keyword']
        markup.add(types.InlineKeyboardButton(f"📌 {short_keyword}", callback_data=f"exec_view_{tmpl['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="exec_back_to_main"))
    return markup

def get_template_edit_menu(template_id, keyword, work_url, proof_msg):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ تعديل كلمة البحث", callback_data=f"exec_edit_keyword_{template_id}"),
        types.InlineKeyboardButton("🔗 تعديل رابط العمل", callback_data=f"exec_edit_url_{template_id}")
    )
    markup.add(
        types.InlineKeyboardButton("📝 تعديل نص الإثبات", callback_data=f"exec_edit_proof_{template_id}"),
        types.InlineKeyboardButton("🗑️ حذف الباقة", callback_data=f"exec_delete_{template_id}")
    )
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقوائم", callback_data="exec_browse_templates"))
    return markup

def build_proxy_status_text(email):
    """بناء نص معلومات البروكسي للعرض في الواجهة"""
    info = get_proxy_info_for_display(email)
    if not info:
        return "🌐 البروكسي: غير متصل\n"

    # بناء سطر الدولة مع العلم إن وُجد
    country_code = info.get("country_code", "")
    country_name = info.get("country", "Unknown")
    flag = ""
    if country_code and country_code != "??":
        # تحويل رمز الدولة إلى إيموجي علم
        try:
            flag = "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country_code.upper()) + " "
        except Exception:
            flag = ""
    country_display = f"{flag}{country_name}" if country_name != "Unknown" else "غير محدد"

    city = info.get("city", "")
    region = info.get("region", "")
    isp = info.get("isp", "")

    location_parts = [p for p in [city, region] if p]
    location_display = "، ".join(location_parts) if location_parts else "غير محدد"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🌐 **معلومات البروكسي الحالي**",
        f"📡 العنوان: `{info['address']}`",
        f"🖥️ عنوان IP: `{info['ip']}`",
        f"🗺️ الدولة: {country_display}",
        f"🏙️ المدينة: {location_display}",
    ]
    if isp:
        lines.append(f"🏢 المزود: {isp}")
    if info.get("latency") and info["latency"] < 900:
        lines.append(f"📶 زمن الاستجابة: {info['latency']}s")
    lines.append(f"⚡ الحالة: {info['speed']}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

# ==========================================
# 🔄 الخيط الخلفي الرئيسي (متعدد الحسابات)
# ==========================================
# مخازن الحالة الداخلية للخيط — مفتاحها (chat_id, email)
_bg_last_notify = {}
_bg_last_hunt = {}
_bg_last_exec = {}
_bg_last_take = {}   # (chat_id, email) -> timestamp

def _bg_process_one_account(chat_id, email, password, current_time):
    """
    معالجة حساب واحد في الخيط الخلفي:
    - إشعارات + اصطحاب تلقائي + تنفيذ دوري
    - يعمل بغض النظر عن الحساب النشط في الواجهة
    - محاط بحماية كاملة ضد الانهيار
    """
    try:
        _bg_process_one_account_inner(chat_id, email, password, current_time)
    except Exception as _bg_acc_err:
        print(f"[BG-ACC] خطأ في حساب {email}: {_bg_acc_err}")

def _bg_process_one_account_inner(chat_id, email, password, current_time):
    key = (chat_id, email)
    e = email.lower().strip()
    settings = get_email_settings(email)

    # ── الإشعارات ──
    do_notify = settings['notify_status'] or settings['all_notify_status']
    if do_notify:
        interval_secs = settings['notify_interval'] * 60
        if current_time - _bg_last_notify.get(key, 0) >= interval_secs:
            _bg_last_notify[key] = current_time
            data, status = get_site_data(email, password, chat_id)
            if status == "SUCCESS" and data and data['tasks']:
                user_ignored = ignored_tasks.get(chat_id, [])
                if chat_id not in sent_notifications:
                    sent_notifications[chat_id] = set()

                # مفتاح sent_notifications خاص بكل email داخل chat_id
                sn_key = f"{chat_id}_{e}"
                if sn_key not in sent_notifications:
                    sent_notifications[sn_key] = set()

                if settings['all_notify_status']:
                    filtered_tasks = [
                        t for t in data['tasks']
                        if t['task_page'] not in user_ignored
                        and t['task_page'] not in sent_notifications[sn_key]
                    ]
                    if filtered_tasks:
                        user_notify_tasks[chat_id] = filtered_tasks[:10]
                        for t in filtered_tasks[:10]:
                            sent_notifications[sn_key].add(t['task_page'])
                            task_title = t.get('description', '').split('\n')[0][:40].strip() or "مهمة تفاعلية جديدة"
                            active_label = user_data_store.get(chat_id, {}).get('email', '')
                            acc_tag = f"\n👤 الحساب: {e.split('@')[0]}" if active_label.lower().strip() != e else ""
                            msg = f"📢 مهمة جديدة متوفرة{acc_tag}\n\n"
                            msg += f"• اسم المهمة: {task_title}\n"
                            msg += f"• الثمن: {t['price']} روبل\n"
                            msg += f"• التطبيق: {t.get('app_name', 'منصة أخرى')}\n"
                            msg += f"• الحالة: {t.get('is_restricted', 'غير مقيدة')}\n"
                            if t.get('is_restricted') == "مقيدة" and t.get('restrictions'):
                                msg += f"• القيود: {t['restrictions']}\n"
                            msg += "\n━━━━━━━━━━"
                            inline_markup = types.InlineKeyboardMarkup()
                            inline_markup.add(types.InlineKeyboardButton(
                                text="🔕 تجاهل هذه المهمة",
                                callback_data=f"ign_specific_{len(sent_notifications[sn_key])}_{t['task_page'][:50]}"
                            ))
                            try:
                                bot.send_message(chat_id, msg, reply_markup=inline_markup)
                                time.sleep(1)
                            except Exception:
                                pass

                elif settings['notify_status']:
                    filtered_tasks = [t for t in data['tasks'] if t['task_page'] not in user_ignored]
                    if filtered_tasks:
                        user_notify_tasks[chat_id] = filtered_tasks[:5]
                        active_label = user_data_store.get(chat_id, {}).get('email', '')
                        acc_tag = f"\n👤 الحساب: {e.split('@')[0]}" if active_label.lower().strip() != e else ""
                        msg = f"📢 مهام جديدة متوفرة{acc_tag}:\n\n"
                        for idx, t in enumerate(filtered_tasks[:5], start=1):
                            msg += f"🔢 {idx} ➖ {t['price']} RUB | {t['duration']}\n"
                        inline_markup = types.InlineKeyboardMarkup()
                        inline_markup.add(types.InlineKeyboardButton(
                            text="🔕 تجاهل مهمة من القائمة", callback_data="ign_task"
                        ))
                        try:
                            bot.send_message(chat_id, msg, reply_markup=inline_markup)
                        except Exception:
                            pass

    # ── الاصطحاب التلقائي ──
    if settings['auto_hunt_status']:
        last_take = _bg_last_take.get(key, 0)
        if current_time - last_take >= TAKE_COOLDOWN:
            hunt_interval = 120
            if current_time - _bg_last_hunt.get(key, 0) >= hunt_interval:
                _bg_last_hunt[key] = current_time
                data, status = get_site_data(email, password, chat_id)
                if status == "SUCCESS" and data and data['tasks']:
                    mode = settings['hunt_mode']
                    for target_task in data['tasks']:
                        task_minutes = target_task.get('minutes', 120)
                        should_take = (mode == "GT" and task_minutes > 120) or (mode == "GTE" and task_minutes >= 120)
                        if should_take:
                            session = get_authenticated_session(email, password)
                            if session:
                                success = take_task_via_post(session, target_task['task_page'])
                                if success:
                                    _bg_last_take[key] = time.time()
                                    active_label = user_data_store.get(chat_id, {}).get('email', '')
                                    acc_tag = f"\n👤 الحساب: {e.split('@')[0]}" if active_label.lower().strip() != e else ""
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚡ تم اصطحاب مهمة تلقائياً!{acc_tag}\n"
                                            f"💰 السعر: {target_task['price']} RUB\n"
                                            f"⏱️ الوقت: {target_task['duration']}"
                                        )
                                    except Exception:
                                        pass

                                    if settings['auto_execute_status']:
                                        saved_templates = cloud_get_auto_tasks(chat_id)
                                        task_desc_lower = target_task.get('description', '').lower()
                                        task_url_str = target_task['task_page'].lower()
                                        for tmpl in saved_templates:
                                            kw = tmpl['keyword'].lower()
                                            if kw in task_desc_lower or kw in task_url_str:
                                                order_id_match = re.search(r"/(\d+)/", target_task['task_page'])
                                                if order_id_match:
                                                    ord_id = order_id_match.group(1)
                                                    execute_page_url = f"https://forumok.com/publisher-requests-socio/addRequest/order_id/{ord_id}?ok=1"
                                                    if submit_task_proof_automatically(session, execute_page_url, tmpl.get('work_url'), tmpl.get('proof_msg')):
                                                        try:
                                                            bot.send_message(chat_id, f"✅ تم إرسال التقرير بنجاح للمهمة المصطادة.")
                                                        except Exception:
                                                            pass
                                                break
                            break

    # ── التنفيذ الدوري ──
    if settings['auto_execute_status']:
        exec_interval_secs = settings['auto_execute_interval'] * 60
        if current_time - _bg_last_exec.get(key, 0) >= exec_interval_secs:
            _bg_last_exec[key] = current_time
            session = get_authenticated_session(email, password)
            if session:
                tasks, status = extract_confirmed_tasks(session)
                if status == "SUCCESS" and tasks:
                    templates = cloud_get_auto_tasks(chat_id)
                    if templates:
                        for task in tasks:
                            task_info = get_task_full_description(session, task['task_link'])
                            if task_info:
                                for tmpl in templates:
                                    if search_text_in_description(task_info['description_html'], task_info['description_text'], tmpl['keyword']):
                                        success = submit_task_report(session, task_info['form_action'], tmpl.get('work_url', ''), tmpl.get('proof_msg', ''))
                                        if success:
                                            active_label = user_data_store.get(chat_id, {}).get('email', '')
                                            acc_tag = f"\n👤 الحساب: {e.split('@')[0]}" if active_label.lower().strip() != e else ""
                                            try:
                                                bot.send_message(chat_id, f"🤖 [عمل دوري]: تم تنفيذ {task['name']}{acc_tag} | 💰 {task['price']}")
                                            except Exception:
                                                pass
                                        time.sleep(random.randint(30, 120))
                                        break


def global_background_worker():
    last_proxy_check = 0
    last_reserve_check = 0
    RESERVE_CHECK_INTERVAL = 5 * 60  # فحص الاحتياطي كل 5 دقائق
    consecutive_errors = 0

    while True:
        try:
            consecutive_errors = 0
            current_time = time.time()

            # ── تحديث البروكسيات الديناميكية كل 30 دقيقة ──
            if current_time - last_proxy_check >= PROXY_REFRESH_INTERVAL:
                last_proxy_check = current_time
                print("[BG] بدء تحديث البروكسيات الديناميكية...")
                threading.Thread(target=refresh_dynamic_proxies, daemon=True).start()

            # ── فحص صحة الاحتياطي كل 5 دقائق ──
            if current_time - last_reserve_check >= RESERVE_CHECK_INTERVAL:
                last_reserve_check = current_time
                needed = _needed_reserve_size()
                with reserve_pool_lock:
                    reserve_count = len([p for p in proxy_reserve_pool["proxies"]
                                         if p.get("status", "active") != "dead"])
                if reserve_count < needed:
                    print(f"[BG] الاحتياطي منخفض ({reserve_count}/{needed}) — تعبئة...")
                    trigger_reserve_fill()

            # ── المرور على جميع chat_ids وجميع حساباتهم النشطة ──
            with active_accounts_lock:
                snapshot = {cid: dict(accs) for cid, accs in active_accounts.items()}

            for chat_id, accounts in snapshot.items():
                for email_key, creds in accounts.items():
                    try:
                        _bg_process_one_account(chat_id, creds['email'], creds['password'], current_time)
                    except Exception as ex:
                        print(f"[BG] خطأ في معالجة {email_key}: {ex}")

        except Exception as e:
            consecutive_errors += 1
            print(f"[BG] خطأ عام (#{consecutive_errors}): {e}")
            sleep_time = min(60, 5 * consecutive_errors)
            time.sleep(sleep_time)
            continue
        time.sleep(5)

# ==========================================
# 📞 معالجة الضغطات (Callbacks)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_all_inline_callbacks(call):
    try:
        _handle_callback_inner(call)
    except Exception as _cb_err:
        print(f"[CALLBACK] خطأ غير متوقع: {_cb_err}")
        try:
            bot.answer_callback_query(call.id, "⚠️ حدث خطأ، حاول مرة أخرى.")
        except Exception:
            pass

def _handle_callback_inner(call):
    chat_id = call.message.chat.id
    data = call.data
    message_id = call.message.message_id

    if chat_id in user_sessions:
        step = user_sessions[chat_id].get('step', '')
        waiting_steps = [
            'WAITING_EMAIL', 'WAITING_PASSWORD',
            'WAITING_CUSTOM_INTERVAL', 'EXEC_SET_INTERVAL',
            'WAIT_IGN_NUM',
            'EXEC_ADD_KEYWORD', 'EXEC_ADD_URL', 'EXEC_ADD_PROOF',
            'EXEC_EDIT_KEYWORD', 'EXEC_EDIT_URL', 'EXEC_EDIT_PROOF',
            'EXEC_WAIT_SHARE_CHAT_ID',
            'WITHDRAW_WAIT_AMOUNT', 'WITHDRAW_EDIT_WALLET',
            'MANUAL_EXEC_FILL', 'MANUAL_EXEC_PROOF',
            'MANUAL_EXEC_NOW_FIELD1', 'MANUAL_EXEC_NOW_FIELD2',
            'MANUAL_EXEC_CUSTOM_URL', 'MANUAL_EXEC_CUSTOM_WORK_URL', 'MANUAL_EXEC_CUSTOM_PROOF',
            'WAITING_DELETE_ACCOUNT'
        ]
        if step in waiting_steps:
            del user_sessions[chat_id]

    elif data.startswith("show_fp_"):
        bot.answer_callback_query(call.id)
        idx = int(data.replace("show_fp_", ""))
        saved_accounts = get_saved_multi_accounts(chat_id)
        if 0 <= idx < len(saved_accounts):
            acc = saved_accounts[idx]
            fp = acc.get('fingerprint') or cloud_get_fingerprint_for_account(chat_id, acc['email'])
            label = acc['email'].split('@')[0]
            if fp:
                fp_msg = (
                    f"🔑 **بصمة الحساب: {label}**\n\n"
                    f"`{fp}`\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ هذه البصمة فريدة لهذا الحساب فقط\n"
                    f"🔒 لا تُشارك مع أي حساب آخر أبداً\n"
                    f"💾 محفوظة بشكل دائم في السحابة"
                )
            else:
                fp_msg = f"⚠️ لا توجد بصمة للحساب {label}، سجّل خروجاً ثم دخولاً مجدداً لإنشائها."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="switch_account_menu"))
            bot.send_message(chat_id, fp_msg, parse_mode="Markdown", reply_markup=markup)
        return

    elif data == "switch_account_menu":
        bot.answer_callback_query(call.id)
        msg_text = "🔄 **إدارة الحسابات**\nاختر حساباً للتبديل إليه أو قم بإضافة حساب جديد:\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_switch_account_menu(chat_id))
        return

    elif data == "add_new_account":
        bot.answer_callback_query(call.id)
        delete_transient_message(bot, chat_id)
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني للحساب الجديد:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}
        return

    elif data == "delete_account_start":
        bot.answer_callback_query(call.id)
        saved_accounts = get_saved_multi_accounts(chat_id)
        if not saved_accounts:
            bot.answer_callback_query(call.id, "⚠️ لا توجد حسابات محفوظة.", show_alert=True)
            return
        # بناء قائمة الحسابات مرقمة
        lines = ["🗑️ **حذف حساب من القائمة**\n\nأرسل **رقم الحساب** الذي تريد حذفه:\n"]
        for i, acc in enumerate(saved_accounts, 1):
            label = acc['email'].split('@')[0]
            lines.append(f"  {i}. {label}")
        lines.append("\nأو أرسل **إلغاء** للرجوع بدون حذف.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
        delete_transient_message(bot, chat_id)
        msg = bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown", reply_markup=markup)
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_DELETE_ACCOUNT'}
        return

    elif data.startswith("switch_acc_"):
        idx = int(data.replace("switch_acc_", ""))
        saved_accounts = get_saved_multi_accounts(chat_id)
        if 0 <= idx < len(saved_accounts):
            acc = saved_accounts[idx]
            new_email_lower = acc['email'].lower().strip()

            # ── حفظ إعدادات الحساب الحالي قبل التبديل ──
            old_email = user_data_store.get(chat_id, {}).get('email', '')
            if old_email:
                sync_chat_settings_to_email(chat_id, old_email)

            # حفظ بيانات الحساب الجديد كحساب نشط للعرض
            user_data_store[chat_id] = {'email': acc['email'], 'password': acc['password']}
            cloud_save_account(chat_id, acc['email'], acc['password'])

            # ── تسجيل الحساب الجديد في نظام الحسابات النشطة (إذا لم يكن مسجلاً) ──
            register_account_in_active(chat_id, acc['email'], acc['password'])

            # ── إذا كان الحساب المُبدَّل إليه مُعلَّماً كـ"مُسجَّل خروجه"، فامسح العلامة
            # لأن التبديل إليه يعني أننا سنعيد استخدامه (وستُعاد الجلسة تلقائياً)
            with logged_out_lock:
                if chat_id in logged_out_accounts:
                    logged_out_accounts[chat_id].discard(new_email_lower)

            # ── تحميل إعدادات الحساب الجديد ──
            # أولاً: جرب من المخزن المستقل (email-level)
            e_settings = get_email_settings(acc['email'])
            if e_settings['notify_status'] or e_settings['auto_hunt_status'] or e_settings['auto_execute_status']:
                # الحساب له إعدادات محفوظة → حمّلها للواجهة
                sync_email_settings_to_chat(chat_id, acc['email'])
            else:
                # حمّل من السحابة (الإعدادات الخاصة بـ chat_id)
                cloud_load_user_settings(chat_id)
                sync_chat_settings_to_email(chat_id, acc['email'])

            # التحقق من وجود جلسة صالحة مخزنة للحساب المُبدَّل إليه
            with auth_sessions_lock:
                cached = user_auth_sessions.get(new_email_lower)

            if not cached:
                # لا توجد جلسة مخزنة → نجهّز البروكسي والجلسة في الخلفية فوراً
                threading.Thread(
                    target=_prepare_session_with_proxy,
                    args=(acc['email'], acc['password']),
                    daemon=True
                ).start()
            # إذا كانت الجلسة موجودة فستُستخدم مباشرة عند أي طلب قادم

            bot.answer_callback_query(call.id)
            safe_edit_or_send(bot, chat_id, message_id, "🏠 **القائمة الرئيسية**\nــــــــــــــــــ", reply_markup=get_main_menu(chat_id))
        else:
            bot.answer_callback_query(call.id, "⚠️ حدث خطأ أثناء التبديل.", show_alert=True)
        return

    elif data == "login_start":
        bot.answer_callback_query(call.id)
        delete_transient_message(bot, chat_id)
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}
        return

    elif data == "proxy_status":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id)
        if not creds:
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        email = creds.get('email', '')
        proxy_text = build_proxy_status_text(email)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="proxy_status"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))

        safe_edit_or_send(bot, chat_id, message_id, proxy_text, reply_markup=markup)
        return

    elif data == "view_tasks":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return

        # ⚡ رد فوري + تشغيل الجلب في خيط خلفي حتى لا يتجمد البوت
        safe_edit_or_send(bot, chat_id, message_id, "⏳ جارٍ جلب المهام...")

        def _do_view_tasks():
            creds = user_data_store.get(chat_id)
            if not creds:
                return
            result, status = get_site_data(creds['email'], creds['password'], chat_id)
            if status == "SUCCESS":
                msg = f"💰 **الرصيد:** `{result['balance']}` RUB\n\n📌 **المهام المتوفرة:**\n"
                if result['tasks']:
                    for i, t in enumerate(result['tasks'][:10], start=1):
                        msg += f"🔢 {i} ➖ {t['price']} RUB | {t['duration']}\n"
                else:
                    msg += "🟢 لا توجد مهام حالياً.\n"
                msg += f"\n📊 **الإحصائيات:**\n🟡 قيد التنفيذ: {result['stats']['to_execute']}\n🔵 قيد المراجعة: {result['stats']['on_check']}"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="view_tasks"))
                markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                safe_edit_or_send(bot, chat_id, message_id, msg, reply_markup=markup)
            else:
                err_markup = types.InlineKeyboardMarkup()
                err_markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                safe_edit_or_send(bot, chat_id, message_id, "⚠️ فشل جلب البيانات. حاول مجدداً.", reply_markup=err_markup)

        threading.Thread(target=_do_view_tasks, daemon=True).start()
        return

    elif data == "hunt_menu":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        safe_edit_or_send(bot, chat_id, message_id, "🎯 **تصيد المهام**\nــــــــــــــــــ", reply_markup=get_hunting_menu())
        return

    elif data == "exec_menu":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        msg = "⚙️ **لوحة تحكم تنفيذ المهام**\nاختر أحد الخيارات أدناه:\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, msg, reply_markup=get_task_execution_menu(chat_id))
        return

    elif data == "logout":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        email_to_logout = creds.get('email', '').lower().strip()

        # ── تسجيل خروج حقيقي: مسح الجلسة النشطة ──
        if email_to_logout:
            # مسح الجلسة المصادقة من الذاكرة
            with auth_sessions_lock:
                user_auth_sessions.pop(email_to_logout, None)
            # إيقاف جميع المهام التلقائية لهذا الحساب
            e = email_to_logout
            acct_notify_status[e] = False
            acct_all_notify_status[e] = False
            acct_auto_hunt_status[e] = False
            acct_auto_execute_status[e] = False
            # تعليم الحساب كـ "مُسجَّل خروجه" في الذاكرة
            with logged_out_lock:
                if chat_id not in logged_out_accounts:
                    logged_out_accounts[chat_id] = set()
                logged_out_accounts[chat_id].add(email_to_logout)

        # ── مسح بيانات الجلسة الخاصة بـ chat_id (الواجهة) فقط ──
        # لا نحذف الحساب من multi_accounts حتى يبقى في قائمة الحسابات المحفوظة
        for store in [user_data_store, user_sessions, user_numbered_tasks,
                      notify_status, notify_interval, auto_hunt_status, hunt_mode,
                      last_take_time, user_notify_tasks, ignored_tasks,
                      auto_execute_status, auto_execute_interval, all_notify_status]:
            store.pop(chat_id, None)

        safe_edit_or_send(
            bot, chat_id, message_id,
            "🚪 **تم تسجيل الخروج بنجاح**\n\n"
            "💤 جلستك الحالية انتهت.\n"
            "يمكنك تسجيل الدخول مجدداً من قائمة الحسابات المحفوظة:",
            reply_markup=get_auth_menu(chat_id)
        )
        return

    elif data == "back_main":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        safe_edit_or_send(bot, chat_id, message_id, "🏠 **القائمة الرئيسية**\nــــــــــــــــــ", reply_markup=get_main_menu(chat_id))
        return

    elif data == "notif_menu":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        current_interval = notify_interval.get(chat_id, 10)
        is_active = notify_status.get(chat_id, False)
        status_text = "🟢 مفعلة" if is_active else "🔴 متوقفة"
        msg_text = f"🔔 **الإشعارات الدورية: {status_text}**\n⏱️ الفترة الحالية: {current_interval} دقائق\n\nاختر فترة التنبيه أو اضغط تخصيص:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_notifications_config_menu(chat_id))
        return

    elif data == "take_work_menu":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            safe_edit_or_send(bot, chat_id, message_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        creds = user_data_store.get(chat_id, {})
        email = creds.get('email', '')
        safe_edit_or_send(bot, chat_id, message_id, "⚡ **خيارات اصطحاب المهام**\nــــــــــــــــــ", reply_markup=get_take_work_menu(chat_id, email))
        return

    elif data == "back_hunt":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(bot, chat_id, message_id, "🎯 **تصيد المهام**\nــــــــــــــــــ", reply_markup=get_hunting_menu())
        return

    elif data == "toggle_notify":
        bot.answer_callback_query(call.id)
        current = notify_status.get(chat_id, False)
        notify_status[chat_id] = not current
        if notify_status[chat_id]:
            all_notify_status[chat_id] = False
        cloud_save_user_settings(chat_id)
        current_interval = notify_interval.get(chat_id, 10)
        is_active = notify_status.get(chat_id, False)
        status_text = "🟢 مفعلة" if is_active else "🔴 متوقفة"
        msg_text = f"🔔 **إعدادات الإشعارات:**\n⏱️ الفترة الحالية: {current_interval} دقائق\n\nاختر من الخيارات أدناه:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_notifications_config_menu(chat_id))
        return

    elif data == "toggle_all_notify":
        bot.answer_callback_query(call.id)
        current = all_notify_status.get(chat_id, False)
        all_notify_status[chat_id] = not current
        if all_notify_status[chat_id]:
            notify_status[chat_id] = False
        cloud_save_user_settings(chat_id)
        current_interval = notify_interval.get(chat_id, 10)
        msg_text = f"🔔 **إعدادات الإشعارات:**\n⏱️ الفترة الحالية: {current_interval} دقائق\n\nاختر من الخيارات أدناه:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_notifications_config_menu(chat_id))
        return

    elif data == "set_notify_10":
        notify_interval[chat_id] = 10
        notify_status[chat_id] = True
        cloud_save_user_settings(chat_id)
        bot.answer_callback_query(call.id, "✅ تم الضبط إلى 10 دقائق")
        msg_text = f"🔔 **الإشعارات الدورية: 🟢 مفعلة**\n⏱️ الفترة الحالية: 10 دقائق\n\nاختر فترة التنبيه أو اضغط تخصيص:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_notifications_config_menu(chat_id))
        return

    elif data == "set_notify_15":
        notify_interval[chat_id] = 15
        notify_status[chat_id] = True
        cloud_save_user_settings(chat_id)
        bot.answer_callback_query(call.id, "✅ تم الضبط إلى 15 دقيقة")
        msg_text = f"🔔 **الإشعارات الدورية: 🟢 مفعلة**\n⏱️ الفترة الحالية: 15 دقيقة\n\nاختر فترة التنبيه أو اضغط تخصيص:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_notifications_config_menu(chat_id))
        return

    elif data == "custom_notify":
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'WAITING_CUSTOM_INTERVAL'}
        msg_text = "📥 **أدخل فترة التنبيه بالدقائق**\n(من 3 إلى 120 دقيقة)\n\nاكتب الرقم وأرسله في الشات مباشرة:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_notifications_config_menu(chat_id))
        return

    elif data == "toggle_gt":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        current_active = auto_hunt_status.get(chat_id, False)
        current_mode = hunt_mode.get(chat_id, "")
        if current_active and current_mode == "GT":
            auto_hunt_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تصيد (أكبر من ساعتين)"
        else:
            auto_hunt_status[chat_id] = True
            hunt_mode[chat_id] = "GT"
            status_msg = "✅ تم تفعيل تصيد (أكبر من ساعتين)"
        cloud_save_user_settings(chat_id)
        # مزامنة للخيط الخلفي
        if creds.get('email'):
            sync_chat_settings_to_email(chat_id, creds['email'])
        full_msg = f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, full_msg, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
        return

    elif data == "toggle_gte":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        current_active = auto_hunt_status.get(chat_id, False)
        current_mode = hunt_mode.get(chat_id, "")
        if current_active and current_mode == "GTE":
            auto_hunt_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تصيد (ساعتين فما فوق)"
        else:
            auto_hunt_status[chat_id] = True
            hunt_mode[chat_id] = "GTE"
            status_msg = "✅ تم تفعيل تصيد (ساعتين فما فوق)"
        cloud_save_user_settings(chat_id)
        # مزامنة للخيط الخلفي
        if creds.get('email'):
            sync_chat_settings_to_email(chat_id, creds['email'])
        full_msg = f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, full_msg, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
        return

    elif data == "manual_take":
        bot.answer_callback_query(call.id)
        if not check_and_load_session_silently(chat_id):
            bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.", reply_markup=get_auth_menu(chat_id))
            return
        creds = user_data_store[chat_id]
        result, status = get_site_data(creds['email'], creds['password'], chat_id)
        if status == "SUCCESS":
            if not result['tasks']:
                full_msg = "⚡ **اصطحاب العمل**\n📋 لا توجد مهام متوفرة حالياً.\nــــــــــــــــــ"
                safe_edit_or_send(bot, chat_id, message_id, full_msg, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
            else:
                lines = ["📌 **قائمة المهام للاصطحاب اليدوي:**\n"]
                for i, task in enumerate(result['tasks'], start=1):
                    lines.append(f"🔢 {i} - السعر: {task['price']} RUB | المدة: {task['duration']}")
                bot.send_message(chat_id, "\n".join(lines))
        else:
            bot.send_message(chat_id, "⚠️ تعذر تحميل المهام اليدوية.")
        return

    elif data == "exec_auto_on":
        auto_execute_status[chat_id] = True
        cloud_save_user_settings(chat_id)
        bot.answer_callback_query(call.id, "🟢 تم تشغيل التنفيذ التلقائي")
        msg = "⚙️ **لوحة تحكم تنفيذ المهام**\n🟢 تم تشغيل التنفيذ التلقائي\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, msg, reply_markup=get_task_execution_menu(chat_id))
        return

    elif data == "exec_auto_off":
        auto_execute_status[chat_id] = False
        cloud_save_user_settings(chat_id)
        bot.answer_callback_query(call.id, "🔴 تم إيقاف التنفيذ التلقائي")
        msg = "⚙️ **لوحة تحكم تنفيذ المهام**\n🔴 تم إيقاف التنفيذ التلقائي\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, msg, reply_markup=get_task_execution_menu(chat_id))
        return

    elif data == "exec_add_template":
        if chat_id in user_sessions:
            bot.answer_callback_query(call.id, "⚠️ يرجى إكمال العملية السابقة أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'EXEC_ADD_KEYWORD'}
        bot.send_message(chat_id, "📝 **إضافة باقة جديدة**\n\n🔍 **الخطوة 1/3:** أدخل جزء من وصف المهمة للبحث عنه (كلمة مفتاحية):")
        return

    elif data == "exec_browse_templates":
        bot.answer_callback_query(call.id)
        templates = cloud_get_auto_tasks(chat_id)
        if not templates:
            msg_text = "📂 لا توجد البقات محفوظة لهذا الحساب حالياً.\n\nاضغط على '➕ إضافة الباقة' بالأسفل للبدء."
            safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_task_execution_menu(chat_id))
            return

        msg = f"📂 **البقاتك المحفوظة:** ({len(templates)} باقة)\n\n"
        for i, tmpl in enumerate(templates, 1):
            msg += f"**{i}.** 🔍 {tmpl['keyword'][:80]}\n"
            msg += f"   🔗 الحقل 1: {tmpl.get('work_url', '-')[:50]}\n"
            msg += f"   📝 الحقل 2: {tmpl.get('proof_msg', '-')[:50]}\n\n"

        markup = get_templates_browse_menu(chat_id)
        if markup:
            bot.send_message(chat_id, msg, reply_markup=markup)
        else:
            bot.send_message(chat_id, msg)
        return

    elif data.startswith("exec_view_"):
        template_id = data.replace("exec_view_", "")
        templates = cloud_get_auto_tasks(chat_id)
        template = next((t for t in templates if str(t['id']) == template_id), None)

        if not template:
            bot.answer_callback_query(call.id, "⚠️ الباقة غير موجودة")
            return

        bot.answer_callback_query(call.id)
        msg = (
            f"🔧 الباقة المحددة:\n\n"
            f"🔍 كلمة البحث:\n{template['keyword'][:200]}\n\n"
            f"🔗 رابط العمل (الحقل 1):\n{template.get('work_url', 'فارغ')[:200]}\n\n"
            f"📝 نص الإثبات (الحقل 2):\n{template.get('proof_msg', 'فارغ')[:200]}"
        )
        bot.send_message(chat_id, msg, reply_markup=get_template_edit_menu(template_id, template['keyword'], template.get('work_url', ''), template.get('proof_msg', '')))
        return

    elif data.startswith("exec_edit_keyword_"):
        template_id = data.replace("exec_edit_keyword_", "")
        templates = cloud_get_auto_tasks(chat_id)
        template = next((t for t in templates if str(t['id']) == template_id), None)
        if not template:
            bot.answer_callback_query(call.id, "⚠️ الباقة غير موجودة")
            return
        bot.answer_callback_query(call.id)
        if chat_id in user_sessions:
            bot.send_message(chat_id, "⚠️ يرجى إكمال العملية السابقة أولاً.")
            return
        user_sessions[chat_id] = {'step': 'EXEC_EDIT_KEYWORD', 'edit_id': template_id, 'old_template': template}
        bot.send_message(chat_id, f"✏️ تعديل كلمة البحث\n\nالقيمة الحالية:\n{template['keyword'][:200]}\n\nأدخل القيمة الجديدة:")
        return

    elif data.startswith("exec_edit_url_"):
        template_id = data.replace("exec_edit_url_", "")
        templates = cloud_get_auto_tasks(chat_id)
        template = next((t for t in templates if str(t['id']) == template_id), None)
        if not template:
            bot.answer_callback_query(call.id, "⚠️ الباقة غير موجودة")
            return
        bot.answer_callback_query(call.id)
        if chat_id in user_sessions:
            bot.send_message(chat_id, "⚠️ يرجى إكمال العملية السابقة أولاً.")
            return
        user_sessions[chat_id] = {'step': 'EXEC_EDIT_URL', 'edit_id': template_id, 'old_template': template}
        bot.send_message(chat_id, f"✏️ تعديل رابط العمل (الحقل 1)\n\nالقيمة الحالية:\n{template.get('work_url', 'فارغ')[:200]}\n\nأدخل القيمة الجديدة (أو `-` لتركه فارغاً):")
        return

    elif data.startswith("exec_edit_proof_"):
        template_id = data.replace("exec_edit_proof_", "")
        templates = cloud_get_auto_tasks(chat_id)
        template = next((t for t in templates if str(t['id']) == template_id), None)
        if not template:
            bot.answer_callback_query(call.id, "⚠️ الباقة غير موجودة")
            return
        bot.answer_callback_query(call.id)
        if chat_id in user_sessions:
            bot.send_message(chat_id, "⚠️ يرجى إكمال العملية السابقة أولاً.")
            return
        user_sessions[chat_id] = {'step': 'EXEC_EDIT_PROOF', 'edit_id': template_id, 'old_template': template}
        bot.send_message(chat_id, f"✏️ تعديل نص الإثبات (الحقل 2)\n\nالقيمة الحالية:\n{template.get('proof_msg', 'فارغ')[:200]}\n\nأدخل القيمة الجديدة:")
        return

    elif data.startswith("exec_delete_"):
        template_id = data.replace("exec_delete_", "")
        templates = cloud_get_auto_tasks(chat_id)
        template = next((t for t in templates if str(t['id']) == template_id), None)
        if not template:
            bot.answer_callback_query(call.id, "⚠️ الباقة غير موجودة")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ نعم، احذف", callback_data=f"exec_confirm_delete_{template_id}"),
            types.InlineKeyboardButton("❌ إلغاء", callback_data=f"exec_view_{template_id}")
        )
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"⚠️ هل أنت متأكد من حذف الباقة؟\n\n{template['keyword'][:100]}", reply_markup=markup)
        return

    elif data.startswith("exec_confirm_delete_"):
        template_id = data.replace("exec_confirm_delete_", "")
        if cloud_delete_auto_task(template_id):
            bot.answer_callback_query(call.id, "✅ تم حذف الباقة بنجاح")
            safe_edit_or_send(bot, chat_id, message_id, "🗑️ تم حذف الباقة.", reply_markup=get_task_execution_menu(chat_id))
        else:
            bot.answer_callback_query(call.id, "❌ فشل الحذف")
        return

    elif data == "exec_manual_now":
        creds = user_data_store.get(chat_id)
        if not creds:
            bot.answer_callback_query(call.id, "⚠️ يرجى تسجيل الدخول أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ جاري جلب المهام قيد التنفيذ...")

        def _fetch_pending_tasks():
            try:
                session = get_authenticated_session(creds['email'], creds['password'])
                if not session:
                    safe_edit_or_send(bot, chat_id, message_id, "❌ فشل تجديد الجلسة.", reply_markup=get_task_execution_menu(chat_id))
                    return
                tasks, status = extract_confirmed_tasks(session)
                if status != "SUCCESS":
                    safe_edit_or_send(bot, chat_id, message_id, f"❌ {status}", reply_markup=get_task_execution_menu(chat_id))
                    return
                if not tasks:
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="exec_back_to_main"))
                    safe_edit_or_send(bot, chat_id, message_id,
                        "📋 **لا توجد مهام قيد التنفيذ حالياً.**",
                        reply_markup=markup)
                    return
                user_pending_tasks[chat_id] = tasks
                markup = types.InlineKeyboardMarkup(row_width=1)
                for i, task in enumerate(tasks[:15]):
                    btn_text = f"{task['platform']} | 💰 {task['price']} | ⏱ {task['time_remaining'][:20]}"
                    markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"manual_exec_task_{i}"))
                markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="exec_back_to_main"))
                msg_text = f"⚡ **المهام قيد التنفيذ ({len(tasks)} مهمة)**\n\nاختر مهمة:\nــــــــــــــــــ"
                safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=markup)
            except Exception as e:
                safe_edit_or_send(bot, chat_id, message_id, f"❌ خطأ: {e}", reply_markup=get_task_execution_menu(chat_id))

        threading.Thread(target=_fetch_pending_tasks, daemon=True).start()
        return

    elif data.startswith("manual_exec_task_"):
        idx_t = int(data.replace("manual_exec_task_", ""))
        tasks = user_pending_tasks.get(chat_id, [])
        if not tasks or idx_t >= len(tasks):
            bot.answer_callback_query(call.id, "⚠️ المهمة غير متوفرة.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ جاري جلب وصف المهمة...")
        task = tasks[idx_t]
        creds = user_data_store.get(chat_id)
        if not creds:
            bot.answer_callback_query(call.id, "⚠️ يرجى تسجيل الدخول أولاً.", show_alert=True)
            return

        def _fetch_task_description(t, idx):
            wait_msg = None
            try:
                wait_msg = bot.send_message(chat_id, "⏳ جاري جلب وصف المهمة...")
                session = get_authenticated_session(creds['email'], creds['password'])
                task_link = t.get('original_url', t['task_link'])
                description_text = ""
                task_type_text = ""
                task_title = t.get('name', '')
                youtube_search_title = ""   # عنوان البحث في يوتيوب
                youtube_channel_name = ""   # اسم القناة

                if session:
                    try:
                        r = session.get(task_link, headers=HEADERS, timeout=10)
                        if r.status_code == 200:
                            from bs4 import BeautifulSoup as _BS
                            soup = _BS(r.text, "html.parser")

                            # استخراج العنوان (اسم الطلب)
                            name_td = soup.find("td", string="Название")
                            if name_td:
                                name_link = name_td.find_next("td").find("a")
                                if name_link:
                                    task_title = name_link.get_text(strip=True)

                            # استخراج نوع المهمة
                            type_td = soup.find("td", string=re.compile(r"Тип задания", re.I))
                            if type_td:
                                type_val = type_td.find_next_sibling("td")
                                if type_val:
                                    task_type_text = type_val.get_text(strip=True)

                            # استخراج الوصف "ما يجب فعله" + عنوان البحث + اسم القناة
                            what_td = soup.find("td", string="Что делать")
                            if what_td:
                                desc_td = what_td.find_next("td")
                                if desc_td:
                                    desc_div = desc_td.find("div", style=re.compile(r"overflow-wrap"))
                                    target_el = desc_div if desc_div else desc_td
                                    description_text = target_el.get_text(separator="\n", strip=True)

                                    # ── استخراج عنوان البحث في يوتيوب ──
                                    # البنية: فقرة تحتوي "поиске" ثم <strong> يليها مباشرة
                                    for p_tag in target_el.find_all("p"):
                                        p_text = p_tag.get_text()
                                        if "поиске" in p_text or "поиск" in p_text:
                                            strong_tags = p_tag.find_all("strong")
                                            for st in strong_tags:
                                                candidate = st.get_text(strip=True)
                                                if len(candidate) > 5:
                                                    youtube_search_title = candidate
                                                    break
                                            # إذا لم نجد <strong> نبحث في الفقرة التالية
                                            if not youtube_search_title:
                                                next_p = p_tag.find_next_sibling("p")
                                                if next_p:
                                                    st = next_p.find("strong")
                                                    if st:
                                                        youtube_search_title = st.get_text(strip=True)
                                            break

                                    # إذا لم نجد بالفقرات، نبحث في كل النص عن أول <strong> بعد "поиске"
                                    if not youtube_search_title:
                                        full_html = str(target_el)
                                        idx_search = full_html.lower().find("поиске")
                                        if idx_search == -1:
                                            idx_search = full_html.lower().find("поиск")
                                        if idx_search != -1:
                                            chunk = full_html[idx_search:]
                                            tmp_soup = _BS(chunk, "html.parser")
                                            st = tmp_soup.find("strong")
                                            if st:
                                                candidate = st.get_text(strip=True)
                                                if len(candidate) > 5:
                                                    youtube_search_title = candidate

                                    # ── استخراج اسم القناة ──
                                    # البنية: "от канала" ثم <strong> أو <span> مباشرة
                                    full_html = str(target_el)
                                    for kw in ["от канала", "канала"]:
                                        idx_ch = full_html.lower().find(kw)
                                        if idx_ch != -1:
                                            chunk = full_html[idx_ch:]
                                            tmp_soup = _BS(chunk, "html.parser")

                                            # أولاً: ابحث في <span> المميّز بلون خلفية (أصفر غالباً = اسم القناة)
                                            candidate = ""
                                            for span in tmp_soup.find_all("span"):
                                                style = span.get("style", "")
                                                if "background-color" in style:
                                                    txt = span.get_text(strip=True)
                                                    txt = txt.strip().rstrip("-").strip()
                                                    if len(txt) > 1:
                                                        candidate = txt
                                                        break

                                            # ثانياً: إذا لم يُجدِ، ابحث في <strong> لكن تأكد أنه ليس كلمة تحذير
                                            if not candidate:
                                                st = tmp_soup.find("strong")
                                                if st:
                                                    txt = st.get_text(strip=True).strip().rstrip("-").strip()
                                                    # تجاهل كلمات التحذير الروسية الشائعة
                                                    ignore_words = ["ВНИМАНИЕ", "ОБЯЗАТЕЛЬНО", "ВАЖНО", "СТРОГО", "НОВОЕ"]
                                                    if len(txt) > 1 and not any(w in txt.upper() for w in ignore_words):
                                                        candidate = txt

                                            if candidate:
                                                youtube_channel_name = candidate
                                                break

                    except Exception:
                        pass

                try:
                    bot.delete_message(chat_id, wait_msg.message_id)
                except Exception:
                    pass

                # ── رسالة المعلومات الأساسية (مع Markdown) ──
                msg_lines = ["📋 *تنفيذ المهمة*\n"]
                msg_lines.append(f"🌐 المنصة: {t['platform']}")
                msg_lines.append(f"💰 السعر: {t['price']}")
                msg_lines.append(f"⏱ الوقت: {t['time_remaining']}")
                if task_title:
                    msg_lines.append(f"\n📌 *اسم المهمة:* {task_title}")
                if task_type_text:
                    msg_lines.append(f"🏷 *نوع المهمة:* {task_type_text}")

                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton("⚡ تنفيذ الآن (إرسال الروابط)", callback_data=f"manual_exec_now_{idx}"),
                    types.InlineKeyboardButton("🔙 رجوع", callback_data="exec_manual_now")
                )

                bot.send_message(chat_id, "\n".join(msg_lines), parse_mode="Markdown")

                                # ── رسالة عنوان البحث (تنسيق MarkdownV2 - قابلة للنسخ بالكامل بنقرة واحدة) ──
                if youtube_search_title:
                    # هروب الرموز الخاصة بـ MarkdownV2 لحماية النص من الأخطاء والانهيار
                    escaped_title = (
                        str(youtube_search_title)
                        .replace('\\', '\\\\')
                        .replace('_', '\\_')
                        .replace('*', '\\*')
                        .replace('[', '\\[')
                        .replace(']', '\\]')
                        .replace('(', '\\(')
                        .replace(')', '\\)')
                        .replace('~', '\\~')
                        .replace('`', '\\`')
                        .replace('>', '\\>')
                        .replace('#', '\\#')
                        .replace('+', '\\+')
                        .replace('-', '\\-')
                        .replace('=', '\\=')
                        .replace('|', '\\|')
                        .replace('{', '\\{')
                        .replace('}', '\\}')
                        .replace('.', '\\.')
                        .replace('!', '\\!')
                    )
                    
                    bot.send_message(
                        chat_id,
                        f"🔍 عنوان البحث في يوتيوب \\(اضغط للنسخ\\):\n\n`{escaped_title}`",
                        parse_mode="MarkdownV2"
                    )


                # ── رسالة اسم القناة (بدون Markdown - قابلة للنسخ) ──
                if youtube_channel_name:
                    bot.send_message(
                        chat_id,
                        f"📺 اسم القناة (انسخه):\n\n{youtube_channel_name}"
                    )

                # ── رسالة الوصف الكامل ──
                if description_text:
                    max_desc = 2000
                    desc_display = description_text[:max_desc]
                    if len(description_text) > max_desc:
                        desc_display += "\n…[مقتطع]"
                    bot.send_message(
                        chat_id,
                        f"📝 ما يجب فعله:\n\n{desc_display}"
                    )
                else:
                    bot.send_message(chat_id, "⚠️ لم يتم العثور على وصف تفصيلي للمهمة.")

                # ── رسالة الأزرار ──
                bot.send_message(chat_id, "━━━━━━━━━━━━━━━━━━━━\n     https://imgbb.com      اختر الإجراء:", reply_markup=markup)

            except Exception as e:
                if wait_msg:
                    try:
                        bot.delete_message(chat_id, wait_msg.message_id)
                    except Exception:
                        pass
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="exec_manual_now"))
                bot.send_message(chat_id, f"❌ خطأ أثناء جلب وصف المهمة: {e}", reply_markup=markup)

        threading.Thread(target=_fetch_task_description, args=(task, idx_t), daemon=True).start()
        return

    elif data.startswith("manual_exec_fill_"):
        idx_t = int(data.replace("manual_exec_fill_", ""))
        tasks = user_pending_tasks.get(chat_id, [])
        if not tasks or idx_t >= len(tasks):
            bot.answer_callback_query(call.id, "⚠️ المهمة غير متوفرة.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        task = tasks[idx_t]
        user_sessions[chat_id] = {'step': 'MANUAL_EXEC_FILL', 'selected_task': task}
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data=f"manual_exec_task_{idx_t}")
        )
        msg = (
            f"📎 **الحقل 1 — رابط العمل**\n\n"
            f"أرسل رابط عملك الآن:\n"
            f"(أو أرسل `-` إذا لم يكن مطلوباً)"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
        return

    elif data.startswith("manual_exec_now_"):
        idx_t = int(data.replace("manual_exec_now_", ""))
        tasks = user_pending_tasks.get(chat_id, [])
        if not tasks or idx_t >= len(tasks):
            bot.answer_callback_query(call.id, "⚠️ المهمة غير متوفرة.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        task = tasks[idx_t]
        user_sessions[chat_id] = {'step': 'MANUAL_EXEC_NOW_FIELD1', 'selected_task': task, 'task_idx': idx_t}
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data=f"manual_exec_task_{idx_t}")
        )
        msg = (
            f"⚡ **تنفيذ الآن**\n\n"
            f"🌐 المنصة: {task['platform']}\n"
            f"💰 السعر: {task['price']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📎 **أرسل رابط العمل (الحقل 1):**\n"
            f"(أو أرسل `-` إذا لم يكن مطلوباً)"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
        return

    elif data == "manual_exec_custom":
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'MANUAL_EXEC_CUSTOM_URL'}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"))
        bot.send_message(chat_id,
            "✍️ **تنفيذ مهمة برابط يدوي**\n\n"
            "أرسل رابط المهمة (مثال):\n"
            "`https://forumok.com/create-request/1588396/youtube/7b8229d2`",
            parse_mode="Markdown", reply_markup=markup)
        return

    elif data == "manual_exec_cancel":
        bot.answer_callback_query(call.id)
        if chat_id in user_sessions:
            step = user_sessions[chat_id].get('step', '')
            if 'MANUAL_EXEC' in step:
                del user_sessions[chat_id]
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        safe_edit_or_send(bot, chat_id, message_id,
            "⚙️ **لوحة تحكم تنفيذ المهام**\nــــــــــــــــــ",
            reply_markup=get_task_execution_menu(chat_id))
        return

    elif data == "exec_set_interval":
        if chat_id in user_sessions:
            bot.answer_callback_query(call.id, "⚠️ يرجى إكمال العملية السابقة أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'EXEC_SET_INTERVAL'}
        bot.send_message(chat_id, "⏱️ أدخل الفترة الزمنية للتنفيذ الدوري بالدقائق (من 1 إلى 80 دقيقة):")
        return

    elif data == "exec_share_by_chat_id":
        bot.answer_callback_query(call.id)
        if chat_id in user_sessions:
            bot.answer_callback_query(call.id, "⚠️ يرجى إكمال العملية السابقة أولاً.", show_alert=True)
            return
        user_sessions[chat_id] = {'step': 'EXEC_WAIT_SHARE_CHAT_ID'}
        msg_text = "📧 **مشاركة البقات مع حساب تليجرام آخر**\n\nاكتب chat_id الخاص بحساب التليجرام الذي تريد إرسال البقات إليه:"
        safe_edit_or_send(bot, chat_id, message_id, msg_text, reply_markup=get_task_execution_menu(chat_id))
        return

    elif data == "exec_back_to_main":
        bot.answer_callback_query(call.id)
        msg = "⚙️ **لوحة تحكم تنفيذ المهام**\nــــــــــــــــــ"
        safe_edit_or_send(bot, chat_id, message_id, msg, reply_markup=get_task_execution_menu(chat_id))
        return

    elif data == "ign_task":
        if chat_id not in user_notify_tasks or not user_notify_tasks[chat_id]:
            bot.answer_callback_query(call.id, "⚠️ لا توجد مهام حالياً لتجاهلها.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'WAIT_IGN_NUM'}
        bot.send_message(chat_id, "🔢 أدخل رقم المهمة لتجاهلها:")
        return

    elif data.startswith("ign_specific_"):
        bot.answer_callback_query(call.id)
        parts = data.split("_", 3)
        if len(parts) >= 4:
            task_identifier = parts[3]
            if chat_id in user_notify_tasks:
                for task in user_notify_tasks[chat_id]:
                    if task['task_page'][:50] == task_identifier:
                        if chat_id not in ignored_tasks:
                            ignored_tasks[chat_id] = []
                        if task['task_page'] not in ignored_tasks[chat_id]:
                            ignored_tasks[chat_id].append(task['task_page'])
                        bot.answer_callback_query(call.id, "✅ تم تجاهل المهمة بنجاح")
                        try:
                            bot.delete_message(chat_id, message_id)
                        except Exception:
                            pass
                        return
        bot.answer_callback_query(call.id, "⚠️ لم يتم العثور على المهمة", show_alert=True)
        return

    # ==========================================
    # 💸 معالجات زر السحب
    # ==========================================
    elif data == "withdraw_menu":
        creds = user_data_store.get(chat_id)
        if not creds:
            bot.answer_callback_query(call.id, "⚠️ يرجى تسجيل الدخول أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ جاري جلب بيانات السحب...")

        def _do_fetch_withdraw():
            try:
                session = get_authenticated_session(creds['email'], creds['password'])
                if not session:
                    safe_edit_or_send(bot, chat_id, message_id, "❌ فشل تجديد الجلسة.", reply_markup=get_main_menu(chat_id))
                    return
                info = fetch_withdrawal_page(session)

                if info["status"] == "restricted_10days":
                    # جلب بيانات المحفظة لعرض زر التعديل
                    wallet_r = info.get("wallet", "")
                    if not wallet_r:
                        # محاولة جلب من صفحة الإعدادات
                        try:
                            profile = fetch_billing_profile(session)
                            if profile:
                                wallet_r = profile.get("wallet", "")
                        except Exception:
                            pass
                    msg = (
                        "🔒 **السحب مقيد مؤقتاً**\n\n"
                        "⏳ مسموح بطلب سحب واحد فقط كل **10 أيام**.\n"
                        "يرجى الانتظار حتى انتهاء فترة القيد."
                    )
                    safe_edit_or_send(bot, chat_id, message_id, msg,
                        reply_markup=get_withdraw_menu_limited(wallet_r))
                    return

                if info["status"] == "error":
                    safe_edit_or_send(bot, chat_id, message_id,
                        f"❌ خطأ: {info.get('msg', 'غير معروف')}",
                        reply_markup=get_main_menu(chat_id))
                    return

                balance = info.get("balance", 0.0)
                wallet = info.get("wallet", "غير محدد")
                pay_system = info.get("pay_system", "غير محدد")

                # فحص الحد الأدنى 300 روبل
                if balance < 300:
                    msg = (
                        f"⚠️ **لا يمكن السحب**\n\n"
                        f"💰 رصيدك الحالي: **{balance:.2f} روبل**\n"
                        f"📌 الحد الأدنى للسحب: **300 روبل**\n\n"
                        f"أكمل المهام لزيادة رصيدك."
                    )
                    safe_edit_or_send(bot, chat_id, message_id, msg,
                        reply_markup=get_withdraw_menu_limited(wallet))
                    return

                msg = (
                    f"💸 **سحب الرصيد**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 الرصيد المتاح: **{balance:.2f} روبل**\n"
                    f"🏦 نظام الدفع: {pay_system}\n"
                    f"📬 عنوان المحفظة: `{wallet}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
                safe_edit_or_send(bot, chat_id, message_id, msg,
                    reply_markup=get_withdraw_menu(balance, wallet, pay_system))
            except Exception as e:
                safe_edit_or_send(bot, chat_id, message_id, f"❌ خطأ غير متوقع: {e}",
                    reply_markup=get_main_menu(chat_id))

        threading.Thread(target=_do_fetch_withdraw, daemon=True).start()
        return

    elif data == "withdraw_do":
        creds = user_data_store.get(chat_id)
        if not creds:
            bot.answer_callback_query(call.id, "⚠️ يرجى تسجيل الدخول أولاً.", show_alert=True)
            return
        # طلب مبلغ السحب
        if chat_id in user_sessions:
            bot.answer_callback_query(call.id, "⚠️ يرجى إكمال العملية السابقة أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'WITHDRAW_WAIT_AMOUNT'}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="withdraw_cancel"))
        bot.send_message(chat_id,
            "💸 **أدخل مبلغ السحب بالروبل** (الحد الأدنى 300):\n"
            "أو أرسل `كل` لسحب كامل الرصيد:",
            parse_mode="Markdown", reply_markup=markup)
        return

    elif data == "withdraw_edit_wallet":
        creds = user_data_store.get(chat_id)
        if not creds:
            bot.answer_callback_query(call.id, "⚠️ يرجى تسجيل الدخول أولاً.", show_alert=True)
            return
        if chat_id in user_sessions:
            bot.answer_callback_query(call.id, "⚠️ يرجى إكمال العملية السابقة أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "⏳ جاري جلب بيانات المحفظة...")

        def _do_fetch_billing():
            try:
                session = get_authenticated_session(creds['email'], creds['password'])
                if not session:
                    bot.send_message(chat_id, "❌ فشل تجديد الجلسة.")
                    return
                profile = fetch_billing_profile(session)
                if not profile:
                    bot.send_message(chat_id, "❌ فشل جلب بيانات المحفظة.")
                    return
                user_sessions[chat_id] = {
                    'step': 'WITHDRAW_EDIT_WALLET',
                    'billing_profile': profile
                }
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="withdraw_cancel"))
                bot.send_message(chat_id,
                    f"✏️ **تعديل عنوان المحفظة**\n\n"
                    f"🏦 نظام الدفع الحالي: {profile['pay_system']}\n"
                    f"📬 العنوان الحالي: `{profile['wallet']}`\n\n"
                    f"أرسل العنوان الجديد:",
                    parse_mode="Markdown", reply_markup=markup)
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ: {e}")

        threading.Thread(target=_do_fetch_billing, daemon=True).start()
        return

    elif data == "withdraw_cancel":
        bot.answer_callback_query(call.id)
        if chat_id in user_sessions:
            step = user_sessions[chat_id].get('step', '')
            if step in ('WITHDRAW_WAIT_AMOUNT', 'WITHDRAW_EDIT_WALLET'):
                del user_sessions[chat_id]
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        try:
            bot.send_message(chat_id, "🏠 **القائمة الرئيسية**\nــــــــــــــــــ",
                parse_mode="Markdown", reply_markup=get_main_menu(chat_id))
        except Exception:
            pass
        return

# ==========================================
# 📨 معالجة الرسائل
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_bot_logic(message):
    try:
        _handle_message_inner(message)
    except Exception as _msg_err:
        print(f"[MESSAGE] خطأ غير متوقع: {_msg_err}")
        try:
            bot.send_message(message.chat.id, "⚠️ حدث خطأ، حاول مجدداً.")
        except Exception:
            pass

def _handle_message_inner(message):
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""

    if text.lower() not in ["/start", "start"]:
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

    if text.lower() in ["/start", "start"]:
        remove_keyboard = types.ReplyKeyboardRemove()
        if check_and_load_session_silently(chat_id):
            bot.send_message(chat_id, "مرحباً بك في لوحة التحكم الرئيسية ⚙️", reply_markup=remove_keyboard)
            bot.send_message(chat_id, "إليك القائمة الرئيسية:", reply_markup=get_main_menu(chat_id))
        else:
            bot.send_message(chat_id, "مرحباً بك في البوت.", reply_markup=remove_keyboard)
            bot.send_message(chat_id, "⚙️ يرجى تسجيل الدخول للبدء أو اختيار حسابك المحفوظ:", reply_markup=get_auth_menu(chat_id))
        return

    if chat_id in user_sessions:
        step = user_sessions[chat_id]['step']

        if step == 'WAITING_EMAIL':
            delete_transient_message(bot, chat_id)
            user_sessions[chat_id]['email'] = text
            user_sessions[chat_id]['step'] = 'WAITING_PASSWORD'
            msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
            user_transient_messages[chat_id] = msg.message_id
            return

        elif step == 'WAITING_PASSWORD':
            delete_transient_message(bot, chat_id)
            email = user_sessions[chat_id]['email']
            password = text
            del user_sessions[chat_id]

            email_lower = email.lower().strip()

            # رسالة انتظار مناسبة
            with proxy_store_lock:
                has_proxies = (
                    email_lower not in EXEMPT_ACCOUNTS and
                    email_lower in dynamic_proxy_store and
                    bool(dynamic_proxy_store[email_lower].get("proxies"))
                )
            if email_lower in EXEMPT_ACCOUNTS:
                status_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الحساب...")
            elif has_proxies:
                status_msg = bot.send_message(chat_id, "⚡ جاري تسجيل الدخول بأسرع بروكسي متاح...")
            else:
                status_msg = bot.send_message(
                    chat_id,
                    "🌐 جاري جلب البروكسيات واختبارها...\n"
                    "⏳ سيتم تسجيل الدخول بأول بروكسي سريع يُعثر عليه\n"
                    "📦 ثم يكمل تجهيز أفضل 20 بروكسي في الخلفية"
                )

            # تسجيل الدخول — يعثر على أول بروكسي سريع ثم يُسجَّل فوراً
            session = get_authenticated_session(email, password)

            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass

            if session:
                user_data_store[chat_id] = {'email': email, 'password': password}
                cloud_save_account(chat_id, email, password)
                save_multi_account(chat_id, email, password)
                cloud_load_user_settings(chat_id)

                # ── تسجيل الحساب في نظام الحسابات النشطة المتعددة ──
                register_account_in_active(chat_id, email, password)
                sync_chat_settings_to_email(chat_id, email)

                # حفظ الجلسة في المخزن العام (قد تكون محفوظة بالفعل من get_authenticated_session)
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = session

                # ── مسح علامة "مُسجَّل خروجه" عند إعادة الدخول ──
                with logged_out_lock:
                    if chat_id in logged_out_accounts:
                        logged_out_accounts[chat_id].discard(email_lower)

                remove_keyboard = types.ReplyKeyboardRemove()
                bot.send_message(chat_id, "✅", reply_markup=remove_keyboard)

                welcome_msg = "🎉 **تم تسجيل الدخول بنجاح!**"
                if email_lower in EXEMPT_ACCOUNTS:
                    welcome_msg += "\n🔵 تم تفعيل البروكسي الثابت المخصص."
                else:
                    with proxy_store_lock:
                        proxy_count = len(dynamic_proxy_store.get(email_lower, {}).get("proxies", []))
                    if proxy_count >= PROXIES_PER_ACCOUNT:
                        welcome_msg += f"\n🌐 تم تفعيل {proxy_count} بروكسي ديناميكي."
                    else:
                        welcome_msg += f"\n⚡ تم تسجيل الدخول بأسرع بروكسي.\n📦 جاري تجهيز أفضل {PROXIES_PER_ACCOUNT} بروكسي في الخلفية..."
                welcome_msg += "\n\nــــــــــــــــــ"

                bot.send_message(chat_id, welcome_msg, parse_mode="Markdown", reply_markup=get_main_menu(chat_id))
            else:
                bot.send_message(chat_id, "❌ فشل تسجيل الدخول، تأكد من بياناتك.", reply_markup=get_auth_menu(chat_id))
            return

        elif step == 'WAITING_DELETE_ACCOUNT':
            delete_transient_message(bot, chat_id)
            # السماح بكتابة "إلغاء" أو "الغاء" للخروج بدون حذف
            if text.strip().lower() in ['إلغاء', 'الغاء', 'cancel', 'لا']:
                del user_sessions[chat_id]
                bot.send_message(chat_id, "↩️ تم الإلغاء.",
                    reply_markup=get_switch_account_menu(chat_id))
                return
            if not text.strip().isdigit():
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
                bot.send_message(chat_id, "⚠️ أرسل رقم الحساب فقط، أو أرسل **إلغاء** للرجوع:",
                    parse_mode="Markdown", reply_markup=markup)
                return
            idx = int(text.strip()) - 1
            saved_accounts = get_saved_multi_accounts(chat_id)
            if idx < 0 or idx >= len(saved_accounts):
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
                bot.send_message(chat_id,
                    f"⚠️ الرقم غير موجود. أدخل رقماً بين 1 و {len(saved_accounts)}، أو أرسل **إلغاء**:",
                    parse_mode="Markdown", reply_markup=markup)
                return

            del user_sessions[chat_id]
            acc_to_delete = saved_accounts[idx]
            email_del = acc_to_delete['email'].lower().strip()
            label_del = email_del.split('@')[0]

            # ── حذف من الذاكرة ──
            with active_accounts_lock:
                if chat_id in active_accounts:
                    active_accounts[chat_id].pop(email_del, None)

            # ── حذف من السحابة ──
            threading.Thread(
                target=cloud_delete_multi_account,
                args=(chat_id, email_del),
                daemon=True
            ).start()

            # ── إزالة الجلسة والبروكسي ──
            with auth_sessions_lock:
                user_auth_sessions.pop(email_del, None)
            with proxy_store_lock:
                dynamic_proxy_store.pop(email_del, None)

            # ── إذا كان الحساب المحذوف هو الحساب النشط، امسح الواجهة ──
            active_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
            if active_email == email_del:
                for store in [user_data_store, user_sessions, user_numbered_tasks,
                              notify_status, notify_interval, auto_hunt_status, hunt_mode,
                              last_take_time, user_notify_tasks, ignored_tasks,
                              auto_execute_status, auto_execute_interval, all_notify_status]:
                    store.pop(chat_id, None)

            bot.send_message(chat_id,
                f"✅ **تم حذف الحساب {label_del} نهائياً**\n\n"
                f"🗑️ تم حذفه من القائمة وجميع الجلسات.",
                parse_mode="Markdown",
                reply_markup=get_switch_account_menu(chat_id))
            return

        elif step == 'WAITING_CUSTOM_INTERVAL':
            if text.isdigit():
                minutes = int(text)
                if 3 <= minutes <= 120:
                    notify_interval[chat_id] = minutes
                    notify_status[chat_id] = True
                    cloud_save_user_settings(chat_id)
                    del user_sessions[chat_id]
                    bot.send_message(chat_id, f"✅ تم ضبط فترة التنبيه إلى {minutes} دقيقة.")
                else:
                    bot.send_message(chat_id, "⚠️ يرجى إدخال قيمة بين 3 و 120 دقيقة:")
            else:
                bot.send_message(chat_id, "❌ الرجاء إدخال أرقام فقط (مثال: 25):")
            return

        elif step == 'EXEC_SET_INTERVAL':
            if text.isdigit():
                minutes = int(text)
                if 1 <= minutes <= 80:
                    auto_execute_interval[chat_id] = minutes
                    cloud_save_user_settings(chat_id)
                    del user_sessions[chat_id]
                    bot.send_message(chat_id, f"✅ تم ضبط الفترة الدورية إلى {minutes} دقيقة.")
                else:
                    bot.send_message(chat_id, "⚠️ يرجى إدخال قيمة بين 1 و 80 دقيقة:")
            else:
                bot.send_message(chat_id, "❌ الرجاء إدخال أرقام فقط (مثال: 10):")
            return

        elif step == 'WAIT_IGN_NUM':
            if text.isdigit():
                idx = int(text) - 1
                if chat_id in user_notify_tasks and 0 <= idx < len(user_notify_tasks[chat_id]):
                    task_url = user_notify_tasks[chat_id][idx]['task_page']
                    if chat_id not in ignored_tasks:
                        ignored_tasks[chat_id] = []
                    if task_url not in ignored_tasks[chat_id]:
                        ignored_tasks[chat_id].append(task_url)
                    del user_sessions[chat_id]
                    bot.send_message(chat_id, "✅ تم تجاهل المهمة.")
                else:
                    bot.send_message(chat_id, "⚠️ الرقم غير موجود بالقائمة:")
            else:
                bot.send_message(chat_id, "❌ أدخل رقم صحيح فقط:")
            return

        elif step == 'EXEC_ADD_KEYWORD':
            user_sessions[chat_id]['keyword'] = text
            user_sessions[chat_id]['step'] = 'EXEC_ADD_URL'
            bot.send_message(chat_id, "🔗 **الخطوة 2/3:** أدخل رابط العمل للحقل الأول (أو أرسل `-` إذا لم يوجد):")
            return

        elif step == 'EXEC_ADD_URL':
            work_url_val = "" if text in ["-", "لا يوجد", "لايوجد"] else text
            user_sessions[chat_id]['work_url'] = work_url_val
            user_sessions[chat_id]['step'] = 'EXEC_ADD_PROOF'
            bot.send_message(chat_id, "📝 **الخطوة 3/3:** أدخل نص التقرير والإثبات للحقل الثاني:")
            return

        elif step == 'EXEC_ADD_PROOF':
            keyword = user_sessions[chat_id]['keyword']
            work_url = user_sessions[chat_id]['work_url']
            proof_msg = text
            del user_sessions[chat_id]
            if cloud_save_auto_task(chat_id, keyword, work_url, proof_msg):
                bot.send_message(chat_id, "✅ **تم حفظ الباقة بنجاح!**")
            else:
                bot.send_message(chat_id, "❌ فشل حفظ الباقة.")
            return

        elif step == 'EXEC_EDIT_KEYWORD':
            template_id = user_sessions[chat_id]['edit_id']
            new_keyword = text
            old_data = user_sessions[chat_id].get('old_template', {})
            del user_sessions[chat_id]
            if cloud_update_template(template_id, new_keyword, old_data.get('work_url', ''), old_data.get('proof_msg', '')):
                bot.send_message(chat_id, "✅ تم تحديث كلمة البحث.")
            else:
                bot.send_message(chat_id, "❌ فشل التحديث.")
            return

        elif step == 'EXEC_EDIT_URL':
            template_id = user_sessions[chat_id]['edit_id']
            new_url = "" if text in ["-", "لا يوجد", "لايوجد"] else text
            old_data = user_sessions[chat_id].get('old_template', {})
            del user_sessions[chat_id]
            if cloud_update_template(template_id, old_data.get('keyword', ''), new_url, old_data.get('proof_msg', '')):
                bot.send_message(chat_id, "✅ تم تحديث رابط العمل.")
            else:
                bot.send_message(chat_id, "❌ فشل التحديث.")
            return

        elif step == 'EXEC_EDIT_PROOF':
            template_id = user_sessions[chat_id]['edit_id']
            new_proof = text
            old_data = user_sessions[chat_id].get('old_template', {})
            del user_sessions[chat_id]
            if cloud_update_template(template_id, old_data.get('keyword', ''), old_data.get('work_url', ''), new_proof):
                bot.send_message(chat_id, "✅ تم تحديث نص الإثبات.")
            else:
                bot.send_message(chat_id, "❌ فشل التحديث.")
            return

        elif step == 'EXEC_WAIT_SHARE_CHAT_ID':
            target_chat_id_text = text.strip()
            del user_sessions[chat_id]
            if not target_chat_id_text.isdigit() and not (target_chat_id_text.startswith('-') and target_chat_id_text[1:].isdigit()):
                bot.send_message(chat_id, "❌ الرجاء إدخال chat_id رقمي صحيح.")
                return
            target_chat_id = int(target_chat_id_text)
            status_msg = bot.send_message(chat_id, f"⏳ جاري نقل البقات إلى حساب التليجرام: {target_chat_id}...")
            result = cloud_share_templates_by_chat_id(target_chat_id, current_chat_id=chat_id)
            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass
            if result == "SUCCESS":
                bot.send_message(chat_id, f"✅ تم نقل البقات إلى حساب التليجرام {target_chat_id} بنجاح.")
            elif result == "ALREADY_EXISTS":
                bot.send_message(chat_id, "ℹ️ جميع البقات موجودة مسبقاً لدى هذا الحساب، لم يتم إضافة جديد.")
            elif result == "EMPTY":
                bot.send_message(chat_id, "⚠️ لا توجد البقات محفوظة لنقلها!")
            else:
                bot.send_message(chat_id, "❌ حدث خطأ غير متوقع.")
            return

        elif step == 'WITHDRAW_WAIT_AMOUNT':
            creds = user_data_store.get(chat_id, {})
            amount_text = text.strip()
            del user_sessions[chat_id]
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.")
                return

            # سحب كامل الرصيد أو مبلغ محدد
            withdraw_all = amount_text in ["كل", "الكل", "all", "ALL"]
            if not withdraw_all:
                try:
                    amount_val = float(amount_text.replace(",", "."))
                    if amount_val < 300:
                        bot.send_message(chat_id, "❌ الحد الأدنى للسحب هو 300 روبل.")
                        return
                except ValueError:
                    bot.send_message(chat_id, "❌ أدخل رقماً صحيحاً أو كلمة 'كل' لسحب كامل الرصيد.")
                    return
            else:
                amount_val = None

            wait_msg = bot.send_message(chat_id, "⏳ جاري تنفيذ طلب السحب...")

            def _do_withdraw(a_val, a_all):
                try:
                    session = get_authenticated_session(creds['email'], creds['password'])
                    if not session:
                        try:
                            bot.delete_message(chat_id, wait_msg.message_id)
                        except Exception:
                            pass
                        bot.send_message(chat_id, "❌ فشل تجديد الجلسة.")
                        return

                    info = fetch_withdrawal_page(session)

                    if info["status"] == "restricted_10days":
                        try:
                            bot.delete_message(chat_id, wait_msg.message_id)
                        except Exception:
                            pass
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                        bot.send_message(chat_id,
                            "🔒 **السحب مقيد مؤقتاً**\n\n"
                            "⏳ مسموح بطلب سحب واحد فقط كل **10 أيام**.",
                            parse_mode="Markdown", reply_markup=markup)
                        return

                    if info["status"] != "ok":
                        try:
                            bot.delete_message(chat_id, wait_msg.message_id)
                        except Exception:
                            pass
                        bot.send_message(chat_id, f"❌ فشل جلب بيانات السحب: {info.get('msg', '')}")
                        return

                    balance = info.get("balance", 0.0)
                    if balance < 300:
                        try:
                            bot.delete_message(chat_id, wait_msg.message_id)
                        except Exception:
                            pass
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                        bot.send_message(chat_id,
                            f"⚠️ رصيدك {balance:.2f} روبل — أقل من الحد الأدنى 300 روبل.",
                            reply_markup=markup)
                        return

                    # تحديد المبلغ النهائي
                    final_amount = balance if a_all else min(a_val, balance)

                    post_data = {
                        "withdrawal[user_id]": info.get("user_id", ""),
                        "withdrawal[_csrf_token]": info.get("csrf_token", ""),
                        "withdrawal[amount]": str(final_amount)
                    }
                    r = session.post(WITHDRAWAL_URL, data=post_data, headers=HEADERS, timeout=12)
                    try:
                        bot.delete_message(chat_id, wait_msg.message_id)
                    except Exception:
                        pass

                    if r.status_code == 200:
                        # فحص صفحة النتيجة
                        soup_r = BeautifulSoup(r.text, "html.parser")
                        notif = soup_r.find("div", class_="notification")
                        if notif and "10" in notif.get_text():
                            markup = types.InlineKeyboardMarkup()
                            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                            bot.send_message(chat_id,
                                "🔒 **السحب مقيد — مسموح بسحب واحد كل 10 أيام**.",
                                parse_mode="Markdown", reply_markup=markup)
                        else:
                            markup = types.InlineKeyboardMarkup()
                            markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main"))
                            bot.send_message(chat_id,
                                f"✅ **تم إرسال طلب السحب بنجاح!**\n\n"
                                f"💰 المبلغ: **{final_amount:.2f} روبل**\n"
                                f"📬 إلى: `{info.get('wallet', '')}`\n"
                                f"⏱ المدة المتوقعة: 2-5 أيام عمل",
                                parse_mode="Markdown", reply_markup=markup)
                    else:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                        bot.send_message(chat_id,
                            f"❌ فشل طلب السحب (كود: {r.status_code}).",
                            reply_markup=markup)
                except Exception as e:
                    try:
                        bot.delete_message(chat_id, wait_msg.message_id)
                    except Exception:
                        pass
                    bot.send_message(chat_id, f"❌ خطأ غير متوقع: {e}")

            threading.Thread(target=_do_withdraw, args=(amount_val, withdraw_all), daemon=True).start()
            return

        elif step == 'MANUAL_EXEC_FILL':
            # الحقل 1: رابط العمل — يجب أن يكون URL صالح أو "-"
            if text not in ["-", "لا يوجد", "لايوجد"]:
                if not re.match(r'^https?://', text.strip()):
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"))
                    bot.send_message(chat_id,
                        "⚠️ **رابط غير صالح!**\n\n"
                        "الحقل الأول يجب أن يكون رابط URL صالحاً يبدأ بـ `http://` أو `https://`\n\n"
                        "📎 **أعد إرسال رابط العمل:**\n(أو أرسل `-` إذا لم يكن مطلوباً)",
                        parse_mode="Markdown", reply_markup=markup)
                    return
            work_url_val = "" if text in ["-", "لا يوجد", "لايوجد"] else text
            user_sessions[chat_id]['work_url'] = work_url_val
            user_sessions[chat_id]['step'] = 'MANUAL_EXEC_PROOF'
            task_idx = user_sessions[chat_id].get('task_idx', '')
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"),
            )
            bot.send_message(chat_id,
                "📝 **الحقل 2 — رابط الإثبات:**\n(رابط إثبات التنفيذ أو وصف)",
                parse_mode="Markdown", reply_markup=markup)
            return

        elif step == 'MANUAL_EXEC_NOW_FIELD1':
            # "تنفيذ الآن" — الحقل 1
            # السماح بـ "-" أو رابط URL صالح فقط
            if text not in ["-", "لا يوجد", "لايوجد"]:
                if not re.match(r'^https?://', text.strip()):
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"))
                    bot.send_message(chat_id,
                        "⚠️ **رابط غير صالح!**\n\n"
                        "الحقل الأول يجب أن يكون رابط URL صالحاً يبدأ بـ `http://` أو `https://`\n\n"
                        "📎 **أعد إرسال رابط العمل:**\n(أو أرسل `-` إذا لم يكن مطلوباً)",
                        parse_mode="Markdown", reply_markup=markup)
                    return
            work_url_val = "" if text in ["-", "لا يوجد", "لايوجد"] else text
            user_sessions[chat_id]['work_url'] = work_url_val
            user_sessions[chat_id]['step'] = 'MANUAL_EXEC_NOW_FIELD2'
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"))
            bot.send_message(chat_id,
                "📝 **الحقل 2 — رابط الإثبات:**\n(رابط إثبات التنفيذ أو وصف)",
                parse_mode="Markdown", reply_markup=markup)
            return

        elif step == 'MANUAL_EXEC_NOW_FIELD2':
            # "تنفيذ الآن" — الحقل 2 — تنفيذ فوري
            task = user_sessions[chat_id].get('selected_task', {})
            work_url = user_sessions[chat_id].get('work_url', '')
            proof_msg = text
            del user_sessions[chat_id]

            creds = user_data_store.get(chat_id)
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.")
                return

            wait_msg = bot.send_message(chat_id, "⏳ جاري إرسال التقرير...")

            def _do_now_exec(t, wu, pm):
                try:
                    session = get_authenticated_session(creds['email'], creds['password'])
                    if not session:
                        try: bot.delete_message(chat_id, wait_msg.message_id)
                        except: pass
                        bot.send_message(chat_id, "❌ فشل تجديد الجلسة.")
                        return
                    task_info = get_task_full_description(session, t['task_link'])
                    success = False
                    if task_info and task_info.get('form_action'):
                        success = submit_task_report(session, task_info['form_action'], wu, pm)
                    if not success:
                        task_id_val = t.get('task_id', '')
                        if task_id_val:
                            execute_page_url = f"https://forumok.com/publisher-requests-socio/addRequest/order_id/{task_id_val}?ok=1"
                            success = submit_task_proof_automatically(session, execute_page_url, wu, pm)
                    try: bot.delete_message(chat_id, wait_msg.message_id)
                    except: pass
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="exec_back_to_main"))
                    if success:
                        bot.send_message(chat_id,
                            f"✅ **تم تنفيذ المهمة بنجاح!**\n\n"
                            f"🌐 المنصة: {t['platform']}\n"
                            f"💰 السعر: {t['price']}",
                            parse_mode="Markdown", reply_markup=markup)
                    else:
                        bot.send_message(chat_id, "❌ فشل إرسال التقرير. تحقق من الروابط.", reply_markup=markup)
                except Exception as e:
                    try: bot.delete_message(chat_id, wait_msg.message_id)
                    except: pass
                    bot.send_message(chat_id, f"❌ خطأ: {e}")

            threading.Thread(target=_do_now_exec, args=(task, work_url, proof_msg), daemon=True).start()
            return

        elif step == 'MANUAL_EXEC_PROOF':
            # الحقل 2: رابط الإثبات
            task = user_sessions[chat_id].get('selected_task', {})
            work_url = user_sessions[chat_id].get('work_url', '')
            proof_msg = text
            del user_sessions[chat_id]

            creds = user_data_store.get(chat_id)
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.")
                return

            wait_msg = bot.send_message(chat_id, "⏳ جاري إرسال التقرير...")

            def _do_manual_exec(t, wu, pm):
                try:
                    session = get_authenticated_session(creds['email'], creds['password'])
                    if not session:
                        try: bot.delete_message(chat_id, wait_msg.message_id)
                        except: pass
                        bot.send_message(chat_id, "❌ فشل تجديد الجلسة.")
                        return
                    task_info = get_task_full_description(session, t['task_link'])
                    success = False
                    if task_info and task_info.get('form_action'):
                        success = submit_task_report(session, task_info['form_action'], wu, pm)
                    if not success:
                        # fallback: try addRequest directly
                        task_id_val = t.get('task_id', '')
                        if task_id_val:
                            execute_page_url = f"https://forumok.com/publisher-requests-socio/addRequest/order_id/{task_id_val}?ok=1"
                            success = submit_task_proof_automatically(session, execute_page_url, wu, pm)
                    try: bot.delete_message(chat_id, wait_msg.message_id)
                    except: pass
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="exec_back_to_main"))
                    if success:
                        bot.send_message(chat_id,
                            f"✅ **تم تنفيذ المهمة بنجاح!**\n\n"
                            f"🌐 المنصة: {t['platform']}\n"
                            f"💰 السعر: {t['price']}",
                            parse_mode="Markdown", reply_markup=markup)
                    else:
                        bot.send_message(chat_id, "❌ فشل إرسال التقرير. تحقق من الروابط.", reply_markup=markup)
                except Exception as e:
                    try: bot.delete_message(chat_id, wait_msg.message_id)
                    except: pass
                    bot.send_message(chat_id, f"❌ خطأ: {e}")

            threading.Thread(target=_do_manual_exec, args=(task, work_url, proof_msg), daemon=True).start()
            return

        elif step == 'MANUAL_EXEC_CUSTOM_URL':
            # رابط المهمة اليدوي
            if not text.startswith("http"):
                bot.send_message(chat_id, "❌ يرجى إرسال رابط صحيح يبدأ بـ http")
                return
            user_sessions[chat_id]['custom_task_url'] = text
            user_sessions[chat_id]['step'] = 'MANUAL_EXEC_CUSTOM_WORK_URL'
            # استخراج المنصة من الرابط
            platform = get_platform_from_url(text)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"))
            bot.send_message(chat_id,
                f"✅ رابط المهمة: `{text[:80]}`\n🌐 المنصة: {platform}\n\n"
                f"📎 **أرسل رابط العمل (الحقل 1):**\n(أو `-` إذا لم يوجد)",
                parse_mode="Markdown", reply_markup=markup)
            return

        elif step == 'MANUAL_EXEC_CUSTOM_WORK_URL':
            work_url_val = "" if text in ["-", "لا يوجد", "لايوجد"] else text
            user_sessions[chat_id]['work_url'] = work_url_val
            user_sessions[chat_id]['step'] = 'MANUAL_EXEC_CUSTOM_PROOF'
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="manual_exec_cancel"))
            bot.send_message(chat_id,
                "📝 **أرسل رابط الإثبات (الحقل 2):**",
                parse_mode="Markdown", reply_markup=markup)
            return

        elif step == 'MANUAL_EXEC_CUSTOM_PROOF':
            custom_url = user_sessions[chat_id].get('custom_task_url', '')
            work_url = user_sessions[chat_id].get('work_url', '')
            proof_msg = text
            del user_sessions[chat_id]

            creds = user_data_store.get(chat_id)
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.")
                return

            wait_msg = bot.send_message(chat_id, "⏳ جاري تنفيذ المهمة...")

            def _do_custom_exec(curl, wu, pm):
                try:
                    session = get_authenticated_session(creds['email'], creds['password'])
                    if not session:
                        try: bot.delete_message(chat_id, wait_msg.message_id)
                        except: pass
                        bot.send_message(chat_id, "❌ فشل تجديد الجلسة.")
                        return
                    # normalize url
                    task_url = curl
                    if "?ok=1" not in task_url:
                        task_url += "?ok=1" if "?" not in task_url else "&ok=1"
                    task_info = get_task_full_description(session, task_url)
                    success = False
                    if task_info and task_info.get('form_action'):
                        success = submit_task_report(session, task_info['form_action'], wu, pm)
                    if not success:
                        id_match = re.search(r'/(\d+)/', curl)
                        if id_match:
                            execute_page_url = f"https://forumok.com/publisher-requests-socio/addRequest/order_id/{id_match.group(1)}?ok=1"
                            success = submit_task_proof_automatically(session, execute_page_url, wu, pm)
                    try: bot.delete_message(chat_id, wait_msg.message_id)
                    except: pass
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="exec_back_to_main"))
                    platform = get_platform_from_url(curl)
                    if success:
                        bot.send_message(chat_id,
                            f"✅ **تم تنفيذ المهمة بنجاح!**\n🌐 المنصة: {platform}",
                            parse_mode="Markdown", reply_markup=markup)
                    else:
                        bot.send_message(chat_id, "❌ فشل إرسال التقرير. تحقق من الروابط.", reply_markup=markup)
                except Exception as e:
                    try: bot.delete_message(chat_id, wait_msg.message_id)
                    except: pass
                    bot.send_message(chat_id, f"❌ خطأ: {e}")

            threading.Thread(target=_do_custom_exec, args=(custom_url, work_url, proof_msg), daemon=True).start()
            return

        elif step == 'WITHDRAW_EDIT_WALLET':
            creds = user_data_store.get(chat_id, {})
            new_wallet = text.strip()
            profile = user_sessions[chat_id].get('billing_profile', {})
            del user_sessions[chat_id]
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.")
                return
            if not new_wallet:
                bot.send_message(chat_id, "❌ العنوان لا يمكن أن يكون فارغاً.")
                return

            wait_msg = bot.send_message(chat_id, "⏳ جاري تحديث عنوان المحفظة...")

            def _do_update_wallet(wlt, prof):
                try:
                    session = get_authenticated_session(creds['email'], creds['password'])
                    if not session:
                        try:
                            bot.delete_message(chat_id, wait_msg.message_id)
                        except Exception:
                            pass
                        bot.send_message(chat_id, "❌ فشل تجديد الجلسة.")
                        return
                    # جلب أحدث CSRF إذا لزم
                    csrf = prof.get("csrf_token", "")
                    uid = prof.get("user_id", "")
                    pay_sys = prof.get("pay_system", "webmoney")
                    # تحديد قيمة pay_system
                    pay_sys_val = "webmoney"
                    if "toncoin" in pay_sys.lower() or "telegram" in pay_sys.lower():
                        pay_sys_val = "toncoin"
                    elif "card" in pay_sys.lower() or "карта" in pay_sys.lower():
                        pay_sys_val = "card"

                    success = update_billing_profile(session, pay_sys_val, wlt, csrf, uid)
                    try:
                        bot.delete_message(chat_id, wait_msg.message_id)
                    except Exception:
                        pass
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("💸 فتح قائمة السحب", callback_data="withdraw_menu"))
                    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main"))
                    if success:
                        bot.send_message(chat_id,
                            f"✅ **تم تحديث عنوان المحفظة بنجاح!**\n\n"
                            f"📬 العنوان الجديد: `{wlt}`",
                            parse_mode="Markdown", reply_markup=markup)
                    else:
                        bot.send_message(chat_id, "❌ فشل تحديث عنوان المحفظة.", reply_markup=markup)
                except Exception as e:
                    try:
                        bot.delete_message(chat_id, wait_msg.message_id)
                    except Exception:
                        pass
                    bot.send_message(chat_id, f"❌ خطأ: {e}")

            threading.Thread(target=_do_update_wallet, args=(new_wallet, profile), daemon=True).start()
            return

    if "@" in text and not check_and_load_session_silently(chat_id):
        delete_transient_message(bot, chat_id)
        user_sessions[chat_id] = {'step': 'WAITING_PASSWORD', 'email': text}
        msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
        user_transient_messages[chat_id] = msg.message_id
        return

    if text.isdigit():
        if chat_id not in user_numbered_tasks or not user_numbered_tasks[chat_id]:
            bot.send_message(chat_id, "⚠️ اضغط على زر 'اصطحاب يدوي' أولاً لاستدعاء القائمة:")
            return
        index = int(text) - 1
        if 0 <= index < len(user_numbered_tasks[chat_id]):
            creds = user_data_store.get(chat_id)
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.")
                return
            selected_task = user_numbered_tasks[chat_id][index]

            session = get_authenticated_session(creds['email'], creds['password'])
            if session:
                last_take = last_take_time.get(chat_id, 0)
                if time.time() - last_take < TAKE_COOLDOWN:
                    remaining = int(TAKE_COOLDOWN - (time.time() - last_take))
                    bot.send_message(chat_id, f"⏳ انتظر {remaining} ثانية قبل المحاولة القادمة:")
                    return

                success = take_task_via_post(session, selected_task['task_page'])
                if success:
                    last_take_time[chat_id] = time.time()
                    bot.send_message(chat_id, f"✅ تم اصطحاب المهمة {text}\n💰 السعر: {selected_task['price']} RUB\n⏱️ الوقت: {selected_task['duration']}")

                    if auto_execute_status.get(chat_id, False):
                        saved_templates = cloud_get_auto_tasks(chat_id)
                        task_desc_lower = selected_task.get('description', '').lower()
                        task_url_str = selected_task['task_page'].lower()
                        for tmpl in saved_templates:
                            kw = tmpl['keyword'].lower()
                            if kw in task_desc_lower or kw in task_url_str:
                                order_id_match = re.search(r"/(\d+)/", selected_task['task_page'])
                                if order_id_match:
                                    ord_id = order_id_match.group(1)
                                    execute_page_url = f"https://forumok.com/publisher-requests-socio/addRequest/order_id/{ord_id}?ok=1"
                                    if submit_task_proof_automatically(session, execute_page_url, tmpl.get('work_url'), tmpl.get('proof_msg')):
                                        bot.send_message(chat_id, "✅ تم إرسال تقرير الإثبات تلقائياً بنجاح.")
                                break
                else:
                    bot.send_message(chat_id, f"❌ فشل اصطحاب المهمة {text}")
        else:
            bot.send_message(chat_id, "❌ رقم غير صحيح.")

# ==========================================
# 🖥️ السيرفر المساعد
# ==========================================
class KeepAliveServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("Bot Running".encode("utf-8"))

    def log_message(self, format, *args):
        pass

def run_uptime_server():
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(('', port), KeepAliveServer)
    httpd.serve_forever()

def preload_all_user_settings():
    """
    تحميل بيانات جميع المستخدمين من السحابة عند بدء التشغيل.
    - يقرأ الحسابات الرئيسية من users_accounts
    - يقرأ الحسابات المتعددة من multi_accounts (السحابي — لا تضيع عند إعادة التشغيل)
    - يجهّز البروكسي والجلسة لكل حساب في الخلفية
    """
    try:
        # ── 1: تحميل الحسابات الرئيسية من users_accounts ──
        response = requests.get(DB_API_URL, headers=DB_HEADERS, timeout=10)
        if response.status_code == 200:
            all_accounts = response.json()
            accounts_to_prepare = []
            for account in all_accounts:
                chat_id = account['chat_id']
                if account.get('username') and account.get('password'):
                    user_data_store[chat_id] = {
                        'email': account['username'],
                        'password': account['password']
                    }
                    accounts_to_prepare.append((account['username'], account['password']))
                notify_status[chat_id] = account.get('notify_status', False)
                notify_interval[chat_id] = account.get('notify_interval', 10)
                auto_hunt_status[chat_id] = account.get('auto_hunt_status', False)
                all_notify_status[chat_id] = account.get('all_notify_status', False)
                hunt_mode[chat_id] = account.get('hunt_mode', 'GTE')
                auto_execute_status[chat_id] = account.get('auto_execute_status', False)
                auto_execute_interval[chat_id] = account.get('auto_execute_interval', 5)
                print(f"✅ {chat_id}: إشعارات={notify_status[chat_id]}, اصطحاب={auto_hunt_status[chat_id]}")

            print(f"🎉 تم تحميل {len(all_accounts)} مستخدم من users_accounts")

        # ── 2: تحميل الحسابات المتعددة من multi_accounts (السحابي) ──
        print("☁️ جلب الحسابات المتعددة من Supabase...")
        all_multi = cloud_load_all_multi_accounts()  # يملأ الكاش أيضاً
        total_multi = sum(len(v) for v in all_multi.values())
        print(f"📦 تم جلب {total_multi} حساب متعدد لـ {len(all_multi)} مستخدم")

        # ── 3: تسجيل جميع الحسابات في active_accounts ──
        seen_emails = set()
        for cid, saved_list in all_multi.items():
            for acc in saved_list:
                register_account_in_active(cid, acc['email'], acc['password'])
                e = acc['email'].lower().strip()
                # مزامنة إعدادات الحساب الرئيسي
                if user_data_store.get(cid, {}).get('email', '').lower() == e:
                    sync_chat_settings_to_email(cid, acc['email'])
                else:
                    acct_notify_status.setdefault(e, False)
                    acct_all_notify_status.setdefault(e, False)
                    acct_notify_interval.setdefault(e, 10)
                    acct_auto_hunt_status.setdefault(e, False)
                    acct_hunt_mode.setdefault(e, 'GTE')
                    acct_auto_execute_status.setdefault(e, False)
                    acct_auto_execute_interval.setdefault(e, 5)

        print(f"🔄 الحسابات النشطة: {sum(len(v) for v in active_accounts.values())} حساب")

        # ── 4: تجهيز الجلسات في الخلفية بتأخير تدريجي ──
        # التأخير يوزع الضغط على الخادم بدل إطلاق كل الخيوط دفعة واحدة
        all_accounts_to_prepare = []
        accounts_to_prepare_set = {e.lower() for e, _ in accounts_to_prepare}
        all_accounts_to_prepare.extend(accounts_to_prepare)

        for cid, saved_list in all_multi.items():
            for acc in saved_list:
                e_lower = acc['email'].lower()
                if e_lower not in accounts_to_prepare_set:
                    accounts_to_prepare_set.add(e_lower)
                    all_accounts_to_prepare.append((acc['email'], acc['password']))

        def _staggered_prepare(accounts_list):
            """تجهيز الجلسات بتأخير 3 ثواني بين كل حساب"""
            for i, (email, password) in enumerate(accounts_list):
                if i > 0:
                    time.sleep(3)  # 3 ثواني بين كل حساب
                threading.Thread(
                    target=_prepare_session_with_proxy,
                    args=(email, password),
                    daemon=True
                ).start()

        threading.Thread(target=_staggered_prepare, args=(all_accounts_to_prepare,), daemon=True).start()

    except Exception as e:
        print(f"❌ خطأ في التحميل: {e}")

# ==========================================
# ==========================================
# 📢 إشعار التوقف والاسترداد
# ==========================================
import traceback
import sys

OWNER_CHAT_ID = CAPTCHA_ALERT_CHAT_ID  # يُرسل الإشعار لنفس chat_id المضبوط أعلى

def send_crash_alert(reason: str):
    """إرسال رسالة تيليغرام عند توقف البوت"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = (
        f"🚨 *توقف البوت* 🚨\n"
        f"🕐 الوقت: `{now}`\n"
        f"❌ السبب:\n```\n{reason[:3000]}\n```"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": OWNER_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
    except Exception as e:
        print(f"[ALERT] فشل إرسال إشعار التوقف: {e}")

def send_restart_alert():
    """إشعار عند إعادة التشغيل الناجحة"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"✅ *البوت يعمل مجدداً*\n🕐 وقت الاسترداد: `{now}`"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": OWNER_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
    except Exception:
        pass

def watchdog_thread():
    """مراقب الخيوط — يُعيد تشغيل global_background_worker إذا مات"""
    global t_worker
    while True:
        time.sleep(60)
        if not t_worker.is_alive():
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[WATCHDOG] {now} — background_worker مات، إعادة تشغيل...")
            send_crash_alert("background_worker توقف بشكل غير متوقع — تمت إعادة تشغيله تلقائياً")
            t_worker = threading.Thread(target=global_background_worker, daemon=True)
            t_worker.start()

# ==========================================
# 🚀 نقطة الانطلاق
# ==========================================
if __name__ == "__main__":
    print("🚀 تشغيل نظام إدارة البروكسيات المتكامل...")

    # ── خيط DB المركزي (يعالج كل طلبات الحفظ بدل خيط لكل عملية) ──
    _db_worker_thread2 = threading.Thread(target=_db_save_worker, daemon=True)
    _db_worker_thread2.start()

    # خيط التشغيل الخلفي
    t_worker = threading.Thread(target=global_background_worker, daemon=True)
    t_worker.start()

    # خيط السيرفر المساعد
    t_server = threading.Thread(target=run_uptime_server, daemon=True)
    t_server.start()

    # خيط المراقب
    t_watchdog = threading.Thread(target=watchdog_thread, daemon=True)
    t_watchdog.start()

    # تحميل بيانات المستخدمين
    preload_all_user_settings()

    # تحميل البروكسيات للحسابات النشطة فور التشغيل
    print("🌐 بدء تحميل البروكسيات الديناميكية للحسابات النشطة...")
    threading.Thread(target=refresh_dynamic_proxies, daemon=True).start()

    # تعبئة المخزن الاحتياطي الذكي فور التشغيل
    print("🧠 بدء تعبئة المخزن الاحتياطي للحسابات القادمة...")
    threading.Thread(target=_fill_reserve_pool_worker, daemon=True).start()

    print("✅ البوت يعمل الآن...")
    consecutive_errors = 0

    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                restart_on_change=False,
                none_stop=True,
                interval=0,
                allowed_updates=None
            )
            # إذا خرج infinity_polling بدون استثناء
            consecutive_errors = 0

        except KeyboardInterrupt:
            send_crash_alert("تم إيقاف البوت يدوياً (KeyboardInterrupt)")
            sys.exit(0)

        except Exception as _poll_err:
            consecutive_errors += 1
            error_details = traceback.format_exc()
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[POLLING] {now_str} — خطأ #{consecutive_errors}: {_poll_err}")

            # إرسال إشعار تيليغرام بالخطأ
            send_crash_alert(f"خطأ في infinity_polling (#{consecutive_errors}):\n{error_details}")

            # انتظار تصاعدي حتى 60 ثانية
            wait_time = min(5 * consecutive_errors, 60)
            print(f"[POLLING] إعادة المحاولة خلال {wait_time} ثانية...")
            time.sleep(wait_time)

            # إشعار عند الاسترداد الناجح
            send_restart_alert()