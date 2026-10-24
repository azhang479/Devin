from pathlib import Path

from fastapi.testclient import TestClient

from appeals.api import app

ROOT = Path(__file__).resolve().parents[1]


def test_api_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("APPEALS_TODAY", "2026-10-24")
    with TestClient(app) as client:
        queue = client.get("/api/queue").json()
        assert len(queue) == 30
        assert [row["priority"] for row in queue] == sorted(
            (row["priority"] for row in queue), reverse=True
        )

        appeal = next(row for row in queue if row["action"] == "appeal")
        detail = client.get(f"/api/denials/{appeal['id']}").json()
        assert detail["triage"]["evidence"] is not None
        assert detail["note_text"]
        assert detail["letter"]
        assert client.get(f"/api/denials/{appeal['id']}/letter.txt").status_code == 200

        fixture = ROOT / "tests" / "fixtures" / "sample.835"
        response = client.post(
            "/api/denials",
            files={"remit": ("sample.835", fixture.read_bytes(), "text/plain")},
            data={"note": "Six weeks of physical therapy and weakness."},
        )
        assert response.status_code == 201
        ids = response.json()["ids"]
        assert len(ids) == 2
        assert client.get(f"/api/denials/{ids[0]}").status_code == 200
        assert client.post(f"/api/denials/{ids[0]}/approve").json()["status"] == "approved"
        assert client.get(f"/api/denials/{ids[0]}").json()["status"] == "approved"
        assert client.get("/api/stats").json()["total_amount_at_stake"] > 0
        assert {row["payer_id"] for row in client.get("/api/rules").json()} == {
            "acme",
            "blueriver",
            "summit",
        }
        assert client.get("/").text.find("UI coming") >= 0
        assert client.get("/static/index.html").status_code == 200
