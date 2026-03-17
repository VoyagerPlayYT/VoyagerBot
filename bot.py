import os
import asyncio
import zipfile
import shutil
import logging
import json
import struct
import plistlib
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events, Button

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_ID     = int(os.environ.get("API_ID", "1"))
API_HASH   = os.environ.get("API_HASH", "a")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@VoyagersIPA")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "0"))
PORT       = int(os.environ.get("PORT", "10000"))

pending = {}

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"VoyagersBot OK")
    def log_message(self, *a): pass

def start_http():
    HTTPServer(("0.0.0.0", PORT), PingHandler).serve_forever()

# ── Info parser using plistlib (no plutil needed) ─────────
def get_info(ipa: Path):
    info = {"name":"Unknown","bundle_id":"unknown",
            "version":"?.?.?","min_ios":"?","size_mb":"?"}
    try:
        size_mb = round(ipa.stat().st_size / 1024 / 1024, 1)
        info["size_mb"] = str(size_mb)
        with zipfile.ZipFile(ipa) as z:
            pl = [f for f in z.namelist()
                  if f.endswith("Info.plist") and f.count("/")==2]
            if not pl:
                pl = [f for f in z.namelist() if f.endswith("Info.plist")]
            if pl:
                raw = z.read(pl[0])
                try:
                    d = plistlib.loads(raw)
                    info["name"]      = d.get("CFBundleDisplayName") or d.get("CFBundleName","Unknown")
                    info["bundle_id"] = d.get("CFBundleIdentifier","unknown")
                    info["version"]   = d.get("CFBundleShortVersionString","?.?.?")
                    info["min_ios"]   = d.get("MinimumOSVersion","?")
                except Exception:
                    # Try binary plist fallback
                    import re
                    text = raw.decode("utf-8", errors="ignore")
                    def find_val(key):
                        idx = text.find(key)
                        if idx == -1: return None
                        sub = text[idx+len(key):idx+len(key)+200]
                        m = re.search(r'<string>(.*?)</string>', sub)
                        return m.group(1) if m else None
                    info["name"]      = find_val("CFBundleDisplayName") or find_val("CFBundleName") or "Unknown"
                    info["bundle_id"] = find_val("CFBundleIdentifier") or "unknown"
                    info["version"]   = find_val("CFBundleShortVersionString") or "?.?.?"
                    info["min_ios"]   = find_val("MinimumOSVersion") or "?"
    except Exception as e:
        logger.error(f"info err: {e}")
    return info

# ── Safe patcher — only patches known safe patterns ───────
def patch_binary(path: Path):
    try:
        data = bytearray(path.read_bytes())
    except Exception:
        return 0

    count = 0

    # Pattern 1: StoreKit canMakePayments / isPurchased
    # MOV W0, #0 ; RET -> MOV W0, #1 ; RET
    FALSE_RET = b'\x00\x00\x80\x52\xc0\x03\x5f\xd6'
    TRUE_RET  = b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'

    # Only patch if surrounded by known premium-related patterns
    PREMIUM_MARKERS = [
        b'isPremium', b'isPro', b'isSubscribed', b'isPurchased',
        b'isUnlocked', b'hasPremium', b'hasSubscription',
        b'premiumUser', b'proUser', b'isVIP', b'isActive',
        b'SKPayment', b'SKProduct', b'StoreKit',
        b'com.apple.storekit',
    ]

    idx = 0
    while True:
        pos = data.find(FALSE_RET, idx)
        if pos == -1: break
        # Check 4KB window around this position for premium markers
        window_start = max(0, pos - 2048)
        window_end   = min(len(data), pos + 2048)
        window = bytes(data[window_start:window_end])
        for marker in PREMIUM_MARKERS:
            if marker in window:
                data[pos:pos+8] = TRUE_RET
                count += 1
                break
        idx = pos + 1

    if count > 0:
        path.write_bytes(data)
    return count

def patch_ipa(ipa: Path, work: Path):
    ex = work/"ex"
    ex.mkdir(parents=True, exist_ok=True)
    info = get_info(ipa)

    with zipfile.ZipFile(ipa) as z:
        z.extractall(ex)

    total = 0
    payload_dir = ex/"Payload"
    if payload_dir.exists():
        for app in payload_dir.iterdir():
            if not app.name.endswith(".app"): continue
            # Main binary only — safer
            main = app/app.stem
            if main.exists() and main.is_file():
                total += patch_binary(main)

    out_name = f"{info['name']}-v{info['version']}-voyagersipa.ipa"
    # Replace spaces and special chars
    out_name = out_name.replace(" ", "_").replace("/","_")
    out = work/out_name

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=1) as z:  # compresslevel=1 = faster
        for f in ex.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(ex))

    return out, info, total

