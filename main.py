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
import traceback
import sys

# ==========================================
# ⏳ العد التنازلي (24 ساعة من لحظة تشغيل البوت)
# ==========================================
BOT_START_TIME = time.time()
def get_countdown_text() -> str:
    try:
        elapsed = time.time() - BOT_START_TIME
        total_seconds = 24 * 3600
        remaining = total_seconds - elapsed
        if remaining <= 0:
            return "[0mini]"
        remaining_int = int(remaining)
        hours = remaining_int // 3600
        minutes = (remaining_int % 3600) // 60
        if hours >= 1:
            return f"[{hours}h {minutes}mini]" if minutes > 0 else f"[{hours}h]"
        else:
            return f"[{minutes}mini]"
    except Exception:
        return "[--]"

# ==========================================
# الإعدادات الأساسية
# ==========================================
TELEGRAM_TOKEN = "8960468660:AAFlqHUbIMmf08gOC7dFqv9ugD1QObQXxnw"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==========================================
# ⏰ إعدادات التوقيت العشوائي لإشعارات الكلية
# ==========================================
ALL_NOTIFY_DAY_MIN_MINUTES = 3
ALL_NOTIFY_DAY_MAX_MINUTES = 10
ALL_NOTIFY_NIGHT_MIN_MINUTES = 20
ALL_NOTIFY_NIGHT_MAX_MINUTES = 35
MOROCCO_UTC_OFFSET = 1
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6

def _morocco_hour() -> int:
    from datetime import timedelta
    utc_now = datetime.now(timezone.utc)
    morocco_now = utc_now + timedelta(hours=MOROCCO_UTC_OFFSET)
    return morocco_now.hour

def _is_night_now() -> bool:
    h = _morocco_hour()
    return h >= NIGHT_START_HOUR or h < NIGHT_END_HOUR

def _all_notify_next_interval_seconds() -> int:
    if _is_night_now():
        minutes = random.randint(ALL_NOTIFY_NIGHT_MIN_MINUTES, ALL_NOTIFY_NIGHT_MAX_MINUTES)
    else:
        minutes = random.randint(ALL_NOTIFY_DAY_MIN_MINUTES, ALL_NOTIFY_DAY_MAX_MINUTES)
    extra_seconds = random.randint(0, 59)
    return minutes * 60 + extra_seconds

# ==========================================
# 🔔 إعدادات التنبيهات الخاصة
# ==========================================
CAPTCHA_ALERT_CHAT_ID = 8486184645
BASE_URL = "https://forumok.com"
LOGIN_URL = "https://forumok.com/login"
TARGET_URL = "https://forumok.com/orders-search/socio"
STATS_URL = "https://forumok.com/publisher-requests/socio/confirmed"
CONFIRMED_URL = "https://forumok.com/publisher-requests/socio/confirmed"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL
}

def _safe_get(url, session=None, retries=3, **kwargs):
    req = session or requests
    kwargs.setdefault("timeout", 15)
    for i in range(retries):
        try:
            return req.get(url, **kwargs)
        except requests.exceptions.RequestException:
            if i == retries - 1: raise
            time.sleep(2 * (i + 1))

# ==========================================
# 🗄️ نظام التخزين المحلي (بديل السحابة)
# ==========================================
local_multi_accounts = {}  # chat_id -> [{'email': ..., 'password': ...}, ...]
local_user_settings = {}   # chat_id -> {settings}

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
        local_multi_accounts[cid] = [a for a in local_multi_accounts[cid] if a['email'] != email.lower().strip()]
    return True

def load_user_settings(chat_id):
    cid = int(chat_id)
    if cid not in local_user_settings:
        local_user_settings[cid] = {
            'notify_status': False, 'all_notify_status': False, 'notify_interval': 10,
            'auto_hunt_status': False, 'hunt_mode': 'GTE'
        }
    return local_user_settings[cid]

def save_user_settings(chat_id, settings):
    local_user_settings[int(chat_id)] = settings
    return True

# ==========================================
# متغيرات الحالة العامة
# ==========================================
user_sessions = {}
user_data_store = {}          # chat_id -> {email, password}
user_numbered_tasks = {}
user_transient_messages = {}
user_auth_sessions = {}
auth_sessions_lock = threading.Lock()
logged_out_accounts = {}      # chat_id -> set of email_lower
logged_out_lock = threading.Lock()
_handling_blocked = set()
_handling_blocked_lock = threading.Lock()

active_accounts = {}          # chat_id -> {email: {email, password}}
active_accounts_lock = threading.Lock()

# إعدادات مستقلة لكل حساب
acct_notify_status = {}
acct_all_notify_status = {}
acct_notify_interval = {}
acct_auto_hunt_status = {}
acct_hunt_mode = {}

# متغيرات الواجهة
notify_status = {}
all_notify_status = {}
notify_interval = {}
auto_hunt_status = {}
hunt_mode = {}
last_take_time = {}
TAKE_COOLDOWN = 60
user_notify_tasks = {}
ignored_tasks = {}
sent_notifications = {}

def get_email_settings(email):
    e = email.lower().strip()
    notify_on = acct_notify_status.get(e, False)
    all_notify_on = acct_all_notify_status.get(e, False)
    if notify_on and all_notify_on:
        notify_on = False
        acct_notify_status[e] = False
    return {
        'notify_status': notify_on,
        'all_notify_status': all_notify_on,
        'notify_interval': acct_notify_interval.get(e, 10),
        'auto_hunt_status': acct_auto_hunt_status.get(e, False),
        'hunt_mode': acct_hunt_mode.get(e, 'GTE'),
    }

def sync_chat_settings_to_email(chat_id, email):
    e = email.lower().strip()
    acct_notify_status[e] = notify_status.get(chat_id, False)
    acct_all_notify_status[e] = all_notify_status.get(chat_id, False)
    acct_notify_interval[e] = notify_interval.get(chat_id, 10)
    acct_auto_hunt_status[e] = auto_hunt_status.get(chat_id, False)
    acct_hunt_mode[e] = hunt_mode.get(chat_id, 'GTE')

def sync_email_settings_to_chat(chat_id, email):
    e = email.lower().strip()
    notify_status[chat_id] = acct_notify_status.get(e, False)
    all_notify_status[chat_id] = acct_all_notify_status.get(e, False)
    notify_interval[chat_id] = acct_notify_interval.get(e, 10)
    auto_hunt_status[chat_id] = acct_auto_hunt_status.get(e, False)
    hunt_mode[chat_id] = acct_hunt_mode.get(e, 'GTE')

