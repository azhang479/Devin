import json
import os
from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from appeals.ai_evidence import match_criteria_ai
from appeals.ai_letter import draft_argument
from appeals.carc import load_carc_table
from appeals.doc_request import draft_doc_request
from appeals.eob import EOBValidationError, extract_eob, extract_pdf_text
from appeals.letter import render_letter
from appeals.llm import client as llm_client
from appeals.llm.client import LLMClient, LLMError
from appeals.models import Denial
from appeals.parser import parse_835
from appeals.rules import PayerRules, load_rules
from appeals.store import DenialRecord, InMemoryStore
from appeals.triage import triage

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
app = FastAPI(title="Appeals Copilot", description="Synthetic claim-denial decision support.")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
store = InMemoryStore()
payer_rules: dict[str, PayerRules] = {}
carc_table: dict = {}


def get_llm_client() -> LLMClient | None:
    return llm_client.get_client()


def _today() -> date:
    return date.fromisoformat(os.environ.get("APPEALS_TODAY", "2026-10-24"))


def _policy_for(denial: Denial, payer: PayerRules):
    if denial.lines:
        for policy in payer.policies:
            if any(line.cpt in policy.cpt_codes for line in denial.lines):
                return policy
    return None


def _add_record(
    record_id: str,
    denial: Denial,
    payer: PayerRules,
    note: str,
    auth_number: str | None,
    proof: bool,
    client: LLMClient | None = None,
    source: str = "835",
) -> DenialRecord:
    triage_args = {
        "note_text": note,
        "auth_number": auth_number,
        "proof_of_timely_filing": proof,
        "today": _today(),
    }
    analysis_method = "keyword"
    ai_error = None
    if client is None:
        result = triage(denial, payer, carc_table, **triage_args)
    else:
        try:
            result = triage(
                denial,
                payer,
                carc_table,
                **triage_args,
                evidence_matcher=lambda note_text, policy: match_criteria_ai(
                    note_text, policy, client
                ),
            )
            if result.evidence.method == "ai":
                analysis_method = "ai"
        except LLMError as exc:
            result = triage(denial, payer, carc_table, **triage_args)
            analysis_method = "keyword_fallback"
            ai_error = str(exc)
    policy = _policy_for(denial, payer)
    argument = (
        draft_argument(denial, result, payer, policy, note, client)
        if client is not None
        else None
    )
    letter = render_letter(denial, result, payer, policy, argument=argument)
    doc_request, doc_request_method = draft_doc_request(
        denial, result, policy, client
    )
    record = DenialRecord(
        id=record_id,
        denial=denial,
        payer=payer,
        note=note,
        auth_number=auth_number,
        proof_of_timely_filing=proof,
        triage=result,
        letter=letter,
        doc_request=doc_request,
        doc_request_method=doc_request_method,
        analysis_method=analysis_method,
        ai_error=ai_error,
        ai_argument=argument is not None,
        source=source,
    )
    store.add(record)
    return record


