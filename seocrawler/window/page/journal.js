// Вкладка «Журнал» (главная, #log): что нажимали, что закончилось, что сломалось - по всей программе.
// Записи - из «журнал программы.txt» (applog.py), новые сверху. «Подробный журнал» проверки - отдельно, на главной.
(() => {
  const $ = id => document.getElementById(id);
  if (!$('jrList')) return;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const KIND = {action: 'Действие', event: 'Уведомление', error: 'Ошибка', info: 'Сообщение'};
  let kind = '', tm = null, timer = null;
  const day = d => { const t = new Date(d + 'T00:00'), now = new Date(), y = new Date(now - 864e5);
    return t.toDateString() === now.toDateString() ? 'Сегодня' : t.toDateString() === y.toDateString() ? 'Вчера'
      : t.toLocaleDateString('ru', {day: 'numeric', month: 'long'}); };
  async function load(){
    const q = new URLSearchParams({kind, q: $('jrQ').value.trim()});
    let j; try { j = await (await fetch('/api/log?' + q)).json(); } catch (e) { return; }
    let cur = '', html = '';
    for (const r of j.items) {
      const d = r.t.slice(0, 10);
      if (d !== cur) { cur = d; html += `<div class="jr-day">${esc(day(d))}</div>`; }
      html += `<div class="jr-i ${r.kind}"><span class="jr-t">${esc(r.t.slice(11, 16))}</span><span class="jr-k">${esc(KIND[r.kind] || '')}</span>
        <div class="jr-x">${r.site ? `<span class="jr-s">${esc(r.site)}</span>` : ''}${esc(r.text)}`
        + (r.todo ? `<div class="jr-todo"><b>Что сделать:</b> ${esc(r.todo)}</div>` : '')
        + (r.detail ? `<details><summary>Подробнее</summary><pre>${esc(r.detail)}</pre></details>` : '') + '</div></div>';
    }
    $('jrList').innerHTML = html || `<p class="mut">${kind || $('jrQ').value ? 'Ничего не нашлось.' : 'Журнал пока пуст: записи появятся, когда вы начнёте работать в окне.'}</p>`;
    $('jrFile').textContent = j.file || '';
  }
  document.querySelectorAll('#jrKinds button').forEach(b => b.onclick = () => {
    kind = b.dataset.k; document.querySelectorAll('#jrKinds button').forEach(x => x.classList.toggle('on', x === b)); load(); });
  $('jrQ').oninput = () => { clearTimeout(tm); tm = setTimeout(load, 300); };
  $('jrOpen').onclick = () => fetch('/api/log_open', {method: 'POST', body: '{}'});
  // пока вкладка открыта - обновлять раз в 5 секунд
  window.loadJournal = () => { load(); clearInterval(timer);
    timer = setInterval(() => { if ($('jrList').offsetParent) load(); else clearInterval(timer); }, 5000); };
})();
