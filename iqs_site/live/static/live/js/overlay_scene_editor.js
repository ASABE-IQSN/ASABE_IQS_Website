"use strict";

// ── Available data bindings ───────────────────────────────────────────
const BINDINGS = [
  { value: '',           label: '(none – static content)' },
  // SSE / overlay fields
  { value: 'team_name',   label: 'Team Name' },
  { value: 'team_number', label: 'Team Number' },
  { value: 'hook_name',   label: 'Hook Name' },
  { value: 'distance',    label: 'Distance (ft)' },
  { value: 'speed',       label: 'Speed (ft/s)' },
  { value: 'force',       label: 'Force (lbf)' },
  { value: 'tractor_name',label: 'Tractor Name' },
  // Card slot roles
  { value: 'photo',  label: 'Photo (card)' },
  { value: 'name',   label: 'Name (card)' },
  { value: 'bio',    label: 'Bio (card)' },
  { value: 'stat_1', label: 'Stat 1 (card)' },
  { value: 'stat_2', label: 'Stat 2 (card)' },
  { value: 'caption',label: 'Caption (card)' },
];

// ── State ─────────────────────────────────────────────────────────────
let elements = [];
let selectedId = null;
let interaction = null; // { type:'drag'|'resize', handle, startMouse, startEl, canvasRect }
let saveTimer = null;
let idCounter = Date.now();

// ── DOM refs ──────────────────────────────────────────────────────────
const canvas      = document.getElementById('editorCanvas');
const canvasOuter = document.getElementById('canvasOuter');
const canvasArea  = document.getElementById('canvasArea');
const layerList   = document.getElementById('layerList');
const rightPanel  = document.getElementById('rightPanel');
const deleteBtn   = document.getElementById('deleteBtn');
const saveBtn     = document.getElementById('saveBtn');
const saveStatus  = document.getElementById('saveStatus');
const nameInput   = document.getElementById('sceneNameInput');

// Canvas logical size (from scene)
const REF_W = window.SCENE_DATA.canvas_width  || 1920;
const REF_H = window.SCENE_DATA.canvas_height || 1080;

// Scale factor: canvas displayed px / reference px
let scale = 1;

// ── Init ──────────────────────────────────────────────────────────────
function init() {
  elements = JSON.parse(JSON.stringify(window.SCENE_DATA.elements || []));
  fitCanvas();
  renderAll();
  setupListeners();
  window.addEventListener('resize', () => { fitCanvas(); renderAll(); });
}

// ── Canvas sizing ─────────────────────────────────────────────────────
function fitCanvas() {
  const area = canvasArea.getBoundingClientRect();
  const padding = 48;
  const maxW = area.width  - padding;
  const maxH = area.height - padding;
  const scaleW = maxW / REF_W;
  const scaleH = maxH / REF_H;
  scale = Math.min(scaleW, scaleH, 1); // never upscale beyond 1:1
  canvas.style.width  = (REF_W * scale) + 'px';
  canvas.style.height = (REF_H * scale) + 'px';
}

// ── Helpers ───────────────────────────────────────────────────────────
function getEl(id) { return elements.find(e => e.id === id) || null; }
function genId()   { return 'el_' + (++idCounter); }

function defaultStyle(type) {
  if (type === 'text') return {
    font_size: 2.2, font_weight: 700, color: '#ffffff',
    background: 'transparent', border_radius: 0, border: '',
    text_align: 'left', opacity: 1,
  };
  if (type === 'image') return {
    object_fit: 'cover', border_radius: 8, border: '',
    background: 'rgba(148,163,184,.1)', opacity: 1,
  };
  // rect
  return {
    background: 'rgba(15,23,42,0.85)', border_radius: 12,
    border: '1px solid rgba(148,163,184,.2)', opacity: 1,
    backdrop_filter: 'blur(10px)',
  };
}

// ── Render ────────────────────────────────────────────────────────────
function renderAll() {
  renderCanvas();
  renderLayerList();
  renderSidebar();
  deleteBtn.disabled = !selectedId;
  canvas.classList.toggle('empty', elements.length === 0);
}

function renderCanvas() {
  // Remove existing scene elements
  canvas.querySelectorAll('.scene-el').forEach(n => n.remove());

  for (const el of elements) {
    canvas.appendChild(buildElDiv(el));
  }
}

