"""Готовые title, description и H1: программа не только находит плохие заголовки, но и предлагает,
как их написать. Только для страниц, которые могут попасть в поиск и у которых есть замечание: нет title или
описания, одинаковые у разных страниц, слишком длинные или короткие, нет H1 или он одинаковый.

Откуда берётся название страницы (по порядку): главный запрос группы из семантики (если её собирали для этой
проверки); свой H1 страницы, если он ни у кого больше не повторяется; первая часть title (до « | »), если она
своя; самый частый текст ссылок на страницу («Настенные котлы», не «Подробнее»). Номер страницы списка
(?PAGEN_1=2, /page/2/) дописывается: «… — страница 2».
К названию добавляется то, что точно есть на сайте: город (если он стоит в title у многих страниц), название
компании (хвост title у многих страниц), цена и наличие товара из разметки, первое предложение своего текста
страницы (без меню и подвала). Ничего не придумывается: нет данных — нет и слов про них.
Результат — ctx.meta_suggest (для отчёта, аудита, Excel и заголовки.csv) и колонка «Предлагаю» в проблемах
про title, description и H1."""
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..common import DESC_LONG, DESC_SHORT, TITLE_LONG, TITLE_SHORT, dead_pages, note_fault
from ...fmt import balance_quotes
from .meta_text import (BUY, CLAUSE, GENERIC_ANCHOR, INFO, PAGE_N, PROD_URL, SENT, SERVICE, SERVICE_URL, SHOP_URL,
                        STALE_YEAR, _brand, _cap, _city, _clean, _cut, _facts, _fix_punct, _norm, _own_facts,
                        _price, _product, _sentence, _short, _shorter, _sku, _strip_tail, _template)


def _low(s):
    return _clean(s).lower()


def _text_problem(text, url, counts, owner, owner_key, words, long_limit, short_limit):
    """Что не так с title или описанием: ([что не так], пометка «хозяина» дубля или "").
    У одинаковых текстов «хозяин» - страница ближе всех к главной: она свой текст оставляет, менять надо остальным."""
    missing, same, too_long, too_short = words
    if not text:
        return [missing], ""
    n = counts[text.lower()]
    if n > 1:
        if owner[(owner_key, text.lower())] != url:
            return [f"{same} у {n} стр."], ""
        return [], f"{same} у {n} стр.: у этой (ближе к главной) остаётся, меняется у остальных"
    if len(text) > long_limit:
        return [f"{too_long} ({len(text)} симв.)"], ""
    if len(text) < short_limit:
        return [f"{too_short} ({len(text)} симв.)"], ""
    return [], ""


