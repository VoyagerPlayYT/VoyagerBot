#!/usr/bin/env python3
"""
🔄 Синхронизирует пресеты в docs/ для GitHub Pages
"""

import json
from pathlib import Path

presets_path = Path("storage/presets")
docs_path = Path("docs")

docs_path.mkdir(exist_ok=True)

presets = {}

if presets_path.exists():
    for file in presets_path.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                presets[file.stem] = {
                    "dylibs": data.get("dylibs", []),
                    "count": len(data.get("dylibs", []))
                }
        except Exception as e:
            print(f"⚠️ {e}")

output = docs_path / "presets.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(presets, f, ensure_ascii=False, indent=2)

print(f"✅ Synced {len(presets)} presets")
