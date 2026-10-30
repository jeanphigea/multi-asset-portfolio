// ─── State ────────────────────────────────────────────────────────────────────
let portfolio = [];   // [{ticker, shares, holdings:[...]}]
let grandTotal = 0;   // total £ across all ETFs + direct
let fundamentals = {}; // live company fundamentals keyed by companyKey
let quality = {};      // Buffett-style multi-year quality scores keyed by companyKey
const charts = {};
const expandedCards = new Set(); // tickers currently in expanded view
const PALETTE = [
  {bg:'#eff6ff',fg:'#1d4ed8',bar:'#2563eb'},{bg:'#f0fdf4',fg:'#15803d',bar:'#16a34a'},
  {bg:'#fdf4ff',fg:'#7e22ce',bar:'#9333ea'},{bg:'#fff7ed',fg:'#c2410c',bar:'#ea580c'},
  {bg:'#f0f9ff',fg:'#0369a1',bar:'#0284c7'},{bg:'#fefce8',fg:'#a16207',bar:'#ca8a04'},
  {bg:'#fef2f2',fg:'#b91c1c',bar:'#dc2626'},{bg:'#f5f3ff',fg:'#6d28d9',bar:'#7c3aed'}
];
function pal(i){ return PALETTE[i % PALETTE.length]; }

// ─── API helpers ──────────────────────────────────────────────────────────────
async function api(path, opts={}){
  const r = await fetch(path, {headers:{'Content-Type':'application/json'}, ...opts});
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ─── Load ─────────────────────────────────────────────────────────────────────
// Returns true on success. On failure the previously loaded data is still on
// screen but is NOT current — say so loudly rather than letting stale numbers
// pass for fresh ones.
async function load({retries = 2} = {}){
  setBusy(true);
  for(let attempt = 0; ; attempt++){
    try {
      const [p, f, q, ai, comp] = await Promise.all([
        api('/api/summary'),
        api('/api/fundamentals').catch(() => ({})),
        api('/api/quality').catch(() => ({})),
        api('/api/ai-maturity').catch(() => ({})),
        api('/api/compute-asset').catch(() => ({})),
      ]);
      portfolio = p; fundamentals = f; quality = q;
      // Re-keyed through the same normaliser as holding names (see companyKey).
      const rekey = o => Object.fromEntries(Object.entries(o).map(([k, v]) => [companyKey(k), v]));
      AI_MATURITY = rekey(ai); COMPUTE_ASSET = rekey(comp);
      risk.cache = {}; risk.data = null;   // weights may have changed; re-ask the server
      render();
      setStale(null);
      const etfCount = portfolio.filter(e => !e.is_direct).length;
      const directEntry = portfolio.find(e => e.is_direct);
      const parts = [];
      if(etfCount) parts.push(`${etfCount} ETF${etfCount>1?'s':''}`);
      if(directEntry) parts.push(`${directEntry.position_count} direct positions`);
      setBusy(false);
      document.getElementById('last-loaded').textContent = parts.length
        ? parts.join(' · ') + ` · updated ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`
        : 'No ETFs yet — add some with the ETFs button';
      return true;
    } catch(e) {
      if(attempt < retries){
        setStatus(`⏳ Load failed (${e.message}) — retrying ${attempt+1}/${retries}…`);
        await new Promise(r => setTimeout(r, 500 * (attempt + 1)));
        continue;
      }
      setBusy(false);
      setStatus('❌ Could not load data: ' + e.message);
      setStale(e.message);
      return false;
    }
  }
}

// Banner shown whenever what's on screen is known to be out of date.
function setStale(msg){
  const bar = document.getElementById('stale-bar');
  if(!msg){ bar.style.display = 'none'; return; }
  bar.innerHTML = `⚠️ <strong>Showing stale data</strong>: the last refresh failed (${esc(msg)}). ` +
    `Figures below may not reflect your latest changes. ` +
    `<button class="btn sm" onclick="load()" style="margin-left:8px">Retry now</button>`;
  bar.style.display = 'block';
}

// Status is a toast. Progress (⏳) and problems (❌ ⚠️) stay until replaced or
// dismissed; anything else is a confirmation and fades on its own.
let statusTimer = null;
function setStatus(msg){
  const el = document.getElementById('status-bar');
  clearTimeout(statusTimer);
  if(!msg){ el.classList.remove('show'); return; }
  el.innerHTML = `<span>${esc(msg)}</span><button class="t-close" onclick="setStatus('')" aria-label="Dismiss">×</button>`;
  el.classList.add('show');
  if(!/^(⏳|❌|⚠)/.test(msg)) statusTimer = setTimeout(() => el.classList.remove('show'), 6000);
}
function setBusy(on){ document.body.classList.toggle('busy', on); }

// ─── Render ───────────────────────────────────────────────────────────────────
function render(){
  const grid = document.getElementById('grid');
  Object.values(charts).forEach(c => c.destroy());
  Object.keys(charts).forEach(k => delete charts[k]);
  applyChartTheme();

  const etfTotal = portfolio
    .filter(e => !e.is_direct && e.last_price_gbp != null)
    .reduce((s, e) => s + e.shares * e.last_price_gbp, 0);
  const directEntry = portfolio.find(e => e.is_direct);
  const directTotal = directEntry ? directEntry.shares : 0; // shares = basket GBP
  grandTotal = etfTotal + directTotal;
  renderKpis(etfTotal, directTotal, directEntry);

  grid.innerHTML = portfolio.map((etf, i) => cardHtml(etf, i)).join('');
  grid.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.card');
      card.querySelectorAll('.seg-btn').forEach(t => t.classList.toggle('active', t === btn));
      card.querySelectorAll('.card-pane').forEach(p => p.classList.toggle('active', p.dataset.pane === btn.dataset.tab));
      if(btn.dataset.tab === 'chart'){
        const i = portfolio.findIndex(e => 'card-' + e.ticker === card.id);
        if(i >= 0) drawChart(portfolio[i].ticker, portfolio[i].holdings, i);
      }
    });
  });

  switchTab(activeTab);   // re-draw whichever tab is showing
}

function renderKpis(etfTotal, directTotal, directEntry){
  const set = (id, v) => { document.getElementById(id).textContent = v; };
  const share = v => grandTotal > 0 ? (v / grandTotal * 100).toFixed(1) + '%' : '—';
  const etfs = portfolio.filter(e => !e.is_direct);
  set('kpi-total', grandTotal > 0 ? fmtGbp(grandTotal) : '—');
  set('kpi-etf', fmtGbp(etfTotal));
  set('kpi-etf-sub', `${etfs.length} funds · ${share(etfTotal)}`);
  set('kpi-direct', fmtGbp(directTotal));
  set('kpi-direct-sub', directEntry ? `${directEntry.position_count} positions · ${share(directTotal)}` : 'none');
  const rows = buildExposureRows();
  const seen = rows.reduce((a, r) => a + r.total, 0);
  set('kpi-coverage', share(seen));
  set('kpi-coverage-sub', `${rows.length} holdings identified`);
  const top = rows.find(r => sectorOf(r.key) !== 'Commodities' && sectorOf(r.key) !== CASH_SECTOR);
  set('kpi-top', top ? top.displayName : '—');
  set('kpi-top-sub', top ? `${fmtGbp(top.total)} · ${share(top.total)}` : '');
  renderPriceAsOf();
}

function fmtGbp(v){ return v==null ? '' : '£'+v.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0}); }

function toggleExpand(ticker){
  if(expandedCards.has(ticker)) expandedCards.delete(ticker);
  else expandedCards.add(ticker);
  // Re-render just this card's holdings pane
  const etf = portfolio.find(e=>e.ticker===ticker);
  const i = portfolio.indexOf(etf);
  const card = document.getElementById('card-'+ticker);
  if(!card || !etf) return;
  const pane = card.querySelector('.card-pane[data-pane="table"]');
  const btn  = card.querySelector('.expand-btn');
  const expanded = expandedCards.has(ticker);
  pane.innerHTML = holdingsTableHtml(etf, i, expanded);
  btn.textContent = expanded ? 'Show top 3' : `Show all ${etf.holdings.length}`;
}

function holdingsTableHtml(etf, i, expanded){
  const {ticker, shares, holdings, last_price_gbp, total_covered_pct, is_direct} = etf;
  const p = pal(i);
  const hasData = holdings && holdings.length > 0;
  // For DIRECT: use shares (=total_basket_gbp) with implicit price of 1.0
  const hasPrice = last_price_gbp != null;
  const cols = hasPrice ? 3 : 2;

  if(!hasData){
    return `<div class="muted" style="padding:12px 0;font-size:12px">No holdings data</div>`;
  }

  const maxP = Math.max(...holdings.map(h=>h.weight_pct));
  const visible = expanded ? holdings : holdings.slice(0,3);
  const headerRow = `<tr><th>Holding</th><th class="r">Weight</th>${hasPrice ? '<th class="r">Value</th>' : ''}</tr>`;

  const rows = visible.map(h => {
    const gbpVal = hasPrice ? (h.weight_pct/100) * shares * last_price_gbp : null;
    return `<tr>
      <td class="name">${h.holding_name}</td>
      <td class="col-pct r">${h.weight_pct.toFixed(2)}%
        <div class="bar-wrap"><div class="bar-fill" style="width:${(h.weight_pct/maxP*100).toFixed(1)}%;background:${p.bar}"></div></div>
      </td>${hasPrice ? `<td class="col-gbp r">${fmtGbp(gbpVal)}</td>` : ''}
    </tr>`;
  }).join('');

  const coveredRow = total_covered_pct > 0 && !is_direct ? `
    <div class="covered-row" title="Share of the fund's weight that its provider publishes, and so can be looked through">
      <span>${total_covered_pct.toFixed(0)}% visible</span>
      <div class="covered-bar-wrap"><div class="covered-bar-fill" style="width:${Math.min(total_covered_pct,100).toFixed(1)}%"></div></div>
    </div>` : '';

  return `<table class="htable">${headerRow}${rows}</table>${coveredRow}`;
}

function cardHtml(etf, i){
  const {ticker, shares, holdings, last_price_gbp,
         is_direct, position_count} = etf;
  const p = pal(i);
  const hasData = holdings && holdings.length > 0;
  const src = holdings[0]?.source || 'none';
  const asOf = holdings[0]?.as_of_date || '';
  // For DIRECT: last_price_gbp=1.0 is synthetic; don't show as a real price
  const hasPrice = last_price_gbp != null && !is_direct;
  const expanded = expandedCards.has(ticker);
  const value = is_direct ? shares : hasPrice ? shares * last_price_gbp : null;
  const weight = value != null && grandTotal > 0 ? (value / grandTotal * 100).toFixed(1) + '% of portfolio' : '';

  let meta = '';
  if(is_direct){
    meta = `<div class="card-meta"><span class="dot manual"></span>Direct stock holdings
      ${REF.DEMO ? '' : '<button class="link" onclick="openEditStocks()">Edit</button>'}</div>`;
  } else if(hasData){
    const dotCls = src==='live'?'live':src==='manual'?'manual':'db';
    const label = src==='live'?'Live':src==='manual'?'Manual':'Built-in';
    meta = `<div class="card-meta"><span class="dot ${dotCls}"></span>${label} data${asOf ? ` · as of ${asOf}` : ''}</div>`;
  }

  const sub = is_direct
    ? `${position_count || holdings.length} positions`
    : `${shares.toLocaleString()} shares${hasPrice ? ` · £${last_price_gbp.toFixed(2)}` : ''}`;
  const n = holdings ? holdings.length : 0;
  const expandBtn = n > 3
    ? `<button class="link expand-btn" onclick="toggleExpand('${ticker}')">${expanded ? 'Show top 3' : `Show all ${n}`}</button>`
    : '';

  return `
  <div class="card" id="card-${ticker}">
    <div class="card-head">
      <div class="card-id">
        <span class="etf-mark" style="background:${p.bar}"></span>
        <div>
          <div class="card-ticker">${is_direct ? 'Direct<small>stocks</small>' : ticker}</div>
          <div class="card-sub">${sub}</div>
        </div>
      </div>
      <div class="card-val">
        <div class="v">${value != null ? fmtGbp(value) : '—'}</div>
        <div class="w">${weight}</div>
      </div>
    </div>
    ${meta}
    <div class="card-bar">
      <div class="seg">
        <button class="seg-btn active" data-tab="table">Holdings</button>
        <button class="seg-btn" data-tab="chart">Chart</button>
      </div>
      ${expandBtn}
    </div>
    <div class="card-pane active" data-pane="table">
      ${holdingsTableHtml(etf, i, expanded)}
    </div>
    <div class="card-pane" data-pane="chart">
      <div class="chart-wrap"><canvas id="chart-${ticker}"></canvas></div>
    </div>
    ${!hasData && !is_direct && !REF.DEMO ? unknownBox(ticker) : ''}
  </div>`;
}

function unknownBox(ticker){
  return `
  <div class="unknown-box">
    <h4>Manual holdings entry</h4>
    <p style="margin-bottom:8px">Enter one holding per line: <code>Name, Weight%</code></p>
    <textarea class="htextarea" id="manual-${ticker}"
      placeholder="Apple Inc, 7.5\nMicrosoft Corp, 6.2\nNVIDIA Corp, 5.8"></textarea>
    <button class="btn sm primary save-btn" onclick="saveManual('${ticker}')">Save holdings</button>
  </div>`;
}

function drawChart(ticker, holdings, idx){
  if(!holdings || !holdings.length) return;
  const canvas = document.getElementById('chart-'+ticker);
  if(!canvas) return;
  if(charts[ticker]) charts[ticker].destroy();
  const top10 = holdings.slice(0,10);
  const p = pal(idx);
  applyChartTheme();
  charts[ticker] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: top10.map(h => h.holding_name.length>22 ? h.holding_name.slice(0,22)+'…' : h.holding_name),
      datasets:[{data: top10.map(h=>h.weight_pct), backgroundColor: p.bar}]
    },
    options:{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{callback:v=>v+'%'}},y:{ticks:{font:{size:10}}}}
    }
  });
}

// ─── Overlap ─────────────────────────────────────────────────────────────────
let overlapExpanded = false;

/**
 * Normalize a holding name to a canonical key for deduplication.
 * Rules:
 *  - Corporate bonds (contain coupon pattern like "3.15%") are kept as-is.
 *  - Share class suffix (A, B, C, A/C, Cl A, Class B …) is stripped before
 *    normalization and re-appended so "Apple Inc A" ≠ "Apple Inc C".
 *  - Common corporate suffixes (Corp, Inc, Ltd, PLC, AG, NV, SA, SpA,
 *    Holdings, Group, ADR) are removed.
 *  - ".com" and standalone "com" (e.g. "Amazon com") are removed.
 *  - Punctuation (commas, dots, hyphens) → space; whitespace collapsed.
 *  - Result is lowercase.
 */
function normalizeName(n) {
  // Leave bonds alone — they contain a coupon rate like "3.15%"
  if (/\d+\.\d+%/.test(n)) return n.toLowerCase();

  // Detect and preserve trailing share-class suffix: " A", " C", " A/C",
  // "Cl A", "Class B", etc. (must be 1-2 letters A-C at end of string)
  const classRx = /\s+(?:cl(?:ass)?\s+)?([A-C](?:\/[A-C])?)$/i;
  const classMatch = n.match(classRx);
  const classSuffix = classMatch ? ' ' + classMatch[1].toUpperCase() : '';
  let s = classMatch ? n.slice(0, classMatch.index) : n;

  s = s.toLowerCase();
  // Fold accents so "Nestlé" and "Nestle", "L'Oréal" and "L'OREAL" produce one key.
  s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  s = s.replace(/\.com\b/g, '');          // "Amazon.com" → "Amazon"
  // Drop descriptive parentheticals — "Gold (Physical)" → "Gold" — but keep the
  // scraper's numeric duplicate counters, "Samsung … (2)", which mark a genuinely
  // separate line (preferred vs common shares).
  s = s.replace(/\s*\((?!\s*\d+\s*\))[^)]*\)/g, '');
  // Drop dots first so dotted legal forms collapse into single tokens
  // ("N.V." → "nv", "Co., Ltd." → "co, ltd") and can be matched below.
  s = s.replace(/\./g, '');
  s = s.replace(/[,\-]/g, ' ');           // remaining punctuation → space
  // Remove legal-form suffixes (word-boundary safe). justETF returns full legal
  // names ("Samsung Electronics Co., Ltd."), other sources return short ones.
  s = s.replace(/\b(corp|corporation|inc|incorporated|ltd|limited|plc|co|company|ag|nv|bv|sa|se|spa|sas|ab|asa|oyj|kgaa|pte|llc|lp|publ|ser|holdings|holding|group|adr|ads|com)\b/g, '');
  s = s.replace(/\s+/g, ' ').trim();      // collapse whitespace
  s = s.replace(/[\s&.,;:_\-]+$/, '');     // trailing "&" / punctuation left by suffix removal

  return (NAME_ALIASES[s] || s) + classSuffix;
}

