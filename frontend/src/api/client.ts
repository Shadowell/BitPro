import axios from 'axios';
import type { Ticker, Kline, OrderBook, FundingRate, FundingOpportunity, Strategy, Alert } from '../types';

const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// ============================================
// 行情 API
// ============================================

export const marketApi = {
  // 获取单个交易对行情
  getTicker: (exchange: string, symbol: string): Promise<Ticker> =>
    api.get('/market/ticker', { params: { exchange, symbol } }),

  // 获取多个交易对行情
  getTickers: (exchange: string, symbols?: string[]): Promise<Ticker[]> =>
    api.get('/market/tickers', {
      params: { exchange, symbols: symbols?.join(',') },
    }),

  // 获取 K 线数据
  getKlines: (
    exchange: string,
    symbol: string,
    timeframe = '1h',
    limit = 100
  ): Promise<Kline[]> =>
    api.get('/market/klines', {
      params: { exchange, symbol, timeframe, limit },
    }),

  // 获取订单簿
  getOrderbook: (exchange: string, symbol: string, limit = 20): Promise<OrderBook> =>
    api.get('/market/orderbook', { params: { exchange, symbol, limit } }),

  // 获取交易对列表
  getSymbols: (exchange: string, quote = 'USDT'): Promise<{ symbols: string[] }> =>
    api.get('/market/symbols', { params: { exchange, quote } }),
};

// ============================================
// 资金费率 API
// ============================================

export const fundingApi = {
  // 获取资金费率列表
  getRates: (exchange: string, symbols?: string[]): Promise<FundingRate[]> =>
    api.get('/funding/rates', {
      params: { exchange, symbols: symbols?.join(',') },
    }),

  // 获取单个交易对资金费率
  getRate: (exchange: string, symbol: string): Promise<FundingRate> =>
    api.get(`/funding/rate/${symbol}`, { params: { exchange } }),

  // 获取资金费率历史
  getHistory: (
    exchange: string,
    symbol: string,
    limit = 100
  ): Promise<{ timestamp: number; rate: number }[]> =>
    api.get('/funding/history', { params: { exchange, symbol, limit } }),

  // 获取套利机会
  getOpportunities: (
    exchange: string,
    minRate = 0.0001,
    limit = 20
  ): Promise<FundingOpportunity[]> =>
    api.get('/funding/opportunities', { params: { exchange, min_rate: minRate, limit } }),

  // 获取汇总
  getSummary: (): Promise<{
    exchanges: Record<string, { total: number; avgRate: number }>;
    topOpportunities: FundingOpportunity[];
  }> => api.get('/funding/summary'),
};

// ============================================
// 策略 API
// ============================================

export const strategyApi = {
  // 获取策略列表
  getList: (): Promise<Strategy[]> => api.get('/strategy/list'),

  // 获取策略详情
  get: (id: number): Promise<Strategy> => api.get(`/strategy/${id}`),

  // 创建策略
  create: (data: {
    name: string;
    description?: string;
    scriptContent: string;
    config?: Record<string, unknown>;
    exchange?: string;
    symbols?: string[];
  }): Promise<Strategy> => api.post('/strategy/create', data),

  // 更新策略
  update: (id: number, data: Partial<Strategy>): Promise<Strategy> =>
    api.put(`/strategy/${id}`, data),

  // 删除策略
  delete: (id: number): Promise<void> => api.delete(`/strategy/${id}`),

  // 启动策略
  start: (id: number): Promise<{ message: string }> =>
    api.post(`/strategy/${id}/start`),

  // 停止策略
  stop: (id: number): Promise<{ message: string }> =>
    api.post(`/strategy/${id}/stop`),

  // 获取策略状态
  getStatus: (id: number): Promise<{
    id: number;
    name: string;
    status: string;
    isRunning: boolean;
    totalPnl: number;
  }> => api.get(`/strategy/${id}/status`),
};

// ============================================
// 监控 API
// ============================================

export const monitorApi = {
  // 获取告警列表
  getAlerts: (): Promise<Alert[]> => api.get('/monitor/alerts'),

  // 创建告警
  createAlert: (data: {
    name: string;
    type: string;
    symbol?: string;
    condition: Record<string, unknown>;
  }): Promise<Alert> => api.post('/monitor/alert', data),
};

// ============================================
// 策略上线 (自动交易 / 实盘) API
// ============================================

