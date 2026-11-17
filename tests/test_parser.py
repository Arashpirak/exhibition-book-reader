from exhibit_reader.layout import CAT_MARK
from exhibit_reader.parser import normalize_booth, parse_lines


def test_normalize_booth_variants():
    assert normalize_booth("17.1A01-02, 17.1B22-23") == ("17.1A01-02,17.1B22-23", True)
    assert normalize_booth("17.1AO3") == ("17.1A03", True)
    assert normalize_booth("171C13")[0] == "17.1C13"
    booth, ok = normalize_booth("17.1B33-35,17.1C10-12,17.1H24-26,17.117-19")
    assert booth == "17.1B33-35,17.1C10-12,17.1H24-26,17.1I17-19" and not ok


FULL = [
    CAT_MARK + "动力、电力设备",
    CAT_MARK + "Power Machinery and Electric Power",
    "*（17.1A01-02，17.1B22-23）百发动力（无锡）有限公司",
    "BAIFA POWER (WUXI) LTD.",
    "江苏省无锡市锡山国家经济技术开发区安泰三路972号（邮",
    "政编码：214106)",
    "NO.972,ANTAI 3RD ROAD,XISHAN ECO&TECH",
    "DEVELOPMENT ZONE,WUXI,JIANGSU,CHINA",
    "TEL:86-510-85345555~FAX:86-510-85345566",
    "E-MAIL: marketing@baifapower.com",
    "URL: www.baifapower.com",
    "（17.1A08-12）福建省亚南科技股份有限公",
    "司",
    "FUJIAN YANAN TECHNOLOGY CO.,LTD",
    "浙江省台州市路桥区横街绿田大道一号（邮政编码",
    "：318056)",
    "NO.1 LUTIAN ROAD",
    "E-MAlL: sales@yanan -motor.com",
    "URL:wwW.Yanan-motor.com",
]


def test_full_records():
    recs = parse_lines(FULL, "p.jpg", "001")
    assert len(recs) == 2
    a, b = recs
    assert a.booth == "17.1A01-02,17.1B22-23" and a.domestic_sale and not a.is_continuation
    assert a.name_cn == "百发动力(无锡)有限公司"
    assert a.name_en == "BAIFA POWER (WUXI) LTD."
    assert a.address_cn == "江苏省无锡市锡山国家经济技术开发区安泰三路972号"
    assert a.postcode == "214106"
    assert a.address_en == "NO.972, ANTAI 3RD ROAD, XISHAN ECO&TECH DEVELOPMENT ZONE, WUXI, JIANGSU, CHINA"
    assert (a.tel, a.fax) == ("86-510-85345555", "86-510-85345566")
    assert a.email == "marketing@baifapower.com" and a.url == "www.baifapower.com"
    assert (a.category_cn, a.category_en) == ("动力、电力设备", "Power Machinery and Electric Power")
    assert a.page_no == "001" and a.source_image == "p.jpg"
    assert not b.domestic_sale
    assert b.name_cn == "福建省亚南科技股份有限公司"
    assert b.name_en == "FUJIAN YANAN TECHNOLOGY CO.,LTD"
    assert b.postcode == "318056" and b.address_en == "NO.1 LUTIAN ROAD"
    assert b.email == "sales@yanan-motor.com" and b.url == "www.yanan-motor.com"


def test_page_starting_mid_record():
    lines = ["22/F.,YUANTAI BLDG.,QUANZHOU,FUJIAN",
             "TEL:86-595-22184028~FAX:86-595-22287517",
             "E-MAIL:info@cmecqz.com",
             "*(17.1B44-46) 毅飞泵业（福州）有限公司",
             "EIFEL PUMP(FUZHOU) CORPN.,LTD"]
    recs = parse_lines(lines, "p3.jpg", "003")
    frag, rec = recs
    assert frag.is_continuation and frag.booth == ""
    assert frag.address_en.startswith("22/F.") and frag.email == "info@cmecqz.com"
    assert frag.tel == "86-595-22184028"
    assert rec.booth == "17.1B44-46" and rec.name_en == "EIFEL PUMP (FUZHOU) CORPN.,LTD"


def test_name_en_wrap_and_missing_bracket_and_paren_fix():
    lines = ["*(17.1B42-43 福建省泉州机械设备进出口有限责任公司",
             "FUJIAN QUANZHOU MACHINERY & EQUIPMENT",
             "I/E CORP.",
             "福建省泉州市远太大厦22层（邮政编码：362000)",
             "*（17.1C23-24）普力迈动力科技（无锡）有限",
             "公司",
             "PRIME POWER TECHNOLOGY WUXI) CO.,LTD."]
    a, b = parse_lines(lines, "x.jpg", None)
    assert a.booth == "17.1B42-43"
    assert a.name_en == "FUJIAN QUANZHOU MACHINERY & EQUIPMENT I/E CORP."
    assert a.address_cn == "福建省泉州市远太大厦22层" and a.postcode == "362000"
    assert b.name_cn == "普力迈动力科技(无锡)有限公司"
    assert b.name_en == "PRIME POWER TECHNOLOGY (WUXI) CO.,LTD."


