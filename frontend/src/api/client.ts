import axios, { type AxiosRequestConfig } from 'axios';
import type {
  Ticker,
  Kline,
  OrderBook,
  FundingRate,
  FundingOpportunity,
  Strategy,
} from '../types';

const API_BASE = '/api/v2';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

function snakeToCamel(input: string): string {
  return input.replace(/_([a-z])/g, (_, s: string) => s.toUpperCase());
}

function camelToSnake(input: string): string {
  return input.replace(/[A-Z]/g, (s) => `_${s.toLowerCase()}`);
}

function camelizeDeep<T = any>(value: any): T {
  if (Array.isArray(value)) {
    return value.map((item) => camelizeDeep(item)) as T;
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).reduce((acc, [key, val]) => {
      acc[snakeToCamel(key)] = camelizeDeep(val);
      return acc;
    }, {} as Record<string, any>) as T;
  }
  return value as T;
}

function snakifyDeep<T = any>(value: any): T {
  if (Array.isArray(value)) {
    return value.map((item) => snakifyDeep(item)) as T;
  }
  if (value && typeof value === 'object' && !(value instanceof FormData)) {
    return Object.entries(value).reduce((acc, [key, val]) => {
      acc[camelToSnake(key)] = snakifyDeep(val);
      return acc;
    }, {} as Record<string, any>) as T;
  }
  return value as T;
}

function unwrapEnvelope(raw: any): any {
  if (raw && typeof raw === 'object' && 'success' in raw && 'data' in raw) {
    return raw.data;
  }
  return raw;
}

async function getReq<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const normalized = config ? { ...config, params: snakifyDeep(config.params) } : undefined;
  const raw = await api.get(url, normalized);
  return camelizeDeep<T>(unwrapEnvelope(raw));
}

async function postReq<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const normalized = config ? { ...config, params: snakifyDeep(config.params) } : undefined;
  const raw = await api.post(url, snakifyDeep(data), normalized);
  return camelizeDeep<T>(unwrapEnvelope(raw));
}

async function putReq<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const normalized = config ? { ...config, params: snakifyDeep(config.params) } : undefined;
  const raw = await api.put(url, snakifyDeep(data), normalized);
  return camelizeDeep<T>(unwrapEnvelope(raw));
}

async function deleteReq<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const normalized = config ? { ...config, params: snakifyDeep(config.params) } : undefined;
  const raw = await api.delete(url, normalized);
  return camelizeDeep<T>(unwrapEnvelope(raw));
}

// ============================================
// 行情 API
// ============================================

export const marketApi = {
  getTicker: (exchange: string, symbol: string): Promise<Ticker> =>
    getReq('/market/ticker', { params: { exchange, symbol } }),

  getTickers: (exchange: string, symbols?: string[]): Promise<Ticker[]> =>
    getReq('/market/tickers', {
      params: { exchange, symbols: symbols?.join(','), offset: 0, limit: 500 },
    }),

  getKlines: (
    exchange: string,
    symbol: string,
    timeframe = '1h',
    limit = 100
  ): Promise<Kline[]> =>
    getReq('/market/klines', {
      params: { exchange, symbol, timeframe, limit },
    }),

  getOrderbook: (exchange: string, symbol: string, limit = 20): Promise<OrderBook> =>
    getReq('/market/orderbook', { params: { exchange, symbol, limit } }),

  getSymbols: (exchange: string, quote = 'USDT'): Promise<{ symbols: string[] }> =>
    getReq('/market/symbols', { params: { exchange, quote } }),
};

// ============================================
// 资金费率 API
// ============================================

export const fundingApi = {
  getRates: (exchange: string, symbols?: string[]): Promise<FundingRate[]> =>
    getReq('/funding/rates', {
      params: { exchange, symbols: symbols?.join(',') },
    }),

  getRate: (exchange: string, symbol: string): Promise<FundingRate> =>
    getReq(`/funding/rate/${symbol}`, { params: { exchange } }),

  getHistory: (
    exchange: string,
    symbol: string,
    limit = 100
  ): Promise<{ timestamp: number; rate: number }[]> =>
    getReq('/funding/history', { params: { exchange, symbol, limit } }),

  getOpportunities: (
    exchange: string,
    minRate = 0.0001,
    limit = 20
  ): Promise<FundingOpportunity[]> =>
    getReq('/funding/opportunities', { params: { exchange, minRate, limit } }),

  getSummary: (): Promise<{
    exchanges: Record<string, { total: number; avgRate: number }>;
    topOpportunities: FundingOpportunity[];
  }> => getReq('/funding/summary'),
};

// ============================================
// 交易 API
// ============================================

