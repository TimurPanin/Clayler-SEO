"""На чём сделан сайт: движок (CMS) или конструктор и его версия, фреймворки, веб-сервер, защита и CDN, хостинг
по IP (провайдер и номер сети — ASN), DNS-серверы и почта домена, регистратор и срок домена, SSL-сертификат,
сервисы на сайте (онлайн-чат, коллтрекинг, карты…).

Всё бесплатно и без ключей: главная страница сайта (заголовки, cookie, HTML), адреса скриптов и картинок из базы
проверки, DNS через dns.google, сеть по IP — RIPEstat (stat.ripe.net) и RDAP, домен — whois.tcinet.ru для .ru/.su/.рф,
для остальных RDAP (rdap.org) или whois зоны.
Определяется при сборке отчёта (в том числе «Обновить отчёт» у старых проверок), один раз на проверку —
результат в meta «site_tech». Это состояние сайта на день сборки, а не на день обхода."""
import datetime as dt
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import settings as S, sysproxy
from .fetcher import UA_PRESETS, _classify, _decompress

TIMEOUT = 10

# ---------- движки и конструкторы: (название, вид, признаки в HTML, в адресах файлов/страниц, в заголовках, в cookie)
# вид: cms — движок, builder — конструктор (сайт живёт на чужой платформе), shop — платформа магазина
ENGINES = [
    ("1С-Битрикс", "cms", [r"/bitrix/(?:js|templates|cache|components)/", r"\bBX\.setCSSList\b", r"bitrix_sessid"],
     [r"/bitrix/"], [("x-powered-cms", r"bitrix")], [r"^BITRIX_SM_"]),
    ("WordPress", "cms", [r"/wp-content/", r"/wp-includes/", r"wp-json"], [r"/wp-content/", r"/wp-includes/"],
     [("link", r"api\.w\.org")], [r"^wordpress_", r"^wp-settings"]),
    ("Tilda", "builder", [r"tildacdn\.(?:com|pro|net)", r"data-tilda-", r"<!--/?tilda"], [r"tildacdn\."], [], []),
    ("Wix", "builder", [r"static\.wixstatic\.com", r"wix-bolt", r"_wixCssImports"], [r"wixstatic\.com"],
     [("x-wix-request-id", r"."), ("server", r"pepyaka")], []),
    ("Joomla", "cms", [r"/media/jui/", r"/media/system/js/", r"/components/com_", r"Joomla!"], [r"/media/jui/", r"/components/com_"],
     [], []),
    ("Drupal", "cms", [r"/sites/(?:default|all)/(?:files|themes|modules)/", r"Drupal\.settings", r"drupal-settings-json"],
     [r"/sites/default/files/"], [("x-drupal-cache", r"."), ("x-generator", r"drupal")], [r"^SESS[0-9a-f]{20,}"]),
    ("MODX", "cms", [r"/assets/components/", r"\bmodx\b"], [r"/assets/components/"], [("x-powered-by", r"modx")], []),
    ("OpenCart", "shop", [r"catalog/view/theme/", r"index\.php\?route=", r"catalog/view/javascript/"],
     [r"catalog/view/(?:theme|javascript)/", r"route=product/"], [], [r"^OCSESSID$"]),
    ("UMI.CMS", "cms", [r"umi\.cms", r"/styles/common/", r"umiru"], [], [("x-generated-by", r"umi")], []),
    ("NetCat", "cms", [r"/netcat(?:_template|_files)?/"], [r"/netcat(?:_files|_template)?/"], [], []),
    ("HostCMS", "cms", [r"/hostcmsfiles/"], [r"/hostcmsfiles/"], [], []),
    ("Webasyst (Shop-Script)", "shop", [r"/wa-data/public/", r"/wa-content/", r"/wa-apps/"], [r"/wa-data/", r"/wa-content/"],
     [], []),
    ("DataLife Engine", "cms", [r"DataLife Engine", r"/engine/classes/", r"dle_root"], [r"/engine/classes/"], [], []),
    ("InstantCMS", "cms", [r"instantcms"], [], [], []),
    ("Amiro.CMS", "cms", [r"amiro", r"/_mod_files/"], [r"/_mod_files/"], [], []),
    ("DIAFAN.CMS", "cms", [r"diafan"], [], [], []),
    ("CS-Cart", "shop", [r"cs-cart", r"dispatch=products\.", r"/design/themes/"], [r"dispatch=products\."], [], []),
    ("PHPShop", "shop", [r"phpshop"], [], [], []),
    ("Simpla", "shop", [r"simpla"], [], [], []),
    ("PrestaShop", "shop", [r"prestashop", r"/modules/ps_"], [r"/modules/ps_"], [], [r"^PrestaShop-"]),
    ("Magento", "shop", [r"Mage\.Cookies", r"/static/version\d+/", r"mage/cookies"], [r"/static/version\d+/"],
     [("x-magento-cache-debug", r".")], [r"^X-Magento-Vary$"]),
    ("Shopify", "shop", [r"cdn\.shopify\.com", r"Shopify\.theme"], [r"cdn\.shopify\.com"], [("x-shopid", r".")], []),
    ("InSales", "shop", [r"insales(?:-cdn)?\.(?:ru|com)", r"InSales\."], [r"insales"], [], []),
    ("Ecwid", "shop", [r"app\.ecwid\.com"], [], [], []),
    ("Битрикс24 (сайты и магазины в облаке)", "builder", [r"bitrix24\.(?:site|shop)", r"b24site"], [], [], []),
    ("uKit", "builder", [r"ukit\.com", r"ukit-"], [], [], []),
    ("uCoz", "builder", [r"\bucoz\b", r"\.ucoz\.(?:ru|net)", r"s\d+\.ucoz\.net"], [r"ucoz\.net"], [], []),
    ("Nethouse", "builder", [r"nethouse\.(?:ru|me)"], [], [], []),
    ("Flexbe", "builder", [r"flexbe"], [r"flexbe"], [], []),
    ("LPgenerator", "builder", [r"lpgenerator"], [], [], []),
    ("LPmotor", "builder", [r"lpmotor"], [], [], []),
    ("Craftum", "builder", [r"craftum"], [], [], []),
    ("Мегагрупп", "builder", [r"megagroup\.ru", r"/g/libs/"], [], [], []),
    ("Webflow", "builder", [r"data-wf-(?:page|site)", r"webflow\.(?:com|js)"], [], [], []),
    ("Squarespace", "builder", [r"static\d?\.squarespace\.com"], [], [], []),
    ("Readymag", "builder", [r"readymag"], [], [], []),
    ("Taplink", "builder", [r"taplink\.(?:cc|ru|at)"], [], [], []),
    ("October CMS", "cms", [r"/modules/system/assets/(?:js|css)/framework"], [r"/modules/system/assets/"], [],
     [r"^october_session$"]),
    ("Ghost", "cms", [r"ghost-(?:url|api)"], [], [], []),
]

