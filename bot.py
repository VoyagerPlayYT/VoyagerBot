import os
import zipfile
import shutil
import struct
import logging
import json
import subprocess
import threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@VoyagersIPA")
ADMIN_ID   = os.environ.get("ADMIN_ID", "0")
PORT       = int(os.environ.get("PORT", "10000"))
API        = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_API   = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

# ── Dummy HTTP server so Render doesn't kill us ───────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"VoyagersBot OK")
    def log_message(self, *a): pass

def start_http():
    HTTPServer(("0.0.0.0", PORT), PingHandler).serve_forever()

# ── Telegram helpers ──────────────────────────────────────
def tg(method, **params):
    url  = f"{API}/{method}"
    data = json.dumps(params).encode()
    req  = Request(url, data=data,
                   headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        logger.error(f"tg {method} error: {e}")
        return {}

def send(chat_id, text):
    return tg("sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown")

def edit(chat_id, msg_id, text):
    return tg("editMessageText", chat_id=chat_id,
              message_id=msg_id, text=text, parse_mode="Markdown")

def download_file(file_id):
    r = tg("getFile", file_id=file_id)
    fp = r.get("result", {}).get("file_path", "")
    if not fp: return None
    with urlopen(f"{FILE_API}/{fp}", timeout=120) as resp:
        return resp.read()

def send_to_channel(path: Path, caption: str):
    import http.client
    boundary = "VoyagerBound7MA4"
    parts = []
    def field(name, value):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    field("chat_id", CHANNEL_ID)
    field("parse_mode", "Markdown")
    field("caption", caption)
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
        f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        + path.read_bytes() + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    payload = b"".join(parts)
    conn = http.client.HTTPSConnection("api.telegram.org")
    conn.request("POST", f"/bot{BOT_TOKEN}/sendDocument", payload,
                 {"Content-Type": f"multipart/form-data; boundary={boundary}",
                  "Content-Length": str(len(payload))})
    return json.loads(conn.getresponse().read())

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
    info = {"name":"Unknown","bundle_id":"unknown","version":"?.?.?","min_ios":"?"}
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
    for app in (ex/"Payload").iterdir():
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

# ── Update handler ────────────────────────────────────────
def handle(upd: dict):
    msg     = upd.get("message", {})
    if not msg: return
    chat_id = msg["chat"]["id"]
    user_id = str(msg.get("from",{}).get("id",""))
    text    = msg.get("text","")
    doc     = msg.get("document")

    if ADMIN_ID != "0" and user_id != ADMIN_ID:
        send(chat_id, "❌ Нет доступа.")
        return

    if text == "/start":
        send(chat_id,
             "👋 *VoyagersIPA Bot*\n\n"
             "Отправь `.ipa` файл — пропатчу и выложу в @VoyagersIPA\n\n"
             "✅ Premium Unlocked\n✅ Pro Unlocked\n✅ No Ads")
        return

    if not doc:
        return

    if not doc.get("file_name","").endswith(".ipa"):
        send(chat_id, "❌ Нужен `.ipa` файл!")
        return

    if doc.get("file_size",0) > 500*1024*1024:
        send(chat_id, "❌ Слишком большой файл (макс 500MB)")
        return

    st     = send(chat_id, "⏳ Скачиваю IPA...")
    msg_id = st.get("result",{}).get("message_id")
    work   = Path(f"/tmp/voy_{msg.get('message_id',0)}")
    work.mkdir(parents=True, exist_ok=True)

    try:
        raw = download_file(doc["file_id"])
        if not raw:
            edit(chat_id, msg_id, "❌ Не удалось скачать")
            return
        ipa = work/doc["file_name"]
        ipa.write_bytes(raw)

        edit(chat_id, msg_id, "🔧 Патчу бинарник...")
        out, info, patches = patch_ipa(ipa, work)

        caption = (
            f"📱 *{info['name']}*\n\n"
            f"✅ Tweak: Premium Unlocked\n"
            f"📦 Version: {info['version']}\n"
            f"🔒 Patched ✓\n\n"
            f"ℹ️ *Additional Information*\n"
            f"• Min OS Version: {info['min_ios']}\n"
            f"• Bundle ID: `{info['bundle_id']}`\n\n"
            f"_Patched by @VoyagersIPA_"
        )

        edit(chat_id, msg_id, "📤 Отправляю в канал...")
        res = send_to_channel(out, caption)
        logger.info(f"channel result: {res}")

        edit(chat_id, msg_id,
             f"✅ *Готово!*\n\n"
             f"📱 {info['name']} v{info['version']}\n"
             f"Патчей: {patches}\n"
             f"Опубликовано в {CHANNEL_ID} 🎉")
    except Exception as e:
        logger.error(f"handle err: {e}", exc_info=True)
        try: edit(chat_id, msg_id, f"❌ Ошибка: {e}")
        except: pass
    finally:
        shutil.rmtree(work, ignore_errors=True)

# ── Main ──────────────────────────────────────────────────
def main():
    # Start HTTP server in background thread
    t = threading.Thread(target=start_http, daemon=True)
    t.start()
    logger.info(f"HTTP server on port {PORT}")
    logger.info("VoyagersBot polling...")

    offset = 0
    while True:
        try:
            r = tg("getUpdates", offset=offset, timeout=25, limit=10)
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                threading.Thread(target=handle, args=(upd,), daemon=True).start()
        except Exception as e:
            logger.error(f"poll err: {e}")
            import time; time.sleep(3)

if __name__ == "__main__":
    main()
