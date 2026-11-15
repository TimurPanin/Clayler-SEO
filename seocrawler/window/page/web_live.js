/* Живая паутина на настоящей проверке: раз в 1,5 с спрашивает у программы /api/web и передаёт
 * паутинам (web.js) ход проверки, ошибки, остановки и конец.
 *
 *   ClaylerWeb.live([webCard, webBackground])   - подключить одну или несколько паутин
 *
 * Программа пишет состояние раз в ~3 секунды, поэтому новые страницы и ошибки не выдаются паутине
 * пачкой, а раскладываются равномерно до следующего ответа: паук идёт ровно, а не рывками.
 * Ход берётся из общей доли сделанного (overall, 0–100), той же, что у полосы прогресса,
 * поэтому к концу проверки паутина как раз заполняется. Ошибка - адрес с кодом 4xx, 5xx или без
 * ответа, предупреждение - переадресация 3xx.
 *
 * Наведение на узел паутины показывает адрес страницы и её главную проблему (/api/web_node), нажатие
 * открывает эту страницу в отчёте. Паутина декоративная, поэтому узел переводится в страницу по ходу проверки:
 * сколько страниц было готово, когда плелась эта нить (st.track - доля сделанного и число страниц).
 */
(function () {
  "use strict";
  if (!window.ClaylerWeb) return;

  var POLL = 1500, TICK = 200, STUCK = 20; // через сколько секунд без готовых адресов паук замирает

  ClaylerWeb.live = function (webs, opt) {
    webs = [].concat(webs);
    opt = opt || {};
    var url = opt.url || "/api/web";
    var st = { running: false, first: true, shown: 0, target: 0, bad: null, warn: null, qBad: 0, qWarn: 0, step: "", spread: 0,
      track: [], folder: "" };
    var stopped = false, pollT = 0, tickT = 0;
    function all(fn, a, b, c) { webs.forEach(function (w) { w[fn](a, b, c); }); }

    function tick() { // раскладываем полученное до следующего ответа программы
      tickT = 0;
      if (!st.running) return;
      var left = Math.max(1, st.spread--);
      if (st.target > st.shown && !st.stuck) { st.shown += (st.target - st.shown) / left; all("progress", st.shown * 10, 1000); }
      var nb = Math.ceil(st.qBad / left), nw = Math.ceil(st.qWarn / left);
      st.qBad -= nb; st.qWarn -= nw;
      // вспышек за раз немного: паутина сама сливает частые ошибки в один участок
      for (var i = 0; i < Math.min(nb, 3); i++) all("error");
      for (i = 0; i < Math.min(nw, 2); i++) all("warning");
      if (st.spread > 0 || st.qBad || st.qWarn) tickT = setTimeout(tick, TICK);
    }

    function apply(s) {
      var pct = s.overall != null ? s.overall : (s.progress && s.progress[1] ? 100 * s.progress[0] / s.progress[1] : null);
      if (s.running && pct != null) {
        // новая проверка, или следующий сайт (конкурент) - доля сделанного начинается заново
        var restart = !st.running || pct < st.target - 20 || (st.site && s.site && s.site !== st.site);
        if (restart) {
          all("start");
          st.shown = 0; st.target = 0; st.bad = s.bad; st.warn = s.warn; st.qBad = st.qWarn = 0;
          st.running = true; st.track = []; st.folder = "";
          if (st.first && pct > 3) { st.shown = st.target = pct; all("progress", pct * 10, 1000, { instant: true }); }
        }
        st.first = false; st.site = s.site;
        if (s.folder) st.folder = s.folder;
        if (s.unit === "pages" && s.progress && s.progress[0] != null) { // для наведения: доля сделанного -> страниц готово
          var last = st.track[st.track.length - 1];
          if (!last || s.progress[0] > last[1]) st.track.push([pct, s.progress[0]]);
        }
        var grew = pct > st.target;
        st.target = Math.max(st.target, pct);
        if (s.bad != null) { if (st.bad != null && s.bad > st.bad) st.qBad += s.bad - st.bad; st.bad = s.bad; }
        if (s.warn != null) { if (st.warn != null && s.warn > st.warn) st.qWarn += s.warn - st.warn; st.warn = s.warn; }
        st.stuck = (s.stuck || 0) > STUCK;
        if (st.stuck) all("pause"); else all("resume");
        // программа обновляет состояние раз в ~3 с: новое раскладываем на это время
        if (grew || s.bad > st.bad0 || s.warn > st.warn0) st.spread = Math.round(POLL * 2 / TICK);
        st.bad0 = s.bad; st.warn0 = s.warn;
        if (!tickT) tick();
      } else if (!s.running && st.running) {
        st.running = false;
        all("progress", st.target * 10, 1000);
        all("finish", { complete: !s.stopped }); // остановили вручную - не доплетаем
      }
      st.first = false;
    }

    function poll() {
      clearTimeout(pollT); pollT = 0;
      if (stopped || noApi) return;
      fetch(url, { cache: "no-store" }).then(function (r) {
        if (r.status === 404) { noApi = true; return null; } // окно старое, без /api/web: только события окна
        return r.json();
      }).then(function (s) { if (s) apply(s); })
        .catch(function () { /* окно перезапускается - спросим ещё раз */ }).then(function () {
          if (!stopped && !noApi) pollT = setTimeout(poll, document.hidden ? POLL * 4 : (st.running ? POLL : POLL * 4));
        });
    }

    // События окна (app.js, 'clayler:crawl'): по ним спрашиваем программу сразу, не дожидаясь опроса.
    // Если /api/web нет, паутина идёт только по ним: страницы без общего числа, без ошибок сайта.
    var noApi = false;
    function onCrawl(e) {
      var d = (e && e.detail) || {};
      if (!noApi) { if (d.type !== "page" && d.type !== "warning") poll(); return; }
      if (d.type === "start") all("start");
      else if (d.type === "page") all("page", d.delta || 1);
      else if (d.type === "warning") all("pause");
      else if (d.type === "end" || d.type === "pause" || d.type === "error") all("finish", { complete: d.type === "end" });
    }
    window.addEventListener("clayler:crawl", onCrawl);
    webs.forEach(function (w) { if (w.role === "card") w.onPick = function (h, e, clicked) { pick(st, h, e, clicked); }; });
    poll();
    return {
      stop: function () { stopped = true; clearTimeout(pollT); clearTimeout(tickT); window.removeEventListener("clayler:crawl", onCrawl); },
      apply: apply // для проверки без программы: подать состояние вручную
    };
  };

  // ---------- Подсказка у узла паутины ----------
  function pagesAt(track, f) { // сколько страниц было готово, когда плелась нить на доле f
    var pct = f * 100, a = [0, 0];
    for (var i = 0; i < track.length; i++) {
      var b = track[i];
      if (pct <= b[0]) return a[1] + (b[1] - a[1]) * (b[0] > a[0] ? (pct - a[0]) / (b[0] - a[0]) : 1);
      a = b;
    }
    return a[1];
  }
  var tip = null, cache = {}, want = "";
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function showTip(html, e) {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "web-tip";
      tip.style.cssText = "position:fixed;z-index:60;pointer-events:none;max-width:380px;padding:8px 11px;border-radius:9px;" +
        "background:var(--card,#1e1e1e);color:var(--tx,#eee);border:1px solid var(--bd,#3a3a3a);font-size:13px;line-height:1.4;" +
        "overflow-wrap:anywhere;box-shadow:0 6px 22px rgba(0,0,0,.45)";
      document.body.appendChild(tip);
    }
    tip.innerHTML = html; tip.style.display = "block";
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(6, Math.min(e.clientX + 14, innerWidth - w - 8)) + "px";
    tip.style.top = (e.clientY + 16 + h > innerHeight - 6 ? e.clientY - h - 12 : e.clientY + 16) + "px";
  }
  function hideTip() { if (tip) tip.style.display = "none"; want = ""; }
  function tipHtml(d) {
    if (!d) return '<span style="opacity:.7">Смотрю, какая это страница…</span>';
    if (!d.url) return '<span style="opacity:.7">' + esc(d.note || "Страница ещё не проверена") + "</span>";
    var col = d.sev === "crit" ? "var(--crit,#ff8f80)" : d.sev === "warn" ? "var(--warn,#e5a54b)" : d.sev === "note" ? "var(--tx2,#d0d0d0)" : "var(--good,#4fbf8a)";
    return "<b>" + esc(d.url) + "</b>" + (d.problem ? '<br><span style="color:' + col + '">' + esc(d.problem) + "</span>" : "") +
      (d.where ? '<br><span style="opacity:.75">' + esc(d.where) + "</span>" : "") +
      '<br><span style="opacity:.6">' + (d.report ? "Нажмите - открыть в отчёте" : "Отчёт будет готов после проверки") + "</span>";
  }
  function pick(st, h, e, clicked) {
    if (!h || !st.folder) { hideTip(); return; }
    var n = Math.max(0, Math.round(pagesAt(st.track, h.f)) - 1);
    var key = st.folder + "|" + (h.kind === "node" ? "page" : h.kind) + "|" + n;
    function open(d) {
      if (d && d.url && d.report) // в отчёте откроются проблемы этой страницы
        window.open(d.report + "#page=" + encodeURIComponent(d.url) + ((d.issues || []).length ? "&issues=" + d.issues.join(",") : ""), "_blank");
    }
    var have = cache[key];
    if (have && have.url && Date.now() - have.at > 4000 && !have.report) have = null; // отчёт мог появиться
    if (have) { showTip(tipHtml(have), e); if (clicked) open(have); return; }
    showTip(tipHtml(null), e);
    if (want === key) return;
    want = key;
    fetch("/api/web_node?folder=" + encodeURIComponent(st.folder) + "&kind=" + (h.kind === "node" ? "page" : h.kind) + "&n=" + n,
      { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      d.at = Date.now(); cache[key] = d;
      if (want === key) { showTip(tipHtml(d), e); if (clicked) open(d); }
    }).catch(function () { if (want === key) hideTip(); });
  }

  // Сами встаём в места, которые окно оставило под паутину: #webStage в карточке «Идёт проверка»
  // и #webBg - бледный слой на весь фон. Нет мест - ничего не делаем (например, на демо-странице).
  function boot() {
    var webs = [];
    [["webStage", "card"], ["webBg", "background"]].forEach(function (x) {
      var box = document.getElementById(x[0]);
      if (!box || box.querySelector("canvas")) return;
      var c = document.createElement("canvas");
      box.appendChild(c);
      webs.push(ClaylerWeb.create(c, { role: x[1] }));
    });
    if (webs.length) ClaylerWeb.page = { webs: webs, live: ClaylerWeb.live(webs) };
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
