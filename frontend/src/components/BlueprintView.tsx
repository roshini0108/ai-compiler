import { Download, FileCode2 } from "lucide-react";
import { useMemo, useState } from "react";
import { humanizeKey, prettyJson } from "../lib/format";
import type { CompileResult } from "../types";
import { JsonViewer } from "./JsonViewer";

type Props = {
  result?: CompileResult;
};

const tabs = ["ir", "db_schema", "api_schema", "rbac", "validation", "generated_files"] as const;

export function BlueprintView({ result }: Props) {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("ir");
  const blueprintJson = useMemo(() => (result ? prettyJson(result) : ""), [result]);

  if (!result) {
    return (
      <section className="blueprint-empty">
        <FileCode2 size={22} />
        <h2>Final blueprint</h2>
        <p>The complete application specification will appear here after the compiler finishes.</p>
      </section>
    );
  }

  const activeValue = result[activeTab];

  return (
    <section className="blueprint">
      <div className="blueprint-header">
        <div>
          <p className="eyebrow">Generated Blueprint</p>
          <h2>{result.app_name ?? "Compiled Application"}</h2>
        </div>
        <button type="button" className="secondary-button" onClick={() => downloadJson(blueprintJson)}>
          <Download size={16} />
          Export JSON
        </button>
      </div>

      <div className="tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={activeTab === tab ? "tab-active" : ""}
            onClick={() => setActiveTab(tab)}
          >
            {humanizeKey(tab)}
          </button>
        ))}
      </div>

      <JsonViewer value={activeValue} />
    </section>
  );
}

function downloadJson(json: string) {
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "application-blueprint.json";
  link.click();
  URL.revokeObjectURL(url);
}
