import os
import asyncio
import zipfile
import shutil
import struct
import logging
import json
import subprocess
import threading
from pathlib import Path
from urllib.request import urlopen, Request
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_ID     = int(os.environ.get("API_ID", "0"))
API_HASH   = os.environ.get("API_HASH", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@VoyagersIPA")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "0"))
PORT       = int(os.environ.get("PORT", "10000"))

# ── HTTP server for Render ────────────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"VoyagersBot OK")
    def log_message(self, *a): pass

def start_http():
    HTTPServer(("0.0.0.0", PORT), PingHandler).serve_forever()

# ── Patcher ───────────────────────────────────────────────
def patch_binary(path: Path):
    data  = bytearray(path.read_bytes())
    count = 0
    FALSE_RET = b'\x00\x00\x80\x52\xc0\x03\x5f\xd6'
    TRUE_RET  = b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'
    idx = 0
    while True:
        pos = data.find(FALSE_RET, idx)
        if pos == -1: break
        data[pos:pos+8] = TRUE_RET
        count += 1
        idx = pos + 1
    path.write_bytes(data)
    return count

def get_info(ipa: Path):
    info = {"name":"Unknown","bundle_id":"unknown",
            "version":"?.?.?","min_ios":"?"}
    try:
        with zipfile.ZipFile(ipa) as z:
            pl = [f for f in z.namelist()
                  if f.endswith("Info.plist") and f.count("/")==2]
            if not pl:
                pl = [f for f in z.namelist() if f.endswith("Info.plist")]
            if pl:
                tmp = Path("/tmp/_info.plist")
                tmp.write_bytes(z.read(pl[0]))
                r = subprocess.run(
                    ["plutil","-convert","json","-o","-",str(tmp)],
                    capture_output=True, text=True)
                if r.returncode == 0:
                    d = json.loads(r.stdout)
                    info["name"]      = d.get("CFBundleDisplayName") or d.get("CFBundleName","Unknown")
                    info["bundle_id"] = d.get("CFBundleIdentifier","unknown")
                    info["version"]   = d.get("CFBundleShortVersionString","?.?.?")
                    info["min_ios"]   = d.get("MinimumOSVersion","?")
    except Exception as e:
        logger.error(f"info err: {e}")
    return info

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
            main = app/app.stem
            if main.exists(): total += patch_binary(main)
            fw = app/"Frameworks"
            if fw.exists():
                for f in fw.iterdir():
                    b = f if f.suffix==".dylib" else f/f.stem
                    if b.exists() and b.is_file():
                        try: total += patch_binary(b)
                        except: pass
    out = work/f"{info['name']}-v{info['version']}-voyagersipa.ipa"
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        for f in ex.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(ex))
    return out, info, total

# ── Main bot ──────────────────────────────────────────────
async def main():
    # HTTP server
    t = threading.Thread(target=start_http, daemon=True)
    t.start()
    logger.info(f"HTTP on port {PORT}")

    bot = TelegramClient("voyager_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

    @bot.on(events.NewMessage(pattern="/start"))
    async def start(event):
        await event.respond(
            "👋 **VoyagersIPA Bot**\n\n"
            "Отправь `.ipa` файл — пропатчу и выложу в @VoyagersIPA\n\n"
            "✅ Premium Unlocked\n✅ Pro Unlocked\n✅ No Ads"
        )

    @bot.on(events.NewMessage(func=lambda e: e.document and
            e.document.mime_type in ("application/octet-stream",
                                     "application/x-ios-app",
                                     "application/zip") or
            (e.document and e.file.name and e.file.name.endswith(".ipa"))))
    async def handle_ipa(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("❌ Нет доступа.")
            return

        if event.document.size > 500 * 1024 * 1024:
            await event.respond("❌ Файл слишком большой (макс 500MB)")
            return

        fname = event.file.name or "app.ipa"
        if not fname.endswith(".ipa"):
            return

        status = await event.respond("⏳ Скачиваю IPA...")
        work = Path(f"/tmp/voy_{event.id}")
        work.mkdir(parents=True, exist_ok=True)

        try:
            ipa = work/fname
            await event.download_media(ipa)
            await status.edit("🔧 Патчу бинарник...")

            out, info, patches = patch_ipa(ipa, work)

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

            await status.edit("📤 Отправляю в канал...")
            await bot.send_file(CHANNEL_ID, out, caption=caption)

            await status.edit(
                f"✅ **Готово!**\n\n"
                f"📱 {info['name']} v{info['version']}\n"
                f"Патчей: {patches}\n"
                f"Опубликовано в {CHANNEL_ID} 🎉"
            )
        except Exception as e:
            logger.error(f"err: {e}", exc_info=True)
            await status.edit(f"❌ Ошибка: {e}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    logger.info("VoyagersBot started!")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