# фреймворки и технологии на сайте: (название, признаки в HTML, заголовок, cookie)
TECH = [
    ("Next.js (React)", [r"__NEXT_DATA__", r"/_next/static/"], [("x-powered-by", r"next\.js")], []),
    ("Nuxt (Vue)", [r"__NUXT__", r"/_nuxt/"], [], []),
    ("React", [r"data-reactroot", r"react(?:-dom)?(?:\.production)?\.min\.js"], [], []),
    ("Vue.js", [r"\bvue(?:\.runtime)?(?:\.global)?(?:\.prod)?(?:\.min)?\.js", r"data-v-[0-9a-f]{8}"], [], []),
    ("Angular", [r"ng-version=", r"\bng-app\b"], [], []),
    ("Gatsby", [r"___gatsby"], [], []),
    ("Laravel", [], [], [r"^laravel_session$", r"^october_session$"]),
    ("Django", [r"csrfmiddlewaretoken"], [], [r"^csrftoken$"]),
    ("Ruby on Rails", [r'name="csrf-param" content="authenticity_token"'], [], [r"^_\w+_session$"]),
    ("ASP.NET", [r"__VIEWSTATE"], [("x-aspnet-version", r"."), ("x-powered-by", r"asp\.net")], [r"^ASP\.NET_SessionId$"]),
    ("Java", [], [], [r"^JSESSIONID$"]),
    ("Bootstrap", [r"bootstrap(?:\.bundle)?(?:\.min)?\.(?:css|js)"], [], []),
    ("WooCommerce (магазин на WordPress)", [r"woocommerce"], [], [r"^woocommerce_"]),
    ("Elementor (конструктор страниц WordPress)", [r"elementor"], [], []),
    ("Yoast SEO (SEO-плагин WordPress)", [r"Yoast SEO"], [], []),
    ("Rank Math (SEO-плагин WordPress)", [r"rank-math|Rank Math"], [], []),
    ("Аспро (готовое решение для Битрикса)", [r"/bitrix/templates/aspro", r"aspro"], [], []),
    ("Композитный кеш Битрикса", [], [("x-bitrix-composite", r".")], []),
    ("LiteSpeed Cache", [], [("x-litespeed-cache", r".")], []),
    ("Varnish (кеш)", [], [("x-varnish", r".")], []),
]

# защита от DDoS и CDN: (название, заголовки, cookie, слово в названии сети по IP)
SHIELDS = [
    ("Cloudflare", [("cf-ray", r"."), ("server", r"cloudflare")], [r"^__cf_bm$", r"^cf_clearance$"], r"cloudflare"),
    ("DDoS-Guard", [("server", r"ddos-guard")], [r"^__ddg"], r"ddos-guard"),
    ("Qrator", [("server", r"qrator")], [r"^qrator"], r"qrator"),
    ("StormWall", [("server", r"stormwall")], [], r"stormwall"),
    ("Servicepipe", [("server", r"servicepipe")], [], r"servicepipe"),
    ("Variti", [("server", r"variti")], [r"^spid$", r"^spsc$"], r"variti"),
    ("NGENIX", [("server", r"ngenix"), ("x-ngenix-cache", r".")], [], r"ngenix"),
    ("CDNvideo", [("server", r"cdnvideo")], [], r"cdnvideo"),
    ("Akamai", [("x-akamai-transformed", r"."), ("server", r"akamai")], [], r"akamai"),
    ("Fastly", [("x-fastly-request-id", r"."), ("via", r"varnish.*fastly|fastly")], [], r"fastly"),
    ("Amazon CloudFront", [("x-amz-cf-id", r"."), ("via", r"cloudfront")], [], r"cloudfront"),
    ("Sucuri", [("x-sucuri-id", r"."), ("server", r"sucuri")], [], r"sucuri"),
    ("Imperva", [("x-cdn", r"imperva|incapsula")], [r"^incap_ses"], r"incapsula|imperva"),
    ("Яндекс Облако CDN", [("server", r"yandex-cdn")], [], r"yandex.*cdn"),
]

# хостинг-платформы, где сервером управляет платформа, а не владелец сайта (сайт на GitHub Pages
# показывался как «скрыт за Fastly»). Признаки: заголовки ответа, имя сервера по IP, блок адресов, движок.
# headers: "fixed" — свои заголовки ответа задать нельзя, иначе — как их задать; cdn — чья сеть отдаёт сайт;
# redirects — можно ли сделать редирект 301 с отдельного адреса и как; cache — сколько браузер хранит файлы.
PLATFORMS = [
    {"name": "GitHub Pages", "hdr": [("server", r"^github\.com$"), ("x-github-request-id", r".")],
     "rdns": r"\.github\.(?:com|io)$", "net": r"github", "ips": ["185.199.108.0/22"], "cdn": "Fastly",
     "headers": "fixed", "cache": "10 минут (Cache-Control: max-age=600)",
     "redirects": "нельзя: GitHub Pages сам склеивает только www и http, редирект с отдельной страницы не задаётся"},
    {"name": "GitLab Pages", "hdr": [], "rdns": r"gitlab", "net": r"", "ips": ["35.185.44.232/32"],
     "headers": "fixed", "cache": "", "redirects": "в файле _redirects"},
    {"name": "Netlify", "hdr": [("server", r"^netlify"), ("x-nf-request-id", r".")], "rdns": r"netlify",
     "net": r"", "ips": ["75.2.60.5/32"], "headers": "в файле _headers или netlify.toml",
     "redirects": "в файле _redirects или netlify.toml"},
    {"name": "Vercel", "hdr": [("server", r"^vercel"), ("x-vercel-id", r".")], "rdns": r"vercel", "net": r"vercel",
     "ips": ["76.76.21.0/24"], "headers": "в файле vercel.json (раздел headers)",
     "redirects": "в файле vercel.json (раздел redirects)"},
    {"name": "Tilda", "engine": "Tilda", "headers": "fixed", "redirects": "в настройках сайта Тильды (раздел «Редиректы»)"},
    {"name": "Wix", "engine": "Wix", "headers": "fixed", "redirects": "в настройках SEO Wix (менеджер редиректов)"},
]


