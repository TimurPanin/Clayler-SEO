"""PDF для витрины (Kwork и т. п.): тот же аудит в PDF, но с пометкой «Пример отчёта», с вашим именем без контактов
и ссылок на Telegram, телефоны, почты и адреса проверенного сайта скрыты. Собирается по кнопке «⋯ → PDF для витрины
(демо)» из готовой проверки: сайт заново не обходится. Лежит в папке проверки (аудит_демо.pdf), в папку для клиента
не попадает."""
import os

from .audit import DEMO_FILE, REPORT_META, write_audit
from .site_tech import recheck_paths


def write(out_dir):
    """Возвращает (путь к PDF, текст ошибки или "")."""
    from .analyze import cached_analyze
    from .pdf import html_to_pdf
    from .storage import Store
    store = Store(os.path.join(out_dir, "crawl.db"))
    try:
        st = store.get_meta("site_tech", None)
        if isinstance(st, dict) and recheck_paths(st, store):  # старые проверки: движок по чужим картинкам
            store.set_meta("site_tech", st)
            store.commit()
        issues, _pages, summary = cached_analyze(store)
        meta = {k: store.get_meta(k, "") for k in REPORT_META}
        if isinstance(meta.get("security"), dict):  # витрина: без подробностей об открытых паролях настоящего сайта
            meta["security"] = dict(meta["security"], env_keys={})
    finally:
        store.db.close()
    tmp = os.path.join(out_dir, ".аудит_демо.html")
    dst = os.path.join(out_dir, DEMO_FILE)
    write_audit(tmp, meta, issues, summary, demo=True)
    try:
        err = html_to_pdf(tmp, dst)
    finally:
        os.remove(tmp)
    return dst, err
