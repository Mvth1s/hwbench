// hwbench — couche interactive du site du classement (amélioration progressive).
// Sans ce script, chaque page reste complète : il ajoute la bascule de thème, le menu étroit,
// les popups « i », le tri, les filtres, la pagination, l'état d'URL et les exports.
// Aucun texte affiché n'est écrit ici : tout vient du catalogue publié dans #hw-i18n ou du DOM.
// Aucune donnée d'un export n'est insérée en HTML (textContent uniquement).

const I18N = (() => {
  try { return JSON.parse(document.getElementById('hw-i18n').textContent); } catch (e) { return {}; }
})();
const fill = (text, values) => String(text || '').replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
const reducedMotion = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const NUM = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });

// ---------- Thème (clair / sombre, choix mémorisé dans hwbench.theme) ----------
function currentTheme() {
  const forced = document.documentElement.dataset.theme;
  if (forced === 'light' || forced === 'dark') return forced;
  return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function initTheme() {
  const button = document.querySelector('[data-theme-toggle]');
  if (!button) return;
  const label = () => {
    const text = currentTheme() === 'dark' ? I18N.theme_to_light : I18N.theme_to_dark;
    if (text) { button.setAttribute('aria-label', text); button.title = text; }
  };
  button.hidden = false;
  label();
  button.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('hwbench.theme', next); } catch (e) { /* stockage indisponible */ }
    label();
  });
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', label);
}

// ---------- Menu sur écran étroit ----------
function initMenu() {
  const button = document.querySelector('[data-menu-toggle]');
  const nav = document.getElementById('hw-nav');
  if (!button || !nav) return;
  button.hidden = false;
  button.addEventListener('click', () => {
    const open = !nav.classList.contains('is-open');
    nav.classList.toggle('is-open', open);
    button.setAttribute('aria-expanded', String(open));
    button.textContent = open ? I18N.close : I18N.menu;
  });
}

// ---------- Popups « i » (contenu dans <template id="tip-…">) ----------
function initTips() {
  const buttons = document.querySelectorAll('[data-tip]');
  if (!buttons.length) return;
  let pop = null;
  let opener = null;
  const close = (restore) => {
    if (!pop) return;
    pop.remove(); pop = null;
    if (opener) { opener.setAttribute('aria-expanded', 'false'); if (restore) opener.focus(); }
    opener = null;
  };
  const open = (button) => {
    const tpl = document.getElementById('tip-' + button.dataset.tip);
    if (!tpl) return;
    close(false);
    opener = button;
    pop = document.createElement('div');
    pop.className = 'hw-pop';
    pop.setAttribute('role', 'dialog');
    pop.tabIndex = -1;
    const body = tpl.content.cloneNode(true);
    const title = body.querySelector('.hw-pop__title');
    const head = document.createElement('div');
    head.className = 'hw-pop__head';
    if (title) {
      title.id = 'hw-pop-title';
      pop.setAttribute('aria-labelledby', title.id);
      head.appendChild(title);
    }
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'hw-pop__close';
    x.setAttribute('aria-label', I18N.close || '×');
    x.textContent = '×';
    x.addEventListener('click', () => close(true));
    head.appendChild(x);
    pop.appendChild(head);
    pop.appendChild(body);
    document.body.appendChild(pop);
    const r = button.getBoundingClientRect();
    const width = pop.offsetWidth;
    const left = Math.max(16, Math.min(r.left + window.scrollX - 16, document.documentElement.clientWidth - width - 16));
    pop.style.left = Math.round(left) + 'px';
    pop.style.top = Math.round(r.bottom + window.scrollY + 8) + 'px';
    button.setAttribute('aria-expanded', 'true');
    pop.focus();
  };
  buttons.forEach((button) => {
    button.hidden = false;
    button.addEventListener('click', (e) => {
      e.stopPropagation();
      if (opener === button) close(true); else open(button);
    });
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(true); });
  document.addEventListener('pointerdown', (e) => {
    if (pop && !pop.contains(e.target) && !(e.target.closest && e.target.closest('[data-tip]'))) close(false);
  });
}

