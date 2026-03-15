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

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