// Bridges that normalisation cannot reach on its own — abbreviations and
// renamings. Maps a normalised variant onto the canonical key that
// COMPANY_ESTIMATES / COMPANY_YAHOO / the fundamentals table are stored under.
// Add a line here whenever a data source starts spelling a company differently.
// Both sides of every lookup (holding names AND the META/fundamentals keys) are
// pushed through normalizeName, so only genuine abbreviations need listing here.
// Served from names.py so the browser and the server key companies
// identically — see the note there.
const {NAME_ALIASES} = REF;

// Commodity futures have no Yahoo sector; these label them by commodity type.
const {COMMODITY_SECTORS} = REF;

// GICS taxonomy, from reference.py.
const {GICS_FROM_YAHOO, GICS_FROM_LABEL, GICS_ORDER} = REF;
// As-of dates and source of the static benchmark weights, shown beside every comparison.
const {MSCI_WORLD_AS_OF, MSCI_ACWI_AS_OF, MSCI_ACWI_SOURCE} = REF;

function renderOverlap(){
  if(portfolio.length < 1){
    document.getElementById('overlap-section').style.display='none';
    return;
  }

  // Build tally of ALL holdings across all ETFs, merging by normalized name.
  // tally key  = normalizeName(holding_name)
  // displayName = preferred human-readable name (DIRECT beats ETF; longer beats shorter)
  const tally = {};
  portfolio.forEach(etf => {
    (etf.holdings||[]).forEach(h => {
      const k = normalizeName(h.holding_name);
      if(!tally[k]){
        tally[k] = {displayName: h.holding_name, tickerSet: new Set(), weights:{}, gbpVals:{}};
      }
      // Prefer DIRECT name (already clean), otherwise prefer longer name as canonical
      if(etf.is_direct || h.holding_name.length > tally[k].displayName.length){
        tally[k].displayName = h.holding_name;
      }
      tally[k].tickerSet.add(etf.ticker);
      // Accumulate in case two variants of same company appear in the same ETF
      tally[k].weights[etf.ticker] = (tally[k].weights[etf.ticker] || 0) + h.weight_pct;
      if(etf.last_price_gbp != null){
        tally[k].gbpVals[etf.ticker] = (tally[k].gbpVals[etf.ticker] || 0)
          + (h.weight_pct/100) * etf.shares * etf.last_price_gbp;
      }
    });
  });

  // Convert tickerSet → array for downstream use
  Object.values(tally).forEach(v => { v.tickers = Array.from(v.tickerSet); });

  // Sort by total £ value descending (sum across all ETFs that hold it)
  const all = Object.entries(tally).map(([, v]) => {
    const totalGbp = Object.values(v.gbpVals).reduce((a,b)=>a+b, 0);
    return [v.displayName, v, totalGbp];
  }).sort((a,b) => b[2] - a[2]);

  if(!all.length){
    document.getElementById('overlap-section').style.display='none';
    return;
  }

  const MAX = 50;
  const COLLAPSED = 10;
  const capped = all.slice(0, MAX);
  const visible = overlapExpanded ? capped : capped.slice(0, COLLAPSED);

  const tickers = portfolio.map(e=>e.ticker);
  const head = `<th>Holding</th><th class="r">% of total</th><th class="r">Total £</th>${tickers.map(t=>`<th class="r">${t === 'DIRECT' ? 'Direct' : t}</th>`).join('')}<th class="r">In</th>`;

  const body = visible.map(([name, v, totalGbp]) => {
    const overlapCls = v.tickers.length >= 2 ? 'font-weight:600' : 'color:var(--sub)';
    // % of grand total portfolio
    const pctTotal = grandTotal > 0 && totalGbp > 0 ? totalGbp / grandTotal * 100 : null;
    const pctCell = pctTotal != null
      ? `<td style="text-align:right;font-size:11px;font-weight:600;color:var(--accent)">${pctTotal.toFixed(2)}%</td>`
      : `<td style="text-align:right;color:var(--muted)">—</td>`;
    const totalCell = totalGbp > 0 ? `<td style="text-align:right;font-weight:500;color:var(--pos)">${fmtGbp(totalGbp)}</td>`
                                   : `<td style="text-align:right;color:var(--muted)">—</td>`;
    const etfCells = tickers.map(t => {
      if(v.weights[t] == null) return `<td class="r" style="color:var(--faint)">—</td>`;
      const gbp = v.gbpVals[t];
      return `<td class="r">${v.weights[t].toFixed(2)}%${gbp>0?`<br><span style="font-size:10.5px;color:var(--pos)">${fmtGbp(gbp)}</span>`:''}</td>`;
    }).join('');
    const countBadge = v.tickers.length >= 2
      ? `<td class="r"><span class="chip accent">${v.tickers.length}</span></td>`
      : `<td class="r" style="color:var(--muted)">1</td>`;
    return `<tr style="${overlapCls}"><td>${name}</td>${pctCell}${totalCell}${etfCells}${countBadge}</tr>`;
  }).join('');

  const remaining = capped.length - COLLAPSED;
  const toggleBtn = capped.length > COLLAPSED
    ? `<div style="margin-top:12px;display:flex;align-items:center;gap:10px">
        <button class="btn sm" onclick="toggleOverlap()">
          ${overlapExpanded ? `Show top ${COLLAPSED}` : `Show all ${capped.length} holdings`}</button>
        ${!overlapExpanded ? `<span class="muted" style="font-size:12px">${remaining} more hidden</span>` : ''}
       </div>`
    : '';

  document.getElementById('overlap-body').innerHTML =
    `<div style="overflow-x:auto"><table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${toggleBtn}`;
  document.getElementById('overlap-section').style.display = activeTab==='portfolio' ? 'block' : 'none';
}

function toggleOverlap(){
  overlapExpanded = !overlapExpanded;
  renderOverlap();
}

// ─── Company Exposure tab ────────────────────────────────────────────────────
let activeTab = 'portfolio';

const TABS = ['portfolio', 'exposure', 'charts', 'countries', 'risk'];

function switchTab(t){
  if(!TABS.includes(t)) t = 'portfolio';
  activeTab = t;
  try { localStorage.setItem('tab', t); } catch(e){}
  if(location.hash !== '#' + t) history.replaceState(null, '', '#' + t);
  TABS.forEach(x => document.getElementById('tab-'+x).classList.toggle('active', t===x));
  document.querySelector('main').classList.toggle('wide', t==='exposure');
  document.getElementById('grid').style.display = t==='portfolio' ? '' : 'none';
  ['overlap', 'exposure', 'charts', 'countries', 'risk'].forEach(s =>
    document.getElementById(s + '-section').style.display = 'none');
  if(t==='portfolio')      renderOverlap();
  else if(t==='exposure')  renderExposure();
  else if(t==='charts')    renderCharts();
  else if(t==='countries') renderCountries();
  else                     renderRisk();
}

// Company-level key: like normalizeName but share classes (A/C) collapse together
// Higher = better label for a merged row. Parenthesised variants lose; among
// equals the longer (more descriptive) name wins.
function nameRank(n){
  return (/\(\s*\d+\s*\)/.test(n) ? 0 : 2000) + (/\([^)]*\)/.test(n) ? 0 : 1000) + n.length;
}

function companyKey(n){
  // Company level: collapse share classes ("Alphabet A"/"Alphabet C") and the
  // scraper's duplicate-line counters ("Samsung … (2)" = preferred vs common)
  // into a single company, since both are exposure to the same business.
  return normalizeName(n)
    .replace(/\s*\(\s*\d+\s*\)\s*$/, '')
    .replace(/\s+[A-C](\/[A-C])?$/, '')
    .trim();
}

// Static metadata + FY2024e fundamentals. Keys are companyKey(name) of the name used
// in holdings/DIRECT. Values: [ticker, sector, roe, fcf, de, eps, m10y, roic, div, beta, pe]
// Shared score palette: pastel blue / green / orange / red. Used by every /20
// score and by the fundamentals cells, so one value always means one colour.
const SCORE_BG = ['var(--s0)', 'var(--s1)', 'var(--s2)', 'var(--s3)'];

// ─── Column definitions ──────────────────────────────────────────────────────
// Single source of truth for every column heading and its hover explanation.
// Edit a definition here and it updates the tooltip everywhere the column is used.
const COL_DEFS = {
  // Identity / exposure
  num:       ['#',            'Row number, ordered by total exposure.'],
  company:   ['Company',      'Company name. Variants across data sources are merged — "Microsoft" and "Microsoft Corp" are one row; share classes (A/C) and preferred lines collapse together. Corporate bonds stay separate.'],
  tickerCol: ['Ticker',       'Stock ticker symbol.'],
  sector:    ['Sector',       'GICS sector — the taxonomy MSCI publishes under, so it matches the Sectors tab. From Yahoo where it maps, otherwise the curated profile in reference.py. Hover a cell for the finer label.'],
  country:   ['Country',      'Country the company is classified to — MSCI\'s classification where it is unambiguous, otherwise primary listing and incorporation. Curated in reference.py; Yahoo\'s head-office country is the fallback.'],
  direct:    ['Direct (£)',   'Value of shares you hold directly, in GBP.'],
  etfExp:    ['ETF Exp. (£)', 'Indirect exposure through your ETFs: for each ETF, (holding weight % ÷ 100) × your ETF shares × ETF price. Summed across every ETF holding the company.'],
  total:     ['TOTAL (£)',    'Direct + ETF exposure combined — your true economic exposure to this company.'],
  pctComb:   ['% Combined',   'This company as a share of your total portfolio value.'],
  sources:   ['Sources',      'Which of your ETFs contribute exposure to this company.'],
  notes:     ['Notes',        'How you hold it: directly, through ETFs, or both.'],

  // Quality score
  score20:   ['Momentum /20', 'MOMENTUM score — 5 pillars, 4 points each.\n' +
                              'Named for what drives it: Growth + Momentum are 40% of the total, so this ranks companies ' +
                              'in an earnings up-cycle with strong price action. Contrast with Quality /20, which measures ' +
                              'durability over multiple years and excludes momentum entirely.\n\n' +
                              '• Profitability — ROE, ROIC, net & gross margin\n' +
                              '• Growth — revenue & EPS growth\n' +
                              '• Balance sheet — D/E, FCF margin, payout ratio\n' +
                              '• Valuation — P/E, PEG\n' +
                              '• Momentum — 12-month return, analyst upside, consensus rating\n' +
                              'Per metric: blue=4, green=3, orange=1, red=0. Pillar = average of its available metrics; total = average of available pillars × 5.\n' +
                              '* marks under 70% of metrics available.'],
  prof:      ['Prof',         'Profitability pillar /4 — ROE, ROIC, net margin, gross margin.'],
  grw:       ['Grw',          'Growth pillar /4 — revenue growth and EPS growth.'],
  bal:       ['Bal',          'Balance sheet pillar /4 — debt-to-equity, FCF margin, payout ratio.'],
  val:       ['Val',          'Valuation pillar /4 — P/E and PEG.'],
  mom:       ['Mom',          'Momentum pillar /4 — 12-month price change, analyst target upside, consensus rating.'],

  // Buffett-style quality score
  quality20: ['Quality /20', 'BUFFETT-STYLE QUALITY — durable business economics, measured over multiple years.\n' +
                              'Deliberately excludes momentum and analyst ratings, which quality investors treat as noise.\n\n' +
                              '• Returns on capital /4 — ROIC, ROE, and ROIC minus an assumed 9% cost of capital. ' +
                              'Buffett: ROIC is "the primary test of managerial economic performance".\n' +
                              '• Consistency /4 — gross-margin stability, share of years with positive free cash flow, ' +
                              'worst-year ROIC, and worst year-over-year revenue change. Does the business shrink in bad years?\n' +
                              '• Moat /4 — gross margin level AND trend. A widening margin signals real pricing power.\n' +
                              '• Balance sheet /4 — debt-to-equity, interest coverage, net cash position.\n' +
                              '• Capital allocation /4 — share count direction (buybacks good, dilution bad) ' +
                              'and whether reinvested capital earns above cost of capital.\n\n' +
                              'Score = average of available pillars × 5.\n' +
                              '* flags a short history or a missing pillar — not comparable to a complete score.\n\n' +
                              'LIMITATION: built on 4–5 years of statements (all yfinance provides). Buffett judges over 10+ ' +
                              'years and a full cycle. A window covering only an up-cycle will make cyclicals look consistent, ' +
                              'so semiconductor names still score higher here than a decade of data would justify.'],

  // AI maturity score
  aiMaturity:['AI Maturity /20', 'AI MATURITY — how well the company governs and deploys AI internally.\n' +
                              'Eight dimensions scored 1–5, weighted, then ×4 to put it on the /20 scale.\n\n' +
                              '• D1 Strategy & value creation      15%  funded, piloted roadmap with quantified objectives\n' +
                              '• D2 Governance & accountability    15%  dedicated committee, Chief AI Officer, board reporting\n' +
                              '• D3 Data                           12%  training-data provenance, quality, traceability\n' +
                              '• D4 Technology & industrialisation 12%  MLOps platform, robustness testing, production deployment\n' +
                              '• D5 Talent, culture & organisation 12%  training plans, social dialogue, change management\n' +
                              '• D6 Deployment & realised value    12%  production use cases on core processes, measured\n' +
                              '• D7 Risk, compliance & controls    12%  risk mapping, system classification, AI Act readiness\n' +
                              '• D8 Financial & stakeholder comms  10%  AI metrics, cost transparency, equity story\n\n' +
                              'LEVELS (on the native /5 scale): >4.2 Transformational · 3.5–4.2 Integrated · ' +
                              '2.6–3.4 Structured · 1.8–2.5 Exploratory · <1.8 Emerging.\n' +
                              'No company in the source study reached Transformational.\n\n' +
                              'Framework: Paul-Antoine Tual, 20 Jul 2026 — paulantoinetual.fr/blog/cac-40-vs-nasdaq-top-10\n' +
                              '‡ marks OUR estimate for a company outside the author\'s 20-company panel. ' +
                              'Those are read from public sources only and are not comparable in rigour to his published scores.\n\n' +
                              'CAVEAT from the source: this measures publicly DOCUMENTED maturity, not audited capability. ' +
                              'The internal dimensions (D3 Data, D4 Technology, D5 Talent) are structurally under-documented ' +
                              'and therefore biased downward.'],

  // Compute-as-asset score
  compute:   ['Compute /20',  'COMPUTE-AS-ASSET score — how much sellable compute capacity the company owns.\n\n' +
                              'Score = Asset Base (0–100) × Monetization Multiplier (0–1) ÷ 5, expressed out of 20 ' +
                              'so it sits on the same scale as Momentum and Quality.\n\n' +
                              'ASSET BASE\n' +
                              '• Owned capacity /40 — critical IT power owned or long-leased (GW) plus installed accelerator fleet.\n' +
                              '   ≥5GW=40 · 2–5GW=32 · 0.5–2GW=22 · 100–500MW=12 · <100MW=5 · none=0\n' +
                              '• Secured power /25 — contracted generation, PPAs, grid interconnects. The binding constraint on growth.\n' +
                              '• Funded pipeline /20 — announced capacity vs current, and whether it is financed.\n' +
                              '• Pricing power /15 — utilization, contract length, ability to raise $/GPU-hour.\n\n' +
                              'MONETIZATION MULTIPLIER\n' +
                              '1.00 pure merchant (selling compute IS the business) · 0.85 major merchant + internal use ·\n' +
                              '0.50 mostly captive, some external · 0.25 captive only (cost centre) · 0.00 owns no compute\n\n' +
                              'The multiplier is a gate, not a component: Meta owns a vast fleet but sells none of it, so it scores low. ' +
                              'Chip suppliers (TSMC, ASML, Samsung) score 0 — they supply the buildout but own no meter they can charge rent on.\n\n' +
                              'This is an EXPOSURE axis, deliberately separate from the /20 quality score.'],

  // Fundamentals
  roe:       ['ROE',          'Return on Equity — net income ÷ shareholders\' equity. How efficiently the company turns equity into profit. >25% very good, <8% poor.'],
  fcfMargin: ['FCF Margin',   'Free Cash Flow margin — (operating cash flow − capex) ÷ revenue. Cash actually generated per £1 of sales. >20% very good, negative is a red flag.'],
  de:        ['D/E',          'Debt-to-Equity — total debt ÷ shareholders\' equity. Leverage; lower is safer. <0.3x very good, >2x risky.'],
  revGrowth: ['Rev Grw',      'Year-over-year revenue growth. Cleaner signal of underlying momentum than EPS growth, which buybacks and one-offs distort.'],
  epsGrowth: ['EPS Growth',   'Year-over-year growth in earnings per share. Can be distorted by buybacks, tax one-offs and base effects — read alongside revenue growth.'],
  netMargin: ['Net Margin',   'Net income ÷ revenue. Profit kept per £1 of sales. >25% very good.'],
  grossMgn:  ['Gross Mgn',    'Gross profit ÷ revenue. Pricing power and moat strength — distinguishes a durable advantage from cost-cutting. >50% very good.'],
  roic:      ['ROIC',         'Return on Invested Capital — operating profit after tax ÷ (debt + equity − cash). STATIC estimate, not refreshed live.'],
  divYield:  ['Div Yield',    'Annual dividend ÷ share price. Income characteristic, not a quality measure — growth companies deliberately pay 0%.'],
  beta:      ['Beta',         'Volatility vs the market over 3 years. 1.0 moves with the market, >1.5 amplifies swings, <0.8 defensive. A risk profile, not good or bad.'],
  pe:        ['P/E',          'Price ÷ trailing 12-month earnings. What you pay per £1 of profit. <15× cheap, >40× priced for high growth. Negative earnings show as —.'],
  peg:       ['PEG',          'P/E ÷ earnings growth rate. Values a company against its own growth, so it treats growth stocks more fairly than raw P/E. <1 cheap for the growth.'],
  m12:       ['12M',          '12-month price change. Momentum persists empirically, but it is backward-looking.'],
  upside:    ['Upside',       'Analyst mean price target vs current price. Consensus opinion, not a forecast — analysts are structurally optimistic.'],
};

