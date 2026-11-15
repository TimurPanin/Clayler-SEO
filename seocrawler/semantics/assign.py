"""Разложить новые запросы по готовым группам (вкладка «Разложить» на странице «Семантика»).

Группы - те, что уже есть: группы собранной семантики (с решениями человека) или свой файл «запрос + группа»
(Excel, CSV из Key Collector и т. п.). Новые запросы - вставленный список или файл. Бесплатно и без сети:
каждый новый запрос сравнивается со всеми запросами группы по словам.

Как сравнивается:
- слова приводятся к основе (stem), «котел» = «котлы», Baxi = бакси (keys из семантики);
- синонимы из словаря: «айфон = iphone» - одно слово (и словарь ниши сайта, synonyms.py);
- не учитываются слова из словаря «не учитывать» («купить», «цена», «в») и города;
- у каждой группы считается, в какой доле её запросов встречается каждое слово; слово, которое есть почти во всех
  группах («котел»), весит меньше редкого («термопара»): «термопара для газового котла» уйдёт в «Термопары»,
  а не в «Газовые котлы»;
- запрос с маркером статьи («как», «что такое», «своими руками») - в «Статьи для блога», с маркером галереи
  («фото», «видео») - в «Галерея и портфолио»; рядом тема - группа, к которой он ближе всего.
Результат последней раскладки хранится по сайту в «решения семантики/<сайт> - раскладка.json» (для Excel)."""
import json
import math
import time

from . import City, _canon, dicts as DI, keys, norm, tokens
from . import decisions, imports

ARTICLES, GALLERY, NONE = "Статьи для блога", "Галерея и портфолио", "Не подошло ни к одной группе"
MIN_SCORE = 0.45      # меньше - «не подошло»
CLOSE = 0.08          # вторая группа ближе этого - «спорно»
MAX_NEW = 20000
GROUP_HEAD = ("групп", "кластер", "group", "cluster", "категор", "раздел")
SHORT = 3             # синоним из стольких букв («сто», «ми») не меняется в запросе с цифрами


def _syn_keys(w):
    """Ключи слова для словаря синонимов: основа и основа без гласной на конце («батарея» - «батаре», «батареи» -
    «батар»), звучание - только у слов длиннее SHORT."""
    out = set()
    for k in keys(w):
        if k.startswith("~"):
            if len(w) > SHORT:
                out.add(k)
            continue
        out.add(k)
        if len(k) >= 5 and k[-1] in "аеиоуыэюя":
            out.add(k.rstrip("аеиоуыэюя"))
    return out


class Words:
    """Слова запросов → номер слова: одинаковые по основе, звучанию и синонимам - один номер."""
    def __init__(self, d):
        self.ignore = set()
        for w in DI.active(d["ignore"]):
            for t in tokens(w):
                self.ignore |= keys(t)
        self.city = City().stems
        self.phrase_syn, self.word_syn = [], {}
        for line in d["synonyms"]:
            if line.lstrip().startswith("#"):
                continue
            parts = [norm(p) for p in line.split("=") if norm(p)]
            if len(parts) < 2:
                continue
            head = parts[0]
            if " " not in head:   # «айфон = iphone» и потом «iphone = айфон»: главное слово - из первой строки
                head = next((self.word_syn[k] for k in keys(head) if k in self.word_syn), head)
                for k in _syn_keys(parts[0]):
                    self.word_syn.setdefault(k, head)
            for p in parts[1:]:
                if " " in p:
                    # фраза узнаётся в любой форме и порядке слов: «циркуляционного насоса», «насос циркуляционный»
                    pc = tuple(sorted(_canon(keys(t)) for t in tokens(p)))
                    if pc:
                        self.phrase_syn.append((pc, head))
                elif " " not in head:
                    for k in _syn_keys(p):
                        self.word_syn.setdefault(k, head)
        self.phrase_syn.sort(key=lambda x: -len(x[0]))
        self.ids, self.n = {}, 0
        self.memo, self.first = {}, {}

    def _phrases(self, toks):
        if not self.phrase_syn:
            return toks
        cs = [_canon(keys(t)) for t in toks]
        out, i = [], 0
        while i < len(toks):
            for pc, head in self.phrase_syn:
                n = len(pc)
                if i + n <= len(toks) and tuple(sorted(cs[i:i + n])) == pc:
                    out += tokens(head)
                    i += n
                    break
            else:
                out.append(toks[i])
                i += 1
        return out

    def _id(self, ks):
        found = {self.ids[k] for k in ks if k in self.ids}
        i = min(found) if found else self.n
        if not found:
            self.n += 1
        for k in ks:
            self.ids.setdefault(k, i)
        return i

    def of(self, q):
        """Множество номеров значимых слов запроса."""
        if q in self.memo:
            return self.memo[q]
        toks = self._phrases(tokens(norm(q)))
        digits = any(ch.isdigit() for t in toks for ch in t)
        out, first = set(), None
        for t in toks:
            if len(t) == 1 and not t.isdigit():
                continue
            ks = keys(t)
            syn = next((self.word_syn[k] for k in _syn_keys(t) if k in self.word_syn), None)
            if syn and len(t) <= SHORT and digits:   # «сто рублей», «100 литров»: короткое слово рядом с числом - не синоним
                syn = None
            if syn:
                ks = keys(syn)
            if ks & self.ignore or ks & self.city:
                continue
            i = self._id(frozenset(x for x in ks if not x.startswith("~") or len(x) > 4))
            first = i if first is None else first
            out.add(i)
        self.memo[q], self.first[q] = frozenset(out), first
        return self.memo[q]


