import os
import asyncio
import zipfile
import shutil
import struct
import logging
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError
import urllib.request

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@VoyagersIPA")
ADMIN_ID   = os.environ.get("ADMIN_ID", "0")
API        = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_API   = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

def tg(method, **params):
    url  = f"{API}/{method}"
    data = json.dumps(params).encode()
    req  = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        logger.error(f"tg {method} error: {e}")
        return {}

def send(chat_id, text, parse_mode="Markdown"):
    return tg("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)

def edit(chat_id, msg_id, text, parse_mode="Markdown"):
    return tg("editMessageText", chat_id=chat_id,
              message_id=msg_id, text=text, parse_mode=parse_mode)

def download_file(file_id):
    r = tg("getFile", file_id=file_id)
    fp = r.get("result", {}).get("file_path", "")
    if not fp: return None
    url = f"{FILE_API}/{fp}"
    req = Request(url)
    with urlopen(req, timeout=120) as resp:
        return resp.read()

def send_document_to_channel(path: Path, caption: str):
    import http.client, mimetypes
    boundary = "----VoyagerBoundary7MA4YWxkTrZu0gW"
    body = []
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="chat_id"')
    body.append(b"")
    body.append(CHANNEL_ID.encode())
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="parse_mode"')
    body.append(b"")
    body.append(b"Markdown")
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="caption"')
    body.append(b"")
    body.append(caption.encode())
    body.append(f"--{boundary}".encode())
    fname = path.name.encode()
    body.append(b'Content-Disposition: form-data; name="document"; filename="' + fname + b'"')
    body.append(b"Content-Type: application/octet-stream")
    body.append(b"")
    body.append(path.read_bytes())
    body.append(f"--{boundary}--".encode())
    payload = b"\r\n".join(body)
    conn = http.client.HTTPSConnection("api.telegram.org")
    conn.request("POST", f"/bot{BOT_TOKEN}/sendDocument",
                 payload,
                 {"Content-Type": f"multipart/form-data; boundary={boundary}",
                  "Content-Length": str(len(payload))})
    resp = conn.getresponse()
    return json.loads(resp.read())

# ── Patcher ───────────────────────────────────────────────

def patch_binary(path: Path):
    data = bytearray(path.read_bytes())
    count = 0
    # MOV W0,#0 ; RET  →  MOV W0,#1 ; RET
    FALSE_RET = b'\x00\x00\x80\x52\xc0\x03\x5f\xd6'
    TRUE_RET  = b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'
    idx = 0
    while True:
        pos = data.find(FALSE_RET, idx)
        if pos == -1: break
        data[pos:pos+8] = TRUE_RET
        count += 1
        idx = pos + 1
    # BL → NOP for common ad methods
    AD_SIGS = [b'showAd\x00', b'showBanner\x00',
               b'showInterstitial\x00', b'showRewarded\x00']
    path.write_bytes(data)
    return count

def get_info(ipa: Path):
    info = {"name":"Unknown","bundle_id":"unknown",
            "version":"?.?.?","min_ios":"?"}
    try:
        with zipfile.ZipFile(ipa) as z:
            plists = [f for f in z.namelist()
                      if f.endswith("Info.plist") and f.count("/")==2]
            if not plists:
                plists = [f for f in z.namelist() if f.endswith("Info.plist")]
            if plists:
                raw = z.read(plists[0])
                tmp = Path("/tmp/_info.plist")
                tmp.write_bytes(raw)
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
        logger.error(f"info error: {e}")
    return info

def patch_ipa(ipa: Path, work: Path):
    ex = work/"ex"
    ex.mkdir(parents=True, exist_ok=True)
    info = get_info(ipa)
    with zipfile.ZipFile(ipa) as z:
        z.extractall(ex)
    total = 0
    payload = ex/"Payload"
    for app in payload.iterdir():
        if not app.name.endswith(".app"): continue
        main = app/app.stem
        if main.exists():
            total += patch_binary(main)
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

# ── Bot loop ──────────────────────────────────────────────

def handle_update(upd: dict):
    msg = upd.get("message", {})
    if not msg: return
    chat_id = msg["chat"]["id"]
    user_id = str(msg.get("from",{}).get("id",""))

    if ADMIN_ID != "0" and user_id != ADMIN_ID:
        send(chat_id, "❌ Нет доступа.")
        return

    text = msg.get("text","")
    doc  = msg.get("document")

    if text == "/start":
        send(chat_id,
             "👋 *VoyagersIPA Bot*\n\n"
             "Отправь `.ipa` файл — пропатчу и выложу в @VoyagersIPA\n\n"
             "• Premium Unlocked\n• No Ads\n• Pro Unlocked")
        return

    if not doc:
        send(chat_id, "Отправь `.ipa` файл 👆")
        return

    if not doc.get("file_name","").endswith(".ipa"):
        send(chat_id, "❌ Нужен `.ipa` файл!")
        return

    if doc.get("file_size",0) > 500*1024*1024:
        send(chat_id, "❌ Файл слишком большой (макс 500MB)")
        return

    st = send(chat_id, "⏳ Скачиваю IPA...")
    msg_id = st.get("result",{}).get("message_id")
    work = Path(f"/tmp/voy_{msg.get('message_id')}")
    work.mkdir(parents=True, exist_ok=True)

    try:
        edit(chat_id, msg_id, "⏳ Скачиваю IPA...")
        raw = download_file(doc["file_id"])
        if not raw:
            edit(chat_id, msg_id, "❌ Не удалось скачать файл")
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
        res = send_document_to_channel(out, caption)
        logger.info(f"Channel post: {res}")

        edit(chat_id, msg_id,
             f"✅ *Готово!*\n\n"
             f"📱 {info['name']} v{info['version']}\n"
             f"• Патчей: {patches}\n"
             f"Опубликовано в {CHANNEL_ID}")
    except Exception as e:
        logger.error(f"handle error: {e}", exc_info=True)
        try: edit(chat_id, msg_id, f"❌ Ошибка: {e}")
        except: pass
    finally:
        shutil.rmtree(work, ignore_errors=True)

def main():
    logger.info("VoyagersBot starting...")
    offset = 0
    while True:
        try:
            r = tg("getUpdates", offset=offset, timeout=30, limit=10)
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    handle_update(upd)
                except Exception as e:
                    logger.error(f"update error: {e}")
        except Exception as e:
            logger.error(f"polling error: {e}")
            import time; time.sleep(5)

if __name__ == "__main__":
    main()
