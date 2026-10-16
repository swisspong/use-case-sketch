"""Find struck-through and underlined text on a rendered page, from pixels only.

Vision models miss thin lines, so code finds them and the mark pass only reads the words
inside the boxes drawn here (docs/ocr-table-structure-experiment.md, experiments 8-9).
Table borders, rules and signature strokes are rejected. Thresholds are relative to the
page size and were tuned on a few scans: anything doubtful is dropped, never guessed.
"""

import io
import re
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, UnidentifiedImageError

_DARK = 140  # grey level below which a pixel is ink


@dataclass(frozen=True)
class EditLine:
    kind: Literal["strike", "underline"]
    top: int
    bottom: int
    left: int
    right: int
    # Lines that continue one marked passage onto the next text line share a run.
    run: int = 0


def find_edit_lines(png: bytes) -> list[EditLine]:
    try:
        page = Image.open(io.BytesIO(png)).convert("L")
    except (UnidentifiedImageError, OSError, ValueError):
        return []
    ink = page.point(lambda v: 1 if v < _DARK else 0)
    w, h = ink.size
    data = ink.tobytes()
    rows = [data[y * w : (y + 1) * w] for y in range(h)]
    columns = ink.transpose(Image.Transpose.TRANSPOSE).tobytes()
    # Page-long vertical strokes are table borders; they split the page into cells.
    borders = [x for x in range(w) if columns[x * h : (x + 1) * h].count(1) > 0.4 * h]

    min_run = max(20, w // 55)  # longer than any stroke inside a letter
    run = re.compile(rb"\x01{%d,}" % min_run)
    segments: list[list[int]] = []  # [top, bottom, left, right]
    for y, row in enumerate(rows):
        for m in run.finditer(row):
            x0, x1 = m.span()
            for s in segments:
                overlap = min(x1, s[3]) - max(x0, s[2])
                if y - s[1] <= 1 and overlap > 0.6 * min(x1 - x0, s[3] - s[2]):
                    s[1], s[2], s[3] = y, min(s[2], x0), max(s[3], x1)
                    break
            else:
                segments.append([y, y, x0, x1])
    segments = _join_collinear(segments, min_run // 2)

    gap, band, reach = max(2, h // 1000), max(6, h // 200), h // 60

    def density(y0: int, y1: int, x0: int, x1: int) -> float:
        y0, y1 = max(0, y0), min(h, y1)
        dark = sum(rows[y][x0:x1:2].count(1) for y in range(y0, y1))
        return dark / max(1, (y1 - y0) * (x1 - x0) / 2)

    def corner(x: int, top: int, bottom: int) -> bool:
        for cx in range(max(0, x - 4), min(w, x + 5)):
            column = columns[cx * h : (cx + 1) * h]
            up = len(column[:top]) - len(column[:top].rstrip(b"\x01"))
            down = len(column[bottom + 1 :]) - len(column[bottom + 1 :].lstrip(b"\x01"))
            if (up >= reach and down >= reach) or up + down >= 3 * reach:
                return True
        return False

    found = []
    for top, bottom, left, right in segments:
        if right - left < w // 40:  # shorter than a short word: dash, signature stroke
            continue
        if bottom - top > max(5, h // 450):  # too thick for a pen or strike line
            continue
        cell_left = max([b for b in borders if b <= left], default=0)
        cell_right = min([b for b in borders if b >= right], default=w)
        if right - left > 0.97 * (cell_right - cell_left):  # a row border of the cell
            continue
        if density(top - gap - band, top - gap, left, right) < 0.04:  # no text on it
            continue
        if corner(left, top, bottom) or corner(right - 1, top, bottom):  # table corner
            continue
        # Text must sit on most of the line; a border runs on past the text.
        step = 3 * band
        chunks = range(left, right, step)
        covered = sum(
            density(top - gap - band, top - gap, c, min(c + step, right)) >= 0.02
            for c in chunks
        )
        if covered < 0.75 * len(chunks):
            continue
        below = density(bottom + gap, bottom + gap + band, left, right)
        kind = "strike" if below >= 0.04 else "underline"
        # Where the text of this line starts and ends inside the cell (ragged right).
        text_rows = (
            range(top - band, bottom + band)
            if kind == "strike"
            else range(top - 2 * band, top - gap)
        )
        lo, hi = cell_left + 4, cell_right - 4
        firsts, lasts = [], []
        for y in text_rows:
            if 0 <= y < h and (first := rows[y].find(1, lo, hi)) >= 0:
                firsts.append(first)
                lasts.append(rows[y].rfind(1, lo, hi))
        found.append(
            (
                EditLine(kind, top, bottom, left, right),
                cell_left,
                bool(firsts) and left - min(firsts) <= w // 60,
                bool(lasts) and max(lasts) - right <= w // 60,
            )
        )
    return _number_runs(found, max_pitch=h // 25)


def _number_runs(found, max_pitch: int) -> list[EditLine]:
    """A line that reaches the end of its text line, followed on the next text line of
    the same cell by a line of the same kind starting at the line start, is one run."""
    lines: list[EditLine] = []
    previous: dict[tuple[str, int], tuple[EditLine, bool]] = {}
    run = -1
    for line, cell, starts, ends in sorted(found, key=lambda f: (f[1], f[0].top)):
        before = previous.get((line.kind, cell))
        continues = (
            before is not None
            and before[1]
            and starts
            and 0 < line.top - before[0].top <= max_pitch
        )
        if not continues:
            run += 1
        numbered = EditLine(
            **{**line.__dict__, "run": before[0].run if continues else run}
        )
        lines.append(numbered)
        previous[(line.kind, cell)] = (numbered, ends)
    return sorted(lines, key=lambda line: (line.top, line.left))


def draw_edit_boxes(png: bytes, lines: list[EditLine]) -> bytes:
    """The page with a red box around struck text and a blue box around underlined text."""
    page = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(page)
    up, down = page.height // 90, page.height // 300
    for line in lines:
        if line.kind == "strike":
            box, colour = (line.top - up // 2, line.bottom + up // 2), (230, 0, 0)
        else:
            box, colour = (line.top - up, line.bottom + down), (0, 80, 255)
        draw.rectangle(
            [line.left - 4, box[0], line.right + 4, box[1]], outline=colour, width=3
        )
    out = io.BytesIO()
    page.save(out, format="PNG")
    return out.getvalue()


def _join_collinear(segments: list[list[int]], max_gap: int) -> list[list[int]]:
    """Descenders touching a border split it into pieces; join pieces on one line."""
    joined: list[list[int]] = []
    for s in sorted(segments, key=lambda s: (s[0], s[2])):
        for j in joined:
            same_line = abs(s[0] - j[0]) <= 2 and abs(s[1] - j[1]) <= 3
            if same_line and s[2] - j[3] <= max_gap and s[3] >= j[2]:
                j[:] = [
                    min(j[0], s[0]),
                    max(j[1], s[1]),
                    min(j[2], s[2]),
                    max(j[3], s[3]),
                ]
                break
        else:
            joined.append(list(s))
    return joined
