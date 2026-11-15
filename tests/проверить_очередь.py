"""Автотест: «Очередь сайтов» (seocrawler/site_queue.py) - сайты по одному, сами, без человека.

Два тестовых сайта и один адрес, где никто не отвечает: очередь проверяет первый, пропускает мёртвый с пометкой
(и сообщением в Telegram), идёт дальше, в конце присылает итог и встаёт на паузу. Ещё: разбор списка (свой лимит,
«большой», заметки), повтор сайта не добавляется, «Остановить» - сайт снова ждёт и продолжится с того же места,
очередь на паузе; после «перезапуска программы» сайт, который шёл, снова ждёт (--continue); сайт, упавший посреди
обхода (tests/downsite.py, 502 на всё), прекращается сам и пропускается; «Пропустить сайт» - очередь идёт дальше.
Запуск: py -3 tests/проверить_очередь.py"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from проверить_всё import wait_up  # noqa: E402

SITES = [("htmlsite", 8796), ("imgsite", 8797)]
DEAD = 8799   # здесь никто не отвечает
DOWN = 8798   # tests/downsite.py: падает посреди обхода


def main():
    tmp = tempfile.mkdtemp(prefix="clayler-queue-")
    os.environ.update(CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1",
                      CLAYLER_NO_SPEED_LAB="1")
    from seocrawler.window import job as J
    J.REPORTS = tmp
    from seocrawler import site_queue as Q, telegram
    Q.FILE = os.path.join(tmp, "очередь.json")
    Q.HISTORY = os.path.join(tmp, "очередь история.json")   # не писать прогоны теста в настоящую историю
    Q.LISTS = os.path.join(tmp, "списки")
    telegram.notify_job = lambda job: None
    sent = []
    Q._tg = sent.append
    from seocrawler.window.server import start_check
    fails = []

    def check(cond, text):
        if not cond:
            fails.append(text)

    # разбор списка
    p = Q.parse("site.ru\nhttps://www.big.ru/ 2000 большой # каталог\n# заметка\nне адрес\nshop.ru, # магазин")
    check([x["url"] for x in p] == ["https://site.ru/", "https://www.big.ru/", "https://shop.ru/"], f"разбор: {p}")
    check(p[1]["limit"] == 2000 and p[1]["big"] and p[1]["note"] == "каталог", f"лимит и «большой»: {p[1]}")
    check(p[0]["limit"] is None and not p[0]["big"] and p[2]["note"] == "магазин", f"без лимита: {p[0]}, {p[2]}")
    os.makedirs(Q.LISTS)
    with open(os.path.join(Q.LISTS, "Тест.txt"), "w", encoding="utf-8") as f:
        f.write("a.ru\nb.ru большой\n")
    check(Q.ready_lists() == [{"name": "Тест", "file": "Тест.txt", "count": 2}], f"готовые списки: {Q.ready_lists()}")

    srvs = [subprocess.Popen([sys.executable, os.path.join(HERE, f"{n}.py"), str(p)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for n, p in SITES]
    try:
        for n, p in SITES:
            if not wait_up(p):
                print(f"✗ очередь: тестовый сайт {n} не запустился (порт {p} занят?)")
                sys.exit(1)
        urls = [f"http://127.0.0.1:{SITES[0][1]}/", f"http://127.0.0.1:{DEAD}/", f"http://127.0.0.1:{SITES[1][1]}/"]
        n, err = Q.add("\n".join(urls), pages=15)
        check(n == 3 and not err, f"добавлено {n}, ошибка {err}")
        n, err = Q.add(urls[0])
        check(n == 0, "сайт, который уже ждёт, добавился второй раз")
        st = Q.status(J.JOB)
        check(st["paused"] and st["counts"]["wait"] == 3 and st["pages"] == 15, f"после добавления: {st['counts']}")
        Q.tick(J.JOB, start_check)
        check(not J.JOB.running, "на паузе очередь сама начала проверку")
        check(Q.action("start", {}) == "", "«Запустить»")
        t0, seen_run = time.time(), set()
        while time.time() - t0 < 400:
            Q.tick(J.JOB, start_check)
            d = Q.load()
            seen_run |= {i["url"] for i in d["items"] if i["state"] == "run"}
            if d.get("notified"):
                break
            time.sleep(0.3)
        d = Q.load()
        states = [i["state"] for i in d["items"]]
        check(states == ["done", "fail", "done"], f"состояния: {states}")
        check(d["paused"] and d.get("notified"), "очередь кончилась, но не встала на паузу / нет итога")
        check(seen_run == set(urls), "не каждый сайт был «идёт»")
        check(all(i.get("folder") for i in d["items"] if i["state"] == "done"), "у готового сайта нет папки")
        check(d["items"][0].get("pages") and d["items"][0]["pages"] <= 15, f"страниц: {d['items'][0].get('pages')}")
        check(d["items"][1].get("reason"), "у пропущенного сайта нет причины")
        check(len(sent) == 2 and f"{DEAD}" in sent[0] and "пропущен" in sent[0], f"Telegram о пропуске: {sent[:1]}")
        check(len(sent) == 2 and "закончилась" in sent[1] and "проверено 2 из 3" in sent[1] and f"{DEAD}" in sent[1],
              f"Telegram итог: {sent[1:]}")
        # «Ещё раз» и «Остановить»: сайт снова ждёт, продолжится с того же места, очередь на паузе
        check(Q.action("retry", {"url": urls[0]}) == "" and Q.action("pages", {"pages": 400}) == "", "«Ещё раз»")
        Q.action("clear_done", {})
        check([i["url"] for i in Q.load()["items"]] == [urls[0]], "«Убрать готовые» убрал не то")
        Q.action("start", {})
        Q.tick(J.JOB, start_check)
        check(J.JOB.running and Q.load()["items"][0]["state"] == "run", "после «Ещё раз» сайт не начался")
        time.sleep(1.5)
        check(Q.action("stop", {}, J.JOB) == "", "«Остановить»")
        t1 = time.time()
        # под нагрузкой полного прогона сборка отчёта после «Остановить» (снимки телефона в Chromium) бывает
        # дольше 2 минут: тест падал, хотя очередь работала верно
        while J.JOB.running and time.time() - t1 < 300:
            time.sleep(0.3)
        it = Q.load()["items"][0]
        check(it["state"] == "wait" and it.get("resume") and Q.load()["paused"], f"после «Остановить»: {it}")
        check(len(sent) == 2, "после «Остановить» ушло лишнее сообщение в Telegram")
        # «перезапуск программы» посреди сайта: в файле «идёт», а в этой программе его никто не запускал
        d = Q.load()
        d["items"][0]["state"], d["items"][0]["resume"] = "run", False
        Q.save(d)
        Q.tick(J.JOB, start_check)
        it = Q.load()["items"][0]
        check(it["state"] == "wait" and it.get("resume"), f"после перезапуска: {it}")
        Q.action("start", {})
        Q.tick(J.JOB, start_check)
        t1 = time.time()
        while time.time() - t1 < 30 and not any("Продолжаю прошлую" in ln for ln in J.JOB.lines):
            time.sleep(0.3)
        check(any("Продолжаю прошлую проверку" in ln for ln in J.JOB.lines), "сайт после перезапуска начался заново, а не продолжился")
        Q.action("stop", {}, J.JOB)
        t1 = time.time()
        while J.JOB.running and time.time() - t1 < 300:
            time.sleep(0.3)

        # сайт упал посреди обхода (502 на всё): обход прекращается сам, сайт - «пропущен», очередь идёт дальше;
        # «Пропустить сайт»: текущий останавливается, очередь не встаёт на паузу
        down = subprocess.Popen([sys.executable, os.path.join(HERE, "downsite.py"), str(DOWN), "40"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        srvs.append(down)
        check(wait_up(DOWN), "тестовый сайт downsite не запустился")
        os.environ.update(CLAYLER_DOWN_STREAK="5", CLAYLER_DOWN_SECONDS="2")
        Q.action("clear_all", {})
        sent.clear()
        Q.add(f"http://127.0.0.1:{DOWN}/\nhttp://127.0.0.1:{SITES[1][1]}/ 400\nhttp://127.0.0.1:{SITES[0][1]}/", pages=150)
        Q.action("start", {})
        t0, skipped = time.time(), False
        while time.time() - t0 < 400:
            Q.tick(J.JOB, start_check)
            d = Q.load()
            if not skipped and d["items"][1]["state"] == "run" and J.JOB.running:
                time.sleep(1.5)
                check(Q.action("skip", {}, J.JOB) == "", "«Пропустить сайт»")
                skipped = True
            if d.get("notified"):
                break
            time.sleep(0.3)
        d = Q.load()
        it = d["items"]
        check([i["state"] for i in it] == ["fail", "fail", "done"], f"упавший и пропущенный: {[(i['state'], i.get('reason')) for i in it]}")
        check("перестал отвечать" in (it[0].get("reason") or "") and "502" in it[0]["reason"] and it[0].get("folder"),
              f"упавший сайт: {it[0].get('reason')}, папка {it[0].get('folder')}")
        check((it[1].get("reason") or "").startswith("пропущен вручную"), f"пропущенный: {it[1].get('reason')}")
        check(d.get("notified"), "после «Пропустить сайт» очередь не дошла до конца")
        check(any("перестал отвечать" in m and f"{DOWN}" in m for m in sent), f"нет сообщения об упавшем сайте: {sent}")
        check(not any(f"{SITES[1][1]}</b> пропущен" in m for m in sent), "о пропущенном вручную ушло сообщение")
        for k in ("CLAYLER_DOWN_STREAK", "CLAYLER_DOWN_SECONDS"):
            os.environ.pop(k, None)
    finally:
        for s in srvs:
            s.kill()
    if fails:
        print("✗ очередь сайтов:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("✓ очередь сайтов: по одному, мёртвый и упавший посреди обхода пропущены, итог в Telegram, пауза, стоп, "
          "«Пропустить сайт», переживает перезапуск")


if __name__ == "__main__":
    main()
