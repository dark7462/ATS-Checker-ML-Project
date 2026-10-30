import { buildVisualData, cameraForKey, findClosestTarget, projectPoint } from './scene.mjs';
import { formatScore } from './score-format.mjs';

const $ = id => document.getElementById(id);
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const selected = { jd: null, resume: null };
let result = null;
let visual = null;
let activeTab = 'matches';
let loadingTimers = [];
let sceneFrame = 0;
let lastFrame = 0;
let sceneWidth = 0;
let sceneHeight = 0;
let screenTargets = [];
let sceneActive = false;
let motionPaused = reducedMotion;
const camera = { yaw: -0.48, pitch: -0.23, distance: 6.3, dragging: false, x: 0, y: 0 };
const canvas = $('sceneCanvas');
const ctx = canvas.getContext('2d');
const colors = { jd: '#335bff', resume: '#ef5a52', collision: '#a650d9' };

function setError(message) {
  $('formError').textContent = message || '';
  $('formError').hidden = !message;
}

function sizeLabel(bytes) {
  return bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function setFile(kind, file) {
  if (!file) return;
  selected[kind] = file;
  const name = kind === 'jd' ? 'jdName' : 'resumeName';
  const hint = kind === 'jd' ? 'jdHint' : 'resumeHint';
  const drop = kind === 'jd' ? 'jdDrop' : 'resumeDrop';
  $(name).textContent = file.name;
  $(hint).textContent = `${sizeLabel(file.size)} · ready to map`;
  $(drop).classList.add('has-file');
  $('analyzeButton').disabled = !selected.jd || !selected.resume;
  setError('');
}

function validateFiles() {
  if (!selected.jd || !selected.resume) return 'Upload both a JD and a resume first.';
  if (!selected.jd.name.toLowerCase().endsWith('.txt')) return 'The JD must be a .txt file.';
  if (!selected.resume.name.toLowerCase().endsWith('.pdf')) return 'The resume must be a PDF file.';
  if (selected.jd.size === 0 || selected.resume.size === 0) return 'One of the files is empty.';
  if (selected.jd.size > 250_000) return 'The JD is too large. Please use a file under 250 KB.';
  if (selected.resume.size > 5_000_000) return 'The resume is too large. Please use a file under 5 MB.';
  return '';
}

for (const [kind, inputId, dropId] of [['jd', 'jdInput', 'jdDrop'], ['resume', 'resumeInput', 'resumeDrop']]) {
  const input = $(inputId);
  const drop = $(dropId);
  input.addEventListener('change', () => setFile(kind, input.files[0]));
  drop.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); }
  });
  for (const eventName of ['dragenter', 'dragover']) {
    drop.addEventListener(eventName, event => { event.preventDefault(); drop.classList.add('is-over'); });
  }
  for (const eventName of ['dragleave', 'drop']) {
    drop.addEventListener(eventName, event => { event.preventDefault(); drop.classList.remove('is-over'); });
  }
  drop.addEventListener('drop', event => setFile(kind, event.dataTransfer?.files?.[0]));
}

function setLoading(value) {
  $('loadingOverlay').hidden = !value;
  $('analyzeButton').disabled = value || !selected.jd || !selected.resume;
  loadingTimers.forEach(clearTimeout);
  loadingTimers = [];
  if (value) {
    $('loadingText').textContent = 'Reading your files';
    loadingTimers.push(setTimeout(() => { $('loadingText').textContent = 'Placing skills in space'; }, 2300));
    loadingTimers.push(setTimeout(() => { $('loadingText').textContent = 'Measuring the overlap'; }, 5200));
  }
}

$('uploadForm').addEventListener('submit', async event => {
  event.preventDefault();
  const error = validateFiles();
  if (error) { setError(error); return; }
  const files = new FormData();
  files.append('jd', selected.jd, selected.jd.name);
  files.append('resume', selected.resume, selected.resume.name);
  setLoading(true);
  setError('');
  try {
    const response = await fetch('/api/analyze', { method: 'POST', body: files });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Could not analyze these files.');
    result = payload;
    visual = buildVisualData(result);
    renderResult();
    history.pushState({ page: 'results' }, '', '/results');
    showResults();
  } catch (cause) {
    setError(cause instanceof Error ? cause.message : 'Could not analyze these files.');
  } finally {
    setLoading(false);
  }
});

