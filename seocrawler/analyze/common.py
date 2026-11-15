"""Общее для всех проверок: важность проблем, класс Issue, пороги из settings.py и вспомогательные расчёты
(свой текст страницы, почти дубли, внутренний PageRank).

У каждой проблемы два текста: «что это значит» (why) и «что сделать» (fix).
page_col — в какой колонке лежит адрес страницы, у которой эта проблема
(для оценки здоровья сайта). None — проблема не про конкретную страницу."""
import ipaddress
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

CRIT, WARN, NOTE = "critical", "warning", "notice"
SEV_RU = {CRIT: "Критично", WARN: "Предупреждение", NOTE: "Замечание"}
from ..settings import (TITLE_LONG, TITLE_SHORT, DESC_LONG, DESC_SHORT, DEEP_CLICKS, THIN_OWN_WORDS, H2_NEEDED_WORDS,
                       NEAR_DUP, TEMPLATE_MIN_PAGES, TEMPLATE_SHARE, IMG_HEAVY_KB, IMG_VERY_HEAVY_KB, IMG_OLD_FORMAT_KB,
                       PAGE_HEAVY_MB, TEMPLATE_HEAVY_MB, SLOW_SECONDS, CRAWL_WASTE_WARN, CERT_WARN_DAYS,
                       CERT_CRIT_DAYS, SITEWIDE_SHARE, CACHE_MIN_DAYS, MOBILE_HEAVY_MB,
                       DOMAIN_WARN_DAYS, DOMAIN_CRIT_DAYS)
# Проверки, которые обычно зависят от одной настройки всего сайта (сервер, шаблон)
TEMPLATE_KEYS = {"no_lastmod", "no_compress", "no_lang", "canon_missing", "viewport_missing", "viewport_zoom",
                 "og_missing", "schema_none", "keywords", "desc_missing", "head_invalid", "html_multi", "dup_ids"}
ALL_PAGES_KEYS = {"viewport_missing", "viewport_zoom", "head_invalid", "html_multi", "dup_ids", "no_compress"}


@dataclass
class Issue:
    key: str
    severity: str
    category: str
    title: str
    why: str
    fix: str
    columns: list
    rows: list = field(default_factory=list)
    page_col: object = 0
    sitewide: str = ""   # «на всём сайте: 9 469 из 9 472 стр.» — одна настройка сайта, а не тысячи проблем
    gain: float = 0.0    # на сколько процентов вырастет здоровье, если исправить только эту проблему
    show_col: object = None   # колонка с примером страницы для «показать на странице» в отчёте, если page_col нет
    grouped: int = 0     # сколько ссылок шаблона собрано одной строкой «на N страницах» (битые ссылки, health.py)
    group_dsts: set = field(default_factory=set)    # эти адреса (колонка ссылки) - ссылки шаблона
    group_pages: set = field(default_factory=set)   # страницы, где они стоят: сводки видят проблему на них
    count_note: str = ""   # подпись количества вместо числа строк (дубли: «4 группы, 1 905 стр.»)

    @property
    def count(self):
        return len(self.rows)

    @property
    def count_text(self):
        # count_note - когда строка списка не одна страница: у дублей строка - группа («4 группы, 1 905 стр.»)
        return self.sitewide or getattr(self, "count_note", "") or f"{len(self.rows):,}".replace(",", " ")


def _q(db, sql, *args):
    return [dict(r) for r in db.execute(sql, args).fetchall()]


# (база, последний номер в strs, {номер: строка}) - одним кортежем: замена атомарная, поток не возьмёт словарь
# другой базы. Выбрасывается после анализа (forget_strs): на thehome.ru это сотни МБ (проверка кода 01.11.2026)
_STRS = [None]


def forget_strs():
    _STRS[0] = None
LINK_COLS = ("src", "dst", "anchor")   # колонки-строки ссылок (в link_rows - номера в strs)