// <th> builder driven by COL_DEFS, so heading text and tooltip never drift apart.
function th(key, {cls = '', label = null} = {}){
  const d = COL_DEFS[key];
  if(!d) return `<th class="${cls}">${key}</th>`;
  return `<th class="${cls}" title="${esc(d[1])}">${label ?? d[0]}</th>`;
}
function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ─── AI maturity ─────────────────────────────────────────────────────────────
// Eight dimensions scored 1–5, weighted to a total, then ×4 for a /20 scale.
// Framework: Paul-Antoine Tual, "Top 10 CAC 40 et Nasdaq : la taille ne dit pas
// la maturité IA" (20 Jul 2026), paulantoinetual.fr/blog/cac-40-vs-nasdaq-top-10.
//
// provenance 'published' = the author's own score for that company.
// provenance 'estimated' = our reading of the same framework against public
// sources, for companies outside his 20-company panel. Flagged in the UI with ‡
// because it is NOT comparable in rigour to a published score.
const AI_DIM_WEIGHTS = REF.AI_DIMENSIONS;   // [[name, weight]] from scores.py

// Loaded from /api/ai-maturity; keys re-run through companyKey() on load.
let AI_MATURITY = {};

// Returns {score20, score5, level, dims, provenance, source, asOf} or null.
function aiMaturityScore(key){
  const d = AI_MATURITY[key];
  if(!d) return null;
  const s5 = d.score5;
  const level = s5 > 4.2 ? 'Transformational' : s5 >= 3.5 ? 'Integrated'
              : s5 >= 2.6 ? 'Structured' : s5 >= 1.8 ? 'Exploratory' : 'Emerging';
  return {score20: s5 * 4, score5: s5, level, dims: d.dims,
          provenance: d.provenance, source: d.source, asOf: d.as_of || d.asOf};
}

// ─── Compute-as-asset data ───────────────────────────────────────────────────
// [ownedCapacity/40, securedPower/25, fundedPipeline/20, pricingPower/15, multiplier, source, asOf]
// Score = (sum of first four) × multiplier. Keys are companyKey(name).
// MAINTENANCE: capacity/power figures need a quarterly review against
// SemiAnalysis, Synergy Research or company filings. Update as_of when you do.
// Loaded from /api/compute-asset; keys re-run through companyKey() on load.
let COMPUTE_ASSET = {};

// Returns {score, base, mult, parts, source, asOf} or null when not applicable.
function computeAssetScore(key){
  const d = COMPUTE_ASSET[key];
  if(!d) return null;
  const {cap, pwr, pipe, price, mult} = d;
  const base = cap + pwr + pipe + price;          // /100, matching the pillar weights
  return {score: base * mult / 5,                 // rescaled to /20 for comparability
          base, mult, parts: {cap, pwr, pipe, price}, source: d.source, asOf: d.as_of};
}

// Static FY2024e estimates from reference.py: [ticker, label, roe, fcf, de, eps, net margin, roic, div, beta, pe]
const {COMPANY_ESTIMATES} = REF;
const META_BLANK = ['—','—','—','—','—','—','—','—','—','—','—'];

// AI maturity cell — same palette and bands as the other /20 scores.
function aiCellHtml(ai){
  const cls = 'scorecol';
  if(!ai) return `<td class="${cls} nodata" title="${esc(
    "Not yet assessed.\n\n" +
    "Unlike Momentum and Quality, AI Maturity cannot be computed from market data — it requires " +
    "reading each company's filings and disclosures against the eight-dimension framework. " +
    "Scores therefore exist only where that research has been done: the top holdings by exposure, " +
    "plus any company in the source study 20-company panel.\n\n" +
    "Add an assessment with POST /api/ai-maturity (see spec/12-research-scores.md).")}"></td>`;
  const b = ai.score20 >= 16 ? 0 : ai.score20 >= 12 ? 1 : ai.score20 >= 8 ? 2 : 3;
  const dimLines = ai.dims
    ? '\n' + AI_DIM_WEIGHTS.map((w, i) =>
        `  ${w[0].padEnd(36)} ${ai.dims[i].toFixed(1)}/5  (${(w[1]*100).toFixed(0)}%)`).join('\n') + '\n'
    : '\n  (per-dimension scores not published for this company)\n';
  const tip =
    `${ai.score5.toFixed(2)}/5 → ${ai.score20.toFixed(1)}/20 — ${ai.level}\n` +
    dimLines +
    `\n${ai.provenance === 'published'
        ? 'Published score by the framework author.'
        : '‡ OUR ESTIMATE — company is outside the author\'s panel, scored from public sources only.'}\n` +
    `Basis: ${ai.source}\nAs of ${ai.asOf}`;
  return `<td class="${cls}" style="background:${SCORE_BG[b]};font-weight:700" title="${esc(tip)}">` +
         `${ai.score20.toFixed(1)}${ai.provenance === 'estimated' ? '<span style="color:var(--muted)">‡</span>' : ''}</td>`;
}

// Aggregate every holding — direct and looked through each ETF — into one row
// per company. Shared by the exposure table and the charts tab so the two can
// never disagree about what the portfolio contains.
// scaled: spread each ETF's unpublished remainder like its visible holdings, so
// the rows add up to the whole fund rather than the part its provider discloses.
function buildExposureRows({scaled = false} = {}){
  const comp = {};
  portfolio.forEach(etf => {
    const f = scaled && !etf.is_direct && etf.total_covered_pct > 0 ? 100 / etf.total_covered_pct : 1;
    (etf.holdings||[]).forEach(h => {
      if(/\d+\.\d+%/.test(h.holding_name)) return;      // skip corporate bonds
      const k = companyKey(h.holding_name);
      if(!comp[k]) comp[k] = {displayName:h.holding_name, direct:0, etfExp:0, sources:new Set()};
      // Pick the cleanest label for the merged row: a DIRECT holding's name wins
      // outright; otherwise prefer a name with no "(2)" duplicate-counter and no
      // "(Physical)"-style qualifier, falling back to the longest.
      if(etf.is_direct || nameRank(h.holding_name) > nameRank(comp[k].displayName)){
        comp[k].displayName = h.holding_name;
      }
      const gbp = etf.last_price_gbp != null ? (h.weight_pct/100) * etf.shares * etf.last_price_gbp * f : 0;
      if(etf.is_direct){ comp[k].direct += gbp; }
      else { comp[k].etfExp += gbp; comp[k].sources.add(etf.ticker); }
    });
  });
  return Object.entries(comp)
    .map(([k, v]) => ({...v, key:k, total: v.direct + v.etfExp}))
    .filter(v => v.total > 0)
    .sort((a,b) => b.total - a.total);
}