# ── Bot ───────────────────────────────────────────────────
async def main():
    threading.Thread(target=start_http, daemon=True).start()
    logger.info(f"HTTP on port {PORT}")

    bot = TelegramClient("voyager_bot", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("VoyagersBot started!")

    @bot.on(events.NewMessage(pattern="/start"))
    async def start_cmd(event):
        await event.respond(
            "👋 **VoyagersIPA Bot**\n\n"
            "Отправь `.ipa` файл — пропатчу и покажу превью\n"
            "Ты сам решаешь публиковать в канал или нет\n\n"
            "✅ Premium Unlocked\n"
            "✅ Pro Unlocked\n"
            "✅ No Ads\n"
            "✅ Subscription Bypass"
        )

    @bot.on(events.NewMessage(func=lambda e: e.document is not None))
    async def handle_ipa(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("❌ Нет доступа.")
            return

        fname = event.file.name or ""
        if not fname.endswith(".ipa"):
            return

        if event.document.size > 500 * 1024 * 1024:
            await event.respond("❌ Файл слишком большой (макс 500MB)")
            return

        size_mb = round(event.document.size / 1024 / 1024, 1)
        status = await event.respond(f"⏳ Скачиваю IPA ({size_mb}MB)...")
        work = Path(f"/tmp/voy_{event.id}")
        work.mkdir(parents=True, exist_ok=True)

        try:
            ipa = work/fname
            await event.download_media(ipa)
            await status.edit("🔧 Патчу бинарник...")

            loop = asyncio.get_event_loop()
            out, info, patches = await loop.run_in_executor(
                None, patch_ipa, ipa, work)

            caption = (
                f"📱 **{info['name']}**\n\n"
                f"✅ Tweak: Premium Unlocked\n"
                f"📦 Version: {info['version']}\n"
                f"🔒 Patched ✓\n\n"
                f"ℹ️ **Additional Information**\n"
                f"• Min OS Version: {info['min_ios']}\n"
                f"• Bundle ID: `{info['bundle_id']}`\n\n"
                f"_Patched by @VoyagersIPA_"
            )

            patch_info = (
                f"\n\n📊 Патчей применено: {patches}"
                if patches > 0 else
                "\n\n⚠️ Паттерны не найдены — возможно серверная проверка"
            )

            await status.edit(f"✅ Готово! Отправляю превью...")

            sent = await bot.send_file(
                event.chat_id,
                out,
                caption=caption + patch_info + "\n\n❓ **Публиковать в канал?**",
                buttons=[
                    [Button.inline("✅ Опубликовать", data=f"pub_{event.id}")],
                    [Button.inline("❌ Отмена", data=f"cancel_{event.id}")]
                ]
            )

            pending[f"pub_{event.id}"] = {
                "path": str(out),
                "caption": caption,
                "work": str(work),
            }
            await status.delete()

        except Exception as e:
            logger.error(f"err: {e}", exc_info=True)
            await status.edit(f"❌ Ошибка: {e}")

    @bot.on(events.CallbackQuery(pattern=b"pub_.*"))
    async def publish(event):
        key = event.data.decode()
        data = pending.get(key)
        if not data:
            await event.answer("❌ Файл устарел, отправь заново", alert=True)
            return
        await event.answer("📤 Публикую...")
        try:
            out = Path(data["path"])
            await bot.send_file(CHANNEL_ID, out, caption=data["caption"])
            await event.edit(
                data["caption"] + f"\n\n✅ **Опубликовано в {CHANNEL_ID}!**",
                buttons=None
            )
            del pending[key]
        except Exception as e:
            await event.answer(f"❌ Ошибка: {e}", alert=True)
        finally:
            shutil.rmtree(data["work"], ignore_errors=True)

    @bot.on(events.CallbackQuery(pattern=b"cancel_.*"))
    async def cancel(event):
        key = event.data.decode().replace("cancel_", "pub_")
        data = pending.pop(key, None)
        if data:
            shutil.rmtree(data["work"], ignore_errors=True)
        await event.edit("❌ Отменено", buttons=None)

    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
