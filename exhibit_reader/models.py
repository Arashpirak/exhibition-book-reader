"""Shared data model. Frozen contract — owned by the orchestrator (see CLAUDE.md)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Callable, Optional

# Column order used by every exporter.
RECORD_FIELDS = [
    "booth", "domestic_sale", "name_cn", "name_en", "address_cn", "postcode",
    "address_en", "tel", "fax", "email", "url", "category_cn", "category_en",
    "area", "page_no", "source_image", "is_continuation", "confidence", "raw_text",
]


@dataclass
class ExhibitorRecord:
    booth: str = ""                # e.g. "17.1A01-02,17.1B22-23"
    domestic_sale: bool = False    # leading "*" in the catalog
    name_cn: str = ""
    name_en: str = ""
    address_cn: str = ""           # without the "(邮政编码: …)" part
    postcode: str = ""
    address_en: str = ""
    tel: str = ""
    fax: str = ""
    email: str = ""
    url: str = ""
    category_cn: str = ""          # section header, e.g. "动力、电力设备"
    category_en: str = ""          # e.g. "Power Machinery and Electric Power"
    area: str = ""                 # e.g. "D"
    page_no: str = ""              # printed page number, e.g. "001"
    source_image: str = ""         # file name of the photo
    is_continuation: bool = False  # True if this fragment continues a record from the previous page
    confidence: float = 0.0        # mean OCR score of the lines used
    raw_text: str = ""             # the joined source lines, for audit

    def to_row(self) -> list:
        d = asdict(self)
        return [d[k] for k in RECORD_FIELDS]


@dataclass
class Settings:
    input_folder: str = "."
    file_pattern: str = "*.jpg;*.jpeg;*.png"
    output_folder: str = "output"
    output_basename: str = "exhibitors"
    export_excel: bool = True
    export_access: bool = True
    ocr_engine: str = "rapidocr"           # "rapidocr" | "claude"
    claude_model: str = "claude-haiku-5-5"
    min_confidence: float = 0.5            # drop OCR boxes below this score
    header_ratio: float = 0.13             # top fraction of the page ignored (fair logo)
    footer_ratio: float = 0.06             # bottom fraction ignored (page number is read separately)
    side_tab_ratio: float = 0.10           # right fraction ignored (vertical "D区 / Area D" tab)
    column_split: float = 0.0              # 0 = auto-detect, else split x as fraction of width
    merge_continuations: bool = True
    keep_raw_text: bool = True
    save_debug_text: bool = False          # write per-image OCR lines to output/debug/
    workers: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    def to_dict(self) -> dict:
        return asdict(self)


# progress(done_images, total_images, message)
ProgressCallback = Callable[[int, int, str], None]
OptionalProgress = Optional[ProgressCallback]
