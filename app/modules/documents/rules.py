"""Deterministic quality heuristics. No dictionary or language model is consulted."""

import re
from collections import Counter

from app.modules.documents.text_quality import assess_problem_characters


def assess_quality(text: str, image_percent: float, thresholds: dict[str, int]) -> dict:
    problems = assess_problem_characters(text)
    thai = sum("\u0e01" <= c <= "\u0e5b" for c in text if not c.isspace())
    characters = problems.non_whitespace_count
    quality = {
        "thai_percent": round(100 * thai / characters, 2) if characters else 0,
        "garbled_thai_percent": round(problems.percent, 2),
        "text_chars": characters,
        "image_percent": round(image_percent, 2),
    }
    # Decide with the same values exposed by the API (inclusive boundaries).
    failed = []
    # Historical snapshots keep their original minimum-Thai direction.
    thai_rule = (
        ("min_thai_percent", "thai_percent", True)
        if "min_thai_percent" in thresholds
        else ("max_thai_percent", "thai_percent", False)
    )
    for key, metric, minimum in (
        thai_rule,
        ("max_garbled_thai_percent", "garbled_thai_percent", False),
        ("min_text_chars", "text_chars", True),
        ("max_image_percent", "image_percent", False),
    ):
        if (
            (quality[metric] < thresholds[key])
            if minimum
            else (quality[metric] > thresholds[key])
        ):
            failed.append(key)
    return quality | {"failed": failed, "passed": not failed}


_SEPARATOR_ROW = re.compile(r"^[\s|:-]*-[\s|:-]*$")
_LABEL = re.compile(r"^([^:|\n]{1,80}):")
_LAYOUT = re.compile(r"[\s|]")
_HEADER_LINE_CHARS = 80


def same_content(plain: str, structured: str) -> bool:
    """True when pass 2 only re-laid out pass 1: no character added or substituted, and
    every pass-1 line kept, except a layout-frame header row turned into labels.
    Whitespace, pipes and separator rows are ignored.

    The header row may span several short pass-1 lines ("วาระที่", "หน่วยงาน",
    "ที่รับผิดชอบ"), one header may itself wrap over two lines, and an empty column's
    header never becomes a label. So a run of consecutive dropped lines is accepted when
    every line is short and the run, joined, holds a label."""
    flat = _LAYOUT.sub("", plain)
    labels, kept = [], []
    for line in structured.splitlines():
        if _SEPARATOR_ROW.match(line):
            continue
        match = _LABEL.match(line)
        label = _LAYOUT.sub("", match.group(1)) if match else ""
        # A label is a column header copied from the page, not text written with a colon.
        if label and label in flat and label + ":" not in flat:
            labels.append(label)
            line = line[match.end() :]
        kept.append(line)
    rebuilt = _LAYOUT.sub("", "".join(kept))
    if Counter(rebuilt) - Counter(flat):
        return False
    dropped: list[str] = []
    for line in [*plain.splitlines(), ""]:
        line = _LAYOUT.sub("", line)
        if line not in rebuilt:
            dropped.append(line)
            continue
        if dropped and not (
            all(len(d) <= _HEADER_LINE_CHARS for d in dropped)
            and any(label in "".join(dropped) for label in labels)
        ):
            return False
        dropped = []
    return True


# <br> and HTML table tags end a line or cell; inline tags only wrap text.
_BREAK_TAG = re.compile(
    r"</?(?:br|table|thead|tbody|tfoot|tr|td|th)\b[^>]*>", re.IGNORECASE
)
_INLINE_TAG = re.compile(r"</?(?:sup|sub|b|strong|i|em|u|p|span)\s*/?>", re.IGNORECASE)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")
# LaTeX tables: \multicolumn{n}{spec}{text} keeps text; \begin/\end{env}{spec} and \hline go;
# & separates cells and \\ ends a row.
_LATEX_TABLE = re.compile(
    r"\\(?:begin|end)\{(?:tabular|array|table)\*?\}|\\hline|\\multicolumn"
)
_LATEX_SPAN = re.compile(r"\\multi(?:column|row)\{[^{}]*\}\{[^{}]*\}\{([^{}]*)\}")
_LATEX_ENV = re.compile(
    r"\\(?:begin|end)\{(?:tabular|array|table)\*?\}(?:\{[^{}]*\})?|\\[hc]line(?:\{[^{}]*\})?"
)
_LATEX_BREAK = re.compile(r"\\\\|&")
# Edit marks pass 1 sometimes adds on its own (~~struck~~, ++underlined++). They are found
# too unreliably to keep (experiment 8), so they are removed and the text stays.
_STRUCK = re.compile(r"~~(.+?)~~", re.DOTALL)
_UNDERLINED = re.compile(r"\+\+(?=\S)(.+?)(?<=\S)\+\+", re.DOTALL)


