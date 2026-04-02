import { useEffect, useState, useCallback } from 'react';
import { websocketManager, type WSMessage } from '../services/websocketManager';

type MessageHandler = (data: WSMessage) => void;

export interface RealtimeTicker {
  symbol: string;
  last: number;
  high?: number;
  low?: number;
  volume?: number;
  quoteVolume?: number;
  quote_volume?: number;
  changePercent?: number;
  change_percent?: number;
}

interface UseWebSocketOptions {
  url?: string;
  onMessage?: MessageHandler;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WSMessage | null;
  subscribe: (channel: string, exchange: string, symbol?: string) => void;
  unsubscribe: (channel: string, exchange: string, symbol?: string) => void;
  sendMessage: (message: Record<string, unknown>) => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url = `ws://${window.location.host}/api/v2/ws`,
    onMessage,
    onConnect,
    onDisconnect,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  useEffect(() => {
    websocketManager.connect(url);

    const handler = (msg: WSMessage) => {
      setLastMessage(msg);

      if (msg.event === 'connected' || msg.type === 'connected') {
        setIsConnected(true);
        onConnect?.();
      } else if (msg.event === 'disconnected' || msg.type === 'disconnected') {
        setIsConnected(false);
        onDisconnect?.();
      }

      onMessage?.(msg);
    };

    websocketManager.addHandler(handler);
    setIsConnected(websocketManager.isConnected());

    return () => {
      websocketManager.removeHandler(handler);
    };
  }, [url, onMessage, onConnect, onDisconnect]);

  const sendMessage = useCallback((message: Record<string, unknown>) => {
    websocketManager.send(message);
  }, []);

  const subscribe = useCallback((channel: string, exchange: string, symbol?: string) => {
    websocketManager.subscribe(channel, exchange, symbol);
  }, []);

  const unsubscribe = useCallback((channel: string, exchange: string, symbol?: string) => {
    websocketManager.unsubscribe(channel, exchange, symbol);
  }, []);

  return {
    isConnected,
    lastMessage,
    subscribe,
    unsubscribe,
    sendMessage,
  };
}

export function useTickerWebSocket(exchange: string, symbol: string) {
  const [ticker, setTicker] = useState<RealtimeTicker | null>(null);

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: (msg) => {
      if (msg.channel === 'ticker' && msg.symbol === symbol) {
        setTicker(msg.data as RealtimeTicker);
      }
    },
  });

  useEffect(() => {
    if (isConnected && symbol) {
      subscribe('ticker', exchange, symbol);
      return () => unsubscribe('ticker', exchange, symbol);
    }
    return undefined;
  }, [isConnected, exchange, symbol, subscribe, unsubscribe]);

  return { ticker, isConnected };
}

export function useTickersWebSocket(exchange: string) {
  const [tickers, setTickers] = useState<RealtimeTicker[]>([]);

  const { isConnected, subscribe, unsubscribe } = useWebSocket({
    onMessage: (msg) => {
      if (msg.channel === 'tickers' && msg.exchange === exchange) {
        const data = msg.data;
        if (Array.isArray(data)) {
          setTickers(data as RealtimeTicker[]);
        } else if (data && typeof data === 'object') {
          setTickers(Object.values(data as Record<string, RealtimeTicker>));
        }
      }
    },
  });

  useEffect(() => {
    if (isConnected) {
      subscribe('tickers', exchange);
      return () => unsubscribe('tickers', exchange);
    }
    return undefined;
  }, [isConnected, exchange, subscribe, unsubscribe]);

  return { tickers, isConnected };
}

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
    return undefined;
  }, [isConnected, exchange, subscribe, unsubscribe]);

  return { fundingRates: Array.from(fundingRates.values()), isConnected };
}
