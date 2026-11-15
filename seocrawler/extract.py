"""Свои данные со страниц: правила извлечения (CSS-селектор, XPath или регулярное выражение) - цена, артикул,
телефон, наличие, автор статьи, есть ли на странице нужный скрипт. Идея как у Custom Extraction и Custom Search
в Screaming Frog, код свой, только стандартная библиотека.

Правила хранятся в «правила извлечения.json» в папке «данные»: {"rules": [{"name", "type", "expr", "what", "site"}]}.
type: css / xpath / regex. what: text (текст), html (код внутри), count (сколько совпадений), attr:<имя> (атрибут).
site: пусто - для всех сайтов, иначе только для этого сайта (с www и без).
Правила применяются при обходе к коду каждой страницы своего сайта (в режиме JavaScript - к странице после скриптов),
результат - колонка pages.extract (JSON {имя: [значения]}); в отчёте - раздел «Свои данные со страниц» и файл
«свои данные.csv»."""
import json
import os
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from . import jsonfile, paths

FILE = os.environ.get("CLAYLER_EXTRACT_FILE") or paths.data("правила извлечения.json")
TYPES = {"css": "CSS-селектор", "xpath": "XPath", "regex": "Регулярное выражение"}
WHATS = {"text": "текст", "html": "код внутри", "count": "сколько найдено"}  # и attr:<имя>
MAX_RULES = 30
MAX_VALUES = 10      # значений одного правила с одной страницы
MAX_LEN = 500        # символов в одном значении
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# тег закрывает незакрытый предыдущий того же рода (<li>…<li>, <p>…<p>), как делает браузер
_AUTOCLOSE = {"li": {"li"}, "p": {"p"}, "option": {"option"}, "tr": {"tr", "td", "th"}, "td": {"td", "th"},
              "th": {"td", "th"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}}
_NO_TEXT = {"script", "style", "noscript", "template"}


# ---------- правила

def _host(u):
    h = (urlsplit(u).hostname if "://" in (u or "") else (u or "").strip().split("/")[0].split(":")[0]) or ""
    h = h.lower()
    return h[4:] if h.startswith("www.") else h


def check_rule(r):
    """Правило в порядке → (правило, ""), иначе (None, что не так)."""
    name = " ".join(str(r.get("name") or "").split())[:60]
    typ = r.get("type") if r.get("type") in TYPES else "css"
    expr = str(r.get("expr") or "").strip()
    what = str(r.get("what") or "text").strip()
    if not name:
        return None, "У правила нет названия."
    if not expr:
        return None, f"«{name}»: не написано, что искать."
    if what not in WHATS and not (what.startswith("attr:") and re.fullmatch(r"attr:[\w:\-]+", what)):
        return None, f"«{name}»: непонятно, что брать ({what})."
    try:
        if typ == "css":
            _css_parse(expr)
        elif typ == "xpath":
            _xp_parse(expr)
        else:
            re.compile(expr)
    except (ValueError, re.error) as e:
        return None, f"«{name}»: ошибка в выражении: {e}"
    return {"name": name, "type": typ, "expr": expr, "what": what, "site": _host(r.get("site") or "")}, ""


def load_all():
    data = jsonfile.load(FILE)
    out = []
    for r in ((data.get("rules") if isinstance(data, dict) else None) or [])[:MAX_RULES]:
        ok, _ = check_rule(r if isinstance(r, dict) else {})
        if ok:
            out.append(ok)
    return out


def save_all(rules):
    """Сохранить правила из окна. Возвращает (правила, ошибка)."""
    out, names = [], set()
    for r in (rules or [])[:MAX_RULES]:
        ok, err = check_rule(r if isinstance(r, dict) else {})
        if not ok:
            return None, err
        key = (ok["name"].lower(), ok["site"])
        if key in names:
            return None, f"Два правила с названием «{ok['name']}»: назовите их по-разному."
        names.add(key)
        out.append(ok)
    jsonfile.save(FILE, {"rules": out})
    return out, ""


def for_site(start_url, rules=None):
    """Правила для этого сайта: общие и записанные на него."""
    if rules is None and os.environ.get("CLAYLER_NO_USER_SETTINGS") == "1" and not os.environ.get("CLAYLER_EXTRACT_FILE"):
        return []   # автотесты: ваши правила не мешают эталонам
    h = _host(start_url)
    return [r for r in (load_all() if rules is None else rules) if not r["site"] or r["site"] == h]


# ---------- дерево страницы

