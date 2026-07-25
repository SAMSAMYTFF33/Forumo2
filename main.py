import time
import requests
import random
from bs4 import BeautifulSoup
import threading
import re
import os
import json
import telebot
from telebot import types
import concurrent.futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
import traceback
import sys
import html as html_module

# ==========================================
# ⏳ العد التصاعدي
# ==========================================
BOT_START_TIME = time.time()

def get_countdown_text() -> str:
    try:
        elapsed = time.time() - BOT_START_TIME
        total_minutes = int(elapsed) // 60
        total_hours   = total_minutes // 60

        if total_minutes < 60:
            return f"[{total_minutes}mini]"

        if total_hours < 24:
            return f"[{total_hours}h]"

        days  = total_hours // 24
        hours = total_hours % 24
        if hours > 0:
            return f"[{days} يوم {hours}h]"
        return f"[{days} يوم]"
    except Exception:
        return "[--]"

# ==========================================
# الإعدادات الأساسية
# ==========================================
TELEGRAM_TOKEN = "8691444284:AAHncu1hKOtf16Z9UagyhaPqck1JxkXpA6w"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

CAPTCHA_ALERT_CHAT_ID = 7638322813

BASE_URL      = "https://forumok.com"
LOGIN_URL     = "https://forumok.com/login"
TARGET_URL    = "https://forumok.com/orders-search/socio"
STATS_URL     = "https://forumok.com/publisher-requests/socio/confirmed"
CONFIRMED_URL = "https://forumok.com/publisher-requests/socio/confirmed"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL
}

TAKE_COOLDOWN = 30

# ==========================================
# 🌐 نظام البروكسيات الديناميكي (ProxyScrape)
# ------------------------------------------
# كل حساب (email) بياخد بروكسي خاص بيه دائم، محفوظ في ملف على القرص
# عشان يفضل نفسه حتى لو البوت اتعمله ريستارت. لو البروكسي مات بيتستبدل
# تلقائياً من مخزون بروكسيات جاهزة (مجانية + بروكسيات حسابك المدفوعة لو متاحة).
# ==========================================

# ⚠️ حط المفتاح كـ environment variable، متسيبوش مكتوب هنا في الكود:
#     export PROXYSCRAPE_API_KEY="مفتاحك"
# (بما إن المفتاح ظهر قبل كده في المحادثة، يُفضّل تعمل Regenerate له من لوحة ProxyScrape)
PROXYSCRAPE_API_KEY = os.environ.get("PROXYSCRAPE_API_KEY", "JZ3pweHyZZ9jQm8UnreSczl8vQxwf5tFE7k4aHyd0b6dSm3nSYO6cmgDrh0HqSTR")

PROXYSCRAPE_BASE          = "https://api.proxyscrape.com"
PROXY_TEST_URL            = "https://api.ipify.org?format=json"
PROXY_TEST_TIMEOUT        = 6
PROXY_TEST_WORKERS        = 20
PROXY_ASSIGNMENTS_FILE    = "account_proxies.json"

proxy_lock          = threading.Lock()
assigned_proxies    = {}   # { email_lower: "ip:port" أو "ip:port:user:pass" }
working_proxy_pool  = []   # بروكسيات جاهزة ومُتحقق منها، لسه مش متعيّنة لحد


