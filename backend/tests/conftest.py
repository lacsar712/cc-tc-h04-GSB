import os
import tempfile

import pytest

# 必须在 import models/api 之前把数据库指向临时 sqlite。
_DB_PATH = os.path.join(tempfile.gettempdir(), "test_h04_tunnelconv.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("JWT_SECRET", "test-secret")

PASSWORDS = {
    "surveyor": "surv123456",
    "inspector": "insp123456",
    "supervisor": "supv123456",
}

import claimer  # noqa: E402

# 在 api 导入并 start() 认领线程之前就置位停止信号，
# 线程首轮即退出、绝不触碰数据库，保证测试全程同步可控。
claimer._stop.set()

import api  # noqa: E402 ,F401  导入即建表、播种
from models import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client():
    api.app.testing = True
    return api.app.test_client()


@pytest.fixture()
def auth(client):
    def _headers(username: str) -> dict:
        resp = client.post(
            "/api/auth/login",
            json={"username": username, "password": PASSWORDS[username]},
        )
        assert resp.status_code == 200, resp.get_json()
        token = resp.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _headers
