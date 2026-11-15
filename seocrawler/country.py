"""Страна сайта: на какую страну работает бизнес - по признакам с самого сайта, а не по месту хостинга.

Признаки (всё из базы проверки, без нейросетей и внешних сервисов):
- доменная зона: .kz → Казахстан, .ru и .рф → Россия; общие зоны (.com, .net, .io, .online…) ничего не говорят;
- телефоны со страниц: код страны (+375 - Беларусь, +998 - Узбекистан…); у +7 по следующей цифре: 6 и 7 -
  Казахстан, остальные - Россия;
- валюта цен в тексте страниц: ₸ / тг / тенге, ₽ / руб, ₴ / грн, BYN и т. д.;
- регион в языке страницы: og:locale ru_KZ, <html lang="ru-KZ">, hreflang kk-KZ; язык без региона - только
  язык страны (kk - Казахстан, uk - Украина…). ru_RU стоит по умолчанию во многих конструкторах, поэтому весит мало.
Каждый признак даёт баллы стране; страна с наибольшей суммой - ответ, «точно», если она сильно впереди.
Где стоит сервер - отдельно, из «На чём сделан сайт» (site_tech: страна сети по RDAP, бесплатно), с пометкой,
если сайт за Cloudflare и подобными: тогда видно страну сервиса защиты, а не сервера.

Справочник стран ниже - обычные данные (код ISO, название, телефонный код, зоны, валюта, флаг), не список под сайт.
Флаг рисуется картинкой SVG (flag_svg): эмодзи-флаги в Windows не рисуются. Флаги упрощённые - без гербов
и мелких деталей; страны вне справочника - серая плашка с кодом."""
import json
import math
import re
import zlib
from collections import Counter

from .fmt import esc, num, plural

