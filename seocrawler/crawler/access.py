"""Сайт не открывается: понятная причина (access_check.py) в журнал, окно и отчёт.

- В начале обхода главная открывается один раз. Если не открылась (нет ответа или 401/403/429/503), программа
  выясняет причину по шагам: «соединение режут по дороге» (обрыв на шаге https - провайдер или защита сайта,
  через VPN проходит), «сайт не пускает программы» (браузеру Chrome отвечает, программе - нет) и т. д.
  Строка в журнал «Сайт не открывается: …» или «Сайт не пускает программы: …», в базе meta access.
- Сайт не пускает программы, а «Проверять как» не выбрано: дальше обход идёт как браузер Chrome (иначе отчёт
  был бы из одной ошибки 403); в отчёте это видно в строке «Сайт проверялся …».
- Сайт отвечает через раз (shaky.py) или упал посреди обхода (main_loop.site_is_down): причина выясняется один раз
  и дописывается к «Сайт перестал отвечать: …»."""
from .. import access_check
from ..fetcher import UA_PRESETS


class AccessMixin:
    def _diagnose(self):
        d = access_check.diagnose(self.start, ua=self.fetcher.user_agent, verify_ssl=self.cfg.verify_ssl,
                                  timeout=min(self.cfg.timeout, 15), headers=(self.auth or {}).get(self.root_host))
        self.store.set_meta("access", d)
        return d

    def check_access(self):
        """Перед шагом 1: открывается ли главная, и если нет - почему."""
        r = self.fetcher.fetch(self.start, read_body=False)
        if r.status and r.status < 400 or (r.status or 0) in (404, 410) or 500 <= (r.status or 0) < 503:
            return None   # открылась (или ответила обычной ошибкой сайта - она попадёт в отчёт как есть)
        self.log("\nГлавная не открылась (" + (f"код {r.status}" if r.status else r.error or "нет ответа")
                 + "), выясняю почему...")
        d = self._diagnose()
        msg = access_check.line(d)
        if d["kind"] == "bots_blocked" and self.cfg.user_agent == "crawler":
            self.switch_to_browser()
            self.log("Сайт не пускает программы: браузеру Chrome отвечает " + str(d.get("browser")) + ", программе - "
                     + str(d.get("program")) + ". Дальше проверяю как браузер Chrome, в отчёте это будет видно.")
        elif msg:
            self.log(msg)
        else:
            self.log("   Со второго раза главная открылась - продолжаю как обычно.")
        return d

    def switch_to_browser(self):
        ua = UA_PRESETS["chrome"]
        for f in (self.fetcher, self.insecure):
            f.user_agent = ua
        self.cfg.user_agent = "chrome"
        self.store.set_meta("config", self.cfg.__dict__)
        self.store.set_meta("ua_switched", {"from": "crawler", "to": "chrome"})

    def access_reason(self, r):
        """Короткая причина для «Сайт перестал отвечать: …» (один раз за обход): «соединение режут по дороге…»."""
        if hasattr(self, "_access_reason"):
            return self._access_reason
        self._access_reason = ""
        if r is not None and r.status and r.status not in access_check.BOT_CODES:
            return ""
        try:
            d = self._diagnose()
        except Exception:
            return ""
        self._access_reason = access_check.short(d)
        if self._access_reason:
            self.log("   Причина: " + self._access_reason + ".")
        return self._access_reason
