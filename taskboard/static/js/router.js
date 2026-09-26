/** History-API router: current route, navigate(), href() with the base path, link interception. */
import { parseRoute } from "./lib/routes.js";
import { useEffect, useState } from "./ui.js";

/** The deployment's base path from <base href>, e.g. "/" or "/taskboard/". */
export const BASE = new URL(document.baseURI).pathname.replace(/\/?$/, "/");

const listeners = new Set();

function current() {
  return parseRoute(location.pathname, location.search, BASE);
}

let route = current();

function update() {
  route = current();
  for (const listener of listeners) listener(route);
}

/** Absolute URL path for an app-relative path such as "t/K7Q2MX". */
export function href(path) {
  return BASE + String(path).replace(/^\/+/, "");
}

export function navigate(path, { replace = false } = {}) {
  const target = href(path);
  if (target === location.pathname + location.search) return;
  history[replace ? "replaceState" : "pushState"](null, "", target);
  update();
  if (!replace) window.scrollTo(0, 0);
}

export function useRoute() {
  const [value, setValue] = useState(route);
  useEffect(() => {
    listeners.add(setValue);
    setValue(route);
    return () => listeners.delete(setValue);
  }, []);
  return value;
}

window.addEventListener("popstate", update);

// Plain <a href> links inside the app navigate without reloading the page.
document.addEventListener("click", (event) => {
  if (event.defaultPrevented || event.button !== 0) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest?.("a[href]");
  if (!link || link.target || link.hasAttribute("download")) return;
  const url = new URL(link.href);
  if (url.origin !== location.origin || !url.pathname.startsWith(BASE)) return;
  if (url.pathname.startsWith(`${BASE}api/`) || url.pathname.startsWith(`${BASE}static/`)) return;
  event.preventDefault();
  navigate(url.pathname.slice(BASE.length) + url.search);
});
