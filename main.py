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
TELEGRAM_TOKEN = "8947312047:AAEv7tnwcpu00hXqO0o1k0JyEJOMOIQjZrs"
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

# 🤖 تنفيذ تلقائي عبر القوالب مع كل اصطحاب ناجح
# 🤖 القوالب: خدمتين مستقلتين + حالة تشغيل/إيقاف لكل واحدة
template_scan_status    = {}  # chat_id -> True/False — "تنفيذ المهام" (فحص المهام الحالية دفعة واحدة)
template_scan_stop_events = {}  # chat_id -> threading.Event() لإيقاف الفحص الجاري فورًا
template_delay_status   = {}  # chat_id -> True/False — "تمرير تنفيذ بعد الاصطحاب" (مهلة عشوائية)
_known_confirmed_ids    = {}  # (chat_id, email_lower) -> set(task_id) — لمعرفة المهمة اللي اتاخدت جديد
_template_no_match_cache = {} # chat_id -> set(task_id) اتفحصت قبل كده ومالهاش تطابق
_template_cache_lock    = threading.Lock()

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
    """
    لما الـ CAPTCHA تظهر، بيتوقف الاصطحاب التلقائي لهذا الحساب بس
    (acct_auto_hunt_status خاص بالحساب نفسه، مش بكل الحسابات) — باقي
    حسابات نفس الشات بتفضل شغالة عادي من غير أي تأثير.

    بيتبعت تنبيه فيه زر "✅ لقد نفدت captcha" لكل شات الحساب ده شغال
    فيه فعليًا (زيادة على شات الأدمن)، وبمجرد الضغط عليه الحساب يرجع
    يشتغل عادي تاني.
    """
    email_lower = email.lower().strip()
    account_label = email_lower.split("@")[0]
    acct_auto_hunt_status[email_lower] = False
    with auth_sessions_lock:
        user_auth_sessions.pop(email_lower, None)

    captcha_msg = (
        f"🤖 **تنبيه: CAPTCHA ظهر!**\n\n"
        f"🔐 الحساب: **{account_label}** (`{email_lower}`)\n"
        f"⚠️ تم إيقاف الاصطحاب لهذا الحساب فقط — باقي حساباتك شغالة عادي.\n"
        f"يجب حل التحقق يدوياً، وبعدين اضغط الزر تحت عشان الحساب يرجع يشتغل."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "✅ لقد نفدت captcha", callback_data=f"captcha_resolved_{email_lower}"
    ))

    target_chats = {CAPTCHA_ALERT_CHAT_ID}
    with active_accounts_lock:
        for cid, accounts in active_accounts.items():
            if email_lower in accounts:
                target_chats.add(cid)

    for cid in target_chats:
        try:
            bot.send_message(cid, captcha_msg, parse_mode="Markdown", reply_markup=markup)
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
            # 🔒 تسجيل الدخول / التحقق من الجلسة دايمًا اتصال عادي —
            # حتى لو الجلسة كانت لسه شايلة بروكسي من آخر عرض/اصطحاب مهمة.
            cached.proxies = {}
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
    """
    يجيب أرقام الإحصائيات الصحيحة من نفس صفحة
    /publisher-requests/socio/confirmed اللي بيستخدمها زر 'تنفيذ مهام' —
    عن طريق قراءة الجدول الفعلي (رابط بعنوان title معروف + الرقم جنبه في
    نفس الصف)، بدل البحث النصي العشوائي في الصفحة كلها اللي كان بيدّي
    أرقام غلط لو الكلمة اتكررت في مكان تاني (زي عنوان الجدول نفسه).
    """
    stats = {"to_execute": "0", "on_check": "0", "arbitration": "0", "completed": "0"}
    label_map = {
        "Выполнить":   "to_execute",    # قيد التنفيذ
        "На проверке": "on_check",      # قيد المراجعة
        "Арбитраж":    "arbitration",   # التحكيم
        "Выполнено":   "completed",     # مكتملة
    }
    try:
        r = session.get(CONFIRMED_URL, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return stats
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", class_="link-requests"):
            key = label_map.get(a.get("title", "").strip())
            if not key:
                continue
            tr = a.find_parent("tr")
            if not tr:
                continue
            tds = tr.find_all("td")
            if len(tds) >= 2:
                count_text = tds[-1].get_text(strip=True)
                if count_text.isdigit():
                    stats[key] = count_text
    except Exception:
        pass
    return stats

def get_site_data(username, password, chat_id):
    session = get_authenticated_session(username, password, chat_id)
    if not session:
        return None, "AUTH_FAILED"

    # 🌐 جلب/عرض المهام اتصال عادي من غير بروكسي — البروكسي بيتفعّل بس
    # لحظة الاصطحاب الفعلي (شوف take_task_via_post وموقع استدعائها).
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
                stats_data = {"to_execute": "0", "on_check": "0", "arbitration": "0", "completed": "0"}

        user_numbered_tasks[chat_id] = tasks_list
        return {"balance": balance, "stats": stats_data, "tasks": tasks_list}, "SUCCESS"
    except Exception:
        return None, "ERROR"

def take_task_via_post(session, task_page_url):
    try:
        try:
            response = session.get(task_page_url, headers=HEADERS, timeout=10)
        except Exception:
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


def fetch_confirmed_tasks(session):
    """
    يجيب قائمة المهام المصطحبة اللي لسه محتاجة تنفيذ من
    /publisher-requests/socio/confirmed — للعرض في قائمة "تنفيذ مهام".
    اتصال عادي (زي عرض المهام)، من غير بروكسي.
    """
    tasks = []
    try:
        r = session.get(CONFIRMED_URL, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return tasks
        soup = BeautifulSoup(r.text, "html.parser")
        tbody = soup.find("tbody", class_="td-request")
        if not tbody:
            return tasks
        for row in tbody.find_all("tr"):
            checkbox = row.find("input", class_="batch_checkbox")
            if not checkbox or not checkbox.get("value"):
                continue
            task_id = checkbox.get("value")
            link = row.find("a", href=re.compile(rf"/request/{task_id}/history"))
            title = link.get_text(strip=True) if link else f"مهمة {task_id}"
            cells = row.find_all("td")
            remaining = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            tasks.append({"id": task_id, "title": title, "remaining": remaining})
    except Exception:
        pass
    return tasks


def submit_task_report(session, task_id, report_url, report_message):
    """
    بيبعت تقرير إنجاز المهمة رقم task_id عبر فورم 'Где выполнено' الموجود
    في /request/{task_id}/history — بياخد الحقول الـ hidden ديناميكيًا من
    الفورم نفسه (بدل ما يفترضها) ويضيف عليها request[url] و request[message].

    التوقيت مبني على نمط بشري بسيط (تأخيرات عشوائية بين كل خطوة والتانية)
    عشان الطلبات ماتبقاش سلسلة سريعة جدًا ومتوقعة:
      1) فتح الصفحة، وتأخير بسيط زي وقت القراءة/التمرير.
      2) تأخير قبل "التركيز" على حقل الرابط.
      3) تأخير بعد "لصق" الرابط قبل الضغط على إرسال.
    ملحوظة مهمة: البوت ده بيشتغل بطلبات HTTP مباشرة (requests) مش متصفح
    حقيقي، فمفيش DOM ولا ماوس ولا سكرول فعلي يتحرك — التأخيرات دي بتحاكي
    الإيقاع الزمني البشري بس (وهو الحاجة اللي السيرفر فعليًا بيقدر يلاحظها
    زي معدل الطلبات)، مش حركة فأرة أو تمرير حقيقي على شاشة مش موجودة.
    """
    page_url = f"{BASE_URL}/request/{task_id}/history"
    try:
        r = session.get(page_url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return "FAILED"

        # 🕐 تأخير "قراءة/تمرير" الصفحة بعد فتحها
        time.sleep(random.uniform(1, 3))

        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form", attrs={"name": "message_form"})
        if not form:
            form = soup.find("form", action=re.compile(r"/history"))
        if not form:
            return "FAILED"

        post_data = {}
        for hidden_input in form.find_all("input", type="hidden"):
            if hidden_input.get("name"):
                post_data[hidden_input.get("name")] = hidden_input.get("value", "")

        # 🕐 تأخير "التركيز" على حقل الرابط قبل تعبئته
        time.sleep(random.uniform(1, 2))

        post_data["request[status]"]  = "completed"
        post_data["request[url]"]     = report_url
        post_data["request[message]"] = report_message

        # 🕐 تأخير بعد "لصق" البيانات وقبل الضغط على إرسال
        time.sleep(random.uniform(1, 3))

        action = form.get("action") or page_url
        post_action_url = action if action.startswith("http") else BASE_URL + action

        res = session.post(post_action_url, data=post_data, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return "FAILED"

        page_state = detect_page_state(res.text)
        if page_state == "blocked":
            return "BLOCKED"
        if page_state == "captcha":
            return "CAPTCHA"

        return "SUCCESS"
    except Exception:
        return "FAILED"


# ==========================================
# 🤖 تنفيذ مهام عبر القوالب (نفس منطق السكريبت اللي كان شغال على الهاتف،
# لكن الملف بقى بيتبعت عبر شات البوت بدل ما يتقرا من تخزين الهاتف المحلي)
# ==========================================
TEMPLATE_DB_DIR = "template_dbs"
os.makedirs(TEMPLATE_DB_DIR, exist_ok=True)


def _template_db_path(chat_id):
    return os.path.join(TEMPLATE_DB_DIR, f"{chat_id}.txt")


def parse_local_database(file_path):
    """
    بتحلل ملف القوالب (نفس الصيغة بالظبط اللي كانت بتتقرا من الهاتف):
    كل مهمة مرجعية مفصولة بـ © وفيها رابط الصورة (sun9...) ثم "URL:"
    ثم رابط التنفيذ، ثم "to be sure:" ثم نص التقرير.
    """
    database = {}
    if not os.path.exists(file_path):
        return database
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return database

    blocks = content.split("©")
    for block in blocks:
        if not block.strip():
            continue
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) >= 4:
            img_url = lines[1]
            img_clean_key = img_url.split("?")[0]

            url_work = ""
            to_be_sure = ""
            for i, line in enumerate(lines):
                if line.startswith("URL:") and i + 1 < len(lines):
                    url_work = lines[i + 1]
                if "to be sure:" in line and i + 1 < len(lines):
                    to_be_sure = lines[i + 1]

            if img_clean_key and url_work:
                database[img_clean_key] = {"url": url_work, "message": to_be_sure}

    return database


def get_template_db_for_chat(chat_id):
    """بتقرا وتحلل ملف القوالب الخاص بهذا الشات من على القرص (لو موجود)."""
    return parse_local_database(_template_db_path(chat_id))


def save_template_db_file(chat_id, file_bytes):
    """بتحفظ الملف اللي بعته المستخدم في الشات كقاعدة قوالب لهذا الشات."""
    path = _template_db_path(chat_id)
    with open(path, "wb") as f:
        f.write(file_bytes)
    # قاعدة جديدة = نتائج الفحص القديمة ممكن تتغيّر، فنمسح الكاش القديم
    with _template_cache_lock:
        _template_no_match_cache.pop(chat_id, None)
    return parse_local_database(path)


def delete_template_db_file(chat_id):
    """بتحذف ملف القوالب الخاص بهذا الشات لو موجود، وترجع True/False."""
    path = _template_db_path(chat_id)
    existed = os.path.exists(path)
    if existed:
        try:
            os.remove(path)
        except Exception:
            pass
    with _template_cache_lock:
        _template_no_match_cache.pop(chat_id, None)
    return existed


def _is_template_no_match_cached(chat_id, task_id):
    with _template_cache_lock:
        return task_id in _template_no_match_cache.get(chat_id, set())


def _mark_template_no_match(chat_id, task_id):
    with _template_cache_lock:
        _template_no_match_cache.setdefault(chat_id, set()).add(task_id)


SUN_IMAGE_URL_PATTERN = re.compile(
    r'https://sun9-\d+\.(?:userapi\.com|vkuserphoto\.ru)/[^\s"\'><]+'
)


def find_template_match_for_task(session, chat_id, task_id):
    """
    بتفحص مهمة واحدة مقابل قاعدة القوالب وترجع (status, matched_data):
      - ("CACHED_NO_MATCH", None) لو اتفحصت قبل كده ولقيت مفيش تطابق
      - ("NO_DB", None) لو مفيش ملف قوالب أصلاً
      - ("NO_IMAGE", None) لو الصفحة مفيهاش رابط صورة sun
      - ("NO_MATCH", None) لو فيه صورة بس مش موجودة في القوالب
      - ("MATCHED", {"url":..., "message":...}) لو لقيت تطابق
      - ("FAILED", None) لو حصل خطأ في الطلب نفسه

    لو النتيجة NO_IMAGE أو NO_MATCH، بتتسجل في كاش عام لكل الشات عشان أي
    حساب تاني يشوف نفس الـ task_id يتخطاه فورًا من غير ما يعيد الفحص.
    """
    if _is_template_no_match_cached(chat_id, task_id):
        return "CACHED_NO_MATCH", None

    db = get_template_db_for_chat(chat_id)
    if not db:
        return "NO_DB", None

    page_url = f"{BASE_URL}/request/{task_id}/history"
    try:
        r = session.get(page_url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return "FAILED", None

        found_urls = SUN_IMAGE_URL_PATTERN.findall(r.text)
        if not found_urls:
            _mark_template_no_match(chat_id, task_id)
            return "NO_IMAGE", None

        for sun_url in found_urls:
            clean_key = sun_url.split("?")[0]
            if clean_key in db:
                return "MATCHED", db[clean_key]

        _mark_template_no_match(chat_id, task_id)
        return "NO_MATCH", None
    except Exception:
        return "FAILED", None


def scan_and_match_all_tasks(session, chat_id, stop_event=None):
    """
    فحص فقط (من غير أي تنفيذ) لكل المهام المصطحبة حاليًا مقابل قاعدة
    البيانات. بترجع قائمة المهام المتطابقة (عشان تُنفّذ لاحقًا بعد المهلة
    العشوائية) + إحصائيات الفحص.
    """
    db = get_template_db_for_chat(chat_id)
    if not db:
        return {"error": "no_db"}

    tasks = fetch_confirmed_tasks(session)
    matched_list = []
    stats = {
        "total": len(tasks), "no_image": 0, "no_match": 0,
        "cached": 0, "check_failed": 0, "stopped": False,
    }

    for t in tasks:
        if stop_event is not None and stop_event.is_set():
            stats["stopped"] = True
            break

        task_id = t["id"]
        status, matched_data = find_template_match_for_task(session, chat_id, task_id)

        if status == "MATCHED":
            matched_list.append((task_id, matched_data))
        elif status == "CACHED_NO_MATCH":
            stats["cached"] += 1
        elif status == "NO_IMAGE":
            stats["no_image"] += 1
        elif status == "NO_MATCH":
            stats["no_match"] += 1
        else:
            stats["check_failed"] += 1

    return {"matched_list": matched_list, "stats": stats}


def _snapshot_confirmed_baseline(chat_id):
    """
    بتتنادى مرة واحدة أول ما يتفعّل زر 'تنفيذ تلقائي' — بتسجّل المهام
    المصطحبة الحالية لكل حساب كخط أساس، عشان بعد كده أي مهمة 'جديدة'
    تظهر في القائمة تتعرف إنها المهمة اللي لسه اتاخدت، من غير ما نعيد
    فحص المهام القديمة اللي كانت موجودة من قبل التفعيل.
    """
    saved = get_saved_multi_accounts(chat_id)
    for acc in saved:
        email_lower = acc['email'].lower().strip()
        try:
            session = get_authenticated_session(acc['email'], acc['password'], chat_id)
            if not session:
                continue
            tasks = fetch_confirmed_tasks(session)
            _known_confirmed_ids[(chat_id, email_lower)] = {t['id'] for t in tasks}
        except Exception:
            continue


def handle_task_taken_for_templates(chat_id, email, password):
    """
    بتتنادى فورًا بعد أي اصطحاب ناجح (لو زر 'تمرير تنفيذ بعد الاصطحاب'
    شغال بس). بتقارن قائمة المهام المصطحبة الحالية بالـ baseline المحفوظ،
    وأي ID جديد ظهر (يعني المهمة اللي لسه اتاخدت) بيتفحص فورًا مقابل
    القوالب. لو فيه تطابق، مش بيتنفذ فورًا — بيستنى مهلة عشوائية بين 9
    و20 دقيقة الأول، وبعدين يبعت التقرير. لو مفيش تطابق، تُترك المهمة
    دون أي تدخل.
    """
    email_lower = email.lower().strip()
    try:
        session = get_authenticated_session(email, password, chat_id)
        if not session:
            return
        tasks = fetch_confirmed_tasks(session)
        current_ids = {t['id'] for t in tasks}
        known = _known_confirmed_ids.get((chat_id, email_lower), set())
        newly_appeared = current_ids - known
        _known_confirmed_ids[(chat_id, email_lower)] = current_ids

        for task_id in newly_appeared:
            status, matched_data = find_template_match_for_task(session, chat_id, task_id)
            if status != "MATCHED":
                continue  # مفيش تطابق — تُترك المهمة دون أي تدخل

            delay_seconds = random.randint(9 * 60, 20 * 60)
            threading.Thread(
                target=_delayed_template_submit,
                args=(chat_id, email, password, task_id, matched_data, delay_seconds),
                daemon=True
            ).start()
    except Exception as e:
        print(f"[TEMPLATE] خطأ في الفحص بعد الاصطحاب: {e}")


def _delayed_template_submit(chat_id, email, password, task_id, matched_data, delay_seconds):
    """بتستنى المهلة العشوائية المحسوبة، وبعدين تبعت تقرير المهمة."""
    time.sleep(delay_seconds)
    try:
        session = get_authenticated_session(email, password, chat_id)
        if not session:
            return
        status = submit_task_report(session, task_id, matched_data["url"], matched_data["message"])
        if status == "SUCCESS":
            try:
                bot.send_message(
                    chat_id,
                    f"🤖 **تمرير تنفيذ بعد الاصطحاب**\n\n"
                    f"✅ تم تنفيذ المهمة #{task_id} تلقائيًا بعد مهلة {delay_seconds // 60} دقيقة."
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[TEMPLATE] خطأ في التنفيذ المؤجل للمهمة {task_id}: {e}")

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

# ==========================================
# 🌐 الـ IP الحقيقي الحالي (IP الهاتف نفسه — بدون بروكسي)
# ==========================================
_current_ip_cache = {"ip": None, "ts": 0}
IP_CACHE_TTL_SECONDS = 20  # كاش قصير جدًا عشان يفضل حقيقي وحديث، مش IP قديم من وقت تسجيل الدخول


def get_current_public_ip():
    """
    بترجع الـ IP الحقيقي الحالي اللي البوت شغال بيه فعليًا دلوقتي (IP
    الهاتف نفسه، مفيش بروكسي). بتتحدث تلقائيًا كل {IP_CACHE_TTL_SECONDS}
    ثانية بس — مش بترجع IP قديم متخزن من وقت تسجيل الدخول، وبتشتغل حتى
    لو الحساب جديد أو مجهول (لأن الـ IP مالوش علاقة بالحساب نفسه، هو IP
    الجهاز اللي البوت شغال عليه).
    """
    now = time.time()
    if _current_ip_cache["ip"] and (now - _current_ip_cache["ts"]) < IP_CACHE_TTL_SECONDS:
        return _current_ip_cache["ip"]
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        ip = r.json().get("ip") or "غير معروف"
    except Exception:
        # لو الطلب فشل، منرجعش IP قديم مكذوب — إما آخر قيمة معروفة أو "غير معروف"
        ip = _current_ip_cache["ip"] or "غير معروف"
    _current_ip_cache["ip"] = ip
    _current_ip_cache["ts"] = now
    return ip


def get_main_menu_text(chat_id=None) -> str:
    text = f"🏠 القائمة الرئيسية  {get_countdown_text()}\nــــــــــــــــــ"
    if chat_id and chat_id in user_data_store:
        email = user_data_store[chat_id].get('email', '')
        if email:
            ip = get_current_public_ip()
            text += f"\n{email}\nIp: {ip}"
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
    markup.add(types.InlineKeyboardButton(
        "✅ تنفيذ مهام", callback_data="submit_tasks_menu"
    ))
    markup.add(types.InlineKeyboardButton(
        "🤖 تنفيذ عبر القوالب", callback_data="template_menu"
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

def get_template_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    scan_on  = template_scan_status.get(chat_id, False)
    delay_on = template_delay_status.get(chat_id, False)
    markup.add(types.InlineKeyboardButton(
        f"تنفيذ المهام (الحالية)  {'🟢' if scan_on else '🔴'}",
        callback_data="template_scan_toggle"
    ))
    markup.add(types.InlineKeyboardButton(
        f"تمرير تنفيذ بعد الاصطحاب  {'🟢' if delay_on else '🔴'}",
        callback_data="template_delay_toggle"
    ))
    markup.add(types.InlineKeyboardButton(
        "📎 إضافة ملف قاعدة بيانات", callback_data="template_upload_start"
    ))
    markup.add(types.InlineKeyboardButton(
        "🗑️ حذف ملف قاعدة بيانات", callback_data="template_delete"
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


WAKE_MAX_PER_BURST = 2  # أقصى عدد مرات "إيقاظ" مبكر مسموح بيها للحساب خلال نفس الدفعة
_wake_count       = {}  # key -> عدد مرات الإيقاظ في الدفعة الحالية
_wake_burst_start = {}  # key -> وقت أول إيقاظ في الدفعة الحالية

RESTAGGER_DELAY_SECONDS = 15  # وقت كافي لكل الحسابات الموقظة تعمل فحصها الفوري قبل ما نعيد التنظيم
_pending_restagger      = set()  # chat_ids فيها إعادة تنظيم مجدولة بالفعل (لمنع التكرار)
_pending_restagger_lock = threading.Lock()


def _schedule_restagger(chat_id):
    """
    بعد أي دفعة إيقاظ، الحسابات بتتجمع كلها قريب من بعض بدل التوزيع
    المتباعد الأصلي (0، 20، 40، 60 ثانية...). الدالة دي بتجدول إعادة
    توزيع (recompute_hunt_stagger) بعد فترة قصيرة كافية إن كل حساب
    اتوقظ يكون خلص فحصه الفوري، فيرجعوا يشتغلوا منظمين تاني بنفس الفارق
    (80 ÷ عدد الحسابات) — بس محسوب من اللحظة دي كخط أساس جديد.
    مفيش تكرار: لو فيه إعادة تنظيم مجدولة بالفعل لنفس الشات، مبنجدولش تانية.
    """
    with _pending_restagger_lock:
        if chat_id in _pending_restagger:
            return
        _pending_restagger.add(chat_id)

    def _do():
        try:
            time.sleep(RESTAGGER_DELAY_SECONDS)
            recompute_hunt_stagger(chat_id)
        finally:
            with _pending_restagger_lock:
                _pending_restagger.discard(chat_id)

    threading.Thread(target=_do, daemon=True).start()


def _wake_other_accounts(chat_id, current_email_lower):
    """
    لما حساب يكتشف مهمة موجودة فعلاً، الدالة دي بتخلي باقي حسابات نفس
    الشات تحاول تصطحب فورًا (في أقرب دورة فحص خلال 5 ثواني بالأكتر)، من
    غير ما تستنى الـ80 ثانية بتاعتها تكتمل.

    عشان مايحصلش تكديس طلبات سريعة على بعض (لو ظهرت كذا مهمة قريب من
    بعض واستفزت أكتر من حساب ينبّه في نفس الوقت) ويزوّد احتمال ظهور
    captcha، كل حساب مسموح له بإيقاظ مبكر مرتين بس خلال أي نافذة 80
    ثانية. أي محاولة إيقاظ تالتة قبل ما الـ80 ثانية تكتمل بتتجاهل تمامًا،
    فالحساب يرجع ياخد مهلته الطبيعية كاملة.

    وبعد أي إيقاظ فعلي، بتتجدول إعادة توزيع (شوف _schedule_restagger)
    عشان الحسابات ترجع تشتغل بفارق (80 ÷ عدد الحسابات) منظم زي الأصل،
    بدل ما تفضل متكدسة قريب من بعض بعد التنبيه.
    """
    with active_accounts_lock:
        accounts = dict(active_accounts.get(chat_id, {}))
    now = time.time()
    woke_anyone = False
    for email_key in accounts.keys():
        if email_key == current_email_lower:
            continue
        key = (chat_id, email_key)

        burst_start = _wake_burst_start.get(key)
        count = _wake_count.get(key, 0)

        # عدت 80 ثانية من أول إيقاظ في الدفعة الحالية؟ ابدأ عدّ جديد من الصفر
        if burst_start is None or (now - burst_start) >= HUNT_INTERVAL_SECONDS:
            burst_start = now
            count = 0

        if count >= WAKE_MAX_PER_BURST:
            continue  # اتنبه كفاية — سيبه ياخد مهلته الطبيعية

        _bg_last_hunt[key] = 0
        count += 1
        _wake_count[key] = count
        _wake_burst_start[key] = burst_start
        woke_anyone = True

    if woke_anyone:
        _schedule_restagger(chat_id)


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
                                # 🌐 لا بروكسي هنا — الاتصال بيمشي على IP الهاتف مباشرة
                                take_status = take_task_via_post(
                                    session, target_task['task_page']
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
                                    # 🤖 لو زر "تنفيذ تلقائي عبر القوالب" شغال، مرّر المهمة دي
                                    # للفحص فورًا (من غير مهلة، ماشي مع حدث الاصطحاب نفسه)
                                    if template_delay_status.get(chat_id, False):
                                        threading.Thread(
                                            target=handle_task_taken_for_templates,
                                            args=(chat_id, email, password),
                                            daemon=True
                                        ).start()
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
        if step in ['WAITING_EMAIL', 'WAITING_PASSWORD', 'WAITING_DELETE_ACCOUNT',
                    'WAITING_REPORT_URL', 'WAITING_REPORT_MESSAGE']:
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
                        f"⚖️ التحكيم: {result['stats']['arbitration']}\n"
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

    elif data == "submit_tasks_menu":
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
            bot.edit_message_text("⏳ جارٍ جلب المهام المصطحبة...", chat_id, message_id)
        except Exception:
            pass

        def _do_submit_menu():
            session = get_authenticated_session(creds['email'], creds['password'], chat_id)
            if not session:
                err_markup = types.InlineKeyboardMarkup()
                err_markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                try:
                    bot.edit_message_text("⚠️ فشل تسجيل الدخول.",
                                          chat_id, message_id, reply_markup=err_markup)
                except Exception:
                    pass
                return
            tasks = fetch_confirmed_tasks(session)
            markup = types.InlineKeyboardMarkup(row_width=1)
            if tasks:
                for t in tasks[:15]:
                    label = (f"{t['title']} — متبقي {t['remaining']}"
                             if t['remaining'] else t['title'])
                    markup.add(types.InlineKeyboardButton(
                        label, callback_data=f"submit_task_{t['id']}"
                    ))
                msg = "✅ **اختر المهمة اللي عايز تنفّذها (ترسل تقرير الإنجاز):**"
            else:
                msg = "🟢 مفيش مهام مصطحبة محتاجة تنفيذ حالياً."
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
            try:
                bot.edit_message_text(msg, chat_id, message_id,
                                     parse_mode="Markdown", reply_markup=markup)
            except Exception:
                bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

        threading.Thread(target=_do_submit_menu, daemon=True).start()

    elif data.startswith("submit_task_"):
        bot.answer_callback_query(call.id)
        task_id = data.replace("submit_task_", "")
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "🔗 أدخل الرابط اللي نفذت فيه المهمة (Где выполнено):")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_REPORT_URL', 'task_id': task_id}

    elif data.startswith("captcha_resolved_"):
        email_lower = data.replace("captcha_resolved_", "")
        acct_auto_hunt_status[email_lower] = True

        # لو الحساب ده هو النشط حاليًا في الشات، رجّع مزامنة حالة أزرار GT/GTE معاه
        active_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
        if active_email == email_lower:
            sync_email_settings_to_chat(chat_id, email_lower)

        bot.answer_callback_query(call.id, "✅ تم إرجاع الحساب للعمل")
        try:
            bot.edit_message_text(
                f"✅ **تم إرجاع الحساب `{email_lower}` للاصطحاب العادي.**",
                chat_id, message_id, parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "template_menu":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "🤖 **القوالب**\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_template_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "template_scan_toggle":
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

        currently_on = template_scan_status.get(chat_id, False)

        if not currently_on:
            db = get_template_db_for_chat(chat_id)
            if not db:
                try:
                    bot.edit_message_text(
                        "🚫 **يرجى إضافة ملف قاعدة بيانات (.txt) أولاً لتتمكن من تشغيل الخدمة.**",
                        chat_id, message_id,
                        parse_mode="Markdown", reply_markup=get_template_menu(chat_id)
                    )
                except Exception:
                    pass
                return  # الزر بيفضل 🔴 لأن التفعيل اتلغى

            template_scan_status[chat_id] = True
            stop_event = threading.Event()
            template_scan_stop_events[chat_id] = stop_event
            try:
                bot.edit_message_text(
                    "✅ **تم تشغيل تنفيذ المهام**\n"
                    "🔍 جاري فحص المهام المصطحبة حالياً مقابل قاعدة البيانات...",
                    chat_id, message_id,
                    parse_mode="Markdown", reply_markup=get_template_menu(chat_id)
                )
            except Exception:
                pass

            def _run_scan():
                session = get_authenticated_session(creds['email'], creds['password'], chat_id)
                if not session:
                    template_scan_status[chat_id] = False
                    template_scan_stop_events.pop(chat_id, None)
                    bot.send_message(chat_id, "❌ فشل تسجيل الدخول، حاول تاني.",
                                     reply_markup=get_template_menu(chat_id))
                    return

                # المرحلة 1: فحص كل المهام الحالية مقابل القاعدة (من غير أي تنفيذ بعد)
                scan_result = scan_and_match_all_tasks(session, chat_id, stop_event=stop_event)
                if scan_result.get("error") == "no_db":
                    template_scan_status[chat_id] = False
                    template_scan_stop_events.pop(chat_id, None)
                    bot.send_message(chat_id, "📎 مفيش ملف قاعدة بيانات مرفوع.",
                                     reply_markup=get_template_menu(chat_id))
                    return

                matched_list = scan_result["matched_list"]
                stats = scan_result["stats"]

                if not matched_list:
                    template_scan_status[chat_id] = False
                    template_scan_stop_events.pop(chat_id, None)
                    note = " (تم إيقاف الفحص يدويًا)" if stats.get("stopped") else ""
                    bot.send_message(
                        chat_id,
                        f"🔴 **لا توجد مهام مطابقة حاليًا{note}**\n"
                        f"📋 تم فحص {stats['total']} مهمة من غير أي تطابق.",
                        parse_mode="Markdown", reply_markup=get_template_menu(chat_id)
                    )
                    return

                # المرحلة 2: إعلان عدد المهام المطابقة اللي هتتنفذ
                try:
                    bot.send_message(
                        chat_id,
                        f"🎯 **تم العثور على {len(matched_list)} مهمة مطابقة من إجمالي {stats['total']}**\n\n"
                        f"⏳ جاري تنفيذها الآن واحدة واحدة (بفاصل عشوائي 3-20 ثانية بين كل مهمة والتانية)...",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

                # المرحلة 3: تنفيذ كل مهمة مطابقة، بفارق عشوائي 3-20 ثانية بين كل مهمة والتانية
                submitted = 0
                failed = 0
                stopped_mid = False
                for i, (task_id, matched_data) in enumerate(matched_list):
                    if stop_event.is_set():
                        stopped_mid = True
                        break

                    status = submit_task_report(session, task_id,
                                                matched_data["url"], matched_data["message"])
                    if status == "SUCCESS":
                        submitted += 1
                    elif status == "BLOCKED":
                        threading.Thread(target=handle_blocked_account,
                                         args=(creds['email'],), daemon=True).start()
                        failed += 1
                        break
                    else:
                        failed += 1

                    if i < len(matched_list) - 1:
                        gap = random.randint(3, 20)
                        gap_waited = 0
                        while gap_waited < gap:
                            if stop_event.is_set():
                                stopped_mid = True
                                break
                            time.sleep(1)
                            gap_waited += 1
                        if stopped_mid:
                            break

                template_scan_status[chat_id] = False
                template_scan_stop_events.pop(chat_id, None)

                stopped_note = " (تم إيقافه يدويًا أثناء التنفيذ)" if stopped_mid else ""
                summary = (
                    f"🔴 **انتهى تنفيذ المهام{stopped_note}**\n\n"
                    f"🎯 مطابقة: {len(matched_list)}\n"
                    f"✅ تم تنفيذها فعليًا: {submitted}\n"
                    f"❌ فشل: {failed}\n"
                    f"🖼️ من غير صورة: {stats['no_image']}\n"
                    f"🔍 غير مطابقة: {stats['no_match']}\n"
                    f"⏭️ متخطاة (كاش): {stats['cached']}"
                )
                bot.send_message(chat_id, summary, parse_mode="Markdown",
                                 reply_markup=get_template_menu(chat_id))

            threading.Thread(target=_run_scan, daemon=True).start()

        else:
            # إيقاف فوري وسلس: نضبط علم التوقف، والحلقة بتخرج بعد المهمة الحالية بس
            stop_event = template_scan_stop_events.get(chat_id)
            if stop_event:
                stop_event.set()
            template_scan_status[chat_id] = False
            try:
                bot.edit_message_text(
                    "🔴 **تم إيقاف تنفيذ المهام**",
                    chat_id, message_id,
                    parse_mode="Markdown", reply_markup=get_template_menu(chat_id)
                )
            except Exception:
                pass

    elif data == "template_delay_toggle":
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

        currently_on = template_delay_status.get(chat_id, False)

        if not currently_on:
            db = get_template_db_for_chat(chat_id)
            if not db:
                try:
                    bot.edit_message_text(
                        "🚫 **يرجى إضافة ملف قاعدة بيانات (.txt) أولاً لتتمكن من تشغيل الخدمة.**",
                        chat_id, message_id,
                        parse_mode="Markdown", reply_markup=get_template_menu(chat_id)
                    )
                except Exception:
                    pass
                return

            template_delay_status[chat_id] = True
            threading.Thread(target=_snapshot_confirmed_baseline,
                             args=(chat_id,), daemon=True).start()
            status_msg = "✅ تم تشغيل تمرير التنفيذ بعد الاصطحاب (مهلة 9–20 دقيقة عشوائية)"
        else:
            template_delay_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تمرير التنفيذ بعد الاصطحاب"

        try:
            bot.edit_message_text(
                f"🤖 **القوالب**\n{status_msg}\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_template_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "template_upload_start":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            chat_id,
            "📎 ابعتلي دلوقتي ملف قاعدة البيانات (.txt) كمرفق (Document) هنا في الشات."
        )
        user_transient_messages[chat_id] = msg.message_id

    elif data == "template_delete":
        bot.answer_callback_query(call.id)
        existed = delete_template_db_file(chat_id)

        # وقف أي خدمة شغالة كانت معتمدة على الملف ده
        stopped_services = []
        if template_scan_status.get(chat_id, False):
            ev = template_scan_stop_events.get(chat_id)
            if ev:
                ev.set()
            template_scan_status[chat_id] = False
            stopped_services.append("تنفيذ المهام")
        if template_delay_status.get(chat_id, False):
            template_delay_status[chat_id] = False
            stopped_services.append("تمرير تنفيذ بعد الاصطحاب")

        if existed:
            msg = "🗑️ تم حذف ملف قاعدة البيانات بنجاح."
            if stopped_services:
                msg += f"\n⚠️ تم إيقاف: {', '.join(stopped_services)} تلقائيًا لاعتمادهم على الملف."
        else:
            msg = "ℹ️ مفيش ملف قاعدة بيانات مرفوع أصلاً."

        try:
            bot.edit_message_text(
                f"🤖 **القوالب**\n{msg}\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_template_menu(chat_id),
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

        elif step == 'WAITING_REPORT_URL':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            user_sessions[chat_id]['report_url'] = text
            user_sessions[chat_id]['step'] = 'WAITING_REPORT_MESSAGE'
            msg = bot.send_message(
                chat_id,
                "📝 أدخل أي ملاحظات إضافية (اختياري) — أو أرسل '-' لو مفيش:"
            )
            user_transient_messages[chat_id] = msg.message_id
            return

        elif step == 'WAITING_REPORT_MESSAGE':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            task_id    = user_sessions[chat_id].get('task_id')
            report_url = user_sessions[chat_id].get('report_url', '')
            report_msg = "" if text.strip() == "-" else text
            del user_sessions[chat_id]

            creds = user_data_store.get(chat_id)
            if not creds:
                bot.send_message(chat_id, "⚠️ يرجى تسجيل الدخول أولاً.",
                                 reply_markup=get_auth_menu(chat_id))
                return

            status_msg = bot.send_message(chat_id, "⏳ جاري إرسال التقرير...")

            def _do_submit_report():
                session = get_authenticated_session(creds['email'], creds['password'], chat_id)
                try:
                    bot.delete_message(chat_id, status_msg.message_id)
                except Exception:
                    pass
                if not session:
                    bot.send_message(chat_id, "❌ فشل تسجيل الدخول، حاول تاني.",
                                     reply_markup=get_main_menu(chat_id))
                    return
                result = submit_task_report(session, task_id, report_url, report_msg)
                if result == "SUCCESS":
                    bot.send_message(
                        chat_id,
                        f"✅ **تم إرسال تقرير المهمة #{task_id} بنجاح**",
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(chat_id)
                    )
                elif result == "BLOCKED":
                    threading.Thread(target=handle_blocked_account,
                                     args=(creds['email'],), daemon=True).start()
                elif result == "CAPTCHA":
                    threading.Thread(target=handle_captcha_detected,
                                     args=(creds['email'], "إرسال تقرير"), daemon=True).start()
                else:
                    bot.send_message(
                        chat_id,
                        f"❌ فشل إرسال تقرير المهمة #{task_id}، حاول تاني.",
                        reply_markup=get_main_menu(chat_id)
                    )

            threading.Thread(target=_do_submit_report, daemon=True).start()
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


@bot.message_handler(content_types=['document'])
def handle_template_document(message):
    """
    استقبال ملف قاعدة القوالب (نفس صيغة F_C_NOWE.txt) كمرفق في الشات —
    بديل إرسال الملف من تخزين الهاتف المحلي بما إننا بقينا على استضافة.
    """
    chat_id = message.chat.id
    try:
        doc = message.document
        filename = (doc.file_name or "").lower()
        if not filename.endswith(".txt"):
            bot.reply_to(message, "⚠️ محتاج ملف نصي (.txt) بصيغة قاعدة القوالب.")
            return

        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        db = save_template_db_file(chat_id, downloaded)

        if not db:
            bot.reply_to(
                message,
                "⚠️ تم استلام الملف لكن مفيش أي قالب اتفهم منه — تأكد إن الصيغة "
                "زي مثال `F_C_NOWE.txt` (كل مهمة تبدأ بـ © ومفصولة زي المطلوب)."
            )
            return

        bot.reply_to(
            message,
            f"✅ **تم استلام قاعدة القوالب بنجاح**\n\n"
            f"📦 عدد القوالب المرجعية: {len(db)}\n"
            f"اضغط \"🤖 تنفيذ عبر القوالب\" من القائمة الرئيسية عشان يبدأ التنفيذ.",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[TEMPLATE] خطأ في استلام الملف: {e}")
        try:
            bot.reply_to(message, "⚠️ حصل خطأ أثناء استلام الملف، حاول تاني.")
        except Exception:
            pass


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
