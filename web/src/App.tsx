import { useEffect, useState } from "react";
import { fetchState, subscribeState } from "./api";
import { Dashboard } from "./components/Dashboard";
import type { ImpState } from "./types";

export default function App() {
  const [state, setState] = useState<ImpState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState("connecting");

  useEffect(() => {
    let cancelled = false;

    fetchState()
      .then((nextState) => {
        if (!cancelled) {
          setState(nextState);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });

    const unsubscribe = subscribeState(
      (nextState) => {
        setState(nextState);
        setError(null);
        setStreamStatus("live");
      },
      (message) => setStreamStatus(message),
    );

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  if (error && !state) {
    return <main className="app-shell centered error-state">API unavailable: {error}</main>;
  }

  if (!state) {
    return <main className="app-shell centered">Loading IMP dashboard...</main>;
  }

  return <Dashboard state={state} streamStatus={streamStatus} apiError={error} />;
}
