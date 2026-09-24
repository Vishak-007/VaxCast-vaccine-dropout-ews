/* ============================================================
   DoseWatch — app logic
   ============================================================ */

const M = window.Motion || {};
const animate = M.animate || ((el, kf, o) => { try { el.animate && el.animate(kf, o); } catch (e) {} });
const inView = M.inView || (() => () => {});
const stagger = M.stagger || (() => 0);
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const fmtInt = n => (n == null ? '—' : Math.round(n).toLocaleString('en-IN'));
const fmtPct = (n, d = 1) => (n == null ? '—' : (n * 100).toFixed(d) + '%');
const YEAR_LABEL = { '2017-2018': '2017–18', '2018-2019': '2018–19', '2019-2020': '2019–20' };

const WATCH_KEY = 'dosewatch:watchlist';

/* ---------------------------------------------------------------- state */

const state = {
  data: null,
  filters: { q: '', state: '', band: '', minCohort: 0 },
  sort: { key: 'dropout', dir: 'desc' },
  watch: loadWatch(),
  watchOnly: false,
  activeId: null,
};

function loadWatch() {
  try { return new Set(JSON.parse(localStorage.getItem(WATCH_KEY) || '[]')); }
  catch { return new Set(); }
}
function saveWatch() {
  try { localStorage.setItem(WATCH_KEY, JSON.stringify([...state.watch])); } catch {}
}
const idOf = d => `${d.state}::${d.district}`;

/* ---------------------------------------------------------------- boot */

init();