export const tradingApi = {
  getBalance: (exchange: string): Promise<{ exchange: string; balance: any[] }> =>
    getReq('/trading/balance', { params: { exchange } }),

  getBalanceDetail: (exchange: string): Promise<{ exchange: string; trading: any[]; funding: any[] }> =>
    getReq('/trading/balance/detail', { params: { exchange } }),

  getOpenOrders: (exchange: string, symbol?: string): Promise<{ exchange: string; orders: any[] }> =>
    getReq('/trading/orders/open', { params: { exchange, symbol } }),

  getOrderHistory: (exchange: string, limit = 50, symbol?: string): Promise<{ exchange: string; orders: any[] }> =>
    getReq('/trading/orders/history', { params: { exchange, limit, symbol } }),

  cancelOrder: (orderId: string, exchange: string, symbol: string): Promise<{ result: any }> =>
    deleteReq(`/trading/order/${orderId}`, { params: { exchange, symbol } }),

  transfer: (data: {
    exchange: string;
    currency: string;
    amount: number;
    fromAccount: string;
    toAccount: string;
  }): Promise<any> =>
    postReq('/trading/transfer', data),

  spotOrder: (data: {
    exchange: string;
    symbol: string;
    side: 'buy' | 'sell';
    type: 'market' | 'limit';
    amount: number;
    price?: number | null;
  }): Promise<{ order: any; warnings?: string[] }> =>
    postReq('/trading/spot/order', data),

  futuresOrder: (data: {
    exchange: string;
    symbol: string;
    side: 'long' | 'short';
    action: 'open' | 'close';
    amount: number;
    leverage: number;
    price?: number | null;
  }): Promise<{ order: any }> =>
    postReq('/trading/futures/order', data),
};

// ============================================
// 策略 API
// ============================================

export const strategyApi = {
  getList: (): Promise<Strategy[]> => getReq('/strategies'),

  get: (id: number): Promise<Strategy> => getReq(`/strategies/${id}`),

  create: (data: {
    name: string;
    description?: string;
    scriptContent: string;
    config?: Record<string, unknown>;
    exchange?: string;
    symbols?: string[];
  }): Promise<Strategy> => postReq('/strategies', data),

  update: (id: number, data: Partial<Strategy>): Promise<Strategy> =>
    putReq(`/strategies/${id}`, data),

  delete: (id: number): Promise<void> => deleteReq(`/strategies/${id}`),

  start: (id: number): Promise<{ started: boolean }> => postReq(`/strategies/${id}/start`),

  stop: (id: number): Promise<{ stopped: boolean }> => postReq(`/strategies/${id}/stop`),

  getStatus: (id: number): Promise<{
    strategyId: number;
    name: string;
    status: string;
    pnl: number;
    totalTrades: number;
  }> => getReq(`/strategies/${id}/status`),
};

// ============================================
// 监控 API
// ============================================

export const monitorApi = {
  getAlerts: (): Promise<any[]> => getReq('/monitor/alerts'),

  createAlert: (data: {
    name: string;
    type: string;
    exchange: string;
    symbol?: string;
    threshold: number;
    telegramBotToken?: string;
    telegramChatId?: string;
  }): Promise<{ id: number }> => postReq('/monitor/alerts', data),

  toggleAlert: (id: number, enabled: boolean): Promise<{ id: number; enabled: boolean }> =>
    putReq(`/monitor/alerts/${id}`, null, { params: { enabled } }),

  deleteAlert: (id: number): Promise<{ deleted: boolean }> =>
    deleteReq(`/monitor/alerts/${id}`),

  getRunningStrategies: (): Promise<any[]> =>
    getReq('/monitor/running-strategies'),

  getLongShortRatio: (exchange: string, symbol: string): Promise<any> =>
    getReq('/monitor/long-short-ratio', { params: { exchange, symbol } }),

  getOpenInterest: (exchange: string, symbol: string): Promise<any> =>
    getReq('/monitor/open-interest', { params: { exchange, symbol } }),
};

// ============================================
// 策略上线 (自动交易 / 实盘) API
// ============================================

export const liveApi = {
  getStrategies: (): Promise<any> => getReq('/live/strategies'),

  configure: (config: {
    [key: string]: unknown;
  }): Promise<any> => postReq('/live/configure', config),

  start: (): Promise<any> => postReq('/live/start'),

  stop: (): Promise<any> => postReq('/live/stop'),

  pause: (): Promise<any> => postReq('/live/pause'),

  resume: (): Promise<any> => postReq('/live/resume'),

  getDashboard: (): Promise<any> => getReq('/live/dashboard'),

  getEvents: (limit = 50, eventType?: string): Promise<any> =>
    getReq('/live/events', { params: { limit, eventType } }),

  getEquityCurve: (): Promise<any> => getReq('/live/equity_curve'),

  preFlight: (config: {
    [key: string]: unknown;
  }): Promise<any> => postReq('/live/pre_flight', config),

  testTelegram: (message: string): Promise<any> =>
    postReq('/live/test_telegram', { message }),
};

// ============================================
// 模拟盘 API
// ============================================

export const paperApi = {
  run: (config: {
    [key: string]: unknown;
  }): Promise<any> => postReq('/paper-trading/run', config),

  getInstances: (): Promise<any> => getReq('/paper-trading/instances'),

  getInstance: (instanceId: string): Promise<any> => getReq(`/paper-trading/instances/${instanceId}`),

  deleteInstance: (instanceId: string): Promise<any> => deleteReq(`/paper-trading/instances/${instanceId}`),

  clearInstances: (): Promise<any> => deleteReq('/paper-trading/instances'),

  getSignals: (instanceId?: string, strategy?: string, symbol?: string, timeframe?: string, limit?: number): Promise<any> =>
    getReq('/paper-trading/signals', { params: { instanceId: instanceId, strategy, symbol, timeframe, limit } }),
};

