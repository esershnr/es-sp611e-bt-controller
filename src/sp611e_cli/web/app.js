/**
 * SP611E Neo Dashboard - Interactive Client Application
 */

// Application State
// effectId === null means the strip is in static (solid color) mode.
const state = {
  isPoweredOn: true,
  color: { hex: '#00F0FF', r: 0, g: 240, b: 255 },
  brightness: 255,
  effectId: null,
  speed: 8,
  activeMac: '',
};

/**
 * Coalescing sender: the SP611E accepts a single BLE connection and every
 * request costs 1-4 s, so while one request is in flight we only remember the
 * latest payload and send it once the current one finishes. Intermediate
 * values (slider drags, color-wheel sweeps) are dropped instead of queued.
 */
function createCoalescedSender(url, { onSuccess, onError }) {
  let inFlight = false;
  let pending = null;

  async function run(payload) {
    inFlight = true;
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (data.success) {
        onSuccess(data, payload);
      } else {
        onError(data.error || 'İşlem başarısız.', payload);
      }
    } catch (err) {
      onError('Sunucu ile iletişim hatası: ' + err.message, payload);
    } finally {
      inFlight = false;
      if (pending !== null) {
        const next = pending;
        pending = null;
        run(next);
      }
    }
  }

  return (payload) => {
    if (inFlight) {
      pending = payload;
    } else {
      run(payload);
    }
  };
}

// 16 Curated Neon & Natural Swatches
const PRESET_SWATCHES = [
  { name: 'Siber Kırmızı', hex: '#FF0055', r: 255, g: 0, b: 85 },
  { name: 'Neon Turuncu', hex: '#FF5722', r: 255, g: 87, b: 34 },
  { name: 'Gün Batımı Amber', hex: '#FF9900', r: 255, g: 153, b: 0 },
  { name: 'Elektrik Sarı', hex: '#FFDD00', r: 255, g: 221, b: 0 },
  { name: 'Asit Limon', hex: '#76FF03', r: 118, g: 255, b: 3 },
  { name: 'Zümrüt Yeşil', hex: '#00E676', r: 0, g: 230, b: 118 },
  { name: 'Neon Camgöbeği', hex: '#00F0FF', r: 0, g: 240, b: 255 },
  { name: 'Gök Mavisi', hex: '#00B0FF', r: 0, g: 176, b: 255 },
  { name: 'Kraliyet Mavisi', hex: '#2979FF', r: 41, g: 121, b: 255 },
  { name: 'Derin Mor', hex: '#651FFF', r: 101, g: 31, b: 255 },
  { name: 'Elektrik Menekşe', hex: '#D500F9', r: 213, g: 0, b: 249 },
  { name: 'Sıcak Pembe', hex: '#F50057', r: 245, g: 0, b: 87 },
  { name: 'Saf Beyaz', hex: '#FFFFFF', r: 255, g: 255, b: 255 },
  { name: 'Sıcak Beyaz', hex: '#FFE0B2', r: 255, g: 224, b: 178 },
  { name: 'Doğal Beyaz', hex: '#F5F5F5', r: 245, g: 245, b: 245 },
  { name: 'Soğuk Beyaz', hex: '#E0F7FA', r: 224, g: 247, b: 250 },
];

// Helper: Hex to RGB
function hexToRgb(hex) {
  let cleaned = hex.replace('#', '').trim();
  if (cleaned.length === 3) {
    cleaned = cleaned.split('').map(c => c + c).join('');
  }
  const num = parseInt(cleaned, 16);
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255,
  };
}

