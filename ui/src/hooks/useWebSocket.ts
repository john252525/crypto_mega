"use client";

import { useEffect, useRef } from "react";
import { API_BASE } from "@/lib/api";

/**
 * Generic reconnecting WebSocket hook.
 *
 * Connects to `ws(s)://<host><path>`, automatically reconnects on close
 * after a 3-second delay, and cleans up on unmount.
 *
 * @param path      - WebSocket path (e.g. "/ws/signals")
 * @param onMessage - Callback invoked with parsed JSON for each message
 */
export function useWebSocket(
  path: string | null,
  onMessage: (data: unknown) => void,
): void {
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!path) return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let unmounted = false;

    function connect() {
      if (unmounted) return;

      // Derive ws:// or wss:// URL from API_BASE or current page location.
      let wsUrl: string;
      if (API_BASE.startsWith("http")) {
        wsUrl = API_BASE.replace(/^http/, "ws") + path;
      } else {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsUrl = `${proto}//${window.location.host}${API_BASE}${path}`;
      }

      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          onMessageRef.current(data);
        } catch {
          // Non-JSON message; pass raw string
          onMessageRef.current(event.data);
        }
      };

      ws.onclose = () => {
        if (!unmounted) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        // onerror is always followed by onclose, which handles reconnect.
        ws?.close();
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null; // prevent reconnect on intentional close
        ws.close();
      }
    };
  }, [path]);
}
