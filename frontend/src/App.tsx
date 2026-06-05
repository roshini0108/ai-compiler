import { useEffect, useMemo, useRef, useState } from "react";
import { compilePrompt, getHealth } from "./api/compiler";
import { BlueprintView } from "./components/BlueprintView";
import { ErrorPanel } from "./components/ErrorPanel";
import { PromptForm } from "./components/PromptForm";
import { StageCard } from "./components/StageCard";
import { StageTimeline } from "./components/StageTimeline";
import { StatusHeader } from "./components/StatusHeader";
import type { CompileEvent, CompileResult, HealthResponse, StageState } from "./types";

const initialStages: StageState[] = [
  { stage: 1, label: "Intent Extraction", status: "idle" },
  { stage: 2, label: "Building IR", status: "idle" },
  { stage: 3, label: "Database Schema", status: "idle" },
  { stage: 4, label: "API Schema", status: "idle" },
  { stage: 5, label: "Auth & RBAC", status: "idle" },
  { stage: 6, label: "Cross-Layer Validation", status: "idle" },
  { stage: 7, label: "Repair Engine", status: "idle" },
  { stage: 8, label: "Generating Runtime", status: "idle" }
];

function App() {
  const [prompt, setPrompt] = useState("");
  const [stages, setStages] = useState<StageState[]>(initialStages);
  const [health, setHealth] = useState<HealthResponse>();
  const [healthError, setHealthError] = useState<string>();
  const [isCheckingHealth, setIsCheckingHealth] = useState(true);
  const [isCompiling, setIsCompiling] = useState(false);
  const [result, setResult] = useState<CompileResult>();
  const [error, setError] = useState<{ message: string; detail?: string }>();
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    getHealth()
      .then((response) => {
        setHealth(response);
        setHealthError(undefined);
      })
      .catch((err: Error) => setHealthError(err.message))
      .finally(() => setIsCheckingHealth(false));
  }, []);

  const completedCount = useMemo(
    () => stages.filter((stage) => stage.status === "done" || stage.status === "skipped").length,
    [stages]
  );

  async function handleSubmit() {
    const trimmedPrompt = prompt.trim();

    if (!trimmedPrompt) {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setStages(initialStages.map((stage) => ({ ...stage, status: "idle", output: undefined })));
    setResult(undefined);
    setError(undefined);
    setIsCompiling(true);

    try {
      await compilePrompt(trimmedPrompt, handleCompilerEvent, controller.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError({ message: (err as Error).message });
        markCurrentStageFailed();
      }
    } finally {
      abortRef.current = null;
      setIsCompiling(false);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    setIsCompiling(false);
  }

  function handleCompilerEvent(event: CompileEvent) {
    if (event.type === "stage_start") {
      updateStage(event.stage, {
        label: event.label,
        status: "running",
        startedAt: Date.now(),
        finishedAt: undefined
      });
      return;
    }

    if (event.type === "stage_done") {
      updateStage(event.stage, {
        label: event.label,
        status: "done",
        output: event.output,
        finishedAt: Date.now()
      });
      return;
    }

    if (event.type === "stage_skip") {
      updateStage(event.stage, {
        label: event.label,
        status: "skipped",
        finishedAt: Date.now()
      });
      return;
    }

    if (event.type === "complete") {
      setResult(event);
      return;
    }

    if (event.type === "error") {
      setError({ message: event.message, detail: event.detail });
      markCurrentStageFailed();
    }
  }

  function updateStage(stageNumber: number, patch: Partial<StageState>) {
    setStages((current) =>
      current.map((stage) =>
        stage.stage === stageNumber
          ? {
              ...stage,
              ...patch,
              startedAt: patch.startedAt ?? stage.startedAt
            }
          : stage
      )
    );
  }

  function markCurrentStageFailed() {
    setStages((current) => {
      const running = current.find((stage) => stage.status === "running");
      if (!running) {
        return current;
      }

      return current.map((stage) =>
        stage.stage === running.stage ? { ...stage, status: "error", finishedAt: Date.now() } : stage
      );
    });
  }

  return (
    <main className="shell">
      <StatusHeader health={health} healthError={healthError} isChecking={isCheckingHealth} />

      <section className="workspace">
        <div className="left-column">
          <PromptForm
            prompt={prompt}
            setPrompt={setPrompt}
            isCompiling={isCompiling}
            onSubmit={handleSubmit}
            onCancel={handleCancel}
          />

          <div className="progress-panel">
            <div className="progress-copy">
              <span>{completedCount} / {stages.length} stages resolved</span>
              <strong>{isCompiling ? "Compilation running" : result ? "Compilation complete" : "Ready"}</strong>
            </div>
            <div className="progress-track">
              <span style={{ width: `${(completedCount / stages.length) * 100}%` }} />
            </div>
            <StageTimeline stages={stages} />
          </div>
        </div>

        <div className="right-column">
          {error ? <ErrorPanel message={error.message} detail={error.detail} /> : null}

          <section className="stage-grid">
            {stages.map((stage) => (
              <StageCard key={stage.stage} stage={stage} />
            ))}
          </section>
        </div>
      </section>

      <BlueprintView result={result} />
    </main>
  );
}

export default App;
