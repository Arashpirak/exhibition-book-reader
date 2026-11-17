"""Integration test on the three sample photos in the project root.

OCR results are cached in output/debug/<image>.json (created on first run, ~20 s per image);
delete the cache to force a fresh OCR run.
"""
import json
import os

import pytest

from exhibit_reader import pipeline
from exhibit_reader.models import Settings
from exhibit_reader.ocr_engine import OcrBox, get_engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "output", "debug")
SAMPLES = sorted(f for f in os.listdir(ROOT) if f.startswith("photo_") and f.endswith(".jpg"))

EXPECTED_BOOTHS = {
    "17.1A01-02,17.1B22-23", "17.1A03", "17.1A04-07,17.1B17-20", "17.1A08-12,17.1B12-16",
    "17.1A13-17,17.1B07-11", "17.1A21", "17.1A22-23", "17.1B01-02",
    "17.1B03", "17.1A18-20,17.1B04-06", "17.1B21", "17.1B28-29", "17.1B30-32",
    "17.1B33-35,17.1C10-12,17.1H24-26,17.1I17-19", "17.1B38-39", "17.1B40-41,17.1C06-07", "17.1B42-43",
    "17.1B44-46", "17.1C01-03", "17.1C04-05", "17.1B36-37,17.1C08-09", "17.1C13", "17.1C14-15",
    "17.1B24-27,17.1C16-19", "17.1C20-22,17.1D21-23", "17.1C23-24,17.1D19-20",
}
EXPECTED_EMAILS = {
    "marketing@baifapower.com", "foguangfadian@126.com", "872849339@qq.com", "sales@yanan-motor.com",
    "sales@chinalutian.com", "wndj@wnmotor.com", "valy@senci.cn", "chenxi@lymotors.com",
    "erick83@163.com", "william@techtop.net.cn", "nytl008@163.com", "kevin@farrand.cn",
    "manager@hongfumotor.com", "daniel@sumec.com.cn", "emeiengine@vip.163.com", "qjpower@163.com",
    "info@cmecqz.com", "export@eifelcn.com", "cp@winsunpower.cn", "yz@jsyzdj.com", "gl_sale@guanglu.com",
    "sales1@plus-power.cn", "isaac@koopchina.com", "director@longkaipower.com", "tony@pacelinkpower.com",
}


class CachedEngine:
    """Real RapidOCR, but results are cached on disk so the test suite stays fast."""
    _real = None

    def read(self, image_path, settings):
        name = os.path.splitext(os.path.basename(image_path))[0]
        path = os.path.join(CACHE, name + ".json")
        if not os.path.exists(path):
            if CachedEngine._real is None:
                CachedEngine._real = get_engine("rapidocr")
            boxes = CachedEngine._real.read(image_path, settings)
            from PIL import Image
            w, h = Image.open(image_path).size
            os.makedirs(CACHE, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"w": w, "h": h, "boxes": [b.to_dict() for b in boxes]}, fh, ensure_ascii=False)
        with open(path, encoding="utf-8") as fh:
            return [OcrBox.from_dict(b) for b in json.load(fh)["boxes"]]


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    if len(SAMPLES) < 3:
        pytest.skip("sample photos not present")
    mp = pytest.MonkeyPatch()
    mp.setattr(pipeline, "get_engine", lambda *a, **k: CachedEngine())
    out = tmp_path_factory.mktemp("out")
    s = Settings(input_folder=ROOT, file_pattern="photo_*.jpg", output_folder=str(out),
                 export_excel=False, export_access=False)
    msgs = []
    recs = pipeline.run(s, progress=lambda d, t, m: msgs.append((d, t, m)))
    mp.undo()
    assert msgs and msgs[-1][0] == msgs[-1][1] == 3
    return recs


def test_all_booths_found(records):
    assert {r.booth for r in records} == EXPECTED_BOOTHS
    assert len(records) == len(EXPECTED_BOOTHS)


def test_records_per_page(records):
    pages = {}
    for r in records:
        pages[r.page_no] = pages.get(r.page_no, 0) + 1
    assert pages == {"001": 8, "002": 9, "003": 9}


def test_emails_and_urls_exact(records):
    assert {r.email for r in records if r.email} == EXPECTED_EMAILS
    by_booth = {r.booth: r for r in records}
    assert by_booth["17.1A01-02,17.1B22-23"].url == "www.baifapower.com"
    assert by_booth["17.1A04-07,17.1B17-20"].url == "www.cqdinking.com"   # top of the right column
    assert by_booth["17.1B24-27,17.1C16-19"].url == "www.koopchina.com"
    assert by_booth["17.1B40-41,17.1C06-07"].url == "fcqj.com"
    for r in records:
        assert " " not in r.email and " " not in r.url


def test_continuations_merged(records):
    by_booth = {r.booth: r for r in records}
    assert not any(r.is_continuation for r in records)
    liyuan = by_booth["17.1B01-02"]        # page 001 -> page 002
    assert liyuan.email == "chenxi@lymotors.com" and liyuan.url == "www.lymotors.com"
    assert "GONGMAO" in liyuan.address_en and liyuan.postcode == "355000"
    cmec = by_booth["17.1B42-43"]          # page 002 -> page 003
    assert cmec.email == "info@cmecqz.com" and cmec.tel == "86-595-22184028"
    assert "QUANZHOU" in cmec.name_en and "YUANTAI" in cmec.address_en
    pb = by_booth["17.1C13"]               # bottom of left column -> top of right column
    assert "POWERSOURCE" in pb.name_en and pb.postcode == "355000"


def test_no_logo_or_side_tab_text(records):
    bad = ("中国进出口", "IMPORT AND EXPORT", "Since", "Area D", "Booth Legend", "温馨提示")
    for r in records:
        for v in (r.name_cn, r.name_en, r.address_cn, r.address_en):
            assert not any(b in v for b in bad), v


def test_categories_and_area(records):
    assert all(r.category_cn == "动力、电力设备" for r in records)
    assert all(r.category_en == "Power Machinery and Electric Power" for r in records)
    assert all(r.area == "D" for r in records)
    assert all(r.name_cn and r.name_en and r.address_cn for r in records)
