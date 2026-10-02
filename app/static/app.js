const fmt = new Intl.NumberFormat('ja-JP');
const formatOptional = value => value == null ? '—' : fmt.format(value);
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const products = ['chat', 'codex', 'work'];
const colors = {chat:'#176b4d', codex:'#3478a4', work:'#d49a31'};
let availablePeriod = {start_date:null, end_date:null};
const signalFilters = {};
const severityFilters = {high:true, medium:true, info:true};
let detectorLabels = {};
const serviceFilters = {overall:true, chat:true, codex:true, work:true};
let currentAlerts = [];
let individualLoaded = false;
let currentIndividualData = null;
const DEFAULT_LIMITS = {fiveHour:26300000, weekly:173000000};
const LIMIT_SETTINGS_KEY = 'chatgpt-dashboard.limit-settings.v1';
let limitSettings = loadLimitSettings();
const DAY_OVERRIDES_KEY = 'chatgpt-dashboard.day-overrides.v1';
let dayOverrides = loadDayOverrides();
let currentPeriod = {start:null, end:null};

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
  load(currentPeriod.start, currentPeriod.end);
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
    setMessage('一度に選べるJSONは2ファイルまでです。', 'error');
    workspaceFiles.value = '';
    return;
  }
  const button = workspaceImportButton;
  button.disabled = true;
  button.textContent = '取込中…';
  setMessage('JSONの形式を検証しています。', '');
  try {
    const body = withDayOverrides(new FormData());
    files.forEach(file => body.append('files', file));
    const response = await fetch('/api/import', {method:'POST', body});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    render(data);
    setMessage(`${data.state.imported_days}日分を取り込みました。`, 'success');
  } catch (error) {
    setMessage(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'アップロードして分析';
    workspaceFiles.value = '';
  }
});