def fixed_platform(store):
    """Платформа, на которой заголовки ответа задать нельзя (GitHub Pages, Tilda…), и стоит ли DNS у Cloudflare
    (тогда заголовки можно добавить через Cloudflare). None — заголовки настраиваются как обычно."""
    st = store.get_meta("site_tech", None) or {}
    p = platform(st)
    if not p or p["headers"] != "fixed":
        return None
    return {**p, "cloudflare_dns": st.get("dns_provider") == "Cloudflare"}


LIMIT = "Это ограничение хостинга"  # в совете пункта: исправить нельзя, в смету работ не идёт
CF_TIP = ("Обойти можно только через Cloudflare: DNS сайта уже там. Включите для записей сайта проксирование "
          "(оранжевое облачко), режим SSL «Full», и тогда ")


def platform(st):
    """Хостинг-платформа сайта по сохранённым данным site_tech (работает и у старых проверок, без интернета)."""
    if not st:
        return None
    home = st.get("home") or {}
    net = st.get("net") or {}
    hdrs = {"server": home.get("server") or "", **(st.get("platform_headers") or {})}
    engines = [e.get("name") for e in st.get("engines") or []]
    for p in PLATFORMS:
        if p.get("engine"):
            if engines[:1] == [p["engine"]]:
                return p
            continue
        if _hdr(p["hdr"], hdrs):
            return p
        if p["rdns"] and re.search(p["rdns"], net.get("rdns") or "", re.I):
            return p
        if p["net"] and re.search(p["net"], (net.get("net") or "") + " " + (net.get("org") or ""), re.I):
            return p
        for ip in st.get("ips") or []:
            try:
                if any(ipaddress.ip_address(ip) in ipaddress.ip_network(n) for n in p.get("ips") or []):
                    return p
            except ValueError:
                pass
    return None

# сервисы на сайте
SERVICES = [
    ("Яндекс Метрика", r"mc\.yandex\.(?:ru|com)/(?:metrika|watch)|\bym\(\d+"),
    ("Google Analytics", r"google-analytics\.com|gtag\('config', *'(?:G|UA)-"),
    ("Google Tag Manager", r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]{4,}"),
    ("Top.Mail.ru", r"top-fwz1\.mail\.ru"),
    ("Пиксель VK", r"vk\.com/js/api/openapi|VK\.Retargeting|vk\.ru/rtrg"),
    ("JivoSite (онлайн-чат)", r"jivosite\.com|code\.jivo\.ru"),
    ("Битрикс24 (формы, чат, CRM)", r"bitrix24\.(?:ru|com|by|kz)/b\d+|b24-widget|cdn-ru\.bitrix24|crm/site_button"),
    ("amoCRM", r"amocrm\.(?:ru|com)"),
    ("Roistat (сквозная аналитика)", r"roistat"),
    ("Calltouch (коллтрекинг)", r"calltouch"),
    ("CoMagic / UIS (коллтрекинг)", r"comagic|uiscom"),
    ("Callibri (коллтрекинг)", r"callibri"),
    ("Envybox (виджеты обратного звонка)", r"envybox|envycrm"),
    ("Marquiz (квизы)", r"marquiz"),
    ("Talk-Me (онлайн-чат)", r"talk-me\.ru"),
    ("Carrot quest", r"carrotquest"),
    ("Яндекс Карты", r"api-maps\.yandex\.ru|yandex\.ru/map-widget"),
    ("Google Карты", r"maps\.googleapis\.com|google\.com/maps/embed"),
    ("reCAPTCHA (Google)", r"google\.com/recaptcha|recaptcha/api\.js"),
    ("SmartCaptcha (Яндекс)", r"smartcaptcha"),
    ("hCaptcha", r"hcaptcha\.com"),
    ("Flocktory", r"flocktory"),
    ("Гудок (виджеты звонка)", r"gudok\.tel"),
    ("CloudPayments (оплата)", r"cloudpayments"),
    ("ЮKassa (оплата)", r"yookassa|yoomoney"),
    ("RetailCRM", r"retailcrm"),
    ("Mindbox", r"mindbox"),
    ("Diginetica (поиск по сайту)", r"diginetica"),
    ("Яндекс Бизнес / виджет отзывов", r"yandex\.ru/sprav/widget"),
]

# провайдеры: слово в названии сети, обратном имени IP, DNS-серверах, почтовых серверах → название
PROVIDERS = [
    (r"timeweb|inoventica", "Timeweb"), (r"cloud\.ru|sbercloud", "Cloud.ru (Сбер)"),
    (r"regtime|webnames", "Webnames (Регтайм)"), (r"\br01\b", "R01"),(r"beget", "Beget"), (r"reg\.ru|regru|reg-ru|\bREGRU", "REG.RU"),
    (r"sprinthost", "Sprinthost"), (r"selectel", "Selectel"), (r"yandex.?cloud|yandexcloud", "Яндекс Облако"),
    (r"yandex", "Яндекс"), (r"mcs\.mail\.ru|vk.?cloud|vkcs", "VK Cloud"), (r"mail\.ru|\bVK\b|vk\.com|\bvkontakte", "VK (Mail.ru)"),
    (r"masterhost", "Masterhost"), (r"hostland", "Hostland"), (r"nic\.ru|ru-center|rucenter", "RU-CENTER (nic.ru)"),
    (r"\bjino\b", "Jino"), (r"firstvds|first-vds|ispsystem", "FirstVDS"), (r"ruvds", "RuVDS"), (r"aeza", "Aeza"),
    (r"netangels", "NetAngels"), (r"spaceweb|sweb\.ru", "SpaceWeb"), (r"smartape", "SmartApe"), (r"agava", "Агава"),
    (r"1gb\.ru", "1Gb.ru"), (r"majordomo", "Majordomo"), (r"serverspace", "Serverspace"), (r"rusonyx", "Rusonyx"),
    (r"dataline", "DataLine"), (r"cloud4y", "Cloud4Y"), (r"macloud|mclouds", "MClouds"), (r"ihc\.ru|\bIHC\b", "IHC"),
    (r"hostinger", "Hostinger"), (r"hetzner", "Hetzner"), (r"\bovh", "OVH"), (r"digitalocean", "DigitalOcean"),
    (r"contabo", "Contabo"), (r"linode", "Linode (Akamai)"), (r"vultr|choopa", "Vultr"),
    (r"amazon|\baws\b|awsdns", "Amazon Web Services"), (r"google", "Google Cloud"), (r"microsoft|azure|outlook", "Microsoft"),
    (r"cloudflare", "Cloudflare"), (r"ddos-guard", "DDoS-Guard"), (r"qrator", "Qrator"), (r"stormwall", "StormWall"),
    (r"ngenix", "NGENIX"), (r"servicepipe", "Servicepipe"), (r"variti", "Variti"), (r"tilda", "Tilda"), (r"\bwix", "Wix"),
    (r"rostelecom|rtcomm", "Ростелеком"), (r"\bmts\b|mtsru", "МТС"), (r"megafon", "МегаФон"),
    (r"beeline|vimpelcom", "Билайн"), (r"hoster\.by", "hoster.by"), (r"\bps\.kz|pskz", "PS.kz"), (r"ucoz|ukit", "uCoz / uKit"),
    (r"nethouse", "Nethouse"), (r"bitrix", "Битрикс24"), (r"fozzy", "Fozzy"), (r"hostiq", "HostiQ"),
]