// ---------- Apparition des barres, compteur du podium ----------
function initReveal() {
  const items = document.querySelectorAll('[data-reveal]');
  if (!items.length) return;
  if (reducedMotion() || !('IntersectionObserver' in window)) { items.forEach((el) => el.classList.add('is-in')); return; }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add('is-in'); io.unobserve(entry.target); } });
  }, { threshold: 0.1 });
  items.forEach((el) => io.observe(el));
}
function initCounter() {
  const el = document.querySelector('[data-count]');
  if (!el || reducedMotion()) return;
  const value = Number(el.dataset.count);
  const final = el.textContent;
  if (!Number.isFinite(value)) return;
  el.setAttribute('aria-label', final);
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / 1200);
    el.textContent = k < 1 ? NUM.format(value * (1 - Math.pow(1 - k, 4))) : final;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---------- Téléchargements ----------
function download(name, blob) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
function downloadCSV(name, rows) {
  // les champs qui commencent par =, +, - ou @ sont préfixés d'une apostrophe (pas de formule)
  const cell = (v) => {
    let s = String(v ?? '');
    if (/^[=+\-@]/.test(s)) s = "'" + s;
    return /[;"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  download(name, new Blob(['﻿' + rows.map((r) => r.map(cell).join(';')).join('\n')], { type: 'text/csv;charset=utf-8' }));
}
const PNG_PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-family', 'font-size', 'font-weight', 'color'];
async function exportPNG(figure, name) {
  const svg = figure.querySelector('svg');
  if (!svg) return;
  const clone = svg.cloneNode(true);
  const src = [svg, ...svg.querySelectorAll('*')];
  const dst = [clone, ...clone.querySelectorAll('*')];
  src.forEach((node, i) => {
    const cs = getComputedStyle(node);
    PNG_PROPS.forEach((p) => dst[i].style.setProperty(p, cs.getPropertyValue(p)));
  });
  const box = svg.viewBox.baseVal;
  const pad = 24;
  const title = figure.querySelector('.hw-chart__title');
  const head = title ? 34 : 0;
  const w = box.width + pad * 2;
  const h = box.height + pad * 2 + head;
  const bg = getComputedStyle(document.body).backgroundColor;
  const ink = getComputedStyle(document.body).color;
  clone.setAttribute('x', pad); clone.setAttribute('y', pad + head);
  clone.setAttribute('width', box.width); clone.setAttribute('height', box.height);
  const wrap = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  wrap.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  wrap.setAttribute('width', w); wrap.setAttribute('height', h);
  const rect = document.createElementNS(wrap.namespaceURI, 'rect');
  rect.setAttribute('width', '100%'); rect.setAttribute('height', '100%'); rect.setAttribute('fill', bg);
  wrap.appendChild(rect);
  if (title) {
    const text = document.createElementNS(wrap.namespaceURI, 'text');
    text.setAttribute('x', pad); text.setAttribute('y', pad + 14);
    text.setAttribute('font-family', 'system-ui, sans-serif'); text.setAttribute('font-size', '15');
    text.setAttribute('font-weight', '600'); text.setAttribute('fill', ink);
    text.textContent = title.textContent;
    wrap.appendChild(text);
  }
  wrap.appendChild(clone);
  const img = new Image();
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(wrap));
  await img.decode().catch(() => {});
  const canvas = document.createElement('canvas');
  canvas.width = w * 2; canvas.height = h * 2;
  const ctx = canvas.getContext('2d');
  ctx.scale(2, 2);
  ctx.drawImage(img, 0, 0);
  canvas.toBlob((blob) => blob && download(name, blob), 'image/png');
}
function initPNG() {
  document.querySelectorAll('[data-png]').forEach((button) => {
    const figure = document.getElementById(button.dataset.png);
    if (!figure) return;
    button.hidden = false;
    button.addEventListener('click', () => exportPNG(figure, button.dataset.pngName || 'hwbench.png'));
  });
}

// ---------- Classement : filtres, tri, pagination, état d'URL ----------
const DEFAULTS = { q: '', kind: 'all', cpu: 'all', gpu: 'all', rel: 'all', since: 'all', smin: '', smax: '', sort: 'rank', dir: '1', page: '1', per: '25' };
const FILTER_KEYS = ['q', 'kind', 'cpu', 'gpu', 'rel', 'since', 'smin', 'smax'];

function initRanking() {
  const table = document.getElementById('rank-table');
  if (!table) return;
  const tbody = table.tBodies[0];
  const rows = [...tbody.rows];
  const panel = document.querySelector('[data-filters]');
  const pager = document.querySelector('[data-pager]');
  const empty = document.querySelector('[data-no-results]');
  const countText = document.querySelector('[data-count-text]');
  const pageText = document.querySelector('[data-page-text]');
  const resets = document.querySelectorAll('[data-reset]');
  const category = table.dataset.category;
  const generated = table.dataset.generated;
  const state = { ...DEFAULTS };
  const params = new URLSearchParams(location.search);
  Object.keys(DEFAULTS).forEach((k) => { if (params.get(k)) state[k] = params.get(k); });

  const num = (s) => (s === '' || s == null ? null : Number(s));
  const rowData = rows.map((tr) => ({
    tr,
    rank: num(tr.dataset.rank),
    score: num(tr.dataset.score),
    name: tr.dataset.name,
    cpu: tr.dataset.cpu,
    gpu: tr.dataset.gpu,
    kind: tr.dataset.kind,
    kindLabel: tr.cells[4].textContent.replace(/^\s*\S+\s*/, '').trim(),
    cpub: tr.dataset.cpub,
    gpub: tr.dataset.gpub,
    rel: tr.dataset.rel,
    date: tr.dataset.date,
    cv: tr.dataset.cv,
    search: (tr.dataset.name + ' ' + tr.dataset.cpu + ' ' + tr.dataset.gpu).toLowerCase(),
  }));

  // contrôles
  panel.hidden = false;
  pager.hidden = false;
  const field = (name) => panel.querySelector(`[name="${name}"]`) || pager.querySelector(`[name="${name}"]`);
  ['q', 'cpu', 'gpu', 'rel', 'since', 'smin', 'smax', 'per'].forEach((k) => { const el = field(k); if (el) el.value = state[k]; });
  const chips = panel.querySelectorAll('[data-kind]');
  const syncChips = () => chips.forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.kind === state.kind)));
  syncChips();
  chips.forEach((c) => c.addEventListener('click', () => { state.kind = c.dataset.kind; state.page = '1'; syncChips(); render(); }));
  ['q', 'smin', 'smax'].forEach((k) => field(k).addEventListener('input', (e) => { state[k] = e.target.value.trim(); state.page = '1'; render(); }));
  ['cpu', 'gpu', 'rel', 'since', 'per'].forEach((k) => field(k).addEventListener('change', (e) => { state[k] = e.target.value; state.page = '1'; render(); }));
  resets.forEach((b) => b.addEventListener('click', () => {
    FILTER_KEYS.forEach((k) => { state[k] = DEFAULTS[k]; const el = field(k); if (el) el.value = DEFAULTS[k]; });
    state.page = '1'; syncChips(); render();
  }));
  pager.querySelectorAll('[data-page]').forEach((b) => b.addEventListener('click', () => {
    const pages = Number(pager.dataset.pages || 1);
    const p = Number(state.page);
    state.page = String({ first: 1, prev: Math.max(1, p - 1), next: Math.min(pages, p + 1), last: pages }[b.dataset.page]);
    render();
    table.closest('.hw-table-wrap').scrollIntoView({ block: 'nearest' });
  }));

  // en-têtes triables
  const heads = [...table.tHead.rows[0].cells].filter((th) => th.dataset.sort);
  heads.forEach((th) => {
    const button = document.createElement('button');
    button.type = 'button';
    while (th.firstChild) button.appendChild(th.firstChild);
    th.appendChild(button);
    button.addEventListener('click', () => {
      const k = th.dataset.sort;
      state.dir = state.sort === k ? String(-Number(state.dir)) : '1';
      state.sort = k;
      state.page = '1';
      render();
    });
  });

  // onglets : la page de l'autre catégorie reprend les filtres
  document.querySelectorAll('[data-tab]').forEach((a) => a.addEventListener('click', () => {
    const q = query(['page']);
    a.href = a.getAttribute('href').split('?')[0] + (q ? '?' + q : '');
  }));

  const copy = pager.querySelector('[data-copy]');
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(location.href); } catch (e) { return; }
    copy.textContent = I18N.copied;
    setTimeout(() => { copy.textContent = I18N.copy_link; }, 1800);
  });

  const since = () => {
    if (state.since === 'all' || !generated) return '';
    const d = new Date(generated + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - Number(state.since));
    return d.toISOString().slice(0, 10);
  };
  const matches = (r) => {
    const smin = num(state.smin);
    const smax = num(state.smax);
    const from = since();
    return (state.kind === 'all' || r.kind === state.kind)
      && (state.cpu === 'all' || r.cpub === state.cpu)
      && (state.gpu === 'all' || r.gpub === state.gpu)
      && (state.rel === 'all' || r.rel === state.rel)
      && (!from || r.date >= from)
      && (smin == null || (r.score != null && r.score >= smin))
      && (smax == null || (r.score != null && r.score <= smax))
      && (!state.q || r.search.includes(state.q.toLowerCase()));
  };
  // les machines non classées (sans points) restent en fin de liste pour le rang et les points,
  // quel que soit le sens du tri
  const compare = (a, b) => {
    const dir = Number(state.dir) || 1;
    const k = state.sort;
    if (k === 'rank' || k === 'score') {
      if (a.rank == null || b.rank == null) {
        if (a.rank == null && b.rank == null) return a.name.localeCompare(b.name, 'fr');
        return a.rank == null ? 1 : -1;
      }
      return (a.rank - b.rank) * dir;
    }
    const x = k === 'kind' ? a.kindLabel : a[k] || '';
    const y = k === 'kind' ? b.kindLabel : b[k] || '';
    return (x.localeCompare(y, 'fr') || (a.rank ?? 1e9) - (b.rank ?? 1e9)) * dir;
  };
  const query = (skip = []) => {
    const p = new URLSearchParams();
    Object.keys(DEFAULTS).forEach((k) => { if (!skip.includes(k) && state[k] !== DEFAULTS[k]) p.set(k, state[k]); });
    return p.toString();
  };

  let visible = [];
  function render() {
    visible = rowData.filter(matches).sort(compare);
    const per = Number(state.per) || 25;
    const pages = Math.max(1, Math.ceil(visible.length / per));
    const page = Math.min(Math.max(1, Number(state.page) || 1), pages);
    state.page = String(page);
    pager.dataset.pages = String(pages);
    const slice = visible.slice((page - 1) * per, page * per);
    tbody.replaceChildren(...slice.map((r) => r.tr));
    // points : le sens « 1 » met les meilleurs en tête, donc des valeurs décroissantes
    heads.forEach((th) => {
      const up = Number(state.dir) > 0 !== (th.dataset.sort === 'score');
      th.setAttribute('aria-sort', th.dataset.sort === state.sort ? (up ? 'ascending' : 'descending') : 'none');
    });
    countText.textContent = visible.length
      ? fill(I18N.count, { a: NUM.format((page - 1) * per + 1), b: NUM.format((page - 1) * per + slice.length), c: NUM.format(visible.length) })
      : I18N.none;
    pageText.textContent = fill(I18N.page, { p: page, n: pages });
    pager.querySelector('[data-page="first"]').disabled = page <= 1;
    pager.querySelector('[data-page="prev"]').disabled = page <= 1;
    pager.querySelector('[data-page="next"]').disabled = page >= pages;
    pager.querySelector('[data-page="last"]').disabled = page >= pages;
    const filtered = FILTER_KEYS.some((k) => state[k] !== DEFAULTS[k]);
    resets.forEach((b) => { if (!b.closest('[data-no-results]')) b.hidden = !filtered; });
    empty.hidden = visible.length > 0;
    table.closest('.hw-table-wrap').hidden = visible.length === 0;
    const q = query();
    try { history.replaceState(null, '', location.pathname + (q ? '?' + q : '') + location.hash); } catch (e) { /* file:// */ }
  }

  pager.querySelector('[data-csv]').addEventListener('click', () => {
    const head = I18N.csv_head || [];
    const lines = visible.map((r) => [r.rank ?? '', r.name, r.cpu, r.gpu, r.kindLabel, r.score ?? '', r.cv, r.rel === 'ok' ? 1 : 0, r.date]);
    downloadCSV(fill(I18N.csv_name, { category }), [head, ...lines]);
  });

  render();
}

initTheme();
initMenu();
initTips();
initRanking();
initReveal();
initCounter();
initPNG();
