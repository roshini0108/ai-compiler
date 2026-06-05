export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type StageStatus = "idle" | "running" | "done" | "skipped" | "error";

export type StageState = {
  stage: number;
  label: string;
  status: StageStatus;
  output?: JsonValue;
  startedAt?: number;
  finishedAt?: number;
};

export type HealthResponse = {
  status: string;
  model?: string;
  ready?: boolean;
};

export type CompileEvent =
  | {
      type: "stage_start";
      stage: number;
      label: string;
    }
  | {
      type: "stage_done";
      stage: number;
      label: string;
      output: JsonValue;
    }
  | {
      type: "stage_skip";
      stage: number;
      label: string;
    }
  | {
      type: "complete";
      ir: JsonValue;
      db_schema: JsonValue;
      api_schema: JsonValue;
      rbac: JsonValue;
      validation: JsonValue;
      generated_files: Record<string, string>;
      app_name?: string;
    }
  | {
      type: "error";
      message: string;
      detail?: string;
    };

export type CompileResult = Extract<CompileEvent, { type: "complete" }>;