MAIL = [(r"yandex", "Яндекс 360 (почта для домена)"), (r"mail\.ru|vk\.com|vkmail", "VK WorkSpace (почта Mail.ru)"),
        (r"google|googlemail", "Google Workspace"), (r"outlook|microsoft", "Microsoft 365"), (r"zoho", "Zoho Mail")]

# зоны, у которых сведения о домене отдаёт whois.tcinet.ru (у них нет RDAP)
TCINET = ("ru", "su", "xn--p1ai")
# вторые уровни, которые продаются как отдельные зоны: name.msk.ru, name.com.ua…
SLD = {"com", "net", "org", "msk", "spb", "co", "ac", "gov", "edu", "nov", "kiev", "in", "or", "pp", "nsk"}


def provider_name(*texts):
    for t in texts:
        if not t:
            continue
        for rx, name in PROVIDERS:
            if re.search(rx, t, re.I):
                return name
    return ""


def base_domain(host):
    parts = host.lower().rstrip(".").split(".")
    if len(parts) >= 3 and parts[-2] in SLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_public(ip):
    try:
        a = ipaddress.ip_address(ip)
        return not (a.is_private or a.is_loopback or a.is_reserved or a.is_link_local)
    except ValueError:
        return False


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "ClaylerSEO", "Accept": "application/json",
                                               **(headers or {})})
    with sysproxy.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _ssl_ctx(verify=True):
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ---------- главная страница: заголовки, cookie, HTML (редиректы проходим сами, вход на закрытый сайт — только этому хосту)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def fetch_home(url):
    try:
        from .site_auth import headers_for
        auth = headers_for(url) or {}
    except Exception:
        auth = {}
    out = {"hops": []}
    for verify in (True, False):
        opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=_ssl_ctx(verify)))
        cur = url
        try:
            for _ in range(8):
                host = (urllib.parse.urlsplit(cur).hostname or "").lower()
                h = {"User-Agent": UA_PRESETS["chrome"], "Accept": "text/html,*/*;q=0.8",
                     "Accept-Encoding": "gzip, deflate", **auth.get(host, {})}
                try:
                    r = opener.open(urllib.request.Request(cur, headers=h), timeout=TIMEOUT)
                except urllib.error.HTTPError as e:
                    r = e
                status = r.status if hasattr(r, "status") else r.code
                hdrs = {}
                for k, v in r.headers.items():
                    hdrs[k.lower()] = (hdrs[k.lower()] + ", " + v) if k.lower() in hdrs else v
                cookies = [c.split("=", 1)[0].strip() for c in (r.headers.get_all("Set-Cookie") or [])]
                out["hops"].append({"url": cur, "status": status, "headers": hdrs, "cookies": cookies})
                if status in (301, 302, 303, 307, 308) and hdrs.get("location"):
                    cur = urllib.parse.urljoin(cur, hdrs["location"])
                    continue
                body = r.read(3_000_000)
                out.update(url=cur, status=status, headers=hdrs,
                           html=_decompress(body, hdrs.get("content-encoding", "")).decode("utf-8", "replace"))
                if not verify:
                    out["ssl_bad"] = True
                return out
        except Exception as e:
            if verify and isinstance(getattr(e, "reason", e), ssl.SSLError):
                out["hops"] = []
                continue  # сертификат не прошёл проверку — смотрим сайт без проверки, как обход
            out["error"] = _classify(e)
            return out
    return out


# ---------- DNS через DNS-over-HTTPS (в Python нет запросов NS и MX без сторонних библиотек)
def dns(name, rtype):
    for url in (f"https://dns.google/resolve?name={urllib.parse.quote(name)}&type={rtype}",
                f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(name)}&type={rtype}"):
        try:
            d = _get_json(url, {"Accept": "application/dns-json"})
            want = {"A": 1, "NS": 2, "MX": 15, "AAAA": 28}[rtype]
            return [a["data"].rstrip(".") for a in d.get("Answer") or [] if a.get("type") == want]
        except Exception:
            continue
    return None


# ---------- сеть по IP: кому принадлежит адрес
def ip_info(ip):
    info = {"ip": ip}
    try:
        info["rdns"] = socket.gethostbyaddr(ip)[0]
    except Exception:
        pass
    try:
        d = _get_json(f"https://stat.ripe.net/data/prefix-overview/data.json?resource={ip}")["data"]
        if d.get("asns"):
            info["asn"] = d["asns"][0].get("asn")
            info["holder"] = d["asns"][0].get("holder", "")
        info["prefix"] = d.get("resource", "")
    except Exception as e:
        info["error"] = "RIPEstat: " + str(e)[:80]
    try:
        d = _get_json(f"https://rdap.org/ip/{ip}")
        info["net"] = d.get("name", "")
        for ent in d.get("entities") or []:
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if item[0] == "fn" and item[3]:
                    info.setdefault("org", item[3])
        info["country"] = d.get("country", "")
    except Exception:
        pass
    return info


# ---------- домен: регистратор, дата регистрации и окончания
def _whois(server, query):
    with socket.create_connection((server, 43), timeout=TIMEOUT) as s:
        s.sendall((query + "\r\n").encode("utf-8"))
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    return data.decode("utf-8", "replace")


def _date(s):
    s = (s or "").strip()
    m = re.match(r"(\d{4})[-.](\d{2})[-.](\d{2})", s) or re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    if not m:
        return ""
    y, mo, d = m.groups() if len(m.group(1)) == 4 else (m.group(3), m.group(2), m.group(1))
    return f"{y}-{mo}-{d}"


