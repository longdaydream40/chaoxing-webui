const API_BASE =
  (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) ||
  window.location.origin;
const TOKEN_KEY = "lycoris_app_token";
const USER_KEY = "lycoris_app_user";

const usernameEl = document.getElementById("username");
const passwordEl = document.getElementById("password");
const loginBtn = document.getElementById("loginBtn");
const msgEl = document.getElementById("msg");

async function login() {
  try {
    msgEl.textContent = "Authenticating...";
    const resp = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: usernameEl.value.trim(),
        password: passwordEl.value.trim(),
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Login failed.");
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    window.location.href = "/";
  } catch (error) {
    msgEl.textContent = `Login failed: ${error.message}`;
  }
}

loginBtn.addEventListener("click", login);
