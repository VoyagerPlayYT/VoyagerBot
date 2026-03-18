#!/usr/bin/env python3
"""
Voyager Dylib Bot v3.0
Функции: reply keyboard, смена языка всего бота, App Store поиск,
инжект dylib в IPA с прогрессом, источники dylib, настройки, история, статистика
"""

import os, sys, asyncio, zipfile, shutil, logging, json, tempfile, time
import aiohttp
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from telethon import TelegramClient, events, Button
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from dotenv import load_dotenv

# ============================================================
# КОНСТАНТЫ
# ============================================================

SESSION_NAME    = "voyager_dylib_bot"
HISTORY_FILE    = "history.json"
STATS_FILE      = "stats.json"
SETTINGS_FILE   = "settings.json"
MAX_HISTORY     = 100
DYLIB_PAGE_SIZE = 8
VERSION         = "3.0"
CHANNEL         = "@voyagersipa"
ITUNES_TIMEOUT  = 15

DYLIB_SOURCES = {
    "ru": (
        "\U0001f4da **Источники dylib:**\n\n"
        "\U0001f4f1 Telegram:\n"
        "  \u2022 @iosgodsipa\n"
        "  \u2022 @iphoneipa\n"
        "  \u2022 @voyagersipa\n\n"
        "\U0001f419 GitHub:\n"
        "  \u2022 github.com/opa334/TrollStore\n"
        "  \u2022 github.com/Al4ise/Azule\n"
        "  \u2022 github.com/nickhwallace/Dopamine\n\n"
        "\U0001f4a1 Скачай .dylib \u2192 положи в папку бота \u2192 перезапусти"
    ),
    "en": (
        "\U0001f4da **Dylib sources:**\n\n"
        "\U0001f4f1 Telegram:\n"
        "  \u2022 @iosgodsipa\n"
        "  \u2022 @iphoneipa\n"
        "  \u2022 @voyagersipa\n\n"
        "\U0001f419 GitHub:\n"
        "  \u2022 github.com/opa334/TrollStore\n"
        "  \u2022 github.com/Al4ise/Azule\n"
        "  \u2022 github.com/nickhwallace/Dopamine\n\n"
        "\U0001f4a1 Download .dylib \u2192 put in bot folder \u2192 restart"
    ),
}

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================
# СОСТОЯНИЕ
# ============================================================

user_langs:   Dict[int, str]  = {}
user_dylib:   Dict[int, List[str]] = {}  # мультиселект: список выбранных dylib
user_state:   Dict[int, dict] = {}
history:      List[dict]      = []
stats:        dict            = {}
bot_settings: dict            = {}

# ============================================================
# ПЕРЕВОДЫ
# ============================================================
# ВАЖНО: кнопки reply-keyboard определяются по тексту в btn_* ключах.
# Смена языка меняет ВСЕ — и тексты сообщений, и тексты кнопок.

