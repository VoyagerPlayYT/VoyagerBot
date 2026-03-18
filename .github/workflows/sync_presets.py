#!/usr/bin/env python3
"""
🔄 Полная синхронизация пресетов
Читает presets.json из корня → сохраняет в storage/presets/
Затем копирует в docs/presets.json для GitHub Pages
"""

import json
from pathlib import Path

# ════════════════════════════════════════════════════════════════
# 1️⃣ ЧИТАЕМ presets.json ИЗ КОРНЯ
# ════════════════════════════════════════════════════════════════

root_presets_file = Path("presets.json")
presets_data = {}

if root_presets_file.exists():
    try:
        with open(root_presets_file, "r", encoding="utf-8") as f:
            presets_data = json.load(f)
        print(f"📖 Read {len(presets_data)} presets from presets.json")
    except Exception as e:
        print(f"❌ Error reading presets.json: {e}")
else:
    print("⚠️ presets.json not found in root")

# ════════════════════════════════════════════════════════════════
# 2️⃣ СОХРАНЯЕМ В storage/presets/
# ════════════════════════════════════════════════════════════════

storage_presets_dir = Path("storage/presets")
storage_presets_dir.mkdir(parents=True, exist_ok=True)

# Получаем существующие файлы
existing_files = set(f.stem for f in storage_presets_dir.glob("*.json"))

for preset_name, preset_data in presets_data.items():
    preset_file = storage_presets_dir / f"{preset_name}.json"
    
    # Проверяем, существует ли уже
    if preset_name in existing_files:
        print(f"  ✅ Keeping existing: {preset_name}.json")
    else:
        print(f"  ✨ Creating new: {preset_name}.json")
    
    # Сохраняем (перезаписываем или создаём)
    with open(preset_file, "w", encoding="utf-8") as f:
        json.dump({
            "name": preset_data.get("name", preset_name),
            "dylibs": preset_data.get("dylibs", []),
            "created_at": preset_data.get("created_at", ""),
            "id": preset_data.get("id", ""),
        }, f, ensure_ascii=False, indent=2)

print(f"💾 Saved {len(presets_data)} presets to storage/presets/")

# ════════════════════════════════════════════════════════════════
# 3️⃣ КОПИРУЕМ В docs/presets.json ДЛЯ GITHUB PAGES
# ════════════════════════════════════════════════════════════════

docs_path = Path("docs")
docs_path.mkdir(exist_ok=True)

# Читаем из storage/presets/ и преобразуем для веб-интерфейса
web_presets = {}

for file in storage_presets_dir.glob("*.json"):
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            web_presets[file.stem] = {
                "dylibs": data.get("dylibs", []),
                "count": len(data.get("dylibs", [])),
                "created_at": data.get("created_at", ""),
            }
            print(f"  📦 Added to web: {file.stem} ({len(data.get('dylibs', []))} dylib)")
    except Exception as e:
        print(f"  ❌ Error: {e}")

# Сохраняем для веб-интерфейса
output_file = docs_path / "presets.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(web_presets, f, ensure_ascii=False, indent=2)

print(f"🌐 Synced {len(web_presets)} presets to docs/presets.json")
print(f"✅ Sync complete!")
