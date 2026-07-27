/**
 * secure-dom.js — Escape HTML / sanitize same-origin URLs for notification UIs.
 * Also includes fast logout enhancement for instant logout feedback.
 */
(function () {
  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function safeUrl(u) {
    try {
      var x = new URL(u || "/notifications", window.location.origin);
      if (x.origin !== window.location.origin) return "/notifications";
      return x.pathname + x.search + x.hash;
    } catch (e) {
      return "/notifications";
    }
  }

  window.escHtml = escHtml;
  window.safeUrl = safeUrl;

  // ═══════════════════════════════════════════════════════════════════
  // FAST LOGOUT - Makes logout feel instant with immediate feedback
  // ═══════════════════════════════════════════════════════════════════
  function initFastLogout() {
    const logoutLinks = document.querySelectorAll('a[href="/auth/logout"], a[href*="/auth/logout"]');
    
    logoutLinks.forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        
        // Immediate visual feedback
        link.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span class="topbar-logout-label">Signing out...</span>';
        link.style.opacity = '0.6';
        link.style.pointerEvents = 'none';
        link.style.cursor = 'wait';
        
        // Clear client-side storage immediately (instant local logout)
        try {
          localStorage.clear();
          sessionStorage.clear();
        } catch (err) {
          // Ignore storage errors
        }
        
        // Clear service worker caches if present
        if ('caches' in window) {
          caches.keys().then(function(names) {
            names.forEach(function(name) {
              caches.delete(name);
            });
          });
        }
        
        // Navigate to logout (server clears session)
        window.location.href = '/auth/logout';
      });
    });
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFastLogout);
  } else {
    initFastLogout();
  }
})();
