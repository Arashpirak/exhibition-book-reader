# Exhibition Book Reader

Reads photographed pages of the China Import and Export Fair exhibitor catalog (Chinese + English, two columns)
and writes every exhibitor record to Excel (.xlsx) and/or Access (.accdb).

## Install (Windows, Python 3.12 64-bit)
```
python -m pip install -r requirements.txt
```
Requires the 64-bit Microsoft Access Database Engine (ACE) for `.accdb` output.

## Run
- GUI: double-click `run_app.bat` (or `python app.py`). Pick the image folder, output folder and formats, then Start.
- OCR is fully local (RapidOCR). The optional `claude` engine needs `ANTHROPIC_API_KEY`.

## Output
`output/exhibitors.xlsx` (sheet `Exhibitors`) and `output/exhibitors.accdb`.

## Tests
```
python -m pytest -q
```

## Build the stand-alone exe (for people without Python)
```
python -m pip install pyinstaller
python packaging/make_assets.py
python -m PyInstaller --noconfirm --clean --workpath build --distpath dist packaging/ExhibitionBookReader.spec
```
Result: `dist/ExhibitionBookReader.exe` (one file, ~140 MB, Windows 64-bit, no install needed) plus
`dist/HOW TO USE.txt` for the person receiving it. Settings are kept in `%APPDATA%\ExhibitionBookReader`.
Check a build without opening the window: `ExhibitionBookReader.exe --batch <photos folder>` writes
`<photos folder>\output\` and `run_log.txt`.
