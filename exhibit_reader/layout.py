"""Page layout analysis: drop logo / side tab / page number / booth legend, split the two
text columns and return body lines in reading order (left column, then right column).

Section headers (category boxes) are emitted as marker lines starting with CAT_MARK so the
parser can assign categories; every other returned line is plain OCR text.
"""
from __future__ import annotations

import re
from statistics import median

from .models import Settings
from .ocr_engine import OcrBox

CAT_MARK = "##CATEGORY## "

_LOGO_RE = re.compile(r"中国进出|进出口.{0,2}品交易会|IMPORT\s*AND\s*EXPORT\s*FAIR|^Since\s*19\d\d$", re.I)
_LEGEND_RE = re.compile(
    r"Booth\s*Legend|展位位置|^Hall\b|展厅|^Floor|楼层|^Aisle|通道$|Booth\s*Number|^展位号$|温馨提示|"
    r"内销意愿|表示参展|\(\s*Note\s*\)|^Note\b|means the exhibitor|intention of domestic|domestic sale$|^\d\.\d[A-Z]\d{2}$",
    re.I)
_PAGE_RE = re.compile(r"^\s*(\d{3})\d?\s*$")
_CJK_RE = re.compile(r"[㐀-鿿]")
_START_HINT = re.compile(r"^\s*\*?\s*[(（]\s*\d")
_FIELD_HINT = re.compile(r"TEL|FAX|MA[IlL1]{2}|URL|www|邮|编码|@|\d{3}", re.I)


def _is_vertical(b: OcrBox) -> bool:
    return (b.y1 - b.y0) > 1.6 * (b.x1 - b.x0)


def page_info(boxes: list[OcrBox], image_width: int, image_height: int, settings: Settings) -> dict:
    """Printed page number, area letter and side-tab category of one page."""
    w, h = image_width, image_height
    info = {"page_no": "", "area": "", "category_cn": "", "category_en": ""}
    pages = [b for b in boxes if b.cy > 0.75 * h and _PAGE_RE.match(b.text)]
    if pages:
        info["page_no"] = _PAGE_RE.match(max(pages, key=lambda b: b.cy).text).group(1)
    tab = sorted((b for b in boxes if b.cx > (1 - settings.side_tab_ratio) * w and b.cy < 0.9 * h
                  and b.score >= max(settings.min_confidence, 0.5)),
                 key=lambda b: b.cy)
    cn, en = [], []
    for b in tab:
        t = b.text.strip()
        m = re.match(r"^(?:Area\s*)?([A-Z])\s*区?$", t) or re.match(r"^([A-Z])\s*区$", t)
        if m:
            info["area"] = info["area"] or m.group(1)
        elif t.lower() == "area":
            continue
        elif _CJK_RE.search(t):
            cn.append(t)
        elif len(t) > 3:
            en.append(t)
    info["category_cn"] = "".join(cn)
    info["category_en"] = " ".join(en)
    return info


def _filter_body(boxes: list[OcrBox], w: int, h: int, s: Settings) -> list[OcrBox]:
    logo = [b for b in boxes if b.cy < 0.25 * h and _LOGO_RE.search(b.text.strip())]
    header_cut = max(b.y1 for b in logo) + 4 if logo else s.header_ratio * h
    out = []
    for b in boxes:
        t = b.text.strip()
        if not t or b.score < s.min_confidence:
            continue
        if b.cy < header_cut or _LOGO_RE.search(t):
            continue
        if b.cy > (1 - s.footer_ratio) * h or (b.cy > 0.75 * h and _PAGE_RE.match(t)):
            continue
        if b.cx > (1 - s.side_tab_ratio) * w:          # vertical side tab
            continue
        if b.cx < 0.03 * w or (_is_vertical(b) and len(t) <= 2 and b.x1 < 0.06 * w):  # facing-page bleed
            continue
        if _LEGEND_RE.search(t):
            continue
        out.append(b)
    return out


def _column_split(boxes: list[OcrBox], w: int, s: Settings) -> float:
    if s.column_split and 0 < s.column_split < 1:
        return s.column_split * w
    best, best_x = None, w * 0.5
    for x in range(int(0.3 * w), int(0.7 * w), 4):
        crossing = sum(1 for b in boxes if b.x0 < x < b.x1)
        key = (crossing, abs(x - 0.5 * w))
        if best is None or key < best:
            best, best_x = key, x
    # centre of the gap containing best_x
    lo = hi = best_x
    while lo > 0.25 * w and sum(1 for b in boxes if b.x0 < lo - 4 < b.x1) <= best[0]:
        lo -= 4
    while hi < 0.75 * w and sum(1 for b in boxes if b.x0 < hi + 4 < b.x1) <= best[0]:
        hi += 4
    return (lo + hi) / 2


def _group_lines(col: list[OcrBox]) -> list[tuple[str, float, float, float]]:
    """Merge boxes on the same visual line. Returns (text, score, x0, cy)."""
    lines: list[list[OcrBox]] = []
    for b in sorted(col, key=lambda b: b.cy):
        if lines:
            last = lines[-1]
            ly0 = min(x.y0 for x in last)
            ly1 = max(x.y1 for x in last)
            ov = min(ly1, b.y1) - max(ly0, b.y0)
            no_x_overlap = all(b.x0 >= x.x1 - 5 or b.x1 <= x.x0 + 5 for x in last)
            if ov > 0.6 * min(b.h, ly1 - ly0) and no_x_overlap:
                last.append(b)
                continue
        lines.append([b])
    out = []
    for ln in lines:
        ln.sort(key=lambda b: b.x0)
        text = ln[0].text.strip()
        for b in ln[1:]:
            t = b.text.strip()
            sep = "" if (_CJK_RE.search(text[-1:]) or _CJK_RE.search(t[:1])) else " "
            text += sep + t
        out.append((text, sum(b.score for b in ln) / len(ln), ln[0].x0, sum(b.cy for b in ln) / len(ln)))
    return out


def _mark_headers(lines, col_width: float):
    """Section headers are centred in the column, i.e. clearly indented vs neighbouring lines."""
    out = []
    for i, (text, score, x0, cy) in enumerate(lines):
        neigh = [l[2] for j, l in enumerate(lines) if j != i and abs(j - i) <= 3]
        indent = x0 - median(neigh) if neigh else 0
        if indent > 0.12 * col_width and not _START_HINT.match(text) and not _FIELD_HINT.search(text) \
                and len(text) < 45:
            text = CAT_MARK + text
        out.append((text, score))
    return out


def to_reading_lines_scored(boxes: list[OcrBox], image_width: int, settings: Settings,
                            image_height: int | None = None) -> list[tuple[str, float]]:
    if not boxes:
        return []
    w = image_width
    h = image_height or int(max(b.y1 for b in boxes) / 0.85)
    body = _filter_body(boxes, w, h, settings)
    if not body:
        return []
    split = _column_split(body, w, settings)
    left = [b for b in body if b.cx < split]
    right = [b for b in body if b.cx >= split]
    out: list[tuple[str, float]] = []
    for col, width in ((left, split), (right, w * (1 - settings.side_tab_ratio) - split)):
        out.extend(_mark_headers(_group_lines(col), max(width, 1)))
    return out


def to_reading_lines(boxes: list[OcrBox], image_width: int, settings: Settings,
                     image_height: int | None = None) -> list[str]:
    """Body lines in reading order (left column top->bottom, then right column)."""
    return [t for t, _ in to_reading_lines_scored(boxes, image_width, settings, image_height)]