async function init() {
  const ledgerEl = $('#ledger');
  ledgerEl.classList.add('is-loading');
  paintSkeleton();

  try {
    const res = await fetch('data/districts.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
  } catch (err) {
    showFatal(err);
    return;
  }

  ledgerEl.classList.remove('is-loading');
  buildStaticUI();
  wireControls();
  wireKeyboard();
  render();
  revealSections();
  openFromHash();
  window.addEventListener('hashchange', openFromHash);

  // the page grows as data lands, so a load-time #section anchor ends up stale — re-align it
  const secId = (location.hash.match(/^#(overview|ledger|method)$/) || [])[1];
  if (secId) requestAnimationFrame(() => document.getElementById(secId)?.scrollIntoView());
}

function openFromHash() {
  const m = decodeURIComponent(location.hash).match(/^#d\/(.+?)\/(.+)$/);
  if (!m) return;
  const d = state.data.districts.find(x => x.state === m[1] && x.district === m[2]);
  if (d && idOf(d) !== state.activeId) openPanel(d);
}

function showFatal(err) {
  const main = $('main');
  main.innerHTML = `
    <section class="section" style="text-align:center;padding-block:96px">
      <h2 class="section__title" style="display:inline-block">Data could not be loaded</h2>
      <p class="section__note" style="margin:16px auto 0;max-width:44ch">
        The district dataset (<code>data/districts.json</code>) did not load — ${String(err.message || err)}.
        This page must be served over HTTP (not opened as a file). Try
        <code>python -m http.server</code> from the project root, then open
        <code>/dosewatch/dashboard/</code>.
      </p>
    </section>`;
  $('#counters').querySelectorAll('.counter__num').forEach(n => n.textContent = '—');
}

/* ---------------------------------------------------------------- skeleton */

function paintSkeleton() {
  const sk = $('#ledger-skeleton');
  sk.innerHTML = Array.from({ length: 12 }, () => '<div class="skrow"></div>').join('');
}

/* ---------------------------------------------------------------- static UI */

function buildStaticUI() {
  const { national, states } = state.data;

  $('#provenance').textContent = state.data.generated;
  $('#method-source').textContent =
    `Generated from ${national.districts} districts · ${state.data.generated} · latest reported year ${YEAR_LABEL[national.years.at(-1)]}`;

  // counters
  setCounter('districts', fmtInt(national.districts), national.districts);
  setCounter('high', fmtInt(national.high), national.high);
  setCounter('dropout', fmtPct(national.dropout), national.dropout * 100, '%');
  setCounter('missed', fmtInt(national.children_missed), national.children_missed);

  // band list
  const bandCounts = { high: national.high, watch: national.watch, ontrack: national.ontrack };
  const bandMeta = {
    high: `at or above ${fmtPct(national.threshold_high)} dropout`,
    watch: `${fmtPct(national.threshold_watch)}–${fmtPct(national.threshold_high)} dropout`,
    ontrack: `below ${fmtPct(national.threshold_watch)} dropout`,
  };
  $('#bandlist').querySelectorAll('.bandlist__row').forEach(row => {
    const b = row.dataset.band;
    row.querySelector('.bandlist__val').textContent = fmtInt(bandCounts[b]);
    row.querySelector('.bandlist__meta').textContent = bandMeta[b];
  });

  // histogram
  paintHistogram(national.threshold_high, national.threshold_watch);

  // state bars
  paintStateBars(states);

  // state filter options
  const sel = $('#state-filter');
  [...states].map(s => s.state).sort().forEach(name => {
    const o = document.createElement('option');
    o.value = name; o.textContent = name;
    sel.appendChild(o);
  });
}

function setCounter(key, text, target, suffix = '') {
  const el = $(`.counter[data-k="${key}"] .counter__num`);
  if (!el) return;
  if (reduceMotion || !M.animate) { el.textContent = text; return; }
  const obj = { v: 0 };
  animate(obj, { v: target }, {
    duration: 1.1, ease: [0.16, 1, 0.3, 1],
    onUpdate: () => {
      el.textContent = suffix === '%'
        ? obj.v.toFixed(1) + '%'
        : Math.round(obj.v).toLocaleString('en-IN');
    },
  }).finished?.then(() => { el.textContent = text; });
}

function paintHistogram(thrHigh, thrWatch) {
  const host = $('#hist');
  const axis = $('#hist-axis');
  host.innerHTML = '';
  axis.innerHTML = '';

  const BIN = 0.005, N = 32, TOP = BIN * N; // 0–16%, last bin is 15.5%+
  const counts = new Array(N).fill(0);
  state.data.districts.forEach(d => {
    const i = Math.min(N - 1, Math.floor(d.dropout / BIN));
    counts[i]++;
  });
  const max = Math.max(...counts);

  counts.forEach((c, i) => {
    const lo = i * BIN, hi = i === N - 1 ? 1 : lo + BIN;
    const bar = document.createElement('div');
    bar.className = 'hist__bar';
    bar.dataset.band = lo >= thrHigh ? 'high' : (hi > thrWatch ? 'watch' : 'ontrack');
    bar.dataset.tip = `${fmtPct(lo, 1)}${i === N - 1 ? '+' : '–' + fmtPct(hi, 1)} · ${c} district${c === 1 ? '' : 's'}`;
    bar.style.height = (c ? Math.max(2, Math.sqrt(c / max) * 100) : 0).toFixed(1) + '%';
    host.appendChild(bar);
  });

  const mk = document.createElement('div');
  mk.className = 'hist__threshold';
  mk.style.left = Math.min(98, (thrHigh / TOP) * 100) + '%';
  mk.innerHTML = `<span>High-risk · ${fmtPct(thrHigh)}</span>`;
  host.appendChild(mk);

  [0, 0.04, 0.08, 0.12, `${Math.round(TOP * 100)}%+`].forEach(v => {
    const s = document.createElement('span');
    s.textContent = typeof v === 'string' ? v : fmtPct(v, 0);
    axis.appendChild(s);
  });

  // entrance handled by a pure-CSS keyframe (see .hist__bar) — always completes, never traps content
  $$('.hist__bar', host).forEach((b, i) => b.style.setProperty('--i', i));
}

function paintStateBars(states) {
  const ol = $('#statebars');
  ol.innerHTML = '';
  const top = [...states].filter(s => s.districts >= 2).slice(0, 12);
  const max = Math.max(...top.map(s => s.dropout));
  top.forEach(s => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'statebar';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', 'false');
    btn.dataset.state = s.state;
    btn.innerHTML = `
      <span class="statebar__name" title="${s.state}">${s.state}</span>
      <span class="statebar__track"><span class="statebar__fill" style="width:${(s.dropout / max * 100).toFixed(1)}%"></span></span>
      <span class="statebar__val">${fmtPct(s.dropout)}</span>`;
    btn.addEventListener('click', () => {
      const next = state.filters.state === s.state ? '' : s.state;
      state.filters.state = next;
      $('#state-filter').value = next;
      syncStateBarPressed();
      render();
      $('#ledger').scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    });
    li.appendChild(btn);
    ol.appendChild(li);
  });
}

function syncStateBarPressed() {
  $$('.statebar').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.state === state.filters.state)));
}

/* ---------------------------------------------------------------- controls */

function wireControls() {
  const q = $('#q');
  q.addEventListener('input', debounce(() => { state.filters.q = q.value.trim().toLowerCase(); render(); }, 120));

  $('#state-filter').addEventListener('change', e => {
    state.filters.state = e.target.value;
    syncStateBarPressed();
    render();
  });

  $('#band-filter').addEventListener('click', e => {
    const btn = e.target.closest('button');
    if (!btn) return;
    state.filters.band = btn.dataset.v;
    $$('#band-filter button').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    render();
  });

  const mc = $('#min-cohort');
  mc.addEventListener('input', () => {
    state.filters.minCohort = +mc.value;
    $('#min-cohort-val').textContent = (+mc.value).toLocaleString('en-IN');
    render();
  });

  $('#clear-filters').addEventListener('click', clearFilters);
  $$('[data-clear]').forEach(b => b.addEventListener('click', clearFilters));

  $$('.ledger__head button.th').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sort.key === key) {
        state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.sort.key = key;
        state.sort.dir = (key === 'district' || key === 'state') ? 'asc' : 'desc';
      }
      render();
    });
  });

  $('#watch-toggle').addEventListener('click', () => {
    state.watchOnly = !state.watchOnly;
    $('#watch-toggle').setAttribute('aria-pressed', String(state.watchOnly));
    render();
  });

  $('#export-btn').addEventListener('click', exportCsv);

  // panel close
  $('#scrim').addEventListener('click', closePanel);
}

