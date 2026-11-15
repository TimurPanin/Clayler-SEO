"""Местное SEO: телефоны и адреса на страницах (версия 6), микроразметка организации (30.09.2026)."""
from ... import calltrack
from ..common import NOTE, defaultdict


def _calltracking(add, pages):
    """Коллтрекинг (24.10.2026): номер в HTML от сервера и после JavaScript разный - его подменяет скрипт.
    Это сведение, а не ошибка. Сервис - подсказка по адресу скрипта."""
    swap, svc_only = [], []
    for p in pages:
        c = calltrack.load(p)
        if not c:
            continue
        svc = ", ".join(c.get("svc") or []) or "сервис не определён"
        if c.get("swap"):
            swap.append([p["url"], "\n".join(c.get("raw") or []) or "-", "\n".join(c.get("js") or []), svc])
        else:
            svc_only.append([p["url"], svc])
    names = sorted({s for r in swap for s in r[3].split(", ") if s != "сервис не определён"})
    add("calltracking", NOTE, "Местное SEO", "На сайте коллтрекинг, номер подменяется",
        "Телефон в HTML, который отдаёт сервер, и телефон после выполнения скриптов разные: номер подменяет скрипт "
        "коллтрекинга (сервис учёта звонков). Так обычно и задумано - каждый посетитель или каждый источник рекламы "
        "видит свой номер, чтобы считать звонки. Это не ошибка. Поисковые роботы и карточка организации видят номер "
        "из HTML от сервера, поэтому в проверках телефонов сравнивается именно он. Какой номер увидит "
        "конкретный посетитель, узнать нельзя: в колонке «После JavaScript» - номер, который показался при проверке."
        + (f" Сервис узнан по адресу скрипта: {', '.join(names)}." if names else ""),
        "Ничего делать не нужно, если подмена настроена вами. Проверьте, что в HTML от сервера стоит основной номер "
        "компании - тот же, что в Яндекс Бизнесе, 2ГИС и Google Картах, и что подменные номера не попадают в "
        "микроразметку организации.",
        ["Адрес", "Номер в HTML от сервера", "Номер после JavaScript", "Сервис"], swap)
    if not swap:   # без JavaScript подмену не видно - только сам подключённый скрипт
        names = sorted({s for r in svc_only for s in r[1].split(", ")})
        add("calltracking_script", NOTE, "Местное SEO", f"Подключён скрипт коллтрекинга: {', '.join(names)}",
            "На страницах есть скрипт сервиса учёта звонков. Такой скрипт обычно подменяет телефон на сайте: каждый "
            "посетитель или каждый источник рекламы видит свой номер. Подмена видна только после выполнения скриптов; "
            "при этой проверке номер на страницах не поменялся или скрипты не выполнялись. Это не ошибка.",
            "Ничего делать не нужно. Проверьте только, что в HTML от сервера стоит основной номер компании - тот же, "
            "что в Яндекс Бизнесе, 2ГИС и Google Картах.",
            ["Адрес", "Сервис"], svc_only)


def run(ctx):
    add, indexable = ctx.add, ctx.indexable
    _calltracking(add, ctx.html_ok)
    import json as _j
    ph_pages, ad_pages, with_c = defaultdict(list), defaultdict(list), 0
    for p in indexable:
        if not p.get("contacts"):
            continue
        try:
            c = _j.loads(p["contacts"])
        except ValueError:
            continue
        with_c += 1
        # коллтрекинг: подменные номера у каждого посетителя свои - сравниваем номера из HTML от сервера
        sp = calltrack.server_phones(p)
        for x in (c.get("phones", []) if sp is None else sp):
            ph_pages[x].append(p["url"])
        for x in c.get("addresses", []):
            ad_pages[x].append(p["url"])
    if with_c and (len(ph_pages) > 1 or len(ad_pages) > 1):
        crow = []
        for label, d in (("Телефон", ph_pages), ("Адрес", ad_pages)):
            if len(d) > 1:
                for val, urls in sorted(d.items(), key=lambda kv: -len(kv[1])):
                    crow.append([label, val, len(urls), "\n".join(urls[:2])])
        add("contacts_mix", NOTE, "Местное SEO", "На разных страницах разные телефоны или адреса",
            "Программа собрала телефоны (из кликабельных номеров и записей вида +7 (xxx) xxx-xx-xx) и адреса "
            "(ул., проспект… с номером дома) со всех страниц; блоки с реквизитами (юр. адрес, ИНН, банк) пропущены. "
            "Если у компании несколько офисов или отделов, это нормально. Если нет, скорее всего, после смены адреса "
            "или телефона поправили не все страницы: это путает и посетителей, и Яндекс (карточка организации).",
            "Посмотрите редкие значения (внизу списка): на каких страницах они стоят и актуальны ли. Заодно сверьте "
            "Яндекс Бизнес, 2ГИС и Google Карты - старые данные дольше всего живут там.",
            ["Что", "Значение", "На скольких страницах", "Например"], crow, page_col=None)


    # Адрес или телефон на сайте есть, а микроразметки организации нет ни на одной странице: Яндекс и Google берут
    # из неё название, адрес, телефон и часы работы для карточки организации и быстрых ответов.
    has_schema_data = any("schema_types" in p for p in indexable)  # старые проверки микроразметку не собирали
    org = any(_org_type(t) for p in indexable for t in (p.get("schema_types") or "").split(", "))
    if (ad_pages or ph_pages) and has_schema_data and not org:
        where = sorted({u for d in (ad_pages, ph_pages) for urls in d.values() for u in urls}, key=lambda u: (len(u), u))
        add("org_schema_none", NOTE, "Местное SEO", "Нет микроразметки организации (адрес, телефон, часы работы)",
            "На сайте есть адрес или телефон компании, но ни на одной странице нет микроразметки Organization или LocalBusiness. "
            "Из неё поисковики берут название, адрес, телефон и часы работы - для карточки организации, "
            "быстрых ответов и сниппета. Без неё эти данные приходится угадывать по тексту страницы.",
            "Добавьте на страницу «Контакты» (или в подвал сайта) блок JSON-LD LocalBusiness (лучше подходящий "
            "подтип, например Store или HVACBusiness) с полями name, address, telephone, openingHours. "
            "Данные должны совпадать с Яндекс Бизнесом и 2ГИС. Проверить - validator.schema.org.",
            ["Страница с адресом или телефоном"], [[u] for u in where[:20]], page_col=None)


# Типы Schema.org, которые описывают организацию: Organization, LocalBusiness и их подтипы (Store, AutoRepair…)
_ORG_TYPES = {"Organization", "LocalBusiness", "Corporation", "Store", "Dentist", "Restaurant", "Hotel", "Plumber",
              "Electrician", "Locksmith", "RoofingContractor", "GeneralContractor", "HousePainter", "MovingCompany",
              "AutoRepair", "AutoDealer", "GasStation", "Pharmacy", "Physician", "Hospital", "LegalService", "Attorney",
              "Notary", "RealEstateAgent", "TravelAgency", "Library", "Bakery", "CafeOrCoffeeShop", "BarOrPub",
              "BeautySalon", "HairSalon", "DaySpa", "ExerciseGym", "EmploymentAgency", "InsuranceAgency", "BankOrCreditUnion"}


def _org_type(t):
    t = t.strip()
    return t in _ORG_TYPES or t != "Service" and t.endswith(("Business", "Store", "Service", "Organization", "Establishment", "Agency"))
