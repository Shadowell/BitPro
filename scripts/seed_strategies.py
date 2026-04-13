#!/usr/bin/env python3
"""
将种子策略导入到 SQLite 数据库
读取 data/seed/strategies.json + strategies/*.py 脚本内容，写入 strategies 表。
已存在同名策略时默认跳过，传 --force 可覆盖。
"""
import json
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = PROJECT_ROOT / "data" / "seed" / "strategies.json"
SCRIPTS_DIR = PROJECT_ROOT / "strategies"
DB_PATH = os.environ.get("DB_PATH", str(PROJECT_ROOT / "data" / "crypto_data.db"))

PLACEHOLDER_SCRIPT = '''"""
{name}

{description}

此策略使用 v2 引擎内置实现 (strategy_key: {strategy_key})，
通过回测页面选择此策略即可运行。
"""

# v2 引擎策略，无需自定义脚本
# strategy_key = "{strategy_key}"
'''


def load_script_content(entry: dict) -> str:
    script_file = entry.get("script_file")
    if script_file:
        path = SCRIPTS_DIR / script_file
        if path.exists():
            return path.read_text(encoding="utf-8")
    return PLACEHOLDER_SCRIPT.format(
        name=entry["name"],
        description=entry.get("description", ""),
        strategy_key=entry.get("strategy_key", ""),
    )


def ensure_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            script_content TEXT NOT NULL,
            config TEXT,
            status TEXT DEFAULT 'stopped',
            exchange TEXT,
            symbols TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()


def seed(force: bool = False):
    if not SEED_FILE.exists():
        print(f"[ERROR] 种子文件不存在: {SEED_FILE}")
        sys.exit(1)

    entries = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    print(f"[INFO] 读取到 {len(entries)} 个种子策略")
    print(f"[INFO] 数据库: {DB_PATH}")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    inserted = 0
    skipped = 0
    updated = 0

    for entry in entries:
        name = entry["name"]
        description = entry.get("description", "")
        config = json.dumps(entry.get("config", {}))
        exchange = entry.get("exchange", "okx")
        symbols = json.dumps(entry.get("symbols", ["BTC/USDT"]))
        script_content = load_script_content(entry)

        existing = conn.execute(
            "SELECT id FROM strategies WHERE name = ?", (name,)
        ).fetchone()

        if existing and not force:
            skipped += 1
            continue

        now = datetime.now().isoformat()
        if existing:
            conn.execute(
                """UPDATE strategies
                   SET description=?, script_content=?, config=?,
                       exchange=?, symbols=?, updated_at=?
                   WHERE name=?""",
                (description, script_content, config, exchange, symbols, now, name),
            )
            updated += 1
        else:
            conn.execute(
                """INSERT INTO strategies
                   (name, description, script_content, config, status, exchange, symbols, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'stopped', ?, ?, ?, ?)""",
                (name, description, script_content, config, exchange, symbols, now, now),
            )
            inserted += 1

    conn.commit()
    conn.close()

    print(f"[DONE] 新增 {inserted} | 更新 {updated} | 跳过 {skipped}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    if force:
        print("[INFO] --force 模式：已存在的策略将被覆盖")
    seed(force=force)