class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, attrs or {}, parent
        self.children = []   # Node или строка (текст)
        self.text = None

    def elements(self):
        return [c for c in self.children if isinstance(c, Node)]

    def iter(self):   # все потомки по порядку
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def get_text(self):
        out = []

        def walk(n):
            for c in n.children:
                if isinstance(c, str):
                    out.append(c)
                elif c.tag not in _NO_TEXT:
                    walk(c)
        walk(self)
        return " ".join(" ".join(out).split())

    def inner_html(self):
        out = []

        def walk(n):
            for c in n.children:
                if isinstance(c, str):
                    out.append(c if n.tag in _NO_TEXT else escape(c, quote=False))
                else:
                    a = "".join(f' {k}="{escape(v)}"' if v is not None else f" {k}" for k, v in c.attrs.items())
                    out.append(f"<{c.tag}{a}>")
                    if c.tag not in _VOID:
                        walk(c)
                        out.append(f"</{c.tag}>")
        walk(self)
        return "".join(out).strip()


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        close = _AUTOCLOSE.get(tag)
        if close:
            for i in range(len(self.stack) - 1, 0, -1):
                t = self.stack[i].tag
                if t in close:
                    del self.stack[i:]
                    break
                if t in ("ul", "ol", "table", "tbody", "thead", "dl", "select", "div"):
                    break
        d = {}
        for k, v in attrs:
            d.setdefault(k.lower(), v)
        n = Node(tag, d, self.stack[-1])
        self.stack[-1].children.append(n)
        if tag not in _VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def tree(html_text):
    t = _Tree()
    try:
        t.feed(html_text)
        t.close()
    except Exception:
        pass
    return t.root


# ---------- CSS-селекторы: тег, *, #id, .класс, [атрибут], [a=v] [a^=v] [a$=v] [a*=v] [a~=v],
# :first-child, :last-child, :nth-child(n), :nth-of-type(n), :not(простой), сочетания « », >, +, ~ и запятая

_CSS_TOKEN = re.compile(r"""\s*(?:(?P<comb>[>+~,])|(?P<simple>(?:[\w\-]+|\*)?(?:\#[\w\-]+|\.[\w\-]+|
    \[\s*[\w\-:]+\s*(?:[~^$*|]?=\s*(?:"[^"]*"|'[^']*'|[^\]\s]+))?\s*\]|:[\w\-]+(?:\([^)]*\))?)*))\s*""", re.X)
_CSS_PART = re.compile(r"""(?P<tag>^[\w\-]+|^\*)|\#(?P<id>[\w\-]+)|\.(?P<cls>[\w\-]+)|
    \[\s*(?P<an>[\w\-:]+)\s*(?:(?P<op>[~^$*|]?=)\s*(?P<av>"[^"]*"|'[^']*'|[^\]\s]+))?\s*\]|
    :(?P<ps>[\w\-]+)(?:\((?P<pa>[^)]*)\))?""", re.X)


def _compound(s):
    """«div.price[itemprop]» → список проверок одного элемента."""
    tests, pos = [], 0
    while pos < len(s):
        m = _CSS_PART.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"не понял «{s[pos:]}»")
        if m.group("tag") and m.group("tag") != "*":
            tests.append(("tag", m.group("tag").lower()))
        elif m.group("id"):
            tests.append(("attr", "id", "=", m.group("id")))
        elif m.group("cls"):
            tests.append(("attr", "class", "~=", m.group("cls")))
        elif m.group("an"):
            v = m.group("av")
            if v and v[0] in "\"'":
                v = v[1:-1]
            tests.append(("attr", m.group("an").lower(), m.group("op"), v))
        elif m.group("ps"):
            ps, pa = m.group("ps").lower(), (m.group("pa") or "").strip()
            if ps in ("first-child", "last-child"):
                tests.append((ps,))
            elif ps in ("nth-child", "nth-of-type"):
                if not pa.isdigit():
                    raise ValueError(f":{ps}({pa}) - умею только число, например :{ps}(2)")
                tests.append((ps, int(pa)))
            elif ps == "not":
                tests.append(("not", _compound(pa)))
            else:
                raise ValueError(f"не знаю :{ps}")
        pos = m.end()
    return tests


def _css_parse(sel):
    """Строку селектора → список цепочек [(сочетание, проверки), ...] (по одной на часть через запятую)."""
    groups, chain, comb, pos = [], [], " ", 0
    sel = sel.strip()
    while pos < len(sel):
        m = _CSS_TOKEN.match(sel, pos)
        if not m or m.end() == pos:
            raise ValueError(f"не понял «{sel[pos:]}»")
        pos = m.end()
        if m.group("comb") == ",":
            if not chain:
                raise ValueError("пустая часть перед запятой")
            groups.append(chain)
            chain, comb = [], " "
        elif m.group("comb"):
            comb = m.group("comb")
        elif m.group("simple"):
            chain.append((comb if chain else " ", _compound(m.group("simple"))))
            comb = " "
        # пробел между простыми селекторами - потомок: comb уже " "
    if not chain:
        raise ValueError("пустой селектор")
    groups.append(chain)
    return groups


