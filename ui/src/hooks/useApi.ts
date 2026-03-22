"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface UseApiResult<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refetch: () => void;
}

/**
 * Generic data-fetching hook with optional polling.
 *
 * @param path    - API path (e.g. "/paper/leaderboard")
 * @param interval - Polling interval in milliseconds. 0 = no polling (default).
 */
export function useApi<T>(
  path: string | null,
  interval: number = 0,
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    if (!path) return;
    try {
      setLoading((prev) => (data == null ? true : prev)); // only show loading on first fetch
      const result = await api<T>(path);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (interval > 0 && path) {
      intervalRef.current = setInterval(fetchData, interval);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchData, interval, path]);

  return { data, error, loading, refetch: fetchData };
}