// ============================================
// 数据管理 API
// ============================================

export interface DataSyncMeta {
  exchange: string;
  symbol: string;
  timeframe: string;
  dataType: string;
  firstTimestamp: number | null;
  lastTimestamp: number | null;
  totalRecords: number;
  status: string | null;
  lastSyncAt: string | null;
  errorMessage: string | null;
  updatedAt?: string | null;
}

export interface DataSyncStatusResponse {
  isRunning: boolean;
  currentJob: {
    exchange: string | null;
    status: string | null;
    totalFetched: number;
    totalInserted: number;
    errors: number;
  } | null;
  summary: {
    totalRecords: number;
    exchanges: string[];
    symbolsCount: number;
    pairs: number;
  };
  details: DataSyncMeta[];
}

export interface DataSyncConfigResponse {
  defaultSymbols: string[];
  defaultTimeframes: string[];
  defaultHistoryDays: number;
}

export interface DataSyncTableStat {
  tableName: string;
  timeframe: string;
  exchange: string;
  symbol: string;
  recordCount: number;
  firstTimestamp: number | null;
  lastTimestamp: number | null;
}

export interface DataSyncTableStatsResponse {
  tables: DataSyncTableStat[];
  totalRecords: number;
  totalPairs: number;
}

export interface DataSyncStartRequest {
  exchange?: string;
  symbols?: string[];
  timeframes?: string[];
  historyDays?: number;
  startDate?: string;
  endDate?: string;
}

export interface DataSyncStartResponse {
  message?: string;
  exchange?: string;
  symbols?: string[];
  timeframes?: string[];
  historyDays?: number;
}

export interface DataSyncSyncOneRequest {
  exchange?: string;
  symbol: string;
  timeframe: string;
  startDate?: string;
  endDate?: string;
  historyDays?: number;
}

export interface DataSyncSyncOneResponse {
  exchange: string;
  symbol: string;
  timeframe: string;
  status: string;
  totalFetched: number;
  totalInserted: number;
  error?: string | null;
  elapsedSeconds?: number | null;
}

export interface DataSyncDeleteRequest {
  exchange?: string;
  symbol?: string;
  timeframe?: string;
}

export interface DataSyncDeleteResponse {
  message: string;
  deleted: number;
}

export const dataSyncApi = {
  getStatus: (): Promise<DataSyncStatusResponse> => getReq('/sync/status'),

  getConfig: (): Promise<DataSyncConfigResponse> => getReq('/sync/config'),

  getData: (exchange?: string): Promise<Array<Record<string, unknown>>> =>
    getReq('/sync/data', { params: { exchange } }),

  getTableStats: (): Promise<DataSyncTableStatsResponse> => getReq('/sync/table-stats'),

  startSync: (data: DataSyncStartRequest): Promise<DataSyncStartResponse> =>
    postReq('/sync/start', data),

  syncOne: (data: DataSyncSyncOneRequest): Promise<DataSyncSyncOneResponse> =>
    postReq('/sync/sync-one', data),

  dailyUpdate: (exchange?: string): Promise<DataSyncStartResponse> =>
    postReq('/data_sync/daily_update', null, { params: { exchange } }),

  deleteData: (data: DataSyncDeleteRequest): Promise<DataSyncDeleteResponse> =>
    postReq('/data_sync/delete', data),
};

// ============================================
// 健康检查 API
// ============================================

export const healthApi = {
  check: (): Promise<{ status: string }> => getReq('/system/health'),
  checkExchanges: (): Promise<{ exchanges: Record<string, string> }> =>
    getReq('/system/exchanges'),
};

// ============================================
// AI Agent API
// ============================================

export const agentApi = {
  createTask: (data: {
    [key: string]: unknown;
  }): Promise<{ taskId: string; status: string; message: string }> =>
    postReq('/agent/tasks', data),

  listTasks: (): Promise<any[]> => getReq('/agent/tasks'),

  getTask: (taskId: string): Promise<any> => getReq(`/agent/tasks/${taskId}`),

  getIterations: (taskId: string): Promise<any[]> =>
    getReq(`/agent/tasks/${taskId}/iterations`),

  stopTask: (taskId: string): Promise<any> =>
    postReq(`/agent/tasks/${taskId}/stop`),

  acceptBest: (taskId: string): Promise<any> =>
    postReq(`/agent/tasks/${taskId}/accept`),
};

// ============================================
// 回测 API
// ============================================

export const backtestApi = {
  runSync: (data: Record<string, unknown>): Promise<any> =>
    postReq('/backtest/run_sync', data),
  getStrategies: (): Promise<Record<string, unknown>> =>
    getReq('/backtest/strategies'),
};

export default api;
