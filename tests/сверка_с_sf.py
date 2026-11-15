"""Сверка обхода программы с выгрузкой Screaming Frog, страница за страницей. Не автотест, инструмент.
Берёт из папки выгрузок SF то, что там есть: internal_all.csv или отдельные response_codes_all, page_titles_all,
meta_description_all, h1_all, canonicals_all, links_all (глубина), content_all (слова).
(sitemaps_all у SF - не список из sitemap, а все адреса с пометкой, поэтому не сравнивается.)
Сравнивает: охват (какие страницы нашёл только SF, какие только мы - с разбивкой по разделам и параметрам),
код ответа, редирект, Title, Description, H1, canonical, meta robots, индексируемость, глубину, число слов
(SF по умолчанию не считает слова в <nav> и <footer>, поэтому сравнение с нашим content_words).
Адреса сравниваются без учёта порядка параметров и кодирования.
Запуск: py -3 tests/сверка_с_sf.py <папка выгрузок SF> <reports/<сайт>_<дата>/crawl.db> [--все]
(--все - печатать все расхождения, а не по 12 примеров)."""
import collections
import csv
import os
import re
import sqlite3
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

csv.field_size_limit(10 ** 9)
args = [a for a in sys.argv[1:] if not a.startswith("--")]
SHOW = 10 ** 9 if "--все" in sys.argv else 12
sfdir, db = args[0], args[1]
c = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row


