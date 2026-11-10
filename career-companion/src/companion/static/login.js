// Trades the single-use launch token (in the URL fragment, which is never sent to the server
// or written to logs) for a session cookie, then removes it from the address bar.
(async function () {
  "use strict";
  const status = document.getElementById("login-status");
  const match = /[#&]t=([^&]+)/.exec(window.location.hash);
  history.replaceState(null, "", "/");
  if (!match) {
    status.textContent = "Open the link printed in the terminal when you started the app. " +
      "If you already used it, stop the app and start it again for a new link.";
    return;
  }
  try {
    const resp = await fetch("/auth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: match[1] }),
    });
    if (resp.ok) {
      window.location.replace("/");
    } else {
      const data = await resp.json();
      status.textContent = data.error || "Sign-in failed.";
    }
  } catch (err) {
    status.textContent = "Could not reach the app. Is it still running?";
  }
})();
