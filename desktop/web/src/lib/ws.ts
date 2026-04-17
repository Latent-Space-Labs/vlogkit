import type { AnalyzeEvent } from "./events";
import { getBridge } from "./bridge";

/**
 * Connect to the per-project event stream. Returns a disconnect function.
 * Auto-reconnects with exponential backoff (500 ms → 8 s).
 */
export function connectEventStream(
  projectId: string,
  onEvent: (evt: AnalyzeEvent) => void,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 500;

  function open() {
    if (closed) return;
    const { apiPort, token } = getBridge();
    if (!apiPort || !token) {
      // Bridge not ready yet (first paint / SSR hydration quirk). Retry soon.
      setTimeout(open, 500);
      return;
    }
    const url = `ws://127.0.0.1:${apiPort}/projects/${projectId}/events?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(url);
    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data));
      } catch (e) {
        console.error("ws parse error", e);
      }
    };
    ws.onopen = () => {
      backoff = 500;
    };
    ws.onclose = () => {
      if (closed) return;
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 8000);
    };
    ws.onerror = () => {
      ws?.close();
    };
  }

  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
