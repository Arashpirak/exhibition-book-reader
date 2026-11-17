# PyInstaller spec — build with:  python -m PyInstaller --noconfirm --clean packaging/ExhibitionBookReader.spec
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=collect_data_files("rapidocr_onnxruntime")           # OCR models + config.yaml
          + [(os.path.join(SPECPATH, "app.ico"), ".")],             # window icon
    hiddenimports=["exhibit_reader.exporters", "exhibit_reader.settings_store", "exhibit_reader.pipeline",
                   "win32com.client", "pyodbc", "openpyxl"]
                  # NumPy 2.x loads its C-extension helpers dynamically; PyInstaller misses some of them
                  + [m for pkg in ("numpy._core", "numpy.linalg", "numpy.random")
                     for m in collect_submodules(pkg) if ".tests" not in m],
    excludes=["anthropic", "numpy._core.tests", "numpy.tests", "numpy.f2py", "numpy.testing", "matplotlib", "pandas", "scipy", "torch", "IPython", "pytest", "notebook",
              "PyQt5", "PySide6", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
splash = Splash(os.path.join(SPECPATH, "splash.png"), binaries=a.binaries, datas=a.datas,
                text_pos=(137, 128), text_size=9, text_color="#6e6e73", minify_script=True)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, splash, splash.binaries, [],
    name="ExhibitionBookReader",
    icon=os.path.join(SPECPATH, "app.ico"),
    console=False,
    upx=False,
    runtime_tmpdir=None,
)
