#!/usr/bin/env python3
"""
🔄 Auto-save скрипт
Сохраняет файлы и статистику
"""

import json
from pathlib import Path
from datetime import datetime

# Создаём папки
Path("storage").mkdir(exist_ok=True)
Path("storage/configs").mkdir(exist_ok=True)
Path("storage/presets").mkdir(exist_ok=True)
Path("storage/users").mkdir(exist_ok=True)

# Сохраняем статистику
stats = {
    "last_auto_save": datetime.now().isoformat(),
    "status": "✅ Active",
    "total_files": len(list(Path("storage").glob("**/*.json"))),
}

with open("storage/stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"✅ Auto-save: {stats['total_files']} files")