function buildElDiv(el) {
  const div = document.createElement('div');
  div.className = 'scene-el' + (el.id === selectedId ? ' selected' : '');
  div.dataset.id = el.id;
  div.style.left   = el.x + '%';
  div.style.top    = el.y + '%';
  div.style.width  = el.width + '%';
  div.style.height = el.height + '%';

  const s = el.style || {};

  // Common styles
  div.style.background   = s.background || 'transparent';
  div.style.borderRadius = (s.border_radius || 0) + 'px';
  div.style.border       = s.border || '';
  div.style.opacity      = s.opacity ?? 1;
  if (s.backdrop_filter) div.style.backdropFilter = s.backdrop_filter;

  if (el.type === 'text') {
    const fsPx = (s.font_size || 2) / 100 * REF_H * scale;
    div.style.fontSize   = fsPx + 'px';
    div.style.fontWeight = s.font_weight || 400;
    div.style.color      = s.color || '#ffffff';
    div.style.textAlign  = s.text_align || 'left';
    div.style.display    = 'flex';
    div.style.alignItems = 'center';
    div.style.padding    = '0 4px';
    div.style.overflow   = 'hidden';
    div.style.lineHeight = '1.3';
    div.style.whiteSpace = 'nowrap';
    div.style.userSelect = 'none';
    div.textContent = el.binding ? `[${el.binding}]` : (el.content || 'Text');
  } else if (el.type === 'image') {
    div.style.overflow = 'hidden';
    const placeholder = document.createElement('div');
    placeholder.style.cssText = 'width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:rgba(148,163,184,.5);font-size:12px;';
    placeholder.textContent = el.binding ? `[${el.binding}]` : '\u{1F5BC} Image';
    div.appendChild(placeholder);
  }
  // rect: just the styled div

  // Label (only when selected)
  if (el.id === selectedId) {
    const lbl = document.createElement('span');
    lbl.className = 'el-label';
    lbl.textContent = el.label || el.type;
    div.appendChild(lbl);

    // Resize handles
    ['nw','n','ne','e','se','s','sw','w'].forEach(h => {
      const handle = document.createElement('div');
      handle.className = `resize-handle resize-${h}`;
      handle.dataset.handle = h;
      div.appendChild(handle);
    });
  }

  div.addEventListener('pointerdown', onElPointerDown);
  return div;
}

function renderLayerList() {
  layerList.innerHTML = '';
  // Render in reverse (top layer first visually)
  for (let i = elements.length - 1; i >= 0; i--) {
    const el = elements[i];
    const item = document.createElement('div');
    item.className = 'layer-item' + (el.id === selectedId ? ' selected' : '');
    item.dataset.id = el.id;

    const badge = document.createElement('span');
    badge.className = `layer-type-badge badge-${el.type}`;
    badge.textContent = el.type[0].toUpperCase();

    const name = document.createElement('span');
    name.className = 'layer-name';
    name.textContent = el.label || el.type;

    const orderBtns = document.createElement('div');
    orderBtns.className = 'layer-order-btns';

    const upBtn = document.createElement('button');
    upBtn.className = 'layer-order-btn';
    upBtn.textContent = '\u25B2';
    upBtn.title = 'Move up';
    upBtn.addEventListener('click', (e) => { e.stopPropagation(); moveLayer(el.id, 1); });

    const dnBtn = document.createElement('button');
    dnBtn.className = 'layer-order-btn';
    dnBtn.textContent = '\u25BC';
    dnBtn.title = 'Move down';
    dnBtn.addEventListener('click', (e) => { e.stopPropagation(); moveLayer(el.id, -1); });

    orderBtns.appendChild(upBtn);
    orderBtns.appendChild(dnBtn);

    item.appendChild(badge);
    item.appendChild(name);
    item.appendChild(orderBtns);

    item.addEventListener('click', () => { selectedId = el.id; renderAll(); });
    layerList.appendChild(item);
  }
}

