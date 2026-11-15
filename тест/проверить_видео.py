"""Автотест видео обхода (04.10.2026, seocrawler/crawl_video.py): ход проверки раскладывается на шаги по порядку
обхода, ошибки (4xx, 5xx, нет ответа) и редиректы считаются верно, ничего не теряется. Без браузера и сети:
само видео пишется в Chromium за ~20 с и проверяется руками."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import crawl_video as V  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


st = Store(os.path.join(tempfile.mkdtemp(), "crawl.db"))
codes = [200] * 500 + [404] * 7 + [500] * 2 + [None] + [301] * 13
for k, code in enumerate(codes):
    u = f"https://site.ru/p{k}"
    st.enqueue(u, 1, True, "page", None, "done")
    st.save_page({"url": u, "status": code})
st.enqueue("https://site.ru/img.jpg", 1, True, "resource", None, "done")  # картинки в видео не считаются
st.save_page({"url": "https://site.ru/img.jpg", "status": 404})
st.commit()
total, frames = V.timeline(st)
check(total == len(codes), f"страниц {total}")
check(len(frames) == V.FPS_DATA * V.RUN_SECONDS, f"шагов {len(frames)}")
check(frames[-1][0] == total and all(a[0] <= b[0] for a, b in zip(frames, frames[1:])), "счётчик страниц не растёт до конца")
check(sum(f[1] for f in frames) == 10 and sum(f[2] for f in frames) == 13, "ошибки и редиректы посчитаны неверно")
check("—" not in V.PAGE and "рограмм" not in V.PAGE, "текст в видео: длинное тире или «программа»")
st.db.close()

if fails:
    print("ОШИБКИ в видео обхода:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ видео обхода: ход проверки по шагам, ошибки и редиректы")
