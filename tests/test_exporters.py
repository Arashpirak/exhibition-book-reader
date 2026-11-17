import os
import pytest
from exhibit_reader.models import ExhibitorRecord, Settings
from exhibit_reader import exporters, settings_store


def recs():
    return [
        ExhibitorRecord(booth="17.1A01-02", domestic_sale=True, name_cn="宁波测试电力设备有限公司",
                        name_en="Ningbo Test Power Co., Ltd.", address_cn="浙江省宁波市鄞州区", postcode="315000",
                        address_en="Yinzhou, Ningbo", tel="0574-1234567", email="a@b.cn", url="www.test.cn",
                        category_cn="动力、电力设备", category_en="Power Machinery", area="D", page_no="001",
                        source_image="p1.jpg", confidence=0.93, raw_text="line1\nline2 中文"),
        ExhibitorRecord(booth="", is_continuation=True, name_cn="续", source_image="p2.jpg"),
    ]


def test_excel_roundtrip(tmp_path):
    from openpyxl import load_workbook
    p = exporters.export_excel(recs(), str(tmp_path / "sub" / "x.xlsx"))
    ws = load_workbook(p)["Exhibitors"]
    assert ws["A1"].font.bold and ws.freeze_panes == "A2" and ws.auto_filter.ref
    assert ws.max_row == 3
    assert ws["C2"].value == "宁波测试电力设备有限公司"
    assert ws["K2"].value == "www.test.cn"


def test_access_roundtrip(tmp_path):
    pyodbc = pytest.importorskip("pyodbc")
    p = exporters.export_access(recs(), str(tmp_path / "x.accdb"))
    conn = pyodbc.connect(r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=" + p + ";")
    rows = conn.cursor().execute("SELECT booth, name_cn, address_cn, domestic_sale, confidence, raw_text, is_continuation "
                                 "FROM Exhibitors ORDER BY id").fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0].name_cn == "宁波测试电力设备有限公司" and rows[0].address_cn == "浙江省宁波市鄞州区"
    assert rows[0].domestic_sale is True and abs(rows[0].confidence - 0.93) < 1e-9
    assert "中文" in rows[0].raw_text and rows[1].is_continuation is True


def test_export_dispatch(tmp_path):
    s = Settings(output_folder=str(tmp_path / "out"), export_access=False)
    out = exporters.export(recs(), s)
    assert len(out) == 1 and out[0].endswith("exhibitors.xlsx") and os.path.exists(out[0])
    assert exporters.export([], Settings(output_folder=str(tmp_path / "o2"))) and True


def test_settings_store(tmp_path):
    p = str(tmp_path / "s.json")
    assert settings_store.load(p) == Settings()
    s = Settings(output_basename="展会", min_confidence=0.7)
    settings_store.save(s, p)
    assert settings_store.load(p) == s
    open(p, "w").write("{broken")
    assert settings_store.load(p) == Settings()
    open(p, "w").write('{"workers": "x", "unknown": 1, "output_basename": "q"}')
    t = settings_store.load(p)
    assert t.workers == 1 and t.output_basename == "q"
