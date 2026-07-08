import time
import random
import os
import psutil
import requests
import asyncio
import aiohttp
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from PIL import Image
import pyttsx3  # 🎙 سیستم آفلاین و باکیفیت جدید برای صدای مردونه و رفع ارور زبان فارسی

# استفاده از API رسمی و عمومی تلگرام
API_ID = 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

app = Client("aria_assistant", api_id=API_ID, api_hash=API_HASH)

# زمان روشن شدن ربات برای محاسبه دقیق آپ‌تایم سیستم
START_TIME = time.time()

# حافظه وضعیت‌ها, بازی‌ها, کلاک زنده و متغیرهای محلی
games = {}
last_replied = {}       # آنتی‌اسپم ۵ دقیقه‌ای منشی تلفنی
live_clocks = {}        # وضعیت کلاک‌های زنده فعال در چت‌ها
live_crypto_active = {} # وضعیت مانیتور زنده ارز و تتر

settings = {
    "night_mode": False,       # مود شب (۱۲ شب تا ۸ صبح)
    "group_assistant": False,  # منشی در گروه‌ها (پیش‌فرض خاموش)
    "status": "آفلاین"         # وضعیت فعلی آریا (باشگاه، گیم، درس و...)
}

# تابع کمکی جدید برای دانلود ناهمگام و پرسرعت فایل از اینترنت
async def download_file(url, destination):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                with open(destination, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024 * 1024) # تکه‌های ۱ مگابایتی
                        if not chunk:
                            break
                        f.write(chunk)
                return True
    return False

# تابع تبدیل متن به ویس با صدای مردونه و پشتیبانی کامل از فارسی
def text_to_voice_male(text, output_file):
    engine = pyttsx3.init()
    
    # تنظیم سرعت خواندن ویس (۱۶۰ لاتی‌ترین و روان‌ترین حالته)
    engine.setProperty('rate', 160)
    
    # ست کردن صدای مردونه موتور صوتی سیستم
    voices = engine.getProperty('voices')
    for voice in voices:
        if "male" in voice.name.lower() or "m" in voice.id.lower():
            engine.setProperty('voice', voice.id)
            break
            
    engine.save_to_file(text, output_file)
    engine.runAndWait()

