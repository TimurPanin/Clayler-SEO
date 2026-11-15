"""Снимок результата анализа: доказать, что переделка кода не изменила отчёт (КАК_ПИСАТЬ_КОД.md, раздел 7).

  py -3 тест/снимок_анализа.py снять <папка кода> <база crawl.db> <файл снимка>
  py -3 тест/снимок_анализа.py сравнить <снимок до> <снимок после>

Снимать с PYTHONHASHSEED=0: часть сводки (вес, шаблоны) иначе может отличаться от запуска к запуску при том же коде.

Берёт все находки (ключ, важность, тексты, колонки, строки) и сводку. Базу не трогает: анализ идёт на её копии во
временной
папке. <папка кода> - корень программы; старый код удобно достать так: git worktree add <папка> HEAD.
"""
import json
import os
import shutil
import sys
import tempfile


def take(code_dir, db_path, out_path):
    sys.path.insert(0, code_dir)
    os.environ.update(CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1")
    from seocrawler.analyze import analyze
    from seocrawler.storage import Store
    with tempfile.TemporaryDirectory(prefix="clayler-snap-") as tmp:
        copy = os.path.join(tmp, "crawl.db")
        shutil.copy(db_path, copy)
        semantics = os.path.join(os.path.dirname(os.path.abspath(db_path)), "семантика.json")
        if os.path.exists(semantics):   # готовые заголовки и перелинковка берут из неё группы
            shutil.copy(semantics, tmp)
        store = Store(copy)
        issues, pages, summary = analyze(store)
        store.db.close()
    snap = {"issues": {i.key: {"severity": i.severity, "category": i.category, "title": i.title, "why": i.why,
                               "fix": i.fix,
                               "columns": i.columns, "rows": i.rows} for i in issues},
            "pages": len(pages), "health": summary.get("health"), "summary": summary}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, default=str)
    print(f"снято: находок {len(issues)}, страниц {len(pages)}, здоровье {summary.get('health')}")


def differences(a, b):
    out = []
    for k in ("pages", "health", "summary"):
        if a[k] != b[k]:
            out.append(f"{k}: отличается" if k == "summary" else f"{k}: {a[k]} -> {b[k]}")
    for key in sorted(a["issues"].keys() | b["issues"].keys()):
        x, y = a["issues"].get(key), b["issues"].get(key)
        if x is None or y is None:
            out.append(f"{key}: {'появилась' if x is None else 'пропала'}")
            continue
        for field in x:
            if x[field] != y[field]:
                extra = f" ({len(x[field])} -> {len(y[field])})" if field == "rows" else ""
                out.append(f"{key}: отличается {field}{extra}")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["снять"] and len(sys.argv) == 5:
        take(*sys.argv[2:])
        return 0
    if sys.argv[1:2] == ["сравнить"] and len(sys.argv) == 4:
        with open(sys.argv[2], encoding="utf-8") as f:
            a = json.load(f)
        with open(sys.argv[3], encoding="utf-8") as f:
            b = json.load(f)
        diff = differences(a, b)
        print("\n".join(diff) if diff else "отличий нет: находок " + str(len(a["issues"])))
        return 1 if diff else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