TR: Dict[str, Dict[str, str]] = {
    "ru": {
        "welcome":          "\U0001f44b **Voyager Dylib Bot** v{version}\n\n\U0001f4e6 Инжектор dylib в IPA\n\U0001f4da Dylib: **{count}**\n\U0001f4e3 Канал: {channel}\n\nВыбери действие \U0001f447",
        "btn_upload":       "\U0001f4e6 Загрузить IPA",
        "btn_appstore":     "\U0001f50d App Store",
        "btn_dylibs":       "\U0001f4da Dylib",
        "btn_lang":         "\U0001f310 Язык: RU",
        "btn_history":      "\U0001f4cb История",
        "btn_settings":     "\u2699\ufe0f Настройки",
        "btn_channel":      "\U0001f4e3 Канал",
        "help":             "\U0001f527 **Инструкция:**\n\n1\ufe0f\u20e3 **\U0001f4da Dylib** \u2192 выбери dylib\n2\ufe0f\u20e3 **\U0001f4e6 Загрузить IPA** \u2192 отправь .ipa\n   или **\U0001f50d App Store** \u2192 найди приложение\n3\ufe0f\u20e3 Получи патченый IPA!\n\n\U0001f310 **Язык** \u2014 меняет ВЕСЬ интерфейс\n\u2699\ufe0f **Настройки** \u2014 AppleID, канал, admin",
        "no_dlib":          "\u26a0\ufe0f **Dylib не выбран!**\n\nНажми **\U0001f4da Dylib**",
        "dlib_selected":    "\u2705 Выбран: **{dlib}**\n\n\U0001f4e6 Отправь .ipa файл:",
        "no_dylibs_folder": "\U0001f4ad В папке нет .dylib файлов!",
        "dylib_header":     "\U0001f4da **Выбери dylib:**\n\nСтр. {page}/{total}",
        "send_ipa":         "\U0001f4e6 **Отправь .ipa** для инжекта\n\U0001f48a Dylib: **{dlib}**",
        "dl_progress":      "\U0001f4e5 Скачиваю...\n`{name}`\n{pct}% \u2014 {recv} / {total}",
        "patching":         "\U0001f528 Инжектирую **{dlib}**...\n\u23f3 Подожди...",
        "patch_step":       "\U0001f528 {step}",
        "patch_done":       "\u2705 **Готово!**\n\n\U0001f4c4 `{filename}`\n\U0001f48a **{dlib}**\n\U0001f4e4 Отправляю...",
        "patch_err":        "\u274c **Ошибка:**\n`{error}`",
        "appstore_prompt":  "\U0001f50d **App Store**\n\nВведи название приложения:",
        "appstore_search":  "\U0001f50d Ищу **{query}**...",
        "appstore_results": "\U0001f50d **Результаты «{query}»:**",
        "appstore_none":    "\u274c По запросу **{query}** ничего\n\nПопробуй другое название",
        "appstore_timeout": "\u23f1 Поиск занял слишком долго (>{t}с)\n\nПопробуй ещё раз",
        "appstore_err":     "\u274c Ошибка поиска: {error}",
        "no_ipa_link":      "\u274c Прямая ссылка на IPA недоступна для **{name}**\n\nСкачай IPA вручную с {channel}",
        "hist_header":      "\U0001f4cb **История** ({count}):\n\n",
        "hist_empty":       "\U0001f4ed История пуста",
        "hist_entry":       "{n}. `{dlib}` \u2190 `{ipa}` [{t}]",
        "stats_header":     "\U0001f4ca **Статистика**\n\n\U0001f527 Патчей: **{patches}**\n\U0001f465 Юзеров: **{users}**\n\U0001f4da Dylib: **{dylibs}**\n\n\U0001f3c6 **Топ:**\n{top}",
        "stats_row":        "  {n}. `{name}` \u2014 {cnt}\u00d7",
        "stats_empty":      "\U0001f4ca Нет данных",
        "sett_header":      "\u2699\ufe0f **Настройки**\n\n\U0001f464 AppleID: `{appleid}`\n\U0001f4e3 Канал: `{channel}`\n\U0001f511 Admin: `{admin}`",
        "sett_appleid":     "\U0001f464 Введи Apple ID (email):",
        "sett_channel":     "\U0001f4e3 Введи ID канала (напр. -100123456789 или @name):",
        "sett_admin":       "\U0001f511 Введи Telegram ID администратора:",
        "sett_saved":       "\u2705 Сохранено: **{key}** = `{val}`",
        "sett_invalid":     "\u274c Неверный формат. Попробуй ещё раз.",
        "lang_prompt":      "\U0001f310 **Выбери язык:**",
        "lang_ru":          "\U0001f1f7\U0001f1fa Язык изменён на **Русский**\n\nКлавиатура обновлена \U0001f447",
        "lang_en":          "\U0001f1fa\U0001f1f8 Language changed to **English**\n\nKeyboard updated \U0001f447",
        "channel_text":     "\U0001f4e3 **Канал:** {channel}\n\nThere:\n\u2022 IPA файлы\n\u2022 dylib патчи\n\u2022 Обновления",
        "page_info":        "\U0001f4c4 {cur}/{total}",
        "back":             "\u25c0 Назад",
        "home":             "\U0001f3e0 Меню",
        "next_pg":          "Вперёд \u25b6",
        "prev_pg":          "\u25c0 Назад",
        "cancel":           "\u274c Отмена",
        "dl_btn":           "\U0001f4e5 Скачать IPA",
        "pick_dlib":        "\U0001f48a Выбрать dylib",
    },
    "en": {
        "welcome":          "\U0001f44b **Voyager Dylib Bot** v{version}\n\n\U0001f4e6 dylib injector for IPA\n\U0001f4da Dylibs: **{count}**\n\U0001f4e3 Channel: {channel}\n\nPick an action \U0001f447",
        "btn_upload":       "\U0001f4e6 Upload IPA",
        "btn_appstore":     "\U0001f50d App Store",
        "btn_dylibs":       "\U0001f4da Dylib",
        "btn_lang":         "\U0001f310 Lang: EN",
        "btn_history":      "\U0001f4cb History",
        "btn_settings":     "\u2699\ufe0f Settings",
        "btn_channel":      "\U0001f4e3 Channel",
        "help":             "\U0001f527 **How to use:**\n\n1\ufe0f\u20e3 **\U0001f4da Dylib** \u2192 pick a dylib\n2\ufe0f\u20e3 **\U0001f4e6 Upload IPA** \u2192 send .ipa\n   or **\U0001f50d App Store** \u2192 find app\n3\ufe0f\u20e3 Get patched IPA!\n\n\U0001f310 **Lang** \u2014 switches ALL interface\n\u2699\ufe0f **Settings** \u2014 AppleID, channel, admin",
        "no_dlib":          "\u26a0\ufe0f **No dylib selected!**\n\nTap **\U0001f4da Dylib**",
        "dlib_selected":    "\u2705 Selected: **{dlib}**\n\n\U0001f4e6 Send your .ipa file:",
        "no_dylibs_folder": "\U0001f4ad No .dylib files in folder!",
        "dylib_header":     "\U0001f4da **Pick a dylib:**\n\nPage {page}/{total}",
        "send_ipa":         "\U0001f4e6 **Send your .ipa** to inject\n\U0001f48a Dylib: **{dlib}**",
        "dl_progress":      "\U0001f4e5 Downloading...\n`{name}`\n{pct}% \u2014 {recv} / {total}",
        "patching":         "\U0001f528 Injecting **{dlib}**...\n\u23f3 Please wait...",
        "patch_step":       "\U0001f528 {step}",
        "patch_done":       "\u2705 **Done!**\n\n\U0001f4c4 `{filename}`\n\U0001f48a **{dlib}**\n\U0001f4e4 Sending...",
        "patch_err":        "\u274c **Error:**\n`{error}`",
        "appstore_prompt":  "\U0001f50d **App Store**\n\nEnter app name:",
        "appstore_search":  "\U0001f50d Searching **{query}**...",
        "appstore_results": "\U0001f50d **Results for «{query}»:**",
        "appstore_none":    "\u274c Nothing found for **{query}**\n\nTry different name",
        "appstore_timeout": "\u23f1 Search too slow (>{t}s)\n\nTry again",
        "appstore_err":     "\u274c Search error: {error}",
        "no_ipa_link":      "\u274c Direct IPA unavailable for **{name}**\n\nDownload manually from {channel}",
        "hist_header":      "\U0001f4cb **History** ({count}):\n\n",
        "hist_empty":       "\U0001f4ed No patches yet",
        "hist_entry":       "{n}. `{dlib}` \u2190 `{ipa}` [{t}]",
        "stats_header":     "\U0001f4ca **Statistics**\n\n\U0001f527 Patches: **{patches}**\n\U0001f465 Users: **{users}**\n\U0001f4da Dylibs: **{dylibs}**\n\n\U0001f3c6 **Top:**\n{top}",
        "stats_row":        "  {n}. `{name}` \u2014 {cnt}\u00d7",
        "stats_empty":      "\U0001f4ca No data yet",
        "sett_header":      "\u2699\ufe0f **Settings**\n\n\U0001f464 AppleID: `{appleid}`\n\U0001f4e3 Channel: `{channel}`\n\U0001f511 Admin: `{admin}`",
        "sett_appleid":     "\U0001f464 Enter Apple ID (email):",
        "sett_channel":     "\U0001f4e3 Enter channel ID (e.g. -100123456789 or @name):",
        "sett_admin":       "\U0001f511 Enter admin Telegram ID:",
        "sett_saved":       "\u2705 Saved: **{key}** = `{val}`",
        "sett_invalid":     "\u274c Invalid format. Try again.",
        "lang_prompt":      "\U0001f310 **Choose language:**",
        "lang_ru":          "\U0001f1f7\U0001f1fa Язык изменён на **Русский**\n\nКлавиатура обновлена \U0001f447",
        "lang_en":          "\U0001f1fa\U0001f1f8 Language changed to **English**\n\nKeyboard updated \U0001f447",
        "channel_text":     "\U0001f4e3 **Channel:** {channel}\n\nFind there:\n\u2022 IPA files\n\u2022 dylib patches\n\u2022 Updates",
        "page_info":        "\U0001f4c4 {cur}/{total}",
        "back":             "\u25c0 Back",
        "home":             "\U0001f3e0 Menu",
        "next_pg":          "Next \u25b6",
        "prev_pg":          "\u25c0 Prev",
        "cancel":           "\u274c Cancel",
        "dl_btn":           "\U0001f4e5 Download IPA",
        "pick_dlib":        "\U0001f48a Select dylib",
    },
}