function renderExposure(){
  const sec = document.getElementById('exposure-section');
  if(!portfolio.length){ sec.style.display='none'; return; }

  // Re-key the static metadata and the live fundamentals through the SAME
  // normaliser used on holding names. Without this, a data source renaming
  // "Samsung Electronics" to "Samsung Electronics Co., Ltd." silently drops the
  // company's fundamentals instead of matching them.
  const META_BY_KEY = {}, fundByKey = {}, qualByKey = {};
  for(const [k, v] of Object.entries(COMPANY_ESTIMATES))  META_BY_KEY[companyKey(k)] = v;
  for(const [k, v] of Object.entries(fundamentals))  fundByKey[companyKey(k)]   = v;
  for(const [k, v] of Object.entries(quality))       qualByKey[companyKey(k)]   = v;

  const all = buildExposureRows();
  all.forEach((r, i) => { r.rank = i + 1; });
  const q = (document.getElementById('exp-search').value || '').trim().toLowerCase();
  const rows = all.filter(r => {
    if(expFilter === 'both'   && !(r.direct > 0 && r.etfExp > 0)) return false;
    if(expFilter === 'direct' && !(r.direct > 0)) return false;
    if(expFilter === 'etf'    && r.direct > 0) return false;
    if(!q) return true;
    const m = META_BY_KEY[r.key] || META_BLANK, lv = fundByKey[r.key];
    return [r.displayName, m[0], m[1], lv?.yahoo_ticker, lv?.industry, sectorOf(r.key),
            countryOf(r.key), ...r.sources].join(' ').toLowerCase().includes(q);
  });
  document.getElementById('exp-count').textContent = rows.length === all.length
    ? `${all.length} companies` : `${rows.length} of ${all.length} companies`;

  const fmt0 = x => '£' + Math.round(x).toLocaleString('en-GB');
  const head = `<tr>
    ${th('num',      {cls:'tl sticky-1'})}
    ${th('company',  {cls:'tl sticky-2'})}
    ${th('tickerCol',{cls:'tl'})}
    ${th('sector',   {cls:'tl'})}
    ${th('country',  {cls:'tl'})}
    ${th('direct')}
    ${th('etfExp')}
    ${th('total')}
    ${th('pctComb')}
    ${th('sources',  {cls:'tl'})}
    ${th('notes',    {cls:'tl'})}
    ${th('score20',  {cls:'sep scorecol grp-start acc-mom'})}
    ${th('quality20',{cls:'scorecol acc-qual'})}
    ${th('aiMaturity',{cls:'scorecol acc-ai'})}
    ${th('compute',  {cls:'sep scorecol grp-end acc-comp'})}
    ${th('roe',      {cls:'sep'})}
    ${th('fcfMargin')}
    ${th('de')}
    ${th('epsGrowth')}
    ${th('netMargin')}
    ${th('roic')}
    ${th('divYield')}
    ${th('beta')}
    ${th('pe')}
  </tr>`;

  const fmtP  = x => x.toFixed(1) + '%';
  const fmtS  = x => (x >= 0 ? '+' : '') + x.toFixed(1) + '%';

  // Score each metric: very good → blue, good → green, not great → orange, bad → red.
  // Thresholds are [blue, green, orange] cut-offs; dir 'hi' = higher is better.
  const SCORE = [
    {dir:'hi', t:[25, 15, 8]},      // ROE %
    {dir:'hi', t:[20, 10, 0]},      // FCF Margin %
    {dir:'lo', t:[0.3, 1.0, 2.0]},  // D/E x
    {dir:'hi', t:[25, 10, 0]},      // EPS Growth %
    {dir:'hi', t:[25, 12, 5]},      // Net Margin %
    {dir:'hi', t:[20, 12, 6]},      // ROIC %
    {dir:'hi', t:[4, 2, 0.5]},      // Div Yield %
    {dir:'lo', t:[0.8, 1.1, 1.5]},  // Beta
    {dir:'lo', t:[15, 25, 40]},     // P/E
  ];

  // /20 quality score: 5 pillars × 4 pts. Per metric blue=4, green=3, orange=1, red=0;
  // pillar = avg of its available metrics, total = avg(available pillars) × 5.
  const BAND_PTS = [4, 3, 1, 0];
  function metricPts(val, dir, t){
    if(val == null || isNaN(val)) return null;
    let band;
    if(dir === 'hi') band = val >= t[0] ? 0 : val >= t[1] ? 1 : val >= t[2] ? 2 : 3;
    else             band = val <= t[0] ? 0 : val <= t[1] ? 1 : val <= t[2] ? 2 : 3;
    return BAND_PTS[band];
  }
  function computeScore(lv, meta){
    const num = s => { const n = parseFloat(String(s).replace(/[~+×x%]/g, '')); return isNaN(n) ? null : n; };
    const pillars = {
      'Profitability': [
        [lv?.roe,                                   'hi', [25, 15, 8]],
        [num(meta[7]),                              'hi', [20, 12, 6]],   // ROIC (static)
        [lv?.net_margin,                            'hi', [25, 12, 5]],
        [lv?.gross_margin,                          'hi', [50, 35, 20]],
      ],
      'Growth': [
        [lv?.rev_growth,                            'hi', [15, 7, 0]],
        [lv?.eps_growth,                            'hi', [25, 10, 0]],
      ],
      'Balance sheet': [
        [lv?.de,                                    'lo', [0.3, 1.0, 2.0]],
        [lv?.fcf_margin,                            'hi', [20, 10, 0]],
        [lv?.payout > 0 ? lv.payout : null,         'lo', [40, 60, 80]],  // 0 = no dividend, skip
      ],
      'Valuation': [
        [lv?.pe > 0 ? lv.pe : null,                 'lo', [15, 25, 40]],
        [lv?.peg > 0 ? lv.peg : null,               'lo', [1, 1.5, 2.5]],
      ],
      'Momentum': [
        [lv?.m12_change,                            'hi', [25, 10, 0]],
        [lv?.target_upside,                         'hi', [20, 10, 0]],
        [lv?.rec_mean,                              'lo', [1.8, 2.3, 3.0]],
      ],
    };
    let pillarVals = [], detail = [], nAvail = 0, nTotal = 0;
    for(const [name, metrics] of Object.entries(pillars)){
      const pts = metrics.map(([v, dir, t]) => { nTotal++; return metricPts(v, dir, t); })
                         .filter(p => p != null);
      nAvail += pts.length;
      if(pts.length){
        const avg = pts.reduce((a,b) => a+b, 0) / pts.length;
        pillarVals.push(avg);
        detail.push(`${name} ${avg.toFixed(1)}/4 (${pts.length} metric${pts.length>1?'s':''})`);
      } else {
        detail.push(`${name} — no data`);
      }
    }
    if(!pillarVals.length) return null;
    const score = pillarVals.reduce((a,b) => a+b, 0) / pillarVals.length * 5;
    return {score, lowConf: nAvail / nTotal < 0.7, detail: detail.join('\n'), nAvail, nTotal};
  }
  // All four /20 scores share SCORE_BG and the same 16/12/8 bands, so a colour
  // means the same thing in every column. The axes are told apart by the
  // accent underline on their headers, not by the cell fill.
  function qualityCellHtml(q){
    if(!q || q.q_score == null) return `<td class="scorecol nodata" title="No financial statements available to score from."></td>`;
    const d = q.detail || {};
    const b = q.q_score >= 16 ? 0 : q.q_score >= 12 ? 1 : q.q_score >= 8 ? 2 : 3;
    const fm = (x, s) => x == null ? '—' : (typeof x === 'number' ? x.toFixed(1)+(s||'') : x);
    const tip =
      `Returns on capital  ${fm(q.p_returns)}/4\n` +
      `Consistency         ${fm(q.p_consistency)}/4\n` +
      `Moat                ${fm(q.p_moat)}/4\n` +
      `Balance sheet       ${fm(q.p_balance)}/4\n` +
      `Capital allocation  ${fm(q.p_capital)}/4\n` +
      `= ${q.q_score.toFixed(1)}/20\n\n` +
      `ROIC ${fm(d.roic,'%')}  (worst year ${fm(d.roic_min,'%')})\n` +
      `Gross margin ${fm(d.gross_margin,'%')}, trend ${d.gm_trend==null?'—':(d.gm_trend>=0?'+':'')+d.gm_trend.toFixed(1)+'pp'}\n` +
      `Worst yr revenue change ${d.rev_worst==null?'—':(d.rev_worst>=0?'+':'')+d.rev_worst.toFixed(0)+'%'}\n` +
      `Share count ${d.share_chg==null?'—':(d.share_chg>=0?'+':'')+d.share_chg.toFixed(1)+'%/yr'}` +
      `${d.share_chg!=null ? (d.share_chg<0?' (buybacks)':' (dilution)') : ''}\n` +
      `Positive FCF in ${d.fcf_years ?? '—'}/${d.fcf_total ?? '—'} yrs · ${q.years ?? '—'} yrs of data` +
      (d.low_confidence ? '\n\n* LOW CONFIDENCE — short history or missing pillar' : '');
    return `<td class="scorecol" style="background:${SCORE_BG[b]};font-weight:700"
              title="${esc(tip)}">${q.q_score.toFixed(1)}${d.low_confidence?'<span style="color:var(--muted)">*</span>':''}</td>`;
  }


  // Compute-as-asset cell — same palette and bands as the other /20 scores.
  function computeCellHtml(ca){
    const cls = 'sep scorecol grp-end';
    if(!ca) return `<td class="${cls} nodata" title="Owns no sellable compute capacity — not part of this asset class."></td>`;
    const b = ca.score >= 16 ? 0 : ca.score >= 12 ? 1 : ca.score >= 8 ? 2 : 3;
    const tip = `Asset base ${ca.base}/100\n` +
      `  Owned capacity   ${ca.parts.cap}/40\n` +
      `  Secured power    ${ca.parts.pwr}/25\n` +
      `  Funded pipeline  ${ca.parts.pipe}/20\n` +
      `  Pricing power    ${ca.parts.price}/15\n` +
      `Monetization ×${ca.mult.toFixed(2)}\n` +
      `= ${(ca.base * ca.mult).toFixed(0)}/100  →  ${ca.score.toFixed(1)}/20\n\n` +
      `Source: ${ca.source} (as of ${ca.asOf})`;
    return `<td class="${cls}" style="background:${SCORE_BG[b]};font-weight:700"
              title="${esc(tip)}">${ca.score.toFixed(1)}</td>`;
  }

  function scoreCellHtml(sc){
    if(!sc) return `<td class="sep scorecol grp-start nodata" title="No fundamentals available to score from."></td>`;
    const band = sc.score >= 16 ? 0 : sc.score >= 12 ? 1 : sc.score >= 8 ? 2 : 3;
    const tip = sc.detail + `\n${sc.nAvail}/${sc.nTotal} metrics available` + (sc.lowConf ? ' — low confidence' : '');
    return `<td class="sep scorecol grp-start" style="background:${SCORE_BG[band]};font-weight:700" title="${esc(tip)}">` +
           `${sc.score.toFixed(1)}${sc.lowConf ? '<span style="color:var(--muted)">*</span>' : ''}</td>`;
  }
  function scoreBg(idx, str){
    if(str === '—') return '';
    const n = parseFloat(String(str).replace(/[~+×x%]/g, ''));
    if(isNaN(n)) return '';
    const {dir, t} = SCORE[idx];
    let band;
    if(dir === 'hi') band = n >= t[0] ? 0 : n >= t[1] ? 1 : n >= t[2] ? 2 : 3;
    else             band = n <= t[0] ? 0 : n <= t[1] ? 1 : n <= t[2] ? 2 : 3;
    if(idx === 8 && n <= 0) return '';   // negative/zero P/E: not meaningful
    return 'background:' + SCORE_BG[band] + ';';
  }
  const body = rows.map(v => {
    const meta = META_BY_KEY[v.key] || META_BLANK;
    let [ticker, sector, ...fund] = meta;
    // Overlay live Yahoo fundamentals where available (ROIC stays static)
    const lv = fundByKey[v.key];
    // Sector, in order of preference: the curated label, then Yahoo's own
    // classification, then the commodity type for a futures line. Ticker falls
    // back to the symbol the fundamentals were actually fetched under.
    const blankCell = x => (x == null || x === '' || x === '—');
    if(blankCell(sector)) sector = lv?.sector || COMMODITY_SECTORS[v.key] || '—';
    if(blankCell(ticker)) ticker = lv?.yahoo_ticker || '—';
    const gics = sectorOf(v.key);
    const sectorTip = [sector !== gics && sector !== '—' ? sector : null, lv?.industry].filter(Boolean).join(' · ');
    const country = countryOf(v.key);
    const liveFlags = new Array(9).fill(false);
    if(lv){
      const ov = (idx, val, fmt) => { if(val != null){ fund[idx] = fmt(val); liveFlags[idx] = true; } };
      ov(0, lv.roe,        fmtP);
      ov(1, lv.fcf_margin, fmtP);
      ov(2, lv.de,         x => x.toFixed(2) + 'x');
      ov(3, lv.eps_growth, fmtS);
      ov(4, lv.net_margin, fmtP);
      ov(6, lv.div_yield,  x => x.toFixed(1) + '%');
      ov(7, lv.beta,       x => x.toFixed(2) + '×');
      ov(8, lv.pe,         x => '~' + Math.round(x) + '×');
    }
    const pct = grandTotal > 0 ? (v.total / grandTotal * 100).toFixed(2) + '%' : '—';
    const note = v.direct > 0 && v.etfExp > 0 ? 'Direct + ETF' : v.direct > 0 ? 'Direct only' : 'ETF only';
    const scoreCell = scoreCellHtml(lv ? computeScore(lv, meta) : null);
    const qualCell  = qualityCellHtml(qualByKey[v.key]);
    const aiCell    = aiCellHtml(aiMaturityScore(v.key));
    const compCell  = computeCellHtml(computeAssetScore(v.key));
    const fundCells = fund.map((f, j) => {
      const blank = (f === '—' || f == null || f === '');
      const cls = [j === 0 ? 'sep' : '', blank ? 'nodata' : ''].filter(Boolean).join(' ');
      if(blank) return `<td${cls?` class="${cls}"`:''} title="Not available for this company."></td>`;
      return `<td${cls?` class="${cls}"`:''} style="${scoreBg(j, f)}color:${liveFlags[j]?'var(--text)':'var(--sub)'}">${f}</td>`;
    }).join('');
    return `<tr>
      <td class="tl sticky-1" style="color:var(--muted)">${v.rank}</td>
      <td class="tl sticky-2" style="font-weight:600">${v.displayName}</td>
      <td class="tl" style="color:var(--sub)">${ticker}</td>
      <td class="tl"${sectorTip ? ` title="${esc(sectorTip)}"` : ''}><span class="sector-cell"><span class="dot" style="background:${SECTOR_COLOURS[gics]}"></span>${gics === 'Unclassified' ? '<span style="color:var(--muted)">—</span>' : gics}</span></td>
      <td class="tl" style="color:var(--sub)">${country === 'Unknown' ? '—' : country}</td>
      <td style="color:var(--pos)">${v.direct > 0 ? fmt0(v.direct) : '—'}</td>
      <td style="color:var(--accent)">${v.etfExp > 0 ? fmt0(v.etfExp) : '—'}</td>
      <td style="font-weight:700">${fmt0(v.total)}</td>
      <td style="font-weight:600;color:var(--accent)">${pct}</td>
      <td class="tl" style="font-size:11px;color:var(--sub)">${Array.from(v.sources).join(', ') || '—'}</td>
      <td class="tl" style="font-size:11px;color:${note==='Direct + ETF'?'var(--warn)':'var(--muted)'}">${note}</td>
      ${scoreCell}
      ${qualCell}
      ${aiCell}
      ${compCell}
      ${fundCells}
    </tr>`;
  }).join('');

  document.getElementById('exposure-body').innerHTML = rows.length
    ? `<table class="exp-table"><thead>${head}</thead><tbody>${body}</tbody></table>`
    : `<div class="empty">No companies match${q ? ` “${esc(q)}”` : ''}.</div>`;
  document.getElementById('fund-updated').textContent = fundUpdatedLabel();
  sec.style.display = 'block';   // must be visible BEFORE measuring column widths
  const table = document.querySelector('#exposure-body table');
  makeColumnsResizable(table);
  syncStickyCols(table);
}


// ─── Benchmark selection ─────────────────────────────────────────────────────
// One choice shared by Sectors, Countries and Risk, so every comparison on the
// page is against the same index. Stored with the Risk settings.
function currentBenchmark(){ return BENCHMARKS[risk.bench]; }

// Weights rescaled to sum to 100, so a hand-entered table that adds to 99.5
// cannot shift every difference by half a point.
function benchWeights(kind){
  const w = currentBenchmark()[kind];
  const tot = Object.values(w).reduce((a, x) => a + x, 0) || 1;
  return Object.fromEntries(Object.entries(w).map(([k, x]) => [k, x / tot * 100]));
}

function setBenchmark(k){
  if(!BENCHMARKS[k]) return;
  risk.bench = k;
  try { localStorage.setItem('risk', JSON.stringify({bench: risk.bench, years: risk.years})); } catch(e){}
  document.querySelectorAll('.bench-select').forEach(sel => { sel.value = k; });
  risk.data = risk.cache[riskKey()] || null;
  switchTab(activeTab);
}

// ─── Charts tab ──────────────────────────────────────────────────────────────
// Sector allocation against MSCI World. The portfolio's own sector labels come
// from three different sources, so everything is mapped onto GICS first — see
// reference.py.

const SECTOR_LIMIT = 200;          // companies included, largest exposure first

// One colour per GICS sector, used identically in both pies so a slice can be
// compared across charts by colour alone.
const SECTOR_COLOURS = {
  'Information Technology': '#3b82f6', 'Financials':             '#10b981',
  'Health Care':            '#8b5cf6', 'Consumer Discretionary': '#f59e0b',
  'Industrials':            '#64748b', 'Communication Services': '#ec4899',
  'Consumer Staples':       '#14b8a6', 'Energy':                 '#ef4444',
  'Materials':              '#a16207', 'Utilities':              '#0ea5e9',
  'Real Estate':            '#84cc16', 'Commodities':            '#d97706',
  'Cash & Money Market':    '#94a3b8', 'Unclassified':           '#cbd5e1',
};

// Mirrors gics_sector() in reference.py. Commodity status is decided from
// the holding's identity, never its label: energy commodities share the
// "Oil & Gas" label with energy equities.
function gicsSector(key, label, yahooSector){
  if(COMMODITY_SECTORS[key]) return 'Commodities';
  if(yahooSector){
    const hit = GICS_FROM_YAHOO[yahooSector.trim().toLowerCase()];
    if(hit) return hit;
  }
  // Curated profile next: already GICS, where labels such as "Consumer" are ambiguous.
  const prof = profileOf(key);
  if(prof && prof[0]) return prof[0];
  if(label && label !== '—'){
    const k = label.trim().toLowerCase();
    const hit = GICS_FROM_LABEL[k] || GICS_FROM_YAHOO[k];
    if(hit) return hit;
  }
  return 'Unclassified';
}

function sectorBreakdown(){
  const META = {}, FUND = {};
  for(const [k, v] of Object.entries(COMPANY_ESTIMATES)) META[companyKey(k)] = v;
  for(const [k, v] of Object.entries(fundamentals)) FUND[companyKey(k)] = v;

  const rows = buildExposureRows().slice(0, SECTOR_LIMIT);
  const by = {};
  let total = 0, unclassified = 0;
  rows.forEach(r => {
    const label  = META[r.key]?.[1];
    const sector = gicsSector(r.key, label, FUND[r.key]?.sector);
    by[sector] = (by[sector] || 0) + r.total;
    total += r.total;
    if(sector === 'Unclassified') unclassified += r.total;
  });
  return {by, total, rows: rows.length, unclassified};
}

function pieConfig(labels, values, title, subtitle){
  return {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map(l => SECTOR_COLOURS[l] || '#cbd5e1'),
        borderColor: cssVar('--surface'), borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '52%',
      plugins: {
        legend: {position: 'right',
                 labels: {boxWidth: 10, font: {size: 11}, padding: 8}},
        title:    {display: true, text: title, font: {size: 13, weight: '600'}},
        subtitle: {display: !!subtitle, text: subtitle,
                   color: cssVar('--muted'), font: {size: 11}, padding: {bottom: 8}},
        tooltip: {callbacks: {label: c => `${c.label}  ${c.parsed.toFixed(1)}%`}},
      },
    },
  };
}

function renderCharts(){
  const sec = document.getElementById('charts-section');
  sec.style.display = 'block';
  if(!portfolio.length) return;
  applyChartTheme();

  const {by, total, rows, unclassified} = sectorBreakdown();
  const pct = s => total > 0 ? (by[s] || 0) / total * 100 : 0;
  const bench = currentBenchmark(), IDX = benchWeights('sectors');
  document.getElementById('sector-vs').textContent = `Portfolio vs ${bench.name}`;

  // The look-through only reaches the holdings ETF providers actually publish
  // (often just the top 10), so the classified total is less than the portfolio.
  // State that plainly: these percentages are shares of what could be seen
  // through, not of everything owned.
  const coverage = grandTotal > 0 ? total / grandTotal * 100 : 0;
  document.getElementById('sector-scope').textContent =
    `${rows} companies · ${fmtGbp(total)} of ${fmtGbp(grandTotal)} (${coverage.toFixed(0)}% ` +
    `of the portfolio) · ${bench.name} weights approximate, as of ${MSCI_WORLD_AS_OF}`;

  // Order both charts the same way, largest portfolio slice first, so the two
  // legends line up and colours can be read across.
  const present = GICS_ORDER.filter(s => pct(s) > 0.05 || IDX[s]);
  const ordered = present.sort((a, b) => pct(b) - pct(a));

  ['chart-sector-portfolio', 'chart-sector-msci'].forEach(id => {
    if(charts[id]) charts[id].destroy();
  });
  charts['chart-sector-portfolio'] = new Chart(
    document.getElementById('chart-sector-portfolio'),
    pieConfig(ordered, ordered.map(pct), 'Your portfolio',
              `${rows} companies, direct + ETF look-through`));
  charts['chart-sector-msci'] = new Chart(
    document.getElementById('chart-sector-msci'),
    pieConfig(ordered.filter(s => IDX[s]),
              ordered.filter(s => IDX[s]).map(s => IDX[s]),
              bench.name, `${bench.note} · approximate weights`));

  // Over/underweight table — the part you actually act on.
  const diffRows = ordered.map(s => {
    // A sector the index does not hold has a 0% weight there: the difference is still a number.
    const mine = pct(s), idx = IDX[s] || 0;
    return {s, mine, idx, diff: mine - idx};
  }).sort((a, b) => b.mine - a.mine);

  const fmtPct  = x => x.toFixed(1) + '%';
  const fmtDiff = d => {
    const col = Math.abs(d) < 1 ? 'var(--sub)' : d > 0 ? 'var(--pos)' : 'var(--neg)';
    return `<span style="color:${col};font-weight:600">${d >= 0 ? '+' : ''}${d.toFixed(1)} pp</span>`;
  };
  document.getElementById('sector-diff').innerHTML = `
    <table class="diff-table">
      <thead><tr>
        <th>GICS sector</th><th>Portfolio</th><th>${esc(bench.name)}</th>
        <th>Difference</th><th>Value</th>
      </tr></thead>
      <tbody>
        ${diffRows.map(r => `<tr>
          <td><span class="swatch" style="background:${SECTOR_COLOURS[r.s] || '#cbd5e1'}"></span>${r.s}</td>
          <td>${fmtPct(r.mine)}</td>
          <td>${fmtPct(r.idx)}</td>
          <td>${fmtDiff(r.diff)}</td>
          <td style="color:var(--sub)">${fmtGbp(by[r.s] || 0)}</td>
        </tr>`).join('')}
        <tr><td>Total</td><td>${fmtPct(diffRows.reduce((a, r) => a + r.mine, 0))}</td>
            <td>100.0%</td><td></td><td>${fmtGbp(total)}</td></tr>
      </tbody>
    </table>
    ${unclassified > 0 ? `<div class="note" style="margin-top:10px">
      ${fmtGbp(unclassified)} (${(unclassified / total * 100).toFixed(1)}%) could not be
      classified — these are holdings with no sector from either source, so they sit
      outside the comparison rather than being assigned to a sector on a guess.</div>` : ''}
  `;
}