# код ISO: (название, телефонный код, валюта - шаблон рядом с числом, как назвать валюту)
COUNTRIES = {
    "RU": ("Россия", "7", r"₽|руб\.?|рубл[а-яё]*|RUB", "в рублях"),
    "KZ": ("Казахстан", "7", r"₸|тг\.?|тенге|KZT", "в тенге"),
    "BY": ("Беларусь", "375", r"BYN|бел\.?\s?руб[а-яё.]*", "в белорусских рублях"),
    "UA": ("Украина", "380", r"₴|грн\.?|гривен[а-яё]*|гривн[а-яё]*|UAH", "в гривнах"),
    "UZ": ("Узбекистан", "998", r"сум(?:ов|а)?|сўм|so'm|UZS", "в сумах"),
    "KG": ("Киргизия", "996", r"сом(?:ов|а)?|KGS", "в сомах"),
    "TJ": ("Таджикистан", "992", r"сомони|TJS", "в сомони"),
    "TM": ("Туркменистан", "993", r"TMT", "в манатах"),
    "AM": ("Армения", "374", r"֏|драм(?:ов)?|AMD", "в драмах"),
    "GE": ("Грузия", "995", r"₾|лари|GEL", "в лари"),
    "AZ": ("Азербайджан", "994", r"₼|манат[а-яё]*|AZN", "в манатах"),
    "MD": ("Молдова", "373", r"MDL|лей|леев|lei", "в леях"),
    "MN": ("Монголия", "976", r"₮|MNT|тугрик[а-яё]*", "в тугриках"),
    "LT": ("Литва", "370", "", ""), "LV": ("Латвия", "371", "", ""), "EE": ("Эстония", "372", "", ""),
    "PL": ("Польша", "48", r"zł|PLN|злот[а-яё]*", "в злотых"),
    "DE": ("Германия", "49", "", ""), "FR": ("Франция", "33", "", ""), "IT": ("Италия", "39", "", ""),
    "ES": ("Испания", "34", "", ""), "PT": ("Португалия", "351", "", ""),
    "GB": ("Великобритания", "44", r"£|GBP", "в фунтах"), "IE": ("Ирландия", "353", "", ""),
    "NL": ("Нидерланды", "31", "", ""), "BE": ("Бельгия", "32", "", ""), "LU": ("Люксембург", "352", "", ""),
    "AT": ("Австрия", "43", "", ""), "CH": ("Швейцария", "41", r"CHF", "во франках"),
    "CZ": ("Чехия", "420", r"Kč|CZK", "в кронах"), "SK": ("Словакия", "421", "", ""),
    "HU": ("Венгрия", "36", r"HUF|форинт[а-яё]*", "в форинтах"), "RO": ("Румыния", "40", r"RON", "в леях"),
    "BG": ("Болгария", "359", r"лв\.?|BGN", "в левах"), "RS": ("Сербия", "381", r"RSD|динар[а-яё]*", "в динарах"),
    "ME": ("Черногория", "382", "", ""), "HR": ("Хорватия", "385", "", ""), "SI": ("Словения", "386", "", ""),
    "GR": ("Греция", "30", "", ""), "CY": ("Кипр", "357", "", ""),
    "FI": ("Финляндия", "358", "", ""), "SE": ("Швеция", "46", r"SEK", "в кронах"),
    "NO": ("Норвегия", "47", r"NOK", "в кронах"), "DK": ("Дания", "45", r"DKK", "в кронах"),
    "TR": ("Турция", "90", r"₺|TRY|лир[аы]?", "в лирах"), "IL": ("Израиль", "972", r"₪|ILS|шекел[а-яё]*", "в шекелях"),
    "AE": ("ОАЭ", "971", r"AED|дирхам[а-яё]*", "в дирхамах"), "SA": ("Саудовская Аравия", "966", r"SAR", "в риалах"),
    "QA": ("Катар", "974", r"QAR", "в риалах"), "EG": ("Египет", "20", r"EGP", "в фунтах"),
    "IN": ("Индия", "91", r"₹|INR|рупи[а-яё]*", "в рупиях"), "CN": ("Китай", "86", r"CNY|RMB|юан[а-яё]*", "в юанях"),
    "JP": ("Япония", "81", r"JPY|иен[а-яё]*", "в иенах"), "KR": ("Южная Корея", "82", r"₩|KRW|вон[ау]?", "в вонах"),
    "TH": ("Таиланд", "66", r"฿|THB", "в батах"), "VN": ("Вьетнам", "84", r"₫|VND|донг[а-яё]*", "в донгах"),
    "ID": ("Индонезия", "62", r"IDR", "в рупиях"), "MY": ("Малайзия", "60", r"MYR", "в ринггитах"),
    "SG": ("Сингапур", "65", r"SGD", "в долларах"), "US": ("США", "1", r"USD", "в долларах"),
    "CA": ("Канада", "1", r"CAD", "в канадских долларах"), "MX": ("Мексика", "52", r"MXN", "в песо"),
    "BR": ("Бразилия", "55", r"R\$|BRL", "в реалах"), "AR": ("Аргентина", "54", r"ARS", "в песо"),
    "AU": ("Австралия", "61", r"AUD", "в австралийских долларах"), "NZ": ("Новая Зеландия", "64", r"NZD", "в долларах"),
    "ZA": ("ЮАР", "27", r"ZAR", "в рэндах"),
}
# зоны, которые не совпадают с кодом страны, и национальные зоны кириллицей
TLD_COUNTRY = {"uk": "GB", "su": "RU", "рф": "RU", "moscow": "RU", "москва": "RU", "spb": "RU", "tatar": "RU",
               "рус": "RU", "дети": "RU", "қаз": "KZ", "бел": "BY", "укр": "UA", "срб": "RS", "мкд": None}
# зоны стран, которые используют как общие: ничего не говорят о стране бизнеса
GENERIC_CC = {"io", "co", "me", "tv", "ai", "fm", "ws", "cc", "to", "ly", "gg", "la", "am", "md"}
# язык без региона: только язык одной страны
LANG_COUNTRY = {"kk": "KZ", "be": "BY", "uk": "UA", "uz": "UZ", "ky": "KG", "tg": "TJ", "tk": "TM", "hy": "AM",
                "ka": "GE", "az": "AZ", "mn": "MN", "lt": "LT", "lv": "LV", "et": "EE", "pl": "PL", "cs": "CZ",
                "sk": "SK", "hu": "HU", "bg": "BG", "sr": "RS", "hr": "HR", "sl": "SI", "el": "GR", "fi": "FI",
                "sv": "SE", "nb": "NO", "no": "NO", "da": "DK", "tr": "TR", "he": "IL", "ja": "JP", "ko": "KR",
                "th": "TH", "vi": "VN", "id": "ID", "ro": "RO"}