def link_rows(db, cols, where):
    """Ссылки со всего сайта: кортежи cols (из src, dst, anchor, nofollow, kind, internal) по условию where на kind,
    internal, nofollow. Как SELECT cols FROM links WHERE where, но без представления links: номера из link_rows
    переводятся в строки одним словарём, загруженным один раз (01.11.2026, thehome.ru: 28 млн ссылок).
    Быстрее (без трёх поисков в strs на строку), и один адрес в памяти - один объект на все ссылки, а не копия на
    каждую: множества входящих ссылок и PageRank на большом сайте занимали гигабайты. Порядок строк тот же, что у
    представления (обе выборки идут по link_rows подряд)."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='link_rows'").fetchone() is None:
        cache = {}   # старая база (до версии 6): таблица links с текстом - одинаковые строки делаем одним объектом
        for r in db.execute(f"SELECT {', '.join(cols)} FROM links WHERE {where}"):
            yield tuple(cache.setdefault(x, x) if isinstance(x, str) else x for x in r)
        return
    top = db.execute("SELECT MAX(id) FROM strs").fetchone()[0]
    cached = _STRS[0]
    if cached is None or cached[0] is not db or cached[1] != top:   # другая база или в strs дописали
        cached = _STRS[0] = (db, top, dict(db.execute("SELECT id, s FROM strs")))
    get = cached[2].get
    sel = ", ".join(f"l.{c}" for c in ("src", "dst") + tuple(cols))
    text = [c in LINK_COLS for c in cols]
    for r in db.execute(f"SELECT {sel} FROM link_rows l WHERE ({where})"):
        # как JOIN в представлении links: ссылка без адреса откуда или куда не попадает
        if get(r[0]) is None or get(r[1]) is None:
            continue
        yield tuple(get(x) if t and x is not None else x for x, t in zip(r[2:], text))


def own_text(pages, blocks=None):
    """Свой текст страницы — без шаблона сайта (own_blocks; blocks — уже посчитанные own_blocks).
    Возвращает {url: (слов своего текста, отпечаток MinHash своего текста)}; страницы без блоков — не входят."""
    items = list((own_blocks(pages) if blocks is None else blocks).items())
    if len(items) >= PARALLEL_MIN:
        # процессам - сами списки блоков (ссылки на то, что уже в памяти), склеивает каждый процесс у себя: заранее
        # склеенные тексты всех страниц - ещё одна копия всего текста сайта (проверка кода 01.11.2026)
        res = _parallel(_own_blocks_one, [own for _u, own in items])
        if res is not None:
            return {u: r for (u, _own), r in zip(items, res)}
    return {u: _own_one(" ".join(own)) for u, own in items}


def _own_one(text):
    """(слов, отпечаток MinHash) одного текста - отдельной функцией, чтобы считать и в других процессах."""
    from ..parser import minhash, _WORD
    words = _WORD.findall(text.lower())
    return len(words), minhash(words)


def _own_blocks_one(own):
    return _own_one(" ".join(own))


# Отпечаток текста - 64 прохода по всем пятёркам слов страницы, на чистом Python ~15-20 мс на страницу товара:
# на 57 тыс. страниц thehome.ru это четверть часа на одном ядре. Большой сайт (от PARALLEL_MIN страниц) считаем на
# нескольких ядрах; результат тот же, порядок тот же (01.11.2026). Маленькие сайты и тесты - как раньше, одним ядром.
PARALLEL_MIN = int(__import__("os").environ.get("CLAYLER_PARALLEL_MIN") or 2000)


def workers_now(busy=None, free=None):
    """Сколько процессов брать прямо сейчас. Замер на базе thehome.ru (01.11.2026, 61 тыс. страниц): 1 процесс -
    270 с, 2 - 142 с, 4 - 77 с, 6 - 58 с (процессор всего компьютера 16 / 23 / 40 / 56%). Поэтому:
    - не больше настоящих ядер (половина логических, у i5-10400F - 6) и не больше 6;
    - процессор занят другими программами - оставляем им их долю: процессов не больше половины свободных логических
      ядер (компьютер занят на 20% - 12 × 0,8 / 2 = 4; на 95% - один процесс);
    - на каждый процесс - 1 ГБ свободной памяти; меньше чем на два - считаем одним процессом.
    busy, free - для автотеста (иначе замеряются)."""
    import os
    from .. import memory
    n = os.cpu_count() or 2
    best = max(1, min(6, n // 2))
    busy = memory.cpu_busy() if busy is None else busy
    if busy is not None:
        best = min(best, max(1, int(n * (100 - busy) / 100 / 2)))   # почти всё занято - одним процессом
    free = memory.free_mb() if free is None else free
    if free is not None:
        if free < 2000:
            return 1
        best = min(best, free // 1000)
    return max(1, best)


def _parallel(fn, args, workers=None):
    """[fn(a) for a in args] на нескольких ядрах. None - не получилось (тогда считаем как обычно).
    workers - сколько процессов (по умолчанию workers_now())."""
    import os
    import __main__
    workers = workers or workers_now()
    # Новый процесс в Windows заново загружает главный файл программы. crawl.py и app.py запускают работу только в
    # «if __name__ == "__main__"», а скрипт без этого выполнился бы в каждом процессе целиком (так 6 раз подряд
    # прошёл весь анализ в проверочном скрипте 01.11.2026). Поэтому - только из них или по явной просьбе (тесты).
    main = os.path.basename(getattr(__main__, "__file__", "") or "")
    if workers < 2 or (main not in ("crawl.py", "app.py") and os.environ.get("CLAYLER_PARALLEL") != "1"):
        return None
    try:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(fn, args, chunksize=max(1, len(args) // (workers * 8))))
    except Exception:
        return None


# закон сохранения для испорченных данных: {что не прочиталось: [адреса, пример адреса, ошибка]} за один анализ
FAULTS = {}


def note_fault(where: str, url: str, err: object) -> None:
    """Данные страницы испорчены или часть анализа упала: страница не должна выпадать из проверки молча.
    Попадает в служебный пункт «Данные, которые не прочитались» (checks/crashes.data_faults)."""
    row = FAULTS.setdefault(where, [set(), url or "", str(err)[:120]])
    row[0].add(url or "")   # одну страницу читают несколько проверок: считаем страницы, а не чтения


def dead_pages(ctx) -> set:
    """Страницы без своего содержимого: пустые («не найдена», ctx.soft404 из checks/content) и копии главной на чужом
    адресе. Заголовки и ссылки им не нужны, сначала они должны заработать."""
    return ctx.soft404 | ctx.home_copies


def unpack_blocks(p):
    """Блоки текста страницы (колонка blocks, сжатая zlib) списком строк; нет или не распаковались - None.
    Одна на всех: own_blocks, мягкие 404, наличие, коммерческие факторы, готовые заголовки."""
    import zlib
    b = p.get("blocks")
    if not b:
        return None
    try:
        return zlib.decompress(b).decode("utf-8").split("\n")
    except (zlib.error, UnicodeDecodeError) as e:
        note_fault("текст страницы", p.get("url"), e)
        return None


def page_json(p: dict, key: str):
    """Колонка страницы с JSON (shop, schema_info, contacts, hidden_links): разобранное значение; нет или испорчена -
    None."""
    raw = p.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        note_fault(f"данные страницы ({key})", p.get("url"), e)
        return None


def own_blocks(pages):
    """Блоки своего текста страницы — без шаблона сайта. Шаблон — блоки текста (пункт меню, строка шапки, «Цену
    узнавайте по телефону»), которые повторяются на многих страницах: не меньше чем на 10 и не меньше 5% страниц.
    Так шаблон отрезается на любом сайте, даже если меню не размечено тегами <nav>/<footer>.
    Возвращает {url: [блоки]}; страницы без блоков — не входят."""
    unpack = unpack_blocks
    # Два прохода, а не все распакованные тексты разом: на большом сайте (thehome.ru, 77 тыс. страниц) это
    # гигабайты - распаковать дважды дешевле, чем держать (01.11.2026). Результат тот же.
    df, n = defaultdict(int), 0
    for p in pages:
        bl = unpack(p)
        if bl is not None:
            n += 1
            for t in set(x.lower() for x in bl):
                df[t] += 1
    if not n:
        return {}
    limit = max(TEMPLATE_MIN_PAGES, int(TEMPLATE_SHARE * n))
    out = {}
    for p in pages:
        bl = unpack(p)
        if bl is not None:
            out[p["url"]] = [x for x in bl if df[x.lower()] < limit]
    return out


def near_duplicates(pages, threshold=0.9, bands=16):
    """Группы почти одинаковых страниц. Сначала кандидаты через «корзины» (LSH), потом точное сравнение
    отпечатков. Полные дубли (одинаковый текст) сюда не попадают — они в отдельной проверке."""
    sigs = {}
    for p in pages:
        if p.get("minhash"):
            sigs[p["url"]] = (p["minhash"].split(","), p.get("content_hash"))
    if len(sigs) < 2:
        return []
    n = len(next(iter(sigs.values()))[0])
    rows = n // bands
    buckets = defaultdict(list)
    for u, (sig, _) in sigs.items():
        for b in range(bands):
            buckets[(b, tuple(sig[b * rows:(b + 1) * rows]))].append(u)
    parent = {u: u for u in sigs}

    def find(u):
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u
    best = defaultdict(float)
    checked = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > 500:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if (a, b) in checked:
                    continue
                checked.add((a, b))
                sa, ha = sigs[a]
                sb, hb = sigs[b]
                if ha and ha == hb:
                    continue  # полный дубль
                sim = sum(x == y for x, y in zip(sa, sb)) / n
                if sim >= threshold:
                    parent[find(a)] = find(b)
                    best[a] = max(best[a], sim)
                    best[b] = max(best[b], sim)
    groups = defaultdict(list)
    for u in best:
        groups[find(u)].append(u)
    out = []
    for g in groups.values():
        g.sort()
        sims = [best[u] for u in g]
        out.append([len(g), f"{round(min(sims) * 100)}–{round(max(sims) * 100)}%" if min(sims) != max(sims)
                    else f"{round(max(sims) * 100)}%", "\n".join(g[:30])])
    out.sort(key=lambda r: -r[0])
    return out


def final_url(redir, u):
    """Куда в итоге ведёт адрес по цепочке переадресаций redir {откуда: куда}; на петле - где петля замкнулась."""
    seen = set()
    while u in redir and u not in seen:
        seen.add(u)
        u = redir[u]
    return u


def pagerank(db, nodes, redir, damping=0.85, iters=40, shares=None):
    """Внутренний PageRank по обычным (не nofollow) ссылкам. Шкала 1–100, логарифмическая,
    как Link Score у Screaming Frog. shares — словарь: туда пишется доля веса страницы (в сумме 1) для «Куда уходит вес»."""
    if not nodes:
        return {}
    out = defaultdict(set)
    for src, dst in link_rows(db, ("src", "dst"), "kind='a' AND nofollow=0 AND internal=1"):
        d = final_url(redir, dst)
        if src in nodes and d in nodes and src != d:
            out[src].add(d)
    # Считаем по номерам страниц в списках, а не по адресам в словарях - на большом сайте (thehome.ru, 57 тыс.
    # страниц, миллионы связей, 40 проходов) это минуты (01.11.2026). Порядок обхода страниц и ссылок прежний,
    # поэтому и суммы те же до последнего знака.
    order = list(nodes)
    n = len(order)
    idx = {u: i for i, u in enumerate(order)}
    outs = [[idx[v] for v in out[u]] for u in order]
    rank = [1 / n] * n
    for _ in range(iters):
        new = [(1 - damping) / n] * n
        dangling = sum(rank[i] for i in range(n) if not outs[i])
        for i in range(n):
            o = outs[i]
            if o:
                share = damping * rank[i] / len(o)
                for j in o:
                    new[j] += share
        add = damping * dangling / n
        rank = [x + add for x in new]
    rank = {u: rank[i] for i, u in enumerate(order)}
    if shares is not None:
        shares.update(rank)
    lo, hi = min(rank.values()), max(rank.values())
    if hi <= lo:
        return {u: 100 for u in nodes}
    llo, lhi = math.log(lo), math.log(hi)
    return {u: round(1 + 99 * (math.log(v) - llo) / (lhi - llo)) for u, v in rank.items()}
