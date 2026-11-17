# Exhibition Book Reader — project contract

Local Windows Python 3.12 (64-bit) app that reads photographed pages of the China Import and Export Fair
exhibitor catalog (`*.jpg` in the project root and any operator-chosen folder), extracts every exhibitor
record and writes them to Excel (.xlsx) and/or Access (.accdb). Has a small Tkinter settings/run window.

Catalog format knowledge: `.claude/skills/exhibition-catalog-format/SKILL.md` (read it before touching OCR/parsing).
Background research: `docs/telegram_research.md`.

## Package layout (each file has ONE owner — never edit another owner's file; ask the supervisor instead)
| Path | Owner session |
|---|---|
| `exhibit_reader/models.py`, `CLAUDE.md`, `.claude/**` | orchestrator (frozen; propose changes to supervisor) |
| `exhibit_reader/ocr_engine.py`, `exhibit_reader/layout.py`, `exhibit_reader/parser.py`, `exhibit_reader/pipeline.py`, `tests/test_parser.py`, `tests/test_pipeline.py` | `ocr-parser` |
| `exhibit_reader/exporters.py`, `exhibit_reader/settings_store.py`, `tests/test_exporters.py` | `exporters` |
| `exhibit_reader/gui.py`, `app.py`, `run_app.bat` | `gui` |
| `requirements.txt`, `README.md`, `tests/test_e2e.py`, integration fixes | `supervisor` |

## Interfaces (stable — implement exactly)
```python
# exhibit_reader/models.py  (already written)
ExhibitorRecord, Settings, ProgressCallback

# exhibit_reader/ocr_engine.py
class OcrBox: text: str; x0,y0,x1,y1: float; score: float          # pixel coords of original image
def get_engine(name: str) -> "OcrEngine"                              # "rapidocr" (default), "claude" (optional)
class OcrEngine: def read(self, image_path: str, settings: Settings) -> list[OcrBox]

# exhibit_reader/layout.py
def to_reading_lines(boxes: list[OcrBox], image_width: int, settings: Settings) -> list[str]
    # drops header/footer/side-tab, splits into columns, returns lines in reading order (left col then right col)

# exhibit_reader/parser.py
def parse_lines(lines: list[str], source_image: str, page_no: str|None) -> list[ExhibitorRecord]
    # first record may have booth=="" and is_continuation=True when page starts mid-record

# exhibit_reader/pipeline.py
def run(settings: Settings, progress: ProgressCallback|None = None, stop_flag: threading.Event|None = None) -> list[ExhibitorRecord]
    # iterates images (sorted by name), OCR → layout → parse, merges continuations into the previous
    # page's last record, then calls exporters.export(records, settings). Returns all records.

# exhibit_reader/exporters.py
def export(records: list[ExhibitorRecord], settings: Settings) -> list[str]   # returns written file paths
def export_excel(records, path) -> str ; def export_access(records, path) -> str

# exhibit_reader/settings_store.py
def load(path="settings.json") -> Settings ; def save(settings, path="settings.json") -> None
```

## Rules
- Fully local by default: RapidOCR (`rapidocr_onnxruntime`, Chinese+English). The `claude` engine is optional and
  only used when the operator picks it and `ANTHROPIC_API_KEY` is set (model `claude-haiku-5-5` default, `claude-sonnet-5-5` option).
- Access: 64-bit "Microsoft Access Driver (*.mdb, *.accdb)" is installed. Create the .accdb with pywin32 ADOX
  (`ADOX.Catalog`, provider `Microsoft.ACE.OLEDB.16.0`, fall back to 12.0), insert with pyodbc.
- Excel: openpyxl, one sheet `Exhibitors`, header row bold+frozen+autofilter, sensible column widths, UTF-8 Chinese intact.
- GUI: Tkinter + ttk only (no extra GUI deps). Never block the UI thread: run the pipeline in a worker thread,
  report through `progress`. Follow `apple-design` / `emil-design-eng` skill principles: clear hierarchy, immediate feedback, restraint.
- Tests: pytest in `tests/`. Use the three root sample images as fixtures for integration tests.
- Use `python -m pip install -r requirements.txt`; pin nothing exotic. Venv optional (`.venv`).
- Token budget is limited: read only files you need, no large dumps, keep messages short.
- No git repo here: never delete or rewrite files outside your ownership.
- When blocked or done, message the supervisor session (its id is in your brief) with a ≤5-line status.
