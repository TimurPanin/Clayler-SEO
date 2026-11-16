"""robots.txt: правила как у Google (* и $, самое длинное правило побеждает,
при равенстве побеждает Allow) плюс директива Яндекса Clean-param."""
import re
from urllib.parse import urlsplit, unquote


CLOSED_LIKE = "Закрыт в robots%"   # urls.skip_reason адреса, закрытого в robots.txt (условие LIKE)
# «none» в meta robots и X-Robots-Tag - это «noindex, nofollow». Но «max-image-preview:none» (и с пробелом после
# двоеточия) - только про вид сниппета: страница с ним открыта для поиска. Такие пары «max-…: значение» убираем
_MAX_RX = re.compile(r"max-[a-z-]+\s*:\s*[^\s,;]*", re.I)
_NONE_RX = re.compile(r"\bnone\b", re.I)


def says_none(text: str) -> bool:
    """В правилах для роботов (meta robots, X-Robots-Tag) есть «none» как запрет, а не значение max-image-preview."""
    return bool(_NONE_RX.search(_MAX_RX.sub(" ", text or "")))


def is_html_page(text: str) -> bool:
    """Вместо файла (robots.txt, sitemap) пришла обычная страница: код 200 ещё не значит, что это тот файл
    (sait-primer.com: на любой адрес - главная, и её HTML попал в готовый robots.txt для разработчика)."""
    head = (text or "").lstrip("﻿ \r\n\t")[:300].lower()
    return head.startswith(("<!doctype", "<html", "<head", "<body")) or "<html" in head


def sitemap_gone(status: int, body: bytes) -> bool:
    """Файла sitemap нет: адрес отвечает 404 или 410 либо вместо файла открывается обычная страница."""
    return status in (404, 410) or (status == 200 and is_html_page((body or b"").decode("utf-8", "replace")))


def page_instead(entry: dict) -> bool:
    """Запись meta «robots» одного сайта: вместо robots.txt была страница. В старых базах её HTML лежит в text."""
    return bool(entry.get("html") or is_html_page(entry.get("text")))


class Robots:
    def __init__(self, text: str = "", user_agent_token: str = "googlebot"):
        self.raw = text or ""
        self.sitemaps = []
        self.clean_params = []  # [(set(params), path_prefix)]
        self.crawl_delay = None
        self.rules = []  # [(allow: bool, pattern_str, regex)]
        self._parse(self.raw, user_agent_token.lower())

    def _parse(self, text, token):
        groups = []  # [(agents, rules, delay)]
        cur_agents, cur_rules, cur_delay = [], [], None
        last_was_agent = False
        # BOM (невидимый знак в начале файла из Блокнота): без этого первая строка «User-agent» не узнавалась,
        # и все запреты файла терялись
        for line in text.lstrip("\ufeff").splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key, val = key.strip().lower(), val.strip()
            if key == "user-agent":
                if not last_was_agent and cur_agents:
                    groups.append((cur_agents, cur_rules, cur_delay))
                    cur_agents, cur_rules, cur_delay = [], [], None
                cur_agents.append(val.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if key == "sitemap":
                self.sitemaps.append(val)
            elif key == "clean-param":
                parts = val.split()
                if parts:
                    names = set(parts[0].split("&"))
                    prefix = parts[1] if len(parts) > 1 else ""
                    prefix = prefix.rstrip("*")
                    self.clean_params.append((names, prefix))
            elif key in ("allow", "disallow") and cur_agents:
                cur_rules.append((key == "allow", val))
            elif key == "crawl-delay" and cur_agents:
                try:
                    cur_delay = float(val)
                except ValueError:
                    pass
        if cur_agents:
            groups.append((cur_agents, cur_rules, cur_delay))

        # Выбираем группу: самое специфичное совпадение по имени робота, иначе *
        best, best_len = None, -1
        for agents, rules, delay in groups:
            for a in agents:
                if a != "*" and a in token and len(a) > best_len:
                    best, best_len = (rules, delay), len(a)
        if best is None:
            merged, delay = [], None
            for agents, rules, d in groups:
                if "*" in agents:
                    merged += rules
                    delay = d if d is not None else delay
            best = (merged, delay)
        rules, self.crawl_delay = best
        for allow, pat in rules:
            if pat == "" and not allow:
                continue  # "Disallow:" без значения = разрешено всё
            self.rules.append((allow, pat, self._compile(pat)))

    @staticmethod
    def _compile(pat):
        anchored = pat.endswith("$")
        if anchored:
            pat = pat[:-1]
        rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in pat)
        return re.compile("^" + rx + ("$" if anchored else ""))

    def allowed(self, url: str):
        """Возвращает (разрешено, правило_которое_сработало)."""
        p = urlsplit(url)
        # правило сравнивается с путём вместе с параметрами (как у Google и Яндекса): «Disallow: /catalog/$» не
        # закрывает «/catalog/?page=2». Два вида пути: с русскими буквами и как в адресе (%D0%BA…)
        query = ("?" + p.query) if p.query else ""
        path, raw = unquote(p.path or "/") + query, (p.path or "/") + query
        best = None  # (длина, allow, pat)
        for allow, pat, rx in self.rules:
            if rx.match(path) or rx.match(raw):
                key = (len(pat), allow)
                if best is None or key > (best[0], best[1]):
                    best = (len(pat), allow, pat)
        if best is None:
            return True, ""
        return best[1], ("Allow: " if best[1] else "Disallow: ") + best[2]
