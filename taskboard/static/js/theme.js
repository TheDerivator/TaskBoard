/** Light/dark theme: follows the system until the user picks one, then remembers the choice. */
import { readPref, writePref } from "./prefs.js";
import { useEffect, useState } from "./ui.js";

const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function apply(theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

export function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/** [theme, toggle]: toggling stores the explicit choice. */
export function useTheme() {
  const [theme, setTheme] = useState(currentTheme);
  useEffect(() => {
    const onSystemChange = (event) => {
      if (readPref("theme", null) === null) {
        apply(event.matches ? "dark" : "light");
        setTheme(currentTheme());
      }
    };
    systemDark.addEventListener("change", onSystemChange);
    return () => systemDark.removeEventListener("change", onSystemChange);
  }, []);
  const toggle = () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    writePref("theme", next);
    apply(next);
    setTheme(next);
  };
  return [theme, toggle];
}
