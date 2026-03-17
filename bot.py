import os
import asyncio
import zipfile
import shutil
import struct
import logging
import subprocess
from pathlib import Path
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID  = os.environ.get("CHANNEL_ID", "@VoyagersIPA")
ADMIN_ID    = int(os.environ.get("ADMIN_ID", "0"))

# ── Binary patcher ────────────────────────────────────────

MH_MAGIC_64  = 0xFEEDFACF
MH_CIGAM_64  = 0xCFFAEDFE
FAT_MAGIC    = 0xCAFEBABE
FAT_CIGAM    = 0xBEBAFECA

PATCH_PATTERNS = [
    # StoreKit receipt check patterns
    (b'\x00\x00\x94\x1a\x00\x00\x00\x0a', b'\x00\x00\x94\x1a\x00\x00\x20\x1a'),
    # isPurchased / isSubscribed true patches
    (b'\x00\x00\x80\x52\xc0\x03\x5f\xd6', b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'),
    # canMakePayments bypass
    (b'\xe0\x03\x1f\xaa\xc0\x03\x5f\xd6', b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'),
]

BOOL_FALSE_PATTERNS = [
    b'\x00\x00\x80\x52\xc0\x03\x5f\xd6',  # MOV W0, #0 ; RET
]
BOOL_TRUE_PATCH = b'\x20\x00\x80\x52\xc0\x03\x5f\xd6'  # MOV W0, #1 ; RET

PREMIUM_STRINGS = [
    b'isPremium', b'isPro', b'isSubscribed', b'isPurchased',
    b'isUnlocked', b'hasPremium', b'hasSubscription', b'isVIP',
    b'premiumUser', b'proUser', b'subscribedUser', b'paidUser',
    b'isActive', b'hasAccess', b'isMember', b'isFullVersion',
]

AD_STRINGS = [
    b'showAd', b'showInterstitial', b'showBanner', b'showRewarded',
    b'loadAd', b'loadInterstitial', b'requestAd', b'displayAd',
    b'GADInterstitial', b'GADBannerView', b'MPInterstitial',
    b'UnityAds', b'AppLovin', b'ironSource', b'Vungle',
]

def read_uint32(data, offset, little_endian=True):
    fmt = '<I' if little_endian else '>I'
    return struct.unpack_from(fmt, data, offset)[0]

def patch_binary(binary_path: Path) -> tuple[int, int]:
    """Patch a Mach-O binary. Returns (premium_patches, ad_patches)."""
    data = bytearray(binary_path.read_bytes())
    magic = struct.unpack_from('>I', data, 0)[0]

    offsets = []

    if magic in (MH_MAGIC_64, MH_CIGAM_64):
        offsets = [0]
    elif magic in (FAT_MAGIC, FAT_CIGAM):
        le = (magic == FAT_CIGAM)
        narch = read_uint32(data, 4, little_endian=not le)
        for i in range(narch):
            base = 8 + i * 20
            off  = read_uint32(data, base + 8, little_endian=not le)
            offsets.append(off)

    premium_count = 0
    ad_count      = 0

    for arch_off in offsets:
        arch_data = data[arch_off:]

        # 1) Generic bool-return patches
        for pattern in BOOL_FALSE_PATTERNS:
            idx = 0
            while True:
                pos = arch_data.find(pattern, idx)
                if pos == -1: break
                # Check surrounding bytes for premium-related context
                context_start = max(0, pos - 256)
                context = arch_data[context_start:pos]
                for ps in PREMIUM_STRINGS:
                    if ps.lower() in bytes(context).lower():
                        data[arch_off + pos:arch_off + pos + len(BOOL_TRUE_PATCH)] = BOOL_TRUE_PATCH
                        premium_count += 1
                        break
                idx = pos + 1

        # 2) Direct StoreKit patterns
        for orig, patched in PATCH_PATTERNS:
            idx = 0
            while True:
                pos = bytes(data).find(orig, arch_off + idx)
                if pos == -1: break
                data[pos:pos + len(patched)] = patched
                premium_count += 1
                idx = pos - arch_off + 1

        # 3) Ad method NOP-out (replace first 4 bytes with RET)
        RET_INSTR = b'\xc0\x03\x5f\xd6'
        for ad_str in AD_STRINGS:
            idx = 0
            while True:
                pos = bytes(data).find(ad_str, arch_off + idx)
                if pos == -1: break
                # Find nearest function prologue before this string ref
                # Simple heuristic: look for STP x29, x30 pattern
                search_back = bytes(data[max(arch_off, pos-512):pos])
                prologue = search_back.rfind(b'\xfd\x7b\xbf\xa9')
                if prologue != -1:
                    func_start = max(arch_off, pos-512) + prologue
                    data[func_start:func_start+4] = RET_INSTR
                    ad_count += 1
                idx = pos - arch_off + 1

    binary_path.write_bytes(data)
    return premium_count, ad_count

def get_app_info(ipa_path: Path) -> dict:
    """Extract app name, bundle ID, version from IPA."""
    info = {"name": "Unknown", "bundle_id": "unknown", "version": "?.?.?", "min_ios": "?"}
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_files = [f for f in z.namelist()
                          if f.endswith('Info.plist') and f.count('/') == 2]
            if not plist_files:
                plist_files = [f for f in z.namelist() if f.endswith('Info.plist')]
            if plist_files:
                plist_data = z.read(plist_files[0])
                # Parse with plutil
                tmp = Path('/tmp/info_tmp.plist')
                tmp.write_bytes(plist_data)
                try:
                    result = subprocess.run(
                        ['plutil', '-convert', 'json', '-o', '-', str(tmp)],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        import json
                        d = json.loads(result.stdout)
                        info["name"]      = d.get("CFBundleDisplayName") or d.get("CFBundleName", "Unknown")
                        info["bundle_id"] = d.get("CFBundleIdentifier", "unknown")
                        info["version"]   = d.get("CFBundleShortVersionString", "?.?.?")
                        info["min_ios"]   = d.get("MinimumOSVersion", "?")
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"get_app_info error: {e}")
    return info

def patch_ipa(ipa_path: Path, work_dir: Path) -> tuple[Path, dict, int, int]:
    """Unzip IPA, patch all binaries, repack. Returns patched IPA path."""
    extract_dir = work_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    info = get_app_info(ipa_path)

    # Unzip
    with zipfile.ZipFile(ipa_path, 'r') as z:
        z.extractall(extract_dir)

    # Find all Mach-O binaries
    payload = extract_dir / "Payload"
    total_premium = 0
    total_ads     = 0

    for app_dir in payload.iterdir():
        if not app_dir.name.endswith('.app'):
            continue
        # Main binary
        main_bin = app_dir / app_dir.stem
        if main_bin.exists() and main_bin.is_file():
            p, a = patch_binary(main_bin)
            total_premium += p
            total_ads     += a
            logger.info(f"Patched {main_bin.name}: {p} premium, {a} ad patches")

        # Frameworks
        frameworks = app_dir / "Frameworks"
        if frameworks.exists():
            for fw in frameworks.iterdir():
                if fw.suffix in ('.dylib', '.framework'):
                    bin_path = fw if fw.suffix == '.dylib' else fw / fw.stem
                    if bin_path.exists() and bin_path.is_file():
                        try:
                            p, a = patch_binary(bin_path)
                            total_premium += p
                            total_ads     += a
                        except Exception:
                            pass

    # Repack
    out_name = f"{info['name']}-v{info['version']}-voyagersipa.ipa"
    out_path  = work_dir / out_name

    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for file in extract_dir.rglob('*'):
            if file.is_file():
                zout.write(file, file.relative_to(extract_dir))

    return out_path, info, total_premium, total_ads

# ── Telegram handlers ─────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *VoyagersPatch Bot*\n\n"
        "Отправь мне `.ipa` файл — я пропатчу его и выложу в канал @VoyagersIPA\n\n"
        "• Premium Unlocked\n"
        "• Pro Unlocked\n"
        "• No Ads\n\n"
        "_Только для iOS IPA файлов_",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    doc  = update.message.document

    # Admin check
    if ADMIN_ID and user.id != ADMIN_ID:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if not doc.file_name.endswith('.ipa'):
        await update.message.reply_text("❌ Нужен `.ipa` файл!")
        return

    if doc.file_size > 500 * 1024 * 1024:
        await update.message.reply_text("❌ Файл слишком большой (макс 500MB)")
        return

    status_msg = await update.message.reply_text("⏳ Скачиваю IPA...")

    work_dir = Path(f"/tmp/voyager_{update.message.message_id}")
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Download
        file = await ctx.bot.get_file(doc.file_id)
        ipa_path = work_dir / doc.file_name
        await file.download_to_drive(ipa_path)

        await status_msg.edit_text("🔧 Патчу бинарник...")

        # Patch
        out_ipa, info, premium_patches, ad_patches = patch_ipa(ipa_path, work_dir)

        if premium_patches == 0 and ad_patches == 0:
            await status_msg.edit_text(
                "⚠️ Патчи не применились — возможно приложение уже пропатчено "
                "или использует серверную проверку.\n\nОтправляю как есть..."
            )
        else:
            await status_msg.edit_text(
                f"✅ Пропатчено!\n"
                f"• Premium патчей: {premium_patches}\n"
                f"• Ad патчей: {ad_patches}\n\n"
                f"📤 Отправляю в канал..."
            )

        # Caption for channel
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

        # Send to channel
        with open(out_ipa, 'rb') as f:
            await ctx.bot.send_document(
                chat_id=CHANNEL_ID,
                document=f,
                filename=out_ipa.name,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )

        await status_msg.edit_text(
            f"✅ *Готово!*\n\n"
            f"📱 {info['name']} v{info['version']}\n"
            f"• Premium патчей: {premium_patches}\n"
            f"• Ad патчей: {ad_patches}\n\n"
            f"Опубликовано в {CHANNEL_ID}",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle direct IPA URL links."""
    user = update.effective_user
    if ADMIN_ID and user.id != ADMIN_ID:
        return

    text = update.message.text.strip()
    if not (text.startswith('http') and '.ipa' in text):
        return

    status_msg = await update.message.reply_text("⏳ Скачиваю по ссылке...")
    work_dir = Path(f"/tmp/voyager_url_{update.message.message_id}")
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        import aiohttp
        ipa_path = work_dir / "app.ipa"

        async with aiohttp.ClientSession() as session:
            async with session.get(text) as resp:
                if resp.status != 200:
                    await status_msg.edit_text(f"❌ Не удалось скачать: HTTP {resp.status}")
                    return
                with open(ipa_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        f.write(chunk)

        await status_msg.edit_text("🔧 Патчу бинарник...")
        out_ipa, info, premium_patches, ad_patches = patch_ipa(ipa_path, work_dir)

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

        with open(out_ipa, 'rb') as f:
            await ctx.bot.send_document(
                chat_id=CHANNEL_ID,
                document=f,
                filename=out_ipa.name,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )

        await status_msg.edit_text(
            f"✅ *Готово!* Опубликовано в {CHANNEL_ID}\n"
            f"📱 {info['name']} v{info['version']}\n"
            f"• Патчей: {premium_patches + ad_patches}",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"URL error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    logger.info("VoyagersBot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
