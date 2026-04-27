window.APP_CONFIG = {
  API_BASE_URL: ["127.0.0.1", "localhost"].includes(window.location.hostname)
    ? "http://127.0.0.1:8000"
    : "",
};