def _load_proxy_assignments():
    global assigned_proxies
    try:
        if os.path.exists(PROXY_ASSIGNMENTS_FILE):
            with open(PROXY_ASSIGNMENTS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # توافق مع نسخة قديمة كانت بتخزن السطر كـ نص بسيط بدل dict
            migrated = {}
            for email_lower, value in loaded.items():
                if isinstance(value, dict) and "proxy" in value:
                    migrated[email_lower] = value
                elif isinstance(value, str):
                    migrated[email_lower] = {
                        "proxy": value,
                        "ip": value.split(":")[0],
                        "country": "غير معروف",
                    }
            assigned_proxies = migrated
    except Exception as e:
        print(f"[PROXY] فشل تحميل ملف التعيينات: {e}")
        assigned_proxies = {}


def _save_proxy_assignments():
    try:
        with open(PROXY_ASSIGNMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(assigned_proxies, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[PROXY] فشل حفظ ملف التعيينات: {e}")


def _fetch_free_proxies(protocol="http", limit=200):
    url = f"{PROXYSCRAPE_BASE}/v4/free-proxy-list/get"
    params = {
        "request": "getproxies", "protocol": protocol,
        "timeout": 10000, "country": "all", "limit": limit,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return [ln.strip() for ln in r.text.strip().splitlines() if ":" in ln]
    except Exception as e:
        print(f"[PROXY] فشل جلب القائمة المجانية: {e}")
        return []


def _get_subaccounts():
    if not PROXYSCRAPE_API_KEY:
        return []
    url = f"{PROXYSCRAPE_BASE}/v4/account/subaccounts"
    try:
        r = requests.get(url, headers={"api-token": PROXYSCRAPE_API_KEY}, timeout=15)
        if r.status_code != 200:
            print(f"[PROXY] تعذر جلب subaccounts (status {r.status_code})")
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[PROXY] خطأ أثناء جلب subaccounts: {e}")
        return []


def _fetch_account_datacenter_proxies(subaccount_id, protocol="http"):
    url = f"{PROXYSCRAPE_BASE}/v4/account/{subaccount_id}/datacenter_shared/proxy-list"
    params = {"type": "getproxies", "protocol": protocol, "format": "normal"}
    try:
        r = requests.get(url, headers={"api-token": PROXYSCRAPE_API_KEY},
                          params=params, timeout=15)
        if r.status_code != 200:
            return []
        return [ln.strip() for ln in r.text.strip().splitlines() if ":" in ln]
    except Exception:
        return []


def _fetch_account_proxies():
    """يحاول يجيب بروكسيات من أي subaccount مفعّل عنده منتج datacenter."""
    subs = _get_subaccounts()
    if not subs:
        return []
    proxies = []
    for sub in subs:
        if any("datacenter" in p for p in sub.get("products", [])):
            proxies.extend(_fetch_account_datacenter_proxies(sub.get("id")))
    return proxies


def _build_proxy_url(proxy_str):
    """يدعم صيغتين: ip:port  أو  ip:port:user:pass"""
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        return f"http://{user}:{pw}@{ip}:{port}"
    return f"http://{proxy_str}"


def _proxy_ip(proxy_str):
    return proxy_str.split(":")[0]


def _lookup_ip_country(ip):
    """بحث سريع عن بلد الـ IP (بدون مفتاح). بيرجع 'غير معروف' لو الطلب فشل."""
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,country"},
            timeout=5,
        )
        data = r.json()
        if data.get("status") == "success" and data.get("country"):
            return data["country"]
    except Exception:
        pass
    return "غير معروف"


def _test_proxy(proxy_str):
    proxy_url = _build_proxy_url(proxy_str)
    try:
        r = requests.get(PROXY_TEST_URL,
                          proxies={"http": proxy_url, "https": proxy_url},
                          timeout=PROXY_TEST_TIMEOUT)
        return proxy_str, (r.status_code == 200)
    except Exception:
        return proxy_str, False


def _test_many(proxies):
    alive = []
    if not proxies:
        return alive
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROXY_TEST_WORKERS) as ex:
        futures = [ex.submit(_test_proxy, p) for p in proxies]
        for fut in concurrent.futures.as_completed(futures):
            proxy_str, ok = fut.result()
            if ok:
                alive.append(proxy_str)
    return alive


def _target_proxy_count():
    """عدد البروكسيات المطلوب = عدد الحسابات المحفوظة على البوت (مش أكتر).
    لو مسجل 3 حسابات مثلاً، فبمجرد ما نلاقي 3 بروكسيات شغالة نوقف الفحص."""
    emails = set()
    for accs in local_multi_accounts.values():
        for acc in accs:
            emails.add(acc['email'].lower().strip())
    return max(len(emails), 1)


def refresh_proxy_pool():
    """يجيب بروكسيات جديدة ويختبرها، ويوقف الفحص فوراً بمجرد ما يوصل عدد
    البروكسيات الشغّالة (المعيّنة + المتاحة في المخزون) لعدد الحسابات —
    مفيش داعي نفحص أكتر من كده."""
    global working_proxy_pool

    target = _target_proxy_count()
    with proxy_lock:
        have = len(working_proxy_pool) + len(assigned_proxies)
    if have >= target:
        print(f"[PROXY] عدد البروكسيات الشغالة ({have}) يكفي عدد الحسابات ({target}) — تخطي الفحص.")
        return

    candidates = _fetch_free_proxies(limit=max(target * 10, 50))
    if PROXYSCRAPE_API_KEY:
        candidates += _fetch_account_proxies()
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        print("[PROXY] لا توجد بروكسيات جديدة لجلبها الآن.")
        return

    found = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROXY_TEST_WORKERS) as ex:
        futures = [ex.submit(_test_proxy, p) for p in candidates]
        for fut in concurrent.futures.as_completed(futures):
            try:
                proxy_str, ok = fut.result()
            except Exception:
                continue
            if ok:
                with proxy_lock:
                    used     = {info["proxy"] for info in assigned_proxies.values()}
                    pool_set = set(working_proxy_pool)
                    if proxy_str not in used and proxy_str not in pool_set:
                        working_proxy_pool.append(proxy_str)
                        found += 1
                    have_now = len(working_proxy_pool) + len(assigned_proxies)
                if have_now >= target:
                    # وصلنا للعدد المطلوب — نوقف فحص أي بروكسيات باقية فوراً
                    for f in futures:
                        f.cancel()
                    break

    print(f"[PROXY] تم العثور على {found} بروكسي جديد شغال — "
          f"المتاح الآن: {len(working_proxy_pool)} (الهدف: {target})")


def ensure_account_proxy(email, chat_id=None):
    """
    بتتنادى مرة واحدة عند إضافة الحساب (مش وقت الاصطحاب). بتاخد بروكسي
    فريد 100% من المخزون (مبيتشاركش مع أي حساب تاني إطلاقاً)، بتحدد بلد
    الـ IP بتاعه، وبتحفظه كبروكسي دائم لهذا الحساب. لو أصلاً معيّن، بترجّع
    نفس المعلومات من غير ما تاخد بروكسي جديد.
    """
    email_lower = email.lower().strip()

    with proxy_lock:
        existing = assigned_proxies.get(email_lower)
    if existing:
        return existing

    with proxy_lock:
        need_refill = (len(working_proxy_pool) + len(assigned_proxies)) < _target_proxy_count()
    if need_refill:
        refresh_proxy_pool()

    with proxy_lock:
        # ضمان عدم المشاركة إطلاقاً: نسحب بروكسي من المخزون فقط (مش مستخدم
        # عند أي حساب تاني أصلاً)، ونشيله من المخزون فور تعيينه.
        if not working_proxy_pool:
            new_proxy = None
        else:
            new_proxy = working_proxy_pool.pop(0)

    if not new_proxy:
        if chat_id:
            try:
                bot.send_message(
                    chat_id,
                    f"🚫 **لا يوجد بروكسي متاح حالياً**\n\n"
                    f"👤 الحساب: {email_lower.split('@')[0]}\n"
                    f"🛑 لم يُعثر على بروكسي شغّال لتجهيزه لهذا الحساب. سيُعاد المحاولة تلقائياً."
                )
            except Exception:
                pass
        return None

    ip      = _proxy_ip(new_proxy)
    country = _lookup_ip_country(ip)
    info = {"proxy": new_proxy, "ip": ip, "country": country}

    with proxy_lock:
        assigned_proxies[email_lower] = info
        _save_proxy_assignments()

    if chat_id:
        try:
            bot.send_message(
                chat_id,
                f"🌐 **تم تجهيز بروكسي للحساب**\n\n"
                f"👤 {email_lower}\n"
                f"IP: `{ip}`\n"
                f"Country: {country}"
            )
        except Exception:
            pass

    return info


def get_account_proxy_info(email):
    """بيرجع {proxy, ip, country} للحساب لو معيّن له بروكسي، وإلا None.
    للعرض بس — مبيعملش أي تعيين جديد."""
    with proxy_lock:
        return assigned_proxies.get(email.lower().strip())


def get_proxy_for_account(email, chat_id=None, force_new=False):
    """
    يرجّع proxy URL جاهز (يبدأ بـ http://) لاستخدامه مع requests — من غير
    أي فحص استباقي (بينغ لـ ipify) عشان نوفّر موارد الاستضافة المجانية.

    الفلسفة: "شغل ذكي مش شغل مجهود":
      - كل حساب بياخد بروكسي فريد ودائم (عادةً من لحظة إضافة الحساب عبر
        ensure_account_proxy)، ومبيتشاركش مع أي حساب تاني إطلاقاً.
      - الاستخدام الفعلي (اصطحاب مهمة) هو نفسه الفحص. لو فشل فعلاً بسبب
        البروكسي وقت الاستخدام، الكود المستدعي بينادي هنا بـ force_new=True
        فيتغيّر البروكسي — وده بيحصل بس وقت الحاجة الحقيقية.
    """
    email_lower = email.lower().strip()

    if force_new:
        with proxy_lock:
            assigned_proxies.pop(email_lower, None)
        if chat_id:
            try:
                bot.send_message(
                    chat_id,
                    f"⚠️ **تبديل بروكسي**\n\n"
                    f"👤 الحساب: {email_lower.split('@')[0]}\n"
                    f"🔁 البروكسي القديم فشل في الاتصال، جاري تعيين بروكسي جديد..."
                )
            except Exception:
                pass
        info = ensure_account_proxy(email_lower, chat_id=chat_id)
        return _build_proxy_url(info["proxy"]) if info else None

    with proxy_lock:
        current = assigned_proxies.get(email_lower)
    if current:
        return _build_proxy_url(current["proxy"])

    info = ensure_account_proxy(email_lower, chat_id=chat_id)
    return _build_proxy_url(info["proxy"]) if info else None


def _init_proxy_system():
    """تحميل التعيينات المحفوظة + تعبئة أولية للمخزون — بتشتغل في Thread
    منفصل عن استقبال رسائل البوت، عشان البوت يرد فوراً على /start حتى لو
    فحص البروكسيات لسه شغال في الخلفية."""
    _load_proxy_assignments()
    with proxy_lock:
        need_refill = (len(working_proxy_pool) + len(assigned_proxies)) < _target_proxy_count()
    if need_refill:
        refresh_proxy_pool()


def _is_proxy_error(exc) -> bool:
    """هل الاستثناء سببه البروكسي (اتصال/تايم أوت)، عشان نستبدله بدل ما
    نتعامل معاه كخطأ عادي في الموقع نفسه."""
    return isinstance(exc, (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ReadTimeout,
    ))


def _session_has_proxy_attached(session):
    proxy_dict = getattr(session, 'proxies', {})
    if not proxy_dict:
        return False
    return bool(proxy_dict.get("http") or proxy_dict.get("https"))

# ==========================================
# التخزين المحلي (بدون سحابة)
# ==========================================
local_multi_accounts = {}   
local_user_settings  = {}   

def get_saved_multi_accounts(chat_id):
    return local_multi_accounts.get(int(chat_id), [])

def save_multi_account(chat_id, email, password):
    cid = int(chat_id)
    if cid not in local_multi_accounts:
        local_multi_accounts[cid] = []
    email_lower = email.lower().strip()
    for acc in local_multi_accounts[cid]:
        if acc['email'] == email_lower:
            acc['password'] = password
            return True
    local_multi_accounts[cid].append({'email': email_lower, 'password': password})
    return True

def delete_multi_account(chat_id, email):
    cid = int(chat_id)
    if cid in local_multi_accounts:
        local_multi_accounts[cid] = [
            a for a in local_multi_accounts[cid]
            if a['email'] != email.lower().strip()
        ]
    return True

# ==========================================
# متغيرات الحالة العامة
# ==========================================
user_sessions           = {}
user_data_store         = {}   
user_numbered_tasks     = {}
user_transient_messages = {}

user_auth_sessions = {}
auth_sessions_lock = threading.Lock()

logged_out_accounts = {}
logged_out_lock     = threading.Lock()

_handling_blocked      = set()
_handling_blocked_lock = threading.Lock()

active_accounts      = {}
active_accounts_lock = threading.Lock()

acct_auto_hunt_status = {}
acct_hunt_mode        = {}
auto_hunt_status = {}
hunt_mode        = {}
last_take_time   = {}

# ==========================================
# دوال مساعدة للإعدادات
# ==========================================
def get_email_settings(email):
    e = email.lower().strip()
    return {
        'auto_hunt_status': acct_auto_hunt_status.get(e, False),
        'hunt_mode':        acct_hunt_mode.get(e, 'GTE'),
    }

def sync_chat_settings_to_email(chat_id, email):
    e = email.lower().strip()
    acct_auto_hunt_status[e] = auto_hunt_status.get(chat_id, False)
    acct_hunt_mode[e]        = hunt_mode.get(chat_id, 'GTE')

def sync_email_settings_to_chat(chat_id, email):
    e = email.lower().strip()
    auto_hunt_status[chat_id] = acct_auto_hunt_status.get(e, False)
    hunt_mode[chat_id]        = acct_hunt_mode.get(e, 'GTE')

def register_account_in_active(chat_id, email, password):
    with active_accounts_lock:
        if chat_id not in active_accounts:
            active_accounts[chat_id] = {}
        active_accounts[chat_id][email.lower().strip()] = {
            'email': email, 'password': password
        }

# ==========================================
# 🚨 كشف الحظر والـ CAPTCHA
# ==========================================
def detect_page_state(html_text):
    if not html_text:
        return None
    html_lower = html_text.lower()
    blocked_sigs = ["заблокирован", "аккаунт заблокирован",
                    "account is blocked", "account blocked"]
    for s in blocked_sigs:
        if s in html_lower:
            return "blocked"
    captcha_sigs = ["recaptcha", "g-recaptcha", "captcha",
                    "i am not a robot", "я не робот",
                    "cloudflare", "cf-challenge", "challenge-form"]
    for s in captcha_sigs:
        if s in html_lower:
            return "captcha"
    if "login-box" in html_lower and "Выход" not in html_text:
        return "captcha"
    return None

def handle_blocked_account(email, chat_id_origin=None):
    email_lower = email.lower().strip()
    with _handling_blocked_lock:
        if email_lower in _handling_blocked:
            return
        _handling_blocked.add(email_lower)
    try:
        account_label = email_lower.split("@")[0]
        acct_auto_hunt_status[email_lower] = False
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)

        affected_chats = []
        with active_accounts_lock:
            for cid, accounts in active_accounts.items():
                if email_lower in accounts:
                    affected_chats.append(cid)

        blocked_msg = (
            f"🚫 **تنبيه: حساب محظور**\n\n"
            f"⛔ الحساب **{account_label}** (`{email_lower}`) تعرّض للحظر.\n"
            f"📌 تم تسجيل الخروج وحذفه تلقائياً."
        )
        for cid in affected_chats:
            with active_accounts_lock:
                if cid in active_accounts:
                    active_accounts[cid].pop(email_lower, None)
            delete_multi_account(cid, email_lower)
            with logged_out_lock:
                if cid not in logged_out_accounts:
                    logged_out_accounts[cid] = set()
                logged_out_accounts[cid].add(email_lower)
            active_email = user_data_store.get(cid, {}).get("email", "").lower().strip()
            if active_email == email_lower:
                for store in [user_data_store, user_sessions, user_numbered_tasks,
                               auto_hunt_status, hunt_mode, last_take_time]:
                    store.pop(cid, None)
            try:
                bot.send_message(cid, blocked_msg, parse_mode="Markdown")
            except Exception:
                pass
    finally:
        def _clear():
            time.sleep(120)
            with _handling_blocked_lock:
                _handling_blocked.discard(email_lower)
        threading.Thread(target=_clear, daemon=True).start()

