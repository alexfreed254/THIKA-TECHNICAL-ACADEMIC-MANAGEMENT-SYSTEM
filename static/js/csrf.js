/**
 * csrf.js — Auto-inject Flask-WTF CSRF token into forms and fetch/XHR.
 */
(function () {
  function getToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? (meta.getAttribute("content") || "") : "";
  }

  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (!form || !form.tagName || form.tagName.toLowerCase() !== "form") return;
      var method = (form.getAttribute("method") || "get").toLowerCase();
      if (method !== "post") return;
      if (form.querySelector('input[name="csrf_token"]')) return;
      var token = getToken();
      if (!token) return;
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "csrf_token";
      input.value = token;
      form.appendChild(input);
    },
    true
  );

  if (typeof window.fetch === "function") {
    var _fetch = window.fetch;
    window.fetch = function (input, init) {
      init = init || {};
      var method = (init.method || "GET").toUpperCase();
      if (["POST", "PUT", "PATCH", "DELETE"].indexOf(method) !== -1) {
        var token = getToken();
        if (token) {
          var headers = init.headers || {};
          if (typeof Headers !== "undefined" && headers instanceof Headers) {
            if (!headers.has("X-CSRFToken") && !headers.has("X-CSRF-Token")) {
              headers.set("X-CSRFToken", token);
            }
          } else {
            var h = {};
            for (var k in headers) {
              if (Object.prototype.hasOwnProperty.call(headers, k)) h[k] = headers[k];
            }
            if (!h["X-CSRFToken"] && !h["X-CSRF-Token"]) h["X-CSRFToken"] = token;
            init.headers = h;
          }
        }
      }
      return _fetch.call(this, input, init);
    };
  }
})();
