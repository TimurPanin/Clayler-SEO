"""Сколько заняла проверка: для отчёта, аудита и списка отчётов (чтобы понимать, сколько ждать на похожем сайте)."""
import time


def seconds(meta):
    """Время работы обхода, секунд. Новые проверки хранят его сами (work_seconds, с продолжениями вместе);
    у старых — от начала до конца (если проверку продолжали, туда попадёт и перерыв)."""
    if meta.get("work_seconds"):
        return float(meta["work_seconds"])
    try:
        a = time.mktime(time.strptime(meta.get("started_at") or "", "%Y-%m-%d %H:%M:%S"))
        b = time.mktime(time.strptime(meta.get("finished_at") or "", "%Y-%m-%d %H:%M:%S"))
        return b - a if b > a else None
    except ValueError:
        return None


def fmt(sec):
    if sec is None:
        return ""
    m = round(sec / 60)
    if m < 1:
        return "меньше минуты"
    h, m = divmod(m, 60)
    return (f"{h} ч {m} мин" if m else f"{h} ч") if h else f"{m} мин"


def text(meta, pages):
    """«Проверка заняла 1 ч 20 мин (≈160 страниц в минуту)» или ""."""
    sec = seconds(meta)
    if not sec:
        return ""
    speed = f" (≈{round(pages / (sec / 60))} страниц в минуту)" if pages and sec >= 60 else ""
    return f"Проверка заняла {fmt(sec)}{speed}"