W_TLD, W_PHONE, W_MONEY, W_LOCALE, W_LANG = 3.0, 3.0, 3.0, 1.5, 1.0
_DIAL = sorted(((v[1], k) for k, v in COUNTRIES.items() if k not in ("KZ", "CA")), key=lambda x: -len(x[0]))
_INTL = re.compile(r"(?<![\w+])\+\s?(\d[\d\s\-\(\) ]{7,18}\d)")
_NUM = r"\d[\d\s .,]*"
_MONEY = {k: re.compile(r"(?:" + _NUM + r"\s?(?:" + v[2] + r")(?![a-zа-яё])|(?<![a-zа-яё])(?:" + v[2] + r")\s?\d)",
                        re.I)
          for k, v in COUNTRIES.items() if v[2]}


def name(code):
    return COUNTRIES.get(code, (code,))[0]


def phone_country(digits):
    """Страна по номеру без «+» (только цифры). +7: 6 и 7 после кода - Казахстан, иначе Россия."""
    if digits.startswith("7") and len(digits) == 11:
        return "KZ" if digits[1] in "67" else "RU"
    for dial, code in _DIAL:
        if digits.startswith(dial) and 8 <= len(digits) - len(dial) <= 12:
            return code
    return None


def tld_country(host):
    host = (host or "").lower().rstrip(".")
    try:
        host = host.encode("ascii").decode("idna") if "xn--" in host else host
    except Exception:
        pass
    tld = host.rsplit(".", 1)[-1]
    if tld in TLD_COUNTRY:
        return TLD_COUNTRY[tld], tld
    if len(tld) == 2 and tld not in GENERIC_CC and tld.isascii() and tld.isalpha():
        return tld.upper(), tld
    return None, tld


def _region(tag):
    """«ru-KZ», «ru_kz», «kk» → (регион, язык)."""
    p = re.split(r"[-_]", (tag or "").strip())
    lang = p[0].lower() if p and p[0] else ""
    reg = next((x.upper() for x in p[1:] if len(x) == 2 and x.isalpha()), "")
    return reg, lang


