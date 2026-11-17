"""End-to-end: exported xlsx/accdb must contain the same records."""
import os
import pytest
import openpyxl
from exhibit_reader import pipeline
from exhibit_reader.models import Settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")


def test_outputs_consistent():
    x = os.path.join(OUT, "exhibitors.xlsx")
    a = os.path.join(OUT, "exhibitors.accdb")
    if not (os.path.exists(x) and os.path.exists(a)):
        pytest.skip("run `python -m exhibit_reader.pipeline` first")
    ws = openpyxl.load_workbook(x)["Exhibitors"]
    rows = list(ws.iter_rows(values_only=True))
    n_x = len(rows) - 1
    import pyodbc
    c = pyodbc.connect(r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=" + a)
    n_a = c.cursor().execute("select count(*) from Exhibitors").fetchone()[0]
    c.close()
    assert n_x == n_a >= 24
    hdr = [str(h).lower() for h in rows[0]]
    assert any("booth" in h for h in hdr)
