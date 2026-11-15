"""План внутренней перелинковки: не только «на страницу мало ссылок», а с каких именно страниц
поставить ссылку и каким текстом.

Кому нужны ссылки (по важности): страницы групп запросов из семантики, которые продвигаем, если на них мало
ссылок или они глубоко; страницы без единой ссылки (знаем о них только из sitemap); страницы, на которые ведёт
одна-две ссылки; страницы дальше DEEP_CLICKS кликов от главной. Страницы списка (?page=2), фильтры с «?»,
служебные (контакты, политика) — не берём.

Откуда ставить ссылку (до трёх страниц): раздел выше по адресу (/katalog/kotly/ для /katalog/kotly/baxi/),
если он ещё не ссылается; страницы на ту же тему — с теми же словами в H1 и title (редкие слова сайта
весят больше), не глубже DEEP_CLICKS − 1 кликов, чтобы после ссылки страница стала ближе к главной; среди них —
те, на которые самих ведёт больше ссылок (их «вес» больше). Главная не предлагается, и одной странице
не советуем больше MAX_PER_DONOR новых ссылок.
Текст ссылки: главный запрос группы из семантики, иначе название страницы (H1 или начало title); для второй
и третьей ссылки — другой вариант названия, чтобы тексты не были одинаковыми.

Связь с «Запрос → страница» Семантики: семантика берётся с решениями человека (decisions.apply) и
сверкой страниц (plan.enrich), как в окне. Страница группы «Подходит / Доработать» получает ссылки, если на неё мало
ссылок, она глубоко или ни одна ссылка на неё не содержит слов главного запроса; текст второй и третьей ссылки -
другие запросы группы (не перестановка тех же слов). «Не та страница» ссылок не получает (сначала выбрать страницу).
Для групп «Создать» - готовый адрес новой страницы из «Запрос → страница» и откуда поставить на неё ссылки после
создания: раздел, в котором её создавать, и страницы на ту же тему."""
import json
import math
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from ..common import DEEP_CLICKS, dead_pages
from ...fmt import quote
from ...urls import page_key
from .meta_text import PAGE_N, SERVICE, _brand, _city, _clean, _strip_tail

MAX_TARGETS = 3000
MAX_PER_DONOR = 15
DONORS = 3
_W = re.compile(r"[а-яёa-z0-9]{3,}", re.I)


def _stems(text, skip):
    from ...semantics.stem import stem
    return {stem(w) for w in _W.findall((text or "").lower().replace("ё", "е"))} - skip


ANCHOR_SKIP = {"это", "или", "страна", "производитель", "отзывы", "отзыв", "инструкция", "фото", "видео", "своими", "руками", "бесплатно", "скачать",
               "официальный", "сайт", "форум", "схема", "ремонт"}
QUESTION = {"как", "что", "какой", "какая", "какие", "какую", "почему", "зачем", "сколько", "где", "когда", "чем",
            "лучше", "лучшие", "своими"}


def sem_groups(folder):
    """Группы семантики этой проверки с решениями человека и «Запрос → страница» (land); [] - не собирали."""
    from ...semantics import decisions, export, plan
    if not os.path.exists(os.path.join(folder, export.JSON_NAME)):
        return []
    data = export.load(folder)
    if not data or not data.get("groups"):
        return []
    return plan.enrich(decisions.apply(data, folder), None)["groups"]


def ctx_groups(ctx):
    """sem_groups для этой проверки, один раз на анализ."""
    if getattr(ctx, "sem_groups", None) is None:
        try:
            ctx.sem_groups = sem_groups(os.path.dirname(os.path.abspath(ctx.store.path)))
        except Exception:
            ctx.sem_groups = []
    return ctx.sem_groups


def sem_pages(ctx):
    """Страницы групп «Подходит / Доработать»: {адрес из «Запрос → страница»: группа}."""
    return {g["land"]["url"]: g for g in ctx_groups(ctx)
            if g.get("a") and (g.get("land") or {}).get("st") in ("ok", "fix") and g["land"].get("url")}


