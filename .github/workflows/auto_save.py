#!/usr/bin/env python3
"""
Auto-save скрипт для GitHub Actions
Сохраняет все данные из памяти бота в файлы
"""

import json
import os
from pathlib import Path
from datetime import datetime

def auto_save():
    """Автосохранение всех данных."""
    
    storage_path = Path("storage")
    storage_path.mkdir(exist_ok=True)
    
    # Пример: сохранение статистики
    stats = {
        "last_save": datetime.now().isoformat(),
        "status": "✅ Active",
        "files": len(list(storage_path.glob("**/*.json"))),
    }
    
    stats_file = storage_path / "stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Auto-save completed at {datetime.now()}")
    print(f"📊 Files: {stats['files']}")

if __name__ == "__main__":
    auto_save()
