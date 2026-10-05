from datetime import datetime, timezone

from models import ConvergenceLog, SessionLocal
import claimer


def add_row(chainage, delta_mm=1.0, status="done"):
    """直接落库一条（绕过 HTTP），返回新 id。"""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status=status,
            verdict="合格" if status == "done" else None,
            reason="seed" if status == "done" else None,
            created_by="surveyor",
            created_at=now,
            processed_at=now if status == "done" else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_new_log_is_on_top_of_master_list(client, auth):
    h = auth("surveyor")
    old_id = add_row("K12+180", 1.2)

    resp = client.post("/api/logs", json={"chainage": "K20+050", "delta_mm": 2.1}, headers=h)
    assert resp.status_code == 201
    new_id = resp.get_json()["id"]
    assert new_id > old_id

    rows = client.get("/api/logs", headers=h).get_json()
    ids = [r["id"] for r in rows]
    assert ids[0] == new_id, "新单必须排在总表最上"
    assert ids == sorted(ids, reverse=True), "总表必须严格按 id 倒序"


def test_latest_for_section_returns_newest_id(client, auth):
    h = auth("surveyor")
    first = client.post("/api/logs", json={"chainage": "K20+050", "delta_mm": 1.0}, headers=h)
    second = client.post("/api/logs", json={"chainage": "K20+050", "delta_mm": 2.0}, headers=h)
    other = client.post("/api/logs", json={"chainage": "K21+000", "delta_mm": 3.0}, headers=h)
    assert first.status_code == second.status_code == other.status_code == 201

    resp = client.get("/api/chainages/K20+050/latest", headers=h)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == second.get_json()["id"], "同断面再写一单，取最新必须吐新号"
    assert data["chainage"] == "K20+050"


def test_commit_instant_master_and_latest_agree(client, auth):
    """落库那一拍（仍是 pending）：总表最上与按断面取最新必须是同一个新 id。"""
    h = auth("surveyor")
    add_row("K20+050", 1.0)

    resp = client.post("/api/logs", json={"chainage": "K20+050", "delta_mm": 2.4}, headers=h)
    new_id = resp.get_json()["id"]
    assert resp.get_json()["status"] == "pending"

    top_id = client.get("/api/logs", headers=h).get_json()[0]["id"]
    latest_id = client.get("/api/chainages/K20+050/latest", headers=h).get_json()["id"]
    assert top_id == latest_id == new_id


def test_latest_on_empty_section_is_404_and_fabricates_nothing(client, auth):
    h = auth("surveyor")
    add_row("K20+050", 1.0)
    resp = client.get("/api/chainages/K99+999/latest", headers=h)
    assert resp.status_code == 404
    body = resp.get_json()
    assert "id" not in body, "空断面不许编造编号"
    assert body["detail"]


def test_inspector_is_read_only(client, auth):
    h = auth("inspector")
    resp = client.post("/api/logs", json={"chainage": "K20+050", "delta_mm": 1.0}, headers=h)
    assert resp.status_code == 403
    assert client.get("/api/logs", headers=h).status_code == 200


def test_supervisor_is_read_only_and_never_fabricates(client, auth):
    h = auth("supervisor")
    # 监理不能报送
    resp = client.post("/api/logs", json={"chainage": "K20+050", "delta_mm": 1.0}, headers=h)
    assert resp.status_code == 403

    # 监理可查最新：有单吐真号
    real_id = add_row("K20+050", 1.0)
    got = client.get("/api/chainages/K20+050/latest", headers=h)
    assert got.status_code == 200
    assert got.get_json()["id"] == real_id

    # 监理查空断面：404，不编造
    empty = client.get("/api/chainages/K88+888/latest", headers=h)
    assert empty.status_code == 404
    assert "id" not in empty.get_json()


def test_queue_top_and_master_top_share_one_ordering_rule(client, auth):
    """排队（待认领）谁在最上 = 最旧 pending 先处理（FIFO）；
    总表谁在最上 = 最新一单。两者都只认 id 即落库顺序，不得各写一套排序。"""
    h = auth("surveyor")
    id_a = add_row("K20+050", 1.0, status="pending")
    id_b = add_row("K20+051", 1.0, status="pending")
    id_c = add_row("K20+052", 1.0, status="pending")

    # 认领队列最上：最旧一单先被处理
    assert claimer.claim_once() is True
    db = SessionLocal()
    try:
        claimed = (
            db.query(ConvergenceLog).filter(ConvergenceLog.status == "done").one()
        )
        assert claimed.id == id_a
    finally:
        db.close()

    # 总表最上：最新一单（与认领队列同一 id 口径的两端，互不矛盾）
    rows = client.get("/api/logs", headers=h).get_json()
    assert rows[0]["id"] == id_c
    assert [r["id"] for r in rows] == [id_c, id_b, id_a]


def test_anonymous_rejected(client):
    assert client.get("/api/logs").status_code == 401
    assert client.get("/api/chainages/K20+050/latest").status_code == 401
