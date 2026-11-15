/* Живая паутина Clayler SEO: паук плетёт паутину по ходу проверки.
 *
 * Паутина декоративная: она не повторяет структуру сайта, а отражает ход проверки.
 * Сначала радиальные нити из центра и рамка, потом спираль изнутри наружу. Вся паутина -
 * это доля проверки: на 100 страниц и на 20 000 к концу она заполняется одинаково,
 * просто на большом сайте одна нить - это пачка страниц.
 *
 * Подключение: <script src="/page/web_spider.js"></script><script src="/page/web.js"></script>
 *   var w = ClaylerWeb.create(canvas, {role: "card"});      // или role: "background" - бледный слой фона
 *   w.start({total: 10000})   новая проверка (старая паутина медленно тает)
 *   w.progress(done, total)   сколько страниц готово и сколько всего ожидается (лучше всего);
 *                             третьим аргументом {instant: true} - сразу показать сплетённое, без беготни
 *   w.page(n)                 или просто: готово ещё n страниц (по умолчанию 1)
 *   w.error() / w.warning()   на сайте ошибка / предупреждение: текущая нить вспыхивает
 *   w.pause() / w.resume()    проверка встала / пошла дальше (page и progress сами снимают паузу)
 *   w.finish({complete})      конец: паук доплетает (если complete не false), паутина вспыхивает, паук садится в центр
 *   w.reset()                 убрать паутину совсем
 *   w.destroy()               отцепиться от canvas
 *   w.onPick = function (hit, event, clicked) {}   наведение и нажатие на узел паутины (только role "card")
 * Настройки (общие для всех паутин, хранятся в браузере):
 *   ClaylerWeb.setPrefs({background: false, spider: false}); ClaylerWeb.getPrefs()
 *   background - показывать ли бледный слой паутины на фоне окна; spider - показывать ли паучка.
 * Экземпляров может быть несколько (по паутине на сайт при параллельной проверке).
 * Анимация сама засыпает, когда вкладка скрыта, окно свёрнуто или canvas не виден.
 */
