"""Перепись готовых проверок (ИНЖЕНЕРНЫЕ_ПРАВИЛА.md, раздел «Закон сохранения»): какие значения на самом деле
встречаются в базах папки «reports» - коды ответа, ошибки связи, типы содержимого, индексируемость, причины пропуска.
Не автотест, а инструмент: запускать после проверки нового необычного сайта или раз в месяц. Только чтение баз.
Всё, что помечено «⚠ без ящика», программа не умеет разложить (codes.bucket) - это готовая находка.
Запуск: py -3 tests/перепись_баз.py [папка с отчётами]   (вывод - в консоль; > файл.txt, если длинно)"""
import glob
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seocrawler.analyze.checks.codes import BUCKETS, bucket, meaning  # noqa: E402


def short(s):
    """Текст ошибки или причины без адресов и чисел внутри - чтобы одинаковые случаи сложились в одну строку."""
    s = re.sub(r"https?://\S+", "<адрес>", "" if s is None else str(s))
    return re.sub(r"\d+(\.\d+)?", "N", s)[:100]


TEXT = {
    "ошибки связи (свои)": "SELECT p.error FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND p.error<>''",
    "ошибки связи (чужие)": "SELECT p.error FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=0 AND p.error<>''",
    "тип содержимого (свои страницы с кодом 200)": """SELECT p.content_type FROM pages p JOIN urls u ON u.url=p.url
        WHERE u.internal=1 AND u.kind='page' AND p.status=200""",
    "тип содержимого (свои файлы с кодом 200)": """SELECT p.content_type FROM pages p JOIN urls u ON u.url=p.url
        WHERE u.internal=1 AND u.kind='resource' AND p.status=200""",
    "индексируемость": "SELECT p.indexability FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page'",
    "вид редиректа": "SELECT p.redirect_type FROM pages p WHERE p.redirect_type IS NOT NULL",
    "состояние в очереди": "SELECT state || ' ' || kind || (CASE WHEN internal=1 THEN ' свой' ELSE ' чужой' END) FROM urls",
    "причина пропуска": "SELECT skip_reason FROM urls WHERE skip_reason IS NOT NULL",
}


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "reports")
    dbs = sorted(glob.glob(os.path.join(folder, "*", "crawl.db")))
    codes, texts = defaultdict(Counter), defaultdict(Counter)
    where = defaultdict(set)
    for db in dbs:
        name = os.path.basename(os.path.dirname(db)).split("_")[0]
        try:
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            for internal, kind, st, err, loc in c.execute(
                    "SELECT u.internal, u.kind, p.status, p.error, p.location FROM pages p JOIN urls u ON u.url=p.url"):
                k = ("свои" if internal else "чужие", kind, st, bucket(st, err, loc) if internal and kind != "sitemap" else "")
                codes[k[:2]][k[2:]] += 1
                where[k].add(name)
            for title, q in TEXT.items():
                for (v,) in c.execute(q):
                    texts[title][short(v)] += 1
                    where[(title, short(v))].add(name)
            c.close()
        except sqlite3.Error as e:
            print(f"   {name}: база не читается ({e})")
    print(f"Баз: {len(dbs)}\n\n=== коды ответа (код - ящик - что значит; сколько адресов, в скольких базах)")
    for (who, kind), cnt in sorted(codes.items()):
        print(f"\n   {who}, {kind}:")
        for (st, box), n in sorted(cnt.items(), key=lambda kv: (kv[0][0] is None, kv[0][0] or 0)):
            mark = "  ⚠ без ящика" if box and box not in BUCKETS else ""
            bases = len(where[(who, kind, st, box)])
            print(f"     {n:>9}  [{bases:>2}]  {st}  {box or '-':18} {meaning(st)}{mark}")
    for title, cnt in texts.items():
        print(f"\n=== {title}")
        for v, n in cnt.most_common(40):
            print(f"     {n:>9}  [{len(where[(title, v)]):>2}]  {v!r}")
        if len(cnt) > 40:
            print(f"     ...и ещё {len(cnt) - 40} разных")


if __name__ == "__main__":
    main()
