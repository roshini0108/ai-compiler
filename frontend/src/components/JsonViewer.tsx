import { Copy } from "lucide-react";
import { prettyJson } from "../lib/format";

type Props = {
  value: unknown;
  compact?: boolean;
};

export function JsonViewer({ value, compact = false }: Props) {
  const json = prettyJson(value);

  return (
    <div className={`json-viewer ${compact ? "json-viewer-compact" : ""}`}>
      <button
        type="button"
        className="icon-button"
        aria-label="Copy JSON"
        title="Copy JSON"
        onClick={() => navigator.clipboard.writeText(json)}
      >
        <Copy size={15} />
      </button>
      <pre>{json}</pre>
    </div>
  );
}
