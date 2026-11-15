"""Советы под движок сайта (по разбору пакета hightime.agency): как применить исправление на том движке,
который определила проверка (site_tech), со ссылкой на официальную справку. Чего на движке сделать нельзя (Тильда
сама делает robots.txt и sitemap.xml), - так и пишем, а не «замените файл». Движок не определён - общий совет.

Как дополнять: новый движок - запись в ENGINES (как его узнать по названию из site_tech, подписи и советы по темам);
тема без своего совета берётся из GENERIC. Ссылки - только на официальную справку движка или каталог его модулей,
перед добавлением открыть и убедиться, что страница живая (так проверены все ниже)."""
import re

TOPICS = ("robots", "sitemap", "redirects", "meta", "thumbs")

GENERIC = {
    "robots": "заменить файл robots.txt в корне сайта (через FTP или файловый менеджер хостинга), потом проверить в "
              "Яндекс Вебмастере («Инструменты → Анализ robots.txt»).",
    "sitemap": "положить файл в корень сайта и указать его адрес в Яндекс Вебмастере и Google Search Console; если "
               "движок делает карту сам, файл не класть, а сверить с ним настройки карты.",
    "redirects": "один из трёх вариантов: Apache - вставить в .htaccess; nginx - в настройки сервера; таблица - для модуля "
                 "редиректов в движке. Перед загрузкой просмотрите, куда ведёт каждый адрес.",
    "meta": "загрузить таблицу через импорт в движке или модуле SEO (колонки «Новый …», пустой «Новый H1» пропустить) "
            "или вставить вручную в настройках каждой страницы. Перед загрузкой прочитайте тексты.",
    "thumbs": "пересоздать уменьшенные копии картинок на сервере или поправить шаблон, который выводит несуществующие "
              "размеры.",
}

