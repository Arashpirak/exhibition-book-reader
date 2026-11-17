"""OCR engines. Default: local RapidOCR (Chinese+English). Optional: Claude vision.

Both return a list of OcrBox in pixel coordinates of the original image.
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, asdict

from .models import Settings


@dataclass
class OcrBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "OcrBox":
        return cls(**{k: d[k] for k in ("text", "x0", "y0", "x1", "y1", "score")})


class OcrEngine:
    name = "base"

    def read(self, image_path: str, settings: Settings) -> list[OcrBox]:  # pragma: no cover
        raise NotImplementedError


def _load_bgr(image_path: str):
    """Read an image (unicode path safe) as a BGR numpy array, EXIF-orientation applied."""
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(image_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        arr = np.asarray(im)
    return arr[:, :, ::-1].copy()


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"
    _ocr = None  # shared model instance (loading is slow)

    def __init__(self):
        if RapidOcrEngine._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            RapidOcrEngine._ocr = RapidOCR(det_use_dilation=False, max_side_len=2600)

    # Detection on the full 1440x2560 photo misses some long lines, so we detect on
    # overlapping horizontal bands and de-duplicate.  The recogniser also drops
    # characters on long lines (dense booth lists), so long lines are re-read in
    # overlapping chunks and stitched.
    BAND_H = 700
    BAND_STEP = 520
    DET_KW = dict(box_thresh=0.3, unclip_ratio=1.8, text_score=0.0)  # score filter is in layout

    def read(self, image_path: str, settings: Settings) -> list[OcrBox]:
        img = _load_bgr(image_path)
        return self.read_array(img)

    def read_array(self, img) -> list[OcrBox]:
        import numpy as np
        H = img.shape[0]
        cands = []  # (quad ndarray 4x2, text, score)
        starts = list(range(0, max(H - self.BAND_H, 0) + 1, self.BAND_STEP))
        if starts[-1] + self.BAND_H < H:
            starts.append(max(H - self.BAND_H, 0))
        for y0 in starts:
            y1 = min(y0 + self.BAND_H, H)
            res, _ = RapidOcrEngine._ocr(img[y0:y1], **self.DET_KW)
            for pts, text, score in res or []:
                q = np.array(pts, dtype=np.float32)
                q[:, 1] += y0
                top, bot = q[:, 1].min(), q[:, 1].max()
                # a box touching an inner band edge may be a cut line: the other band has it whole
                if (y0 > 0 and top < y0 + 6) or (y1 < H and bot > y1 - 6):
                    continue
                cands.append((q, str(text), float(score)))
        cands = _dedupe(cands)
        boxes: list[OcrBox] = []
        for q, text, score in cands:
            x0, y0, x1, y1 = q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()
            # chunked re-read only where it pays: booth-list start lines (the recogniser drops
            # characters in long digit runs) and long lines the recogniser could not read
            is_booth = re.match(r"^\s*\*?\s*[(（]\s*\d", text) is not None
            if (x1 - x0) > 12 * max(y1 - y0, 1) and (is_booth or score < 0.6):
                t2, s2 = self._reread_long(img, q)
                n_old, n_new = len(text.replace(" ", "")), len(t2.replace(" ", ""))
                if t2 and (n_new > n_old or (score < 0.6 and s2 > score and n_new >= 0.8 * n_old)):
                    text, score = t2, s2
            if _LATIN_LINE.search(text) and len(_CJK_CHARS.findall(text)) < 3:
                text = self._recover_spaces(img, q, text)
            boxes.append(OcrBox(text, float(x0), float(y0), float(x1), float(y1), score))
        return boxes

    def _recover_spaces(self, img, quad, text: str) -> str:
        """The recogniser drops the spaces between English words on small print. A second read
        of the upscaled line (whole, then in two overlapping halves) is only used to learn where
        the spaces are: characters always stay those of the first read."""
        import cv2
        import numpy as np
        crop = _warp_quad(img, quad)
        h, w = crop.shape[:2]
        if h < 4 or w < 4 * h:
            return text
        pad = max(2, h // 5)
        crop = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        W = crop.shape[1]
        parts = [crop]
        if w > 12 * h:  # long line: halves are read more reliably than the whole
            parts += [crop[:, : int(0.58 * W)], crop[:, int(0.42 * W):]]
        for part in parts:
            try:
                res, _ = RapidOcrEngine._ocr(np.ascontiguousarray(part), use_det=False, use_cls=False)
            except Exception:
                continue
            if res and res[0][0]:
                text = transfer_spaces(text, str(res[0][0]))
        return text

    def _reread_long(self, img, quad):
        import cv2
        import numpy as np
        crop = _warp_quad(img, quad)
        h, w = crop.shape[:2]
        pad = max(2, h // 6)
        crop = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        h, w = crop.shape[:2]
        cw, ov = int(6.5 * h), int(2 * h)
        parts, scores, x = [], [], 0
        while True:
            xe = min(x + cw, w)
            if w - xe < 2 * h:  # avoid a tiny tail chunk
                xe = w
            res, _ = RapidOcrEngine._ocr(np.ascontiguousarray(crop[:, x:xe]), use_det=False, use_cls=False)
            if res:
                parts.append(str(res[0][0]))
                scores.append(float(res[0][1]))
            if xe >= w:
                break
            x = xe - ov
        if not parts:
            return "", 0.0
        text = parts[0]
        for p in parts[1:]:
            text = _stitch(text, p)
        return text, sum(scores) / len(scores)


_LATIN_LINE = re.compile(r"[A-Za-z]{4}")
_CJK_CHARS = re.compile(r"[㐀-鿿]")


def transfer_spaces(old: str, new: str) -> str:
    """Add to `old` the word spaces that `new` (another reading of the same line) has.

    Only spaces are taken, and only where the characters on both sides agree in the two
    readings, so a worse second reading can never corrupt the text.
    """
    from difflib import SequenceMatcher
    o_idx = [i for i, c in enumerate(old) if not c.isspace()]
    n_chars, n_space = [], []
    pending = False
    for c in new:
        if c.isspace():
            pending = True
        else:
            n_chars.append(c)
            n_space.append(pending)
            pending = False
    o_chars = [old[i].upper() for i in o_idx]
    sm = SequenceMatcher(None, o_chars, [c.upper() for c in n_chars], autojunk=False)
    add = set()
    for a, b, size in sm.get_matching_blocks():
        if size < 3:
            continue
        for k in range(1, size):
            if n_space[b + k]:
                add.add(o_idx[a + k])
    if not add:
        return old
    out = []
    for i, c in enumerate(old):
        if i in add and out and not out[-1].isspace():
            # never split an e-mail / url / number
            left, right = old[i - 1], c
            if not (left in "@.-_/:" and False) and not (left.isdigit() and right.isdigit()):
                out.append(" ")
        out.append(c)
    return "".join(out)


def _warp_quad(img, quad):
    """Perspective-crop a (possibly tilted) text quad to an upright rectangle."""
    import cv2
    import numpy as np
    q = quad.astype(np.float32)
    w = int(max(np.linalg.norm(q[0] - q[1]), np.linalg.norm(q[2] - q[3])))
    h = int(max(np.linalg.norm(q[0] - q[3]), np.linalg.norm(q[1] - q[2])))
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(q, dst)
    return cv2.warpPerspective(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC)


def _stitch(a: str, b: str) -> str:
    """Join two overlapping chunk readings: find the best overlap of a's tail and b's head."""
    best = 0
    for k in range(min(len(a), len(b), 12), 1, -1):
        if a[-k:] == b[:k]:
            best = k
            break
    if best:
        return a + b[best:]
    from difflib import SequenceMatcher
    ta, hb = a[-12:], b[:12]
    m = SequenceMatcher(None, ta, hb, autojunk=False).find_longest_match(0, len(ta), 0, len(hb))
    if m.size >= 3:
        return a[: len(a) - len(ta) + m.a + m.size] + b[m.b + m.size:]
    return a + b


def _dedupe(cands):
    """Drop boxes that overlap a better (wider, then higher score) box of the same line."""
    def bbox(q):
        return q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()
    order = sorted(cands, key=lambda c: (-(bbox(c[0])[2] - bbox(c[0])[0]), -c[2]))
    kept = []
    for c in order:
        x0, y0, x1, y1 = bbox(c[0])
        dup = False
        for k in kept:
            X0, Y0, X1, Y1 = bbox(k[0])
            iw = min(x1, X1) - max(x0, X0)
            hmin = min(y1 - y0, Y1 - Y0)
            # same line seen in two bands: centres nearly coincide and x ranges overlap
            if iw > 0.5 * min(x1 - x0, X1 - X0) and abs((y0 + y1) - (Y0 + Y1)) / 2 < 0.4 * hmin:
                dup = True
                break
        if not dup:
            kept.append(c)
    return kept


_CLAUDE_PROMPT = (
    "This is a photo of a page of the China Import and Export Fair exhibitor catalog. "
    "Transcribe ALL body text exactly, line by line, in reading order: the whole LEFT column "
    "top to bottom, then a line containing only '<<<COLUMN>>>', then the whole RIGHT column. "
    "Skip the fair logo at the top, the vertical side tab on the right and the booth legend box. "
    "On the very last line output 'PAGE: <printed page number>' if visible. "
    "Keep Chinese and English exactly as printed, keep '*' and brackets. Output only the text."
)


class ClaudeEngine(OcrEngine):
    """Vision transcription via the Anthropic API. Returns one pseudo-box per line,
    laid out so layout.to_reading_lines keeps the order (left col, then right col)."""
    name = "claude"

    def __init__(self, model: str | None = None):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("The 'claude' OCR engine needs the ANTHROPIC_API_KEY environment variable.")
        import anthropic
        self._client = anthropic.Anthropic()
        self._model = model

    def read(self, image_path: str, settings: Settings) -> list[OcrBox]:
        import io
        from PIL import Image, ImageOps

        with Image.open(image_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            im.thumbnail((1568, 1568))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
        data = base64.standard_b64encode(buf.getvalue()).decode()
        msg = self._client.messages.create(
            model=self._model or settings.claude_model or "claude-haiku-5-5",
            max_tokens=8000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
                {"type": "text", "text": _CLAUDE_PROMPT},
            ]}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return claude_text_to_boxes(text, w, h, settings)


def claude_text_to_boxes(text: str, w: int, h: int, settings: Settings) -> list[OcrBox]:
    """Place transcribed lines in synthetic positions inside the body area."""
    left, right, page = [], [], None
    cur = left
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s == "<<<COLUMN>>>":
            cur = right
            continue
        if s.upper().startswith("PAGE:"):
            page = s.split(":", 1)[1].strip()
            continue
        cur.append(s)
    top = h * (settings.header_ratio + 0.01)
    bottom = h * (1 - settings.footer_ratio - 0.01)
    body_w = w * (1 - settings.side_tab_ratio)
    boxes: list[OcrBox] = []
    for col, (x0, x1) in ((left, (0.02 * w, 0.46 * body_w)), (right, (0.54 * body_w, 0.98 * body_w))):
        n = max(len(col), 1)
        step = (bottom - top) / n
        for i, s in enumerate(col):
            y0 = top + i * step
            boxes.append(OcrBox(s, x0, y0, x1, y0 + step * 0.8, 1.0))
    if page:
        y = h * (1 - settings.footer_ratio / 2)
        boxes.append(OcrBox(page, body_w * 0.9, y - 10, body_w * 0.95, y + 10, 1.0))
    return boxes


def get_engine(name: str, model: str | None = None) -> OcrEngine:
    name = (name or "rapidocr").lower()
    if name == "claude":
        return ClaudeEngine(model)
    if name == "rapidocr":
        return RapidOcrEngine()
    raise ValueError(f"Unknown OCR engine: {name!r} (use 'rapidocr' or 'claude')")
