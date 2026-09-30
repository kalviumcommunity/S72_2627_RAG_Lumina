// Apply the saved theme before first paint (no flash). Values: light | dark | system.
(function () {
  var root = document.documentElement;
  try {
    var t = localStorage.getItem("protocite.theme") || "system";
    var dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.dataset.theme = dark ? "dark" : "light";
  } catch (e) {
    root.dataset.theme = "light";
  }
})();