// Helper: RGB to Hex
function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(x => {
    const hex = Math.max(0, Math.min(255, Math.round(x))).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('').toUpperCase();
}

// Helper: Toast Notifications (Authored SVG Icons)
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const iconSvg = type === 'success'
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>'
    : type === 'error'
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';

  toast.innerHTML = `<span class="toast-icon">${iconSvg}</span><span class="toast-msg">${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Helper: Set Dynamic CSS Variables & Ambient Glow
function updateThemeColors(hex, r, g, b) {
  document.documentElement.style.setProperty('--active-color', hex);
  document.documentElement.style.setProperty('--active-color-rgb', `${r}, ${g}, ${b}`);

  const pct = Math.round((state.brightness / 255) * 100);
  document.documentElement.style.setProperty('--active-brightness', `${state.isPoweredOn ? pct / 100 : 0}`);

  // Update simulator diodes
  const diodes = document.querySelectorAll('.led-diode');
  diodes.forEach(d => {
    if (state.isPoweredOn) {
      d.classList.add('lit');
      d.style.background = hex;
      d.style.opacity = `${Math.max(0.15, state.brightness / 255)}`;
    } else {
      d.classList.remove('lit');
      d.style.background = '#1e293b';
      d.style.opacity = '0.3';
    }
  });

  // Update strip text
  const stripStatusText = document.getElementById('strip-status-text');
  stripStatusText.textContent = state.isPoweredOn
    ? `Durum: Açık • Renk: ${hex} • Parlaklık: %${pct}`
    : 'Durum: Kapalı';
}

// Build 24 Virtual LED Diodes
function initLedStrip() {
  const track = document.getElementById('led-strip-track');
  track.innerHTML = '';
  for (let i = 0; i < 24; i++) {
    const diode = document.createElement('div');
    diode.className = 'led-diode lit';
    track.appendChild(diode);
  }
}

// Populate 16 Swatches
function initSwatches() {
  const grid = document.getElementById('swatches-grid');
  grid.innerHTML = '';
  PRESET_SWATCHES.forEach(s => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'swatch-btn';
    btn.style.backgroundColor = s.hex;
    btn.title = `${s.name} (${s.hex})`;
    btn.setAttribute('aria-label', s.name);

    if (s.hex.toUpperCase() === state.color.hex.toUpperCase()) {
      btn.classList.add('active');
    }

    btn.addEventListener('click', () => {
      document.querySelectorAll('.swatch-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyColor(s.r, s.g, s.b, s.hex);
    });

    grid.appendChild(btn);
  });
}

// Reflect "static color" vs "effect #N" mode in the effect panel
function setEffectModeUI(effectId) {
  state.effectId = effectId;
  const isStatic = effectId === null;
  document.getElementById('active-effect-display').textContent = isStatic
    ? 'Statik Renk'
    : `Efekt #${effectId}`;
  document.querySelectorAll('.effect-tile').forEach(t => {
    t.classList.toggle('active', !isStatic && parseInt(t.dataset.id, 10) === effectId);
  });
  if (isStatic) {
    // Static color is applied via swatches/picker; keep swatch highlight as-is.
    return;
  }
  // A running effect overrides the static color, so drop the swatch highlight.
  document.querySelectorAll('.swatch-btn').forEach(b => b.classList.remove('active'));
}

const sendColor = createCoalescedSender('/api/color', {
  onSuccess: (data) => showToast(`Renk ayarlandı: ${rgbToHex(data.r, data.g, data.b)}`, 'success'),
  onError: (msg) => showToast(msg || 'Renk ayarlanamadı.', 'error'),
});

// API: Apply Color (immediate UI update, coalesced network send)
function applyColor(r, g, b, hex) {
  state.color = { hex, r, g, b };
  // The server switches the strip to solid-color mode (A0 63 01 BE) before
  // writing the color, so any running effect is stopped by this action.
  setEffectModeUI(null);

  // Sync inputs
  document.getElementById('native-color-picker').value = hex;
  document.getElementById('hex-input').value = hex;
  document.getElementById('hex-display').textContent = hex;
  document.getElementById('rgb-r').value = r;
  document.getElementById('rgb-g').value = g;
  document.getElementById('rgb-b').value = b;

  updateThemeColors(hex, r, g, b);
  sendColor({ r, g, b, brightness: state.brightness });
}

const sendBrightnessRequest = createCoalescedSender('/api/brightness', {
  onSuccess: () => {},
  onError: (msg) => showToast(msg || 'Parlaklık ayarlanamadı.', 'error'),
});

// API: Apply Brightness (Debounced + coalesced)
let brightnessTimeout = null;
function sendBrightness(level) {
  state.brightness = level;
  const pct = Math.round((level / 255) * 100);

  document.getElementById('brightness-display').textContent = `${pct}%`;
  document.getElementById('brightness-val-raw').textContent = `${level} / 255`;
  updateThemeColors(state.color.hex, state.color.r, state.color.g, state.color.b);

  if (brightnessTimeout) clearTimeout(brightnessTimeout);
  brightnessTimeout = setTimeout(() => sendBrightnessRequest({ level }), 120);
}

// API: Power Toggle
async function togglePower() {
  const btn = document.getElementById('power-toggle-btn');
  const newState = state.isPoweredOn ? 'off' : 'on';
  btn.classList.toggle('active', newState === 'on');

  try {
    const resp = await fetch('/api/power', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: newState }),
    });
    const data = await resp.json();
    if (data.success) {
      state.isPoweredOn = (newState === 'on');
      btn.classList.toggle('active', state.isPoweredOn);
      updateThemeColors(state.color.hex, state.color.r, state.color.g, state.color.b);
      showToast(`Cihaz ${state.isPoweredOn ? 'açıldı' : 'kapatıldı'}.`, 'success');
    } else {
      btn.classList.toggle('active', state.isPoweredOn);
      showToast(data.error || 'Güç komutu başarısız oldu.', 'error');
    }
  } catch (err) {
    btn.classList.toggle('active', state.isPoweredOn);
    showToast('Bağlantı hatası: ' + err.message, 'error');
  }
}