def sem_sig(folder):
    """Для подписи кеша анализа: семантика и решения по ней (поменяли страницу группы - план пересчитается)."""
    from ...semantics import decisions, export
    p = os.path.join(folder, export.JSON_NAME)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            host = json.load(f).get("host") or ""
        d = decisions._path(host)
        return os.path.getmtime(p), os.path.getmtime(d) if os.path.exists(d) else None
    except Exception:
        return os.path.getmtime(p)


def group_anchors(g, skip, n=3):
    """Тексты ссылок из запросов группы: главный запрос, потом другие запросы - не вопросы, не длиннее 60 знаков,
    не «отзывы / инструкция», и не те же слова в другом порядке («котлы электрические» = «электрические котлы»)."""
    main = ((g.get("a") or {}).get("main") or g["name"]).strip()
    base = _stems(main, skip)
    out, keys = [main], {frozenset(base)}
    for r in g.get("q") or []:
        q = " ".join(str(r[0] or "").split())
        if len(out) >= n:
            break
        if (len(r) > 7 and r[7]) or not 3 <= len(q) <= 60 or (len(r) > 2 and r[2] in ("Информация", "Галерея", "Сравнение", "Навигация")):
            continue
        if set(q.lower().replace("ё", "е").split()) & (ANCHOR_SKIP | QUESTION):
            continue
        k = frozenset(_stems(q, skip))
        # уточнение главного запроса («радиаторы отопления для частного дома»), а не соседняя тема группы
        # («запорная арматура для радиатора отопления»): все слова главного запроса и начинается с одного из них
        first = _stems(q.split()[0], set())
        if k and k not in keys and base <= k and first & base:
            out.append(q)
            keys.add(k)
    return out


def _site_pages(ctx):
    """Страницы для плана. Сироты из sitemap (на них нет ссылок) в ctx.indexable не входят - добираем из базы."""
    dead = dead_pages(ctx)   # они занимали бы места в плане и доноров
    pages = [p for p in ctx.indexable if not urlsplit(p["url"]).query and p["url"] not in dead]
    seen = {p["url"] for p in pages} | dead
    for r in ctx.db.execute("SELECT p.url, p.title, p.h1, u.depth FROM pages p JOIN urls u ON u.url=p.url "
                            "WHERE u.internal=1 AND u.kind='sitemap' AND p.status=200 AND p.indexable=1"):
        if r[0] not in seen and not urlsplit(r[0]).query:
            pages.append({"url": r[0], "title": r[1], "h1": r[2], "depth": r[3], "orphan": True})
    return pages