@app.on_event("startup")
def load_initial_data() -> None:
    global payer_rules, carc_table
    payer_rules = load_rules(ROOT / "rules" / "payers")
    carc_table = load_carc_table(ROOT / "data" / "carc_codes.yaml")
    store.records.clear()
    for path in sorted((ROOT / "data" / "synthetic" / "cases").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        remit_path = path.parent / case["remit_file"]
        parsed = parse_835(remit_path.read_text(encoding="utf-8"))
        payer = payer_rules[case["payer_id"]]
        for index, denial in enumerate(parsed, start=1):
            _add_record(
                case["id"] if len(parsed) == 1 else f"{case['id']}-{index}",
                denial,
                payer,
                case["note"],
                case.get("auth_number"),
                bool(case.get("proof_of_timely_filing", False)),
            )


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/queue")
def get_queue():
    records = sorted(store.records.values(), key=lambda item: item.triage.priority, reverse=True)
    return [
        {
            "id": record.id,
            "patient": record.denial.patient_name,
            "payer_name": record.payer.name,
            "cpt": record.denial.lines[0].cpt if record.denial.lines else None,
            "carc": record.triage.carc,
            "category": record.triage.category,
            "action": record.triage.action,
            "amount_at_stake": record.triage.amount_at_stake,
            "days_left": record.triage.days_left,
            "win_probability": record.triage.win_probability,
            "priority": record.triage.priority,
            "status": record.status,
            "analysis_method": record.analysis_method,
            "source": record.source,
        }
        for record in records
    ]


@app.get("/api/denials/{record_id}")
def get_denial(record_id: str):
    record = store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Denial not found")
    return _denial_detail(record)


def _denial_detail(record: DenialRecord) -> dict:
    return {
        "id": record.id,
        "denial": record.denial.model_dump(mode="json"),
        "payer": {"payer_id": record.payer.payer_id, "name": record.payer.name},
        "triage": record.triage.model_dump(mode="json"),
        "note_text": record.note,
        "letter": record.letter,
        "status": record.status,
        "doc_request": record.doc_request,
        "doc_request_method": record.doc_request_method,
        "analysis_method": record.analysis_method,
        "ai_error": record.ai_error,
        "ai_argument": record.ai_argument,
        "source": record.source,
    }


@app.post("/api/denials", status_code=201)
async def create_denials(
    remit: Annotated[UploadFile, File()],
    note: Annotated[str, Form()] = "",
    auth_number: Annotated[str | None, Form()] = None,
    proof_of_timely_filing: Annotated[bool, Form()] = False,
):
    try:
        denials = parse_835((await remit.read()).decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Unable to parse remit: {exc}") from exc
    if not denials:
        raise HTTPException(status_code=400, detail="No claims found in remit")
    client = get_llm_client()
    ids = []
    for denial in denials:
        payer = payer_rules.get(denial.payer_id)
        if payer is None:
            raise HTTPException(status_code=400, detail=f"Unknown payer_id: {denial.payer_id}")
        record_id = str(uuid4())
        _add_record(
            record_id,
            denial,
            payer,
            note,
            auth_number,
            proof_of_timely_filing,
            client=client,
        )
        ids.append(record_id)
    return {"ids": ids}


@app.get("/api/ai/status")
def get_ai_status():
    return llm_client.status()


@app.post("/api/denials/{record_id}/ai-review")
def ai_review_denial(record_id: str):
    record = store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Denial not found")
    client = get_llm_client()
    if client is None:
        raise HTTPException(status_code=503, detail="AI is disabled; set APPEALS_AI=ollama")
    updated = _add_record(
        record.id,
        record.denial,
        record.payer,
        record.note,
        record.auth_number,
        record.proof_of_timely_filing,
        client=client,
        source=record.source,
    )
    updated.status = "pending"
    return _denial_detail(updated)


@app.post("/api/eobs", status_code=201)
async def create_eob(
    eob: Annotated[UploadFile, File()],
    note: Annotated[str, Form()] = "",
    auth_number: Annotated[str | None, Form()] = None,
    proof_of_timely_filing: Annotated[bool, Form()] = False,
):
    client = get_llm_client()
    if client is None:
        raise HTTPException(status_code=503, detail="AI is disabled; set APPEALS_AI=ollama")
    try:
        text = extract_pdf_text(await eob.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len("".join(text.split())) < 20:
        raise HTTPException(
            status_code=400,
            detail="No extractable text; scanned PDFs are not supported",
        )
    try:
        denial = extract_eob(text, payer_rules, client)
    except EOBValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    payer = payer_rules[denial.payer_id]
    record_id = str(uuid4())
    _add_record(
        record_id,
        denial,
        payer,
        note,
        auth_number,
        proof_of_timely_filing,
        client=client,
        source="eob_pdf",
    )
    return {"ids": [record_id]}


@app.post("/api/denials/{record_id}/approve")
def approve_denial(record_id: str):
    record = store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Denial not found")
    record.status = "approved"
    return {"id": record.id, "status": record.status}


@app.get("/api/denials/{record_id}/letter.txt", response_class=PlainTextResponse)
def get_letter(record_id: str):
    record = store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Denial not found")
    if record.letter is None:
        raise HTTPException(status_code=404, detail="No appeal letter for this denial")
    return PlainTextResponse(record.letter)


@app.get("/api/stats")
def get_stats():
    records = list(store.records.values())
    by_action: dict[str, int] = {}
    for record in records:
        by_action[record.triage.action] = by_action.get(record.triage.action, 0) + 1
    total_at_stake = sum(record.triage.amount_at_stake for record in records)
    appeal_resubmit = sum(
        record.triage.amount_at_stake
        for record in records
        if record.triage.action in {"appeal", "resubmit"}
    )
    expected_recovery = sum(
        record.triage.amount_at_stake * record.triage.win_probability for record in records
    )
    return {
        "count_by_action": by_action,
        "total_amount_at_stake": round(total_at_stake, 2),
        "appeal_and_resubmit_amount": round(appeal_resubmit, 2),
        "expected_recovery": round(expected_recovery, 2),
    }


@app.get("/api/rules")
def get_rules():
    return [
        {
            "payer_id": payer.payer_id,
            "payer": payer.name,
            "deadline_days": payer.appeal.deadline_days,
            "policies": [
                {"policy_id": policy.policy_id, "title": policy.title, "version": policy.version}
                for policy in payer.policies
            ],
        }
        for payer in payer_rules.values()
    ]