def _profiles(groups, W):
    prof = []
    for name, qs in groups:
        sets = [W.of(q) for q in qs]
        sets = [s for s in sets if s]
        if not sets:
            continue
        cnt = {}
        for s in sets:
            for w in s:
                cnt[w] = cnt.get(w, 0) + 1
        share = {w: c / len(sets) for w, c in cnt.items()}
        core = {w for w, v in share.items() if v >= 0.5} | W.of(name)
        prof.append({"name": name, "share": share, "core": core, "n": len(sets)})
    df = {}
    for p in prof:
        for w, v in p["share"].items():
            if v >= 0.1:
                df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1 + len(prof) / c) for w, c in df.items()}
    return prof, idf


def _score(qs, p, idf, first=None):
    """0…1: какая доля «веса» слов запроса есть в группе, и сколько главных слов группы есть в запросе.
    Главное слово запроса обычно первое: «группа безопасности бойлера» - группы безопасности, не бойлеры."""
    total = sum(idf.get(w, 1.5) for w in qs)
    if not total:
        return 0.0
    part = sum(idf.get(w, 1.5) * p["share"].get(w, 0) for w in qs) / total
    core = p["core"]
    cov = (len(core & qs) / len(core)) if core else 0
    if not core & qs:      # ни одного главного слова группы - не она, даже если общие «бойлер», «котел»
        return part * 0.5
    return min(1.0, 0.6 * part + 0.4 * cov + (0.15 if first in core else 0))


def run(groups, new, d=None, data=None):
    """groups: [(название, [запросы])], new: [{"q", "freq"?}] → строки результата.
    data - семантика сайта: тогда к словарю синонимов добавляются общий и словарь ниши сайта (synonyms.py)."""
    d = d or DI.load()
    if data:
        from . import synonyms
        d = dict(d, synonyms=list(d["synonyms"]) + synonyms.lines_for(data))
    W = Words(d)
    info, gal = DI.Markers(d["info"]), DI.Markers(d["gallery"])
    prof, idf = _profiles(groups, W)
    have = {norm(q): name for name, qs in groups for q in qs}
    out = []
    for row in new[:MAX_NEW]:
        q = norm(row["q"])
        if not q:
            continue
        qs = W.of(q)
        res = {"q": q, "freq": row.get("freq"), "group": NONE, "topic": "", "how": "", "alt": "", "why": "", "score": 0}
        ranked = sorted(((_score(qs, p, idf, W.first.get(q)), p) for p in prof), key=lambda x: -x[0])[:2] if qs else []
        best = ranked[0] if ranked and ranked[0][0] > 0 else None
        if q in have:
            res.update(group=have[q], how="уже в группе", score=1)
            out.append(res)
            continue
        mark = None if DI.BUY_RX.search(q) else (info.find(q) and ("info", info.find(q)) or gal.find(q) and ("gallery", gal.find(q)))
        if mark:
            res.update(group=ARTICLES if mark[0] == "info" else GALLERY, how="маркер «" + mark[1] + "»",
                       topic=best[1]["name"] if best and best[0] >= MIN_SCORE * 0.7 else "")
            out.append(res)
            continue
        if not best or best[0] < MIN_SCORE:
            res["how"] = "мало общих слов" if qs else "нет значимых слов"
            if best and best[0] >= MIN_SCORE / 2:   # «айфон 15» ближе всего к «Воздухоотводчикам» - не подсказка
                res["alt"] = best[1]["name"]
            out.append(res)
            continue
        sc, p = best
        common = [w for w in qs if p["share"].get(w, 0) >= 0.1]
        res.update(group=p["name"], score=round(sc, 2), why=", ".join(_word(W, w, q) for w in common))
        if len(ranked) > 1 and ranked[1][0] >= MIN_SCORE and sc - ranked[1][0] < CLOSE:
            res.update(how="спорно", alt=ranked[1][1]["name"])
        else:
            res["how"] = "уверенно" if sc >= 0.65 else "похоже"
        out.append(res)
    return out


