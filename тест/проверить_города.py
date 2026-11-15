"""Проверка поиска городских версий (seocrawler/regions.py) без интернета: переключатель города, варианты адреса,
город в тексте, к какому городу относится адрес. Запуск: python тест/проверить_города.py (и из проверить_всё.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import regions as R  # noqa: E402

# как у talisman-online.ru: переключатель на JavaScript, ссылок на поддомены нет
HTML = """<nav><a href="/news/">Новости</a><a href="/about/">О нас</a></nav>
<div class="dropdown__inner" id="dropdown__inner_city"><p class="dropdown__title">Выберите город </p><ul>
<li><label for="city_1" class="radio"><input type="radio" name="city" id="city_1" value="1" checked />
<span class="radio__circle"></span><span class="radio__text">Екатеринбург</span></label></li>
<li><label for="city_3" class="radio"><input type="radio" name="city" id="city_3" value="3" />
<span class="radio__circle"></span><span class="radio__text">Первоуральск</span></label></li>
<li><label for="city_4" class="radio"><input type="radio" name="city" id="city_4" value="4" />
<span class="radio__circle"></span><span class="radio__text">Нижний Тагил</span></label></li></ul></div>
<ul class="menu"><li>Английский язык</li><li>Немецкий</li></ul>"""


def main():
    bad = []

    def check(ok, what):
        if not ok:
            bad.append(what)

    names = R.city_names(HTML)
    check(names == [("Екатеринбург", True), ("Первоуральск", False), ("Нижний Тагил", False)], f"переключатель: {names}")
    check(R.city_names('<select name="region"><option>Москва</option><option selected>Казань</option></select>')
          == [("Москва", False), ("Казань", True)], "список <select>")
    check(R.city_names("<div class='city'>Москва</div>") == [], "один город - это не переключатель")
    check("ntagil" in R.slug_variants("Нижний Тагил") and "pervouralsk" in R.slug_variants("Первоуральск")
          and "spb" in R.slug_variants("Санкт-Петербург"), "варианты адреса")
    check(R.mentions("Курсы в Нижнем Тагиле", "Нижний Тагил") and R.mentions("в Первоуральске", "Первоуральск")
          and not R.mentions("в Нижнем Новгороде", "Нижний Тагил"), "город в тексте")
    live = {"https://pervouralsk.site.ru/": (200, "https://pervouralsk.site.ru/"),
            "https://ntagil.site.ru/": (200, "https://ntagil.site.ru/")}
    import socket
    real = socket.getaddrinfo
    socket.getaddrinfo = lambda host, *a, **k: [()] if host in ("pervouralsk.site.ru", "ntagil.site.ru") else real("nonexistent.invalid", 80)
    try:
        regs = R.discover("https://www.site.ru/", HTML, ["https://www.site.ru/news/"],
                          lambda u: live.get(u, (404, u)), log=lambda *a: None)
    finally:
        socket.getaddrinfo = real
    check([(r["city"], r["url"], r["main"]) for r in regs] == [
        ("Екатеринбург", "https://www.site.ru/", True), ("Первоуральск", "https://pervouralsk.site.ru/", False),
        ("Нижний Тагил", "https://ntagil.site.ru/", False)], f"адреса городов: {regs}")
    folder = [{"city": "Москва", "url": "https://site.ru/", "main": True},
              {"city": "Санкт-Петербург", "url": "https://site.ru/spb/", "main": False}]
    check(R.region_of("https://site.ru/spb/uslugi/", folder)["city"] == "Санкт-Петербург"
          and R.region_of("https://www.site.ru/uslugi/", folder)["city"] == "Москва"
          and R.region_of("https://shop.site.ru/", folder) is None, "к какому городу относится адрес")
    check(R.match_link("Санкт-Петербург", ["https://site.ru/spb/kontakty/"], "site.ru") == "https://site.ru/spb/",
          "город-раздел по ссылке")
    print(("✗ города: " + "; ".join(bad)) if bad else "✓ города")
    return not bad


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
