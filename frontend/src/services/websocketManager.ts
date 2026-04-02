export interface WSMessage {
  type?: string;
  event?: string;
  channel?: string;
  exchange?: string;
  symbol?: string;
  data?: unknown;
  timestamp?: number;
  message?: string;
}

type Handler = (message: WSMessage) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private readonly handlers = new Set<Handler>();
  private readonly subscriptions = new Set<string>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 8;
  private reconnectInterval = 3000;
  private heartbeatTimer: number | null = null;
  private manualClose = false;
  private url = '';

  connect(url: string) {
    this.url = url;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.manualClose = false;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.flushSubscriptions();
      this.startHeartbeat();
      this.emit({ type: 'connected', event: 'connected' });
    };

    this.ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as WSMessage;
        this.emit(parsed);
      } catch {
        // ignore malformed payload
      }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.emit({ type: 'disconnected', event: 'disconnected' });
      if (!this.manualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts += 1;
        window.setTimeout(() => this.connect(this.url), this.reconnectInterval);
      }
    };

    this.ws.onerror = () => {
      this.emit({ type: 'error', event: 'error' });
    };
  }

  disconnect() {
    this.manualClose = true;
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
  }

  addHandler(handler: Handler) {
    this.handlers.add(handler);
  }

  removeHandler(handler: Handler) {
    this.handlers.delete(handler);
  }

  subscribe(channel: string, exchange: string, symbol?: string) {
    const key = this.makeKey(channel, exchange, symbol);
    this.subscriptions.add(key);
    this.send({ action: 'subscribe', channel, exchange, symbol });
  }

  unsubscribe(channel: string, exchange: string, symbol?: string) {
    const key = this.makeKey(channel, exchange, symbol);
    this.subscriptions.delete(key);
    this.send({ action: 'unsubscribe', channel, exchange, symbol });
  }

  send(payload: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private emit(message: WSMessage) {
    this.handlers.forEach((handler) => handler(message));
  }

  private makeKey(channel: string, exchange: string, symbol?: string) {
    return `${channel}:${exchange}:${symbol || ''}`;
  }

  private flushSubscriptions() {
    this.subscriptions.forEach((key) => {
      const first = key.indexOf(':');
      const second = key.indexOf(':', first + 1);
      if (first < 0 || second < 0) {
        return;
      }
      const channel = key.slice(0, first);
      const exchange = key.slice(first + 1, second);
      const symbol = key.slice(second + 1);
      this.send({ action: 'subscribe', channel, exchange, symbol: symbol || undefined });
    });
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      this.send({ action: 'ping' });
    }, 30000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }
}

export const websocketManager = new WebSocketManager();
