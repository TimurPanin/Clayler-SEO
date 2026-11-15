"""GEO — готовность сайта к ответам нейросетей (Нейро в Яндексе, Алиса, ChatGPT, Perplexity, обзоры ИИ в Google)
и вопросы для блоков «вопрос — ответ» по страницам из семантики. Всё по данным проверки, без платных сервисов."""
import json
import os
import re
import sqlite3
import urllib.request
import zlib
from urllib.parse import urlsplit

from .. import sysproxy
from ..robots import Robots

# ИИ-роботы: имя в robots.txt → чей
AI_BOTS = [("GPTBot", "ChatGPT (обучение)"), ("OAI-SearchBot", "поиск ChatGPT"), ("ChatGPT-User", "ChatGPT по просьбе"),
           ("ClaudeBot", "Claude"), ("Claude-SearchBot", "поиск Claude"), ("PerplexityBot", "Perplexity"),
           ("Google-Extended", "Gemini и ИИ Google"), ("Applebot-Extended", "ИИ Apple"),
           ("Yandex", "Яндекс (Нейро берёт ответы из поиска)"), ("Googlebot", "Google (обзоры ИИ из поиска)")]
PHONE_RX = re.compile(r"(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
ADDR_RX = re.compile(r"\b(ул\.|улица|пр-т|проспект|пер\.|шоссе|д\.\s*\d)", re.I)
QUESTION_RX = re.compile(r"^(как|какой|какая|какие|каким|почему|зачем|сколько|что|чем|можно ли|нужен ли|нужна ли|"
                         r"нужно ли|где|когда|для чего|отличие|отличается|в чем|какую)\b|\b(или|лучше|разница|"
                         r"плюсы и минусы|своими|не работает|не греет|гаснет|ошибка|как выбрать|выбрать)\b")
FAQ_MAX = 8


def _llms_txt(site):
    try:
        req = urllib.request.Request(site.rstrip("/") + "/llms.txt", headers={"User-Agent": "Mozilla/5.0"})
        with sysproxy.urlopen(req, timeout=10) as r:
            body = r.read(2000).decode("utf-8", "replace")
            return r.status == 200 and "<html" not in body.lower()
    except Exception:
        return False


def check(folder, sections):
    """Пункты GEO-проверки: [{name, ok (True/False/None — не узнать), text, fix}]."""
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    meta = {k: v for k, v in db.execute("SELECT key, value FROM meta")}
    site = json.loads(meta.get("start", '""'))
    host = urlsplit(site).netloc
    robots = json.loads(meta.get("robots", "{}"))
    rtext = next((v.get("text") or "" for k, v in robots.items() if urlsplit(k).netloc == host), "")
    out = []

    # 1. ИИ-роботы в robots.txt
    probe = [site] + [s["url"] for s in sorted(sections, key=lambda s: -s["links"])[:3]]
    closed = [f"{name} ({who})" for name, who in AI_BOTS
              if not all(Robots(rtext, name).allowed(u) for u in probe)]
    out.append({"name": "ИИ-роботы пускают на сайт", "ok": not closed,
                "text": "robots.txt никого из ИИ-роботов не закрывает" if not closed else
                "robots.txt закрывает: " + ", ".join(closed),
                "fix": "" if not closed else "Если хотите попадать в ответы этих нейросетей, уберите для них Disallow "
                "в robots.txt. Роботов Яндекса и Google закрывать нельзя: Нейро и обзоры ИИ берут ответы из поиска."})

    # 2. Разметка: товар с ценой, организация, вопросы-ответы, рейтинг, хлебные крошки
    types = {}
    for (st,) in db.execute("SELECT schema_types FROM pages WHERE status=200 AND content_type LIKE 'text/html%' "
                            "AND indexable=1"):
        for t in (st or "").split(", "):
            if t:
                types[t] = types.get(t, 0) + 1
    want = [("Product", "товар", "Product + Offer с ценой и наличием на карточках"),
            ("Offer", "цена", "Offer с ценой - нейросети любят точные цифры"),
            ("Organization", "организация", "Organization или LocalBusiness на главной и в контактах: название, адрес, телефон"),
            ("FAQPage", "вопросы и ответы", "FAQPage на страницах с блоком «вопрос - ответ»"),
            ("AggregateRating", "рейтинг и отзывы", "AggregateRating / Review на карточках, если есть отзывы"),
            ("BreadcrumbList", "хлебные крошки", "BreadcrumbList - показывает структуру сайта")]
    have = lambda t: types.get(t, 0) + (types.get("LocalBusiness", 0) if t == "Organization" else 0)  # noqa: E731
    miss = [(w, fix) for t, w, fix in want if not have(t)]
    got = [f"{w} ({have(t)} стр.)" for t, w, _ in want if have(t)]
    out.append({"name": "Разметка для нейросетей (schema.org)", "ok": not miss,
                "text": ("Есть: " + ", ".join(got) if got else "Разметки нет") +
                        ("; нет: " + ", ".join(w for w, _ in miss) if miss else ""),
                "fix": "; ".join(fix for _, fix in miss)})

    # 3. Текст виден без JavaScript (многие ИИ-роботы скрипты не выполняют)
    js = json.loads(meta.get("config", "{}")).get("render_js")
    urls = [s["url"] for s in sorted(sections, key=lambda s: -s["links"])[:20]] + [site]
    rows = [db.execute("SELECT content_words, raw_words, word_count FROM pages WHERE url=?", (u,)).fetchone()
            for u in urls]
    rows = [r for r in rows if r]
    if js:
        hidden = [u for u, r in zip(urls, rows) if r and r[1] is not None and r[2] and r[1] < 0.5 * r[2]]
        out.append({"name": "Текст виден без JavaScript", "ok": not hidden,
                    "text": "Основной текст есть в HTML" if not hidden else
                    f"На {len(hidden)} важных страницах текст появляется только после скриптов",
                    "fix": "" if not hidden else "Отдавать текст сразу в HTML (серверная отрисовка): ИИ-роботы его "
                    "иначе не увидят."})
    else:
        thin = sum(1 for r in rows if (r[0] or 0) < 50)
        out.append({"name": "Текст виден без JavaScript", "ok": thin <= len(rows) // 3,
                    "text": "Проверка шла без JavaScript - так сайт видят ИИ-роботы. " +
                    ("Текст на важных страницах есть." if thin <= len(rows) // 3 else
                     f"На {thin} из {len(rows)} важных страниц почти нет текста."),
                    "fix": "" if thin <= len(rows) // 3 else "Добавить на разделы короткий понятный текст."})

    # 4. Контакты на главной: телефон и адрес текстом (для ответов «где купить … в городе»)
    b = db.execute("SELECT blocks FROM pages WHERE url=?", (site,)).fetchone()
    text = ""
    if b and b[0]:
        try:
            text = zlib.decompress(b[0]).decode("utf-8")
        except Exception:
            pass
    phone, addr = bool(PHONE_RX.search(text)), bool(ADDR_RX.search(text))
    out.append({"name": "Адрес и телефон текстом", "ok": phone and addr if text else None,
                "text": ("Телефон " + ("есть" if phone else "не найден") + ", адрес " + ("есть" if addr else "не найден"))
                if text else "Текст главной не сохранён в проверке - не узнать",
                "fix": "" if phone and addr else "Написать адрес и телефон текстом (не картинкой) на главной и в "
                "контактах - так нейросеть ответит «где купить … в вашем городе»."})

    # 5. llms.txt — новый стандарт: краткое описание сайта для нейросетей
    has = _llms_txt(site)
    out.append({"name": "Файл llms.txt", "ok": has, "text": "Есть" if has else "Нет",
                "fix": "" if has else "Необязательно, но ничего не стоит: файл /llms.txt - кто вы, что продаёте, "
                "главные разделы со ссылками. Пока его читают не все нейросети."})
    faq_pages = {u for (u,) in db.execute("SELECT url FROM pages WHERE schema_types LIKE '%FAQPage%'")}
    db.close()
    return {"checks": out, "faq_pages": sorted(faq_pages)}


def faq(groups, Q, keys):
    """Вопросы для блока «вопрос — ответ» на странице группы: информационные запросы и запросы-вопросы,
    похожие склеены, сначала частые."""
    for g in groups:
        g["faq"] = []
        if g["prio"] not in (1, 2):
            continue
        seen, out = [], []
        for q in sorted(g["queries"], key=lambda q: -Q[q]["score"]):
            r = Q[q]
            if r["check"] or not (r["intent"] == "Информация" or QUESTION_RX.search(q)):
                continue
            ks = {min(keys(t), key=lambda x: (x.startswith("~"), len(x))) for t in q.split() if len(t) > 2}
            if any(len(ks & s) >= 0.8 * min(len(ks), len(s)) for s in seen):
                continue
            seen.append(ks)
            out.append(q[:1].upper() + q[1:] + ("?" if QUESTION_RX.match(q) and not q.endswith("?") else ""))
            if len(out) >= FAQ_MAX:
                break
        g["faq"] = out
