const API_BASE =
  (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) ||
  window.location.origin;
const TOKEN_KEY = "lycoris_app_token";
const USER_KEY = "lycoris_app_user";

const usernameEl = document.getElementById("username");
const passwordEl = document.getElementById("password");
const registerBtn = document.getElementById("registerBtn");
const msgEl = document.getElementById("msg");

async function register() {
  try {
    msgEl.textContent = "Creating account...";
    const resp = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: usernameEl.value.trim(),
        password: passwordEl.value.trim(),
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Registration failed.");
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    msgEl.textContent = "Account created. Redirecting...";
    setTimeout(() => {
      window.location.href = "/";
    }, 900);
  } catch (error) {
    msgEl.textContent = `Registration failed: ${error.message}`;
  }
}

registerBtn.addEventListener("click", register);
