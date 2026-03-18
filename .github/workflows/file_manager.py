#!/usr/bin/env python3
"""
Помощник для работы с файлами в workflows
"""

import json
from pathlib import Path
from datetime import datetime

class FileManager:
    def __init__(self):
        self.storage = Path("storage")
        self.storage.mkdir(exist_ok=True)

    def save_config(self, user_id: int, dylibs: list):
        """Сохраняет конфиг."""
        config = {
            "user_id": user_id,
            "dylibs": dylibs,
            "created_at": datetime.now().isoformat(),
        }
        
        file = self.storage / f"config_{user_id}_{int(datetime.now().timestamp())}.json"
        with open(file, "w") as f:
            json.dump(config, f, indent=2)
        
        return file

    def save_preset(self, name: str, dylibs: list):
        """Сохраняет пресет."""
        presets_dir = self.storage / "presets"
        presets_dir.mkdir(exist_ok=True)
        
        preset = {
            "name": name,
            "dylibs": dylibs,
            "created_at": datetime.now().isoformat(),
        }
        
        file = presets_dir / f"{name}.json"
        with open(file, "w", encoding="utf-8") as f:
            json.dump(preset, f, ensure_ascii=False, indent=2)
        
        return file

    def load_presets(self) -> dict:
        """Загружает все пресеты."""
        presets_dir = self.storage / "presets"
        presets = {}
        
        if presets_dir.exists():
            for file in presets_dir.glob("*.json"):
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    presets[file.stem] = data.get("dylibs", [])
        
        return presets
