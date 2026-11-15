"""hreflang: языковые и региональные версии страницы (<link rel="alternate" hreflang="en" href="...">).
Поисковик верит связи, только если она взаимная: A указывает на B, а B - обратно на A. Проверяется: нет обратной
ссылки, версия не открывается (ошибка, редирект, закрыта от поиска), неправильный код языка или страны, нет ссылки
на саму себя, один код - на разные адреса. Версии на других доменах проверяются, только если их открывали при обходе,
и только на ошибку и редирект. Страницы с canonical на другой адрес не проверяются."""
import re

from ..common import NOTE, WARN, defaultdict, link_rows

# Коды языков ISO 639-1 (стандарт, который требуют Google и Яндекс)
ISO639 = set("""aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz
ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv
ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn
no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te
tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu""".split())
_CODE = re.compile(r"^([a-z]{2,3})(?:-([a-z]{4}))?(?:-([a-z]{2}|\d{3}))?$", re.I)
# частые ошибки: код страны вместо кода языка, Великобритания как UK
_COMMON = {"ua": "украинский - uk (ua - это код страны)", "by": "белорусский - be (by - код страны)",
           "kz": "казахский - kk (kz - код страны)", "jp": "японский - ja", "cn": "китайский - zh (cn - код страны)",
           "gr": "греческий - el", "dk": "датский - da", "se": "шведский - sv (se - северносаамский)",
           "cz": "чешский - cs", "ee": "эстонский - et (ee - язык эве)"}


def code_problem(code):
    """Что не так с кодом hreflang, или ""."""
    c = (code or "").strip()
    if c.lower() == "x-default":
        return ""
    m = _CODE.match(c)
    if not m:
        return "неправильная запись: нужен код языка (ru) или язык-страна (ru-RU)"
    lang, region = m.group(1).lower(), (m.group(3) or "").lower()
    if lang in _COMMON:
        return "код страны вместо языка: " + _COMMON[lang]
    if lang not in ISO639:
        return f"нет такого кода языка «{lang}»"
    if region == "uk":
        return "Великобритания пишется GB, а не UK (en-GB)"
    return ""


def run(ctx):
    add, db = ctx.add, ctx.db
    links = defaultdict(list)   # страница -> [(код, адрес)]
    for src, dst, lang in link_rows(db, ("src", "dst", "anchor"), "kind='hreflang'"):
        if dst:
            links[src].append(((lang or "").strip(), dst))
    if not links:
        return
    page = {p["url"]: p for p in ctx.pages}
    targets = {s: {d for _, d in v} for s, v in links.items()}

    no_return, broken, bad_code, no_self, dup = [], [], [], [], []
    for src, items in sorted(links.items()):
        if src not in page or page[src]["status"] != 200:
            continue
        if page[src]["indexability"] == "Канонизирована":
            continue   # canonical ведёт на другой адрес: hreflang такой страницы поисковик не учитывает
        seen_codes = defaultdict(set)
        for lang, dst in items:
            seen_codes[lang.lower()].add(dst)
            why = code_problem(lang)
            if why:
                bad_code.append([src, lang, why])
            if dst == src:
                continue
            p = page.get(dst)
            st = ctx.status.get(dst)
            if not st:
                continue   # версию не открывали (другой домен или лимит страниц)
            if p is None or p["status"] != 200:
                code = st[0] or st[1]
                where = ctx.redir.get(dst)
                if p is None and code == 200 and not where:
                    continue   # версия на другом домене открывается, её hreflang и запрет индексации не видны
                broken.append([src, lang, dst, f"редирект на {where}" if where else f"ответ {code}"])
            elif p["indexable"] != 1:
                broken.append([src, lang, dst, "закрыта от поиска: " + (p["indexability"] or "noindex").lower()])
            elif src not in targets.get(dst, ()):
                no_return.append([src, lang, dst])
        if src not in targets[src]:
            no_self.append([src, ", ".join(sorted({lang for lang, _ in items}))])
        for lang, dsts in seen_codes.items():
            if len(dsts) > 1:
                dup.append([src, lang, "\n".join(sorted(dsts))])

    add("hreflang_no_return", WARN, "Индексация", "hreflang без обратной ссылки",
        "Страница указывает свою версию на другом языке, а та в ответ на неё не указывает. Поисковик учитывает "
        "hreflang, только если связь взаимная, иначе может показать в поиске не ту языковую версию.",
        "Передайте разработчику: на каждой версии перечислить все версии страницы, включая её саму, одинаковым списком.",
        ["Страница", "Код", "Версия, которая не ссылается обратно"], no_return)
    add("hreflang_broken", WARN, "Индексация", "hreflang ведёт на редирект, ошибку или закрытую страницу",
        "Указанная языковая версия не открывается, перенаправляет на другой адрес или закрыта от поиска. "
        "Такую связь поисковик пропускает.",
        "Укажите в hreflang конечные рабочие адреса, открытые для поиска.",
        ["Страница", "Код", "Версия", "Что не так"], broken)
    add("hreflang_bad_code", WARN, "Индексация", "Неправильный код языка в hreflang",
        "Код языка пишется по стандарту ISO 639-1 (ru, en, uk), страна - по ISO 3166 (ru-RU, en-GB). С неправильным "
        "кодом поисковик не понимает, для кого эта версия, и не учитывает её.",
        "Исправьте коды в hreflang по колонке «Что не так».",
        ["Страница", "Код", "Что не так"], bad_code)
    add("hreflang_no_self", NOTE, "Индексация", "hreflang без ссылки на саму страницу",
        "Google просит, чтобы в списке версий была и сама страница (hreflang на свой же адрес). Без неё связь "
        "иногда не учитывается.",
        "Добавьте в список hreflang строку с кодом языка этой страницы и её собственным адресом.",
        ["Страница", "Коды в списке"], no_self)
    add("hreflang_dup", NOTE, "Индексация", "Один код hreflang ведёт на разные адреса",
        "На странице один и тот же код языка указан для нескольких адресов: поисковик не знает, какой выбрать.",
        "Оставьте для каждого кода один адрес.",
        ["Страница", "Код", "Адреса"], dup)