def strip_markup(text: str) -> str:
    """Turn markup a plain transcription should not contain back into plain lines.
    Edit marks (~~struck~~, ++underlined++) are removed first, keeping their text and
    layout. <br> and HTML table tags end a line, simple inline tags are removed but their
    text stays, LaTeX tabular cells and rows become lines, and pipe-table cells become one
    line each without separator cells. Tables nested in a cell are flattened the same
    way. Blank lines are dropped, because tags and their indentation leave many. Text
    without markup is returned unchanged."""
    text = _UNDERLINED.sub(r"\1", _STRUCK.sub(r"\1", text)).replace("~~", "")
    if not (
        _BREAK_TAG.search(text)
        or _INLINE_TAG.search(text)
        or _LATEX_TABLE.search(text)
        or any(_TABLE_ROW.match(line) for line in text.splitlines())
    ):
        return text
    plain = _INLINE_TAG.sub("", _BREAK_TAG.sub("\n", text))
    if _LATEX_TABLE.search(plain):
        plain = _LATEX_SPAN.sub(r"\1", plain)
        plain = _LATEX_BREAK.sub("\n", _LATEX_ENV.sub("\n", plain))
    lines = []
    for line in plain.splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        lines.extend(c for c in cells if c and not _SEPARATOR_CELL.match(c))
    return "\n".join(lines)


def repair_tables(text: str) -> str:
    """Insert the separator row a Markdown pipe table needs after its header row when it
    is missing. Cell text is never changed."""
    lines = text.splitlines()
    repaired = []
    for i, line in enumerate(lines):
        repaired.append(line)
        starts_table = _TABLE_ROW.match(line) and not (
            i > 0 and _TABLE_ROW.match(lines[i - 1])
        )
        if not starts_table or _SEPARATOR_ROW.match(line):
            continue
        following = lines[i + 1] if i + 1 < len(lines) else ""
        if not _SEPARATOR_ROW.match(following):
            columns = line.strip().strip("|").count("|") + 1
            repaired.append("| " + " | ".join(["---"] * columns) + " |")
    return "\n".join(repaired)


def drop_empty_labels(plain: str, structured: str) -> str:
    """Remove lines that hold only a label the structuring pass added: a column header
    and a colon with no cell text. The label must also head a non-empty cell elsewhere,
    so a title written with a trailing colon is kept. A colon on the page is kept."""
    flat = _LAYOUT.sub("", plain)
    lines = structured.splitlines()
    empty, used = set(), set()
    for i, line in enumerate(lines):
        match = _LABEL.match(line)
        label = _LAYOUT.sub("", match.group(1)) if match else ""
        if label and label in flat and label + ":" not in flat:
            if line[match.end() :].strip():
                used.add(label)
            else:
                empty.add((i, label))
    drop = {i for i, label in empty if label in used}
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


_EDIT_MARK = re.compile(r"(~~|\+\+)")


def apply_edit_marks(
    text: str, marked: str, struck: int, underlined: int
) -> str | None:
    """Copy the ~~struck~~ / ++underlined++ marks of the mark pass onto text.

    The marks are kept only when there is exactly one pair per detected line of each kind
    and removing them gives back the text (whitespace ignored); otherwise None. They are
    re-inserted into text itself, so its spacing and tables are untouched. Runs split
    only by whitespace (one struck passage over several lines) are joined."""
    if _EDIT_MARK.search(text):
        return None
    if marked.count("~~") != 2 * struck or marked.count("++") != 2 * underlined:
        return None
    if re.sub(r"\s", "", _EDIT_MARK.sub("", marked)) != re.sub(r"\s", "", text):
        return None
    out, i, is_open = [], 0, {"~~": False, "++": False}
    for part in _EDIT_MARK.split(marked):
        if part in is_open:
            if not is_open[part]:  # an opening mark goes right before the next word
                while i < len(text) and text[i].isspace():
                    out.append(text[i])
                    i += 1
            out.append(part)
            is_open[part] = not is_open[part]
            continue
        for ch in part:
            if ch.isspace():
                continue
            while text[i].isspace():
                out.append(text[i])
                i += 1
            out.append(text[i])
            i += 1
    out.append(text[i:])
    joined = re.sub(r"~~(\s*)~~", r"\1", "".join(out))
    return re.sub(r"\+\+(\s*)\+\+", r"\1", joined)
