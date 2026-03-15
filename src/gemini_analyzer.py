import os
import json
import time
import logging
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

BATCH_SIZE = 10

# ── Prompts ────────────────────────────────────────────────────────────────────

PROMPT_BATCH_LOADER = """
You are performing cultural analysis of developer communities using netnographic methodology.

Analyze the uploaded PDFs. Each PDF contains top Reddit posts and comments from one subreddit.

For each subreddit, produce a structured cultural report.

Extract:
1. Beliefs — recurring values, concerns, or worldviews expressed by the community
2. Artifacts — tools, libraries, projects, or technologies being actively discussed
3. Rituals — repeated behaviors or practices (e.g. "weekly thread", "share your setup")
4. Language — jargon, phrases, or terms unique or notable in the community

Preserve source links from the posts wherever available.

Output a JSON array. Each element must match this schema exactly:
{
  "subreddit": "",
  "community_summary": "",
  "beliefs": [{"belief": "", "source_links": []}],
  "artifacts": [{"name": "", "links": []}],
  "rituals": [],
  "language": []
}

Output only the JSON array. No markdown, no explanation, no code fences.
""".strip()

PROMPT_COMPRESS = """
Compress each subreddit cultural report into a Cultural Snapshot.
Limit to 250 tokens per subreddit.

Output a JSON array. Each element must match this schema exactly:
{
  "subreddit": "",
  "summary": "",
  "top_beliefs": [],
  "top_artifacts": [],
  "top_rituals": [],
  "top_language": [],
  "evidence_links": []
}

Rules:
- Preserve at least 3 evidence_links per subreddit (Reddit post URLs from the original data)
- Remove redundancy, keep plain language
- Do not invent content — only compress what was in the input

Output only the JSON array. No markdown, no explanation, no code fences.
""".strip()

PROMPT_BATCH_SUMMARY = """
You are synthesizing cultural research across multiple developer subreddits.

Analyze the cultural snapshots provided. Identify patterns shared across multiple communities.

Output a single JSON object matching this schema exactly:
{
  "batch_id": "",
  "shared_beliefs": [],
  "shared_artifacts": [],
  "shared_rituals": [],
  "shared_language": [],
  "notable_differences": [],
  "evidence_links": []
}

Rules:
- Only include patterns that appear in 2 or more subreddits
- Preserve at least 5 evidence_links (real Reddit URLs from the input)
- Keep entries concise and plain-language

Output only the JSON object. No markdown, no explanation, no code fences.
""".strip()

PROMPT_DASHBOARD = """
You are producing the final dataset for a weekly developer culture briefing dashboard.

Week: {week_range}

Using the batch cultural summaries provided, identify the most significant and interesting
patterns across the developer community this week.

Output a single JSON object matching this schema EXACTLY — field names, types, and nesting
must match precisely:

{{
  "topics": [
    {{
      "icon": "<single emoji best representing this topic>",
      "title": "<headline, present tense, 6-12 words>",
      "description": "<2-3 sentences explaining the trend in plain language for a marketing audience>",
      "tags": ["r/subreddit1", "r/subreddit2"],
      "source_keys": ["key1", "key2"]
    }}
  ],
  "lingo": [
    {{
      "term": "<the phrase or word>",
      "tooltip": "<full definition 2-3 sentences — shown on hover>",
      "meaning": "<one-line plain English meaning>",
      "origin": "r/sub1 · r/sub2"
    }}
  ],
  "artifacts": [
    {{
      "icon": "<single emoji>",
      "name": "<artifact, tool, or topic name>",
      "description": "<2-3 sentences on why it is being shared this week>",
      "examples_label": "<'Projects mentioned' OR 'Tools mentioned' OR 'Concepts mentioned'>",
      "examples": ["name1", "name2", "name3"],
      "source_keys": ["key1", "key2"]
    }}
  ],
  "concerns": [
    {{
      "title": "<concern in 5-10 words>",
      "description": "<2-3 sentences describing the concern and which communities feel it>"
    }}
  ],
  "sources": {{
    "<short_key>": {{
      "sub": "r/<subreddit>",
      "label": "<category label, 2-3 words, title case>",
      "title": "<exact thread title from the PDF>",
      "url": "<full Reddit URL from the evidence_links in the input>"
    }}
  }}
}}

Requirements:
- Produce exactly 4-6 topics
- Produce exactly 6-10 lingo terms
- Produce exactly 3-4 artifacts
- Produce exactly 3 concerns
- Produce 8-12 sources
- Every source_key used in topics[].source_keys and artifacts[].source_keys MUST exist as a key in "sources"
- All URLs in sources must be real Reddit URLs found in the input evidence_links
- All content must be grounded in actual discussions — do not invent threads or claims
- Write for a non-technical marketing audience who wants cultural intelligence about developers

Output only the JSON object. No markdown, no explanation, no code fences.
""".strip()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wait_for_active(client: genai.Client, file_ref, logger: logging.Logger):
    """Poll until a Gemini file leaves PROCESSING state."""
    for _ in range(30):
        state = getattr(file_ref.state, "name", str(file_ref.state))
        if state != "PROCESSING":
            break
        time.sleep(4)
        file_ref = client.files.get(name=file_ref.name)
    state = getattr(file_ref.state, "name", str(file_ref.state))
    if state != "ACTIVE":
        raise RuntimeError(f"File {file_ref.name} stuck in state {state}")
    return file_ref


