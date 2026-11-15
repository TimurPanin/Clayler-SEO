const $ = id => document.getElementById(id);
let wasRunning = false;
// главная в рамке поверх другой страницы (side.js, ?embed=1): видно только окошко, «Закрыть» убирает рамку
const EMBED = new URLSearchParams(location.search).has('embed');
if (EMBED) document.documentElement.classList.add('embed');
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function fmtTime(s){const h=Math.floor(s/3600), m=Math.floor(s%3600/60), r=s%60; return h ? `${h} ч ${m} мин` : m ? `${m} мин ${r} с` : `${r} с`}
// localStorage бывает недоступен: тогда просто не запоминаем
const store = {get(k){ try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v){ try { localStorage.setItem(k, v); } catch (e) {} }};
$('site').addEventListener('input',()=>{$('err').textContent=''});
// «Что проверить»: весь сайт, только раздел или свой список адресов
const mode = () => (document.querySelector('input[name=mode]:checked') || {}).value || 'site';
const MODE_HINT = {site: 'Обход по ссылкам, начиная с главной.',
  section: 'Проверятся только страницы, адрес которых начинается так же (site.ru/catalog/). Ссылки из раздела на остальной сайт не открываются.',
  list: 'Полная проверка только вставленных адресов, без обхода по ссылкам.'};
function showMode(){
  const m = mode();
  $('listBox').hidden = m !== 'list'; $('siteRow').hidden = m === 'list'; $('compBox').hidden = m === 'list';
  $('siteLabel').textContent = m === 'section' ? 'Адрес раздела' : 'Адрес сайта';
  $('site').placeholder = m === 'section' ? 'https://example.ru/catalog/' : 'https://example.ru';
  $('modeHint').textContent = MODE_HINT[m];
  $('err').textContent = '';
}
document.querySelectorAll('input[name=mode]').forEach(r => r.addEventListener('change', showMode)); showMode();
// Конкуренты чипами: сами адреса по-прежнему лежат в скрытом поле #competitors, по одному в строке
function compList(){ return $('competitors').value.split('\n').map(x => x.trim()).filter(Boolean); }
function compRender(){
  $('compChips').querySelectorAll('.cchip').forEach(x => x.remove());
  compList().forEach((u, i) => $('compAdd').insertAdjacentHTML('beforebegin',
    `<span class="cchip">${esc(host(u))}<button type="button" data-comp-del="${i}" aria-label="Убрать ${esc(host(u))}">×</button></span>`));
  $('compAdd').hidden = compList().length >= 5;
}
function compAdd(text){
  const cur = compList();
  String(text || '').split(/[\s,;]+/).map(x => x.trim()).filter(x => /\S+\.\S+/.test(x)).forEach(u => {
    if (cur.length < 5 && !cur.some(c => host(c) === host(u))) cur.push(u); });
  $('competitors').value = cur.join('\n'); compRender();
}
$('compAdd').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); compAdd($('compAdd').value); $('compAdd').value = ''; }
  if (e.key === 'Backspace' && !$('compAdd').value && compList().length) { $('competitors').value = compList().slice(0, -1).join('\n'); compRender(); }
});
$('compAdd').addEventListener('blur', () => { if ($('compAdd').value.trim()) { compAdd($('compAdd').value); $('compAdd').value = ''; } });
$('compAdd').addEventListener('paste', e => { e.preventDefault(); compAdd(e.clipboardData.getData('text')); });
$('compChips').addEventListener('click', e => {
  const b = e.target.closest('[data-comp-del]'); if (b) { const l = compList(); l.splice(+b.dataset.compDel, 1); $('competitors').value = l.join('\n'); compRender(); return; }
  if (e.target === $('compChips')) $('compAdd').focus();
});
// строка под «Дополнительными настройками»: что сейчас выбрано, чтобы не раскрывать
function advSum(){
  const parts = [$('speed').selectedOptions[0].textContent.split(' (')[0].replace('Обычная', 'обычная скорость').replace('Бережно', 'бережно').replace('Быстро', 'быстро'),
    'как ' + ($('seenAs').value === 'custom' ? 'своя настройка' : $('seenAs').selectedOptions[0].textContent.replace('Обычный посетитель', 'посетитель').replace('Программа аудита', 'программа аудита'))];
  if ($('regions').checked) parts.push('с городами');
  if ($('subdomains').checked) parts.push('с поддоменами');
  if ($('no_external').checked) parts.push('без внешних ссылок');
  if ($('ignore_robots').checked) parts.push('без robots.txt');
  const skip = $('skip').value.split('\n').filter(s => s.trim().replace(/\*/g, '')).length;
  if (skip) parts.push(`не обходить: ${skip} ${skip === 1 ? 'маска' : skip < 5 ? 'маски' : 'масок'}`);
  $('advSum').textContent = '· ' + parts.join(' · ');
}
$('adv').addEventListener('change', advSum);
// «Проверять как»: один выбор вместо двух списков; «Своя настройка» открывает оба старых списка
const SEEN_AS = {
  yandex:  {ua:'yandexbot', robots:'yandex',    hint:'Представляется роботом Яндекса и соблюдает правила robots.txt для Яндекса.'},
  google:  {ua:'googlebot', robots:'googlebot', hint:'Представляется роботом Google и соблюдает правила robots.txt для Google.'},
  visitor: {ua:'chrome',    robots:'yandex',    hint:'Представляется браузером Chrome, как обычный человек. Запреты robots.txt берутся для Яндекса.'},
  crawler: {ua:'',          robots:'googlebot', hint:'Честно называет себя программой аудита. Запреты robots.txt берутся для Google.'},
  custom:  {hint:'Выберите отдельно, кем представляться и чьи правила robots.txt соблюдать.'},
};
function showSeenAs(){
  const v = $('seenAs').value, o = SEEN_AS[v] || SEEN_AS.yandex;
  $('customAs').hidden = v !== 'custom'; $('seenAsHint').textContent = o.hint;
}
$('seenAs').addEventListener('change', showSeenAs); showSeenAs(); advSum();
function seenAs(){
  const v = $('seenAs').value, o = SEEN_AS[v];
  return v === 'custom' || !o ? {robots:$('robots').value, ua:$('ua').value} : {robots:o.robots, ua:o.ua};
}
$('go').onclick = async () => {
  const m = mode();
  const site = $('site').value.trim();
  if (m === 'list') {
    if (!/https?:\/\/\S+/.test($('urls').value)) { $('err').textContent = 'Вставьте полные адреса, начинающиеся с https://'; $('urls').focus(); return; }
  } else {
    if (!site) { $('err').textContent = m === 'section' ? 'Введите адрес раздела, например https://example.ru/catalog/' : 'Введите адрес сайта, например https://example.ru'; $('site').focus(); return; }
    if (!/^(https?:\/\/)?[^\s\/]+\.[^\s]+/.test(site)) { $('err').textContent = 'Не похоже на адрес сайта. Пример: https://example.ru'; return; }
    if (m === 'section' && !/^(https?:\/\/)?[^\s\/]+\/\S/.test(site)) { $('err').textContent = 'Впишите адрес раздела целиком, например https://example.ru/catalog/'; return; }
  }
  $('err').textContent = '';
  const body = {site, mode:m, urls:m === 'list' ? $('urls').value : '', competitors:m === 'list' ? '' : $('competitors').value, pages:+$('pages').value, js:$('js').checked, resume:$('resume').checked,
    speed:$('speed').value, ...seenAs(),
    ignore_robots:$('ignore_robots').checked, subdomains:$('subdomains').checked, regions:$('regions').checked, no_external:$('no_external').checked, skip:$('skip').value};
  const r = await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j = await r.json(); if (!r.ok) { $('err').textContent = j.error || 'Не получилось запустить'; return; }
  poll();
};
$('stop').onclick = async () => { $('stop').disabled = true; $('stop').textContent = 'Останавливаю…'; await fetch('/api/stop',{method:'POST'}); };
$('cont').onclick = async () => {   // после «Остановить»: то же действие с того же места (кнопка в карточке проверки)
  const b = $('cont');
  if (!b.dataset.rebuild) { resumeCheck(b.dataset.f); return; }
  b.disabled = true;
  if (await post('/api/rebuild', {folder: b.dataset.f, site: b.dataset.site, again: true})) poll();
  b.disabled = false;
};
// События для модуля паутины (свои файлы, подключаются отдельно): window 'clayler:crawl',
// detail.type: start / page (detail.delta - сколько новых страниц) / warning / pause / error / end / reset
function webEvent(type, extra){ try { window.dispatchEvent(new CustomEvent('clayler:crawl', {detail: Object.assign({type}, extra || {})})); } catch (e) {} }
let pollTimer = 0, lastPages = null, warned = false, formFoldAuto = true;
function logNum(line, re){ const m = re.exec(line || ''); return m ? +m[1].replace(/[^\d]/g, '') : null; }
function speedRu(v){ return String(Math.round(v * 10) / 10).replace('.', ','); }
// «Память: программа 0,4 ГБ · браузер 0,5 ГБ · свободно 17 ГБ · процессор 23% (проверка 8%)»
function resText(r){
  const sz = mb => mb >= 1024 ? (mb / 1024).toLocaleString('ru', {maximumFractionDigits: 1}) + ' ГБ' : Math.round(mb) + ' МБ';
  const parts = ['Память: программа ' + sz(r.prog_mb)];
  if (r.browser_mb >= 20) parts.push('браузер ' + sz(r.browser_mb));   // меньше - служебный процесс Windows, не браузер
  if (r.free_mb != null) parts.push(r.free_mb < 3000 ? `<span class="low" title="Если свободной памяти останется меньше 1,5 ГБ, проверка сама остановится - её можно будет продолжить">свободно ${sz(r.free_mb)}</span>` : 'свободно ' + sz(r.free_mb));
  if (r.cpu != null) parts.push(`процессор ${r.cpu}%` + (r.prog_cpu != null ? ` (проверка ${r.prog_cpu}%)` : ''));
  return parts.join(' · ');
}
// «Сайт 1 из 2 (ваш сайт): https://… - Шаг 3 из 4: …» → номер сайта и сам шаг
function splitStep(step){
  const m = /^Сайт (\d+) из (\d+) \(([^)]+)\): (\S+) - (.*)$/.exec(step || '');
  return m ? {n: +m[1], total: +m[2], who: m[3], url: m[4], step: m[5]} : {n: 0, total: 0, step: step || ''};
}
// полоса из 4 шагов: robots.txt, sitemap, обход, проверки и отчёт; заполнение - по общей доле s.overall
function showSteps(s, step){
  let cur = 0, frac = 0;
  const m = /Шаг (\d) из 4/.exec(step);
  if (s.overall != null) {
    const o = s.overall;
    if (o < 1 && !(m && +m[1] > 1)) { cur = 1; frac = .5; } else if (o < 2) { cur = 2; frac = .5; }
    else if (o < 85) { cur = 3; frac = (o - 2) / 83; } else { cur = 4; frac = (o - 85) / 15; }
  } else if (m) { cur = +m[1]; frac = .5; }
  else if (/отчёт|Готово|Замеряю|Перемеряю|Проверяю|Сравниваю|Открываю/.test(step)) { cur = 4; frac = .5; }
  if (!s.running && s.report && !s.stopped) { cur = 5; }
  [...$('steps').children].forEach((li, i) => {
    const k = i + 1;
    li.className = k < cur ? 'done' : k === cur ? 'now' : '';
    li.querySelector('b').style.width = k < cur ? '100%' : k === cur ? Math.max(4, Math.min(100, frac * 100)).toFixed(1) + '%' : '0';
  });
}
function tile(v, label, cls, tip){ return v == null ? '' : `<div class="tile${cls ? ' ' + cls : ''}"${tip ? ` title="${esc(tip)}"` : ''}><b>${v}</b><span>${label}</span></div>`; }
async function poll(){
  clearTimeout(pollTimer);
  let s; try { s = await (await fetch('/api/status')).json(); } catch (e) { pollTimer = setTimeout(poll, 5000); return; }
  if (s.running && !wasRunning) { webEvent('reset'); webEvent('start', {site: s.site}); lastPages = null; warned = false; }
  if (s.started) $('run').hidden = false;
  $('go').disabled = s.running; $('goNote').hidden = !s.running;
  // форму можно свернуть, пока идёт проверка; сама сворачивается при старте, если её не раскрывали руками
  $('formFold').hidden = !s.running;
  if (s.running && formFoldAuto && store.get('formOpen') !== '1') foldForm(true);
  if (!s.running) foldForm(false);
  const sp = splitStep(s.step), crawl = !s.rebuild && !s.semantics && /^(Шаг|Запускаю|Собираю отчёт|Замеряю|Перемеряю|Проверяю|Сравниваю, что|Открываю|Определяю|Загружаю)/.test(sp.step || 'Запускаю');
  const kick = $('runKicker');
  kick.className = 'kicker' + (s.running ? '' : s.stopped ? ' stopped' : (s.report || s.result || s.semantics || s.competitors) ? ' done' : ' fail');
  kick.querySelector('span').textContent = s.running ? (s.rebuild ? 'Обновляю отчёт' : s.runs ? `Идёт проверка · ${s.runs.length} ${plural(s.runs.length, 'сайт', 'сайта', 'сайтов')} одновременно` : sp.total ? `Идёт проверка · сайт ${sp.n} из ${sp.total}` : 'Идёт проверка')
    : s.stopped ? 'Остановлено' : (s.report || s.result || s.semantics || s.competitors) ? 'Готово' : 'Не закончилась';
  $('runSite').textContent = host(sp.url || s.site) || 'Проверка';
  $('step').textContent = s.running ? (sp.step || 'Запускаю…') :
    (s.stopped ? (s.rebuild ? 'Остановлено. Отчёт обновлён не до конца: нажмите «Обновить отчёт ещё раз»'
                  : s.report ? 'Остановлено. Отчёт собран по тому, что успели проверить' : 'Остановлено')
               : (s.report || s.result ? 'Готово' : s.semantics ? 'Семантика собрана' : 'Проверка не закончилась, посмотрите подробный журнал'));
  // цифры из последней строки прогресса в журнале: «Страниц сайта: … | картинок и файлов: … | внешних ссылок: … | ждут проверки: … | 3.1 адр/с»
  // при одновременной проверке - строка вашего сайта (s.prog_line): в общем журнале пишут и конкуренты
  const pl = s.prog_line != null ? s.prog_line : [...(s.log || [])].reverse().find(l => l.includes('Страниц сайта:')) || '';
  const speed = s.speed != null ? s.speed : (() => { const m = /([\d.]+) адр\/с/.exec(pl); return m ? +m[1] : null; })();
  $('meta').textContent = s.running ? 'Идёт ' + fmtTime(s.elapsed || 0) + (speed && /Шаг 3/.test(sp.step) ? ` · ${speedRu(speed)} ${Number.isInteger(Math.round(speed * 10) / 10) ? plural(speed, 'адрес', 'адреса', 'адресов') : 'адреса'} в секунду` : '')
    : (s.elapsed ? 'Заняла ' + fmtTime(s.elapsed) : '');
  // память и процессор проверки (seocrawler/memory.py): видно без Диспетчера задач, не растёт ли память
  const rs = s.running && s.res && s.res.prog_mb != null ? s.res : null;
  $('resLine').hidden = !rs;
  if (rs) $('resLine').innerHTML = resText(rs);
  $('steps').hidden = !crawl; $('pbar').hidden = crawl || !s.running;
  if (crawl) showSteps(s, sp.step);
  if (s.running && s.overall != null) $('bar').style.width = s.overall + '%';
  else if (s.running && s.progress) $('bar').style.width = Math.min(100, s.progress[0] / s.progress[1] * 100) + '%';
  // плитки с цифрами
  const pages = s.progress ? s.progress[0] : s.done_pages, waiting = s.waiting != null ? s.waiting : logNum(pl, /ждут проверки: ([\d\s  ]+)/);
  const eta = s.running && waiting && speed > 0 ? ' · ≈ ' + fmtTime(Math.round(waiting / speed)).replace(/ \d+ с$/, '') : '';
  $('tiles').innerHTML = !crawl && !s.progress ? '' : [
    s.report_pct != null ? tile(s.report_pct + '%', 'отчёта собрано', 'acc', 'Сборка отчёта: поиск проблем, файлы для клиента, Excel')
      : tile(pages != null ? num(pages) : null, s.progress && s.running ? `страниц проверено из ${num(s.progress[1])}` : 'страниц проверено'),
    tile(s.running && !s.own_done && waiting != null ? num(waiting) : null, 'в очереди' + eta, '', 'Адреса, которые ждут проверки: страницы, картинки, ссылки. Время примерное, по нынешней скорости'),
    tile(logNum(pl, /картинок и файлов: ([\d\s  ]+)/) != null ? num(logNum(pl, /картинок и файлов: ([\d\s  ]+)/)) : null, 'картинок и файлов'),
    tile(logNum(pl, /внешних ссылок: ([\d\s  ]+)/) != null ? num(logNum(pl, /внешних ссылок: ([\d\s  ]+)/)) : null, 'ссылок на другие сайты'),
    tile(logNum(pl, /фото с других сайтов: ([\d\s  ]+)/) != null ? num(logNum(pl, /фото с других сайтов: ([\d\s  ]+)/)) : null, 'фото с других сайтов'),
    // с конкурентами - доля по всем сайтам (s.overall_all): раньше ваш законченный сайт давал 100 %, хотя конкурент шёл
    tile(s.running && (s.overall_all != null ? s.overall_all : s.overall) != null ? Math.min(s.overall_all != null ? 99 : 100, Math.floor(s.overall_all != null ? s.overall_all : s.overall)) + '%' : null,
      'всей проверки сделано', 'acc', s.runs ? 'Ваш сайт и конкуренты вместе: обход, дополнительные проверки и отчёты' : 'После обхода ещё дополнительные проверки и отчёт: процент считает всё вместе'),
  ].join('');
  // пояснение под цифрами
  let txt = '';
  if (s.progress) { const [d,t]=s.progress;
    txt = sp.step === 'Проверяю адреса' ? `Проверено адресов: ${num(d)} из ${num(t)}.` :
      s.unit === 'sitemap' ? `Проверено адресов из sitemap: ${num(d)} из ${num(t)}. Обход сайта уже закончен, это забытые страницы из sitemap.` :
      s.unit === 'search' ? `Проверено адресов из Яндекс Вебмастера и Search Console: ${num(d)} из ${num(t)}. Это страницы, которые знает поиск, а ссылок на них при обходе не нашлось.` :
      s.unit === '' ? `Обход закончен: проверено страниц сайта ${num(d)}. Идут дополнительные проверки (телефон, скорость, дубли адресов), потом соберётся отчёт.` :
      s.unit === 'regions' ? `Ищу городские версии сайта: проверено городов ${num(d)} из ${num(t)}. Если первые 12 не найдутся, поиск закончится сам, потом начнётся обход.` :
      s.unit === 'probe' ? `Закрытых страниц навигации открыто: ${num(d)} из ${num(t)}. Ищу, где на сайте стоят забытые страницы из sitemap.` :
      s.unit === 'slow' ? `Перемерено: ${num(d)} из ${num(t)} медленных страниц. Обход уже закончен, после этого соберётся отчёт.` :
      s.limit_hit ? `Лимит ${num(t)} страниц набран. Допроверяю картинки и ссылки с уже проверенных страниц` + (s.waiting ? `, ждут ещё ${num(s.waiting)}` : '') + `. Потом шаг 4, дополнительные проверки и отчёт.` :
      '';
    if (s.running && s.stuck >= 300) txt = `⚠ Уже ${fmtTime(s.stuck)} не закончилась проверка ни одного адреса. Сайт мог перестать отвечать. `
      + `В подробном журнале видно, какие адреса загружаются. Кнопка «Остановить» соберёт отчёт по уже проверенному.`;
    else if (s.running && s.idle >= 120 && s.pause_note) txt += ` Новых страниц нет ${fmtTime(s.idle)}, но работа идёт: ${s.pause_note}.`;
    else if (s.running && s.idle >= 300) txt = `⚠ Число страниц не меняется уже ${fmtTime(s.idle)}. Программа может проверять картинки, файлы и ссылки на другие сайты, это нормально. `
      + `Если так остаётся долго, откройте подробный журнал: там видно, какие адреса загружаются. Кнопка «Остановить» соберёт отчёт по уже проверенному.`;
    else if (s.running && s.idle_note) txt += ` Последняя страница ${s.idle_note} назад.`;
    // сайт отвечает через раз (crawler/shaky.py): программа сама на паузе или идёт медленнее - это не зависание
    if (s.running && s.shaky_note) txt = `⚠ ${s.shaky_note[0].toUpperCase() + s.shaky_note.slice(1)}. Адреса без ответа проверю ещё раз, делать ничего не нужно.`; }
  if (s.running && s.report_pct != null) txt = `Обход закончен, отчёт собран на ${s.report_pct}%.`;
  if (s.running && s.rebuild) txt = 'Сайт заново не обходится: программа собирает отчёт новой версией по уже проверенным страницам.'
    + (s.report_pct != null ? ` Отчёт собран на ${s.report_pct}%.` : s.overall != null ? ` Сделано ≈ ${Math.floor(s.overall)}%.` : '');
  if (!s.running && s.report) { if (!s.stopped) $('bar').style.width = '100%';
    if (s.site_pages && s.site_pages.length > 1)
      txt = 'Проверено страниц: ' + s.site_pages.map(([u,n]) => `${host(u)}: ${num(n)}`).join(', ') + '.';
    else txt = ''; }
  $('ptext').textContent = txt.trim();
  // «Дальше: конкурент»
  const nx = $('nextUp');
  if (s.running && sp.total && sp.n < sp.total) {
    const rest = (s.sites || []).slice(sp.n).map(host);
    nx.innerHTML = `<b>Дальше:</b> ${rest.length ? esc(rest.join(', ')) : `ещё ${sp.total - sp.n} ${plural(sp.total - sp.n, 'сайт', 'сайта', 'сайтов')}`} (${sp.total - sp.n > 1 ? 'конкуренты' : 'конкурент'}), начнётся автоматически, потом сравнение с вашим сайтом`;
    nx.hidden = false;
  } else nx.hidden = true;
  const log = $('log'); const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
  log.textContent = (s.log || []).join('\n'); if (atBottom) log.scrollTop = log.scrollHeight;
  $('stop').hidden = !s.running; if (s.running){ $('stop').disabled=!!s.stopping; $('stop').textContent=s.stopping ? 'Останавливаю…' : 'Остановить'; }
  const open = $('open');
  open.hidden = !s.report && !s.semantics && !s.result; open.removeAttribute('target');
  if (s.semantics) { open.href = '/semantics?f=' + encodeURIComponent(s.semantics); open.textContent = 'Открыть семантику →'; }
  if (s.result) { open.href = '/r/' + s.result.split('/').map(encodeURIComponent).join('/'); open.target = '_blank'; open.textContent = 'Открыть результат →'; }
  if (s.report) { open.href = '/r/' + encodeURIComponent(s.report) + '/отчёт.html'; open.target = '_blank'; open.textContent = 'Открыть отчёт →'; }
  // остановили - продолжить одной кнопкой: «Обновить отчёт» ещё раз или «Дообойти» с того же места
  const cont = $('cont');
  $('stop').dataset.site = s.site || '';   // «Журнал» (notify.js): нажатие «Остановить» - с названием сайта, а не «-»
  cont.hidden = s.running || !s.stopped || !s.report || !['crawl', 'rebuild'].includes(s.kind);
  if (!cont.hidden) {
    cont.textContent = s.rebuild ? 'Обновить отчёт ещё раз' : 'Дообойти';
    cont.title = s.rebuild ? 'Собрать отчёт заново, сайт заново не обходится'
      : 'Продолжить эту проверку с того места, где она остановилась. Перед запуском можно увеличить лимит страниц';
    cont.dataset.f = s.report; cont.dataset.rebuild = s.rebuild ? '1' : ''; cont.dataset.site = s.site || '';
  }
  const oc = $('openc'); oc.hidden = !s.competitors;
  if (s.competitors) { oc.href = '/r/' + encodeURIComponent(s.competitors) + '/конкуренты.html'; oc.target = '_blank'; oc.textContent = 'Сравнение с конкурентами →'; }
  // значок в меню слева: проверка идёт, сколько сделано
  $('navRun').hidden = !s.running; const ovAll = s.overall_all != null ? s.overall_all : s.overall;
  $('navRun').textContent = s.running && ovAll != null ? Math.floor(ovAll) + '%' : '';
  renderRuns(s);
  // паутина
  if (s.running && pages != null) { if (lastPages != null && pages > lastPages) webEvent('page', {delta: pages - lastPages, pages}); lastPages = pages; }
  if (s.running && (s.stuck >= 300 || s.idle >= 300) && !warned) { warned = true; webEvent('warning'); }
  if (s.running && s.stuck < 300 && s.idle < 300) warned = false;
  if (wasRunning && !s.running) { webEvent(s.stopped ? 'pause' : (s.report || s.result || s.semantics || s.competitors) ? 'end' : 'error', {stopped: s.stopped}); loadReports(); }
  wasRunning = s.running;
  pollTimer = setTimeout(poll, s.running ? 1500 : 10000);  // и без своей проверки: её мог начать бот или наблюдение
}
// Конкуренты, которые проверяются одновременно с вашим сайтом (s.runs, кроме первого - он в главной карточке):
// у каждого своя паутина (/api/web?run=N), полоса, шаг и журнал
const runWebs = {};
function dropRunWebs(){ Object.keys(runWebs).forEach(k => { try { runWebs[k].live.stop(); runWebs[k].web.destroy(); } catch (e) {} delete runWebs[k]; }); }
const RUN_STATE = {wait: 'Ждёт очереди: одновременно проверяются не больше 3 сайтов', done: 'Готово', stopped: 'Остановлено',
  fail: 'Проверка не получилась, посмотрите журнал', skipped: 'Не начат: проверку остановили'};