function clearFilters() {
  state.filters = { q: '', state: '', band: '', minCohort: 0 };
  state.watchOnly = false;
  $('#q').value = '';
  $('#state-filter').value = '';
  $('#min-cohort').value = 0;
  $('#min-cohort-val').textContent = '0';
  $$('#band-filter button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === '')));
  $('#watch-toggle').setAttribute('aria-pressed', 'false');
  syncStateBarPressed();
  render();
}

function wireKeyboard() {
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      e.preventDefault(); $('#q').focus();
    }
    if (e.key === 'Escape') {
      if (!$('#dpanel').hidden) closePanel();
    }
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && document.activeElement.classList.contains('row')) {
      e.preventDefault();
      const rows = $$('.row');
      const i = rows.indexOf(document.activeElement);
      const next = rows[i + (e.key === 'ArrowDown' ? 1 : -1)];
      next && next.focus();
    }
  });
}

/* ---------------------------------------------------------------- filtering + render */

function currentRows() {
  const { q, state: st, band, minCohort } = state.filters;
  let rows = state.data.districts.filter(d => {
    if (st && d.state !== st) return false;
    if (band && d.band !== band) return false;
    if (d.penta1 < minCohort) return false;
    if (state.watchOnly && !state.watch.has(idOf(d))) return false;
    if (q && !(`${d.district} ${d.state}`.toLowerCase().includes(q))) return false;
    return true;
  });
  const { key, dir } = state.sort;
  const mul = dir === 'asc' ? 1 : -1;
  rows.sort((a, b) => {
    let x = a[key], y = b[key];
    if (typeof x === 'string') return x.localeCompare(y) * mul;
    return (x - y) * mul;
  });
  return rows;
}