def handle_captcha_detected(email, context=""):
    email_lower = email.lower().strip()
    account_label = email_lower.split("@")[0]
    acct_auto_hunt_status[email_lower] = False
    with auth_sessions_lock:
        user_auth_sessions.pop(email_lower, None)
    captcha_msg = (
        f"🤖 **تنبيه: CAPTCHA ظهر!**\n\n"
        f"🔐 الحساب: **{account_label}** (`{email_lower}`)\n"
        f"⚠️ يجب حل التحقق يدوياً."
    )
    try:
        bot.send_message(CAPTCHA_ALERT_CHAT_ID, captcha_msg, parse_mode="Markdown")
    except Exception:
        pass

# ==========================================
# إنشاء الجلسات
# ==========================================
def _safe_get(url, session=None, retries=3, **kwargs):
    req = session or requests
    kwargs.setdefault("timeout", 15)
    for i in range(retries):
        try:
            return req.get(url, **kwargs)
        except requests.exceptions.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))

def get_authenticated_session(username, password, chat_id=None):
    email_lower = username.lower().strip()

    with auth_sessions_lock:
        cached = user_auth_sessions.get(email_lower)
    if cached:
        try:
            test_r = cached.get(BASE_URL, headers=HEADERS, timeout=8)
            page_state = detect_page_state(test_r.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
                with auth_sessions_lock:
                    user_auth_sessions.pop(email_lower, None)
                return None
            if page_state == "captcha":
                threading.Thread(target=handle_captcha_detected,
                                 args=(username, "التحقق من الجلسة"), daemon=True).start()
                with auth_sessions_lock:
                    user_auth_sessions.pop(email_lower, None)
                return None
            if "Выход" in test_r.text:
                return cached
        except Exception:
            pass
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)

    # 🌐 تسجيل الدخول وجلب المهام دايماً اتصال عادي من غير بروكسي — زي أي حساب
    # تاني بالظبط. البروكسي بيتفعّل بس وقت اصطحاب المهمة نفسها (take_task_via_post).
    sess = requests.Session()

    login_data = {
        "signin[username]": username,
        "signin[password]": password,
        "signin[remember]": "1",
        "signin[refer_url]": "@office_initial"
    }
    try:
        sess.get(BASE_URL, headers=HEADERS, timeout=12)
        lr = sess.post(LOGIN_URL, data=login_data, headers=HEADERS, timeout=12)
        if lr.status_code == 200:
            page_state = detect_page_state(lr.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account,
                                 args=(username,), daemon=True).start()
                return None
            if page_state == "captcha":
                threading.Thread(target=handle_captcha_detected,
                                 args=(username, "تسجيل الدخول"), daemon=True).start()
                return None
            if "Выход" in lr.text:
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = sess
                return sess
    except Exception:
        pass
    return None