def test_record_split_across_columns_stays_one_record():
    # left column ends with only the start line; right column starts with its English name
    lines = ["*（17.1C13）福建佰腾动力设备有限公司",
             "FUJIAN POWERSOURCE EQUIPMENT CO.,LTD",
             "福建省宁德市福安市溪柄镇工业园区宸山小区A3地块）",
             "（邮政编码：355000）",
             "E-MAIL: manager@hongfumotor.com"]
    (r,) = parse_lines(lines, "x.jpg", "003")
    assert r.name_en == "FUJIAN POWERSOURCE EQUIPMENT CO.,LTD"
    assert r.postcode == "355000" and r.address_cn.endswith("A3地块")


def test_empty_postcode_and_tel_only():
    lines = ["*（17.1B21）河南天力电气设备有限公司", "HENAN TIANLI ELECTRIC EQUIPMENT CO.,LTD",
             "南阳高新技术产业集聚区纬十路东段（邮政编码：）", "NANYANG CITY", "TEL:86-377-63708112"]
    (r,) = parse_lines(lines, "x.jpg", "002")
    assert r.postcode == "" and r.address_cn == "南阳高新技术产业集聚区纬十路东段"
    assert r.tel == "86-377-63708112" and r.fax == ""


def test_english_word_spacing():
    from exhibit_reader.parser import fix_en_spacing as f
    assert f("ANHUI WANNAN ELECTRICMACHINE CO.,LTD") == "ANHUI WANNAN ELECTRIC MACHINE CO.,LTD"
    assert f("JIANGSU YUANZHONG MOTORSSHARE CO.,LTD.") == "JIANGSU YUANZHONG MOTORS SHARE CO.,LTD."
    assert f("EIFELPUMP(FUZHOU)CORPN.,LTD") == "EIFEL PUMP (FUZHOU) CORPN.,LTD"
    assert f("FUJIAN POWERSOURCEEQUIPMENTCO.,LTD") == "FUJIAN POWERSOURCE EQUIPMENT CO.,LTD"
    assert f("HENAN TIANLI ELECTRICEQUIPMENT CO.,LTD") == "HENAN TIANLI ELECTRIC EQUIPMENT CO.,LTD"
    assert f("CAOJIEINDUSTRIALPARK,HECHUANDISTRICT") == "CAOJIE INDUSTRIAL PARK, HECHUAN DISTRICT"
    assert f("NO.8-1JINGXINROAD") == "NO.8-1 JINGXIN ROAD"
    assert f("BAIFA POWER (WUXI) LTD.") == "BAIFA POWER (WUXI) LTD."   # untouched when already fine
    assert f("YONGSHENG") == "YONGSHENG"                             # pinyin left alone


def test_cjk_fixes():
    from exhibit_reader.parser import dedupe_cn_prefix, fix_cn
    assert fix_cn("安微皖南电机股份有限公司") == "安徽皖南电机股份有限公司"
    assert dedupe_cn_prefix("福建镜福建鲁士电机有限公司") == "福建镜鲁士电机有限公司"
    assert dedupe_cn_prefix("江苏苏美达集团有限公司") == "江苏苏美达集团有限公司"
    (r,) = parse_lines(["（17.1A21）安微皖南电机股份有限公司", "ANHUI WANNAN ELECTRICMACHINE CO.,LTD"], "x", None)
    assert r.name_cn == "安徽皖南电机股份有限公司" and r.name_en == "ANHUI WANNAN ELECTRIC MACHINE CO.,LTD"


def test_en_cleanup_digits_and_commas():
    from exhibit_reader.parser import fix_en_spacing, fix_street_no
    assert fix_en_spacing("NO. 5O, DONGQING STREET") == "NO. 50, DONGQING STREET"
    assert fix_en_spacing("NO.8-1JINGXIN ROAD") == "NO.8-1 JINGXIN ROAD"
    assert fix_en_spacing("ANTAI 3RD ROAD, WUXI JIANGSU , CHINA") == "ANTAI 3RD ROAD, WUXI JIANGSU, CHINA"
    assert fix_street_no("NO.6, NANHUA ROAD", "安徽省宣城市泾县泾川镇南华路86号") == "NO.86, NANHUA ROAD"
    assert fix_street_no("NO.14 JINGLIN ROAD", "福建省福安市景林路14号") == "NO.14 JINGLIN ROAD"
    assert fix_street_no("NO.7 X ROAD", "某路19号") == "NO.7 X ROAD"


def test_transfer_spaces_only_adds_spaces():
    from exhibit_reader.ocr_engine import transfer_spaces
    assert transfer_spaces("NO.303KANGLIU ROADKANGQIAO INDUSTRIAL",
                           "NO. 303 KANGLIU ROAD KANGQIAO INDUSTRIAL") == "NO. 303 KANGLIU ROAD KANGQIAO INDUSTRIAL"
    # a worse second reading never changes characters
    assert transfer_spaces("E-MAIL:isaac@koopchina.com", "E-MAIL: isac@koopchina.com") == "E-MAIL: isaac@koopchina.com"
    assert transfer_spaces("TONGXIN ECONOMIC ZONE", "TONGXINEONMCDEVEOPMEN") == "TONGXIN ECONOMIC ZONE"
