export function TerminalPanel({ session }: { session: string | null }) {
  return (
    <section className="panel terminal-panel">
      <div className="panel-title">
        <h2>Terminal</h2>
        <span>xterm fallback reserved</span>
      </div>
      <div className="terminal-placeholder">
        <p>{session ? `Tmux session: ${session}` : "No active tmux session"}</p>
      </div>
    </section>
  );
}
