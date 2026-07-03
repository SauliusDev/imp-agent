export function OutputPanel({ lines }: { lines: string[] }) {
  const content = lines.length ? lines.join("\n") : "Waiting for agent output...";

  return (
    <section className="panel output-panel">
      <div className="panel-title">
        <div>
          <span className="panel-kicker">Stream</span>
          <h2>Agent Output</h2>
        </div>
        <span>{lines.length} lines</span>
      </div>
      <pre>{content}</pre>
    </section>
  );
}
