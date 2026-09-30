/** Windows sign-in (HTTP Negotiate): one request; the browser answers the server's challenges itself. */
import { api } from "./api.js";

const TRIED = "taskboard.windowsSignIn.tried"; // sessionStorage: per tab, forgotten when it closes

function remember(tried) {
  try {
    if (tried) sessionStorage.setItem(TRIED, "1");
    else sessionStorage.removeItem(TRIED);
  } catch {
    // Blocked storage: the page then tries at every load, which is only one extra request.
  }
}

/** Whether this tab should leave automatic sign-in alone: it failed here, or the user logged out. */
export function windowsSignInTried() {
  try {
    return sessionStorage.getItem(TRIED) === "1";
  } catch {
    return false;
  }
}

/** Don't sign in by itself again in this tab (after logging out: else it would undo that at once). */
export function holdWindowsSignIn() {
  remember(true);
}

/** Resolves to the signed-in user ("me"), with the session cookie set; rejects with an ApiError. */
export async function windowsSignIn() {
  remember(true);
  const me = await api.post("/auth/windows");
  remember(false); // it works here: try again by itself once this session has ended
  return me;
}
