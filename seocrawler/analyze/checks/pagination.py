"""Постраничная навигация (каталог, стр. 2, 3...): адреса вида ?page=2, ?PAGEN_1=2, /page/2/ (?p= не берём:
у WordPress это номер записи, а не страницы).
Проверяется: первая страница открывается ещё и по адресу с номером 1 (дубль раздела); разные страницы навигации
показывают одно и то же (номер за концом списка отдаёт последнюю или первую страницу вместо 404).
Canonical страниц 2, 3... на первую - в indexing.py (pagination_canon)."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..common import WARN, defaultdict

_PARAM = re.compile(r"^(pagen_\d+|page|pg|paged|str)$", re.I)
SAME_SHARE = 0.95   # доля совпавших чисел отпечатка (MinHash): «то же самое»
MAX_SERIES = 300    # страниц одного списка для попарного сравнения
_PATH = re.compile(r"/page[-/]?(\d+)/?$", re.I)


def series(url):
    """(адрес списка без номера страницы, номер) или (None, None), если это не страница навигации."""
    s = urlsplit(url)
    m = _PATH.search(s.path)
    q = parse_qsl(s.query, keep_blank_values=True)
    nums = [v for k, v in q if _PARAM.match(k) and v.isdigit()]
    if m:
        path = s.path[:m.start()] + "/"
        return urlunsplit((s.scheme, s.netloc, path, s.query, "")), int(m.group(1))
    if nums:
        rest = urlencode([(k, v) for k, v in q if not (_PARAM.match(k) and v.isdigit())])
        return urlunsplit((s.scheme, s.netloc, s.path, rest, "")), int(nums[0])
    return None, None


def run(ctx):
    add = ctx.add
    groups = defaultdict(list)   # адрес списка -> [(номер, страница)]
    by_url = {p["url"]: p for p in ctx.html_ok}
    for p in ctx.html_ok:
        base, n = series(p["url"])
        if base:
            groups[base].append((n, p))
    if not groups:
        return

    first_dup, same = [], []
    for base, items in sorted(groups.items()):
        main = by_url.get(base)
        for n, p in items:
            canon = p["canonical"] or p["canonical_header"]
            if n <= 1 and main is not None and p["indexable"] == 1 and (not canon or canon == p["url"]):
                first_dup.append([p["url"], base, ctx.src_of(p["url"])])
        # почти одинаковый текст у разных страниц одного списка (номер за концом списка, «залипшая» навигация):
        # отпечаток текста без меню и подвала совпадает на SAME_SHARE и больше
        sig = [(n, p["url"], p["minhash"].split(",")) for n, p in sorted(items + ([(1, main)] if main is not None else []),
                                                                         key=lambda x: x[0])[:MAX_SERIES] if p.get("minhash")]
        done = set()
        for i, (n1, u1, m1) in enumerate(sig):
            for n2, u2, m2 in sig[i + 1:]:
                if n1 != n2 and u2 not in done and len(m1) == len(m2) and \
                        sum(a == b for a, b in zip(m1, m2)) >= SAME_SHARE * len(m1):
                    same.append([u2, u1, ctx.src_of(u2)])
                    done.add(u2)

    add("pagination_page1", WARN, "Индексация", "Первая страница списка открывается и с номером 1",
        "Раздел открывается по двум адресам: обычному и с номером страницы 1 (?page=1, /page/1/). Для поиска это "
        "две одинаковые страницы, вес ссылок делится между ними.",
        "Передайте разработчику: ссылка «1» в навигации должна вести на адрес раздела без номера, а адрес с номером 1 - "
        "перенаправлять на него (301) или указывать на него canonical.",
        ["Адрес с номером 1", "Основной адрес раздела", "Где ссылка"], first_dup)
    add("pagination_same", WARN, "Индексация", "Разные страницы навигации показывают одно и то же",
        "Страница списка с другим номером отдаёт тот же текст, что и другая страница этого списка. Так бывает, когда "
        "номер за концом списка (стр. 50 при 10 страницах) показывает последнюю или первую страницу вместо ошибки 404. "
        "Поисковик видит дубли и тратит на них обход.",
        "Передайте разработчику: номер страницы за концом списка должен отвечать 404 (или 301 на последнюю страницу).",
        ["Страница", "Такая же, как", "Где ссылка"], same)