function showUpload(pushHistory = false) {
  sceneActive = false;
  cancelAnimationFrame(sceneFrame);
  $('uploadPage').hidden = false;
  $('resultsPage').hidden = true;
  $('newAnalysisTop').hidden = true;
  $('topStamp').hidden = false;
  $('pointTooltip').hidden = true;
  if (pushHistory) history.pushState({ page: 'upload' }, '', '/');
  window.scrollTo({ top: 0, behavior: reducedMotion ? 'instant' : 'smooth' });
}

function showResults() {
  if (!result) { showUpload(); return; }
  $('uploadPage').hidden = true;
  $('resultsPage').hidden = false;
  $('newAnalysisTop').hidden = false;
  $('topStamp').hidden = true;
  window.scrollTo({ top: 0, behavior: 'instant' });
  resizeScene();
  sceneActive = true;
  lastFrame = 0;
  cancelAnimationFrame(sceneFrame);
  sceneFrame = requestAnimationFrame(drawScene);
  animateScore(result.score);
}

function startNew() {
  result = null;
  visual = null;
  selected.jd = null;
  selected.resume = null;
  $('uploadForm').reset();
  for (const [drop, name, hint, mainText, subText] of [
    ['jdDrop', 'jdName', 'jdHint', 'Drop your JD here', 'or click to browse · .txt · max 250 KB'],
    ['resumeDrop', 'resumeName', 'resumeHint', 'Drop your resume here', 'or click to browse · selectable PDF · max 5 MB'],
  ]) {
    $(drop).classList.remove('has-file');
    $(name).textContent = mainText;
    $(hint).textContent = subText;
  }
  $('analyzeButton').disabled = true;
  setError('');
  showUpload(true);
}

$('newAnalysis').addEventListener('click', startNew);
$('newAnalysisTop').addEventListener('click', startNew);
$('brandLink').addEventListener('click', event => { event.preventDefault(); startNew(); });
window.addEventListener('popstate', () => {
  if (location.pathname === '/results' && result) showResults();
  else {
    if (location.pathname === '/results') history.replaceState({ page: 'upload' }, '', '/');
    showUpload();
  }
});
if (location.pathname === '/results') history.replaceState({ page: 'upload' }, '', '/');

function animateScore(target) {
  const output = $('scoreNumber');
  const meter = $('scoreFill');
  const display = formatScore(target);
  output.parentElement.classList.toggle('compact', display.length >= 5);
  meter.style.width = '0%';
  if (reducedMotion) { output.textContent = display; meter.style.width = `${target}%`; return; }
  const start = performance.now();
  const duration = 1150;
  function tick(now) {
    if ($('resultsPage').hidden) return;
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    output.textContent = progress === 1 ? display : String(Math.round(target * eased));
    if (progress < 1) requestAnimationFrame(tick);
    else meter.style.width = `${target}%`;
  }
  requestAnimationFrame(tick);
}

function renderResult() {
  $('matchedCount').textContent = `${result.matched.length} MATCHED`;
  $('totalCount').textContent = `${result.total} JD SKILLS`;
  $('matchTabCount').textContent = result.matched.length;
  $('missingTabCount').textContent = result.unmatched.length;
  $('scoreExplain').textContent = `${result.points.toFixed(2)} of ${result.total} possible skill points · full-vector cosine scoring`;
  activeTab = 'matches';
  updateTabs();
}

