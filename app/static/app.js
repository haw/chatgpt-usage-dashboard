const fmt = new Intl.NumberFormat('ja-JP');
const formatOptional = value => value == null ? '—' : fmt.format(value);
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const products = ['chat', 'codex', 'work'];
const colors = {chat:'#176b4d', codex:'#3478a4', work:'#d49a31'};
let availablePeriod = {start_date:null, end_date:null};
let detectorLabels = {};
let currentAlerts = [];
let currentDaily = [];
let previousSignalState = null;  // {label, dates:Set} from the last render, for the "what changed" line
let individualLoaded = false;
let currentIndividualData = null;
const DEFAULT_LIMITS = {fiveHour:26300000, weekly:173000000};
const LIMIT_SETTINGS_KEY = 'chatgpt-dashboard.limit-settings.v1';
let limitSettings = loadLimitSettings();
const DAY_OVERRIDES_KEY = 'chatgpt-dashboard.day-overrides.v1';
const SENSITIVITY_KEY = 'chatgpt-dashboard.sensitivity.v1';
// Five steps only: the analyst needs a feel for "more / less", not a number.
const SENSITIVITY_STEPS = [
  {value:0.5, label:'低'}, {value:0.7, label:'やや低'}, {value:1, label:'標準'}, {value:1.4, label:'やや高'}, {value:2, label:'高'},
];
const sensitivityIndex = value => SENSITIVITY_STEPS.reduce((best, step, index) =>
  Math.abs(step.value - value) < Math.abs(SENSITIVITY_STEPS[best].value - value) ? index : best, 0);
const sensitivityLabel = value => SENSITIVITY_STEPS[sensitivityIndex(value)].label;
let sensitivity = loadSensitivity();
let dayOverrides = loadDayOverrides();
let currentPeriod = {start:null, end:null};

function loadSensitivity() {
  try {
    const saved = Number(localStorage.getItem(SENSITIVITY_KEY));
    if (saved >= 0.25 && saved <= 4) return SENSITIVITY_STEPS[sensitivityIndex(saved)].value;
  } catch (_) {}
  return 1;
}

function renderSensitivity() {
  document.querySelector('#sensitivity-slider').value = sensitivityIndex(sensitivity);
  document.querySelector('#sensitivity-value').textContent = `判定: 標準偏差×${(3.5 / sensitivity).toFixed(sensitivity === 2 ? 2 : 1).replace(/\.0$/, '')}`;
}

function loadDayOverrides() {
  try {
    const saved = JSON.parse(localStorage.getItem(DAY_OVERRIDES_KEY));
    if (saved && typeof saved === 'object') return Object.fromEntries(Object.entries(saved).filter(([date, kind]) => /^\d{4}-\d{2}-\d{2}$/.test(date) && ['holiday', 'workday'].includes(kind)));
  } catch (_) {}
  return {};
}

function persistDayOverrides() {
  try { localStorage.setItem(DAY_OVERRIDES_KEY, JSON.stringify(dayOverrides)); return true; }
  catch (_) { setMessage('休日・平日の設定をブラウザへ保存できませんでした。', 'error'); return false; }
}

// Viewer-specific holiday/workday overrides travel with every request as query or form fields.
function withDayOverrides(target) {
  if (sensitivity !== 1) target.set('sensitivity', String(sensitivity));
  const holidays = Object.keys(dayOverrides).filter(date => dayOverrides[date] === 'holiday').sort().join(',');
  const workdays = Object.keys(dayOverrides).filter(date => dayOverrides[date] === 'workday').sort().join(',');
  if (holidays) target.set('holidays', holidays);
  if (workdays) target.set('workdays', workdays);
  return target;
}

function toggleDayOverride(date, autoKind) {
  if (dayOverrides[date]) delete dayOverrides[date];
  else dayOverrides[date] = autoKind === 'holiday' ? 'workday' : 'holiday';
  persistDayOverrides();
  renderDayOverrideList();
  reloadAll();
}

function reloadAll() {
  load(currentPeriod.start, currentPeriod.end);
  loadTriage();
  if (individualLoaded) loadIndividual(currentIndividualData?.selected_user?.user_id);
}

async function load(start, end) {
  try {
    currentPeriod = {start:start || null, end:end || null};
    const query = withDayOverrides(new URLSearchParams());
    if (start) query.set('start_date', start);
    if (end) query.set('end_date', end);
    const response = await fetch(`/api/dashboard${query.size ? `?${query}` : ''}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    render(data);
  } catch (error) {
    setMessage(`読み込みに失敗しました: ${error.message}`, 'error');
  }
}

const workspaceFiles = document.querySelector('#workspace-json-files');
const workspaceImportButton = document.querySelector('#workspace-import-button');
workspaceImportButton.addEventListener('click', () => workspaceFiles.click());
workspaceFiles.addEventListener('change', async () => {
  const files = Array.from(workspaceFiles.files || []);
  if (!files.length) return;
  if (files.length > 2) {
    setImportMessage('一度に選べるJSONは2ファイルまでです。', 'error');
    workspaceFiles.value = '';
    return;
  }
  const button = workspaceImportButton;
  button.disabled = true;
  button.textContent = '取込中…';
  setImportMessage('JSONの形式を検証しています。', '');
  try {
    const body = withDayOverrides(new FormData());
    files.forEach(file => body.append('files', file));
    const response = await fetch('/api/import', {method:'POST', body});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    render(data);
    loadTriage();
    setImportMessage(`${data.state.imported_days}日分を取り込みました。「インサイト」を更新しました。`, 'success');
  } catch (error) {
    setImportMessage(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'アップロードして分析';
    workspaceFiles.value = '';
  }
});

const TABS = ['triage', 'workspace', 'individual', 'settings'];
function showTab(tab) {
  document.querySelectorAll('.tab-button').forEach(item => {
    const active = item.dataset.tab === tab;
    item.classList.toggle('active', active);
    item.setAttribute('aria-selected', String(active));
  });
  TABS.forEach(name => { document.querySelector(`#${name}-tab`).hidden = name !== tab; });
  if (tab === 'individual' && !individualLoaded) loadIndividual();
  window.scrollTo({top:0});
}
document.querySelectorAll('.tab-button').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tab)));
document.querySelector('#kpi-triage').addEventListener('click', () => showTab('triage'));

