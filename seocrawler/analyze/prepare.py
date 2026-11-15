"""Общие данные для всех проверок: страницы, ссылки, редиректы. Считается один раз, дальше каждая проверка берёт отсюда что ей нужно."""
from .common import Issue, _q, defaultdict, link_rows
from .. import memory
from ..fetcher import HTML_TYPES


def run(ctx):
    store = ctx.store
    db = store.db
    issues = []

    def add(key, sev, cat, title, why, fix, columns, rows, page_col=0, show_col=None):
        if rows:
            issues.append(Issue(key, sev, cat, title, why, fix, columns, rows, page_col, show_col=show_col))

    # Все внутренние HTML-страницы, найденные по ссылкам
    pages = _q(db, """SELECT p.*, u.depth FROM pages p JOIN urls u ON u.url=p.url
                      WHERE u.internal=1 AND u.kind='page'""")
    # с ошибкой загрузки («дольше 30 с - прервана», «не распаковался») страница пришла обрывком: её разбор не
    # годится для проверок, она уже в списке «не ответили» (codes.py) - ложных находок по обрывку не делаем
    def good_html(rows):
        return [p for p in rows if p["status"] == 200 and p["content_type"] in HTML_TYPES and not p["error"]]
    html_ok = good_html(pages)
    indexable = [p for p in html_ok if p["indexable"] == 1]
    # Страницы, известные только из sitemap: ссылок на них нет, поэтому в общие pages не входят (там клики от главной,
    # входящие ссылки и шаблон сайта). Но title, H1 и «страница не найдена» у них настоящие, и смотреть их надо
    # (thehome.ru 06.11.2026: 5 425 пустых страниц из 7 873 считались рабочими «сиротами»).
    # Нужны только колонки заголовков и текста: на большом сайте таких страниц десятки тысяч, а p.* - 65 колонок
    sitemap_html = good_html(_q(db, """SELECT p.url, p.status, p.error, p.content_type, p.indexable, p.title, p.h1,
                                              p.h1_count, p.description, p.word_count, p.text_sample, p.blocks, u.depth
                                       FROM pages p JOIN urls u ON u.url=p.url
                                       WHERE u.internal=1 AND u.kind='sitemap'"""))
    all_checked = _q(db, """SELECT p.url, p.status, p.error, p.location, p.content_type, p.size, p.elapsed, p.ssl_note,
                            p.indexable, p.indexability, u.internal, u.kind FROM pages p JOIN urls u ON u.url=p.url""")
    status = {r["url"]: (r["status"], r["error"]) for r in all_checked}
    # куда ведут редиректы: адреса, закрытые в robots.txt, обход не открывал - их код дочитан при сборке (reread)
    for url, end in ((store.get_meta("redirect_ends", None) or {}).get("ends") or {}).items():
        status.setdefault(url, (end, ""))
    left = db.execute("SELECT COUNT(*) FROM urls WHERE state IN ('queued', 'fetching') AND internal=1 AND kind='page'").fetchone()[0]

    # Входящие ссылки
    inl = defaultdict(set)
    # самый большой шаг подготовки (thehome.ru - 28 млн ссылок, ~2 ГБ): память смотрим и посреди него, раз в 65 536
    # ссылок (memory.guard - только при сборке отчёта; ревью кода 05.11.2026)
    for k, r in enumerate(link_rows(db, ("src", "dst"), "kind='a' AND internal=1")):
        if not k & 0xFFFF:
            memory.guard()
        if r[0] != r[1]:
            inl[r[1]].add(r[0])

    def src_of(url, limit=3):
        s = sorted(inl.get(url, ()))
        if not s:
            f = db.execute("SELECT src FROM links WHERE dst=? LIMIT 1", (url,)).fetchone()
            s = [f[0]] if f else []
        return "\n".join(s[:limit]) + (f"\n…и ещё {len(s) - limit}" if len(s) > limit else "")

    # Редиректы: откуда куда
    redir = {r["url"]: r["location"] for r in _q(db, "SELECT url, location FROM pages WHERE location IS NOT NULL AND location<>''")}
    rtype = {r["url"]: r["redirect_type"] for r in _q(db, "SELECT url, redirect_type FROM pages WHERE redirect_type IS NOT NULL")}

    def follow(u):
        chain, seen = [u], {u}
        while chain[-1] in redir:
            nxt = redir[chain[-1]]
            if nxt in seen:
                return chain + [nxt], True
            chain.append(nxt)
            seen.add(nxt)
            if len(chain) > 20:
                break
        return chain, False

    def code(u):
        st = status.get(u)
        if not st:
            return "не проверялся"
        return st[0] or st[1]

    ctx.add, ctx.all_checked, ctx.code, ctx.db, ctx.follow = add, all_checked, code, db, follow
    ctx.html_ok, ctx.indexable, ctx.inl, ctx.issues, ctx.left = html_ok, indexable, inl, issues, left
    ctx.pages, ctx.redir, ctx.rtype, ctx.src_of, ctx.status = pages, redir, rtype, src_of, status
    ctx.sitemap_html = sitemap_html
    ctx.home = min(html_ok, key=lambda p: p.get("depth") or 0) if html_ok else {}
    ctx.home_copies = _home_copies(store, html_ok, ctx.home)


def _home_copies(store, html_ok, home):
    """Адреса с содержимым главной, если сайт на любой адрес отдаёт главную (nabiullin.com 06.11.2026): заведомо
    несуществующий адрес ответил 200 с её title и H1, и есть другие адреса с точно таким же текстом. Сайт, у которого
    просто нет своей страницы ошибки, сюда не попадает: у него нет таких копий; страницы с разным текстом - тоже."""
    f404 = store.get_meta("fake404", None) or {}
    chain = f404.get("chain") or []
    if not html_ok or len(chain) != 1 or chain[0][1] != 200:
        return set()
    same = (f404.get("title") or "").strip() == (home.get("title") or "").strip() \
        and (f404.get("h1") or "").strip() == (home.get("h1") or "").strip()
    if not same or not home.get("content_hash"):
        return set()
    return {p["url"] for p in html_ok if p["content_hash"] == home["content_hash"] and p["url"] != home["url"]}
