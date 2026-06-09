from textwrap import dedent


def build_repair_prompt(*, error: str, bad_output: str) -> str:
    return dedent(f"""You returned invalid output. Fix it.

ERROR:
{error}

RULES:
- Return ONLY corrected JSON.
- Output must be a single JSON object.
- No markdown, no extra text.

PREVIOUS_OUTPUT:
{bad_output}
""")
