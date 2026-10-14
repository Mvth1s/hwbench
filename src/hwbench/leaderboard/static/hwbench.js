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
const DEFAULTS = { q: '', kind: 'all', cpu: 'all', gpu: 'all', rel: 'all', since: 'all', smin: '', smax: '', sort: 'rank', dir: '1', page: '1', per: '25', sel: '' };
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
    updateURL();
  }
  function updateURL() {
    const q = query();
    try { history.replaceState(null, '', location.pathname + (q ? '?' + q : '') + location.hash); } catch (e) { /* file:// */ }
  }

  // ---- sélection pour la comparaison : cases du tableau, barre de sélection, nuage de points ----
  const tray = document.querySelector('[data-tray]');
  const live = document.querySelector('[data-live]');
  const known = new Map(rowData.map((r) => [r.tr.dataset.id, r]));
  const MAX_SEL = 8;
  let selected = state.sel.split(',').filter((id) => known.has(id)).slice(0, MAX_SEL);
  const points = [...document.querySelectorAll('#fig-scatter g[data-id]')];
  function syncSelection(announce) {
    state.sel = selected.join(',');
    rowData.forEach((r) => {
      const box = r.tr.querySelector('[data-select]');
      if (box) box.checked = selected.includes(r.tr.dataset.id);
      r.tr.classList.toggle('is-selected', selected.includes(r.tr.dataset.id));
    });
    points.forEach((g) => {
      const on = selected.includes(g.dataset.id);
      g.classList.toggle('is-sel', on);
      g.setAttribute('aria-pressed', String(on));
    });
    if (tray) {
      tray.hidden = selected.length === 0;
      const n = selected.length;
      tray.querySelector('[data-tray-count]').textContent = fill(n > 1 ? I18N.sel_count_many : I18N.sel_count, { n });
      const chips = tray.querySelector('[data-tray-chips]');
      const tpl = document.getElementById('tpl-chip');
      chips.replaceChildren(...selected.map((id) => {
        const chip = tpl.content.firstElementChild.cloneNode(true);
        chip.querySelector('[data-name]').textContent = known.get(id).name;
        chip.setAttribute('aria-label', fill(I18N.sel_live_off, { name: known.get(id).name }));
        chip.addEventListener('click', () => toggle(id));
        return chip;
      }));
      const go = tray.querySelector('[data-tray-go]');
      go.href = go.getAttribute('href').split('?')[0] + '?sel=' + encodeURIComponent(selected.join(','));
      go.setAttribute('aria-disabled', String(n < 2));
    }
    if (announce && live) live.textContent = announce;
    updateURL();
  }
  function toggle(id) {
    const on = !selected.includes(id);
    if (on && selected.length >= MAX_SEL) return;
    selected = on ? [...selected, id] : selected.filter((x) => x !== id);
    syncSelection(fill(on ? I18N.sel_live_on : I18N.sel_live_off, { name: known.get(id).name }));
  }
  rowData.forEach((r) => {
    const box = r.tr.querySelector('[data-select]');
    if (!box) return;
    box.hidden = false;
    box.addEventListener('change', () => toggle(r.tr.dataset.id));
  });
  if (tray) {
    points.forEach((g) => {
      g.setAttribute('role', 'button');
      g.tabIndex = 0;
      g.setAttribute('aria-label', fill(I18N.select_aria, { name: known.get(g.dataset.id)?.name || '' }));
      g.addEventListener('click', () => toggle(g.dataset.id));
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(g.dataset.id); } });
    });
    document.querySelectorAll('[data-js-only]').forEach((el) => { el.hidden = false; });
    tray.querySelector('[data-tray-clear]').addEventListener('click', () => { selected = []; syncSelection(''); });
    tray.querySelector('[data-tray-go]').addEventListener('click', (e) => { if (selected.length < 2) e.preventDefault(); });
  }

  pager.querySelector('[data-csv]').addEventListener('click', () => {
    const head = I18N.csv_head || [];
    const lines = visible.map((r) => [r.rank ?? '', r.name, r.cpu, r.gpu, r.kindLabel, r.score ?? '', r.cv, r.rel === 'ok' ? 1 : 0, r.date]);
    downloadCSV(fill(I18N.csv_name, { category }), [head, ...lines]);
  });

  render();
  syncSelection('');
}

