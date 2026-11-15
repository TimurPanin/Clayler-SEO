"""Готовые файлы-исправления для разработчика: по итогам проверки - исправленный robots.txt,
чистый sitemap.xml, правила 301-редиректов (Apache, nginx, таблица для плагинов) и новые title / description
таблицей для загрузки. Лежат в «для клиента/файлы для разработчика», рядом — «Прочитайте сначала.txt».
Ничего не придумывается: каждое изменение следует из найденной проблемы, причина подписана рядом.
Собирается при сборке отчёта (и «Обновить отчёт»); summary["fix_files"] — что получилось, для отчётов."""
import csv
import os
import re
from urllib.parse import unquote, urlsplit

from . import cms_help
from .client_folder import DIR as CLIENT_DIR
from .fmt import esc as _e, num as _n
from .robots import Robots, page_instead
from .urls import is_tracking_param

DIR = "файлы для разработчика"
README = "Прочитайте сначала.txt"
ROBOTS = "robots.txt"
SITEMAP = "sitemap.xml"
RD_APACHE = "редиректы - Apache (.htaccess).txt"
RD_NGINX = "редиректы - nginx.conf"
RD_TABLE = "редиректы - таблица.csv"
META_XLSX = "новые title и description.xlsx"
META_CSV = "новые title и description.csv"
SITEMAP_MAX = 50000  # больше адресов в одном sitemap поисковики не читают
_PAGINATION = re.compile(r"pagen|page|[?&*]p=|/p/|paged", re.I)


def folder(out_dir):
    return os.path.join(out_dir, CLIENT_DIR, DIR)


def _rows(issues, key):
    for i in issues:
        if i.key == key:
            return i.rows
    return []