// ─── Live prices ─────────────────────────────────────────────────────────────
// Position values are stored, not streamed, so the totals only move when prices
// are re-marked. This shows how stale they are and re-marks on demand.
let priceAsOf = null;

function renderPriceAsOf(){
  const el = document.getElementById('kpi-prices');
  if(!el) return;
  const stamps = portfolio.filter(e => !e.is_direct && e.last_price_date).map(e => e.last_price_date).sort();
  const stamp = priceAsOf || (stamps.length ? stamps[stamps.length - 1] : null);
  if(!stamp){ el.textContent = ''; return; }
  const ageH = (Date.now() - new Date(stamp).getTime()) / 36e5;
  const stale = ageH > 24;
  const when = isNaN(ageH) ? stamp
             : ageH < 1  ? `${Math.max(1, Math.round(ageH * 60))} min ago`
             : ageH < 48 ? `${Math.round(ageH)} h ago`
             : `${Math.round(ageH / 24)} days ago`;
  el.innerHTML = `<span class="${stale ? 'stale' : ''}">${stale ? '\u26a0 ' : ''}prices marked ${when}</span>`;
  el.title = stale
    ? 'Prices are stored values, not a live feed. These are more than a day old, so the total below is not current — click Refresh market data to mark to market.'
    : 'Marked to market from Yahoo Finance, including live FX.';
}

// One button re-marks everything market-derived, cheapest first: prices + FX
// (seconds) so the totals move straight away, then fundamentals and the quality
// scores built on them (about a minute). A failure in one stage is reported and
// the other still runs.
const MARKET_BTN = '<svg class="icon"><use href="#i-refresh"/></svg><span class="lbl">Refresh market data</span>';
async function refreshMarketData(){
  const btn = document.getElementById('price-refresh-btn');
  const stage = label => { btn.innerHTML = `<span class="spinner"></span><span class="lbl">${label}</span>`; };
  btn.disabled = true;
  const notes = [], errors = [];

  stage('Pricing…');
  setStatus('⏳ 1/2 Marking every position to market (prices + FX)…');
  try {
    const r = await api('/api/refresh?part=prices', {method:'POST'});
    priceAsOf = r.as_of;
    const before = grandTotal;
    await load();                       // re-pull summary so the totals move
    const delta = grandTotal - before;
    notes.push(`repriced ${r.updated.stocks} stocks, ${r.updated.etfs} ETFs, ${r.updated.fx} FX rates` +
      (before ? ` (total ${delta >= 0 ? '+' : ''}£${Math.round(delta).toLocaleString('en-GB')})` : ''));
    errors.push(...r.errors);
  } catch(e){
    errors.push('prices: ' + e.message);
  }

  stage('Fundamentals…');
  setStatus('⏳ 2/2 Refreshing fundamentals and quality scores from Yahoo Finance (about a minute)…');
  try {
    const r = await api('/api/refresh?part=fundamentals', {method:'POST'});
    const q = await api('/api/refresh?part=quality', {method:'POST'}).catch(e => ({refreshed:0, errors:[e.message]}));
    [fundamentals, quality] = await Promise.all([api('/api/fundamentals'), api('/api/quality')]);
    render();
    notes.push(`${r.refreshed} fundamentals, ${q.refreshed} quality scores`);
    errors.push(...r.errors, ...(q.errors || []));
  } catch(e){
    errors.push('fundamentals: ' + e.message);
  }

  btn.disabled = false; btn.innerHTML = MARKET_BTN;
  const errNote = errors.length
    ? ` — ${errors.length} failed (${errors.slice(0,3).join('; ')}${errors.length > 3 ? '…' : ''})` : '';
  setStatus(`${errors.length ? '⚠️' : '✅'} Market data refreshed: ${notes.join(' · ') || 'nothing updated'}${errNote}`);
}

function fundUpdatedLabel(){
  const ts = Object.values(fundamentals).map(f => f.updated_at).sort().pop();
  return (ts ? 'Fundamentals updated ' + ts.slice(0, 16).replace('T', ' ') + ' UTC' : 'No live fundamentals yet') + ' · Refresh market data to update';
}

// The rank and company columns stay pinned while the table scrolls sideways; the
// second one's offset is the first one's width, which changes when it is dragged.
function syncStickyCols(table){
  if(!table) return;
  const w = table.querySelector('th.sticky-1')?.offsetWidth || 0;
  table.querySelectorAll('.sticky-2').forEach(c => { c.style.left = w + 'px'; });
}

// Drag handles on column headers. Widths persist across re-renders via expColWidths.
let expColWidths = {};

function makeColumnsResizable(table){
  if(!table) return;
  const ths = table.querySelectorAll('thead th');
  // Lock current (or saved) widths so resizing one column doesn't reflow the rest.
  // table-layout:fixed only honours column widths when the table itself has an
  // explicit width, so keep table width = sum of columns at all times.
  let totalW = 0;
  ths.forEach((th, i) => {
    const w = expColWidths[i] || th.offsetWidth;
    th.style.width = w + 'px';
    totalW += w;
  });
  table.style.tableLayout = 'fixed';
  table.style.minWidth = '0';
  table.style.width = totalW + 'px';

  ths.forEach((th, i) => {
    const grip = document.createElement('div');
    grip.className = 'col-resizer';
    th.appendChild(grip);
    grip.addEventListener('pointerdown', e => {
      e.preventDefault();
      const startX = e.pageX;
      const startW = th.offsetWidth;
      const startTableW = table.offsetWidth;
      grip.classList.add('dragging');
      grip.setPointerCapture(e.pointerId);
      const onMove = ev => {
        const w = Math.max(40, startW + (ev.pageX - startX));
        th.style.width = w + 'px';
        table.style.width = (startTableW + (w - startW)) + 'px';
        expColWidths[i] = w;
        syncStickyCols(table);
      };
      const onUp = () => {
        grip.classList.remove('dragging');
        grip.removeEventListener('pointermove', onMove);
        grip.removeEventListener('pointerup', onUp);
      };
      grip.addEventListener('pointermove', onMove);
      grip.addEventListener('pointerup', onUp);
    });
    // Double-click a grip to reset that column to auto width
    grip.addEventListener('dblclick', () => {
      delete expColWidths[i];
      renderExposure();
    });
  });
}

// ─── Manual holdings ─────────────────────────────────────────────────────────
async function saveManual(ticker){
  const raw = document.getElementById('manual-'+ticker).value.trim();
  const items = raw.split('\n').filter(Boolean).map(line => {
    const parts = line.split(',');
    const name = parts[0].trim();
    const weight = parseFloat(parts[1]) || 0;
    return {name, ticker:'', weight, as_of_date: new Date().toISOString().slice(0,10)};
  }).filter(h => h.name && h.weight > 0);

  if(!items.length){ alert('No valid lines found. Use format: Name, Weight'); return; }
  try {
    await api(`/api/holdings/${ticker}`, {method:'POST', body: JSON.stringify(items)});
    await load();
  } catch(e) {
    alert('Error saving holdings: ' + e.message);
  }
}

// ─── Edit Portfolio Modal ─────────────────────────────────────────────────────
function openEdit(){
  const rows = document.getElementById('edit-rows');
  rows.innerHTML = portfolio.map(e =>
    `<div class="etf-row" data-ticker="${e.ticker}">
      <input class="ticker" placeholder="TICKER" value="${e.ticker}" readonly>
      <input class="shares" type="number" placeholder="Shares" value="${e.shares}" min="0">
      <button class="del-btn" onclick="this.closest('.etf-row').remove()" title="Remove">×</button>
    </div>`
  ).join('');
  if(!portfolio.length) addEditRow();
  document.getElementById('edit-overlay').classList.add('open');
}

function addEditRow(){
  const rows = document.getElementById('edit-rows');
  const div = document.createElement('div');
  div.className = 'etf-row';
  div.innerHTML = `
    <input class="ticker" placeholder="TICKER" oninput="this.value=this.value.toUpperCase()">
    <input class="shares" type="number" placeholder="Shares" min="0">
    <button class="del-btn" onclick="this.closest('.etf-row').remove()" title="Remove">×</button>`;
  rows.appendChild(div);
  div.querySelector('.ticker').focus();
}

function closeEdit(){ document.getElementById('edit-overlay').classList.remove('open'); }

async function savePortfolio(){
  const rows = document.querySelectorAll('#edit-rows .etf-row');
  const desired = [];
  for(const row of rows){
    const ticker = row.querySelector('.ticker').value.trim().toUpperCase();
    const shares = parseFloat(row.querySelector('.shares').value) || 0;
    if(ticker && shares >= 0) desired.push({ticker, shares});
  }

  try {
    await api('/api/portfolio', {method:'POST', body: JSON.stringify(desired)});
  } catch(e){
    setStatus('❌ Could not save: ' + e.message);
    return;
  }
  closeEdit();

  // Your edits are already committed server-side at this point; if the reload
  // fails, say so rather than leaving pre-edit numbers on screen.
  if(!await load()){
    setStatus('⚠️ Portfolio saved, but the page could not reload — figures shown are pre-edit.');
  }
}

// Close modal on overlay click
document.getElementById('edit-overlay').addEventListener('click', e => {
  if(e.target === e.currentTarget) closeEdit();
});
document.getElementById('stocks-overlay').addEventListener('click', e => {
  if(e.target === e.currentTarget) closeEditStocks();
});

// ─── Edit Stocks Modal ────────────────────────────────────────────────────────
let _fxRates = {GBP:1.0, GBp:0.01, USD:0.79, EUR:0.843, HKD:0.098};

function stockMvGbp(qty, price, ccy){
  const rate = _fxRates[ccy] ?? 1.0;
  return qty * price * rate;
}

function fmtMv(v){ return v > 0 ? '£' + Math.round(v).toLocaleString() : '—'; }

function renderFxBar(){
  const FX_LABELS = {USD:'USD → £', EUR:'EUR → £', HKD:'HKD → £', GBp:'GBp → £'};
  document.getElementById('fx-bar').innerHTML = Object.entries(FX_LABELS).map(([ccy, lbl]) =>
    `<div class="fx-item">
       <label>${lbl}</label>
       <input type="number" step="0.001" id="fx-${ccy}" value="${_fxRates[ccy]||''}"
              oninput="updateAllMv()" style="width:64px">
     </div>`
  ).join('');
}

function updateAllMv(){
  // Read current FX inputs
  ['USD','EUR','HKD','GBp'].forEach(c => {
    const el = document.getElementById('fx-'+c);
    if(el) _fxRates[c] = parseFloat(el.value) || _fxRates[c];
  });
  // Recompute MV for each stock row
  document.querySelectorAll('#stocks-rows tr').forEach(tr => {
    const qty   = parseFloat(tr.querySelector('.t-qty')?.value) || 0;
    const price = parseFloat(tr.querySelector('.t-price')?.value) || 0;
    const ccy   = tr.querySelector('.t-ccy')?.value || 'USD';
    const mvEl  = tr.querySelector('.t-mv');
    if(mvEl) mvEl.textContent = fmtMv(stockMvGbp(qty, price, ccy));
  });
}

const CCY_OPTIONS = ['USD','EUR','GBp','GBP','HKD'];

function stockRowHtml(s){
  const qty = s.quantity ?? 0;
  const price = s.last_price ?? 0;
  const ccy = s.currency || 'USD';
  const mv = fmtMv(stockMvGbp(qty, price, ccy));
  const ccyOpts = CCY_OPTIONS.map(c => `<option${c===ccy?' selected':''}>${c}</option>`).join('');
  return `<tr>
    <td><input class="t-ticker" placeholder="TKRS" value="${s.ticker||''}" oninput="this.value=this.value.toUpperCase()"></td>
    <td><input class="t-name" placeholder="Company name" value="${s.name||''}"></td>
    <td><input class="t-qty" type="number" min="0" step="1" value="${qty}" oninput="updateAllMv()"></td>
    <td><input class="t-price" type="number" min="0" step="0.01" value="${price}" oninput="updateAllMv()"></td>
    <td><select class="t-ccy" onchange="updateAllMv()">${ccyOpts}</select></td>
    <td class="t-mv">${mv}</td>
    <td><button class="del-btn" onclick="this.closest('tr').remove();updateAllMv()" title="Remove">×</button></td>
  </tr>`;
}

async function openEditStocks(){
  // Load fresh data
  const [stocks, fx] = await Promise.all([
    api('/api/stocks').catch(()=>[]),
    api('/api/fx').catch(()=>({}))
  ]);
  Object.assign(_fxRates, fx);
  renderFxBar();
  const tbody = document.getElementById('stocks-rows');
  tbody.innerHTML = stocks.map(s => stockRowHtml(s)).join('');
  document.getElementById('stocks-overlay').classList.add('open');
  refreshIbkrButton();
}

// ─── Interactive Brokers ──────────────────────────────────────────────────────
// The sync mirrors IBKR into stock_holdings: it adds, updates AND removes rows.
// Because it deletes, it always runs as a dry run first and asks before writing.

async function refreshIbkrButton(){
  const btn  = document.getElementById('ibkr-sync-btn');
  const note = document.getElementById('ibkr-note');
  try {
    const st = await api('/api/ibkr/status');
    btn.style.display = st.configured ? '' : 'none';
    note.textContent = st.configured && st.fetchedAt
      ? `IBKR last fetched ${new Date(st.fetchedAt).toLocaleString('en-GB')}`
      : '';
  } catch {
    btn.style.display = 'none';   // server not running — just hide the control
    note.textContent = '';
  }
}

async function ibkrCall(dryRun){
  const r = await fetch('/api/ibkr/sync', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({dry_run: dryRun ? 1 : 0})
  });
  const body = await r.json();
  if(!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return body;
}

function ibkrSummary(plan){
  const lines = [];
  const names = xs => xs.map(s => s.ticker).join(', ') || '—';
  lines.push(`Add (${plan.toAdd.length}): ${names(plan.toAdd)}`);
  lines.push(`Update (${plan.toUpdate.length}): ${names(plan.toUpdate)}`);
  lines.push(`REMOVE (${plan.toDelete.length}): ${names(plan.toDelete)}`);
  if(plan.etfs.length) lines.push(`\nETFs at IBKR, left untouched: ${plan.etfs.map(e=>e.ticker).join(', ')}`);
  if(plan.stale) lines.push('\n⚠ IBKR was unreachable — this is the last cached statement.');
  return lines.join('\n');
}

async function syncFromIbkr(){
  setStatus('⏳ Fetching positions from IBKR…');
  let plan;
  try {
    plan = await ibkrCall(true);
  } catch(e){
    setStatus('');
    alert('IBKR sync failed: ' + e.message);
    return;
  }

  const proceed = confirm(
    'Sync direct stock holdings from IBKR?\n\n' + ibkrSummary(plan) +
    '\n\nRemoved rows are deleted from the dashboard. A backup of etf.db is taken first.'
  );
  if(!proceed){ setStatus('IBKR sync cancelled'); return; }

  setStatus('⏳ Applying IBKR positions…');
  try {
    const res = await ibkrCall(false);
    setStatus(`✅ IBKR: ${res.toAdd.length} added, ${res.toUpdate.length} updated, ` +
              `${res.toDelete.length} removed (backup ${res.backup})`);
    await openEditStocks();   // repaint the table from the database
    await load();
  } catch(e){
    setStatus('');
    alert('IBKR sync failed: ' + e.message);
  }
}