export const liveApi = {
  // 获取可用策略列表
  getStrategies: (): Promise<any> => api.get('/live/strategies'),

  // 配置实盘系统
  configure: (config: {
    exchange: string;
    strategy_type: string;
    symbol: string;
    timeframe: string;
    initial_equity: number;
    dry_run: boolean;
    loop_interval?: number;
    strategy_config?: Record<string, unknown>;
    risk_config?: Record<string, unknown>;
  }): Promise<any> => api.post('/live/configure', config),

  // 启动
  start: (): Promise<any> => api.post('/live/start'),

  // 停止
  stop: (): Promise<any> => api.post('/live/stop'),

  // 暂停
  pause: (): Promise<any> => api.post('/live/pause'),

  // 恢复
  resume: (): Promise<any> => api.post('/live/resume'),

  // 监控仪表盘
  getDashboard: (): Promise<any> => api.get('/live/dashboard'),

  // 交易事件
  getEvents: (limit = 50, eventType?: string): Promise<any> =>
    api.get('/live/events', { params: { limit, event_type: eventType } }),

  // 权益曲线
  getEquityCurve: (): Promise<any> => api.get('/live/equity_curve'),

  // 飞行检查
  preFlight: (config: {
    strategy: string;
    symbol: string;
    timeframe: string;
    capital_pct: number;
    total_capital: number;
  }): Promise<any> => api.post('/live/pre_flight', config),

  // 测试 Telegram
  testTelegram: (message: string): Promise<any> =>
    api.post('/live/test_telegram', { message }),
};

// ============================================
// 模拟盘 API
// ============================================

export const paperApi = {
  // 运行模拟盘（创建新实例）
  run: (config: {
    strategy: string;
    exchange: string;
    symbol: string;
    timeframe: string;
    initial_capital: number;
    stop_loss: number;
    days_back: number;
  }): Promise<any> => api.post('/paper_trading/run', config),

  // 获取所有实例列表
  getInstances: (): Promise<any> => api.get('/paper_trading/instances'),

  // 获取实例详情
  getInstance: (instanceId: string): Promise<any> => api.get(`/paper_trading/instances/${instanceId}`),

  // 删除实例
  deleteInstance: (instanceId: string): Promise<any> => api.delete(`/paper_trading/instances/${instanceId}`),

  // 清空所有实例
  clearInstances: (): Promise<any> => api.delete('/paper_trading/instances'),

  // 获取信号
  getSignals: (instanceId?: string, strategy?: string, symbol?: string, timeframe?: string, limit?: number): Promise<any> =>
    api.get('/paper_trading/signals', { params: { instance_id: instanceId, strategy, symbol, timeframe, limit } }),
};

// ============================================
// 数据管理 API
// ============================================

export const dataSyncApi = {
  // 获取同步状态
  getStatus: (): Promise<any> => api.get('/data_sync/status'),

  // 获取配置
  getConfig: (): Promise<{
    default_symbols: string[];
    default_timeframes: string[];
    default_history_days: number;
  }> => api.get('/data_sync/config'),

  // 获取已同步数据清单
  getData: (exchange?: string): Promise<any[]> =>
    api.get('/data_sync/data', { params: { exchange } }),

  // 获取分表统计
  getTableStats: (): Promise<{
    tables: any[];
    total_records: number;
    total_pairs: number;
  }> => api.get('/data_sync/table_stats'),

  // 启动批量同步
  startSync: (data: {
    exchange?: string;
    symbols?: string[];
    timeframes?: string[];
    history_days?: number;
    start_date?: string;
    end_date?: string;
  }): Promise<any> => api.post('/data_sync/start', data),

  // 同步单个交易对
  syncOne: (data: {
    exchange?: string;
    symbol: string;
    timeframe: string;
    start_date?: string;
    end_date?: string;
    history_days?: number;
  }): Promise<any> => api.post('/data_sync/sync_one', data),

  // 每日增量更新
  dailyUpdate: (exchange?: string): Promise<any> =>
    api.post('/data_sync/daily_update', null, { params: { exchange } }),

  // 删除数据
  deleteData: (data: {
    exchange?: string;
    symbol?: string;
    timeframe?: string;
  }): Promise<any> => api.post('/data_sync/delete', data),
};

// ============================================
// 健康检查 API
// ============================================

export const healthApi = {
  check: (): Promise<{ status: string }> => api.get('/health'),
  checkExchanges: (): Promise<{ exchanges: Record<string, string> }> =>
    api.get('/health/exchanges'),
};

// ============================================
// AI Agent API
// ============================================

export const agentApi = {
  createTask: (data: {
    symbol?: string;
    timeframe?: string;
    backtest_start?: string;
    backtest_end?: string;
    max_iterations?: number;
    user_prompt?: string;
    goal?: Record<string, number>;
  }): Promise<{ task_id: string; status: string; message: string }> =>
    api.post('/agent/tasks', data),

  listTasks: (): Promise<any[]> => api.get('/agent/tasks'),

  getTask: (taskId: string): Promise<any> => api.get(`/agent/tasks/${taskId}`),

  getIterations: (taskId: string): Promise<any[]> =>
    api.get(`/agent/tasks/${taskId}/iterations`),

  stopTask: (taskId: string): Promise<any> =>
    api.post(`/agent/tasks/${taskId}/stop`),

  acceptBest: (taskId: string): Promise<any> =>
    api.post(`/agent/tasks/${taskId}/accept`),
};

export default api;
