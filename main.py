import time
import random
import os
import psutil
import asyncio
import aiohttp
import re
import math
import shutil
import subprocess
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
import edge_tts

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

settings = {
    "night_mode": False,       # مود شب (۱۲ شب تا ۸ صبح)
    "group_assistant": False,  # منشی در گروه‌ها (پیش‌فرض خاموش)
    "status": "آفلاین"         # وضعیت فعلی آریا (باشگاه، گیم، درس و...)
}

# --- بخش دانلودر حرفه‌ای ناهمگام (با پشتیبانی از رزومه و تکه تکه کردن) ---

async def progress_callback(current, total, status_msg, filename, start_time):
    now = time.time()
    elapsed = now - start_time
    if elapsed == 0:
        elapsed = 0.01
    speed = current / elapsed  # bytes/sec
    percent = (current / total) * 100 if total > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    
    speed_kb = speed / 1024
    speed_mb = speed_kb / 1024
    speed_str = f"{speed_mb:.2f} MB/s" if speed_mb > 1 else f"{speed_kb:.2f} KB/s"
    
    curr_mb = current / (1024 * 1024)
    tot_mb = total / (1024 * 1024)
    
    eta_min = int(eta // 60)
    eta_sec = int(eta % 60)
    eta_str = f"{eta_min:02d}:{eta_sec:02d}"
    
    progress_bar = "".join(["■" if i < int(percent // 10) else "□" for i in range(10)])
    
    progress_text = (
        f"📥 **در حال دانلود فایل:** `{filename}`\n"
        f"📊 [{progress_bar}] {percent:.1f}%\n"
        f"📦 حجم: {curr_mb:.1f}MB از {tot_mb:.1f}MB\n"
        f"⚡️ سرعت: {speed_str}\n"
        f"⏱ زمان باقی‌مانده: {eta_str}"
    )
    try:
        await status_msg.edit_text(progress_text)
    except Exception:
        pass

async def download_file_streaming(url, destination, status_msg):
    # قابلیت Resume و Streaming با دانلود چند مگابایتی
    chunk_size = 1024 * 1024  # 1MB chunks
    start_bytes = 0
    
    if os.path.exists(destination):
        start_bytes = os.path.getsize(destination)
        
    headers = {}
    if start_bytes > 0:
        headers["Range"] = f"bytes={start_bytes}-"
        
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=3600) as response:
                if response.status not in (200, 206):
                    if start_bytes > 0:
                        # اگر سرور از رنج پشتیبانی نکرد مجدد از صفر دانلود میکنیم
                        return await download_file_streaming(url, destination, status_msg)
                    return False
                
                total_bytes = int(response.headers.get("Content-Length", 0)) + start_bytes
                mode = "ab" if start_bytes > 0 else "wb"
                
                current_bytes = start_bytes
                start_time = time.time()
                last_update = 0
                
                with open(destination, mode) as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        if not chunk:
                            break
                        f.write(chunk)
                        current_bytes += len(chunk)
                        
                        now = time.time()
                        if now - last_update > 2.5:
                            await progress_callback(current_bytes, total_bytes, status_msg, os.path.basename(destination), start_time)
                            last_update = now
                return True
        except Exception as e:
            print(f"Error in streaming download: {e}")
            return False

# موتور هوشمند استخراج لینک دانلود مستقیم از گوگل‌پلی و مایکت
async def fetch_store_apk(url):
    try:
        if "myket.ir" in url:
            package_match = re.search(r"apps/([^/?]+)", url)
            if package_match:
                pkg_id = package_match.group(1)
                direct_download = f"https://get.myket.ir/v3/applications/{pkg_id}/download"
                return direct_download, f"{pkg_id}.apk"
        
        elif "play.google.com" in url:
            package_match = re.search(r"id=([^&?]+)", url)
            if package_match:
                pkg_id = package_match.group(1)
                api_url = f"https://api.apps.evozi.com/apk/v1/dl?id={pkg_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url) as res:
                        if res.status == 200:
                            data = await res.json()
                            if data.get("status") == "success":
                                return data.get("url"), f"{pkg_id}.apk"
    except Exception as e:
        print(f"Error store APK fetch: {e}")
    return None, None

# تابع کمکی برای آپلود با نمایش درصد پیشرفت
async def upload_progress(current, total, status_msg, filename, start_time):
    now = time.time()
    elapsed = now - start_time
    if elapsed == 0:
        elapsed = 0.01
    speed = current / elapsed
    percent = (current / total) * 100 if total > 0 else 0
    
    speed_kb = speed / 1024
    speed_mb = speed_kb / 1024
    speed_str = f"{speed_mb:.2f} MB/s" if speed_mb > 1 else f"{speed_kb:.2f} KB/s"
    
    curr_mb = current / (1024 * 1024)
    tot_mb = total / (1024 * 1024)
    
    progress_bar = "".join(["■" if i < int(percent // 10) else "□" for i in range(10)])
    
    try:
        await status_msg.edit_text(
            f"📤 **در حال آپلود تلگرام:** `{filename}`\n"
            f"📊 [{progress_bar}] {percent:.1f}%\n"
            f"📦 حجم: {curr_mb:.1f}MB از {tot_mb:.1f}MB\n"
            f"⚡️ سرعت: {speed_str}"
        )
    except Exception:
        pass

# تابع هوشمند ارسال فایل با متد متناسب بر اساس پسوند
async def send_smart_media(client, chat_id, filepath, caption, status_msg):
    ext = os.path.splitext(filepath)[1].lower()
    start_time = time.time()
    
    # تشخیص MIME و متد مناسب تلگرام
    video_exts = [".mp4", ".mkv", ".mov", ".avi", ".webm"]
    audio_exts = [".mp3", ".ogg", ".wav", ".m4a", ".flac"]
    photo_exts = [".jpg", ".jpeg", ".png", ".bmp"]
    gif_exts = [".gif"]
    
    try:
        if ext in video_exts:
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
            await client.send_video(
                chat_id, 
                video=filepath, 
                caption=caption,
                progress=upload_progress,
                progress_args=(status_msg, os.path.basename(filepath), start_time)
            )
        elif ext in audio_exts:
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
            await client.send_audio(
                chat_id, 
                audio=filepath, 
                caption=caption,
                progress=upload_progress,
                progress_args=(status_msg, os.path.basename(filepath), start_time)
            )
        elif ext in photo_exts:
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
            await client.send_photo(
                chat_id, 
                photo=filepath, 
                caption=caption,
                progress=upload_progress,
                progress_args=(status_msg, os.path.basename(filepath), start_time)
            )
        elif ext in gif_exts:
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            await client.send_animation(
                chat_id, 
                animation=filepath, 
                caption=caption,
                progress=upload_progress,
                progress_args=(status_msg, os.path.basename(filepath), start_time)
            )
        else:
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            await client.send_document(
                chat_id, 
                document=filepath, 
                caption=caption,
                progress=upload_progress,
                progress_args=(status_msg, os.path.basename(filepath), start_time)
            )
        return True
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در آپلود رسانه: {e}")
        return False

# سیستم تقسیم بندی فایل با FFmpeg (برای ویدیو) یا Split باینری (برای سایر فایل ها)
def split_video_ffmpeg(filepath, max_size_mb=1900):
    # حجم ماکزیمم کمتر از 2 گیگابایت برای امنیت در آپلود تلگرام عادی
    file_size = os.path.getsize(filepath)
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size <= max_size_bytes:
        return [filepath]
    
    parts = []
    num_parts = math.ceil(file_size / max_size_bytes)
    
    # بدست آوردن زمان کل ویدیو به کمک ffprobe
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{filepath}\""
    try:
        duration = float(subprocess.check_output(cmd, shell=True).decode().strip())
    except Exception:
        return [filepath] # در صورت نبود ابزار، مستقیما به سراغ اسپلیت عادی می‌رویم
    
    part_duration = duration / num_parts
    base, ext = os.path.splitext(filepath)
    
    for i in range(num_parts):
        start_time = i * part_duration
        part_path = f"{base}_part{i+1}{ext}"
        # برش بدون فشرده سازی برای سرعت بیشتر
        split_cmd = f"ffmpeg -y -ss {start_time} -t {part_duration} -i \"{filepath}\" -c copy \"{part_path}\""
        subprocess.call(split_cmd, shell=True)
        if os.path.exists(part_path) and os.path.getsize(part_path) > 0:
            parts.append(part_path)
            
    return parts

def split_binary_file(filepath, max_size_mb=1900):
    file_size = os.path.getsize(filepath)
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size <= max_size_bytes:
        return [filepath]
    
    parts = []
    chunk_size = 10 * 1024 * 1024  # 10MB Chunks to copy
    base = filepath
    
    part_num = 1
    current_size = 0
    out_file = None
    
    try:
        with open(filepath, "rb") as src:
            while True:
                data = src.read(chunk_size)
                if not data:
                    break
                
                if out_file is None:
                    part_path = f"{base}.part{part_num:03d}"
                    out_file = open(part_path, "wb")
                    parts.append(part_path)
                    part_num += 1
                
                out_file.write(data)
                current_size += len(data)
                
                if current_size >= max_size_bytes:
                    out_file.close()
                    out_file = None
                    current_size = 0
        if out_file:
            out_file.close()
    except Exception as e:
        print(f"Error splitting binary file: {e}")
        return [filepath]
        
    return parts

# تبدیل متن به صدای طبیعی مردونه
async def text_to_voice_male(text, output_file):
    if any(char in "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی" for char in text):
        voice_style = "fa-IR-FaridNeural"  # صدای مردونه طبیعی فارسی 🧔🏻
    else:
        voice_style = "en-US-BrianNeural"  # صدای مردونه طبیعی انگلیسی 🧔🏼
        
    communicate = edge_tts.Communicate(text, voice_style)
    await communicate.save(output_file)

# --- بخش اول: دستورات ادمین (فقط خودت می‌توانی اجرا کنی) ---
@app.on_message(filters.me & filters.text)
async def admin_commands(client, message):
    try:
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
                "• `night mode on` ➡️ فعال‌سازی مود شب\n"
                "• `night mode off` ➡️ غیرفعال‌سازی مود شب\n"
                "• `group bot on` ➡️ فعال‌سازی منشی باصفا در گروه‌ها\n"
                "• `group bot off` ➡️ خاموش کردن منشی گروه‌ها\n"
                "• `set status [متن]` ➡️ تگ کردن وضعیت چاکریم\n"
                "• `clear status` ➡️ پاک کردن وضعیت فعلی\n"
                "• `status` ➡️ آمار و ارقام موتور گوشی (باتری، رم و آپ‌تایم ربات)\n"
                "• `profile [آیدی]` ➡️ دانلود رگباری تمام عکس‌های پروفایل طرف\n\n"
                "🛠 **ابزارهای زنده, دست‌فرمان‌ها و قابلیت‌های خاص:**\n"
                "• `.voice` یا `.tts` ➡️ تبدیل متن به ویس صوتی مردونه بدون تحریم 🎙\n"
                "• `.dl [لینک]` ➡️ لیچ فیلم (پخش لایو)، لینک‌های عادی و گوگل‌پلی/مایکت ⚡️\n"
                "• `.fly [متن]` ➡️ پرواز تماشایی هواپیما روی متنت 🛫\n"
                "• `.duel` ➡️ شروع مبارزه و دوئل متحرک لایو مچ‌اندازی ⚔️\n"
                "• `bomb [تعداد] [متن]` ➡️ به توپ بستن و ارسال رگباری پیام\n"
                "• `code [متن]` ➡️ مشتی کردن کدهات توی باکس پایتون\n"
                "• `del [تعداد]` ➡️ غیب کردن پیام‌های خودت به صورت دوطرفه\n"
                "• `info` ➡️ تار و پود و آمار کارآگاهی طرف\n"
                "• `age` ➡️ حساب کتابِ اینکه طرف چند ساله تو تلگرامه\n"
                "• `stats` ➡️ آمارگیر کل تاریخچه چت جاری بدون هیچ محدوبیتی 📊\n"
                "• `clock` ➡️ ساعت دیجیتال زنده و ثانیه‌شمار تو چت\n"
                "• `stopclock` ➡️ متوقف کردن ساعت لایو\n"
                "• `.marquee [متن]` ➡️ راه انداختن تابلوروان متحرک دور متنت\n"
                "• `.effect [متن]` ➡️ افکت متحرک سه مرحله‌ای مشتی واسه متنت\n\n"
                "👥 **دستورات گروهی:**\n"
                "• `all [متن]` ➡️ تگ همگانی نامرئی\n\n"
                "🎨 **ابزار استیکر (با ریپلای روی پیام):**\n"
                "• `sticker` ➡️ تبدیل عکس به استیکر مشتی\n"
                "• `pic` ➡️ بیرون کشیدن عکس باکیفیت از دل استیکر\n\n"
                "🎮 **بازی دوز:**\n"
                "• بفرست `دوز` یا `dooz` تو پی‌وی هر کی؛ ربات ردیف میشه واسه بازی!"
            )
            await message.reply_text(help_text)
            return

        # 🔹 قابلیت تبدیل متن به ویس مردونه
        if text_lower.startswith(".voice") or text_lower.startswith(".tts"):
            target_text = ""
            if " " in text:
                target_text = text.split(" ", 1)[1].strip()
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
                
                await text_to_voice_male(target_text, voice_file)
                reply_to_id = message.reply_to_message.id if message.reply_to_message else None
                await client.send_voice(chat_id, voice=voice_file, reply_to_message_id=reply_to_id)
                await status_msg.delete()
                if os.path.exists(voice_file): os.remove(voice_file)
            except Exception as e:
                await status_msg.edit_text(f"❌ ویس ردیف نشد سالار. خطا: {e}")
            return

        # 🔹 قابلیت دانلودر ارتقا یافته با بالاترین استانداردها و تکه تکه کردن
        if text.startswith(".dl "):
            url = text.split(".dl ", 1)[1].strip()
            status_msg = await message.edit_text("📥 در حال آنالیز لینک و خفت کردن دیتا...")
            
            store_url, custom_filename = await fetch_store_apk(url)
            if store_url:
                url = store_url
                filename = custom_filename
                is_app = True
            else:
                filename = url.split("/")[-1].split("?")[0]
                if not filename:
                    filename = f"file_{int(time.time())}.mp4"
                is_app = filename.lower().endswith(".apk")
                
            try:
                await status_msg.edit_text("⚡️ لینک فیکس شد! در حال دانلود روی سرور ریل‌وی...")
                
                # بررسی اینکه آیا فایل از قبل وجود داشته برای تلاش در Resume
                success = await download_file_streaming(url, filename, status_msg)
                
                if success and os.path.exists(filename):
                    await status_msg.edit_text("📤 دانلود تمام! در حال پردازش و آپلود خوش‌دست توی چت...")
                    
                    video_extensions = (".mp4", ".mkv", ".mov", ".avi", ".webm")
                    file_size_mb = os.path.getsize(filename) / (1024 * 1024)
                    
                    # تقسیم‌بندی فایل‌های بالاتر از 1.9 گیگابایت برای جلوگیری از محدودیت تلگرام
                    if file_size_mb > 1900:
                        await status_msg.edit_text(f"✂️ حجم فایل ({file_size_mb:.1f}MB) بالا بود! در حال تقسیم به پارت‌ها...")
                        if filename.lower().endswith(video_extensions) and not is_app:
                            parts = split_video_ffmpeg(filename)
                        else:
                            parts = split_binary_file(filename)
                            
                        for part in parts:
                            await send_smart_media(client, chat_id, part, f"📦 پارت درخواستی سالار: `{os.path.basename(part)}`", status_msg)
                            if os.path.exists(part) and part != filename:
                                os.remove(part)
                    else:
                        caption = f"🎬 ویدیوی درخواستی ردیف شد سالار:" if (filename.lower().endswith(video_extensions) and not is_app) else f"⚡️ فایلت ردیف شد سالار:\n📦 `{filename}`"
                        await send_smart_media(client, chat_id, filename, caption, status_msg)
                    
                    await status_msg.delete()
                    if os.path.exists(filename):
                        os.remove(filename)
                else:
                    await status_msg.edit_text("❌ نشد که بشه! سرور لینک رو رد کرد یا فایل دانلود نشد.")
            except Exception as e:
                await status_msg.edit_text(f"❌ کار گره خورد مشتی. خطا:\n`{e}`")
                if os.path.exists(filename): 
                    os.remove(filename)
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
            except Exception: 
                pass
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
            except Exception: 
                pass
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
            except Exception: 
                pass
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
            except Exception: 
                pass
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
            except Exception: 
                pass
            return

        # دستورات تنظیماتی مدیریتی (محدود شده به محیط سیو مسج)
        if is_saved_messages:
            if text_lower == "night mode on":
                settings["night_mode"] = True
                await message.reply_text("🌙 **مود شب اوکی شد فرمانده.**")
                return
            elif text_lower == "night mode off":
                settings["night_mode"] = False
                await message.reply_text("☀️ **مود شب مرخص شد؛ خودم بیدارم سالار.**")
                return
            if text_lower == "group bot on":
                settings["group_assistant"] = True
                await message.reply_text("👥 **بادیگارد گروه‌ها فعال شد.**")
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
                await message.reply_text("🧹 **وضعیت چاکریم ریست شد.**")
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
                except Exception: 
                    pass
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
                        if os.path.exists(file_path):
                            os.remove(file_path)
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
            except Exception: 
                pass
            return

        # 🔹 قابلیت اطلاعات مشخصات کاربری (ID Info)
        if text_lower == "info" and message.reply_to_message:
            reply = message.reply_to_message
            if reply.from_user:
                target_user = reply.from_user
                username = f"@{target_user.username}" if target_user.username else "ندارد"
                is_bot = "🤖 آره بابا باته" if target_user.is_bot else "👤 نه داش، آدم زنده غول تشنه است"
                info_box = (
                    "🕵️‍♂️ **تار و پود و آمار کارآگاهی طرف:**\n\n"
                    f"🆔 **شناسنامه عددی:** `{target_user.id}`\n"
                    f"🗣 **نام شاهچراغ:** {target_user.first_name or 'پر'}\n"
                    f"🆔 **آیدی تلگرام:** {username}\n"
                    f"🤖 **رباته یا آدم؟** {is_bot}\n"
                )
                await message.edit_text(info_box)
            return

        # 🔹 قابلیت تاریخ ساخت اکانت (Chat Age)
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

        # 🔹 قابلیت آمارگیر کل تاریخچه چت
        if text_lower == "stats":
            status_msg = await message.edit_text("📊 در حال چرتکه‌اندازی کل تاریخچه پیام‌های این چت...")
            try:
                m_count, p_count, v_count, s_count = 0, 0, 0, 0
                async for msg in client.get_chat_history(chat_id): 
                    m_count += 1
                    if msg.photo: p_count += 1
                    elif msg.voice or msg.audio: v_count += 1
                    elif msg.sticker: s_count += 1
                await status_msg.edit_text(
                    "📈 **آمار و رقم کل پیام‌های این چت از روز اول:**\n\n"
                    f"💬 کل پیام‌ها: {m_count}\n"
                    f"🖼 عکس‌ها: {p_count}\n"
                    f"🎙 ویس‌ها: {v_count}\n"
                    f"🎭 استیکرها: {s_count}"
                )
            except Exception as e:
                await status_msg.edit_text(f"❌ خطا تو چرتکه‌اندازی: {e}")
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
            except Exception: 
                pass
            return

        if text_lower == "stopclock":
            if chat_id in live_clocks:
                live_clocks[chat_id] = False
                await message.edit_text("🛑 ساعت زنده رو خوابوندم ردیف شد.")
            return

        # 🔹 قابلیت تگ همگانی مخفی (Mention All)
        if text_lower.startswith("all ") and message.chat.type.value in ["group", "supergroup"]:
            custom_text = text.split("all ", 1)[1].strip()
            await message.delete()
            try:
                mentions = ""
                count = 0
                async for member in client.get_chat_members(chat_id):
                    if member.user.is_bot or member.user.is_self: continue
                    mentions += f"[\u200b](tg://user?id={member.user.id})"
                    count += 1
                    if count >= 20:
                        await client.send_message(chat_id, f"{custom_text}{mentions}")
                        mentions = ""
                        count = 0
                        await asyncio.sleep(0.5)
                if mentions:
                    await client.send_message(chat_id, f"{custom_text}{mentions}")
            except Exception: 
                pass
            return

        # 🔹 قابلیت‌های ویرایش عکس، استیکر و افکت با ریپلای
        if message.reply_to_message:
            reply = message.reply_to_message
            
            # تبدیل عکس به استیکر و برعکس
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
                    if os.path.exists(file_path): os.remove(file_path)
                    if os.path.exists(sticker_path): os.remove(sticker_path)
                except Exception: 
                    pass
                return
                
            if text_lower == "pic" and reply.sticker:
                if reply.sticker.is_animated or reply.sticker.is_video: return
                status_msg = await message.reply_text("⏳ وایسا عکس باکیفیت رو بکشم بیرون...")
                try:
                    file_path = await client.download_media(reply)
                    img = Image.open(file_path)
                    img = img.convert("RGB")
                    photo_path = "photo.jpg"
                    img.save(photo_path, "JPEG")
                    await message.delete()
                    await client.send_photo(chat_id, photo=photo_path, caption=f"🖼 استیکری که عکس شد مخلص!")
                    await status_msg.delete()
                    if os.path.exists(file_path): os.remove(file_path)
                    if os.path.exists(photo_path): os.remove(photo_path)
                except Exception: 
                    pass
                return

            # افکت‌های فیلتر تصویر بر اساس درخواست ویرایش عکس
            supported_effects = {
                ".blur": lambda im: im.filter(ImageFilter.BLUR),
                ".sharpen": lambda im: im.filter(ImageFilter.SHARPEN),
                ".contour": lambda im: im.filter(ImageFilter.CONTOUR),
                ".grayscale": lambda im: ImageOps.grayscale(im),
                ".invert": lambda im: ImageOps.invert(im.convert("RGB")),
                ".detail": lambda im: im.filter(ImageFilter.DETAIL),
                ".edge": lambda im: im.filter(ImageFilter.FIND_EDGES)
            }
            if text_lower in supported_effects and (reply.photo or (reply.document and reply.document.mime_type.startswith("image/"))):
                status_msg = await message.reply_text("⏳ در حال اعمال افکت روی عکس سالار...")
                try:
                    file_path = await client.download_media(reply)
                    img = Image.open(file_path)
                    processed_img = supported_effects[text_lower](img)
                    out_path = f"effect_{int(time.time())}.png"
                    processed_img.save(out_path, "PNG")
                    await message.delete()
                    await client.send_photo(chat_id, photo=out_path, caption=f"🎨 افکت `{text_lower}` با موفقیت اعمال شد!")
                    await status_msg.delete()
                    if os.path.exists(file_path): os.remove(file_path)
                    if os.path.exists(out_path): os.remove(out_path)
                except Exception as e:
                    await status_msg.edit_text(f"❌ اعمال افکت شکست خورد: {e}")
                return

    except Exception as e:
        print(f"🛡 [آنتی کرش ادمین]: جلوی یک ارور سیستمی تلگرام گرفته شد: {e}")

# --- قابلیت ذخیره خودکار مدیاهای یکبار مصرف (Anti View-Once) ---
@app.on_message(~filters.me & (filters.private | filters.group))
async def catch_view_once(client, message):
    try:
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
                if os.path.exists(file_path): os.remove(file_path)
            except Exception: 
                pass

        # --- مدیریت منشی و بازی دوز ---
        text = message.text.strip() if message.text else ""
        text_lower = text.lower()
        chat_id = message.chat.id
        current_hour = datetime.now().hour
        is_group = message.chat.type.value in ["group", "supergroup"]

        if is_group:
            if not settings["group_assistant"] or not message.mentioned: return

        # مدیریت بازی دوز با سیستم Minimax و Alpha-Beta Pruning برای سطوح هارد و فوق سخت
        if not is_group and chat_id in games:
            game = games[chat_id]
            try: await message.delete()
            except Exception: pass
            if text == "لغو":
                try: await client.delete_messages(chat_id, [game["bot_msg_id"], game["user_dooz_msg_id"], game.get("diff_msg_id")])
                except Exception: pass
                del games[chat_id]
                await client.send_message(chat_id, "بیخیال بازی شدیم داش، کنسل شد.")
                return
            if game["difficulty"] is None:
                if text in ["راحت", "معمولی", "هارد", "فوق سخت"]:
                    game["difficulty"] = text
                    try: await client.delete_messages(chat_id, [game["diff_msg_id"]])
                    except Exception: pass
                    initial_board = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
                    game["board"] = initial_board
                    bot_msg = await client.send_message(chat_id, f"🎮 دستا بالا دوز شروع شد! (درجه سختی: {text})\n\n" + render_board(initial_board))
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
                    if bot_idx is not None: board[bot_idx] = "⭕"
                    if check_winner(board):
                        del games[chat_id]
                        await clean_game_end(client, chat_id, "🤖 هوش مصنوعی زد جلو مخلص! دفعه بعد قوی‌تر بیا رینگ.", game)
                        return
                    try: await client.edit_message_text(chat_id, bot_msg_id, f"🎮 درجه سختی دعوا: {game['difficulty']}\n\n" + render_board(board))
                    except Exception: pass
                return

        # استارت دوز
        if not is_group and text in ["دوز", "dooz"]:
            if settings["night_mode"] and (0 <= current_hour < 8): return
            diff_msg = await message.reply_text("🤖 **یکی رو انتخاب کن واسه بازی مشتی دوز:**\n\nبنویس واسم:\n🔹 `راحت`\n🔹 `معمولی`\n🔹 `هارد`\n🔹 `فوق سخت`")
            games[chat_id] = {"board": [], "difficulty": None, "bot_msg_id": None, "user_dooz_msg_id": message.id, "diff_msg_id": diff_msg.id}
            return

        # ⚡️ فیلتر هوشمند منشی: فقط و فقط اگر پیام حاوی «سلام» یا کلمات هم‌خانواده انگلیسی باشد جواب بدهد
        is_greeting = any(greet in text_lower for greet in ["سلام", "درود", "خوبی", "hi", "hello", "yo", "slm"])
        if not is_greeting:
            return

        # سیستم منشی با آنتی‌اسپم
        now = time.time()
        if chat_id in last_replied and (now - last_replied[chat_id] < 300): return

        current_status = settings["status"]

        if settings["night_mode"] and (0 <= current_hour < 8):
            if is_group:
                reply_text = f"سلام جمع! 🙋‍♂️\nمن ربات آریام. ستون الان تخت خوابیده، نوتیف‌ها رو هم سایلنت کرده. 😴\nفردا خودش چت‌ها رو چک می‌کنه. چاکریم! 🌙"
            else:
                reply_text = "هوی سالار! زنده باشی. 🙋‍♂️\nالان ساعت از نیمه‌شب گذشته و آریا تخت خوابیده. 😴\nفردا که بلند شد اولین کاری که می‌کنه اینه که میاد پی‌ویت. شب خوش! 🌙"
            await message.reply_text(reply_text)
            last_replied[chat_id] = now
            return

        if 'a' <= (text_lower[0] if text_lower else "") <= 'z':
            if is_group:
                reply_text = f"Yo everyone! 👋\nI'm Aria's bot. He's not here right now (Status: **{current_status}**).\nHe'll check the group as soon as he's back online! 🔥"
            else:
                reply_text = f"Hey there! CHILL OUT, I'm Aria's personal assistant. 😎\nAria isn't online right now (Current Status: **{current_status}**). As soon as he's back, he'll hit you up! ✌️\n\n⚠️ **Notice:** You can play Tic-Tac-Toe by replying with **'dooz'**."
        else:
            if is_group:
                reply_text = f"سلام رفقا! 😍👋\nمن دستیار آریام؛ آریا الان تل نیست و تو وضعیت [ **{current_status}** ] قرار داره. اومد آنلاین شد سریع میاد گروه رو چک می‌کنه. مخلص همگی! 🤝🔥"
            else:
                reply_text = f"سلام سلااام! 😍\nمن دستیار آریام؛ آریا الان آنلاین نیست و در وضعیت [ **{current_status}** ] قرار داره. پیامت رو گرفتم. وقتی بیاد اولین کاری که میکنه اینه که میاد پی‌ویت. خیالت تختِ تخت! ✌️\n\n⚠️ **توجه:** می‌توانید با ارسال کلمه **«دوز»**، به بازی دوز مشغول شوید."

        await client.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(3)
        await message.reply_text(reply_text)
        last_replied[chat_id] = now
    except Exception as e:
        print(f"🛡 [آنتی کرش کاربران]: جلوی یک ارور دیتابیس پایروگرام گرفته شد: {e}")

def render_board(board):
    return f"{board[0]} | {board[1]} | {board[2]}\n---+---+---\n{board[3]} | {board[4]} | {board[5]}\n---+---+---\n{board[6]} | {board[7]} | {board[8]}\n\nعدد ۱ تا ۹ بفرست یا بنویس 'لغو'"

def check_winner(b):
    lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for x, y, z in lines:
        if b[x] == b[y] == b[z] and b[x] not in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]: return b[x]
    if all(x in ["❌", "⭕"] for x in b): return "Draw"
    return None

# پیاده‌سازی مینی‌ماکس به همراه هرس آلفا-بتا برای سختی فوق سخت و هارد
def minimax(board, depth, is_maximizing, alpha, beta):
    winner = check_winner(board)
    if winner == "⭕":
        return 10 - depth
    elif winner == "❌":
        return depth - 10
    elif winner == "Draw":
        return 0
        
    empty = [i for i, x in enumerate(board) if x not in ["❌", "⭕"]]
    
    if is_maximizing:
        best_score = -math.inf
        for move in empty:
            board[move] = "⭕"
            score = minimax(board, depth + 1, False, alpha, beta)
            board[move] = str(move + 1)
            best_score = max(score, best_score)
            alpha = max(alpha, best_score)
            if beta <= alpha:
                break
        return best_score
    else:
        best_score = math.inf
        for move in empty:
            board[move] = "❌"
            score = minimax(board, depth + 1, True, alpha, beta)
            board[move] = str(move + 1)
            best_score = min(score, best_score)
            beta = min(beta, best_score)
            if beta <= alpha:
                break
        return best_score

def get_bot_move(board, diff):
    empty = [i for i, x in enumerate(board) if x not in ["❌", "⭕"]]
    if not empty: return None
    
    # سطح راحت: حرکت کاملاً تصادفی
    if diff == "راحت": 
        return random.choice(empty)
        
    # سطح معمولی: بررسی بردن خود در گام فعلی، و در غیر این صورت حرکت تصادفی
    if diff == "معمولی":
        for move in empty:
            board_copy = list(board)
            board_copy[move] = "⭕"
            if check_winner(board_copy) == "⭕": return move
        for move in empty:
            board_copy = list(board)
            board_copy[move] = "❌"
            if check_winner(board_copy) == "❌": return move
        return random.choice(empty)
        
    # سطح هارد: ترکیب هوشمند (گاهی اشتباه تصادفی با شانس 20 درصد برای شبیه‌سازی واقعی و خستگی ناپذیر)
    if diff == "هارد":
        if random.random() < 0.2:
            return random.choice(empty)
            
    # سطح فوق سخت: استفاده صد در صدی از الگوریتم Minimax بدون ذره‌ای خطا
    best_score = -math.inf
    best_move = None
    for move in empty:
        board_copy = list(board)
        board_copy[move] = "⭕"
        score = minimax(board_copy, 0, False, -math.inf, math.inf)
        if score > best_score:
            best_score = score
            best_move = move
            
    return best_move if best_move is not None else random.choice(empty)

async def clean_game_end(client, chat_id, final_text, game):
    end_msg = await client.send_message(chat_id, final_text)
    await asyncio.sleep(4)
    try: await client.delete_messages(chat_id, [end_msg.id, game["bot_msg_id"], game["user_dooz_msg_id"], game.get("diff_msg_id")])
    except Exception: pass

@app.on_message(filters.private & filters.me)
async def clear_game_on_my_reply(client, message):
    chat_id = message.chat.id
    if chat_id in games: del games[chat_id]

print("🔥 ربات با سیستم آنتی کرش ریل‌وی و بدون بخش قیمت ارز بالا آمد... چاکریم! ⚡️")
app.run()
