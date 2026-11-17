---
name: exhibition-catalog-format
description: Layout and field rules of the China Import and Export Fair exhibitor catalog photos in this project. Load before writing or debugging OCR, layout, or parsing code for exhibit_reader.
---

# Catalog page anatomy (photos ~1440x2560, phone shots, slight tilt/curl, grey shadow possible)

- Top ~13%: fair logo "中国进出口商品交易会 / CHINA IMPORT AND EXPORT FAIR Since 1957" — ignore.
- Right ~10%: vertical side tab "D 区", "动力、电力设备", "Area D", "Power Machinery and Electric Power" — use only to fill `area`/category, never as record text.
- Bottom-right: printed page number "001", "003" — store as `page_no`.
- Page 001 also has a "Booth Legend 展位位置解析" box and a "温馨提示 … (Note): '*' means the exhibitor has the intention of domestic sale" note — skip.
- Section header box: Chinese category (e.g. "动力、电力设备") + English ("Power Machinery and Electric Power") → `category_cn/en` for following records.
- Body: TWO text columns. Reading order = whole left column top→bottom, then right column. Faint bleed-through text from the next page may appear (low OCR score / light grey) — drop low-confidence boxes.

# Record pattern (one exhibitor)
```
*(17.1A01-02,17.1B22-23) 百发动力(无锡)有限公司          <- start line: optional "*", booth list in (), Chinese name (may wrap: "…有限公" / "司")
BAIFA POWER (WUXI) LTD.                                 <- English name, UPPERCASE, may wrap to 2 lines
江苏省无锡市…安泰三路972号 (邮政编码: 214106)              <- Chinese address; "(邮政编码：NNNNNN)" may wrap ("(邮政编码" / "：318056)")
NO. 972, ANTAI 3RD ROAD, … CHINA.                        <- English address, 1-3 lines
TEL:86-510-85345555 ~ FAX:86-510-85345555               <- optional; TEL and FAX split on "~"
E-MAIL: marketing@baifapower.com                         <- optional
URL: www.baifapower.com                                  <- optional
```
- Booth regex: `^\*?\s*[（(]\s*(\d{1,2}\.\d[A-Z]\d{2}(?:-\d{2})?(?:\s*[,，]\s*\d{1,2}\.\d[A-Z]\d{2}(?:-\d{2})?)*)\s*[)）]` — OCR may give full-width brackets/commas, `O` for `0`, `l` for `1`; normalise first.
- Colons may be full-width `：`. "E-MAIL" may OCR as "E-MAlL"/"EMAIL". Strip spaces inside emails/urls.
- A page can START mid-record (e.g. page 003 begins with English address/TEL/E-MAIL/URL lines of the previous page's last exhibitor) → emit a fragment with `booth=""`, `is_continuation=True`; pipeline merges it into the previous record.
- A page can END with only the start line (e.g. "*(17.1C13) 福建佰腾动力设备有限公司") — rest continues on the next page's left column... and the right column may start with the English name of a record that started at the bottom of the left column ("FUJIAN POWERSOURCE EQUIPMENT CO.,LTD" at top of right col page 003 belongs to the record started at the bottom of left col). So: continuation fragments can appear at the top of ANY column; attach to the immediately preceding record in reading order (previous column, or previous page).
- Field classification of a non-start line: contains CJK → Chinese name/address; `TEL`/`FAX` → phones; `E-MAIL` → email; `URL`/`www.` → url; Latin uppercase right after name_cn and before any CJK address → name_en; Latin after address_cn → address_en.

# Accuracy targets (on the 3 sample pages)
Every booth code found (page 001: 9 records, page 003: ~11 incl. fragments). Emails/URLs exact. No logo/side-tab text in any field.
