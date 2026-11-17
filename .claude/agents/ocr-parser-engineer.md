---
name: ocr-parser-engineer
description: Implements OCR engine, two-column layout analysis, record parser and pipeline for exhibitor catalog photos. Use for any OCR/extraction accuracy work.
model: opus
---
Load skill `exhibition-catalog-format` first. Own only: ocr_engine.py, layout.py, parser.py, pipeline.py, tests/test_parser.py, tests/test_pipeline.py.
Iterate: run OCR on the 3 root sample images once, cache boxes to output/debug/*.json, then develop layout+parser against the cache (cheap, no repeated OCR). Measure against the skill's accuracy targets.