class _Site:
    """Что известно о сайте в целом: бренд, город, дерево адресов и сколько раз повторяется каждый заголовок."""

    def __init__(self, pages):
        self.pages = pages
        self.city, self.brand = _city(pages), _brand(pages)
        if self.brand and self.city and self.brand.lower() == self.city.lower():
            self.brand = ""
        # для описания, если общего хвоста title нет, - имя сайта («Exist.ru»)
        host = urlsplit(pages[0]["url"]).hostname or ""
        self.name = self.brand or _cap(host[4:] if host.startswith("www.") else host)
        self.commercial = (sum(1 for p in pages if _product(p)) >= 5
                           or sum(1 for p in pages if PROD_URL.search(urlsplit(p["url"]).path)) >= 5
                           or sum(1 for p in pages if BUY.search(p.get("title") or "")) >= 0.05 * len(pages))
        # листья дерева адресов: у страницы нет страниц «под ней» - так выглядят карточки товаров
        paths = sorted(urlsplit(p["url"]).path.rstrip("/") + "/" for p in pages)
        self.has_kids = {a for a, b in zip(paths, paths[1:]) if b.startswith(a) and b != a}
        self.siblings = Counter(pp.rstrip("/").rsplit("/", 1)[0] for pp in paths)
        self.n_title, self.n_desc, self.n_h1, self.n_h1_first = Counter(), Counter(), Counter(), Counter()
        self.first_part = Counter()
        for p in pages:
            self.n_title[_low(p.get("title"))] += 1
            self.n_desc[_low(p.get("description"))] += 1
            self.n_h1[_low(p.get("h1"))] += 1
            self.n_h1_first[_low((p.get("h1") or "").split(" | ")[0] if (p.get("h1_count") or 0) > 1
                                 else p.get("h1"))] += 1
            self.first_part[self.strip_tail(_clean(p.get("title"))).lower()] += 1
        self.owner = {}
        for p in sorted(pages, key=lambda p: (p.get("depth") or 0, len(p["url"]))):
            for f, v in (("t", _clean(p.get("title"))), ("d", _clean(p.get("description"))),
                         ("h", _clean(p.get("h1")))):
                self.owner.setdefault((f, v.lower()), p["url"])

    def strip_tail(self, name):
        return _strip_tail(name, self.brand, self.city)

    def problems(self):
        """({адрес: (страница, что не так)}, [(страница, пометка «хозяина» дубля)])."""
        need, owners = {}, []
        for p in self.pages:
            url, h = p["url"], _clean(p.get("h1"))
            why_title, note = _text_problem(_clean(p.get("title")), url, self.n_title, self.owner, "t",
                                            ("нет title", "такой же title", "длинный", "короткий"), TITLE_LONG,
                                            TITLE_SHORT)
            if note:
                owners.append((p, note))
            why_desc, note = _text_problem(_clean(p.get("description")), url, self.n_desc, self.owner, "d",
                                           ("нет описания", "такое же описание", "длинное", "короткое"), DESC_LONG,
                                           DESC_SHORT)
            if note:
                owners.append((p, note))
            why_h1 = []
            if not p.get("h1_count"):
                why_h1.append("нет H1")
            elif h and self.n_h1[h.lower()] > 1 and self.owner[("h", h.lower())] != url:
                why_h1.append(f"такой же H1 у {self.n_h1[h.lower()]} стр.")
            if why_title or why_desc or why_h1:
                need[url] = (p, {"title": why_title, "description": why_desc, "h1": why_h1})
        return need, owners


def _load_semantics(ctx):
    """Семантика, если её собирали для этой проверки: {страница группы: группа с главным запросом и готовым ТЗ}."""
    sem = {}
    try:
        folder = os.path.dirname(os.path.abspath(ctx.store.path))
        with open(os.path.join(folder, "семантика.json"), encoding="utf-8") as f:
            for g in json.load(f).get("groups") or []:
                if g.get("page") and g.get("a"):
                    sem.setdefault(g["page"], g)
    except FileNotFoundError:
        pass   # Семантику для этого сайта не собирали: обычное дело, заголовки строятся без неё
    except (OSError, ValueError) as e:
        note_fault("файл семантика.json", "", e)
    return sem


def _link_names(ctx, site, need, sem):
    """Название страницы из текста ссылок на неё - только для тех, кому не хватило H1 и title."""
    hard = [u for u, (p, _w) in need.items()
            if u not in sem and not (_low(p.get("h1")) and site.n_h1[_low(p.get("h1"))] == 1)
            and not (site.first_part[site.strip_tail(_clean(p.get("title"))).lower()] == 1
                     and _clean(p.get("title")))]
    if not hard:
        return {}
    from .inlink_anchors import anchors_for
    menu_min = max(20, int(0.3 * len(ctx.html_ok)))
    anchors = {}
    for u, c in anchors_for(ctx, hard[:3000]).items():
        good = [(a, n) for a, n in c.items() if a and 3 <= len(a) <= 70 and not GENERIC_ANCHOR.match(a.strip())
                and re.search(r"[а-яёa-z]{3}", a, re.I) and len(a.split()) <= 8
                and not a.rstrip().endswith(("?", "!", "»", "…", "..."))
                and not (" " not in a.strip() and len(a.strip()) < 5)]   # «Фран», «Ещё» - не название
        # одно и то же слово в меню на каждой странице («Котлы») - тоже подходит, но текстовые - лучше
        good.sort(key=lambda x: (x[1] >= menu_min, -x[1], -len(x[0])))
        if good:
            anchors[u] = good[0][0]
    # один и тот же текст ссылки у многих страниц («Вам помочь?», «Frontier III» у всех модификаций) ничего не различает
    same = Counter(a.lower() for a in anchors.values())
    return {u: a for u, a in anchors.items() if same[a.lower()] <= 2}