function addStockRow(){
  const tbody = document.getElementById('stocks-rows');
  const tr = document.createElement('tr');
  tr.innerHTML = stockRowHtml({ticker:'', name:'', quantity:0, last_price:0, currency:'USD'}).replace('<tr>','').replace('</tr>','');
  tbody.appendChild(tr);
  tr.querySelector('.t-ticker')?.focus();
}

function closeEditStocks(){
  document.getElementById('stocks-overlay').classList.remove('open');
}

async function saveStocks(){
  // Save FX rates first
  const fxPayload = {};
  ['USD','EUR','HKD','GBp'].forEach(c => {
    const el = document.getElementById('fx-'+c);
    if(el) fxPayload[c] = parseFloat(el.value) || _fxRates[c];
  });
  await api('/api/fx', {method:'POST', body: JSON.stringify(fxPayload)}).catch(()=>{});

  // Collect stocks
  const rows = document.querySelectorAll('#stocks-rows tr');
  const items = [];
  for(const tr of rows){
    const ticker = tr.querySelector('.t-ticker')?.value.trim().toUpperCase();
    const name   = tr.querySelector('.t-name')?.value.trim();
    const qty    = parseFloat(tr.querySelector('.t-qty')?.value) || 0;
    const price  = parseFloat(tr.querySelector('.t-price')?.value) || 0;
    const ccy    = tr.querySelector('.t-ccy')?.value || 'USD';
    if(ticker && name) items.push({ticker, name, quantity: qty, last_price: price, currency: ccy});
  }
  setStatus(`⏳ Saving ${items.length} stock positions…`);
  try {
    await api('/api/stocks', {method:'POST', body: JSON.stringify(items)});
    closeEditStocks();
    await load();
  } catch(e){
    alert('Error saving stocks: ' + e.message);
  }
}

// ─── Company profiles: curated GICS sector + country ─────────────────────────
// From reference.py. Keys are re-run through companyKey() on first use, for
// the same reason COMPANY_ESTIMATES is: both sides of a lookup must share one
// normaliser or a renamed holding silently drops its profile.
const {COMPANY_PROFILES, CASH_SECTOR, COUNTRY_META} = REF;

let _profileKeyed = null, _metaKeyed = null, _fundKeyed = null, _fundSrc = null;
function profileOf(key){
  if(!_profileKeyed){
    _profileKeyed = {};
    for(const [k, v] of Object.entries(COMPANY_PROFILES)) _profileKeyed[companyKey(k)] = v;
  }
  return _profileKeyed[key];
}
function metaOf(key){
  if(!_metaKeyed){
    _metaKeyed = {};
    for(const [k, v] of Object.entries(COMPANY_ESTIMATES)) _metaKeyed[companyKey(k)] = v;
  }
  return _metaKeyed[key];
}
function fundOf(key){
  if(_fundSrc !== fundamentals){          // re-key whenever fundamentals are reloaded
    _fundKeyed = {};
    for(const [k, v] of Object.entries(fundamentals)) _fundKeyed[companyKey(k)] = v;
    _fundSrc = fundamentals;
  }
  return _fundKeyed[key];
}
function sectorOf(key){ return gicsSector(key, metaOf(key)?.[1], fundOf(key)?.sector); }

// Yahoo spells a few countries differently from MSCI.
const YAHOO_COUNTRY = {'Korea, Republic of': 'South Korea', 'Republic of Korea': 'South Korea',
                       'Korea': 'South Korea', 'USA': 'United States', 'UK': 'United Kingdom'};

// Commodities and cash are buckets, not countries. The curated profile wins over
// Yahoo, which reports the head office rather than the index classification.
function countryOf(key){
  if(COMMODITY_SECTORS[key]) return 'Commodities';
  const p = profileOf(key);
  if(p && p[1]) return p[1];
  const y = fundOf(key)?.country;
  return y ? (YAHOO_COUNTRY[y] || y) : 'Unknown';
}

// ─── Countries tab ───────────────────────────────────────────────────────────
const NON_COUNTRY = ['Unknown', 'Commodities', 'Cash'];
const REGION_ORDER = ['North America', 'Europe', 'Asia Pacific', 'Latin America', 'Middle East & Africa', 'Other'];
const REGION_COLOURS = {'North America': '#3b82f6', 'Europe': '#10b981', 'Asia Pacific': '#f59e0b',
                        'Latin America': '#ec4899', 'Middle East & Africa': '#8b5cf6', 'Other': '#94a3b8'};
let countryScaled = false;
const openCountries = new Set();

const regionOf = c => COUNTRY_META[c]?.[0] || 'Other';
const marketOf = c => COUNTRY_META[c]?.[1] || '—';

function onCountryScale(on){
  countryScaled = on;
  try { localStorage.setItem('ctryScale', on ? '1' : '0'); } catch(e){}
  renderCountries();
}

function countryBreakdown(){
  const rows = buildExposureRows({scaled: countryScaled});
  const by = {};
  rows.forEach(r => {
    const c = countryOf(r.key);
    (by[c] ||= {country: c, total: 0, companies: []});
    by[c].total += r.total;
    by[c].companies.push(r);
  });
  const equity = Object.values(by).filter(b => !NON_COUNTRY.includes(b.country))
                       .sort((a, b) => b.total - a.total);
  const other = NON_COUNTRY.map(c => by[c]).filter(Boolean);
  const equityTotal = equity.reduce((a, b) => a + b.total, 0);
  const seen = rows.reduce((a, r) => a + r.total, 0);
  return {equity, other, equityTotal, seen};
}

function renderCountries(){
  const sec = document.getElementById('countries-section');
  sec.style.display = 'block';
  if(!portfolio.length) return;
  applyChartTheme();

  const {equity, other, equityTotal, seen} = countryBreakdown();
  const pct  = b => equityTotal > 0 ? b.total / equityTotal * 100 : 0;
  const fmtP = x => x.toFixed(1) + '%';
  const bench = currentBenchmark(), bn = esc(bench.name), IDX = benchWeights('countries');
  const OTHER = IDX.Other || 0;
  document.getElementById('ctry-bar-title').textContent = `Largest countries vs ${bench.name}`;
  // A country the index does not hold has a 0% weight there: the difference is still a number.
  const diffHtml = d => {
    const col = Math.abs(d) < 1 ? 'var(--sub)' : d > 0 ? 'var(--pos)' : 'var(--neg)';
    return `<span style="color:${col};font-weight:600">${d >= 0 ? '+' : ''}${d.toFixed(1)} pp</span>`;
  };

  // ── KPIs ──
  const byName = Object.fromEntries(equity.map(b => [b.country, b]));
  const share  = c => byName[c] ? pct(byName[c]) : 0;
  const isEM   = c => ['EM', 'Frontier'].includes(marketOf(c));
  const emMine = equity.filter(b => isEM(b.country)).reduce((a, b) => a + pct(b), 0);
  const emIdx  = Object.entries(IDX).filter(([c]) => isEM(c)).reduce((a, [, w]) => a + w, 0);
  const top = equity[0];
  const nonEq = other.filter(b => b.country !== 'Unknown').reduce((a, b) => a + b.total, 0);
  const kpi = (label, value, sub) =>
    `<div class="kpi"><div class="k-label">${label}</div><div class="k-value">${value}</div><div class="k-sub">${sub}</div></div>`;
  document.getElementById('ctry-kpis').innerHTML = [
    kpi('Countries', equity.length, `${equity.reduce((a, b) => a + b.companies.length, 0)} companies classified`),
    top ? kpi('Largest', esc(top.country), `${fmtP(pct(top))} · ${bn} ${fmtP(IDX[top.country] || 0)}`) : '',
    kpi('United Kingdom', fmtP(share('United Kingdom')), `home market · ${bn} ${fmtP(IDX['United Kingdom'] || 0)}`),
    kpi('Emerging markets', fmtP(emMine), `${bn} ${fmtP(emIdx)}${OTHER ? ' (named countries)' : ''}`),
    kpi('Outside equities', fmtGbp(nonEq), `commodities + cash · ${seen > 0 ? fmtP(nonEq / seen * 100) : '—'} of look-through`),
  ].join('');

  // ── Bar chart: largest countries, plus any big index country you are missing ──
  const idxTop = Object.entries(IDX).filter(([c]) => c !== 'Other')
                       .sort((a, b) => b[1] - a[1]).slice(0, 10).map(([c]) => c);
  const names = [...new Set([...equity.slice(0, 14).map(b => b.country), ...idxTop])]
                  .sort((a, b) => share(b) - share(a) || (IDX[b] || 0) - (IDX[a] || 0));
  document.getElementById('ctry-bar-sub').textContent =
    `share of classified equity · ${bench.name} weights approximate`;
  ['chart-country-bar', 'chart-region'].forEach(id => { if(charts[id]) charts[id].destroy(); });
  charts['chart-country-bar'] = new Chart(document.getElementById('chart-country-bar'), {
    type: 'bar',
    data: {labels: names, datasets: [
      {label: 'Your portfolio', data: names.map(share), backgroundColor: cssVar('--accent'),
       borderRadius: 3, barPercentage: .9, categoryPercentage: .75},
      {label: bench.name, data: names.map(c => IDX[c] || 0), backgroundColor: cssVar('--faint'),
       borderRadius: 3, barPercentage: .9, categoryPercentage: .75},
    ]},
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {legend: {position: 'top', align: 'end', labels: {boxWidth: 10, boxHeight: 10, font: {size: 11}}},
                tooltip: {callbacks: {label: c => ` ${c.dataset.label}  ${c.parsed.x.toFixed(1)}%`}}},
      scales: {x: {ticks: {callback: v => v + '%'}, grid: {color: cssVar('--line')}},
               y: {ticks: {font: {size: 11}}, grid: {display: false}}},
    },
  });

  // ── Region donut + table ──
  const reg = {}, regIdx = {};
  equity.forEach(b => { const r = regionOf(b.country); reg[r] = (reg[r] || 0) + pct(b); });
  Object.entries(IDX).forEach(([c, w]) => { if(c !== 'Other'){ const r = regionOf(c); regIdx[r] = (regIdx[r] || 0) + w; } });
  const regions = REGION_ORDER.filter(r => reg[r] > 0.05 || regIdx[r]);
  charts['chart-region'] = new Chart(document.getElementById('chart-region'), {
    type: 'doughnut',
    data: {labels: regions, datasets: [{data: regions.map(r => reg[r] || 0),
           backgroundColor: regions.map(r => REGION_COLOURS[r]), borderColor: cssVar('--surface'), borderWidth: 2}]},
    options: {responsive: true, maintainAspectRatio: false, cutout: '58%',
              plugins: {legend: {position: 'right', labels: {boxWidth: 10, font: {size: 11}, padding: 8}},
                        tooltip: {callbacks: {label: c => ` ${c.label}  ${c.parsed.toFixed(1)}%`}}}},
  });
  document.getElementById('region-table').innerHTML = `
    <table class="diff-table"><thead><tr><th>Region</th><th>Portfolio</th><th>${bn}</th><th>Difference</th></tr></thead>
    <tbody>${regions.map(r => `<tr>
      <td><span class="swatch" style="background:${REGION_COLOURS[r]}"></span>${r}</td>
      <td>${fmtP(reg[r] || 0)}</td><td>${fmtP(regIdx[r] || 0)}</td>
      <td>${diffHtml((reg[r] || 0) - (regIdx[r] || 0))}</td></tr>`).join('')}
      <tr><td>Total</td><td>100.0%</td><td>${fmtP(100 - OTHER)}</td><td></td></tr>
    </tbody></table>
    ${OTHER ? `<p class="note" style="margin-top:8px">The index's remaining ${fmtP(OTHER)} sits in markets too small to list individually.</p>` : ''}`;

  // ── Country table ──
  const maxPct = Math.max(...equity.map(pct), 1);
  const detail = b => {
    const list = [...b.companies].sort((x, y) => y.total - x.total);
    return `<tr class="ctry-detail"><td colspan="9"><ul>${list.map(c =>
      `<li><span title="${esc(c.displayName)}">${esc(c.displayName)}</span>
           <span class="muted">${c.direct > 0 ? 'direct' : ''}${c.direct > 0 && c.etfExp > 0 ? ' + ' : ''}${c.etfExp > 0 ? [...c.sources].join(', ') : ''}</span>
           <span style="min-width:62px;text-align:right">${fmtGbp(c.total)}</span></li>`).join('')}</ul></td></tr>`;
  };
  const row = (b, inComparison) => {
    const open = openCountries.has(b.country);
    const idx = IDX[b.country] || 0;
    const p = pct(b);
    const topNames = [...b.companies].sort((x, y) => y.total - x.total).slice(0, 3).map(c => esc(c.displayName)).join(', ');
    return `<tr class="ctry-row${open ? ' open' : ''}" data-country="${esc(b.country)}">
      <td><span class="caret">▸</span> <strong>${esc(b.country)}</strong></td>
      <td style="color:var(--sub)">${inComparison ? regionOf(b.country) : 'Outside comparison'}</td>
      <td>${inComparison ? `<span class="chip">${marketOf(b.country)}</span>` : ''}</td>
      <td class="r">${inComparison ? `<span class="share-bar" style="width:${(p / maxPct * 60).toFixed(0)}px"></span>${fmtP(p)}` : '—'}</td>
      <td class="r" style="color:var(--sub)">${inComparison ? fmtP(idx) : '—'}</td>
      <td class="r">${inComparison ? diffHtml(p - idx) : ''}</td>
      <td class="r" style="font-weight:600">${fmtGbp(b.total)}</td>
      <td class="r" style="color:var(--sub)">${b.companies.length}</td>
      <td style="color:var(--sub);max-width:340px;overflow:hidden;text-overflow:ellipsis">${topNames}</td>
    </tr>${open ? detail(b) : ''}`;
  };
  // Index countries you hold nothing in are worth seeing too: an absence is a position.
  const missing = Object.entries(IDX)
    .filter(([c, w]) => c !== 'Other' && !byName[c] && w >= 0.2).sort((a, b) => b[1] - a[1]);
  document.getElementById('country-table').innerHTML = `
    <div style="overflow-x:auto"><table class="data-table">
      <thead><tr><th>Country</th><th>Region</th><th>Market</th><th class="r">Portfolio</th><th class="r">${bn}</th>
        <th class="r">Difference</th><th class="r">Value</th><th class="r">Companies</th><th>Largest holdings</th></tr></thead>
      <tbody>${equity.map(b => row(b, true)).join('')}</tbody>
      ${missing.length ? `<tbody><tr class="tbody-sep"><td colspan="9">In ${bn}, not held</td></tr>
        ${missing.map(([c, w]) => `<tr><td style="color:var(--sub)">${c}</td><td style="color:var(--sub)">${regionOf(c)}</td>
          <td><span class="chip">${marketOf(c)}</span></td><td class="r">0.0%</td><td class="r" style="color:var(--sub)">${fmtP(w)}</td>
          <td class="r">${diffHtml(-w)}</td><td class="r">—</td><td class="r">0</td><td></td></tr>`).join('')}</tbody>` : ''}
      ${other.length ? `<tbody><tr class="tbody-sep"><td colspan="9">Not a country</td></tr>
        ${other.map(b => row(b, false)).join('')}</tbody>` : ''}
    </table></div>`;

  const coverage = grandTotal > 0 ? seen / grandTotal * 100 : 0;
  const unknown = other.find(b => b.country === 'Unknown');
  document.getElementById('ctry-note').innerHTML =
    (countryScaled
      ? `<strong>Scaled view.</strong> Each ETF's unpublished remainder is assumed to be spread like its visible holdings, so ` +
        `${fmtGbp(seen)} of ${fmtGbp(grandTotal)} is allocated. That is exact for single-country funds (VUSA) and an approximation for broad ones (EMIM, IAPD). `
      : `Percentages are shares of the ${fmtGbp(equityTotal)} of equity that could be looked through ` +
        `(${fmtGbp(seen)} of ${fmtGbp(grandTotal)}, ${coverage.toFixed(0)}% of the portfolio, is visible). ` +
        `Turn on <em>Scale each ETF to 100%</em> to allocate the unseen remainder too. `) +
    `Countries follow MSCI's classification where it is unambiguous, otherwise primary listing and incorporation, ` +
    `so Tencent and Alibaba count as China and Shell as the United Kingdom. ` +
    `${bn} weights are static and approximate (${esc(bench.note)}; ACWI figures from ${MSCI_ACWI_SOURCE}, ${MSCI_ACWI_AS_OF}). ` +
    (unknown ? `${fmtGbp(unknown.total)} has no country yet: add the company to COMPANY_PROFILES in reference.py, or refresh fundamentals.` : '');
}