def _origin(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


# ---------------------------------------------------------------- robots.txt

def _key(line):
    s = line.split("#", 1)[0].strip()
    return (s.split(":", 1)[0].strip().lower(), s.split(":", 1)[1].strip()) if ":" in s else ("", "")


def _groups(lines):
    """[(номер последней строки User-agent группы, есть ли в группе Disallow с правилом)]"""
    out, prev = [], ""
    for n, line in enumerate(lines):
        k, v = _key(line)
        if k == "user-agent":
            if prev == "user-agent":
                out[-1][0] = n
            else:
                out.append([n, False])
        elif k == "disallow" and v and out:
            out[-1][1] = True
        if k:
            prev = k
    return out


def _blocked(text, url):
    return any(not Robots(text, bot).allowed(url)[0] for bot in ("googlebot", "yandex"))


def _allow_for(text, url):
    """Правило Allow, которое открывает файл стилей или скрипта и не открывает ничего, кроме таких же файлов:
    папка + *.css. Длиннее запрета, поэтому побеждает (у Google и Яндекса выигрывает самое длинное правило)."""
    path = urlsplit(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".css", ".js"):
        return ""
    parts = path.split("/")[1:-1]
    for depth in range(1, len(parts) + 1):
        cand = "/" + "/".join(parts[:depth]) + "/*" + ext
        if not _blocked(_add_allow(text, [cand]), url):
            return cand
    return path if not _blocked(_add_allow(text, [path]), url) else ""


def _add_allow(text, pats, note="# Открыты стили и скрипты: без них поисковик видит страницу сломанной"):
    lines = text.splitlines()
    for end, has_dis in reversed(_groups(lines)):
        if has_dis:
            lines[end + 1:end + 1] = [note] + ["Allow: " + p for p in pats]
    return "\n".join(lines) + "\n"


# параметр постраничной навигации в адресе закрытой страницы: PAGEN_1 (Битрикс), page, p, paged, pg
_PAGE_PARAM = re.compile(r"^(?:pagen_\d+|page|p|paged|pg|pagenum|page_num)$", re.I)


def _bots(text):
    return tuple(Robots(text, bot) for bot in ("googlebot", "yandex"))


def _shut(bots, url):
    """Закрыт ли адрес хоть для одного робота (как _blocked, но robots.txt уже разобран)."""
    return any(not b.allowed(url)[0] for b in bots)


def _pager(u):
    """(раздел, параметр навигации), если навигация - единственный параметр адреса: /catalog/sofas/?PAGEN_1=2 →
    ("/catalog/", "PAGEN_1"); иначе None."""
    from urllib.parse import parse_qsl
    p = urlsplit(u)
    q = parse_qsl(p.query, keep_blank_values=True)
    if len(q) != 1 or not _PAGE_PARAM.match(q[0][0]):
        return None
    seg = [x for x in p.path.split("/") if x]
    return ("/" + seg[0] + "/" if len(seg) > 1 else "/"), q[0][0]


def _pagination_allows(text, closed_urls, others=()):
    """Правило закрывает не только навигацию, а все адреса с «?» (Disallow: /*? - и фильтры, и сортировки): его не
    убираем, а открываем одну навигацию узким Allow для её параметра (длиннее запрета, поэтому побеждает и у Яндекса,
    и у Google; thehome.ru). Узко - в разделе, где она нашлась: «Allow: /catalog/*?PAGEN_1=». Раньше было
    «Allow: /*?PAGEN_1=» на весь сайт - оно открывало и /search/?PAGEN_1=2, /personal/….
    others - другие закрытые адреса сайта: правило, которое откроет хоть один из них (поиск, кабинет, фильтр
    «?PAGEN_1=2&sort=…»), не берём. Возвращает ([правила Allow], {открытые адреса навигации})."""
    old = _bots(text)
    others = [o for o in others if not _pager(o) and _shut(old, o)]
    pats = []
    for u in closed_urls:
        pg = _pager(u)
        if not pg or not _shut(old, u):
            continue
        sec, param = pg
        pat = f"{sec}*?{param}=" if sec != "/" else f"/?{param}="
        if pat in pats:
            continue
        new = _bots(_add_allow(text, pats + [pat]))
        if not _shut(new, u) and not any(not _shut(new, o) for o in others):
            pats.append(pat)
    opened = set()
    if pats:
        new = _bots(_add_allow(text, pats))
        opened = {u for u in closed_urls if _shut(old, u) and not _shut(new, u)}
    return pats, opened


def robots_fix(store, issues, start, make_sitemap):
    """(новый текст robots.txt или "", [что изменено])."""
    hosts = store.get_meta("robots", {}) or {}
    org = _origin(start)
    rb = hosts.get(org) or {}
    text, status = rb.get("text") or "", rb.get("status") or 0
    changes = []
    if page_instead(rb):
        text = "User-agent: *\nDisallow:\n"
        changes.append("Вместо robots.txt сайт отдаёт обычную страницу. Сделан простой файл: обходить можно всё, "
                       "указан адрес sitemap.")
    elif not text.strip():
        if status not in (404, 410) and status != 200:
            return "", []  # robots.txt не прочитался (ошибка сервера) — не гадаем
        text = "User-agent: *\nDisallow:\n"
        changes.append("Файла robots.txt на сайте нет. Сделан простой файл: обходить можно всё, указан адрес sitemap.")
    lines = text.splitlines()
    # 1. Постраничная навигация, закрытая в robots.txt, из-за которой товары находятся только через sitemap
    # или не находятся вовсе (hidden_behind_blocked)
    beh = _rows(issues, "behind_blocked") + _rows(issues, "hidden_behind_blocked")
    rules = {}
    for r in beh:
        rule = (r[2] or "").strip()
        if rule.lower().startswith("disallow:") and _PAGINATION.search(rule.split(":", 1)[1]):
            rules[rule.split(":", 1)[1].strip()] = rules.get(rule.split(":", 1)[1].strip(), 0) + 1
    for pat, n in rules.items():
        hit = False
        for k, line in enumerate(lines):
            kk, v = _key(line)
            if kk == "disallow" and v == pat:
                lines[k] = "# " + line.strip()
                hit = True
        if hit:
            lines.insert(0, f"# Правило «Disallow: {pat}» убрано: оно закрывало постраничную навигацию, и {_n(n)} стр. "
                            "робот не находил по ссылкам (знал только из sitemap или не знал вовсе). На страницах 2, 3… списка должен стоять "
                            "noindex, follow или canonical на первую страницу.")
            changes.append(f"Открыта постраничная навигация (было «Disallow: {pat}»): по ней робот дойдёт до "
                           f"{_n(n)} стр., которые сейчас не находит по ссылкам.")
    text = "\n".join(lines) + "\n"
    # правило шире навигации (Disallow: /*? - все адреса с параметрами): узкий Allow для параметра навигации
    wide = [r for r in beh if (r[2] or "").strip().lower().startswith("disallow:")
            and not _PAGINATION.search((r[2] or "").split(":", 1)[1])]
    if wide:
        closed = list(dict.fromkeys(u.strip() for r in wide for u in (r[1] or "").split("\n") if u.strip()))
        try:   # остальные закрытые адреса сайта: правило не должно открыть ни один из них (не больше 20 000 для скорости)
            others = [u for (u,) in store.db.execute("SELECT url FROM urls WHERE state='skipped' AND internal=1 "
                                                     "AND skip_reason LIKE 'Закрыт в robots%' LIMIT 20000")]
        except Exception:
            others = []
        pats, opened = _pagination_allows(text, closed, others)
        if pats:
            # сколько страниц станет видно: только те, у которых хоть одна закрытая страница навигации откроется
            # (раньше - все страницы за широким запретом, и за фильтрами тоже)
            n = len({r[0] for r in wide if any(u.strip() in opened for u in (r[1] or "").split("\n"))})
            text = _add_allow(text, pats, "# Открыта постраничная навигация (страницы 2, 3… списка) в разделах, где "
                                          f"она нашлась: без неё робот не доходит по ссылкам до {_n(n)} стр. Остальные "
                                          "закрытые адреса (фильтры, сортировки, поиск) остаются закрытыми")
            changes.append("Открыта постраничная навигация: " + ", ".join("«Allow: " + p + "»" for p in pats)
                           + f" - только в этих разделах; общий запрет адресов с параметрами остался, и ни один другой "
                           f"закрытый адрес, найденный при проверке (фильтры, сортировки, поиск), не открылся; по "
                           f"навигации робот дойдёт до {_n(n)} стр. На страницах 2, 3… списка должен стоять noindex, "
                           "follow или canonical на первую страницу.")
    # 2. Закрытые стили и скрипты
    files = []
    for r in _rows(issues, "js_blocked"):
        for u in (r[1] or "").split("\n"):
            u = u.strip()
            if u and u not in files:
                files.append(u)
        if len(files) > 300:
            break
    pats = []
    for u in files:
        if not _blocked(_add_allow(text, pats) if pats else text, u):
            continue
        p = _allow_for(_add_allow(text, pats) if pats else text, u)
        if p and p not in pats:
            pats.append(p)
    if pats:
        text = _add_allow(text, pats)
        changes.append("Открыты стили и скрипты, без которых поисковик видит страницу сломанной: "
                       + ", ".join("«Allow: " + p + "»" for p in pats[:6]) + (" и др." if len(pats) > 6 else "") + ".")
    # 3. Метки в адресах — Clean-param для Яндекса
    seen = set()
    for (removed,) in store.db.execute("SELECT DISTINCT removed FROM param_links"):
        for name in (removed or "").split(","):
            name = name.strip()
            if name and is_tracking_param(name):
                seen.add(name)
    covered = set()
    for names, prefix in Robots(text, "yandex").clean_params:
        if not prefix or prefix == "/":
            covered |= names
    miss = sorted(seen - covered)
    if miss:
        text = text.rstrip("\n") + ("\n\n# Метки в адресах: Яндекс не будет считать адрес с ними отдельной страницей"
                                    f"\nClean-param: {'&'.join(miss)}\n")
        changes.append(f"Для Яндекса добавлен Clean-param с метками, которые встречаются в ссылках сайта "
                       f"({', '.join(miss[:8])}{' и др.' if len(miss) > 8 else ''}).")
    # 4. Адрес sitemap
    if make_sitemap and not Robots(text, "googlebot").sitemaps:
        text = text.rstrip("\n") + f"\n\nSitemap: {org}/{SITEMAP}\n"
        changes.append("Добавлен адрес карты сайта (Sitemap), его не было.")
    return (text if changes else ""), changes


# ---------------------------------------------------------------- sitemap.xml

def sitemap_urls(store, issues, start):
    org = _origin(start)
    rows = [r[0] for r in store.db.execute(
        "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' "
        "AND p.status=200 AND p.indexability='Индексируемая' ORDER BY u.depth, p.url")]
    drop = {r[0] for r in _rows(issues, "soft404")}
    for r in _rows(issues, "dup_content"):  # из одинаковых страниц — только первая
        drop |= set((r[1] or "").split("\n")[1:])
    in_sm = {r[0] for r in store.db.execute("SELECT url FROM sitemap")}
    for a, b in _rows(issues, "slash_dup"):  # /page и /page/ — один из двух: тот, что был в sitemap, иначе со слешем
        drop.add(b if (a in in_sm and b not in in_sm) else a)
    return [u for u in rows if _origin(u) == org and u not in drop]


SITEMAP_PROBLEMS = ("sitemap_errors", "sitemap_redirect", "sitemap_nonindex", "not_in_sitemap", "orphans",
                    "hidden_behind_blocked")


def own_sitemap_ok(store, issues, sm):
    """Своя карта сайта уже такая, какую мы бы сделали: те же рабочие страницы, и проверки sitemap ничего не нашли.
    Тогда свой sitemap.xml не кладём - разработчик заменил бы рабочую карту такой же (timurpanin.ru)."""
    if any(i.key in SITEMAP_PROBLEMS for i in issues):
        return False
    own = {r[0] for r in store.db.execute("SELECT url FROM sitemap")}
    return bool(own) and own == set(sm)


def _xml(u):
    return u.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def write_sitemap(dst, urls, org):
    """Один файл; больше 50 000 адресов — sitemap.xml со списком файлов sitemap1.xml, sitemap2.xml…"""
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    parts = [urls[i:i + SITEMAP_MAX] for i in range(0, len(urls), SITEMAP_MAX)] or [[]]

    def one(path, chunk):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(head + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            f.writelines(f"  <url><loc>{_xml(u)}</loc></url>\n" for u in chunk)
            f.write("</urlset>\n")
    if len(parts) == 1:
        one(os.path.join(dst, SITEMAP), parts[0])
        return [SITEMAP]
    names = []
    for k, chunk in enumerate(parts, 1):
        names.append(f"sitemap{k}.xml")
        one(os.path.join(dst, names[-1]), chunk)
    with open(os.path.join(dst, SITEMAP), "w", encoding="utf-8", newline="\n") as f:
        f.write(head + '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.writelines(f"  <sitemap><loc>{_xml(org)}/{n}</loc></sitemap>\n" for n in names)
        f.write("</sitemapindex>\n")
    return [SITEMAP] + names


# ---------------------------------------------------------------- редиректы

def _variants(path):
    """Тот же адрес с мелкой ошибкой: слеш в конце, заглавные буквы, .html, мусор в конце."""
    out = [path[:-1] if path.endswith("/") else path + "/", path.lower()]
    for tail in (".html", ".htm", ".php"):
        if path.endswith(tail):
            out += [path[:-len(tail)], path[:-len(tail)] + "/"]
    junk = path.rstrip(").,;:!'\"»")
    if junk != path:
        out += [junk, junk.rstrip("/") + "/"]
    return out


def redirects(store, issues, start):
    """[(старый адрес, новый адрес, почему)] — для 404 и цепочек редиректов внутри сайта."""
    org = _origin(start)
    ok = {r[0] for r in store.db.execute(
        "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' "
        "AND p.status=200 AND p.indexability='Индексируемая'")}
    ok = {u for u in ok if _origin(u) == org}
    home = {org + "/", org}
    by_path = {urlsplit(u).path: u for u in ok if not urlsplit(u).query}
    by_slug = {}
    for p, u in by_path.items():
        slug = p.rstrip("/").rsplit("/", 1)[-1]
        if slug:
            by_slug.setdefault(slug, []).append(u)
    out, done = [], set()
    dead = store.db.execute(
        "SELECT p.url, p.status FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' "
        "AND p.status IN (404, 410) ORDER BY u.depth, p.url").fetchall()
    for url, status in dead:
        if _origin(url) != org or url in done:
            continue
        path = urlsplit(url).path
        dst, why = "", ""
        for v in _variants(path):
            if v in by_path and by_path[v] != url:
                dst, why = by_path[v], f"{status}: тот же адрес с опечаткой (слеш, буквы, окончание)"
                break
        if not dst:
            slug = path.rstrip("/").rsplit("/", 1)[-1]
            same = by_slug.get(slug) or []
            if slug and len(same) == 1 and len(slug) >= 6:
                dst, why = same[0], f"{status}: страница с тем же адресом в другом разделе (переехала)"
        if not dst:
            segs = [s for s in path.split("/") if s]
            for k in range(len(segs) - 1, 0, -1):
                for cand in ("/" + "/".join(segs[:k]) + "/", "/" + "/".join(segs[:k])):
                    if cand in by_path and by_path[cand] not in home:
                        dst, why = by_path[cand], f"{status}: страницы больше нет - ведём в раздел выше"
                        break
                if dst:
                    break
        if dst:
            out.append((url, dst, why))
            done.add(url)
    for r in _rows(issues, "redirect_chains"):
        chain = [x.lstrip("→ ").strip() for x in (r[2] or "").split("\n")]
        src, final = chain[0], chain[-1]
        if src not in done and final in ok and _origin(src) == org:
            out.append((src, final, f"цепочка из {r[1]} редиректов - сразу на конечный адрес"))
            done.add(src)
    return out


def _tokens(path):
    """Слова адреса без расширений и мусора: «/iSpring.es» → {"ispring"}, «/000000» → {}."""
    words = re.split(r"[^a-zа-яё0-9]+", unquote(path).lower())
    return {w for w in words if len(w) >= 5 and not w.isdigit() and w not in ("index", "html", "default")}


def dead_decisions(store, rules, start):
    """Внутренние 404 без редиректа в rules: у каждой своё решение. [(адрес, кандидат или "", что сделать,
    сколько страниц ссылается)]. Кандидат - единственная рабочая страница, в последней части адреса которой есть
    слово из битого адреса («/iSpring.es» → «/cases/ispring»): ставить его без проверки нельзя."""
    org = _origin(start)
    done = {r[0] for r in rules}
    ok = [r[0] for r in store.db.execute(
        "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' "
        "AND p.status=200 AND p.indexability='Индексируемая'") if _origin(r[0]) == org and not urlsplit(r[0]).query]
    slugs = {u: _tokens(urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1]) for u in ok}
    out = []
    for url, n_in in store.db.execute(
            "SELECT p.url, (SELECT COUNT(DISTINCT l.src) FROM links l WHERE l.dst=p.url) FROM pages p "
            "JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' AND p.status IN (404, 410) "
            "ORDER BY u.depth, p.url"):
        if url in done or _origin(url) != org:
            continue
        words = _tokens(urlsplit(url).path)
        cands = [u for u in ok if words & slugs[u]] if words and not urlsplit(url).query else []
        exact = [u for u in cands if slugs[u] == words]
        cand = (exact or cands)[0] if len(exact) == 1 or (not exact and len(cands) == 1) else ""
        what = (f"возможная замена по словам адреса - откройте обе страницы и решите, ставить ли редирект; "
                f"если нет - уберите ссылки" if cand else "подходящей замены нет - уберите или исправьте ссылки")
        out.append((url, cand, what + (f" (ссылаются страниц: {n_in})" if n_in else ""), n_in or 0))
    return out


def _rx(s):
    return re.sub(r'([.^$*+?()\[\]{}|\\"])', r"\\\1", s)


def apache_text(rules, maybe=()):
    out = ["# 301-редиректы по итогам SEO-аудита. Вставьте в начало файла .htaccess в корне сайта",
           "# (если в нём уже есть «RewriteEngine On», вторую строку ниже можно не вставлять).",
           "# Нужен модуль mod_rewrite (Apache 2.4).", "", "RewriteEngine On", ""]
    for n, (src, dst, why) in enumerate(list(rules) + list(maybe)):
        p = urlsplit(src)
        dst_s = dst.replace("%", "\\%").replace("$", "\\$")
        off = "# " if n >= len(rules) else ""   # «проверьте» - выключено, включает человек
        out.append(f"# {'ПРОВЕРЬТЕ и уберите # у строк ниже: ' if off else ''}{why}")
        if p.query:
            out.append(f'{off}RewriteCond %{{QUERY_STRING}} "^{_rx(p.query)}$"')
        out.append(f'{off}RewriteRule "^{_rx(unquote(p.path).lstrip("/"))}$" "{dst_s}" [R=301,L,NE{",QSD" if p.query else ""}]')
    return "\n".join(out) + "\n"


def nginx_text(rules, maybe=()):
    """Адрес без параметров сверяется по $uri (путь без ?utm=… и расшифрованный): так редирект срабатывает и со
    ссылок с метками, а метки переносятся на новый адрес. Адрес с параметрами - по $request_uri целиком.
    maybe - [(старый, новый, почему)] «проверьте»: строками-комментариями, включает человек."""
    q = lambda s: s.replace('"', "%22")  # noqa: E731
    out = ["# 301-редиректы по итогам SEO-аудита для nginx.",
           "# 1) Блоки map вставьте в раздел http { ... } (например, в nginx.conf или отдельный файл в conf.d).",
           "# 2) Строки if вставьте в раздел server { ... } сайта, выше остальных правил location.",
           "# 3) Проверьте настройки: nginx -t, затем перезагрузите nginx.", "",
           "map $uri $seo_redirect {", '    default "";']
    # с параметрами в старом или новом адресе - точным совпадением (к новому с «?» метки не допишешь)
    with_q = [(s, d, w) for s, d, w in rules if urlsplit(s).query or "?" in d]
    exact = set(with_q)
    seen = set()   # «/a%20b» и «/a b» в $uri - один ключ, а повтор ключа map nginx не примет
    for src, dst, why in rules:
        key = unquote(urlsplit(src).path)
        if (src, dst, why) not in exact and key not in seen:
            seen.add(key)
            out.append(f'    "{q(key)}" "{q(dst)}";  # {why}')
    for src, dst, why in maybe:
        key = unquote(urlsplit(src).path)
        if not urlsplit(src).query and key not in seen:
            seen.add(key)
            out.append(f'    # "{q(key)}" "{q(dst)}";  # ПРОВЕРЬТЕ: {why}')
    out.append("}")
    if with_q:
        out += ["", "map $request_uri $seo_redirect_q {", '    default "";']
        for src, dst, why in with_q:
            p = urlsplit(src)
            out.append(f'    "{q(p.path + ("?" + p.query if p.query else ""))}" "{q(dst)}";  # {why}')
        out.append("}")
    out += ["", "# в server { ... }:"]
    if with_q:
        out.append("if ($seo_redirect_q) { return 301 $seo_redirect_q; }")
    out.append("if ($seo_redirect) { return 301 $seo_redirect$is_args$args; }")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- title и description

# «Новый …» - что загружать (неизменное - текущим текстом, см. meta_rows); как сейчас - отдельно, несколько H1 -
# по одному в колонке, без склейки через « | » (её можно по ошибке загрузить на сайт как один заголовок)
META_HEAD = ["Адрес", "Новый title", "Новый description", "Новый H1", "Что меняется", "Проверьте глазами",
             "Title сейчас", "Description сейчас", "H1 сейчас", "Второй H1 сейчас"]
ODD = re.compile(r"\*{2,}|#{2,}|\?{3,}|_{3,}|\{\{|\}\}|\[\[|\]\]|%%|\bundefined\b|\bnull\b|\bNaN\b|&[a-z]+;")


def _look(r):
    """Что проверить глазами в строке пакета: обрезки, «…», старые годы, мусор в текущих текстах, несколько H1."""
    import time
    out = list(r.get("look") or [])
    year = int(time.strftime("%Y"))
    if (r.get("desc") or "").endswith("…"):
        out.append("description: кончается на «…» - лучше законченной фразой")
    for k, name in (("title", "title"), ("desc", "description")):
        # «работаем с 2012 года», «основаны в 2010» - факт, а не устаревший план
        old = sorted({y for y in re.findall(r"(?<!\bс )(?<!\bсо )(?<!основан[аоы] в )(?<!основан в )"
                                            r"\b(20[0-3]\d)\b", r.get(k) or "", re.I) if int(y) <= year - 2})
        if old:
            out.append(f"{name}: упомянут {', '.join(old)} год - ещё актуально?")
    for k, name in (("title_now", "title"), ("h1_now", "H1"), ("desc_now", "description")):
        m = ODD.search(r.get(k) or "")
        if m:
            out.append(f"{name} сейчас: странный кусок «{m.group(0)}» - поправьте на сайте")
    h1s = _h1s(r)
    if len(h1s) > 1:
        out.append(f"на странице {len(h1s)} H1" + (" с одним текстом" if len(set(h1s)) == 1 else "")
                   + " - главный оставьте, остальные сделайте H2 или обычным текстом (сначала посмотрите, видны ли оба)")
    return "; ".join(dict.fromkeys(out))


def _h1s(r):
    """H1 страницы списком: crawler склеивает несколько H1 через « | », а в одном H1 « | » тоже бывает - сколько их
    на самом деле, говорит h1_n (число H1 при обходе; в старых сводках его нет - тогда по « | »)."""
    h = r.get("h1_now") or ""
    n = r.get("h1_n")
    return [x for x in h.split(" | ") if x] if n is None or n > 1 else ([h] if h else [])


def meta_rows(summary):
    """Новые колонки при импорте ничего не сотрут: где title или description не меняются - текущий текст.
    H1 - так же, если он один; при нескольких H1 «Новый H1» пустой, если не меняется (склейку нельзя загружать)."""
    out = []
    for r in summary.get("meta_suggest") or []:
        what = [n for n, k in (("title", "title"), ("description", "desc"), ("H1", "h1")) if r.get(k)]
        if what:
            h1s = _h1s(r)
            out.append([r["url"], r.get("title") or r.get("title_now") or "", r.get("desc") or r.get("desc_now") or "",
                        r.get("h1") or (h1s[0] if len(h1s) == 1 else ""), ", ".join(what), _look(r),
                        r.get("title_now") or "", r.get("desc_now") or "", h1s[0] if h1s else "", "\n".join(h1s[1:])])
    # дубли без готового текста и «хозяева» дублей: страница в таблице с причиной, текст на сайте не меняется
    manual = {}
    for r in summary.get("meta_manual") or []:
        m = manual.setdefault(r["url"], dict(r, look=[]))
        m["look"] = list(dict.fromkeys(m["look"] + list(r.get("look") or [])))
        m["keep"] = m.get("keep") and r.get("keep")
    done = {r[0] for r in out}
    for u, r in manual.items():
        if u in done:
            continue
        h1s = _h1s(r)
        what = r.get("what") or "ничего (оставить)" if r.get("keep") else r.get("what") or "вручную: " + ", ".join(
            n for n, k in (("title", "title"), ("description", "description"), ("H1", "h1")) if (r.get("why") or {}).get(k))
        out.append([u, r.get("title_now") or "", r.get("desc_now") or "", h1s[0] if len(h1s) == 1 else "", what,
                    _look(r), r.get("title_now") or "", r.get("desc_now") or "", h1s[0] if h1s else "",
                    "\n".join(h1s[1:])])
    return out


def write_meta_xlsx(path, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from .xlsx_report import _clean
    wb = Workbook()
    ws = wb.active
    ws.title = "Новые title и description"
    ws.append(META_HEAD)
    for r in rows:
        ws.append([_clean(c) for c in r])
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDEFGHIJ", (50, 60, 80, 45, 18, 50, 50, 60, 45, 45)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)


# ---------------------------------------------------------------- всё вместе

def _readme(site, items, skipped, cms):
    L = [f"Файлы для разработчика сайта {site}", "",
         "Здесь готовые исправления по итогам SEO-аудита. Каждое следует из найденной проблемы. "
         "Перед заменой на сайте сохраните старые файлы, чтобы можно было вернуть.", ""]
    for it in items:
        L += [f"* {it['file']}", f"  {it['what']}"] + [f"  - {c}" for c in it.get("changes", [])] + \
             [f"  Как применить: {it['how']}", ""]
    if skipped:
        L += ["Чего здесь нет и почему:"] + [f"  - {s}" for s in skipped] + [""]
    if cms:
        L += [f"Движок сайта - {cms_help.name(cms)} (определён при проверке): советы «Как применить» - для него.", ""]
    else:
        L += ["Движок сайта при проверке не определился - советы общие; уточните у разработчика, как это делается на вашем движке.", ""]
    return "\n".join(L).replace("\n", "\r\n")


def write(store, issues, summary, out_dir):
    """Пишет файлы и возвращает [{file, what, n}] для отчётов. Старые файлы прошлой сборки заменяются."""
    start = store.get_meta("start", "") or ""
    if not start:
        return []
    site = (urlsplit(start).hostname or "").removeprefix("www.")
    dst = folder(out_dir)
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(dst):  # прошлая сборка
        try:
            os.remove(os.path.join(dst, f))
        except OSError:
            pass
    items, skipped = [], []
    cms = cms_help.of_store(store)   # советы «Как применить» - под движок сайта (cms_help)
    scope = store.get_meta("scope", None)
    full = not summary.get("queue_left") and not (scope and scope.get("mode") in ("section", "list"))
    # sitemap
    sm = sitemap_urls(store, issues, start) if full else []
    notes = []   # что делать не нужно - строкой в отчёт, без файла
    if sm and own_sitemap_ok(store, issues, sm):
        note = (f"Карта сайта на самом сайте в порядке: в ней те же {_n(len(sm))} рабочих страниц, открытых для "
                "поиска, без ошибок, редиректов и закрытых страниц. Менять её не нужно.")
        skipped.append("sitemap.xml: " + note[0].lower() + note[1:])
        notes.append({"file": "", "n": 0, "key": "sitemap_ok", "what": note})
        sm = []
    if sm:
        hidden = _rows(issues, "hidden_behind_blocked")
        names = write_sitemap(dst, sm, _origin(start))
        items.append({"file": " и ".join(names) if len(names) <= 3 else f"{SITEMAP} и ещё {len(names) - 1} файла",
                      "n": len(sm), "key": "sitemap",
                      "what": f"Чистая карта сайта, рабочих страниц, открытых для поиска: {_n(len(sm))}. Без адресов "
                              "с ошибками, редиректами, noindex, закрытых в robots.txt, с canonical на другую "
                              "страницу и без дублей."
                              + (f" В неё не вошли {_n(len(hidden))} стр. из проблемы «Страницы, которые поисковик не "
                                 "находит»: программа их не открывала. Добавьте их, когда откроете навигацию и "
                                 "убедитесь, что они работают." if hidden else ""),
                      "how": cms_help.how(cms, "sitemap")})
    elif not full:
        skipped.append("sitemap.xml: сайт проверен не полностью, карта из части страниц была бы неполной.")
    # robots.txt
    text, changes = robots_fix(store, issues, start, bool(sm))
    if text:
        with open(os.path.join(dst, ROBOTS), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        items.append({"file": ROBOTS, "n": len(changes), "key": "robots", "changes": changes,
                      "what": "Исправленный robots.txt. Что поменялось (рядом с изменёнными строками - пояснение "
                              "после знака #):",
                      "how": cms_help.how(cms, "robots")})
    else:
        skipped.append("robots.txt: исправлять в нём нечего.")
    # редиректы
    rules = redirects(store, issues, start)
    dead = dead_decisions(store, rules, start)   # у каждой внутренней 404 своё решение
    maybe = [(u, c, "похоже по словам адреса") for u, c, _, _ in dead if c]
    if rules or dead:
        if rules or maybe:   # одни «уберите ссылки» - в файлы сервера вставлять нечего
            with open(os.path.join(dst, RD_APACHE), "w", encoding="utf-8", newline="\n") as f:
                f.write(apache_text(rules, maybe))
            with open(os.path.join(dst, RD_NGINX), "w", encoding="utf-8", newline="\n") as f:
                f.write(nginx_text(rules, maybe))
        with open(os.path.join(dst, RD_TABLE), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Старый адрес", "Новый адрес", "Почему", "Что сделать"])
            w.writerows([*r, "поставить редирект"] for r in rules)
            w.writerows([u, c, "404, точной замены нет", what] for u, c, what, _ in dead)
        no_cand = sum(1 for d in dead if not d[1])
        items.append({"file": f"{RD_APACHE}, {RD_NGINX}, {RD_TABLE}" if rules or maybe else RD_TABLE,
                      "n": len(rules) or len(dead), "key": "redirects",
                      "what": (f"301-редиректы: {_n(len(rules))} шт. Страницы с ошибкой 404 ведут на тот же адрес без "
                               "опечатки, на переехавшую страницу или в раздел выше; цепочки редиректов заменены одним "
                               "переходом." if rules else f"Страницы с ошибкой 404 внутри сайта: {_n(len(dead))}.")
                              + (f" Ещё для {_n(len(maybe))} стр. 404 есть возможная замена по словам адреса: в "
                                 "файлах для Apache и nginx эти строки выключены знаком #, включайте после проверки."
                                 if maybe else "")
                              + (f" Для {_n(no_cand)} стр. 404 замены нет - на них нужно убрать или исправить ссылки "
                                 "(в таблице - сколько страниц на них ссылается)." if no_cand else ""),
                      "how": cms_help.how(cms, "redirects")})
    # title и description
    mr = meta_rows(summary)
    if mr:
        with open(os.path.join(dst, META_CSV), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(META_HEAD)
            w.writerows(mr)
        names = META_CSV
        try:
            write_meta_xlsx(os.path.join(dst, META_XLSX), mr)
            names = f"{META_XLSX}, {META_CSV}"
        except Exception:
            pass
        n_new = sum(1 for r in mr if not r[4].startswith(("ничего", "вручную")))   # без «оставить» и «вручную»
        items.append({"file": names, "n": n_new, "key": "meta",
                      "what": f"Новые title, description и H1 для {_n(n_new)} стр."
                              + (f" Ещё {_n(len(mr) - n_new)} стр. - с пометкой «ничего (оставить)» или «вручную»: "
                                 "дубли и то, что программа сама не сократит." if len(mr) > n_new else "")
                              + " В колонках «Новый …» там, где менять не нужно, стоит текущий текст, поэтому при "
                              "загрузке ничего не сотрётся (кроме H1 на страницах с несколькими H1 - там ячейка пустая, если H1 не меняется). Что меняется - "
                              "в колонке «Что меняется», как сейчас - в последних колонках (несколько H1 - по одному). "
                              "В колонке «Проверьте глазами» - что прочитать перед загрузкой: "
                              f"таких строк {_n(sum(1 for r in mr if r[5]))}.",
                      "how": cms_help.how(cms, "meta")})
    if not items:
        try:
            os.rmdir(dst)
        except OSError:
            pass
        return notes
    with open(os.path.join(dst, README), "w", encoding="utf-8-sig", newline="") as f:
        f.write(_readme(site, items, skipped, cms))
    return [{"file": it["file"], "n": it["n"], "key": it["key"],
             "what": "Исправленный robots.txt. " + " ".join(it["changes"]) if it["key"] == "robots" else it["what"]}
            for it in items] + notes


def _label(names):
    """Для клиента — без имён .csv в тексте (так же, как во всех клиентских файлах): «… и таблица CSV»."""
    parts = names.split(", ")
    keep = [p for p in parts if not p.endswith(".csv")]
    return ", ".join(keep) + (" и таблица CSV" if len(keep) < len(parts) else "") if keep else "таблица CSV"


def html_block(files, client=False, h2="h2", cls="card", h2_cls="sec"):
    """Список готовых файлов для отчётов. В рабочем отчёте — ссылка на папку."""
    if not files:
        return ""
    real = [f for f in files if f["file"]]   # без файла - строка «менять не нужно» (sitemap_ok)
    li = "".join(f"<li><b>{_e(_label(f['file']) if client else f['file'])}</b> - {_e(f['what'])}</li>"
                 if f["file"] else f"<li>{_e(f['what'])}</li>" for f in files)
    where = ("" if not real else
             f"Файлы лежат в папке «{DIR}», которую мы передаём вместе с отчётом. Внутри - «{README}» "
             "с пояснениями к каждому файлу." if client else
             f'Папка: <a href="{_e(CLIENT_DIR)}/{_e(DIR)}/">{_e(CLIENT_DIR)}\\{_e(DIR)}</a> '
             f'(отдайте разработчику вместе с отчётом; внутри - «{README}» с пояснениями).')
    intro = ("Чтобы не переписывать исправления вручную, мы подготовили готовые файлы. Разработчику останется "
             "проверить их и загрузить на сайт." if real else "Готовые файлы не понадобились:")
    return (f'<{h2} class="{h2_cls}">Готовые файлы для разработчика</{h2}><div class="{cls}">'
            f'<p class="mut" style="margin:0 0 8px">{intro}</p>'
            f'<ul style="margin:0;padding-left:18px">{li}</ul>' + (f'<p class="mut">{where}</p>' if where else "")
            + '</div>')


def audit_html(summary, for_pdf=False):
    b = html_block(summary.get("fix_files"), client=for_pdf, h2="h2", cls="", h2_cls="")
    return f'<section class="pt">{b}</section>' if b else ""


def docx_paras(summary, _para, _run):
    files = summary.get("fix_files") or []
    if not files:
        return []
    body = [_para([_run("Готовые файлы для разработчика", bold=True, size=28)], 80, keep=True),
            _para([_run("Чтобы не переписывать исправления вручную, мы подготовили готовые файлы. Разработчику "
                        "останется проверить их и загрузить на сайт.", color="6B6B70", size=20)], 80)]
    for f in files:
        body.append(_para([_run(_label(f["file"]), bold=True, size=20), _run(" - " + f["what"], size=20)]
                          if f["file"] else [_run(f["what"], size=20)], 40, indent=360))
    if any(f["file"] for f in files):
        body.append(_para([_run(f"Файлы лежат в папке «{DIR}», внутри - «{README}» с пояснениями.",
                                color="6B6B70", size=20)], 160))
    return body
