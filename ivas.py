# -*- coding: utf-8 -*-
import asyncio
import re
import requests
from bs4 import BeautifulSoup
import time
import html 
import json
import os
import traceback
from telegram import Bot
from urllib.parse import urljoin
from datetime import datetime, timedelta

# --- إعداداتك ---
YOUR_BOT_TOKEN = "8221352741:AAG3VIrf-qbrYydQW9Ljg4-SOUXHCmQ0s34"
YOUR_CHAT_IDS = ["-1003219322152"]

LOGIN_URL = "https://ivas.jackx.qzz.io/login"
BASE_URL = "https://ivas.jackx.qzz.io/"
SMS_API_ENDPOINT = "https://ivas.jackx.qzz.io/portal/sms/received/getsms"

USERNAME = "albrans182@gmail.com"
PASSWORD = "albrans123"

POLLING_INTERVAL_SECONDS = 5 # زدنا الوقت قليلاً ليكون أكثر أماناً
STATE_FILE = "processed_sms_ids_ivasms.json"

# ... (قواميس الدول والخدمات تبقى كما هي في كودك) ...
COUNTRY_FLAGS = {"Afghanistan": "🇦🇫", "Bangladesh": "🇧🇩", "India": "🇮🇳", "United States": "🇺🇸", "TOGO": "🇹🇬", "Unknown Country": "🏴‍☠️"}
known_services = {
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "google": "google",
    "netflix": "netflix",
    "binance": "binance",
    "unknown": "unknown"
}

def detect_service(sms_text, service_div_text):
    service_text = service_div_text or ""
    for svc_name in known_services:
        if svc_name.lower() in service_text.lower() or svc_name.lower() in sms_text.lower():
            return svc_name.lower()  # الآن يظهر بالحروف الصغيرة
    return "unknown"

def load_processed_ids():
    if not os.path.exists(STATE_FILE): return set()
    try:
        with open(STATE_FILE, 'r') as f: return set(json.load(f))
    except: return set()

def save_processed_ids(processed_ids):
    with open(STATE_FILE, 'w') as f: json.dump(list(processed_ids), f)

async def send_telegram_message(bot, chat_id, message_data):
    try:
        number_str = message_data.get("number", "N/A")
        code_str = message_data.get("code", "N/A")
        # تنظيف نص الرسالة من الرموز الحساسة مثل < > & # لكي لا تسبب خطأ HTML
        raw_sms = str(message_data.get("full_sms", "N/A"))
        safe_sms = html.escape(raw_sms) 

        # تنسيق الرسالة النهائي
        full_message = (
            f"{number_str}\n\n"
            f"{code_str}\n\n"
            f"{safe_sms}"
        )
        
        await bot.send_message(
            chat_id=chat_id,
            text=full_message,
            parse_mode="HTML"
        )

    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")

async def main_loop():
    print("🚀 بدء تشغيل البوت...")
    session = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0'}
    bot = Bot(token=YOUR_BOT_TOKEN)
    
    # 1. تسجيل الدخول لمرة واحدة
    try:
        print("🔑 محاولة تسجيل الدخول لمرة واحدة...")
        res = session.get(LOGIN_URL, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        token = soup.find('input', {'name': '_token'})['value']
        
        login_data = {'email': USERNAME, 'password': PASSWORD, '_token': token}
        login_res = session.post(LOGIN_URL, data=login_data, headers=headers)
        
        if "login" in login_res.url:
            print("❌ فشل تسجيل الدخول! تأكد من البيانات.")
            return
        print("✅ تم تسجيل الدخول بنجاح.")
        
        # استخراج توكن الجلسة الجديد للاستخدام في الـ API
        dash_soup = BeautifulSoup(login_res.text, 'html.parser')
        csrf_token = dash_soup.find('meta', {'name': 'csrf-token'})['content']
    except Exception as e:
        print(f"❌ خطأ في تسجيل الدخول: {e}")
        return

    processed_ids = load_processed_ids()

    # 2. حلقة الفحص المتكرر
    while True:
        try:
            print(f"\n--- [{datetime.now().strftime('%H:%M:%S')}] فحص رسائل جديدة ---")
            
            # جلب الرسائل (نستخدم الدالة fetch_sms_from_api التي في كودك)
            # تم دمج المنطق هنا لتبسيط العمل
            today = datetime.now()
            from_date = (today - timedelta(days=1)).strftime('%m/%d/%Y')
            to_date = today.strftime('%m/%d/%Y')
            
            api_payload = {'from': from_date, 'to': to_date, '_token': csrf_token}
            response = session.post(SMS_API_ENDPOINT, data=api_payload, headers=headers)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            group_divs = soup.find_all('div', {'class': 'pointer'})
            
            for div in group_divs:
                group_id = re.search(r"getDetials\('(.+?)'\)", div.get('onclick', '')).group(1)
                
                # جلب الأرقام لكل مجموعة
                num_url = urljoin(BASE_URL, "portal/sms/received/getsms/number")
                num_res = session.post(num_url, data={'start': from_date, 'end': to_date, 'range': group_id, '_token': csrf_token})
                num_soup = BeautifulSoup(num_res.text, 'html.parser')
                
                for num_div in num_soup.select("div[onclick*='getDetialsNumber']"):
                    phone = num_div.text.strip()
                    
                    # جلب الرسائل لكل رقم
                    sms_url = urljoin(BASE_URL, "portal/sms/received/getsms/number/sms")
                    sms_res = session.post(sms_url, data={'start': from_date, 'end': to_date, 'Number': phone, 'Range': group_id, '_token': csrf_token})
                    sms_soup = BeautifulSoup(sms_res.text, 'html.parser')
                    
                    for card in sms_soup.find_all('div', class_='card-body'):
                        p_tag = card.find('p', class_='mb-0')
                        if not p_tag: continue
                        
                        sms_text = p_tag.get_text(separator='\n').strip()
                        unique_id = f"{phone}-{sms_text}" # معرف فريد
                        
                        if unique_id not in processed_ids:
                            print(f"🆕 رسالة جديدة من {phone}!")
                            
                            # استخراج البيانات
                            service_div = card.find('div', class_='col-sm-4')
                            service = detect_service(sms_text, service_div.text if service_div else "")
                            code_match = re.search(r'(\d{3}-\d{3})', sms_text) or re.search(r'\b(\d{4,8})\b', sms_text)
                            
                            msg_data = {
                                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "number": phone,
                                "country": group_id.split(' ')[0],
                                "flag": COUNTRY_FLAGS.get(group_id.split(' ')[0], "🏴‍☠️"),
                                "service": service,
                                "code": code_match.group(1) if code_match else "N/A",
                                "full_sms": sms_text
                            }
                            
                            # إرسال لكل الـ Chat IDs
                            for cid in YOUR_CHAT_IDS:
                                await send_telegram_message(bot, cid, msg_data)
                            
                            processed_ids.add(unique_id)
                            save_processed_ids(processed_ids)

            print(f"💤 انتظار {POLLING_INTERVAL_SECONDS} ثانية...")
            await asyncio.sleep(POLLING_INTERVAL_SECONDS)
            
        except Exception as e:
            print(f"❌ حدث خطأ أثناء الفحص: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف البوت.")
        