# ключ: (как узнать по названию движка из site_tech, подпись, {тема: совет}, {тема: ссылка})
ENGINES = {
    "tilda": (r"tilda", "Тильда", {
        "robots": "на Тильде robots.txt заменить нельзя - она делает его сама. Используйте файл для сверки: что "
                  "закрыть, задаётся в «Настройки сайта → SEO» (запрет индексации страниц - в настройках страницы).",
        "sitemap": "не заменять: Тильда делает карту сама (адрес сайт/sitemap.xml). Сверить: страницы с ошибками и "
                   "закрытые от индексации в карту попадать не должны - закройте их в настройках страницы.",
        "redirects": "файлы для Apache и nginx на Тильде не нужны - редиректы задаются в «Настройки сайта → "
                     "Переадресация» по таблице (старый адрес → новый).",
        "meta": "title, description и H1 вставляются вручную: «Настройки страницы → SEO» (title, description), "
                "H1 - в блоке страницы (тип заголовка H1 в настройках блока).",
        "thumbs": "картинки на Тильде хранит и уменьшает сама платформа: проверьте блок, где картинка не открывается, "
                  "и загрузите её заново.",
    }, {"robots": "https://help-ru.tilda.cc/search-engine", "sitemap": "https://help-ru.tilda.cc/search-engine",
        "redirects": "https://help-ru.tilda.cc/redirect", "meta": "https://help-ru.tilda.cc/search-engine"}),
    "bitrix": (r"bitrix|битрикс", "1С-Битрикс", {
        "robots": "«Маркетинг → Поисковая оптимизация → Настройка robots.txt» или файл в корне сайта.",
        "sitemap": "сверить с картой, которую делает 1С-Битрикс («Маркетинг → Поисковая оптимизация → Настройка "
                   "sitemap.xml»): лишние адреса исключить в настройках карты, а файл класть вместо карты движка, "
                   "только если её создание выключено.",
        "redirects": "сайты на Apache - .htaccess, на nginx (Битрикс VM) - настройки nginx; правила адресов движка - "
                     "«Настройки → Настройки продукта → Обработка адресов».",
        "meta": "title и description - в свойствах страниц и разделов («SEO» у элементов инфоблока), шаблоны - в "
                "настройках инфоблока; H1 - в шаблоне компонента.",
    }, {"robots": "https://dev.1c-bitrix.ru/user_help/service/seo/robots.php",
        "sitemap": "https://dev.1c-bitrix.ru/user_help/service/seo/sitemap.php",
        "redirects": "https://dev.1c-bitrix.ru/user_help/settings/urlrewrite/index.php",
        "meta": "https://dev.1c-bitrix.ru/user_help/service/seo/index.php"}),
    "wordpress": (r"wordpress", "WordPress", {
        "robots": "файл в корне сайта или редактор robots.txt в плагине SEO (Yoast, Rank Math).",
        "sitemap": "не заменять: карту на WordPress делает сам движок (wp-sitemap.xml) или плагин SEO (Yoast, Rank "
                   "Math). Сверить её с этим файлом: адреса, которых здесь нет (страницы с ошибками, редиректами, "
                   "noindex, служебные), исключить в настройках карты плагина; страницы, которых нет в карте движка, - "
                   "проверить, не закрыты ли они от поиска в настройках записи.",
        "redirects": "удобно загрузить таблицу в плагин Redirection (импорт CSV: старый адрес, новый адрес).",
        "meta": "title и description - в плагине SEO (Yoast, Rank Math) у каждой страницы или импортом; H1 - "
                "заголовок записи в шаблоне темы.",
        "thumbs": "пересоздать уменьшенные копии плагином Regenerate Thumbnails.",
    }, {"redirects": "https://wordpress.org/plugins/redirection/", "meta": "https://wordpress.org/plugins/wordpress-seo/",
        "sitemap": "https://wordpress.org/plugins/wordpress-seo/",
        "thumbs": "https://wordpress.org/plugins/regenerate-thumbnails/"}),
    "joomla": (r"joomla", "Joomla", {
        "redirects": "компонент «Перенаправления» (Компоненты → Перенаправления): старый адрес → новый.",
        "meta": "title и description - во вкладке «Публикация» материала и пункта меню.",
    }, {"redirects": "https://docs.joomla.org/", "meta": "https://docs.joomla.org/"}),
    "drupal": (r"drupal", "Drupal", {
        "redirects": "модуль Redirect (импорт таблицы - модулем Path redirect import).",
        "meta": "модуль Metatag: title и description у материалов и по шаблонам.",
        "sitemap": "карту делает модуль Simple XML sitemap - файл для сверки его настроек.",
    }, {"redirects": "https://www.drupal.org/project/redirect", "meta": "https://www.drupal.org/project/metatag",
        "sitemap": "https://www.drupal.org/project/simple_sitemap"}),
    "opencart": (r"opencart", "OpenCart", {
        "meta": "title, description и H1 - вкладка «Общее» у товара и категории («Мета-тег Title», «Мета-тег "
                "Description», «HTML-тег H1» в русских сборках).",
        "redirects": "в OpenCart нет своего модуля редиректов - .htaccess (Apache) или настройки nginx.",
    }, {"meta": "https://docs.opencart.com/", "redirects": "https://docs.opencart.com/"}),
    "modx": (r"modx", "MODX", {
        "meta": "title и description - поля ресурса (longtitle, description) или дополнение SEO Pro / SEO Suite.",
        "redirects": "дополнение Redirector или .htaccess / nginx.",
    }, {"meta": "https://docs.modx.com/", "redirects": "https://docs.modx.com/"}),
    "wix": (r"\bwix\b", "Wix", {
        "robots": "robots.txt на Wix редактируется в «SEO-инструменты → Редактор robots.txt», файл заменить нельзя.",
        "sitemap": "карту Wix делает сам - файл только для сверки.",
        "redirects": "«SEO-инструменты → Менеджер переадресаций» (можно загрузить таблицу CSV).",
        "meta": "«SEO-настройки» каждой страницы; title и description по шаблону - в «SEO-настройках сайта».",
    }, {"robots": "https://support.wix.com/ru", "sitemap": "https://support.wix.com/ru",
        "redirects": "https://support.wix.com/ru", "meta": "https://support.wix.com/ru"}),
}


def detect(engines):
    """Ключ движка из ENGINES по списку движков site_tech ([{name: …}] или названия), или ""."""
    for e in engines or []:
        n = ((e.get("name") if isinstance(e, dict) else e) or "").lower().replace("-", "").replace(" ", "")
        for key, (rx, *_rest) in ENGINES.items():
            if re.search(rx, n):
                return key
    return ""


def of_store(store):
    st = store.get_meta("site_tech", {}) or {}
    return detect(st.get("engines"))


def how(engine, topic, with_link=True):
    """Совет по теме для движка (или общий) - текст, со ссылкой на справку, если она есть."""
    _rx, _name, tips, links = ENGINES.get(engine, ("", "", {}, {}))
    text = tips.get(topic) or GENERIC.get(topic, "")
    link = links.get(topic) if topic in tips else ""
    return text + (f" Справка: {link}" if with_link and link else "")


def name(engine):
    return ENGINES[engine][1] if engine in ENGINES else ""