function updateTabs() {
  const matchTab = $('matchesTab');
  const missingTab = $('missingTab');
  matchTab.classList.toggle('active', activeTab === 'matches');
  missingTab.classList.toggle('active', activeTab === 'missing');
  matchTab.setAttribute('aria-selected', activeTab === 'matches');
  missingTab.setAttribute('aria-selected', activeTab === 'missing');
  const list = $('skillList');
  list.replaceChildren();
  const rows = activeTab === 'matches' ? result.matched : result.unmatched;
  if (!rows.length) {
    const empty = document.createElement('div');
    empty.className = 'skill-empty';
    empty.textContent = activeTab === 'matches' ? 'No skill pairs crossed the matching threshold.' : 'Every extracted JD skill found a match.';
    list.append(empty);
    return;
  }
  rows.forEach((row, index) => {
    const item = document.createElement('div');
    item.className = `skill-row${activeTab === 'missing' ? ' missing' : ''}`;
    item.style.animationDelay = `${Math.min(index, 8) * 45}ms`;
    const pair = document.createElement('div');
    pair.className = 'skill-pair';
    const left = document.createElement('span');
    left.textContent = activeTab === 'matches' ? row.jd : row;
    pair.append(left);
    if (activeTab === 'matches') {
      const arrow = document.createElement('i'); arrow.textContent = '↔';
      const right = document.createElement('span'); right.textContent = row.resume;
      pair.append(arrow, right);
    }
    const chip = document.createElement('span');
    chip.className = 'skill-chip';
    chip.textContent = activeTab === 'matches' ? `+${row.credit.toFixed(2)} PT` : 'NO PAIR';
    item.append(pair, chip);
    list.append(item);
  });
}

$('matchesTab').addEventListener('click', () => { activeTab = 'matches'; updateTabs(); });
$('missingTab').addEventListener('click', () => { activeTab = 'missing'; updateTabs(); });

