/**
 * Progressive SPA navigation for the existing Flask/Jinja portals.
 *
 * Same-portal GET links are fetched and only <main> is replaced. Downloads,
 * forms, auth actions, external links, and incompatible portal layouts retain
 * normal browser navigation. This preserves every server-side permission check
 * and existing URL while removing most full-page reloads.
 */
(function () {
  'use strict';

  const CACHE_TTL = 10_000;
  const cache = new Map();
  let activeRequest = null;
  let navigationSequence = 0;
  let dashboardTimer = null;
  let dashboardEvents = null;
  let prefetchTimer = null;

  function ensureProgressBar() {
    let bar = document.getElementById('spa-progress');
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'spa-progress';
    bar.setAttribute('aria-hidden', 'true');
    bar.innerHTML = '<span></span>';
    document.body.appendChild(bar);
    return bar;
  }

  function setLoading(loading) {
    const bar = ensureProgressBar();
    document.documentElement.classList.toggle('spa-loading', loading);
    bar.classList.toggle('active', loading);
  }

  function normalizedUrl(value) {
    try {
      const url = new URL(value, window.location.href);
      url.hash = '';
      return url;
    } catch (_) {
      return null;
    }
  }

  function isDownloadLike(anchor, url) {
    if (anchor.hasAttribute('download')) return true;
    if (anchor.dataset.noSpa !== undefined) return true;
    if (anchor.target && anchor.target !== '_self') return true;
    if (anchor.rel && /\bexternal\b/i.test(anchor.rel)) return true;
    if (/\/auth\/(logout|login)/.test(url.pathname)) return true;
    if (/\/(download|export)(\/|$)/i.test(url.pathname)) return true;
    if (/\.(pdf|xlsx?|csv|zip|docx?|png|jpe?g|webp|mp4|mov|mp3)$/i.test(url.pathname)) return true;
    return false;
  }

  function eligibleAnchor(target) {
    const anchor = target instanceof Element ? target.closest('a[href]') : null;
    if (!anchor || !document.querySelector('.dashboard-container')) return null;
    const raw = anchor.getAttribute('href') || '';
    if (!raw || raw === '#' || raw.startsWith('#') || raw.startsWith('javascript:')) return null;
    const url = normalizedUrl(anchor.href);
    if (!url || url.origin !== window.location.origin || isDownloadLike(anchor, url)) return null;
    return { anchor, url };
  }

  function portalSignature(root) {
    const role = root.querySelector('.sidebar .role-badge');
    if (role) return role.textContent.replace(/\s+/g, ' ').trim().toLowerCase();
    const sidebar = root.querySelector('.sidebar');
    return sidebar ? sidebar.className : '';
  }

  async function fetchPage(url, signal) {
    const key = url.href;
    const cached = cache.get(key);
    if (cached && Date.now() - cached.time < CACHE_TTL) return cached.html;

    const response = await fetch(key, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers: {
        'Accept': 'text/html',
        'X-Requested-With': 'SPA',
      },
    });

    const contentType = response.headers.get('content-type') || '';
    const disposition = response.headers.get('content-disposition') || '';
    if (!response.ok || !contentType.includes('text/html') || /attachment/i.test(disposition)) {
      throw new Error('FULL_NAVIGATION_REQUIRED');
    }

    const html = await response.text();
    cache.set(key, { html, time: Date.now() });
    return html;
  }

  function loadStylesAndDependencies(doc) {
    const tasks = [];
    const loadedStyles = new Set(
      Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
        .map(link => new URL(link.href, location.href).href)
    );

    doc.querySelectorAll('link[rel="stylesheet"][href]').forEach(source => {
      const href = new URL(source.getAttribute('href'), location.href).href;
      if (loadedStyles.has(href)) return;
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      link.dataset.spaAsset = 'true';
      tasks.push(new Promise(resolve => {
        link.onload = resolve;
        link.onerror = resolve;
        document.head.appendChild(link);
      }));
      loadedStyles.add(href);
    });

    document.querySelectorAll('style[data-spa-page-style]').forEach(style => style.remove());
    doc.head.querySelectorAll('style').forEach(source => {
      const style = document.createElement('style');
      style.dataset.spaPageStyle = 'true';
      style.textContent = source.textContent;
      document.head.appendChild(style);
    });

    const loadedScripts = new Set(
      Array.from(document.querySelectorAll('script[src]'))
        .map(script => new URL(script.src, location.href).href)
    );
    doc.querySelectorAll('script[src]').forEach(source => {
      const src = new URL(source.getAttribute('src'), location.href).href;
      if (loadedScripts.has(src)) return;
      const script = document.createElement('script');
      script.src = src;
      script.async = false;
      if (source.type) script.type = source.type;
      script.dataset.spaAsset = 'true';
      tasks.push(new Promise(resolve => {
        script.onload = resolve;
        script.onerror = resolve;
        document.head.appendChild(script);
      }));
      loadedScripts.add(src);
    });

    return Promise.all(tasks);
  }

  function destroyPageWidgets(root) {
    if (window.Chart && typeof window.Chart.getChart === 'function') {
      root.querySelectorAll('canvas').forEach(canvas => {
        const chart = window.Chart.getChart(canvas);
        if (chart) chart.destroy();
      });
    }
    window.dispatchEvent(new CustomEvent('spa:before-swap'));
  }

  function collectPageAssets(doc) {
    const assets = [];
    const holder = doc.getElementById('spa-page-scripts');
    if (holder) {
      holder.querySelectorAll('script, style').forEach(node => assets.push(node));
    }
    return assets;
  }

  function executePageScripts(container, externalNodes) {
    document.querySelectorAll('[data-spa-page-script]').forEach(node => node.remove());

    const existingHolder = document.getElementById('spa-page-scripts');
    if (existingHolder) existingHolder.innerHTML = '';

    const run = (oldScript, replaceInPlace) => {
      if (oldScript.src) {
        const src = new URL(oldScript.getAttribute('src') || oldScript.src, location.href).href;
        if (Array.from(document.querySelectorAll('script[src]')).some(s => s.src === src)) {
          if (replaceInPlace) oldScript.remove();
          return;
        }
      }
      const script = document.createElement('script');
      Array.from(oldScript.attributes).forEach(attr => script.setAttribute(attr.name, attr.value));
      if (!oldScript.src) script.textContent = oldScript.textContent;
      script.dataset.spaPageScript = 'true';
      if (replaceInPlace) oldScript.replaceWith(script);
      else if (existingHolder) existingHolder.appendChild(script);
      else document.body.appendChild(script);
    };

    container.querySelectorAll('script').forEach(node => run(node, true));
    (externalNodes || []).forEach(node => {
      if (node.tagName === 'SCRIPT') run(node, false);
    });
  }

  function applyExternalStyles(nodes) {
    document.querySelectorAll('style[data-spa-page-style="body"]').forEach(node => node.remove());
    (nodes || []).forEach(node => {
      if (node.tagName !== 'STYLE') return;
      const style = document.createElement('style');
      style.dataset.spaPageStyle = 'body';
      style.textContent = node.textContent;
      document.head.appendChild(style);
    });
  }

  function updateFlashes(doc, currentMain) {
    const currentContent = currentMain.closest('.main-content');
    const nextMain = doc.querySelector('.main-content main');
    const nextContent = nextMain && nextMain.closest('.main-content');
    if (!currentContent || !nextContent) return;

    Array.from(currentContent.children).forEach(child => {
      if (child !== currentMain && child.tagName !== 'HEADER' && /(^|\s)flash-/.test(child.className || '')) {
        child.remove();
      }
    });
    Array.from(nextContent.children).forEach(child => {
      if (child !== nextMain && child.tagName !== 'HEADER' && /(^|\s)flash-/.test(child.className || '')) {
        currentContent.insertBefore(child.cloneNode(true), currentMain);
      }
    });
  }

  function updateSidebar(url) {
    document.querySelectorAll('.sidebar-menu a').forEach(anchor => {
      anchor.classList.remove('active');
      const href = anchor.getAttribute('href');
      if (!href || href === '#') return;
      const candidate = normalizedUrl(href);
      if (!candidate) return;
      if (url.pathname === candidate.pathname ||
          (candidate.pathname !== '/' && url.pathname.startsWith(candidate.pathname + '/'))) {
        anchor.classList.add('active');
      }
    });
  }

  function setupTopbarLogout() {
    const bellWrapper = document.getElementById('notifWrapper');
    if (!bellWrapper || !bellWrapper.parentElement) return;

    // Remove any leftover Sign Out links still in the sidebar
    document.querySelectorAll('.sidebar a[href="/auth/logout"]').forEach(node => {
      if (!node.classList.contains('topbar-logout')) node.remove();
    });

    if (document.querySelector('.topbar-logout')) return;

    const logout = document.createElement('a');
    logout.href = '/auth/logout';
    logout.className = 'topbar-logout';
    logout.title = 'Sign out';
    logout.setAttribute('aria-label', 'Sign out');
    logout.innerHTML = '<i class="fas fa-sign-out-alt" aria-hidden="true"></i>'
      + '<span class="topbar-logout-label">Sign Out</span>';
    bellWrapper.insertAdjacentElement('afterend', logout);
  }

  function setupDashboardRefresh() {
    if (dashboardTimer) clearInterval(dashboardTimer);
    dashboardTimer = null;
    if (dashboardEvents) dashboardEvents.abort();
    dashboardEvents = null;

    const status = document.getElementById('dashboard-live-status');
    if (!status) return;
    const dot = status.querySelector('#dashboard-live-dot');
    const text = status.querySelector('#dashboard-live-text');
    const intervalSeconds = 20;
    let remaining = intervalSeconds;
    let formDirty = false;
    dashboardEvents = new AbortController();
    const options = { signal: dashboardEvents.signal };

    document.addEventListener('input', event => {
      if (event.target instanceof Element && event.target.closest('form')) formDirty = true;
    }, options);
    document.addEventListener('change', event => {
      if (event.target instanceof Element && event.target.closest('form')) formDirty = true;
    }, options);
    document.addEventListener('submit', () => { formDirty = false; }, options);

    const render = paused => {
      if (!dot || !text) return;
      dot.style.background = paused ? '#f59e0b' : '#10b981';
      text.textContent = paused
        ? (formDirty ? 'Live · paused (unsaved changes)' : 'Live · paused')
        : `Live · refresh in ${remaining}s`;
    };

    dashboardTimer = setInterval(() => {
      const active = document.activeElement;
      const interacting = formDirty || document.hidden ||
        (active && /^(INPUT|SELECT|TEXTAREA)$/.test(active.tagName));
      if (interacting) {
        remaining = intervalSeconds;
        render(true);
        return;
      }
      remaining -= 1;
      if (remaining <= 0) {
        navigate(new URL(window.location.href), { push: false, force: true });
        remaining = intervalSeconds;
      }
      render(false);
    }, 1000);
    render(false);
  }

  async function swapPage(html, url, push) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const currentMain = document.querySelector('.main-content main');
    const nextMain = doc.querySelector('.main-content main');
    if (!currentMain || !nextMain ||
        portalSignature(document) !== portalSignature(doc)) {
      window.location.assign(url.href);
      return;
    }

    const pageAssets = collectPageAssets(doc);
    await loadStylesAndDependencies(doc);
    applyExternalStyles(pageAssets);
    destroyPageWidgets(currentMain);
    updateFlashes(doc, currentMain);
    currentMain.innerHTML = nextMain.innerHTML;

    const nextTitle = doc.querySelector('.topbar-title');
    const currentTitle = document.querySelector('.topbar-title');
    if (nextTitle && currentTitle) currentTitle.innerHTML = nextTitle.innerHTML;
    document.title = doc.title || document.title;
    updateSidebar(url);
    executePageScripts(currentMain, pageAssets);
    setupTopbarLogout();
    setupDashboardRefresh();

    if (push) history.pushState({ spa: true }, '', url.href);
    window.scrollTo({ top: 0, behavior: 'instant' });
    const heading = currentMain.querySelector('h1, [role="heading"]');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      heading.focus({ preventScroll: true });
    }
    window.dispatchEvent(new CustomEvent('spa:page-loaded', {
      detail: { url: url.href, main: currentMain },
    }));
  }

  async function navigate(url, options = {}) {
    const { push = true, force = false } = options;
    const sequence = ++navigationSequence;
    if (activeRequest) activeRequest.abort();
    activeRequest = new AbortController();
    setLoading(true);

    try {
      if (force) cache.delete(url.href);
      const html = await fetchPage(url, activeRequest.signal);
      if (sequence !== navigationSequence) return;
      await swapPage(html, url, push);
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      window.location.assign(url.href);
    } finally {
      if (sequence === navigationSequence) {
        activeRequest = null;
        setLoading(false);
      }
    }
  }

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const eligible = eligibleAnchor(event.target);
    if (!eligible) return;
    event.preventDefault();
    navigate(eligible.url);
  });

  document.addEventListener('mouseover', event => {
    const eligible = eligibleAnchor(event.target);
    if (!eligible) return;
    clearTimeout(prefetchTimer);
    prefetchTimer = setTimeout(() => {
      if (!cache.has(eligible.url.href)) {
        fetchPage(eligible.url, new AbortController().signal).catch(() => {});
      }
    }, 120);
  });

  document.addEventListener('mouseout', () => clearTimeout(prefetchTimer));
  window.addEventListener('popstate', () => navigate(new URL(window.location.href), { push: false }));

  setupTopbarLogout();
  setupDashboardRefresh();
  updateSidebar(new URL(window.location.href));
})();
