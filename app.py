from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal

from extractor.doc_reader import extract_text_from_bytes
from extractor.llm import extract_requirements_via_ollama
from extractor.validator import validate_and_repair
from extractor.capability_detector import detect_capabilities, normalize_text
from extractor.context_store import set_context

Priority = Literal["Urgent","High", "Normal", "Low","None"]

class ExtractSOWRequest(BaseModel):
    request_id: str = Field(..., description="Workfront Issue/Request ID")
    priority: Priority = Field(..., description="Derived from topic group")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    filename: str = Field(..., description="Original uploaded filename")
    file_bytes_base64: str = Field(..., description="Base64-encoded file bytes")

class ExtractSOWResponse(BaseModel):
    meta: dict
    timeline: dict
    detected_competencies: dict
    notes: list

app = FastAPI(title="AI Intake Service", version="0.2-accurate")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/extract-sow", response_model=ExtractSOWResponse)
def extract_sow(payload: ExtractSOWRequest):
    try:
        sow_text, checksum = extract_text_from_bytes(payload.filename, payload.file_bytes_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read document: {e}")

    # Deterministic capability scan (accuracy layer)
    detected = detect_capabilities(sow_text)
    sow_norm = normalize_text(sow_text)
    set_context(payload.request_id, sow_text_raw=sow_text, sow_text_norm=sow_norm, detected=detected)

    llm_raw = extract_requirements_via_ollama(
        request_id=payload.request_id,
        filename=payload.filename,
        checksum=checksum,
        priority=payload.priority,
        start_date=payload.start_date,
        end_date=payload.end_date,
        sow_text=sow_text,
    )

    try:
        validated = validate_and_repair(llm_raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"LLM extraction invalid after repair attempts: {e}")

    return validated
