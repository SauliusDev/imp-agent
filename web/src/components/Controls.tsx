import { Pause, Play, RefreshCw, RotateCw, Square, Terminal } from "lucide-react";
import { useState } from "react";
import { sendControl } from "../api";
import type { ControlAction } from "../types";

type ControlButton = {
  action: ControlAction;
  label: string;
  icon: typeof Play;
  disabled?: boolean;
};

export function Controls({ running, paused }: { running: boolean; paused: boolean }) {
  const [busyAction, setBusyAction] = useState<ControlAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const buttons: ControlButton[] = [
    { action: "run", label: "Run", icon: Play, disabled: running },
    { action: "pause", label: "Pause", icon: Pause, disabled: !running || paused },
    { action: "resume", label: "Resume", icon: RefreshCw, disabled: !paused },
    { action: "quit", label: "Quit", icon: Square },
    { action: "reload-config", label: "Reload", icon: RotateCw },
  ];

  async function handleControl(action: ControlAction) {
    setBusyAction(action);
    setError(null);
    try {
      await sendControl(action);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <section className="control-strip" aria-label="Runner controls">
      <div className="control-buttons">
        {buttons.map(({ action, label, icon: Icon, disabled }) => (
          <button
            key={action}
            type="button"
            onClick={() => void handleControl(action)}
            disabled={disabled || busyAction !== null}
            title={label}
          >
            <Icon size={16} aria-hidden="true" />
            <span>{busyAction === action ? "Sending" : label}</span>
          </button>
        ))}
        <button type="button" disabled title="Terminal fallback is reserved for a later task">
          <Terminal size={16} aria-hidden="true" />
          <span>Terminal</span>
        </button>
      </div>
      {error ? <p className="control-error">{error}</p> : null}
    </section>
  );
}
