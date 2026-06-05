import { Play, Square, WandSparkles } from "lucide-react";

type Props = {
  prompt: string;
  setPrompt: (prompt: string) => void;
  isCompiling: boolean;
  onSubmit: () => void;
  onCancel: () => void;
};

const examplePrompt =
  "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics.";

export function PromptForm({ prompt, setPrompt, isCompiling, onSubmit, onCancel }: Props) {
  const canSubmit = prompt.trim().length > 8 && !isCompiling;

  return (
    <section className="prompt-panel">
      <div className="prompt-title">
        <WandSparkles size={18} />
        <span>Product idea</span>
      </div>

      <textarea
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        placeholder={examplePrompt}
        spellCheck
      />

      <div className="prompt-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={() => setPrompt(examplePrompt)}
          disabled={isCompiling}
        >
          Use Example
        </button>
        {isCompiling ? (
          <button type="button" className="danger-button" onClick={onCancel}>
            <Square size={16} />
            Stop
          </button>
        ) : (
          <button type="button" className="primary-button" onClick={onSubmit} disabled={!canSubmit}>
            <Play size={16} />
            Compile
          </button>
        )}
      </div>
    </section>
  );
}
