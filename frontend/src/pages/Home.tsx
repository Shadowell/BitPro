import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Star, RefreshCw, Search } from 'lucide-react';
import { useStore } from '../stores/useStore';
import { useSettingsStore } from '../stores/useSettingsStore';
import { marketApi, healthApi } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { TOP50_SYMBOLS } from '../components/SymbolSearch';
import { useTickersWebSocket } from '../hooks/useWebSocket';

// 币种图标颜色映射
const COIN_COLORS: Record<string, string> = {
  BTC: 'bg-orange-500',
  ETH: 'bg-blue-500',
  USDT: 'bg-green-500',
  BNB: 'bg-yellow-500',
  XRP: 'bg-gray-400',
  USDC: 'bg-blue-400',
  SOL: 'bg-purple-500',
  DOGE: 'bg-yellow-400',
  ADA: 'bg-blue-600',
  AVAX: 'bg-red-500',
  DOT: 'bg-pink-500',
  LINK: 'bg-blue-500',
  LTC: 'bg-gray-300',
  UNI: 'bg-pink-400',
  NEAR: 'bg-green-400',
  APT: 'bg-teal-400',
  ARB: 'bg-blue-300',
  OP: 'bg-red-400',
  SUI: 'bg-cyan-400',
  PEPE: 'bg-green-500',
  FIL: 'bg-blue-400',
  ATOM: 'bg-purple-400',
  INJ: 'bg-blue-500',
  FET: 'bg-purple-500',
  TIA: 'bg-violet-500',
  BCH: 'bg-green-600',
  XLM: 'bg-gray-400',
  WIF: 'bg-amber-500',
  RUNE: 'bg-green-500',
  AAVE: 'bg-purple-400',
};

// 币种全名映射
const COIN_NAMES: Record<string, string> = {
  BTC: 'Bitcoin', ETH: 'Ethereum', USDT: 'Tether', BNB: 'BNB',
  XRP: 'XRP', USDC: 'USD Coin', SOL: 'Solana', DOGE: 'Dogecoin',
  ADA: 'Cardano', AVAX: 'Avalanche', DOT: 'Polkadot', LINK: 'Chainlink',
  LTC: 'Litecoin', UNI: 'Uniswap', NEAR: 'NEAR Protocol', APT: 'Aptos',
  ARB: 'Arbitrum', OP: 'Optimism', SUI: 'Sui', PEPE: 'Pepe',
  FIL: 'Filecoin', ATOM: 'Cosmos', INJ: 'Injective', FET: 'Fetch.ai',
  TIA: 'Celestia', BCH: 'Bitcoin Cash', XLM: 'Stellar', WIF: 'dogwifhat',
  RUNE: 'THORChain', AAVE: 'Aave', MATIC: 'Polygon', STX: 'Stacks',
  IMX: 'Immutable X', SEI: 'Sei',
};

// 分类标签
const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'top', label: '热门' },
  { key: 'defi', label: 'DeFi' },
  { key: 'layer1', label: '公链' },
  { key: 'layer2', label: '二层' },
  { key: 'meme', label: 'Meme' },
  { key: 'ai', label: 'AI' },
];