// ─── Theme ───────────────────────────────────────────────────────────────────
function cssVar(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

// Chart.js draws to canvas and cannot read CSS variables, so it is re-themed at draw time.
function applyChartTheme(){
  if(typeof Chart === 'undefined') return;
  Chart.defaults.color = cssVar('--sub');
  Chart.defaults.borderColor = cssVar('--line');
  Chart.defaults.font.family = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
}

function toggleTheme(){
  const root = document.documentElement;
  const dark = root.dataset.theme
    ? root.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('theme', root.dataset.theme); } catch(e){}
  if(portfolio.length) render();
}

// ─── Risk tab ────────────────────────────────────────────────────────────────
// Two halves. History (risk.py, real prices): what today's mix would have done.
// Scenarios: forward-looking shocks from reference.py applied to every
// company in the look-through, and to the benchmark through its sector,
// country and theme weights, so the two are judged by the same rules.
const {BENCHMARKS, SCENARIOS, SCENARIOS_AS_OF, COUNTRY_CCY, CCY_GROUP, AI_MEGACAPS, RISK_FREE_RATE} = REF;

const risk = {bench: 'acwi', years: 3, data: null, cache: {}, loading: false, error: null,
              mode: 'forward', sel: {forward: SCENARIOS[0].key, history: null}, severity: 1};
try {
  const saved = JSON.parse(localStorage.getItem('risk') || '{}');
  if(BENCHMARKS[saved.bench]) risk.bench = saved.bench;
  if([1, 3, 5, 10].includes(saved.years)) risk.years = saved.years;
} catch(e){}

const fmtPct  = (x, d = 1) => x == null || isNaN(x) ? '—' : x.toFixed(d) + '%';
const fmtSPct = (x, d = 1) => x == null || isNaN(x) ? '—' : (x >= 0 ? '+' : '') + x.toFixed(d) + '%';
const fmtNum  = (x, d = 2) => x == null || isNaN(x) ? '—' : x.toFixed(d);
const fmtDate = s => s ? new Date(s).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'}) : '—';
const fmtSGbp = v => (v >= 0 ? '+' : '−') + '£' + Math.abs(Math.round(v)).toLocaleString('en-GB');
const signCol = (x, neutral = 0.5) => Math.abs(x) < neutral ? 'var(--sub)' : x > 0 ? 'var(--pos)' : 'var(--neg)';

function riskKey(){ return risk.bench + '|' + risk.years; }

async function loadRisk(force = false){
  const k = riskKey();
  if(!force && risk.cache[k]){ risk.data = risk.cache[k]; return drawRisk(); }
  risk.loading = true; risk.error = null;
  drawRisk();
  const btn = document.getElementById('risk-refresh');
  btn.disabled = true;
  try {
    const d = await api(`/api/risk?benchmark=${risk.bench}&years=${risk.years}${force ? '&refresh=1' : ''}`);
    if(d.ok === false) throw new Error(d.error);
    if(force) risk.cache = {};
    risk.cache[k] = d;
    if(k === riskKey()) risk.data = d;
    if(force) setStatus(`✅ Price history re-downloaded${d.errors.length ? ` — ${d.errors.length} symbols failed` : ''}`);
  } catch(e){
    risk.error = e.message;
  }
  btn.disabled = false;
  risk.loading = false;
  if(k === riskKey()) drawRisk();
}

function renderRisk(){
  document.getElementById('risk-section').style.display = 'block';
  if(!portfolio.length) return;
  if(risk.data && risk.cache[riskKey()] === risk.data) drawRisk();
  else loadRisk();
}

function onRiskControls(){
  risk.bench = document.getElementById('risk-bench').value;
  try { localStorage.setItem('risk', JSON.stringify({bench: risk.bench, years: risk.years})); } catch(e){}
  risk.data = risk.cache[riskKey()] || null;
  renderRisk();
}

function drawRisk(){
  applyChartTheme();
  const d = risk.data;
  const kpis = document.getElementById('risk-kpis');
  ['chart-risk-growth', 'chart-risk-dd'].forEach(id => { if(charts[id]){ charts[id].destroy(); delete charts[id]; } });
  if(risk.error && !d){
    kpis.innerHTML = `<div class="panel" style="grid-column:1/-1">❌ Could not compute risk: ${esc(risk.error)}
      <button class="btn sm" style="margin-left:8px" onclick="loadRisk()">Retry</button></div>`;
  } else if(!d){
    kpis.innerHTML = `<div class="panel" style="grid-column:1/-1"><span class="spinner"></span>
      Downloading up to ten years of prices for every holding… the first run takes a few seconds.</div>`;
    ['risk-metrics', 'risk-contrib'].forEach(id => document.getElementById(id).innerHTML = '');
  } else {
    drawRiskHistory(d);
  }
  drawScenarios();
}

function drawRiskHistory(d){
  const p = d.portfolio, b = d.benchmark_metrics, rel = d.relative, bn = d.benchmark.name;
  const better = (mine, theirs, higherIsBetter) => mine == null || theirs == null ? '' :
    ((higherIsBetter ? mine > theirs : mine < theirs) ? 'color:var(--pos)' : 'color:var(--neg)');
  const kpi = (label, value, sub, style = '') =>
    `<div class="kpi"><div class="k-label">${label}</div><div class="k-value" style="${style}">${value}</div><div class="k-sub">${sub}</div></div>`;
  document.getElementById('risk-kpis').innerHTML = [
    kpi('Max drawdown', fmtPct(p.max_drawdown), `${bn} ${fmtPct(b.max_drawdown)} · ${fmtDate(p.trough)}`,
        better(p.max_drawdown, b.max_drawdown, true)),
    kpi('Volatility', fmtPct(p.volatility), `a year · ${bn} ${fmtPct(b.volatility)}`, better(p.volatility, b.volatility, false)),
    kpi('Beta', fmtNum(rel.beta), `vs ${bn} · correlation ${fmtNum(rel.correlation)}`),
    kpi('1-week VaR 95%', fmtPct(p.var95_week), `≈ ${fmtGbp(p.var95_week / 100 * grandTotal)} · ${bn} ${fmtPct(b.var95_week)}`,
        better(p.var95_week, b.var95_week, false)),
    kpi('Sharpe ratio', fmtNum(p.sharpe), `${bn} ${fmtNum(b.sharpe)} · risk-free ${RISK_FREE_RATE}%`, better(p.sharpe, b.sharpe, true)),
    kpi('Annual return', fmtPct(p.cagr), `${bn} ${fmtPct(b.cagr)}`, better(p.cagr, b.cagr, true)),
  ].join('');

  // ── Growth + drawdown charts ──
  const s = d.series;
  const ddOf = nav => { let peak = -Infinity; return nav.map(v => { peak = Math.max(peak, v); return (v / peak - 1) * 100; }); };
  const line = (label, data, colour, fill) => ({label, data, borderColor: colour, backgroundColor: fill || colour,
    borderWidth: 1.6, pointRadius: 0, tension: 0, fill: !!fill});
  const accent = cssVar('--accent'), bcol = cssVar('--muted');
  const common = {responsive: true, maintainAspectRatio: false, interaction: {mode: 'index', intersect: false},
    plugins: {legend: {position: 'top', align: 'end', labels: {boxWidth: 10, boxHeight: 2, font: {size: 11}}}},
    scales: {x: {ticks: {maxTicksLimit: 7, maxRotation: 0, callback(v){ return fmtDate(this.getLabelForValue(v)).replace(/^\d+ /, ''); }},
                 grid: {display: false}},
             y: {grid: {color: cssVar('--line')}}}};
  document.getElementById('risk-growth-sub').textContent = `${fmtDate(d.window.start)} – ${fmtDate(d.window.end)}, in GBP`;
  charts['chart-risk-growth'] = new Chart(document.getElementById('chart-risk-growth'), {type: 'line',
    data: {labels: s.dates, datasets: [line('Your portfolio', s.portfolio.map(v => v * 100), accent),
                                       line(bn, s.benchmark.map(v => v * 100), bcol)]},
    options: {...common, plugins: {...common.plugins, tooltip: {callbacks: {label: c => ` ${c.dataset.label}  £${c.parsed.y.toFixed(1)}`}}},
              scales: {...common.scales, y: {...common.scales.y, ticks: {callback: v => '£' + v}}}}});
  charts['chart-risk-dd'] = new Chart(document.getElementById('chart-risk-dd'), {type: 'line',
    data: {labels: s.dates, datasets: [line('Your portfolio', ddOf(s.portfolio), accent, accent + '33'),
                                       line(bn, ddOf(s.benchmark), bcol)]},
    options: {...common, plugins: {...common.plugins, tooltip: {callbacks: {label: c => ` ${c.dataset.label}  ${c.parsed.y.toFixed(1)}%`}}},
              scales: {...common.scales, y: {...common.scales.y, max: 0, ticks: {callback: v => v + '%'}}}}});

  // ── Metrics table ──
  const recovery = m => m.recovery ? `${m.days_to_recover} days` : 'not yet';
  const rows = [
    ['Total return', fmtSPct(p.total_return), fmtSPct(b.total_return), [p.total_return, b.total_return, true]],
    ['Annualised return', fmtPct(p.cagr), fmtPct(b.cagr), [p.cagr, b.cagr, true]],
    ['Volatility (annualised)', fmtPct(p.volatility), fmtPct(b.volatility), [p.volatility, b.volatility, false]],
    ['Sharpe ratio', fmtNum(p.sharpe), fmtNum(b.sharpe), [p.sharpe, b.sharpe, true]],
    ['Sortino ratio', fmtNum(p.sortino), fmtNum(b.sortino), [p.sortino, b.sortino, true]],
    ['Max drawdown', fmtPct(p.max_drawdown), fmtPct(b.max_drawdown), [p.max_drawdown, b.max_drawdown, true]],
    ['…peak to trough', `${fmtDate(p.peak)} → ${fmtDate(p.trough)}`, `${fmtDate(b.peak)} → ${fmtDate(b.trough)}`],
    ['…time to recover', recovery(p), recovery(b)],
    ['Current drawdown', fmtPct(p.current_drawdown), fmtPct(b.current_drawdown), [p.current_drawdown, b.current_drawdown, true]],
    ['1-week VaR 95%', fmtPct(p.var95_week), fmtPct(b.var95_week), [p.var95_week, b.var95_week, false]],
    ['1-week CVaR 95% (average bad week)', fmtPct(p.cvar95_week), fmtPct(b.cvar95_week), [p.cvar95_week, b.cvar95_week, false]],
    ['Worst week', fmtPct(p.worst_week), fmtPct(b.worst_week), [p.worst_week, b.worst_week, true]],
    ['Worst month', fmtPct(p.worst_month), fmtPct(b.worst_month), [p.worst_month, b.worst_month, true]],
    ['Best month', fmtPct(p.best_month), fmtPct(b.best_month)],
    ['Positive months', fmtPct(p.positive_months, 0), fmtPct(b.positive_months, 0), [p.positive_months, b.positive_months, true]],
  ];
  const relRows = [
    ['Beta', fmtNum(rel.beta), 'Moves about this much for a 1% benchmark move'],
    ['Correlation', fmtNum(rel.correlation), '1 = moves in lockstep with the benchmark'],
    ['Tracking error', fmtPct(rel.tracking_error), 'How far returns stray from the benchmark, a year'],
    ['Upside capture', fmtPct(rel.up_capture, 0), 'Share of the benchmark’s up-months you keep'],
    ['Downside capture', fmtPct(rel.down_capture, 0), 'Share of the benchmark’s down-months you take; under 100% cushions'],
  ];
  document.getElementById('risk-metrics-sub').textContent = `${d.window.years}-year window · weekly returns`;
  document.getElementById('risk-metrics').innerHTML = `
    <table class="diff-table" style="margin-top:0">
      <thead><tr><th>Metric</th><th>Portfolio</th><th>${esc(bn)}</th></tr></thead>
      <tbody>${rows.map(([n, a, c, cmp]) => `<tr><td>${n}</td>
        <td style="${cmp ? better(...cmp) : ''};font-weight:600">${a}</td><td style="color:var(--sub)">${c}</td></tr>`).join('')}
      </tbody></table>
    <table class="diff-table">
      <thead><tr><th>Relative to ${esc(bn)}</th><th></th><th style="text-align:left">Reads as</th></tr></thead>
      <tbody>${relRows.map(([n, v, h]) => `<tr><td>${n}</td><td style="font-weight:600">${v}</td>
        <td style="text-align:left;color:var(--muted);font-size:11.5px">${h}</td></tr>`).join('')}</tbody></table>`;

  // ── Risk contributions ──
  const top = d.contributions.slice(0, 14);
  const rest = d.contributions.slice(14);
  const maxShare = Math.max(...d.contributions.map(c => c.risk_share || 0), 1);
  const row = c => {
    const ratio = c.weight > 0 ? c.risk_share / c.weight : 0;
    return `<tr><td><strong>${esc(c.name === c.id ? c.id : c.name)}</strong>${c.name !== c.id ? ` <span class="muted">${esc(c.id)}</span>` : ''}</td>
      <td class="r">${fmtPct(c.weight)}</td>
      <td class="r"><span class="share-bar" style="width:${Math.max(2, c.risk_share / maxShare * 70).toFixed(0)}px;background:${ratio > 1.5 ? 'var(--neg)' : ratio < 0.7 ? 'var(--pos)' : 'var(--accent)'}"></span>${fmtPct(c.risk_share)}</td>
      <td class="r" style="color:var(--sub)">${fmtPct(c.volatility, 0)}</td>
      <td class="r" style="color:var(--sub)">${fmtNum(c.beta)}</td></tr>`;
  };
  const restW = rest.reduce((a, c) => a + c.weight, 0), restR = rest.reduce((a, c) => a + (c.risk_share || 0), 0);
  document.getElementById('risk-contrib').innerHTML = `
    <div style="overflow-x:auto"><table class="data-table">
      <thead><tr><th>Position</th><th class="r">Weight</th><th class="r">Share of risk</th><th class="r">Volatility</th><th class="r">Beta</th></tr></thead>
      <tbody>${top.map(row).join('')}
        ${rest.length ? `<tr><td style="color:var(--sub)">${rest.length} other positions</td><td class="r">${fmtPct(restW)}</td>
          <td class="r">${fmtPct(restR)}</td><td></td><td></td></tr>` : ''}</tbody></table></div>
    <p class="note" style="margin-top:8px">Red bars take more than 1.5× their weight in risk, green less than 0.7×.
      Diversification is why the shares can differ from the weights: a volatile position that moves against the rest can carry little risk.</p>`;

  const miss = d.missing.length ? ` No price history for ${d.missing.join(', ')}, so they are left out.` : '';
  document.getElementById('risk-note').innerHTML =
    `<strong>How the history is computed.</strong> Today's positions and weights are run through real prices (${esc(d.benchmark.note)} for the benchmark), ` +
    `converted to GBP so currency moves count, and rebalanced daily. It measures the risk of the current mix, not of past trades. ` +
    `Volatility, beta and VaR use weekly returns, because daily returns across Hong Kong, London and New York closes understate co-movement. ` +
    `Holdings with a short history are re-weighted out until they start trading: ${fmtPct(d.coverage_start, 0)} of today's portfolio had a price at the start of this window. ` +
    `Cash-like holdings (CSH2) earn ${RISK_FREE_RATE}% a year.${miss} ` +
    `Price history downloaded ${d.history_as_of ? fmtDate(d.history_as_of) : '—'}.`;
}

// ─── Scenario model ──────────────────────────────────────────────────────────
function companyTags(key){
  const label = (metaOf(key)?.[1] || '').toLowerCase();
  const ind = (fundOf(key)?.industry || '').toLowerCase();
  const t = [];
  if(/semi/.test(label) || /semiconductor/.test(ind)) t.push('semis');
  if(AI_MEGACAPS.includes(key)) t.push('ai_megacap');
  if(/gold|silver/.test(label) || /gold|precious/.test(ind)) t.push('gold_miners');
  if(/defen[cs]e/.test(label) || /aerospace & defense/.test(ind)) t.push('defence');
  if(/bitcoin/.test(label)) t.push('bitcoin');
  if(/bank/.test(label) || /^banks/.test(ind)) t.push('banks');
  if(/auto/.test(label) || /auto manufacturers/.test(ind)) t.push('autos');
  return t;
}

