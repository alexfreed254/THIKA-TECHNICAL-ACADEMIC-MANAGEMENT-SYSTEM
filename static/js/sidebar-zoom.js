/**
 * Sidebar zoom — horizontal range 0% … Max (200%).
 * Applies to .main-content so the sidebar (and slider) stay usable.
 * Persists in localStorage key ttti_zoom (percent). Migrates legacy 1/1.1/1.2 multipliers.
 */
(function () {
  var MIN = 0;
  var MAX = 200;
  var KEY = 'ttti_zoom';

  function readPct() {
    var raw = parseFloat(localStorage.getItem(KEY) || '100');
    if (isNaN(raw)) return 100;
    // Legacy multipliers from click-to-cycle zoom (1, 1.1, 1.2)
    if (raw > 0 && raw <= 3) raw = Math.round(raw * 100);
    return Math.min(MAX, Math.max(MIN, Math.round(raw)));
  }

  function zoomTarget() {
    return document.querySelector('.main-content') || document.body;
  }

  function applyZoom(pct) {
    pct = Math.min(MAX, Math.max(MIN, Math.round(Number(pct) || 0)));
    var level = pct / 100;
    var target = zoomTarget();

    // Clear previous body zoom from older click-cycle implementation
    if (document.body && document.body !== target) {
      document.body.style.zoom = '';
      document.body.style.transform = '';
    }

    target.style.zoom = String(level);

    // Firefox does not support CSS zoom — use scale fallback
    var zoomUnsupported = typeof CSS !== 'undefined' && CSS.supports && !CSS.supports('zoom', '1');
    if (zoomUnsupported || (target.style.zoom === '' && level !== 1)) {
      if (level === 0) {
        target.style.transform = 'scale(0)';
        target.style.transformOrigin = 'top left';
        target.style.width = '100%';
      } else {
        target.style.transform = 'scale(' + level + ')';
        target.style.transformOrigin = 'top left';
        target.style.width = (100 / level) + '%';
      }
    } else {
      target.style.transform = '';
      target.style.width = '';
    }

    var lbl = document.getElementById('zoomLabel');
    if (lbl) lbl.textContent = pct + '%';

    var slider = document.getElementById('zoomSlider');
    if (slider) {
      slider.value = String(pct);
      slider.setAttribute('aria-valuenow', String(pct));
    }

    localStorage.setItem(KEY, String(pct));
  }

  function bindSlider(slider) {
    if (!slider || slider.dataset.zoomBound === '1') return;
    slider.dataset.zoomBound = '1';
    slider.min = String(MIN);
    slider.max = String(MAX);
    slider.step = '5';

    function onChange() {
      applyZoom(slider.value);
    }

    slider.addEventListener('input', onChange);
    slider.addEventListener('change', onChange);
    // Keep mobile sidebar open while dragging
    slider.addEventListener('click', function (e) { e.stopPropagation(); });
    slider.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
  }

  function init() {
    var pct = readPct();
    bindSlider(document.getElementById('zoomSlider'));
    applyZoom(pct);
  }

  window.TTTIZoom = { apply: applyZoom, init: init, MIN: MIN, MAX: MAX };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
