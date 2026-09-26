/** Per-browser preferences (theme, sidebar) in localStorage; tolerates storage being unavailable. */

const PREFIX = "taskboard.";

export function readPref(name, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + name);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function writePref(name, value) {
  try {
    if (value === undefined || value === null) localStorage.removeItem(PREFIX + name);
    else localStorage.setItem(PREFIX + name, JSON.stringify(value));
  } catch {
    // Private mode or blocked storage: the preference simply isn't remembered.
  }
}
