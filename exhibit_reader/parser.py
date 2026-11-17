"""Turn reading-order body lines of one catalog page into ExhibitorRecord objects."""
from __future__ import annotations

import re

from .layout import CAT_MARK
from .models import ExhibitorRecord

_FW = str.maketrans({"（": "(", "）": ")", "，": ",", "：": ":", "～": "~", "　": " ", "；": ";",
                     "－": "-", "—": "-", "–": "-", "．": "."})
_CJK = re.compile(r"[㐀-鿿]")
_LATIN = re.compile(r"[A-Za-z]")

# start line: optional "*", "(" booth list ")" then the Chinese name; ")" may be lost by OCR
_START = re.compile(r"^\s*(\*?)\s*\(\s*(\d[0-9A-Za-z.,\-~\s]*?)\s*\)?\s*([㐀-鿿].*|)$")
_SEG = re.compile(r"^(\d{1,2})\.(\d)([A-Z])(\d{2})(?:-(\d{1,2}))?$")
_SEG_NOLETTER = re.compile(r"^(\d{2})\.(\d)(\d{2})(?:-(\d{1,2}))?$")
_SEG_NODOT = re.compile(r"^(\d{2})(\d)([A-Z])(\d{2})(?:-(\d{1,2}))?$")

_TEL = re.compile(r"T\s*E\s*L\s*[:.]?\s*([0-9][0-9\-\s/()+,]*[0-9])", re.I)
_FAX = re.compile(r"F\s*A\s*X\s*[:.]?\s*([0-9][0-9\-\s/()+,]*[0-9])", re.I)
_EMAIL = re.compile(r"^\s*E\s*[-_.]?\s*M\s*A\s*[IlL1|]\s*[IlL1|]\s*[:.]?\s*(.*)$", re.I)
_URL = re.compile(r"^\s*(?:URL|UR1|UPL)\s*[:.]?\s*(.*)$", re.I)
_POST = re.compile(r"[(]?\s*邮\s*政?\s*编?\s*码?\s*[:]?\s*(\d*)\s*\)*")
_CO_EN = re.compile(r"(CO\.?\s*,?\s*LTD\.?|LTD\.?|LIMITED|CORP(?:ORATION|N)?\.?|COMPANY|INC\.?|GROUP|"
                    r"FACTORY|CO\.)\s*$", re.I)
_CO_CN = re.compile(r"(公司|集团|厂|中心|研究所|商行|合作社|研究院)$")
_ADDR_CN_HINT = re.compile(r"邮|号|路|街|区|镇|村|园|楼|层|大厦")


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line.translate(_FW)).strip()


def normalize_booth(raw: str) -> tuple[str, bool]:
    """'17.1A01-02, 17.1B22-23' -> ('17.1A01-02,17.1B22-23', ok). ok=False if a segment was guessed."""
    ok = True
    segs = []
    for seg in re.split(r"[,;]", raw):
        s = seg.replace(" ", "").replace("~", "-")
        if not s:
            continue
        # OCR confusions inside the numeric parts
        s = re.sub(r"(?<=[\d.])[Oo](?=[\d\-]|$)", "0", s)
        m = re.match(r"^(\d{1,2}\.\d[A-Z])([0-9OolI|\-]+)$", s)
        if m:  # after the row letter only digits are allowed
            s = m.group(1) + m.group(2).translate(str.maketrans("OolI|", "00111"))
        m = _SEG.match(s)
        if m:
            segs.append(s)
            continue
        m = _SEG_NODOT.match(s)
        if m:
            segs.append(f"{m.group(1)}.{m.group(2)}{m.group(3)}{m.group(4)}" + (f"-{m.group(5)}" if m.group(5) else ""))
            continue
        m = _SEG_NOLETTER.match(s)
        if m:  # the thin letter "I" is the one OCR drops
            segs.append(f"{m.group(1)}.{m.group(2)}I{m.group(3)}" + (f"-{m.group(4)}" if m.group(4) else ""))
            ok = False
            continue
        segs.append(s)
        ok = False
    return ",".join(segs), ok


def _clean_email(s: str) -> str:
    s = s.replace(" ", "").strip(" .,;:")
    s = s.replace("。", ".").replace("，", ",")
    return s