def register_account_in_active(chat_id, email, password):
    with active_accounts_lock:
        if chat_id not in active_accounts:
            active_accounts[chat_id] = {}
        active_accounts[chat_id][email.lower().strip()] = {'email': email, 'password': password}

# ==========================================
# 🚨 كشف وإدارة BLOCKED و CAPTCHA
# ==========================================
def detect_page_state(html_text):
    if not html_text: return None
    html_lower = html_text.lower()
    if any(sig in html_lower for sig in ["заблокирован", "аккаунт заблокирован", "account is blocked", "account blocked"]):
        return "blocked"
    if any(sig in html_lower for sig in ["recaptcha", "g-recaptcha", "captcha", "i am not a robot", "я не робот", "cloudflare", "cf-challenge", "challenge-form"]):
        return "captcha"
    if "login-box" in html_lower and "Выход" not in html_text:
        return "captcha"
    return None

def handle_blocked_account(email, chat_id_origin=None):
    email_lower = email.lower().strip()
    with _handling_blocked_lock:
        if email_lower in _handling_blocked: return
        _handling_blocked.add(email_lower)
    try:
        account_label = email_lower.split("@")[0]
        acct_notify_status[email_lower] = False
        acct_all_notify_status[email_lower] = False
        acct_auto_hunt_status[email_lower] = False
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)
        
        affected_chats = []
        with active_accounts_lock:
            for cid, accounts in active_accounts.items():
                if email_lower in accounts: affected_chats.append(cid)

        blocked_msg = f"🚫 **تنبيه: حساب محظور**\n\n⛔ الحساب **{account_label}** (`{email_lower}`) تعرّض للحظر.\n📌 تم تسجيل الخروج وحذفه تلقائياً."
        for cid in affected_chats:
            with active_accounts_lock:
                if cid in active_accounts: active_accounts[cid].pop(email_lower, None)
            delete_multi_account(cid, email_lower)
            with logged_out_lock:
                if cid not in logged_out_accounts: logged_out_accounts[cid] = set()
                logged_out_accounts[cid].add(email_lower)
            
            active_email = user_data_store.get(cid, {}).get("email", "").lower().strip()
            if active_email == email_lower:
                for store in [user_data_store, user_sessions, user_numbered_tasks, notify_status, notify_interval, auto_hunt_status, hunt_mode, last_take_time, user_notify_tasks, ignored_tasks, all_notify_status]:
                    store.pop(cid, None)
            try: bot.send_message(cid, blocked_msg, parse_mode="Markdown")
            except Exception: pass
    finally:
        def _clear():
            time.sleep(120)
            with _handling_blocked_lock: _handling_blocked.discard(email_lower)
        threading.Thread(target=_clear, daemon=True).start()

def handle_captcha_detected(email, context=""):
    email_lower = email.lower().strip()
    account_label = email_lower.split("@")[0]
    acct_notify_status[email_lower] = False
    acct_all_notify_status[email_lower] = False
    acct_auto_hunt_status[email_lower] = False
    with auth_sessions_lock:
        user_auth_sessions.pop(email_lower, None)
    captcha_msg = f"🤖 **تنبيه: CAPTCHA ظهر!**\n\n🔐 الحساب: **{account_label}** (`{email_lower}`)\n⚠️ يجب حل التحقق يدوياً."
    try: bot.send_message(CAPTCHA_ALERT_CHAT_ID, captcha_msg, parse_mode="Markdown")
    except Exception: pass

# ==========================================
# إنشاء الجلسات (بدون بروكسي)
# ==========================================
def create_session():
    return requests.Session()

