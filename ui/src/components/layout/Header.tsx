"use client";

import { useEffect, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { HealthStatus } from "@/lib/types";
import StatusDot from "@/components/shared/StatusDot";

export default function Header() {
  const { data: health } = useApi<HealthStatus>("/health", 10_000);
  const [clock, setClock] = useState("");

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(
        now.toLocaleTimeString("en-US", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const engineOk = health?.engine_running ?? false;
  const exchangeOk = !!health?.exchange;
  const dbOk = health?.db ?? false;
  const dataOk = health?.data_status === "ok";
  const alerts = health?.alerts ?? [];

  return (
    <header className="border-b border-border bg-card/60 backdrop-blur-sm">
      <div className="flex items-center justify-between px-4 py-2">
        {/* Title */}
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-bold text-accent tracking-wider uppercase">
            CryptoMega
          </h1>
          <span className="text-mono-xs text-gray-500">signal tournament</span>
        </div>

        {/* Health indicators */}
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <HealthDot label="Engine" ok={engineOk} />
          <HealthDot label="Exchange" ok={exchangeOk} />
          <HealthDot label="DB" ok={dbOk} />
          <HealthDot label="Data" ok={dataOk} />

          <span className="text-border">|</span>

          {/* WS status */}
          <div className="flex items-center gap-1.5">
            <StatusDot
              color={health ? "green" : "gray"}
              pulse={!health}
            />
            <span>WS</span>
          </div>

          <span className="text-border">|</span>

          {/* Clock */}
          <span className="font-medium text-gray-300 tabular-nums">
            {clock}
          </span>
        </div>
      </div>

      {/* Alert banner */}
      {alerts.length > 0 && (
        <div className="px-4 py-1.5 bg-danger/10 border-t border-danger/20 animate-slideDown">
          <div className="flex items-center gap-2 text-xs text-danger">
            <span className="font-bold">[ALERT]</span>
            <span>{alerts[alerts.length - 1]}</span>
            {alerts.length > 1 && (
              <span className="text-danger/60">
                (+{alerts.length - 1} more)
              </span>
            )}
          </div>
        </div>
      )}
    </header>
  );
}

function HealthDot({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <StatusDot color={ok ? "green" : "red"} pulse={!ok} />
      <span>{label}</span>
    </div>
  );
}
