import json
import html

from extractor.schema import Step1Output
from extractor.context_store import get_context
from extractor.schema import COMPETENCY_KEYS

def normalize_weights(obj: dict) -> None:
    """
    Normalize weights to sum to 1.0, with a guardrail:
    - If required=true and evidence exists but weight=0, assign a small non-zero
      weight based on deterministic document-emphasis score (not hard-coded).
    - Preserve LLM's relative weights among non-zero items.
    """
    comps = obj.get("detected_competencies", {})
    meta = obj.get("meta", {}) or {}
    req_id = meta.get("request_id")

    # Current weights
    w = {k: float(v.get("weight", 0.0) or 0.0) for k, v in comps.items()}

    # Identify "required but invisible" items (must have evidence)
    zero_required = [
        k for k, v in comps.items()
        if v.get("required") is True
        and float(v.get("weight", 0.0) or 0.0) == 0.0
        and (v.get("evidence") or [])
    ]

    nonzero_keys = [k for k in comps.keys() if w.get(k, 0.0) > 0.0]
    total_nonzero = sum(w[k] for k in nonzero_keys)

    # If nothing to guardrail, normal normalization only
    if not zero_required:
        if total_nonzero > 0:
            for k in comps:
                comps[k]["weight"] = w.get(k, 0.0) / total_nonzero
        return

    # Get deterministic emphasis scores (from detector context); fallback to 1.0
    det_scores = {k: 1.0 for k in zero_required}
    if req_id:
        ctx = get_context(req_id)
        if ctx and getattr(ctx, "detected", None):
            for k in zero_required:
                det_scores[k] = float(ctx.detected.get(k, {}).get("score", 1.0) or 1.0)

    score_sum = sum(det_scores.values()) or 1.0

    # Small pool reserved for required-but-zero items
    SUPPORTING_POOL = 0.15

    # If LLM provided some non-zero weights, scale them down to make room
    if total_nonzero > 0:
        scale = (1.0 - SUPPORTING_POOL) / total_nonzero
        for k in nonzero_keys:
            w[k] = w[k] * scale
    else:
        # LLM gave all zeros; distribute full 1.0 by deterministic score
        SUPPORTING_POOL = 1.0

    # Distribute pool among required-but-zero items by deterministic score
    for k in zero_required:
        w[k] = (det_scores[k] / score_sum) * SUPPORTING_POOL

    # Assign normalized weights (NO early rounding)
    total = sum(w.values()) or 1.0
    for k in comps:
        comps[k]["weight"] = float(w.get(k, 0.0)) / total

    # ✅ Final correction: force exact sum to 1.0 (prevents schema failures)
    keys = list(comps.keys())
    if keys:
        current_sum = sum(float(comps[k]["weight"]) for k in keys)
        delta = 1.0 - current_sum
        # add delta to the largest weight (most stable)
        max_k = max(keys, key=lambda kk: float(comps[kk]["weight"]))
        comps[max_k]["weight"] = float(comps[max_k]["weight"]) + delta


def enforce_facts_and_evidence(obj: dict) -> None:
    meta = obj.get("meta", {}) or {}
    req_id = meta.get("request_id")
    if not req_id:
        return

    ctx = get_context(req_id)
    if not ctx:
        return

    sow_norm = ctx.sow_text_norm
    facts = ctx.detected or {}
    comps = obj.get("detected_competencies", {})

    # ✅ Safety-net: ensure all expected competency keys exist
    for k in COMPETENCY_KEYS:
        comps.setdefault(
            k,
            {
                "required": False,
                "weight": 0.0,
                "evidence": [],
                "why": []
            }
        )

    # ✅ Remove any unexpected competency keys
    for bad_key in list(comps.keys()):
        if bad_key not in COMPETENCY_KEYS:
            print(f"[VALIDATOR] Removing unexpected competency key: {bad_key}")
            comps.pop(bad_key, None)

    print(
        "[VALIDATOR] Competency keys after safety-net:",
        list(comps.keys())
    )

    # ✅ Normalize "why" to List[str]
    for c in comps.values():
        why_val = c.get("why")
        if isinstance(why_val, str):
            c["why"] = [why_val]
        elif why_val is None:
            c["why"] = []
        elif isinstance(why_val, list):
            c["why"] = [str(x) for x in why_val]

    # ✅ Enforce deterministic required flags
    for key, fact in facts.items():
        if key in comps and fact.get("required") is True:
            comps[key]["required"] = True
            if not comps[key].get("evidence"):
                comps[key]["evidence"] = list(fact.get("evidence", []))[:3]

    # ✅ Evidence validation + grounding
    for key, c in comps.items():
        ev = c.get("evidence") or []
        cleaned = []

        for e in ev:
            if not e:
                continue
            e_norm = html.unescape(str(e)).casefold().strip()
            if e_norm and e_norm in sow_norm:
                cleaned.append(html.unescape(str(e)))

        if c.get("required") and not cleaned:
            det = facts.get(key, {})
            cleaned = list(det.get("evidence", []))[:3]

        cleaned.sort(key=len, reverse=True)
        c["evidence"] = cleaned


def validate_and_repair(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        raise RuntimeError("LLM returned empty output (no JSON).")

    try:
        obj = json.loads(raw_text)

        # ✅ Normalize alternate key name
        if "competencies" in obj and "detected_competencies" not in obj:
            obj["detected_competencies"] = obj.pop("competencies")

        # ✅ Guarantee detected_competencies shape
        if "detected_competencies" not in obj or not isinstance(obj["detected_competencies"], dict):
            obj["detected_competencies"] = {}

        # ✅ Normalize notes to List[str]
        notes_val = obj.get("notes")

        if isinstance(notes_val, dict):
            flattened = []
            for v in notes_val.values():
                if isinstance(v, list):
                    flattened.extend([str(x) for x in v])
                elif isinstance(v, str):
                    flattened.append(v)
            obj["notes"] = flattened

        elif isinstance(notes_val, str):
            obj["notes"] = [notes_val]

        elif notes_val is None:
            obj["notes"] = []

        elif isinstance(notes_val, list):
            obj["notes"] = [str(x) for x in notes_val]

        # ✅ Strip illegal top-level keys
        allowed_top_keys = {"meta", "timeline", "detected_competencies", "notes"}
        for k in list(obj.keys()):
            if k not in allowed_top_keys:
                print(
                    f"[VALIDATOR] LLM returned illegal top-level key '{k}', stripping it"
                )
                obj.pop(k, None)

        enforce_facts_and_evidence(obj)
        normalize_weights(obj)

        validated = Step1Output.model_validate(obj)
        
        print(
            "[WEIGHTS]",
             {
                k: v["weight"]
                for k, v in validated.model_dump()["detected_competencies"].items()
             }
            )

        return validated.model_dump()

    except Exception as e:
        raise RuntimeError(
            f"Validation failed after deterministic correction: {e}"
        )