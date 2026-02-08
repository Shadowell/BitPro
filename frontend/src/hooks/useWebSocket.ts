import { useEffect, useRef, useState, useCallback } from 'react';

type MessageHandler = (data: WebSocketMessage) => void;

interface WebSocketMessage {
  type?: string;
  channel?: string;
  exchange?: string;
  symbol?: string;
  data?: unknown;
  timestamp?: number;
  message?: string;
}

interface UseWebSocketOptions {
  url?: string;
  onMessage?: MessageHandler;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  reconnectAttempts?: number;
  reconnectInterval?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  subscribe: (channel: string, exchange: string, symbol?: string) => void;
  unsubscribe: (channel: string, exchange: string, symbol?: string) => void;
  sendMessage: (message: Record<string, unknown>) => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url = `ws://${window.location.host}/api/v1/ws`,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  // 连接 WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        reconnectCountRef.current = 0;
        onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketMessage;
          setLastMessage(data);
          onMessage?.(data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        onDisconnect?.();

        // 自动重连
        if (reconnectCountRef.current < reconnectAttempts) {
          reconnectCountRef.current++;
          console.log(`Reconnecting... (${reconnectCountRef.current}/${reconnectAttempts})`);
          setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        onError?.(error);
      };

      wsRef.current = ws;
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
    }
  }, [url, onConnect, onDisconnect, onError, onMessage, reconnectAttempts, reconnectInterval]);

  // 断开连接
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  // 发送消息
  const sendMessage = useCallback((message: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  // 订阅频道
  const subscribe = useCallback(
    (channel: string, exchange: string, symbol?: string) => {
      sendMessage({
        action: 'subscribe',
        channel,
        exchange,
        symbol,
      });
    },
    [sendMessage]
  );

  // 取消订阅
  const unsubscribe = useCallback(
    (channel: string, exchange: string, symbol?: string) => {
      sendMessage({
        action: 'unsubscribe',
        channel,
        exchange,
        symbol,
      });
    },
    [sendMessage]
  );

  // 心跳
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      sendMessage({ action: 'ping' });
    }, 30000);

    return () => clearInterval(interval);
  }, [isConnected, sendMessage]);

  // 初始化连接
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    isConnected,
    lastMessage,
    subscribe,
    unsubscribe,
    sendMessage,
  };
}

// 专用于 Ticker 的 Hook
export function useTickerWebSocket(exchange: string, symbol: string) {
  const [ticker, setTicker] = useState<Record<string, unknown> | null>(null);

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: (msg) => {
      if (msg.channel === 'ticker' && msg.symbol === symbol) {
        setTicker(msg.data as Record<string, unknown>);
      }
    },
  });

  useEffect(() => {
    if (isConnected && symbol) {
      subscribe('ticker', exchange, symbol);
      return () => unsubscribe('ticker', exchange, symbol);
    }
  }, [isConnected, exchange, symbol, subscribe, unsubscribe]);

  return { ticker, isConnected };
}

// 专用于批量 Ticker 的 Hook（首页用，订阅所有主流交易对）
export function useTickersWebSocket(exchange: string) {
  const [tickers, setTickers] = useState<Record<string, unknown>[]>([]);

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: (msg) => {
      if (msg.channel === 'tickers' && msg.exchange === exchange) {
        const data = msg.data;
        if (Array.isArray(data)) {
          setTickers(data);
        } else if (data && typeof data === 'object') {
          // 如果返回的是 object（symbol -> ticker），转成数组
          setTickers(Object.values(data as Record<string, unknown>) as Record<string, unknown>[]);
        }
      }
    },
  });

  useEffect(() => {
    if (isConnected) {
      subscribe('tickers', exchange);
      return () => unsubscribe('tickers', exchange);
    }
  }, [isConnected, exchange, subscribe, unsubscribe]);

  return { tickers, isConnected };
}

// 专用于资金费率的 Hook
export function useFundingWebSocket(exchange: string) {
  const [fundingRates, setFundingRates] = useState<Map<string, unknown>>(new Map());

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: (msg) => {
      if (msg.channel === 'funding' && msg.exchange === exchange) {
        setFundingRates((prev) => {
          const next = new Map(prev);
          next.set(msg.symbol || '', msg.data);
          return next;
        });
      }
    },
  });

  useEffect(() => {
    if (isConnected) {
      subscribe('funding', exchange);
      return () => unsubscribe('funding', exchange);
    }
  }, [isConnected, exchange, subscribe, unsubscribe]);

  return { fundingRates: Array.from(fundingRates.values()), isConnected };
}
