"""Взрыв параметров: у одной страницы десятки вариантов адреса с параметрами."""
from ..common import NOTE, defaultdict, urlsplit


def run(ctx):
    add, db = ctx.add, ctx.db
    from urllib.parse import parse_qsl
    pv = defaultdict(lambda: [0, defaultdict(int), 0, ""])
    for url, state, reason in db.execute("SELECT url, state, skip_reason FROM urls WHERE internal=1 AND kind='page' AND url LIKE '%?%'"):
        sp_ = urlsplit(url)
        base_ = sp_.scheme + "://" + sp_.netloc + sp_.path
        v = pv[base_]
        v[0] += 1
        for k, _ in parse_qsl(sp_.query, keep_blank_values=True):
            v[1][k] += 1
        if state == "done":
            v[2] += 1
        v[3] = v[3] or url
    prow = [[b, v[0], v[2], ", ".join(f"{k} ({n})" for k, n in sorted(v[1].items(), key=lambda kv: -kv[1])[:6]), v[3]]
            for b, v in pv.items() if v[0] >= 20]
    prow.sort(key=lambda r: -r[1])
    add("param_explosion", NOTE, "Индексация", "Страницы с десятками вариантов адреса с параметрами",
        "У этих страниц найдено много адресов с параметрами (сортировка, фильтры, страницы списка). Каждый вариант "
        "для робота - отдельный адрес: он тратит на них время и может найти дубли. В колонке «Открыто программой» - "
        "сколько из них не закрыто в robots.txt и реально обходится.",
        "Параметры, которые не меняют содержимое (сортировка, вид), закройте в robots.txt или через Clean-param "
        "для Яндекса и canonical на адрес без параметров. Нужные фильтры (с отдельным спросом) лучше сделать "
        "отдельными страницами с понятным адресом.",
        ["Страница", "Вариантов с параметрами", "Открыто программой", "Параметры (сколько раз)", "Пример"],
        prow, page_col=None)

