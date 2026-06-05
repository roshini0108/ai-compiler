import { CircleAlert } from "lucide-react";

type Props = {
  message: string;
  detail?: string;
};

export function ErrorPanel({ message, detail }: Props) {
  return (
    <section className="error-panel" role="alert">
      <div className="error-heading">
        <CircleAlert size={18} />
        <strong>Compilation stopped</strong>
      </div>
      <p>{message}</p>
      {detail ? <pre>{detail}</pre> : null}
    </section>
  );
}
