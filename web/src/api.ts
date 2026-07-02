import type { ControlAction, ImpState } from "./types";

const API_BASE = import.meta.env.VITE_IMP_API_BASE ?? "";

export async function fetchState(): Promise<ImpState> {
  const response = await fetch(`${API_BASE}/api/state`);
  if (!response.ok) {
    throw new Error(`state request failed: ${response.status}`);
  }
  return response.json() as Promise<ImpState>;
}

export async function sendControl(action: ControlAction): Promise<void> {
  const response = await fetch(`${API_BASE}/api/${action}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`${action} failed: ${response.status}`);
  }
}

export function subscribeState(onState: (state: ImpState) => void, onError?: (message: string) => void): () => void {
  const source = new EventSource(`${API_BASE}/api/events`);
  source.onmessage = (event) => onState(JSON.parse(event.data) as ImpState);
  source.onerror = () => onError?.("state stream disconnected");
  return () => source.close();
}
