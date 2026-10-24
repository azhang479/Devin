from pathlib import Path

from fastapi.testclient import TestClient
from fpdf import FPDF

from appeals import api
from appeals.llm.client import LLMError
from appeals.parser import parse_835

ROOT = Path(__file__).resolve().parents[1]
EOB_PDF = ROOT / "data" / "synthetic" / "eobs" / "CASE-001.pdf"
EOB_835 = ROOT / "data" / "synthetic" / "cases" / "CASE-001.835"


class FakeClient:
    model = "fake"

    def __init__(self, eob_payload=None, fail_evidence=False):
        self.eob_payload = eob_payload
        self.fail_evidence = fail_evidence

    def generate_json(self, system, user, schema):
        if "Explanation of Benefits" in system:
            return self.eob_payload
        if self.fail_evidence:
            raise LLMError("synthetic model failure")
        note = user.split("Clinical note:\n<<<\n", 1)[1].split("\n>>>", 1)[0]
        criteria = [
            line.split(": ", 1)[0].removeprefix("- ")
            for line in user.split("Criteria:\n", 1)[1].split("\n\nClinical note:", 1)[0].splitlines()
            if line.startswith("- ")
        ]
        quote = next((sentence.strip() for sentence in note.split(".") if sentence.strip()), note)
        return {
            "criteria": [
                {"criterion_id": criterion_id, "met": True, "quote": quote}
                for criterion_id in criteria
            ]
        }

    def generate_text(self, system, user):
        if self.fail_evidence:
            raise LLMError("synthetic model failure")
        return "The provided clinical record supports review under the stated policy."


class FailingClient:
    model = "fake"

    def generate_json(self, system, user, schema):
        raise LLMError("synthetic extraction failure")

    def generate_text(self, system, user):
        raise LLMError("synthetic generation failure")


def _client(monkeypatch, llm_client):
    monkeypatch.setenv("APPEALS_TODAY", "2026-10-24")
    monkeypatch.setattr(api, "get_llm_client", lambda: llm_client)
    return TestClient(api.app)


def _medical_necessity_record_id():
    return next(
        record.id
        for record in api.store.records.values()
        if record.triage.category == "medical_necessity"
    )


def test_ai_review_disabled_unknown_record_and_status_endpoint(monkeypatch):
    monkeypatch.delenv("APPEALS_AI", raising=False)
    with _client(monkeypatch, None) as client:
        record_id = _medical_necessity_record_id()
        assert client.post(f"/api/denials/{record_id}/ai-review").status_code == 503
        assert client.post("/api/denials/missing/ai-review").status_code == 404
        assert client.get("/api/ai/status").json() == {
            "enabled": False,
            "model": None,
            "reachable": False,
        }


def test_ai_review_uses_fake_client_and_falls_back_on_llm_error(monkeypatch):
    with _client(monkeypatch, FakeClient()) as client:
        record_id = _medical_necessity_record_id()
        response = client.post(f"/api/denials/{record_id}/ai-review")
        assert response.status_code == 200
        assert response.json()["analysis_method"] == "ai"
        assert response.json()["triage"]["evidence"]["method"] == "ai"
        assert response.json()["status"] == "pending"

    with _client(monkeypatch, FakeClient(fail_evidence=True)) as client:
        record_id = _medical_necessity_record_id()
        response = client.post(f"/api/denials/{record_id}/ai-review")
        assert response.status_code == 200
        assert response.json()["analysis_method"] == "keyword_fallback"
        assert response.json()["ai_error"] == "synthetic model failure"


def test_gather_documentation_seed_has_template_doc_request(monkeypatch):
    with _client(monkeypatch, None) as client:
        record = next(
            item
            for item in api.store.records.values()
            if item.triage.action == "gather_documentation"
            and item.triage.category == "medical_necessity"
        )

        detail = client.get(f"/api/denials/{record.id}").json()

        assert detail["doc_request_method"] == "template"
        assert detail["doc_request"]


def test_eob_endpoint_creation_disabled_and_blank_pdf(monkeypatch):
    denial = parse_835(EOB_835.read_text(encoding="utf-8"))[0]
    payload = denial.model_dump(mode="json")
    with _client(monkeypatch, FakeClient(eob_payload=payload)) as client:
        response = client.post(
            "/api/eobs",
            files={"eob": ("CASE-001.pdf", EOB_PDF.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 201
        record_id = response.json()["ids"][0]
        detail = client.get(f"/api/denials/{record_id}").json()
        assert detail["source"] == "eob_pdf"
        assert any(
            row["id"] == record_id and row["source"] == "eob_pdf"
            for row in client.get("/api/queue").json()
        )

    with _client(monkeypatch, None) as client:
        response = client.post(
            "/api/eobs",
            files={"eob": ("CASE-001.pdf", EOB_PDF.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 503

    pdf = FPDF()
    pdf.add_page()
    blank_pdf = bytes(pdf.output())
    with _client(monkeypatch, FakeClient()) as client:
        response = client.post(
            "/api/eobs",
            files={"eob": ("blank.pdf", blank_pdf, "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == (
            "No extractable text; scanned PDFs are not supported"
        )


def test_eob_endpoint_maps_validation_and_model_errors(monkeypatch):
    denial = parse_835(EOB_835.read_text(encoding="utf-8"))[0]
    invalid_payload = denial.model_dump(mode="json")
    invalid_payload["claim_id"] = "NOT-IN-EOB"
    with _client(monkeypatch, FakeClient(eob_payload=invalid_payload)) as client:
        response = client.post(
            "/api/eobs",
            files={"eob": ("CASE-001.pdf", EOB_PDF.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 422
        assert any("Claim number not found" in error for error in response.json()["detail"]["errors"])

    with _client(monkeypatch, FailingClient()) as client:
        response = client.post(
            "/api/eobs",
            files={"eob": ("CASE-001.pdf", EOB_PDF.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 502
        assert "synthetic extraction failure" in response.json()["detail"]
