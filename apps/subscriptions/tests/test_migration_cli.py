"""独立进程验证部署用迁移入口，避免仅测试注入连接的分支。"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_migration_cli_uses_explicit_url_and_handles_percent_in_path(tmp_path):
    service = Path(__file__).resolve().parents[1]
    database_file = tmp_path / "local%database.db"
    env = {**os.environ, "SUBSCRIPTIONS_DATABASE_URL": f"sqlite+aiosqlite:///{database_file}"}
    base = [sys.executable, "-m", "alembic", "-c", str(service / "alembic.ini")]
    subprocess.run(
        [*base, "upgrade", "head"],
        env=env,
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_file) as connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"subscriptions", "subscription_items", "item_revisions"} <= names
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0001_subscription_domain",
        )
    subprocess.run(
        [*base, "downgrade", "base"],
        env=env,
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_file) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'subscriptions'"
            ).fetchone()
            is None
        )