def _clean_url(s: str) -> str:
    s = s.replace(" ", "").strip(" .,;:").replace("。", ".")
    i = s.lower().find("www.")
    if i > 0:
        s = s[i:]
    return s.lower()


# ---- English word spacing: RapidOCR often drops the spaces between English words.
# Long run-together uppercase runs are re-split on known catalog words (pinyin place names
# are left as unknown chunks, e.g. "JINGXINROAD" -> "JINGXIN ROAD").
_EN_WORDS = set("""
ELECTRIC ELECTRICAL ELECTRICITY ELECTRONIC ELECTRONICS MACHINE MACHINES MACHINERY MECHANICAL
MOTOR MOTORS SHARE PUMP PUMPS EQUIPMENT POWER POWERSOURCE TECHNOLOGY TECHNOLOGICAL SCIENCE
INDUSTRIAL INDUSTRY DEVELOPMENT ECONOMIC ROAD STREET AVENUE ZONE PARK TOWN CITY COUNTY DISTRICT
PROVINCE CHINA AREA BUILDING FLOOR GROUP CORPORATION CORPN COMPANY LIMITED TRADING IMPORT EXPORT
GENERATOR GENERATORS ENGINE ENGINES DIESEL GASOLINE MANUFACTURING INTERNATIONAL HOLDING HOLDINGS
COMMUNITY PLOT SECTION EAST WEST SOUTH NORTH HIGH TECH NEW ENERGY TRANSMISSION
FUJIAN JIANGSU ZHEJIANG SHANGHAI SICHUAN CHONGQING SHENZHEN GUANGDONG SHANDONG FUZHOU NANTONG
CHANGZHOU QUANZHOU TAIZHOU ZHENGZHOU NANJING NANYANG NINGDE
""".split())
_EN_AFTER_WORD = {"AND", "OF"}   # short words: only accepted right after a known word ("OF" also at run start)
_EN_TAIL = {"ECO", "CO", "LTD"}  # accepted only as the last piece of a run


def _split_run(run: str) -> str:
    if len(run) < 6 or run in _EN_WORDS:
        return run
    n = len(run)
    # best[i] = (unknown_chars, pieces, segmentation) for run[:i]
    best: list = [None] * (n + 1)
    best[0] = (0, 0, [])
    for i in range(n):
        if best[i] is None:
            continue
        unk, pcs, seg = best[i]
        prev_known = bool(seg) and seg[-1][1]
        for j in range(i + 2, n + 1):
            w = run[i:j]
            ok = w in _EN_WORDS or (w in _EN_AFTER_WORD and (prev_known or (w == "OF" and i == 0))) \
                or (w in _EN_TAIL and j == n)
            if ok:
                cand = (unk, pcs + 1, seg + [(w, True)])
                if best[j] is None or cand[:2] < best[j][:2]:
                    best[j] = cand
        # one unknown char (extends the previous unknown chunk)
        if seg and not seg[-1][1]:
            cand = (unk + 1, pcs, seg[:-1] + [(seg[-1][0] + run[i], False)])
        else:
            cand = (unk + 1, pcs + 1, seg + [(run[i], False)])
        if best[i + 1] is None or cand[:2] < best[i + 1][:2]:
            best[i + 1] = cand
    unk, _, seg = best[n]
    if not any(k for _, k in seg) or any(len(w) < 2 and not k for w, k in seg):
        return run
    return " ".join(w for w, _ in seg)


