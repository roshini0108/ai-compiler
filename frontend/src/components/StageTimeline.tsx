import { Check, Circle, Loader2, Minus, X } from "lucide-react";
import type { StageState } from "../types";

type Props = {
  stages: StageState[];
};

export function StageTimeline({ stages }: Props) {
  return (
    <section className="timeline" aria-label="Compilation progress">
      {stages.map((stage) => (
        <div key={stage.stage} className={`timeline-item timeline-${stage.status}`}>
          <span className="timeline-icon">{iconFor(stage.status)}</span>
          <span className="timeline-label">{stage.label}</span>
        </div>
      ))}
    </section>
  );
}

function iconFor(status: StageState["status"]) {
  if (status === "running") {
    return <Loader2 className="spin" size={15} />;
  }

  if (status === "done") {
    return <Check size={15} />;
  }

  if (status === "skipped") {
    return <Minus size={15} />;
  }

  if (status === "error") {
    return <X size={15} />;
  }

  return <Circle size={15} />;
}
