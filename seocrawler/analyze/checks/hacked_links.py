"""Похоже на взлом: спрятанные ссылки на чужие сайты и ссылки на казино, ставки, займы, сайты для взрослых
на сайте другой тематики. Скрытые ссылки - из pages.hidden_links (парсер помечает ссылки
в блоке со стилем display:none, visibility:hidden, font-size:0, left:-9999px и т. п.; ссылка, которая видна на той же
странице, туда не попадает). Новые чужие ссылки сразу на многих страницах - в сравнении проверок (compare.py)."""
import re
from collections import defaultdict
from urllib.parse import unquote

from ..common import CRIT, WARN, link_rows, page_json
from ... import urls as U
from ...fmt import plural

# слова спам-ссылок: основа слова, чтобы ловить падежи, но всегда с начала слова (\b): без этого «азино» находилось
# в «магазинов», «порно» - в «упорно». Без \b только названия, которых нет внутри обычных слов и которые
# в адресах и названиях пишут слитно (vulkancasino.com, вулканказино, buyviagra.net)
SPAM = [
    ("казино и игровые автоматы", r"казино|casino|\bазино|\bигровы[ехм]\s+автомат|\bонлайн[\s-]+слот|\bслоты\b|\bрулетк"),
    ("ставки и букмекеры", r"1xbet|\b1хбет|melbet|\bмелбет|\bpin-?up|\bпин-?ап|\bбукмекер|\bставк[иа]\s+на\s+спорт|\bbetting\b"),
    ("займы и кредиты", r"\bмикрозайм|\bзайм\w*\s+(?:онлайн|на\s+карту|без)|\bzaim|\bpayday\b|\bкредит\w*\s+без\s+(?:справок|отказа)"),
    ("сайты для взрослых", r"\bпорно|\bporn|\bxxx\b|\bsex\b|\bсекс|\bэскорт|\bescort|\bпроститут|\bшлюх|\bинтим\s*услуг|onlyfans"),
    ("лекарства без рецепта", r"\bвиагр|viagra|\bсиалис|cialis|\bлевитр|levitra"),
    ("покупка документов", r"\bкупить\s+диплом|\bдипломы?\s+купить|\bправа\s+купить|\bкупить\s+(?:водительские\s+)?права"),
]
SPAM_RX = [(name, re.compile(rx, re.I)) for name, rx in SPAM]
OWN_TOPIC_SHARE = 0.03    # слово есть в title или H1 у такой доли страниц сайта - это тема сайта, а не взлом
# Служебные ссылки виджетов карт («API», «Условия»): их вставляет сам виджет, и они бывают скрыты
# (nabiullin.com: tech.yandex.ru/maps - 13 строк «так выглядит взлом»). Не про конкретный сайт, а про
# сервисы.
MAP_WIDGET = re.compile(r"https?://(?:[\w-]+\.)*"
                        r"(?:yandex\.[a-z]+/(?:legal/)?maps\w*|google\.[a-z.]+/maps|2gis\.[a-z]+)(?:[/?#]|$)", re.I)


def _what(text):
    return [name for name, rx in SPAM_RX if rx.search(text)]


def _own_url_rx(start):
    """Адрес самого проверяемого сайта внутри чужой ссылки (кнопки «Поделиться»: vk.com/share.php?url=<страница
    сайта>, connect.ok.ru/offer?url=…, t.me/share?url=…). Его слова - не про чужой сайт: на thehome.ru
    товар «Штора Ridder Sex on the Beach» дал ложные «ссылки на сайты для взрослых» в кнопках «Поделиться»."""
    host = U.host_of(start or "")
    host = host[4:] if host.startswith("www.") else host
    if not host:
        return None
    # после имени сайта - граница: «/», «:», «?» или конец; mysite.ru.casino-xxx.com и mysite.ru-sex.com - чужие
    # сайты, их адрес проверяется. Точка в конце имени (mysite.ru./) - тот же сайт.
    return re.compile(r"https?://(?:[\w-]+\.)*" + re.escape(host) + r"\.?(?![\w.-])[^\s&#]*", re.I)


def _suspect(href, anchor, own_rx, topics):
    """Чем подозрительна ссылка на чужой сайт: адрес и текст ссылки; topics - тема сайта, она подозрением не считается.
    В ссылке стоит адрес самого сайта - это кнопка «Поделиться» (vk.com/share.php?url=<страница>&title=<название>):
    ни вложенный адрес, ни параметры после «?» (название и текст страницы) не проверяются, только сам чужой адрес до
    «?» и текст ссылки. Раньше вместо этого не считались подозрительными слова из title самой страницы -
    но так не нашлась бы спам-ссылка на странице, которую создали взломщики (title «Казино онлайн»)."""
    text = unquote(href)
    if own_rx is not None and own_rx.search(text):
        text = own_rx.sub(" ", text).split("?", 1)[0]
    return [w for w in _what(text + " " + (anchor or "")) if w not in topics]


