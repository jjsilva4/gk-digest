import os
from datetime import datetime, timezone
from fpdf import FPDF

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"

MAX_BODY_CHARS = 3000
MAX_COMMENT_CHARS = 1000


def _clean(text: str) -> str:
    """Remove null bytes and other control characters that break PDF rendering."""
    if not text:
        return ""
    return "".join(c for c in text if c >= " " or c in "\n\t")


class DigestPDF(FPDF):
    def __init__(self, subreddit_name: str, week_range: str, post_count: int):
        super().__init__()
        self.subreddit_name = subreddit_name
        self.week_range = week_range
        self.post_count = post_count
        self.set_auto_page_break(auto=True, margin=15)
        self.add_font("Arial", "", FONT_REGULAR)
        self.add_font("Arial", "B", FONT_BOLD)
        self.add_font("Arial", "I", FONT_ITALIC)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Arial", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f"r/{self.subreddit_name}  |  {self.week_range}", align="L")
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Arial", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)

    def cover_page(self):
        self.add_page()
        self.set_font("Arial", "B", 32)
        self.set_y(60)
        self.cell(0, 14, f"r/{self.subreddit_name}", align="C")
        self.ln(10)
        self.set_font("Arial", "", 16)
        self.cell(0, 10, self.week_range, align="C")
        self.ln(8)
        self.set_font("Arial", "", 13)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"{self.post_count} qualifying posts", align="C")
        self.set_text_color(0, 0, 0)
        self.ln(6)
        self.set_font("Arial", "I", 10)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, "GK Digest  —  GitKraken Marketing", align="C")
        self.set_text_color(0, 0, 0)

    def add_post(self, post: dict, index: int):
        self.add_page()

        title = _clean(post["title"])
        score = post["score"]
        created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
        date_str = created.strftime("%b %d, %Y")
        url = _clean(post["url"])
        body = _clean(post["selftext"])
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "... [truncated]"

        # Post number badge
        self.set_font("Arial", "B", 9)
        self.set_fill_color(30, 30, 30)
        self.set_text_color(255, 255, 255)
        self.cell(20, 7, f"  #{index}", fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(9)

        # Title
        self.set_font("Arial", "B", 14)
        self.multi_cell(0, 7, title)
        self.ln(2)

        # Meta line
        self.set_font("Arial", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(0, 6, f"Score: {score:,}    Posted: {date_str}")
        self.ln(5)
        self.set_font("Arial", "I", 8)
        self.set_text_color(0, 0, 200)
        self.multi_cell(0, 5, url)
        self.set_text_color(0, 0, 0)
        self.ln(3)

        # Post body
        if body:
            self.set_font("Arial", "", 10)
            self.multi_cell(0, 5, body)
            self.ln(4)

        # Comments section
        if post["comments"]:
            self.set_font("Arial", "B", 10)
            self.set_fill_color(240, 240, 240)
            self.cell(0, 7, "  Top Comments", fill=True)
            self.ln(8)

            for i, comment in enumerate(post["comments"], 1):
                cbody = _clean(comment["body"])
                if len(cbody) > MAX_COMMENT_CHARS:
                    cbody = cbody[:MAX_COMMENT_CHARS] + "... [truncated]"
                cscore = comment["score"]

                self.set_font("Arial", "B", 9)
                self.set_text_color(60, 60, 60)
                self.cell(0, 5, f"Comment #{i}  |  Score: {cscore:,}")
                self.ln(5)
                self.set_font("Arial", "", 9)
                self.set_text_color(0, 0, 0)
                self.set_x(self.get_x() + 5)
                self.multi_cell(self.w - self.l_margin - self.r_margin - 5, 5, cbody)
                self.ln(2)

                for reply in comment.get("replies", []):
                    rbody = _clean(reply["body"])
                    if len(rbody) > MAX_COMMENT_CHARS:
                        rbody = rbody[:MAX_COMMENT_CHARS] + "... [truncated]"
                    rscore = reply["score"]

                    self.set_font("Arial", "I", 8)
                    self.set_text_color(100, 100, 100)
                    self.set_x(self.get_x() + 10)
                    self.cell(0, 4, f"Reply  |  Score: {rscore:,}")
                    self.ln(4)
                    self.set_font("Arial", "", 8)
                    self.set_x(self.get_x() + 10)
                    self.multi_cell(self.w - self.l_margin - self.r_margin - 10, 4, rbody)
                    self.ln(2)
                    self.set_text_color(0, 0, 0)

                self.ln(3)


def build_pdf(subreddit_name: str, posts: list[dict], output_path: str, week_range: str) -> None:
    pdf = DigestPDF(subreddit_name, week_range, len(posts))
    pdf.cover_page()

    for i, post in enumerate(posts, 1):
        pdf.add_post(post, i)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