@dataclass
class _Draft:
    """Черновик заголовков одной страницы: что есть сейчас и что о ней решили по дороге."""
    url: str
    page: dict
    why: dict
    title_now: str
    desc_now: str
    h1_now: str
    h1_main: str     # несколько H1 склеены « | »: название страницы - первый из них (у дублей title он часто свой)
    group: dict      # группа Семантики этой страницы или None
    path: str
    sem_name: str = ""
    name: str = ""
    src: str = ""
    page_no: int = 0
    kind: str = ""
    price: str = ""
    prod: dict = None
    look: list = field(default_factory=list)   # что проверить глазами перед тем, как ставить на сайт (fix_files)

    @classmethod
    def of(cls, url, page, why, group):
        h1_now = _clean(page.get("h1"))
        h1_main = h1_now.split(" | ")[0] if (page.get("h1_count") or 0) > 1 else h1_now
        return cls(url=url, page=page, why=why, title_now=_clean(page.get("title")),
                   desc_now=_clean(page.get("description")), h1_now=h1_now, h1_main=h1_main, group=group,
                   path=urlsplit(url).path)


class _Suggester:
    """Готовые заголовки страниц по очереди: занятые title и описания копятся, чтобы не создать новых дублей."""

    def __init__(self, ctx, site, need, sem):
        self.site, self.sem, self.manual = site, sem, ctx.meta_manual
        self.anchors = _link_names(ctx, site, need, sem)
        self.template = _template(site.pages)
        # одно и то же предложение у многих страниц («Интернет-магазин фабрики … называют первым») - текст шаблона,
        # для описания не годится
        self.sent_n = Counter(_sentence(p, self.template, "") for p, _w in need.values())
        self.by_path = {urlsplit(p["url"]).path.rstrip("/"): p for p in site.pages if not urlsplit(p["url"]).query}
        self.used_title, self.used_desc = set(site.n_title), set(site.n_desc)

    def row(self, url, page, why):
        """Строка таблицы заголовков; None - страницы в таблице нет (нечего предложить или разобрана вручную)."""
        d = _Draft.of(url, page, why, self.sem.get(url))
        self._choose_name(d)
        if not d.name:
            return None
        d.name = _cap(_cut(balance_quotes(d.name), 90))
        if not self._make_name_distinct(d):
            return None
        self._classify(d)
        title = self._title(d)
        desc = self._description(d)
        row = {"url": url, "kind": d.kind, "src": d.src,
               "why": "; ".join(f"{k if k != 'description' else 'описание'}: {', '.join(v)}" for k, v in why.items() if v),
               "title_now": d.title_now, "title": title if why["title"] else "",
               "desc_now": d.desc_now, "desc": desc if why["description"] else "",
               # h1_now несколько H1 склеивает « | »
               "h1_now": d.h1_now, "h1": self._h1(d), "h1_n": page.get("h1_count") or 0}
        for k, now in (("title", d.title_now), ("desc", d.desc_now), ("h1", d.h1_now)):
            row[k] = " ".join(row[k].split())   # без пробелов по краям и двойных
            if row[k] and row[k].lower() == now.lower():
                row[k] = ""
        row["look"] = d.look
        if row["title"] or row["desc"] or row["h1"]:
            return row
        if d.look:   # менять нечего (своё описание оставлено), но есть что сделать вручную - не теряем
            self._manual(d, d.look)
        return None

    def _manual(self, d, look):
        self.manual.append(_manual_row(d.page, why=d.why, look=look))

    def _choose_name(self, d):
        """Название страницы: главный запрос Семантики, начало title, H1 или текст ссылок - что первым подойдёт."""
        site, h_main = self.site, d.h1_main
        fp = site.strip_tail(d.title_now)
        fp_own = bool(fp) and site.first_part[fp.lower()] == 1 and len(fp) >= 3
        g = d.group
        d.sem_name = _cap((g["a"].get("main") or g["name"]) if g else "")
        # «Записаться», «Для взрослых в группе» - не название страницы: такие запросы из семантики не берём
        if (g and len(d.sem_name.split()) >= 2 and len(d.sem_name) >= 12
                and d.sem_name.split()[0].lower() not in ("для", "в", "на", "по", "с", "от", "о", "и", "без", "под")
                # «записаться москва» - действие
                and not d.sem_name.split()[0].lower().endswith(("ть", "ться", "чь"))):
            d.name, d.src = d.sem_name, "главный запрос из семантики"
        elif fp_own and h_main and len(fp) <= 90 and (_norm(h_main) in _norm(fp) or (
                len(h_main) < 20 and len(fp) >= len(h_main) + 10)):
            # «Аксессуары Haima S8» подробнее, чем H1 «Haima S8»; «3D программа расстановки мебели онлайн» - чем
            # «3D-программа»
            d.name, d.src = fp, "начало title"
        elif (h_main and site.n_h1[d.h1_now.lower()] == 1 and site.n_h1_first[h_main.lower()] == 1
              and 3 <= len(h_main) <= 90):
            d.name, d.src = site.strip_tail(h_main) or h_main, "H1 страницы"
        elif fp_own:
            d.name, d.src = fp, "начало title"
        elif d.url in self.anchors:
            self._name_from_links(d)
        elif h_main or fp:
            d.name, d.src = site.strip_tail(h_main or fp) or h_main or fp, "H1 или title (повторяется - уточните)"

    def _name_from_links(self, d):
        d.name, d.src = _clean(self.anchors[d.url]), "текст ссылок на страницу"
        # короткий текст ссылки («Duster III») - дополнить названием страницы уровнем выше («Запчасти для Dacia»)
        par = self.by_path.get(d.path.rstrip("/").rsplit("/", 1)[0])
        if not par:
            return
        ph = self.site.strip_tail(re.sub(r"\s*\([^()]*\)", "", _clean(par.get("h1") or par.get("title"))))
        # «Duster III», не «Оснастка для…»
        model = len(d.name.split()) <= 3 and not re.search(r"\b[а-яё]{4,}\b", d.name)
        if ph and model and d.name.lower() not in ph.lower() and len(ph) + len(d.name) < 70:
            d.name, d.src = f"{ph} {d.name}", "текст ссылок + раздел выше"

    def _make_name_distinct(self, d):
        """Одинаковые товары в разных адресах: отличие - число в конце адреса или артикул. False - отличить нечем."""
        site = self.site
        if not ("уточните" in d.src or site.n_title[d.title_now.lower()] > 1 or site.n_h1[d.h1_now.lower()] > 1):
            return True
        mnum = re.search(r"[-_](\d{3,})/?$", d.path)
        sku = _sku(d.page) if not mnum else ""
        if mnum and mnum.group(1) not in d.name:
            d.name = f"{d.name} {mnum.group(1)}"
        elif sku and sku.lower() not in d.name.lower():
            d.name = f"{d.name}, артикул {sku}"   # «Холодильник CANDY» у трёх карточек - различает артикул
        elif "уточните" in d.src:
            # одно и то же название у многих страниц («Модификация», «Автозапчасти») - это шаблон раздела, честно
            # предложить нечего. В файлах для разработчика страница всё равно есть - с причиной (дубль не должен
            # пропасть молча)
            self._manual(d, ["у страницы нет своего названия (H1 и title как у других) - "
                             "уникальный текст напишите вручную или поправьте шаблон"])
            return False
        return True

    def _classify(self, d):
        """Вид страницы (товар, статья, служебная, раздел, страница) - от него зависят шаблоны заголовков."""
        site, path = self.site, d.path
        m = PAGE_N.search(d.url)
        d.page_no = int(m.group(1)) if m and int(m.group(1)) > 1 else 0
        d.prod = _product(d.page)
        pk = path.rstrip("/") + "/"
        leaf = pk not in site.has_kids and site.siblings[pk.rstrip("/").rsplit("/", 1)[0]] >= 5 and pk.count("/") >= 3
        facts = _own_facts(d.page, self.template) if site.commercial else (0, False, "", False)
        n_price, cart, one_price, store = facts
        info, service = bool(INFO.search(path)), bool(SERVICE.search(path))
        # товар: разметка товара, или в своём тексте одна-три цены и «в корзину»/«купить», или «лист» каталога
        # (нет страниц под ним) с «в корзину»/«артикул» и не больше трёх цен
        is_prod = bool(d.prod) or (site.commercial and not info and not service and not d.page_no
                                   and pk not in site.has_kids
                                   and ((n_price <= 3 and cart and (n_price >= 1 or leaf)) or bool(PROD_URL.search(path))))
        # раздел магазина («… - купить, цены», «выбор, цены и наличие»): адрес каталога или витрина (корзина, наличие),
        # а не цены и «заказать» на странице услуги (primerline.agency: «Контекстная реклама…: в России, США - купить, цены»)
        shop = site.commercial and ((bool(SHOP_URL.search(path)) and not SERVICE_URL.search(path))
                                    or (store and n_price >= 2))
        d.kind = ("товар" if is_prod else "статья" if info else "служебная" if service
                  else "раздел" if shop else "страница")
        d.price = _price(d.prod) or (one_price if d.kind == "товар" else "")

    def _in_city(self):
        return f" в {self.site.city}" if self.site.city else ""

    def _title_variants(self, d, name):
        """Варианты title от полного к короткому."""
        # «Фран - мебель… | Фран» не нужно
        brand = self.site.brand if self.site.brand.lower() not in name.lower() else ""
        tail = f" | {brand}" if brand else ""
        in_city = self._in_city()
        if d.page_no:
            return [f"{name} - страница {d.page_no}{tail}", f"{name} - страница {d.page_no}"]
        if d.kind == "товар":
            buy = f"{name} - купить{in_city}" + (f" по цене {d.price}" if d.price else ", цена")
            return [buy + tail, buy, f"{name} - купить, цена", name]
        if d.kind == "раздел":
            return [f"{name}{in_city} - купить, цены{tail}", f"{name}{in_city} - купить, цены",
                    f"{name} - купить, цены", name]
        if d.kind == "служебная":
            return [f"{name} - {brand}" if brand else name, name]
        return [f"{name}{in_city}{tail}", f"{name}{tail}", name]

    def _title(self, d):
        name, g = d.name, d.group
        variants = self._title_variants(d, name)
        # готовый title из семантики - только если он о том же главном запросе (группа «Офлайн-курсы» на /online - нет)
        if (g and d.src.startswith("главный запрос") and g["a"].get("title") and not d.page_no
                and _norm(g["a"]["title"]).startswith(_norm(d.sem_name))):
            variants.insert(0, g["a"]["title"])
        title = next((v for v in variants if len(v) <= TITLE_LONG), "") or self._shortened_title(d, variants)
        if title.lower() in self.used_title and title.lower() != d.title_now.lower():
            # такой title уже у другой страницы - добавим отличие, иначе отметим «уточните»
            h_now = d.h1_now
            extra = h_now if h_now and h_now.lower() not in title.lower() and self.site.n_h1[h_now.lower()] == 1 else ""
            if extra and len(f"{title} - {extra}") <= TITLE_LONG + 15:
                title = f"{title} - {extra}"
            else:
                d.src += "; совпадает с другой страницей - уточните"
        site_name = self.site.name
        if (len(title) < TITLE_SHORT and site_name.lower() not in title.lower()
                and len(title) + len(site_name) + 3 <= TITLE_LONG):
            title = f"{title} | {site_name}"   # слишком короткий title («Серая кухня») - с названием сайта
        self.used_title.add(title.lower())
        return title

    def _shortened_title(self, d, variants):
        """Длинное название-перечисление: убираем последние пункты по одному, а не режем на полуслове."""
        n_var = len(self._title_variants(d, d.name))
        title = next((v for k in range(n_var) for nm in list(_shorter(d.name))[1:]
                      if len(v := self._title_variants(d, nm)[k]) <= TITLE_LONG), "")
        if title:
            if d.kind != "товар":   # у товара сокращение уточнений - обычное дело
                d.look.append("title: название сокращено - смысл не потерялся?")
            return title
        d.look.append("title: обрезан по длине - фраза законченная?")
        return _short(variants[-1], TITLE_LONG)

    def _sentence_for(self, d):
        """Первое предложение своего текста страницы, если оно не из шаблона. У статьи заголовок часто вопрос
        («Как выбрать б/у холодильник?»), слов из него в первом предложении может не быть - второй раз берём
        без этого условия."""
        for topic in ((d.name, "") if d.kind == "статья" else (d.name,)):
            sent = _sentence(d.page, self.template, topic)
            if sent and self.sent_n[sent] <= 1:
                return sent
        return ""

    def _new_description(self, d):
        """Новое описание: факты страницы + первое предложение своего текста."""
        name, g, site_name, in_city = d.name, d.group, self.site.name, self._in_city()
        sent = self._sentence_for(d)
        lead = sent + " " if sent else ""
        if g and g["a"].get("description") and not d.page_no:
            desc = g["a"]["description"]
        elif d.kind == "товар":
            # бренд и страна со страницы - описания товаров не одинаковые («…: цена 1 594 ₽, Marazzi, Италия»)
            fc = _facts(d.page)
            in_stock = "instock" in str((d.prod or {}).get("availability", "")).lower()
            facts = ", ".join(x for x in (f"цена {d.price}" if d.price else "",
                                          fc["brand"] if fc.get("brand") and fc["brand"].lower() not in name.lower() else "",
                                          fc.get("country", ""), "в наличии" if in_stock else "") if x)
            desc = f"{name}{in_city}" + (f": {facts}" if facts else "") + f". {lead}Заказывайте на сайте {site_name}."
        elif d.kind == "раздел":
            desc = f"{name}{in_city}: выбор, цены и наличие. {lead}Купить на сайте {site_name}."
        elif sent:
            desc = lead
        else:
            desc = f"{name}{in_city}".rstrip(".!?") + f". Подробнее - на сайте {site_name}."
        if d.page_no:
            desc = f"{name} - страница {d.page_no}. " + desc
        return _fix_punct(_clean(desc))

    def _description(self, d):
        desc = _fit_description(self._new_description(d))
        too_long = d.why["description"] and d.why["description"][0].startswith("длинное")
        if too_long and d.desc_now:
            parts = SENT.split(d.desc_now)        # длинное своё - просто сократить по предложениям
            keep = ""
            for s in parts:
                if len((keep + " " + s).strip()) > DESC_LONG:
                    break
                keep = (keep + " " + s).strip()
            # сокращённое своё - только если такого описания ещё ни у кого нет (страницы 2, 3 списка,
            # одинаковый текст у разделов): иначе сокращение даёт новый дубль
            keep = _fix_punct(keep)
            if len(keep) >= DESC_SHORT and keep.lower() not in self.used_desc:
                desc = keep
                if len(keep) < 0.6 * len(d.desc_now):
                    d.look.append("description: от своего осталось первое предложение - смысл и выгода остались?")
        desc = self._without_stale_year(desc)
        # обрыв «…» вместо своего законченного описания - хуже, чем было: своё оставляем, сократить - вручную
        if desc.endswith("…") and d.desc_now and not d.desc_now.endswith("…") and too_long:
            desc = d.desc_now
            d.look.append("description: длинное, сократить без обрыва не получилось - сократите вручную")
        self.used_desc.add(desc.lower())
        return desc

    def _without_stale_year(self, desc):
        """Предложение со старым годом («задачи на 2022 год») выкидываем, если без него есть что оставить;
        иначе - пометка «проверьте» (fix_files._look)."""
        parts = SENT.split(desc)
        fresh = [s for s in parts if not any(int(y) <= int(time.strftime("%Y")) - 2 for y in STALE_YEAR.findall(s))]
        joined = " ".join(fresh)
        if len(fresh) < len(parts) and len(joined) >= DESC_SHORT and joined.lower() not in self.used_desc:
            return joined
        return desc

    def _h1(self, d):
        # H1 у страниц списка обычно общий - номер в H1 не нужен
        if d.why["h1"] and d.name.lower() != d.h1_now.lower() and (self.site.n_h1[d.name.lower()] == 0 or d.page_no):
            return d.name
        return ""


