// Server-Sent Events (SSE) connection manager.
//
// SSE is a browser API for receiving a stream of events from the server
// over a persistent HTTP connection. Unlike WebSockets, SSE is one-way
// (server -> browser only) and reconnects automatically if the connection drops.
//
// Why a shared module instead of connecting inside each component?
// The backend creates one asyncio.Queue per SSE connection. If StatsPanel
// and LiveFeed each created their own EventSource, we'd have two queues and
// two connections. A shared module creates one EventSource and dispatches
// to all registered callbacks.

type UpdateCallback = () => void;

class SseManager {
  private source: EventSource | null = null;
  private callbacks: Set<UpdateCallback> = new Set();

  connect(): void {
    if (this.source) return;  // already connected

    // EventSource opens a persistent connection to /api/events.
    // The proxy in vite.config.ts forwards this to FastAPI at localhost:8000.
    this.source = new EventSource('/api/events');

    // The backend sends events with type "update" via EventBus.notify().
    // addEventListener("update", ...) registers for that specific event type.
    this.source.addEventListener('update', () => {
      for (const cb of this.callbacks) cb();
    });

    this.source.onerror = () => {
      // EventSource reconnects automatically — no manual retry needed.
      // This callback is informational only.
      console.warn('[SSE] connection error, will auto-reconnect');
    };
  }

  disconnect(): void {
    this.source?.close();
    this.source = null;
  }

  subscribe(cb: UpdateCallback): () => void {
    this.callbacks.add(cb);
    // Return an unsubscribe function — callers use this in onDestroy()
    return () => this.callbacks.delete(cb);
  }
}

// Singleton: one SSE connection for the whole app
export const sseManager = new SseManager();