def detect(db, start, site_tech=None, max_pages=300):
    """{"code", "name", "sure": True/False, "why": [признаки], "scores", "server": {...}} или None, если признаков нет.
    db - sqlite-соединение с базой проверки, start - адрес сайта."""
    from urllib.parse import urlsplit
    score, why = Counter(), {}

    def add(code, pts, text):
        if code and pts > 0:
            score[code] += pts
            why.setdefault(code, []).append(text)

    host = urlsplit(start or "").hostname or ""
    code, tld = tld_country(host)
    add(code, W_TLD, f"домен .{tld}")

    cols = {r[1] for r in db.execute("PRAGMA table_info(pages)")}
    pick = [c for c in ("lang", "hreflang", "og", "contacts", "blocks") if c in cols]
    rows = db.execute(f"""SELECT {', '.join(pick)} FROM pages p JOIN urls u ON u.url=p.url
                          WHERE u.internal=1 AND u.kind='page' AND p.status=200 ORDER BY u.depth, p.url
                          LIMIT ?""", (max_pages,)).fetchall() if pick else []
    phones, money, locales, langs = set(), Counter(), Counter(), Counter()
    for row in rows:
        r = dict(zip(pick, row))
        try:
            c = json.loads(r.get("contacts") or "{}")
            phones.update(re.sub(r"\D", "", p) for p in c.get("phones") or [])
        except ValueError:
            pass
        text = ""
        if r.get("blocks"):
            try:
                text = zlib.decompress(r["blocks"]).decode("utf-8", "replace")
            except Exception:
                text = ""
        for m in _INTL.findall(text):
            phones.add(re.sub(r"\D", "", m))
        for k, rx in _MONEY.items():
            n = len(rx.findall(text))
            if n:
                money[k] += n
        tags = []
        try:
            og = json.loads(r.get("og") or "{}")
            if og.get("og:locale"):
                tags.append(("og:locale", og["og:locale"]))
        except ValueError:
            pass
        if r.get("lang"):
            tags.append(("lang", r["lang"]))
        for part in (r.get("hreflang") or "").split(";"):
            tag = part.strip().split(" ")[0]
            if tag and tag.lower() != "x-default":
                tags.append(("hreflang", tag))
        for src, tag in tags:
            reg, lang = _region(tag)
            if reg:
                locales[(src, reg, tag.replace("_", "-"))] += 1
            elif lang:
                langs[lang] += 1

    by_phone = Counter(phone_country(p) for p in phones if p)
    by_phone.pop(None, None)
    total = sum(by_phone.values())
    for code, n in by_phone.items():
        dial = "+7 " + ("6xx/7xx" if code == "KZ" else "3xx-9xx") if code in ("KZ", "RU") else "+" + COUNTRIES[code][1]
        add(code, W_PHONE * n / total, f"телефоны {dial}: {n} из {total}")
    total = sum(money.values())
    for code, n in money.items():
        if n >= 2 or total == n:
            add(code, W_MONEY * n / total, f"цены {COUNTRIES[code][3]} ({num(n)} {plural(n, 'раз', 'раза', 'раз')})")
    regs = Counter()
    for (src, reg, tag), n in locales.items():
        regs[reg] += n
    total = sum(regs.values())
    shown = {}
    for (src, reg, tag), n in sorted(locales.items(), key=lambda x: -x[1]):
        shown.setdefault(reg, f"{src} {tag}")
    for reg, n in regs.items():
        # ru-RU стоит по умолчанию во многих конструкторах (Tilda, WordPress): весит вдвое меньше
        add(reg, W_LOCALE * n / total * (0.5 if reg == "RU" else 1), shown[reg])
    for lang, n in langs.most_common(3):
        if lang in LANG_COUNTRY:
            add(LANG_COUNTRY[lang], W_LANG, f"язык страниц {lang}")

    server = server_info(site_tech)
    if not score:
        return {"code": "", "server": server} if server else None
    (best, pts), *rest = score.most_common()
    second = rest[0][1] if rest else 0
    others = [{"code": c, "name": name(c)} for c, p in rest if p >= max(2.0, pts / 2)]
    return {"code": best, "name": name(best), "sure": pts >= 4 and second <= pts / 2, "why": why[best],
            "scores": {c: round(p, 2) for c, p in score.most_common(5)}, "others": others, "server": server}


def server_info(site_tech):
    """Где стоит сервер: страна сети по RDAP из «На чём сделан сайт». За Cloudflare и подобными - страна сервиса."""
    t = site_tech or {}
    net = t.get("net") or {}
    cc = (net.get("country") or "").upper()
    if not cc:
        return None
    shield = (t.get("shields") or [{}])[0].get("name", "")
    return {"code": cc, "name": name(cc), "holder": t.get("hosting") or net.get("holder") or net.get("org") or "",
            "shield": shield}


def text(c, flag=True):
    """«Казахстан» / «скорее всего Казахстан» и строка признаков - для отчётов. HTML."""
    if not c or not c.get("code"):
        return "", ""
    head = (flag_svg(c["code"]) + " " if flag else "") + ("" if c.get("sure") else "скорее всего ") + esc(c["name"])
    bits = list(c.get("why") or [])
    if c.get("others"):
        bits.append("есть признаки и других стран: " + ", ".join(o["name"] for o in c["others"]))
    return head, ", ".join(bits)


def server_text(s):
    if not s:
        return ""
    if s.get("shield"):
        return f"сервер скрыт за {s['shield']} (видна страна сервиса: {s['name']})"
    return f"сервер стоит: {s['name']}" + (f" ({s['holder']})" if s.get("holder") else "")


# ---------- флаги: упрощённые картинки SVG 30×20
def _stripes(colors, vertical=False, weights=None):
    weights = weights or [1] * len(colors)
    total, pos, out = sum(weights), 0.0, []
    for c, w in zip(colors, weights):
        size = (30 if vertical else 20) * w / total
        out.append(f'<rect x="{pos:.2f}" y="0" width="{size + 0.05:.2f}" height="20" fill="{c}"/>' if vertical else
                   f'<rect x="0" y="{pos:.2f}" width="30" height="{size + 0.05:.2f}" fill="{c}"/>')
        pos += size
    return "".join(out)


