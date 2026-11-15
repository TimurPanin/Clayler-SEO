// Горячие клавиши окна (29.10.2026, по просьбе пользователя: «чтобы не тыкать много раз по кнопкам»).
// Одна буква или цифра, без Ctrl и Alt. Не срабатывают, пока курсор в поле ввода и пока открыто окошко (кроме «?»).
// Клавиша по физическому месту (e.code): работает и в русской раскладке (S = «Ы», [ = «Х»).
// Подключается на всех страницах окна после side.js; «?» - окошко со списком, строка «Горячие клавиши» внизу меню.
(() => {
  const KEYS = [
    ['/', 'Найти сайт (как Ctrl+K)'],
    ['1 … 9', 'Пункты меню слева по порядку'],
    ['T', 'Техничка'], ['S', 'Семантика'],
    ['N', 'Новая проверка: курсор в поле адреса сайта'],
    ['O', 'Открыть отчёт или семантику последней проверки'],
    ['R', 'После «Остановить»: «Обновить отчёт ещё раз» или «Дообойти»'],
    ['X', 'Остановить идущую проверку (сначала спросит)'],
    ['G', 'Семантика: «Собрать заново»'],
    ['[  ]', 'Семантика: предыдущая и следующая вкладка'],
    ['?', 'Это окошко'], ['Esc', 'Закрыть окошко'],
  ];
  const $ = id => document.getElementById(id);
  const shown = el => el && !el.hidden && !el.disabled && el.offsetParent !== null;
  const press = el => { if (!shown(el)) return false; el.click(); return true; };
  const typing = t => t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

  let dlg = null;
  function help(){
    if (!dlg) {
      dlg = document.createElement('dialog');
      dlg.id = 'kHelp';
      dlg.innerHTML = `<h2>Горячие клавиши</h2>
        <p class="mut">Работают на всех страницах окна, кроме моментов, когда курсор стоит в поле ввода. Буквы - и в русской раскладке.</p>
        <table class="k-help">${KEYS.map(([k, t]) => `<tr><td>${k.split(/\s+/).map(x => x === '…' ? '…' : `<kbd>${x}</kbd>`).join(' ')}</td><td>${t}</td></tr>`).join('')}</table>
        <div class="dlg-btns"><button type="button" id="kHelpClose">Закрыть</button></div>`;
      document.body.appendChild(dlg);
      $('kHelpClose').onclick = () => dlg.close();
      dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
    }
    if (dlg.open) dlg.close(); else dlg.showModal();
    return true;
  }

  function newCheck(){
    if ($('site') && window.showView) {
      window.showView('home');
      setTimeout(() => { $('site').focus(); $('site').select(); }, 0);
    } else {
      location.href = '/';   // с «Семантики» и «Словаря» - на главную, к форме проверки
    }
    return true;
  }

  function stop(){
    const b = [$('stop'), $('semStop')].find(shown);
    if (!b) return false;
    if (confirm('Остановить идущую проверку? Отчёт соберётся по тому, что успели проверить.')) b.click();
    return true;
  }

  function tab(step){
    const T = [...document.querySelectorAll('.sem-tabs a[data-v]')].filter(shown);
    if (!T.length) return false;
    const i = T.findIndex(a => a.classList.contains('on'));
    T[(i + step + T.length) % T.length].click();
    return true;
  }

  function nav(n){
    const items = [...document.querySelectorAll('#side .nav-group .nav')].filter(shown);
    return items[n - 1] ? (items[n - 1].click(), true) : false;
  }

  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.repeat || typing(e.target)) return;
    // «?» в русской раскладке - Shift+7, поэтому смотрим и сам знак; цифры с Shift - не переход по меню (проверка кода 29.10.2026)
    const c = e.code, isHelp = e.key === '?' || (c === 'Slash' && e.shiftKey);
    if (document.querySelector('dialog[open]') && !(isHelp && dlg && dlg.open)) return;
    let done = false;
    if (isHelp) done = help();
    else if (c === 'Slash') done = press($('kFind'));
    else if (/^Digit[1-9]$/.test(c) && !e.shiftKey) done = nav(+c.slice(5));
    else if (c === 'KeyT') done = press(document.querySelector('.room-b[data-room="tech"]'));
    else if (c === 'KeyS') done = press(document.querySelector('.room-b[data-room="sem"]'));
    else if (c === 'KeyN') done = newCheck();
    else if (c === 'KeyO') done = press($('open'));
    else if (c === 'KeyR') done = press($('cont'));
    else if (c === 'KeyX') done = stop();
    else if (c === 'KeyG') done = press($('semGo'));
    else if (c === 'BracketLeft' || c === 'BracketRight') done = tab(c === 'BracketRight' ? 1 : -1);
    if (done) e.preventDefault();
  });

  // строка внизу меню слева, над «Настройками»
  const foot = document.querySelector('#side .side-foot');
  if (foot) {
    const b = document.createElement('button');
    b.className = 'conn'; b.type = 'button'; b.id = 'kHelpBtn';
    b.title = 'Список горячих клавиш (клавиша ?)';
    b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h1M11 10h2M16 10h1M8 14h8"/></svg><span>Горячие клавиши</span><small>?</small>';
    b.onclick = help;
    const set = foot.querySelector('#sideSet');
    foot.insertBefore(b, set || null);
  }
})();
