import json
import requests
import re
from typing import Optional

from extractor.context_store import get_context


def extract_json_block(text: str) -> str:
    """Extract the first JSON object found in text. Removes markdown fences and surrounding text."""
    if not text:
        return text

    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0).strip()
    return text.strip()


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "mistral"

SCHEMA_TEMPLATE = {
  "meta": {"request_id": "", "source": "SOW", "confidence_score": 0.0},
  "timeline": {"start_date": None, "end_date": None, "duration_weeks": 0},
  "detected_competencies": {
    "workfront_core": {"required": False, "weight": 0.0, "evidence": [], "why": []},
    "workfront_planning": {"required": False, "weight": 0.0, "evidence": [], "why": []},
    "workfront_fusion": {"required": False, "weight": 0.0, "evidence": [], "why": []},
    "integrations": {"required": False, "weight": 0.0, "evidence": [], "why": []},
    "aem": {"required": False, "weight": 0.0, "evidence": [], "why": []},
    "csc": {"required": False, "weight": 0.0, "evidence": [], "why": []},
    "migration": {"required": False, "weight": 0.0, "evidence": [], "why": []}
  },
  "notes": []
}


def build_prompt(*, request_id: str, filename: str, checksum: str, priority: str,
                 start_date: Optional[str], end_date: Optional[str], sow_text: str) -> str:
    schema_str = json.dumps(SCHEMA_TEMPLATE, indent=2)

    ctx = get_context(request_id)
    detected_facts = ctx.detected if ctx else {}
    facts_block = json.dumps(detected_facts, indent=2)

    return f"""You are a strict SOW extraction engine.

Return ONLY JSON matching the schema. No prose. No markdown. No code fences.

CRITICAL ACCURACY RULES:
- Do not invent facts. Only extract what is explicitly present in the SOW_TEXT.
- Evidence MUST be short exact phrases from SOW_TEXT.
- Weights must sum to 1.0 (if not, leave as-is; server will normalize deterministically).
- DETECTED_FACTS are produced by deterministic scan. If DETECTED_FACTS.<capability>.required is true, you MUST keep that capability required=true.
- For every required=true capability, include at least one evidence phrase from SOW_TEXT.

- For every competency where required=true, include a `why` field AS A LIST OF STRINGS.
- The `why` field must be an array (list), even if it contains only one sentence.
- Each item in the `why` list must be a concise natural-language sentence explaining why the competency is required, based only on SOW_TEXT.

- Do not restate the evidence verbatim; explain the reason in plain language.
- If a competency is not required, omit the `why` field.
- Populate the `notes` field with 1–3 concise sentences summarizing the overall scope of work.
- Notes must be derived strictly from SOW_TEXT.
- Notes should describe what the initiative is doing at a high level (e.g., intake standardization, planning enablement, execution, AEM, migration).
- Do NOT repeat competency names or weights.
- Do NOT restate evidence strings verbatim.
- If the scope is narrow, a single sentence is sufficient.
- You MUST NOT introduce any new top-level keys.
- The ONLY allowed top-level keys are: meta, timeline, detected_competencies, notes.
- Inside detected_competencies, you MUST include ALL competency keys exactly as provided in the schema, even if required=false.
- Do NOT add keys such as scope, activities, assumptions, or similar.

SCHEMA (fill values, keep keys exactly):
{schema_str}

DETECTED_FACTS (deterministic scan; cannot be overridden):
{facts_block}

REQUEST_METADATA:
- request_id: {request_id}
- filename: {filename}
- checksum: {checksum}
- priority: {priority}
- start_date: {start_date}
- end_date: {end_date}

SOW_TEXT:
<<<
{sow_text}
>>>
"""


def extract_requirements_via_ollama(*, request_id, filename, checksum, priority,
                                  start_date, end_date, sow_text) -> str:
    prompt = build_prompt(
        request_id=request_id,
        filename=filename,
        checksum=checksum,
        priority=priority,
        start_date=start_date,
        end_date=end_date,
        sow_text=sow_text,
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": -1,
        "options": {"temperature": 0, "top_p": 0.1, "num_predict": 2000, "num_ctx": 4096}
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=600)
    r.raise_for_status()
    data = r.json()
    content = (data.get("message", {}) or {}).get("content", "")
    return extract_json_block(content)
