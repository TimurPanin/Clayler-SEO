"""«Страница глазами поисковика»: исходный HTML страницы без выполнения JavaScript и без стилей.

Так страницу видит робот, который не запускает скрипты (Яндекс чаще всего, Google — до рендеринга):
текст, заголовки, ссылки, картинки (подписью alt), скрытые блоки. Скрипты и стили вырезаются,
теги и атрибуты оформления убираются, остаётся только структура."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ..fetcher import Fetcher, UA_PRESETS
from ..parser import parse_html, detect_encoding
from ..analyze.checks.mixed_letters import mixed_words, mark

DROP = {"script", "style", "template", "head", "title"}           # вырезаются вместе с содержимым
STUB = {"svg": "картинка SVG", "canvas": "canvas", "video": "видео", "audio": "аудио",
        "object": "object", "embed": "embed", "iframe": "фрейм"}  # вместо содержимого — пометка
VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "area", "col", "base", "param", "track"}
KEEP_ATTRS = {"href", "colspan", "rowspan", "type", "value", "placeholder", "name"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"link", "meta", "base", "source", "track", "param", "noscript"}  # сам тег не показываем


def _hidden(attrs):
    st = (attrs.get("style") or "").replace(" ", "").lower()
    return "hidden" in attrs or "display:none" in st or "visibility:hidden" in st or attrs.get("aria-hidden") == "true"


class Cleaner(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.out = []
        self.drop = 0          # внутри script/style/svg — ничего не выводим
        self.stack = []        # открытые теги, которые мы вывели (чтобы закрыть корректно)
        self.mixed = 0

    def handle_starttag(self, tag, attrs_list):
        attrs = {k: (v or "") for k, v in attrs_list}
        if self.drop:
            if tag in DROP or tag in STUB:
                self.drop += 1
            return
        if tag in DROP:
            self.drop = 1
            return
        if tag in STUB:
            src = attrs.get("src") or attrs.get("data") or ""
            self.out.append(f'<span class="stub">[{STUB[tag]}{": " + html.escape(src[:120]) if src else ""}]</span>')
            if tag not in VOID:
                self.drop = 1
            return
        if tag == "noscript":
            self.out.append('<span class="tagmark">noscript</span>')
            return
        if tag in SKIP_TAGS or tag in ("html", "body"):
            return
        if tag == "img":
            alt = attrs.get("alt")
            src = attrs.get("src") or attrs.get("data-src") or ""
            if alt is None and "alt" not in attrs:
                self.out.append(f'<span class="img noalt" title="{html.escape(src)}">[картинка без alt]</span>')
            elif not alt.strip():
                self.out.append(f'<span class="img" title="{html.escape(src)}">[картинка, alt пустой]</span>')
            else:
                self.out.append(f'<span class="img" title="{html.escape(src)}">[картинка: {html.escape(alt)}]</span>')
            return
        keep = []
        for k, v in attrs.items():
            if k in KEEP_ATTRS:
                if k == "href":
                    v = urljoin(self.base, v)
                    keep.append(f'href="{html.escape(v)}" target="_blank" rel="noopener"')
                    if "nofollow" in (attrs.get("rel") or "").lower():
                        keep.append('class="nofollow" title="nofollow"')
                else:
                    keep.append(f'{k}="{html.escape(v)}"')
        cls = []
        if _hidden(attrs):
            cls.append("hid")
        a = (" " + " ".join(keep)) if keep else ""
        if cls:
            a += f' data-hidden="1"'
        if tag in HEADINGS:
            self.out.append(f'<{tag}{a}><span class="tagmark">{tag.upper()}</span>')
        elif tag in ("form", "button", "input", "select", "textarea"):
            self.out.append(f'<{tag}{a} disabled>' if tag != "form" else f'<{tag}{a}>')
        else:
            self.out.append(f"<{tag}{a}>")
        if cls:
            self.out.append('<span class="tagmark hidmark" title="Блок скрыт (hidden или display:none): '
                            'посетитель его не видит, а робот читает">скрыто</span>')
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.drop:
            if tag in DROP or tag in STUB:
                self.drop -= 1
            return
        if tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if self.drop or not data:
            return
        text = html.escape(data)
        words = set(mixed_words(data))
        for w in words:  # подменённые буквы (латинская C вместо русской С и т. п.) — подсвечиваем
            self.mixed += 1
            text = re.sub(r"(?<![^\W\d_])" + re.escape(html.escape(w)) + r"(?![^\W\d_])",
                          f'<mark class="mix" title="{html.escape(mark(w))}">{html.escape(w)}</mark>', text)
        self.out.append(text)

    def result(self):
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


PAGE_CSS = """body{font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:16px;color:#1f1e1c;background:#fff}
a{color:#2f4bc0}a.nofollow{color:#9a6b00}
.tagmark{display:inline-block;font:11px/1.4 ui-monospace,Consolas,monospace;background:#3b5bdb;color:#fff;border-radius:4px;
padding:0 5px;margin-right:6px;vertical-align:2px}
.hidmark{background:#b7791f}[data-hidden]{outline:1px dashed #b7791f;display:block}
.img{display:inline-block;font-size:12px;border:1px solid #c9d3f5;background:#f1f4ff;border-radius:4px;padding:0 5px;margin:1px}
.img.noalt{border-color:#c0392b;background:#fdecea;color:#c0392b}
.stub{font-size:12px;color:#6b6a66}
mark.mix{background:#fdecea;color:#c0392b;border-bottom:2px solid #c0392b}
table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:2px 6px}"""


def view(url, ua="crawler"):
    """Загружает страницу (редиректы проходит сам, до 5) и возвращает сводку и очищенный HTML."""
    if "://" not in url:
        url = "https://" + url
    f = Fetcher(UA_PRESETS.get(ua, UA_PRESETS["crawler"]))
    chain = []
    r = None
    for _ in range(6):
        r = f.fetch(url)
        chain.append({"url": url, "status": r.status or r.error})
        if r.error or not (300 <= r.status < 400) or not r.location:
            break
        url = urljoin(url, r.location)
    f.close()
    out = {"url": url, "chain": chain, "status": r.status, "error": r.error, "content_type": r.content_type,
           "elapsed": round(r.elapsed, 2), "size": r.size}
    if r.error or not r.body:
        return out
    if not r.is_html:
        out["error"] = f"Это не HTML-страница ({r.content_type or 'тип не указан'})"
        return out
    ct = r.headers.get("content-type", "")
    p = parse_html(r.body, ct)
    enc = detect_encoding(r.body, ct)[0]
    raw = r.body.decode(enc, "replace")
    base = urljoin(url, p.get("base") or "") if p.get("base") else url
    host = urlsplit(url).hostname
    links = [x for x in p["links"] if x.get("kind") == "a"]
    internal = sum(1 for x in links if urlsplit(urljoin(base, x["href"])).hostname == host)
    c = Cleaner(base)
    try:
        c.feed(raw)
        c.close()
    except Exception:
        pass
    body = c.result()
    headings = re.findall(r"<(h[1-6])[^>]*>(.*?)</\1>", body, re.S)
    out.update({
        "title": p["titles"], "description": p["descriptions"], "h1": p["h1"], "robots": p["robots"],
        "canonical": p["canonicals"], "x_robots": r.headers.get("x-robots-tag", ""),
        "lang": p.get("lang") or "", "words": p["word_count"], "links": len(links), "links_internal": internal,
        "images": len(p["images"]), "images_no_alt": sum(1 for i in p["images"] if i.get("alt") is None),
        "headings": [[t.upper(), re.sub(r"<[^>]+>", "", re.sub(r'<span class="tagmark">.*?</span>', "", s)).strip()[:150]]
                     for t, s in headings[:200]],
        "mixed": c.mixed, "encoding": enc,
        "html": ('<!doctype html><html><head><meta charset="utf-8"><style>' + PAGE_CSS + "</style></head><body>"
                 + body + "</body></html>"),
        "source": raw[:3_000_000],
    })
    return out
