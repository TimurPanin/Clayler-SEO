"""Проверка списка адресов (как режим List у Screaming Frog) и проверка переезда сайта.

Список: каждый адрес открывается, редиректы проходятся до конца; для каждого — куда ведёт, код, title, H1,
canonical, открыт ли для поиска. Переезд: адреса берутся из прошлой проверки сайта (до переезда или нового дизайна)
и сравниваются с тем, что по ним отдаётся сейчас: страница на месте, переехала по 301, пропала, ушла на главную,
поменялся title или H1, пропал текст. Можно указать новый домен — тогда старые адреса проверяются на нём."""
import csv
import html
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit, urlunsplit

from .fetcher import Fetcher, UA_PRESETS
from .parser import parse_html
from . import urls as U

MAX_URLS = 50_000
MAX_HOPS = 10

VERDICTS = [  # ключ, подпись, важность (для цвета и порядка)
    ("gone", "Пропала: ошибка или нет ответа", "crit"),
    ("home", "Редирект на главную вместо своей страницы", "crit"),
    ("loop", "Редиректы по кругу", "crit"),
    ("closed", "Закрыта от поиска (noindex или canonical на другую)", "warn"),
    ("temp", "Временный редирект (302/307) вместо 301", "warn"),
    ("chain", "Цепочка редиректов (больше одного шага)", "warn"),
    ("changed", "На месте, но поменялся title, H1 или пропал текст", "warn"),
    ("moved", "Переехала: один 301 на рабочую страницу", "ok"),
    ("ok", "На месте, всё в порядке", "ok"),
]
LABEL = {k: t for k, t, _ in VERDICTS}
LEVEL = {k: lv for k, _, lv in VERDICTS}


def read_list(text):
    """Адреса из вставленного текста или файла: по одному в строке, можно с мусором вокруг (из Excel, CSV)."""
    out, seen = [], set()
    for line in (text or "").splitlines():
        for part in line.replace(";", " ").replace(",", " ").replace("\t", " ").split():
            part = part.strip().strip('"').strip("'")
            if not part.lower().startswith(("http://", "https://")):
                continue
            u = U.normalize(part) or part
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out[:MAX_URLS]


def from_check(folder):
    """Адреса из прошлой проверки: рабочие страницы сайта и всё из sitemap, с их title, H1 и числом слов."""
    db = sqlite3.connect(f"file:{os.path.join(folder, 'crawl.db')}?mode=ro", uri=True)
    try:
        old = {}
        for url, title, h1, words, idx in db.execute(
                "SELECT p.url, p.title, p.h1, p.word_count, p.indexable FROM pages p JOIN urls u ON u.url=p.url "
                "WHERE u.internal=1 AND u.kind='page' AND p.status=200 "
                "AND p.content_type IN ('text/html','application/xhtml+xml') ORDER BY u.depth, p.url"):
            old[url] = {"title": title or "", "h1": h1 or "", "words": words or 0, "indexable": idx}
        try:
            for (url,) in db.execute("SELECT url FROM sitemap"):
                old.setdefault(url, {})
        except sqlite3.Error:
            pass
        start = json.loads((db.execute("SELECT value FROM meta WHERE key='start'").fetchone() or ['""'])[0])
    finally:
        db.close()
    return start, old


def _swap_host(url, new_host):
    """https://old.ru/a/ → https://new.ru/a/ (схема — как у нового адреса, если он с ней указан)."""
    if not new_host:
        return url
    nh = new_host if "://" in new_host else "https://" + new_host
    n = urlsplit(nh)
    s = urlsplit(url)
    return urlunsplit((n.scheme, n.netloc, s.path, s.query, ""))


class _Pace:
    """Не чаще одного запроса в delay секунд на весь список (бережно к серверу)."""
    def __init__(self, delay):
        self.delay, self.next, self.lock = delay, 0.0, threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            t = max(now, self.next)
            self.next = t + self.delay
        if t > now:
            time.sleep(t - now)


def check_one(fetcher, pace, url):
    chain, u, seen = [], url, set()
    r = None
    for _ in range(MAX_HOPS):
        pace.wait()
        r = fetcher.fetch(u, read_body=True)
        chain.append((u, r.status or r.error))
        if r.status and 300 <= r.status < 400 and r.location:
            nxt = U.normalize(urljoin(u, r.location)) or urljoin(u, r.location)
            if nxt in seen or nxt == u:
                chain.append((nxt, "цикл"))
                return {"url": url, "chain": chain, "final": nxt, "status": "цикл", "loop": True}
            seen.add(u)
            u = nxt
            continue
        break
    row = {"url": url, "chain": chain, "final": u, "status": r.status or r.error, "loop": False,
           "title": "", "h1": "", "canonical": "", "robots": "", "words": 0, "time": round(r.ttfb or 0, 2)}
    if r.status == 200 and r.is_html and r.body:
        p = parse_html(r.body, r.headers.get("content-type", ""))
        row.update(title=(p["titles"] or [""])[0], h1=" | ".join(p["h1"]), words=p["word_count"],
                   canonical=U.normalize(p["canonicals"][0], u) if p["canonicals"] else "",
                   robots="; ".join(c for n, c in p["robots"] if n in ("robots", "yandex", "googlebot")))
    xr = r.headers.get("x-robots-tag", "") if r else ""
    if xr:
        row["robots"] = (row["robots"] + "; " + xr).strip("; ")
    return row