# ==========================================
# استخراج البيانات
# ==========================================
def translate_and_parse_duration(duration_text):
    duration_text = duration_text.strip().lower()
    try:
        m = re.search(r"(\d+)", duration_text)
        if not m:
            return 120, "2 ساعات"
        number = int(m.group(1))
        if any(x in duration_text for x in ["день", "дня", "дней"]):
            total_minutes = number * 24 * 60
            text = "1 يوم" if number == 1 else f"{number} أيام"
        elif any(x in duration_text for x in ["час", "часа", "часов"]):
            total_minutes = number * 60
            text = "1 ساعة" if number == 1 else f"{number} ساعات"
        elif any(x in duration_text for x in ["минут", "минуты", "минутку"]):
            total_minutes = number
            text = "1 دقيقة" if number == 1 else f"{number} دقائق"
        else:
            total_minutes = number * 60
            text = f"{number} ساعات"
        return total_minutes, text
    except Exception:
        return 120, "2 ساعات"

def fetch_publisher_stats(session):
    stats = {"to_execute": "0", "on_check": "0", "completed": "0"}
    try:
        r = session.get(STATS_URL, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            page_text = r.text
            m = re.search(r"Выполнить\s+(\d+)", page_text)
            if m:
                stats["to_execute"] = m.group(1)
            m = re.search(r"На проверке\s+(\d+)", page_text)
            if m:
                stats["on_check"] = m.group(1)
            m = re.search(r"Выполнено\s+(\d+)", page_text)
            if m:
                stats["completed"] = m.group(1)
    except Exception:
        pass
    return stats

def get_site_data(username, password, chat_id):
    session = get_authenticated_session(username, password, chat_id)
    if not session:
        return None, "AUTH_FAILED"
    try:
        r = _safe_get(TARGET_URL, session=session, headers=HEADERS, timeout=12)
        page_state = detect_page_state(r.text)
        if page_state == "blocked":
            threading.Thread(target=handle_blocked_account,
                             args=(username,), daemon=True).start()
            return None, "BLOCKED"
        if page_state == "captcha":
            threading.Thread(target=handle_captcha_detected,
                             args=(username, "جلب المهام"), daemon=True).start()
            return None, "CAPTCHA"
        if "Выход" not in r.text:
            return None, "SESSION_EXPIRED"

        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(separator="\n")

        balance = "0.0"
        m = re.search(r"Доступно:\s*([\d.,\s]+)\s*р\.", page_text)
        if m:
            balance = m.group(1).strip()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            stats_future = ex.submit(fetch_publisher_stats, session)

            PLATFORM_MAP = {
                "youtube": "YouTube", "telegram": "Telegram",
                "yandex": "Yandex", "google": "Google",
                "vkontakte": "VKontakte", "vk": "VKontakte",
                "instagram": "Instagram", "tiktok": "TikTok",
                "twitter": "Twitter", "facebook": "Facebook", "ok": "OK",
            }

            tasks_list = []
            tbody = soup.find("tbody", class_="td-order-search")
            rows = tbody.find_all("tr", id=re.compile(r"^tr\d+")) if tbody else []

            for row in rows:
                try:
                    row_classes = row.get("class", []) or []
                    if "taken-list" in row_classes or "gray-list" in row_classes:
                        continue

                    cells = row.find_all("td")
                    if len(cells) < 9:
                        continue

                    action_cell = cells[-1]
                    take_link = action_cell.find("a", href=True)
                    if not take_link or action_cell.find("img", alt="take") is None:
                        continue

                    take_href = take_link.get("href", "")
                    task_page_url = (take_href if take_href.startswith("http")
                                     else BASE_URL + take_href)
                    if "?ok=1" not in task_page_url:
                        task_page_url += ("?ok=1" if "?" not in task_page_url
                                          else "&ok=1")

                    price_raw = cells[3].get_text(strip=True).replace(",", ".").replace(" ", "")
                    try:
                        real_price = float(price_raw)
                    except ValueError:
                        continue

                    country_img = cells[4].find("img")
                    country_code = country_img.get("alt", "--") if country_img else "--"

                    raw_duration = "2 часа"
                    task_desc = ""
                    info_img = cells[2].find("img", class_="cursor-help")
                    if info_img:
                        raw_content = html_module.unescape(info_img.get("content", ""))
                        mini = BeautifulSoup(raw_content, "html.parser")
                        for small in mini.find_all("small"):
                            if "Время на выполнение" in small.get_text():
                                b = small.find("b")
                                if b:
                                    raw_duration = b.get_text(strip=True)
                        parts = [tag.get_text(separator=" ", strip=True)
                                 for tag in mini.find_all(["p", "li"])
                                 if tag.get_text(strip=True)]
                        task_desc = " ".join(parts)

                    task_minutes, arabic_duration = translate_and_parse_duration(raw_duration)

                    plat_img = cells[1].find("img")
                    platform_key = plat_img.get("alt", "").lower().strip() if plat_img else ""
                    app_name = PLATFORM_MAP.get(platform_key, "منصة أخرى")

                    is_restricted = "غير مقيدة"
                    restrictions_details = ""
                    task_desc_check = task_desc.lower()
                    if country_code not in ("", "--", "---"):
                        is_restricted = "مقيدة"
                        restrictions_details = country_code
                    elif any(x in task_desc_check for x in
                             ["россия", "russia", "только для рф", "рф"]):
                        is_restricted = "مقيدة"
                        restrictions_details = "روسيا"

                    tasks_list.append({
                        "price": f"{real_price:.2f}",
                        "task_page": task_page_url,
                        "duration": arabic_duration,
                        "minutes": task_minutes,
                        "description": task_desc,
                        "app_name": app_name,
                        "is_restricted": is_restricted,
                        "restrictions": restrictions_details,
                    })
                except Exception:
                    continue

            try:
                stats_data = stats_future.result(timeout=8)
            except Exception:
                stats_data = {"to_execute": "0", "on_check": "0", "completed": "0"}

        user_numbered_tasks[chat_id] = tasks_list
        return {"balance": balance, "stats": stats_data, "tasks": tasks_list}, "SUCCESS"
    except Exception:
        return None, "ERROR"

def take_task_via_post(session, task_page_url, email=None, chat_id=None):
    try:
        try:
            response = session.get(task_page_url, headers=HEADERS, timeout=10)
        except Exception as e:
            if email and _is_proxy_error(e):
                retry_proxy = get_proxy_for_account(email, chat_id=chat_id, force_new=True)
                if not retry_proxy:
                    return "FAILED"
                session.proxies = {"http": retry_proxy, "https": retry_proxy}
                response = session.get(task_page_url, headers=HEADERS, timeout=10)
            else:
                return "FAILED"
        if response.status_code != 200:
            return "FAILED"

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text()

        not_available = ["нет заданий", "no tasks", "задание недоступно",
                         "order not found", "not found", "404"]
        for sig in not_available:
            if sig in page_text.lower():
                return "FAILED"

        form = soup.find("form", action=re.compile(r"batch|order_request"))
        if not form:
            return "FAILED"

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
            return "FAILED"

        res = session.post(post_action_url, data=post_data, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return "FAILED"

        response_text = res.text

        if "задание уже выполняется" in response_text:
            return "SAME_IP"

        if "Аккаунты не выбраны" in response_text:
            return "ALREADY_TAKEN"

        if "взяли задание в работу" in response_text:
            return "SUCCESS"

        return "FAILED"
    except Exception:
        return "FAILED"

# ==========================================
# 🔥 الواجهات
# ==========================================
def get_auth_menu(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if chat_id:
        saved = get_saved_multi_accounts(chat_id)
        for i, acc in enumerate(saved, 1):
            label = acc['email'].split('@')[0]
            markup.add(types.InlineKeyboardButton(
                f"⚡ الدخول المباشر: الحساب {i} ({label})",
                callback_data=f"switch_acc_{i-1}"
            ))
    markup.add(types.InlineKeyboardButton(
        "🔐 تسجيل الدخول بحساب جديد", callback_data="login_start"
    ))
    return markup

def get_main_menu_text(chat_id=None) -> str:
    text = f"🏠 القائمة الرئيسية  {get_countdown_text()}\nــــــــــــــــــ"
    if chat_id and chat_id in user_data_store:
        email = user_data_store[chat_id].get('email', '')
        if email:
            info = get_account_proxy_info(email)
            text += f"\n{email}"
            if info:
                text += f"\nIp: {info.get('ip', '?')}\nCountry: {info.get('country', 'غير معروف')}"
            else:
                text += "\n⏳ جاري تجهيز البروكسي..."
    return text

def get_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    user_label = "غير محدد"
    if chat_id in user_data_store:
        email = user_data_store[chat_id].get('email', '')
        if "@" in email:
            user_label = email.split('@')[0]
    markup.add(types.InlineKeyboardButton(
        f"👤 الحساب الحالي: {user_label} 🔄",
        callback_data="switch_account_menu"
    ))
    markup.add(types.InlineKeyboardButton(
        "📋 عرض المهام المتاحة وتحديثها", callback_data="view_tasks"
    ))
    markup.add(types.InlineKeyboardButton(
        "🎯 اصطحاب للعمل (GT / GTE)", callback_data="take_work_menu"
    ))
    return markup

def get_switch_account_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    saved = get_saved_multi_accounts(chat_id)
    current_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
    with logged_out_lock:
        lo_set = set(logged_out_accounts.get(chat_id, set()))
    for i, acc in enumerate(saved, 1):
        email = acc['email']
        label = email.split('@')[0]
        e = email.lower().strip()
        if e == current_email:
            icon = "✅"
        elif e in lo_set:
            icon = "💤"
        else:
            icon = "⚡" if acct_auto_hunt_status.get(e, False) else "🔘"
        markup.add(types.InlineKeyboardButton(
            f"{icon} الحساب {i}: {label}",
            callback_data=f"switch_acc_{i-1}"
        ))
    markup.add(types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="add_new_account"))
    markup.add(types.InlineKeyboardButton("🗑️ حذف حساب", callback_data="delete_account_start"))
    markup.add(types.InlineKeyboardButton("🚪 تسجيل الخروج", callback_data="logout"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return markup

def get_take_work_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    current_mode = hunt_mode.get(chat_id, "GTE")
    is_active    = auto_hunt_status.get(chat_id, False)
    icon_gt  = "🟢" if (is_active and current_mode == "GT")  else "🔴"
    icon_gte = "🟢" if (is_active and current_mode == "GTE") else "🔴"
    markup.add(types.InlineKeyboardButton(
        f"اصطحاب > 2 ساعات  {icon_gt}", callback_data="toggle_gt"
    ))
    markup.add(types.InlineKeyboardButton(
        f"اصطحاب >= 2 ساعات  {icon_gte}", callback_data="toggle_gte"
    ))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return markup

# ==========================================
# 🔄 الخيط الخلفي
# ==========================================
_bg_last_hunt = {}
_bg_last_take = {}

HUNT_INTERVAL_SECONDS = 80  # مهلة جلب المهام لكل حساب

def recompute_hunt_stagger(chat_id):
    """
    توزّع بداية دورة الـ80 ثانية بالتساوي بين حسابات نفس الشات، ميكانيكيًا:
    لو عندك N حساب، الفرق بين بداية كل حساب واللي بعده = 80/N ثانية،
    مع بقاء كل حساب بيتفحص كل 80 ثانية بالظبط زي ما هو.
    مثال (N=4): حساب1 فورًا، حساب2 بعد 20ث، حساب3 بعد 40ث، حساب4 بعد 60ث.
    بتتنادى تلقائيًا كل ما يتضاف أو يتحذف حساب في الشات.
    """
    saved = get_saved_multi_accounts(chat_id)
    n = len(saved)
    if n == 0:
        return
    spacing = HUNT_INTERVAL_SECONDS / n
    now = time.time()
    for i, acc in enumerate(saved):
        email_lower = acc['email']  # متخزن بالفعل lower-case في save_multi_account
        key = (chat_id, email_lower)
        offset = i * spacing
        # أول فحص لهذا الحساب هيحصل تحديدًا بعد offset ثانية من دلوقتي
        _bg_last_hunt[key] = now - (HUNT_INTERVAL_SECONDS - offset)


def _wake_other_accounts(chat_id, current_email_lower):
    """
    لما حساب يكتشف مهمة موجودة فعلاً، الدالة دي بتخلي باقي حسابات نفس
    الشات تحاول تصطحب فورًا (في أقرب دورة فحص خلال 5 ثواني بالأكتر)، من
    غير ما تستنى الـ80 ثانية بتاعتها تكتمل.
    """
    with active_accounts_lock:
        accounts = dict(active_accounts.get(chat_id, {}))
    for email_key in accounts.keys():
        if email_key == current_email_lower:
            continue
        _bg_last_hunt[(chat_id, email_key)] = 0


_same_ip_blocked_tasks = {}
_same_ip_blocked_lock  = threading.Lock()
SAME_IP_BLOCK_EXPIRY   = 12 * 3600  


def _is_task_blocked(email_lower, task_id):
    now = time.time()
    with _same_ip_blocked_lock:
        acc_map = _same_ip_blocked_tasks.get(email_lower)
        if not acc_map:
            return False

        expired = [tid for tid, added_at in acc_map.items()
                   if now - added_at >= SAME_IP_BLOCK_EXPIRY]
        for tid in expired:
            acc_map.pop(tid, None)
        if not acc_map:
            _same_ip_blocked_tasks.pop(email_lower, None)
            return False

        return task_id in acc_map


def _add_blocked_task(email_lower, task_id):
    with _same_ip_blocked_lock:
        _same_ip_blocked_tasks.setdefault(email_lower, {})[task_id] = time.time()


def _extract_task_id(task_page_url):
    m = re.search(r"/create-request/(\d+)", task_page_url)
    if m:
        return m.group(1)
    m = re.search(r"/order[_/](\d+)", task_page_url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)/?(?:\?|$)", task_page_url)
    if m:
        return m.group(1)
    return task_page_url  

def _bg_process_one_account_inner(chat_id, email, password, current_time):
    e = email.lower().strip()
    key = (chat_id, e)
    settings = get_email_settings(email)

    if settings['auto_hunt_status']:
        last_take = _bg_last_take.get(key, 0)
        if current_time - last_take >= TAKE_COOLDOWN:
            if current_time - _bg_last_hunt.get(key, 0) >= HUNT_INTERVAL_SECONDS:
                _bg_last_hunt[key] = current_time
                data, status = get_site_data(email, password, chat_id)
                if status == "SUCCESS" and data and data['tasks']:
                    # 🔔 فيه مهمة موجودة فعلاً — نبّه باقي حسابات نفس الشات
                    # يحاولوا يصطحبوا فورًا من غير انتظار دورتهم الطبيعية.
                    _wake_other_accounts(chat_id, e)
                    mode = settings['hunt_mode']
                    for target_task in data['tasks']:
                        task_id = _extract_task_id(target_task['task_page'])
                        if _is_task_blocked(e, task_id):
                            continue  

                        task_minutes = target_task.get('minutes', 120)
                        should_take = ((mode == "GT"  and task_minutes > 120) or
                                       (mode == "GTE" and task_minutes >= 120))
                        if should_take:
                            session = get_authenticated_session(email, password, chat_id)
                            if session:
                                # تأكيد إن البروكسي الخاص بالحساب لسه مرتبط بالجلسة قبل الاصطحاب
                                proxy_url = get_proxy_for_account(e, chat_id=chat_id)
                                if proxy_url:
                                    session.proxies = {"http": proxy_url, "https": proxy_url}

                                if not _session_has_proxy_attached(session):
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"🚫 **تنبيه: تعذّر الاصطحاب**\n\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"🛑 لا يوجد اتصال ناجح بأي بروكسي حالياً، ولن يتم الاصطحاب بالـ IP الأصلي إطلاقاً.\n"
                                            f"🔁 سيُعاد المحاولة تلقائياً عند توفر بروكسي شغّال."
                                        )
                                    except Exception:
                                        pass
                                    break

                                take_status = take_task_via_post(
                                    session, target_task['task_page'],
                                    email=e, chat_id=chat_id
                                )
                                if take_status == "SUCCESS":
                                    _bg_last_take[key] = time.time()
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚡ تم اصطحاب مهمة تلقائياً!\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"💰 السعر: {target_task['price']} RUB\n"
                                            f"⏱️ الوقت: {target_task['duration']}"
                                        )
                                    except Exception:
                                        pass
                                elif take_status == "SAME_IP":
                                    _add_blocked_task(e, task_id)
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚠️ **تنبيه: نفس عنوان IP**\n\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"🆔 رقم المهمة: {task_id}\n"
                                            f"🛑 الموقع رفض الاصطحاب لأن نفس الـ IP يستخدمه حساب آخر لديك في مهمة قيد التنفيذ حالياً.\n"
                                            f"🚫 لن يُعاد تجربة هذه المهمة من هذا الحساب لمدة 12 ساعة."
                                        )
                                    except Exception:
                                        pass
                                elif take_status == "ALREADY_TAKEN":
                                    _add_blocked_task(e, task_id)
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚠️ **تنبيه: هذه المهمة نُفّذت من قبل**\n\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"🆔 رقم المهمة: {task_id}\n"
                                            f"🛑 الموقع لم يعرض أي حساب للاختيار، لأن هذا الحساب سبق ونفّذ هذه المهمة تحديداً من قبل.\n"
                                            f"🚫 لن يُعاد تجربة هذه المهمة من هذا الحساب لمدة 12 ساعة."
                                        )
                                    except Exception:
                                        pass
                                # ↩️ رجّع الجلسة لاتصال عادي بعد محاولة الاصطحاب —
                                # البروكسي بيتفعّل بس لحظة الاصطحاب نفسها.
                                session.proxies = {}
                            break