# --- بخش اول: دستورات ادمین (فقط خودت می‌توانی اجرا کنی) ---
@app.on_message(filters.me & filters.text)
async def admin_commands(client, message):
    text = message.text.strip() if message.text else ""
    text_lower = text.lower()
    chat_id = message.chat.id
    me = await client.get_me()
    is_saved_messages = message.chat.type.value == "private" and message.chat.id == me.id

    # 🔹 قابلیت راهنمای کامل دستورات (فقط در بخش Saved Messages کار می‌کند)
    if is_saved_messages and text_lower == "help":
        help_text = (
            "👑 **داشبورد فرمانروایی یوزربات آریا:**\n\n"
            "⚙️ **تنظیمات مشتی و منشی (ارسال در سیو مسج):**\n"
            "• `night mode on` ➡️ فعال‌سازی مود شب (منشی اتوماتیک مخلصم از ساعت ۱۲ شب تا ۸ صبح)\n"
            "• `night mode off` ➡️ غیرفعال‌سازی مود شب\n"
            "• `group bot on` ➡️ فعال‌سازی منشی باصفا در گروه‌ها اگه تگت کردن\n"
            "• `group bot off` ➡️ خاموش کردن منشی گروه‌ها\n"
            "• `set status [متن]` ➡️ تگ کردن وضعیت چاکریم (کجا پلاسیم؟)\n"
            "• `clear status` ➡️ پاک کردن وضعیت فعلی\n"
            "• `status` ➡️ آمار و ارقام موتور گوشی (باتری، رم و آپ‌تایم ربات)\n"
            "• `profile [آیدی]` ➡️ دانلود رگباری تمام عکس‌های پروفایل طرف\n\n"
            "🛠 **ابزارهای زنده, دست‌فرمان‌ها و قابلیت‌های خاص:**\n"
            "• `.voice` یا `.tts` ➡️ (رو پیام متنی ریپلای کن یا جلوش متن بنویس) تبدیل متن به ویس صوتی مردونه بدون تحریم 🎙\n"
            "• `.dl [لینک]` ➡️ لیچ و دانلود فایل با سرعت نور از وب و آپلود در تلگرام ⚡️\n"
            "• `.fly [متن]` ➡️ پرواز تماشایی هواپیما روی متنت (روشن کردن موتور جت) 🛫\n"
            "• `.duel` ➡️ (روی پیام طرف ریپلای کن) شروع مبارزه و دوئل متحرک لایو مچ‌اندازی ⚔️\n"
            "• `bomb [تعداد] [متن]` ➡️ به توپ بستن و ارسال رگباری پیام\n"
            "• `code [متن]` ➡️ مشتی کردن کدهات توی باکس خوشگل پایتون\n"
            "• `del [تعداد]` ➡️ غیب کردن پیام‌های خودت به صورت دوطرفه و سه‌سوت\n"
            "• `info` ➡️ (رو پیام ریپلای کن) تار و پود و آمار کارآگاهی طرف\n"
            "• `age` ➡️ (رو پیام ریپلای کن) حساب کتابِ اینکه طرف چند ساله تو تلگرامه\n"
            "• `stats` ➡️ آمارگیر کل تاریخچه چت جاری بدون هیچ محدودیتی 📊\n"
            "• `clock` ➡️ ساعت دیجیتال زنده و ثانیه‌شمار تو چت\n"
            "• `stopclock` ➡️ متوقف کردن ساعت لایو\n"
            "• `.marquee [متن]` ➡️ راه انداختن تابلوروان متحرک دور متنت\n"
            "• `.live_crypto` ➡️ تابلوی زنده قیمت دلار و تتر تو چت\n"
            "• `.stop_live` ➡️ تخته کردن دکون تابلوی ارز\n"
            "• `.effect [متن]` ➡️ افکت متحرک سه مرحله‌ای مشتی واسه متنت\n\n"
            "👥 **دستورات گروهی:**\n"
            "• `all [متن]` ➡️ تگ همگانی نامرئی؛ همه گپ رو بی‌صدا بکش بالا!\n\n"
            "🎨 **ابزار استیکر (با ریپلای روی پیام):**\n"
            "• `sticker` ➡️ تبدیل عکس به استیکر مشتیِ تلگرام\n"
            "• `pic` ➡️ بیرون کشیدن عکس باکیفیت از دل استیکر\n\n"
            "🎮 **بازی دوز:**\n"
            "• بفرست `دوز` یا `dooz` تو پی‌وی هر کی؛ ربات ردیف میشه واسه بازی!"
        )
        await message.reply_text(help_text)
        return

    # 🔹 قابلیت جدید و اختصاصی: تبدیل متن به ویس مردونه فیکس شده بدون ارور زبان فارسی
    if text_lower.startswith(".voice") or text_lower.startswith(".tts"):
        target_text = ""
        
        # اگه جلوی دستور متن نوشته بودی
        if " " in text:
            target_text = text.split(" ", 1)[1].strip()
        # اگه روی پیامی ریپلای کرده بودی
        elif message.reply_to_message and message.reply_to_message.text:
            target_text = message.reply_to_message.text.strip()
            
        if not target_text:
            await message.edit_text("❌ مشتی یا جلوی دستور متن بنویس یا روی یه پیام متنی ریپلای کن!")
            return
            
        await message.delete()
        status_msg = await client.send_message(chat_id, "🎙 در حال ردیف کردن ویس مردونه سالار...")
            
        try:
            await client.send_chat_action(chat_id, ChatAction.RECORD_AUDIO)
            voice_file = f"manual_{int(time.time())}.mp3"
            
            if os.path.exists(voice_file): os.remove(voice_file)
            
            # اجرای رندر آفلاین با pyttsx3
            text_to_voice_male(target_text, voice_file)
            
            # ارسال ویس به عنوان ریپلای (اگه ریپلای بوده) یا ارسال عادی
            reply_to_id = message.reply_to_message.id if message.reply_to_message else None
            await client.send_voice(chat_id, voice=voice_file, reply_to_message_id=reply_to_id)
            await status_msg.delete()
            if os.path.exists(voice_file): os.remove(voice_file)
        except Exception as e:
            await status_msg.edit_text(f"❌ ویس ردیف نشد سالار. خطا: {e}")
        return

    # 🔹 قابلیت جدید: دانلودر و لیچر مافوق صوت با aiohttp (.dl)
    if text.startswith(".dl "):
        url = text.split(".dl ", 1)[1].strip()
        status_msg = await message.edit_text("📥 در حال خفت کردن فایل از اینترنت با سرعت فضا...")
        
        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            filename = f"file_{int(time.time())}.dat"
            
        try:
            success = await download_file(url, filename)
            
            if success and os.path.exists(filename):
                await status_msg.edit_text("📤 دانلود روی سرور ردیف شد! در حال آپلود توی چت...")
                await client.send_document(chat_id, document=filename, caption=f"⚡️ فایلت ردیف شد سالار:\n📦 `{filename}`")
                await status_msg.delete()
                os.remove(filename)
            else:
                await status_msg.edit_text("❌ نشد که بشه! سرور لینک رو رد کرد یا فایل دانلود نشد.")
        except Exception as e:
            await status_msg.edit_text(f"❌ کار گره خورد مشتی. خطا:\n`{e}`")
            if os.path.exists(filename): os.remove(filename)
        return

    # 🔹 قابلیت پرواز هواپیما روی متن (.fly)
    if text.startswith(".fly "):
        input_text = text.split(".fly ", 1)[1].strip()
        await message.delete()
        
        fly_msg = await client.send_message(chat_id, "✈️")
        await asyncio.sleep(0.3)
        
        frames = [
            f"✈️ {input_text[:2]}",
            f"🛫 {input_text[:5]}",
            f"🚀 {input_text[:10]}",
            f"✨ {input_text}"
        ]
        
        try:
            for frame in frames:
                await fly_msg.edit_text(frame)
                await asyncio.sleep(0.4)
        except: pass
        return

    # 🔹 قابلیت شبیه‌ساز مبارزه و دوئل متحرک (.duel)
    if text_lower == ".duel" and message.reply_to_message:
        reply = message.reply_to_message
        enemy = reply.from_user.first_name if reply.from_user else "حریف"
        await message.delete()
        
        duel_msg = await client.send_message(chat_id, f"⚔️ کل‌کل بالا گرفت! دوئل بین **آریا** و **{enemy}** شروع شد!")
        await asyncio.sleep(1)
        
        hp_aria, hp_enemy = 100, 100
        
        try:
            while hp_aria > 0 and hp_enemy > 0:
                dmg_to_enemy = random.randint(15, 30)
                dmg_to_aria = random.randint(15, 30)
                
                turn = random.choice(["aria", "enemy"])
                if turn == "aria":
                    hp_enemy = max(0, hp_enemy - dmg_to_enemy)
                    action = f"⚔️ آریا یه چک خوابوند تو گوشش! (-{dmg_to_enemy} HP)"
                else:
                    hp_aria = max(0, hp_aria - dmg_to_aria)
                    action = f"💥 {enemy} پاتک زد و شاخ شد! (-{dmg_to_aria} HP)"
                
                status = (
                    f"🥊 **رینگ زنده مچ‌اندازی:**\n\n"
                    f"👤 آریا سالار: `[{hp_aria}%]` {'❤️' if hp_aria > 40 else '💔'}\n"
                    f"👤 {enemy}: `[{hp_enemy}%]` {'❤️' if hp_enemy > 40 else '💔'}\n\n"
                    f"🎬 گزارش زنده: _{action}_"
                )
                await duel_msg.edit_text(status)
                await asyncio.sleep(1.2)
            
            winner = "آریا پرچم بالاست! 🎉" if hp_aria > 0 else f"{enemy} شانس آورد ربات بود... 🤖"
            await duel_msg.edit_text(f"🏁 **پایان دعوا!**\n\n🏆 برنده نهایی معرکه: **{winner}**")
        except: pass
        return

    # 🔹 قابلیت بمب‌افکن پیام (Bomb)
    if text_lower.startswith("bomb "):
        try:
            parts = text.split(" ", 2)
            if len(parts) >= 3:
                count = int(parts[1])
                msg_text = parts[2]
                await message.delete()
                for _ in range(count):
                    await client.send_message(chat_id, msg_text)
                    await asyncio.sleep(0.3)
        except Exception as e:
            await client.send_message("me", f"❌ ستون خطایی تو بمب باران رخ داد:\n{e}")
        return

    # 🔹 قابلیت متحرک تابلو روان (.marquee)
    if text.startswith(".marquee "):
        input_text = text.split(".marquee ", 1)[1].strip()
        await message.delete()
        marquee_msg = await client.send_message(chat_id, "🎬 ردیف کردن تابلو روان...")
        
        display_width = 15
        padded_text = " " * display_width + input_text + " " * display_width
        
        try:
            for i in range(len(padded_text) - display_width + 1):
                frame = padded_text[i:i + display_width]
                await marquee_msg.edit_text(f"📟 `[ {frame} ]`")
                await asyncio.sleep(0.4)
        except: pass
        return

    # 🔹 قابلیت مانیتور زنده قیمت دلار تهران و تتر (.live_crypto)
    if text_lower == ".live_crypto":
        live_crypto_active[chat_id] = True
        await message.delete()
        crypto_msg = await client.send_message(chat_id, "💵 خفت کردن قیمت دلار و تتر از کف بازار...")
        
        last_tether, last_dollar = 0, 0
        url = "https://api.keybit.ir/uasi/" 
        
        try:
            while chat_id in live_crypto_active and live_crypto_active[chat_id]:
                res = requests.get(url).json()
                tether_price = int(res["tether"]["p"])
                dollar_price = int(res["dollar"]["p"])
                
                tether_emoji = "🟢" if tether_price >= last_tether else "🔴"
                dollar_emoji = "🟢" if dollar_price >= last_dollar else "🔴"
                
                last_tether, last_dollar = tether_price, dollar_price
                
                box = (
                    "💵 **تابلو زنده و لحظه‌ای بازار ارز:**\n\n"
                    f"{tether_emoji} **تتر (USDT):** `{tether_price:,} تومان`\n"
                    f"{dollar_emoji} **دلار تهران:** `{dollar_price:,} تومان`\n\n"
                    f"⏱ *بروزرسانی خودکار | ساعت مخلصتیم: {datetime.now().strftime('%H:%M:%S')}*"
                )
                await crypto_msg.edit_text(box)
                await asyncio.sleep(10)
        except: pass
        return

    if text_lower == ".stop_live":
        if chat_id in live_crypto_active:
            live_crypto_active[chat_id] = False
            await message.edit_text("🛑 دکون تابلوی قیمت ارز رو تخته کردم سالار.")
        return

    # 🔹 قابلیت افکت لایو متنی (.effect)
    if text.startswith(".effect "):
        gif_text = text.split(".effect ", 1)[1].strip()
        status_msg = await message.edit_text("🎨 در حال رندر و ردیف کردن افکت متنی...")
        
        try:
            f1 = await client.send_message(chat_id, f"🔥 **{gif_text}** 🔥")
            await asyncio.sleep(0.4)
            f2 = await client.send_message(chat_id, f"✨ ` {gif_text} ` ✨")
            await asyncio.sleep(0.4)
            f3 = await client.send_message(chat_id, f"⚡️ __ {gif_text} __ ⚡️")
            
            await client.delete_messages(chat_id, [f1.id, f2.id, f3.id])
            await message.delete()
            
            await client.send_message(chat_id, f"🎬 **[ {gif_text} ]**")
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ اِ لاتی شد که! خطا داد: {e}")
        return

    # دستورات تنظیماتی مدیریتی (محدود شده به محیط سیو مسج جهت امنیت)
    if is_saved_messages:
        if text_lower == "night mode on":
            settings["night_mode"] = True
            await message.reply_text("🌙 **مود شب اوکی شد فرمانده.**\n(از ۱۲ شب تا ۸ صبح هر کی بیاد منشی با لاتی‌ترین لحن جوابشو میده)")
            return
        elif text_lower == "night mode off":
            settings["night_mode"] = False
            await message.reply_text("☀️ **مود شب مرخص شد؛ خودم بیدارم سالار.**")
            return

        if text_lower == "group bot on":
            settings["group_assistant"] = True
            await message.reply_text("👥 **بادیگارد گروه‌ها فعال شد؛ تگت کنن هواتو دارم.**")
            return
        elif text_lower == "group bot off":
            settings["group_assistant"] = False
            await message.reply_text("👥 **منشی گروه‌ها رفت استراحت.**")
            return

        if text_lower.startswith("set status "):
            new_status = text.split("set status ", 1)[1].strip()
            settings["status"] = new_status
            await message.reply_text(f"📌 **وضعیت جدیدت رو کوک کردم مخلص:**\n» `{new_status}`")
            return
        elif text_lower == "clear status":
            settings["status"] = "آفلاین"
            await message.reply_text("🧹 **وضعیت چاکریم رو ریست کردم؛ رفت رو حالت آفلاین.**")
            return

        if text_lower == "status":
            uptime_seconds = int(time.time() - START_TIME)
            uptime_str = f"{uptime_seconds // 3600} ساعت و {(uptime_seconds % 3600) // 60} دقیقه"
            ram_usage = psutil.virtual_memory().percent
            battery_str = "نامشخص"
            try:
                if os.path.exists("/sys/class/power_supply/battery/capacity"):
                    with open("/sys/class/power_supply/battery/capacity", "r") as f:
                        battery_str = f"{f.read().strip()}%"
            except: pass

            info_text = (
                "⚙️ **وضعیت موتورخونه گوشی و ربات آریا:**\n\n"
                f"🔋 **بنیه باتری:** {battery_str}\n"
                f"📊 **فشار روی رم:** {ram_usage}%\n"
                f"⏱ **نفس ربات (آپ‌تایم):** {uptime_str}\n"
                f"💬 **منشی گپ‌ها:** {'✅ رو به راهه' if settings['group_assistant'] else '❌ خوابیده'}\n"
                f"🌙 **مود شب:** {'✅ بیداره' if settings['night_mode'] else '❌ بیخیال'}\n"
                f"📌 **کجا پلاسی؟** `{settings['status']}`"
            )
            await message.reply_text(info_text)
            return

        if text_lower.startswith("profile "):
            target = text.split("profile ", 1)[1].strip()
            status_msg = await message.reply_text("🔍 در حال خفت کردن عکس‌های پروفایل طرف...")
            try:
                user = await client.get_users(target)
                photos = []
                async for photo in client.get_chat_photos(user.id):
                    photos.append(photo)
                if not photos:
                    await status_msg.edit_text("❌ طرف اصلاً عکس پروفایل نداره که!")
                    return
                for idx, photo in enumerate(photos, 1):
                    file_path = await client.download_media(photo.file_id)
                    await client.send_document("me", document=file_path, caption=f"👤 داشمون: {user.first_name}\n🖼 فریم عکس: {idx}")
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ کار گره خورد سالار: {e}")
            return

    # 🔹 باکس کدهای پایتونی (Code Box)
    if text_lower.startswith("code "):
        code_content = text.split("code ", 1)[1].strip()
        await message.edit_text(f"```python\n{code_content}\n```")
        return

    # 🔹 قابلیت پاکسازی سریع چت خودت (Self Purge)
    if text_lower.startswith("del "):
        try:
            limit = int(text.split("del ", 1)[1].strip())
            await message.delete()
            
            my_messages = []
            async for msg in client.get_chat_history(chat_id):
                if msg.from_user and msg.from_user.is_self:
                    my_messages.append(msg.id)
                if len(my_messages) >= limit:
                    break
            
            if my_messages:
                await client.delete_messages(chat_id, my_messages)
        except: pass
        return

    # 🔹 قابلیت اطلاعات جاسوسی و مشخصات کاربری (ID Info) با ریپلای
    if text_lower == "info" and message.reply_to_message:
        reply = message.reply_to_message
        if reply.from_user:
            target_user = reply.from_user
            user_id = target_user.id
            username = f"@{target_user.username}" if target_user.username else "ندارد"
            is_bot = "🤖 آره بابا باته" if target_user.is_bot else "👤 نه داش، آدم زنده غول تشنه است"
            dc_id = target_user.dc_id or "نامشخص"
            
            info_box = (
                "🕵️‍♂️ **تار و پود و آمار کارآگاهی طرف:**\n\n"
                f"🆔 **شناسنامه عددی:** `{user_id}`\n"
                f"🗣 **نام شاهچراغ:** {target_user.first_name or 'پر'}\n"
                f"👪 **لقب/فامیل:** {target_user.last_name or 'پر'}\n"
                f"🆔 **آیدی تلگرام:** {username}\n"
                f"🤖 **رباته یا آدم؟** {is_bot}\n"
                f"🌐 **سرور متصل (Data Center):** دی‌سی {dc_id}\n"
            )
            await message.edit_text(info_box)
        else:
            await message.reply_text("❌ این پیام بی‌صاحابه، فرستنده‌اش معلوم نیست.")
        return

    # 🔹 قابلیت تاریخ ساخت اکانت حدودی (Chat Age) با ریپلای
    if text_lower == "age" and message.reply_to_message:
        reply = message.reply_to_message
        if reply.from_user:
            uid = reply.from_user.id
            if uid < 100000000: year = "قبل از ۲۰۱۰ (پیرمرد و عتیقه)"
            elif uid < 200000000: year = "۲۰۱۱ ~ ۲۰۱۲ (قدیمی خاک‌خورده)"
            elif uid < 400000000: year = "۲۰۱۳ ~ ۲۰۱۵ (با تجربه)"
            elif uid < 800000000: year = "۲۰۱۶ ~ ۲۰۱۸ (وسط باز)"
            elif uid < 1500000000: year = "۲۰۱۹ ~ ۲۰۲۱ (نسبتاً جدید)"
            elif uid < 2000000000: year = "۲۰۲۲ ~ ۲۰۲۳ (امروزی)"
            else: year = "۲۰۲۴ به بعد (جوجه تلگرامی جدید)"
            
            await message.edit_text(f"📅 **چرتکه‌اندازی قدمت اکانت:**\n\n👤 این رفیقمون اکانتشو حدوداً سال **{year}** ردیف کرده.")
        return

    # 🔹 قابلیت ارتقایافته آمارگیر پیام‌ها: حالا کل تاریخچه چت رو جارو می‌کنه بدون محدودیت ۱۰۰ تا
    if text_lower == "stats":
        status_msg = await message.edit_text("📊 در حال چرتکه‌اندازی کل تاریخچه پیام‌های این چت... (کمی صبور باش)")
        try:
            m_count, p_count, v_count, s_count = 0, 0, 0, 0
            async for msg in client.get_chat_history(chat_id): 
                m_count += 1
                if msg.photo: p_count += 1
                elif msg.voice or msg.audio: v_count += 1
                elif msg.sticker: s_count += 1
            
            await status_msg.edit_text(
                "📈 **آمار و رقم کل پیام‌های این چت از روز اول:**\n\n"
                f"💬 کل پیام‌های رد و بدل شده: {m_count}\n"
                f"🖼 آمار عکس‌ها: {p_count}\n"
                f"🎙 آمار ویس‌ها و صداها: {v_count}\n"
                f"🎭 آمار استیکرها: {s_count}"
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ خطا تو چرتکه‌اندازی کل تاریخچه گپ: {e}")
        return

    # 🔹 قابلیت ساعت دیجیتال آنلاین (Live Clock)
    if text_lower == "clock":
        live_clocks[chat_id] = True
        await message.delete()
        clock_msg = await client.send_message(chat_id, "🕒 در حال کوک کردن ساعت زنده...")
        try:
            while chat_id in live_clocks and live_clocks[chat_id]:
                now_str = datetime.now().strftime("%H:%M:%S")
                await clock_msg.edit_text(f"⏱ **ساعت لایو و ثانیه‌شمار آریا:**\n\n🕒 `[ {now_str} ]`")
                await asyncio.sleep(2)
        except: pass
        return

    if text_lower == "stopclock":
        if chat_id in live_clocks:
            live_clocks[chat_id] = False
            await message.edit_text("🛑 ساعت زنده رو خوابوندم ردیف شد.")
        return

    # 🔹 قابلیت تگ همگانی مخفی (Mention All) در گروه‌ها
    if text_lower.startswith("all ") and message.chat.type.value in ["group", "supergroup"]:
        custom_text = text.split("all ", 1)[1].strip()
        await message.delete()
        
        try:
            mentions = ""
            count = 0
            async for member in client.get_chat_members(chat_id):
                if member.user.is_bot or member.user.is_self:
                    continue
                mentions += f"[\u200b](tg://user?id={member.user.id})"
                count += 1
                
                if count >= 20:
                    await client.send_message(chat_id, f"{custom_text}{mentions}")
                    mentions = ""
                    count = 0
                    await asyncio.sleep(0.5)
            
            if mentions:
                await client.send_message(chat_id, f"{custom_text}{mentions}")
        except: pass
        return

    # قابلیت تبدیل عکس به استیکر و برعکس با ریپلای
    if message.reply_to_message:
        reply = message.reply_to_message
        
        if text_lower == "sticker" and (reply.photo or reply.document):
            status_msg = await message.reply_text("⏳ وایسا عکس رو بچپونم تو قالب استیکر...")
            try:
                file_path = await client.download_media(reply)
                img = Image.open(file_path)
                sticker_path = "sticker.webp"
                img.save(sticker_path, "WEBP")
                
                await message.delete()
                await client.send_sticker(chat_id, sticker=sticker_path)
                await status_msg.delete()
                os.remove(file_path)
                os.remove(sticker_path)
            except: pass
            return
            
        if text_lower == "pic" and reply.sticker:
            if reply.sticker.is_animated or reply.sticker.is_video:
                return
            status_msg = await message.reply_text("⏳ وایسا عکس باکیفیت رو از دل استیکر بکشم بیرون...")
            try:
                file_path = await client.download_media(reply)
                img = Image.open(file_path)
                img = img.convert("RGB")
                photo_path = "photo.jpg"
                img.save(photo_path, "JPEG")
                
                await message.delete()
                await client.send_photo(chat_id, photo=photo_path, caption=f"🖼 عکسی که از تو شکم استیکر کشیدم بیرون مخلص!")
                await status_msg.delete()
                os.remove(file_path)
                os.remove(photo_path)
            except: pass
            return

# --- قابلیت ذخیره خودکار مدیاهای یکبار مصرف گروه‌ها (Anti View-Once) ---
@app.on_message(~filters.me & (filters.private | filters.group))
async def catch_view_once(client, message):
    is_vo = False
    if message.photo and message.photo.ttl_seconds: is_vo = True
    elif message.video and message.video.ttl_seconds: is_vo = True

    if is_vo:
        try:
            sender_name = message.from_user.first_name if message.from_user else "ناشناس"
            
            file_path = await client.download_media(message)
            if message.photo:
                await client.send_photo("me", photo=file_path, caption=f"📸 فرستنده: {sender_name}")
            else:
                await client.send_video("me", video=file_path, caption=f"🎥 فرستنده: {sender_name}")
                
            if os.path.exists(file_path):
                os.remove(file_path)
        except: pass

    # --- بدنه اصلی مدیریت منشی و بازی دوز ---
    text = message.text.strip() if message.text else ""
    text_lower = text.lower()
    chat_id = message.chat.id
    current_hour = datetime.now().hour
    is_group = message.chat.type.value in ["group", "supergroup"]

    if is_group:
        if not settings["group_assistant"] or not message.mentioned:
            return

    # مدیریت بازی دوز در جریان (محیط پی‌وی)
    if not is_group and chat_id in games:
        game = games[chat_id]
        try: await message.delete()
        except: pass
        
        if text == "لغو":
            try: await client.delete_messages(chat_id, [game["bot_msg_id"], game["user_dooz_msg_id"], game.get("diff_msg_id")])
            except: pass
            del games[chat_id]
            await client.send_message(chat_id, "بیخیال بازی شدیم داش، کنسل شد.")
            return
            
        if game["difficulty"] is None:
            if text in ["راحت", "معمولی", "هارد", "فوق سخت"]:
                game["difficulty"] = text
                try: await client.delete_messages(chat_id, [game["diff_msg_id"]])
                except: pass
                initial_board = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
                game["board"] = initial_board
                bot_msg = await client.send_message(chat_id, f"🎮 دستا بالا دوز شروع شد! (درجه سختی مچ‌اندازی: {text})\n\n" + render_board(initial_board))
                game["bot_msg_id"] = bot_msg.id
            return
            
        board = game["board"]
        bot_msg_id = game["bot_msg_id"]
        num_map = {"1":0,"2":1,"3":2,"4":3,"5":4,"6":5,"7":6,"8":7,"9":8,
                   "۱":0,"۲":1,"۳":2,"۴":3,"۵":4,"۶":5,"۷":6,"۸":7,"۹":8}
                   
        if text in num_map:
            idx = num_map[text]
            if board[idx] not in ["❌", "⭕"]:
                board[idx] = "❌"
                if check_winner(board):
                    del games[chat_id]
                    await clean_game_end(client, chat_id, "🎉 بردی ستون! دمت گرم چسبید، پرچمت بالاست.", game)
                    return
                    
                bot_idx = get_bot_move(board, game["difficulty"])
                if bot_idx is not None:
                    board[bot_idx] = "⭕"
                    
                if check_winner(board):
                    del games[chat_id]
                    await clean_game_end(client, chat_id, "🤖 هوش مصنوعی زد جلو مخلص! دفعه بعد قوی‌تر بیا رینگ.", game)
                    return
                try: await client.edit_message_text(chat_id, bot_msg_id, f"🎮 درجه سختی دعوا: {game['difficulty']}\n\n" + render_board(board))
                except: pass
            return

    # استارت دوز
    if not is_group and text in ["دوز", "dooz"]:
        if settings["night_mode"] and (0 <= current_hour < 8):
            return
        diff_msg = await message.reply_text("🤖 **یکی رو انتخاب کن واسه بازی مشتی دوز:**\n\nبنویس واسم:\n🔹 `راحت`\n🔹 `معمولی`\n🔹 `هارد`\n🔹 `فوق سخت`")
        games[chat_id] = {"board": [], "difficulty": None, "bot_msg_id": None, "user_dooz_msg_id": message.id, "diff_msg_id": diff_msg.id}
        return

    # سیستم منشی با آنتی‌اسپم ۵ دقیقه‌ای
    now = time.time()
    if chat_id in last_replied and (now - last_replied[chat_id] < 300):
        return

    current_status = settings["status"]

    # ۱. بخش مود شب (ساعت ۱۲ شب تا ۸ صبح)
    if settings["night_mode"] and (0 <= current_hour < 8):
        if is_group:
            reply_text = (
                f"سلام جمع! 🙋‍♂️\n"
                f"من ربات آریام. ستون الان تخت خوابیده، نوتیف‌های گروه رو هم سایلنت کرده که بیدار نشه. 😴\n"
                f"بگذارید راحت بخوابه، فردا اومد بالا خودش چت‌ها رو چک می‌کنه. چاکریم! 🌙"
            )
        else:
            reply_text = (
                "هوی سالار! زنده باشی. 🙋‍♂️\n"
                "الان ساعت از نیمه‌شب گذشته و آریا تخت خوابیده (یا شایدم داره گیم می‌زنه) 😴\n"
                "نوتیف چتت رو سایلنت کردم که بیدار نشه. فردا که بلند شد اولین کاری که می‌کنه اینه که میاد پی‌ویت. شب خوش! 🌙"
            )
        await message.reply_text(reply_text)
        last_replied[chat_id] = now
        return

    # ۲. بخش انگلیسی (طول روز)
    if 'a' <= (text_lower[0] if text_lower else "") <= 'z':
        if is_group:
            reply_text = (
                f"Yo everyone! 👋\n"
                f"I'm Aria's bot. He's not here right now (Status: **{current_status}**).\n"
                f"I've marked your tag, and he'll check the group as soon as he's back online! 🔥"
            )
        else:
            reply_text = (
                f"Hey there! CHILL OUT, I'm Aria's personal assistant. 😎\n"
                f"Aria isn't online right now (Current Status: **{current_status}**). But I've got your message locked and loaded! As soon as he's back, he'll hit you up. Stay tuned! ✌️\n\n"
                f"⚠️ **Notice:** If you wish to pass the time while waiting, you may start a game of Tic-Tac-Toe by replying with the word **'dooz'**."
            )
            
    # ۳. بخش فارسی (طول روز)
    else:
        if is_group:
            reply_text = (
                f"سلام رفقا! چه خبر؟ 😍👋\n"
                f"من دستیار آریام؛ آریا الان تل نیست و تو وضعیت [ **{current_status}** ] قرار داره.\n"
                f"تگتون رو براش نگه می‌دارم، اومد آنلاین شد سریع میاد گروه رو چک می‌کنه. مخلص همگی! 🤝🔥"
            )
        else:
            reply_text = (
                f"سلام سلااام! چطوری رفیق؟ مخلصیم. 😍\n"
                f"من دستیار آریام؛ آریا الان آنلاین نیست و در وضعیت [ **{current_status}** ] قرار داره. پیامت رو گرفتم و جاش کاملاً امنه. وقتی بیاد اولین کاری که میکنه اینه که میاد پی‌ویت. خیالت تختِ تخت! ✌️\n\n"
                f"⚠️ **توجه:** در صورت تمایل به صبوری و سرگرمی، می‌توانید با ارسال کلمه **«دوز»**، به بازی دوز مشغول شوید تا آریا آنلاین شود."
            )

    await client.send_chat_action(chat_id, ChatAction.TYPING)
    await asyncio.sleep(3)
    await message.reply_text(reply_text)
    last_replied[chat_id] = now

def render_board(board):
    return f"{board[0]} | {board[1]} | {board[2]}\n---+---+---\n{board[3]} | {board[4]} | {board[5]}\n---+---+---\n{board[6]} | {board[7]} | {board[8]}\n\nعدد ۱ تا ۹ بفرست یا بنویس 'لغو'"

def check_winner(b):
    lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for x, y, z in lines:
        if b[x] == b[y] == b[z] and b[x] not in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]: return b[x]
    if all(x in ["❌", "⭕"] for x in b): return "Draw"
    return None

def get_bot_move(board, diff):
    empty = [i for i, x in enumerate(board) if x not in ["❌", "⭕"]]
    if not empty: return None
    if diff == "راحت": return random.choice(empty)
    for move in empty:
        board_copy = list(board)
        board_copy[move] = "⭕"
        if check_winner(board_copy) == "⭕": return move
    for move in empty:
        board_copy = list(board)
        board_copy[move] = "❌"
        if check_winner(board_copy) == "❌": return move
    return random.choice(empty)

async def clean_game_end(client, chat_id, final_text, game):
    end_msg = await client.send_message(chat_id, final_text)
    await asyncio.sleep(4)
    try: await client.delete_messages(chat_id, [end_msg.id, game["bot_msg_id"], game["user_dooz_msg_id"], game.get("diff_msg_id")])
    except: pass

@app.on_message(filters.private & filters.me)
async def clear_game_on_my_reply(client, message):
    chat_id = message.chat.id
    if chat_id in games: del games[chat_id]

print("🔥 ربات نسخه شاهنشاه با لحن لوتی و سیستم ویس اختصاصی مردونه بالا آمد... مخلصیم! ⚡️")
app.run()