def _word(W, wid, q):
    """Слово запроса с этим номером - для пояснения «общие слова»."""
    for t in tokens(norm(q)):
        # через W.of, как при раскладке: с синонимами («iphone» = «айфон»). Раньше прямой _id по словам без синонимов
        # давал «?» и заводил лишние номера слов
        if wid in W.of(t):
            return t
    return "?"


# ---------- откуда группы и запросы

def groups_from_semantics(data):
    """Группы собранной семантики (с решениями): кроме «Без группы» и убранных."""
    out = []
    for g in data.get("groups") or []:
        if g.get("kind") == "manual":
            continue
        qs = [r[0] for r in g.get("q") or [] if not (len(r) > 7 and r[7])]   # без «возможно, про другое»
        if qs:
            out.append((g["name"], qs))
    return out


def groups_from_file(name, raw):
    """Свой файл с группами: колонка «Группа» (кластер, категория) и колонка с запросом."""
    for rows in imports._table(name, raw):
        for i, r in enumerate(rows[:15]):
            cells = [str(c or "").strip().lower() for c in r]
            g = next((j for j, c in enumerate(cells) if any(w in c for w in GROUP_HEAD)), None)
            qcol = next((j for j, c in enumerate(cells) if j != g and any(w in c for w in ("запрос", "фраза", "ключ",
                                                                                             "query", "keyword"))), None)
            if g is None or qcol is None:
                continue
            out = {}
            for row in rows[i + 1:]:
                if max(g, qcol) >= len(row):
                    continue
                q, name_ = imports._query(row[qcol]), str(row[g] or "").strip()
                if q and name_:
                    out.setdefault(name_, []).append(q)
            if out:
                return list(out.items())
    raise ValueError("в файле не нашлось колонок «Группа» и «Запрос»")


def new_from(text="", name="", raw=b""):
    rows = {}
    if raw:
        lst, _kind = imports.parse(name or "запросы.txt", raw)
        for r in lst:
            rows[r["q"]] = r
    for line in (text or "").splitlines():
        line = line.split("\t")
        q = imports._query(line[0])
        if q and q not in rows:
            r = {"q": q}
            if len(line) > 1 and imports._num(line[1]) is not None:
                r["freq"] = int(imports._num(line[1]))
            rows[q] = r
    return list(rows.values())


# ---------- последний результат по сайту

def _path(host):
    return decisions.site_file(host, " - раскладка")


def save(host, result, source):
    d = {"made": time.strftime("%d.%m.%Y %H:%M"), "source": source, "rows": result}
    decisions.save_site_file(host, " - раскладка", d, indent=0)
    return d


def load(host):
    try:
        with open(_path(host), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def summary(rows):
    s = {"total": len(rows), "groups": 0, "articles": 0, "gallery": 0, "none": 0, "doubt": 0, "have": 0}
    for r in rows:
        if r["group"] == ARTICLES:
            s["articles"] += 1
        elif r["group"] == GALLERY:
            s["gallery"] += 1
        elif r["group"] == NONE:
            s["none"] += 1
        elif r["how"] == "уже в группе":
            s["have"] += 1
        else:
            s["groups"] += 1
            s["doubt"] += r["how"] == "спорно"
    return s


def write_xlsx(path, d, site):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Раскладка"
    head = ["Запрос", "Частотность", "Группа", "Тема (для статей и галереи)", "Как определено", "Ещё подходит",
            "Общие слова с группой"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F5D50")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    order = {ARTICLES: 1, GALLERY: 2, NONE: 3}
    for r in sorted(d["rows"], key=lambda r: (order.get(r["group"], 0), r["group"], -(r.get("freq") or 0), r["q"])):
        ws.append([r["q"], r.get("freq"), r["group"], r.get("topic") or "", r.get("how") or "", r.get("alt") or "",
                   r.get("why") or ""])
    for col, w in zip("ABCDEFG", (48, 13, 34, 30, 22, 30, 30)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    s = summary(d["rows"])
    ws2 = wb.create_sheet("Итог")
    for row in (["Сайт", site], ["Разложено", d["made"]], ["Группы взяты", d.get("source") or ""],
                ["Новых запросов", s["total"]], ["Легли в группы", s["groups"]], ["  из них спорно", s["doubt"]],
                ["Уже были в группах", s["have"]], [ARTICLES, s["articles"]], [GALLERY, s["gallery"]], [NONE, s["none"]]):
        ws2.append(row)
    ws2.column_dimensions["A"].width = 30
    ws2.column_dimensions["B"].width = 40
    wb.save(path)