function render() {
  const rows = currentRows();
  const total = state.data.districts.length;

  // header sort indicators
  $$('.ledger__head .th').forEach(th => {
    if (th.dataset.sort === state.sort.key) th.setAttribute('aria-sort', state.sort.dir === 'asc' ? 'ascending' : 'descending');
    else th.removeAttribute('aria-sort');
  });

  // count line
  const activeFilters = countActiveFilters();
  $('#ledger-count').textContent = activeFilters
    ? `${rows.length} of ${total} districts match — sorted by ${sortLabel()}`
    : `All ${total} districts, sorted by ${sortLabel()}`;
  $('#clear-filters').hidden = !activeFilters;

  // watch badge
  const wn = $('#watch-n');
  wn.textContent = state.watch.size;
  wn.hidden = state.watch.size === 0;

  const body = $('#rows');
  const empty = $('#ledger-empty');

  if (!rows.length) {
    body.innerHTML = '';
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  const tpl = $('#tpl-row');
  const frag = document.createDocumentFragment();
  const capped = rows.slice(0, 260); // guard DOM size; virtually always < 260 after filter

  capped.forEach(d => frag.appendChild(buildRow(d, tpl)));
  body.innerHTML = '';
  body.appendChild(frag);

  if (rows.length > capped.length) {
    const more = document.createElement('div');
    more.style.cssText = 'padding:16px;text-align:center;font-size:12.5px;color:var(--ink-3);font-family:var(--mono)';
    more.textContent = `+${rows.length - capped.length} more — narrow the filters to see them`;
    body.appendChild(more);
  }

  if (!reduceMotion && M.animate) {
    animate(body, { opacity: [0.4, 1] }, { duration: 0.28, ease: 'linear' });
    animate($$('.row', body).slice(0, 14),
      { transform: ['translateY(5px)', 'translateY(0)'] },
      { duration: 0.34, delay: stagger(0.015), ease: [0.16, 1, 0.3, 1] });
  }
}

function countActiveFilters() {
  const f = state.filters;
  return (f.q ? 1 : 0) + (f.state ? 1 : 0) + (f.band ? 1 : 0) + (f.minCohort ? 1 : 0) + (state.watchOnly ? 1 : 0);
}
function sortLabel() {
  const map = { rank: 'rank', district: 'district name', state: 'state', penta1: 'cohort size', dropout: 'dropout rate', trend: '3-year change' };
  return `${map[state.sort.key]} (${state.sort.dir === 'asc' ? 'asc' : 'desc'})`;
}

function buildRow(d, tpl) {
  const node = tpl.content.firstElementChild.cloneNode(true);
  node.dataset.id = idOf(d);
  node.href = `#d/${encodeURIComponent(d.state)}/${encodeURIComponent(d.district)}`;
  node.classList.add('row--' + d.band);
  if (idOf(d) === state.activeId) node.classList.add('is-active');

  node.querySelector('.row__rank').textContent = String(d.rank).padStart(3, '0');
  node.querySelector('.row__name').textContent = d.district;
  node.querySelector('.row__state').textContent = d.state;
  node.querySelector('.row__num').textContent = fmtInt(d.penta1);
  node.querySelector('.row__drop-val').textContent = fmtPct(d.dropout);
  node.querySelector('.row__funnel').appendChild(dropoutBar(d));
  node.querySelector('.row__trend').append(...trendNodes(d.trend));

  const star = node.querySelector('.row__star');
  const on = state.watch.has(idOf(d));
  star.setAttribute('aria-pressed', String(on));
  star.setAttribute('aria-label', on ? 'Remove from watchlist' : 'Add to watchlist');
  star.addEventListener('click', e => {
    e.preventDefault(); e.stopPropagation();
    toggleWatch(d, star);
  });

  node.addEventListener('click', e => {
    e.preventDefault();
    openPanel(d);
  });

  return node;
}

function toggleWatch(d, star) {
  const id = idOf(d);
  if (state.watch.has(id)) state.watch.delete(id);
  else state.watch.add(id);
  saveWatch();
  const on = state.watch.has(id);
  star && star.setAttribute('aria-pressed', String(on));
  $('#watch-n').textContent = state.watch.size;
  $('#watch-n').hidden = state.watch.size === 0;
  if (state.watchOnly) render();
  if (!reduceMotion && M.animate && star && on) {
    animate(star, { transform: ['scale(1)', 'scale(1.32)', 'scale(1)'] }, { duration: 0.34 });
  }
}

/* ---------------------------------------------------------------- funnel + trend viz */

const DROP_SCALE = 0.30; // full bar ≈ 30% dropout (near the observed max)

function dropoutBar(d) {
  const wrap = document.createElement('span');
  wrap.className = 'dbar';
  const fill = document.createElement('span');
  fill.className = 'dbar__fill';
  fill.style.width = Math.min(100, d.dropout / DROP_SCALE * 100).toFixed(1) + '%';
  wrap.appendChild(fill);
  // tick at the high-risk threshold
  const tick = document.createElement('span');
  tick.className = 'dbar__tick';
  tick.style.left = (state.data.national.threshold_high / DROP_SCALE * 100).toFixed(1) + '%';
  wrap.appendChild(tick);
  return wrap;
}

function funnelSvg(d) {
  const w1 = 100;
  const w2 = Math.max(2, d.penta2 / d.penta1 * 100);
  const w3 = Math.max(2, d.penta3 / d.penta1 * 100);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 100 18');
  svg.setAttribute('class', 'funnel');
  svg.setAttribute('preserveAspectRatio', 'none');
  const H = 6, GAP = 3;
  const rows = [[0, w1], [H + GAP, w2], [2 * (H + GAP), w3]];
  rows.forEach(([y, w], i) => {
    const track = document.createElementNS(ns, 'rect');
    track.setAttribute('class', 'f-track');
    track.setAttribute('x', 0); track.setAttribute('y', y);
    track.setAttribute('width', 100); track.setAttribute('height', H);
    svg.appendChild(track);
    if (i > 0 && w < 99.5) {
      const leak = document.createElementNS(ns, 'rect');
      leak.setAttribute('class', 'f-leak');
      leak.setAttribute('x', w); leak.setAttribute('y', y);
      leak.setAttribute('width', Math.max(0, 100 - w)); leak.setAttribute('height', H);
      svg.appendChild(leak);
    }
    const fill = document.createElementNS(ns, 'rect');
    fill.setAttribute('class', 'f-fill');
    fill.setAttribute('x', 0); fill.setAttribute('y', y);
    fill.setAttribute('width', w); fill.setAttribute('height', H);
    svg.appendChild(fill);
  });
  return svg;
}

function trendNodes(t) {
  const span = document.createElement('span');
  const num = document.createElement('span');
  if (t == null || Math.abs(t) < 0.003) {
    span.className = 'arw trend-flat'; span.textContent = '→';
    num.className = 'trend-flat'; num.textContent = 'flat';
  } else if (t > 0) {
    span.className = 'arw trend-up'; span.textContent = '▲';
    num.className = 'trend-up'; num.textContent = '+' + (t * 100).toFixed(1);
  } else {
    span.className = 'arw trend-down'; span.textContent = '▼';
    num.className = 'trend-down'; num.textContent = (t * 100).toFixed(1);
  }
  return [span, num];
}

/* ---------------------------------------------------------------- district panel */

function openPanel(d) {
  state.activeId = idOf(d);
  $$('.row').forEach(r => r.classList.toggle('is-active', r.dataset.id === state.activeId));

  const panel = $('#dpanel');
  const scrim = $('#scrim');
  $('#dpanel-inner').innerHTML = panelHtml(d);
  wirePanel(d);

  scrim.hidden = false;
  panel.hidden = false;
  document.body.style.overflow = 'hidden';
  panel.focus();

  if (!reduceMotion && M.animate) {
    animate(scrim, { opacity: [0, 1] }, { duration: 0.2 });
    animate(panel, { transform: ['translateX(100%)', 'translateX(0)'] }, { duration: 0.42, ease: [0.16, 1, 0.3, 1] });
    animate($$('.dp-sec', panel), { opacity: [0, 1], transform: ['translateY(10px)', 'translateY(0)'] },
      { duration: 0.4, delay: stagger(0.05, { startDelay: 0.12 }), ease: [0.16, 1, 0.3, 1] });
  }
  history.replaceState(null, '', `#d/${encodeURIComponent(d.state)}/${encodeURIComponent(d.district)}`);
}

function closePanel() {
  const panel = $('#dpanel');
  const scrim = $('#scrim');
  if (panel.hidden) return;
  const done = () => {
    panel.hidden = true; scrim.hidden = true;
    document.body.style.overflow = '';
    state.activeId = null;
    $$('.row').forEach(r => r.classList.remove('is-active'));
  };
  if (!reduceMotion && M.animate) {
    animate(scrim, { opacity: [1, 0] }, { duration: 0.18 });
    animate(panel, { transform: ['translateX(0)', 'translateX(100%)'] },
      { duration: 0.32, ease: [0.4, 0, 1, 1] }).finished.then(done);
  } else done();
  history.replaceState(null, '', '#ledger');
}

function bandName(b) { return { high: 'High risk', watch: 'Watch', ontrack: 'On track' }[b]; }

function narrative(d) {
  const nat = state.data.national;
  const yr = YEAR_LABEL[nat.years.at(-1)];
  const drv = d.drivers[0];
  let bandLine;
  if (d.band === 'high')
    bandLine = `That places <strong>${d.district}</strong> in the <strong>high-risk band</strong> — at or above the ${fmtPct(nat.threshold_high)} dropout threshold that marks the worst fifth of districts.`;
  else if (d.band === 'watch')
    bandLine = `That puts it on the <strong>watch list</strong>: above the ${fmtPct(nat.threshold_watch)} mark but below the high-risk cut. Left unaddressed, the signals below can tip it over.`;
  else
    bandLine = `That is within the <strong>on-track band</strong>, but the contributing signals below still merit a look before the next cohort.`;

  const lead = `In ${yr}, <strong>${fmtInt(d.children_missed)}</strong> children in ${d.district} received pentavalent dose 1 but not dose 3 — a dropout of <strong>${fmtPct(d.dropout)}</strong>, ranking it <strong>${d.rank}</strong> of ${nat.districts} monitored districts.`;
  const why = drv ? ` The strongest signal is <strong>${drv.label.toLowerCase()}</strong>: ${drv.explanation}` : '';
  const trendLine = d.trend > 0.01
    ? ` Dropout has risen ${(d.trend * 100).toFixed(1)} points across the reported years.`
    : d.trend < -0.01
      ? ` Encouragingly, dropout has fallen ${Math.abs(d.trend * 100).toFixed(1)} points since ${YEAR_LABEL[nat.years[0]]}.`
      : '';
  return `${lead} ${bandLine}${why}${trendLine}`;
}

const INTERVENTIONS = {
  third_dose_falloff: [
    ['9–12 month catch-up drive', 'Line-list every dose-2 child now age-eligible for dose 3 and assign each to an ANM for a home visit.'],
    ['Due-date reminders', 'Trigger an RCH-portal / ASHA reminder at the dose-2 visit so the dose-3 date is booked before the family leaves.'],
  ],
  second_dose_falloff: [
    ['Tighten newborn tracking', 'Reconcile the dose-1 register against the dose-2 due-list every month at the sub-centre.'],
    ['Book the next dose on the spot', 'Use the MCP card / e-registration to schedule dose 2 before the dose-1 session ends.'],
  ],
  rural_catchment: [
    ['Denser outreach calendar', 'Raise session frequency in the most remote sub-centres and pre-announce a fixed monthly schedule.'],
    ['Reach far habitations', 'Run ASHA-accompanied mobile sessions for hamlets beyond ~5 km of a fixed site.'],
  ],
  service_volatility: [
    ['Audit the micro-plan', 'Find the months with missed sessions and stabilise the calendar and vaccinator roster.'],
    ['Check the cold chain', 'Review ILR/cold-chain uptime and vaccine-indent timeliness for the district store.'],
  ],
  seasonal_disruption: [
    ['Plan around the low month', 'Pre-position stock and schedule compensatory sessions ahead of the known monsoon/harvest/migration dip.'],
    ['Cover migrants', 'Coordinate transit-point and destination-block vaccination for migrant families.'],
  ],
  worsening_trend: [
    ['Escalate to district review', 'Three years of deterioration means routine action has not worked — put it on the DTF agenda.'],
    ['Confirm the signal', 'Commission a rapid coverage-evaluation survey to validate the HMIS trend before reallocating resources.'],
  ],
  large_cohort: [
    ['Rebalance ANM areas', 'Add session days where the load per vaccinator is highest and split oversized sub-centre areas.'],
    ['Add a fixed site', 'Consider an extra fixed session site in the largest wards / urban slums.'],
  ],
  low_private_share: [
    ['Bring private providers into reporting', 'Onboard private and charitable clinics so their doses are counted and children followed up.'],
    ['Build public-side resilience', 'With little private buffer, any lapse in public sessions hits coverage directly — protect the session calendar.'],
  ],
};

function panelHtml(d) {
  const nat = state.data.national;
  const st = state.data.states.find(s => s.state === d.state) || { dropout: null };
  const yrs = nat.years;

  // funnel — per-step loss
  const p1 = d.penta1, p2 = d.penta2, p3 = d.penta3;
  const funnelRow = (lab, val, prev, drop) => {
    const lost = prev != null ? prev - val : 0;
    const pct = prev ? lost / p1 : 0;
    return `
    <div class="dp-funnel__row ${drop ? 'dp-funnel__row--drop' : ''}">
      <span class="dp-funnel__lab">${lab}</span>
      <span class="dp-funnel__track"><span class="dp-funnel__fill" data-w="${(val / p1 * 100).toFixed(2)}" style="width:0%"><span>${fmtInt(val)}</span></span></span>
      <span class="dp-funnel__delta">${prev == null ? '' : lost > 0 ? `−${fmtInt(lost)} · ${fmtPct(pct)}` : 'no further loss'}</span>
    </div>`;
  };

  // drivers
  const driversHtml = d.drivers.length ? d.drivers.map(dr => `
    <div class="driver">
      <div class="driver__top">
        <span class="driver__name">${dr.label}</span>
        <span class="driver__pct">${Math.round((dr.share ?? 0) * 100)}% of signal</span>
      </div>
      <div class="driver__bar"><span class="driver__bar-fill" data-w="${Math.round((dr.share ?? 0) * 100)}" style="width:0%"></span></div>
      <p class="driver__exp">${dr.explanation}</p>
    </div>`).join('') : `<p class="driver__exp">No single signal stands out — dropout here tracks the district's overall cohort dynamics.</p>`;

  // interventions from top drivers
  const seen = new Set();
  const ivx = [];
  d.drivers.forEach(dr => (INTERVENTIONS[dr.key] || []).forEach(([h, b]) => {
    if (seen.has(h)) return; seen.add(h);
    ivx.push(`<li><span class="ivx__mark">✓</span><span><b>${h}.</b> ${b}</span></li>`);
  }));
  const ivxHtml = ivx.slice(0, 5).join('') ||
    `<li><span class="ivx__mark">✓</span><span>Maintain the current session calendar and monthly due-list review.</span></li>`;

  // comparison
  const cmpMax = Math.max(d.dropout, st.dropout || 0, nat.dropout) || 1;
  const cmpRow = (cls, lab, v) => `
    <div class="cmp__row cmp__row--${cls}">
      <span class="cmp__lab">${lab}</span>
      <span class="cmp__track"><span class="cmp__fill" data-w="${(v / cmpMax * 100).toFixed(1)}" style="width:0%"></span></span>
      <span class="cmp__val">${fmtPct(v)}</span>
    </div>`;

  // trend series
  const pts = d.series.filter(s => s.dropout != null);
  const trendSvg = pts.length >= 2 ? trendChartSvg(pts) :
    `<p class="driver__exp">Only one year of comparable data — no trend line yet.</p>`;

  const watched = state.watch.has(idOf(d));

  return `
    <div class="dp-head">
      <button class="dp-close" id="dp-close" aria-label="Close panel">✕</button>
      <div class="dp-eyebrow"><span class="dp-rank">Rank ${String(d.rank).padStart(3, '0')} / ${nat.districts}</span><span>·</span><span>Pentavalent 1 → 3</span></div>
      <h2 class="dp-name" id="dp-name">${d.district}</h2>
      <div class="dp-state">${d.state}</div>
      <span class="dp-band dp-band--${d.band}"><span class="dot dot--${d.band}"></span>${bandName(d.band)}</span>
    </div>

    <div class="dp-sec">
      <div class="dp-headline">
        <span class="dp-big ${d.band === 'high' ? 'dp-big--high' : ''}">${fmtPct(d.dropout)}</span>
        <span class="dp-headline-note">dose 1 → dose 3 dropout · ${fmtInt(d.children_missed)} children in ${YEAR_LABEL[yrs.at(-1)]}</span>
      </div>
      <p class="dp-narrative">${narrative(d)}</p>
    </div>

    <div class="dp-sec">
      <div class="dp-sec__title">Cohort funnel</div>
      <div class="dp-funnel">
        ${funnelRow('Dose 1', p1, null, false)}
        ${funnelRow('Dose 2', p2, p1, true)}
        ${funnelRow('Dose 3', p3, p2, true)}
      </div>
      <p class="dp-funnel__note">Doses delivered and reported to HMIS in ${YEAR_LABEL[yrs.at(-1)]}. Counts are constrained so each dose cannot exceed the one before it.</p>
    </div>

    <div class="dp-sec">
      <div class="dp-sec__title">Why this district is flagged</div>
      ${driversHtml}
    </div>

    <div class="dp-sec">
      <div class="dp-sec__title">Dropout vs state &amp; nation</div>
      <div class="cmp">
        ${cmpRow('district', d.district.length > 12 ? 'District' : d.district, d.dropout)}
        ${cmpRow('state', d.state.length > 12 ? 'State' : d.state, st.dropout || 0)}
        ${cmpRow('national', 'All India', nat.dropout)}
      </div>
    </div>

    <div class="dp-sec">
      <div class="dp-sec__title">Three-year trend</div>
      ${trendSvg}
    </div>

    <div class="dp-sec">
      <div class="dp-sec__title">Recommended interventions</div>
      <ul class="ivx">${ivxHtml}</ul>
    </div>

    <div class="dp-actions">
      <button class="btn" id="dp-watch" aria-pressed="${watched}">${watched ? '★ On watchlist' : '☆ Add to watchlist'}</button>
      <button class="btn" id="dp-copy">Copy summary</button>
    </div>`;
}

function trendChartSvg(pts) {
  const W = 380, H = 120, padL = 34, padR = 12, padT = 12, padB = 24;
  const maxY = Math.max(...pts.map(p => p.dropout)) * 1.15 || 0.05;
  const x = i => padL + i * (W - padL - padR) / (pts.length - 1);
  const y = v => padT + (1 - v / maxY) * (H - padT - padB);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.dropout).toFixed(1)}`).join(' ');
  const grid = [0, maxY / 2, maxY].map(v =>
    `<line class="tl-grid" x1="${padL}" y1="${y(v).toFixed(1)}" x2="${W - padR}" y2="${y(v).toFixed(1)}"/>
     <text class="tl-lab" x="4" y="${(y(v) + 3).toFixed(1)}">${(v * 100).toFixed(0)}%</text>`).join('');
  const dots = pts.map((p, i) =>
    `<circle class="tl-dot" cx="${x(i).toFixed(1)}" cy="${y(p.dropout).toFixed(1)}" r="3.5"/>
     <text class="tl-lab" x="${x(i).toFixed(1)}" y="${H - 8}" text-anchor="middle">${YEAR_LABEL[p.year]}</text>`).join('');
  return `<svg class="trendchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Dropout rate over ${pts.length} years">
    ${grid}<path class="tl-line" d="${line}"/>${dots}
  </svg>`;
}

function wirePanel(d) {
  $('#dp-close').addEventListener('click', closePanel);

  $('#dp-watch').addEventListener('click', e => {
    toggleWatch(d, $(`.row[data-id="${cssEsc(idOf(d))}"] .row__star`));
    const on = state.watch.has(idOf(d));
    e.currentTarget.setAttribute('aria-pressed', String(on));
    e.currentTarget.textContent = on ? '★ On watchlist' : '☆ Add to watchlist';
  });

  $('#dp-copy').addEventListener('click', async e => {
    const txt = plainSummary(d);
    try { await navigator.clipboard.writeText(txt); e.currentTarget.textContent = 'Copied ✓'; }
    catch { e.currentTarget.textContent = 'Copy failed'; }
    setTimeout(() => { e.currentTarget.textContent = 'Copy summary'; }, 1600);
  });

  // animate bars in
  requestAnimationFrame(() => {
    if (reduceMotion || !M.animate) {
      $$('.dp-funnel__fill, .driver__bar-fill, .cmp__fill', $('#dpanel')).forEach(el => el.style.width = el.dataset.w + '%');
      return;
    }
    $$('.dp-funnel__fill', $('#dpanel')).forEach((el, i) =>
      animate(el, { width: ['0%', el.dataset.w + '%'] }, { duration: 0.6, delay: 0.15 + i * 0.08, ease: [0.16, 1, 0.3, 1] }));
    $$('.driver__bar-fill', $('#dpanel')).forEach((el, i) =>
      animate(el, { width: ['0%', el.dataset.w + '%'] }, { duration: 0.5, delay: 0.25 + i * 0.06, ease: [0.16, 1, 0.3, 1] }));
    $$('.cmp__fill', $('#dpanel')).forEach((el, i) =>
      animate(el, { width: ['0%', el.dataset.w + '%'] }, { duration: 0.5, delay: 0.3 + i * 0.06, ease: [0.16, 1, 0.3, 1] }));
    const path = $('.tl-line', $('#dpanel'));
    if (path && path.getTotalLength) {
      const L = path.getTotalLength();
      path.style.strokeDasharray = L;
      animate(path, { strokeDashoffset: [L, 0] }, { duration: 0.8, delay: 0.3, ease: [0.16, 1, 0.3, 1] });
    }
  });
}

function plainSummary(d) {
  const nat = state.data.national;
  const yr = YEAR_LABEL[nat.years.at(-1)];
  const lines = [
    `DoseWatch — ${d.district}, ${d.state}`,
    `Pentavalent dose 1 → 3 dropout (${yr}): ${fmtPct(d.dropout)} · rank ${d.rank}/${nat.districts} · band: ${bandName(d.band)}`,
    `Children who missed dose 3: ${fmtInt(d.children_missed)} (dose1 ${fmtInt(d.penta1)} → dose3 ${fmtInt(d.penta3)})`,
    d.series.filter(s => s.dropout != null).map(s => `${YEAR_LABEL[s.year]} ${fmtPct(s.dropout)}`).join('  →  '),
    '',
    'Contributing signals:',
    ...d.drivers.map((x, i) => `  ${i + 1}. ${x.label} — ${x.explanation}`),
    '',
    'Recommended interventions:',
    ...[...new Set(d.drivers.flatMap(x => (INTERVENTIONS[x.key] || []).map(([h, b]) => `  • ${h}: ${b}`)))].slice(0, 5),
    '',
    `Source: ${state.data.generated}`,
  ];
  return lines.join('\n');
}

function cssEsc(s) { return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&'); }

/* ---------------------------------------------------------------- export */

function exportCsv() {
  const rows = currentRows();
  const head = ['rank', 'district', 'state', 'band', 'penta1', 'penta2', 'penta3', 'dropout_pct', 'leak_1_2_pct', 'leak_2_3_pct', 'trend_pts', 'children_missed', 'top_signal'];
  const lines = [head.join(',')];
  rows.forEach(d => {
    lines.push([
      d.rank, csv(d.district), csv(d.state), d.band, d.penta1, d.penta2, d.penta3,
      (d.dropout * 100).toFixed(2), (d.leak_12 * 100).toFixed(2), (d.leak_23 * 100).toFixed(2),
      (d.trend * 100).toFixed(2), d.children_missed, csv(d.drivers[0]?.label || ''),
    ].join(','));
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `dosewatch_${state.filters.state ? state.filters.state.replace(/\W+/g, '-').toLowerCase() + '_' : ''}${stamp}.csv`;
  a.click();
  URL.revokeObjectURL(url);

  const btn = $('#export-btn');
  const orig = btn.textContent;
  btn.textContent = `Exported ${rows.length} rows ✓`;
  setTimeout(() => { btn.textContent = orig; }, 1800);
}
function csv(s) { return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }

/* ---------------------------------------------------------------- scroll reveal */

function revealSections() {
  // Purely additive: content is fully visible by default. When a block first scrolls
  // into view we play a short transform-only lift. If the observer never fires
  // (headless, odd timing, no IO support) the content is simply already in place.
  if (reduceMotion || !M.animate || !('IntersectionObserver' in window)) return;

  const blocks = $$('.section').flatMap(sec =>
    [sec.querySelector('.section__head'),
     ...$$('.panel, .method-grid > article', sec)].filter(Boolean));

  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (!e.isIntersecting || e.target.dataset.lift) return;
      e.target.dataset.lift = '1';
      io.unobserve(e.target);
      // only lift things that are entering from below — avoids a jump for above-fold content
      if (e.boundingClientRect.top > window.innerHeight * 0.6) {
        animate(e.target, { opacity: [0.55, 1], transform: ['translateY(12px)', 'translateY(0)'] },
          { duration: 0.45, ease: [0.16, 1, 0.3, 1] });
      }
    });
  }, { rootMargin: '0px 0px -6% 0px' });

  blocks.forEach(k => io.observe(k));
}

/* ---------------------------------------------------------------- utils */

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