function renderSidebar() {
  if (!selectedId) {
    rightPanel.innerHTML = '<div class="no-selection">Select an element to edit its properties</div>';
    return;
  }
  const el = getEl(selectedId);
  if (!el) return;

  const s = el.style || {};

  const bindingOptions = BINDINGS.map(b =>
    `<option value="${b.value}"${el.binding === b.value ? ' selected' : ''}>${b.label}</option>`
  ).join('');

  const isText  = el.type === 'text';
  const isImage = el.type === 'image';

  rightPanel.innerHTML = `
    <div class="prop-group">
      <div class="prop-group-title">Element</div>
      <div class="prop-row full">
        <div>
          <label class="prop-label">Label</label>
          <input class="prop-input" id="pLabel" type="text" value="${esc(el.label || '')}">
        </div>
      </div>
      ${isText ? `
      <div class="prop-row full">
        <div>
          <label class="prop-label">Data Binding</label>
          <select class="prop-input" id="pBinding">${bindingOptions}</select>
        </div>
      </div>
      <div class="prop-row full" id="contentRow" style="${el.binding ? 'display:none' : ''}">
        <div>
          <label class="prop-label">Static Text</label>
          <input class="prop-input" id="pContent" type="text" value="${esc(el.content || '')}">
        </div>
      </div>
      ` : isImage ? `
      <div class="prop-row full">
        <div>
          <label class="prop-label">Data Binding (slot role)</label>
          <select class="prop-input" id="pBinding">${bindingOptions}</select>
        </div>
      </div>
      ` : ''}
    </div>

    <div class="prop-group">
      <div class="prop-group-title">Position &amp; Size</div>
      <div class="prop-row">
        <div><label class="prop-label">X (%)</label><input class="prop-input" id="pX" type="number" step="0.1" value="${el.x.toFixed(2)}"></div>
        <div><label class="prop-label">Y (%)</label><input class="prop-input" id="pY" type="number" step="0.1" value="${el.y.toFixed(2)}"></div>
      </div>
      <div class="prop-row">
        <div><label class="prop-label">Width (%)</label><input class="prop-input" id="pW" type="number" step="0.1" value="${el.width.toFixed(2)}"></div>
        <div><label class="prop-label">Height (%)</label><input class="prop-input" id="pH" type="number" step="0.1" value="${el.height.toFixed(2)}"></div>
      </div>
    </div>

    ${isText ? `
    <div class="prop-group">
      <div class="prop-group-title">Typography</div>
      <div class="prop-row">
        <div><label class="prop-label">Size (% canvas H)</label><input class="prop-input" id="pFontSize" type="number" step="0.1" min="0.5" value="${(s.font_size || 2).toFixed(1)}"></div>
        <div><label class="prop-label">Weight</label>
          <select class="prop-input" id="pFontWeight">
            ${[400,500,600,700,800,900].map(w=>`<option value="${w}"${(s.font_weight||400)==w?' selected':''}>${w}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="prop-row">
        <div><label class="prop-label">Align</label>
          <select class="prop-input" id="pTextAlign">
            ${['left','center','right'].map(a=>`<option value="${a}"${(s.text_align||'left')===a?' selected':''}>${a}</option>`).join('')}
          </select>
        </div>
        <div><label class="prop-label">Color</label>
          <div class="color-row">
            <input type="color" class="color-swatch" id="pColorSwatch" value="${toHex(s.color||'#ffffff')}">
            <input class="prop-input" id="pColor" type="text" value="${esc(s.color||'#ffffff')}">
          </div>
        </div>
      </div>
    </div>
    ` : ''}

    <div class="prop-group">
      <div class="prop-group-title">Appearance</div>
      ${!isText ? `
      <div class="prop-row full">
        <div><label class="prop-label">Background</label>
          <div class="color-row">
            <input type="color" class="color-swatch" id="pBgSwatch" value="${toHex(s.background||'transparent')}">
            <input class="prop-input" id="pBg" type="text" value="${esc(s.background||'transparent')}">
          </div>
        </div>
      </div>
      ` : ''}
      <div class="prop-row">
        <div><label class="prop-label">Border Radius</label><input class="prop-input" id="pRadius" type="number" step="1" min="0" value="${s.border_radius||0}"></div>
        <div><label class="prop-label">Opacity</label><input class="prop-input" id="pOpacity" type="number" step="0.05" min="0" max="1" value="${s.opacity??1}"></div>
      </div>
      <div class="prop-row full">
        <div><label class="prop-label">Border (CSS)</label><input class="prop-input" id="pBorder" type="text" value="${esc(s.border||'')}"></div>
      </div>
      ${!isText && !isImage ? `
      <div class="prop-row full">
        <div><label class="prop-label">Backdrop Filter</label><input class="prop-input" id="pBackdrop" type="text" placeholder="blur(10px)" value="${esc(s.backdrop_filter||'')}"></div>
      </div>
      ` : ''}
    </div>
  `;

  // Wire up sidebar inputs
  bindSidebarInputs(el, isText, isImage);
}

function bindSidebarInputs(el, isText, isImage) {
  const s = el.style;

  const get = id => document.getElementById(id);
  const on  = (id, ev, fn) => { const el = get(id); if (el) el.addEventListener(ev, fn); };

  on('pLabel',   'input', e => { el.label = e.target.value; renderLayerList(); });
  on('pX',       'input', e => { el.x = clamp(parseFloat(e.target.value)||0, 0, 99); updateElDiv(el); });
  on('pY',       'input', e => { el.y = clamp(parseFloat(e.target.value)||0, 0, 99); updateElDiv(el); });
  on('pW',       'input', e => { el.width  = clamp(parseFloat(e.target.value)||1, 1, 100); updateElDiv(el); });
  on('pH',       'input', e => { el.height = clamp(parseFloat(e.target.value)||1, 1, 100); updateElDiv(el); });
  on('pRadius',  'input', e => { s.border_radius = parseInt(e.target.value)||0; updateElDiv(el); });
  on('pOpacity', 'input', e => { s.opacity = clamp(parseFloat(e.target.value)||1, 0, 1); updateElDiv(el); });
  on('pBorder',  'input', e => { s.border = e.target.value; updateElDiv(el); });

  if (!isText) {
    on('pBg',      'input', e => { s.background = e.target.value; updateElDiv(el); if (get('pBgSwatch')) get('pBgSwatch').value = toHex(e.target.value); });
    on('pBgSwatch','input', e => { s.background = e.target.value; updateElDiv(el); if (get('pBg')) get('pBg').value = e.target.value; });
  }

  if (!isText && !isImage) {
    on('pBackdrop','input', e => { s.backdrop_filter = e.target.value; updateElDiv(el); });
  }

  if (isText) {
    on('pFontSize',  'input', e => { s.font_size   = parseFloat(e.target.value)||2; updateElDiv(el); });
    on('pFontWeight','change',e => { s.font_weight = parseInt(e.target.value);       updateElDiv(el); });
    on('pTextAlign', 'change',e => { s.text_align  = e.target.value;                 updateElDiv(el); });
    on('pColor',     'input', e => { s.color = e.target.value; updateElDiv(el); if (get('pColorSwatch')) get('pColorSwatch').value = toHex(e.target.value); });
    on('pColorSwatch','input',e => { s.color = e.target.value; updateElDiv(el); if (get('pColor')) get('pColor').value = e.target.value; });
    on('pBinding',   'change',e => {
      el.binding = e.target.value;
      const contentRow = document.getElementById('contentRow');
      if (contentRow) contentRow.style.display = el.binding ? 'none' : '';
      updateElDiv(el);
    });
    on('pContent',   'input', e => { el.content = e.target.value; updateElDiv(el); });
  }

  if (isImage) {
    on('pBinding','change', e => { el.binding = e.target.value; updateElDiv(el); });
  }
}

// Update a single element div without full re-render
function updateElDiv(el) {
  const existing = canvas.querySelector(`[data-id="${el.id}"]`);
  if (!existing) return;
  const fresh = buildElDiv(el);
  canvas.replaceChild(fresh, existing);
}

// ── Layer operations ──────────────────────────────────────────────────
function moveLayer(id, dir) {
  const idx = elements.findIndex(e => e.id === id);
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= elements.length) return;
  [elements[idx], elements[newIdx]] = [elements[newIdx], elements[idx]];
  renderAll();
}

// ── Add element ───────────────────────────────────────────────────────
function addElement(type) {
  const id = genId();
  const el = {
    id,
    type,
    label: type === 'rect' ? 'Rectangle' : type === 'image' ? 'Image' : 'Text',
    x: 5, y: 5,
    width:  type === 'rect' ? 40 : type === 'image' ? 20 : 30,
    height: type === 'rect' ? 20 : type === 'image' ? 25 : 8,
    binding: '',
    content: type === 'text' ? 'New Text' : '',
    style: defaultStyle(type),
  };
  elements.push(el);
  selectedId = id;
  renderAll();
}

// ── Delete ────────────────────────────────────────────────────────────
function deleteSelected() {
  if (!selectedId) return;
  elements = elements.filter(e => e.id !== selectedId);
  selectedId = null;
  renderAll();
}

// ── Pointer events ────────────────────────────────────────────────────
function onElPointerDown(e) {
  e.stopPropagation();
  const div = e.currentTarget;
  const id  = div.dataset.id;
  const handle = e.target.dataset?.handle || null;

  if (selectedId !== id && !handle) {
    selectedId = id;
    renderAll();
    return;
  }

  selectedId = id;
  if (selectedId !== id) renderAll();

  const el = getEl(id);
  if (!el) return;

  const rect = canvas.getBoundingClientRect();
  interaction = {
    type:       handle ? 'resize' : 'drag',
    handle,
    startMX:    e.clientX,
    startMY:    e.clientY,
    startX:     el.x,
    startY:     el.y,
    startW:     el.width,
    startH:     el.height,
    canvasW:    rect.width,
    canvasH:    rect.height,
  };

  canvas.setPointerCapture(e.pointerId);
  e.preventDefault();
}

canvas.addEventListener('pointermove', (e) => {
  if (!interaction || !selectedId) return;

  const el = getEl(selectedId);
  if (!el) return;

  const dx = (e.clientX - interaction.startMX) / interaction.canvasW * 100;
  const dy = (e.clientY - interaction.startMY) / interaction.canvasH * 100;
  const MIN = 2;

  if (interaction.type === 'drag') {
    el.x = Math.max(0, interaction.startX + dx);
    el.y = Math.max(0, interaction.startY + dy);
  } else {
    const h = interaction.handle;
    if (h.includes('e')) el.width  = Math.max(MIN, interaction.startW + dx);
    if (h.includes('s')) el.height = Math.max(MIN, interaction.startH + dy);
    if (h.includes('w')) {
      const nw = Math.max(MIN, interaction.startW - dx);
      el.x = interaction.startX + (interaction.startW - nw);
      el.width = nw;
    }
    if (h.includes('n')) {
      const nh = Math.max(MIN, interaction.startH - dy);
      el.y = interaction.startY + (interaction.startH - nh);
      el.height = nh;
    }
  }

  // Fast DOM update (no full re-render during drag)
  const div = canvas.querySelector(`[data-id="${selectedId}"]`);
  if (div) {
    div.style.left   = el.x + '%';
    div.style.top    = el.y + '%';
    div.style.width  = el.width + '%';
    div.style.height = el.height + '%';
  }
});

canvas.addEventListener('pointerup', () => {
  if (!interaction) return;
  interaction = null;
  // Sync sidebar position fields
  const el = getEl(selectedId);
  if (el) {
    const pX = document.getElementById('pX'); if (pX) pX.value = el.x.toFixed(2);
    const pY = document.getElementById('pY'); if (pY) pY.value = el.y.toFixed(2);
    const pW = document.getElementById('pW'); if (pW) pW.value = el.width.toFixed(2);
    const pH = document.getElementById('pH'); if (pH) pH.value = el.height.toFixed(2);
  }
});

canvas.addEventListener('pointerdown', (e) => {
  if (e.target === canvas) {
    selectedId = null;
    renderAll();
  }
});

// ── Save ──────────────────────────────────────────────────────────────
async function save() {
  saveStatus.textContent = 'Saving\u2026';
  saveBtn.disabled = true;
  try {
    const res = await fetch(window.SAVE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
      body: JSON.stringify({ name: nameInput.value.trim(), elements }),
    });
    if (!res.ok) throw new Error(res.status);
    saveStatus.textContent = 'Saved \u2713';
    setTimeout(() => { saveStatus.textContent = ''; }, 2500);
  } catch (_) {
    saveStatus.textContent = 'Error';
  }
  saveBtn.disabled = false;
}

// ── Listeners setup ───────────────────────────────────────────────────
function setupListeners() {
  document.querySelectorAll('[data-add]').forEach(btn => {
    btn.addEventListener('click', () => addElement(btn.dataset.add));
  });
  deleteBtn.addEventListener('click', deleteSelected);
  saveBtn.addEventListener('click', save);

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) deleteSelected();
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save(); }
  });
}

// ── Utilities ─────────────────────────────────────────────────────────
function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }
function toHex(color) {
  if (!color || color === 'transparent') return '#000000';
  if (color.startsWith('#') && (color.length === 4 || color.length === 7)) return color;
  // Try to parse rgb/rgba -> hex via canvas
  try {
    const c = document.createElement('canvas'); c.width = c.height = 1;
    const ctx = c.getContext('2d'); ctx.fillStyle = color; ctx.fillRect(0,0,1,1);
    const d = ctx.getImageData(0,0,1,1).data;
    return '#' + [d[0],d[1],d[2]].map(v=>v.toString(16).padStart(2,'0')).join('');
  } catch(_) { return '#000000'; }
}

// ── Boot ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