def global_background_worker():
    while True:
        try:
            current_time = time.time()
            with active_accounts_lock:
                snapshot = {cid: dict(accs) for cid, accs in active_accounts.items()}
            for chat_id, accounts in snapshot.items():
                for email_key, creds in accounts.items():
                    try:
                        _bg_process_one_account_inner(
                            chat_id, creds['email'], creds['password'], current_time
                        )
                    except Exception as ex:
                        print(f"[BG] خطأ في {email_key}: {ex}")
        except Exception as e:
            print(f"[BG] خطأ عام: {e}")
        time.sleep(5)

# ==========================================
# 📞 معالجة Callbacks
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_all_inline_callbacks(call):
    try:
        _handle_callback_inner(call)
    except Exception as err:
        print(f"[CALLBACK] خطأ: {err}")
        try:
            bot.answer_callback_query(call.id, "⚠️ حدث خطأ.")
        except Exception:
            pass

def _handle_callback_inner(call):
    chat_id    = call.message.chat.id
    data       = call.data
    message_id = call.message.message_id

    if chat_id in user_sessions:
        step = user_sessions[chat_id].get('step', '')
        if step in ['WAITING_EMAIL', 'WAITING_PASSWORD', 'WAITING_DELETE_ACCOUNT']:
            del user_sessions[chat_id]

    if data.startswith("switch_acc_"):
        idx  = int(data.replace("switch_acc_", ""))
        saved = get_saved_multi_accounts(chat_id)
        if 0 <= idx < len(saved):
            acc = saved[idx]
            new_email_lower = acc['email'].lower().strip()
            old_email = user_data_store.get(chat_id, {}).get('email', '')
            if old_email:
                sync_chat_settings_to_email(chat_id, old_email)
            user_data_store[chat_id] = {'email': acc['email'], 'password': acc['password']}
            register_account_in_active(chat_id, acc['email'], acc['password'])
            with logged_out_lock:
                if chat_id in logged_out_accounts:
                    logged_out_accounts[chat_id].discard(new_email_lower)
            sync_email_settings_to_chat(chat_id, acc['email'])
            with auth_sessions_lock:
                cached = user_auth_sessions.get(new_email_lower)
            if not cached:
                threading.Thread(
                    target=lambda: get_authenticated_session(acc['email'], acc['password'], chat_id),
                    daemon=True
                ).start()
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_text(
                    get_main_menu_text(chat_id), chat_id, message_id,
                    reply_markup=get_main_menu(chat_id)
                )
            except Exception:
                bot.send_message(chat_id, get_main_menu_text(chat_id),
                                 reply_markup=get_main_menu(chat_id))
        else:
            bot.answer_callback_query(call.id, "⚠️ خطأ.", show_alert=True)

    elif data == "switch_account_menu":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "🔄 **إدارة الحسابات**\nاختر حساباً أو أضف جديداً:\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_switch_account_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "add_new_account":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني للحساب الجديد:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}

    elif data == "delete_account_start":
        bot.answer_callback_query(call.id)
        saved = get_saved_multi_accounts(chat_id)
        if not saved:
            bot.answer_callback_query(call.id, "⚠️ لا توجد حسابات.", show_alert=True)
            return
        lines = ["🗑️ **حذف حساب**\n\nأرسل **رقم الحساب** للحذف:\n"]
        for i, acc in enumerate(saved, 1):
            lines.append(f"  {i}. {acc['email'].split('@')[0]}")
        lines.append("\nأو أرسل **إلغاء** للرجوع.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "\n".join(lines),
                               parse_mode="Markdown", reply_markup=markup)
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_DELETE_ACCOUNT'}

    elif data == "login_start":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}

    elif data == "logout":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        email_to_logout = creds.get('email', '').lower().strip()
        if email_to_logout:
            with auth_sessions_lock:
                user_auth_sessions.pop(email_to_logout, None)
            acct_auto_hunt_status[email_to_logout] = False
            with logged_out_lock:
                if chat_id not in logged_out_accounts:
                    logged_out_accounts[chat_id] = set()
                logged_out_accounts[chat_id].add(email_to_logout)
        for store in [user_data_store, user_sessions, user_numbered_tasks,
                      auto_hunt_status, hunt_mode, last_take_time]:
            store.pop(chat_id, None)
        try:
            bot.edit_message_text(
                "🚪 **تم تسجيل الخروج بنجاح**",
                chat_id, message_id,
                reply_markup=get_auth_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "back_main":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                get_main_menu_text(chat_id), chat_id, message_id,
                reply_markup=get_main_menu(chat_id)
            )
        except Exception:
            pass

    elif data == "view_tasks":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id)
        if not creds:
            try:
                bot.edit_message_text(
                    "⚠️ يرجى تسجيل الدخول أولاً.",
                    chat_id, message_id,
                    reply_markup=get_auth_menu(chat_id)
                )
            except Exception:
                pass
            return
        try:
            bot.edit_message_text("⏳ جارٍ جلب المهام...", chat_id, message_id)
        except Exception:
            pass

        def _do_view():
            result, status = get_site_data(creds['email'], creds['password'], chat_id)
            if status == "SUCCESS":
                msg = (f"💰 **الرصيد:** `{result['balance']}` RUB\n\n"
                       f"📌 **المهام الصالحة:**\n")
                if result['tasks']:
                    for i, t in enumerate(result['tasks'][:10], 1):
                        restricted_icon = "🔒" if t['is_restricted'] == "مقيدة" else "🌐"
                        msg += (f"🔢 {i} ➖ {t['price']} RUB"
                                f" | {t['duration']}"
                                f" | {t['app_name']}"
                                f" {restricted_icon}\n")
                else:
                    msg += "🟢 لا توجد مهام صالحة حالياً.\n"
                msg += (f"\n📊 **الإحصائيات:**\n"
                        f"🟡 قيد التنفيذ: {result['stats']['to_execute']}\n"
                        f"🔵 قيد المراجعة: {result['stats']['on_check']}\n"
                        f"✅ مكتملة: {result['stats']['completed']}")
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="view_tasks"))
                markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                try:
                    bot.edit_message_text(msg, chat_id, message_id,
                                         parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    bot.send_message(chat_id, msg,
                                     parse_mode="Markdown", reply_markup=markup)
            else:
                err_markup = types.InlineKeyboardMarkup()
                err_markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                try:
                    bot.edit_message_text("⚠️ فشل جلب البيانات.",
                                          chat_id, message_id, reply_markup=err_markup)
                except Exception:
                    pass

        threading.Thread(target=_do_view, daemon=True).start()

    elif data == "take_work_menu":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "⚡ **خيارات اصطحاب المهام**\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_take_work_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "toggle_gt":
        bot.answer_callback_query(call.id)
        current_active = auto_hunt_status.get(chat_id, False)
        current_mode   = hunt_mode.get(chat_id, "")

        if current_active and current_mode == "GT":
            auto_hunt_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تصيد (أكبر من ساعتين) لجميع الحسابات المحفوظة"
        else:
            auto_hunt_status[chat_id] = True
            hunt_mode[chat_id] = "GT"
            status_msg = "✅ تم تفعيل تصيد (أكبر من ساعتين) لجميع الحسابات المحفوظة"

        saved_accounts = get_saved_multi_accounts(chat_id)
        for acc in saved_accounts:
            sync_chat_settings_to_email(chat_id, acc['email'])

        try:
            bot.edit_message_text(
                f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_take_work_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "toggle_gte":
        bot.answer_callback_query(call.id)
        current_active = auto_hunt_status.get(chat_id, False)
        current_mode   = hunt_mode.get(chat_id, "")

        if current_active and current_mode == "GTE":
            auto_hunt_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تصيد (ساعتين فما فوق) لجميع الحسابات المحفوظة"
        else:
            auto_hunt_status[chat_id] = True
            hunt_mode[chat_id] = "GTE"
            status_msg = "✅ تم تفعيل تصيد (ساعتين فما فوق) لجميع الحسابات المحفوظة"

        saved_accounts = get_saved_multi_accounts(chat_id)
        for acc in saved_accounts:
            sync_chat_settings_to_email(chat_id, acc['email'])

        try:
            bot.edit_message_text(
                f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_take_work_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

# ==========================================
# 📨 معالجة الرسائل
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_bot_logic(message):
    try:
        _handle_message_inner(message)
    except Exception as err:
        print(f"[MESSAGE] خطأ: {err}")
        try:
            bot.send_message(message.chat.id, "⚠️ حدث خطأ، حاول مجدداً.")
        except Exception:
            pass

def _handle_message_inner(message):
    chat_id = message.chat.id
    text    = message.text.strip() if message.text else ""

    if text.lower() not in ["/start", "start"]:
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

    if text.lower() in ["/start", "start"]:
        remove_kb = types.ReplyKeyboardRemove()
        if chat_id in user_data_store or get_saved_multi_accounts(chat_id):
            bot.send_message(chat_id, "مرحباً ⚙️", reply_markup=remove_kb)
            bot.send_message(chat_id, get_main_menu_text(chat_id),
                             reply_markup=get_main_menu(chat_id))
        else:
            bot.send_message(chat_id, "مرحباً.", reply_markup=remove_kb)
            bot.send_message(chat_id, "⚙️ سجّل الدخول للبدء:",
                             reply_markup=get_auth_menu(chat_id))
        return

    if chat_id in user_sessions:
        step = user_sessions[chat_id]['step']

        if step == 'WAITING_EMAIL':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            user_sessions[chat_id]['email'] = text
            user_sessions[chat_id]['step']  = 'WAITING_PASSWORD'
            msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
            user_transient_messages[chat_id] = msg.message_id
            return

        elif step == 'WAITING_PASSWORD':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            email    = user_sessions[chat_id]['email']
            password = text
            del user_sessions[chat_id]
            email_lower = email.lower().strip()

            status_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الحساب...")
            session = get_authenticated_session(email, password, chat_id)
            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass

            if session:
                user_data_store[chat_id] = {'email': email, 'password': password}
                save_multi_account(chat_id, email, password)
                register_account_in_active(chat_id, email, password)
                sync_chat_settings_to_email(chat_id, email)
                recompute_hunt_stagger(chat_id)
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = session
                with logged_out_lock:
                    if chat_id in logged_out_accounts:
                        logged_out_accounts[chat_id].discard(email_lower)
                # 🌐 جهّز بروكسي دائم وفريد لهذا الحساب فورًا (في الخلفية) —
                # هيتحدد بلد الـ IP وييتبعت تنبيه لما يخلص.
                threading.Thread(
                    target=ensure_account_proxy,
                    args=(email_lower,), kwargs={"chat_id": chat_id},
                    daemon=True
                ).start()
                remove_kb = types.ReplyKeyboardRemove()
                bot.send_message(chat_id, "✅", reply_markup=remove_kb)
                bot.send_message(
                    chat_id,
                    "🎉 **تم تسجيل الدخول بنجاح!**\nــــــــــــــــــ",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(chat_id)
                )
            else:
                bot.send_message(
                    chat_id,
                    "❌ فشل تسجيل الدخول، تأكد من بياناتك.",
                    reply_markup=get_auth_menu(chat_id)
                )
            return

        elif step == 'WAITING_DELETE_ACCOUNT':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            if text.strip().lower() in ['إلغاء', 'الغاء', 'cancel', 'لا']:
                del user_sessions[chat_id]
                bot.send_message(chat_id, "↩️ تم الإلغاء.",
                                 reply_markup=get_switch_account_menu(chat_id))
                return
            if not text.strip().isdigit():
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء",
                                                      callback_data="switch_account_menu"))
                bot.send_message(chat_id, "⚠️ أرسل رقم الحساب فقط:",
                                 parse_mode="Markdown", reply_markup=markup)
                return
            idx   = int(text.strip()) - 1
            saved = get_saved_multi_accounts(chat_id)
            if idx < 0 or idx >= len(saved):
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء",
                                                      callback_data="switch_account_menu"))
                bot.send_message(
                    chat_id,
                    f"⚠️ أدخل رقماً بين 1 و {len(saved)}:",
                    parse_mode="Markdown", reply_markup=markup
                )
                return
            del user_sessions[chat_id]
            acc_to_delete = saved[idx]
            email_del     = acc_to_delete['email'].lower().strip()
            label_del     = email_del.split('@')[0]

            with active_accounts_lock:
                if chat_id in active_accounts:
                    active_accounts[chat_id].pop(email_del, None)
            delete_multi_account(chat_id, email_del)
            recompute_hunt_stagger(chat_id)
            _bg_last_hunt.pop((chat_id, email_del), None)
            _bg_last_take.pop((chat_id, email_del), None)
            with auth_sessions_lock:
                user_auth_sessions.pop(email_del, None)

            active_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
            if active_email == email_del:
                for store in [user_data_store, user_sessions, user_numbered_tasks,
                               auto_hunt_status, hunt_mode, last_take_time]:
                    store.pop(chat_id, None)

            bot.send_message(
                chat_id,
                f"✅ **تم حذف الحساب {label_del} نهائياً**",
                parse_mode="Markdown",
                reply_markup=get_switch_account_menu(chat_id)
            )
            return

    if "@" in text and chat_id not in user_data_store:
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        user_sessions[chat_id] = {'step': 'WAITING_PASSWORD', 'email': text}
        msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
        user_transient_messages[chat_id] = msg.message_id

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