document.querySelectorAll('.tab-button').forEach(button => button.addEventListener('click', () => {
  const tab = button.dataset.tab;
  document.querySelectorAll('.tab-button').forEach(item => {
    const active = item === button;
    item.classList.toggle('active', active);
    item.setAttribute('aria-selected', String(active));
  });
  document.querySelector('#workspace-tab').hidden = tab !== 'workspace';
  document.querySelector('#individual-tab').hidden = tab !== 'individual';
  if (tab === 'individual' && !individualLoaded) loadIndividual();
}));

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
document.querySelector('#daily-table').addEventListener('click', event => {
  const button = event.target.closest('.day-kind-toggle');
  if (button) toggleDayOverride(button.dataset.date, button.dataset.auto);
});
document.querySelector('#day-override-list').addEventListener('click', event => {
  const button = event.target.closest('.day-override-remove');
  if (!button) return;
  delete dayOverrides[button.dataset.date];
  persistDayOverrides();
  renderDayOverrideList();
  load(currentPeriod.start, currentPeriod.end);
  if (individualLoaded) loadIndividual(currentIndividualData?.selected_user?.user_id);
});
document.querySelector('#day-override-clear').addEventListener('click', () => {
  dayOverrides = {};
  persistDayOverrides();
  renderDayOverrideList();
  load(currentPeriod.start, currentPeriod.end);
  if (individualLoaded) loadIndividual(currentIndividualData?.selected_user?.user_id);
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
document.querySelector('#signal-filters').addEventListener('click', event => {
  const button = event.target.closest('.signal-toggle');
  if (!button) return;
  const signal = button.dataset.signal;
  signalFilters[signal] = !signalFilters[signal];
  button.classList.toggle('active', signalFilters[signal]);
  button.setAttribute('aria-pressed', String(signalFilters[signal]));
  renderAlerts(currentAlerts);
});
document.querySelectorAll('.severity-toggle').forEach(button => button.addEventListener('click', () => {
  const severity = button.dataset.severity;
  severityFilters[severity] = !severityFilters[severity];
  button.classList.toggle('active', severityFilters[severity]);
  button.setAttribute('aria-pressed', String(severityFilters[severity]));
  renderAlerts(currentAlerts);
}));
document.querySelectorAll('.service-toggle').forEach(button => button.addEventListener('click', () => {
  const service = button.dataset.service;
  serviceFilters[service] = !serviceFilters[service];
  button.classList.toggle('active', serviceFilters[service]);
  button.setAttribute('aria-pressed', String(serviceFilters[service]));
  renderAlerts(currentAlerts);
}));

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
  document.querySelector('#alert-count').textContent = fmt.format(data.kpis.alerts);
  document.querySelector('#period').textContent = selected.start_date ? `${selected.start_date} – ${selected.end_date}` : 'データなし';
  document.querySelector('#updated').textContent = state.completed_at ? `最終取込 ${new Date(state.completed_at).toLocaleString('ja-JP')}` : '未取込';
  renderLineChart('#dau-chart', data.daily, 'active_users');
  renderLineChart('#token-chart', data.daily, 'tokens');
  renderAnalysisChart(data.analysis || [], '#analysis-chart', `${selected.start_date !== availablePeriod.start_date || selected.end_date !== availablePeriod.end_date ? '選択期間全体の中央値とMAD' : '全期間の直前最大7日（最低5日）'}から計算`);
  renderSignalFilters(data.detectors || []);
  renderDetectorErrors(data.detector_errors || []);
  document.querySelector('#pending-note').textContent = data.pending_days ? `判定保留 ${fmt.format(data.pending_days)}日（同じ区分の基準データが不足）` : '';
  renderAlerts(data.alerts);
  renderTable(data.daily);
}

function renderSignalFilters(detectors) {
  const container = document.querySelector('#signal-filters');
  detectorLabels = Object.fromEntries(detectors.map(d => [d.id, d.label]));
  container.querySelectorAll('.signal-control').forEach(el => el.remove());
  detectors.filter(d => d.scopes.includes('workspace')).forEach(d => {
    if (!(d.id in signalFilters)) signalFilters[d.id] = true;
    const active = signalFilters[d.id];
    const params = Object.entries(d.params || {}).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(', ');
    container.insertAdjacentHTML('beforeend', `<span class="signal-control"><button type="button" class="signal-toggle${active ? ' active' : ''}" data-signal="${esc(d.id)}" aria-pressed="${active}">${esc(d.label)}</button><span class="help signal-help" tabindex="0" aria-label="${esc(d.label)}の判定条件">?<span class="help-content"><strong>${esc(d.label)}</strong><br>${esc(d.description)}${params ? `<br><small>設定: ${params}</small>` : ''}</span></span></span>`);
  });
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
  if (!dates.length) { el.innerHTML = '<li class="muted">手動設定はありません。日次データ表の区分をクリックすると切り替えられます。</li>'; return; }
  el.innerHTML = dates.map(date => `<li><span>${esc(date)} ${weekday(date)}</span><span class="day-kind ${esc(dayOverrides[date])}">${dayOverrides[date] === 'holiday' ? '休日' : '平日'}</span><button type="button" class="day-override-remove" data-date="${esc(date)}">解除</button></li>`).join('');
}

function openLimitSettings() {
  fillLimitSettings();
  renderDayOverrideList();
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
  const actualDots = rows.map((row,index) => `<circle cx="${x(index)}" cy="${y(row.value)}" r="${row.is_anomaly?6:3}" class="${row.is_anomaly?'analysis-anomaly':'analysis-dot'}"><title>${row.date}${row.kind==='holiday'?'（休日）':''} 実測: ${fmt.format(row.value)}${row.baseline === null?'（判定保留: 同じ区分の基準不足）':` / 中央値: ${fmt.format(row.baseline)} / 判定ライン: ${fmt.format(row.threshold)}`}</title></circle>`).join('');
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
function renderAlerts(rows){currentAlerts=rows;const el=document.querySelector('#alerts');if(!rows.length){el.className='empty';el.textContent='選択期間に異常兆候はありません';return}const visible=rows.filter(row=>{const signalVisible=signalFilters[row.detector]!==false;const service=row.product||'overall';return signalVisible&&severityFilters[row.severity]!==false&&serviceFilters[service]!==false});if(!visible.length){el.className='empty';el.textContent='選択中の条件に表示する異常兆候はありません';return}const severityLabels={high:'高',medium:'中',info:'参考'};el.className='alerts';el.innerHTML=visible.map(row=>`<article class="${esc(row.severity)}"><b><span class="severity ${esc(row.severity)}">${severityLabels[row.severity]||esc(row.severity)}</span>${esc(detectorLabels[row.detector]||row.type)}</b><strong>${esc(row.product?.toUpperCase()||'全製品')}</strong><span>${esc(row.date)}</span><span>${fmt.format(row.value)}${row.baseline!=null?`（基準 ${fmt.format(row.baseline)}）`:row.threshold!=null?`（判定 ${fmt.format(row.threshold)}）`:''}</span><small>${esc(row.reason)}</small></article>`).join('')}
function weekday(date){const day=new Date(`${date}T00:00:00Z`).getUTCDay();const labels=['日','月','火','水','木','金','土'];const kind=day===0?'sun':day===6?'sat':'';return `<span class="weekday ${kind}">(${labels[day]})</span>`}
function dayKindCell(row){const kind=row.day_kind||'workday';const source=row.day_kind_source||'weekday';const sourceLabels={weekend:'週末',weekday:'暦',inferred:'推定',override:'手動'};const auto=source==='override'?(kind==='holiday'?'workday':'holiday'):kind;return `<td><button type="button" class="day-kind-toggle day-kind ${esc(kind)} ${esc(source)}" data-date="${esc(row.date)}" data-auto="${esc(source==='override'?auto:kind)}" title="クリックで${kind==='holiday'?'平日':'休日'}に切替（このブラウザだけに保存）">${kind==='holiday'?'休日':'平日'}<small>${sourceLabels[source]||esc(source)}</small></button></td>`}
function renderTable(rows){const el=document.querySelector('#daily-table');if(!rows.length){el.innerHTML='<tr><td colspan="9" class="empty">指定期間にデータがありません</td></tr>';return}el.innerHTML=[...rows].reverse().map(row=>`<tr class="${row.day_kind==='holiday'?'holiday-row':''}"><td>${esc(row.date)} ${weekday(row.date)}</td>${dayKindCell(row)}${products.map(p=>`<td>${formatOptional(row.active_users?.[p])}</td>`).join('')}${products.map(p=>`<td>${formatOptional(row.tokens?.[p])}</td>`).join('')}<td><strong>${formatOptional(row.tokens?.total)}</strong></td></tr>`).join('')}
function renderIndividualTable(rows){const el=document.querySelector('#individual-daily-table');if(!rows.length){el.innerHTML='<tr><td colspan="8" class="empty">データがありません</td></tr>';return}el.innerHTML=[...rows].reverse().map(row=>{const agentTokens=row.tokens.codex+row.tokens.work;return `<tr><td>${esc(row.date)} ${weekday(row.date)}</td>${products.map(p=>`<td>${formatOptional(row.tokens?.[p])}</td>`).join('')}<td><strong>${formatOptional(row.tokens?.total)}</strong></td><td>${fmt.format(agentTokens)}</td>${limitCells(agentTokens,limitSettings.fiveHour)}</tr>`}).join('')}
function renderIndividualWeeklyTable(rows){const el=document.querySelector('#individual-weekly-table');const weeks=buildWeeklyRows(rows);if(!weeks.length){el.innerHTML='<tr><td colspan="8" class="empty">データがありません</td></tr>';return}el.innerHTML=[...weeks].reverse().map(row=>`<tr><td>${esc(row.start)} – ${esc(row.end)}</td>${products.map(p=>`<td>${fmt.format(row[p])}</td>`).join('')}<td><strong>${fmt.format(row.total)}</strong></td><td>${fmt.format(row.agentTokens)}</td>${limitCells(row.agentTokens,limitSettings.weekly)}</tr>`).join('')}
function setMessage(text,kind){const el=document.querySelector('#message');el.textContent=text;el.className=`message ${kind}`}
function setIndividualMessage(text,kind){const el=document.querySelector('#individual-message');el.textContent=text;el.className=`message ${kind}`}
function setSettingsMessage(text,kind){const el=document.querySelector('#settings-message');el.textContent=text;el.className=`message ${kind}`}
load();
