import { useEffect, useState } from "react";
import { RateLimitError } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

const MAX_AUTO_RETRIES = 3;

/**
 * Runs `load` whenever `key` changes; ignores responses from superseded requests.
 * When the server says "too many requests" it asks again by itself once the wait is over.
 */
export function useApi<T>(load: () => Promise<T>, key: string): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, error: null, loading: true });
  const [retry, setRetry] = useState({ key, n: 0 });
  const attempt = retry.key === key ? retry.n : 0;

  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setState((s) => ({ ...s, loading: true, error: null }));
    load()
      .then((data) => current && setState({ data, error: null, loading: false }))
      .catch((e: Error) => {
        if (!current) return;
        setState({ data: null, error: e.message, loading: false });
        if (e instanceof RateLimitError && attempt < MAX_AUTO_RETRIES) {
          timer = setTimeout(() => setRetry({ key, n: attempt + 1 }), e.retryAfter * 1000 + 300);
        }
      });
    return () => {
      current = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  return state;
}
