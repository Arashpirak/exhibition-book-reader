"""Run OCR -> layout -> parse over a folder of catalog photos, merge continuations, export."""
from __future__ import annotations

import glob
import json
import os
import threading

from .layout import page_info, to_reading_lines_scored
from .models import ExhibitorRecord, ProgressCallback, Settings
from .ocr_engine import OcrBox, get_engine
from .parser import parse_lines

_JOIN = {"name_cn": "", "address_cn": "", "name_en": " ", "address_en": " "}
_TAKE_IF_EMPTY = ("booth", "postcode", "tel", "fax", "email", "url", "category_cn", "category_en", "area")


def list_images(settings: Settings) -> list[str]:
    pats = [p.strip() for p in (settings.file_pattern or "*.jpg").split(";") if p.strip()]
    found = set()
    for p in pats:
        found.update(glob.glob(os.path.join(settings.input_folder or ".", p)))
    return sorted(found, key=lambda f: os.path.basename(f).lower())


def merge_into(prev: ExhibitorRecord, frag: ExhibitorRecord) -> None:
    """Append a continuation fragment (top of a page/column) to the record it belongs to."""
    for f, sep in _JOIN.items():
        a, b = getattr(prev, f), getattr(frag, f)
        if b:
            setattr(prev, f, (a + sep + b).strip() if a else b)
    for f in _TAKE_IF_EMPTY:
        if not getattr(prev, f) and getattr(frag, f):
            setattr(prev, f, getattr(frag, f))
    if frag.raw_text:
        prev.raw_text = (prev.raw_text + "\n" + frag.raw_text).strip()
    if frag.confidence:
        prev.confidence = round((prev.confidence + frag.confidence) / 2, 3) if prev.confidence else frag.confidence
    if frag.source_image and frag.source_image not in prev.source_image:
        prev.source_image += ";" + frag.source_image


def _image_size(path: str) -> tuple[int, int]:
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        return im.size


def process_boxes(boxes: list[OcrBox], w: int, h: int, settings: Settings, source_image: str,
                  debug_name: str | None = None) -> tuple[list[ExhibitorRecord], dict]:
    info = page_info(boxes, w, h, settings)
    scored = to_reading_lines_scored(boxes, w, settings, h)
    lines = [t for t, _ in scored]
    recs = parse_lines(lines, source_image, info["page_no"], [s for _, s in scored])
    for r in recs:
        r.area = r.area or info["area"]
        if not settings.keep_raw_text:
            r.raw_text = ""
    if settings.save_debug_text and debug_name:
        d = os.path.join(settings.output_folder or "output", "debug")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, debug_name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(info, ensure_ascii=False) + "\n" + "\n".join(lines))
    return recs, info


def run(settings: Settings, progress: ProgressCallback | None = None,
        stop_flag: threading.Event | None = None) -> list[ExhibitorRecord]:
    images = list_images(settings)
    total = len(images)
    report = progress or (lambda done, tot, msg: None)
    if not images:
        report(0, 0, f"No images matching {settings.file_pattern} in {os.path.abspath(settings.input_folder)}")
        return []
    report(0, total, f"Loading OCR engine '{settings.ocr_engine}'…")
    engine = get_engine(settings.ocr_engine, settings.claude_model) if settings.ocr_engine == "claude" \
        else get_engine(settings.ocr_engine)
    records: list[ExhibitorRecord] = []
    cat_cn = cat_en = area = ""
    for i, path in enumerate(images):
        if stop_flag is not None and stop_flag.is_set():
            report(i, total, "Stopped by user.")
            break
        name = os.path.basename(path)
        report(i, total, f"Reading {name} ({i + 1}/{total})…")
        try:
            boxes = engine.read(path, settings)
            w, h = _image_size(path)
            recs, info = process_boxes(boxes, w, h, settings, name, os.path.splitext(name)[0])
        except Exception as e:  # keep going with the other pages
            report(i + 1, total, f"ERROR on {name}: {e}")
            continue
        # carry section category / area across pages
        for r in recs:
            if r.category_cn or r.category_en:
                cat_cn, cat_en = r.category_cn or cat_cn, r.category_en or cat_en
            else:
                r.category_cn, r.category_en = cat_cn, cat_en
            if r.area:
                area = r.area
            else:
                r.area = area
            if not r.category_cn and info.get("category_cn"):
                r.category_cn = info["category_cn"]
            if not r.category_en and info.get("category_en"):
                r.category_en = info["category_en"]
        for r in recs:
            if r.is_continuation and settings.merge_continuations and records:
                merge_into(records[-1], r)
            else:
                records.append(r)
        n_new = sum(1 for r in recs if not r.is_continuation)
        report(i + 1, total, f"{name}: page {info.get('page_no') or '?'}, {n_new} exhibitors")

    # the side-tab area letter is not readable on every page: fill gaps with the most common one
    areas = [r.area for r in records if r.area]
    if areas:
        common = max(set(areas), key=areas.count)
        for r in records:
            r.area = r.area or common

    try:  # exporters are owned by another module; only call them if present
        from . import exporters  # noqa: WPS433
    except ImportError:
        exporters = None
    if exporters is not None and records:
        try:
            paths = exporters.export(records, settings)
            report(total, total, "Saved: " + ", ".join(paths))
        except getattr(exporters, "PartialExportError", ()) as e:
            report(total, total, "Saved: " + ", ".join(e.paths))
            report(total, total, f"Export failed: {e}")
        except Exception as e:
            report(total, total, f"Export failed: {e}")
    report(total, total, f"Done: {len(records)} exhibitors from {total} image(s).")
    return records


def _load_settings() -> Settings:
    try:
        from . import settings_store
        return settings_store.load()
    except Exception:
        return Settings()


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    s = _load_settings()
    s.input_folder = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    recs = run(s, progress=lambda d, t, m: print(f"[{d}/{t}] {m}"))
    by_page: dict[str, int] = {}
    for r in recs:
        by_page[r.page_no or "?"] = by_page.get(r.page_no or "?", 0) + 1
    print("Records per page:", by_page)
    for r in recs:
        print(f"{r.page_no} | {r.booth:<34} | {r.name_cn} | {r.name_en} | {r.email} | {r.url}")