// ---------- Page machine : ajout d'une machine à « Face à… », CSV des résultats bruts ----------
function initAddMachine() {
  document.querySelectorAll('[data-add-target]').forEach((select) => {
    const figure = document.getElementById(select.dataset.addTarget);
    if (!figure) return;
    const rows = figure.querySelector('[data-bars]');
    const table = figure.querySelector('[data-bars-table]');
    const top = Number(figure.dataset.top) || 1;
    const template = rows.querySelector('.hw-hbars__row:not(.is-hl)') || rows.firstElementChild;
    select.closest('[data-add-machine]').hidden = false;
    let added = null;
    select.addEventListener('change', () => {
      if (added) { added.row.remove(); added.tr.remove(); added = null; }
      const link = document.querySelector('[data-cmp-link]');
      if (link) link.href = link.getAttribute('href').split('?')[0] + '?sel=' + encodeURIComponent(link.dataset.self);
      const points = Number(select.value);
      if (!select.value || !Number.isFinite(points)) return;
      const name = select.options[select.selectedIndex].textContent + ' · ' + select.dataset.added;
      const row = template.cloneNode(true);
      row.classList.add('is-added');
      const labels = row.querySelector('.hw-hbars__label');
      labels.replaceChildren(Object.assign(document.createElement('span'), { textContent: name }));
      row.querySelector('.hw-bar>i').style.setProperty('--f', Math.min(1, Math.max(0.003, points / top)).toFixed(4));
      row.querySelector('.hw-num').textContent = NUM.format(points);
      rows.appendChild(row);
      const tr = document.createElement('tr');
      const th = Object.assign(document.createElement('th'), { scope: 'row', textContent: name });
      tr.append(th, Object.assign(document.createElement('td'), { textContent: NUM.format(points) }));
      table.appendChild(tr);
      added = { row, tr };
      const id = select.options[select.selectedIndex].dataset.id;
      if (link && id) link.href = link.getAttribute('href').split('?')[0] + '?sel=' + encodeURIComponent(link.dataset.self + ',' + id);
    });
  });
}
function initTableCSV() {
  document.querySelectorAll('[data-csv-table]').forEach((button) => {
    const table = document.getElementById(button.dataset.csvTable);
    if (!table) return;
    button.hidden = false;
    button.addEventListener('click', () => {
      const rows = [...table.rows].map((tr) => [...tr.cells].map((cell) => cell.textContent.trim()));
      downloadCSV(button.dataset.csvName || 'hwbench.csv', rows);
    });
  });
}


