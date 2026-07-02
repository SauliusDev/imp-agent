import impIcon from "../assets/imp-agent.png";
import { Controls } from "./Controls";
import { OutputPanel } from "./OutputPanel";
import { Roadmap } from "./Roadmap";
import { TerminalPanel } from "./TerminalPanel";
import type { ImpState } from "../types";

function formatPct(value: number | null | undefined) {
  return value == null ? "?%" : `${Math.round(value)}%`;
}

function formatElapsed(seconds: number | undefined) {
  if (!seconds) return "0s";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

export function Dashboard({
  state,
  streamStatus,
  apiError,
}: {
  state: ImpState;
  streamStatus: string;
  apiError: string | null;
}) {
  const current = state.current;

  return (
    <main className="app-shell">
      <header className="topbar">
        <img src={impIcon} alt="" className="brand-icon" />
        <div className="headline">
          <h1>IMP Agent</h1>
          <p>
            <span>{state.provider}</span>
            <span>{state.epic_id || "no epic loaded"}</span>
            <span>{state.app_phase}</span>
          </p>
        </div>
        <div className="usage" aria-label="Usage">
          <span>5h {formatPct(state.usage.five_hour_pct)}</span>
          <span>7d {formatPct(state.usage.seven_day_pct)}</span>
          <span>Snt {formatPct(state.usage.sonnet_pct)}</span>
          <span>{state.usage.decision ?? "PROCEED"}</span>
        </div>
      </header>

      <Controls running={Boolean(current)} paused={state.app_phase === "paused"} />

      {apiError ? <div className="notice">{apiError}</div> : null}
      {state.halted ? <div className="notice danger">{state.halt_reason ?? "Pipeline halted"}</div> : null}

      <section className="workspace">
        <Roadmap rows={state.roadmap_rows} pendingCount={state.pending_stories.length} />

        <section className="panel current-panel">
          <div className="panel-title">
            <h2>Current Step</h2>
            <span className="status-pill">{streamStatus}</span>
          </div>
          {current ? (
            <dl className="meta-grid">
              <dt>Story</dt>
              <dd>{current.story_id}</dd>
              <dt>Step</dt>
              <dd>{current.step}</dd>
              <dt>Attempt</dt>
              <dd>
                {current.attempt}/{current.max_attempts || "open"}
              </dd>
              <dt>Elapsed</dt>
              <dd>{formatElapsed(current.elapsed_s)}</dd>
              <dt>Tmux</dt>
              <dd>{current.tmux_session ?? "starting"}</dd>
              <dt>Log</dt>
              <dd>{current.log_path}</dd>
            </dl>
          ) : (
            <p className="muted">Idle. Start the run when the server is ready.</p>
          )}
        </section>

        <OutputPanel lines={state.output_lines} />
        <TerminalPanel session={current?.tmux_session ?? null} />
      </section>
    </main>
  );
}
