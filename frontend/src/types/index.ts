// 行情相关类型
export interface Ticker {
  exchange: string;
  symbol: string;
  last: number;
  bid?: number;
  ask?: number;
  high?: number;
  low?: number;
  volume?: number;
  quoteVolume?: number;
  change?: number;
  changePercent?: number;
  timestamp?: number;
}

export interface Kline {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OrderBook {
  exchange: string;
  symbol: string;
  bids: [number, number][];
  asks: [number, number][];
  timestamp?: number;
}

// 资金费率相关
export interface FundingRate {
  exchange: string;
  symbol: string;
  currentRate: number;
  predictedRate?: number;
  nextFundingTime?: number;
  markPrice?: number;
  indexPrice?: number;
}

export interface FundingOpportunity {
  symbol: string;
  exchange: string;
  rate: number;
  annualized: number;
  nextFundingTime: number;
}

// 策略相关
export interface Strategy {
  id: number;
  name: string;
  description?: string;
  scriptContent: string;
  config?: Record<string, unknown>;
  status: 'running' | 'stopped' | 'error';
  exchange?: string;
  symbols?: string[];
  createdAt: string;
  updatedAt: string;
}

export interface StrategyTrade {
  id: number;
  strategyId: number;
  exchange: string;
  symbol: string;
  orderId?: string;
  timestamp: number;
  side: 'buy' | 'sell';
  type: string;
  price: number;
  quantity: number;
  fee?: number;
  pnl?: number;
}

// 回测相关
export interface BacktestResult {
  id: number;
  strategyId: number;
  status: 'running' | 'completed' | 'failed';
  totalReturn?: number;
  annualReturn?: number;
  maxDrawdown?: number;
  sharpeRatio?: number;
  winRate?: number;
  profitFactor?: number;
  totalTrades?: number;
  trades?: StrategyTrade[];
  createdAt: string;
}

// 告警相关
export interface Alert {
  id: number;
  name: string;
  type: 'price' | 'funding' | 'position' | 'liquidation';
  symbol?: string;
  condition: Record<string, unknown>;
  notification?: Record<string, unknown>;
  enabled: boolean;
  lastTriggeredAt?: string;
  createdAt: string;
}

// 持仓
export interface Position {
  exchange: string;
  symbol: string;
  side: 'long' | 'short';
  amount: number;
  entryPrice: number;
  markPrice?: number;
  liquidationPrice?: number;
  unrealizedPnl?: number;
  leverage?: number;
  marginMode?: string;
}

// 余额
export interface Balance {
  currency: string;
  free: number;
  used: number;
  total: number;
}
