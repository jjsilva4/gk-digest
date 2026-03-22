import json
import os
from pathlib import Path

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
INJECT_MARKER = "const DIGEST_DATA = null; // __DIGEST_DATA_INJECT__"


def _render_html(data: dict) -> str:
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

    week_range = data.get("week_range", "")
    og_title = f"GK Developer Culture Briefing — {week_range}" if week_range else "GK Developer Culture Briefing"
    signals = data.get("key_signals", [])
    if signals:
        og_description = signals[0].get("description", "")
    else:
        og_description = "Weekly AI-powered cultural intelligence briefing for developer-focused marketing teams."
    html = html.replace("__OG_TITLE__", og_title.replace('"', "&quot;"))
    html = html.replace("__OG_DESCRIPTION__", og_description.replace('"', "&quot;"))
    return html


def build(analysis_path: str, output_path: str, archive_options: list[dict] | None = None) -> None:
    """
    Read analysis.json, inject it into the dashboard template,
    and write the result to output_path.
    """
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if archive_options:
        data["archive_options"] = archive_options

    html = _render_html(data)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def discover_archive_entries(output_base: str, docs_dir: str) -> list[dict]:
    """
    Find all completed digests by scanning output/*/analysis.json and produce
    dropdown entries plus archive page destinations.
    """
    entries = []
    output_root = Path(output_base)

    if not output_root.exists():
      return entries

    for analysis_file in sorted(output_root.glob("*/analysis.json")):
        run_dir = analysis_file.parent
        with open(analysis_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        run_key = run_dir.name
        archive_rel = f"digests/{run_key}.html"
        entries.append({
            "run_key": run_key,
            "analysis_path": str(analysis_file),
            "archive_output_path": str(Path(docs_dir) / archive_rel),
            "archive_url": archive_rel,
            "label": f"Week of {data.get('week_range', run_key)}",
            "week_range": data.get("week_range", run_key),
        })

    entries.sort(key=lambda entry: entry["run_key"])
    return entries
