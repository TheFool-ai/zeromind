"""验证命令行迁移与默认应用工厂共用显式配置，覆盖启动和退出生命周期。"""

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from subscription_service.bootstrap.app import create_app


def test_factory_uses_configured_database_and_persists_after_restart(tmp_path, monkeypatch):
    service = Path(__file__).resolve().parents[1]
    url = f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}"
    monkeypatch.setenv("SUBSCRIPTIONS_DATABASE_URL", url)
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(service / "alembic.ini"), "upgrade", "head"],
        cwd=tmp_path,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
    )
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/subscriptions",
            json={"name": "启动测试", "feed_address": "https://example.com/feed"},
        )
        assert response.status_code == 201
        detail = response.json()
        assert client.get("/api/docs").status_code == 200
    # 第二个应用实例重新创建连接池，仍能读取已提交数据。
    with TestClient(create_app()) as client:
        response = client.get(f"/api/v1/subscriptions/{detail['id']}")
        assert response.status_code == 200
        assert response.json() == detail
