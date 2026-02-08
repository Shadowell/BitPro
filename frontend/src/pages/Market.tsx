import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useStore } from '../stores/useStore';
import { marketApi } from '../api/client';
import { useTickerWebSocket } from '../hooks/useWebSocket';
import KlineChart from '../components/KlineChart';
import OrderBookChart from '../components/OrderBookChart';
import SymbolSearch from '../components/SymbolSearch';
import type { Kline, OrderBook } from '../types';

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];

export default function Market() {
  const { selectedExchange, selectedSymbol, setSelectedSymbol } = useStore();
  const [klines, setKlines] = useState<Kline[]>([]);
  const [orderbook, setOrderbook] = useState<OrderBook | null>(null);
  const [loading, setLoading] = useState(false);
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [timeframe, setTimeframe] = useState('1h');

  // WebSocket 实时行情
  const { ticker, isConnected } = useTickerWebSocket(selectedExchange, selectedSymbol);

  // 获取交易所支持的完整交易对列表（供搜索组件使用）
  useEffect(() => {
    marketApi.getSymbols(selectedExchange)
      .then((res) => setAllSymbols(res.symbols || []))
      .catch(console.error);
  }, [selectedExchange]);

  // 获取 K 线和深度数据
  const fetchData = () => {
    if (!selectedSymbol) return;

    setLoading(true);
    Promise.all([
      marketApi.getKlines(selectedExchange, selectedSymbol, timeframe, 200),
      marketApi.getOrderbook(selectedExchange, selectedSymbol, 20),
    ])
      .then(([klinesData, orderbookData]) => {
        setKlines(klinesData);
        setOrderbook(orderbookData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, [selectedExchange, selectedSymbol, timeframe]);

  // 实时价格 & 24h涨跌幅
  const lastKline = klines[klines.length - 1];
  const currentPrice = (ticker as any)?.last || lastKline?.close || 0;
  // 后端已统一输出 camelCase
  const priceChange = (ticker as any)?.changePercent ?? 0;

  return (
    <div className="p-6 h-full flex flex-col">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-4">
          <h1 className="text-2xl font-bold text-white">行情</h1>
          
          {/* 交易对搜索选择（主流 Top50 + 模糊搜索） */}
          <SymbolSearch
            value={selectedSymbol}
            onChange={setSelectedSymbol}
            allSymbols={allSymbols}
          />

          {/* 时间周期选择 */}
          <div className="flex bg-crypto-card border border-crypto-border rounded overflow-hidden">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-2 text-sm ${
                  timeframe === tf
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* 刷新按钮 */}
          <button
            onClick={fetchData}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded"
            disabled={loading}
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {/* WebSocket 状态 */}
          <div className="flex items-center space-x-1 text-xs">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-500'}`} />
            <span className="text-gray-400">{isConnected ? '实时' : '离线'}</span>
          </div>
        </div>

        {/* 当前价格 */}
        <div className="text-right">
          <div className="text-2xl font-bold text-white">
            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className={priceChange >= 0 ? 'text-up' : 'text-down'}>
            {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
          </div>
        </div>
      </div>

      {loading && klines.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          加载中...
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-4 min-h-0">
          {/* K线图区域 */}
          <div className="lg:col-span-3 bg-crypto-card border border-crypto-border rounded-lg p-4 min-h-0">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-semibold text-white">
                {selectedSymbol} - {timeframe}
              </h2>
              <div className="text-xs text-gray-400">
                共 {klines.length} 根K线
              </div>
            </div>
            <div className="h-[calc(100%-40px)]">
              {klines.length > 0 ? (
                <KlineChart
                  data={klines}
                  symbol={selectedSymbol}
                  height={500}
                  showVolume={true}
                  showMA={true}
                  maperiods={[5, 10, 20, 30]}
                />
              ) : (
                <div className="h-full flex items-center justify-center text-gray-400">
                  暂无数据
                </div>
              )}
            </div>
          </div>

          {/* 订单簿 */}
          <div className="bg-crypto-card border border-crypto-border rounded-lg p-4 overflow-hidden">
            <h2 className="text-lg font-semibold text-white mb-4">订单簿</h2>
            <OrderBookChart data={orderbook} maxRows={12} />
          </div>
        </div>
      )}
    </div>
  );
}
