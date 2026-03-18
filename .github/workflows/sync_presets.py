#!/usr/bin/env python3
"""
🔄 Синхронизирует пресеты в docs/ для GitHub Pages
"""

import json
from pathlib import Path

presets_path = Path("storage/presets")
docs_path = Path("docs")

# Создаём docs если не существует
docs_path.mkdir(exist_ok=True)

presets = {}

print(f"📁 Checking presets at: {presets_path.absolute()}")
print(f"📁 Output to: {docs_path.absolute()}")

if presets_path.exists():
    files = list(presets_path.glob("*.json"))
    print(f"📄 Found {len(files)} preset files")
    
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                presets[file.stem] = {
                    "dylibs": data.get("dylibs", []),
                    "count": len(data.get("dylibs", []))
                }
                print(f"  ✅ {file.stem}: {len(data.get('dylibs', []))} dylib")
        except Exception as e:
            print(f"  ❌ Error: {e}")
else:
    print("⚠️ storage/presets not found!")

# Сохраняем в docs/presets.json
output_file = docs_path / "presets.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(presets, f, ensure_ascii=False, indent=2)

print(f"✅ Synced {len(presets)} presets to {output_file}")
