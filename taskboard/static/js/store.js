/** App-wide state: the bootstrap document (me, people, projects...), its lookups, a data revision. */
import { api } from "./api.js";
import { indexBoot } from "./lib/lookup.js";
import { isWindowsRefusal, shouldTryWindowsSignIn } from "./lib/signin.js";
import { useEffect, useState } from "./ui.js";
import { windowsSignIn, windowsSignInTried } from "./windows-signin.js";

let state = { status: "loading", boot: null, lookup: null, error: null, revision: 0 };
const listeners = new Set();

function setState(patch) {
  state = { ...state, ...patch };
  for (const listener of listeners) listener(state);
}

export function getState() {
  return state;
}

export function useAppState() {
  const [snapshot, setSnapshot] = useState(state);
  useEffect(() => {
    listeners.add(setSnapshot);
    setSnapshot(state);
    return () => listeners.delete(setSnapshot);
  }, []);
  return snapshot;
}

function show(boot) {
  setState({ status: "ready", boot, lookup: indexBoot(boot), error: null, revision: state.revision + 1 });
}

/** Reload who-am-I and reference data (after login, logout or changes to projects/people). */
export async function refreshBoot() {
  try {
    show(await api.get("/bootstrap"));
  } catch (error) {
    setState({ status: "error", error });
  }
}

/**
 * First load. Where the server offers automatic Windows sign-in, a visitor is signed in before
 * anything is shown. Resolves to a refusal worth telling the visitor about, or null.
 */
export async function startUp() {
  let refusal = null;
  try {
    let boot = await api.get("/bootstrap");
    if (shouldTryWindowsSignIn(boot.me, windowsSignInTried())) {
      try {
        await windowsSignIn();
        boot = await api.get("/bootstrap");
      } catch (error) {
        if (isWindowsRefusal(error)) refusal = error;
      }
    }
    show(boot);
  } catch (error) {
    setState({ status: "error", error });
  }
  return refusal;
}

/** Tell views that data changed, so they reload what they show. */
export function dataChanged() {
  setState({ revision: state.revision + 1 });
}