document.querySelector('#individual-upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  button.textContent = '取込中…';
  setIndividualMessage('JSONの形式を検証しています。', '');
  try {
    const response = await fetch('/api/individual/import', {method:'POST', body:withDayOverrides(new FormData(event.currentTarget))});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    individualLoaded = true;
    renderIndividual(data);
    setIndividualMessage(`${data.selected_user.user_label} の${data.state.imported_days}日分を取り込みました。`, 'success');
  } catch (error) {
    setIndividualMessage(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'アップロードして分析';
  }
});

document.querySelector('#individual-user-select').addEventListener('change', event => loadIndividual(event.target.value));
document.querySelector('#settings-button').addEventListener('click', openLimitSettings);
document.querySelector('#quota-settings-shortcut').addEventListener('click', openLimitSettings);
document.querySelector('#settings-close').addEventListener('click', () => document.querySelector('#settings-dialog').close());
document.querySelector('#limit-settings-form').addEventListener('submit', event => {
  event.preventDefault();
  const fiveHour = Number(document.querySelector('#five-hour-limit').value);
  const weekly = Number(document.querySelector('#weekly-limit').value);
  if (!Number.isSafeInteger(fiveHour) || fiveHour < 1 || !Number.isSafeInteger(weekly) || weekly < 1) {
    setSettingsMessage('上限は1以上の整数で指定してください。', 'error');
    return;
  }
  limitSettings = {fiveHour, weekly};
  if (persistLimitSettings()) setSettingsMessage('このブラウザに保存しました。', 'success');
  if (currentIndividualData) renderIndividualLimitViews(currentIndividualData.daily);
});
document.querySelector('#settings-reset').addEventListener('click', () => {
  limitSettings = {...DEFAULT_LIMITS};
  const saved = persistLimitSettings();
  fillLimitSettings();
  if (saved) setSettingsMessage('初期値にリセットして保存しました。', 'success');
  if (currentIndividualData) renderIndividualLimitViews(currentIndividualData.daily);
});

document.querySelector('#reset-range').addEventListener('click', () => load());
let sensitivityTimer = null;
document.querySelector('#sensitivity-slider').addEventListener('input', event => {
  const next = SENSITIVITY_STEPS[Number(event.target.value)].value;
  if (next === sensitivity) return;
  previousSignalState = {label:sensitivityLabel(sensitivity), dates:signalDates(currentAlerts), alerts:currentAlerts};
  sensitivity = next;
  renderSensitivity();
  try { localStorage.setItem(SENSITIVITY_KEY, String(sensitivity)); } catch (_) {}
  clearTimeout(sensitivityTimer);
  sensitivityTimer = setTimeout(() => {
    load(currentPeriod.start, currentPeriod.end);
    if (individualLoaded) loadIndividual(currentIndividualData?.selected_user?.user_id);
  }, 250);
});
document.querySelector('#history-button').addEventListener('click', openHistory);
document.querySelector('#history-close').addEventListener('click', () => document.querySelector('#history-dialog').close());
async function handleHashCopy(event) {
  const button = event.target.closest('.hash-copy');
  if (!button) return;
  await copyText(button.dataset.hash);
  button.classList.add('copied');
  clearTimeout(button.copyTimer);
  button.copyTimer = setTimeout(() => button.classList.remove('copied'), 1600);
}
document.querySelector('#history-table').addEventListener('click', handleHashCopy);
document.querySelector('#individual-history-table').addEventListener('click', handleHashCopy);
function render(data) {
  const state = data.state || {};
  availablePeriod = data.available_period || availablePeriod;
  const selected = data.selected_period || {};
  document.querySelector('#reset-range').disabled = !selected.start_date || (
    selected.start_date === availablePeriod.start_date && selected.end_date === availablePeriod.end_date
  );
  document.querySelector('#dau').textContent = formatOptional(data.kpis.latest_max_product_dau);
  document.querySelector('#total').textContent = formatOptional(data.kpis.total_tokens);
  document.querySelector('#average').textContent = formatOptional(data.kpis.daily_average_tokens);
  document.querySelector('#period').textContent = selected.start_date ? `${selected.start_date} – ${selected.end_date}` : 'データなし';
  document.querySelector('#updated').textContent = state.completed_at ? `最終取込 ${new Date(state.completed_at).toLocaleString('ja-JP')}` : '未取込';
  renderLineChart('#dau-chart', data.daily, 'active_users');
  renderLineChart('#token-chart', data.daily, 'tokens');
  renderAnalysisChart(data.analysis || [], '#analysis-chart', `${selected.start_date !== availablePeriod.start_date || selected.end_date !== availablePeriod.end_date ? '選択期間全体の中央値とMAD' : '全期間の直前最大7日（最低5日）'}から計算`);
  detectorLabels = Object.fromEntries((data.detectors || []).map(d => [d.id, d.label]));
  currentDaily = data.daily || [];
  renderDetectorErrors(data.detector_errors || []);
  renderDetectorList(data.detectors || []);
  renderDayOverrideList();
  document.querySelector('#pending-note').textContent = data.pending_days ? `判定保留 ${fmt.format(data.pending_days)}日（同じ区分の基準データが不足）` : '';
  renderAlerts(data.alerts);
  renderTable(data.daily, data.alerts);
}

function renderDetectorList(detectors) {
  const el = document.querySelector('#detector-list');
  el.innerHTML = detectors.map(d => `<article class="detector"><b>${esc(d.label)}</b><small class="muted">${esc(d.id)}${d.group === 'operations' ? '・取込状態として表示' : ''}</small><p>${esc(d.description)}</p><small class="muted">${Object.entries(d.params || {}).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(' · ')}</small></article>`).join('');
}

function renderDetectorErrors(errors) {
  const el = document.querySelector('#detector-errors');
  el.textContent = errors.length ? `検知器の設定に問題があります:\n${errors.join('\n')}` : '';
  el.className = errors.length ? 'message error' : 'message hidden';
}

