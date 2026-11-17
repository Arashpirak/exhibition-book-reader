"""Entry point: python app.py  (also the entry point of the packaged ExhibitionBookReader.exe)."""
import os
import sys


def _prepare_frozen():
    """When running as a PyInstaller exe: work next to the exe, keep settings in %APPDATA%."""
    if not getattr(sys, "frozen", False):
        return
    # windowed exe has no console: give libraries that print/log somewhere harmless to write
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
    from exhibit_reader import gui
    cfg = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ExhibitionBookReader")
    os.makedirs(cfg, exist_ok=True)
    gui.SETTINGS_FILE = os.path.join(cfg, "settings.json")
    try:  # close the "starting…" splash shown while the exe unpacks
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except Exception:
        pass


def _batch(folder: str) -> int:
    """No-window run: `ExhibitionBookReader.exe --batch <photos folder>` → <folder>/output/ + run_log.txt."""
    from exhibit_reader import pipeline
    from exhibit_reader.models import Settings
    folder = os.path.abspath(folder)
    out = os.path.join(folder, "output")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "run_log.txt"), "w", encoding="utf-8") as log:
        recs = pipeline.run(Settings(input_folder=folder, output_folder=out),
                            lambda d, t, m: (log.write(f"[{d}/{t}] {m}\n"), log.flush()))
        log.write(f"RECORDS {len(recs)}\n")
    return 0 if recs else 1


if __name__ == "__main__":
    _prepare_frozen()
    if len(sys.argv) >= 3 and sys.argv[1] == "--batch":
        sys.exit(_batch(sys.argv[2]))
    from exhibit_reader.gui import main
    main()
