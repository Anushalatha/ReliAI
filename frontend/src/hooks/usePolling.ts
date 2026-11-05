import { useCallback, useEffect, useRef, useState } from "react";

export function usePolling<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  intervalMs = 0,
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const loaderRef = useRef(loader);
  const activeRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  loaderRef.current = loader;

  const refresh = useCallback(async () => {
    if (busyRef.current || document.visibilityState === "hidden") return;
    busyRef.current = true;
    const controller = new AbortController();
    activeRef.current = controller;
    setRefreshing(true);
    try {
      const value = await loaderRef.current(controller.signal);
      if (!controller.signal.aborted) {
        setData(value);
        setError(null);
        setUpdatedAt(new Date());
      }
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason);
    } finally {
      if (activeRef.current === controller) activeRef.current = null;
      busyRef.current = false;
      if (!controller.signal.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onManualRefresh = () => void refresh();
    window.addEventListener("reliai:refresh", onManualRefresh);
    const timer = intervalMs ? window.setInterval(() => void refresh(), intervalMs) : undefined;
    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
      else activeRef.current?.abort();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (timer) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("reliai:refresh", onManualRefresh);
      activeRef.current?.abort();
    };
  }, [intervalMs, refresh]);

  return { data, loading, refreshing, error, updatedAt, refresh };
}
