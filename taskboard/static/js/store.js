/** App-wide state: the bootstrap document (me, people, projects...), its lookups, a data revision. */
import { api } from "./api.js";
import { indexBoot } from "./lib/lookup.js";
import { useEffect, useState } from "./ui.js";

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

/** Reload who-am-I and reference data (after login, logout or changes to projects/people). */
export async function refreshBoot() {
  try {
    const boot = await api.get("/bootstrap");
    setState({ status: "ready", boot, lookup: indexBoot(boot), error: null, revision: state.revision + 1 });
  } catch (error) {
    setState({ status: "error", error });
  }
}

/** Tell views that data changed, so they reload what they show. */
export function dataChanged() {
  setState({ revision: state.revision + 1 });
}