def _generate(client: genai.Client, model_name: str, parts: list,
              logger: logging.Logger) -> str:
    """Call generate_content with up to 3 retries on transient errors."""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=parts,
            )
            return response.text
        except Exception as e:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                logger.warning(f"  Gemini error (attempt {attempt + 1}): {e} — retrying in {wait}s")
                time.sleep(wait)
            else:
                raise


def _parse_json(text: str):
    """Strip markdown fencing and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def _save(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── Pipeline ───────────────────────────────────────────────────────────────────

def run_pipeline(run_dir: str, week_range: str, batch_size: int, model_name: str,
                 logger: logging.Logger) -> str:
    """
    Run the full 4-step Gemini analysis pipeline.
    Returns the path to analysis.json in run_dir.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    pdf_dir = Path(run_dir)
    pdfs = sorted(pdf_dir.glob("*.pdf"))

    if not pdfs:
        raise ValueError(f"No PDFs found in {run_dir}")

    logger.info(f"Gemini pipeline: {len(pdfs)} PDFs, batch_size={batch_size}, model={model_name}")

    batches = [pdfs[i:i + batch_size] for i in range(0, len(pdfs), batch_size)]
    all_snapshots = []

    # ── Steps 1 + 2: per-batch extraction + compression ──
    for batch_idx, batch in enumerate(batches):
        batch_num = batch_idx + 1
        logger.info(f"  Batch {batch_num}/{len(batches)}: uploading {len(batch)} PDFs...")

        file_refs = []
        for pdf_path in batch:
            logger.info(f"    Uploading {pdf_path.name}...")
            ref = client.files.upload(
                file=str(pdf_path),
                config=types.UploadFileConfig(mime_type="application/pdf"),
            )
            ref = _wait_for_active(client, ref, logger)
            file_refs.append(ref)

        # Step 1: cultural extraction
        logger.info(f"  Batch {batch_num}: extracting cultural data...")
        raw_text = _generate(client, model_name, file_refs + [PROMPT_BATCH_LOADER], logger)
        _save(os.path.join(run_dir, f"batch_{batch_num}_raw.json"), raw_text)

        # Step 2: compress to snapshots
        logger.info(f"  Batch {batch_num}: compressing snapshots...")
        compressed_text = _generate(
            client, model_name,
            [PROMPT_COMPRESS + "\n\nInput data:\n" + raw_text],
            logger,
        )
        _save(os.path.join(run_dir, f"batch_{batch_num}_snapshot.json"), compressed_text)

        try:
            snapshots = _parse_json(compressed_text)
            if isinstance(snapshots, list):
                all_snapshots.extend(snapshots)
            else:
                all_snapshots.append(snapshots)
        except json.JSONDecodeError as e:
            logger.warning(f"  Batch {batch_num}: JSON parse warning for snapshots: {e}")
            all_snapshots.append({"raw": compressed_text})

        # Delete uploaded files to free quota
        for ref in file_refs:
            try:
                client.files.delete(name=ref.name)
            except Exception:
                pass

    # ── Step 3: batch summaries (one per batch) ──
    batch_summary_texts = []
    snapshot_batches = [
        all_snapshots[i:i + batch_size] for i in range(0, len(all_snapshots), batch_size)
    ]
    for batch_idx, snap_batch in enumerate(snapshot_batches):
        batch_num = batch_idx + 1
        logger.info(f"  Summary {batch_num}/{len(snapshot_batches)}: synthesizing patterns...")
        snap_text = json.dumps(snap_batch, indent=2, ensure_ascii=False)
        summary_text = _generate(
            client, model_name,
            [PROMPT_BATCH_SUMMARY + "\n\nSnapshots:\n" + snap_text],
            logger,
        )
        _save(os.path.join(run_dir, f"batch_{batch_num}_summary.json"), summary_text)
        batch_summary_texts.append(summary_text)

    # ── Step 4: final dashboard dataset ──
    logger.info("  Final step: generating dashboard dataset...")
    all_summaries = "\n\n---\n\n".join(batch_summary_texts)
    final_prompt = PROMPT_DASHBOARD.format(week_range=week_range)
    dashboard_text = _generate(
        client, model_name,
        [final_prompt + "\n\nBatch summaries:\n" + all_summaries],
        logger,
    )

    try:
        dashboard_data = _parse_json(dashboard_text)
    except json.JSONDecodeError as e:
        logger.error(f"  Failed to parse final dashboard JSON: {e}")
        _save(os.path.join(run_dir, "analysis_raw.txt"), dashboard_text)
        raise

    dashboard_data["week_range"] = week_range

    analysis_path = os.path.join(run_dir, "analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=2, ensure_ascii=False)

    logger.info(f"  Analysis complete → {analysis_path}")
    return analysis_path
