import { ChevronDown, Database, KeyRound, Layers3, Route, ShieldCheck, Wrench } from "lucide-react";
import { useState } from "react";
import { countItems, elapsed } from "../lib/format";
import type { StageState } from "../types";
import { JsonViewer } from "./JsonViewer";

type Props = {
  stage: StageState;
};

export function StageCard({ stage }: Props) {
  const [open, setOpen] = useState(stage.stage <= 2);
  const counts = summarize(stage);

  return (
    <article className={`stage-card stage-card-${stage.status}`}>
      <button type="button" className="stage-card-header" onClick={() => setOpen((value) => !value)}>
        <span className="stage-icon">{stageIcon(stage.stage)}</span>
        <span className="stage-heading">
          <span className="stage-kicker">Stage {stage.stage}</span>
          <strong>{stage.label}</strong>
        </span>
        <span className={`stage-badge badge-${stage.status}`}>{stage.status}</span>
        <span className="stage-time">{elapsed(stage.startedAt, stage.finishedAt)}</span>
        <ChevronDown className={open ? "chevron-open" : ""} size={18} />
      </button>

      {counts.length ? (
        <div className="stage-metrics">
          {counts.map((item) => (
            <span key={item.label}>{item.label}: {item.value}</span>
          ))}
        </div>
      ) : null}

      {open ? (
        <div className="stage-body">
          {stage.output ? <JsonViewer value={stage.output} compact /> : <p className="muted">Waiting for this stage to emit output.</p>}
        </div>
      ) : null}
    </article>
  );
}

function stageIcon(stage: number) {
  const icons = [Layers3, Database, Database, Route, KeyRound, ShieldCheck, Wrench, Layers3];
  const Icon = icons[stage - 1] ?? Layers3;
  return <Icon size={18} />;
}

function summarize(stage: StageState) {
  const output = stage.output;
  const metricKeys = ["entities", "roles", "features", "tables", "endpoints", "policies", "route_guards", "errors", "warnings"];

  return metricKeys
    .map((key) => ({ label: key.replace(/_/g, " "), value: countItems(output, key) }))
    .filter((item): item is { label: string; value: number } => item.value !== undefined);
}
