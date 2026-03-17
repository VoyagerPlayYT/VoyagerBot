import os
import asyncio
import zipfile
import shutil
import logging
import json
import plistlib
import threading
import subprocess
import stat
import re
import struct
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events, Button
from telethon.tl.types import (BotCommand, BotCommandScopeDefault)
from telethon.tl.functions.bots import SetBotCommandsRequest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────
BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "YOUR_BOT_TOKEN")
API_ID     = int(os.environ.get("API_ID",  "1"))
API_HASH   = os.environ.get("API_HASH",   "a")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@VoyagersIPA")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "0"))
PORT       = int(os.environ.get("PORT",   "10000"))
APPLE_ID   = os.environ.get("APPLE_ID",   "")
APPLE_PASS = os.environ.get("APPLE_PASS", "")

IPATOOL_URL = (
    "https://github.com/majd/ipatool/releases/latest/download/"
    "ipatool-linux-amd64"
)
IPATOOL_PATH = Path("/tmp/ipatool")

# ── Storage ───────────────────────────────────────────────
pending  = {}   # pub_<id> -> {path, caption, work}
sessions = {}   # <id>     -> {ipa, work, info, selected, chat_id}
searches = {}   # <id>     -> [results]

# ── Patch definitions ─────────────────────────────────────
ALL_PATCHES = [
    ("sub",     "💎 Подписка разблокирована",  [b'isSubscribed',b'hasSubscription',b'SKPayment',b'subscription',b'Subscription']),
    ("premium", "👑 Premium Unlocked",          [b'isPremium',b'hasPremium',b'premiumUser',b'SKProduct',b'Premium']),
    ("coins",   "🪙 Безлимитные монеты",        [b'coins',b'Coins',b'gold',b'Gold',b'currency',b'Currency']),
    ("noads",   "🚫 Без рекламы",               [b'showAd',b'GADBanner',b'AdMob',b'UnityAds',b'ironSource',b'Vungle',b'AppLovin']),
    ("iap",     "🛍 Покупки за $0",             [b'SKPayment',b'canMakePayments',b'purchaseProduct',b'buyProduct',b'InAppPurchase']),
    ("pro",     "⚡ Pro версия",                [b'isPro',b'proUser',b'ProVersion',b'isProUser',b'ProUser']),
    ("vip",     "🌟 VIP статус",                [b'isVIP',b'vipUser',b'VIPStatus',b'hasVIP',b'VIPMember']),
    ("lives",   "❤️ Бесконечные жизни",         [b'lives',b'Lives',b'hearts',b'Hearts',b'life',b'Life']),
    ("energy",  "🔋 Бесконечная энергия",       [b'energy',b'Energy',b'stamina',b'Stamina',b'mana',b'Mana']),
    ("unlock",  "🔓 Всё разблокировано",        [b'isUnlocked',b'unlocked',b'locked',b'isLocked',b'Unlock']),
    ("trial",   "♾ Вечный триал",              [b'isTrial',b'trialExpired',b'trialActive',b'freeTrial',b'Trial']),
    ("gems",    "💠 Безлимитные кристаллы",     [b'gems',b'Gems',b'crystals',b'diamonds',b'jewels',b'Crystals']),
]

PATCH_MAP = {pid: markers for pid, _, markers in ALL_PATCHES}

# ── HTTP server for Render ────────────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"VoyagersBot is alive!")
    def log_message(self, *a): pass

def start_http():
    HTTPServer(("0.0.0.0", PORT), PingHandler).serve_forever()

