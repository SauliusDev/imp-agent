export function TerminalPanel({ session }: { session: string | null }) {
  return (
    <section className="panel terminal-panel">
      <div className="panel-title">
        <div>
          <span className="panel-kicker">Shell</span>
          <h2>Terminal</h2>
        </div>
        <span>xterm fallback reserved</span>
      </div>
      <div className="terminal-placeholder">
        <p>{session ? `Tmux session: ${session}` : "No active tmux session"}</p>
      </div>
    </section>
  );
}