const sendEffectRequest = createCoalescedSender('/api/effect', {
  onSuccess: (data) => showToast(`Efekt #${data.effect_id} başlatıldı.`, 'success'),
  onError: (msg) => showToast(msg || 'Efekt ayarlanamadı.', 'error'),
});

// API: Apply Effect
function applyEffect(effectId, speed = null) {
  setEffectModeUI(effectId);
  document.getElementById('custom-effect-id').value = effectId;

  const body = { effect_id: effectId };
  if (speed !== null) body.speed = speed;
  sendEffectRequest(body);
}

const sendSpeedRequest = createCoalescedSender('/api/speed', {
  onSuccess: (data) => showToast(`Efekt hızı ${data.speed}/10 yapıldı.`, 'info'),
  onError: (msg) => showToast(msg || 'Hız ayarlanamadı.', 'error'),
});

// API: Apply Speed (Debounced + coalesced)
let speedTimeout = null;
function sendSpeed(speed) {
  state.speed = speed;
  document.getElementById('speed-display').textContent = `${speed} / 10`;

  if (speedTimeout) clearTimeout(speedTimeout);
  speedTimeout = setTimeout(() => sendSpeedRequest({ speed }), 150);
}

// API: Fetch Initial Status
async function loadStatus() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    if (data.success && data.mac) {
      state.activeMac = data.mac;
      document.getElementById('active-mac-label').textContent = data.mac;
      document.getElementById('manual-mac-input').value = data.mac;
      document.getElementById('status-indicator').className = 'status-indicator ready';
    } else {
      document.getElementById('active-mac-label').textContent = 'MAC Tanımlanmadı';
      document.getElementById('status-indicator').className = 'status-indicator busy';
      showToast('Lütfen hedef SP611E MAC adresini yapılandırın.', 'info');
    }
  } catch (err) {
    document.getElementById('active-mac-label').textContent = 'Bağlantı Hatası';
    document.getElementById('status-indicator').className = 'status-indicator busy';
  }
}

// BLE Scanner Modal Logic
function initScanner() {
  const modal = document.getElementById('scanner-modal');
  const btnOpen = document.getElementById('btn-open-scanner');
  const btnClose = document.getElementById('btn-close-scanner');
  const btnScan = document.getElementById('btn-start-scan');
  const btnSaveMac = document.getElementById('btn-save-mac');
  const deviceList = document.getElementById('device-list');
  const placeholder = document.getElementById('scan-placeholder');
  const scanSpinner = document.getElementById('scan-spinner');
  const scanBtnText = document.getElementById('scan-btn-text');
  const macInput = document.getElementById('manual-mac-input');

  function openModal() {
    modal.classList.add('open');
    setTimeout(() => macInput.focus(), 50);
  }

  function closeModal() {
    modal.classList.remove('open');
    btnOpen.focus();
  }

  btnOpen.addEventListener('click', openModal);
  btnClose.addEventListener('click', closeModal);

  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('open')) {
      closeModal();
    }
  });

  // Manual MAC save
  btnSaveMac.addEventListener('click', async () => {
    const mac = document.getElementById('manual-mac-input').value.trim();
    if (!mac) return;
    try {
      const resp = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mac }),
      });
      const data = await resp.json();
      if (data.success) {
        state.activeMac = data.mac;
        document.getElementById('active-mac-label').textContent = data.mac;
        showToast('Varsayılan MAC adresi kaydedildi.', 'success');
        modal.classList.remove('open');
      } else {
        showToast(data.error || 'Kaydedilemedi.', 'error');
      }
    } catch (err) {
      showToast('Hata: ' + err.message, 'error');
    }
  });

  // BLE Scan
  btnScan.addEventListener('click', async () => {
    btnScan.disabled = true;
    scanSpinner.classList.add('spinning');
    scanBtnText.textContent = 'Cihazlar taranıyor (4s)...';
    placeholder.textContent = 'Bluetooth cihazları aranıyor...';
    placeholder.style.display = 'block';
    deviceList.innerHTML = '';

    try {
      const resp = await fetch('/api/scan?timeout=4.0');
      const data = await resp.json();
      if (data.success) {
        if (data.devices.length === 0) {
          placeholder.textContent = 'Yakında hiçbir BLE cihazı bulunamadı.';
        } else {
          placeholder.style.display = 'none';
          data.devices.forEach(dev => {
            const item = document.createElement('div');
            item.className = `device-item ${dev.is_sp611e ? 'sp611e' : ''}`;
            const badgeHtml = dev.is_sp611e ? '<span class="sp611e-badge">SP611E</span>' : '';
            item.innerHTML = `
              <div class="device-info">
                <span class="device-name">${dev.name} ${badgeHtml}</span>
                <span class="device-mac">${dev.address}</span>
              </div>
              <div class="device-action">
                <span class="device-rssi">${dev.rssi} dBm</span>
                <button type="button" class="btn btn-secondary btn-select-device" data-mac="${dev.address}">Seç</button>
              </div>
            `;
            item.querySelector('.btn-select-device').addEventListener('click', async () => {
              document.getElementById('manual-mac-input').value = dev.address;
              btnSaveMac.click();
            });
            deviceList.appendChild(item);
          });
        }
      } else {
        placeholder.textContent = 'Hata: ' + (data.error || 'Tarama başarısız.');
      }
    } catch (err) {
      placeholder.textContent = 'Tarama hatası: ' + err.message;
    } finally {
      btnScan.disabled = false;
      scanSpinner.classList.remove('spinning');
      scanBtnText.textContent = 'Yeniden Tara';
    }
  });
}

