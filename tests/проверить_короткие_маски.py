"""Семантика: маска без подсказок (длинный заголовок) спрашивается короче, причина «нет запросов» - понятная.
Было: timurpanin.ru - маски «технические seo-аудиты с ручной проверкой» и «тимур панин», подсказок 0,
запросов 0; Search Console (нет галочки) и Вебмастер (нет связи через VPN) - оба «не ответил»."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import accounts, semantics as S  # noqa: E402

bad = []


def check(name, got, want):
    if got != want:
        bad.append(f"{name}: {got!r}, ждали {want!r}")


check("короткие формы", S.shorter("технические seo-аудиты с ручной проверкой"),
      ["технические seo-аудиты", "технический seo-аудит", "seo-аудиты", "seo-аудит"])
check("два слова - без форм", S.shorter("тимур панин"), [])
check("единственное число", [S._one(w) for w in ("газовые", "услуги", "шкафы-купе", "котлов")],
      ["газовый", "услуга", "шкафы-купе", "котлов"])


class FakeSug:
    def __init__(self, ans):
        self.ans, self.asked = ans, []

    def get(self, e, q):
        self.asked.append((e, q))
        return self.ans.get((e, q), [])

    def save(self):
        pass


ph = "технические seo-аудиты с ручной проверкой"
sug = FakeSug({("yandex", "seo-аудит"): ["seo аудит сайта"], ("google", "технический seo-аудит"): ["технический seo аудит"]})
res = {("yandex", ph): [], ("google", ph): [], ("yandex", "газовые котлы"): ["газовые котлы цена"], ("google", "газовые котлы"): []}
out = S._shorter_tasks([ph, "газовые котлы"], res, sug, None, lambda m: None)
check("подсказки коротких форм идут к маске", out,
      {("yandex", "seo-аудит"): (["seo аудит сайта"], ph), ("google", "технический seo-аудит"): (["технический seo аудит"], ph)})
check("маска с подсказками короче не спрашивается", any(q.startswith("газов") for _, q in sug.asked), False)
res2 = {("yandex", ph): None, ("google", ph): []}
check("сервис не ответил - короче не спрашиваем", S._shorter_tasks([ph], res2, FakeSug({}), None, print), {})

check("нет галочки Search Console", accounts.fail_state(RuntimeError(
    'Google Search Console ответил 403: { "error": { "code": 403, "message": "Request had insufficient authentication scopes."')),
    "no_scope")
check("нет связи", accounts.fail_state(OSError("<urlopen error _ssl.c:1064: The handshake operation timed out>")), "no_link")
check("другое", accounts.fail_state(RuntimeError("ответил 500")), "error")
# «Подключения»: ошибка связи - по-русски и про VPN, не английский текст и не «Бережно» (это про сайты)
t = accounts.plain_error("yandex", "<urlopen error [WinError 10061] No connection could be made because the target "
                                   "machine actively refused it>")
check("ошибка связи в «Подключениях»", ("Нет связи с Яндексом" in t, "VPN" in t, "refused" in t, "Бережно" in t),
      (True, True, False, False))

if bad:
    print("ОШИБКИ:\n" + "\n".join(bad))
    sys.exit(1)
print("Короткие маски и причины «нет запросов»: всё в порядке")