def send_crash_alert(reason: str):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"🚨 *توقف البوت* 🚨\n🕐 الوقت: `{now}`\n❌ السبب:\n{reason}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CAPTCHA_ALERT_CHAT_ID, "text": msg,
                  "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass

def watchdog_thread():
    global t_worker
    while True:
        time.sleep(60)
        if not t_worker.is_alive():
            print("[WATCHDOG] background_worker مات — إعادة تشغيل...")
            send_crash_alert("background_worker توقف — تمت إعادة التشغيل")
            t_worker = threading.Thread(target=global_background_worker, daemon=True)
            t_worker.start()

# ==========================================
# 🚀 نقطة الانطلاق
# ==========================================
if __name__ == "__main__":
    print("🚀 تشغيل البوت...")

    # تحميل تعيينات البروكسي + تعبئة أولية للمخزون — في Thread منفصل تمامًا،
    # عشان الفحص (اللي بيعتمد على الإنترنت) ميعطلش استقبال رسائل تليجرام.
    # البوت هيرد فورًا على /start حتى لو الفحص لسه شغال في الخلفية.
    t_proxy_init = threading.Thread(target=_init_proxy_system, daemon=True)
    t_proxy_init.start()

    t_worker = threading.Thread(target=global_background_worker, daemon=True)
    t_worker.start()

    t_server = threading.Thread(target=run_uptime_server, daemon=True)
    t_server.start()

    t_watchdog = threading.Thread(target=watchdog_thread, daemon=True)
    t_watchdog.start()

    print("✅ البوت يعمل الآن...")
    consecutive_errors = 0

    while True:
        try:
            bot.infinity_polling(
                timeout=30, long_polling_timeout=30,
                restart_on_change=False, none_stop=True,
                interval=0, allowed_updates=None
            )
            consecutive_errors = 0
        except KeyboardInterrupt:
            send_crash_alert("تم إيقاف البوت يدوياً")
            sys.exit(0)
        except Exception as _poll_err:
            consecutive_errors += 1
            error_details = traceback.format_exc()
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[POLLING] {now_str} — خطأ #{consecutive_errors}: {_poll_err}")
            send_crash_alert(f"خطأ في polling (#{consecutive_errors}):\n{error_details}")
            wait_time = min(5 * consecutive_errors, 60)
            time.sleep(wait_time)
