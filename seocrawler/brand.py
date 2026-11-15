"""Ваши данные в аудите для клиента: имя или компания, телефон, почта, сайт, Telegram и логотип.
Хранятся в «бренд.json» и «логотип.*» в папке «данные» (не в git). Попадают в аудит (HTML, PDF, Word)
при сборке отчёта — у готовых проверок: «Ещё → Обновить отчёт»."""
import base64
import html
import json
import os

from . import jsonfile, paths

DIR = os.path.dirname(paths.data("бренд.json"))   # «данные» (до переноса - корень)
FILE = os.path.join(DIR, "бренд.json")
FIELDS = [("name", "Имя или компания"), ("phone", "Телефон"), ("email", "Почта"), ("site", "Сайт"), ("telegram", "Telegram")]
LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg", "image/webp": ".webp"}
MAX_LOGO = 600_000


def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
        return {k: str(d.get(k) or "").strip() for k, _ in FIELDS} | {"logo": d.get("logo") or ""}
    except (OSError, ValueError):
        return {k: "" for k, _ in FIELDS} | {"logo": ""}


def _logo_path(d=None):
    name = (d or load()).get("logo")
    p = os.path.join(DIR, os.path.basename(name)) if name else ""
    return p if p and os.path.exists(p) else ""


def save(data):
    """data: поля FIELDS; logo — data:URI новой картинки, "" — оставить как есть, "-" — убрать. Возвращает ошибку или ""."""
    cur = load()
    out = {k: str(data.get(k) or "").strip()[:200] for k, _ in FIELDS}
    out["logo"] = cur.get("logo") or ""
    logo = data.get("logo") or ""
    if logo == "-":
        old = _logo_path(cur)
        if old:
            os.remove(old)
        out["logo"] = ""
    elif logo.startswith("data:"):
        head, _, b64 = logo.partition(",")
        ctype = head[5:].split(";")[0]
        if ctype not in LOGO_TYPES:
            return "Логотип - картинка PNG, JPG, SVG или WebP."
        raw = base64.b64decode(b64 or "", validate=False)
        if len(raw) > MAX_LOGO:
            return "Логотип слишком большой (больше 600 КБ). Уменьшите картинку."
        old = _logo_path(cur)
        if old:
            os.remove(old)
        name = "логотип" + LOGO_TYPES[ctype]
        with open(os.path.join(DIR, name), "wb") as f:
            f.write(raw)
        out["logo"] = name
    jsonfile.save(FILE, out, indent=1)
    return ""


def logo_uri(d=None):
    p = _logo_path(d)
    if not p:
        return ""
    ext = os.path.splitext(p)[1].lower()
    ctype = {v: k for k, v in LOGO_TYPES.items()}.get(ext, "image/png")
    with open(p, "rb") as f:
        return f"data:{ctype};base64," + base64.b64encode(f.read()).decode()


def status():
    d = load()
    return d | {"logo_uri": logo_uri(d)}


def contacts_line(d=None):
    """«Тимур Панин · +7 900 000-00-00 · mail@… · site.ru» — для подписи; пусто, если ничего не заполнено."""
    if os.environ.get("CLAYLER_NO_USER_SETTINGS") == "1":  # автотесты: аудит без личных данных
        return ""
    d = d or load()
    return " · ".join(d[k] for k, _ in FIELDS if d.get(k))


def header_html(d=None, contacts=True):
    """Шапка аудита: логотип и «Подготовил: …». Пусто, если данных нет.
    contacts=False — только имя и логотип, без телефона, почты, сайта и Telegram (демо-PDF для витрины вроде Kwork)."""
    if os.environ.get("CLAYLER_NO_USER_SETTINGS") == "1":
        return ""
    d = d or load()
    if not contacts:
        d = {k: (v if k in ("name", "logo") else "") for k, v in d.items()}
    line, logo = contacts_line(d), logo_uri(d)
    if not line and not logo:
        return ""
    e = html.escape
    parts = []
    for k, _ in FIELDS[1:]:
        v = d.get(k)
        if not v:
            continue
        if k == "email":
            parts.append(f'<a href="mailto:{e(v)}">{e(v)}</a>')
        elif k == "site":
            parts.append(f'<a href="{e(v if "://" in v else "https://" + v)}">{e(v)}</a>')
        elif k == "telegram":
            t = v.lstrip("@").split("/")[-1]
            parts.append(f'<a href="https://t.me/{e(t)}">Telegram: @{e(t)}</a>')
        else:
            parts.append(e(v))
    img = f'<img src="{logo}" alt="{e(d.get("name") or "Логотип")}">' if logo else ""
    who = f'<b>{e(d["name"])}</b>' if d.get("name") else ""
    return (f'<div class="brand">{img}<div><span class="mut">Подготовил</span> {who}'
            + (f'<div class="mut">{" · ".join(parts)}</div>' if parts else "") + '</div></div>')


BRAND_CSS = (".brand{display:flex;gap:14px;align-items:center;padding:0 0 14px;margin:0 0 16px;border-bottom:1px solid var(--bd)}"
             ".brand img{max-height:52px;max-width:180px;object-fit:contain}.brand b{font-size:16px}.brand a{color:inherit}")
