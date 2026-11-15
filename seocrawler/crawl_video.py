"""Видео обхода для витрины (Авито, Kwork): «живая паутина» из окна программы проигрывает готовую проверку за ~20 с —
паучок плетёт сеть по мере того, как проверялись страницы (в порядке обхода), битые адреса вспыхивают красным,
редиректы — жёлтым; справа счётчики, в конце итог: здоровье, проблемы. 1280×720, MP4 (если на компьютере есть
ffmpeg), иначе WebM. Сайт заново не обходится. Кнопка «⋯ → Видео обхода (для Авито и Kwork)», файл «видео обхода.mp4»
в папке проверки (в папку для клиента не попадает). Без контактов: на площадках их писать нельзя."""
import base64
import json
import os
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

from .fmt import num

PAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window", "page")
NAME = "видео обхода"
FPS_DATA = 10      # шагов данных в секунду
RUN_SECONDS = 16   # сколько идёт «обход»
TAIL_SECONDS = 6   # доплетание, паук в центр, итог

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#050b1d;overflow:hidden}
#web{position:absolute;left:40px;top:0;width:720px;height:720px}
#out{position:absolute;left:0;top:0;width:1280px;height:720px}
</style></head><body><canvas id="web"></canvas><canvas id="out" width="1280" height="720"></canvas>
<script src="web_spider.js"></script><script src="web.js"></script><script>
window.recordVideo = function (D) {
  var web = ClaylerWeb.create(document.getElementById("web"), {role: "card", seed: 7});
  ClaylerWeb.setPrefs({spider: true});
  var out = document.getElementById("out"), g = out.getContext("2d"), src = document.getElementById("web");
  var st = {done: 0, errs: 0, warns: 0, end: false, endA: 0};
  var t0 = 0, step = 0, finished = false, stopAt = 0;
  var fmt = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); };
  function text(s, x, y, size, color, weight) {
    g.font = (weight || 400) + " " + size + "px 'Segoe UI', Arial, sans-serif"; g.fillStyle = color; g.fillText(s, x, y);
  }
  function draw() {
    g.fillStyle = "#050b1d"; g.fillRect(0, 0, 1280, 720);
    var gr = g.createRadialGradient(400, 360, 40, 400, 360, 420);
    gr.addColorStop(0, "rgba(40,90,190,0.22)"); gr.addColorStop(1, "rgba(5,11,29,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 820, 720);
    g.drawImage(src, 40, 0, 720, 720);
    var x = 820;
    text("SEO-аудит сайта", x, 92, 22, "#8fa3c9");
    text(D.site, x, 140, D.site.length > 22 ? 30 : 38, "#e6efff", 650);
    text("Проверено страниц", x, 222, 20, "#8fa3c9");
    text(fmt(st.done), x, 290, 64, "#e6efff", 650);
    g.fillStyle = "#13234a"; g.fillRect(x, 318, 400, 10);
    var gb = g.createLinearGradient(x, 0, x + 400, 0); gb.addColorStop(0, "#3d8bff"); gb.addColorStop(1, "#7fd0ff");
    g.fillStyle = gb; g.fillRect(x, 318, 400 * Math.min(1, st.done / Math.max(1, D.total)), 10);
    text(fmt(st.errs), x, 392, 36, "#ff5c6c", 650); text("ошибок", x, 420, 18, "#8fa3c9");
    text(fmt(st.warns), x + 200, 392, 36, "#ffbf5c", 650); text("редиректов", x + 200, 420, 18, "#8fa3c9");
    if (st.end) {
      st.endA = Math.min(1, st.endA + 0.04); g.globalAlpha = st.endA;
      text("Здоровье сайта", x, 500, 20, "#8fa3c9");
      text(D.health + "%", x, 566, 60, D.health >= 90 ? "#58c08a" : D.health >= 70 ? "#ffbf5c" : "#ff5c6c", 650);
      text("Критичных проблем: " + D.crit + "   Предупреждений: " + D.warn, x, 612, 20, "#e6efff");
      text("Полный отчёт: ошибки, причины и готовые исправления", x, 660, 17, "#8fa3c9");
      g.globalAlpha = 1;
    }
  }
  return new Promise(function (resolve) {
    var mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].filter(function (m) { return MediaRecorder.isTypeSupported(m); })[0];
    var rec = new MediaRecorder(out.captureStream(30), {mimeType: mime, videoBitsPerSecond: 8000000}), chunks = [];
    rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
    rec.onstop = function () {
      var r = new FileReader();
      r.onload = function () { resolve(r.result.split(",")[1]); };
      r.readAsDataURL(new Blob(chunks, {type: "video/webm"}));
    };
    rec.start(500);
    web.start({total: D.total});
    function frame(ts) {
      if (!t0) t0 = ts;
      var el = (ts - t0) / 1000;
      while (step < D.frames.length && step / D.fps <= el) {
        var f = D.frames[step++];
        st.done = f[0];
        web.progress(f[0], D.total);
        for (var i = 0; i < f[1]; i++) web.error();
        for (var j = 0; j < f[2]; j++) web.warning();
        st.errs += f[1]; st.warns += f[2];
      }
      if (step >= D.frames.length && !finished) {
        finished = true; st.done = D.total; web.finish(); stopAt = el + D.tail;
        setTimeout(function () { st.end = true; }, 1600);
      }
      draw();
      if (finished && el >= stopAt) { rec.stop(); return; }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
};
</script></body></html>"""


def timeline(store):
    """Страницы сайта в порядке обхода: (сколько проверено, ошибок, редиректов) на каждый шаг данных."""
    rows = store.db.execute(
        "SELECT p.status FROM urls u JOIN pages p ON p.url=u.url WHERE u.internal=1 AND u.kind='page' "
        "AND u.state='done' ORDER BY u.id").fetchall()
    n = len(rows)
    steps = FPS_DATA * RUN_SECONDS
    frames, k = [], 0
    for s in range(1, steps + 1):
        end = round(n * s / steps)
        errs = warns = 0
        for (st,) in rows[k:end]:
            st = st or 0
            if st >= 400 or st == 0:
                errs += 1
            elif 300 <= st < 400:
                warns += 1
        frames.append([end, errs, warns])
        k = end
    return n, frames


def _ffmpeg():
    for p in (shutil.which("ffmpeg"), r"C:\ffmpeg\bin\ffmpeg.exe"):
        if p and os.path.exists(p):
            return p
    return None


def write(out_dir, log=print):
    """Возвращает (путь к видео, текст ошибки или "")."""
    from .analyze import cached_analyze
    from .mobile_view import available
    from .storage import Store
    if not available():
        return "", "нужен встроенный браузер (playwright) - он ставится вместе с режимом JavaScript"
    store = Store(os.path.join(out_dir, "crawl.db"))
    try:
        _issues, _pages, summary = cached_analyze(store)
        total, frames = timeline(store)
        host = (urlsplit(store.get_meta("start", "") or "").hostname or "сайт").removeprefix("www.")
    finally:
        store.db.close()
    if not total:
        return "", "в проверке нет страниц"
    data = {"site": host, "total": total, "frames": frames, "fps": FPS_DATA, "tail": TAIL_SECONDS,
            "health": summary.get("health", 0), "crit": summary.get("crit", 0), "warn": summary.get("warn", 0)}
    tmp = tempfile.mkdtemp(prefix="clayler-video-")
    try:
        for f in ("web.js", "web_spider.js"):
            shutil.copy(os.path.join(PAGE_DIR, f), tmp)
        with open(os.path.join(tmp, "video.html"), "w", encoding="utf-8") as f:
            f.write(PAGE)
        log(f"Записываю видео обхода {host}: {num(total)} страниц, около {RUN_SECONDS + TAIL_SECONDS} с...")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                page.goto("file:///" + os.path.join(tmp, "video.html").replace("\\", "/"))
                page.wait_for_function("!!(window.ClaylerWeb && window.recordVideo)")
                b64 = page.evaluate("D => window.recordVideo(D)", data)
            finally:
                browser.close()
        webm = os.path.join(tmp, "v.webm")
        with open(webm, "wb") as f:
            f.write(base64.b64decode(b64))
        ff = _ffmpeg()
        if ff:
            dst = os.path.join(out_dir, NAME + ".mp4")
            r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                "-preset", "slow", "-crf", "18", "-r", "30", "-movflags", "+faststart", "-an", dst],
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and os.path.exists(dst):
                return dst, ""
            log("MP4 не собрался, сохраняю WebM: " + (r.stderr or "")[-200:])
        dst = os.path.join(out_dir, NAME + ".webm")
        shutil.copy(webm, dst)
        return dst, ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":  # py -3 -m seocrawler.crawl_video <папка проверки>
    import sys
    print(json.dumps(write(sys.argv[1]), ensure_ascii=False))
