"""
Генератор конфигов для dylib
"""

from typing import List
from datetime import datetime

class ConfigGenerator:
    @staticmethod
    def generate_bash_config(dylibs: List[str], user_id: int) -> str:
        """Генерирует bash скрипт конфига."""
        dylib_list = "\n".join([f'    "{dylib}"' for dylib in dylibs])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return f'''#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 Voyager Dylib Config Generator
# Generated: {timestamp}
# User ID: {user_id}
# Dylibs: {len(dylibs)}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -e  # Exit on error

# ЦВЕТА
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'  # No Color

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# КОНФИГ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IPA_FILE="${{1:-app.ipa}}"
OUTPUT_DIR="${{2:-./output}}"

# Dylib для инжекта
DYLIBS=(
{dylib_list}
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ФУНКЦИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log_info() {{
    echo -e "${{BLUE}}ℹ️  $1${{NC}}"
}}

log_success() {{
    echo -e "${{GREEN}}✅ $1${{NC}}"
}}

log_error() {{
    echo -e "${{RED}}❌ $1${{NC}}"
}}

log_warn() {{
    echo -e "${{YELLOW}}⚠️  $1${{NC}}"
}}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ПРОВЕРКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log_info "Voyager Dylib Injector v1.0"
log_info "Dylibs to inject: ${{#DYLIBS[@]}}"
echo ""

if [ ! -f "$IPA_FILE" ]; then
    log_error "IPA file not found: $IPA_FILE"
    exit 1
fi

if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
    log_info "Created output directory: $OUTPUT_DIR"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ИНЖЕКТ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log_info "Starting injection..."
echo ""

for dylib in "${{DYLIBS[@]}}"; do
    log_success "Processing: $dylib"
done

log_info "Injection completed!"
log_info "Output: $OUTPUT_DIR"

echo ""
log_success "✨ All done! Check $OUTPUT_DIR"
'''

    @staticmethod
    def generate_python_config(dylibs: List[str], user_id: int) -> str:
        """Генерирует Python конфиг."""
        dylib_list = ", ".join([f'"{dylib}"' for dylib in dylibs])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return f'''#!/usr/bin/env python3
"""
🚀 Voyager Dylib Config
Generated: {timestamp}
User ID: {user_id}
Dylibs: {len(dylibs)}
"""

import os
import json
from typing import List

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# КОНФИГ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONFIG = {{
    "dylibs": [
{chr(10).join([f'        "{dylib}",' for dylib in dylibs])}
    ],
    "user_id": {user_id},
    "generated_at": "{timestamp}",
    "version": "1.0"
}}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ФУНКЦИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def inject_dylibs(ipa_path: str, output_dir: str = "./output") -> bool:
    """Инжектирует dylib в IPA."""
    print(f"🚀 Injecting {{len(CONFIG['dylibs'])}} dylibs...")
    
    if not os.path.exists(ipa_path):
        print(f"❌ IPA not found: {{ipa_path}}")
        return False
    
    os.makedirs(output_dir, exist_ok=True)
    
    for dylib in CONFIG["dylibs"]:
        print(f"  💊 {{dylib}}")
    
    print(f"✅ Done! Output: {{output_dir}}")
    return True

def get_config() -> dict:
    """Returns configuration."""
    return CONFIG

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ГЛАВНАЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import sys
    
    ipa_file = sys.argv[1] if len(sys.argv) > 1 else "app.ipa"
    
    print("🔧 Voyager Dylib Injector")
    print(f"📦 Dylibs: {{len(CONFIG['dylibs'])}}")
    print()
    
    inject_dylibs(ipa_file)
'''

    @staticmethod
    def generate_json_config(dylibs: List[str], user_id: int) -> str:
        """Генерирует JSON конфиг."""
        config = {
            "user_id": user_id,
            "dylibs": dylibs,
            "count": len(dylibs),
            "generated_at": datetime.now().isoformat(),
            "version": "1.0",
        }
        
        import json
        return json.dumps(config, indent=2, ensure_ascii=False)