def t(key: str, lang: str = "ru", **kw) -> str:
    kw.setdefault("version", VERSION)
    kw.setdefault("count",   len(get_dylibs()))
    kw.setdefault("channel", CHANNEL)
    tmpl = TR.get(lang, TR["ru"]).get(key, f"[{key}]")
    try:
        return tmpl.format(**kw)
    except (KeyError, ValueError):
        return tmpl


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_dylibs(folder: str = ".") -> List[str]:
    try:
        return sorted(f for f in os.listdir(folder) if f.endswith(".dylib"))
    except OSError:
        return []


def dshort(name: str) -> str:
    return name[:-6] if name.endswith(".dylib") else name


def get_lang(uid: int) -> str:
    return user_langs.get(uid, "ru")


def fmt_bytes(n: int) -> str:
    for u in ["Б", "КБ", "МБ", "ГБ"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ГБ"


# ============================================================
# REPLY KEYBOARD
# ============================================================

def reply_kb(lang: str = "ru") -> List:
    """
    Постоянная клавиатура (Button.text) под полем ввода.
    Язык кнопки btn_lang показывает ТЕКУЩИЙ язык.
    Смена языка перестраивает всю клавиатуру.
    """
    return [
        [Button.text(t("btn_upload",   lang)), Button.text(t("btn_appstore", lang))],
        [Button.text(t("btn_dylibs",   lang)), Button.text(t("btn_lang",     lang))],
        [Button.text(t("btn_history",  lang)), Button.text(t("btn_settings", lang))],
        [Button.text(t("btn_channel",  lang))],
    ]


def _all_btn_texts() -> List[str]:
    """Все возможные тексты кнопок (RU + EN) для фильтрации."""
    out = []
    for lng in ("ru", "en"):
        for k in ("btn_upload","btn_appstore","btn_dylibs","btn_lang",
                  "btn_history","btn_settings","btn_channel"):
            out.append(t(k, lng))
    return out


ALL_BTNS: List[str] = []   # заполняем после определения t()


def _match_btn(text: str) -> Optional[str]:
    for lng in ("ru", "en"):
        for k in ("btn_upload","btn_appstore","btn_dylibs","btn_lang",
                  "btn_history","btn_settings","btn_channel"):
            if t(k, lng) == text:
                return k
    return None


# ============================================================
# INLINE KB — DYLIB
# ============================================================

def dylib_kb(page: int = 0, dlibs: Optional[List[str]] = None,
             selected: Optional[List[str]] = None) -> List:
    """
    Мультиселект dylib.
    Выбранные отмечены ✅, невыбранные — 💊.
    Внизу: [✅ Готово (N)] [🗑 Сбросить] [◀ / ▶]
    """
    if dlibs is None:
        dlibs = get_dylibs()
    if selected is None:
        selected = []
    total = max(1, (len(dlibs) + DYLIB_PAGE_SIZE - 1) // DYLIB_PAGE_SIZE)
    page  = max(0, min(page, total - 1))
    rows  = []
    start = page * DYLIB_PAGE_SIZE
    for i in range(start, min(start + DYLIB_PAGE_SIZE, len(dlibs))):
        name  = dlibs[i]
        short = dshort(name)[:22]
        tick  = "\u2705" if name in selected else "\U0001f48a"
        rows.append([Button.inline(
            f"{tick} {short}",
            f"dl_{name}".encode()
        )])
    if not rows:
        rows.append([Button.inline("\U0001f4ad Нет dylib", b"noop")])

    # Навигация
    nav = []
    if page > 0:
        nav.append(Button.inline("\u25c0", f"dp_{page-1}".encode()))
    nav.append(Button.inline(f"\U0001f4c4 {page+1}/{total}", b"noop"))
    if page < total - 1:
        nav.append(Button.inline("\u25b6", f"dp_{page+1}".encode()))
    rows.append(nav)

    # Готово / Сбросить
    n = len(selected)
    done_label = f"\u2705 Готово ({n})" if n > 0 else "\u2705 Готово"
    rows.append([
        Button.inline(done_label,        b"dl_done"),
        Button.inline("\U0001f5d1 Сбросить", b"dl_reset"),
    ])
    return rows


# ============================================================
# ИСТОРИЯ
# ============================================================

def load_history() -> None:
    global history
    try:
        history = json.load(open(HISTORY_FILE, encoding="utf-8"))
    except Exception:
        history = []


def save_hist(entry: dict) -> None:
    history.append(entry)
    history[:] = history[-MAX_HISTORY:]
    try:
        json.dump(history, open(HISTORY_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except OSError:
        pass


def render_hist(lang: str) -> str:
    if not history:
        return t("hist_empty", lang)
    lines = []
    for i, e in enumerate(reversed(history[-20:]), 1):
        lines.append(t("hist_entry", lang,
                       n=i, dlib=dshort(e.get("dlib","?")),
                       ipa=e.get("ipa","?"), t=e.get("time","?")))
    return "\n".join(lines)


# ============================================================
# СТАТИСТИКА
# ============================================================

def load_stats() -> None:
    global stats
    try:
        stats = json.load(open(STATS_FILE, encoding="utf-8"))
    except Exception:
        stats = {"patches": 0, "users": [], "usage": {}}


def record_stats(uid: int, dlib: str) -> None:
    stats["patches"] = stats.get("patches", 0) + 1
    users = stats.setdefault("users", [])
    if uid not in users:
        users.append(uid)
    usage = stats.setdefault("usage", {})
    short = dshort(dlib)
    usage[short] = usage.get(short, 0) + 1
    try:
        json.dump(stats, open(STATS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except OSError:
        pass


def render_stats(lang: str) -> str:
    if not stats.get("patches"):
        return t("stats_empty", lang)
    top = sorted(stats.get("usage",{}).items(), key=lambda x: x[1], reverse=True)[:5]
    top_str = "\n".join(
        t("stats_row", lang, n=i+1, name=n, cnt=c)
        for i,(n,c) in enumerate(top)
    ) or "—"
    return t("stats_header", lang,
             patches=stats.get("patches",0),
             users=len(stats.get("users",[])),
             dylibs=len(get_dylibs()),
             top=top_str)


# ============================================================
# НАСТРОЙКИ
# ============================================================

def load_settings() -> None:
    global bot_settings
    try:
        bot_settings = json.load(open(SETTINGS_FILE, encoding="utf-8"))
    except Exception:
        bot_settings = {"appleid": "—", "channel": CHANNEL, "admin": "—"}


def save_settings() -> None:
    try:
        json.dump(bot_settings, open(SETTINGS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except OSError:
        pass


def render_settings(lang: str) -> str:
    return t("sett_header", lang,
             appleid=bot_settings.get("appleid","—"),
             channel=bot_settings.get("channel", CHANNEL),
             admin=bot_settings.get("admin","—"))


def settings_kb(lang: str) -> List:
    return [
        [Button.inline("\U0001f464 Apple ID",    b"set_appleid")],
        [Button.inline("\U0001f4e3 Channel",     b"set_channel")],
        [Button.inline("\U0001f511 Admin ID",    b"set_admin")],
        [Button.inline("\U0001f4ca Статистика",  b"do_stats")],
    ]


# ============================================================
# APP STORE (iTunes Search API)
# ============================================================

async def itunes_search(query: str, limit: int = 3) -> List[dict]:
    url    = "https://itunes.apple.com/search"
    params = {"term": query, "entity": "software", "limit": limit * 2, "country": "us"}
    try:
        timeout = aiohttp.ClientTimeout(total=ITUNES_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url, params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json(content_type=None)
                out  = []
                for item in data.get("results", [])[:limit]:
                    out.append({
                        "name":    item.get("trackName", "?"),
                        "version": item.get("version", "?"),
                        "bundle":  item.get("bundleId", ""),
                        "id":      item.get("trackId", 0),
                        "price":   item.get("formattedPrice", "Free"),
                        "genre":   item.get("primaryGenreName", ""),
                        "size":    item.get("fileSizeBytes", 0),
                    })
                return out
    except asyncio.TimeoutError:
        raise TimeoutError()
    except Exception as e:
        raise RuntimeError(str(e))


def app_list_kb(apps: List[dict], lang: str) -> List:
    rows = []
    for i, app in enumerate(apps):
        em = "\U0001f193" if "Free" in app.get("price","") else "\U0001f4b0"
        rows.append([Button.inline(
            f"{em} {app['name'][:25]}",
            f"app_{i}".encode()
        )])
    rows.append([Button.inline(t("cancel", lang), b"noop")])
    return rows


def app_detail_kb(idx: int, lang: str) -> List:
    return [
        [Button.inline(t("dl_btn",    lang), f"appdl_{idx}".encode())],
        [Button.inline(t("pick_dlib", lang), b"dp_0"),
         Button.inline(t("back",      lang), b"appback")],
    ]


async def do_appstore_search(event, uid: int, lang: str, query: str) -> None:
    msg = await event.reply(t("appstore_search", lang, query=query))
    try:
        apps = await itunes_search(query, 3)
    except TimeoutError:
        await msg.edit(t("appstore_timeout", lang, t=ITUNES_TIMEOUT))
        return
    except RuntimeError as e:
        await msg.edit(t("appstore_err", lang, error=str(e)))
        return

    if not apps:
        await msg.edit(t("appstore_none", lang, query=query))
        return

    user_state[uid] = {"app_results": apps, "app_query": query}

    lines = [t("appstore_results", lang, query=query), ""]
    for i, a in enumerate(apps, 1):
        em = "\U0001f193" if "Free" in a.get("price","") else "\U0001f4b0"
        lines.append(f"{em} **{a['name']}** v{a['version']} — {a['price']}")

    await msg.edit("\n".join(lines), buttons=app_list_kb(apps, lang))


# ============================================================
# ИНЖЕКТ
# ============================================================

async def inject_dylib(ipa_path: str, dylib_names: List[str], progress_cb=None) -> Tuple[bool, str]:
    tmp_dir: Optional[Path] = None
    try:
        tmp_dir = Path(tempfile.mkdtemp())
        ipa_dir = tmp_dir / "ipa"
        ipa_dir.mkdir()

        for dn in dylib_names:
            if not Path(dn).exists():
                return False, f"Dylib не найден: {dn}"
        if not Path(ipa_path).exists():
            return False, "IPA не найден"

        if progress_cb:
            await progress_cb("\U0001f4c2 Распаковка IPA...")
        try:
            with zipfile.ZipFile(ipa_path, "r") as zf:
                zf.extractall(ipa_dir)
        except zipfile.BadZipFile:
            return False, "Невалидный IPA (bad zip)"

        payload = ipa_dir / "Payload"
        if not payload.exists():
            return False, "Payload не найден"
        app_dirs = [p for p in payload.iterdir() if p.is_dir() and p.suffix == ".app"]
        if not app_dirs:
            app_dirs = [p for p in payload.iterdir() if p.is_dir()]
        if not app_dirs:
            return False, "App bundle не найден"

        app_dir = app_dirs[0]
        fw = app_dir / "Frameworks"
        fw.mkdir(exist_ok=True, parents=True)

        # Читаем данные из Info.plist
        app_name    = "App"
        app_version = "1.0"
        bundle_id   = ""
        min_os      = ""
        plist_path  = app_dir / "Info.plist"
        if plist_path.exists():
            try:
                import plistlib
                with open(plist_path, "rb") as pf:
                    plist = plistlib.load(pf)
                app_name    = plist.get("CFBundleName") or plist.get("CFBundleDisplayName") or app_name
                app_version = plist.get("CFBundleShortVersionString") or plist.get("CFBundleVersion") or app_version
                bundle_id   = plist.get("CFBundleIdentifier", "")
                min_os      = plist.get("MinimumOSVersion", "")
            except Exception:
                pass

        # Инжектируем все выбранные dylib по очереди
        for i, dn in enumerate(dylib_names, 1):
            if progress_cb:
                await progress_cb(
                    f"\U0001f489 [{i}/{len(dylib_names)}] {dshort(dn)} \u2192 {app_dir.name}..."
                )
            shutil.copy2(dn, fw / Path(dn).name)

        if progress_cb:
            await progress_cb("\U0001f4e6 Перепаковка IPA...")

        # Имя файла: AppName_voyagersipa.ipa
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in app_name)
        out       = f"{safe_name}_voyagersipa.ipa"
        base      = out[:-4]
        shutil.make_archive(base, "zip", ipa_dir)
        if not os.path.exists(base + ".zip"):
            return False, "Ошибка архивации"
        shutil.move(base + ".zip", out)
        return True, out, app_name, app_version, bundle_id, min_os

    except Exception as e:
        logger.error(f"inject_dylib: {e}", exc_info=True)
        return False, str(e)
    finally:
        if tmp_dir and tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass


# ============================================================
# КОНФИГ
# ============================================================

load_dotenv("VoyagerBot.env")
_api_id    = os.getenv("API_ID",    "")
_api_hash  = os.getenv("API_HASH",  "")
_bot_token = os.getenv("BOT_TOKEN", "")

if not all([_api_id, _api_hash, _bot_token]):
    logger.critical("Нет API_ID/API_HASH/BOT_TOKEN в VoyagerBot.env")
    sys.exit(1)
try:
    API_ID = int(_api_id)
except ValueError:
    logger.critical("API_ID должен быть числом")
    sys.exit(1)

client = TelegramClient(SESSION_NAME, API_ID, _api_hash)

# ============================================================
# КОМАНДЫ (/start, /help, ...)
# ============================================================

@client.on(events.NewMessage(pattern=r"^/start"))
async def cmd_start(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    await client.send_message(event.chat_id, t("welcome", lang), buttons=reply_kb(lang))


@client.on(events.NewMessage(pattern=r"^/help"))
async def cmd_help(event):
    await event.reply(t("help", get_lang(event.sender_id)))


@client.on(events.NewMessage(pattern=r"^/dylibs"))
async def cmd_dylibs(event):
    lang = get_lang(event.sender_id)
    d    = get_dylibs()
    tot  = max(1, (len(d) + DYLIB_PAGE_SIZE - 1) // DYLIB_PAGE_SIZE)
    await event.reply(t("dylib_header", lang, page=1, total=tot), buttons=dylib_kb(0))


@client.on(events.NewMessage(pattern=r"^/stats"))
async def cmd_stats(event):
    await event.reply(render_stats(get_lang(event.sender_id)))


@client.on(events.NewMessage(pattern=r"^/history"))
async def cmd_history(event):
    lang = get_lang(event.sender_id)
    await event.reply(t("hist_header", lang, count=len(history)) + render_hist(lang))


@client.on(events.NewMessage(pattern=r"^/settings"))
async def cmd_settings_cmd(event):
    lang = get_lang(event.sender_id)
    await event.reply(render_settings(lang), buttons=settings_kb(lang))


@client.on(events.NewMessage(pattern=r"^/search (.+)"))
async def cmd_search(event):
    uid   = event.sender_id
    lang  = get_lang(uid)
    query = event.pattern_match.group(1).strip()
    await do_appstore_search(event, uid, lang, query)


# ============================================================
# CALLBACK — INLINE КНОПКИ
# ============================================================

@client.on(events.CallbackQuery(data=b"noop"))
async def cb_noop(event):
    await event.answer()


@client.on(events.CallbackQuery(data=b"do_stats"))
async def cb_stats(event):
    await event.answer()
    await event.respond(render_stats(get_lang(event.sender_id)))


@client.on(events.CallbackQuery(data=b"appback"))
async def cb_appback(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    st   = user_state.get(uid, {})
    apps = st.get("app_results", [])
    if apps:
        lines = [t("appstore_results", lang, query=st.get("app_query","")), ""]
        for i, a in enumerate(apps, 1):
            em = "\U0001f193" if "Free" in a.get("price","") else "\U0001f4b0"
            lines.append(f"{em} **{a['name']}** v{a['version']} — {a['price']}")
        await event.edit("\n".join(lines), buttons=app_list_kb(apps, lang))
    else:
        await event.answer()


# ── Смена языка (ГЛАВНАЯ ФУНКЦИЯ — меняет весь интерфейс) ────────────────────

@client.on(events.CallbackQuery(func=lambda e: e.data in (b"setlang_ru", b"setlang_en")))
async def cb_set_lang(event):
    """
    Смена языка всего бота.
    - user_langs[uid] обновляется → все t() начнут возвращать новый язык
    - reply_kb(new_lang) отправляется → все кнопки под полем ввода обновляются
    - Все следующие сообщения и кнопки будут на новом языке
    """
    uid      = event.sender_id
    new_lang = "ru" if event.data == b"setlang_ru" else "en"
    old_lang = get_lang(uid)
    if new_lang == old_lang:
        await event.answer("Уже установлен!" if new_lang == "ru" else "Already set!")
        return
    user_langs[uid] = new_lang
    await event.answer()
    conf_key = "lang_ru" if new_lang == "ru" else "lang_en"
    # Отправляем сообщение с НОВОЙ клавиатурой — это и есть смена языка
    await client.send_message(event.chat_id, t(conf_key, new_lang), buttons=reply_kb(new_lang))
    logger.info(f"uid={uid} сменил язык: {old_lang} -> {new_lang}")


# ── Выбор dylib ───────────────────────────────────────────────────────────────

@client.on(events.CallbackQuery(func=lambda e: (
    e.data.startswith(b"dl_")
    and e.data not in (b"dl_done", b"dl_reset")
)))
async def cb_dylib_toggle(event):
    """Тап на dylib — переключает галочку (мультиселект)."""
    uid  = event.sender_id
    lang = get_lang(uid)
    name = event.data[3:].decode()

    if not os.path.exists(name):
        await event.answer("\u274c Файл не найден")
        return

    sel = user_dylib.setdefault(uid, [])
    if name in sel:
        sel.remove(name)
        await event.answer(f"\u2796 {dshort(name)}")
    else:
        sel.append(name)
        await event.answer(f"\u2705 {dshort(name)}")

    # Перерисовываем список с обновлёнными галочками
    d   = get_dylibs()
    tot = max(1, (len(d) + DYLIB_PAGE_SIZE - 1) // DYLIB_PAGE_SIZE)
    # Определяем текущую страницу из сообщения (если не можем — 0)
    try:
        cur_page = user_state.get(uid, {}).get("dylib_page", 0)
    except Exception:
        cur_page = 0

    sel_names = ", ".join(dshort(s) for s in sel) if sel else "—"
    header = (
        t("dylib_header", lang, page=cur_page+1, total=tot) +
        f"\n\n\u2705 Выбрано ({len(sel)}): {sel_names}"
    )
    await event.edit(header, buttons=dylib_kb(cur_page, d, sel))


@client.on(events.CallbackQuery(data=b"dl_done"))
async def cb_dylib_done(event):
    """Кнопка Готово — подтверждает выбор dylib."""
    uid  = event.sender_id
    lang = get_lang(uid)
    sel  = user_dylib.get(uid, [])

    if not sel:
        await event.answer("\u26a0\ufe0f Выбери хотя бы один dylib!")
        return

    names = "\n".join(f"  \u2705 {dshort(s)}" for s in sel)
    await event.answer("\u2705 Готово!")
    await event.edit(
        f"\u2705 **Выбрано dylib ({len(sel)}):**\n{names}\n\n"
        f"\U0001f4e6 Теперь отправь .ipa файл\n"
        f"\U0001f517 или пришли прямую ссылку на IPA",
        buttons=[
            [Button.inline("\U0001f4da Изменить выбор", b"dp_0")],
        ]
    )


@client.on(events.CallbackQuery(data=b"dl_reset"))
async def cb_dylib_reset(event):
    """Кнопка Сбросить — снимает все галочки."""
    uid  = event.sender_id
    lang = get_lang(uid)
    user_dylib[uid] = []

    d   = get_dylibs()
    tot = max(1, (len(d) + DYLIB_PAGE_SIZE - 1) // DYLIB_PAGE_SIZE)
    cur = user_state.get(uid, {}).get("dylib_page", 0)
    await event.answer("\U0001f5d1 Сброшено")
    await event.edit(
        t("dylib_header", lang, page=cur+1, total=tot),
        buttons=dylib_kb(cur, d, [])
    )


# ── Пагинация dylib ───────────────────────────────────────────────────────────

@client.on(events.CallbackQuery(func=lambda e: e.data.startswith(b"dp_")))
async def cb_dylib_page(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    try:
        page = int(event.data[3:].decode())
    except ValueError:
        page = 0
    user_state.setdefault(uid, {})["dylib_page"] = page
    d   = get_dylibs()
    sel = user_dylib.get(uid, [])
    tot = max(1, (len(d) + DYLIB_PAGE_SIZE - 1) // DYLIB_PAGE_SIZE)
    sel_names = ", ".join(dshort(s) for s in sel) if sel else "—"
    header = (
        t("dylib_header", lang, page=page+1, total=tot) +
        f"\n\n\u2705 Выбрано ({len(sel)}): {sel_names}"
    )
    await event.edit(header, buttons=dylib_kb(page, d, sel))


# ── App Store детали ──────────────────────────────────────────────────────────

@client.on(events.CallbackQuery(func=lambda e: e.data.startswith(b"app_")))
async def cb_app_detail(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    try:
        idx = int(event.data[4:].decode())
    except ValueError:
        await event.answer(); return
    apps = user_state.get(uid, {}).get("app_results", [])
    if idx >= len(apps):
        await event.answer("Not found"); return
    a    = apps[idx]
    size_str = fmt_bytes(int(a.get("size",0))) if a.get("size") else "?"
    text = (
        f"\U0001f4f1 **{a['name']}**\n\n"
        f"\U0001f3f7 v{a['version']}\n"
        f"\U0001f3ae {a['genre']}\n"
        f"\U0001f4b0 {a['price']}\n"
        f"\U0001f4e6 {size_str}\n"
        f"\U0001f511 `{a.get('bundle','?')}`"
    )
    user_state.setdefault(uid, {})["sel_idx"] = idx
    await event.edit(text, buttons=app_detail_kb(idx, lang))


@client.on(events.CallbackQuery(func=lambda e: e.data.startswith(b"appdl_")))
async def cb_app_dl(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    try:
        idx = int(event.data[6:].decode())
    except ValueError:
        await event.answer(); return
    apps = user_state.get(uid, {}).get("app_results", [])
    if idx >= len(apps):
        await event.answer("Not found"); return
    name = apps[idx]["name"]
    ch   = bot_settings.get("channel", CHANNEL)
    await event.edit(
        t("no_ipa_link", lang, name=name, channel=ch),
        buttons=[
            [Button.inline(f"\U0001f4e3 {ch}", b"noop")],
            [Button.inline(t("pick_dlib", lang), b"dp_0"),
             Button.inline(t("back",      lang), b"appback")],
        ]
    )


# ── Настройки ─────────────────────────────────────────────────────────────────

@client.on(events.CallbackQuery(func=lambda e: e.data in (b"set_appleid", b"set_channel", b"set_admin")))
async def cb_settings_input(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    key  = event.data.decode()[4:]   # "appleid" / "channel" / "admin"
    user_state[uid] = {"awaiting": f"sett_{key}"}
    await event.answer()
    await event.respond(t(f"sett_{key}", lang))


# ============================================================
# REPLY KEYBOARD — обработчик нажатий кнопок (Button.text)
# ============================================================

@client.on(events.NewMessage(func=lambda e: (
    not e.file
    and bool(getattr(e, "message", None))
    and bool(getattr(e.message, "text", None))
    and not e.message.text.startswith("/")
    and _match_btn(e.message.text.strip()) is not None
)))
async def handle_reply_kb(event):
    """
    Центральный обработчик всех кнопок reply keyboard.
    Все кнопки работают на ТЕКУЩЕМ ЯЗЫКЕ пользователя.
    """
    uid  = event.sender_id
    lang = get_lang(uid)
    key  = _match_btn(event.message.text.strip())

    if key == "btn_upload":
        dlib = user_dylib.get(uid)
        if dlib:
            await event.reply(t("send_ipa", lang, dlib=dshort(dlib)))
        else:
            await event.reply(t("no_dlib", lang))

    elif key == "btn_appstore":
        user_state[uid] = {"awaiting": "appstore_query"}
        await event.reply(t("appstore_prompt", lang))

    elif key == "btn_dylibs":
        dlibs = get_dylibs()
        if not dlibs:
            await event.reply(t("no_dylibs_folder", lang) + "\n\n" + DYLIB_SOURCES[lang])
            return
        sel = user_dylib.get(uid, [])
        tot = max(1, (len(dlibs) + DYLIB_PAGE_SIZE - 1) // DYLIB_PAGE_SIZE)
        sel_names = ", ".join(dshort(s) for s in sel) if sel else "—"
        header = (
            t("dylib_header", lang, page=1, total=tot) +
            f"\n\n\u2705 Выбрано ({len(sel)}): {sel_names}"
        )
        user_state.setdefault(uid, {})["dylib_page"] = 0
        await event.reply(header, buttons=dylib_kb(0, dlibs, sel))

    elif key == "btn_lang":
        # Показываем выбор языка
        await event.reply(
            t("lang_prompt", lang),
            buttons=[
                [Button.inline("\U0001f1f7\U0001f1fa Русский", b"setlang_ru"),
                 Button.inline("\U0001f1fa\U0001f1f8 English",  b"setlang_en")],
            ]
        )

    elif key == "btn_history":
        await event.reply(t("hist_header", lang, count=len(history)) + render_hist(lang))

    elif key == "btn_settings":
        await event.reply(render_settings(lang), buttons=settings_kb(lang))

    elif key == "btn_channel":
        ch = bot_settings.get("channel", CHANNEL)
        await event.reply(t("channel_text", lang, channel=ch))


# ============================================================
# ТЕКСТОВЫЙ ВВОД (поиск, настройки)
# ============================================================

@client.on(events.NewMessage(func=lambda e: (
    not e.file
    and bool(getattr(e, "message", None))
    and bool(getattr(e.message, "text", None))
    and not e.message.text.startswith("/")
    and _match_btn(e.message.text.strip()) is None
)))
async def handle_text_input(event):
    uid  = event.sender_id
    lang = get_lang(uid)
    text = event.message.text.strip()
    aw   = user_state.get(uid, {}).get("awaiting", "")

    if aw == "appstore_query":
        user_state.pop(uid, None)
        await do_appstore_search(event, uid, lang, text)

    elif aw == "sett_appleid":
        if "@" in text and "." in text:
            bot_settings["appleid"] = text
            save_settings()
            user_state.pop(uid, None)
            await event.reply(t("sett_saved", lang, key="AppleID", val=text))
        else:
            await event.reply(t("sett_invalid", lang))

    elif aw == "sett_channel":
        if text.startswith("-100") or text.startswith("@"):
            bot_settings["channel"] = text
            save_settings()
            user_state.pop(uid, None)
            await event.reply(t("sett_saved", lang, key="Channel", val=text))
        else:
            await event.reply(t("sett_invalid", lang))

    elif aw == "sett_admin":
        if text.lstrip("-").isdigit():
            bot_settings["admin"] = text
            save_settings()
            user_state.pop(uid, None)
            await event.reply(t("sett_saved", lang, key="Admin", val=text))
        else:
            await event.reply(t("sett_invalid", lang))


# ============================================================
# IPA ФАЙЛ → ИНЖЕКТ
# ============================================================

async def _run_injection(event, uid: int, lang: str, ipa_path: str, ipa_label: str) -> None:
    """Общая логика инжекта — используется и для файла и для URL."""
    sel = user_dylib.get(uid, [])
    if not sel:
        await event.reply(t("no_dlib", lang), buttons=dylib_kb(0))
        return

    shorts = " + ".join(dshort(s) for s in sel)
    status = await event.reply(t("patching", lang, dlib=shorts))

    async def patch_hook(msg: str) -> None:
        try:
            await status.edit(t("patch_step", lang, step=msg))
        except Exception:
            pass

    ok, *rest = await inject_dylib(ipa_path, sel, progress_cb=patch_hook)

    if ok:
        result      = rest[0]
        app_name    = rest[1] if len(rest) > 1 else "App"
        app_version = rest[2] if len(rest) > 2 else "1.0"
        bundle_id   = rest[3] if len(rest) > 3 else ""
        min_os      = rest[4] if len(rest) > 4 else ""
        fname = os.path.basename(result)

        # Пытаемся найти ссылку на App Store по bundle_id
        store_link = ""
        if bundle_id:
            store_link = f"https://apps.apple.com/app/id"  # без track_id — просто красиво
        # Запрашиваем track_id из iTunes если есть bundle_id
        if bundle_id:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        "https://itunes.apple.com/lookup",
                        params={"bundleId": bundle_id, "limit": 1},
                        timeout=aiohttp.ClientTimeout(total=8)
                    ) as r:
                        if r.status == 200:
                            data = await r.json(content_type=None)
                            results = data.get("results", [])
                            if results:
                                track_id = results[0].get("trackId", "")
                                developer = results[0].get("artistName", "")
                                if track_id:
                                    store_link = f"https://apps.apple.com/app/id{track_id}"
            except Exception:
                developer = ""
        else:
            developer = ""

        tweak_label = shorts

        if lang == "ru":
            extra_header = "Дополнительная информация ℹ️"
        else:
            extra_header = "Additional Information ℹ️"

        lines = []
        if store_link:
            lines.append(f'📱 <a href="{store_link}">{app_name}</a>')
        else:
            lines.append(f"📱 <b>{app_name}</b>")
        lines.append(f"💊 Tweak: {tweak_label}")
        lines.append(f"🔖 Version: {app_version}")
        if lang == "ru":
            lines.append("✅ Пропатчено ✓")
        else:
            lines.append("✅ Patched ✓")
        lines.append(f"📣 @voyagersipa")
        lines.append("")
        lines.append(f"<b>{extra_header}</b>")
        if min_os:
            if lang == "ru":
                lines.append(f"📌 Мин. iOS: {min_os}")
            else:
                lines.append(f"📌 Min OS Version: {min_os}")
        if bundle_id:
            lines.append(f"🔑 Bundle ID: <code>{bundle_id}</code>")
        if developer:
            if lang == "ru":
                lines.append(f"👨‍💻 Разработчик: {developer}")
            else:
                lines.append(f"👨‍💻 Developer: {developer}")

        caption = "\n".join(lines)

        # Удаляем статусное сообщение — весь результат будет в caption файла
        try:
            await status.delete()
        except Exception:
            pass

        try:
            await client.send_file(
                event.chat_id, result,
                caption=caption,
                force_document=True,
                parse_mode="html"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}")
            await event.reply(t("patch_err", lang, error=f"Ошибка отправки: {e}"))
            return
        ch = bot_settings.get("channel", os.getenv("CHANNEL_ID", ""))
        if ch and ch != "—":
            try:
                await client.send_file(ch, result, caption=caption, force_document=True, parse_mode="html")
            except Exception as e:
                logger.warning(f"Канал отправка: {e}")
        save_hist({"dlib": sel, "ipa": ipa_label,
                   "time": time.strftime("%d.%m %H:%M"), "uid": uid})
        for d in sel:
            record_stats(uid, d)
        # Удаляем файл ТОЛЬКО после успешной отправки
        if os.path.exists(result):
            try:
                os.remove(result)
            except OSError:
                pass
    else:
        await status.edit(t("patch_err", lang, error=rest[0]))


@client.on(events.NewMessage(func=lambda e: e.file is not None))
async def handle_ipa(event):
    """Получен .ipa файл — скачиваем с прогрессом, затем инжектируем."""
    fname = getattr(event.file, "name", "") or ""
    if not fname.lower().endswith(".ipa"):
        return

    uid  = event.sender_id
    lang = get_lang(uid)
    sel  = user_dylib.get(uid, [])

    if not sel:
        await event.reply(t("no_dlib", lang), buttons=dylib_kb(0))
        return

    status   = await event.reply(t("dl_progress", lang, name=fname, pct=0, recv="0Б", total="?"))
    temp_ipa = f"tmp_{uid}_{int(time.time())}.ipa"
    last_upd = [0.0]

    async def dl_hook(recv: int, total: int) -> None:
        now = time.time()
        if now - last_upd[0] < 1.5:
            return
        last_upd[0] = now
        pct = int(recv / total * 100) if total else 0
        try:
            await status.edit(t("dl_progress", lang, name=fname, pct=pct,
                                recv=fmt_bytes(recv),
                                total=fmt_bytes(total) if total else "?"))
        except Exception:
            pass

    try:
        await event.download_media(temp_ipa, progress_callback=dl_hook)
    except Exception as e:
        await status.edit(t("patch_err", lang, error=f"Скачивание: {e}"))
        return

    await status.delete()
    await _run_injection(event, uid, lang, temp_ipa, fname)

    if os.path.exists(temp_ipa):
        try:
            os.remove(temp_ipa)
        except OSError:
            pass


@client.on(events.NewMessage(func=lambda e: (
    not e.file
    and bool(getattr(e, "message", None))
    and bool(getattr(e.message, "text", None))
    and e.message.text.strip().lower().startswith("http")
    and ".ipa" in e.message.text.lower()
    and _match_btn(e.message.text.strip()) is None
)))
async def handle_ipa_url(event):
    """
    Прямая ссылка на IPA (http://...*.ipa).
    Скачиваем через aiohttp → инжектируем.
    """
    uid  = event.sender_id
    lang = get_lang(uid)
    url  = event.message.text.strip().split()[0]  # берём первый токен (URL)
    sel  = user_dylib.get(uid, [])

    if not sel:
        await event.reply(t("no_dlib", lang), buttons=dylib_kb(0))
        return

    fname    = url.split("/")[-1].split("?")[0] or "app.ipa"
    temp_ipa = f"tmp_{uid}_{int(time.time())}.ipa"
    status   = await event.reply(
        t("dl_progress", lang, name=fname, pct=0, recv="0Б", total="?")
    )

    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await status.edit(t("patch_err", lang,
                                        error=f"HTTP {resp.status}"))
                    return
                total_size = int(resp.headers.get("Content-Length", 0))
                received   = 0
                last_upd   = 0.0
                with open(temp_ipa, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
                        received += len(chunk)
                        now = time.time()
                        if now - last_upd >= 1.5:
                            last_upd = now
                            pct = int(received / total_size * 100) if total_size else 0
                            try:
                                await status.edit(t(
                                    "dl_progress", lang, name=fname, pct=pct,
                                    recv=fmt_bytes(received),
                                    total=fmt_bytes(total_size) if total_size else "?"
                                ))
                            except Exception:
                                pass
    except asyncio.TimeoutError:
        await status.edit(t("patch_err", lang, error="Timeout при скачивании"))
        return
    except Exception as e:
        await status.edit(t("patch_err", lang, error=str(e)))
        return

    await status.delete()
    await _run_injection(event, uid, lang, temp_ipa, fname)

    if os.path.exists(temp_ipa):
        try:
            os.remove(temp_ipa)
        except OSError:
            pass


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    load_history()
    load_stats()
    load_settings()

    dlibs = get_dylibs()
    logger.info(f"Dylib в папке: {len(dlibs)}")

    await client.start(bot_token=_bot_token)

    try:
        await client(SetBotCommandsRequest(
            scope=BotCommandScopeDefault(),
            lang_code="",
            commands=[
                BotCommand("start",    "\U0001f3e0 Главное меню"),
                BotCommand("dylibs",   "\U0001f4da Список dylib"),
                BotCommand("search",   "\U0001f50d Поиск App Store"),
                BotCommand("history",  "\U0001f4cb История патчей"),
                BotCommand("stats",    "\U0001f4ca Статистика"),
                BotCommand("settings", "\u2699 Настройки"),
                BotCommand("help",     "\u2753 Помощь"),
            ]
        ))
        logger.info("Команды зарегистрированы")
    except Exception as e:
        logger.warning(f"set_bot_commands: {e}")

    logger.info(f"\U0001f680 Voyager Dylib Bot v{VERSION} запущен! {CHANNEL}")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())