function renderRuns(s){
  const box = $('runs'), list = (s.runs || []).filter(r => r.n > 1);
  box.hidden = !list.length;
  const keys = list.map(r => r.n + '|' + r.site);
  if (box.dataset.keys !== keys.join(' ')) {  // другая проверка - собрать заново
    dropRunWebs(); box.dataset.keys = keys.join(' ');
    box.innerHTML = list.length ? '<h3></h3>' : '';
    list.forEach(r => {
      box.insertAdjacentHTML('beforeend', `<div class="run-item" data-run="${r.n}"><div class="web-stage"></div><div>
        <div class="run-top"><b>${esc(host(r.site))}</b><span class="mut run-pages"></span></div>
        <div class="run-step"></div><div class="pbar"><i></i></div><a class="run-rep" target="_blank" hidden>Открыть отчёт →</a>
        <details class="log"><summary>Журнал этого сайта</summary><pre></pre></details></div></div>`);
      const el = box.lastElementChild;
      if (window.ClaylerWeb && ClaylerWeb.live) {
        const c = document.createElement('canvas'); el.querySelector('.web-stage').appendChild(c);
        const web = ClaylerWeb.create(c, {role: 'card'});
        runWebs[r.n] = {web, live: ClaylerWeb.live([web], {url: '/api/web?run=' + r.n})};
      }
    });
  }
  const h3 = box.querySelector('h3');
  if (h3) h3.textContent = !s.running ? (list.length > 1 ? 'Конкуренты' : 'Конкурент')
    : (list.length > 1 ? 'Конкуренты проверяются' : 'Конкурент проверяется') + ' одновременно с вашим сайтом';
  list.forEach(r => {
    const el = box.querySelector(`[data-run="${r.n}"]`); if (!el) return;
    el.className = 'run-item' + (r.state === 'done' ? ' done' : '');
    const st = el.querySelector('.run-step'), shaky = r.state === 'run' && r.shaky_note, stuck = !shaky && r.state === 'run' && r.stuck >= 300;
    st.className = 'run-step' + (stuck || shaky ? ' warn' : '');
    st.textContent = shaky ? `⚠ ${r.shaky_note[0].toUpperCase() + r.shaky_note.slice(1)}.` : stuck ? `⚠ Уже ${fmtTime(r.stuck)} не закончилась проверка ни одного адреса: сайт мог перестать отвечать.`
      : r.state === 'run' ? (r.step || 'Запускаю…').replace(/^Шаг (\d) из 4: /, 'Шаг $1 из 4 · ') : RUN_STATE[r.state] || '';
    const p = r.progress, pages = r.state === 'run' && p ? p[0] : r.done_pages != null ? r.done_pages : p ? p[0] : null;
    el.querySelector('.run-pages').textContent = pages == null ? '' : r.state === 'run' && p ? `${num(p[0])} из ${num(p[1])} стр.` : `${num(pages)} стр.`;
    el.querySelector('.pbar i').style.width = (r.overall != null ? r.overall : r.state === 'done' ? 100 : 0) + '%';
    const rep = el.querySelector('.run-rep'); rep.hidden = !r.report;
    if (r.report) rep.href = '/r/' + encodeURIComponent(r.report) + '/отчёт.html';
    const pre = el.querySelector('pre'), atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
    pre.textContent = (r.log || []).join('\n'); if (atBottom) pre.scrollTop = pre.scrollHeight;
  });
}
function foldForm(fold){
  $('form').classList.toggle('folded', fold);
  $('formFold').textContent = fold ? 'Развернуть' : 'Свернуть'; $('formFold').setAttribute('aria-expanded', String(!fold));
}
$('formFold').onclick = () => {
  const fold = !$('form').classList.contains('folded');
  formFoldAuto = false; store.set('formOpen', fold ? '0' : '1'); foldForm(fold);
};
// ---------- Список «Отчёты»: карточка на сайт, последняя проверка сверху, история свёрнута
let REP = {sites: [], archive: []};
const MONTHS = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
function parseDate(s){ const m = /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)/.exec(s||''); return m ? new Date(+m[1], m[2]-1, +m[3], +m[4], +m[5]) : null; }
function when(s){
  const d = parseDate(s); if (!d) return '';
  const t = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate()), now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((today - day) / 86400000);
  if (diff === 0) return 'сегодня в ' + t;
  if (diff === 1) return 'вчера в ' + t;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${d.getFullYear() !== now.getFullYear() ? ' ' + d.getFullYear() : ''} в ${t}`;
}
function plural(n, one, few, many){ n = Math.abs(n) % 100; if (n > 10 && n < 20) return many; n %= 10; return n === 1 ? one : (n >= 2 && n <= 4 ? few : many); }
function num(n){ return (n ?? 0).toLocaleString('ru'); }
function mb(b){ return b >= 1e9 ? (b/1e9).toFixed(1).replace('.', ',') + ' ГБ' : b >= 1e6 ? Math.round(b/1e6) + ' МБ' : Math.max(1, Math.round(b/1e3)) + ' КБ'; }
function hcls(h){ return h == null ? 'none' : h >= 90 ? 'good' : h >= 70 ? 'mid' : 'bad'; }
function host(u){ return String(u||'').replace(/^https?:\/\//,'').replace(/\/$/,''); }
const H_TIP = 'Здоровье - доля страниц сайта без критичных ошибок и предупреждений. Замечания не считаются. Проблема всего сайта (битая ссылка в меню, тяжёлый шаблон) снимает 5-10%, все вместе не больше 30%.';

const MON3 = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
function whenShort(s){  // «Сегодня, 17:22», «Вчера, 21:08», «1 окт, 19:39»
  const d = parseDate(s); if (!d) return '';
  const t = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`, now = new Date();
  const diff = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  return diff === 0 ? 'Сегодня, ' + t : diff === 1 ? 'Вчера, ' + t
    : `${d.getDate()} ${MON3[d.getMonth()]}${d.getFullYear() !== now.getFullYear() ? ' ' + d.getFullYear() : ''}, ${t}`;
}