def _attr_ok(node, name, op, val):
    v = node.attrs.get(name)
    if v is None:
        return False
    if op is None:
        return True
    v = v or ""
    if op == "=":
        return v == val
    if op == "~=":
        return val in v.split()
    if op == "^=":
        return bool(val) and v.startswith(val)
    if op == "$=":
        return bool(val) and v.endswith(val)
    if op == "*=":
        return bool(val) and val in v
    if op == "|=":
        return v == val or v.startswith(val + "-")
    return False


def _match(node, tests):
    for t in tests:
        k = t[0]
        if k == "tag":
            if node.tag != t[1]:
                return False
        elif k == "attr":
            if not _attr_ok(node, t[1], t[2], t[3]):
                return False
        elif k in ("first-child", "last-child", "nth-child", "nth-of-type"):
            sib = node.parent.elements() if node.parent else [node]
            if k == "nth-of-type":
                sib = [s for s in sib if s.tag == node.tag]
            i = sib.index(node)
            if (k == "first-child" and i != 0) or (k == "last-child" and i != len(sib) - 1) or \
                    (k in ("nth-child", "nth-of-type") and i + 1 != t[1]):
                return False
        elif k == "not":
            if _match(node, t[1]):
                return False
    return True


def _chain_ok(node, chain):
    """Проверка справа налево: последний простой селектор - сам элемент."""
    comb, tests = chain[-1]
    if not _match(node, tests):
        return False
    if len(chain) == 1:
        return True
    rest = chain[:-1]
    if comb == ">":
        p = node.parent
        return p is not None and p.tag != "#root" and _chain_ok(p, rest)
    if comb == " ":
        p = node.parent
        while p is not None and p.tag != "#root":
            if _chain_ok(p, rest):
                return True
            p = p.parent
        return False
    sib = node.parent.elements() if node.parent else []
    before = sib[:sib.index(node)]
    if comb == "+":
        return bool(before) and _chain_ok(before[-1], rest)
    return any(_chain_ok(s, rest) for s in before)   # ~


def css_select(root, sel):
    groups = _css_parse(sel) if isinstance(sel, str) else sel
    return [n for n in root.iter() if any(_chain_ok(n, g) for g in groups)]


# ---------- XPath (частый набор): /a/b, //a, //*, [@a], [@a='v'], [contains(@a,'v')], [starts-with(@a,'v')],
# [contains(text(),'v')], [contains(.,'v')], [text()='v'], [n], [last()], and / or в условии; в конце /text() или /@атрибут

_XP_STEP = re.compile(r"(//|/)?\s*(text\(\)|[\w\-]+|\*|\.\.|\.|@[\w\-:]+)\s*((?:\[(?:[^\[\]]|\[[^\]]*\])*\])*)")
_XP_PRED = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]")
_XP_COND = re.compile(r"""^\s*(?:
    (?P<num>\d+)|(?P<last>last\(\))|
    (?P<fn>contains|starts-with)\(\s*(?P<farg>@[\w\-:]+|text\(\)|\.)\s*,\s*(?P<fv>"[^"]*"|'[^']*')\s*\)|
    (?P<lhs>@[\w\-:]+|text\(\)|\.)\s*(?:(?P<op>!?=)\s*(?P<v>"[^"]*"|'[^']*'))?
    )\s*$""", re.X)


def _xp_cond(c):
    parts = re.split(r"\s+or\s+", c.strip())
    out = []
    for part in parts:
        ands = []
        for a in re.split(r"\s+and\s+", part):
            m = _XP_COND.match(a)
            if not m:
                raise ValueError(f"не понял условие [{c}]")
            ands.append(m.groupdict())
        out.append(ands)
    return out


def _xp_parse(expr):
    expr = expr.strip()
    if not expr:
        raise ValueError("пустой XPath")
    steps, pos = [], 0
    while pos < len(expr):
        m = _XP_STEP.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError(f"не понял «{expr[pos:]}»")
        axis = m.group(1) or ("/" if pos else "")
        preds = [_xp_cond(p) for p in _XP_PRED.findall(m.group(3) or "")]
        steps.append((axis, m.group(2), preds))
        pos = m.end()
    for i, (_, name, _) in enumerate(steps[:-1]):
        if name.startswith("@") or name == "text()":
            raise ValueError(f"{name} может быть только в конце")
    return steps