// 分类配置
const CATEGORY_SYMBOLS: Record<string, string[]> = {
  top: ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE', 'ADA', 'AVAX'],
  defi: ['UNI', 'AAVE', 'LINK', 'INJ', 'RUNE'],
  layer1: ['ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'NEAR', 'APT', 'SUI', 'ATOM', 'SEI'],
  layer2: ['ARB', 'OP', 'MATIC', 'IMX', 'STX'],
  meme: ['DOGE', 'PEPE', 'WIF'],
  ai: ['FET', 'NEAR'],
};

// 热门交易对
// 使用统一的 TOP50 列表
const HOT_SYMBOLS = TOP50_SYMBOLS;

interface TickerData {
  symbol: string;
  coin: string;
  name: string;
  last: number;
  change_percent: number;
  high: number;
  low: number;
  volume: number;
  quote_volume: number;
  sparkline: number[]; // 简易走势
  isFavorite: boolean;
}

// 迷你走势图 SVG 组件
function SparklineChart({ data, isUp }: { data: number[]; isUp: boolean }) {
  const { upColor, downColor } = useSettingsStore((s) => s.getColors());

  if (!data || data.length < 2) return <div className="w-[120px] h-[40px]" />;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const width = 120;
  const height = 40;
  const padding = 2;

  const points = data.map((val, i) => {
    const x = padding + (i / (data.length - 1)) * (width - padding * 2);
    const y = height - padding - ((val - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(' ');

  const color = isUp ? upColor : downColor;

  return (
    <svg width={width} height={height} className="flex-shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// 24h 范围条
function RangeBar({ low, high, current }: { low: number; high: number; current: number }) {
  const range = high - low || 1;
  const pct = Math.max(0, Math.min(100, ((current - low) / range) * 100));

  return (
    <div className="flex items-center space-x-2 text-xs">
      <span className="text-gray-500 w-[70px] text-right font-mono">
        ${formatNum(low)}
      </span>
      <div className="flex-1 h-1 bg-gray-700 rounded-full relative min-w-[60px]">
        <div
          className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-white rounded-full"
          style={{ left: `${pct}%` }}
        />
      </div>
      <span className="text-gray-500 w-[70px] font-mono">
        ${formatNum(high)}
      </span>
    </div>
  );
}

// 格式化数字
function formatNum(num: number): string {
  if (num >= 10000) return num.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (num >= 100) return num.toFixed(2);
  if (num >= 1) return num.toFixed(4);
  if (num >= 0.01) return num.toFixed(5);
  return num.toFixed(6);
}

function formatVolume(vol: number): string {
  if (vol >= 1e9) return `$${(vol / 1e9).toFixed(2)}B`;
  if (vol >= 1e6) return `$${(vol / 1e6).toFixed(1)}M`;
  if (vol >= 1e3) return `$${(vol / 1e3).toFixed(0)}K`;
  return `$${vol.toFixed(0)}`;
}

type SortKey = 'name' | 'price' | 'change' | 'volume';
type SortDir = 'asc' | 'desc';

export default function Home() {
  const { selectedExchange } = useStore();
  const navigate = useNavigate();

  const [tickers, setTickers] = useState<TickerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [apiStatus, setApiStatus] = useState<string>('checking');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [favorites, setFavorites] = useState<Set<string>>(() => {
    const saved = localStorage.getItem('bitpro_favorites');
    return saved ? new Set(JSON.parse(saved)) : new Set(['BTC/USDT', 'ETH/USDT', 'SOL/USDT']);
  });
  const [sortKey, setSortKey] = useState<SortKey>('volume');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [activeTab, setActiveTab] = useState<'favorites' | 'crypto' | 'spot' | 'futures'>('crypto');

  // WebSocket 实时批量行情
  const { tickers: wsTickers, isConnected: wsConnected } = useTickersWebSocket(selectedExchange);

  // 保存上一次的 sparkline 用于平滑过渡
  const sparklineCache = useRef<Record<string, number[]>>({});

  // 切换收藏
  const toggleFavorite = (symbol: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      localStorage.setItem('bitpro_favorites', JSON.stringify([...next]));
      return next;
    });
  };

  // 排序切换
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  // 将原始 ticker 数据转为展示数据
  const mapTickerData = useCallback((tickersData: any[]): TickerData[] => {
    return tickersData.map((t: any) => {
      const coin = t.symbol.split('/')[0];
      const changePct = t.changePercent ?? t.change_percent ?? 0;
      const quoteVol = t.quoteVolume ?? t.quote_volume ?? 0;

      // 如果 sparkline 缓存中有该 symbol，追加最新价到尾部（滚动效果）
      const cached = sparklineCache.current[t.symbol];
      let sparkline: number[];
      if (cached && cached.length >= 2) {
        sparkline = [...cached.slice(-23), t.last]; // 保留最近24个点
      } else {
        sparkline = generateSparkline(t.low, t.high, t.last, changePct);
      }
      sparklineCache.current[t.symbol] = sparkline;

      return {
        symbol: t.symbol,
        coin,
        name: COIN_NAMES[coin] || coin,
        last: t.last,
        change_percent: changePct,
        high: t.high || t.last,
        low: t.low || t.last,
        volume: t.volume || 0,
        quote_volume: quoteVol,
        sparkline,
        isFavorite: favorites.has(t.symbol),
      };
    });
  }, [favorites]);

  // 首次 HTTP 加载（WebSocket 连上前保证有数据）
  const fetchAllTickers = useCallback(async () => {
    try {
      const tickersData = await marketApi.getTickers(selectedExchange, HOT_SYMBOLS);
      const items = mapTickerData(tickersData as any[]);
      setTickers(items);
    } catch (err) {
      console.error('Failed to fetch tickers:', err);
    }
  }, [selectedExchange, mapTickerData]);

  // 手动刷新
  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchAllTickers();
    setIsRefreshing(false);
  };

  // 初始化：HTTP 加载 + 健康检查
  useEffect(() => {
    setLoading(true);
    healthApi.check()
      .then(() => setApiStatus('connected'))
      .catch(() => setApiStatus('disconnected'));

    fetchAllTickers().finally(() => setLoading(false));
  }, [fetchAllTickers]);

  // WebSocket 实时更新：当收到 wsTickers 数据时，更新列表
  useEffect(() => {
    if (wsTickers && wsTickers.length > 0) {
      const items = mapTickerData(wsTickers as any[]);
      if (items.length > 0) {
        setTickers(items);
        setLoading(false);
        if (apiStatus === 'checking') setApiStatus('connected');
      }
    }
  }, [wsTickers, mapTickerData, apiStatus]);

  // 更新连接状态
  useEffect(() => {
    if (wsConnected) {
      setApiStatus('connected');
    }
  }, [wsConnected]);

  // 过滤 & 排序
  const displayedTickers = useMemo(() => {
    let list = [...tickers];

    // 搜索过滤
    if (searchQuery) {
      const q = searchQuery.toUpperCase();
      list = list.filter(
        (t) => t.coin.includes(q) || t.name.toUpperCase().includes(q) || t.symbol.includes(q)
      );
    }

    // Tab 过滤
    if (activeTab === 'favorites') {
      list = list.filter((t) => favorites.has(t.symbol));
    }

    // 分类过滤
    if (activeCategory !== 'all') {
      const categoryCoins = CATEGORY_SYMBOLS[activeCategory];
      if (categoryCoins) {
        list = list.filter((t) => categoryCoins.includes(t.coin));
      }
    }

    // 排序
    list.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'name': cmp = a.coin.localeCompare(b.coin); break;
        case 'price': cmp = a.last - b.last; break;
        case 'change': cmp = a.change_percent - b.change_percent; break;
        case 'volume': cmp = a.quote_volume - b.quote_volume; break;
      }
      return sortDir === 'desc' ? -cmp : cmp;
    });

    return list;
  }, [tickers, searchQuery, activeCategory, activeTab, favorites, sortKey, sortDir]);

  // 点击行跳转行情页
  const handleRowClick = (symbol: string) => {
    const store = useStore.getState();
    store.setSelectedSymbol(symbol);
    navigate('/market');
  };

  const SortIcon = ({ k }: { k: SortKey }) => (
    <span className="ml-1 text-gray-500 inline-flex flex-col text-[8px] leading-[6px]">
      <span className={sortKey === k && sortDir === 'asc' ? 'text-white' : ''}>▲</span>
      <span className={sortKey === k && sortDir === 'desc' ? 'text-white' : ''}>▼</span>
    </span>
  );

  return (
    <div className="h-full flex flex-col">
      {/* 顶部栏 */}
      <div className="px-6 pt-5 pb-3 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <h1 className="text-xl font-bold text-white">行情总览</h1>
          <div className="flex items-center space-x-1.5">
            <span className={`w-2 h-2 rounded-full ${
              wsConnected ? 'bg-green-500' : apiStatus === 'disconnected' ? 'bg-red-500' : 'bg-yellow-500 animate-pulse'
            }`} />
            <span className="text-xs text-gray-500">
              {selectedExchange.toUpperCase()} · {wsConnected ? '实时' : '连接中'}
            </span>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          {/* 搜索框 */}
          <div className="relative">
            <Search className="w-4 h-4 text-gray-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="搜索币种..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-gray-800 border border-crypto-border rounded-lg pl-8 pr-3 py-1.5 text-sm text-white w-48 focus:outline-none focus:border-blue-500 placeholder:text-gray-600"
            />
          </div>
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Tab 切换 */}
      <div className="px-6 flex items-center space-x-6 border-b border-crypto-border">
        {([
          { key: 'favorites', label: '自选' },
          { key: 'crypto', label: '现货' },
          { key: 'spot', label: '币币' },
          { key: 'futures', label: '合约' },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'text-white border-white'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 分类标签 */}
      <div className="px-6 py-3 flex items-center space-x-2 overflow-x-auto">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setActiveCategory(cat.key)}
            className={`px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
              activeCategory === cat.key
                ? 'bg-gray-700 text-white'
                : 'bg-gray-800/50 text-gray-500 hover:text-gray-300 hover:bg-gray-800'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* 表头 */}
      <div className="px-6 grid grid-cols-[40px_1fr_140px_100px_140px_1fr_1fr] items-center py-2 text-xs text-gray-500 border-b border-crypto-border/50">
        <span></span>
        <button onClick={() => handleSort('name')} className="text-left flex items-center hover:text-gray-300">
          币种 <SortIcon k="name" />
        </button>
        <button onClick={() => handleSort('price')} className="text-left flex items-center hover:text-gray-300">
          最新价 <SortIcon k="price" />
        </button>
        <button onClick={() => handleSort('change')} className="text-left flex items-center hover:text-gray-300">
          24h 涨跌 <SortIcon k="change" />
        </button>
        <span className="text-center">24h 走势</span>
        <button onClick={() => handleSort('volume')} className="text-left flex items-center hover:text-gray-300">
          24h 成交额 <SortIcon k="volume" />
        </button>
        <span className="text-left">24h 区间</span>
      </div>

      {/* 数据列表 */}
      <div className="flex-1 overflow-y-auto px-6">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-500">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" /> 加载中...
          </div>
        ) : displayedTickers.length === 0 ? (
          <div className="flex items-center justify-center py-20 text-gray-500">
            {searchQuery ? `未找到 "${searchQuery}" 相关币种` : '暂无数据'}
          </div>
        ) : (
          displayedTickers.map((t) => (
            <div
              key={t.symbol}
              onClick={() => handleRowClick(t.symbol)}
              className="grid grid-cols-[40px_1fr_140px_100px_140px_1fr_1fr] items-center py-3.5 border-b border-crypto-border/30 hover:bg-gray-800/40 cursor-pointer transition-colors group"
            >
              {/* 收藏星 */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleFavorite(t.symbol);
                }}
                className="flex items-center justify-center"
              >
                <Star
                  className={`w-4 h-4 ${
                    favorites.has(t.symbol)
                      ? 'text-yellow-400 fill-yellow-400'
                      : 'text-gray-600 hover:text-gray-400'
                  }`}
                />
              </button>

              {/* 名称 */}
              <div className="flex items-center space-x-3">
                <div className={`w-7 h-7 rounded-full ${COIN_COLORS[t.coin] || 'bg-gray-600'} flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}>
                  {t.coin.charAt(0)}
                </div>
                <div>
                  <div className="text-white font-semibold text-sm leading-tight">{t.coin}</div>
                  <div className="text-gray-500 text-xs leading-tight">{t.name}</div>
                </div>
              </div>

              {/* 价格 */}
              <div className="text-white font-mono text-sm">
                ${formatNum(t.last)}
              </div>

              {/* 24h 涨跌 */}
              <div className={`font-mono text-sm ${t.change_percent >= 0 ? 'text-up' : 'text-down'}`}>
                {t.change_percent >= 0 ? '+' : ''}{t.change_percent.toFixed(2)}%
              </div>

              {/* 迷你走势图 */}
              <div className="flex justify-center">
                <SparklineChart data={t.sparkline} isUp={t.change_percent >= 0} />
              </div>

              {/* 24h 成交额 */}
              <div className="text-gray-400 text-sm font-mono">
                {formatVolume(t.quote_volume)}
              </div>

              {/* 24h 范围 */}
              <RangeBar low={t.low} high={t.high} current={t.last} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// 根据高低价和涨跌方向生成模拟 sparkline 数据（24 个点）
function generateSparkline(low: number, high: number, last: number, changePct: number): number[] {
  const points = 24;
  const data: number[] = [];
  const range = high - low || 1;

  // 起始价格（根据涨跌推算）
  const open = last / (1 + changePct / 100);
  
  for (let i = 0; i < points; i++) {
    const progress = i / (points - 1);
    // 基础趋势线
    const trend = open + (last - open) * progress;
    // 添加随机波动
    const noise = (Math.sin(i * 2.5 + changePct) * 0.3 + Math.cos(i * 1.7) * 0.2) * range * 0.15;
    const val = Math.max(low, Math.min(high, trend + noise));
    data.push(val);
  }

  // 确保最后一个点是当前价格
  data[data.length - 1] = last;
  return data;
}
