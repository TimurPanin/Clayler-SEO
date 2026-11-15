"""Общее для тестов, которые делают настоящий обход и читают файлы находок."""
import csv
import os


def issue_rows(folder, key):
    """Строки файла находки из папки «проблемы»; находки нет - пустой список."""
    path = os.path.join(folder, "проблемы", key + ".csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def quiet_env(reports_dir):
    """Окружение обхода для теста: своя папка отчётов, без личных настроек и без проверки орфографии в сети."""
    return dict(os.environ, CLAYLER_REPORTS=reports_dir, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1")