// Move of a currency against GBP: named, else its group, else 0. HKD is pegged.
function fxFor(ccy, sc){
  if(!ccy || ccy === 'GBP') return 0;
  const f = sc.fx || {};
  if(f[ccy] != null) return f[ccy];
  if(ccy === 'HKD') return f.USD || 0;
  const g = ccy === 'EM' ? 'EM' : CCY_GROUP[ccy];
  return g && f[g] != null ? f[g] : 0;
}

// GBP return of one company, in %, at severity k.
function holdingShock(key, sc, k){
  const sector = sectorOf(key), country = countryOf(key);
  if(sector === CASH_SECTOR || country === 'Cash') return 0;
  let local, ccy;
  if(sector === 'Commodities'){
    local = (sc.commodities || {})[COMMODITY_SECTORS[key]] ?? 0;
    ccy = 'USD';
  } else {
    local = sc.market + (sc.sectors[sector] || 0) + (sc.countries[country] || 0);
    companyTags(key).forEach(t => { local += sc.tags[t] || 0; });
    ccy = COUNTRY_CCY[country] || 'USD';
  }
  local = Math.max(-95, local * k);
  return ((1 + local / 100) * (1 + k * fxFor(ccy, sc) / 100) - 1) * 100;
}

// Same rules applied to the benchmark's sector / theme mix, country by country.
function benchShock(bkey, sc, k){
  const b = BENCHMARKS[bkey];
  const wavg = (weights, adj) => {
    const tot = Object.values(weights).reduce((a, w) => a + w, 0) || 1;
    return Object.entries(weights).reduce((a, [n, w]) => a + w / tot * (adj[n] || 0), 0);
  };
  const sAdj = wavg(b.sectors, sc.sectors);
  const tAdj = Object.entries(b.tags || {}).reduce((a, [t, w]) => a + w / 100 * (sc.tags[t] || 0), 0);
  let r = 0, ws = 0;
  for(const [c, w] of Object.entries(b.countries)){
    const local = Math.max(-95, k * (sc.market + sAdj + tAdj + (c === 'Other' ? 0 : (sc.countries[c] || 0))));
    r += w * ((1 + local / 100) * (1 + k * fxFor(COUNTRY_CCY[c] || 'EM', sc) / 100) - 1);
    ws += w;
  }
  return r / ws * 100;
}

function runScenario(sc, k){
  const rows = buildExposureRows({scaled: true});   // whole funds, not just their published top holdings
  let total = 0, pnl = 0;
  const items = [], bySector = {};
  rows.forEach(r => {
    const s = holdingShock(r.key, sc, k), d = r.total * s / 100;
    total += r.total; pnl += d;
    items.push({name: r.displayName, key: r.key, value: r.total, shock: s, pnl: d});
    const sec = sectorOf(r.key);
    bySector[sec] = (bySector[sec] || 0) + d;
  });
  const pct = total > 0 ? pnl / total * 100 : 0;
  return {pct, gbp: pct / 100 * grandTotal, items, bySector, bench: benchShock(risk.bench, sc, k)};
}

// ─── Scenario UI ─────────────────────────────────────────────────────────────
function drawScenarios(){
  if(charts['chart-scen']){ charts['chart-scen'].destroy(); delete charts['chart-scen']; }
  if(charts['chart-scen-path']){ charts['chart-scen-path'].destroy(); delete charts['chart-scen-path']; }
  const bn = BENCHMARKS[risk.bench].name;
  const list = document.getElementById('scen-list'), detail = document.getElementById('scen-detail');
  let entries;
  if(risk.mode === 'forward'){
    entries = SCENARIOS.map(sc => ({key: sc.key, name: sc.name, sub: sc.horizon, ...runScenario(sc, risk.severity)}))
                       .map(e => ({...e, mine: e.pct, theirs: e.bench}));
    document.getElementById('scen-sub').textContent =
      `Hypothetical shocks as of ${SCENARIOS_AS_OF}, in GBP · severity ${Math.round(risk.severity * 100)}%`;
  } else {
    if(!risk.data){
      list.innerHTML = ''; detail.innerHTML = `<div class="empty"><span class="spinner"></span> Loading price history…</div>`;
      return;
    }
    entries = risk.data.episodes.map(e => ({key: e.key, name: e.name, sub: `${fmtDate(e.start)} – ${fmtDate(e.end)}`,
                                            mine: e.portfolio.return, theirs: e.benchmark.return, ep: e}));
    if(!risk.sel.history && entries.length) risk.sel.history = entries[0].key;
    document.getElementById('scen-sub').textContent = `Today's holdings through real market sell-offs, in GBP`;
  }

  const accent = cssVar('--accent'), bcol = cssVar('--faint');
  charts['chart-scen'] = new Chart(document.getElementById('chart-scen'), {type: 'bar',
    data: {labels: entries.map(e => e.name), datasets: [
      {label: 'Your portfolio', data: entries.map(e => e.mine), backgroundColor: accent, borderRadius: 3},
      {label: bn, data: entries.map(e => e.theirs), backgroundColor: bcol, borderRadius: 3}]},
    options: {indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      onClick: (_, els) => { if(els.length){ risk.sel[risk.mode] = entries[els[0].index].key; drawScenarios(); } },
      plugins: {legend: {position: 'top', align: 'end', labels: {boxWidth: 10, boxHeight: 10, font: {size: 11}}},
                tooltip: {callbacks: {label: c => ` ${c.dataset.label}  ${fmtSPct(c.parsed.x)}`}}},
      scales: {x: {ticks: {callback: v => v + '%'}, grid: {color: cssVar('--line')}}, y: {grid: {display: false}, ticks: {font: {size: 11}}}}}});

  const selKey = risk.sel[risk.mode];
  list.innerHTML = entries.map(e => `
    <button class="scen-item${e.key === selKey ? ' active' : ''}" data-key="${e.key}">
      <span class="scen-name">${esc(e.name)}</span>
      <span class="scen-sub">${esc(e.sub)}</span>
      <span class="scen-nums"><b style="color:${signCol(e.mine)}">${fmtSPct(e.mine)}</b>
        <span class="muted">vs ${fmtSPct(e.theirs)}</span></span>
    </button>`).join('');

  const e = entries.find(x => x.key === selKey) || entries[0];
  if(!e){ detail.innerHTML = ''; return; }
  const diff = e.mine - e.theirs;
  const impact = (label, v, sub, col) =>
    `<div class="impact"><div class="k-label">${label}</div><div class="impact-v" style="color:${col}">${v}</div><div class="k-sub">${sub}</div></div>`;

  if(risk.mode === 'forward'){
    const sc = SCENARIOS.find(s => s.key === e.key);
    const hits = [...e.items].sort((a, b) => a.pnl - b.pnl).slice(0, 8);
    const cushions = [...e.items].filter(x => x.pnl > 0).sort((a, b) => b.pnl - a.pnl).slice(0, 5);
    const sectors = Object.entries(e.bySector).sort((a, b) => a[1] - b[1]);
    const maxAbs = Math.max(...sectors.map(([, v]) => Math.abs(v)), 1);
    const chips = (obj, unit = '%') => Object.entries(obj || {}).filter(([, v]) => v)
      .map(([k, v]) => `<span class="chip" style="color:${signCol(v, 0.01)}">${esc(k.replace(/_/g, ' '))} ${v > 0 ? '+' : ''}${v}${unit}</span>`).join(' ');
    const itemRow = x => `<li><span>${esc(x.name)}</span><span class="muted">${fmtSPct(x.shock, 0)}</span>
      <span style="color:${signCol(x.pnl, 1)};min-width:74px;text-align:right">${fmtSGbp(x.pnl)}</span></li>`;
    detail.innerHTML = `
      <h3 style="font-size:16px">${esc(sc.name)}</h3>
      <p class="note" style="margin:4px 0 2px">${esc(sc.story)}</p>
      <p class="muted" style="font-size:12px">Horizon ${esc(sc.horizon)} · analogue: ${esc(sc.analog)}</p>
      <div class="impact-row">
        ${impact('Your portfolio', fmtSPct(e.mine), fmtSGbp(e.gbp), signCol(e.mine))}
        ${impact(esc(bn), fmtSPct(e.theirs), 'same assumptions', signCol(e.theirs))}
        ${impact('Difference', (diff >= 0 ? '+' : '') + diff.toFixed(1) + ' pp', diff >= 0 ? 'you lose less' : 'you lose more', signCol(diff))}
      </div>
      <label class="severity">Severity <input type="range" id="scen-severity" min="0.5" max="1.5" step="0.05" value="${risk.severity}">
        <span>${Math.round(risk.severity * 100)}%</span></label>
      <div class="grid-2" style="gap:18px;margin-top:6px">
        <div><h4 class="mini-h">Biggest hits</h4><ul class="pnl-list">${hits.map(itemRow).join('')}</ul>
          ${cushions.length ? `<h4 class="mini-h" style="margin-top:12px">What cushions it</h4><ul class="pnl-list">${cushions.map(itemRow).join('')}</ul>` : ''}</div>
        <div><h4 class="mini-h">By sector</h4>
          ${sectors.map(([s, v]) => `<div class="div-bar"><span class="div-label">${esc(s)}</span>
            <span class="div-track"><span class="div-fill ${v < 0 ? 'neg' : 'pos'}" style="width:${(Math.abs(v) / maxAbs * 50).toFixed(1)}%"></span></span>
            <span class="div-val" style="color:${signCol(v, 1)}">${fmtSGbp(v)}</span></div>`).join('')}</div>
      </div>
      <details class="assumptions"><summary>Assumptions behind this scenario</summary>
        <div><b>Market</b> <span class="chip" style="color:${signCol(sc.market, 0.01)}">all equities ${sc.market}%</span></div>
        <div><b>Sectors</b> ${chips(sc.sectors)}</div>
        <div><b>Countries</b> ${chips(sc.countries) || '<span class="muted">none</span>'}</div>
        <div><b>Themes</b> ${chips(sc.tags) || '<span class="muted">none</span>'}</div>
        <div><b>Commodities</b> ${chips(sc.commodities) || '<span class="muted">none</span>'}</div>
        <div><b>Currency vs GBP</b> ${chips(sc.fx) || '<span class="muted">none</span>'}</div>
        <p class="note" style="margin-top:6px">Each company's move is market + its sector + its country + its themes, then converted to GBP.
          All terms are multiplied by the severity. The figures are judgement calls sized to the named analogues, not forecasts.
          They are edited in SCENARIOS in reference.py.</p>
      </details>`;
    document.getElementById('scen-severity').addEventListener('input', ev => {
      risk.severity = parseFloat(ev.target.value);
      ev.target.nextElementSibling.textContent = Math.round(risk.severity * 100) + '%';
      clearTimeout(drawScenarios._t);
      drawScenarios._t = setTimeout(drawScenarios, 120);
    });
  } else {
    const ep = e.ep;
    detail.innerHTML = `
      <h3 style="font-size:16px">${esc(ep.name)}</h3>
      <p class="muted" style="font-size:12px">${fmtDate(ep.start)} – ${fmtDate(ep.end)}, peak to trough of the global sell-off</p>
      <div class="impact-row">
        ${impact('Your portfolio', fmtSPct(ep.portfolio.return), `${fmtSGbp(ep.portfolio.return / 100 * grandTotal)} on today's value`, signCol(ep.portfolio.return))}
        ${impact(esc(bn), fmtSPct(ep.benchmark.return), `deepest point ${fmtPct(ep.benchmark.max_drawdown)}`, signCol(ep.benchmark.return))}
        ${impact('Difference', (diff >= 0 ? '+' : '') + diff.toFixed(1) + ' pp', `your deepest point ${fmtPct(ep.portfolio.max_drawdown)}`, signCol(diff))}
      </div>
      <div class="chart-box" style="height:260px"><canvas id="chart-scen-path"></canvas></div>
      <p class="note" style="margin-top:8px">${ep.portfolio.coverage < 99.5
        ? `${fmtPct(ep.portfolio.coverage, 0)} of today's portfolio was trading at the time; the rest is re-weighted out, so read this as an approximation.`
        : 'Every holding was trading over this window.'}</p>`;
    const labels = ep.portfolio.path.map(p => p[0]);
    const bmap = Object.fromEntries(ep.benchmark.path.map(p => [p[0], p[1]]));
    charts['chart-scen-path'] = new Chart(document.getElementById('chart-scen-path'), {type: 'line',
      data: {labels, datasets: [
        {label: 'Your portfolio', data: ep.portfolio.path.map(p => p[1]), borderColor: accent, pointRadius: 0, borderWidth: 1.8},
        {label: bn, data: labels.map(l => bmap[l] ?? null), borderColor: cssVar('--muted'), pointRadius: 0, borderWidth: 1.6, spanGaps: true}]},
      options: {responsive: true, maintainAspectRatio: false, interaction: {mode: 'index', intersect: false},
        plugins: {legend: {position: 'top', align: 'end', labels: {boxWidth: 10, boxHeight: 2, font: {size: 11}}},
                  tooltip: {callbacks: {label: c => ` ${c.dataset.label}  ${fmtSPct(c.parsed.y - 100)}`}}},
        scales: {x: {ticks: {maxTicksLimit: 6, maxRotation: 0}, grid: {display: false}},
                 y: {ticks: {callback: v => fmtSPct(v - 100, 0)}, grid: {color: cssVar('--line')}}}}});
  }
}

function initRiskControls(){
  const opts = Object.entries(BENCHMARKS).map(([k, b]) => `<option value="${k}"${k === risk.bench ? ' selected' : ''}>${esc(b.name)}</option>`).join('');
  document.querySelectorAll('.bench-select').forEach(sel => { sel.innerHTML = opts; });
  document.querySelectorAll('#risk-years button').forEach(b => {
    b.classList.toggle('active', +b.dataset.y === risk.years);
    b.addEventListener('click', () => {
      risk.years = +b.dataset.y;
      document.querySelectorAll('#risk-years button').forEach(x => x.classList.toggle('active', x === b));
      onRiskControls();
    });
  });
  document.querySelectorAll('#scen-mode button').forEach(b => b.addEventListener('click', () => {
    risk.mode = b.dataset.m;
    document.querySelectorAll('#scen-mode button').forEach(x => x.classList.toggle('active', x === b));
    drawScenarios();
  }));
  document.getElementById('scen-list').addEventListener('click', ev => {
    const it = ev.target.closest('.scen-item');
    if(!it) return;
    risk.sel[risk.mode] = it.dataset.key;
    drawScenarios();
  });
}
initRiskControls();

// ─── Wiring ──────────────────────────────────────────────────────────────────
let expFilter = 'all';
document.querySelectorAll('#exp-filter button').forEach(b => b.addEventListener('click', () => {
  expFilter = b.dataset.f;
  document.querySelectorAll('#exp-filter button').forEach(x => x.classList.toggle('active', x === b));
  renderExposure();
}));

document.getElementById('country-table').addEventListener('click', e => {
  const tr = e.target.closest('.ctry-row');
  if(!tr) return;
  const c = tr.dataset.country;
  openCountries.has(c) ? openCountries.delete(c) : openCountries.add(c);
  renderCountries();
});

// 1–5 switch tabs, / jumps to the exposure filter, Esc closes a dialog.
document.addEventListener('keydown', e => {
  if(e.key === 'Escape'){ closeEdit(); closeEditStocks(); return; }
  if(e.metaKey || e.ctrlKey || e.altKey || e.target.matches('input, textarea, select')) return;
  if(document.querySelector('.overlay.open')) return;
  const i = '12345'.indexOf(e.key);
  if(i >= 0 && e.key.length === 1){ e.preventDefault(); switchTab(TABS[i]); }
  else if(e.key === '/'){ e.preventDefault(); switchTab('exposure'); document.getElementById('exp-search').focus(); }
});
window.addEventListener('hashchange', () => switchTab(location.hash.slice(1)));

// ─── Init ─────────────────────────────────────────────────────────────────────
try {
  countryScaled = localStorage.getItem('ctryScale') === '1';
  document.getElementById('ctry-scale').checked = countryScaled;
} catch(e){}
(() => {
  let saved = null;
  try { saved = localStorage.getItem('tab'); } catch(e){}
  activeTab = TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : (TABS.includes(saved) ? saved : 'portfolio');
})();
load();

