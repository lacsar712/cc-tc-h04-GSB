"""H04 顺序一致性回归：落库 / 总表 / 按断面取最新必须同一口径。"""
from urllib.parse import quote

import pytest

from conftest import auth, insert_log, login


SECTION_A = "K12+180"
SECTION_B = "K20+050"
SECTION_EMPTY = "K99+999"


def latest_url(chainage):
    # 桩号里的 '+' 必须编码成 %2B，否则查询串会把 '+' 解成空格。
    return "/api/logs/latest?chainage=" + quote(chainage, safe="")


# --- 落库那一拍：回传编号 == 库里真实编号 == 总表最上 == 断面最新 -------------

def test_commit_id_matches_list_top_and_section_latest(client):
    token = login(client, "surveyor", "surv123456")

    first = insert_log(SECTION_A, 1.0)
    created = client.post(
        "/api/logs", headers=auth(token), json={"chainage": SECTION_A, "delta_mm": 2.0}
    )
    assert created.status_code == 201
    new_id = created.get_json()["id"]
    assert new_id > first  # 落库顺序：后写的编号更大

    # 总表最上一条必须就是刚落库那张单，不得吐出旧号。
    listing = client.get("/api/logs", headers=auth(token))
    assert listing.status_code == 200
    rows = listing.get_json()
    assert rows[0]["id"] == new_id
    assert [r["id"] for r in rows] == sorted((r["id"] for r in rows), reverse=True)

    # 按断面取最新也必须是同一张单。
    latest = client.get(f"/api/logs/latest?chainage={SECTION_A}", headers=auth(token))
    assert latest.status_code == 200
    assert latest.get_json()["id"] == new_id


def test_new_order_kept_even_when_falling_into_oldest_bucket(client):
    """新单排到最旧一档（同断面已有更旧单）时，取最新仍不得吐旧号。"""
    token = login(client, "surveyor", "surv123456")
    old_ids = [insert_log(SECTION_B, 1.0) for _ in range(3)]

    created = client.post(
        "/api/logs", headers=auth(token), json={"chainage": SECTION_B, "delta_mm": 0.5}
    )
    new_id = created.get_json()["id"]
    assert new_id == max(old_ids) + 1

    latest = client.get(f"/api/logs/latest?chainage={SECTION_B}", headers=auth(token))
    assert latest.get_json()["id"] == new_id
    assert latest.get_json()["id"] != min(old_ids)  # 不许退回最旧编号


# --- 空断面：取最新不许编造编号 ---------------------------------------------

@pytest.mark.parametrize("username,password", [
    ("surveyor", "surv123456"),
    ("inspector", "insp123456"),
    ("supervisor", "supv123456"),
])
def test_latest_on_empty_section_returns_404_and_no_id(client, username, password):
    token = login(client, username, password)
    resp = client.get(f"/api/logs/latest?chainage={SECTION_EMPTY}", headers=auth(token))
    assert resp.status_code == 404
    body = resp.get_json()
    assert body.get("id") is None
    assert str(body.get("id")) not in ("0", "1")  # 不得拿 0/1 之类顶替
    assert "暂无" in body["detail"]


def test_latest_scoped_per_section_does_not_leak_other_section(client):
    token = login(client, "surveyor", "surv123456")
    a_id = insert_log(SECTION_A, 1.0)
    insert_log(SECTION_B, 9.0)  # 编号更大，但属于另一个断面
    resp = client.get(f"/api/logs/latest?chainage={SECTION_A}", headers=auth(token))
    assert resp.status_code == 200
    assert resp.get_json()["id"] == a_id


def test_latest_requires_chainage(client):
    token = login(client, "surveyor", "surv123456")
    resp = client.get("/api/logs/latest", headers=auth(token))
    assert resp.status_code == 400


# --- 排队最上 == 总表最上：pending 认领顺序与列表口径一致 --------------------

def test_pending_claim_order_matches_list_top(client):
    """排队（待认领）谁在最上，必须与总表谁在最上是同一套顺序。"""
    from models import ConvergenceLog, SessionLocal
    from claimer import claim_once

    token = login(client, "surveyor", "surv123456")
    p1 = insert_log(SECTION_A, 1.0, status="pending")
    p2 = insert_log(SECTION_A, 2.0, status="pending")
    p3 = insert_log(SECTION_B, 3.0, status="pending")

    # 待认领按编号从大到小依次被认领（新单在队首）。
    def pending_ids():
        db = SessionLocal()
        try:
            return {
                rid
                for (rid,) in db.query(ConvergenceLog.id)
                .filter(ConvergenceLog.status == "pending")
                .all()
            }
        finally:
            db.close()

    claimed = []
    remaining = pending_ids()
    for _ in range(3):
        assert claim_once() is True
        before = remaining
        remaining = pending_ids()
        claimed.append((before - remaining).pop())
    assert claimed == [p3, p2, p1]

    rows = client.get("/api/logs", headers=auth(token)).get_json()
    assert [r["id"] for r in rows[:3]] == [p3, p2, p1]
    assert claim_once() is False  # 队列空了不许凭空再取


# --- 权限：巡检员 / 监理只读，不能报送 --------------------------------------

@pytest.mark.parametrize("username,password", [
    ("inspector", "insp123456"),
    ("supervisor", "supv123456"),
])
def test_readers_cannot_submit(client, username, password):
    token = login(client, username, password)
    resp = client.post(
        "/api/logs", headers=auth(token), json={"chainage": SECTION_A, "delta_mm": 1.0}
    )
    assert resp.status_code == 403


def test_inspector_can_read_list_and_latest(client):
    token = login(client, "inspector", "insp123456")
    insert_log(SECTION_A, 1.0)
    assert client.get("/api/logs", headers=auth(token)).status_code == 200
    assert client.get(
        f"/api/logs/latest?chainage={SECTION_A}", headers=auth(token)
    ).status_code == 200


def test_supervisor_latest_does_not_fabricate(client):
    token = login(client, "supervisor", "supv123456")
    resp = client.get(f"/api/logs/latest?chainage={SECTION_EMPTY}", headers=auth(token))
    assert resp.status_code == 404
    assert resp.get_json()["id"] is None


def test_anonymous_rejected(client):
    assert client.get("/api/logs").status_code == 401
    assert client.get(f"/api/logs/latest?chainage={SECTION_A}").status_code == 401
    assert client.post("/api/logs", json={"chainage": SECTION_A, "delta_mm": 1}).status_code == 401