(function () {
  "use strict";

  var PREF_KEY = "clayler.web";
  var instances = [];

  function loadPrefs() {
    var p = {};
    try { p = JSON.parse(localStorage.getItem(PREF_KEY) || "{}") || {}; } catch (e) { p = {}; }
    return { background: p.background !== false, spider: p.spider !== false };
  }
  var prefs = loadPrefs();

  function rng(seed) {
    var s = seed >>> 0;
    return function () { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }

  // ---------- Геометрия паутины (в долях радиуса, центр 0,0, y вниз) ----------
  function polyLen(pts) {
    var c = [0], L = 0;
    for (var i = 1; i < pts.length; i++) {
      L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      c.push(L);
    }
    return c;
  }
  function line(a, b, n) {
    var pts = [];
    for (var i = 0; i <= n; i++) { var t = i / n; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]); }
    return pts;
  }
  function sag(a, b, amount, n) { // нить между лучами чуть провисает к центру
    var m = [(a[0] + b[0]) / 2 * (1 - amount), (a[1] + b[1]) / 2 * (1 - amount)], pts = [];
    for (var i = 0; i <= n; i++) {
      var t = i / n, u = 1 - t;
      pts.push([u * u * a[0] + 2 * u * t * m[0] + t * t * b[0], u * u * a[1] + 2 * u * t * m[1] + t * t * b[1]]);
    }
    return pts;
  }

  function buildWeb(seed, K, T) {
    var R = rng(seed), ang = [], len = [], i, k;
    for (i = 0; i < K; i++) {
      ang.push((i + (R() - 0.5) * 0.55) * 2 * Math.PI / K - Math.PI / 2);
      len.push(0.84 + R() * 0.16);
    }
    function pt(i, r) { i = ((i % K) + K) % K; return [Math.cos(ang[i]) * r, Math.sin(ang[i]) * r]; }
    function E(i) { return pt(i, len[((i % K) + K) % K]); }
    var C = [0, 0], moves = [], anchors = [];
    function add(pts, draw, kind) { moves.push({ pts: pts, draw: draw, kind: kind }); }

    // 1) лучи парами: наружу по чётному, по рамке к соседнему, обратно в центр по нечётному
    for (k = 0; k < K; k += 2) {
      add(line(C, E(k), 8), true, "spoke");
      if (R() < 0.3) anchors.push({ after: moves.length - 1, from: E(k), dir: ang[k] + (R() - 0.5) * 0.5 });
      add(sag(E(k), E(k + 1), 0.04, 8), true, "frame");
      add(line(E(k + 1), C, 8), true, "spoke");
    }
    // 2) по лучу 1 наружу и по кругу рамки, доплетая пропущенные куски рамки
    add(line(C, E(1), 8), false, "walk");
    for (i = 1; i < K; i++) add(sag(E(i), E(i + 1), 0.04, 8), i % 2 === 1, i % 2 === 1 ? "frame" : "walk");
    // 3) по лучу 0 внутрь к началу спирали
    var r0 = 0.1, r1 = 0.97, N = K * T;
    add(line(E(0), pt(0, r0 * len[0]), 8), false, "walk");
    // 4) ловчая спираль изнутри наружу: радиус - доля длины луча, так спираль повторяет неровную рамку
    for (var s = 0; s < N; s++) {
      var a = pt(s, (r0 + (r1 - r0) * s / N) * len[s % K]);
      var b = pt(s + 1, (r0 + (r1 - r0) * (s + 1) / N) * len[(s + 1) % K]);
      add(sag(a, b, 0.035 + 0.02 * s / N, 6), true, "spiral");
    }
    // длины и накопленные расстояния: s - путь паука, d - сплетённая нить
    var S = 0, D = 0;
    moves.forEach(function (m) {
      m.cum = polyLen(m.pts); m.len = m.cum[m.cum.length - 1];
      m.s0 = S; S += m.len;
      m.d0 = D; if (m.draw) D += m.len;
      m.marks = [];
    });
    return { moves: moves, anchors: anchors, pathLen: S, drawnLen: D };
  }

  function pointOn(m, u) { // точка на нити, u - расстояние от её начала
    var c = m.cum, p = m.pts, n = c.length - 1;
    if (u <= 0) return [p[0][0], p[0][1], Math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0])];
    if (u >= m.len) return [p[n][0], p[n][1], Math.atan2(p[n][1] - p[n - 1][1], p[n][0] - p[n - 1][0])];
    var lo = 0, hi = n;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (c[mid] <= u) lo = mid; else hi = mid; }
    var t = (u - c[lo]) / ((c[hi] - c[lo]) || 1);
    return [p[lo][0] + (p[hi][0] - p[lo][0]) * t, p[lo][1] + (p[hi][1] - p[lo][1]) * t,
      Math.atan2(p[hi][1] - p[lo][1], p[hi][0] - p[lo][0])];
  }

  // ---------- Паучок: картинка с синей подсветкой по краю и знаком на спине ----------
  var spiderImg = null, spiderReady = false, parts = null, partsReady = false;
  function ensureSpiderImg() {
    if (spiderImg || !window.CLAYLER_SPIDER_PNG) return;
    function ready() { instances.forEach(function (w) { w._sprite = null; w._wake(); }); }
    spiderImg = new Image();
    spiderImg.onload = function () { spiderReady = true; ready(); };
    spiderImg.src = window.CLAYLER_SPIDER_PNG;
    var P = window.CLAYLER_SPIDER_PARTS; // тело и 8 лапок отдельно - для шага
    if (!P) return;
    var left = 1 + P.legs.length;
    function one() { if (--left === 0) { partsReady = true; ready(); } }
    parts = { w: P.w, h: P.h, body: new Image(), legs: P.legs.map(function (l) {
      var im = new Image(); im.onload = one; im.src = l.src;
      return { im: im, x: l.x, y: l.y, px: l.px, py: l.py, g: l.g, side: l.name.charAt(0) === "L" ? 1 : -1 };
    }) };
    parts.body.onload = one; parts.body.src = P.body;
  }

  // Шаг: лапки качаются двумя четвёрками попеременно, как у настоящего паука
  // (левая 1 и 3 с правой 2 и 4, потом остальные). Поз 8 на шаг, каждая рисуется один раз на размер,
  // поэтому в кадре по-прежнему одна картинка - окно не нагружается, сколько бы ни было страниц.
  var STEP_FRAMES = 8, SWING = 0.2;
  function drawPose(g, x0, y0, k, f) { // f - доля шага 0..1
    var a = f * Math.PI * 2;
    parts.legs.forEach(function (l) {
      var s = Math.sin(a + (l.g ? Math.PI : 0)), lift = Math.cos(a + (l.g ? Math.PI : 0)) > 0 ? 0.95 : 1;
      g.save();
      g.translate(x0 + l.px * k, y0 + l.py * k);
      g.rotate(s * SWING * l.side);
      g.scale(lift, lift); // лапка в воздухе чуть короче - будто приподнята
      g.drawImage(l.im, (l.x - l.px) * k, (l.y - l.py) * k, l.im.width * k, l.im.height * k);
      g.restore();
    });
    g.drawImage(parts.body, x0, y0, parts.w * k, parts.h * k);
  }

  function bakeSprite(size) { // спрайт рисуется один раз на размер, в кадре только поворот
    var pad = Math.ceil(size * 0.25), W = size + pad * 2;
    var c = document.createElement("canvas"); c.width = c.height = W;
    var g = c.getContext("2d");
    var cx = W / 2, cy = W / 2;
    if (spiderReady) {
      var h = size, w = size * spiderImg.width / spiderImg.height;
      var out = { c: c, half: W / 2, frames: null };
      var frames = partsReady ? STEP_FRAMES : 1;
      for (var fi = 0; fi < frames; fi++) {
        var fc = fi ? document.createElement("canvas") : c;
        if (fi) fc.width = fc.height = W;
        var fg = fc.getContext("2d"), src = spiderImg;
        if (partsReady) { // поза лапок без свечения, потом свечение по краю всей фигуры
          src = document.createElement("canvas"); src.width = src.height = W;
          drawPose(src.getContext("2d"), cx - w / 2, cy - h / 2, h / parts.h, fi / frames);
          fg.shadowColor = "rgba(80,170,255,0.95)"; fg.shadowBlur = Math.max(4, size * 0.12);
          fg.drawImage(src, 0, 0);
          fg.shadowBlur = Math.max(2, size * 0.05);
          fg.drawImage(src, 0, 0);
        } else {
          fg.shadowColor = "rgba(80,170,255,0.95)"; fg.shadowBlur = Math.max(4, size * 0.12);
          fg.drawImage(src, cx - w / 2, cy - h / 2, w, h);
          fg.shadowBlur = Math.max(2, size * 0.05);
          fg.drawImage(src, cx - w / 2, cy - h / 2, w, h);
        }
        fg.shadowBlur = 0;
        // знак на брюшке (на картинке голова снизу, брюшко сверху)
        drawMark(fg, cx - w / 2 + w * 0.477, cy - h / 2 + h * 0.36, size * 0.075);
        if (partsReady) (out.frames = out.frames || []).push(fc);
      }
      return out;
    } else { // запасной паучок, если картинки нет
      var r = size * 0.22;
      g.strokeStyle = "#0b0f18"; g.lineCap = "round"; g.lineWidth = Math.max(1.5, size * 0.045);
      g.shadowColor = "rgba(80,170,255,0.9)"; g.shadowBlur = size * 0.1;
      for (var i = 0; i < 8; i++) {
        var side = i < 4 ? -1 : 1, j = i % 4, a = (-0.9 + j * 0.55);
        var kx = cx + side * Math.cos(a) * r * 1.9, ky = cy + Math.sin(a) * r * 1.6 + r * 0.3;
        var ex = cx + side * Math.cos(a) * r * 2.6, ey = ky + r * (j < 2 ? -0.9 : 1.1);
        g.beginPath(); g.moveTo(cx, cy + r * 0.3); g.quadraticCurveTo(kx, ky - r * 0.6, ex, ey); g.stroke();
      }
      g.fillStyle = "#11151f";
      g.beginPath(); g.ellipse(cx, cy - r * 0.35, r * 0.9, r * 1.1, 0, 0, Math.PI * 2); g.fill();
      g.beginPath(); g.arc(cx, cy + r * 0.85, r * 0.55, 0, Math.PI * 2); g.fill();
      g.shadowBlur = 0;
      drawMark(g, cx, cy - r * 0.4, size * 0.075);
    }
    return { c: c, half: W / 2 };
  }
  function drawMark(g, x, y, s) { // синие «песочные часы» на спине
    g.save();
    g.shadowColor = "rgba(90,190,255,1)"; g.shadowBlur = s * 2.2;
    g.fillStyle = "#6fd0ff";
    g.beginPath();
    g.moveTo(x - s * 0.8, y - s * 1.3); g.lineTo(x + s * 0.8, y - s * 1.3); g.lineTo(x, y);
    g.lineTo(x + s * 0.8, y + s * 1.3); g.lineTo(x - s * 0.8, y + s * 1.3); g.lineTo(x, y);
    g.closePath(); g.fill();
    g.restore();
  }

  var glowCache = {};
  function glowDot(radius, color) { // мягкое светящееся пятно для узлов и вспышек
    var key = radius + color;
    if (glowCache[key]) return glowCache[key];
    var s = Math.ceil(radius * 2), c = document.createElement("canvas"); c.width = c.height = s;
    var g = c.getContext("2d"), gr = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    gr.addColorStop(0, color); gr.addColorStop(0.35, color.replace(/[\d.]+\)$/, "0.35)")); gr.addColorStop(1, color.replace(/[\d.]+\)$/, "0)"));
    g.fillStyle = gr; g.fillRect(0, 0, s, s);
    return (glowCache[key] = c);
  }

  // ---------- Сама паутина ----------
  var SPOT = 0.07; // полудлина красного или жёлтого участка нити, в долях радиуса
  var COLORS = {
    glow: "rgba(70,160,255,0.16)", core: "rgba(225,244,255,0.78)", spokeCore: "rgba(235,248,255,0.9)",
    errGlow: "rgba(255,40,60,0.38)", errCore: "rgba(255,95,110,0.95)",
    warnGlow: "rgba(255,170,40,0.16)", warnCore: "rgba(255,196,90,0.75)",
    node: "rgba(200,235,255,0.95)"
  };

  function Web(canvas, opt) {
    opt = opt || {};
    this.cv = canvas; this.ctx = canvas.getContext("2d");
    this.role = opt.role || "card";
    this.opt = {
      spider: opt.spider !== undefined ? opt.spider : this.role === "card",
      backdrop: opt.backdrop !== undefined ? opt.backdrop : this.role === "card",
      spokes: opt.spokes || 24, turns: opt.turns || 14,
      stretch: opt.stretch || (this.role === "background" ? 1.6 : 1.2),
      size: opt.size || (this.role === "background" ? 0.62 : 0.46),
      seed: opt.seed
    };
    this.layer = document.createElement("canvas");
    this.ghost = null; this.ghostA = 0;
    this.time = 0; this.last = 0; this.raf = 0; this.awake = true; this.visible = true;
    this.reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._newWeb();
    this.phase = "idle";
    this._resize();
    var self = this;
    this._onVis = function () { self._wake(); };
    document.addEventListener("visibilitychange", this._onVis);
    if (window.ResizeObserver) { this._ro = new ResizeObserver(function () { self._resize(); self._wake(); }); this._ro.observe(canvas); }
    else window.addEventListener("resize", this._onVis);
    if (window.IntersectionObserver) {
      this._io = new IntersectionObserver(function (e) { self.visible = e[e.length - 1].isIntersecting; self._wake(); });
      this._io.observe(canvas);
    }
    ensureSpiderImg();
    if (this.role === "card") this._hoverInit();
    instances.push(this);
    this._wake();
  }

  Web.prototype._newWeb = function () {
    var seed = this.opt.seed !== undefined ? this.opt.seed : (Math.random() * 1e9) | 0;
    this.web = buildWeb(seed, this.opt.spokes, this.opt.turns);
    this.s = 0; this.sTarget = 0; this.dTarget = 0;
    this.done = 0; this.total = 0;
    this.built = -1; this.dirty = true; this.lastBuild = 0;
    this.flashes = []; this.lastFlash = -1;
    this.heading = Math.PI / 2; this.finishT = -1; this.home = null;
    this.mi = 0; this.hover = null;
  };

  Web.prototype._resize = function () {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = Math.max(1, Math.round(this.cv.clientWidth * dpr)), h = Math.max(1, Math.round(this.cv.clientHeight * dpr));
    if (w === this.W && h === this.H) return;
    this.cv.width = this.layer.width = w; this.cv.height = this.layer.height = h;
    this.W = w; this.H = h; this.dpr = dpr;
    this.R = Math.min(h * 0.5 * 0.94, w * 0.5 / this.opt.stretch * 0.94, Math.max(w, h) * this.opt.size);
    this.Rx = this.R * Math.min(this.opt.stretch, w / h); this.Ry = this.R;
    this.cx = w / 2; this.cy = h / 2;
    this.lw = Math.max(1, this.R / 230) * dpr * 0.8;
    this._sprite = null; this.dirty = true; this.built = -1; this._bg = null;
  };

  Web.prototype._xy = function (p) { return [this.cx + p[0] * this.Rx, this.cy + p[1] * this.Ry]; };

  Web.prototype._path = function (g, m, upto) {
    var p = m.pts, c = m.cum, a = this._xy(p[0]);
    g.moveTo(a[0], a[1]);
    for (var i = 1; i < p.length; i++) {
      if (upto !== undefined && c[i] > upto) {
        var e = pointOn(m, upto), q = this._xy(e); g.lineTo(q[0], q[1]); return;
      }
      var b = this._xy(p[i]); g.lineTo(b[0], b[1]);
    }
  };

  Web.prototype._strokeSet = function (g, list, glow, core, wGlow, wCore, upto) {
    if (!list.length) return;
    var self = this;
    g.beginPath(); list.forEach(function (m) { self._path(g, m, m === upto.m ? upto.u : undefined); });
    g.strokeStyle = glow; g.lineWidth = wGlow; g.stroke();
    g.strokeStyle = core; g.lineWidth = wCore; g.stroke();
  };

  // Слой со всеми готовыми нитями перерисовывается не чаще ~8 раз в секунду
  Web.prototype._build = function (upTo) {
    var g = this.layer.getContext("2d"), lw = this.lw, self = this, mv = this.web.moves;
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, this.W, this.H);
    g.globalCompositeOperation = "lighter"; g.lineCap = "round"; g.lineJoin = "round";
    var norm = [], spokes = [], marked = [], nodes = [];
    for (var i = 0; i < upTo; i++) {
      var m = mv[i]; if (!m.draw) continue;
      if (m.kind === "spiral") norm.push(m); else spokes.push(m);
      if (m.marks.length) marked.push(m);
      if (m.kind === "spiral") nodes.push(m.pts[m.pts.length - 1]);
    }
    var none = {};
    // нити-растяжки к краям
    g.beginPath();
    this.web.anchors.forEach(function (a) {
      if (a.after >= upTo) return;
      var p = self._xy(a.from); g.moveTo(p[0], p[1]);
      g.lineTo(p[0] + Math.cos(a.dir) * self.R * 2, p[1] + Math.sin(a.dir) * self.R * 2);
    });
    g.strokeStyle = "rgba(150,205,255,0.16)"; g.lineWidth = lw; g.stroke();
    this._strokeSet(g, spokes, COLORS.glow, COLORS.spokeCore, lw * 5, lw * 1.1, none);
    this._strokeSet(g, norm, COLORS.glow, COLORS.core, lw * 4, lw * 0.85, none);
    this._drawMarks(g, marked);
    // яркие узлы на пересечениях спирали с лучами
    var dot = glowDot(Math.round(lw * 4), COLORS.node), half = dot.width / 2;
    g.globalAlpha = 0.7;
    nodes.forEach(function (p) { var q = self._xy(p); g.drawImage(dot, q[0] - half, q[1] - half); });
    g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
    this.built = upTo; this.dirty = false; this.lastBuild = this.time;
  };

  Web.prototype._pathRange = function (g, m, a, b) { // кусок нити от a до b
    a = Math.max(0, a); b = Math.min(m.len, b);
    var p = this._xy(pointOn(m, a)); g.moveTo(p[0], p[1]);
    for (var i = 1; i < m.pts.length; i++) if (m.cum[i] > a && m.cum[i] < b) { p = this._xy(m.pts[i]); g.lineTo(p[0], p[1]); }
    p = this._xy(pointOn(m, b)); g.lineTo(p[0], p[1]);
  };

  // Ошибки и предупреждения остаются красноватыми и жёлтыми участками там, где паук был в тот момент.
  // Предупреждения скромнее ошибок, чтобы красное не терялось.
  Web.prototype._drawMarks = function (g, list) {
    var self = this, lw = this.lw, H = SPOT;
    ["warn", "err"].forEach(function (kind) {
      list.forEach(function (m) {
        m.marks.forEach(function (k) {
          if (k.kind !== kind) return;
          var err = kind === "err";
          var a = Math.min(1, (err ? 0.75 : 0.5) + (err ? 0.1 : 0.06) * k.n);
          g.beginPath(); self._pathRange(g, m, k.u - H, k.u + H);
          // свечение складывается, а саму нить перекрашиваем поверх белой
          g.globalCompositeOperation = "lighter"; g.globalAlpha = a;
          g.strokeStyle = err ? COLORS.errGlow : COLORS.warnGlow; g.lineWidth = lw * (err ? 6 : 4.5); g.stroke();
          g.globalCompositeOperation = "source-over";
          g.strokeStyle = err ? COLORS.errCore : COLORS.warnCore; g.lineWidth = lw * (err ? 1.5 : 1.2); g.stroke();
        });
      });
    });
    g.globalAlpha = 1; g.globalCompositeOperation = "lighter";
  };

  Web.prototype._moveAt = function (s) {
    var mv = this.web.moves, i = clamp(this.mi, 0, mv.length - 1);
    while (i < mv.length - 1 && s >= mv[i].s0 + mv[i].len) i++;
    while (i > 0 && s < mv[i].s0) i--;
    this.mi = i; return i;
  };

  Web.prototype._sForDrawn = function (d) {
    var mv = this.web.moves;
    for (var i = 0; i < mv.length; i++) {
      var m = mv[i];
      if (m.draw && d <= m.d0 + m.len) return m.s0 + Math.max(0, d - m.d0);
    }
    return this.web.pathLen;
  };

  Web.prototype._retarget = function () {
    var f = this.total > 0 ? this.done / this.total : this.done / (this.done + 150);
    f = Math.min(f, 0.985);
    this.dTarget = Math.max(this.dTarget, f * this.web.drawnLen);
    this.sTarget = Math.max(this.sTarget, this._sForDrawn(this.dTarget));
  };

  Web.prototype._currentDrawMove = function () { // нить под пауком или последняя сплетённая
    var mv = this.web.moves, i = this._moveAt(this.s);
    while (i > 0 && !mv[i].draw) i--;
    return mv[i];
  };

  // ---------- Команды ----------
  Web.prototype.start = function (o) {
    o = o || {};
    if (this.built > 0 || this.s > 0) { // старая паутина медленно тает
      var gh = document.createElement("canvas"); gh.width = this.W; gh.height = this.H;
      this._build(this._moveAt(this.s) + 1);
      gh.getContext("2d").drawImage(this.layer, 0, 0);
      this.ghost = gh; this.ghostA = 1;
    }
    this._newWeb();
    this.total = o.total || 0;
    this.phase = "run";
    this._wake();
  };
  Web.prototype.progress = function (done, total, o) {
    if (this.phase === "idle" || this.phase === "done") this.phase = "run";
    if (this.phase === "paused" && (done || 0) > this.done) this.phase = "run"; // пошли новые страницы - паук ожил
    this.done = Math.max(this.done, done || 0);
    if (total) this.total = Math.max(total, this.done);
    this._retarget();
    if (o && o.instant) { this.s = this.sTarget; this.dirty = true; } // окно открыли посреди проверки: сразу на место
    this._wake();
  };
  Web.prototype.page = function (n) { this.progress(this.done + (n === undefined ? 1 : n), this.total); };
  Web.prototype._mark = function (kind) {
    if (this.phase === "idle") return;
    var m = this._currentDrawMove(), u = clamp(this.s - m.s0, 0, m.len), near = null;
    // частые ошибки подряд сливаются в один участок поярче, чтобы паутина не стала сплошь красной
    m.marks.forEach(function (k) { if (k.kind === kind && Math.abs(k.u - u) < SPOT * 1.5) near = k; });
    if (!near && m.marks.length >= (m.kind === "spiral" ? 1 : 3)) { // на нити не больше 3 участков, дальше они только ярче
      m.marks.forEach(function (k) { if (!near || Math.abs(k.u - u) < Math.abs(near.u - u)) near = k; });
      if (near.kind === "warn" && kind === "err") near.kind = "err";
    }
    if (near) near.n++; else m.marks.push({ kind: kind, u: u, n: 1 });
    this.dirty = true;
    if (this.time - this.lastFlash > 0.15) { // вспышек не больше ~6 в секунду
      this.lastFlash = this.time;
      this.flashes.push({ m: m, kind: kind, t0: this.time, u: Math.min(m.len, this.s - m.s0) });
      if (this.flashes.length > 12) this.flashes.shift();
    }
    this._wake();
  };
  Web.prototype.error = function () { this._mark("err"); };
  Web.prototype.warning = function () { this._mark("warn"); };
  Web.prototype.pause = function () { if (this.phase === "run") this.phase = "paused"; this._wake(); };
  Web.prototype.resume = function () { if (this.phase === "paused") this.phase = "run"; this._wake(); };
  Web.prototype.finish = function (o) {
    if (this.phase === "idle") return;
    if (!o || o.complete !== false) { // доплетает оставшееся секунды за три, сколько бы ни осталось
      this.sTarget = this.web.pathLen; this.phase = "finishing";
      this.finishV = Math.max(1.6, (this.web.pathLen - this.s) / 3);
    }
    else this._goHome();
    this._wake();
  };
  Web.prototype.reset = function () { this.ghost = null; this._newWeb(); this.phase = "idle"; this._wake(); };
  Web.prototype.setOptions = function (o) {
    for (var k in o) this.opt[k] = o[k];
    this.W = 0; this._resize(); this._wake();
  };
  Web.prototype.destroy = function () {
    cancelAnimationFrame(this.raf); this.raf = 0;
    document.removeEventListener("visibilitychange", this._onVis);
    window.removeEventListener("resize", this._onVis);
    if (this._ro) this._ro.disconnect();
    if (this._io) this._io.disconnect();
    instances.splice(instances.indexOf(this), 1);
  };

  Web.prototype._goHome = function () {
    var m = this.web.moves[this._moveAt(this.s)], p = pointOn(m, this.s - m.s0);
    this.home = { x: p[0], y: p[1], t0: this.time, dur: 1.2 + Math.hypot(p[0], p[1]) * 1.2 };
    this.phase = "homing";
    this.finishT = this.time;
  };

  // ---------- Наведение и нажатие ----------
  // Узлы - концы сплетённых нитей (узлы спирали, кончики лучей, углы рамки), а ещё красные и жёлтые участки.
  // Паутина декоративная, поэтому узел - это место в ходе проверки: f - доля сплетённого до него (0..1).
  // Какая там страница, решает тот, кто подключил паутину: w.onPick = function (hit, ev, clicked) {...},
  // hit = {kind: "node" | "err" | "warn", f, key} или null, когда мышь ушла с узла.
  Web.prototype._hoverInit = function () {
    var self = this, cv = this.cv;
    function at(e) { var r = cv.getBoundingClientRect(); return self._hit(e.clientX - r.left, e.clientY - r.top); }
    function set(h, e, clicked) {
      var was = self.hover;
      self.hover = h;
      if (!h !== !was || (h && was && h.key !== was.key)) self._wake();
      cv.style.cursor = h ? "pointer" : "";
      if (self.onPick) self.onPick(h, e, clicked);
    }
    cv.addEventListener("pointermove", function (e) { if (e.pointerType !== "touch") set(at(e), e, false); });
    cv.addEventListener("pointerleave", function (e) { set(null, e, false); });
    cv.addEventListener("click", function (e) { var h = at(e); if (h) set(h, e, true); });
  };

  Web.prototype._hit = function (mx, my) {
    if (this.phase === "idle" || !this.onPick) return null;
    var mv = this.web.moves, cur = this._moveAt(this.s), x = mx * this.dpr, y = my * this.dpr;
    var best = null, R = 9 * this.dpr, bd = R * R, self = this, D = this.web.drawnLen;
    function near(p, kind, d, key, w) {
      var q = self._xy(p), dd = ((q[0] - x) * (q[0] - x) + (q[1] - y) * (q[1] - y)) / w;
      if (dd < bd) { bd = dd; best = { kind: kind, f: clamp(d / D, 0, 1), key: key, x: q[0], y: q[1] }; }
    }
    for (var i = 0; i <= cur && i < mv.length; i++) {
      var m = mv[i];
      if (!m.draw) continue;
      var whole = i < cur || this.phase === "done" || this.phase === "homing";
      if (whole && Math.hypot(m.pts[m.pts.length - 1][0], m.pts[m.pts.length - 1][1]) > 0.05) // центр - не узел
        near(m.pts[m.pts.length - 1], "node", m.d0 + m.len, "n" + i, 1);
      // участок с ошибкой ловится охотнее узла рядом
      m.marks.forEach(function (k, j) { near(pointOn(m, k.u), k.kind, m.d0 + k.u, "m" + i + "." + j, 2.2); });
    }
    return best;
  };

  // ---------- Кадр ----------
  Web.prototype._wake = function () {
    if (this.raf || document.hidden || !this.visible) return;
    var self = this;
    this.last = 0;
    this.raf = requestAnimationFrame(function f(ts) { self.raf = 0; self._frame(ts); });
  };

  Web.prototype._frame = function (ts) {
    if (document.hidden || !this.visible) return;
    if (this.role === "background" && !prefs.background) { this.ctx.clearRect(0, 0, this.W, this.H); return; }
    var dt = this.last ? Math.min(0.1, (ts - this.last) / 1000) : 0;
    var fps = this.phase === "run" || this.phase === "finishing" || this.phase === "homing" || this.flashes.length || this.ghost ? 40 : 20;
    if (this.last && ts - this.last < 1000 / fps - 2) { var self0 = this; this.raf = requestAnimationFrame(function (t) { self0.raf = 0; self0._frame(t); }); return; }
    this.last = ts; this.time += dt; this._dt = dt;
    this._step(dt);
    this._draw();
    var self = this, still = this.reduce && this.phase !== "run" && this.phase !== "finishing" && this.phase !== "homing" && !this.ghost && !this.flashes.length;
    if (!still) this.raf = requestAnimationFrame(function (t) { self.raf = 0; self._frame(t); });
  };

  Web.prototype._step = function (dt) {
    if (this.ghost) { this.ghostA -= dt / 3; if (this.ghostA <= 0) this.ghost = null; }
    var self = this;
    this.flashes = this.flashes.filter(function (f) { return self.time - f.t0 < 1.4; });
    if (this.phase === "run" || this.phase === "finishing") {
      var back = this.sTarget - this.s;
      if (back > 0) {
        // чем больше отставание от проверки, тем быстрее паук; по готовым нитям бежит быстрее
        var v = clamp(back * 1.4, 0.02, 3.5);
        if (this.phase === "finishing") v = Math.max(v, this.finishV);
        var m = this.web.moves[this._moveAt(this.s)];
        if (!m.draw) v *= 2.5;
        var prev = this._moveAt(this.s);
        this.s = Math.min(this.sTarget, this.s + v * dt);
        if (this._moveAt(this.s) !== prev) this.dirty = true;
      }
      if (this.phase === "finishing" && this.s >= this.web.pathLen - 1e-6) this._goHome();
    }
    if (this.phase === "homing" && this.time - this.home.t0 >= this.home.dur) this.phase = "done";
    if (this.dirty && this.time - this.lastBuild > 0.12) this._build(this._moveAt(this.s));
  };

  Web.prototype._spiderPos = function () {
    if (this.phase === "homing" || this.phase === "done") {
      var h = this.home, t = clamp((this.time - h.t0) / h.dur, 0, 1), e = t * t * (3 - 2 * t);
      return [h.x * (1 - e), h.y * (1 - e), Math.atan2(-h.y, -h.x), t >= 1];
    }
    if (this.phase === "idle") return [0, 0, -Math.PI / 2, true];
    var m = this.web.moves[this._moveAt(this.s)], p = pointOn(m, this.s - m.s0);
    return [p[0], p[1], p[2], false];
  };

  Web.prototype._draw = function () {
    var g = this.ctx, W = this.W, H = this.H, t = this.time, lw = this.lw;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "source-over"; g.globalAlpha = 1;
    if (this.opt.backdrop) {
      if (!this._bg) {
        var bg = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.75);
        bg.addColorStop(0, "#0d1b3d"); bg.addColorStop(0.55, "#081330"); bg.addColorStop(1, "#040a1c");
        this._bg = bg;
      }
      g.fillStyle = this._bg; g.fillRect(0, 0, W, H);
    } else g.clearRect(0, 0, W, H);

    var done = this.web.drawnLen ? clamp(this.dTarget / this.web.drawnLen, 0, 1) : 0;
    var fin = this.finishT >= 0 ? Math.max(0, 1 - (t - this.finishT) / 1.6) : 0;

    // мягкое свечение у центра, растёт вместе с паутиной
    var gl = 0.10 + 0.22 * done + 0.35 * fin;
    var cg = g.createRadialGradient(this.cx, this.cy, 0, this.cx, this.cy, this.R * 0.55);
    cg.addColorStop(0, "rgba(120,190,255," + gl + ")"); cg.addColorStop(1, "rgba(120,190,255,0)");
    g.fillStyle = cg; g.fillRect(0, 0, W, H);

    // лёгкое покачивание, сильнее в простое
    var calm = this.phase === "run" ? 0.4 : 1, sway = this.reduce ? 0 : calm;
    var rot = Math.sin(t * 0.55) * 0.006 * sway, sc = 1 + Math.sin(t * 0.8 + 1) * 0.005 * sway;
    var ox = this.cx, oy = this.cy - this.Ry * 1.1; // качается как подвешенная сверху
    g.translate(ox, oy); g.rotate(rot); g.scale(sc, sc); g.translate(-ox, -oy);

    if (this.ghost) { g.globalAlpha = Math.max(0, this.ghostA) * 0.8; g.drawImage(this.ghost, 0, 0); g.globalAlpha = 1; }
    g.drawImage(this.layer, 0, 0);
    if (fin > 0) { g.globalCompositeOperation = "lighter"; g.globalAlpha = fin * 0.9; g.drawImage(this.layer, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = "source-over"; }

    // нити, сплетённые после последней перерисовки слоя, и та, что плетётся сейчас
    var cur = this._moveAt(this.s), mv = this.web.moves, live = [], self = this;
    if (this.phase !== "idle") {
      for (var i = Math.max(0, this.built); i <= cur && i < mv.length; i++) if (mv[i].draw) live.push(mv[i]);
      g.globalCompositeOperation = "lighter"; g.lineCap = "round";
      var curM = mv[cur];
      this._strokeSet(g, live, COLORS.glow, COLORS.core, lw * 4, lw * 0.9, { m: curM, u: this.s - curM.s0 });
      this._drawMarks(g, live.filter(function (m) { return m.marks.length; }));
      // кончик свежей нити светится ярче
      if (curM.draw && (this.phase === "run" || this.phase === "finishing")) {
        var tip = this._xy(pointOn(curM, this.s - curM.s0)), dot = glowDot(Math.round(lw * 9), "rgba(190,230,255,0.8)");
        g.drawImage(dot, tip[0] - dot.width / 2, tip[1] - dot.height / 2);
      }
    }

    // вспышки ошибок и предупреждений
    this.flashes.forEach(function (f) {
      var k = 1 - (t - f.t0) / 1.4, err = f.kind === "err", a = k * k * (err ? 1 : 0.6);
      g.globalAlpha = a;
      g.beginPath(); self._pathRange(g, f.m, f.u - SPOT * 2.5, f.u + SPOT * 2.5);
      g.strokeStyle = err ? "rgba(255,50,70,0.55)" : "rgba(255,180,60,0.4)"; g.lineWidth = lw * (err ? 9 : 6); g.stroke();
      g.strokeStyle = err ? "rgba(255,190,195,1)" : "rgba(255,225,170,0.9)"; g.lineWidth = lw * 1.6; g.stroke();
      var p = self._xy(pointOn(f.m, f.u)), r = Math.round(lw * (err ? 16 : 10) * (1.3 - k * 0.3));
      var sp = glowDot(r, err ? "rgba(255,90,100,0.9)" : "rgba(255,200,90,0.8)");
      g.drawImage(sp, p[0] - sp.width / 2, p[1] - sp.height / 2);
    });
    g.globalAlpha = 1; g.globalCompositeOperation = "source-over";

    // узел или участок под мышью - кольцом
    if (this.hover && this.phase !== "idle") {
      var hc = this.hover.kind === "err" ? "rgba(255,120,130,0.95)" : this.hover.kind === "warn" ? "rgba(255,205,110,0.95)" : "rgba(215,240,255,0.95)";
      g.beginPath(); g.arc(this.hover.x, this.hover.y, 6 * this.dpr, 0, Math.PI * 2);
      g.strokeStyle = hc; g.lineWidth = 1.5 * this.dpr; g.stroke();
    }

    // паучок
    if (this.opt.spider && prefs.spider && (this.phase !== "idle" || this.ghost)) {
      var sp2 = this._spiderPos(), pos = this._xy(sp2);
      if (!this._sprite) this._sprite = bakeSprite(Math.round(this.R * 0.27));
      var want = sp2[2], d = Math.atan2(Math.sin(want - this.heading), Math.cos(want - this.heading));
      if (this.phase !== "paused" && !(sp2[3] && this.phase === "done")) this.heading += d * Math.min(1, 0.25);
      // шаг идёт от пройденного пути: бежит быстро - лапки чаще, стоит - лапки встают ровно
      var lp = this._lastPos, moved = lp ? Math.hypot(pos[0] - lp[0], pos[1] - lp[1]) : 0;
      this._lastPos = pos;
      var stride = this._sprite.c.width * 0.45; // путь за один шаг, в пикселях
      if (moved > 0.05 && moved < stride * 3) this.stepF = (this.stepF || 0) + moved / stride;
      else if (this.stepF) { // встал: лапки доводятся до ровной позы (каждые полшага - ровная)
        var near = Math.round(this.stepF * 2) / 2;
        this.stepF += clamp(near - this.stepF, -this._dt * 2, this._dt * 2);
      }
      var fr = this._sprite.frames, img = this._sprite.c, bob = 0;
      if (fr) img = fr[((Math.round((this.stepF || 0) * fr.length) % fr.length) + fr.length) % fr.length];
      else if (this.phase !== "done" && this.phase !== "paused") bob = Math.sin(t * 18) * 0.025; // без лапок по частям - покачивание
      g.save(); g.translate(pos[0], pos[1]); g.rotate(this.heading - Math.PI / 2 + bob);
      g.drawImage(img, -this._sprite.half, -this._sprite.half); g.restore();
    }
    g.setTransform(1, 0, 0, 1, 0, 0);
  };

  window.ClaylerWeb = {
    create: function (canvas, opt) { return new Web(canvas, opt); },
    getPrefs: function () { return { background: prefs.background, spider: prefs.spider }; },
    setPrefs: function (p) {
      for (var k in p) prefs[k] = !!p[k];
      try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch (e) { /* без хранилища - только до перезагрузки */ }
      instances.forEach(function (w) { w._wake(); });
    }
  };
})();