def fix_en_spacing(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"(?<=\d)[Oo](?![A-Za-z])", "0", s)             # "NO.5O," -> "NO.50,"
    s = re.sub(r"[A-Z]{6,}", lambda m: _split_run(m.group(0)), s)
    s = re.sub(r"(?<=\d)(?=[A-Z]{4,})", " ", s)                # "NO.8-1JINGXIN" -> "NO.8-1 JINGXIN" (keeps "3RD")
    s = re.sub(r"\s+([,;])", r"\1", s)                         # "JIANGSU , CHINA" -> "JIANGSU, CHINA"
    s = re.sub(r"(?<=[A-Za-z])\(", " (", s)                    # "PUMP(FUZHOU" -> "PUMP (FUZHOU"
    s = re.sub(r"\)(?=[A-Za-z])", ") ", s)                     # "(FUZHOU)CORPN" -> "(FUZHOU) CORPN"
    s = re.sub(r",(?!\s*LTD)(?=[A-Za-z])", ", ", s)            # keep "CO.,LTD"
    s = re.sub(r"(?<=[A-Za-z]{2})\.(?=[A-Z]{2})", ". ", s)     # "EXP.CO" -> "EXP. CO" (not "P.R.CHINA")
    s = re.sub(r"\bCO\s*\.?\s*,\s*LTD", "CO.,LTD", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def fix_street_no(addr_en: str, addr_cn: str) -> str:
    """OCR sometimes drops the first digit of the English street number ("NO.6" for "NO. 86").
    The Chinese address of the same record carries the same number ("…路86号"): use it when the
    English one is a proper suffix of it."""
    m_en = re.search(r"\bNO\s*\.?\s*(\d+(?:-\d+)?)(?![\d-])", addr_en, re.I)
    m_cn = re.search(r"(\d+(?:-\d+)?)号", addr_cn)
    if m_en and m_cn:
        en, cn = m_en.group(1), m_cn.group(1)
        if en != cn and cn.endswith(en) and len(cn) - len(en) <= 2:
            return addr_en[: m_en.start(1)] + cn + addr_en[m_en.end(1):]
    return addr_en


# ---- Chinese OCR slips
_CN_FIX = {"安微": "安徽", "江办": "江苏", "浙汀": "浙江", "福健": "福建", "四JII": "四川", "广冻": "广东",
           "山冻": "山东", "河曲": "河南", "湖冂": "湖南", "重决": "重庆", "上梅": "上海", "无钖": "无锡"}


def fix_cn(s: str) -> str:
    for a, b in _CN_FIX.items():
        s = s.replace(a, b)
    return s


def dedupe_cn_prefix(s: str) -> str:
    """'福建镜福建鲁士电机…' -> '福建镜鲁士电机…' (OCR repeated a 2-4 char leading prefix)."""
    m = re.match(r"^([㐀-鿿]{2,4})([㐀-鿿]{0,2}?)\1", s)
    return s[: m.end(2)] + s[m.end():] if m else s


def _join_en(a: str, b: str) -> str:
    if not a:
        return b
    if a.endswith(("-", "/")):
        return a + b
    return a + " " + b


class _Rec:
    def __init__(self, rec: ExhibitorRecord):
        self.r = rec
        self.state = "start"         # start -> name_cn -> name_en -> addr_cn -> addr_en -> contact
        self.addr_cn_raw = ""
        self.lines: list[str] = []
        self.scores: list[float] = []

    def finish(self) -> ExhibitorRecord:
        r = self.r
        if self.addr_cn_raw:
            raw = self.addr_cn_raw
            m = _POST.search(raw)
            if m:
                r.postcode = m.group(1)
                raw = (raw[: m.start()] + raw[m.end():])
            r.address_cn = raw.strip(" ()")
        r.name_en = r.name_en.strip(" ,")
        if r.name_en.count(")") > r.name_en.count("("):  # OCR often loses "(" : "BAIFA POWER WUXI) LTD."
            r.name_en = re.sub(r"(\w+)\)", lambda m: "(" + m.group(1) + ")", r.name_en, count=1)
        r.address_en = fix_en_spacing(r.address_en.strip(" ,"))
        r.name_en = fix_en_spacing(r.name_en)
        r.address_en = fix_street_no(r.address_en, r.address_cn)
        r.name_cn = dedupe_cn_prefix(fix_cn(r.name_cn))
        r.address_cn = fix_cn(r.address_cn)
        r.raw_text = "\n".join(self.lines)
        if self.scores:
            r.confidence = round(sum(self.scores) / len(self.scores), 3)
        return r

    # ---- line handlers
    def add(self, line: str, score: float | None = None):
        self.lines.append(line)
        if score is not None:
            self.scores.append(score)
        r = self.r
        if _EMAIL.match(line):
            r.email = r.email or _clean_email(_EMAIL.match(line).group(1))
            self.state = "contact"
            return
        if _URL.match(line) or line.lower().startswith("www."):
            m = _URL.match(line)
            r.url = r.url or _clean_url(m.group(1) if m else line)
            self.state = "contact"
            return
        if re.match(r"^\s*(TEL|FAX)\b", line, re.I) or ("~" in line and _TEL.search(line)):
            left, _, right = line.partition("~")
            t = _TEL.search(line)
            f = _FAX.search(right or line)
            if t:
                r.tel = r.tel or t.group(1).replace(" ", "").strip(",")
            if f:
                r.fax = r.fax or f.group(1).replace(" ", "").strip(",")
            self.state = "contact"
            return
        if self.state == "addr_cn" and re.match(r"^[:(]*\s*\d{5,6}\s*\)*$", line):
            self.addr_cn_raw += line.replace(" ", "")   # wrapped "(邮政编码" / ":318056)"
            return
        if _CJK.search(line):
            self._add_cjk(line)
        elif _LATIN.search(line) or re.search(r"\d", line):
            self._add_latin(line)

    def _add_cjk(self, line: str):
        r = self.r
        name_open = self.state in ("start", "name_cn") and (
            (r.name_cn and not _CO_CN.search(r.name_cn)) or (not r.name_cn and self.state == "name_cn"))
        if name_open and "邮" not in line and not re.search(r"\d+号", line) and \
                (len(line) <= 14 or _CO_CN.search(line)):
            r.name_cn += line.replace(" ", "")
            self.state = "name_cn"
            return
        if self.state == "start" and not r.name_cn and not r.booth and len(line) <= 3 and line.endswith("司"):
            r.name_cn = line  # tail of a name wrapped from the previous page
            self.state = "name_cn"
            return
        self.addr_cn_raw += line.replace(" ", "")
        self.state = "addr_cn"

    def _add_latin(self, line: str):
        r = self.r
        if self.state == "start":
            # fragment at the top of a page: decide by content
            target = "name_en" if _CO_EN.search(line) and not re.search(r"\b(ROAD|RD|STREET|ZONE|NO\.)", line, re.I) \
                else "addr_en"
        elif self.state == "name_cn":
            target = "name_en"
        elif self.state == "name_en":
            target = "addr_en" if _CO_EN.search(r.name_en) else "name_en"
        elif self.state in ("addr_cn", "addr_en"):
            target = "addr_en"
        else:  # after contact lines: stray text, keep only in raw_text
            return
        if target == "name_en":
            r.name_en = _join_en(r.name_en, line)
            self.state = "name_en"
        else:
            r.address_en = _join_en(r.address_en, line)
            self.state = "addr_en"


def parse_lines(lines: list[str], source_image: str, page_no: str | None,
                scores: list[float] | None = None) -> list[ExhibitorRecord]:
    """Parse body lines (reading order) of one page.

    The first record has booth=="" and is_continuation=True when the page starts mid-record.
    Lines starting with layout.CAT_MARK set category_cn / category_en for following records.
    """
    out: list[ExhibitorRecord] = []
    cur: _Rec | None = None
    cat_cn = cat_en = ""

    def new_rec(**kw) -> _Rec:
        return _Rec(ExhibitorRecord(page_no=page_no or "", source_image=source_image,
                                    category_cn=cat_cn, category_en=cat_en, **kw))

    for i, raw in enumerate(lines):
        sc = scores[i] if scores and i < len(scores) else None
        if raw.startswith(CAT_MARK):
            t = _norm(raw[len(CAT_MARK):])
            if _CJK.search(t):
                cat_cn = t
            else:
                cat_en = t
            continue
        line = _norm(raw)
        if not line:
            continue
        m = _START.match(line)
        if m and re.search(r"\d{1,2}\.?\d[A-Z]?\d{2}", m.group(2).replace(" ", "")):
            if cur:
                out.append(cur.finish())
            booth, ok = normalize_booth(m.group(2))
            cur = new_rec(booth=booth, domestic_sale=bool(m.group(1)))
            cur.lines.append(line)
            if sc is not None:
                cur.scores.append(sc * (1.0 if ok else 0.8))
            cur.r.name_cn = m.group(3).replace(" ", "")
            cur.state = "name_cn"
            continue
        if cur is None:
            cur = new_rec(is_continuation=True)
        cur.add(line, sc)
    if cur:
        out.append(cur.finish())
    return out
