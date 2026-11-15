"""PDF из HTML средствами Chrome или Edge, которые уже стоят на компьютере (режим без окна, --print-to-pdf).
Сторонние библиотеки не нужны. Нет ни Chrome, ни Edge — PDF просто не собирается."""
import os
import subprocess
import tempfile


def find_browser():
    """Chrome или Edge на Windows."""
    if os.name != "nt":
        return None
    env = os.environ
    roots = [env.get("PROGRAMFILES", r"C:\Program Files"), env.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
             env.get("LOCALAPPDATA", "")]
    for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
        for root in roots:
            if root and os.path.exists(os.path.join(root, rel)):
                return os.path.join(root, rel)
    return None


def html_to_pdf(src, dst, timeout=180):
    """Возвращает "" или текст ошибки."""
    exe = find_browser()
    if not exe:
        return "не найден Chrome или Edge"
    profile = tempfile.mkdtemp(prefix="clayler-pdf-")  # отдельный профиль: не мешает открытому браузеру
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
           f"--user-data-dir={profile}", f"--print-to-pdf={os.path.abspath(dst)}",
           "file:///" + os.path.abspath(src).replace("\\", "/")]
    try:
        if os.path.exists(dst):
            os.remove(dst)
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except PermissionError:
        return "файл PDF открыт в другой программе - закройте его"
    except Exception as e:
        return str(e)[:150]
    return "" if os.path.exists(dst) and os.path.getsize(dst) > 0 else "браузер не создал файл"