// ---------- Comparaison : machines choisies (?sel=…&base=…), depuis data.json ----------
const SVG_NS = 'http://www.w3.org/2000/svg';
const TONES = ['s1', 's2', 's3', 'acc'];
const SMARKS = ['●', '■', '▲', '◆'];
const SHAPES = ['circle', 'square', 'triangle', 'diamond'];
const KEYS = ['cpu_single', 'cpu_multi', 'gpu', 'combined'];
const PCT = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
function el(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
  if (text != null) node.textContent = text;
  return node;
}
function mark(shape, x, y, r, cls) {
  if (shape === 'square') return el('rect', { x: x - r * 0.88, y: y - r * 0.88, width: r * 1.76, height: r * 1.76, class: cls });
  if (shape === 'triangle') return el('polygon', { points: `${x},${y - r * 1.15} ${x + r * 1.1},${y + r * 0.85} ${x - r * 1.1},${y + r * 0.85}`, class: cls });
  if (shape === 'diamond') return el('polygon', { points: `${x},${y - r * 1.2} ${x + r * 1.2},${y} ${x},${y + r * 1.2} ${x - r * 1.2},${y}`, class: cls });
  return el('circle', { cx: x, cy: y, r, class: cls });
}
function niceTicks(max) {
  const steps = [50, 100, 250, 500, 1000, 2000, 2500, 5000, 10000];
  const step = steps.find((s) => max / s <= 5) || 20000;
  const out = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(v);
  return out;
}
function radarSVG(series, caption) {
  const size = 380, c = size / 2, R = c - 48;
  const max = Math.max(1250, ...series.flatMap((s) => s.vals)) * 1.02;
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / 3;
  const P = (i, v) => [c + Math.cos(ang(i)) * R * (v / max), c + Math.sin(ang(i)) * R * (v / max)];
  const svg = el('svg', { class: 'hw-svg hw-svg--radar', viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': caption });
  [250, 500, 750, 1000].forEach((t) => svg.append(el('polygon', { points: [0, 1, 2].map((i) => P(i, t).join(',')).join(' '), class: t === 1000 ? 'ref' : 'grid', fill: 'none' })));
  [0, 1, 2].forEach((i) => {
    const [x, y] = P(i, max);
    svg.append(el('line', { x1: c, y1: c, x2: x, y2: y, class: 'grid' }));
    const [lx, ly] = P(i, max * 1.14);
    svg.append(el('text', { x: lx, y: ly + 4, 'text-anchor': 'middle', class: 'ink' }, I18N.axes[i]));
  });
  const [rx, ry] = P(0, 1000);
  svg.append(el('text', { x: rx + 6, y: ry + 3 }, '1000'));
  series.forEach((s, k) => {
    const g = el('g', { class: `series tone-${TONES[k % 4]}` });
    g.append(el('polygon', { points: s.vals.map((v, i) => P(i, v).join(',')).join(' '), class: `poly dash-${k % 4}` }));
    s.vals.forEach((v, i) => { const [x, y] = P(i, v); g.append(mark(SHAPES[k % 4], x, y, 4, 'mk')); });
    svg.append(g);
  });
  return svg;
}
function groupedSVG(groups, series, caption) {
  const W = 640, H = 320, m = { l: 48, r: 10, t: 16, b: 34 };
  const vals = groups.flatMap((g) => g.vals.filter((v) => v != null));
  const max = Math.max(1250, ...vals) * 1.05;
  const iw = W - m.l - m.r, ih = H - m.t - m.b, gw = iw / groups.length, n = series.length;
  const bw = Math.min(28, (gw * 0.72) / n);
  const Y = (v) => m.t + ih - (v / max) * ih;
  const svg = el('svg', { class: 'hw-svg', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': caption });
  niceTicks(max).forEach((t) => {
    svg.append(el('line', { x1: m.l, x2: m.l + iw, y1: Y(t), y2: Y(t), class: t === 1000 ? 'ref' : 'grid' }));
    svg.append(el('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'mono' }, NUM.format(t)));
  });
  groups.forEach((g, gi) => {
    g.vals.forEach((v, si) => {
      if (v == null) return;
      const x = m.l + gi * gw + (gw - bw * n) / 2 + si * bw;
      const s = el('g', { class: `series tone-${TONES[si % 4]}` });
      s.append(el('rect', { x: x + 1, y: Y(v), width: Math.max(1, bw - 2), height: m.t + ih - Y(v), class: 'gbar' }));
      s.append(mark(SHAPES[si % 4], x + bw / 2, Y(v) - 8, 3.5, 'mk'));
      s.append(el('title', {}, `${series[si]} · ${g.label} : ${NUM.format(v)}`));
      svg.append(s);
    });
    svg.append(el('text', { x: m.l + gi * gw + gw / 2, y: H - 12, 'text-anchor': 'middle', class: 'ink' }, g.label));
  });
  return svg;
}

function initCompare() {
  const root = document.querySelector('[data-cmp]');
  if (!root) return;
  fetch('data.json').then((r) => r.json()).then((data) => buildCompare(root, data)).catch(() => { /* page sans JS conservée */ });
}
function buildCompare(root, data) {
  const byId = new Map(data.machines.map((m) => [m.id, m]));
  const max = Number(root.dataset.max) || 8;
  const ranked = data.machines.filter((m) => m.points.combined != null).sort((a, b) => b.points.combined - a.points.combined || a.id.localeCompare(b.id));
  const rankOf = new Map(ranked.map((m, i) => [m.id, i + 1]));
  const params = new URLSearchParams(location.search);
  let sel = [...new Set((params.get('sel') || '').split(',').filter((id) => byId.has(id)))].slice(0, max);
  let base = Math.min(Number(params.get('base')) || 0, Math.max(0, sel.length - 1));
  const q = (s) => root.querySelector(s);
  document.querySelector('[data-cmp-fallback]').hidden = true;
  root.hidden = false;
  document.querySelector('[data-cmp-tools]').hidden = false;
  const title = document.querySelector('[data-cmp-title]');
  const live = q('[data-live]');
  const cards = q('[data-cards]');
  const addCard = q('[data-add-card]');
  const add = q('[data-cmp-add]');
  const fmt = (v) => (v == null ? '—' : NUM.format(v));

  function bars(target, key) {
    const tpl = document.getElementById('tpl-cmp-bar');
    const ms = sel.map((id) => byId.get(id));
    const top = Math.max(1, ...ms.map((m) => m.info[key] || 0)) * 1.06;
    target.replaceChildren(...ms.map((m, i) => {
      const row = tpl.content.firstElementChild.cloneNode(true);
      const markEl = row.querySelector('[data-mark]');
      markEl.textContent = SMARKS[i % 4];
      markEl.classList.add('tone-' + TONES[i % 4]);
      row.querySelector('[data-label]').textContent = m.name;
      row.querySelector('.hw-bar').classList.add('hw-bar--' + TONES[i % 4]);
      row.querySelector('.hw-bar>i').style.setProperty('--f', ((m.info[key] || 0) / top).toFixed(4));
      row.querySelector('[data-value]').textContent = fmt(m.info[key]);
      return row;
    }));
  }

  function render() {
    const ms = sel.map((id) => byId.get(id));
    base = Math.min(base, Math.max(0, ms.length - 1));
    title.textContent = ms.length ? fill(I18N.cmp_title, { n: ms.length }) : title.textContent;
    // cartes
    cards.querySelectorAll('.hw-cmpcard:not([data-add-card])').forEach((c) => c.remove());
    const tpl = document.getElementById('tpl-cmp-card');
    ms.forEach((m, i) => {
      const card = tpl.content.firstElementChild.cloneNode(true);
      card.classList.toggle('is-base', i === base);
      const mk = card.querySelector('[data-mark]');
      mk.textContent = SMARKS[i % 4];
      mk.classList.add('tone-' + TONES[i % 4]);
      card.querySelector('[data-rank]').textContent = rankOf.has(m.id) ? I18N.rank_prefix + rankOf.get(m.id) : I18N.unranked;
      const x = card.querySelector('[data-remove]');
      x.setAttribute('aria-label', fill(I18N.cmp_remove, { name: m.name }));
      x.addEventListener('click', () => { sel = sel.filter((id) => id !== m.id); if (base >= sel.length) base = 0; live.textContent = fill(I18N.cmp_removed, { name: m.name }); render(); });
      const name = card.querySelector('[data-name]');
      name.textContent = m.name;
      name.href = 'machines/' + encodeURIComponent(m.id) + '.html';
      card.querySelector('[data-cpu]').textContent = m.cpu.model || '—';
      card.querySelector('[data-gpu]').textContent = m.gpu.model || '—';
      const combined = card.querySelector('[data-combined]');
      combined.textContent = m.points.combined != null ? fmt(m.points.combined) : I18N.unranked;
      combined.classList.toggle('is-unranked', m.points.combined == null);
      const rel = card.querySelector('[data-rel]');
      rel.textContent = (m.reliable ? '● ' : '▲ ') + I18N.reliability[m.reliable ? 'ok' : 'check'];
      rel.classList.toggle('hw-alert', !m.reliable);
      const radio = card.querySelector('[data-base]');
      radio.checked = i === base;
      radio.addEventListener('change', () => { base = i; render(); });
      cards.insertBefore(card, addCard);
    });
    [...add.options].forEach((o) => { if (o.value) o.disabled = sel.includes(o.value); });
    add.disabled = sel.length >= max;
    const enough = ms.length >= 2;
    q('[data-cmp-few]').hidden = enough;
    q('[data-cmp-enough]').hidden = !enough;
    if (enough) {
      const b = ms[base];
      q('[data-cmp-basetxt]').textContent = fill(I18N.cmp_base, { name: b.name });
      const head = q('[data-cmp-head]');
      head.querySelectorAll('th:not(:first-child)').forEach((th) => th.remove());
      ms.forEach((m, i) => {
        const th = document.createElement('th');
        th.scope = 'col';
        th.className = 'hw-right';
        const mk = Object.assign(document.createElement('span'), { textContent: SMARKS[i % 4] + ' ', className: 'tone-' + TONES[i % 4] });
        mk.setAttribute('aria-hidden', 'true');
        th.append(mk, document.createTextNode(m.name));
        head.append(th);
      });
      q('[data-cmp-rows]').replaceChildren(...KEYS.map((k) => {
        const tr = document.createElement('tr');
        tr.append(Object.assign(document.createElement('th'), { scope: 'row', textContent: I18N.categories[k] }));
        ms.forEach((m) => {
          const td = document.createElement('td');
          td.className = 'hw-right';
          const v = m.points[k], bv = b.points[k];
          const val = Object.assign(document.createElement('span'), { className: 'hw-gap__v hw-num', textContent: v == null ? I18N.unranked : fmt(v) });
          const d = document.createElement('span');
          d.className = 'hw-gap__d hw-num';
          if (m === b) d.textContent = I18N.cmp_base_cell;
          else if (v != null && bv) {
            const dv = (v / bv - 1) * 100;
            d.textContent = (dv >= 0 ? '▲ +' : '▼ −') + PCT.format(Math.abs(dv)) + ' %';
            d.classList.add(dv >= 0 ? 'is-up' : 'is-down');
          }
          td.append(val, d);
          tr.append(td);
        });
        return tr;
      }));
      const full = ms.filter((m) => ['cpu_single', 'cpu_multi', 'gpu'].every((k) => m.points[k] != null)).slice(0, 4);
      q('[data-cmp-radar]').replaceChildren(radarSVG(full.map((m) => ({ vals: ['cpu_single', 'cpu_multi', 'gpu'].map((k) => m.points[k]) })), document.querySelector('#fig-radar .hw-chart__title').textContent));
      q('[data-cmp-legend]').replaceChildren(...full.map((m, i) => {
        const li = document.createElement('li');
        const mk = Object.assign(document.createElement('span'), { textContent: SMARKS[i % 4], className: 'tone-' + TONES[i % 4] });
        mk.setAttribute('aria-hidden', 'true');
        li.append(mk, document.createTextNode(' ' + m.name));
        return li;
      }));
      q('[data-cmp-radarcap]').hidden = ms.length <= 4;
      q('[data-cmp-group]').replaceChildren(groupedSVG(KEYS.map((k) => ({ label: I18N.categories[k], vals: ms.map((m) => m.points[k]) })), ms.map((m) => m.name), document.querySelector('#fig-group .hw-chart__title').textContent));
      bars(q('[data-cmp-mem]'), 'memory_mibs');
      bars(q('[data-cmp-seq]'), 'disk_seq_mibs');
      // section masquée si aucune machine choisie n'a de mesure mémoire ni disque
      q('[data-cmp-info]').hidden = !ms.some((m) => m.info.memory_mibs != null || m.info.disk_seq_mibs != null);
    }
    const p = new URLSearchParams();
    if (sel.length) p.set('sel', sel.join(','));
    if (base) p.set('base', String(base));
    try { history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : '') + location.hash); } catch (e) { /* file:// */ }
  }

  add.addEventListener('change', () => {
    const id = add.value;
    add.value = '';
    if (!id || sel.includes(id) || sel.length >= max) return;
    sel = [...sel, id];
    live.textContent = fill(I18N.cmp_added, { name: byId.get(id).name });
    render();
  });
  const copy = document.querySelector('[data-cmp-copy]');
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(location.href); } catch (e) { return; }
    const label = copy.textContent;
    copy.textContent = I18N.copied;
    setTimeout(() => { copy.textContent = label; }, 1800);
  });
  document.querySelector('[data-cmp-csv]').addEventListener('click', () => {
    const r1 = (v) => (v == null ? '' : v.toFixed(1));
    const rows = sel.map((id) => byId.get(id)).map((m) => [m.name, r1(m.points.cpu_single), r1(m.points.cpu_multi), r1(m.points.gpu), r1(m.points.combined), r1(m.info.memory_mibs), r1(m.info.disk_seq_mibs)]);
    downloadCSV(I18N.cmp_csv_name, [I18N.cmp_csv_head, ...rows]);
  });
  render();
}

// ---------- Soumettre : boutons « Copier » et contrôle local du fichier JSON ----------
function initCopyCode() {
  document.querySelectorAll('[data-copy-code]').forEach((button) => {
    const code = button.parentElement.querySelector('code');
    if (!code || !navigator.clipboard) return;
    button.hidden = false;
    const label = button.textContent;
    button.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(code.textContent); } catch (e) { return; }
      button.textContent = button.dataset.copied;
      setTimeout(() => { button.textContent = label; }, 1600);
    });
  });
}
// Règles de privacy.py (clés et valeurs sensibles, clés autorisées), injectées par le
// générateur dans #hw-privacy : aucune liste d'identifiants en dur ici.
function privacyRules() {
  try {
    const raw = JSON.parse(document.getElementById('hw-privacy').textContent);
    const re = (p) => new RegExp(p.source, p.flags);
    return {
      key: re(raw.keys),
      values: raw.values.map((p) => ({ re: new RegExp(p.source, p.flags + 'g'), name: p.name })),
      allowed: Object.fromEntries(Object.entries(raw.allowed).map(([k, p]) => [k, new RegExp('^(?:' + p.source + ')$', p.flags)])),
    };
  } catch (e) { return null; }
}
function findIds(node, rules, path = '', out = []) {
  if (Array.isArray(node)) node.forEach((v, i) => findIds(v, rules, path + i + '.', out));
  else if (node && typeof node === 'object') {
    Object.entries(node).forEach(([k, v]) => {
      const allowed = rules.allowed[k] && typeof v === 'string' && rules.allowed[k].test(v);
      if (!allowed && rules.key.test(k) && v !== null) out.push(path + k);
      else if (!allowed) findIds(v, rules, path + k + '.', out);
    });
  } else if (typeof node === 'string') {
    rules.values.forEach((p) => { p.re.lastIndex = 0; if (p.re.test(node)) out.push(path.replace(/\.$/, '') + ' (' + p.name + ')'); });
  }
  return out;
}
function initFileCheck() {
  const drop = document.querySelector('[data-drop]');
  const report = document.querySelector('[data-check-report]');
  const rules = privacyRules();
  if (!drop || !report || !window.FileReader || !rules) return;
  const C = I18N.check || {};
  drop.hidden = false;
  report.hidden = false;
  document.querySelectorAll('[data-nojs-note]').forEach((n) => { n.hidden = true; });
  const card = report.querySelector('[data-check-card]');
  card.hidden = true;
  const readable = report.dataset.readable.split(',');
  const tone = { ok: ['✓', C.pass], warn: ['!', C.note], ko: ['✕', C.fail] };
  function show(name, checks) {
    const worst = checks.some((c) => c[1] === 'ko') ? 'ko' : checks.some((c) => c[1] === 'warn') ? 'warn' : 'ok';
    const verdict = report.querySelector('[data-verdict]');
    verdict.textContent = tone[worst][0] + ' ' + C[worst];
    verdict.className = 'hw-check-verdict is-' + worst;
    report.querySelector('[data-file-name]').textContent = name;
    const tpl = document.getElementById('tpl-check');
    report.querySelector('[data-checks]').replaceChildren(...checks.map(([key, status, detail]) => {
      const li = tpl.content.firstElementChild.cloneNode(true);
      const mk = li.querySelector('[data-mark]');
      mk.textContent = tone[status][0];
      mk.classList.add('is-' + status);
      li.querySelector('[data-sr]').textContent = tone[status][1] + ' : ';
      li.querySelector('[data-label]').textContent = C[key];
      li.querySelector('[data-detail]').textContent = detail;
      return li;
    }));
    card.hidden = false;
    report.querySelector('[data-idle]').hidden = true;
  }
  function analyse(file) {
    if (!file) return;
    file.text().then((text) => {
      const checks = [];
      let data;
      try { data = JSON.parse(text); checks.push(['json', 'ok', NUM.format(text.length / 1024) + ' Kio']); } catch (e) { checks.push(['json', 'ko', String(e.message).slice(0, 80)]); show(file.name, checks); return; }
      const schema = String(data.schema_version ?? '');
      checks.push(['schema', readable.includes(schema) ? 'ok' : 'ko', 'schema_version = ' + (schema || '—')]);
      const version = String(data.hwbench_version || '');
      checks.push(['version', version === report.dataset.version ? 'ok' : version ? 'warn' : 'ko', 'hwbench_version = ' + (version || '—') + ' / ' + report.dataset.version]);
      checks.push(['date', data.created ? 'ok' : 'ko', data.created || '—']);
      checks.push(['machine', data.machine ? 'ok' : 'ko', data.machine || '—']);
      const ids = findIds(data, rules);
      checks.push(['ids', ids.length ? 'ko' : 'ok', ids.length ? ids.slice(0, 3).join(', ') : '0']);
      checks.push(['name', /^[a-z0-9][a-z0-9-]*\.json$/.test(file.name) ? 'ok' : 'ko', file.name]);
      show(file.name, checks);
    });
  }
  const input = drop.querySelector('[data-file]');
  input.addEventListener('change', () => analyse(input.files[0]));
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('is-over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('is-over'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('is-over'); analyse(e.dataTransfer.files[0]); });
}

initTheme();
initMenu();
initCopyCode();
initFileCheck();
initCompare();
initAddMachine();
initTableCSV();
initTips();
initRanking();
initReveal();
initCounter();
initPNG();