def verdict(row, old=None, home=""):
    st, chain = row["status"], row["chain"]
    hops = len(chain) - 1
    if row.get("loop"):
        return "loop"
    if st != 200:
        return "gone"
    codes = [c for _, c in chain[:-1]]
    if hops and home and row["final"].rstrip("/") == home.rstrip("/") and row["url"].rstrip("/") != home.rstrip("/"):
        return "home"
    if "noindex" in (row.get("robots") or "").lower() or (row.get("canonical") and row["canonical"] != row["final"]):
        return "closed"
    if any(c in (302, 303, 307) for c in codes):
        return "temp"
    if hops > 1:
        return "chain"
    if old:
        if (old.get("title") and old["title"] != row.get("title")) or (old.get("h1") and old["h1"] != row.get("h1")) \
                or (old.get("words", 0) >= 150 and row.get("words", 0) < 0.5 * old["words"]):
            return "changed"
    return "moved" if hops else "ok"


def run(urls, out_base, old=None, new_host="", ua="crawler", threads=4, delay=0.2, stop_file="", log=print,
        title="Проверка списка адресов", auth=None):
    """urls — что проверять; old — {старый адрес: что было} для переезда. Пишет out_base + .html/.csv/.json."""
    fetcher = Fetcher(UA_PRESETS.get(ua, ua), timeout=15, total_timeout=30)
    if auth:
        fetcher.host_headers.update(auth)  # {хост: заголовки} — логин и пароль только своему сайту
    pace = _Pace(delay)
    targets = [(u, _swap_host(u, new_host)) for u in urls]
    home = ""
    if targets:
        s = urlsplit(targets[0][1])
        home = f"{s.scheme}://{s.netloc}/"
    rows, done, t0 = [None] * len(targets), [0], time.time()
    lock = threading.Lock()

    def work(i):
        if stop_file and os.path.exists(stop_file):
            return
        src, dst = targets[i]
        try:
            r = check_one(fetcher, pace, dst)
        except Exception as e:  # сбой на одном адресе не должен ронять весь список
            r = {"url": dst, "chain": [(dst, str(e)[:80])], "final": dst, "status": str(e)[:80], "loop": False}
        r["src"] = src
        r["verdict"] = verdict(r, (old or {}).get(src), home)
        rows[i] = r
        with lock:
            done[0] += 1
            if done[0] % 25 == 0 or done[0] == len(targets):
                log(f"Проверено адресов: {done[0]} из {len(targets)}")
    with ThreadPoolExecutor(max(1, threads)) as ex:
        list(ex.map(work, range(len(targets))))
    rows = [r for r in rows if r]
    stopped = len(rows) < len(targets)
    _write(out_base, rows, old is not None, new_host, title, time.time() - t0, stopped, len(targets))
    return rows