def run(ctx):
    add, html_ok = ctx.add, ctx.html_ok
    if not html_ok:
        return
    # тема самого сайта: магазин сантехники может продавать «рулетку», сайт МФО - писать о займах
    own = defaultdict(int)
    for p in html_ok:
        for name in _what(" ".join(x or "" for x in (p.get("title"), p.get("h1")))):
            own[name] += 1
    own_topics = {n for n, c in own.items() if c >= max(2, OWN_TOPIC_SHARE * len(html_ok))}
    home = ctx.home
    own_topics |= set(_what(" ".join(x or "" for x in (home.get("title"), home.get("h1"), home.get("description")))))
    own_rx = _own_url_rx(ctx.store.get_meta("start", "") or home["url"])

    hidden = []
    for p in html_ok:
        for href, anchor in page_json(p, "hidden_links") or ():
            spam = _suspect(href, anchor, own_rx, own_topics)
            if not spam and MAP_WIDGET.match(href):
                continue
            hidden.append([p["url"], href, anchor or "-", ", ".join(spam) or "-"])
    bad_hidden = any(r[3] != "-" for r in hidden)
    add("hacked_hidden_links", CRIT if bad_hidden else WARN, "Безопасность",
        "Спрятанные ссылки на чужие сайты (так выглядит взлом)",
        "Эти ссылки стоят в блоке, который скрыт от посетителя (стиль display:none, нулевой шрифт, сдвиг далеко за "
        "край экрана), а поисковик их видит. Так взломщики ставят ссылки на свои сайты: посетитель и владелец их не "
        "замечают, а поисковик наказывает сайт за продажу ссылок. Иногда так прячут и безобидное (старый блок "
        "партнёров) - поэтому проверьте глазами. Ссылки, которые видны на той же странице, сюда не попадают."
        + (" В колонке «Что подозрительно» - ссылки на казино, ставки, займы и подобное: это почти наверняка взлом."
           if bad_hidden else ""),
        "Откройте страницу, нажмите Ctrl+U (код страницы) и найдите адрес ссылки. Если вы её не ставили - "
        "сайт взломан: передайте разработчику или хостингу, пусть найдут и удалят вредный код в шаблоне или базе, "
        "сменят пароли от админки, хостинга и FTP, обновят движок и модули. После чистки проверьте сайт в "
        "Яндекс Вебмастере («Безопасность и нарушения») и Search Console («Проблемы безопасности»).",
        ["Страница", "Скрытая ссылка", "Текст ссылки", "Что подозрительно"], hidden)

    # видимые ссылки на чужие сайты со спам-словами (скрытые уже выше)
    seen_hidden = {(r[0], r[1]) for r in hidden}
    spam_rows = []
    for src, dst, anchor in link_rows(ctx.db, ("src", "dst", "anchor"), "internal=0 AND kind='a'"):
        if not dst or not dst.startswith("http") or (src, dst) in seen_hidden:
            continue
        what = _suspect(dst, anchor, own_rx, own_topics)
        if what:
            spam_rows.append([src, dst, anchor or "-", ", ".join(what)])
    ok = {p["url"] for p in html_ok}
    spam_rows = [r for r in spam_rows if r[0] in ok]
    hosts = {U.host_of(r[1]) for r in spam_rows}
    add("hacked_spam_links", CRIT, "Безопасность",
        "Ссылки на казино, ставки, займы или сайты для взрослых",
        "На сайте другой тематики стоят ссылки на чужие сайты со словами про казино, ставки, займы, лекарства или "
        f"сайты для взрослых ({len(hosts)} {plural(len(hosts), 'сайт', 'сайта', 'сайтов')}). "
        "Обычно так выглядит взлом или спам в комментариях и отзывах. Поисковики за такие ссылки понижают сайт, "
        "а Яндекс может пометить его как опасный. Тема самого сайта учтена: если сайт сам о займах, ссылки про "
        "займы сюда не попадают.",
        "Если ссылку поставили не вы - удалите её. Ссылка в шаблоне или на многих страницах - признак взлома: "
        "передайте разработчику, пусть удалит вредный код и сменит пароли. Ссылка в комментарии или отзыве - "
        "удалите комментарий и включите проверку комментариев перед публикацией.",
        ["Страница", "Ссылка", "Текст ссылки", "Что подозрительно"], spam_rows)