def _parse_whois(text):
    out = {}
    keys = {"registrar": ["registrar", "sponsoring registrar", "registrar name"],
            "created": ["created", "creation date", "registered on", "registration time", "registered"],
            "expires": ["paid-till", "registry expiry date", "registrar registration expiration date", "expiration date",
                        "expiry date", "expires on", "expire", "expires"],
            "free": ["free-date"]}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        for field_, names in keys.items():
            if k in names and v and field_ not in out:
                out[field_] = v if field_ == "registrar" else _date(v)
        if k in ("nserver", "name server") and v:
            out.setdefault("ns", []).append(v.split()[0].lower().rstrip("."))
    return out


def domain_info(domain):
    tld = domain.rsplit(".", 1)[-1]
    info = {"domain": domain}
    try:
        if tld in TCINET:
            info.update(_parse_whois(_whois("whois.tcinet.ru", domain)))
            info["source"] = "whois.tcinet.ru"
        else:
            try:
                d = _get_json(f"https://rdap.org/domain/{domain}")
                for ev in d.get("events") or []:
                    if ev.get("eventAction") == "registration":
                        info["created"] = _date(ev.get("eventDate"))
                    if ev.get("eventAction") == "expiration":
                        info["expires"] = _date(ev.get("eventDate"))
                for ent in d.get("entities") or []:
                    if "registrar" in (ent.get("roles") or []):
                        for item in (ent.get("vcardArray") or [None, []])[1]:
                            if item[0] == "fn":
                                info["registrar"] = item[3]
                info["source"] = "RDAP"
            except Exception:
                ref = re.search(r"whois:\s*(\S+)", _whois("whois.iana.org", tld))
                if ref:
                    info.update(_parse_whois(_whois(ref.group(1), domain)))
                    info["source"] = ref.group(1)
    except Exception as e:
        info["error"] = str(e)[:120]
    return info


# ---------- SSL-сертификат
def cert_info(host):
    def fields(c):
        iss = dict(x[0] for x in c.get("issuer", ()))
        exp = dt.datetime.strptime(c["notAfter"], "%b %d %H:%M:%S %Y %Z").date().isoformat() if c.get("notAfter") else ""
        return {"issuer": iss.get("organizationName", "") or iss.get("commonName", ""), "issuer_cn": iss.get("commonName", ""),
                "expires": exp}
    try:
        with socket.create_connection((host, 443), timeout=TIMEOUT) as s:
            with _ssl_ctx(True).wrap_socket(s, server_hostname=host) as t:
                return fields(t.getpeercert())
    except ssl.SSLError as e:
        bad = str(e)[:120]
    except Exception as e:
        return {"error": str(e)[:120]}
    try:  # сертификат не прошёл проверку — всё равно узнаём, кем выдан и до какого числа
        with socket.create_connection((host, 443), timeout=TIMEOUT) as s:
            with _ssl_ctx(False).wrap_socket(s, server_hostname=host) as t:
                der = t.getpeercert(binary_form=True)
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
            f.write(ssl.DER_cert_to_PEM_cert(der))
        try:
            c = ssl._ssl._test_decode_cert(f.name)
        finally:
            os.remove(f.name)
        return {**fields(c), "bad": bad}
    except Exception:
        return {"bad": bad}


# ---------- что видно в HTML, заголовках, cookie и адресах файлов
def _hits(patterns, text):
    return [p for p in patterns if re.search(p, text, re.I)]


def _hdr(rules, headers):
    return [f"{k}: {headers[k][:60]}" for k, rx in rules if k in headers and re.search(rx, headers[k], re.I)]


def _ck(rules, cookies):
    return [c for c in cookies for rx in rules if re.search(rx, c, re.I)]


def _version(name, html, headers):
    gen = generator(html)
    if gen:
        m = re.search(r"(?:wordpress|joomla!?|drupal|ghost|prestashop|modx\w*)\D{0,20}(\d+(?:\.\d+){0,2})", gen, re.I)
        if m and name.split()[0].lower()[:5] in gen.lower():
            return m.group(1), "мета-тег generator"
    if name == "WordPress":
        vers = re.findall(r"wp-(?:includes|emoji)[^\"'>]*?\?ver=(\d+\.\d+(?:\.\d+)?)", html)
        if vers:
            v = max(set(vers), key=vers.count)
            return v, "номер версии в адресах файлов /wp-includes/"
    return "", ""