def key(u):
    p = urlsplit(u)
    q = sorted((unquote(a), unquote(b)) for a, b in parse_qsl(p.query, keep_blank_values=True))
    return (p.scheme, p.netloc.lower(), unquote(p.path), tuple(q))


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def load(name):
    p = os.path.join(sfdir, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# одна запись на адрес SF из всех найденных файлов
sf = collections.OrderedDict()
FIELDS = {
    "internal_all.csv": {"Content Type": "ct", "Status Code": "code", "Status": "status", "Indexability": "idx",
                         "Indexability Status": "idx_why", "Redirect URL": "redirect", "Title 1": "title",
                         "Meta Description 1": "desc", "H1-1": "h1", "Canonical Link Element 1": "canonical",
                         "Meta Robots 1": "robots", "Crawl Depth": "depth", "Word Count": "words"},
    "response_codes_all.csv": {"Content Type": "ct", "Status Code": "code", "Status": "status", "Indexability": "idx",
                               "Indexability Status": "idx_why", "Redirect URL": "redirect"},
    "page_titles_all.csv": {"Title 1": "title"},
    "meta_description_all.csv": {"Meta Description 1": "desc"},
    "h1_all.csv": {"H1-1": "h1", "Occurrences": "h1_n"},
    "canonicals_all.csv": {"Canonical Link Element 1": "canonical", "Meta Robots 1": "robots"},
    "links_all.csv": {"Crawl Depth": "depth"},
    "content_all.csv": {"Word Count": "words"},
}
used = []
for fname, cols in FIELDS.items():
    rows = load(fname)
    if rows is None:
        continue
    used.append(f"{fname} ({len(rows)})")
    for r in rows:
        d = sf.setdefault(r["Address"], {})
        for col, f in cols.items():
            if col in r and f not in d:
                d[f] = r[col]
print("файлы SF:", ", ".join(used))

pages = {key(r["url"]): r for r in c.execute("SELECT * FROM pages")}
urls = {key(r["url"]): r for r in c.execute("SELECT url, kind, state, skip_reason, depth FROM urls")}

out = collections.defaultdict(list)


def section(u):
    p = urlsplit(u)
    seg = [s for s in p.path.split("/") if s]
    head = "/" + "/".join(seg[:2]) + "/" if seg else "/"
    params = ",".join(sorted({k for k, _ in parse_qsl(p.query, keep_blank_values=True)}))
    return f"{p.netloc} {head}" + (f" ?{params}" if params else "")


def is_html(d):
    return "html" in (d.get("ct") or "")


sf_html_ok = set()
cmp_n = 0
for u, d in sf.items():
    k = key(u)
    code = int(d.get("code") or 0)
    pg, uu = pages.get(k), urls.get(k)
    if code == 200 and is_html(d):
        sf_html_ok.add(k)
    if pg is None:
        if d.get("status") == "Blocked by robots.txt" and uu and "robots.txt" in (uu["skip_reason"] or ""):
            continue  # закрыт в robots.txt у обоих
        if not is_html(d) and code != 0 and not (300 <= code < 400):
            why = "ресурс (картинка, скрипт)"
        else:
            why = "html/редирект"
        out[f"есть у SF, у нас нет страницы - {why}: SF {d.get('status') or code} / у нас "
            + (f"{uu['state']} {uu['skip_reason'] or ''}".strip() if uu else "адреса нет")].append(u)
        continue
    if (pg["status"] or 0) != code:
        out["код"].append(f"{u} SF={code} {d.get('status')} мы={pg['status']} {pg['error'] or ''}")
    if d.get("redirect") and key(d["redirect"]) != key(pg["location"] or ""):
        out["редирект"].append(f"{u} SF={d['redirect']} мы={pg['location']}")
    if not (code == 200 and is_html(d)):
        continue
    cmp_n += 1
    for name, f, b in (("title", "title", pg["title"]), ("description", "desc", pg["description"]),
                       ("h1", "h1", (pg["h1"] or "").split(" | ")[0]), ("canonical", "canonical", pg["canonical"]),
                       ("meta robots", "robots", re.sub(r"\b(robots|googlebot|yandex): ", "", pg["meta_robots"] or ""))):
        if f not in d:
            continue
        a, b = ws(d[f]), ws(b)
        same = ((key(a) if a else None) == (key(b) if b else None)) if f == "canonical" else a.lower() == b.lower()
        if not same:
            out[name].append(f"{u}\n      SF={a!r}\n      мы={b!r}")
    if d.get("h1_n") and pg["h1_count"] is not None and int(d["h1_n"]) != pg["h1_count"]:
        out["число H1"].append(f"{u} SF={d['h1_n']} мы={pg['h1_count']}")
    if "idx" in d and bool(pg["indexable"]) != (d["idx"] == "Indexable"):
        out["индексируемость"].append(f"{u} SF={d['idx']}/{d.get('idx_why')} мы={pg['indexable']}/{pg['indexability']}")
    if d.get("depth") and uu and uu["depth"] is not None and uu["depth"] != int(d["depth"]):
        out["глубина"].append(f"{u} SF={d['depth']} мы={uu['depth']}")
    if d.get("words"):
        sw, ow = int(d["words"]), int(pg["content_words"] or 0)
        if sw and abs(sw - ow) / sw > 0.3:
            out["слов без меню и подвала (>30%)"].append(f"{u} SF={sw} мы={ow}")

# охват с нашей стороны: html 200 у нас, которых нет у SF
ours_only = [r["url"] for r in pages.values() if r["status"] == 200 and "html" in (r["content_type"] or "")]
sf_keys = {key(u) for u in sf}
ours_only = [u for u in ours_only if key(u) not in sf_keys]
our_html_ok = sum(1 for r in pages.values() if r["status"] == 200 and "html" in (r["content_type"] or ""))

print(f"адресов SF: {len(sf)}, html 200 у SF: {len(sf_html_ok)}, у нас: {our_html_ok}, сравнено: {cmp_n}")
for k, v in sorted(out.items(), key=lambda x: -len(x[1])):
    print(f"\n### {k}: {len(v)}")
    if k.startswith("есть у SF") and len(v) > SHOW:
        for s, n in collections.Counter(section(u) for u in v).most_common(10):
            print(f"   [{n}] {s}")
    for x in v[:SHOW]:
        print("  ", x)
print(f"\n### html 200 только у нас (у SF адреса нет): {len(ours_only)}")
for s, n in collections.Counter(section(u) for u in ours_only).most_common(15):
    print(f"   [{n}] {s}")
for x in ours_only[:SHOW]:
    print("  ", x)