class _Planner:
    """План перелинковки: кому нужны ссылки и кто их может дать. Порядок: targets() дополняет страницы новыми из
    Семантики, потом build_donors() считает доноров по всем, потом plan_for(). Сколько ссылок назначено донору -
    состояние (used)."""

    def __init__(self, ctx, pages):
        self.pages, self.inl = pages, ctx.inl
        self.city, self.brand = _city(pages), _brand(pages)
        self.skip = set()
        for w in (self.city, self.brand, "купить", "цена", "цены", "заказать", "интернет", "магазин", "официальный",
                  "сайт", "для", "без", "под", "при", "или"):
            self.skip |= _stems(w, set())
        self.home = min(pages, key=lambda p: (p.get("depth") or 0, len(p["url"])))["url"]
        self.n_h1 = Counter(x.strip().lower() for p in pages for x in _clean(p.get("h1")).split(" | ") if x.strip())
        self.by_url = {p["url"]: p for p in pages}
        self.by_path = {urlsplit(p["url"]).path.rstrip("/"): p for p in pages}
        self.used = Counter()
        self._load_groups(ctx)
        self.n_names = Counter()
        for p in pages:
            for v in {self.h1_of(p).lower(), self.strip(self.h1_of(p)).lower(),
                      self.strip(_clean(p.get("title"))).lower()}:
                self.n_names[v] += 1

    def strip(self, name):
        return _strip_tail(name, self.brand, self.city)

    def h1_of(self, p):
        """Несколько H1 склеены через « | » («Блог о секретах английского | Словообразование…») - берём свой,
        а не общий для всего раздела."""
        parts = [x.strip() for x in _clean(p.get("h1")).split(" | ") if x.strip()]
        return min(parts, key=lambda x: (self.n_h1[x.lower()], -len(x))) if parts else ""

    def name_of(self, p):
        h, t = self.h1_of(p), self.strip(_clean(p.get("title")))
        return h if 3 <= len(h) <= 80 else t

    def _load_groups(self, ctx):
        """Семантика этой проверки («Запрос → страница» с решениями человека). sem: адрес → (группа, тексты ссылок);
        sem_new: новые страницы, которые советуют создать."""
        self.sem, self.sem_new = {}, []
        self.key_url = {page_key(u) or u: u for u in self.by_url}
        for g in sorted(ctx_groups(ctx), key=lambda g: -(g.get("score") or 0)):
            land = g.get("land") or {}
            if not g.get("a") or not land.get("url"):
                continue
            if land.get("st") in ("ok", "fix"):
                u = self.key_url.get(page_key(land["url"]) or land["url"])
                if u and u not in self.sem:
                    self.sem[u] = (g, group_anchors(g, self.skip))
            elif land.get("st") == "create" and land.get("new"):
                self.sem_new.append(g)

    def _without_query(self, ctx):
        """Страницы групп, на которые ни одна ссылка не содержит слова главного запроса."""
        out = set()
        if self.sem:
            from .inlink_anchors import anchors_for
            for u, anc in anchors_for(ctx, list(self.sem)).items():
                need = _stems(self.sem[u][1][0], self.skip)
                if need and anc and not any(need <= _stems(a, self.skip) for a in anc):
                    out.add(u)
        return out

    def targets(self, ctx):
        """Кому нужны ссылки: [(важность, порядок, длина адреса, адрес, почему)], самые важные первыми."""
        no_query = self._without_query(ctx)
        out = []
        for p in self.pages:
            target = self._target_of(p, no_query)
            if target:
                out.append(target)
        out += self._new_page_targets()
        out.sort()
        return out[:MAX_TARGETS]

    def _target_of(self, p, no_query):
        u = p["url"]
        if u == self.home or PAGE_N.search(u) or SERVICE.search(urlsplit(u).path):
            return None
        n_in, depth = len(self.inl.get(u, ())), p.get("depth") or 0
        why, prio = [], 9
        if n_in == 0 or p.get("orphan"):
            why.append("на страницу нет ни одной ссылки - поисковик знает о ней только из sitemap")
            prio = 1
        elif n_in <= 2:
            why.append(f"на страницу ссылается {n_in} {'страница' if n_in == 1 else 'страницы'}")
            prio = 2
        if depth > DEEP_CLICKS:
            why.append(f"{depth} кликов от главной")
            prio = min(prio, 3)
        order = depth
        if u in self.sem and (n_in <= 5 or depth > DEEP_CLICKS - 1 or u in no_query):
            main = self.sem[u][1][0]
            if u in no_query:
                why.append(f"ни одна ссылка на неё не содержит запрос {quote(main)}")
            why.insert(0, f"страница группы запросов {quote(main)} из семантики")
            prio, order = 0, -(self.sem[u][0].get("score") or 0)    # среди страниц групп - сначала с большим спросом
        return (prio, order, len(u), u, why) if why else None

    def _new_page_targets(self):
        """Новые страницы из «Запрос → страница»: в базе их нет, адрес, title и H1 - из семантики."""
        out = []
        for g in self.sem_new:
            land, a = g["land"], g.get("a") or {}
            u = land["url"]
            if u in self.by_url:
                continue
            near = self.key_url.get(page_key(g.get("near") or "") or g.get("near") or "")
            self.by_url[u] = {"url": u, "title": land.get("title") or a.get("title") or "", "h1": land.get("h1")
                              or g["name"],
                              "depth": ((self.by_url[near].get("depth") or 0) + 1) if near else 0, "new": True,
                              "near": near,
                              "sub": (g.get("todo") or "").startswith("Создать подраздел")}
            self.sem[u] = (g, group_anchors(g, self.skip))
            out.append((0, -(g.get("score") or 0), len(u), u,
                        [f"новая страница под группу запросов {quote(self.sem[u][1][0])} из семантики: "
                         "создать по адресу слева и поставить на неё ссылки"]))
        return out

    def build_donors(self):
        """Кто может дать ссылку: не глубоко, не служебная, не главная; индекс по редким словам заголовков."""
        pages = self.pages
        self.donor_ok = {p["url"] for p in pages if (p.get("depth") or 0) <= DEEP_CLICKS - 1 and p["url"] != self.home
                         and not SERVICE.search(urlsplit(p["url"]).path) and not PAGE_N.search(p["url"])}
        self.st = {u: _stems(f'{p.get("h1") or ""} {p.get("title") or ""}', self.skip) for u, p in self.by_url.items()}
        self.df = Counter(s for p in pages for s in self.st[p["url"]])
        self.rare_max = max(30, 0.05 * len(pages))
        self.index = defaultdict(list)
        for u in self.donor_ok:
            for s in self.st[u]:
                if self.df[s] <= self.rare_max:
                    self.index[s].append(u)

    def _anchors(self, p, mine):
        """Текст ссылки: запросы группы из семантики / H1 / начало title - только своё (не шаблонное «Автозапчасти»
        у сотен страниц) и не длиннее 60 знаков."""
        alt = list(mine)
        for v in (self.strip(self.h1_of(p)), self.strip(_clean(p.get("title"))), self.h1_of(p)):
            if (v and 3 <= len(v) <= 60 and self.n_names[v.lower()] <= 2
                    and v.lower() not in (a.lower() for a in alt)):
                alt.append(v)
        return alt

    def _named_donors(self, u, p, have):
        """Доноры, которых видно сразу: раздел, где создать страницу, и раздел выше по адресу."""
        donors = []
        near = p.get("near")
        if near and near != self.home and near != u:
            donors.append((near, "раздел, в котором создать страницу" if p.get("sub") else "страница из этой группы запросов"))
        par = self.by_path.get(urlsplit(u).path.rstrip("/").rsplit("/", 1)[0])
        if (par and par["url"] in self.donor_ok and par["url"] not in have and par["url"] != u and par["url"] != near
                and self.used[par["url"]] < MAX_PER_DONOR * 4):
            donors.append((par["url"], "раздел выше по адресу"))
        return donors

    def _can_give(self, d, u, have, donors):
        """Может ли страница d поставить ссылку на u: своя ли ещё квота и нет ли уже такой ссылки."""
        return d != u and d not in have and self.used[d] < MAX_PER_DONOR and d not in (x for x, _ in donors)

    def _donors_by_query(self, u, base, query, have, donors):
        """Страница группы семантики: донор - страница, в H1 или title которой есть все слова главного запроса."""
        cand = [d for d in self.donor_ok if base <= self.st[d] and self._can_give(d, u, have, donors)]
        cand.sort(key=lambda d: (-len(self.inl.get(d, ())), self.by_url[d].get("depth") or 0, len(d), d))
        return [(d, f"страница на ту же тему (в заголовке есть {quote(query)})") for d in cand[:DONORS - len(donors)]]

    def _donors_by_words(self, u, words, have, donors):
        """Обычная страница: донор - страница с теми же редкими словами в заголовке."""
        df, st = self.df, self.st
        score = Counter()
        for s in sorted(words):   # по порядку: сумма дробных чисел зависит от порядка
            for d in self.index.get(s, ()):
                score[d] += 1 / math.log(2 + df[s])
        need = 0.5 * sum(1 / math.log(2 + df[s]) for s in sorted(words))
        # общих редких слов - не меньше двух (одно лишь название бренда - слабая связь)
        min_shared = min(2, len(words))
        cand = [d for d, sc in score.items() if sc >= need and len(st[d] & words) >= min_shared
                and self._can_give(d, u, have, donors)]
        cand.sort(key=lambda d: (-score[d], -len(self.inl.get(d, ())), self.by_url[d].get("depth") or 0, len(d), d))
        out = []
        for d in cand[:DONORS - len(donors)]:
            common = sorted(st[d] & words, key=lambda s: (df[s], s))[:3]
            out.append((d, "страница на ту же тему" + (f" (общие слова: {', '.join(common)})" if common else "")))
        return out

    def _link_rows(self, donors, alt, mine, base):
        """Какую ссылку поставить у каждого донора. Запрос группы - ближе всего к донору (общие слова сверх главного
        запроса); подходящего нет - название страницы или снова главный запрос: с «Гибкая подводка для газового котла»
        - не «...для унитаза»."""
        rows, free = [], list(alt)
        for k, (d, reason) in enumerate(donors):
            self.used[d] += 1
            anchor = alt[k % len(alt)]
            if mine and k:
                fit = [a for a in free if a in mine and len(_stems(a, self.skip) & self.st[d]) > len(base)]
                rest = [a for a in free if a not in mine]
                anchor = (max(fit, key=lambda a: (len(_stems(a, self.skip) & self.st[d]), -free.index(a))) if fit
                          else rest[0] if rest else mine[0])
            if anchor in free:
                free.remove(anchor)
            rows.append({"from": d, "from_name": self.name_of(self.by_url[d]), "anchor": anchor, "reason": reason,
                         "from_depth": self.by_url[d].get("depth") or 0})
        return rows

    def plan_for(self, prio, u, why):
        """Строка плана для страницы; None - нечем подписать ссылку или её некому дать."""
        p = self.by_url[u]
        depth = p.get("depth") or 0
        mine = self.sem[u][1] if u in self.sem else []
        alt = self._anchors(p, mine)
        if not alt:
            return None
        have = self.inl.get(u, set())
        words = {s for s in self.st[u] if self.df[s] <= self.rare_max}
        donors = self._named_donors(u, p, have)
        base = _stems(mine[0], self.skip) if mine else set()
        if base:
            donors += self._donors_by_query(u, base, mine[0], have, donors)
        elif words:
            donors += self._donors_by_words(u, words, have, donors)
        if not donors:
            return None
        rows = self._link_rows(donors, alt, mine, base)
        new_depth = min([r["from_depth"] + 1 for r in rows] + [depth if depth else 99])
        return {"url": u, "name": self.name_of(p), "why": "; ".join(why), "inlinks": len(have), "depth": depth,
                "new_depth": new_depth, "links": rows, "prio": prio, "new": bool(p.get("new"))}


def run(ctx):
    pages = _site_pages(ctx)
    ctx.link_plan = []
    if len(pages) < 20:
        return
    planner = _Planner(ctx, pages)
    targets = planner.targets(ctx)
    planner.build_donors()
    plan = [x for x in (planner.plan_for(prio, u, why) for prio, _o, _l, u, why in targets) if x]

    def more(u, why):
        """Добавить страницу в план позже (вес ссылок считается после проверок: analyze/weight.py)."""
        if u in planner.by_url and all(x["url"] != u for x in plan):
            x = planner.plan_for(0, u, why)
            if x:
                plan.append(x)
                return x
        return None
    ctx.link_more = more
    ctx.link_plan = plan
