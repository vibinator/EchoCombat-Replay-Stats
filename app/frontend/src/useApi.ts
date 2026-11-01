import { useEffect, useRef, useState } from "react";
import { onAnswerChange, RateLimitError, track } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

const MAX_AUTO_RETRIES = 3;

/**
 * Runs `load` whenever `key` changes; ignores responses from superseded requests.
 * An answer the cache already has shows at once; when the background refresh brings a different one the page
 * updates by itself (no loading state). If the server cannot be reached the page keeps what it shows.
 * When the server says "too many requests" it asks again by itself once the wait is over.
 */
export function useApi<T>(load: () => Promise<T>, key: string): ApiState<T> {
  const [state, setState] = useState<ApiState<T> & { key: string | null }>({ data: null, error: null, loading: true, key: null });
  const [retry, setRetry] = useState({ key, n: 0 });
  const [update, setUpdate] = useState({ key, n: 0 }); // an answer this page shows has changed
  const attempt = retry.key === key ? retry.n : 0;
  const version = update.key === key ? update.n : 0;

  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const { result, paths } = track(load);
    if (version === 0) setState((s) => ({ ...s, loading: true, error: null })); // an update keeps the page as it is
    result
      .then((data) => current && setState({ data, error: null, loading: false, key }))
      .catch((e: Error) => {
        if (!current) return;
        // what is shown for this key stays (the top bar says the server is busy); otherwise show why it failed
        setState((s) => (s.key === key && s.data !== null ? { ...s, loading: false } : { data: null, error: e.message, loading: false, key }));
        if (e instanceof RateLimitError && attempt < MAX_AUTO_RETRIES) {
          timer = setTimeout(() => setRetry({ key, n: attempt + 1 }), e.retryAfter * 1000 + 300);
        }
      });
    const stop = onAnswerChange((path) => {
      if (current && paths.has(path)) setUpdate((u) => ({ key, n: (u.key === key ? u.n : 0) + 1 }));
    });
    return () => {
      current = false;
      clearTimeout(timer);
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt, version]);

  return { data: state.data, error: state.error, loading: state.loading };
}

/** Calls `fn` now and every `ms` while the tab is visible; a hidden tab asks nothing (and catches up when shown). */
export function useWhileVisible(fn: () => void, ms: number): void {
  const latest = useRef(fn);
  latest.current = fn;
  useEffect(() => {
    let last = 0;
    let timer: ReturnType<typeof setInterval> | undefined;
    const run = () => {
      last = Date.now();
      latest.current();
    };
    const start = () => {
      clearInterval(timer);
      if (document.hidden) return;
      if (Date.now() - last >= ms) run();
      timer = setInterval(run, ms);
    };
    start();
    document.addEventListener("visibilitychange", start);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", start);
    };
  }, [ms]);
}
