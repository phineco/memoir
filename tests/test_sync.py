from models import NewPerson, SyncLog, get_session


def test_successful_packet_is_idempotent(client, login):
    login()
    packet = {"type": "new_person", "clientId": "same-packet", "payload": {"name": "New Relative"}}
    assert client.post("/api/sync", json={"family_id": "a", "packet": packet}).get_json()["applied"] is True
    assert client.post("/api/sync", json={"family_id": "a", "packet": packet}).get_json()["applied"] is False
    assert get_session().query(NewPerson).filter_by(name="New Relative").count() == 1


def test_repeated_failure_logs_do_not_block_corrected_retry(client, login):
    login()
    packet = {"type": "new_person", "clientId": "retry-packet", "payload": {}}
    for _ in range(2):
        assert client.post("/api/sync", json={"family_id": "a", "packet": packet}).status_code == 400
    packet["payload"] = {"name": "Confirmed Relative"}
    assert client.post("/api/sync", json={"family_id": "a", "packet": packet}).get_json()["applied"] is True
    assert get_session().query(SyncLog).filter_by(status="failed").count() == 2


def test_invalid_nested_payload_returns_controlled_error(client, login):
    login()
    packet = {"type": "tree_upsert", "clientId": "invalid-shape", "payload": {"persons": [42]}}
    assert client.post("/api/sync", json={"family_id": "a", "packet": packet}).status_code == 400


def test_invalid_packet_types_are_logged_without_secondary_error(client, login):
    login()
    assert client.post("/api/sync", json=[1]).status_code == 400
    packet = {"type": [], "clientId": "invalid-type", "payload": {}}
    assert client.post("/api/sync", json={"family_id": "a", "packet": packet}).status_code == 400
