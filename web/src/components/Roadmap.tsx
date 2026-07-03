import type { RoadmapRow } from "../types";

function statusLabel(status: string) {
  return status.replace(/[-_]/g, " ");
}

export function Roadmap({ rows, pendingCount }: { rows: RoadmapRow[]; pendingCount: number }) {
  return (
    <section className="panel roadmap-panel">
      <div className="panel-title">
        <div>
          <span className="panel-kicker">Ledger</span>
          <h2>Roadmap</h2>
        </div>
        <span>{pendingCount} pending</span>
      </div>
      {rows.length ? (
        <ol className="roadmap-list">
          {rows.map(([type, id, status, detail, blocked], index) => (
            <li key={`${type}-${id}-${index}`} className={`roadmap-row ${type} ${status}`}>
              <span className="status-dot" aria-hidden="true" />
              <span className="row-id">{id}</span>
              <span className="row-detail">{detail || type}</span>
              <span className="row-status">{statusLabel(status)}</span>
              {blocked ? <em>{blocked}</em> : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">No roadmap rows loaded.</p>
      )}
    </section>
  );
}