// Bind DOM Events
function bindEvents() {
  // Power button
  const pwrBtn = document.getElementById('power-toggle-btn');
  pwrBtn.classList.add('active');
  pwrBtn.addEventListener('click', togglePower);

  // Native color picker: 'input' fires continuously while dragging the wheel,
  // so debounce before hitting the device (each BLE round-trip takes seconds).
  const picker = document.getElementById('native-color-picker');
  let pickerTimeout = null;
  picker.addEventListener('input', (e) => {
    const hex = e.target.value.toUpperCase();
    const { r, g, b } = hexToRgb(hex);
    document.querySelectorAll('.swatch-btn').forEach(b => b.classList.remove('active'));
    if (pickerTimeout) clearTimeout(pickerTimeout);
    pickerTimeout = setTimeout(() => applyColor(r, g, b, hex), 200);
  });

  const clearSwatchHighlight = () =>
    document.querySelectorAll('.swatch-btn').forEach(b => b.classList.remove('active'));

  // Hex Input & Apply button
  document.getElementById('btn-apply-color').addEventListener('click', () => {
    const hex = document.getElementById('hex-input').value.trim();
    if (!/^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(hex)) {
      showToast('Geçersiz Hex renk formatı.', 'error');
      return;
    }
    const { r, g, b } = hexToRgb(hex);
    clearSwatchHighlight();
    applyColor(r, g, b, rgbToHex(r, g, b));
  });

  // RGB inputs change
  ['rgb-r', 'rgb-g', 'rgb-b'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => {
      const clamp = v => Math.max(0, Math.min(255, parseInt(v, 10) || 0));
      const r = clamp(document.getElementById('rgb-r').value);
      const g = clamp(document.getElementById('rgb-g').value);
      const b = clamp(document.getElementById('rgb-b').value);
      clearSwatchHighlight();
      applyColor(r, g, b, rgbToHex(r, g, b));
    });
  });

  // Brightness Slider
  const bSlider = document.getElementById('brightness-slider');
  bSlider.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    sendBrightness(val);

    // Update preset active state
    document.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
  });

  // Brightness Presets
  document.querySelectorAll('.btn-preset').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const pct = parseInt(btn.dataset.pct, 10);
      const val = Math.round((pct / 100) * 255);
      bSlider.value = val;
      sendBrightness(val);
    });
  });

  // Effect tiles click
  document.querySelectorAll('.effect-tile').forEach(tile => {
    tile.addEventListener('click', () => {
      const effectId = parseInt(tile.dataset.id, 10);
      applyEffect(effectId, state.speed);
    });
  });

  // Custom Effect input
  document.getElementById('btn-apply-custom-effect').addEventListener('click', () => {
    const effectId = parseInt(document.getElementById('custom-effect-id').value, 10);
    if (effectId >= 1 && effectId <= 255) {
      applyEffect(effectId, state.speed);
    } else {
      showToast('Efekt ID 1 ile 255 arasında olmalıdır.', 'error');
    }
  });

  // Speed Slider
  const sSlider = document.getElementById('speed-slider');
  sSlider.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    sendSpeed(val);
  });
}

// Initialization on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  initLedStrip();
  initSwatches();
  bindEvents();
  initScanner();
  loadStatus();
  updateThemeColors(state.color.hex, state.color.r, state.color.g, state.color.b);
});
