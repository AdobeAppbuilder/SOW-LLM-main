"""Deterministic capability detection (section-aware, signal-based).

This is the accuracy layer:
- Detects capabilities across the entire document (not just tables).
- Uses multiple signals to avoid false positives from single-token mentions.
- Returns explainable evidence + signals.

It does NOT do weight math; weights remain an LLM suggestion + deterministic normalization.
"""

from __future__ import annotations

import re
import html
from typing import Dict, List

CAP_KEYS = [
    "workfront_core",
    "workfront_planning",
    "workfront_fusion",
    "integrations",
    "aem",
    "csc",
    "migration",
]

HIGH_SIGNAL_HEADERS = [
    "scope",
    "in scope",
    "out of scope",
    "activities",
    "activities and deliverables",
    "activities and deliverables",
    "deliverables",
    "products and services",
    "statement of work",
]

NEGATION_PATTERNS = [
    r"out of scope",
    r"not in scope",
    r"excluded",
    r"not included",
    r"future phase",
    r"later phase",
]

CAPABILITY_DEFS: Dict[str, Dict] = {
    "aem": {
        "aliases": ["adobe experience manager", "aem", "aem sites", "aem cloud service", "edge delivery", "edge delivery services", "eds"],
        "strong_phrases": ["adobe experience manager (aem)", "aem-related activities", "aem cloud service", "edge delivery"],
        "activity_verbs": ["implement", "implementation", "migrate", "migration", "governance", "architecture", "code review", "go-live", "readiness", "templates", "components", "blocks"],
        "threshold_required": 6,
        "threshold_mentioned": 3,
    },
    "workfront_core": {
        "aliases": ["workfront core", "intake & request management", "intake and request management", "execution alignment", "controlled conversion", "projects and tasks"],
        "strong_phrases": ["intake & request management", "execution alignment"],
        "activity_verbs": ["routing", "governance", "conversion", "request"],
        "threshold_required": 4,
        "threshold_mentioned": 2,
    },
    "workfront_planning": {
        "aliases": ["workfront planning", "planning enablement", "planning & prioritization", "planning and prioritization", "planning records", "dependencies", "timelines", "scenarios"],
        "strong_phrases": ["planning enablement", "planning & prioritization"],
        "activity_verbs": ["prioritization", "planning", "dependencies"],
        "threshold_required": 4,
        "threshold_mentioned": 2,
    },
    "workfront_fusion": {
        "aliases": ["workfront fusion", "fusion", "automation & validation", "automation and validation", "scenario", "webhook"],
        "strong_phrases": ["automation & validation", "workfront fusion"],
        "activity_verbs": ["automation", "webhook", "error handling", "validation"],
        "threshold_required": 4,
        "threshold_mentioned": 2,
    },
    "integrations": {
        "aliases": ["integrations", "integrations & data flow", "api-based", "api based", "connector", "integration"],
        "strong_phrases": ["integrations & data flow", "api-based"],
        "activity_verbs": ["api", "sync", "integration"],
        "threshold_required": 3,
        "threshold_mentioned": 2,
    },
    "migration": {
        "aliases": ["migration", "migrate", "legacy transition", "stabilization", "change enablement"],
        "strong_phrases": ["migration & change enablement", "csc / migration"],
        "activity_verbs": ["migration", "transition", "stabilization"],
        "threshold_required": 4,
        "threshold_mentioned": 2,
    },
    "csc": {
        "aliases": ["csc", "csc / migration", "customer success cloud"],
        "strong_phrases": ["csc / migration"],
        "activity_verbs": ["adoption", "enablement"],
        "threshold_required": 3,
        "threshold_mentioned": 2,
    },
}


def normalize_text(text: str) -> str:
    t = html.unescape(text)
    t = t.casefold()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _section_boost(norm_text: str) -> int:
    score = 0
    for h in HIGH_SIGNAL_HEADERS:
        if h in norm_text:
            score += 1
    return score


def _negation_penalty(window: str) -> int:
    for pat in NEGATION_PATTERNS:
        if re.search(pat, window):
            return 5
    return 0


def detect_capabilities(raw_text: str) -> dict:
    norm = normalize_text(raw_text)
    base_section = _section_boost(norm)

    results = {}
    for key in CAP_KEYS:
        spec = CAPABILITY_DEFS.get(key, {})
        aliases = spec.get('aliases', [])
        strong = spec.get('strong_phrases', [])
        verbs = spec.get('activity_verbs', [])

        score = 0
        signals: List[str] = []
        evidence: List[str] = []

        for a in aliases:
            if a and a.casefold() in norm:
                score += 1
                if len(evidence) < 5:
                    evidence.append(a)

        for sp in strong:
            if sp and sp.casefold() in norm:
                score += 4
                signals.append(f"Strong phrase: {sp}")
                if sp not in evidence and len(evidence) < 5:
                    evidence.append(sp)

        if score > 0 and verbs:
            for v in verbs:
                if v and v.casefold() in norm:
                    score += 1
                    signals.append(f"Activity verb: {v}")
                    break

        if score > 0 and base_section:
            score += min(2, base_section)
            signals.append("High-signal sections present")

        penalty = 0
        for sp in strong:
            idx = norm.find(sp.casefold())
            if idx != -1:
                window = norm[max(0, idx-120): idx+120]
                penalty = max(penalty, _negation_penalty(window))
        if penalty:
            score = max(0, score - penalty)
            signals.append("Negation cue detected")

        thr_req = spec.get('threshold_required', 4)
        thr_ment = spec.get('threshold_mentioned', 2)

        required = score >= thr_req
        confidence = "high" if score >= (thr_req + 3) else ("medium" if required else ("low" if score >= thr_ment else "none"))

        results[key] = {
            "required": bool(required),
            "score": int(score),
            "confidence": confidence,
            "evidence": evidence[:5],
            "signals": signals[:6],
        }

    # Coupling rule
    if "csc / migration" in norm:
        for k in ("csc", "migration"):
            results[k]["required"] = True
            if "csc / migration" not in results[k]["evidence"]:
                results[k]["evidence"].insert(0, "csc / migration")
            results[k]["signals"].append("Coupling rule: CSC / Migration")
            results[k]["confidence"] = "high"

    return results
