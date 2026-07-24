/**
 * secure-dom.js — Escape HTML / sanitize same-origin URLs for notification UIs.
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
})();
