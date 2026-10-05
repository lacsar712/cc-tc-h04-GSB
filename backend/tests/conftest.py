import os
import tempfile

# 必须在导入 api / models 之前指定测试库并关掉启动期建种与后台认领线程。
_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="tunnelconv-test-", suffix=".db")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["DISABLE_STARTUP"] = "1"
os.environ["DISABLE_CLAIMER"] = "1"

import pytest  # noqa: E402

from models import Base, ConvergenceLog, SessionLocal, engine  # noqa: E402
from rules import judge  # noqa: E402
import api  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    api.app.testing = True
    with api.app.test_client() as c:
        yield c
    Base.metadata.drop_all(engine)


def login(client, username, password):
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def insert_log(chainage, delta_mm=1.0, status="done", created_by="surveyor"):
    """绕过接口直接落一行，返回其自增编号。"""
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        verdict, reason = judge(float(delta_mm)) if status == "done" else (None, None)
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status=status,
            verdict=verdict,
            reason=reason,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()
