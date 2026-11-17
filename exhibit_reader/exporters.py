"""Excel and Access exporters."""
from __future__ import annotations

import os
import re

from .models import ExhibitorRecord, Settings, RECORD_FIELDS

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_WIDTHS = {"booth": 22, "name_cn": 30, "name_en": 36, "address_cn": 40, "address_en": 45,
           "tel": 20, "fax": 20, "email": 28, "url": 28, "category_cn": 22, "category_en": 28,
           "raw_text": 50}


def _clean(v):
    return _ILLEGAL.sub("", v) if isinstance(v, str) else v


def _ensure_dir(path: str) -> str:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def export_excel(records: list[ExhibitorRecord], path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    path = _ensure_dir(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Exhibitors"
    ws.append(RECORD_FIELDS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(vertical="center")
    for r in records:
        ws.append([_clean(x) for x in r.to_row()])
    ws.freeze_panes = "A2"
    last = get_column_letter(len(RECORD_FIELDS))
    ws.auto_filter.ref = f"A1:{last}{max(ws.max_row, 1)}"
    for i, name in enumerate(RECORD_FIELDS, 1):
        ws.column_dimensions[get_column_letter(i)].width = _WIDTHS.get(name, max(12, len(name) + 4))
    wb.save(path)
    return path


def _create_empty_accdb(path: str) -> None:
    import win32com.client
    errors = []
    for prov in ("Microsoft.ACE.OLEDB.16.0", "Microsoft.ACE.OLEDB.12.0"):
        try:
            cat = win32com.client.Dispatch("ADOX.Catalog")
            cat.Create(f"Provider={prov};Data Source={path};")
            conn = cat.ActiveConnection
            if conn is not None:
                conn.Close()
            return
        except Exception as e:
            errors.append(f"{prov}: {e}")
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
    raise RuntimeError("Cannot create .accdb: " + " | ".join(errors))


def export_access(records: list[ExhibitorRecord], path: str) -> str:
    import pyodbc

    path = _ensure_dir(path)
    if os.path.exists(path):
        os.remove(path)
    _create_empty_accdb(path)

    cols = []
    for f in RECORD_FIELDS:
        if f in ("domestic_sale", "is_continuation"):
            t = "YESNO"
        elif f == "confidence":
            t = "DOUBLE"
        elif f in ("address_cn", "address_en", "raw_text"):
            t = "LONGTEXT"
        else:
            t = "TEXT(255)"
        cols.append(f"[{f}] {t}")
    conn = pyodbc.connect(
        r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=" + path + ";", autocommit=False)
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Exhibitors (id AUTOINCREMENT PRIMARY KEY, " + ", ".join(cols) + ")")
        sql = ("INSERT INTO Exhibitors (" + ", ".join(f"[{f}]" for f in RECORD_FIELDS) + ") VALUES ("
               + ", ".join("?" * len(RECORD_FIELDS)) + ")")
        rows = []
        for r in records:
            row = []
            for f, v in zip(RECORD_FIELDS, r.to_row()):
                if f in ("domestic_sale", "is_continuation"):
                    v = bool(v)
                elif f == "confidence":
                    v = float(v or 0.0)
                else:
                    v = _clean(v if v is not None else "")
                    if f not in ("address_cn", "address_en", "raw_text"):
                        v = v[:255]
                row.append(v)
            rows.append(row)
        if rows:
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()
    return path


ACCESS_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def access_available() -> bool:
    """True when the 64-bit Access ODBC driver (Access / Access Database Engine) is installed."""
    try:
        import pyodbc
        return ACCESS_DRIVER in pyodbc.drivers()
    except Exception:
        return False


class PartialExportError(RuntimeError):
    """Some formats were written, others failed. `paths` lists the files that were written."""

    def __init__(self, paths: list[str], message: str):
        super().__init__(message)
        self.paths = paths


def export(records: list[ExhibitorRecord], settings: Settings) -> list[str]:
    out: list[str] = []
    folder = settings.output_folder or "output"
    base = settings.output_basename or "exhibitors"
    if settings.export_excel:
        out.append(export_excel(records, os.path.join(folder, base + ".xlsx")))
    if settings.export_access:
        try:
            out.append(export_access(records, os.path.join(folder, base + ".accdb")))
        except Exception as e:
            if not out:
                raise
            hint = "" if access_available() else " (the Microsoft Access database driver is not installed)"
            raise PartialExportError(out, f"Access file not written{hint}: {e}") from e
    return out