def _xp_val(node, what):
    if what == "text()":
        return " ".join(" ".join(c for c in node.children if isinstance(c, str)).split())
    if what == ".":
        return node.get_text()
    return node.attrs.get(what[1:])


def _xp_test(node, cond, pos, size):
    for ands in cond:
        ok = True
        for g in ands:
            if g["num"]:
                ok = pos == int(g["num"])
            elif g["last"]:
                ok = pos == size
            elif g["fn"]:
                v, s = _xp_val(node, g["farg"]), g["fv"][1:-1]
                ok = v is not None and (s in v if g["fn"] == "contains" else v.startswith(s))
            else:
                v = _xp_val(node, g["lhs"])
                if g["op"]:
                    ok = v is not None and ((v == g["v"][1:-1]) == (g["op"] == "="))
                else:   # [@a] - атрибут есть; [text()] и [.] - есть текст
                    ok = v is not None if g["lhs"].startswith("@") else bool(v)
            if not ok:
                break
        if ok:
            return True
    return False


def xpath_select(root, expr):
    """Узлы (Node) или строки (для /text() и /@атрибут)."""
    steps = _xp_parse(expr) if isinstance(expr, str) else expr
    cur = [root]
    for i, (axis, name, preds) in enumerate(steps):
        if name.startswith("@") or name == "text()":
            out = []
            for n in cur:
                if name == "text()":
                    out += [" ".join(c.split()) for c in n.children if isinstance(c, str) and c.strip()]
                elif name[1:] in n.attrs:
                    out.append(n.attrs[name[1:]] or "")
            return out
        nxt, seen = [], set()
        for n in cur:
            if name == ".":
                cand = [n]
            elif name == "..":
                cand = [n.parent] if n.parent else []
            elif axis == "//":
                cand = [c for c in n.iter() if name == "*" or c.tag == name.lower()]
            else:
                cand = [c for c in n.elements() if name == "*" or c.tag == name.lower()]
            for cond in preds:   # [n] и last() - позиция среди отобранных у этого родителя
                if axis == "//" and any(g["num"] or g["last"] for ands in cond for g in ands):
                    by_parent = {}
                    for c in cand:
                        by_parent.setdefault(id(c.parent), []).append(c)
                    cand = [c for grp in by_parent.values() for k, c in enumerate(grp, 1) if _xp_test(c, cond, k, len(grp))]
                else:
                    cand = [c for k, c in enumerate(cand, 1) if _xp_test(c, cond, k, len(cand))]
            for c in cand:
                if id(c) not in seen:
                    seen.add(id(c))
                    nxt.append(c)
        cur = nxt
    return cur


# ---------- применить правила к странице

def _clip(v):
    v = " ".join(str(v).split()) if v is not None else ""
    return v[:MAX_LEN] + ("…" if len(v) > MAX_LEN else "")


def _node_value(n, what):
    if isinstance(n, str):
        return n
    if what == "html":
        return n.inner_html()
    if what.startswith("attr:"):
        return n.attrs.get(what[5:])
    return n.get_text()


def apply_rule(rule, html_text, root=None):
    """Значения одного правила для страницы (список строк; для «сколько найдено» - [число])."""
    what = rule["what"]
    if rule["type"] == "regex":
        rx = re.compile(rule["expr"], re.I | re.S)
        if what == "count":
            return [str(sum(1 for _ in rx.finditer(html_text)))]
        out = []
        for m in rx.finditer(html_text):
            v = _clip(m.group(1) if rx.groups else m.group(0))
            if v and v not in out:
                out.append(v)
            if len(out) >= MAX_VALUES:
                break
        return out
    if root is None:
        root = tree(html_text)
    found = css_select(root, rule["expr"]) if rule["type"] == "css" else xpath_select(root, rule["expr"])
    if what == "count":
        return [str(len(found))]
    out = []
    for n in found:
        v = _node_value(n, what)
        if v is None:
            continue
        v = _clip(v)
        if v and v not in out:   # одно и то же значение (телефон в шапке и подвале) - один раз
            out.append(v)
        if len(out) >= MAX_VALUES:
            break
    return out


def apply(rules, html_text):
    """{имя правила: [значения]} для страницы. Ошибка одного правила не мешает другим."""
    if not rules or not html_text:
        return None
    root = tree(html_text) if any(r["type"] != "regex" for r in rules) else None
    out = {}
    for r in rules:
        try:
            out[r["name"]] = apply_rule(r, html_text, root)
        except Exception:
            out[r["name"]] = []
    return out


