"""
Менеджер файлов — сохранение конфигов и пресетов
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

class FileManager:
    def __init__(self, base_path: str = "storage"):
        self.base_path = Path(base_path)
        self.configs_path = self.base_path / "configs"
        self.presets_path = self.base_path / "presets"
        self.users_path = self.base_path / "users"
        self.backup_path = self.base_path / "backups"
        
        # Создаём директории
        for path in [self.configs_path, self.presets_path, self.users_path, self.backup_path]:
            path.mkdir(parents=True, exist_ok=True)

    # ════════════════════════════════════════════════════════════════
    # КОНФИГИ
    # ════════════════════════════════════════════════════════════════

    def save_config(self, user_id: int, dylibs: List[str], config_name: str = "default") -> str:
        """
        Сохраняет конфиг dylib в файл.
        Возвращает путь к файлу.
        """
        config_data = {
            "user_id": user_id,
            "dylibs": dylibs,
            "created_at": datetime.now().isoformat(),
            "count": len(dylibs),
        }
        
        filename = f"config_{user_id}_{config_name}_{int(datetime.now().timestamp())}.json"
        filepath = self.configs_path / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Config saved: {filepath}")
        return str(filepath)

    def get_user_configs(self, user_id: int) -> List[Dict]:
        """Получает все конфиги пользователя."""
        configs = []
        for file in self.configs_path.glob(f"config_{user_id}_*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    config["filename"] = file.name
                    configs.append(config)
            except Exception as e:
                print(f"⚠️ Error loading {file}: {e}")
        
        # Сортируем по времени создания (новые первыми)
        return sorted(configs, key=lambda x: x["created_at"], reverse=True)

    def delete_config(self, user_id: int, filename: str) -> bool:
        """Удаляет конфиг."""
        filepath = self.configs_path / filename
        if filepath.exists():
            filepath.unlink()
            print(f"🗑️ Config deleted: {filename}")
            return True
        return False

    # ════════════════════════════════════════════════════════════════
    # ПРЕСЕТЫ
    # ════════════════════════════════════════════════════════════════

    def save_preset(self, preset_name: str, dylibs: List[str]) -> bool:
        """Сохраняет пресет."""
        preset_data = {
            "name": preset_name,
            "dylibs": dylibs,
            "created_at": datetime.now().isoformat(),
            "count": len(dylibs),
        }
        
        filename = f"{preset_name}.json"
        filepath = self.presets_path / filename
        
        # Проверяем, существует ли уже
        if filepath.exists():
            print(f"⚠️ Preset already exists: {preset_name}")
            return False
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(preset_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Preset saved: {preset_name}")
        return True

    def load_preset(self, preset_name: str) -> Optional[List[str]]:
        """Загружает пресет по имени."""
        filepath = self.presets_path / f"{preset_name}.json"
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("dylibs", [])
        except Exception as e:
            print(f"❌ Error loading preset: {e}")
            return None

    def get_all_presets(self) -> Dict[str, List[str]]:
        """Получает все пресеты."""
        presets = {}
        for file in self.presets_path.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = file.stem
                    presets[name] = data.get("dylibs", [])
            except Exception as e:
                print(f"⚠️ Error loading {file}: {e}")
        
        return presets

    def delete_preset(self, preset_name: str) -> bool:
        """Удаляет пресет."""
        filepath = self.presets_path / f"{preset_name}.json"
        if filepath.exists():
            filepath.unlink()
            print(f"🗑️ Preset deleted: {preset_name}")
            return True
        return False

    # ════════════════════════════════════════════════════════════════
    # ПОЛЬЗОВАТЕЛЬСКИЕ ДАННЫЕ
    # ════════════════════════════════════════════════════════════════

    def save_user_data(self, user_id: int, data: Dict) -> bool:
        """Сохраняет данные пользователя."""
        filepath = self.users_path / f"user_{user_id}.json"
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ Error saving user data: {e}")
            return False

    def load_user_data(self, user_id: int) -> Optional[Dict]:
        """Загружает данные пользователя."""
        filepath = self.users_path / f"user_{user_id}.json"
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error loading user data: {e}")
            return None

    # ════════════════════════════════════════════════════════════════
    # БЭКАП
    # ════════════════════════════════════════════════════════════════

    def create_backup(self) -> str:
        """Создаёт резервную копию всех файлов."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
        backup_dir = self.backup_path / backup_name
        
        try:
            shutil.copytree(self.base_path, backup_dir, 
                          ignore=shutil.ignore_patterns('backups'))
            print(f"✅ Backup created: {backup_name}")
            return backup_name
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return ""

    def restore_backup(self, backup_name: str) -> bool:
        """Восстанавливает из бэкапа."""
        backup_dir = self.backup_path / backup_name
        
        if not backup_dir.exists():
            print(f"❌ Backup not found: {backup_name}")
            return False
        
        try:
            # Удаляем текущие данные
            for item in [self.configs_path, self.presets_path, self.users_path]:
                if item.exists():
                    shutil.rmtree(item)
            
            # Копируем из бэкапа
            for item in backup_dir.iterdir():
                if item.name != 'backups':
                    if item.is_dir():
                        shutil.copytree(item, self.base_path / item.name)
                    else:
                        shutil.copy2(item, self.base_path / item.name)
            
            print(f"✅ Restored from: {backup_name}")
            return True
        except Exception as e:
            print(f"❌ Restore failed: {e}")
            return False

    # ════════════════════════════════════════════════════════════════
    # СТАТИСТИКА
    # ════════════════════════════════════════════════════════════════

    def get_storage_stats(self) -> Dict:
        """Получает статистику хранилища."""
        def count_files(path):
            return len(list(path.glob("*.json"))) if path.exists() else 0
        
        return {
            "configs": count_files(self.configs_path),
            "presets": count_files(self.presets_path),
            "users": count_files(self.users_path),
            "backups": len(list(self.backup_path.glob("*"))) if self.backup_path.exists() else 0,
        }

    def cleanup_old_files(self, days: int = 30) -> int:
        """Удаляет старые файлы (старше N дней)."""
        from time import time
        
        cutoff = time() - (days * 86400)
        deleted = 0
        
        for filepath in self.configs_path.glob("*.json"):
            if filepath.stat().st_mtime < cutoff:
                filepath.unlink()
                deleted += 1
        
        print(f"🗑️ Deleted {deleted} old files")
        return deleted
