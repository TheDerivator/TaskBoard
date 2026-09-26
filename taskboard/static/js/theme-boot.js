/* Applies the saved (or the system's) colour theme before the first paint, to avoid a flash. */
(function () {
  var theme = null;
  try {
    theme = JSON.parse(localStorage.getItem("taskboard.theme"));
  } catch (e) {
    theme = null;
  }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
