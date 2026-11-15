// Часть страницы «Семантика» (page/semantics.js - выбор сайта, загрузка, сбор, экраны по адресу после #): задачи по важности сверху страницы.
// Общие $, esc, num, plural, host, path, DATA, FOLDER, KIND, PAGE_SIZE и др. - из semantics.js (подключён раньше).
// ---------- задачи: что сделать на сайте, по важности
const PRIO = {hi: 'Важно', mid: 'Средне', lo: 'Потом'};
function tasks(){
  const G = DATA.groups, T = [];
  const cann = DATA.cannibal || [];
  const create = G.filter(g => g.kind === 'create'), fix = G.filter(g => g.kind === 'page' && g.a && g.a.problems.length);
  const absent = G.filter(g => g.kind === 'absent'), manual = G.filter(g => g.kind === 'manual');
  const near = nearList(), flt = fltList(), fltOk = flt.filter(([, f]) => f.products >= 3).length;
  const geo = (DATA.geo || {}).checks || [], geoOk = geo.filter(c => c.ok).length, nfaq = G.filter(g => g.faq && g.faq.length).length;
  const art = DATA.articles || [];
  const ex = (list, a, b) => list.slice(0, 3).map(x => [a(x), b(x)]);
  const tz = '/api/semantics_tz?f=' + encodeURIComponent(FOLDER), xlsx = '/api/semdec/xlsx?f=' + encodeURIComponent(FOLDER);
  if (cann.length) T.push({id: 'cannibal', p: 'hi', title: 'Страницы мешают друг другу', meta: `${num(cann.length)} ${plural(cann.length, 'случай', 'случая', 'случаев')}`,
    desc: 'По одному запросу на сайте несколько страниц: поиск не понимает, какую показывать, и обе стоят ниже. Оставьте одну главной, вторую сделайте про другое или склейте.',
    ex: ex(cann, c => c.why, c => c.pages.slice(0, 3).map(p => path(p.url)).join('  ·  ') + (c.pages.length > 3 ? `  и ещё ${c.pages.length - 3}` : '')), a1: ['Разобрать', '#cann'], a2: ['Список в Excel', xlsx]});
  // не та страница и смешанные группы, группы из текста кнопок и меню: решения в semdec.js (экраны #landing, #junk)
  const land = G.filter(g => g.landing), mixed = G.filter(g => g.mixed && !g.landing), junk = G.filter(g => g.junk);
  if (land.length || mixed.length) T.push({id: 'landing', p: 'hi', title: 'Похоже, не та страница', meta: [land.length && `${num(land.length)} ${plural(land.length, 'группа', 'группы', 'групп')}`,
      mixed.length && `смешаны запросы: ${num(mixed.length)}`].filter(Boolean).join(', '),
    desc: 'Группа привязана к странице, которая не про это, или в одной группе смешаны разные желания людей («онлайн» и «офлайн», «для детей» и «для взрослых»). Выберите правильную страницу, создайте новую или разделите группу.',
    ex: ex([...land, ...mixed], g => g.name, g => g.landing ? '→ ' + path(g.page) : `смешаны «${g.mixed.a}» и «${g.mixed.b}»`), a1: ['Проверить', '#landing']});
  if (junk.length) T.push({id: 'junk', p: 'mid', title: 'Группы из текста кнопок и меню', meta: 'похоже на мусор',
    desc: 'Эти группы собраны из подписей на сайте («Узнать подробнее», «Записаться»), а не из того, что ищут ваши клиенты. Уберите их: отчёт станет чище.',
    ex: ex(junk, g => g.name, g => g.q.length ? '«' + g.q[0][0] + '»' : ''), a1: ['Убрать в отсеянное', '#junk']});
  if (near.length) T.push({id: 'near', p: 'hi', title: 'Почти на первой странице', meta: `${num(near.length)} ${plural(near.length, 'запрос', 'запроса', 'запросов')} на 11–20 месте`,
    desc: 'Сайт уже рядом с первой страницей поиска: часто хватает поправить title и H1 под запрос, добавить абзац текста и пару внутренних ссылок.',
    ex: ex(near, ([r]) => r[0], ([r]) => String(r[8]).replace('.', ',') + ' место'), a1: ['Показать', '#near'], a2: ['Все в Excel', xlsx]});
  if (create.length) T.push({id: 'create', p: 'hi', title: 'Создать страницы', meta: `${num(create.length)} ${plural(create.length, 'группа', 'группы', 'групп')}`,
    desc: 'Спрос есть, а подходящей страницы на сайте нет. Для каждой готовы адрес, title, H1, описание, объём текста и подзаголовки.',
    ex: ex(create, g => g.name, g => g.land && g.land.url ? path(g.land.url) : `${num(g.q.length)} ${plural(g.q.length, 'запрос', 'запроса', 'запросов')}`), a1: ['Скачать ТЗ', tz], a2: ['Запрос → страница', '#pages/create']});
  if (fix.length) {
    const types = new Map();  // замечания по типу: «Title без …» - сколько страниц
    fix.forEach(g => g.a.problems.forEach(p => { const t = p.split(/[:(]| [-–—] /)[0].trim(); types.set(t, (types.get(t) || 0) + 1); }));
    T.push({id: 'fix', p: 'mid', title: 'Доработать страницы', meta: `${num(fix.length)} ${plural(fix.length, 'группа', 'группы', 'групп')} с замечаниями`,
      desc: 'Страница есть, но запросы группы на ней раскрыты слабо. Удобнее чинить по типу замечания.',
      ex: [...types].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([t, n]) => [t, `${num(n)} ${plural(n, 'страница', 'страницы', 'страниц')}`]),
      a1: ['Открыть список', '#groups/fix'], a2: ['ТЗ по страницам', tz]});
  }
  if (flt.length) T.push({id: 'flt', p: 'mid', title: 'Страницы-фильтры', meta: `${num(flt.length)}${fltOk ? `, под ${num(fltOk)} уже есть товары` : ''}`,
    desc: fltOk ? `Начните с ${num(fltOk)}: товары уже на сайте, осталось только создать страницу с подборкой.` : 'Частые уточнения запросов, под которые магазины делают отдельные страницы с подборкой товаров.',
    ex: ex(flt, ([, f]) => f.name, ([, f]) => `${num(f.queries)} ${plural(f.queries, 'запрос', 'запроса', 'запросов')}`), a1: [fltOk ? `Показать ${num(fltOk)}` : 'Показать', '#flt'], a2: [`Все ${num(flt.length)} в Excel`, xlsx]});
  // вход есть, но сбор не прошёл (нет связи, нет галочки Search Console) - пишем причину, а не «попросите владельца»
  const R = DATA.real || {}, badRun = ['no_link', 'no_scope', 'error'];
  if (!realOk()) T.push({id: 'access', p: 'mid', title: 'Подключить Вебмастер и Search Console', meta: 'точный спрос',
    desc: badRun.includes(R.wm) || badRun.includes(R.gsc)
      ? [badRun.includes(R.wm) && realWhy('Вебмастер', R.wm, 'Яндекс'), badRun.includes(R.gsc) && realWhy('Search Console', R.gsc, 'Google')].filter(Boolean).join(' ')
      : 'Попросите владельца сайта дать доступ: появятся настоящие показы и места в поиске вместо примерного спроса, и задача «Почти на первой странице».',
    a1: ['Что нужно', '#near'], a2: ['Подключения', R.gsc === 'no_scope' && !badRun.includes(R.wm) ? '/#google' : '/#yandex']});
  const gaps = rivalGaps();
  if (gaps.length) T.push({id: 'absent', p: 'lo', title: 'Темы конкурентов, которых нет у вас', meta: `${num(gaps.length)} ${plural(gaps.length, 'тема', 'темы', 'тем')}`,
    desc: 'У конкурентов есть разделы, под которые люди ищут, а у вас подходящей страницы нет. Где товары уже есть, страницу сделать просто; остальное решите сами.',
    ex: ex(gaps, m => m.name, m => 'у ' + m.hosts.join(', ')), a1: ['Показать темы', '#rivals'], a2: ['Запрос → страница', '#pages/absent']});
  else if (absent.length) T.push({id: 'absent', p: 'lo', title: 'Есть у конкурента, нет у вас', meta: `${num(absent.length)} ${plural(absent.length, 'группа', 'группы', 'групп')}`,
    desc: 'Люди это ищут, а на сайте нет ни страницы, ни товаров. Решите, стоит ли добавлять такой раздел.',
    ex: ex(absent, g => g.name, g => g.rivals.length ? 'у ' + host(g.rivals[0]) : ''), a1: ['Показать группы', '#groups/absent']});
  const other = G.filter(g => g.real && g.real.other);
  if (other.length) T.push({id: 'other', p: 'hi', title: 'Поиск показывает не ту страницу', meta: `${num(other.length)} ${plural(other.length, 'группа', 'группы', 'групп')}`,
    desc: 'По запросам группы Google показывает другую страницу сайта, а не ту, что под неё заточена. Либо сделайте главной ту, что показывается, либо усильте нужную: title, H1, текст и ссылки на неё.',
    ex: ex(other, g => g.name, g => path(g.real.other.url)), a1: ['Показать', '#pages/other']});
  if (geo.length) T.push({id: 'geo', p: 'lo', title: 'Готовность к нейросетям (GEO)', meta: `${geoOk} из ${geo.length}`,
    desc: `Чтобы нейросети чаще цитировали сайт${nfaq ? `, добавьте блоки «вопрос - ответ» на ${num(nfaq)} ${plural(nfaq, 'страницу', 'страницы', 'страниц')}` : ''}.`,
    a1: [nfaq ? `Вопросы для ${num(nfaq)} ${plural(nfaq, 'страницы', 'страниц', 'страниц')}` : 'Открыть', '#geo/faq'], a2: ['Что проверяется', '#geo']});
  if (art.length) T.push({id: 'art', p: 'lo', title: 'План статей для блога', meta: `${num(art.length)} ${plural(art.length, 'тема', 'темы', 'тем')}`,
    desc: 'Из запросов «как», «что такое», «почему»: их удобнее закрывать статьями, а не страницами товаров и услуг.',
    ex: ex(art, a => a.title, a => `${num(a.n)} ${plural(a.n, 'запрос', 'запроса', 'запросов')}`), a1: ['Показать темы', '#art'], a2: ['План в Excel', xlsx]});
  if (manual.length) T.push({id: 'manual', p: 'lo', title: 'Разобрать запросы без группы', meta: `${num(manual.length)} ${plural(manual.length, 'группа', 'группы', 'групп')}`,
    desc: 'Эти запросы не подошли ни к одному разделу сайта. Посмотрите: лишнее уберите словами на вкладке «Отсеяно», нужное станет задачей.',
    ex: ex(manual, g => g.name, g => `${num(g.q.length)} ${plural(g.q.length, 'запрос', 'запроса', 'запросов')}`), a1: ['Показать', '#groups/manual'], a2: ['Убрать слова', '#dropped']});
  TASKS = T;
  $('cntTasks').textContent = num(T.length);
  drawTasks();
}
let TASKS = [];
function drawTasks(){
  const by = p => TASKS.filter(t => t.p === p).length;
  $('taskFlt').querySelectorAll('.fpill').forEach(b => { const p = b.dataset.p, n = p ? by(p) : TASKS.length;
    b.classList.toggle('on', p === prio); b.innerHTML = (p ? PRIO[p] : 'Все') + (n ? ` <small>${n}</small>` : ''); b.hidden = !!p && !n; });
  const list = TASKS.filter(t => !prio || t.p === prio);
  const btn = ([t, h], cls) => h ? `<a class="btn small${cls}" href="${esc(h)}"${h.startsWith('/r/') ? ' download' : ''}>${esc(t)}</a>` : '';
  $('semTasks').innerHTML = list.length ? list.map(t => `<article class="task" data-task="${t.id}">
    <span class="task-ck" data-task="${t.id}"></span>
    <div class="task-main"><div class="task-t"><span class="prio p-${t.p}">${PRIO[t.p]}</span><h3>${esc(t.title)}</h3><span class="mut">${esc(t.meta)}</span></div>
      <p>${esc(t.desc)}</p>
      ${t.ex && t.ex.length ? `<div class="task-ex">${t.ex.map(([a, b]) => `<div><span>${esc(a)}</span>${b ? `<span class="mono">${esc(b)}</span>` : ''}</div>`).join('')}</div>` : ''}</div>
    <div class="task-acts">${btn(t.a1, ' primary')}${t.a2 ? btn(t.a2, '') : ''}</div></article>`).join('')
    : '<div class="card sem-none"><p class="mut">Задач нет: всё в порядке.</p></div>';
  if (window.semDec) semDec.tasks();
}
$('taskFlt').addEventListener('click', e => { const b = e.target.closest('.fpill'); if (!b) return; prio = b.dataset.p; drawTasks(); });
