/** Windows sign-in decisions: when the page tries it by itself, and which failures to mention. Pure. */

/** The server's 401 that the browser did not answer (or that Windows refused): nobody was identified. */
const UNANSWERED = "windows_sign_in_required";

/** Only for visitors who are not signed in, only when the server asks for it, once per tab. */
export function shouldTryWindowsSignIn(me, alreadyTried) {
  return Boolean(me?.is_anonymous && me.login?.windows?.automatic && !alreadyTried);
}

/**
 * An attempt nobody asked for fails silently, unless Windows did say who it is and TaskBoard
 * refused that person (no account, suspended): they should know why they are not signed in.
 */
export function isWindowsRefusal(error) {
  return (error?.status === 401 || error?.status === 403) && error.code !== UNANSWERED;
}

/** What to tell someone who pressed "Sign in with Windows" and it failed. */
export function windowsSignInMessage(error) {
  if (error?.code === UNANSWERED) {
    return "Windows sign-in did not work in this browser. Use a TaskBoard account, or ask your administrator.";
  }
  return error?.message ?? String(error);
}