function labels(c, short){
  const s = c.summary || {}, out = [];
  if (c.running) out.push(['run', 'идёт сейчас']);
  else if (!c.finished) out.push(['warn', 'не закончена', 'Проверку остановили или она прервалась. Отчёт по тому, что успели проверить.']);
  if (s.queue_left) out.push(['warn', short ? 'не полностью' : `не полностью · ${num(s.pages)} из ~${num(s.pages + s.queue_left)} стр.`,
    'Не хватило лимита страниц. «Дообойти» продолжит эту проверку: покажет её лимит страниц и даст его увеличить.']);
  if (c.js) out.push(['', 'JavaScript', 'Страницы открывались во встроенном браузере, как у посетителя.']);
  if (c.scope && c.scope.mode === 'section') out.push(['', short ? 'раздел' : 'только раздел ' + c.scope.prefix,
    'Проверен только раздел ' + c.scope.prefix + ': здоровье и проблемы по страницам раздела.']);
  if (c.scope && c.scope.mode === 'list') out.push(['', short ? 'список' : `список из ${num(c.scope.count)} адресов`,
    'Проверены только адреса из вставленного списка, без обхода по ссылкам.']);
  if (s.unchecked) out.push(['old', short ? 'не удалось проверить' : 'не удалось проверить: сайт не открылся',
    'Ни одна страница сайта не открылась (сайт не ответил, закрыл доступ или перенаправил по кругу), поэтому здоровья нет.']);
  if (c.health_old) out.push(['old', short ? 'старый расчёт здоровья' : 'здоровье по старому расчёту',
    'Отчёт собран до 15.10.2026: тогда одна проблема в меню или шаблоне давала здоровье почти 0%. «⋯ → Обновить отчёт» пересчитает (сайт заново не обходится).']);
  if (c.finished && s.health == null && !s.unchecked) out.push(['old', short ? 'старая версия программы' : 'старая версия программы, части проверок нет',
    'Проверка сделана старой версией программы: здоровья и части проверок в ней нет. «⋯ → Обновить отчёт» соберёт отчёт заново (сайт заново не обходится).']);
  return out.map(([k, t, tip]) => `<span class="tag ${k}"${tip ? ` title="${esc(tip)}"` : ''}>${esc(t)}</span>`).join('');
}
// «нет свежих данных»: последняя проверка сайта старше месяца - отчёт клиенту по ней уже не про сегодняшний сайт
const STALE_DAYS = 30;
function staleTag(c){
  if (c.running || !c.finished) return '';
  const d = (Date.now() - new Date(c.finished.replace(' ', 'T')).getTime()) / 864e5;
  return d > STALE_DAYS ? `<span class="tag warn" title="Последняя проверка ${Math.floor(d)} дн. назад. Сайт с тех пор мог измениться: перед отчётом клиенту проверьте его заново.">нет свежих данных</span>` : '';
}
function base(c, archived){ return '/r/' + (archived ? 'archive' + '/' : '') + encodeURIComponent(c.folder) + '/'; }
function smallLinks(c, archived){
  const b = base(c, archived), out = [];
  if (c.has_card) out.push(`<a href="${b}карточка.html" target="_blank" title="Всё главное о сайте на одной странице: дата проверки, здоровье, что исправить первым, движок и хостинг, бренды, смета, файлы">Карточка</a>`);
  if (c.has_audit) out.push(`<a href="${b}аудит.html" target="_blank">Аудит</a>`);
  if (c.has_html) out.push(`<a href="${b}отчёт.html" target="_blank">Отчёт</a>`);
  return out.join('');
}
// «Отчёты ▾»: все файлы проверки. items - наверху меню, rest - в подменю «Ещё ›» (чтобы меню было коротким, как в Windows)
function reportItems(c, archived){
  const b = base(c, archived), items = [], rest = [];
  if (c.has_card) items.push(`<a href="${b}карточка.html" target="_blank" title="Всё главное о сайте на одной странице: дата проверки, здоровье, что исправить первым, движок и хостинг, бренды, смета, файлы">Карточка сайта</a>`);
  if (c.has_audit) rest.push(`<a href="${b}аудит.html" target="_blank" title="Понятный документ для клиента: главное, что исправить, и сколько это даст">Аудит для клиента</a>`);
  if (c.has_html) items.push(`<a href="${b}отчёт.html" target="_blank" title="Все найденные проблемы со списками адресов">Полный отчёт</a>`);
  if (c.has_client_html) items.push(`<a href="${b}отчёт_для_клиента.html" target="_blank" title="Тот же полный отчёт, но без служебных подсказок, с пометкой «предварительный аудит» и вашими контактами. Один файл, открывается у клиента без программы">Полный отчёт для клиента (HTML)</a>`);
  if (c.has_client_html) rest.push(`<a href="${b}отчёт_для_клиента.html" download="${esc('SEO-аудит ' + host(c.site) + '.html')}" title="Сохранить файл в «Загрузки», чтобы отправить клиенту">Скачать отчёт для клиента</a>`);
  if (c.has_audit_pdf) rest.push(`<a href="${b}аудит.pdf" target="_blank">Аудит в PDF, для клиента</a>`);
  if (c.has_video || c.has_video_webm) rest.push(`<a href="${b}видео обхода.${c.has_video ? 'mp4' : 'webm'}" target="_blank" title="Короткое видео: паучок плетёт паутину по сайту, ошибки вспыхивают красным. Без контактов - для Авито и Kwork">Видео обхода</a>`);
  if (c.has_dev_files) items.push(`<button data-act="open_folder" data-dev="1" data-f="${esc(c.folder)}" title="Папка «для клиента\\файлы для разработчика»: robots.txt, sitemap.xml, 301-редиректы (Apache, nginx, таблица), новые title и description, «Прочитайте сначала.txt»">Файлы для разработчика (папка)</button>`);
  if (c.has_demo_pdf) rest.push(`<a href="${b}аудит_демо.pdf" target="_blank" title="Пример отчёта для витрины (Kwork и т. п.): без ваших контактов, телефоны и адреса сайта скрыты">PDF для витрины (демо)</a>`);
  if (c.has_web_png) rest.push(`<a href="${b}паутина.png" target="_blank" title="Сплетённая паутина с цифрой здоровья сайта: обложка для Авито и Kwork, копия в папке «для клиента»">Картинка паутины (PNG)</a>`);
  if (c.has_express_pdf) rest.push(`<a href="${b}экспресс.pdf" target="_blank" title="Один лист: здоровье и 5 главных проблем, отправить потенциальному клиенту">Экспресс-аудит (1 лист PDF)</a>`);
  if (c.has_audit_docx) rest.push(`<a href="${b}аудит.docx">Аудит в Word</a>`);
  if (c.has_xlsx) rest.push(`<a href="${b}отчёт.xlsx">Таблица Excel</a>`);
  if (c.has_compare) rest.push(`<a href="${b}сравнение.html" target="_blank">Что изменилось с прошлой проверки</a>`);
  if (c.has_competitors) rest.push(`<a href="${b}конкуренты.html" target="_blank">Сравнение с конкурентами</a>`);
  if (c.has_semantics_xlsx) rest.push(`<a href="${b}семантика.xlsx" title="Запросы по группам и страницам сайта">Семантика в Excel</a>`);
  return {items, rest};
}
// «⋯»: действия с проверкой; редкие (rest) - в подменю «Ещё ›»
function actionItems(c, g, archived){
  const items = [], rest = [];
  if (g && !archived && c.finished) rest.push(`<button data-act="compare" data-key="${esc(g.key)}">Сравнить с конкурентом…</button>`);
  if (g && !archived && c.finished) rest.push(`<a href="/semantics?f=${encodeURIComponent(c.folder)}" title="Какие запросы ищут люди и какая страница сайта должна по ним показываться">${c.has_semantics ? 'Семантика' : 'Собрать семантику…'}</a>`);
  if (c.has_client_html || c.has_audit_pdf || c.has_xlsx) items.push(`<button data-act="open_folder" data-client="1" data-f="${esc(c.folder)}" title="Отдельная папка с тремя файлами для отправки клиенту: полный отчёт (HTML), аудит в PDF, таблица Excel и папка «файлы для разработчика». Обновляется сама после каждой проверки и «Обновить отчёт»">Открыть папку для клиента</button>`);
  if (c.has_dev_files) items.push(`<button data-act="open_folder" data-dev="1" data-f="${esc(c.folder)}" title="Готовые исправления для разработчика сайта: robots.txt, sitemap.xml, 301-редиректы (Apache, nginx, таблица), новые title и description для загрузки. Лежат в папке для клиента">Файлы для разработчика</button>`);
  rest.push(`<button data-act="open_folder" data-f="${esc(c.folder)}">Открыть папку с файлами</button>`);
  if (c.summary && c.summary.pages && !c.running) rest.push(`<button data-act="crawl_video" data-f="${esc(c.folder)}" title="Видео на 20 секунд для Авито и Kwork: паучок плетёт паутину в порядке, в котором проверялись страницы, ошибки вспыхивают красным, в конце - здоровье сайта. Без контактов. Сайт заново не обходится">${c.has_video || c.has_video_webm ? 'Записать видео обхода заново' : 'Видео обхода (для Авито и Kwork)'}</button>`);
  if (c.has_audit_pdf && !c.running) rest.push(`<button data-act="demo_pdf" data-f="${esc(c.folder)}" title="Аудит в PDF как пример работы для Kwork и других витрин: с пометкой «Пример отчёта», ваше имя без контактов и ссылок, телефоны, почты и адреса сайта скрыты. Сайт заново не обходится">PDF для витрины (демо)</button>`);
  if (!archived && c.finished && !c.running) items.push(`<button data-act="rebuild" data-f="${esc(c.folder)}" data-site="${esc(c.site)}" title="Собрать отчёт заново новой версией программы, сайт заново не обходится">Обновить отчёт</button>`);
  if (g && !archived) rest.push(...(rest.length ? ['<hr>'] : []), ...Object.entries(TAG_NAMES).filter(([k]) => k !== g.tag)
    .map(([k, t]) => `<button data-act="tag" data-key="${esc(g.key)}" data-tag="${k}" title="Метка сайта: клиенты собраны на экране «Клиенты»">Метка: ${t}</button>`),
    ...(g.tag ? [`<button data-act="tag" data-key="${esc(g.key)}" data-tag="">Убрать метку «${TAG_NAMES[g.tag]}»</button>`] : []));
  if (!c.running) {
    items.push('<hr>');
    items.push(archived ? `<button data-act="unarchive" data-f="${esc(c.folder)}">Вернуть из архива</button>`
                        : `<button data-act="archive" data-f="${esc(c.folder)}" title="Убрать из списка. Файлы остаются, вернуть можно из «Архива» внизу">Убрать в архив</button>`);
    items.push(`<button class="danger" data-act="delete" data-f="${esc(c.folder)}" data-archived="${archived ? 1 : ''}" data-what="${esc(host(c.site) + (c.finished || c.started ? ', ' + when(c.finished || c.started) : ''))}" data-size="${c.size}">Удалить (${mb(c.size)})</button>`);
  }
  return {items, rest};
}
const DOTS = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>';
function menu(label, {items, rest}, cls, aria){
  items = items.slice();
  if (rest.length) {
    const sub = `<div class="sub"><button type="button" class="subbtn" aria-haspopup="true">Ещё</button><div class="menu submenu">${rest.join('')}</div></div>`;
    const hr = items.lastIndexOf('<hr>');
    items.splice(hr < 0 ? items.length : hr, 0, sub);
  }
  while (items[0] === '<hr>') items.shift();
  return items.length ? `<details class="more"><summary class="btn ${cls || ''}"${aria ? ` aria-label="${aria}" title="${aria}"` : ''}>${label}</summary><div class="menu">${items.join('')}</div></details>` : '';
}
// в истории и архиве: одно меню «Ещё» со всем сразу
function moreMenu(c, g, archived, small){
  const r = reportItems(c, archived), a = actionItems(c, g, archived);
  return menu('Ещё', {items: r.items.concat(r.items.length && a.items.length ? ['<hr>'] : [], a.items),
                      rest: r.rest.concat(r.rest.length && a.rest.length ? ['<hr>'] : [], a.rest)}, 'drop' + (small ? ' small' : ''));
}
function rowButtons(c, g){
  const b = base(c), s = c.summary || {}, out = [];
  if (s.queue_left && !c.running) out.push(`<button class="btn warn" data-act="resume" data-f="${esc(c.folder)}" title="Продолжить эту проверку с того места, где она остановилась. Перед запуском можно увеличить лимит страниц">Дообойти</button>`);
  if (c.has_audit) out.push(`<a class="btn primary" href="${b}аудит.html" target="_blank" title="Понятный документ для клиента: главное, что исправить, и сколько это даст">Аудит</a>`);
  else if (c.has_html) out.push(`<a class="btn primary" href="${b}отчёт.html" target="_blank" title="Все найденные проблемы со списками адресов">Полный отчёт</a>`);
  if (!c.has_html && !c.running) out.push(`<button class="btn" data-act="rebuild" data-f="${esc(c.folder)}" data-site="${esc(c.site)}">Собрать отчёт</button>`);
  out.push(menu('Отчёты', reportItems(c), 'drop'));
  out.push(menu(DOTS, actionItems(c, g), '', 'Ещё действия'));
  return out.join('');
}
function ring(h){
  const C = 2 * Math.PI * 22, len = h ? h / 100 * C : 0;  // у 0% дуги нет совсем: без красной точки
  return `<div class="ring ${hcls(h)}${h === 100 ? ' full' : ''}" title="${esc(H_TIP)}"><svg width="52" height="52" viewBox="0 0 52 52" aria-hidden="true"><circle class="trk" cx="26" cy="26" r="22"/>${
    len ? `<circle class="arc" cx="26" cy="26" r="22" stroke-linecap="round" stroke-dasharray="${len.toFixed(1)} 200" transform="rotate(-90 26 26)"/>` : ''}</svg><b>${h == null ? '–' : h + '%'}</b></div>`;
}
// весь сайт с разделом и проверку с JavaScript без него не сравниваем - как сравнение.html и отчёт за месяц
const sameScope = (a, b) => JSON.stringify(a.scope || null) === JSON.stringify(b.scope || null) && !!a.js === !!b.js;
// что изменилось с прошлой проверки: исправлено / новых, при наведении — какие проблемы
function cmpNote(c) {
  const m = c.compare; if (!m) return '';
  const li = (xs, mark) => (xs || []).slice(0, 6).map(x => `${mark} ${x.title} (${x.old} → ${x.new})`).join('\n');
  const tip = [li(m.top_fixed, '✓'), li(m.top_added, '+')].filter(Boolean).join('\n') || 'Проблемы не изменились';
  const bad = (m.new_crit || []).length;
  // своей строкой под линией и цифрой: в колонку 210px рядом не помещается и заезжал на «Страниц»
  return `<span class="cmp"><span class="mut" title="${esc(tip)}">исправлено ${m.fixed}, новых ${m.added}</span>`
    + (bad ? ` <span class="delta down" title="${esc('Новые критичные: ' + m.new_crit.join('; '))}">новые критичные: ${bad}</span>` : '') + '</span>';
}
function spark(checks){
  const pts = checks.filter(c => c.summary && c.summary.health != null && sameScope(c, checks[0])).slice(0, 12).reverse();
  if (pts.length < 2) return '';
  const w = 64, h = 22, step = w / (pts.length - 1);
  const xy = pts.map((c, i) => `${(i * step).toFixed(1)},${(h - 2 - c.summary.health / 100 * (h - 4)).toFixed(1)}`);
  return `<svg class="spark ${hcls(pts[pts.length - 1].summary.health)}" viewBox="-2 0 ${w + 4} ${h}" width="${w + 4}" height="${h}" aria-hidden="true"><polyline points="${xy.join(' ')}"/></svg>`;
}
// динамика здоровья: только если есть прошлая проверка того же охвата
function delta(g){
  const [last, ...rest] = g.checks, h = last.summary && last.summary.health;
  const prev = rest.find(c => c.summary && c.summary.health != null && sameScope(c, last));
  if (h == null || !prev) return '';
  const d = h - prev.summary.health, cls = d > 0 ? 'up' : d < 0 ? 'down' : '';
  return `${spark(g.checks)}<span class="delta ${cls}" title="Прошлая проверка: ${esc(when(prev.finished || prev.started))}, здоровье ${prev.summary.health}%">${d ? (d > 0 ? '+' : '−') + Math.abs(d) : 'без изменений'}</span>${cmpNote(last)}`;
}
function histSpark(checks){
  const pts = checks.filter(c => c.summary && c.summary.health != null && sameScope(c, checks[0])).slice().reverse();
  if (pts.length < 2) return '';
  const w = 90, h = 22, step = w / (pts.length - 1);
  const xy = pts.map((c, i) => `${(i * step).toFixed(1)},${(h - 2 - c.summary.health / 100 * (h - 4)).toFixed(1)}`);
  return `<svg class="spark" viewBox="-2 0 ${w + 4} ${h}" width="${w + 4}" height="${h}" aria-hidden="true"><polyline points="${xy.join(' ')}" style="stroke:var(--mut2)"/>${
    xy.map((p, i) => `<circle cx="${p.split(',')[0]}" cy="${p.split(',')[1]}" r="2" class="${hcls(pts[i].summary.health)}"/>`).join('')}</svg>`;
}
function siteRow(g){
  const c = g.checks[0], s = c.summary || {}, h = s.health;
  const hist = g.checks.slice(1);
  const histHtml = hist.length ? `<details class="history"><summary>История проверок (${hist.length}) ${histSpark(g.checks)}</summary>
    <table>${hist.map(x => { const xs = x.summary || {}; return `<tr>
      <td class="nowrap">${esc(when(x.finished || x.started) || x.folder)}${host(x.site) !== host(c.site) ? `<div class="mut">${esc(host(x.site))}</div>` : ''}</td>
      <td class="h ${hcls(xs.health)}" title="${esc(H_TIP)}">${xs.health == null ? '<span class="mut">нет</span>' : xs.health + '%'}</td>
      <td class="nowrap">${xs.pages != null ? num(xs.pages) + ' стр.' : ''}</td>
      <td>${labels(x, true)}</td>
      <td class="acts"><div class="actions">${smallLinks(x)}${moreMenu(x, null, false, true)}</div></td></tr>`; }).join('')}</table></details>` : '';
  const whenTxt = c.running ? 'Проверяется сейчас' : (whenShort(c.finished || c.started) || c.folder) + (c.took ? ' · за ' + c.took : '');
  return `<div class="rrow"><div class="rgrid" data-card="${esc(g.key)}" title="Нажмите - короткая карточка сайта. Полные отчёты - в «Отчёты ▾»">
    <div class="c-ring">${ring(h)}</div>
    <div class="c-site"><div class="r-name" title="${esc(host(c.site))}"><input type="checkbox" class="r-pick" data-key="${esc(g.key)}"${PICK.has(g.key) ? ' checked' : ''} aria-label="Выбрать ${esc(host(c.site))}"><button type="button" class="r-star${g.fav ? ' on' : ''}" data-fav="${esc(g.key)}" title="${g.fav ? 'Убрать из избранного' : 'В избранное'}" aria-pressed="${!!g.fav}">${g.fav ? '★' : '☆'}</button>${c.flag ? `<span class="r-flag" title="Страна сайта: ${esc(c.country)}">${c.flag}</span> ` : ''}${esc(host(c.site))}</div><div class="r-when">${esc(whenTxt)}</div><div class="r-tags">${g.tag ? `<span class="tag run">${TAG_NAMES[g.tag]}</span>` : ''}${labels(c)}${staleTag(c)}</div></div>
    <div class="c-dyn">${delta(g)}</div>
    <div class="c-pages">${s.pages != null ? num(s.pages) + ' <small class="pg-u">стр.</small>' : ''}</div>
    <div class="c-acts">${rowButtons(c, g)}</div>
  </div>${histHtml}</div>`;
}
let repFilter = store.get('repFilter') || 'all';
const FILTERS = {
  all: () => true,
  bad: g => { const h = (g.checks[0].summary || {}).health; return h != null && h < 70; },
  good: g => { const h = (g.checks[0].summary || {}).health; return h != null && h >= 90; },
  partial: g => { const c = g.checks[0]; return !!((c.summary || {}).queue_left || (!c.finished && !c.running)); },
  fav: g => !!g.fav,
  sem: g => !!g.sem_folder,
  nosem: g => !g.sem_folder,
  // метки работы у проблем (labels.py), по всем сайтам: что отдано разработчику и что ждёт проверки
  sent: g => LBL.some(x => x.site === g.key && x.state === 'sent'),
  wait: g => LBL.some(x => x.site === g.key && x.state === 'wait'),
};
let LBL = [], LBL_STATES = {};   // все метки с названиями проблем (/api/labels?all=1)
async function loadLabels(){
  // true - метки изменились: список проверок перерисовываем только тогда
  try { const j = await (await fetch('/api/labels?all=1')).json(), was = JSON.stringify(LBL);
    LBL = j.items || []; LBL_STATES = j.states || {}; return JSON.stringify(LBL) !== was; } catch (e) { return false; }
}
// галочки у сайтов: «Собрать семантику» и «Загрузить частотность» для всех выбранных (через очередь сайтов)
const PICK = new Set();
function bulk(){
  const box = $('repBulk'), keys = REP.sites.filter(g => PICK.has(g.key));
  [...PICK].forEach(k => { if (!REP.sites.some(g => g.key === k)) PICK.delete(k); });
  box.hidden = !keys.length;
  if (!keys.length) { box.innerHTML = ''; return; }
  const withSem = keys.filter(g => g.sem_folder).length, ready = keys.filter(g => g.checks.some(c => c.finished)).length;
  box.innerHTML = `<b>Выбрано: ${keys.length}</b>
    <button class="primary small" data-bulk="sem"${ready ? '' : ' disabled'} title="Быстрый сбор: главная и разделы, подсказки Яндекса и Google, без Вордстата. Идёт через «Очередь сайтов», пары слов копятся в «Словарь → Ждут подтверждения».">Собрать семантику (${ready})</button>
    <button class="small" data-bulk="freq"${withSem ? '' : ' disabled'} title="Точная частотность Вордстата через Директ, сайт за сайтом: прогнозом Директа, по 100 фраз, без суточного лимита. Если прогноз не ответит - отчётами Вордстата, 1 000 фраз в сутки, после полуночи по Москве продолжится сама.">Загрузить частотность (${withSem})</button>
    <button class="ghost small" data-bulk="all">Выбрать все в списке</button><button class="ghost small" data-bulk="none">Снять выбор</button>
    <span class="mut" id="repBulkMsg"></span>`;
}
let repShown = [];
function renderReports(){
  const q = $('q').value.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '');
  if (!FILTERS[repFilter]) repFilter = 'all';
  const found = REP.sites.filter(g => !q || g.key.includes(q) || g.checks.some(x => host(x.site).includes(q)));
  const sites = found.filter(FILTERS[repFilter]);
  repShown = sites;
  document.querySelectorAll('#repFilters .fpill').forEach(b => {
    const n = found.filter(FILTERS[b.dataset.f]).length;
    b.classList.toggle('on', b.dataset.f === repFilter); b.setAttribute('aria-pressed', String(b.dataset.f === repFilter));
    b.innerHTML = esc(b.textContent.replace(/\s*\d+$/, '')) + (n ? ` <small>${n}</small>` : '');
    if (b.dataset.f === 'sent' || b.dataset.f === 'wait') b.hidden = !n && repFilter !== b.dataset.f;   // меток нет - кнопки не видно
  });
  const box = $('reports');
  const dyn = sites.some(g => delta(g));  // колонка «Динамика» только если хоть одному сайту есть с чем сравнить
  box.className = 'rep' + (dyn ? '' : ' no-dyn');
  if (!REP.sites.length) box.innerHTML = '<p class="mut rep-empty">Отчётов пока нет. Запустите первую проверку.</p>';
  else if (!sites.length) box.innerHTML = '<p class="mut rep-empty">Ничего не нашлось.</p>';
  else box.innerHTML = `<div class="rgrid rhead"><span title="${esc(H_TIP)}">Здоровье</span><span>Сайт</span><span class="c-dyn">Динамика</span><span>Страниц</span><span></span></div>`
    + sites.map(siteRow).join('');
  bulk();
  const arch = REP.archive || [];
  $('archiveBox').hidden = !arch.length;
  $('archiveCount').textContent = arch.length ? `(${arch.length}, ${mb(arch.reduce((a, c) => a + (c.size || 0), 0))})` : '';
  $('archive').innerHTML = arch.map(c => `<div class="arch-row"><div><b>${esc(host(c.site))}</b> <span class="mut">${esc(when(c.finished || c.started) || c.folder)}${
    c.summary && c.summary.health != null ? ' · здоровье ' + c.summary.health + '%' : ''}</span></div><div class="actions">${smallLinks(c, true)}${moreMenu(c, null, true, true)}</div></div>`).join('');
  const total = REP.sites.reduce((a, g) => a + g.checks.reduce((b, c) => b + (c.size || 0), 0), 0);
  const sizeTxt = REP.sites.length ? `${REP.sites.length} ${plural(REP.sites.length, 'сайт', 'сайта', 'сайтов')}, на диске ${mb(total)}` : '';
  $('repTotal').textContent = sizeTxt;
  $('disk').textContent = REP.sites.length ? `На диске ${mb(total)} · ${REP.sites.length} ${plural(REP.sites.length, 'сайт', 'сайта', 'сайтов')}` : '';
}
$('repFilters').addEventListener('click', e => {
  const b = e.target.closest('.fpill'); if (!b) return;
  repFilter = b.dataset.f; store.set('repFilter', repFilter); renderReports();
});
// нажатие на строку сайта - короткая карточка последней проверки прямо в окне (карточка.html, site_card.py)
function openCard(g){
  const c = g.checks[0], dlg = $('cardDlg'), fr = $('cardFrame'), none = $('cardNone');
  $('cardTitle').textContent = host(c.site) + (c.finished ? ' · ' + whenShort(c.finished) : '');
  const url = c.has_card ? base(c) + 'карточка.html' : '';
  fr.hidden = !url; none.hidden = !!url; $('cardTab').hidden = !url;
  if (url) { fr.src = url + '#dark'; $('cardTab').href = url; }
  else {
    fr.removeAttribute('src');
    none.innerHTML = c.running ? '<p>Сайт сейчас проверяется. Карточка появится, когда проверка закончится.</p>'
      : `<p>У этой проверки карточки ещё нет: она сделана до того, как карточка появилась в программе.</p>
         <p class="mut">«Обновить отчёт» соберёт отчёт и карточку заново, сайт заново не обходится.</p>`
        + (c.finished ? `<div class="dlg-btns" style="justify-content:flex-start"><button class="primary" data-act="rebuild" data-f="${esc(c.folder)}" data-site="${esc(c.site)}">Обновить отчёт</button></div>` : '');
  }
  cardLabels(g);
  dlg.showModal();
  loadLabels().then(() => { if (CARD_G === g && dlg.open) cardLabels(g); });   // метку могли поставить только что в отчёте
}
// метки работы у проблем сайта - прямо в карточке, менять без открытия отчёта
let CARD_G = null;
function cardLabels(g){
  CARD_G = g;
  const L = LBL.filter(x => x.site === g.key), box = $('cardLabels');
  box.hidden = !L.length; if (!L.length) { box.innerHTML = ''; return; }
  const opts = cur => '<option value="">без метки</option>' + Object.entries(LBL_STATES).map(([k, t]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${esc(t)}</option>`).join('');
  box.innerHTML = `<div class="cl-h">Метки работы <span class="mut">· ${num(L.length)}. «Не ошибка» уберёт проблему из отчёта после «⋯ → Обновить отчёт»</span></div>`
    + L.map(x => `<div class="cl-row"><span>${esc(x.title)}</span><span class="mut">${esc(String(x.at || "").replace(/^(\d{4})-(\d\d)-(\d\d)/, "$3.$2.$1"))}</span>
      <select data-lkey="${esc(x.key)}" data-lsite="${esc(x.site)}" aria-label="Метка: ${esc(x.title)}">${opts(x.state)}</select></div>`).join('');
}
// вернулись в окно из отчёта (метку ставят там, в другой вкладке) - фильтры «Передано», «Ждёт проверки» заново
addEventListener('focus', () => { if (REP.sites.length) loadLabels().then(ch => { if (ch) renderReports(); }); });
$('cardLabels').addEventListener('change', async e => {
  const s = e.target.closest('select[data-lkey]'); if (!s) return;
  s.disabled = true;
  await fetch('/api/labels', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({site: s.dataset.lsite, key: s.dataset.lkey, state: s.value})}).catch(() => {});
  await loadLabels();
  if (CARD_G) cardLabels(CARD_G);
  renderReports();
});
$('reports').addEventListener('click', e => {
  const row = e.target.closest('.rgrid[data-card]');
  if (!row || e.target.closest('.c-acts, a, button, input, details, summary, .delta, .cmp')) return;
  const g = REP.sites.find(x => x.key === row.dataset.card); if (g) openCard(g);
});
$('cardClose').onclick = () => $('cardDlg').close();
$('cardDlg').addEventListener('click', e => { if (e.target.closest('[data-act="rebuild"]')) $('cardDlg').close(); });
$('cardDlg').addEventListener('close', () => $('cardFrame').removeAttribute('src'));
async function loadReports(){
  try { REP = await (await fetch('/api/reports')).json(); } catch (e) { return; }
  await loadLabels();
  renderReports(); fillSiteSelects(); renderClients(); if (AC_LAST) acChips(AC_LAST);
}

// ---- «Клиенты»: строка на сайт с меткой «клиент» - здоровье, изменение за неделю, новое критичное
const TAG_NAMES = {client: 'клиент', rival: 'конкурент', test: 'тест'};
const fin = c => new Date((c.finished || c.started || '').replace(' ', 'T')).getTime();
function weekAgo(g){
  // проверка того же охвата, законченная не позже чем за 7 дней до последней (иначе предыдущая)
  const last = g.checks.find(c => c.finished); if (!last) return null;
  const same = g.checks.filter(c => c !== last && c.finished && sameScope(c, last) && c.summary && c.summary.health != null);
  return same.find(c => fin(last) - fin(c) >= 7 * 864e5) || same[0] || null;
}
function renderClients(){
  const box = $('clList'); if (!box) return;
  const mine = REP.sites.filter(g => g.tag === 'client');
  $('clPick').innerHTML = REP.sites.filter(g => g.tag !== 'client')
    .map(g => `<option value="${esc(g.key)}">${esc(host(g.site))}</option>`).join('') || '<option value="">Все сайты уже клиенты</option>';
  if (!mine.length) { box.innerHTML = '<p class="mut">Клиентов пока нет. Добавьте сайт выше или поставьте метку в списке проверок.</p>'; return; }
  const rows = mine.map(g => {
    const c = g.checks.find(x => x.finished) || g.checks[0], s = c.summary || {}, w = weekAgo(g), m = c.compare;
    const h = s.health, d = w && h != null ? h - w.summary.health : null;
    const dTxt = d == null ? '<span class="mut">нет прошлой проверки</span>'
      : `<span class="delta ${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${d > 0 ? '+' : ''}${d}%</span> <span class="mut">с ${esc(when(w.finished))}</span>`;
    const crit = m && (m.new_crit || []).length;
    return `<tr><td><b>${esc(host(g.site))}</b><div class="mut">${esc(when(c.finished || c.started))}</div><div class="mut" data-wk="${esc(g.key)}"></div>${staleTag(c)}</td>
      <td class="h ${hcls(h)}">${h == null ? '–' : h + '%'}</td><td>${dTxt}${m ? `<div class="mut">исправлено ${m.fixed}, новых ${m.added}</div>` : ''}</td>
      <td>${crit ? `<span class="delta down" title="${esc(m.new_crit.join('; '))}">новые критичные: ${crit}</span>` : '<span class="mut">нет</span>'}</td>
      <td class="acts"><div class="actions">${c.has_audit ? `<a class="btn small" href="${base(c)}аудит.html" target="_blank">Аудит</a>` : ''}${c.has_compare ? `<a class="btn small" href="${base(c)}сравнение.html" target="_blank">Что изменилось</a>` : ''}${w ? `<button class="btn small" data-act="monthly" data-key="${esc(g.key)}" title="Что изменилось за месяц: здоровье, что исправлено и что появилось - страница для клиента (копия в папке «для клиента»)">Отчёт за месяц</button>` : ''}<button class="btn small ghost" data-act="tag" data-key="${esc(g.key)}" data-tag="" title="Убрать метку «клиент»">Убрать</button></div></td></tr>`;
  });
  fetch('/api/watch').then(r => r.json()).then(W => {
    const by = new Map((W.sites || []).map(s => [host(s.url).replace(/^www\./, '').split('/')[0], s]));
    box.querySelectorAll('[data-wk]').forEach(el => { const s = by.get(el.dataset.wk), w = s && s.weekly;
      el.textContent = w ? 'по расписанию: ' + ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'][w.day] + ' ' + w.time : ''; });
  }).catch(() => {});
  box.innerHTML = `<div class="tw"><table><thead><tr><th>Сайт и последняя проверка</th><th>Здоровье</th><th>За неделю</th><th>Новое критичное</th><th></th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}
// расписание у клиентов (наблюдение.json): показать в строках и включить всем сразу
async function clNight(on){
  const sites = REP.sites.filter(g => g.tag === 'client').map(g => { const c = g.checks.find(x => x.finished) || g.checks[0];
    return {url: c.site, pages: c.max_pages || 10000}; });
  if (!sites.length) { $('clNightMsg').textContent = 'Сначала добавьте клиентов.'; return; }
  const ok = await post('/api/watch/clients', {weekly: on ? $('clWeekly').value : 'выкл', sites});
  $('clNightMsg').textContent = ok ? (on ? `Включено для ${sites.length}: ${$('clWeekly').value}.` : 'Выключено.') : $('cmperr').textContent;
  if (ok) renderClients();
}
$('clNightOn').onclick = () => clNight(true);
$('clNightOff').onclick = () => clNight(false);
$('clAdd').onclick = async () => { const k = $('clPick').value; if (k && await post('/api/site_tag', {key: k, tag: 'client'})) loadReports(); };
// списки «Сайт» в инструментах: последняя законченная проверка каждого сайта
function fillSiteSelects(){
  document.querySelectorAll('select.site-pick, #srSite, #lsSite, #riSite').forEach(sel => {
    const cur = sel.value;
    sel.innerHTML = REP.sites.map(g => g.checks.find(c => c.finished)).filter(Boolean)
      .map(c => `<option value="${esc(c.folder)}">${esc(host(c.site))} - ${esc(when(c.finished))}</option>`).join('')
      || '<option value="">Нет законченных проверок</option>';
    if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
  });
}
$('q').addEventListener('input', renderReports);
// «Карточка» из поиска сайта (Ctrl+K) с другой страницы: /?q=site.ru - сразу отфильтрованный список
{ const q0 = new URLSearchParams(location.search).get('q'); if (q0) { $('q').value = q0; history.replaceState(null, '', location.pathname + location.hash); } }
$('reports').addEventListener('change', e => {
  const c = e.target.closest('.r-pick'); if (!c) return;
  if (c.checked) PICK.add(c.dataset.key); else PICK.delete(c.dataset.key);
  bulk();
});
$('reports').addEventListener('click', async e => {
  const s = e.target.closest('[data-fav]'); if (!s) return;
  const g = REP.sites.find(x => x.key === s.dataset.fav); if (!g) return;
  g.fav = !g.fav; renderReports();
  if (!await post('/api/fav', {key: g.key, on: g.fav})) { g.fav = !g.fav; renderReports(); }
});
$('repBulk').addEventListener('click', async e => {
  const b = e.target.closest('[data-bulk]'); if (!b) return;
  const act = b.dataset.bulk, picked = REP.sites.filter(g => PICK.has(g.key));
  if (act === 'none') { PICK.clear(); renderReports(); return; }
  if (act === 'all') { repShown.forEach(g => PICK.add(g.key)); renderReports(); return; }
  const say = t => { const m = $('repBulkMsg'); if (m) m.innerHTML = t; };
  b.disabled = true;
  try {
    const url = act === 'sem' ? '/api/queue/add_sem' : '/api/direct_many';
    const folders = act === 'sem' ? picked.map(g => (g.checks.find(c => c.finished) || {}).folder).filter(Boolean)
                                  : picked.map(g => g.sem_folder).filter(Boolean);
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({folders, start: true})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || 'Не получилось');
    if (act === 'sem') say(j.added ? `Поставил в очередь: ${j.added}. <a href="#queue">Открыть очередь →</a>` : 'Эти сайты уже ждут семантику в очереди. <a href="#queue">Открыть очередь →</a>');
    else say(`Частотность загрузится по очереди для ${j.added} ${plural(j.added, 'сайта', 'сайтов', 'сайтов')}. Ход загрузки - на странице «Семантика» сайта, блок «Точная частотность».`);
  } catch (err) { say(`<span class="err">${esc(err.message)}</span>`); }
  b.disabled = false;
});
async function post(url, body){
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body || {})});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { $('cmperr').textContent = j.error || 'Не получилось'; return false; }
  $('cmperr').textContent = ''; return true;
}
// меню не уходит за край окна: у нижнего края открывается вверх, подменю «Ещё ›» - влево у правого края
// и сдвигается вверх у нижнего; не помещается совсем - туда, где места больше, с прокруткой внутри
function placeMenu(d){
  const m = d.querySelector(':scope>.menu'); if (!m) return;
  m.classList.remove('up'); m.style.maxHeight = ''; m.style.overflowY = '';
  const b = d.querySelector(':scope>summary').getBoundingClientRect(), h = m.offsetHeight;
  const below = innerHeight - b.bottom - 8, above = b.top - 8;
  if (h > below && above > below) m.classList.add('up');
  const room = Math.max(below, above);
  if (h > room) { m.style.maxHeight = room + 'px'; m.style.overflowY = 'auto'; }
}
function placeSub(s){
  const m = s.querySelector(':scope>.submenu'); if (!m) return;
  m.classList.remove('left'); m.style.top = ''; m.style.maxHeight = ''; m.style.overflowY = '';
  m.style.position = ''; m.style.left = ''; m.style.right = '';
  // меню с прокруткой (окно низкое) обрезает всё, что выходит за его край: подменю - поверх, от строки «Ещё ›»
  if (s.closest('.menu') && s.closest('.menu').style.overflowY === 'auto') {
    const r0 = s.getBoundingClientRect();
    m.style.position = 'fixed'; m.style.top = r0.top + 'px'; m.style.right = 'auto';
    m.style.left = (r0.right + m.offsetWidth > innerWidth - 8 ? Math.max(8, r0.left - m.offsetWidth) : r0.right) + 'px';
    const rr = m.getBoundingClientRect();
    if (rr.height > innerHeight - 16) { m.style.maxHeight = (innerHeight - 16) + 'px'; m.style.overflowY = 'auto'; }
    const ov = m.getBoundingClientRect().bottom - (innerHeight - 8);
    if (ov > 0) m.style.top = Math.max(8, r0.top - ov) + 'px';
    return;
  }
  let r = m.getBoundingClientRect();
  if (r.right > innerWidth - 8) { m.classList.add('left'); r = m.getBoundingClientRect(); }
  if (r.height > innerHeight - 16) { m.style.maxHeight = (innerHeight - 16) + 'px'; m.style.overflowY = 'auto'; r = m.getBoundingClientRect(); }
  const over = r.bottom - (innerHeight - 8);
  if (over > 0) m.style.top = (m.offsetTop - Math.min(over, r.top - 8)) + 'px';
}
document.addEventListener('toggle', e => {
  const d = e.target; if (!d.matches || !d.matches('details.more')) return;
  if (d.open) placeMenu(d); else d.querySelectorAll('.sub.open').forEach(s => s.classList.remove('open'));
}, true);
document.addEventListener('mouseover', e => {
  const s = e.target.closest && e.target.closest('.menu .sub');
  if (s && !s.classList.contains('open')) { s.closest('.menu').querySelectorAll('.sub.open').forEach(o => o.classList.remove('open')); s.classList.add('open'); placeSub(s); }
});
document.addEventListener('mouseout', e => {
  const s = e.target.closest && e.target.closest('.menu .sub');
  if (s && !s.contains(e.relatedTarget)) s.classList.remove('open');
});
addEventListener('resize', () => document.querySelectorAll('details.more[open]').forEach(placeMenu));
document.addEventListener('click', async e => {
  // «Ещё ›» в меню: щелчок открывает подменю (без мыши - тоже), меню не закрывается
  const sb = e.target.closest('.subbtn');
  // только открывает: мышью подменю уже открыто наведением, и щелчок не должен его тут же закрыть (на сенсорном
  // экране касание тоже сначала «наводит»); закрывается - уводом мыши или щелчком мимо меню
  if (sb) { const s = sb.parentElement; if (!s.classList.contains('open')) { s.classList.add('open'); placeSub(s); } return; }
  // закрыть открытые меню «Ещё» при щелчке мимо
  document.querySelectorAll('details.more[open]').forEach(d => { if (!d.contains(e.target)) d.open = false; });
  const b = e.target.closest('[data-act]'); if (!b) return;
  const act = b.dataset.act, f = b.dataset.f;
  const menu = b.closest('details.more'); if (menu) menu.open = false;
  if (act === 'archive' && await post('/api/archive', {folder: f})) loadReports();
  if (act === 'unarchive' && await post('/api/unarchive', {folder: f})) loadReports();
  if (act === 'open_folder' && !await post('/api/open_folder', {folder: f, client: !!b.dataset.client, dev: !!b.dataset.dev}) && (b.dataset.client || b.dataset.dev))
    alert($('cmperr').textContent);
  if (act === 'delete') {
    if (!confirm(`Удалить проверку ${b.dataset.what}?\n\nВсе её файлы (отчёт, аудит, база) будут удалены насовсем, освободится ${mb(+b.dataset.size)}. Это нельзя отменить.\n\nЕсли проверка может ещё пригодиться - лучше «Убрать в архив».`)) return;
    if (await post('/api/delete', {folder: f, archived: !!b.dataset.archived})) loadReports();
  }
  if (act === 'rebuild' && await post('/api/rebuild', {folder: f, site: b.dataset.site})) poll();
  if (act === 'tag' && await post('/api/site_tag', {key: b.dataset.key, tag: b.dataset.tag})) loadReports();
  if (act === 'monthly') {
    const win = window.open('', '_blank');   // окно сразу, иначе браузер посчитает его всплывающим и не откроет
    b.disabled = true; const t = b.textContent; b.textContent = 'Собираю…';
    try {
      const r = await fetch('/api/monthly', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: b.dataset.key})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || 'Не получилось');
      if (win) win.location = j.url; else location.href = j.url;
    } catch (err) { if (win) win.close(); alert(err.message); }
    b.disabled = false; b.textContent = t;
  }
  if (act === 'demo_pdf') {
    document.body.style.cursor = 'progress'; $('cmperr').textContent = 'Собираю PDF для витрины, это до минуты...';
    const ok = await post('/api/demo_pdf', {folder: f});
    document.body.style.cursor = '';
    if (ok) loadReports(); else alert($('cmperr').textContent);
  }
  if (act === 'crawl_video') {
    document.body.style.cursor = 'progress'; $('cmperr').textContent = 'Записываю видео обхода, это около полуминуты...';
    const ok = await post('/api/crawl_video', {folder: f});
    document.body.style.cursor = '';
    if (ok) loadReports(); else alert($('cmperr').textContent);
  }
  if (act === 'compare') openCompare(b.dataset.key);
  if (act === 'resume') resumeCheck(f);
});
// «Дообойти»: лимит берётся из самой проверки, а не из формы (там может стоять другой). Окно показывает
// его и даёт увеличить, если не хватило; проверенные страницы засчитываются, обход идёт до нового лимита
let rsCheck = null;
function resumeCheck(folder){
  const c = REP.sites.flatMap(g => g.checks).find(x => x.folder === folder); if (!c) return;
  const s = c.summary || {}, done = s.pages || 0, left = s.queue_left || 0, was = c.max_pages || 0;
  rsCheck = c;
  $('rsSite').textContent = host(c.site);
  $('rsInfo').innerHTML = (was ? `Лимит этой проверки: <b>${num(was)}</b> ${plural(was, 'страница', 'страницы', 'страниц')}. ` : 'Лимит этой проверки не записан. ')
    + `Проверено ${num(done)}, в очереди ещё ${num(left)}.`;
  const all = done + left, step = all < 1000 ? 100 : all < 100000 ? 1000 : 10000, need = Math.ceil(all / step) * step;
  $('rsPages').value = was > done ? was : need;
  $('rsPages').min = done + 1;
  $('rsHint').textContent = (was && was <= done ? 'Прошлого лимита не хватило, подставлен побольше. ' : '')
    + `Чтобы обойти всё, что уже нашлось, нужно около ${num(need)}. По ходу могут найтись новые страницы.`;
  $('rsErr').textContent = '';
  $('rsDlg').showModal(); $('rsPages').focus();
}
$('rsCancel').onclick = () => $('rsDlg').close();
$('rsPages').addEventListener('keydown', e => { if (e.key === 'Enter') $('rsGo').click(); });
$('rsGo').onclick = () => {
  const c = rsCheck, done = (c.summary || {}).pages || 0, n = Math.floor(+$('rsPages').value);
  if (!(n > done)) { $('rsErr').textContent = `Уже проверено ${num(done)}, лимит должен быть больше.`; return; }
  $('rsDlg').close();
  showView('home');
  document.querySelector('input[name=mode][value=site]').checked = true; showMode();
  $('site').value = c.site; $('resume').checked = true;
  const sel = $('pages');
  sel.querySelectorAll('option[data-resume]').forEach(o => o.remove());
  if (![...sel.options].some(o => +o.value === n)) {  // лимита нет в списке: добавляем его на своё место
    const o = new Option(num(n), n); o.dataset.resume = '1';
    sel.insertBefore(o, [...sel.options].find(x => +x.value > n) || null);
  }
  sel.value = String(n);
  formFoldAuto = false; foldForm(false);
  $('form').scrollIntoView({behavior: 'smooth', block: 'start'});
  $('go').click();
};

// ---------- Сравнение с конкурентами из карточки своего сайта
let cmpOwn = null;
const cmpPicked = {};   // выбор галочек по своему сайту: закрыли окно и открыли снова - галочки на месте
function openCompare(key){
  const g = REP.sites.find(x => x.key === key); if (!g) return;
  const own = g.checks.find(c => c.finished); if (!own) return;
  cmpOwn = own;
  $('cmpOwn').textContent = host(own.site) + ', проверка ' + when(own.finished);
  const others = REP.sites.filter(x => x.key !== key).map(x => [x, x.checks.find(c => c.finished)]).filter(([, c]) => c);
  $('cmpList').innerHTML = others.length ? others.map(([x, c]) => `<label class="pick"><input type="checkbox" value="${esc(c.folder)}"><span><b>${esc(host(c.site))}</b> <span class="mut">${esc(when(c.finished))}${
    c.summary && c.summary.health != null ? ' · здоровье ' + c.summary.health + '%' + (c.health_old ? ' <span title="Отчёт собран до 15.10.2026 по старому расчёту здоровья. «⋯ → Обновить отчёт» пересчитает.">(старый расчёт)</span>' : '') : ''}</span></span></label>`).join('')
    : '<p class="mut">Других сайтов в списке нет. Сначала проверьте конкурента: впишите его адрес в поле «Сайты конкурентов» при новой проверке.</p>';
  const was = new Set(cmpPicked[own.folder] || []);
  $('cmpList').querySelectorAll('input').forEach(i => { i.checked = was.has(i.value); });
  $('cmpErr').textContent = '';
  cmpCount();
  $('cmpdlg').showModal();
}
function cmpCount(){
  const picked = [...$('cmpList').querySelectorAll('input:checked')].map(i => i.value), n = picked.length;
  if (cmpOwn) cmpPicked[cmpOwn.folder] = picked;
  $('cmpGo').disabled = n < 1 || n > 5;
  $('cmpGo').textContent = n ? `Сравнить (${n})` : 'Сравнить';
  $('cmpN').textContent = n ? `Выбрано: ${n} из 5. Теперь нажмите «Сравнить»` : 'Конкуренты не выбраны';
  $('cmpErr').textContent = n > 5 ? 'Не больше 5 конкурентов за раз.' : '';
  return n;
}
$('cmpList').addEventListener('change', cmpCount);
$('cmpCancel').onclick = () => $('cmpdlg').close();
// клик мимо окна: без выбора - закрыть, с выбором - не терять галочки, а показать, что нажать
$('cmpdlg').addEventListener('click', e => {
  if (e.target !== $('cmpdlg')) return;
  const r = $('cmpdlg').getBoundingClientRect();
  if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) return;
  if (!cmpCount()) { $('cmpdlg').close(); return; }
  $('cmpErr').textContent = 'Чтобы сравнить, нажмите «Сравнить» внизу. Закрыть без сравнения - «Отмена».';
  const b = $('cmpdlg').querySelector('.dlg-btns'); b.classList.remove('nudge'); void b.offsetWidth; b.classList.add('nudge');
});
$('cmpGo').onclick = async () => {
  const folders = [cmpOwn.folder, ...[...$('cmpList').querySelectorAll('input:checked')].map(i => i.value)];
  const r = await fetch('/api/compare_sites', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({folders})});
  const j = await r.json(); if (!r.ok) { $('cmpErr').textContent = j.error || 'Не получилось'; return; }
  $('cmpdlg').close(); poll();
};
// ---------- Страница глазами поисковика
$('rvGo').onclick = async () => {
  const url = $('rvUrl').value.trim();
  if (!url) { $('rvErr').textContent = 'Введите адрес страницы.'; return; }
  $('rvErr').textContent = ''; $('rvGo').disabled = true; $('rvGo').textContent = 'Загружаю…';
  try {
    const r = await fetch('/api/robot_view', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, ua: $('rvUa').value})});
    const j = await r.json();
    if (!r.ok) { $('rvErr').textContent = j.error || 'Не получилось'; return; }
    showRobotView(j);
  } catch (e) { $('rvErr').textContent = 'Не получилось: ' + e; }
  finally { $('rvGo').disabled = false; $('rvGo').textContent = 'Показать'; }
};
$('rvUrl').addEventListener('keydown', e => { if (e.key === 'Enter') $('rvGo').click(); });
function showRobotView(j){
  const rows = [];
  const chain = j.chain.map(c => `${esc(c.url)} → ${esc(c.status)}`).join('<br>');
  rows.push(['Ответ', j.chain.length > 1 ? chain : j.error && !j.status ? `<span class="bad">${esc(j.error)}</span>`
    : `${esc(j.status)} · ${String(j.elapsed).replace('.', ',')} с · ${mb(j.size)}`]);
  if (j.error || !j.html) { $('rvSum').innerHTML = rows.map(([k, v]) => `<div class="k">${k}</div><div>${v}</div>`).join('');
    $('rvOut').hidden = false; $('rvFrame').hidden = true; $('rvSnip').hidden = true; $('rvErr').textContent = j.error || 'Страница пустая'; return; }
  const one = (arr, what) => !arr.length ? `<span class="bad">нет</span>` : arr.length > 1
    ? `<span class="bad">${arr.length} ${what}:</span> ` + arr.map(esc).join(' | ') : esc(arr[0]);
  rows.push(['Title', one(j.title, 'штуки')]);
  rows.push(['Description', one(j.description, 'штуки')]);
  rows.push(['H1', one(j.h1, 'штуки')]);
  rows.push(['Индексация', (j.robots.length || j.x_robots) ? `<span class="bad">${esc([...j.robots, j.x_robots].filter(Boolean).join(', '))}</span>` : '<span class="ok">запретов нет</span>']);
  rows.push(['Canonical', j.canonical.length ? j.canonical.map(esc).join(' | ') : 'нет']);
  rows.push(['Текст', `${num(j.words)} слов · язык ${esc(j.lang || 'не указан')} · кодировка ${esc(j.encoding)}`]);
  rows.push(['Ссылки', `${num(j.links)}, из них на свой сайт ${num(j.links_internal)}`]);
  rows.push(['Картинки', `${num(j.images)}` + (j.images_no_alt ? `, <span class="bad">без alt: ${num(j.images_no_alt)}</span>` : '')]);
  if (j.mixed) rows.push(['Смешанные буквы', `<span class="bad">${j.mixed} - подсвечены красным</span>`]);
  $('rvSum').innerHTML = rows.map(([k, v]) => `<div class="k">${k}</div><div>${v}</div>`).join('');
  showSnippet(j);
  $('rvFrame').srcdoc = j.html;
  $('rvHeads').innerHTML = j.headings.length ? j.headings.map(([t, s]) => `<div style="margin-left:${(+t[1] - 1) * 18}px"><b>${t}</b>${esc(s) || '<span class="mut">(пусто)</span>'}</div>`).join('') : '<p class="mut">Заголовков H1–H6 нет.</p>';
  $('rvSrc').textContent = j.source;
  $('rvOut').hidden = false; setTab('clean');
}
// Сниппет в выдаче Google на компьютере: Google режет title и description по ширине в пикселях, а не по числу букв.
// Ширину меряем тем же шрифтом (Arial: заголовок 20 px, описание 14 px), поэтому цифры примерные.
const SNIP = {title: {font: '20px Arial', max: 561}, desc: {font: '14px Arial', max: 985}};
function pxWidth(s, font){
  const c = pxWidth.c || (pxWidth.c = document.createElement('canvas').getContext('2d'));
  c.font = font; return Math.round(c.measureText(s).width);
}
function snipCut(s, {font, max}){  // как Google: по целым словам, в конце « ...»
  s = s.replace(/\s+/g, ' ').trim();
  if (pxWidth(s, font) <= max) return s;
  let out = '';
  for (const w of s.split(' ')) { const t = out ? out + ' ' + w : w; if (pxWidth(t + ' ...', font) > max) break; out = t; }
  if (!out) { let i = s.length; while (i > 0 && pxWidth(s.slice(0, i) + '...', font) > max) i--; out = s.slice(0, i); }
  return out.replace(/[\s,.;:!?-]+$/, '') + ' ...';
}
function showSnippet(j){
  const line = (name, text, o) => {
    if (!text) return `<div class="n">${name}: <span class="bad">нет</span></div>`;
    const t = text.replace(/\s+/g, ' ').trim(), cut = snipCut(t, o), w = pxWidth(t, o.font), shown = cut.endsWith(' ...') ? cut.length - 4 : t.length;
    const n = `${t.length} ${plural(t.length, 'символ', 'символа', 'символов')}`, px = plural(o.max, 'пикселя', 'пикселей', 'пикселей');
    return `<div class="n">${name}: ${n}, ` + (w > o.max
      ? `<span class="bad">показано ${shown}, ширина ${num(w)} из ${num(o.max)} ${px}</span>`
      : `<span class="ok">помещается целиком</span>, ширина ${num(w)} из ${num(o.max)} ${px}`) + `</div>`;
  };
  const title = j.title[0] || '', desc = j.description[0] || '';
  let u = j.url;
  try { const x = new URL(j.url); u = [x.hostname, ...decodeURIComponent(x.pathname).split('/').filter(Boolean)].join(' › '); } catch (e) {}
  $('rvSnip').innerHTML = `<h3>Как страница может выглядеть в выдаче Google</h3>
    <div class="serp"><div class="u">${esc(u)}</div>
    <div class="t">${title ? esc(snipCut(title, SNIP.title)) : '<span class="mut">(title нет, Google возьмёт заголовок сам)</span>'}</div>
    <div class="d">${desc ? esc(snipCut(desc, SNIP.desc)) : '<span class="mut">(description нет, Google возьмёт кусок текста страницы)</span>'}</div></div>
    ${line('Title', title, SNIP.title)}${line('Description', desc, SNIP.desc)}
    <p class="mut" style="margin:8px 0 0">Ширина посчитана шрифтом Arial, как в выдаче Google на компьютере, поэтому цифры примерные.
    Google режет по пикселям и может сам заменить заголовок или описание. Яндекс обрезает по-своему (заголовок обычно показывает длиннее)
    и тоже часто переписывает заголовок и описание под запрос.</p>`;
  $('rvSnip').hidden = false;
}
function setTab(t){
  document.querySelectorAll('.rv-tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  $('rvFrame').hidden = t !== 'clean'; $('rvHeads').hidden = t !== 'heads'; $('rvSrc').hidden = t !== 'src';
}
document.querySelector('.rv-tabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setTab(b.dataset.tab); });
// ---------- Пороги и проверки
let ST = null;
async function loadSettings(){
  ST = await (await fetch('/api/settings')).json();
  $('stThr').innerHTML = ST.thresholds.map(t => `<label for="st_${t.name}" style="margin:0;color:var(--tx)">${esc(t.label)}</label>
    <input type="number" step="any" min="0" id="st_${t.name}" data-name="${t.name}" value="${t.value}" class="${t.value != t.default ? 'changed' : ''}">
    <span class="mut">${esc(t.unit)}${t.value != t.default ? ` · обычно ${t.default}` : ''}</span>`).join('');
  const cats = {};
  ST.checks.forEach(c => (cats[c.category] = cats[c.category] || []).push(c));
  $('stChecks').innerHTML = Object.keys(cats).sort().map(cat => `<div class="st-cat">${esc(cat)}</div>` + cats[cat].map(c =>
    `<label class="st-check${c.off ? ' off' : ''}"><input type="checkbox" data-key="${esc(c.key)}" ${c.off ? '' : 'checked'}><span>${esc(c.title)}</span> <span class="sev">${esc(c.severity)}</span></label>`).join('')).join('');
  countOff();
}
function countOff(){
  const off = document.querySelectorAll('#stChecks input:not(:checked)').length;
  $('stCount').textContent = `(${ST.checks.length}${off ? `, выключено ${off}` : ''})`;
}
$('stChecks').addEventListener('change', e => { const l = e.target.closest('.st-check'); if (l) l.classList.toggle('off', !e.target.checked); countOff(); $('stOk').textContent = ''; });
$('stThr').addEventListener('input', () => { $('stOk').textContent = ''; });
async function saveSettings(thresholds, disabled){
  const r = await fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({thresholds, disabled})});
  const j = await r.json();
  if (!r.ok) { $('stErr').textContent = j.error || 'Не получилось'; return; }
  $('stErr').textContent = ''; await loadSettings(); $('stOk').textContent = 'Сохранено';
}
$('stSave').onclick = () => {
  const thr = {}; document.querySelectorAll('#stThr input').forEach(i => thr[i.dataset.name] = i.value);
  const dis = [...document.querySelectorAll('#stChecks input:not(:checked)')].map(i => i.dataset.key);
  saveSettings(thr, dis);
};
$('stReset').onclick = () => {
  if (!confirm('Вернуть все пороги к обычным значениям и включить все проверки?')) return;
  saveSettings({}, []);
};
loadReports(); poll();
fetch('/api/version').then(r => r.json()).then(V => { $('appVer').textContent = `Версия ${V.app} · Семантика ${V.semantics}`; }).catch(() => {});

// ---- Поиск по сайту (по готовой проверке) ----
document.querySelectorAll('.sr-presets button').forEach(b => b.onclick = () => { $('srQ').value = b.dataset.q; $('srMode').value = 'has'; srMode(); });
function srMode(){ const c = $('srMode').value.startsWith('no_'); $('srQ').disabled = c; $('srWhere').disabled = c; }
$('srMode').onchange = srMode;
$('srGo').onclick = async () => {
  const folder = $('srSite').value;
  if (!folder) { $('srErr').textContent = 'Сначала проверьте сайт.'; return; }
  $('srErr').textContent = ''; $('srGo').disabled = true; $('srGo').textContent = 'Ищу…';
  try {
    const r = await fetch('/api/search', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({folder, query: $('srQ').value, mode: $('srMode').value, where: $('srWhere').value, regex: $('srRx').checked})});
    const j = await r.json();
    if (!r.ok) { $('srErr').textContent = j.error || 'Не получилось'; $('srOut').hidden = true; return; }
    const csv = j.csv ? ` <a href="/r/${encodeURIComponent(folder)}/${encodeURIComponent(j.csv)}">Скачать список для Excel</a>` : '';
    $('srSum').innerHTML = `Найдено страниц: <b>${num(j.found)}</b> из ${num(j.pages)} проверенных.` +
      (j.limited ? ` Показаны первые ${num(j.rows.length)}, все - в файле.` : '') + (j.found ? csv : '');
    $('srRows').innerHTML = j.rows.map(x => `<tr><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url)}</a>${x.title ? `<div class="mut">${esc(x.title)}</div>` : ''}</td>
      <td class="nowrap">${esc(x.where)}${x.n > 1 ? ` <span class="mut">×${x.n}</span>` : ''}</td><td>${esc(x.snippet).replace(/\[(.+?)\]/, '<mark>$1</mark>')}</td></tr>`).join('');
    $('srOut').hidden = false;
  } catch (e) { $('srErr').textContent = 'Не получилось: ' + e; }
  finally { $('srGo').disabled = false; $('srGo').textContent = 'Найти'; }
};

// ---- Свои данные со страниц: правила извлечения (seocrawler/extract.py) ----
const EX_PRESETS = [
  {name: 'Цена', type: 'css', expr: '[itemprop=price]', what: 'attr:content'},
  {name: 'Артикул', type: 'regex', expr: 'Артикул\\s*:\\s*([\\w\\-./]+)', what: 'text'},
  {name: 'Телефон', type: 'css', expr: 'a[href^="tel:"]', what: 'attr:href'},
  {name: 'Метрика в коде', type: 'regex', expr: 'mc\\.yandex\\.ru/metrika|yaCounter|ym\\(', what: 'count'},
  {name: 'Картинок без alt', type: 'css', expr: 'img:not([alt])', what: 'count'},
  {name: 'Хлебные крошки', type: 'xpath', expr: '//*[contains(@class,"breadcrumb")]//a', what: 'text'},
];
const EX_TYPES = {css: 'CSS-селектор', xpath: 'XPath', regex: 'Регулярное выражение'};
const EX_WHATS = {text: 'текст', html: 'код внутри', count: 'сколько найдено', attr: 'атрибут…'};
function exRow(r){
  const attr = (r.what || '').startsWith('attr:'), tr = document.createElement('tr');
  tr.innerHTML = `<td><input class="ex-name" value="${esc(r.name || '')}" placeholder="Цена"></td>
    <td><select class="ex-type">${Object.entries(EX_TYPES).map(([k, t]) => `<option value="${k}"${k === (r.type || 'css') ? ' selected' : ''}>${t}</option>`).join('')}</select></td>
    <td><input class="ex-expr" value="${esc(r.expr || '')}" placeholder=".price"></td>
    <td><select class="ex-what">${Object.entries(EX_WHATS).map(([k, t]) => `<option value="${k}"${k === (attr ? 'attr' : r.what || 'text') ? ' selected' : ''}>${t}</option>`).join('')}</select>
      <input class="ex-attr" placeholder="имя атрибута: content, href, src" value="${esc(attr ? r.what.slice(5) : '')}"${attr ? '' : ' hidden'}></td>
    <td><input class="ex-site" value="${esc(r.site || '')}" placeholder="все сайты"></td>
    <td><button class="ex-del" title="Убрать правило">✕</button></td>`;
  tr.querySelector('.ex-what').onchange = e => { tr.querySelector('.ex-attr').hidden = e.target.value !== 'attr'; };
  tr.querySelector('.ex-del').onclick = () => tr.remove();
  $('exRows').appendChild(tr);
}
function exRules(){
  return [...$('exRows').querySelectorAll('tr')].map(tr => {
    const w = tr.querySelector('.ex-what').value;
    return {name: tr.querySelector('.ex-name').value, type: tr.querySelector('.ex-type').value, expr: tr.querySelector('.ex-expr').value,
            what: w === 'attr' ? 'attr:' + tr.querySelector('.ex-attr').value.trim() : w, site: tr.querySelector('.ex-site').value};
  }).filter(r => r.name.trim() || r.expr.trim());
}
async function exLoad(){
  try { const j = await (await fetch('/api/extract')).json(); $('exRows').innerHTML = ''; j.rules.forEach(exRow); } catch (e) {}
}
$('exAdd').onclick = () => exRow({});
document.querySelectorAll('button[data-ex]').forEach(b => b.onclick = () => exRow(EX_PRESETS[+b.dataset.ex]));
$('exSave').onclick = async () => {
  $('exErr').textContent = $('exOk').textContent = '';
  const r = await fetch('/api/extract', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({rules: exRules()})});
  const j = await r.json();
  if (!r.ok) { $('exErr').textContent = j.error || 'Не получилось'; return; }
  $('exRows').innerHTML = ''; j.rules.forEach(exRow);
  $('exOk').textContent = j.rules.length ? `Сохранено правил: ${j.rules.length}. Сработают при следующей проверке сайта.` : 'Правил нет.';
};
$('exTest').onclick = async () => {
  $('exTErr').textContent = ''; $('exTest').disabled = true; $('exTest').textContent = 'Открываю…';
  try {
    const r = await fetch('/api/extract_test', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: $('exUrl').value, rules: exRules()})});
    const j = await r.json();
    if (!r.ok) { $('exTErr').textContent = j.error || 'Не получилось'; $('exTOut').hidden = true; return; }
    $('exTSum').textContent = `Ответ сайта: ${j.status}, ${j.url}`;
    $('exTRows').innerHTML = j.values.map(v => `<tr><td>${esc(v.name)}</td><td>${v.values.length ? v.values.map(esc).join('<br>') : '<span class="mut">ничего не нашлось</span>'}</td></tr>`).join('');
    $('exTOut').hidden = false;
  } catch (e) { $('exTErr').textContent = 'Не получилось: ' + e; }
  finally { $('exTest').disabled = false; $('exTest').textContent = 'Проверить'; }
};
exLoad();

// ---- Вебмастер и Search Console: вход без пароля ----
async function loadAccounts(){
  let A; try { A = await (await fetch('/api/accounts')).json(); } catch (e) { return; }
  acChips(A);
  $('acList').innerHTML = Object.entries(A).map(([p, a]) => `<div class="ac" data-p="${p}">
    <h3>${esc(a.name)} ${a.expired ? `<span class="bad">${esc(a.relogin || 'вход истёк')}</span>` : a.connected ? '<span class="ok">подключён</span>' : ''}</h3>
    ${a.connected ? `<p>Аккаунт: <b>${esc(a.account || '-')}</b>, с ${esc(a.since)}. Сайтов доступно: ${a.sites.length}</p>
      ${a.sites.length ? `<details><summary class="mut">Список сайтов</summary><p class="mut">${a.sites.map(esc).join('<br>')}</p></details>` : ''}
      <div class="st-btns">${a.expired ? '<button class="primary" data-act="login">Подключить заново</button>' : '<button data-act="refresh">Обновить список сайтов</button>'}<button data-act="logout">Отключить</button></div>`
    : a.has_app ? `<div class="st-btns"><button class="primary" data-act="login">Войти через ${p === 'yandex' ? 'Яндекс' : 'Google'}</button>
      <button data-act="edit">Изменить данные приложения</button></div>` : ''}
    <div class="ac-app" ${a.has_app ? 'hidden' : ''}>
      <p class="mut">Один раз зарегистрируйте своё приложение и вставьте его данные:</p>
      <ol class="mut">${a.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      <div class="st-grid"><div><label>ClientID</label><input type="text" class="ac-id" value="${esc(a.client_id)}"></div>
      <div><label>Client secret</label><input type="password" class="ac-sec" placeholder="${a.has_app ? 'не менять' : ''}"></div></div>
      <div class="st-btns"><button class="primary" data-act="app">Сохранить</button></div></div>
    <div class="err">${esc(a.error)}</div></div>`).join('');
  acOnly();
}
// окошко подключений - только тот сервис, который нажали в «Подключениях»: Яндекс, Google или Директ (
// раньше в одном окне были все три, и Директ было не найти)
const AC_TITLE = {yandex: 'Яндекс Вебмастер и Метрика', google: 'Google Search Console', direct: 'Яндекс Директ: точная частотность'};
let AC_P = '';
function acOnly(){
  document.querySelectorAll('#acList .ac').forEach(x => { x.hidden = !!AC_P && x.dataset.p !== AC_P; });
  $('dirBox').hidden = !!AC_P && AC_P !== 'direct';
  $('acIntro').hidden = AC_P === 'direct';
  // один сервис: его заголовок - наверху окошка вместе с отметкой («подключён», «ключ вставлен»), без повтора ниже
  const box = AC_P === 'direct' ? $('dirBox') : document.querySelector(`#acList .ac[data-p="${AC_P}"]`);
  const h3 = box && box.querySelector('h3'), mark = h3 && h3.querySelector('span');
  document.querySelectorAll('#acDlg .ac h3').forEach(x => { x.hidden = !!AC_P && x === h3; });
  $('acTitle').innerHTML = esc(AC_TITLE[AC_P] || 'Вебмастер, Метрика, Search Console и Директ') + (AC_P && mark ? ' ' + mark.outerHTML : '');
}
// «Подключения» внизу меню слева: Яндекс, Google, Telegram. Точка - состояние, по нажатию - окошко с настройкой
function connState(el, cls, short){ el.className = el.className.replace(/\b(on|off|bad)\b/g, '').trim() + ' ' + cls; el.querySelector('small').textContent = short; }
let AC_LAST = null;   // последний ответ /api/accounts: подсказки адресов пересобираются, когда загрузится список проверок
function acChips(A){
  AC_LAST = A;
  for (const [p, id] of [['yandex', 'acChipY'], ['google', 'acChipG']]) {
    const a = A && A[p]; if (!a) continue;
    const [cls, text] = a.expired ? ['bad', a.relogin || 'вход истёк'] : a.connected && a.error ? ['bad', 'ошибка'] : a.connected ? ['on', 'подключён'] : ['off', 'не подключён'];
    connState($(id), cls, cls === 'on' ? '' : a.expired ? (a.relogin === 'вход истёк' ? 'истёк' : 'нет доступа') : cls === 'bad' ? 'ошибка' : 'нет');
    $(id).title = a.name + ': ' + text + (a.connected ? ' - ' + (a.account || '') + ', сайтов: ' + a.sites.length : '') + (a.error ? '\n' + a.error : '');
  }
  // подсказки в поле «Адрес сайта»: сайты, к которым есть доступ в Вебмастере и Search Console (клиент дал гостевой
  // доступ - один вход видит все его сайты). Ещё не проверенные - первыми
  const seen = new Set(REP.sites.map(g => g.key)), opts = new Map();
  for (const p of ['yandex', 'google']) for (const u of (A && A[p] && A[p].sites) || []) {
    const h = host(String(u).replace(/^sc-domain:/, 'https://')).split('/')[0];
    if (h && !opts.has(h)) opts.set(h, (p === 'yandex' ? 'Вебмастер' : 'Search Console') + (seen.has(h.replace(/^www\./, '')) ? '' : ', ещё не проверялся'));
  }
  $('siteList').innerHTML = [...opts].sort((a, b) => (a[1].includes('ещё') ? 0 : 1) - (b[1].includes('ещё') ? 0 : 1) || a[0].localeCompare(b[0]))
    .map(([h, t]) => `<option value="https://${esc(h)}/" label="${esc(t)}"></option>`).join('');
}
async function acRefreshChips(){
  try { acChips(await (await fetch('/api/accounts')).json()); } catch (e) {}
  try { dirChip(await (await fetch('/api/direct')).json()); } catch (e) {}
}
// «Директ» в «Подключениях»: ключ вставлен и проверка прошла - зелёная точка, проверка не прошла - красная
function dirChip(D){
  const el = $('acChipD'); if (!el || !D) return;
  const cls = !D.has_token ? 'off' : D.check && !D.check_ok ? 'bad' : 'on';
  connState(el, cls, cls === 'off' ? 'нет' : cls === 'bad' ? 'ошибка' : '');
  el.title = 'Яндекс Директ: ' + (cls === 'off' ? 'ключ не вставлен' : D.check || 'ключ вставлен, не проверялся');
}
document.querySelectorAll('.ac-chip').forEach(b => b.onclick = () => { AC_P = b.dataset.p || ''; acOnly(); $('acDlg').showModal(); loadAccounts(); loadDirect(); });
$('acClose').onclick = () => { $('acDlg').close(); acRefreshChips(); };
acRefreshChips();
setInterval(acRefreshChips, 60000);
$('acList').addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  const box = b.closest('.ac'), provider = box.dataset.p, act = b.dataset.act, err = box.querySelector('.err');
  if (act === 'edit') { box.querySelector('.ac-app').hidden = false; return; }
  if (act === 'logout' && !confirm('Отключить? Ключ доступа будет отозван и стёрт с компьютера.')) return;
  const body = {provider};
  if (act === 'app') { body.client_id = box.querySelector('.ac-id').value; body.secret = box.querySelector('.ac-sec').value; }
  b.disabled = true; err.textContent = '';
  const r = await fetch('/api/accounts/' + act, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json(); b.disabled = false;
  if (!r.ok) { err.textContent = j.error || 'Не получилось'; return; }
  if (act === 'login') {
    err.innerHTML = `<span style="color:#222">Открылась страница входа в браузере. Войдите и нажмите «Разрешить», потом вернитесь сюда. <a href="${esc(j.url)}" target="_blank">Если не открылась - нажмите здесь</a></span>`;
    const t0 = Date.now(), iv = setInterval(async () => {   // ждём, пока вход завершится
      const A = await (await fetch('/api/accounts')).json();
      if ((A[provider].connected && !A[provider].expired && (A[provider].account || A[provider].error)) || Date.now() - t0 > 600000) { clearInterval(iv); loadAccounts(); }
    }, 2000);
    return;
  }
  loadAccounts();
});