def _fit_description(desc):
    """Не длиннее предела: сначала выкинуть последнее предложение, потом резать по смыслу."""
    if len(desc) <= DESC_LONG:
        return desc
    parts = SENT.split(desc)
    while len(parts) > 1 and len(" ".join(parts)) > DESC_LONG:
        parts.pop()
    desc = " ".join(parts)
    if len(desc) <= DESC_LONG:
        return desc
    # одно длинное предложение: до придаточного («…для SEO, который…»), если остаётся достаточно
    # (до простой запятой нельзя: «понимать, какие версии…» → «понимать.»), иначе по слову с «…»
    cut = _cut(desc, DESC_LONG - 1)
    heads = [m.start() for m in CLAUSE.finditer(cut) if m.start() >= DESC_SHORT]
    return cut[:heads[-1]].rstrip(" .,;:") + "." if heads else cut.rstrip(".") + "…"


def _manual_row(p, **extra):
    return {"url": p["url"], "title_now": _clean(p.get("title")), "desc_now": _clean(p.get("description")),
            "h1_now": _clean(p.get("h1")), "h1_n": p.get("h1_count") or 0, **extra}


def _add_suggest_column(ctx, out):
    """Колонка «Предлагаю» в проблемах про title, description и H1."""
    by = {r["url"]: r for r in out}
    field_of = {"title_missing": "title", "title_dup": "title", "title_long": "title", "title_short": "title",
                "desc_missing": "desc", "desc_dup": "desc", "desc_long": "desc", "desc_short": "desc",
                "h1_missing": "h1", "h1_dup": "h1"}
    for iss in ctx.issues:
        f = field_of.get(iss.key)
        if not f:
            continue
        col = 2 if iss.key in ("title_dup", "desc_dup", "h1_dup") else 0
        new_rows, any_ = [], False
        for r in iss.rows:
            sug = []
            for x in str(r[col]).split("\n"):
                s = (by.get(x) or {}).get(f, "")
                sug.append(s if col == 0 else (s or "-"))
                any_ = any_ or bool(s)
            new_rows.append(list(r) + ["\n".join(sug)])
        if any_:
            iss.columns = list(iss.columns) + ["Предлагаю" + (" (по порядку адресов)" if col else "")]
            iss.rows[:] = new_rows
            iss.fix += " Готовый вариант для каждой страницы - в колонке «Предлагаю» и в файле заголовки.csv."