function resizeScene() {
  const bounds = $('canvasWrap').getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  sceneWidth = Math.max(1, bounds.width);
  sceneHeight = Math.max(1, bounds.height);
  canvas.width = Math.round(sceneWidth * dpr);
  canvas.height = Math.round(sceneHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

new ResizeObserver(() => { if (!$('resultsPage').hidden) resizeScene(); }).observe($('canvasWrap'));

function line3d(a, b, stroke, width = 1, dash = []) {
  const pa = projectPoint(a, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance);
  const pb = projectPoint(b, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance);
  ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y);
  ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.stroke(); ctx.setLineDash([]);
}

function drawGrid() {
  for (let step = -3; step <= 3; step += 0.5) {
    const strong = Number.isInteger(step);
    line3d([-3, -2.2, step], [3, -2.2, step], strong ? '#bfbacb58' : '#cbc6d431', strong ? 1 : 0.7);
    line3d([step, -2.2, -3], [step, -2.2, 3], strong ? '#bfbacb58' : '#cbc6d431', strong ? 1 : 0.7);
  }
  line3d([-3, 0, 0], [3, 0, 0], '#a8a2b57d', 1);
  line3d([0, -2.3, 0], [0, 2.8, 0], '#a8a2b57d', 1);
  line3d([0, 0, -3], [0, 0, 3], '#a8a2b57d', 1);
  for (const [position, label] of [[[3.1, 0, 0], 'X'], [[0, 2.9, 0], 'Y'], [[0, 0, 3.1], 'Z']]) {
    const p = projectPoint(position, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance);
    ctx.fillStyle = '#a49da9'; ctx.font = '700 10px monospace'; ctx.fillText(label, p.x, p.y);
  }
}

function circle(x, y, radius, color, glow = 0) {
  ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = color;
  if (glow) { ctx.shadowColor = color; ctx.shadowBlur = glow; }
  ctx.fill(); ctx.shadowBlur = 0;
}

function drawNode(node, kind, time) {
  const p = projectPoint(node.position, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance);
  const radius = Math.max(5.5, Math.min(11, p.scale * 0.085));
  const color = colors[kind];
  const pulse = reducedMotion || motionPaused ? 0 : Math.sin(time / 650 + p.x * 0.012) * 1.2;
  circle(p.x, p.y, radius + 7 + pulse, `${color}16`);
  circle(p.x, p.y, radius + pulse, color, 15);
  circle(p.x - radius * .24, p.y - radius * .27, Math.max(1.5, radius * .22), '#ffffffb0');
  screenTargets.push({ x: p.x, y: p.y, radius: radius + 12, text: `${kind === 'jd' ? 'JD' : 'RESUME'} · ${node.label}` });
}

function drawScene(time) {
  if (!sceneActive || !visual) return;
  const dt = lastFrame ? Math.min(time - lastFrame, 60) : 16;
  lastFrame = time;
  if (!camera.dragging && !motionPaused) camera.yaw += dt * 0.00022;
  ctx.clearRect(0, 0, sceneWidth, sceneHeight);
  screenTargets = [];

  // Quiet ambient particles keep the map alive without changing the data.
  for (let index = 0; index < 64; index++) {
    const x = ((index * 113.7) % 101) / 101 * sceneWidth;
    const y = ((index * 47.3) % 103) / 103 * sceneHeight;
    circle(x, y, index % 7 === 0 ? 1.5 : 1, '#b9b2c43b');
  }
  drawGrid();

  for (const pair of visual.collisions) {
    line3d(pair.jd.position, pair.resume.position, '#a650d98c', 2, [5, 5]);
  }
  const dots = [
    ...visual.jd.map(node => ({ node, kind: 'jd' })),
    ...visual.resume.map(node => ({ node, kind: 'resume' })),
  ];
  dots.sort((a, b) => projectPoint(b.node.position, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance).depth - projectPoint(a.node.position, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance).depth);
  for (const dot of dots) drawNode(dot.node, dot.kind, time);
  for (const pair of visual.collisions) {
    const p = projectPoint(pair.position, sceneWidth, sceneHeight, camera.yaw, camera.pitch, camera.distance);
    const pulse = reducedMotion || motionPaused ? 0 : Math.sin(time / 380) * 3;
    circle(p.x, p.y, 13 + pulse, '#a650d91b');
    circle(p.x, p.y, 7 + pulse * .18, colors.collision, 24);
    circle(p.x, p.y, 2, '#fff');
    screenTargets.push({ x: p.x, y: p.y, radius: 18, text: `MATCH · ${pair.jd.label} ↔ ${pair.resume.label} · ${pair.credit.toFixed(2)} pt` });
  }
  sceneFrame = requestAnimationFrame(drawScene);
}

function showTooltip(event) {
  if (camera.dragging) { $('pointTooltip').hidden = true; return; }
  const bounds = canvas.getBoundingClientRect();
  const x = event.clientX - bounds.left;
  const y = event.clientY - bounds.top;
  const closest = findClosestTarget(screenTargets, x, y);
  const tooltip = $('pointTooltip');
  if (!closest) { tooltip.hidden = true; return; }
  tooltip.hidden = false;
  tooltip.textContent = closest.text;
  tooltip.style.left = `${Math.min(x, sceneWidth - 230)}px`;
  tooltip.style.top = `${Math.max(y, 36)}px`;
}

canvas.addEventListener('pointerdown', event => {
  camera.dragging = true; camera.x = event.clientX; camera.y = event.clientY;
  canvas.setPointerCapture(event.pointerId);
  $('pointTooltip').hidden = true;
});
canvas.addEventListener('pointermove', event => {
  if (camera.dragging) {
    camera.yaw += (event.clientX - camera.x) * 0.007;
    camera.pitch = Math.max(-1.25, Math.min(1.25, camera.pitch + (event.clientY - camera.y) * 0.007));
    camera.x = event.clientX; camera.y = event.clientY;
  } else showTooltip(event);
});
canvas.addEventListener('pointerup', () => { camera.dragging = false; });
canvas.addEventListener('pointercancel', () => { camera.dragging = false; });
canvas.addEventListener('pointerleave', () => { $('pointTooltip').hidden = true; });
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  camera.distance = Math.max(4.2, Math.min(10, camera.distance + Math.sign(event.deltaY) * .35));
}, { passive: false });
canvas.addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '_'].includes(event.key)) return;
  event.preventDefault();
  Object.assign(camera, cameraForKey(camera, event.key));
});

$('toggleMotion').addEventListener('click', () => {
  motionPaused = !motionPaused;
  $('toggleMotion').textContent = motionPaused ? '▶' : 'Ⅱ';
  $('toggleMotion').setAttribute('aria-label', motionPaused ? 'Resume rotation' : 'Pause rotation');
  $('toggleMotion').title = motionPaused ? 'Resume rotation' : 'Pause rotation';
});
$('resetView').addEventListener('click', () => {
  camera.yaw = -0.48; camera.pitch = -0.23; camera.distance = 6.3;
});
if (reducedMotion) {
  $('toggleMotion').textContent = '▶';
  $('toggleMotion').setAttribute('aria-label', 'Resume rotation');
  $('toggleMotion').title = 'Resume rotation';
}