def _star(cx, cy, r, fill, n=5):
    pts = []
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * 0.4
        a = math.pi * i / n - math.pi / 2
        pts.append(f"{cx + rr * math.cos(a):.2f},{cy + rr * math.sin(a):.2f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'


def _crescent(cx, cy, r, fill, bg, shift=0.3):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/><circle cx="{cx + r * shift}" cy="{cy}" r="{r * 0.82}" fill="{bg}"/>'


def _nordic(bg, cross, inner=None):
    s = f'<rect width="30" height="20" fill="{bg}"/><rect x="8" width="5" height="20" fill="{cross}"/><rect y="7.5" width="30" height="5" fill="{cross}"/>'
    if inner:
        s += f'<rect x="9.5" width="2" height="20" fill="{inner}"/><rect y="9" width="30" height="2" fill="{inner}"/>'
    return s


def _union(x=0, y=0, w=30, h=20):
    return (f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 60 30" preserveAspectRatio="none">'
            '<rect width="60" height="30" fill="#012169"/><path d="M0,0 60,30M60,0 0,30" stroke="#fff" stroke-width="6"/>'
            '<path d="M0,0 60,30M60,0 0,30" stroke="#C8102E" stroke-width="2"/>'
            '<path d="M30,0v30M0,15h60" stroke="#fff" stroke-width="10"/><path d="M30,0v30M0,15h60" stroke="#C8102E" stroke-width="6"/></svg>')


def _sun(cx, cy, r, fill, rays=True):
    s = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'
    if rays:
        s += (f'<circle cx="{cx}" cy="{cy}" r="{r * 1.45:.2f}" fill="none" stroke="{fill}" stroke-width="{r * 0.45:.2f}" '
              f'stroke-dasharray="{r * 0.35:.2f} {r * 0.35:.2f}"/>')
    return s


FLAGS = {
    "RU": lambda: _stripes(["#fff", "#0039A6", "#D52B1E"]),
    "KZ": lambda: '<rect width="30" height="20" fill="#00AFCA"/>' + _sun(15.5, 8.5, 3, "#FEC50C")
                  + '<path d="M11.5,13.2q4,2.2 8,0" stroke="#FEC50C" stroke-width="1" fill="none"/>'
                  + '<rect x="1.6" y="1" width="1.5" height="18" fill="#FEC50C" opacity=".85"/>',
    "BY": lambda: _stripes(["#C8313E", "#4AA657"], weights=[2, 1]) + '<rect width="4.5" height="20" fill="#fff"/>'
                  + '<path d="M2.25,0v20" stroke="#C8313E" stroke-width="2.2" stroke-dasharray="2 1.4"/>',
    "UA": lambda: _stripes(["#0057B7", "#FFD700"]),
    "UZ": lambda: _stripes(["#0099B5", "#CE1126", "#fff", "#CE1126", "#1EB53A"], weights=[6.3, .4, 6, .4, 6.3])
                  + _crescent(4.5, 3.2, 2.1, "#fff", "#0099B5", .35)
                  + "".join(f'<circle cx="{8 + i * 1.6}" cy="{2 + j * 1.6}" r=".45" fill="#fff"/>' for i in range(3) for j in range(2)),
    "KG": lambda: '<rect width="30" height="20" fill="#E8112D"/>' + _sun(15, 10, 3.6, "#FFEF00")
                  + '<circle cx="15" cy="10" r="2.2" fill="#E8112D"/><circle cx="15" cy="10" r="1.6" fill="#FFEF00"/>',
    "TJ": lambda: _stripes(["#CC0000", "#fff", "#006600"], weights=[2, 3, 2])
                  + '<path d="M13,11h4l-.6-2-1.4,1-1.4-1z" fill="#F8C300"/>',
    "TM": lambda: '<rect width="30" height="20" fill="#00843D"/><rect x="3.5" width="5" height="20" fill="#D22630"/>'
                  + _crescent(13, 5, 2.2, "#fff", "#00843D", .4),
    "AM": lambda: _stripes(["#D90012", "#0033A0", "#F2A800"]),
    "GE": lambda: '<rect width="30" height="20" fill="#fff"/><rect x="13" width="4" height="20" fill="#FF0000"/>'
                  '<rect y="8" width="30" height="4" fill="#FF0000"/>'
                  + "".join(f'<rect x="{x - 1}" y="{y - 1}" width="2" height="2" fill="#FF0000"/>' for x in (6.5, 23.5) for y in (4, 16)),
    "AZ": lambda: _stripes(["#00B5E2", "#EF3340", "#509E2F"]) + _crescent(14.3, 10, 2.4, "#fff", "#EF3340", .3)
                  + _star(17.3, 10, 1.2, "#fff", 8),
    "MD": lambda: _stripes(["#0046AE", "#FFD200", "#CC092F"], vertical=True) + '<rect x="13.6" y="7" width="2.8" height="6" rx="1" fill="#8B5A2B"/>',
    "MN": lambda: _stripes(["#C4272F", "#015197", "#C4272F"], vertical=True) + _star(5, 6, 1.5, "#F9CF02", 5)
                  + '<rect x="4.2" y="8.5" width="1.6" height="7" fill="#F9CF02"/>',
    "LT": lambda: _stripes(["#FDB913", "#006A44", "#C1272D"]),
    "LV": lambda: _stripes(["#9E3039", "#fff", "#9E3039"], weights=[2, 1, 2]),
    "EE": lambda: _stripes(["#0072CE", "#000", "#fff"]),
    "PL": lambda: _stripes(["#fff", "#DC143C"]),
    "DE": lambda: _stripes(["#000", "#DD0000", "#FFCE00"]),
    "FR": lambda: _stripes(["#0055A4", "#fff", "#EF4135"], vertical=True),
    "IT": lambda: _stripes(["#009246", "#fff", "#CE2B37"], vertical=True),
    "ES": lambda: _stripes(["#AA151B", "#F1BF00", "#AA151B"], weights=[1, 2, 1]),
    "PT": lambda: _stripes(["#006600", "#FF0000"], vertical=True, weights=[2, 3]) + '<circle cx="12" cy="10" r="3.2" fill="#FFE900"/>',
    "GB": lambda: _union(),
    "IE": lambda: _stripes(["#169B62", "#fff", "#FF883E"], vertical=True),
    "NL": lambda: _stripes(["#AE1C28", "#fff", "#21468B"]),
    "BE": lambda: _stripes(["#000", "#FDDA24", "#EF3340"], vertical=True),
    "LU": lambda: _stripes(["#ED2939", "#fff", "#00A1DE"]),
    "AT": lambda: _stripes(["#ED2939", "#fff", "#ED2939"]),
    "CH": lambda: '<rect width="30" height="20" fill="#DA291C"/><rect x="13.5" y="4" width="3" height="12" fill="#fff"/>'
                  '<rect x="9" y="8.5" width="12" height="3" fill="#fff"/>',
    "CZ": lambda: _stripes(["#fff", "#D7141A"]) + '<polygon points="0,0 15,10 0,20" fill="#11457E"/>',
    "SK": lambda: _stripes(["#fff", "#0B4EA2", "#EE1C25"]) + '<rect x="7" y="5" width="6" height="9" rx="2" fill="#EE1C25" stroke="#fff" stroke-width=".6"/>',
    "HU": lambda: _stripes(["#CE2939", "#fff", "#477050"]),
    "RO": lambda: _stripes(["#002B7F", "#FCD116", "#CE1126"], vertical=True),
    "BG": lambda: _stripes(["#fff", "#00966E", "#D62612"]),
    "RS": lambda: _stripes(["#C6363C", "#0C4076", "#fff"]) + '<rect x="7" y="5" width="5" height="9" rx="1.5" fill="#C6363C" stroke="#fff" stroke-width=".5"/>',
    "ME": lambda: '<rect width="30" height="20" fill="#D4AF37"/><rect x="1" y="1" width="28" height="18" fill="#C40308"/>'
                  '<circle cx="15" cy="10" r="3" fill="#D4AF37"/>',
    "HR": lambda: _stripes(["#FF0000", "#fff", "#171796"]) + '<rect x="12.5" y="5" width="5" height="7" fill="#FF0000" stroke="#fff" stroke-width=".6"/>',
    "SI": lambda: _stripes(["#fff", "#005CE5", "#ED1C24"]) + '<path d="M6,3h5v5q-2.5,3-5,0z" fill="#005CE5" stroke="#ED1C24" stroke-width=".4"/>',
    "GR": lambda: _stripes(["#0D5EAF", "#fff"] * 4 + ["#0D5EAF"]) + '<rect width="11.1" height="11.1" fill="#0D5EAF"/>'
                  '<rect x="4.45" width="2.2" height="11.1" fill="#fff"/><rect y="4.45" width="11.1" height="2.2" fill="#fff"/>',
    "CY": lambda: '<rect width="30" height="20" fill="#fff"/><ellipse cx="15" cy="9" rx="7" ry="3" fill="#D57800"/>'
                  '<path d="M11,14q4,2 8,0" stroke="#4E5B31" stroke-width="1" fill="none"/>',
    "FI": lambda: _nordic("#fff", "#002F6C"),
    "SE": lambda: _nordic("#006AA7", "#FECC00"),
    "NO": lambda: _nordic("#BA0C2F", "#fff", "#00205B"),
    "DK": lambda: _nordic("#C8102E", "#fff"),
    "TR": lambda: '<rect width="30" height="20" fill="#E30A17"/>' + _crescent(11, 10, 5, "#fff", "#E30A17", .25)
                  + _star(17, 10, 2.4, "#fff"),
    "IL": lambda: '<rect width="30" height="20" fill="#fff"/><rect y="2" width="30" height="3" fill="#0038B8"/>'
                  '<rect y="15" width="30" height="3" fill="#0038B8"/>'
                  '<path d="M15,6.5 18,11.7 12,11.7zM15,13.5 12,8.3 18,8.3z" fill="none" stroke="#0038B8" stroke-width=".8"/>',
    "AE": lambda: _stripes(["#00732F", "#fff", "#000"]) + '<rect width="7.5" height="20" fill="#FF0000"/>',
    "SA": lambda: '<rect width="30" height="20" fill="#006C35"/><rect x="8" y="12.5" width="14" height="1.2" fill="#fff"/>'
                  '<rect x="9" y="6" width="12" height="4" rx="1" fill="#fff" opacity=".85"/>',
    "QA": lambda: '<rect width="30" height="20" fill="#8A1538"/><polygon points="0,0 9,0 11,1.1 9,2.2 11,3.3 9,4.4 11,5.5 9,6.6 '
                  '11,7.7 9,8.8 11,10 9,11.1 11,12.2 9,13.3 11,14.4 9,15.5 11,16.6 9,17.7 11,18.8 9,20 0,20" fill="#fff"/>',
    "EG": lambda: _stripes(["#CE1126", "#fff", "#000"]) + '<rect x="14" y="8" width="2" height="4" fill="#C09300"/>',
    "IN": lambda: _stripes(["#FF9933", "#fff", "#138808"]) + '<circle cx="15" cy="10" r="2.6" fill="none" stroke="#000080" stroke-width=".7"/>',
    "CN": lambda: '<rect width="30" height="20" fill="#EE1C25"/>' + _star(5, 5, 3, "#FFFF00")
                  + "".join(_star(x, y, 1, "#FFFF00") for x, y in ((10, 2), (12, 4), (12, 7), (10, 9))),
    "JP": lambda: '<rect width="30" height="20" fill="#fff"/><circle cx="15" cy="10" r="6" fill="#BC002D"/>',
    "KR": lambda: '<rect width="30" height="20" fill="#fff"/><path d="M10,10a5,5 0 0 1 10,0z" fill="#CD2E3A"/>'
                  '<path d="M10,10a5,5 0 0 0 10,0z" fill="#0047A0"/>'
                  + "".join(f'<rect x="{x}" y="{y}" width="3.5" height="2.4" fill="#000" transform="rotate({a} {x + 1.75} {y + 1.2})"/>'
                            for x, y, a in ((3, 3, -33), (23.5, 3, 33), (3, 14.6, 33), (23.5, 14.6, -33))),
    "TH": lambda: _stripes(["#A51931", "#F4F5F8", "#2D2A4A", "#F4F5F8", "#A51931"], weights=[1, 1, 2, 1, 1]),
    "VN": lambda: '<rect width="30" height="20" fill="#DA251D"/>' + _star(15, 10.5, 5, "#FFFF00"),
    "ID": lambda: _stripes(["#FF0000", "#fff"]),
    "MY": lambda: _stripes(["#CC0001", "#fff"] * 7) + '<rect width="15" height="11.4" fill="#010066"/>'
                  + _crescent(5.5, 5.7, 3.5, "#FC0", "#010066", .3) + _star(10.5, 5.7, 2.4, "#FC0", 14),
    "SG": lambda: _stripes(["#EF3340", "#fff"]) + _crescent(5, 5, 3, "#fff", "#EF3340", .3)
                  + "".join(_star(x, y, .8, "#fff") for x, y in ((8.5, 3), (10, 4.5), (9.5, 6.5), (7.5, 6.5), (7, 4.5))),
    "US": lambda: _stripes(["#B22234", "#fff"] * 6 + ["#B22234"]) + '<rect width="12" height="10.8" fill="#3C3B6E"/>'
                  + "".join(f'<circle cx="{1.2 + i * 2.4}" cy="{1.2 + j * 2.1}" r=".45" fill="#fff"/>' for i in range(5) for j in range(5)),
    "CA": lambda: _stripes(["#D80621", "#fff", "#D80621"], vertical=True, weights=[1, 2, 1])
                  + '<polygon points="15,4 16.2,7 18.5,6.2 17.6,9.4 19.6,9.6 16,12.6 16.3,15 15,14.4 13.7,15 14,12.6 10.4,9.6 '
                    '12.4,9.4 11.5,6.2 13.8,7" fill="#D80621"/>',
    "MX": lambda: _stripes(["#006847", "#fff", "#CE1126"], vertical=True) + '<circle cx="15" cy="10" r="2.4" fill="#8C5A2B"/>',
    "BR": lambda: '<rect width="30" height="20" fill="#009C3B"/><polygon points="15,2 28,10 15,18 2,10" fill="#FFDF00"/>'
                  '<circle cx="15" cy="10" r="4.6" fill="#002776"/>',
    "AR": lambda: _stripes(["#74ACDF", "#fff", "#74ACDF"]) + _sun(15, 10, 1.8, "#F6B40E"),
    "AU": lambda: '<rect width="30" height="20" fill="#012169"/>' + _union(0, 0, 15, 10) + _star(7.5, 15, 2.2, "#fff", 7)
                  + "".join(_star(x, y, 1, "#fff", 7) for x, y in ((22.5, 4), (19, 9), (26, 8), (22.5, 17))),
    "NZ": lambda: '<rect width="30" height="20" fill="#012169"/>' + _union(0, 0, 15, 10)
                  + "".join(_star(x, y, 1.2, "#CC142B") for x, y in ((22.5, 4), (19.5, 9), (25.5, 8), (22.5, 16))),
    "ZA": lambda: '<rect width="30" height="10" fill="#E03C31"/><rect y="10" width="30" height="10" fill="#001489"/>'
                  '<path d="M0,0 13,10 0,20M13,10H30" stroke="#fff" stroke-width="6.5" fill="none"/>'
                  '<path d="M0,0 13,10 0,20M13,10H30" stroke="#007749" stroke-width="4" fill="none"/>'
                  '<polygon points="0,3 9,10 0,17" fill="#FFB81C"/><polygon points="0,4.5 7,10 0,15.5" fill="#000"/>',
}


def flag_svg(code, h=14):
    """Флаг страны картинкой SVG (высота h px). Страна вне справочника - серая плашка с кодом."""
    code = (code or "").upper()
    w = round(h * 1.5)
    title = esc(name(code)) if code else "страна не определена"
    draw = FLAGS.get(code)
    inner = draw() if draw else (f'<rect width="30" height="20" rx="2" fill="#d9dce1"/><text x="15" y="14" font-size="10" '
                                 f'text-anchor="middle" font-family="Arial,sans-serif" font-weight="bold" fill="#444">{esc(code[:3])}</text>')
    return (f'<svg class="flag" viewBox="0 0 30 20" width="{w}" height="{h}" role="img" aria-label="Флаг: {title}" '
            f'style="vertical-align:-2px;border-radius:2px;flex:none"><title>{title}</title>{inner}'
            f'<rect x=".25" y=".25" width="29.5" height="19.5" rx="1.5" fill="none" stroke="rgba(0,0,0,.25)" stroke-width=".5"/></svg>')
