"""Вход в Яндекс Вебмастер и Google Search Console без пароля (OAuth).

Как это работает: кнопка «Войти через Яндекс/Google» открывает страницу Яндекса или Google в браузере,
человек сам входит в свой аккаунт и нажимает «Разрешить». Яндекс/Google возвращают программе одноразовый код
(на адрес http://127.0.0.1:<порт>/oauth/<yandex|google> — это окно программы на этом же компьютере),
программа меняет его на ключ доступа (токен). Пароль программа не видит и не хранит.
Доступ только на чтение. «Отключить» отзывает ключ у Яндекса/Google и стирает его с компьютера.

Хранится в «доступы.json» в папке «данные» (в git не попадает). Ключи и секрет приложения зашифрованы
средствами Windows (DPAPI): расшифровать их может только эта учётная запись Windows на этом компьютере.
Чтобы кнопка заработала, пользователь один раз регистрирует своё приложение (client_id и секрет) —
пошаговая подсказка есть в окне программы (STEPS ниже).
"""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import jsonfile, paths

FILE = os.environ.get("CLAYLER_ACCOUNTS_FILE") or paths.data("доступы.json")

# Адреса Яндекса и Google. В тестах подменяются поддельным сервером (CLAYLER_OAUTH_TEST=http://127.0.0.1:порт).
_T = os.environ.get("CLAYLER_OAUTH_TEST")
PROVIDERS = {
    "yandex": {
        "name": "Яндекс Вебмастер и Метрика",
        "auth": (_T or "https://oauth.yandex.ru") + "/authorize",
        "token": (_T or "https://oauth.yandex.ru") + "/token",
        "revoke": (_T or "https://oauth.yandex.ru") + "/revoke_token",
        "scope": "",  # права задаются при регистрации приложения на oauth.yandex.ru
        "api": (_T or "https://api.webmaster.yandex.net") + "/v4",
        "metrika": _T or "https://api-metrika.yandex.net",
    },
    "google": {
        "name": "Google Search Console",
        "auth": (_T or "https://accounts.google.com") + "/o/oauth2/v2/auth",
        "token": (_T or "https://oauth2.googleapis.com") + "/token",
        "revoke": (_T or "https://oauth2.googleapis.com") + "/revoke",
        "scope": "openid email https://www.googleapis.com/auth/webmasters.readonly",
        "api": (_T or "https://www.googleapis.com") + "/webmasters/v3",
        "inspect": (_T or "https://searchconsole.googleapis.com") + "/v1/urlInspection/index:inspect",
    },
}

# Подсказка в окне: как один раз зарегистрировать приложение. {redirect} — адрес возврата этой копии программы.
STEPS = {
    "yandex": [
        "Откройте https://oauth.yandex.ru/client/new и войдите в свой Яндекс (тот, куда клиенты делегируют сайты).",
        "На вопрос «Какое приложение хотите создать?» выберите «Для авторизации пользователей».",
        "Шаг 1: название «Clayler SEO» (его увидят клиенты), иконка - файл иконка.png из папки «данные», ваша почта.",
        "Шаг 2: отметьте «Веб-сервисы», в Redirect URI вставьте: {redirect} (Suggest Hostname - пусто).",
        "Шаг 3: в «Основных» ничего не отмечайте. В «Дополнительные» напечатайте webmaster и выберите оба: "
        "webmaster:hostinfo и webmaster:verify (без второго Яндекс не отдаёт индексацию и запросы), "
        "потом metrika и выберите metrika:read.",
        "Шаг 4: «Создать». Скопируйте ClientID и Client secret сюда и нажмите «Сохранить».",
    ],
    "google": [
        "Откройте https://console.cloud.google.com/ и создайте проект (или возьмите готовый, например «My Project»).",
        "В поиске сверху напечатайте Google Search Console API, откройте и нажмите Enable.",
        "В поиске откройте Google Auth Platform → Get started: App name «Clayler SEO», ваша почта; Audience - "
        "External; Contact - ваша почта; согласие → Create. Затем слева Audience → Publish app → Confirm (статус "
        "«In production»). Если оставить тестовый режим, Google сам отключает вход через 7 дней. При входе Google "
        "предупредит, что приложение не проверено: нажмите «Дополнительно» → «Перейти на страницу Clayler SEO» - "
        "это ваше же приложение. На следующей странице отметьте галочку доступа к Search Console (или «Выбрать всё»).",
        "Слева Clients → Create client → Application type: Desktop app → Create. Адрес возврата вписывать не нужно.",
        "Скопируйте Client ID и Client secret сюда и нажмите «Сохранить».",
    ],
}

