import requests

from extractor.llm import extract_json_block

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "mistral"


def call_ollama_raw(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "top_p": 0.1, "num_predict": 2048, "num_ctx": 4096}
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    content = (data.get("message", {}) or {}).get("content", "")
    return extract_json_block(content)