# ── ipatool setup ─────────────────────────────────────────
async def ensure_ipatool():
    if IPATOOL_PATH.exists():
        return True
    try:
        logger.info("Downloading ipatool...")
        proc = await asyncio.create_subprocess_exec(
            "curl", "-L", "-o", str(IPATOOL_PATH), IPATOOL_URL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        IPATOOL_PATH.chmod(IPATOOL_PATH.stat().st_mode | stat.S_IEXEC)
        logger.info("ipatool downloaded!")
        return True
    except Exception as e:
        logger.error(f"ipatool download failed: {e}")
        return False

async def ipatool_auth():
    if not APPLE_ID or not APPLE_PASS:
        return False, "Apple ID не настроен в переменных окружения"
    try:
        proc = await asyncio.create_subprocess_exec(
            str(IPATOOL_PATH), "auth", "login",
            "-e", APPLE_ID, "-p", APPLE_PASS, "--non-interactive",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0:
            return True, "OK"
        return False, (out+err).decode(errors="ignore")
    except Exception as e:
        return False, str(e)

async def ipatool_search(query: str):
    await ensure_ipatool()
    try:
        proc = await asyncio.create_subprocess_exec(
            str(IPATOOL_PATH), "search", query,
            "--limit", "5", "--format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0:
            return json.loads(out.decode())
        return []
    except Exception as e:
        logger.error(f"search err: {e}")
        return []

async def ipatool_download(bundle_id: str, output_dir: Path):
    await ensure_ipatool()
    ok, msg = await ipatool_auth()
    if not ok:
        return None, f"Ошибка авторизации: {msg}"
    try:
        out_path = output_dir / f"{bundle_id}.ipa"
        proc = await asyncio.create_subprocess_exec(
            str(IPATOOL_PATH), "download",
            "--bundle-identifier", bundle_id,
            "--output", str(out_path),
            "--non-interactive",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0 and out_path.exists():
            return out_path, None
        return None, (out+err).decode(errors="ignore")[:200]
    except asyncio.TimeoutError:
        return None, "Timeout — файл слишком большой"
    except Exception as e:
        return None, str(e)

# ── Info parser ───────────────────────────────────────────
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
                    text = raw.decode("utf-8", errors="ignore")
                    def fv(key):
                        idx = text.find(key)
                        if idx==-1: return None
                        m = re.search(r'<string>(.*?)</string>', text[idx:idx+200])
                        return m.group(1) if m else None
                    info["name"]      = fv("CFBundleDisplayName") or fv("CFBundleName") or "Unknown"
                    info["bundle_id"] = fv("CFBundleIdentifier") or "unknown"
                    info["version"]   = fv("CFBundleShortVersionString") or "?.?.?"
                    info["min_ios"]   = fv("MinimumOSVersion") or "?"
    except Exception as e:
        logger.error(f"info err: {e}")
    return info

# ── Patcher ───────────────────────────────────────────────
def patch_binary(path: Path, selected: list):
    try:
        data = bytearray(path.read_bytes())
    except Exception:
        return 0
    count = 0
    active_markers = []
    for pid in selected:
        active_markers.extend(PATCH_MAP.get(pid, []))
    if not active_markers:
        return 0
    FALSE_RET = b'\x00\x00\x80\x52\xc0\x03\x5f\xd6'
    TRUE_RET  = b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'
    idx = 0
    while True:
        pos = data.find(FALSE_RET, idx)
        if pos == -1: break
        ws = max(0, pos-2048)
        we = min(len(data), pos+2048)
        window = bytes(data[ws:we])
        for m in active_markers:
            if m in window:
                data[pos:pos+8] = TRUE_RET
                count += 1
                break
        idx = pos + 1
    if count > 0:
        path.write_bytes(data)
    return count

def do_patch_ipa(ipa: Path, work: Path, selected: list):
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
            if main.exists() and main.is_file():
                total += patch_binary(main, selected)
            fw = app/"Frameworks"
            if fw.exists():
                for f in fw.iterdir():
                    b = f if f.suffix==".dylib" else f/f.stem
                    if b.exists() and b.is_file():
                        try: total += patch_binary(b, selected)
                        except: pass
    out_name = re.sub(r'[^\w\-.]', '_',
               f"{info['name']}-v{info['version']}-voyagersipa.ipa")
    out = work/out_name
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for f in ex.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(ex))
    return out, info, total

# ── Keyboards ─────────────────────────────────────────────
def patch_keyboard(sid: str, selected: set):
    rows = []
    for pid, label, _ in ALL_PATCHES:
        chk = "✅ " if pid in selected else "☑️ "
        rows.append([Button.inline(chk+label, data=f"t_{sid}_{pid}")])
    rows.append([
        Button.inline("✅ Все",  data=f"selall_{sid}"),
        Button.inline("❌ Сброс", data=f"clrall_{sid}"),
    ])
    rows.append([Button.inline("🔨 ХАКНУТЬ!", data=f"hack_{sid}")])
    return rows

def main_menu_buttons():
    return [
        [Button.text("📦 Загрузить IPA", resize=True),
         Button.text("🔍 Найти в App Store")],
        [Button.text("📋 История"),
         Button.text("⚙️ Настройки")],
        [Button.text("📢 Канал @VoyagersIPA")],
    ]

def search_keyboard(sid: str, results: list):
    rows = []
    for i, r in enumerate(results):
        name    = r.get("name","?")[:30]
        version = r.get("version","?")
        rows.append([Button.inline(
            f"📱 {name} v{version}",
            data=f"dl_{sid}_{i}"
        )])
    rows.append([Button.inline("❌ Отмена", data=f"srchcancel_{sid}")])
    return rows

# ── Format caption ────────────────────────────────────────
def format_caption(info: dict, selected: list):
    labels = [label for pid, label, _ in ALL_PATCHES if pid in selected]
    tweaks = "\n".join(f"• {l}" for l in labels)
    return (
        f"📱 **{info['name']}**\n\n"
        f"✅ Tweaks:\n{tweaks}\n\n"
        f"📦 Version: {info['version']}\n"
        f"🔒 Patched ✓\n\n"
        f"ℹ️ **Additional Information**\n"
        f"• Min OS Version: {info['min_ios']}\n"
        f"• Bundle ID: `{info['bundle_id']}`\n\n"
        f"_Patched by @VoyagersIPA_"
    )

# ── Main ──────────────────────────────────────────────────
async def main():
    threading.Thread(target=start_http, daemon=True).start()
    logger.info(f"HTTP server on port {PORT}")

    bot = TelegramClient("voyager_bot", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    # Register bot commands
    try:
        await bot(SetBotCommandsRequest(
            scope=BotCommandScopeDefault(),
            lang_code="",
            commands=[
                BotCommand("start",   "🏠 Главное меню"),
                BotCommand("search",  "🔍 Найти приложение"),
                BotCommand("upload",  "📦 Загрузить IPA"),
                BotCommand("channel", "📢 Наш канал"),
                BotCommand("help",    "❓ Помощь"),
            ]
        ))
    except Exception as e:
        logger.warning(f"commands set failed: {e}")

    await ensure_ipatool()
    logger.info("VoyagersBot started!")

    # ── /start ────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern="/start"))
    async def cmd_start(event):
        await event.respond(
            "👋 **VoyagersIPA Bot**\n\n"
            "Я патчу iOS приложения и публикую в @VoyagersIPA\n\n"
            "**Что я умею:**\n"
            "📦 Принимаю `.ipa` файлы напрямую\n"
            "🔍 Ищу и скачиваю из App Store\n"
            "🔨 Патчу: подписки, премиум, рекламу и др.\n"
            "📢 Публикую в канал одной кнопкой\n\n"
            "Выбери действие 👇",
            buttons=main_menu_buttons()
        )

    # ── /help ─────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern="/help"))
    async def cmd_help(event):
        await event.respond(
            "❓ **Помощь**\n\n"
            "**Способ 1 — Загрузить IPA:**\n"
            "Просто отправь `.ipa` файл боту\n\n"
            "**Способ 2 — App Store:**\n"
            "Напиши `/search название приложения`\n"
            "или нажми кнопку 🔍 Найти в App Store\n\n"
            "**Процесс:**\n"
            "1️⃣ Загрузи/найди приложение\n"
            "2️⃣ Выбери что взломать (галочки)\n"
            "3️⃣ Нажми 🔨 ХАКНУТЬ!\n"
            "4️⃣ Получи IPA файл\n"
            "5️⃣ Нажми ✅ Опубликовать\n\n"
            "**Патчи:**\n" +
            "\n".join(f"• {label}" for _, label, _ in ALL_PATCHES),
            buttons=main_menu_buttons()
        )

    # ── /channel ──────────────────────────────────────────
    @bot.on(events.NewMessage(pattern="/channel"))
    async def cmd_channel(event):
        await event.respond(
            f"📢 Наш канал: {CHANNEL_ID}\n"
            "Подпишись чтобы получать пропатченные IPA!",
            buttons=main_menu_buttons()
        )

    # ── /search <query> ───────────────────────────────────
    @bot.on(events.NewMessage(pattern=r"/search (.+)"))
    async def cmd_search(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("❌ Нет доступа.")
            return
        query = event.pattern_match.group(1).strip()
        await _do_search(event, query)

    # ── Text button handlers ──────────────────────────────
    @bot.on(events.NewMessage(pattern="🔍 Найти в App Store"))
    async def btn_search(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            return
        await event.respond(
            "🔍 Введи название приложения:\n"
            "Например: `/search Spotify`",
            buttons=main_menu_buttons()
        )

    @bot.on(events.NewMessage(pattern="📦 Загрузить IPA"))
    async def btn_upload(event):
        await event.respond(
            "📦 Отправь `.ipa` файл прямо в этот чат",
            buttons=main_menu_buttons()
        )

    @bot.on(events.NewMessage(pattern="📢 Канал @VoyagersIPA"))
    async def btn_channel(event):
        await event.respond(
            f"📢 Подпишись на наш канал:\n{CHANNEL_ID}",
            buttons=main_menu_buttons()
        )

    @bot.on(events.NewMessage(pattern="⚙️ Настройки"))
    async def btn_settings(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            return
        apple_status = "✅ Настроен" if APPLE_ID else "❌ Не настроен"
        await event.respond(
            f"⚙️ **Настройки**\n\n"
            f"🍎 Apple ID: {apple_status}\n"
            f"📢 Канал: {CHANNEL_ID}\n"
            f"🤖 Admin ID: {ADMIN_ID}\n\n"
            f"Для изменения обновите переменные в Render",
            buttons=main_menu_buttons()
        )

    @bot.on(events.NewMessage(pattern="📋 История"))
    async def btn_history(event):
        await event.respond(
            "📋 История публикаций пока недоступна\n"
            "В разработке...",
            buttons=main_menu_buttons()
        )

    # ── Search helper ─────────────────────────────────────
    async def _do_search(event, query: str):
        status = await event.respond(f"🔍 Ищу **{query}**...")
        results = await ipatool_search(query)
        if not results:
            await status.edit(
                f"❌ Ничего не найдено по запросу **{query}**\n"
                "Попробуй другой запрос или загрузи IPA вручную"
            )
            return
        sid = str(event.id)
        searches[sid] = results
        text = f"🔍 Результаты для **{query}**:\n\nВыбери приложение:"
        await status.edit(text, buttons=search_keyboard(sid, results))

    # ── IPA file handler ──────────────────────────────────
    @bot.on(events.NewMessage(func=lambda e: e.document is not None))
    async def handle_ipa(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("❌ Нет доступа.")
            return
        fname = event.file.name or ""
        if not fname.endswith(".ipa"):
            return
        if event.document.size > 700 * 1024 * 1024:
            await event.respond("❌ Файл слишком большой (макс 700MB)")
            return
        size_mb = round(event.document.size / 1024 / 1024, 1)
        status  = await event.respond(f"⏳ Скачиваю IPA ({size_mb}MB)...")
        work    = Path(f"/tmp/voy_{event.id}")
        work.mkdir(parents=True, exist_ok=True)
        try:
            ipa = work/fname
            await event.download_media(ipa)
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, get_info, ipa)
            await _show_patch_menu(event, status, work, ipa, info)
        except Exception as e:
            logger.error(f"ipa err: {e}", exc_info=True)
            await status.edit(f"❌ Ошибка: {e}")

    # ── Show patch selection menu ─────────────────────────
    async def _show_patch_menu(event, status, work, ipa, info):
        sid = str(event.id)
        default = {"sub","premium","noads","iap"}
        sessions[sid] = {
            "ipa":      str(ipa),
            "work":     str(work),
            "info":     info,
            "selected": default,
            "chat_id":  event.chat_id,
        }
        await status.delete()
        await bot.send_message(
            event.chat_id,
            f"📱 **{info['name']}** v{info['version']}\n"
            f"`{info['bundle_id']}`\n"
            f"📏 {info.get('size_mb','?')} MB | iOS {info['min_ios']}+\n\n"
            f"Выбери патчи и нажми **🔨 ХАКНУТЬ!**",
            buttons=patch_keyboard(sid, default)
        )

    # ── Inline: search result download ───────────────────
    @bot.on(events.CallbackQuery(pattern=b"dl_.*"))
    async def cb_download(event):
        parts  = event.data.decode().split("_", 2)
        sid    = parts[1]
        idx    = int(parts[2])
        result = searches.get(sid, [])[idx] if searches.get(sid) else None
        if not result:
            await event.answer("❌ Результат устарел", alert=True)
            return
        bundle_id = result.get("bundleIdentifier") or result.get("bundle_id","")
        name      = result.get("name","?")
        await event.answer(f"⏳ Скачиваю {name}...")
        await event.edit(f"⏳ Скачиваю **{name}** из App Store...")
        work = Path(f"/tmp/voy_dl_{sid}")
        work.mkdir(parents=True, exist_ok=True)
        ipa, err = await ipatool_download(bundle_id, work)
        if not ipa:
            await event.edit(f"❌ Ошибка скачивания:\n`{err}`")
            shutil.rmtree(work, ignore_errors=True)
            return
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_info, ipa)
        status = await bot.send_message(event.chat_id, "✅ Скачано!")
        await _show_patch_menu_from_cb(event, status, work, ipa, info)

    async def _show_patch_menu_from_cb(event, status, work, ipa, info):
        sid = f"dl{event.id}"
        default = {"sub","premium","noads","iap"}
        sessions[sid] = {
            "ipa":      str(ipa),
            "work":     str(work),
            "info":     info,
            "selected": default,
            "chat_id":  event.chat_id,
        }
        await status.delete()
        await bot.send_message(
            event.chat_id,
            f"📱 **{info['name']}** v{info['version']}\n"
            f"`{info['bundle_id']}`\n"
            f"📏 {info.get('size_mb','?')} MB | iOS {info['min_ios']}+\n\n"
            f"Выбери патчи и нажми **🔨 ХАКНУТЬ!**",
            buttons=patch_keyboard(sid, default)
        )

    # ── Inline: toggle patch ──────────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"t_.*"))
    async def cb_toggle(event):
        parts = event.data.decode().split("_", 2)
        sid   = parts[1]
        pid   = parts[2]
        sess  = sessions.get(sid)
        if not sess:
            await event.answer("❌ Сессия устарела", alert=True)
            return
        sel = sess["selected"]
        if pid in sel:
            sel.discard(pid)
            await event.answer("☑️ Убрано")
        else:
            sel.add(pid)
            await event.answer("✅ Добавлено")
        info = sess["info"]
        await event.edit(
            f"📱 **{info['name']}** v{info['version']}\n"
            f"`{info['bundle_id']}`\n\n"
            f"Выбрано: {len(sel)} патч(ей)\n"
            f"Нажми **🔨 ХАКНУТЬ!** когда готов",
            buttons=patch_keyboard(sid, sel)
        )

    # ── Inline: select all / clear ────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"selall_.*"))
    async def cb_selall(event):
        sid  = event.data.decode().split("_",1)[1]
        sess = sessions.get(sid)
        if not sess:
            await event.answer("❌ Сессия устарела", alert=True)
            return
        sess["selected"] = {pid for pid,_,_ in ALL_PATCHES}
        await event.answer("✅ Все выбраны")
        info = sess["info"]
        await event.edit(
            f"📱 **{info['name']}** v{info['version']}\n\n"
            f"Выбрано: {len(sess['selected'])} патч(ей)",
            buttons=patch_keyboard(sid, sess["selected"])
        )

    @bot.on(events.CallbackQuery(pattern=b"clrall_.*"))
    async def cb_clrall(event):
        sid  = event.data.decode().split("_",1)[1]
        sess = sessions.get(sid)
        if not sess:
            await event.answer("❌ Сессия устарела", alert=True)
            return
        sess["selected"] = set()
        await event.answer("❌ Сброшено")
        info = sess["info"]
        await event.edit(
            f"📱 **{info['name']}** v{info['version']}\n\n"
            f"Ничего не выбрано",
            buttons=patch_keyboard(sid, set())
        )

    # ── Inline: HACK! ─────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"hack_.*"))
    async def cb_hack(event):
        sid  = event.data.decode().split("_",1)[1]
        sess = sessions.get(sid)
        if not sess:
            await event.answer("❌ Сессия устарела", alert=True)
            return
        sel = sess["selected"]
        if not sel:
            await event.answer("❌ Выбери хотя бы один патч!", alert=True)
            return
        await event.answer("🔨 Хакаю...")
        info   = sess["info"]
        labels = [label for pid,label,_ in ALL_PATCHES if pid in sel]
        await event.edit(
            f"📱 **{info['name']}** v{info['version']}\n\n"
            "🔨 **Патчу:**\n" + "\n".join(labels) + "\n\n⏳ Подождите...",
            buttons=None
        )
        try:
            ipa  = Path(sess["ipa"])
            work = Path(sess["work"])
            loop = asyncio.get_event_loop()
            out, info2, patches = await loop.run_in_executor(
                None, do_patch_ipa, ipa, work, list(sel))
            caption = format_caption(info, list(sel))
            patch_note = (
                f"\n\n📊 Патчей применено: **{patches}**"
                if patches > 0 else
                "\n\n⚠️ Паттерны не найдены (серверная проверка?)"
            )
            sent = await bot.send_file(
                sess["chat_id"],
                out,
                caption=caption + patch_note + "\n\n❓ **Публиковать в канал?**",
                buttons=[
                    [Button.inline("✅ Опубликовать в канал", data=f"pub_{sid}")],
                    [Button.inline("🔄 Перепатчить",         data=f"repatch_{sid}")],
                    [Button.inline("❌ Не публиковать",       data=f"nopub_{sid}")],
                ]
            )
            pending[f"pub_{sid}"] = {
                "path":    str(out),
                "caption": caption,
                "work":    str(work),
            }
            del sessions[sid]
        except Exception as e:
            logger.error(f"hack err: {e}", exc_info=True)
            await bot.send_message(sess["chat_id"], f"❌ Ошибка: {e}")

    # ── Inline: publish ───────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"pub_.*"))
    async def cb_publish(event):
        key  = event.data.decode()
        data = pending.get(key)
        if not data:
            await event.answer("❌ Файл устарел — отправь заново", alert=True)
            return
        await event.answer("📤 Публикую в канал...")
        try:
            out = Path(data["path"])
            await bot.send_file(CHANNEL_ID, out, caption=data["caption"])
            await event.edit(
                data["caption"] + f"\n\n✅ **Опубликовано в {CHANNEL_ID}!**",
                buttons=None
            )
            del pending[key]
            logger.info(f"Published to {CHANNEL_ID}: {out.name}")
        except Exception as e:
            await event.answer(f"❌ Ошибка: {e}", alert=True)
        finally:
            shutil.rmtree(data.get("work",""), ignore_errors=True)

    # ── Inline: repatch ───────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"repatch_.*"))
    async def cb_repatch(event):
        await event.answer("♻️ Открываю меню патчей...")
        key = event.data.decode().replace("repatch_","pub_")
        data = pending.pop(key, None)
        if not data:
            await event.edit("❌ Сессия устарела", buttons=None)
            return
        work = Path(data["work"])
        ipa_files = list(work.glob("*.ipa"))
        orig_ipa  = next((f for f in ipa_files
                         if "voyagersipa" not in f.name), ipa_files[0] if ipa_files else None)
        if not orig_ipa:
            await event.edit("❌ Оригинальный файл не найден", buttons=None)
            return
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_info, orig_ipa)
        sid  = f"re{event.id}"
        sessions[sid] = {
            "ipa":      str(orig_ipa),
            "work":     str(work),
            "info":     info,
            "selected": {"sub","premium","noads","iap"},
            "chat_id":  event.chat_id,
        }
        await event.edit(
            f"📱 **{info['name']}** v{info['version']}\n\n"
            f"Выбери новые патчи:",
            buttons=patch_keyboard(sid, {"sub","premium","noads","iap"})
        )

    # ── Inline: no publish ────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"nopub_.*"))
    async def cb_nopub(event):
        key  = event.data.decode().replace("nopub_","pub_")
        data = pending.pop(key, None)
        if data:
            shutil.rmtree(data.get("work",""), ignore_errors=True)
        await event.edit("❌ Не опубликовано. Файл удалён.", buttons=None)

    # ── Inline: search cancel ─────────────────────────────
    @bot.on(events.CallbackQuery(pattern=b"srchcancel_.*"))
    async def cb_srchcancel(event):
        sid = event.data.decode().split("_",1)[1]
        searches.pop(sid, None)
        await event.edit("❌ Поиск отменён", buttons=None)

    logger.info("All handlers registered. Running...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