def get_authenticated_session(username, password):
    email_lower = username.lower().strip()
    with auth_sessions_lock:
        cached_session = user_auth_sessions.get(email_lower)
    
    if cached_session:
        try:
            test_r = cached_session.get(BASE_URL, headers=HEADERS, timeout=8)
            page_state = detect_page_state(test_r.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
                with auth_sessions_lock: user_auth_sessions.pop(email_lower, None)
                return None
            if page_state == "captcha":
                threading.Thread(target=handle_captcha_detected, args=(username, "أثناء التحقق"), daemon=True).start()
                with auth_sessions_lock: user_auth_sessions.pop(email_lower, None)
                return None
            if "Выход" in test_r.text:
                return cached_session
        except Exception:
            with auth_sessions_lock: user_auth_sessions.pop(email_lower, None)

    # محاولة تسجيل دخول مباشر
    sess = requests.Session()
    login_data = {
        "signin[username]": username,
        "signin[password]": password,
        "signin[remember]": "1",
        "signin[refer_url]": "@office_initial"
    }
    try:
        sess.get(BASE_URL, headers=HEADERS, timeout=8)
        lr = sess.post(LOGIN_URL, data=login_data, headers=HEADERS, timeout=8)
        if lr.status_code == 200:
            page_state = detect_page_state(lr.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
                return None
            if page_state == "captcha":
                threading.Thread(target=handle_captcha_detected, args=(username, "أثناء تسجيل الدخول"), daemon=True).start()
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
    total_minutes = 120
    duration_text = duration_text.strip().lower()
    try:
        number_match = re.search(r"(\d+)", duration_text)
        if not number_match: return 120, "2 ساعات"
        number = int(number_match.group(1))
        if any(x in duration_text for x in ["день", "дня", "дней"]): total_minutes = number * 24 * 60
        elif any(x in duration_text for x in ["час", "часа", "часов"]): total_minutes = number * 60
        elif any(x in duration_text for x in ["минут", "минуты", "минуту"]): total_minutes = number
        else: total_minutes = number * 60
        return total_minutes, f"{number} دقائق" if total_minutes < 60 else f"{number} ساعات"
    except Exception:
        return 120, "2 ساعات"

def fetch_publisher_stats(session):
    stats = {"to_execute": "0", "on_check": "0", "completed": "0", "uncompleted": "0"}
    try:
        r = session.get(STATS_URL, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            page_text = r.text
            m = re.search(r"Выполнить\s+(\d+)", page_text)
            if m: stats["to_execute"] = m.group(1)
            m = re.search(r"На проверке\s+(\d+)", page_text)
            if m: stats["on_check"] = m.group(1)
            m = re.search(r"Выполнено\s+(\d+)", page_text)
            if m: stats["completed"] = m.group(1)
    except Exception: pass
    return stats

def get_site_data(username, password, chat_id):
    session = get_authenticated_session(username, password)
    if not session: return None, "AUTH_FAILED"
    try:
        r = _safe_get(TARGET_URL, session=session, headers=HEADERS, timeout=12)
        page_state = detect_page_state(r.text)
        if page_state == "blocked":
            threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
            return None, "BLOCKED"
        if page_state == "captcha":
            threading.Thread(target=handle_captcha_detected, args=(username, "أثناء جلب المهام"), daemon=True).start()
            return None, "CAPTCHA"
        if "Выход" not in r.text: return None, "SESSION_EXPIRED"

        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(separator="\n")
        balance = "0.0"
        available_match = re.search(r"Доступно:\s*([\d.,\s]+)\s*р\.", page_text)
        if available_match: balance = available_match.group(1).strip()

        PLATFORM_MAP = {"youtube": "YouTube", "telegram": "Telegram", "yandex": "Yandex", "google": "Google", "vkontakte": "VKontakte", "vk": "VKontakte", "instagram": "Instagram", "tiktok": "TikTok", "twitter": "Twitter", "facebook": "Facebook", "ok": "OK"}
        tasks_list = []
        tbody = soup.find("tbody", class_="td-order-search")
        rows = tbody.find_all("tr", id=re.compile(r"^tr\d+")) if tbody else []

        for row in rows:
            try:
                row_classes = row.get("class", []) or []
                if "taken-list" in row_classes or "gray-list" in row_classes: continue
                cells = row.find_all("td")
                if len(cells) < 9: continue
                
                action_cell = cells[-1]
                take_link = action_cell.find("a", href=True)
                if not take_link or action_cell.find("img", alt="take") is None: continue

                take_href = take_link.get("href", "")
                task_page_url = take_href if take_href.startswith("http") else BASE_URL + take_href
                if "?ok=1" not in task_page_url:
                    task_page_url += "?ok=1" if "?" not in task_page_url else "&ok=1"

                price_raw = cells[3].get_text(strip=True).replace(",", ".").replace("  ", " ")
                try: real_price = float(price_raw)
                except ValueError: continue

                country_img = cells[4].find("img")
                country_code = country_img.get("alt", "--") if country_img else "--"

                raw_duration = "2 часа"
                task_desc = ""
                info_img = cells[2].find("img", class_="cursor-help")
                if info_img:
                    import html as html_module
                    raw_content = html_module.unescape(info_img.get("content", ""))
                    mini = BeautifulSoup(raw_content, "html.parser")
                    for small in mini.find_all("small"):
                        if "Время на выполнение" in small.get_text():
                            b = small.find("b")
                            if b: raw_duration = b.get_text(strip=True)
                    parts = [tag.get_text(separator="  ", strip=True) for tag in mini.find_all(["p", "li"]) if tag.get_text(strip=True)]
                    task_desc = "  ".join(parts)

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
                elif any(x in task_desc_check for x in ["россия", "russia", "только для рф", "рф"]):
                    is_restricted = "مقيدة"
                    restrictions_details = "روسيا"

                tasks_list.append({
                    "price": f"{real_price:.2f}", "task_page": task_page_url,
                    "duration": arabic_duration, "minutes": task_minutes,
                    "description": task_desc, "app_name": app_name,
                    "is_restricted": is_restricted, "restrictions": restrictions_details
                })
            except Exception: continue

        stats_data = fetch_publisher_stats(session)
        user_numbered_tasks[chat_id] = tasks_list
        return {"balance": balance, "stats": stats_data, "tasks": tasks_list}, "SUCCESS"
    except Exception:
        return None, "ERROR"

def get_site_data_all_tasks(username, password, chat_id):
    session = get_authenticated_session(username, password)
    if not session: return None, "AUTH_FAILED"
    try:
        r = _safe_get(TARGET_URL, session=session, timeout=12)
        page_state = detect_page_state(r.text)
        if page_state == "blocked":
            threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
            return None, "BLOCKED"
        if page_state == "captcha":
            threading.Thread(target=handle_captcha_detected, args=(username, "إشعارات الكلية"), daemon=True).start()
            return None, "CAPTCHA"
        if "Выход" not in r.text: return None, "SESSION_EXPIRED"

        soup = BeautifulSoup(r.text, "html.parser")
        tbody = soup.find("tbody", class_="td-order-search")
        if not tbody: return {"tasks": []}, "SUCCESS"
        rows = tbody.find_all("tr", id=re.compile(r"^tr\d+"))
        if not rows: return {"tasks": []}, "SUCCESS"

        PLATFORM_MAP = {"youtube": "YouTube", "telegram": "Telegram", "yandex": "Yandex", "google": "Google", "vkontakte": "VKontakte", "vk": "VKontakte", "instagram": "Instagram", "tiktok": "TikTok", "twitter": "Twitter", "facebook": "Facebook", "ok": "OK"}
        tasks_list = []
        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 9: continue
                order_id = re.sub(r"\D", "", row.get("id", ""))
                if not order_id: continue

                plat_img = cells[1].find("img")
                platform_key = plat_img.get("alt", "").lower().strip() if plat_img else ""
                app_name = PLATFORM_MAP.get(platform_key, "منصة أخرى")

                title_link = cells[2].find("a", href=True)
                task_title = title_link.get("title", "") if title_link else ""
                take_href = title_link.get("href", "") if title_link else ""
                take_url = (take_href if take_href.startswith("http") else BASE_URL + take_href) if take_href else ""

                price_raw = cells[3].get_text(strip=True).replace(",", ".").replace("  ", " ")
                try: price_val = float(price_raw)
                except ValueError: price_val = 0.0
                country_img = cells[4].find("img")
                country_code = country_img.get("alt", "--") if country_img else "--"
                taken_text = cells[8].get_text(strip=True)

                duration_raw = "2 часа"
                description = ""
                info_img = cells[2].find("img", class_="cursor-help")
                if info_img:
                    import html as html_module
                    raw_content = html_module.unescape(info_img.get("content", ""))
                    mini = BeautifulSoup(raw_content, "html.parser")
                    for small in mini.find_all("small"):
                        if "Время на выполнение" in small.get_text():
                            b = small.find("b")
                            if b: duration_raw = b.get_text(strip=True)
                    parts = [tag.get_text(separator="  ", strip=True) for tag in mini.find_all(["p", "li"]) if tag.get_text(strip=True)]
                    description = "  ".join(parts)

                task_minutes, arabic_duration = translate_and_parse_duration(duration_raw)
                desc_lower = description.lower()
                is_restricted = "غير مقيدة"
                restrictions_details = ""
                if country_code not in ("", "--", "---"):
                    is_restricted = "مقيدة"
                    restrictions_details = country_code
                elif any(x in desc_lower for x in ["россия", "russia", "только для рф", "рф"]):
                    is_restricted = "مقيدة"
                    restrictions_details = "روسيا"

                tasks_list.append({
                    "price": f"{price_val:.2f}", "task_page": take_url, "order_id": order_id,
                    "title": task_title, "duration": arabic_duration, "minutes": task_minutes,
                    "description": description, "app_name": app_name, "country": country_code,
                    "taken": taken_text, "is_restricted": is_restricted, "restrictions": restrictions_details,
                })
            except Exception: continue
        return {"tasks": tasks_list}, "SUCCESS"
    except Exception:
        return None, "ERROR"

def take_task_via_post(session, task_page_url):
    try:
        response = session.get(task_page_url, headers=HEADERS, timeout=10)
        if response.status_code != 200: return False
        soup = BeautifulSoup(response.text, "html.parser")
        if any(sig in soup.get_text().lower() for sig in ["нет заданий", "no tasks", "задание недоступно", "order not found", "not found", "404"]):
            return False
        form = soup.find("form", action=re.compile(r"batch|order_request"))
        if not form: return False
        post_action_url = form.get('action')
        post_action_url = post_action_url if post_action_url.startswith("http") else BASE_URL + post_action_url
        post_data = {"batch_action": "batchConfirm"}
        for hidden_input in form.find_all("input", type="hidden"):
            if hidden_input.get("name"): post_data[hidden_input.get("name")] = hidden_input.get("value", "")
        
        account_checkboxes = form.find_all("input", class_="batch_checkbox")
        account_ids = [cb.get("value") for cb in account_checkboxes if cb.get("value")]
        if account_ids: post_data["ids[]"] = account_ids
        else: return False

        res = session.post(post_action_url, data=post_data, headers=HEADERS, timeout=10)
        if res.status_code != 200: return False

        time.sleep(1.5)
        confirmed_r = session.get(CONFIRMED_URL, headers=HEADERS, timeout=10)
        if confirmed_r.status_code == 200:
            confirmed_soup = BeautifulSoup(confirmed_r.text, "html.parser")
            table = confirmed_soup.find("table", id="publisher-requests")
            if table and len(table.find_all("tr")) > 1:
                return True
        return False
    except Exception:
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

def get_main_menu_text() -> str:
    return f"🏠 القائمة الرئيسية  {get_countdown_text()}\nــــــــــــــــــ"

def get_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    user_label = "غير محدد"
    if chat_id in user_data_store:
        email = user_data_store[chat_id].get('email', '')
        if "@" in email: user_label = email.split('@')[0]
    markup.add(types.InlineKeyboardButton(f"👤 الحساب الحالي: {user_label} 🔄", callback_data="switch_account_menu"))
    markup.add(types.InlineKeyboardButton("📋 عرض المهام المتاحة وتحديثها", callback_data="view_tasks"))
    markup.add(types.InlineKeyboardButton("🎯 تصيد المهام (إشعارات/اصطحاب)", callback_data="hunt_menu"))
    markup.add(types.InlineKeyboardButton("🚪 تسجيل الخروج من الحساب الحالي", callback_data="logout"))
    return markup

def get_switch_account_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    saved_accounts = get_saved_multi_accounts(chat_id)
    current_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
    with logged_out_lock:
        lo_set = set(logged_out_accounts.get(chat_id, set()))
    for i, acc in enumerate(saved_accounts, 1):
        email = acc['email']
        label = email.split('@')[0]
        e = email.lower().strip()
        is_logged_out = e in lo_set
        is_active_display = (e == current_email)
        if is_active_display: status_icon = "✅"
        elif is_logged_out: status_icon = "💤"
        else:
            hunt_on = acct_auto_hunt_status.get(e, False)
            status_icon = "⚡" if hunt_on else "🔘"
        markup.add(types.InlineKeyboardButton(f"{status_icon} الحساب {i}: {label}", callback_data=f"switch_acc_{i-1}"))
    markup.add(types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="add_new_account"))
    markup.add(types.InlineKeyboardButton("🗑️ حذف حساب", callback_data="delete_account_start"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main"))
    return markup

def get_hunting_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🔔 إشعارات دورية", callback_data="notif_menu"))
    markup.add(types.InlineKeyboardButton("⚡ اصطحاب للعمل", callback_data="take_work_menu"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return markup

def get_notifications_config_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    is_active = notify_status.get(chat_id, False)
    status_icon = "🟢" if is_active else "🔴"
    is_all_active = all_notify_status.get(chat_id, False)
    all_status_icon = "🟢" if is_all_active else "🔴"
    markup.add(types.InlineKeyboardButton("⚙️ تخصيص فترة التنبيه", callback_data="custom_notify"))
    markup.add(types.InlineKeyboardButton(f"إشعارات دورية {status_icon}", callback_data="toggle_notify"))
    markup.add(types.InlineKeyboardButton(f"إشعارات كلية {all_status_icon}", callback_data="toggle_all_notify"))
    markup.add(types.InlineKeyboardButton("15 دقيقة", callback_data="set_notify_15"))
    markup.add(types.InlineKeyboardButton("10 دقائق", callback_data="set_notify_10"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_hunt"))
    return markup

def get_take_work_menu(chat_id, email=""):
    markup = types.InlineKeyboardMarkup(row_width=1)
    current_mode = hunt_mode.get(chat_id, "GTE")
    is_active = auto_hunt_status.get(chat_id, False)
    icon_gt = "🟢" if (is_active and current_mode == "GT") else "🔴"
    icon_gte = "🟢" if (is_active and current_mode == "GTE") else "🔴"
    markup.add(types.InlineKeyboardButton(f"تفعيل > 2 ساعات قطعاً {icon_gt}", callback_data="toggle_gt"))
    markup.add(types.InlineKeyboardButton(f"تفعيل >= 2 ساعات {icon_gte}", callback_data="toggle_gte"))
    markup.add(types.InlineKeyboardButton("👆 اصطحاب يدوي", callback_data="manual_take"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_hunt"))
    return markup

# ==========================================
# 🔄 الخيط الخلفي الرئيسي
# ==========================================
_bg_last_notify = {}
_bg_last_hunt = {}
_bg_last_take = {}
_bg_last_all_notify = {}

def _bg_process_one_account_inner(chat_id, email, password, current_time):
    key = (chat_id, email)
    e = email.lower().strip()
    settings = get_email_settings(email)
    
    # إشعارات الكلية
    if settings['all_notify_status']:
        if key not in _bg_last_all_notify:
            first_interval = _all_notify_next_interval_seconds()
            _bg_last_all_notify[key] = {'last_sent': current_time - random.randint(0, first_interval // 2), 'next_interval': first_interval}
        state = _bg_last_all_notify[key]
        if current_time - state['last_sent'] >= state['next_interval']:
            state['last_sent'] = current_time
            state['next_interval'] = _all_notify_next_interval_seconds()
            try:
                all_data, all_status = get_site_data_all_tasks(email, password, chat_id)
                if all_status == "SUCCESS" and all_data and all_data.get('tasks'):
                    user_ignored = ignored_tasks.get(chat_id, [])
                    sn_key = f"all_{chat_id}_{e}"
                    if sn_key not in sent_notifications: sent_notifications[sn_key] = set()
                    new_tasks = [t for t in all_data['tasks'] if t['task_page'] not in user_ignored and t['task_page'] not in sent_notifications[sn_key]]
                    if new_tasks:
                        for t in new_tasks: sent_notifications[sn_key].add(t['task_page'])
                        period_label = "☀️ نهار" if not _is_night_now() else "🌙 ليل"
                        msg = f"📢 **إشعار كلي** — {period_label}\n👤 الحساب: {e.split('@')[0]}\n\n"
                        for t in new_tasks[:5]:
                            msg += f"📌 **المهمة:** {t.get('description', '').split(chr(10))[0][:50]}\n💰 **السعر:** {t['price']} روبل\n📱 **المنصة:** {t.get('app_name', 'منصة أخرى')}\n⏱️ **المدة:** {t.get('duration', 'غير محدد')}\n🔒 **الحالة:** {t.get('is_restricted', 'غير مقيدة')}\n🔗 `{t['task_page']}`\n━━━━━━━━━━━━━━━━\n"
                        try: bot.send_message(chat_id, msg, parse_mode="Markdown")
                        except Exception: pass
            except Exception: pass
    else:
        if key in _bg_last_all_notify: del _bg_last_all_notify[key]

    # الإشعارات الدورية العادية
    if settings['notify_status'] and not settings['all_notify_status']:
        interval_secs = settings['notify_interval'] * 60
        if current_time - _bg_last_notify.get(key, 0) >= interval_secs:
            _bg_last_notify[key] = current_time
            data, status = get_site_data(email, password, chat_id)
            if status == "SUCCESS" and data and data['tasks']:
                user_ignored = ignored_tasks.get(chat_id, [])
                sn_key = f"{chat_id}_{e}"
                if sn_key not in sent_notifications: sent_notifications[sn_key] = set()
                filtered_tasks = [t for t in data['tasks'] if t['task_page'] not in user_ignored]
                if filtered_tasks:
                    user_notify_tasks[chat_id] = filtered_tasks[:5]
                    msg = f"📢 مهام جديدة متوفرة\n👤 الحساب: {e.split('@')[0]}:\n\n"
                    for idx, t in enumerate(filtered_tasks[:5], start=1):
                        msg += f"🔢 {idx} ➖ {t['price']} RUB | {t['duration']}\n"
                    inline_markup = types.InlineKeyboardMarkup()
                    inline_markup.add(types.InlineKeyboardButton(text="🔕 تجاهل مهمة", callback_data="ign_task"))
                    try: bot.send_message(chat_id, msg, reply_markup=inline_markup)
                    except Exception: pass

    # الاصطحاب التلقائي
    if settings['auto_hunt_status']:
        last_take = _bg_last_take.get(key, 0)
        if current_time - last_take >= TAKE_COOLDOWN:
            if current_time - _bg_last_hunt.get(key, 0) >= 120:
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
                                    try:
                                        bot.send_message(chat_id, f"⚡ تم اصطحاب مهمة تلقائياً!\n👤 الحساب: {e.split('@')[0]}\n💰 السعر: {target_task['price']} RUB\n⏱️ الوقت: {target_task['duration']}")
                                    except Exception: pass
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
                        _bg_process_one_account_inner(chat_id, creds['email'], creds['password'], current_time)
                    except Exception as ex:
                        print(f"[BG] خطأ في معالجة {email_key}: {ex}")
        except Exception as e:
            print(f"[BG] خطأ عام: {e}")
        time.sleep(5)

# ==========================================
# 📞 معالجة الضغطات (Callbacks)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_all_inline_callbacks(call):
    try:
        _handle_callback_inner(call)
    except Exception as _cb_err:
        print(f"[CALLBACK] خطأ: {_cb_err}")
        try: bot.answer_callback_query(call.id, "⚠️ حدث خطأ.")
        except Exception: pass

def _handle_callback_inner(call):
    chat_id = call.message.chat.id
    data = call.data
    message_id = call.message.message_id
    
    if chat_id in user_sessions:
        step = user_sessions[chat_id].get('step', '')
        waiting_steps = ['WAITING_EMAIL', 'WAITING_PASSWORD', 'WAITING_CUSTOM_INTERVAL', 'WAIT_IGN_NUM', 'WAITING_DELETE_ACCOUNT']
        if step in waiting_steps:
            del user_sessions[chat_id]

    elif data.startswith("switch_acc_"):
        idx = int(data.replace("switch_acc_", ""))
        saved_accounts = get_saved_multi_accounts(chat_id)
        if 0 <= idx < len(saved_accounts):
            acc = saved_accounts[idx]
            new_email_lower = acc['email'].lower().strip()
            old_email = user_data_store.get(chat_id, {}).get('email', '')
            if old_email: sync_chat_settings_to_email(chat_id, old_email)
            
            user_data_store[chat_id] = {'email': acc['email'], 'password': acc['password']}
            register_account_in_active(chat_id, acc['email'], acc['password'])
            with logged_out_lock:
                if chat_id in logged_out_accounts: logged_out_accounts[chat_id].discard(new_email_lower)
            
            e_settings = get_email_settings(acc['email'])
            if e_settings['notify_status'] or e_settings['auto_hunt_status']:
                sync_email_settings_to_chat(chat_id, acc['email'])
            else:
                load_user_settings(chat_id)
                sync_chat_settings_to_email(chat_id, acc['email'])
            
            with auth_sessions_lock:
                cached = user_auth_sessions.get(new_email_lower)
            if not cached:
                threading.Thread(target=lambda: get_authenticated_session(acc['email'], acc['password']), daemon=True).start()
            
            bot.answer_callback_query(call.id)
            try: bot.edit_message_text(get_main_menu_text(), chat_id, message_id, reply_markup=get_main_menu(chat_id))
            except Exception: bot.send_message(chat_id, get_main_menu_text(), reply_markup=get_main_menu(chat_id))
        else:
            bot.answer_callback_query(call.id, "⚠️ حدث خطأ.", show_alert=True)

    elif data == "switch_account_menu":
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text("🔄 **إدارة الحسابات**\nاختر حساباً للتبديل إليه أو قم بإضافة حساب جديد:\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_switch_account_menu(chat_id))
        except Exception: pass

    elif data == "add_new_account":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try: bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception: pass
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني للحساب الجديد:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}

    elif data == "delete_account_start":
        bot.answer_callback_query(call.id)
        saved_accounts = get_saved_multi_accounts(chat_id)
        if not saved_accounts:
            bot.answer_callback_query(call.id, "⚠️ لا توجد حسابات محفوظة.", show_alert=True)
            return
        lines = ["🗑️ **حذف حساب من القائمة**\n\nأرسل **رقم الحساب** الذي تريد حذفه:\n"]
        for i, acc in enumerate(saved_accounts, 1):
            lines.append(f"  {i}. {acc['email'].split('@')[0]}")
        lines.append("\nأو أرسل **إلغاء** للرجوع بدون حذف.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
        if chat_id in user_transient_messages:
            try: bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception: pass
        msg = bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown", reply_markup=markup)
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_DELETE_ACCOUNT'}

    elif data == "login_start":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try: bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception: pass
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}

    elif data == "view_tasks":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id)
        if not creds:
            try: bot.edit_message_text("⚠️ يرجى تسجيل الدخول أولاً.", chat_id, message_id, reply_markup=get_auth_menu(chat_id))
            except Exception: pass
            return
        try: bot.edit_message_text("⏳ جارٍ جلب المهام...", chat_id, message_id)
        except Exception: pass

        def _do_view_tasks():
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
                try: bot.edit_message_text(msg, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
                except Exception: bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
            else:
                err_markup = types.InlineKeyboardMarkup()
                err_markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                try: bot.edit_message_text("⚠️ فشل جلب البيانات. حاول مجدداً.", chat_id, message_id, reply_markup=err_markup)
                except Exception: pass
        threading.Thread(target=_do_view_tasks, daemon=True).start()

    elif data == "hunt_menu":
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text("🎯 **تصيد المهام**\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_hunting_menu())
        except Exception: pass

    elif data == "logout":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        email_to_logout = creds.get('email', '').lower().strip()
        if email_to_logout:
            with auth_sessions_lock: user_auth_sessions.pop(email_to_logout, None)
            acct_notify_status[email_to_logout] = False
            acct_all_notify_status[email_to_logout] = False
            acct_auto_hunt_status[email_to_logout] = False
            with logged_out_lock:
                if chat_id not in logged_out_accounts: logged_out_accounts[chat_id] = set()
                logged_out_accounts[chat_id].add(email_to_logout)
        for store in [user_data_store, user_sessions, user_numbered_tasks, notify_status, notify_interval, auto_hunt_status, hunt_mode, last_take_time, user_notify_tasks, ignored_tasks, all_notify_status]:
            store.pop(chat_id, None)
        try: bot.edit_message_text("🚪 **تم تسجيل الخروج بنجاح**\n\n💤 جلستك الحالية انتهت.", chat_id, message_id, reply_markup=get_auth_menu(chat_id))
        except Exception: pass

    elif data == "back_main":
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text(get_main_menu_text(), chat_id, message_id, reply_markup=get_main_menu(chat_id))
        except Exception: pass

    elif data == "notif_menu":
        bot.answer_callback_query(call.id)
        current_interval = notify_interval.get(chat_id, 10)
        is_active = notify_status.get(chat_id, False)
        status_text = "🟢 مفعلة" if is_active else "🔴 متوقفة"
        msg_text = f"🔔 **الإشعارات الدورية: {status_text}**\n⏱️ الفترة الحالية: {current_interval} دقائق\n\nاختر فترة التنبيه أو اضغط تخصيص:"
        try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=get_notifications_config_menu(chat_id))
        except Exception: pass

    elif data == "take_work_menu":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        try: bot.edit_message_text("⚡ **خيارات اصطحاب المهام**\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
        except Exception: pass

    elif data == "back_hunt":
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text("🎯 **تصيد المهام**\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_hunting_menu())
        except Exception: pass

    elif data == "toggle_notify":
        bot.answer_callback_query(call.id)
        current = notify_status.get(chat_id, False)
        new_state = not current
        notify_status[chat_id] = new_state
        if new_state: all_notify_status[chat_id] = False
        creds_t = user_data_store.get(chat_id, {})
        if creds_t.get('email'):
            e_t = creds_t['email'].lower().strip()
            acct_notify_status[e_t] = new_state
            if new_state: acct_all_notify_status[e_t] = False
        save_user_settings(chat_id, {'notify_status': notify_status.get(chat_id, False), 'all_notify_status': all_notify_status.get(chat_id, False), 'notify_interval': notify_interval.get(chat_id, 10), 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
        current_interval = notify_interval.get(chat_id, 10)
        msg_text = f"🔔 **إعدادات الإشعارات:**\n⏱️ الفترة الحالية: {current_interval} دقائق\n\nاختر من الخيارات أدناه:"
        try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=get_notifications_config_menu(chat_id))
        except Exception: pass

    elif data == "toggle_all_notify":
        bot.answer_callback_query(call.id)
        current = all_notify_status.get(chat_id, False)
        new_state = not current
        all_notify_status[chat_id] = new_state
        if new_state: notify_status[chat_id] = False
        creds_t = user_data_store.get(chat_id, {})
        if creds_t.get('email'):
            e_t = creds_t['email'].lower().strip()
            acct_all_notify_status[e_t] = new_state
            if new_state: acct_notify_status[e_t] = False
        save_user_settings(chat_id, {'notify_status': notify_status.get(chat_id, False), 'all_notify_status': all_notify_status.get(chat_id, False), 'notify_interval': notify_interval.get(chat_id, 10), 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
        current_interval = notify_interval.get(chat_id, 10)
        msg_text = f"🔔 **إعدادات الإشعارات:**\n⏱️ الفترة الحالية: {current_interval} دقائق\n\nاختر من الخيارات أدناه:"
        try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=get_notifications_config_menu(chat_id))
        except Exception: pass

    elif data == "set_notify_10":
        notify_interval[chat_id] = 10
        notify_status[chat_id] = True
        all_notify_status[chat_id] = False
        creds_t = user_data_store.get(chat_id, {})
        if creds_t.get('email'):
            e_t = creds_t['email'].lower().strip()
            acct_notify_status[e_t] = True
            acct_all_notify_status[e_t] = False
            acct_notify_interval[e_t] = 10
        save_user_settings(chat_id, {'notify_status': True, 'all_notify_status': False, 'notify_interval': 10, 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
        bot.answer_callback_query(call.id, "✅ تم الضبط إلى 10 دقائق")
        try: bot.edit_message_text("🔔 **الإشعارات الدورية: 🟢 مفعلة**\n⏱️ الفترة الحالية: 10 دقائق\n\nاختر فترة التنبيه أو اضغط تخصيص:", chat_id, message_id, reply_markup=get_notifications_config_menu(chat_id))
        except Exception: pass

    elif data == "set_notify_15":
        notify_interval[chat_id] = 15
        notify_status[chat_id] = True
        all_notify_status[chat_id] = False
        creds_t = user_data_store.get(chat_id, {})
        if creds_t.get('email'):
            e_t = creds_t['email'].lower().strip()
            acct_notify_status[e_t] = True
            acct_all_notify_status[e_t] = False
            acct_notify_interval[e_t] = 15
        save_user_settings(chat_id, {'notify_status': True, 'all_notify_status': False, 'notify_interval': 15, 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
        bot.answer_callback_query(call.id, "✅ تم الضبط إلى 15 دقيقة")
        try: bot.edit_message_text("🔔 **الإشعارات الدورية: 🟢 مفعلة**\n⏱️ الفترة الحالية: 15 دقيقة\n\nاختر فترة التنبيه أو اضغط تخصيص:", chat_id, message_id, reply_markup=get_notifications_config_menu(chat_id))
        except Exception: pass

    elif data == "custom_notify":
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'WAITING_CUSTOM_INTERVAL'}
        msg_text = "📥 **أدخل فترة التنبيه بالدقائق**\n(من 3 إلى 120 دقيقة)\n\nاكتب الرقم وأرسله في الشات مباشرة:"
        try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=get_notifications_config_menu(chat_id))
        except Exception: pass

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
        save_user_settings(chat_id, {'notify_status': notify_status.get(chat_id, False), 'all_notify_status': all_notify_status.get(chat_id, False), 'notify_interval': notify_interval.get(chat_id, 10), 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
        if creds.get('email'): sync_chat_settings_to_email(chat_id, creds['email'])
        try: bot.edit_message_text(f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
        except Exception: pass

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
        save_user_settings(chat_id, {'notify_status': notify_status.get(chat_id, False), 'all_notify_status': all_notify_status.get(chat_id, False), 'notify_interval': notify_interval.get(chat_id, 10), 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
        if creds.get('email'): sync_chat_settings_to_email(chat_id, creds['email'])
        try: bot.edit_message_text(f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
        except Exception: pass

    elif data == "manual_take":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id)
        if not creds: return
        result, status = get_site_data(creds['email'], creds['password'], chat_id)
        if status == "SUCCESS":
            if not result['tasks']:
                try: bot.edit_message_text("⚡ **اصطحاب العمل**\n📋 لا توجد مهام متوفرة حالياً.\nــــــــــــــــــ", chat_id, message_id, reply_markup=get_take_work_menu(chat_id, creds.get('email', '')))
                except Exception: pass
            else:
                lines = ["📌 **قائمة المهام للاصطحاب اليدوي:**\n"]
                for i, task in enumerate(result['tasks'], start=1):
                    lines.append(f"🔢 {i} - السعر: {task['price']} RUB | المدة: {task['duration']}")
                bot.send_message(chat_id, "\n".join(lines))
        else:
            bot.send_message(chat_id, "⚠️ تعذر تحميل المهام اليدوية.")

    elif data == "ign_task":
        if chat_id not in user_notify_tasks or not user_notify_tasks[chat_id]:
            bot.answer_callback_query(call.id, "⚠️ لا توجد مهام حالياً لتجاهلها.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        user_sessions[chat_id] = {'step': 'WAIT_IGN_NUM'}
        bot.send_message(chat_id, "🔢 أدخل رقم المهمة لتجاهلها:")

    elif data.startswith("ign_specific_"):
        bot.answer_callback_query(call.id)
        parts = data.split("_", 3)
        if len(parts) >= 4:
            task_identifier = parts[3]
            if chat_id in user_notify_tasks:
                for task in user_notify_tasks[chat_id]:
                    if task['task_page'][:50] == task_identifier:
                        if chat_id not in ignored_tasks: ignored_tasks[chat_id] = []
                        if task['task_page'] not in ignored_tasks[chat_id]:
                            ignored_tasks[chat_id].append(task['task_page'])
                        bot.answer_callback_query(call.id, "✅ تم تجاهل المهمة بنجاح")
                        try: bot.delete_message(chat_id, message_id)
                        except Exception: pass
                        return
        bot.answer_callback_query(call.id, "⚠️ لم يتم العثور على المهمة", show_alert=True)

# ==========================================
# 📨 معالجة الرسائل
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_bot_logic(message):
    try:
        _handle_message_inner(message)
    except Exception as _msg_err:
        print(f"[MESSAGE] خطأ: {_msg_err}")
        try: bot.send_message(message.chat.id, "⚠️ حدث خطأ، حاول مجدداً.")
        except Exception: pass

def _handle_message_inner(message):
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""
    
    if text.lower() not in ["/start", "start"]:
        try: bot.delete_message(chat_id, message.message_id)
        except Exception: pass

    if text.lower() in ["/start", "start"]:
        remove_keyboard = types.ReplyKeyboardRemove()
        if chat_id in user_data_store or get_saved_multi_accounts(chat_id):
            bot.send_message(chat_id, "مرحباً بك في لوحة التحكم الرئيسية ⚙️", reply_markup=remove_keyboard)
            bot.send_message(chat_id, get_main_menu_text(), reply_markup=get_main_menu(chat_id))
        else:
            bot.send_message(chat_id, "مرحباً بك في البوت.", reply_markup=remove_keyboard)
            bot.send_message(chat_id, "⚙️ يرجى تسجيل الدخول للبدء أو اختيار حسابك المحفوظ:", reply_markup=get_auth_menu(chat_id))
        return

    if chat_id in user_sessions:
        step = user_sessions[chat_id]['step']

        if step == 'WAITING_EMAIL':
            if chat_id in user_transient_messages:
                try: bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception: pass
            user_sessions[chat_id]['email'] = text
            user_sessions[chat_id]['step'] = 'WAITING_PASSWORD'
            msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
            user_transient_messages[chat_id] = msg.message_id
            return

        elif step == 'WAITING_PASSWORD':
            if chat_id in user_transient_messages:
                try: bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception: pass
            email = user_sessions[chat_id]['email']
            password = text
            del user_sessions[chat_id]
            email_lower = email.lower().strip()
            
            status_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الحساب...")
            session = get_authenticated_session(email, password)
            try: bot.delete_message(chat_id, status_msg.message_id)
            except Exception: pass

            if session:
                user_data_store[chat_id] = {'email': email, 'password': password}
                save_multi_account(chat_id, email, password)
                load_user_settings(chat_id)
                register_account_in_active(chat_id, email, password)
                sync_chat_settings_to_email(chat_id, email)
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = session
                with logged_out_lock:
                    if chat_id in logged_out_accounts: logged_out_accounts[chat_id].discard(email_lower)
                
                remove_keyboard = types.ReplyKeyboardRemove()
                bot.send_message(chat_id, "✅", reply_markup=remove_keyboard)
                welcome_msg = f"🎉 **تم تسجيل الدخول بنجاح!**\n\nــــــــــــــــــ"
                bot.send_message(chat_id, welcome_msg, parse_mode="Markdown", reply_markup=get_main_menu(chat_id))
            else:
                bot.send_message(chat_id, "❌ فشل تسجيل الدخول، تأكد من بياناتك.", reply_markup=get_auth_menu(chat_id))
            return

        elif step == 'WAITING_DELETE_ACCOUNT':
            if chat_id in user_transient_messages:
                try: bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception: pass
            if text.strip().lower() in ['إلغاء', 'الغاء', 'cancel', 'لا']:
                del user_sessions[chat_id]
                bot.send_message(chat_id, "↩️ تم الإلغاء.", reply_markup=get_switch_account_menu(chat_id))
                return
            if not text.strip().isdigit():
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
                bot.send_message(chat_id, "⚠️ أرسل رقم الحساب فقط، أو أرسل **إلغاء** للرجوع:", parse_mode="Markdown", reply_markup=markup)
                return
            idx = int(text.strip()) - 1
            saved_accounts = get_saved_multi_accounts(chat_id)
            if idx < 0 or idx >= len(saved_accounts):
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
                bot.send_message(chat_id, f"⚠️ الرقم غير موجود. أدخل رقماً بين 1 و {len(saved_accounts)}، أو أرسل **إلغاء**:", parse_mode="Markdown", reply_markup=markup)
                return

            del user_sessions[chat_id]
            acc_to_delete = saved_accounts[idx]
            email_del = acc_to_delete['email'].lower().strip()
            label_del = email_del.split('@')[0]

            with active_accounts_lock:
                if chat_id in active_accounts: active_accounts[chat_id].pop(email_del, None)
            threading.Thread(target=delete_multi_account, args=(chat_id, email_del), daemon=True).start()
            with auth_sessions_lock: user_auth_sessions.pop(email_del, None)
            
            active_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
            if active_email == email_del:
                for store in [user_data_store, user_sessions, user_numbered_tasks, notify_status, notify_interval, auto_hunt_status, hunt_mode, last_take_time, user_notify_tasks, ignored_tasks, all_notify_status]:
                    store.pop(chat_id, None)

            bot.send_message(chat_id, f"✅ **تم حذف الحساب {label_del} نهائياً**\n\n🗑️ تم حذفه من القائمة وجميع الجلسات.", parse_mode="Markdown", reply_markup=get_switch_account_menu(chat_id))
            return

        elif step == 'WAITING_CUSTOM_INTERVAL':
            if text.isdigit():
                minutes = int(text)
                if 3 <= minutes <= 120:
                    notify_interval[chat_id] = minutes
                    notify_status[chat_id] = True
                    all_notify_status[chat_id] = False
                    creds_ci = user_data_store.get(chat_id, {})
                    if creds_ci.get('email'):
                        e_ci = creds_ci['email'].lower().strip()
                        acct_notify_status[e_ci] = True
                        acct_all_notify_status[e_ci] = False
                        acct_notify_interval[e_ci] = minutes
                    save_user_settings(chat_id, {'notify_status': True, 'all_notify_status': False, 'notify_interval': minutes, 'auto_hunt_status': auto_hunt_status.get(chat_id, False), 'hunt_mode': hunt_mode.get(chat_id, 'GTE')})
                    del user_sessions[chat_id]
                    bot.send_message(chat_id, f"✅ تم ضبط فترة التنبيه إلى {minutes} دقيقة.")
                else:
                    bot.send_message(chat_id, "⚠️ يرجى إدخال قيمة بين 3 و 120 دقيقة:")
            else:
                bot.send_message(chat_id, "❌ الرجاء إدخال أرقام فقط (مثال: 25):")
            return

        elif step == 'WAIT_IGN_NUM':
            if text.isdigit():
                idx = int(text) - 1
                if chat_id in user_notify_tasks and 0 <= idx < len(user_notify_tasks[chat_id]):
                    task_url = user_notify_tasks[chat_id][idx]['task_page']
                    if chat_id not in ignored_tasks: ignored_tasks[chat_id] = []
                    if task_url not in ignored_tasks[chat_id]:
                        ignored_tasks[chat_id].append(task_url)
                    del user_sessions[chat_id]
                    bot.send_message(chat_id, "✅ تم تجاهل المهمة.")
                else:
                    bot.send_message(chat_id, "⚠️ الرقم غير موجود بالقائمة:")
            else:
                bot.send_message(chat_id, "❌ أدخل رقم صحيح فقط:")
            return

    if "@" in text and chat_id not in user_data_store:
        if chat_id in user_transient_messages:
            try: bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception: pass
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
                else:
                    bot.send_message(chat_id, f"❌ فشل اصطحاب المهمة {text}")
        else:
            bot.send_message(chat_id, "❌ رقم غير صحيح.")

# ==========================================
# 🖥️ السيرفر المساعد والمراقبة
# ==========================================
class KeepAliveServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("Bot Running".encode("utf-8"))
    def log_message(self, format, *args): pass

def run_uptime_server():
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(('', port), KeepAliveServer)
    httpd.serve_forever()

def send_crash_alert(reason: str):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"🚨 توقف البوت 🚨\n🕐 الوقت: `{now}`\n❌ السبب:\n`\n{reason[:3000]}\n`"
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CAPTCHA_ALERT_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception: pass

def watchdog_thread():
    global t_worker
    while True:
        time.sleep(60)
        if not t_worker.is_alive():
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[WATCHDOG] {now} — background_worker مات، إعادة تشغيل...")
            send_crash_alert("background_worker توقف بشكل غير متوقع")
            t_worker = threading.Thread(target=global_background_worker, daemon=True)
            t_worker.start()

# ==========================================
# 🚀 نقطة الانطلاق
# ==========================================
if __name__ == "__main__":
    print("🚀 تشغيل البوت...")
    
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
            bot.infinity_polling(timeout=30, long_polling_timeout=30, restart_on_change=False, none_stop=True, interval=0, allowed_updates=None)
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
            print(f"[POLLING] إعادة المحاولة خلال {wait_time} ثانية...")
            time.sleep(wait_time)