async function loadIndividual(userId) {
  try {
    const query = withDayOverrides(new URLSearchParams());
    if (userId) query.set('user_id', userId);
    const response = await fetch(`/api/individual${query.size ? `?${query}` : ''}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    individualLoaded = true;
    renderIndividual(data);
  } catch (error) {
    setIndividualMessage(`読み込みに失敗しました: ${error.message}`, 'error');
  }
}

function renderIndividual(data) {
  currentIndividualData = data;
  const select = document.querySelector('#individual-user-select');
  const selectedId = data.selected_user?.user_id || '';
  select.disabled = !data.users.length;
  select.innerHTML = data.users.length ? data.users.map(user =>
    `<option value="${esc(user.user_id)}"${user.user_id === selectedId ? ' selected' : ''}>${esc(user.user_label)}（${fmt.format(user.total_tokens)} tokens）</option>`
  ).join('') : '<option value="">データがありません</option>';
  document.querySelector('#individual-total').textContent = fmt.format(data.kpis.total_tokens);
  document.querySelector('#individual-average').textContent = fmt.format(data.kpis.daily_average_tokens);
  document.querySelector('#individual-latest').textContent = fmt.format(data.kpis.latest_tokens);
  document.querySelector('#individual-alert-count').textContent = fmt.format(data.kpis.alerts);
  renderLineChart('#individual-token-chart', data.daily, 'tokens', false);
  renderAnalysisChart(data.analysis || [], '#individual-analysis-chart', '各日の直前最大7日（最低5日）から計算');
  renderIndividualLimitViews(data.daily);
}

function loadLimitSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(LIMIT_SETTINGS_KEY));
    if (Number.isSafeInteger(saved?.fiveHour) && saved.fiveHour > 0 && Number.isSafeInteger(saved?.weekly) && saved.weekly > 0) return saved;
  } catch (_) {}
  return {...DEFAULT_LIMITS};
}

function persistLimitSettings() {
  try { localStorage.setItem(LIMIT_SETTINGS_KEY, JSON.stringify(limitSettings)); return true; }
  catch (_) { setSettingsMessage('ブラウザへ保存できませんでした。', 'error'); return false; }
}

function fillLimitSettings() {
  document.querySelector('#five-hour-limit').value = limitSettings.fiveHour;
  document.querySelector('#weekly-limit').value = limitSettings.weekly;
}

function renderDayOverrideList() {
  const el = document.querySelector('#day-override-list');
  const dates = Object.keys(dayOverrides).sort();
  if (!dates.length) { el.innerHTML = '<li class="muted">手動設定はありません。</li>'; return; }
  el.innerHTML = dates.map(date => `<li><span>${esc(date)} ${weekday(date)}</span><span class="day-kind ${esc(dayOverrides[date])}">${dayOverrides[date] === 'holiday' ? '休日' : '平日'}</span><button type="button" class="day-override-remove" data-date="${esc(date)}">解除</button></li>`).join('');
}

function openLimitSettings() {
  fillLimitSettings();
  setSettingsMessage('', 'hidden');
  document.querySelector('#settings-dialog').showModal();
}

function weekStart(date) {
  const value = new Date(`${date}T00:00:00Z`);
  const offset = (value.getUTCDay() + 6) % 7;
  value.setUTCDate(value.getUTCDate() - offset);
  return value.toISOString().slice(0, 10);
}

function buildWeeklyRows(rows) {
  const grouped = new Map();
  rows.forEach(row => {
    const start = weekStart(row.date);
    const current = grouped.get(start) || {start, chat:0, codex:0, work:0, total:0};
    products.forEach(product => current[product] += row.tokens[product]);
    current.total += row.tokens.total;
    grouped.set(start, current);
  });
  return [...grouped.values()].sort((a, b) => a.start.localeCompare(b.start)).map(row => {
    const end = new Date(`${row.start}T00:00:00Z`);
    end.setUTCDate(end.getUTCDate() + 6);
    return {...row, end:end.toISOString().slice(0, 10), agentTokens:row.codex + row.work};
  });
}

function limitInfo(value, limit) {
  const ratio = value / limit * 100;
  const hits = Math.floor(value / limit);
  if (hits > 0) return {ratio, css:'reached', label:`${fmt.format(hits)}回相当`};
  if (ratio >= 80) return {ratio, css:'near', label:'80%以上'};
  return {ratio, css:'normal', label:'未到達目安'};
}

function limitCells(value, limit) {
  const info = limitInfo(value, limit);
  return `<td><span class="limit-ratio">${new Intl.NumberFormat('ja-JP',{maximumFractionDigits:1}).format(info.ratio)}%</span><small class="limit-detail">上限 ${fmt.format(limit)}</small></td><td><span class="limit-status ${info.css}">${info.label}</span></td>`;
}

function renderIndividualLimitViews(rows) {
  renderIndividualTable(rows);
  renderIndividualWeeklyTable(rows);
  renderQuotaEstimate(rows);
}

function renderQuotaEstimate(rows) {
  let fiveHourHits = 0;
  rows.forEach(row => {
    const agentTokens = row.tokens.codex + row.tokens.work;
    fiveHourHits += Math.floor(agentTokens / limitSettings.fiveHour);
  });
  const weeks = buildWeeklyRows(rows).map(row => row.agentTokens);
  const weeklyHits = weeks.reduce((sum, value) => sum + Math.floor(value / limitSettings.weekly), 0);
  const pressureWeeks = weeks.filter(value => value >= limitSettings.weekly * .8).length;
  const maxWeeklyRatio = weeks.length ? Math.max(...weeks) / limitSettings.weekly : 0;
  let level = '低', css = 'support-low', reason = '参考上限の80%未満です';
  if (weeklyHits > 0 || fiveHourHits >= 2) {
    level = '高'; css = 'support-high'; reason = '利用枠へ繰り返し接近・到達した可能性があります';
  } else if (fiveHourHits > 0 || pressureWeeks > 0 || maxWeeklyRatio >= .6) {
    level = '中'; css = 'support-medium'; reason = '利用枠へ接近した可能性があります';
  }
  document.querySelector('#individual-five-hour-hits').textContent = `${fmt.format(fiveHourHits)}回相当`;
  document.querySelector('#individual-weekly-hits').textContent = `${fmt.format(weeklyHits)}回相当`;
  document.querySelector('#individual-five-hour-detail').textContent = `参考上限 ${fmt.format(limitSettings.fiveHour)} tokens`;
  document.querySelector('#individual-weekly-detail').textContent = `${pressureWeeks}週が80%以上・上限 ${fmt.format(limitSettings.weekly)}`;
  const levelEl = document.querySelector('#individual-support-level');
  levelEl.textContent = rows.length ? level : '—';
  levelEl.className = css;
  document.querySelector('#individual-support-reason').textContent = rows.length ? reason : 'データ取込後に判定';
}

function renderAnalysisChart(rows, selector = '#analysis-chart', hint = null) {
  const el = document.querySelector(selector);
  if (!rows.length) {
    el.className = 'chart empty';
    el.textContent = '指定期間にデータがありません';
    return;
  }
  el.className = 'chart line-chart analysis-chart';
  const width = 1000, height = 280, left = 64, right = 18, top = 18, bottom = 42;
  const plotWidth = width-left-right, plotHeight = height-top-bottom;
  const samples = rows.flatMap(row => [row.value, row.baseline, row.threshold]).filter(value => value !== null);
  const max = Math.max(1, ...samples);
  const x = index => left + (rows.length === 1 ? plotWidth/2 : index*plotWidth/(rows.length-1));
  const y = value => top + plotHeight - value/max*plotHeight;
  const grid = [0,.25,.5,.75,1].map(part => {
    const gy = top + plotHeight*(1-part);
    return `<line x1="${left}" y1="${gy}" x2="${width-right}" y2="${gy}" class="grid-line"/><text x="${left-8}" y="${gy+4}" class="axis-label" text-anchor="end">${compact(max*part)}</text>`;
  }).join('');
  const path = (field, css) => {
    const points = rows.map((row,index) => row[field] === null ? null : `${x(index)},${y(row[field])}`);
    const segments = []; let current = [];
    points.forEach(point => { if (point) current.push(point); else if (current.length) { segments.push(current); current=[]; } });
    if (current.length) segments.push(current);
    return segments.map(segment => `<polyline points="${segment.join(' ')}" class="${css}" fill="none" vector-effect="non-scaling-stroke"/>`).join('');
  };
  const actualDots = rows.map((row,index) => `<circle cx="${x(index)}" cy="${y(row.value)}" r="${row.is_anomaly?6:row.is_notable?4.5:3}" class="${row.is_anomaly?'analysis-anomaly':row.is_notable?'analysis-notable':'analysis-dot'}"><title>${row.date}${row.kind==='holiday'?'（休日）':''} 実測: ${fmt.format(row.value)}${row.baseline === null?'（判定保留: 同じ区分の基準不足）':` / 中央値: ${fmt.format(row.baseline)} / 判定ライン: ${fmt.format(row.threshold)}`}</title></circle>`).join('');
  const labelStep = Math.max(1, Math.ceil(rows.length/10));
  const labels = rows.map((row,index) => index%labelStep===0 || index===rows.length-1 ? `<text x="${x(index)}" y="${height-14}" class="axis-label${row.kind==='holiday'?' holiday':''}" text-anchor="middle">${row.date.slice(5)}</text>` : '').join('');
  const narrowed = selector === '#analysis-chart' && availablePeriod.start_date && rows.length && (rows[0].date !== availablePeriod.start_date || rows.at(-1).date !== availablePeriod.end_date);
  const description = hint || `${narrowed?'選択期間全体の中央値とMAD':'全期間の直前最大7日（最低5日）'}から計算`;
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="総トークン異常分析グラフ">${grid}${path('threshold','analysis-threshold-line')}${path('baseline','analysis-baseline-line')}${path('value','analysis-actual-line')}${actualDots}${labels}</svg><small class="drag-hint">${description}</small>`;
}

function renderLineChart(selector, rows, key, rangeEnabled = true) {
  const el = document.querySelector(selector);
  if (!rows.some(row => row[key] != null)) {
    el.className = 'chart empty';
    el.textContent = '指定期間にデータがありません';
    return;
  }
  el.className = 'chart line-chart';
  const width = 1000, height = 260, left = 64, right = 18, top = 18, bottom = 42;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const max = Math.max(1, ...rows.filter(row => row[key] != null).flatMap(row => products.map(product => row[key][product])));
  const x = index => left + (rows.length === 1 ? plotWidth / 2 : index * plotWidth / (rows.length - 1));
  const y = value => top + plotHeight - value / max * plotHeight;
  const grid = [0, .25, .5, .75, 1].map(part => {
    const gy = top + plotHeight * (1 - part);
    return `<line x1="${left}" y1="${gy}" x2="${width-right}" y2="${gy}" class="grid-line"/><text x="${left-8}" y="${gy+4}" class="axis-label" text-anchor="end">${compact(max*part)}</text>`;
  }).join('');
  const series = products.map(product => {
    const path = rows.map((row,index) => row[key] == null ? '' :
      `${index === 0 || rows[index-1][key] == null ? 'M' : 'L'} ${x(index)},${y(row[key][product])}`).join(' ');
    const dots = rows.map((row,index) => row[key] == null ? '' : `<circle cx="${x(index)}" cy="${y(row[key][product])}" r="3" fill="${colors[product]}"><title>${row.date} ${product.toUpperCase()}: ${fmt.format(row[key][product])}</title></circle>`).join('');
    return `<path d="${path}" fill="none" stroke="${colors[product]}" stroke-width="3" vector-effect="non-scaling-stroke"/>${dots}`;
  }).join('');
  const labelStep = Math.max(1, Math.ceil(rows.length / 10));
  const labels = rows.map((row,index) => index % labelStep === 0 || index === rows.length-1 ? `<text x="${x(index)}" y="${height-14}" class="axis-label${row.day_kind==='holiday'?' holiday':''}" text-anchor="middle">${row.date.slice(5)}</text>` : '').join('');
  const rangeLayer = rangeEnabled ? `<rect class="drag-selection" x="0" y="${top}" width="0" height="${plotHeight}"/><rect class="drag-surface" x="${left}" y="${top}" width="${plotWidth}" height="${plotHeight}" fill="transparent"/>` : '';
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="製品別の折れ線グラフ">${grid}${series}${labels}${rangeLayer}</svg>${rangeEnabled?'<small class="drag-hint">グラフ上を横にドラッグして分析期間を選択</small>':''}`;
  if (rangeEnabled) enableRangeDrag(el.querySelector('svg'), rows, left, plotWidth);
}

function enableRangeDrag(svg, rows, left, plotWidth) {
  const surface = svg.querySelector('.drag-surface');
  const selection = svg.querySelector('.drag-selection');
  let startX = null;
  const svgX = event => {
    const rect = svg.getBoundingClientRect();
    return Math.max(left, Math.min(left + plotWidth, (event.clientX - rect.left) / rect.width * 1000));
  };
  surface.addEventListener('pointerdown', event => {
    startX = svgX(event);
    surface.setPointerCapture(event.pointerId);
    selection.setAttribute('x', startX);
    selection.setAttribute('width', 0);
  });
  surface.addEventListener('pointermove', event => {
    if (startX === null) return;
    const current = svgX(event);
    selection.setAttribute('x', Math.min(startX, current));
    selection.setAttribute('width', Math.abs(current - startX));
  });
  surface.addEventListener('pointerup', event => {
    if (startX === null) return;
    const endX = svgX(event);
    const toIndex = value => Math.max(0, Math.min(rows.length-1, Math.round((value-left)/plotWidth*(rows.length-1))));
    const from = Math.min(toIndex(startX), toIndex(endX));
    const to = Math.max(toIndex(startX), toIndex(endX));
    startX = null;
    load(rows[from].date, rows[to].date);
  });
}

function compact(value) { return new Intl.NumberFormat('ja-JP', {notation:'compact', maximumFractionDigits:1}).format(value); }
async function openHistory(){const dialog=document.querySelector('#history-dialog');const table=document.querySelector('#history-table');const individualTable=document.querySelector('#individual-history-table');table.innerHTML='<tr><td colspan="5" class="empty">読み込み中</td></tr>';individualTable.innerHTML='<tr><td colspan="5" class="empty">読み込み中</td></tr>';dialog.showModal();try{const [overallResponse,individualResponse]=await Promise.all([fetch('/api/imports'),fetch('/api/individual/imports')]);const overall=await overallResponse.json();const individual=await individualResponse.json();if(!overallResponse.ok)throw new Error(overall.detail||`HTTP ${overallResponse.status}`);if(!individualResponse.ok)throw new Error(individual.detail||`HTTP ${individualResponse.status}`);renderHistory(overall.imports||[]);renderIndividualHistory(individual.imports||[])}catch(error){const message=`<tr><td colspan="5" class="empty">履歴を読み込めません: ${esc(error.message)}</td></tr>`;table.innerHTML=message;individualTable.innerHTML=message}}
function renderHistory(rows){const table=document.querySelector('#history-table');if(!rows.length){table.innerHTML='<tr><td colspan="5" class="empty">保存されたJSON履歴はありません</td></tr>';return}table.innerHTML=rows.map((row,index)=>`<tr><td>${new Date(row.imported_at).toLocaleString('ja-JP')}${index===0?' <span class="latest-badge">最新</span>':''}</td><td>${esc(row.start_date||'—')} – ${esc(row.end_date||'—')}</td><td>${fmt.format(row.days)}日</td><td>${historyFile(row.active_users_bytes,row.active_users_sha256)}</td><td>${historyFile(row.tokens_bytes,row.tokens_sha256)}</td></tr>`).join('')}
function renderIndividualHistory(rows){const table=document.querySelector('#individual-history-table');if(!rows.length){table.innerHTML='<tr><td colspan="5" class="empty">保存された個人JSON履歴はありません</td></tr>';return}table.innerHTML=rows.map((row,index)=>`<tr><td>${new Date(row.imported_at).toLocaleString('ja-JP')}${index===0?' <span class="latest-badge">最新</span>':''}</td><td>${esc(row.user_label)}</td><td>${esc(row.start_date||'—')} – ${esc(row.end_date||'—')}</td><td>${fmt.format(row.days)}日</td><td>${historyFile(row.bytes,row.sha256)}</td></tr>`).join('')}
function fileSize(bytes){if(bytes<1024)return `${fmt.format(bytes)} B`;return `${new Intl.NumberFormat('ja-JP',{maximumFractionDigits:1}).format(bytes/1024)} KiB`}
function historyFile(bytes,hash){if(bytes == null || !hash)return '—';const short=`${hash.slice(0,12)}…${hash.slice(-12)}`;return `<span class="file-size">${fileSize(bytes)}</span><button type="button" class="hash-copy" data-hash="${esc(hash)}" aria-label="SHA-256をコピー" title="${esc(hash)}"><code>${short}</code><span class="material-icons copy-icon" aria-hidden="true">content_copy</span><span class="copy-feedback" role="status">コピーしました</span></button>`}
async function copyText(value){if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(value);return}const area=document.createElement('textarea');area.value=value;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();document.execCommand('copy');area.remove()}
function weekday(date){const day=new Date(`${date}T00:00:00Z`).getUTCDay();const labels=['日','月','火','水','木','金','土'];const kind=day===0?'sun':day===6?'sat':'';return `<span class="weekday ${kind}">(${labels[day]})</span>`}
function dayKindCell(row){const kind=row.day_kind||'workday';const source=row.day_kind_source||'weekday';const sourceLabels={weekend:'週末',weekday:'暦',inferred:'推定',override:'手動'};const auto=source==='override'?(kind==='holiday'?'workday':'holiday'):kind;return `<td><button type="button" class="day-kind-toggle day-kind ${esc(kind)} ${esc(source)}" data-date="${esc(row.date)}" data-auto="${esc(source==='override'?auto:kind)}" title="クリックで${kind==='holiday'?'平日':'休日'}に切替（このブラウザだけに保存）">${kind==='holiday'?'休日':'平日'}<small>${sourceLabels[source]||esc(source)}</small></button></td>`}
// Dates with at least one non-info signal: the unit the analyst reasons about.
function signalDates(alerts){return new Set(alerts.filter(a=>a.severity!=='info').map(a=>a.date))}
function dateLabel(date){const d=new Date(`${date}T00:00:00Z`);return `${d.getUTCMonth()+1}/${d.getUTCDate()}（${['日','月','火','水','木','金','土'][d.getUTCDay()]}）`}
function kindOf(date){return (currentDaily.find(r=>r.date===date)||{}).day_kind||'workday'}
// Ratio to the median for intuition, plus the value the judgement actually uses (SD multiples) when it exists.
function sdText(score){return score==null?'':`・標準偏差×${Math.abs(score)>=10?Math.round(Math.abs(score)):Math.abs(score).toFixed(1)}`}
function ratioText(value,baseline,kind,score){if(baseline==null)return '';if(!baseline)return kind==='holiday'?'（休日なのに利用）':'（普段は利用なし）';const r=value/baseline;return `（普段 ${compact(baseline)} の ${r>=10?Math.round(r):r.toFixed(1)}倍${sdText(score)}）`}
function productName(product){return product?product.toUpperCase():'全製品'}
// One short sentence per signal: what, how much, compared with what.
function signalSentence(a,kind=kindOf(a.date)){switch(a.type){
  case 'token_spike':case 'token_notable':return `${productName(a.product)}のトークン ${compact(a.value)}${ratioText(a.value,a.baseline,kind,a.score)}`;
  case 'tokens_per_user_spike':case 'tokens_per_user_notable':return `1人あたり${productName(a.product)} ${compact(a.value)}${ratioText(a.value,a.baseline,kind,a.score)}`;
  case 'dau_spike':case 'dau_spike_notable':return `${productName(a.product)}のDAU ${fmt.format(a.value)}人（普段 ${fmt.format(a.baseline)}人${sdText(a.score)}）`;
  case 'dau_drop':case 'dau_drop_notable':return `${productName(a.product)}のDAU ${fmt.format(a.value)}人に減少（普段 ${fmt.format(a.baseline)}人${sdText(a.score)}）`;
  case 'dau_new_max':return `${productName(a.product)}の利用者 ${fmt.format(a.value)}人は直前28日で最多（これまでの最多 ${fmt.format(a.baseline)}人、+${fmt.format(a.value-a.baseline)}人）`;
  case 'holiday_usage':return `休日なのに平日並みの利用 ${compact(a.value)}（平日の ${Math.round(a.value/a.baseline*100)}%）`;
  case 'stale_data':return a.reason;
  default:return `${detectorLabels[a.detector]||a.type}: ${a.reason}`}}
function signalBadge(date,alerts){const rows=alerts.filter(a=>a.date===date);if(!rows.length)return '<td></td>';const rank={high:0,medium:1,info:2};const top=rows.reduce((best,row)=>rank[row.severity]<rank[best]?row.severity:best,'info');return `<td><span class="signal-badge severity ${esc(top)}" title="${esc(rows.map(signalSentence).join('\n'))}">${rows.length}</span></td>`}
// The list under the anomaly chart shows every day detected at the current
// sensitivity and why; after a change, newly detected days are highlighted.
function strongest(list){const rank={high:0,medium:1,info:2};return [...list].sort((x,y)=>rank[x.severity]-rank[y.severity]||((y.value/(y.baseline||1))-(x.value/(x.baseline||1))))[0]}
function renderDelta(alerts){const el=document.querySelector('#signal-delta');const current=signalDates(alerts);const state=previousSignalState;previousSignalState=null;const changed=state&&state.label!==sensitivityLabel(sensitivity);const added=new Set(changed?[...current].filter(d=>!state.dates.has(d)):[]);const dropped=changed?[...state.dates].filter(d=>!current.has(d)).length:0;if(!current.size){el.className='signal-delta hidden';return added}
const items=[...current].sort().reverse().map(d=>{const strong=alerts.filter(x=>x.date===d&&x.severity!=='info');const a=strongest(strong);return `<li class="${added.has(d)?'added':''}"><b>${dateLabel(d)}</b> ${esc(signalSentence(a))}${a.threshold!=null?` <small class="muted">判定ライン ${compact(a.threshold)}</small>`:''}${strong.length>1?` <small class="muted">ほか${strong.length-1}件</small>`:''}${added.has(d)?'<span class="tag-new">新たに検出</span>':''}</li>`});
const title=changed?`感度を ${esc(state.label)} → ${esc(sensitivityLabel(sensitivity))} に変更: 検出 ${current.size}日${added.size?`（<span class="tag-new">新たに ${added.size}日</span>）`:dropped?`（${dropped}日減）`:'（変化なし）'}`:`現在の判定で検出された日: ${current.size}日`;
el.innerHTML=`<p class="delta-title">${title}</p><ul>${items.join('')}</ul>`;el.className='signal-delta';return added}
function renderAlerts(rows){currentAlerts=rows;renderDelta(rows)}
function renderTable(rows,alerts=[]){const el=document.querySelector('#daily-table');if(!rows.length){el.innerHTML='<tr><td colspan="10" class="empty">指定期間にデータがありません</td></tr>';return}el.innerHTML=[...rows].reverse().map(row=>`<tr class="${row.day_kind==='holiday'?'holiday-row':''}"><td>${esc(row.date)} ${weekday(row.date)}</td>${dayKindCell(row)}${signalBadge(row.date,alerts)}${products.map(p=>`<td>${formatOptional(row.active_users?.[p])}</td>`).join('')}${products.map(p=>`<td>${formatOptional(row.tokens?.[p])}</td>`).join('')}<td><strong>${formatOptional(row.tokens?.total)}</strong></td></tr>`).join('')}
function renderIndividualTable(rows){const el=document.querySelector('#individual-daily-table');if(!rows.length){el.innerHTML='<tr><td colspan="8" class="empty">データがありません</td></tr>';return}el.innerHTML=[...rows].reverse().map(row=>{const agentTokens=row.tokens.codex+row.tokens.work;return `<tr><td>${esc(row.date)} ${weekday(row.date)}</td>${products.map(p=>`<td>${formatOptional(row.tokens?.[p])}</td>`).join('')}<td><strong>${formatOptional(row.tokens?.total)}</strong></td><td>${fmt.format(agentTokens)}</td>${limitCells(agentTokens,limitSettings.fiveHour)}</tr>`}).join('')}
function renderIndividualWeeklyTable(rows){const el=document.querySelector('#individual-weekly-table');const weeks=buildWeeklyRows(rows);if(!weeks.length){el.innerHTML='<tr><td colspan="8" class="empty">データがありません</td></tr>';return}el.innerHTML=[...weeks].reverse().map(row=>`<tr><td>${esc(row.start)} – ${esc(row.end)}</td>${products.map(p=>`<td>${fmt.format(row[p])}</td>`).join('')}<td><strong>${fmt.format(row.total)}</strong></td><td>${fmt.format(row.agentTokens)}</td>${limitCells(row.agentTokens,limitSettings.weekly)}</tr>`).join('')}
function setImportMessage(text,kind){const el=document.querySelector('#import-message');el.textContent=text;el.className=`message ${kind}`}
function setMessage(text,kind){const el=document.querySelector('#message');el.textContent=text;el.className=`message ${kind}`}
function setIndividualMessage(text,kind){const el=document.querySelector('#individual-message');el.textContent=text;el.className=`message ${kind}`}
function setSettingsMessage(text,kind){const el=document.querySelector('#settings-message');el.textContent=text;el.className=`message ${kind}`}
// ---- インサイト (triage) ----
const TIER_LABELS = {today:'優先', week:'次に', reference:'参考'};

async function loadTriage() {
  try {
    const query = withDayOverrides(new URLSearchParams());
    query.delete('sensitivity');
    const response = await fetch(`/api/triage${query.size ? `?${query}` : ''}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    renderTriage(data);
  } catch (error) {
    document.querySelector('#triage-status').textContent = `読み込みに失敗しました: ${error.message}`;
  }
}

function renderTriage(data) {
  const status = data.status || {};
  triageEntries = new Map([...(data.today || []), ...(data.week || []), ...(data.reference || [])].map(e => [e.date, e]));
  const statusEl = document.querySelector('#triage-status');
  if (!status.latest_date) {
    statusEl.textContent = 'データがありません。「取込と設定」からJSONを取り込んでください。';
  } else {
    statusEl.innerHTML = `最終データ日 <strong>${dateLabel(status.latest_date)}</strong>（${status.age_days}日前）· 保存 ${fmt.format(status.stored_days)}日分 · 基準: ${esc(status.baseline)}${status.pending_days ? ` · 判定保留 ${status.pending_days}日` : ''}`;
  }
  const stale = document.querySelector('#triage-stale');
  stale.textContent = status.stale ? `取込が止まっています: ${status.stale_reason}` : '';
  stale.className = status.stale ? 'message error' : 'message hidden';
  const errors = document.querySelector('#triage-errors');
  errors.textContent = (data.detector_errors || []).length ? `判定の設定に問題があります: ${data.detector_errors.join(' / ')}` : '';
  errors.className = (data.detector_errors || []).length ? 'message error' : 'message hidden';
  const reset = document.querySelector('#checked-reset');
  reset.hidden = !status.checked_days;
  reset.textContent = status.checked_days ? `確認済み ${status.checked_days}日をすべて解除` : '';
  const kpi = document.querySelector('#alert-count');
  kpi.textContent = status.latest_date ? fmt.format((data.today || []).length) : '—';
  document.querySelector('#alert-detail').textContent = status.latest_date
    ? `${(data.week || []).length ? `次に ${(data.week || []).length}日 · ` : ''}${status.stale ? '取込が止まっています · ' : ''}クリックで一覧へ`
    : 'データ取込後に判定';
  document.querySelector('#kpi-triage').classList.toggle('all-clear', !!status.latest_date && !(data.today || []).length);
  renderTriageList('today', data.today || [], status.latest_date ? '優先して確認する日はありません' : '');
  renderTriageList('week', data.week || [], '次に確認する日はありません');
  renderTriageList('reference', data.reference || [], '参考の日はありません');
}

function renderTriageList(tier, entries, emptyText) {
  const el = document.querySelector(`#triage-${tier}`);
  document.querySelector(`#triage-${tier}-count`).textContent = entries.length ? `${entries.length}日` : '';
  if (!entries.length) { el.className = `triage-list empty${tier === 'today' ? ' all-clear' : ''}`; el.textContent = emptyText; return; }
  el.className = 'triage-list';
  el.innerHTML = entries.map(entry => renderTriageEntry(entry)).join('');
}

function renderTriageEntry(entry) {
  const f = entry.facts || {};
  const kind = f.kind === 'holiday' ? `休日${f.kind_source === 'inferred' ? '（推定）' : f.kind_source === 'override' ? '（手動）' : ''}` : '平日';
  const facts = [kind, f.max_dau != null ? `DAU ${fmt.format(f.max_dau)}` : null, f.total_tokens != null ? `${compact(f.total_tokens)} tokens` : null].filter(Boolean);
  const change = entry.continuing ? `継続${entry.streak}日目` : entry.novel ? '初めてのパターン' : (entry.streak > 1 ? `${entry.streak}日目` : 'この日から');
  const strong = entry.observations.filter(o => o.severity !== 'info');
  const info = entry.observations.filter(o => o.severity === 'info');
  const line = o => `<li class="sev-${esc(o.severity)}" title="${esc(detectorLabels[o.detector] || o.detector)}">${esc(signalSentence(o, f.kind))}${o.threshold != null && o.detector !== 'dau_increase' ? `<small class="muted">判定ライン ${compact(o.threshold)}</small>` : ''}${o.streak > 1 ? `<small class="muted">${o.streak}日連続</small>` : ''}</li>`;
  const checked = !!entry.disposition;
  const checkedText = checked ? `<span class="checked-mark">確認済み <small class="muted">${new Date(entry.disposition.recorded_at).toLocaleDateString('ja-JP')}</small></span>` : '';
  return `<article class="triage-entry tier-${esc(entry.tier)}" data-date="${esc(entry.date)}">
    <header><span class="tier-badge ${esc(entry.tier)}">${TIER_LABELS[entry.tier]}</span><strong class="triage-date">${dateLabel(entry.date)}</strong><span class="triage-facts">${facts.map(esc).join(' · ')}</span><span class="triage-change">${esc(change)}</span><span class="triage-count">${strong.length ? `${entry.detectors}つの観点` : '参考のみ'}</span></header>
    <ul class="triage-observations">${strong.map(line).join('')}</ul>
    ${info.length ? `<details class="triage-info"><summary>参考 ${info.length}件</summary><ul class="triage-observations">${info.map(line).join('')}</ul></details>` : ''}
    <div class="triage-actions">${checkedText}<button type="button" class="check-button" data-date="${esc(entry.date)}" data-kind="${checked ? 'cleared' : 'checked'}">${checked ? '未確認に戻す' : '確認済みにする'}</button><button type="button" class="inspect-button" data-date="${esc(entry.date)}">グラフで見る</button></div>
  </article>`;
}

document.querySelector('#triage-tab').addEventListener('click', event => {
  const inspect = event.target.closest('.inspect-button');
  if (inspect) { openContext(inspect.dataset.date); return; }
  const check = event.target.closest('.check-button');
  if (check) markDay(check.dataset.date, check.dataset.kind, check);
});

document.querySelector('#checked-reset').addEventListener('click', async event => {
  event.preventDefault();  // the button sits inside the <details> summary
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch('/api/dispositions/reset', {method:'POST'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    await loadTriage();
  } catch (error) {
    const el = document.querySelector('#triage-errors');
    el.textContent = `解除に失敗しました: ${error.message}`;
    el.className = 'message error';
  } finally {
    button.disabled = false;
  }
});

// ---- floating "how it crossed the line" charts ----
let triageEntries = new Map();
document.querySelector('#context-close').addEventListener('click', () => document.querySelector('#context-dialog').close());

function metricOf(signal, row) {
  const p = signal.product;
  switch (signal.detector) {
    case 'tokens_per_user': return row.tokens && row.active_users && row.active_users[p] ? row.tokens[p] / row.active_users[p] : null;
    case 'dau_change': case 'dau_increase': return row.active_users ? row.active_users[p] : null;
    case 'holiday_usage': return row.tokens ? row.tokens.total : null;
    default: return row.tokens ? row.tokens[p || 'total'] : null;
  }
}

async function openContext(date) {
  const entry = triageEntries.get(date);
  if (!entry) return;
  const dialog = document.querySelector('#context-dialog');
  document.querySelector('#context-title').textContent = `${dateLabel(date)} の判定`;
  const charts = document.querySelector('#context-charts');
  charts.innerHTML = '<p class="muted">読み込み中…</p>';
  dialog.showModal();
  try {
    const query = withDayOverrides(new URLSearchParams({date}));
    query.delete('sensitivity');
    const response = await fetch(`/api/context?${query}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    const strong = entry.observations.filter(o => o.severity !== 'info');
    const list = strong.length ? strong : entry.observations;
    charts.innerHTML = list.map(o => renderContextChart(o, data.rows, date, entry.facts.kind)).join('');
  } catch (error) {
    charts.innerHTML = `<p class="message error">読み込みに失敗しました: ${esc(error.message)}</p>`;
  }
}

function renderContextChart(signal, rows, date, kind) {
  const points = rows.map(row => ({date:row.date, value:metricOf(signal, row), kind:row.day_kind})).filter(p => p.value != null);
  if (!points.length) return '';
  const width = 640, height = 170, left = 56, right = 14, top = 14, bottom = 28;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const levels = [signal.baseline, signal.threshold].filter(v => v != null);
  const max = Math.max(1, ...points.map(p => p.value), ...levels) * 1.08;
  const x = i => left + (points.length === 1 ? plotWidth / 2 : i * plotWidth / (points.length - 1));
  const y = v => top + plotHeight - v / max * plotHeight;
  const sameKind = signal.detector === 'holiday_usage' ? 'workday' : kind;  // holiday_usage compares a holiday with workdays
  const dots = points.map((p, i) => {
    const isDay = p.date === date;
    const cls = isDay ? 'ctx-day' : p.kind === sameKind ? 'ctx-base' : 'ctx-other';
    return `<circle cx="${x(i)}" cy="${y(p.value)}" r="${isDay ? 6 : 3.5}" class="${cls}"><title>${p.date}${p.kind === 'holiday' ? '（休日）' : ''} ${fmt.format(Math.round(p.value))}</title></circle>`;
  }).join('');
  const line = (v, cls, label) => v == null ? '' : `<line x1="${left}" x2="${width - right}" y1="${y(v)}" y2="${y(v)}" class="${cls}"/><text x="${width - right}" y="${y(v) - 4}" text-anchor="end" class="axis-label">${label} ${compact(v)}</text>`;
  const step = Math.max(1, Math.ceil(points.length / 8));
  const labels = points.map((p, i) => i % step === 0 || p.date === date ? `<text x="${x(i)}" y="${height - 8}" text-anchor="middle" class="axis-label${p.date === date ? ' current' : ''}">${p.date.slice(5)}</text>` : '').join('');
  const title = `${detectorLabels[signal.detector] || signal.detector}${signal.product ? ` · ${signal.product.toUpperCase()}` : ''}`;
  const baseLabel = signal.detector === 'dau_increase' ? 'これまでの最多' : signal.detector === 'holiday_usage' ? '平日の中央値' : '中央値';
  return `<section class="context-chart"><h3>${esc(title)}</h3><p>${esc(signalSentence(signal, kind))}</p><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${line(signal.threshold, 'analysis-threshold-line', '判定ライン')}${line(signal.baseline, 'analysis-baseline-line', baseLabel)}${dots}${labels}</svg></section>`;
}

async function markDay(date, kind, button) {
  button.disabled = true;
  try {
    const response = await fetch('/api/dispositions', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({date, kind})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    await loadTriage();
  } catch (error) {
    const el = document.querySelector('#triage-errors');
    el.textContent = `記録に失敗しました: ${error.message}`;
    el.className = 'message error';
    button.disabled = false;
  }
}

renderSensitivity();
renderDayOverrideList();
load();
loadTriage();