def _write(base, rows, migration, new_host, title, took, stopped, total):
    os.makedirs(os.path.dirname(base), exist_ok=True)
    counts = {k: 0 for k, _, _ in VERDICTS}
    for r in rows:
        counts[r["verdict"]] += 1
    order = {k: i for i, (k, _, _) in enumerate(VERDICTS)}
    rows.sort(key=lambda r: (order[r["verdict"]], r["src"]))

    def chain_text(r):
        return " → ".join(str(c) for _, c in r["chain"])
    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Итог", "Адрес" + (" (старый)" if migration else ""), "Проверялся адрес", "Коды по пути", "Куда привёл",
                    "Код", "Title", "H1", "Canonical", "Meta robots", "Слов", "Ответ сервера, с"])
        for r in rows:
            w.writerow([LABEL[r["verdict"]], r["src"], r["url"] if r["url"] != r["src"] else "", chain_text(r), r["final"],
                        r["status"], r.get("title", ""), r.get("h1", ""), r.get("canonical", ""), r.get("robots", ""),
                        r.get("words", ""), r.get("time", "")])
    e = html.escape
    tiles = "".join(f'<a class="tile {LEVEL[k]}" href="#v-{k}"><b>{counts[k]}</b>{e(t)}</a>'
                    for k, t, _ in VERDICTS if counts[k])
    parts = []
    for k, t, lv in VERDICTS:
        rs = [r for r in rows if r["verdict"] == k]
        if not rs:
            continue
        body = "".join(
            f'<tr><td><a href="{e(r["src"])}" target="_blank">{e(r["src"])}</a>'
            + (f'<div class="mut">проверен {e(r["url"])}</div>' if r["url"] != r["src"] else "")
            + f'</td><td class="nowrap">{e(chain_text(r))}</td><td>'
            + (f'<a href="{e(r["final"])}" target="_blank">{e(r["final"])}</a>' if r["final"] != r["url"] else "")
            + f'</td><td>{e(r.get("title", ""))}<div class="mut">{e(r.get("h1", ""))}</div></td></tr>' for r in rs[:3000])
        more = f'<p class="mut">Показаны первые 3 000 из {len(rs)} - все в файле CSV.</p>' if len(rs) > 3000 else ""
        parts.append(f'<details id="v-{k}" class="grp {lv}"{" open" if lv != "ok" else ""}><summary><span class="dot"></span>'
                     f'{e(t)} <b>{len(rs)}</b></summary><div class="tw"><table><thead><tr><th>Адрес</th><th>Коды по пути</th>'
                     f'<th>Куда привёл</th><th>Title / H1</th></tr></thead><tbody>{body}</tbody></table></div>{more}</details>')
    bad = counts["gone"] + counts["home"] + counts["loop"]
    if migration:
        lead = (f"Проверено {len(rows)} адресов из прошлой проверки сайта" + (f" на новом адресе {e(new_host)}" if new_host else "")
                + f". Потеряно страниц: <b>{bad}</b> (пропали или ведут на главную) - их позиции в поиске уйдут, если не "
                f"поставить 301 на новые адреса.")
        advice = ("<p><b>Что сделать.</b> «Пропала» и «на главную» - поставить 301 со старого адреса на новую страницу с тем же "
                  "содержанием (не на главную). «Временный редирект» - заменить на 301. «Цепочка» - вести сразу на конечный адрес. "
                  "«Поменялся title или H1» - проверить, что на новой странице остались слова, по которым её находили.</p>")
    else:
        lead = f"Проверено адресов: {len(rows)}. С ошибкой или без своей страницы: <b>{bad}</b>."
        advice = ""
    if stopped:
        lead += f" Проверка остановлена: проверено {len(rows)} из {total}."
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
:root{{--bg:#f7f6f3;--card:#fff;--tx:#1f1e1c;--mut:#6b6a66;--bd:#e4e2dc;--crit:#c0392b;--warn:#b7791f;--ok:#2f855a;--acc:#3b5bdb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#181817;--card:#222220;--tx:#ecebe7;--mut:#a3a19b;--bd:#3a3936;--crit:#ef6f5e;--warn:#e0a84a;--ok:#58c08a;--acc:#8ea6ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}}
main{{max-width:1150px;margin:0 auto;padding:24px 16px 60px}}h1{{font-size:24px;margin:0 0 6px}}.mut{{color:var(--mut)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:16px 0}}
.tile{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;color:var(--tx);text-decoration:none;font-size:13px}}
.tile b{{display:block;font-size:24px}}.tile.crit b{{color:var(--crit)}}.tile.warn b{{color:var(--warn)}}.tile.ok b{{color:var(--ok)}}
.grp{{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin:8px 0}}.grp summary{{cursor:pointer;padding:12px 14px;list-style:none}}
.grp summary b{{margin-left:6px}}.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}}
.crit .dot{{background:var(--crit)}}.warn .dot{{background:var(--warn)}}.ok .dot{{background:var(--ok)}}
.tw{{overflow-x:auto;padding:0 14px 12px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);vertical-align:top;overflow-wrap:anywhere}}th{{color:var(--mut);font-weight:500}}
.nowrap{{white-space:nowrap}}a{{color:var(--acc);text-decoration:none}}.card{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:2px 14px}}
</style></head><body><main><h1>{e(title)}</h1>
<p class="mut">{time.strftime("%Y-%m-%d %H:%M")} · заняло {int(took // 60)} мин {int(took % 60)} с · все строки - в файле
<a href="{e(os.path.basename(base))}.csv">{e(os.path.basename(base))}.csv</a> (открывается в Excel)</p>
<p>{lead}</p>{f'<div class="card">{advice}</div>' if advice else ""}
<div class="tiles">{tiles}</div>{"".join(parts)}</main></body></html>"""
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(doc)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "total": len(rows), "migration": migration}, f, ensure_ascii=False)
