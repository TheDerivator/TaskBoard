/** Data hooks: `useApi` loads a GET endpoint and reloads when inputs or the data revision change. */
import { api } from "./api.js";
import { useAppState } from "./store.js";
import { useCallback, useEffect, useRef, useState } from "./ui.js";

/**
 * @param {string|null} path  API path such as "/tasks"; null skips loading
 * @param {object} [params]   query parameters
 * @returns {{data: any, error: ?Error, loading: boolean, reload: () => void}}
 */
export function useApi(path, params = undefined) {
  const { revision } = useAppState();
  const [result, setResult] = useState({ data: null, error: null, loading: path != null });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);
  const key = JSON.stringify(params ?? null);

  useEffect(() => {
    if (path == null) return;
    const ticket = ++latest.current;
    setResult((r) => ({ ...r, loading: true }));
    api.get(path, params).then(
      (data) => ticket === latest.current && setResult({ data, error: null, loading: false }),
      (error) => ticket === latest.current && setResult({ data: null, error, loading: false }),
    );
  }, [path, key, revision, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...result, reload };
}

/** Set the browser tab title for the current view. */
export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · Team Tasks` : "Team Tasks";
  }, [title]);
}