def apply_bytes(rules, body, content_type=""):
    from .parser import detect_encoding
    enc, _ = detect_encoding(body, content_type)
    return apply(rules, body.decode(enc, errors="replace"))


def test_url(url, rules, user_agent="crawler"):
    """Проверить правила на одной странице (кнопка в окне): открыть адрес и показать, что нашлось."""
    from urllib.parse import urljoin
    from .fetcher import Fetcher, UA_PRESETS
    f = Fetcher(UA_PRESETS.get(user_agent, UA_PRESETS["crawler"]))
    for _ in range(6):   # редиректы до конца
        r = f.fetch(url, read_body=True)
        if r.error or not (300 <= r.status < 400) or not r.location:
            break
        url = urljoin(url, r.location)
    if r.error:
        raise ValueError(f"Страница не открылась: {r.error}")
    if not r.body:
        raise ValueError(f"Сайт ответил {r.status}, но страница пустая.")
    res = apply_bytes(rules, r.body, r.headers.get("content-type", "")) or {}
    return {"status": r.status, "url": url,
            "values": [{"name": x["name"], "values": res.get(x["name"], [])} for x in rules]}


# ---------- отчёт

def rules_of(meta_value):
    try:
        v = json.loads(meta_value) if isinstance(meta_value, str) else meta_value
    except ValueError:
        return []
    return [r for r in (v or []) if isinstance(r, dict) and r.get("name")]


def table(rules, pages):
    """Шапка и строки таблицы: адрес + по колонке на правило (несколько значений - через « | »)."""
    names = [r["name"] for r in rules]
    rows = []
    for p in pages:
        raw = p.get("extract")
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        rows.append([p["url"]] + [" | ".join(d.get(n) or []) for n in names])
    rows.sort(key=lambda r: r[0])
    return ["Адрес"] + names, rows


def summary(rules, pages):
    """По каждому правилу: на скольких страницах нашлось и на скольких нет."""
    head, rows = table(rules, pages)
    out = []
    for k, r in enumerate(rules, 1):
        if r["what"] == "count":
            found = sum(1 for row in rows if row[k] not in ("", "0"))
        else:
            found = sum(1 for row in rows if row[k])
        out.append({"name": r["name"], "found": found, "missing": len(rows) - found})
    return out, len(rows)


def write_csv(rules, pages, out_dir):
    from .report import write_csv as _w
    head, rows = table(rules, pages)
    if rows:
        _w(os.path.join(out_dir, "свои данные.csv"), head, rows)
    return len(rows)


def report_html(meta_value, pages, show=300):
    """Раздел отчёта (только для вас, не для клиента)."""
    rules = rules_of(meta_value)
    if not rules:
        return ""
    from .fmt import esc, num
    stats, total = summary(rules, pages)
    head, rows = table(rules, pages)
    what = {"text": "текст", "html": "код", "count": "сколько"}
    lines = "".join(
        f'<tr><td><b>{esc(s["name"])}</b> <span class="mut">{esc(TYPES.get(r["type"], ""))} <code>{esc(r["expr"])}</code>'
        f' → {esc(what.get(r["what"]) or "атрибут " + r["what"][5:])}</span></td>'
        f'<td>{num(s["found"])}</td><td>{num(s["missing"])}</td></tr>' for s, r in zip(stats, rules))
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows[:show])
    more = (f'<p class="more">Показаны первые {num(show)} из {num(len(rows))}. Все строки - в файле <code>свои данные.csv</code>.</p>'
            if len(rows) > show else '<p class="more">Эти же данные - в файле <code>свои данные.csv</code>.</p>')
    return f"""<h2 class="sec">Свои данные со страниц</h2>
<div class="card"><p class="mut" style="margin:0 0 8px">Что нашлось на {num(total)} страницах по вашим правилам
(окно программы, «Свои данные со страниц»). «Нет» - правило на странице ничего не нашло: например, у товара не указана цена.</p>
<div class="tw" style="margin:0"><table><thead><tr><th>Правило</th><th>Нашлось</th><th>Нет</th></tr></thead><tbody>{lines}</tbody></table></div></div>
<details class="issue note"><summary><span class="it">Таблица по страницам</span><span class="cnt">{num(len(rows))}</span></summary>
<div class="tw"><table><thead><tr>{"".join(f"<th>{esc(h)}</th>" for h in head)}</tr></thead><tbody>{body}</tbody></table></div>
{more}</details>"""