_lock = threading.Lock()
_pending = {}  # state → {"provider", "verifier", "redirect", "t"}


# ---------- шифрование средствами Windows ----------

def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    inp, out = BLOB(len(data), buf), BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):  # 0x1 — без окон
        raise OSError("Windows не смогла " + ("зашифровать" if protect else "расшифровать") + " ключ доступа")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def seal(text):
    raw = text.encode("utf-8")
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
    return "plain:" + base64.b64encode(raw).decode()  # не Windows — без шифрования (файл только у пользователя)


def unseal(text):
    kind, _, data = (text or "").partition(":")
    raw = base64.b64decode(data)
    return (_dpapi(raw, False) if kind == "dpapi" else raw).decode("utf-8")


# ---------- файл доступов ----------

def _load():
    return jsonfile.load(FILE)


def _save(data):
    jsonfile.save(FILE, data, indent=1)


def _get(provider):
    return _load().get(provider) or {}


def _load_for_write():
    """Файл доступов перед записью: есть, но не читается - не считаем его пустым, иначе запись одного входа стёрла бы
    остальные (Вебмастер, Метрику, Google). Занят другой программой - 5 попыток за полсекунды, потом ошибка (ничего
    не перезаписываем). Испорчен (не JSON) - переименовать рядом в «доступы.json.испорчен-<время>» и начать с
    пустого: входы в нём и так уже не читаются, а без этого нельзя было бы даже войти заново."""
    for _ in range(5):
        if not os.path.exists(FILE):
            return {}
        try:
            with open(FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            broken = True
        except ValueError:
            broken = True
        except OSError:
            broken = False
        time.sleep(0.1)
    if broken:
        try:
            os.replace(FILE, f"{FILE}.испорчен-{time.strftime('%Y%m%d-%H%M%S')}")
            return {}
        except OSError:
            pass
    raise RuntimeError("Файл доступов не читается (занят другой программой) - ничего не перезаписываю, "
                       "чтобы не потерять другие входы. Повторите через минуту.")


def _put(provider, **fields):
    with _lock:
        data = _load_for_write()
        cur = data.get(provider) or {}
        for k, v in fields.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        data[provider] = cur
        _save(data)


def redirect_uri(provider, port):
    return f"http://127.0.0.1:{port}/oauth/{provider}"


# ключ отозван или истёк (у Google в тестовом режиме приложения - через 7 дней): нужен вход заново
EXPIRED = re.compile(r"invalid_grant|expired|revoked|unauthori[sz]ed|\b401\b", re.I)


# Google выдал ключ без Search Console: при входе не отмечена галочка доступа (Google спрашивает по каждому доступу)
NO_SCOPE = re.compile(r"insufficient authentication scopes|insufficientPermissions|ACCESS_TOKEN_SCOPE_INSUFFICIENT"
                      r"|scope_missing")
def fail_state(err):
    """Почему не загрузились запросы (для семантики): no_scope - у входа Google нет галочки Search Console,
    no_link - нет связи (VPN, обрыв), error - другое."""
    from .plain_errors import _NET
    s = str(err)
    return "no_scope" if NO_SCOPE.search(s) else "no_link" if _NET.search(s) else "error"


SCOPE_TEXT = ("Google дал доступ не ко всему: при входе не отмечена галочка Search Console. Нажмите «Подключить "
              "заново» и на странице Google отметьте галочку «Просмотр данных Search Console» (или «Выбрать всё»).")


def relogin(provider, err):
    """Нужно войти заново: «вход истёк», «нет доступа к Search Console» или пусто."""
    if NO_SCOPE.search(err or ""):
        return "нет доступа к Search Console"
    return "вход истёк" if EXPIRED.search(err or "") else ""


def plain_error(provider, err):
    """Ошибка входа для окна простыми словами (техническое сообщение - в «Журнале»)."""
    if not err:
        return ""
    if NO_SCOPE.search(err):
        return SCOPE_TEXT
    if EXPIRED.search(err):
        return ("Вход истёк. Нажмите «Подключить заново»." + (
            " Если вход слетает раз в неделю, приложение в Google Cloud в тестовом режиме: откройте Google Auth "
            "Platform → Audience и нажмите Publish app." if provider == "google" else ""))
    from .plain_errors import explain, _NET
    if _NET.search(err):   # «Сайт оборвал соединение… Бережно» - это про сайты, а здесь служба Яндекса или Google
        return ("Нет связи с " + ("Яндексом" if provider == "yandex" else "Google") + ": соединение не открылось "
                "или оборвалось. Обычно это VPN: включите или выключите его (в VPN можно пустить домен напрямую) "
                "и нажмите «Обновить список сайтов»")
    e = explain(err)
    return (e["title"] + ". " + e["todo"]).strip(". ") if e.get("todo") else e["title"]


def status(port):
    """Что показать в окне: для каждого сервиса — настроено ли приложение, подключён ли аккаунт."""
    out = {}
    for p, info in PROVIDERS.items():
        cur = _get(p)
        red = redirect_uri(p, port)
        out[p] = {
            "name": info["name"],
            "client_id": cur.get("client_id", ""),
            "has_app": bool(cur.get("client_id") and cur.get("secret")),
            "connected": bool(cur.get("token")),
            "account": cur.get("account", ""),
            "sites": cur.get("sites", []),
            "since": cur.get("since", ""),
            "relogin": relogin(p, cur.get("error")) if cur.get("token") else "",
            "expired": bool(cur.get("token") and relogin(p, cur.get("error"))),
            "error": plain_error(p, cur.get("error") or ""),
            "redirect": red,
            "steps": [s.replace("{redirect}", red) for s in STEPS[p]],
        }
    return out


def save_app(provider, client_id, secret):
    """Сохранить client_id и секрет приложения. Пустой секрет — оставить прежний."""
    if provider not in PROVIDERS:
        return "Нет такого сервиса."
    client_id = (client_id or "").strip()
    secret = (secret or "").strip()
    if not client_id:
        return "Вставьте ClientID."
    if not secret and not _get(provider).get("secret"):
        return "Вставьте Client secret."
    _put(provider, client_id=client_id, **({"secret": seal(secret)} if secret else {}))
    return ""


# ---------- вход ----------

def start(provider, port):
    """Адрес страницы Яндекса/Google, куда отправить человека. Возвращает (url, ошибка)."""
    if provider not in PROVIDERS:
        return None, "Нет такого сервиса."
    cur = _get(provider)
    if not cur.get("client_id"):
        return None, "Сначала впишите ClientID и Client secret (как получить - в подсказке ниже)."
    info = PROVIDERS[provider]
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    red = redirect_uri(provider, port)
    q = {"response_type": "code", "client_id": cur["client_id"], "redirect_uri": red, "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256"}
    if provider == "google":
        q.update(scope=info["scope"], access_type="offline", prompt="consent")
    else:
        q["force_confirm"] = "yes"
    with _lock:
        now = time.time()
        for s in [s for s, v in _pending.items() if now - v["t"] > 900]:
            del _pending[s]
        _pending[state] = {"provider": provider, "verifier": verifier, "redirect": red, "t": now}
    return info["auth"] + "?" + urllib.parse.urlencode(q), ""


def _urlopen(req, timeout):
    """Без VPN, но с его прокси в Windows - напрямую (sysproxy.py)."""
    from .sysproxy import urlopen
    return urlopen(req, timeout)


def _post(url, fields, headers=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers=headers or {})
    try:
        with _urlopen(req, 20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read() or b"{}")
        except ValueError:
            err = {}
        raise RuntimeError(err.get("error_description") or err.get("error") or f"ответ {e.code}")


def _api(provider, path, body=None):
    """Запрос к API Вебмастера или Search Console с текущим ключом (Google — с обновлением ключа).
    path — от адреса API (или полный адрес с https://), body — JSON для POST."""
    info = PROVIDERS[provider]
    token = access_token(provider)
    auth = ("OAuth " if provider == "yandex" else "Bearer ") + token
    headers = {"Authorization": auth, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    url = path if "://" in path else info["api"] + path
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with _urlopen(req, 30) as r:
            out = json.loads(r.read() or b"{}")
        # прошлая ошибка была сетевой (оборвалась связь, VPN): запрос прошёл - красное «ошибка» в «Подключениях»
        # больше не нужно. Раньше оно висело до ручного «Обновить список сайтов» (замечено 20.10.2026)
        old = _get(provider).get("error")
        if old and not relogin(provider, old):
            _put(provider, error=None)
        return out
    except urllib.error.HTTPError as e:
        body = " ".join(e.read()[:300].decode("utf-8", "replace").split())   # в одну строку: причина не теряется при обрезке
        if provider == "yandex" and "Required scope: COMMON" in body:
            raise RuntimeError("у приложения на oauth.yandex.ru не хватает доступа webmaster:verify - добавьте его "
                               "в приложении, потом в программе «Отключить» и «Войти через Яндекс» заново")
        raise RuntimeError(f"{info['name']} ответил {e.code}: {body}")


def finish(provider, params):
    """Яндекс/Google вернули человека в программу с кодом. Меняем код на ключ. Возвращает текст ошибки или ""."""
    if params.get("error"):
        return "Доступ не выдан: " + (params.get("error_description") or params["error"])
    with _lock:
        pend = _pending.pop(params.get("state") or "", None)
    if not pend or pend["provider"] != provider:
        return "Ссылка входа устарела. Нажмите «Войти» в окне программы ещё раз."
    cur = _get(provider)
    try:
        tok = _post(PROVIDERS[provider]["token"], {
            "grant_type": "authorization_code", "code": params.get("code") or "",
            "client_id": cur.get("client_id", ""), "client_secret": unseal(cur.get("secret")),
            "code_verifier": pend["verifier"], "redirect_uri": pend["redirect"]})
    except Exception as e:
        return "Не получилось получить ключ доступа: " + str(e)[:200]
    if not tok.get("access_token"):
        return "Яндекс/Google не выдали ключ доступа."
    account = ""
    if tok.get("id_token"):  # Google: почта аккаунта (получено напрямую от Google по HTTPS, подпись не проверяем)
        try:
            part = tok["id_token"].split(".")[1]
            account = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("email", "")
        except Exception:
            pass
    exp = time.time() + float(tok.get("expires_in") or 3600)
    _put(provider, token=seal(tok["access_token"]), expires=exp, account=account or None, error=None,
         since=time.strftime("%d.%m.%Y %H:%M"),
         **({"refresh": seal(tok["refresh_token"])} if tok.get("refresh_token") else {}))
    # Google спрашивает согласие по каждому доступу: без галочки Search Console ключ есть, а данных не будет
    if provider == "google" and tok.get("scope") and "webmasters" not in tok["scope"]:
        _put(provider, error="scope_missing")
        return SCOPE_TEXT.replace("Нажмите «Подключить заново»", "Нажмите в программе «Подключить заново»")
    refresh_sites(provider)
    return ""


def access_token(provider):
    """Действующий ключ. У Google ключ живёт час — обновляем по refresh-ключу. Яндекс выдаёт на год."""
    cur = _get(provider)
    if not cur.get("token"):
        raise RuntimeError(f"{PROVIDERS[provider]['name']} не подключён.")
    if time.time() < float(cur.get("expires") or 0) - 60 or not cur.get("refresh"):
        return unseal(cur["token"])
    tok = _post(PROVIDERS[provider]["token"], {
        "grant_type": "refresh_token", "refresh_token": unseal(cur["refresh"]),
        "client_id": cur.get("client_id", ""), "client_secret": unseal(cur.get("secret"))})
    _put(provider, token=seal(tok["access_token"]), expires=time.time() + float(tok.get("expires_in") or 3600),
         **({"refresh": seal(tok["refresh_token"])} if tok.get("refresh_token") else {}))
    return tok["access_token"]


def refresh_sites(provider):
    """Список сайтов, которые видит подключённый аккаунт. Пишется в файл доступов (для окна)."""
    try:
        if provider == "yandex":
            uid = _api("yandex", "/user")["user_id"]
            hosts = _api("yandex", f"/user/{uid}/hosts").get("hosts", [])
            sites = [h.get("unicode_host_url") or h.get("ascii_host_url") for h in hosts if h.get("verified")]
            _put(provider, user_id=uid, account=_get(provider).get("account") or f"пользователь {uid}")
        else:
            entries = _api("google", "/sites").get("siteEntry", [])
            sites = [e["siteUrl"] for e in entries if e.get("permissionLevel") != "siteUnverifiedUser"]
        _put(provider, sites=sorted(s for s in sites if s), error=None)
        return ""
    except Exception as e:
        _put(provider, error=str(e)[:300])
        return plain_error(provider, str(e)[:300])   # в окно - по-русски, оригинал остаётся в файле доступов


def disconnect(provider):
    """Отозвать ключ у Яндекса/Google и стереть его. Приложение (client_id) остаётся — войти можно снова."""
    if provider not in PROVIDERS:
        return "Нет такого сервиса."
    cur = _get(provider)
    if cur.get("token"):
        try:
            if provider == "yandex":
                _post(PROVIDERS[provider]["revoke"], {"access_token": unseal(cur["token"]),
                      "client_id": cur.get("client_id", ""), "client_secret": unseal(cur.get("secret"))})
            else:
                _post(PROVIDERS[provider]["revoke"], {"token": unseal(cur.get("refresh") or cur["token"])})
        except Exception:
            pass  # стираем в любом случае; ключ можно отозвать и вручную в аккаунте Яндекса/Google
    _put(provider, token=None, refresh=None, expires=None, account=None, sites=None, since=None, error=None,
         user_id=None)
    return ""