// ---- Яндекс Директ: ключ для точной частотности Вордстата (direct.py) ----
async function loadDirect(){
  let D; try { D = await (await fetch('/api/direct')).json(); } catch (e) { return; }
  dirChip(D);
  $('dirBox').innerHTML = `<h3>Яндекс Директ: точная частотность ${D.has_token ? '<span class="ok">ключ вставлен</span>' : ''}</h3>
    <p class="mut">Частотность Вордстата по городу семантики через API Директа (бесплатно, нужен одобренный доступ к API). Загрузка - на странице «Семантика».</p>
    ${D.check ? `<p class="${D.check_ok ? '' : 'err'}">${esc(D.check)}</p>` : ''}
    ${D.has_token ? `<p class="mut">Ключ с ${esc(D.since)}. Сегодня фраз: ${num(D.used)} из ${num(D.limit)}.</p>` : ''}
    <ol class="mut"><li>Впишите ClientID приложения на oauth.yandex.ru, у которого есть доступ к API Директа, и нажмите «Сохранить».</li>
      <li>«Получить ключ» откроет страницу Яндекса: нажмите «Разрешить» и скопируйте показанный ключ.</li>
      <li>Вставьте ключ сюда, «Сохранить», потом «Проверить».</li></ol>
    <div class="st-grid"><div><label>ClientID</label><input type="text" id="dirId" value="${esc(D.client_id)}"></div>
      <div><label>Ключ (токен)</label><input type="password" id="dirTok" placeholder="${D.has_token ? 'не менять' : ''}" autocomplete="off"></div>
      <div><label>Логин Директа (необязательно, для остатка баллов)</label><input type="text" id="dirLogin" value="${esc(D.login)}"></div></div>
    <div class="st-btns"><button class="primary" data-d="save">Сохранить</button>${D.client_id ? '<button data-d="key">Получить ключ</button>' : ''}
      ${D.has_token ? '<button data-d="check">Проверить</button><button data-d="forget">Стереть ключ</button>' : ''}</div>
    <div class="err" id="dirErr"></div>`;
  acOnly();
}
$('dirBox').addEventListener('click', async e => {
  const b = e.target.closest('button[data-d]'); if (!b) return;
  const act = b.dataset.d, err = $('dirErr');
  if (act === 'forget' && !confirm('Стереть ключ Директа с компьютера?')) return;
  const body = act === 'save' ? {client_id: $('dirId').value, token: $('dirTok').value, login: $('dirLogin').value} : {};
  b.disabled = true; err.textContent = act === 'check' ? 'Проверяю: составляю один маленький отчёт Вордстата…' : '';
  try {
    const r = await fetch('/api/direct/' + act, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const j = await r.json();
    if (!r.ok) { await loadDirect(); $('dirErr').textContent = j.error || 'Не получилось'; return; }
    await loadDirect();
    if (act === 'key') $('dirErr').innerHTML = `<span style="color:#222">Открылась страница Яндекса. Нажмите «Разрешить», скопируйте ключ и вставьте его выше. <a href="${esc(j.url)}" target="_blank">Если не открылась - нажмите здесь</a></span>`;
  } catch (x) { err.textContent = 'Не получилось: ' + x; }
  finally { b.disabled = false; }
});

// ---- Сообщение в Telegram: строка в «Подключениях» и окошко настройки ----
function tgState(T){
  if (!T.ready) return ['off', T.has_token ? 'Telegram: напишите боту' : 'Telegram: не подключён'];
  if (T.online === false) return ['bad', 'Telegram: нет связи'];
  if (!T.enabled) return ['off', 'Telegram: выключен'];
  return ['on', 'Telegram: подключён'];
}
async function tgStatus(live){
  try { return await (await fetch('/api/telegram' + (live ? '?live=1' : ''))).json(); } catch (e) { return null; }
}
function tgChip(T){
  if (!T) return;
  const [cls, text] = tgState(T);
  connState($('tgChip'), cls, cls === 'on' ? '' : cls === 'bad' ? 'нет связи' : T.ready ? 'выключен' : 'нет');  // всё в порядке - только точка
  $('tgChip').title = T.ready ? (T.online === false ? 'Нет связи с Telegram: ' + (T.error || '') : text + '. Бот ' + T.bot + ' пишет вам. Нажмите, чтобы настроить')
                              : 'Настроить сообщение в Telegram, когда проверка закончилась';
}
async function loadTelegram(msg, ok){
  const T = await tgStatus(true); if (!T) return;
  tgChip(T);
  const [cls, text] = tgState(T);
  $('tgBox').innerHTML = `
    <p class="tg-state ${cls}"><i class="dot"></i><b>${esc(text.replace('Telegram: ', ''))}</b>
      ${T.ready ? `<span class="mut">- бот ${esc(T.bot)}${T.chat ? ', чат ' + esc(T.chat) : ''}</span>` : ''}</p>
    ${T.ready ? `<div class="checks">
        <label><input type="checkbox" data-opt="enabled" ${T.enabled ? 'checked' : ''}><span>Присылать итог, когда проверка закончилась</span></label>
        <label><input type="checkbox" data-opt="pdf" ${T.pdf ? 'checked' : ''}><span>Прикладывать аудит PDF<small>Можно открыть на телефоне или переслать клиенту.</small></span></label>
        <label><input type="checkbox" data-opt="stuck" ${T.stuck ? 'checked' : ''}><span>Предупреждать, если проверка застряла<small>Больше 15 минут не прибавляется ни одной страницы.</small></span></label></div>
      <p class="mut">Пока окно программы открыто, боту можно написать /status - ответит, что сейчас проверяется и сколько страниц готово, /last - итог последней проверки.</p>
      <div class="st-btns"><button class="primary" data-act="test">Проверить</button><button data-act="edit">Сменить бота</button><button data-act="off">Отключить</button></div>`
    : T.has_token ? `<p>Бот <b>${esc(T.bot)}</b> сохранён. Откройте его в Telegram, нажмите «Старт» или напишите «привет», потом:</p>
      <div class="st-btns"><button class="primary" data-act="chat">Найти чат и проверить</button><button data-act="off">Отключить</button></div>` : ''}
    <div id="tgSetup" ${T.ready ? 'hidden' : ''}>
      <ol class="mut">${T.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      <label>Токен бота</label><input type="password" id="tgToken" placeholder="${T.has_token ? 'вставьте новый, чтобы заменить' : '123456789:AAH…'}">
      <div class="st-btns"><button ${T.has_token ? '' : 'class="primary"'} data-act="token">Сохранить</button></div></div>
    <div class="err">${ok ? `<span style="color:var(--good)">${esc(ok)}</span>` : esc(msg || (T.online === false ? T.error : '') || '')}</div>`;
}
async function tgPost(act, body){
  const r = await fetch('/api/telegram/' + act, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body || {})});
  const j = await r.json();
  return r.ok ? '' : (j.error || 'Не получилось');
}
$('tgChip').onclick = () => { $('tgDlg').showModal(); loadTelegram(); };
$('tgClose').onclick = () => $('tgDlg').close();
$('tgBox').addEventListener('change', e => {
  const c = e.target.closest('input[data-opt]'); if (!c) return;
  tgPost('option', {name: c.dataset.opt, on: c.checked}).then(() => tgStatus().then(tgChip));
});
$('tgBox').addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  const act = b.dataset.act;
  if (act === 'edit') { $('tgSetup').hidden = false; return; }
  if (act === 'off' && !confirm('Отключить сообщения в Telegram? Токен бота будет стёрт с компьютера.')) return;
  b.disabled = true;
  const err = await tgPost(act, act === 'token' ? {token: $('tgToken').value} : {});
  b.disabled = false;
  await loadTelegram(err, !err && (act === 'test' || act === 'chat') ? 'Пробное сообщение отправлено - проверьте Telegram.' : '');
});
tgStatus(true).then(tgChip);
setInterval(() => tgStatus(true).then(tgChip), 60000);  // следим за связью: раз в минуту