def generator(html):
    m = re.search(r"<meta[^>]+name=[\"']generator[\"'][^>]*content=[\"']([^\"']+)", html, re.I) or \
        re.search(r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*name=[\"']generator", html, re.I)
    return m.group(1).strip()[:100] if m else ""


def site_paths(store, limit=20000, host=""):
    """Адреса скриптов, стилей, картинок и страниц из базы проверки — запасной источник, если главная не открылась.
    host — только адреса самого сайта: картинки с чужих сайтов (/wp-content/ чужого блога) о движке не говорят."""
    out = []
    for sql in ("SELECT DISTINCT src FROM resources LIMIT ?", "SELECT DISTINCT src FROM images LIMIT ?",
                "SELECT url FROM urls WHERE internal=1 LIMIT ?"):
        try:
            out += [r[0] for r in store.db.execute(sql, (limit,)) if r[0]]
        except Exception:
            pass
    if host:
        own = host[4:] if host.startswith("www.") else host
        out = [u for u in out if not (h := (urllib.parse.urlsplit(u).hostname or "").lower())
               or h == own or h.endswith("." + own)]
    return "\n".join(out)


def recheck_paths(st, store):
    """Старые проверки: движок мог быть «узнан» по картинкам с чужих сайтов. Если это был единственный признак,
    а по адресам самого сайта его нет — убираем. Без интернета, только по базе проверки. True — данные изменились."""
    if st.get("paths_own") or not st.get("engines"):
        return False
    paths = site_paths(store, host=st.get("host") or "")
    rx = {name: rx_path for name, _, _, rx_path, _, _ in ENGINES}
    only_paths = lambda e: e.get("how", "").split(";")[0] == "адреса файлов и страниц сайта"
    st["engines"] = [e for e in st["engines"] if not only_paths(e) or _hits(rx.get(e["name"]) or [], paths)]
    st["paths_own"] = True
    return True


def detect(start, store=None, log=print):
    sp = urllib.parse.urlsplit(start)
    host = (sp.hostname or "").lower()
    is_ip = re.fullmatch(r"[\d.]+|[0-9a-f:]+", host or "x") is not None
    out = {"checked_at": dt.date.today().isoformat(), "host": host}
    with ThreadPoolExecutor(6) as ex:
        f_home = ex.submit(fetch_home, start)
        dom = base_domain(host) if host and not is_ip and "." in host else ""
        f_ns = ex.submit(dns, dom, "NS") if dom else None
        f_mx = ex.submit(dns, dom, "MX") if dom else None
        f_dom = ex.submit(domain_info, dom) if dom else None
        f_cert = ex.submit(cert_info, host) if sp.scheme == "https" and not is_ip else None
        try:
            ips = sorted({a[4][0] for a in socket.getaddrinfo(host, None, socket.AF_INET)}) if host else []
        except Exception:
            ips = []
        out["ips"] = ips
        f_ip = ex.submit(ip_info, ips[0]) if ips and _is_public(ips[0]) else None
        home = f_home.result()
        out["ns"] = f_ns.result() if f_ns else None
        out["mx"] = f_mx.result() if f_mx else None
        out["domain"] = f_dom.result() if f_dom else None
        out["cert"] = f_cert.result() if f_cert else None
        out["net"] = f_ip.result() if f_ip else None
    if out["ns"] is None and out.get("domain") and out["domain"].get("ns"):
        out["ns"] = out["domain"]["ns"]
    # если главная после редиректов ушла на другой хост — сертификат и IP смотрим всё равно у адреса проверки
    html = home.get("html") or ""
    headers = home.get("headers") or {}
    cookies = [c for h in home.get("hops") or [] for c in h["cookies"]]
    all_headers = {}
    for h in home.get("hops") or []:
        all_headers.update(h["headers"])
    paths = site_paths(store, host=host) if store is not None else ""
    out["home"] = {"url": home.get("url", start), "status": home.get("status"), "error": home.get("error", ""),
                   "generator": generator(html), "server": all_headers.get("server", ""),
                   "powered": all_headers.get("x-powered-by", ""), "html_size": len(html)}

    engines = []
    for name, kind, rx_html, rx_path, rx_hdr, rx_ck in ENGINES:
        why = []
        if h := _hits(rx_html, html):
            why.append("код главной страницы")
        if rx_path and (h2 := _hits(rx_path, paths)):
            why.append("адреса файлов и страниц сайта")
        if h := _hdr(rx_hdr, all_headers):
            why.append("заголовок ответа " + h[0].split(":")[0])
        if h := _ck(rx_ck, cookies):
            why.append("cookie " + h[0])
        gen = out["home"]["generator"]
        if gen and name.split()[0].split("(")[0].lower().strip(".")[:5] in gen.lower():
            why.append("мета-тег generator")
        # слабые признаки (одно слово в HTML) не считаем, если нет второго подтверждения
        weak = why == ["код главной страницы"] and all(len(p) < 10 and "/" not in p for p in _hits(rx_html, html))
        if why and not weak:
            ver, ver_how = _version(name, html, all_headers)
            engines.append({"name": name, "kind": kind, "version": ver, "how": ", ".join(why) +
                            (f"; версия - {ver_how}" if ver_how else ""), "score": len(why)})
    engines.sort(key=lambda e: -e["score"])
    # Битрикс24 в облаке — это тоже Битрикс: показываем одну строку
    if any(e["name"].startswith("Битрикс24") for e in engines):
        engines = [e for e in engines if e["name"] != "1С-Битрикс"]
    if re.search(r"bitrix24\.(?:site|shop|ru)$|b24site", host):
        engines = [e for e in engines if e["name"] != "1С-Битрикс"] or engines
    out["engines"] = engines[:3]
    out["paths_own"] = True

    tech = []
    for name, rx_html, rx_hdr, rx_ck in TECH:
        why = (["код главной"] if _hits(rx_html, html) else []) + _hdr(rx_hdr, all_headers) + _ck(rx_ck, cookies)
        if why:
            tech.append(name)
    if "Laravel" not in tech and "XSRF-TOKEN" in cookies and any(c.endswith("_session") for c in cookies):
        tech.append("Laravel")
    if not any(e["name"] == "WordPress" for e in engines):
        tech = [t for t in tech if "WordPress" not in t]
    if not any(e["name"] == "1С-Битрикс" for e in engines):
        tech = [t for t in tech if "Битрикс" not in t]
    m = re.search(r"jquery[.-]?(\d+\.\d+(?:\.\d+)?)(?:\.min)?\.js|jquery(?:\.min)?\.js\?ver=(\d+\.\d+(?:\.\d+)?)", html, re.I)
    if m:
        tech.append("jQuery " + (m.group(1) or m.group(2)))
    elif re.search(r"jquery(?:\.min)?\.js", html, re.I):
        tech.append("jQuery")
    pw = out["home"]["powered"]
    if m := re.search(r"PHP/?\s*([\d.]+)?", pw or "", re.I):
        tech.insert(0, "PHP " + (m.group(1) or "").strip())
    elif re.search(r"\.php\b", html + paths) or any(re.match(r"^PHPSESSID$", c) for c in cookies):
        tech.insert(0, "PHP")
    out["tech"] = list(dict.fromkeys(t.strip() for t in tech))

    shields = []
    holder = " ".join(filter(None, [(out["net"] or {}).get("holder", ""), (out["net"] or {}).get("net", ""),
                                    (out["net"] or {}).get("org", "")]))
    for name, rx_hdr, rx_ck, rx_net in SHIELDS:
        why = _hdr(rx_hdr, all_headers) + _ck(rx_ck, cookies)
        if holder and re.search(rx_net, holder, re.I):
            why.append("IP-адрес принадлежит " + name)
        if why:
            shields.append({"name": name, "how": "; ".join(why[:2])})
    out["shields"] = shields
    out["services"] = [n for n, rx in SERVICES if re.search(rx, html, re.I)]
    out["platform_headers"] = {k: all_headers[k][:60] for p in PLATFORMS for k, _ in p.get("hdr", [])
                               if k in all_headers}

    net = out["net"] or {}
    # имя сервера и название блока адресов важнее владельца сети: у ils-school сеть Ростелекома, а сервер — Jino
    hp = provider_name(net.get("rdns"), net.get("net"), net.get("holder"), net.get("org"))
    out["hosting"] = hp
    out["dns_provider"] = provider_name(*(out["ns"] or []))
    if out["mx"] is not None:
        out["mx"] = [x.split()[-1] for x in out["mx"]]  # «10 mx.yandex.net» → без приоритета
    mx = out["mx"] or []
    out["mail"] = next((name for rx, name in MAIL if any(re.search(rx, x, re.I) for x in mx)), "") or \
        provider_name(*mx) or (f"свой почтовый сервер ({mx[0]})" if mx and dom and mx[0].endswith(dom) else "")
    d = out.get("domain") or {}
    if d.get("registrar"):
        d["registrar"] = provider_name(d["registrar"]) or d["registrar"]
    return out


def ensure(store, log=print):
    """Определить один раз на проверку (при сборке отчёта)."""
    if st := store.get_meta("site_tech", None):
        if isinstance(st, dict) and recheck_paths(st, store):
            store.set_meta("site_tech", st)
            store.commit()
        return
    start = store.get_meta("start", "")
    if not start:
        return
    log("Определяю, на чём сделан сайт и где он размещён...")
    try:
        st = detect(start, store, log)
    except Exception as e:
        st = {"error": str(e)[:150], "checked_at": dt.date.today().isoformat()}
    store.set_meta("site_tech", st)
    store.commit()


# ---------- вывод
def _days(iso):
    try:
        return (dt.date.fromisoformat(iso) - dt.date.today()).days
    except Exception:
        return None


def _ru_date(iso):
    try:
        d = dt.date.fromisoformat(iso)
        return d.strftime("%d.%m.%Y")
    except Exception:
        return iso or ""


def _left(n):
    if n is None:
        return ""
    if n < 0:
        return "срок уже прошёл"
    w = "день" if n % 10 == 1 and n % 100 != 11 else ("дня" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "дней")
    return f"осталось {n} {w}"


def rows(st):
    """[(что, значение, пояснение, уровень)] — уровень: "" / "warn" / "crit". Пусто, если данных нет."""
    if not st or (st.get("error") and not st.get("home")):
        return []
    out = []
    home = st.get("home") or {}
    eng = st.get("engines") or []
    kinds = {"cms": "движок", "builder": "конструктор сайтов", "shop": "платформа интернет-магазина"}
    if eng:
        e = eng[0]
        val = e["name"] + (f" {e['version']}" if e.get("version") else "")
        # другие движки — только если их признаки так же весомы, как у главного: иначе это шум и снижает доверие
        rest = [x for x in eng[1:] if x.get("score", 0) >= e.get("score", 0)]
        extra = f" Ещё есть признаки: {', '.join(x['name'] for x in rest)}." if rest else ""
        out.append(("Движок сайта", val, f"{kinds.get(e['kind'], '').capitalize()}. Как узнали: {e['how']}.{extra}", ""))
    elif home.get("error") or (home.get("status") or 0) >= 400:
        out.append(("Движок сайта", "не определён", "Главная страница не открылась: "
                    + (home.get("error") or f"сервер ответил {home.get('status')}") + ".", ""))
    else:
        g = home.get("generator")
        fw = next((t for t in st.get("tech") or [] if t.split()[0] in (
            "Laravel", "Django", "Ruby", "ASP.NET", "Next.js", "Nuxt", "Gatsby", "Java")), "")
        pf0 = platform(st)
        static = pf0 and not pf0.get("engine") and not fw
        out.append(("Движок сайта", g or (f"свой, на {fw}" if fw else "нет, готовые HTML-файлы" if static else "не определён"),
                    "Из мета-тега generator." if g else f"Сайт лежит на {pf0['name']} - это хостинг для готовых "
                    "страниц, движка с панелью управления там нет: правки вносят в файлы сайта." if static else (
                        f"Готового движка нет: сайт написан программистами на фреймворке {fw}, правки делает только "
                        "разработчик." if fw else "Явных признаков известных движков и конструкторов нет: возможно, "
                        "сайт написан с нуля или на редком движке."), ""))
    if st.get("tech"):
        out.append(("Технологии", ", ".join(st["tech"]), "Языки программирования, фреймворки, плагины и библиотеки, "
                    "которые видны в коде главной страницы и в заголовках ответа.", ""))
    if home.get("server"):
        out.append(("Веб-сервер", home["server"], "Заголовок Server в ответе сайта." + (
            " Сервер показывает свою точную версию - лучше её скрыть (server_tokens off в nginx, ServerTokens Prod "
            "в Apache): по версии проще подобрать известные уязвимости." if re.search(r"/\d", home["server"]) else ""), ""))
    if home.get("powered") and not re.match(r"PHP", home["powered"], re.I):
        out.append(("X-Powered-By", home["powered"], "Заголовок ответа сайта.", ""))
    sh = st.get("shields") or []
    pf = platform(st)
    own_cdn = pf and sh and all(s["name"] == pf.get("cdn") for s in sh)  # сеть самой платформы, не отдельная защита
    if sh or home.get("status"):  # сайт не ответил — про защиту сказать нечего
        out.append(("Защита и CDN", ", ".join(s["name"] for s in sh) if sh else "не видно",
                ("Как узнали: " + "; ".join(f"{s['name']} - {s['how']}" for s in sh) + (
                    f". Это сеть, через которую {pf['name']} отдаёт все свои сайты: отдельно её не подключали и не "
                    "настраивают." if own_cdn else ". Сайт отдаётся через сеть "
                    "защиты: посетители и роботы попадают сначала туда. Если защита начнёт показывать проверку «я не робот» "
                    "поисковым роботам, страницы выпадут из поиска - это стоит проверять в Вебмастере.")) if sh else
                "Сайт отвечает напрямую, без Cloudflare, DDoS-Guard и подобных сервисов.", ""))
    net = st.get("net") or {}
    ips = st.get("ips") or []
    if ips:
        hp = st.get("hosting") or ""
        holder = net.get("holder") or net.get("org") or ""
        val = hp or holder or "не определён"
        bits = []
        if net.get("asn"):
            bits.append(f"сеть AS{net['asn']} {holder}".strip())
        if net.get("net") and net.get("net") not in holder:
            bits.append(f"блок адресов {net['net']}")
        if net.get("rdns"):
            bits.append(f"имя сервера {net['rdns']}")
        if net.get("country"):
            bits.append(f"страна {net['country']}")
        note = f"IP {', '.join(ips[:3])}" + (f"; {'; '.join(bits)}" if bits else "") + "."
        if pf and not pf.get("engine"):
            val = pf["name"]
            note += f" Сайт размещён на {pf['name']}: сервером управляет платформа" + (
                ", поэтому заголовки ответа (кеширование, защита) задать нельзя." if pf["headers"] == "fixed" else
                f"; заголовки ответа задаются {pf['headers']}.")
        elif sh and any(s["name"].split()[0].lower() in (hp + holder).lower() for s in sh):
            val = f"скрыт за {sh[0]['name']}"
            note += (" IP-адрес принадлежит сервису защиты, настоящий хостинг он не показывает. Узнать его можно "
                     "в панели защиты или у разработчика.")
        elif not _is_public(ips[0]):
            val, note = "локальный адрес", f"IP {ips[0]} - сайт в локальной сети, хостинг не определяется."
        out.append(("Хостинг", val, note, ""))
    if st.get("ns"):
        dp = st.get("dns_provider")
        out.append(("DNS-серверы", dp or ", ".join(st["ns"][:2]), ", ".join(st["ns"][:4]) +
                    ". Где хранятся настройки домена: сюда идут, чтобы переключить сайт на другой сервер или "
                    "подтвердить права в Вебмастере.", ""))
    if st.get("mx") is not None and st.get("ns"):  # нет DNS-серверов — домена нет, о почте молчим
        out.append(("Почта домена", st.get("mail") or (", ".join(st["mx"][:2]) if st["mx"] else "не настроена"),
                    ("Почтовые серверы (MX): " + ", ".join(st["mx"][:3]) + ".") if st["mx"] else
                    "У домена нет почтовых серверов (MX) - письма на адреса @домена не дойдут.", "" if st["mx"] else "warn"))
    d = st.get("domain") or {}
    if d and (d.get("registrar") or d.get("expires") or d.get("created")):
        n = _days(d.get("expires"))
        lvl = "crit" if n is not None and n < S.DOMAIN_CRIT_DAYS else ("warn" if n is not None and n < S.DOMAIN_WARN_DAYS else "")
        val = d.get("domain", "")
        parts = []
        if d.get("registrar"):
            parts.append(f"регистратор {d['registrar']}")
        if d.get("created"):
            parts.append(f"зарегистрирован {_ru_date(d['created'])}")
        if d.get("expires"):
            parts.append(f"оплачен до {_ru_date(d['expires'])} ({_left(n)})")
        note = "; ".join(parts) + "."
        note = note[:1].upper() + note[1:]
        if lvl:
            note += " Продлите домен заранее: если он истечёт, сайт перестанет открываться и выпадет из поиска."
        out.append(("Домен", val, note, lvl))
    elif d.get("error"):
        out.append(("Домен", d.get("domain", ""), "Сведения о домене не получены: " + d["error"], ""))
    c = st.get("cert") or {}
    if c and (c.get("expires") or c.get("bad")):
        n = _days(c.get("expires"))
        lvl = "crit" if c.get("bad") or (n is not None and n < 7) else ("warn" if n is not None and n < 21 else "")
        iss = c.get("issuer") or "-"
        if c.get("issuer_cn") and c["issuer_cn"] != iss:
            iss += f" ({c['issuer_cn']})"
        note = (f"Выдан: {iss}; действует до {_ru_date(c['expires'])} ({_left(n)})." if c.get("expires") else "")
        if c.get("bad"):
            why = next((ru for k, ru in (("expired", "истёк срок действия"), ("mismatch", "выдан на другой домен"),
                                          ("self-signed", "самоподписанный, не от удостоверяющего центра"),
                                          ("local issuer", "на сервере не хватает промежуточного сертификата"))
                        if k in c["bad"]), c["bad"])
            note += f" Браузер не доверяет сертификату: {why}. Посетители видят предупреждение «Подключение не защищено»."
        elif lvl:
            note += " Сертификат скоро закончится - если он не продлевается сам, продлите его вручную."
        out.append(("SSL-сертификат", "есть" if not c.get("bad") else "с ошибкой", note.strip(), lvl))
    if st.get("services"):
        out.append(("Сервисы на сайте", ", ".join(st["services"]), "Счётчики, чаты, коллтрекинг, карты и другие "
                    "подключённые сервисы, найденные в коде главной страницы.", ""))
    return out


INTRO = ("Определено программой по главной странице, адресам файлов сайта и открытым бесплатным источникам "
         "(DNS, сведения о сети по IP, whois домена).")


def _country_tr(country, _e, flag):
    """Строка «Страна сайта»: по признакам с самого сайта и где стоит сервер (country.py)."""
    from . import country as C
    head, why = C.text(country, flag=flag)
    if not head:
        return ""
    srv = C.server_text((country or {}).get("server"))
    note = "; ".join(x for x in ((f"По сайту: {_e(why)}" if why else ""), _e(srv)) if x)
    return f'<tr><td style="width:9.5em">Страна сайта</td><td><b>{head}</b><br><span class="mut">{note}.</span></td></tr>'


def report_html(st, _e, cls="card", country=None):
    st = st or {}
    r = rows(st) if st else []
    ctr = _country_tr(country, _e, True)
    if not r and not ctr:
        return ""
    tr = ctr + "".join(f'<tr><td style="width:9.5em">{_e(a)}</td><td><b class="{lvl}">{_e(b)}</b><br><span class="mut">{_e(c)}</span></td></tr>'
                       for a, b, c, lvl in r)
    when = f' Данные на {_e(_ru_date(st.get("checked_at")))}.' if st.get("checked_at") else ""
    return (f'<div class="{cls} tech"><h3>На чём сделан сайт и где размещён</h3><p class="mut" style="margin:0 0 8px">'
            f'{INTRO}{when}</p><div class="tw" style="margin:0"><table class="rg">'
            f'<tbody>{tr}</tbody></table></div></div>')


def audit_html(st, _e, country=None):
    st = st or {}
    r = rows(st) if st else []
    ctr = _country_tr(country, _e, False)   # в аудите (PDF и Word) - без картинки флага
    if not r and not ctr:
        return ""
    tr = ctr + "".join(f'<tr><td style="width:9.5em">{_e(a)}</td><td><b class="{lvl}">{_e(b)}</b><br><span class="mut">{_e(c)}</span></td></tr>'
                       for a, b, c, lvl in r)
    when = f' Данные на {_e(_ru_date(st.get("checked_at")))}.' if st.get("checked_at") else ""
    return (f'<section class="pt"><h2>На чём сделан сайт и где размещён</h2><p class="mut">{INTRO}{when}</p>'
            f'<table class="rg"><tbody>{tr}</tbody></table></section>')
