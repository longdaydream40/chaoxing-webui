const COVER_SESSION_KEY = "lycoris_cover_burn_entered";

document.querySelectorAll("[data-cover-return]").forEach((button) => {
  button.addEventListener("click", () => {
    sessionStorage.removeItem(COVER_SESSION_KEY);
    window.location.href = "/";
  });
});
