import json
import os

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
INJECT_MARKER = "const DIGEST_DATA = null; // __DIGEST_DATA_INJECT__"


def build(analysis_path: str, output_path: str) -> None:
    """
    Read analysis.json, inject it into the dashboard template,
    and write the result to output_path.
    """
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    if INJECT_MARKER not in template:
        raise ValueError(
            f"Injection marker not found in template: {TEMPLATE_PATH}\n"
            f"Expected to find: {INJECT_MARKER}"
        )

    json_blob = json.dumps(data, indent=2, ensure_ascii=False)
    replacement = f"const DIGEST_DATA = {json_blob};"
    html = template.replace(INJECT_MARKER, replacement)

    # Inject Open Graph meta values
    week_range = data.get("week_range", "")
    og_title = f"GK Developer Culture Briefing — {week_range}" if week_range else "GK Developer Culture Briefing"
    signals = data.get("key_signals", [])
    if signals:
        og_description = signals[0].get("description", "")
    else:
        og_description = "Weekly AI-powered cultural intelligence briefing for developer-focused marketing teams."
    html = html.replace("__OG_TITLE__", og_title.replace('"', "&quot;"))
    html = html.replace("__OG_DESCRIPTION__", og_description.replace('"', "&quot;"))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
