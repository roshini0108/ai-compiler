import { CheckCircle2, CircleAlert, Cpu, Loader2, Server } from "lucide-react";
import type { HealthResponse } from "../types";

type Props = {
  health?: HealthResponse;
  healthError?: string;
  isChecking: boolean;
};

export function StatusHeader({ health, healthError, isChecking }: Props) {
  const ready = health?.ready && health.status === "ok";

  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">Compiler Control Room</p>
        <h1>AI Application Compiler</h1>
      </div>

      <div className="status-pills" aria-live="polite">
        <span className={`pill ${ready ? "pill-ok" : healthError ? "pill-error" : ""}`}>
          {isChecking ? <Loader2 className="spin" size={16} /> : ready ? <CheckCircle2 size={16} /> : <Server size={16} />}
          Backend {ready ? "online" : healthError ? "offline" : "checking"}
        </span>
        <span className="pill">
          <Cpu size={16} />
          {health?.model ?? "model unknown"}
        </span>
        {healthError ? (
          <span className="pill pill-error">
            <CircleAlert size={16} />
            {healthError}
          </span>
        ) : null}
      </div>
    </header>
  );
}