// ---- Наблюдение: расписание раз в неделю и мониторинг каждый час ----
let W = {sites: [], days: []};
// время списком по 30 минут: поле type=time в английском Chrome показывает 09:00 AM
function wTimes(cur){
  const opts = [];
  for (let m = 0; m < 24 * 60; m += 30) opts.push(String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'));
  if (!opts.includes(cur)) opts.push(cur);
  return opts.sort().map(t => `<option ${t === cur ? 'selected' : ''}>${t}</option>`).join('');
}
function wChip(){
  const mon = W.sites.filter(s => s.monitor), bad = mon.filter(s => s.mon && s.mon.ok === false);
  const weekly = W.sites.filter(s => s.weekly).length;
  // в меню слева: красный счётчик сломанных сайтов, иначе серый - сколько сайтов под наблюдением
  const n = new Set(W.sites.filter(s => s.monitor || s.weekly).map(s => s.url)).size;
  $('wBadge').hidden = !bad.length && !n; $('wBadge').textContent = bad.length || n; $('wBadge').className = 'badge' + (bad.length ? ' bad' : '');
  // баннер сверху: на каких сайтах что-то сломалось
  $('alertBox').hidden = !bad.length;
  if (bad.length) $('alertText').innerHTML = `Наблюдение: ${bad.length > 1 ? 'на сайтах' : 'на'} ${bad.map(s => `<b>${esc(host(s.url))}</b>`).join(', ')} что-то сломалось`
    + (bad[0].mon.problems && bad[0].mon.problems.length ? `: ${esc(bad[0].mon.problems[0])}${bad.length > 1 || bad[0].mon.problems.length > 1 ? ' и другое' : ''}` : '') + '.';
  $('wChip').title = W.sites.length ? `Мониторинг: ${mon.length} сайт(ов)${bad.length ? ', с проблемами: ' + bad.length : ''}. Раз в неделю: ${weekly}.`
                                    : 'Проверка по расписанию и мониторинг сайтов - нажмите, чтобы добавить сайт';
}
async function loadWatch(){
  try { W = await (await fetch('/api/watch')).json(); } catch (e) { return; }
  wChip();
  if (!$('wDlg').open) return;
  $('wList').innerHTML = W.sites.length ? `<div class="tw"><table><thead><tr><th>Сайт</th><th>Мониторинг</th><th>Раз в неделю</th><th>Страниц</th><th></th></tr></thead><tbody>
    ${W.sites.map(s => {
      const m = s.mon || {}, w = s.weekly || {};
      const state = !s.monitor ? '' : !m.checked ? '<div class="mut">скоро первая проверка</div>'
        : m.ok ? `<div class="w-ok">в порядке · ${esc(m.checked)}</div>`
        : `<div class="w-bad">${(m.problems || []).map(esc).join('<br>')}<br><span class="mut">с ${esc(m.since || '')}</span></div>`;
      return `<tr data-url="${esc(s.url)}"><td><b>${esc(s.url)}</b>${state}</td>
        <td><label class="w-chk"><input type="checkbox" class="w-mon" ${s.monitor ? 'checked' : ''}> каждый час</label></td>
        <td class="nowrap"><select class="w-day"><option value="">выкл</option>${W.days.map((d, i) => `<option value="${d}" ${s.weekly && w.day === i ? 'selected' : ''}>${d}</option>`).join('')}</select>
          <select class="w-time">${wTimes(w.time || '09:00')}</select></td>
        <td><select class="w-pages">${[500, 2000, 10000, 50000].map(n => `<option ${(s.pages || 10000) === n ? 'selected' : ''}>${n}</option>`).join('')}</select></td>
        <td class="acts"><button class="w-now" ${s.monitor ? '' : 'disabled'} title="Проверить мониторингом сейчас">Проверить</button> <button class="w-del" title="Убрать из наблюдения">✕</button></td></tr>`;
    }).join('')}</tbody></table></div>` : '<p class="mut">Сайтов под наблюдением пока нет.</p>';
}
async function wPost(act, body){
  $('wErr').textContent = '';
  const r = await fetch('/api/watch/' + act, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json();
  if (!r.ok) $('wErr').textContent = j.error || 'Не получилось';
  await loadWatch();
  return r.ok;
}
function wRowData(tr){
  const day = tr.querySelector('.w-day').value;
  return {url: tr.dataset.url, monitor: tr.querySelector('.w-mon').checked,
          weekly: day ? day + ' ' + tr.querySelector('.w-time').value : '', pages: +tr.querySelector('.w-pages').value};
}
$('wChip').onclick = $('alertGo').onclick = () => { $('wDlg').showModal(); loadWatch(); };
$('wClose').onclick = () => $('wDlg').close();
$('wAdd').onclick = async () => {
  const url = $('wUrl').value.trim(); if (!url) return;
  if (await wPost('save', {url, monitor: true, weekly: '', pages: 10000})) $('wUrl').value = '';
};
$('wUrl').addEventListener('keydown', e => { if (e.key === 'Enter') $('wAdd').click(); });
$('wList').addEventListener('change', e => { const tr = e.target.closest('tr[data-url]'); if (tr) wPost('save', wRowData(tr)); });
$('wList').addEventListener('click', async e => {
  const tr = e.target.closest('tr[data-url]'); if (!tr) return;
  if (e.target.closest('.w-del')) {
    if (confirm('Убрать ' + tr.dataset.url + ' из наблюдения?')) wPost('remove', {url: tr.dataset.url});
  } else if (e.target.closest('.w-now')) {
    const b = e.target.closest('.w-now'); b.disabled = true; b.textContent = 'Проверяю…';
    await wPost('check_now', {url: tr.dataset.url});
  }
});
loadWatch();
setInterval(loadWatch, 60000);

// ---- Ваши данные в аудите: логотип и контакты ----
const BR = ['name', 'phone', 'email', 'site', 'telegram'];
let brLogo = '';
async function loadBrand(){
  let d; try { d = await (await fetch('/api/brand')).json(); } catch (e) { return; }
  BR.forEach(k => $('br_' + k).value = d[k] || '');
  $('brImg').hidden = !d.logo_uri; if (d.logo_uri) $('brImg').src = d.logo_uri; $('brNoLogo').hidden = !d.logo_uri; brLogo = '';
}
$('brLogo').onchange = () => {
  const f = $('brLogo').files[0]; if (!f) return;
  if (f.size > 600000) { $('brErr').textContent = 'Логотип больше 600 КБ - уменьшите картинку.'; return; }
  const r = new FileReader(); r.onload = () => { brLogo = r.result; $('brImg').src = brLogo; $('brImg').hidden = false; $('brNoLogo').hidden = false; $('brErr').textContent = ''; };
  r.readAsDataURL(f);
};
$('brNoLogo').onclick = () => { brLogo = '-'; $('brImg').hidden = true; $('brNoLogo').hidden = true; $('brLogo').value = ''; };
$('brSave').onclick = async () => {
  const body = {logo: brLogo}; BR.forEach(k => body[k] = $('br_' + k).value);
  const r = await fetch('/api/brand', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  $('brErr').textContent = r.ok ? '' : (j.error || 'Не получилось сохранить');
  if (r.ok) { $('brOk').textContent = 'Сохранено'; setTimeout(() => $('brOk').textContent = '', 2500); loadBrand(); }
};

// ---- Список адресов и переезд ----
function lsMode(){ const m = document.querySelector('input[name=lsMode]:checked').value; $('lsList').hidden = m !== 'list'; $('lsMove').hidden = m !== 'move'; }
document.querySelectorAll('input[name=lsMode]').forEach(r => r.onchange = lsMode);
async function loadLists(){
  let j; try { j = await (await fetch('/api/lists')).json(); } catch (e) { return; }
  $('lsPrev').innerHTML = j.items.length ? '<h3>Прошлые проверки списков</h3>' + j.items.map(x =>
    `<div class="ls-row"><a href="/r/${x.path.split('/').map(encodeURIComponent).join('/')}" target="_blank">${esc(x.title)}</a> <span class="mut">${esc(x.when)} · ${num(x.total)} адр.${x.bad ? ` · <b class="bad">потеряно ${num(x.bad)}</b>` : ''}</span></div>`).join('') : '';
}
$('lsGo').onclick = async () => {
  const move = document.querySelector('input[name=lsMode]:checked').value === 'move';
  const body = move ? {folder: $('lsSite').value, new_host: $('lsHost').value.trim()} : {urls: $('lsUrls').value};
  if (!move && !/https?:\/\//.test(body.urls)) { $('lsErr').textContent = 'Вставьте полные адреса, начинающиеся с https://'; return; }
  const r = await fetch('/api/list', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { $('lsErr').textContent = j.error || 'Не получилось запустить'; return; }
  $('lsErr').textContent = ''; showView('home'); poll(); $('run').scrollIntoView({behavior: 'smooth'});
};
// ---- Закрытые сайты ----
async function loadSiteAuth(){
  let j; try { j = await (await fetch('/api/site_auth')).json(); } catch (e) { return; }
  $('saList').innerHTML = j.sites.map(x => `<div class="ls-row"><b>${esc(x.host)}</b> <span class="mut">${x.user ? 'логин ' + esc(x.user) : ''}${x.has_cookie ? (x.user ? ', ' : '') + 'cookie' : ''}</span>
    <button class="small" data-sa-del="${esc(x.host)}">Удалить</button></div>`).join('');
}
$('saSave').onclick = async () => {
  const body = {site: $('sa_site').value.trim(), user: $('sa_user').value.trim(), password: $('sa_pass').value, cookie: $('sa_cookie').value.trim()};
  const r = await fetch('/api/site_auth/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  $('saErr').textContent = r.ok ? '' : (j.error || 'Не получилось сохранить');
  if (r.ok) { ['sa_site','sa_user','sa_pass','sa_cookie'].forEach(k => $(k).value = ''); $('saOk').textContent = 'Сохранено'; setTimeout(() => $('saOk').textContent = '', 2500); loadSiteAuth(); }
};
$('saList').addEventListener('click', async e => {
  const b = e.target.closest('[data-sa-del]'); if (!b) return;
  if (!confirm('Удалить логин и пароль для ' + b.dataset.saDel + '?')) return;
  await fetch('/api/site_auth/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({site: b.dataset.saDel})});
  loadSiteAuth();
});

// ---- Сообщить Яндексу об изменениях: IndexNow и очередь переобхода Вебмастера ----
function riSite(){ const o = $('riSite').selectedOptions[0]; return o ? o.textContent.split(' - ')[0] : ''; }
async function riPost(url, body){
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Не получилось'); return j;
}
async function riKey(){
  if (!$('riSite').value) return;
  $('riKey').textContent = 'Проверяю файл ключа на сайте…';
  try {
    const j = await riPost('/api/reindex/key', {folder: $('riSite').value});
    $('riKey').innerHTML = j.ok ? `Файл ключа на месте: <a href="${esc(j.url)}" target="_blank">${esc(j.file)}</a>. Можно отправлять.`
      : `Один раз: передайте разработчику файл <b>${esc(j.file)}</b> с текстом <code>${esc(j.key)}</code> - положить в корень сайта, чтобы открывался по адресу <a href="${esc(j.url)}" target="_blank">${esc(j.url)}</a>. Потом «Проверить файл».`;
  } catch (e) { $('riKey').textContent = e.message; }
}
$('riSite').addEventListener('change', riKey);
$('riKeyCheck').onclick = riKey;
$('riFind').onclick = async () => {
  $('riErr').textContent = ''; $('riFind').disabled = true;
  try {
    const j = await riPost('/api/reindex/changed', {folder: $('riSite').value});
    $('riUrls').value = j.urls.map(x => x[0]).join('\n');
    $('riInfo').textContent = j.urls.length ? `Сравнил с проверкой ${j.prev}: изменилось или появилось страниц - ${j.urls.length}.`
      : `Сравнил с проверкой ${j.prev}: изменённых страниц нет.`;
  } catch (e) { $('riErr').textContent = e.message; }
  finally { $('riFind').disabled = false; }
};
async function riSend(way){
  const urls = $('riUrls').value.split(/\s+/).filter(u => /^https?:\/\//.test(u));
  if (!urls.length) { $('riErr').textContent = 'Добавьте адреса страниц (или «Найти изменённые страницы»).'; return; }
  if (!confirm(`Отправить ${urls.length} адресов ${way === 'indexnow' ? 'в IndexNow (Яндекс и Bing)' : 'в очередь переобхода Вебмастера'}?`)) return;
  $('riErr').textContent = ''; $('riOk').textContent = 'Отправляю…';
  try { const j = await riPost('/api/reindex/send', {folder: $('riSite').value, way, urls}); $('riOk').textContent = j.message; }
  catch (e) { $('riOk').textContent = ''; $('riErr').textContent = e.message; }
}
$('riSendIN').onclick = () => riSend('indexnow');
$('riSendWM').onclick = () => riSend('webmaster');


// ---- Страницы окна: «Проверки и отчёты» и инструменты из меню слева (адрес после #: #search, #settings…)
const VIEW_LOAD = {settings: () => { if (!ST) loadSettings(); }, brand: loadBrand, list: loadLists, auth: loadSiteAuth, reindex: riKey,
  log: () => window.loadJournal && window.loadJournal()};   // «Журнал» - page/journal.js
// с других страниц окна: /#watch, /#yandex, /#google, /#direct, /#telegram - главная и сразу нужное окошко
const VIEW_DLG = {watch: 'wChip', yandex: 'acChipY', google: 'acChipG', direct: 'acChipD', telegram: 'tgChip'};
function showView(v){
  if (VIEW_DLG[v]) {
    const b = $(VIEW_DLG[v]), back = new URLSearchParams(location.search).get('back') || '';
    history.replaceState(null, '', location.pathname); showView('home');
    setTimeout(() => {
      b.click();
      // пришли из Семантики и т. п. (side.js, ?back=): закрыли окошко - обратно туда, только свой адрес
      const d = document.querySelector('dialog[open]');
      if (d && EMBED) d.addEventListener('close', () => parent.postMessage({claylerEmbed: 'close'}, location.origin), {once: true});
      else if (d && /^\/(?!\/)/.test(back)) d.addEventListener('close', () => { location.href = back; }, {once: true});
    }, 0);
    return;
  }
  if (!document.querySelector(`.view[data-view="${v}"]`)) v = 'home';
  document.querySelectorAll('.view').forEach(x => x.hidden = x.dataset.view !== v);
  // «Инструменты» подсвечен и на экранах самих инструментов (data-also)
  document.querySelectorAll('.nav[data-view]').forEach(a => a.classList.toggle('on', a.dataset.view === v || (a.dataset.also || '').split(' ').includes(v)));
  if (window.ClaylerSide) ClaylerSide.view(v);   // меню слева: какая комната (page/side.js)
  if (('#' + v) !== location.hash && !(v === 'home' && !location.hash)) history.replaceState(null, '', v === 'home' ? location.pathname : '#' + v);
  if (VIEW_LOAD[v]) VIEW_LOAD[v]();
  window.scrollTo(0, 0);
}
document.querySelectorAll('.nav[data-view]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showView(a.dataset.view); }));
// на экране каждого инструмента (data-also у «Инструменты») - ссылка обратно к списку инструментов
(document.querySelector('.nav[data-view="tools"]')?.dataset.also || '').split(' ').forEach(v => {
  const el = document.querySelector(`.view[data-view="${v}"]`);
  if (el) el.insertAdjacentHTML('afterbegin', '<a class="tool-back" href="#tools">← Все инструменты</a>');
});
window.addEventListener('hashchange', () => showView(location.hash.slice(1) || 'home'));
showView(location.hash.slice(1) || 'home');

// ---- Вид окна: паутина на фоне и паучок (модуль паутины, настройки в браузере)
(() => {
  const W = window.ClaylerWeb;
  if (!W || !W.getPrefs) { $('lookCard').hidden = true; return; }
  const p = W.getPrefs();
  $('webBgOn').checked = p.background !== false; $('webSpiderOn').checked = p.spider !== false;
  $('webBgOn').onchange = () => W.setPrefs({background: $('webBgOn').checked});
  $('webSpiderOn').onchange = () => W.setPrefs({spider: $('webSpiderOn').checked});
})();