def run(ctx):
    ctx.meta_suggest = []
    ctx.meta_manual = []   # дубли, для которых текст не собрать: в файлах для разработчика - «напишите вручную»
    # страница «не найдена» при коде 200 (удалённый товар: «Элемент не найден», checks/content soft404 - она раньше в
    # CHECKS): заголовки ей не нужны, нужен код 404 или 301. Раньше программа сочиняла им title и description из текста
    # ссылок (dom-primer.ru: 1 798 из 5 836 предложенных описаний). Убираем с самого начала - и из подсчёта
    # повторов: иначе пустышка ближе к главной становилась «хозяином» дубля живой страницы (ревью).
    # В файлах для разработчика - с причиной, если у неё нет title, описания или H1
    soft, dead = ctx.soft404, dead_pages(ctx)
    pages = [p for p in ctx.indexable if p["url"] not in dead]
    for p in ctx.indexable:
        if p["url"] in soft and not (_clean(p.get("title")) and _clean(p.get("description")) and p.get("h1_count")):
            ctx.meta_manual.append(_manual_row(p, what="не менять: сначала код 404 или 301",
                                               look=["страница «не найдена» (удалённый товар): заголовки не нужны - "
                                                     "сначала "
                                                     "код 404 или 301 на замену, см. «Страница „не найдена“, но сервер говорит, "
                                                     "что всё в порядке»"]))
    if not pages:
        return
    site = _Site(pages)
    need, owners = site.problems()
    for p, note in owners:   # «хозяин» дубля - в таблицу с пояснением, если его самого не меняем по другой причине
        if p["url"] not in need:
            ctx.meta_manual.append(_manual_row(p, keep=True, look=[note]))
    if not need:
        return
    suggester = _Suggester(ctx, site, need, _load_semantics(ctx))
    out = [row for row in (suggester.row(u, p, why) for u, (p, why) in need.items()) if row]
    out.sort(key=lambda r: (r["url"].count("/"), len(r["url"])))
    ctx.meta_suggest = out
    _add_suggest_column(ctx, out)
