import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Database,
  RefreshCw,
  Download,
  Trash2,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  HardDrive,
  BarChart3,
  Search,
  ChevronDown,
  Zap,
  Calendar,
  TrendingUp,
  AlertCircle,
  Info,
  X,
} from 'lucide-react';
import {
  dataSyncApi,
  type DataSyncConfigResponse,
  type DataSyncMeta,
  type DataSyncTableStat,
} from '../api/client';
import { useStore } from '../stores/useStore';

// ============================================
// 常量
// ============================================

const TIMEFRAME_LABELS: Record<string, string> = {
  '1m': '1分钟',
  '5m': '5分钟',
  '15m': '15分钟',
  '1h': '1小时',
  '4h': '4小时',
  '1d': '日线',
};

const TIMEFRAME_COLORS: Record<string, string> = {
  '1m': 'from-rose-500/20 to-rose-600/5 border-rose-500/30',
  '5m': 'from-violet-500/20 to-violet-600/5 border-violet-500/30',
  '15m': 'from-blue-500/20 to-blue-600/5 border-blue-500/30',
  '1h': 'from-cyan-500/20 to-cyan-600/5 border-cyan-500/30',
  '4h': 'from-emerald-500/20 to-emerald-600/5 border-emerald-500/30',
  '1d': 'from-amber-500/20 to-amber-600/5 border-amber-500/30',
};

const TIMEFRAME_BADGE: Record<string, string> = {
  '1m': 'bg-rose-500/20 text-rose-300 border-rose-500/30',
  '5m': 'bg-violet-500/20 text-violet-300 border-violet-500/30',
  '15m': 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  '1h': 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  '4h': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  '1d': 'bg-amber-500/20 text-amber-300 border-amber-500/30',
};

// 币种图标颜色
const COIN_COLORS: Record<string, string> = {
  BTC: '#F7931A', ETH: '#627EEA', SOL: '#9945FF', BNB: '#F3BA2F',
  XRP: '#23292F', DOGE: '#C3A634', ADA: '#0033AD', AVAX: '#E84142',
  LINK: '#2A5ADA', DOT: '#E6007A', ZAMA: '#00D4AA',
};

// ============================================
// 辅助函数
// ============================================

function formatTs(ts: number | null): string {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function getCoinBase(symbol: string): string {
  return symbol.split('/')[0] || symbol;
}

function getDataFreshness(lastTs: number | null): { label: string; color: string } {
  if (!lastTs) return { label: '无数据', color: 'text-gray-500' };
  const hoursSince = (Date.now() - lastTs) / 3600000;
  if (hoursSince < 2) return { label: '最新', color: 'text-green-400' };
  if (hoursSince < 24) return { label: `${Math.floor(hoursSince)}小时前`, color: 'text-yellow-400' };
  if (hoursSince < 168) return { label: `${Math.floor(hoursSince / 24)}天前`, color: 'text-orange-400' };
  return { label: `${Math.floor(hoursSince / 24)}天前`, color: 'text-red-400' };
}

// 计算覆盖率条
function getCoveragePercent(firstTs: number | null, lastTs: number | null, targetDays: number): number {
  if (!firstTs || !lastTs) return 0;
  const range = lastTs - firstTs;
  const target = targetDays * 86400000;
  return Math.min(100, Math.round((range / target) * 100));
}

// ============================================
// 数据管理页面
// ============================================

export default function DataManager() {
  const { selectedExchange } = useStore();

  const [config, setConfig] = useState<DataSyncConfigResponse | null>(null);
  const [tableStats, setTableStats] = useState<DataSyncTableStat[]>([]);
  const [syncMeta, setSyncMeta] = useState<DataSyncMeta[]>([]);
  const [totalRecords, setTotalRecords] = useState(0);
  const [totalPairs, setTotalPairs] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState('');
  const [syncMsgType, setSyncMsgType] = useState<'info' | 'success' | 'error'>('info');
  const [filterTf, setFilterTf] = useState<string>('');
  const [filterSymbol, setFilterSymbol] = useState('');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [showCustomSync, setShowCustomSync] = useState(false);
  // 自定义同步面板
  const [customStartDate, setCustomStartDate] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 6);
    return d.toISOString().slice(0, 10);
  });
  const [customEndDate, setCustomEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [customSymbols, setCustomSymbols] = useState<string[]>([]);
  const [customTimeframes, setCustomTimeframes] = useState<string[]>([]);
  // 展开详情中的单个同步日期
  const [detailStartDate, setDetailStartDate] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 6);
    return d.toISOString().slice(0, 10);
  });
  const [detailEndDate, setDetailEndDate] = useState(() => new Date().toISOString().slice(0, 10));

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ============================================
  // 数据加载
  // ============================================

  const loadData = useCallback(async () => {
    try {
      const [configRes, statsRes, statusRes] = await Promise.all([
        dataSyncApi.getConfig(),
        dataSyncApi.getTableStats(),
        dataSyncApi.getStatus(),
      ]);
      setConfig(configRes);
      setTableStats(statsRes.tables || []);
      setTotalRecords(statsRes.totalRecords || 0);
      setTotalPairs(statsRes.totalPairs || 0);
      setIsRunning(statusRes.isRunning || false);
      setSyncMeta(statusRes.details || []);

      // 如果不在运行中，停止轮询
      const running = statusRes.isRunning || false;
      if (!running && syncing) {
        setSyncing(false);
        showMsg('同步任务已完成', 'success');
      }
    } catch (e) {
      console.error('加载数据管理信息失败', e);
    } finally {
      setLoading(false);
    }
  }, [syncing]);

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    if (isRunning || syncing) {
      pollRef.current = setInterval(loadData, 4000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [isRunning, syncing, loadData]);

  const showMsg = (msg: string, type: 'info' | 'success' | 'error' = 'info') => {
    setSyncMsg(msg);
    setSyncMsgType(type);
    if (type !== 'error') setTimeout(() => setSyncMsg(''), 8000);
  };

  const getErrorMessage = (error: unknown): string => {
    if (typeof error === 'string') return error;
    if (error && typeof error === 'object') {
      const e = error as {
        message?: string;
        response?: { data?: { error?: { message?: string }; detail?: unknown } };
      };
      const envelopeMessage = e.response?.data?.error?.message;
      if (typeof envelopeMessage === 'string' && envelopeMessage.length > 0) return envelopeMessage;
      const detail = e.response?.data?.detail;
      if (typeof detail === 'string' && detail.length > 0) return detail;
      if (detail && typeof detail === 'object') return JSON.stringify(detail);
      if (typeof e.message === 'string' && e.message.length > 0) return e.message;
    }
    return '请求失败';
  };

  // ============================================
  // 操作
  // ============================================

  const handleStartSync = async () => {
    try {
      setSyncing(true);
      showMsg('全量同步任务已提交，后台拉取最近1年数据...', 'info');
      await dataSyncApi.startSync({ exchange: selectedExchange, historyDays: 365 });
      setTimeout(loadData, 2000);
    } catch (e) {
      showMsg(`启动失败: ${getErrorMessage(e)}`, 'error');
      setSyncing(false);
    }
  };

  const handleCustomSync = async () => {
    const syms = customSymbols.length > 0 ? customSymbols : undefined;
    const tfs = customTimeframes.length > 0 ? customTimeframes : undefined;
    try {
      setSyncing(true);
      const symLabel = syms ? `${syms.length} 个币种` : '全部币种';
      const tfLabel = tfs ? tfs.join('/') : '全部周期';
      showMsg(`自定义同步已启动: ${symLabel} ${tfLabel} (${customStartDate} ~ ${customEndDate})`, 'info');
      await dataSyncApi.startSync({
        exchange: selectedExchange,
        symbols: syms,
        timeframes: tfs,
        startDate: customStartDate,
        endDate: customEndDate,
        historyDays: 365,
      });
      setTimeout(loadData, 2000);
    } catch (e) {
      showMsg(`启动失败: ${getErrorMessage(e)}`, 'error');
      setSyncing(false);
    }
  };

  const handleSyncOne = async (symbol: string, timeframe: string, startDate?: string, endDate?: string) => {
    try {
      const dateHint = startDate ? ` (${startDate} ~ ${endDate || '至今'})` : '';
      showMsg(`正在同步 ${getCoinBase(symbol)} ${TIMEFRAME_LABELS[timeframe] || timeframe}${dateHint}...`, 'info');
      const res = await dataSyncApi.syncOne({
        exchange: selectedExchange,
        symbol,
        timeframe,
        historyDays: 365,
        startDate: startDate,
        endDate: endDate,
      });
      const fetched = res.totalFetched ?? 0;
      const inserted = res.totalInserted ?? 0;
      showMsg(`${getCoinBase(symbol)} ${TIMEFRAME_LABELS[timeframe] || timeframe} 完成: 拉取 ${fetched} 条, 新增 ${inserted} 条`, 'success');
      await loadData();
    } catch (e) {
      showMsg(`同步失败: ${getErrorMessage(e)}`, 'error');
    }
  };

  const handleDelete = async (symbol?: string, timeframe?: string) => {
    const target = symbol
      ? `${getCoinBase(symbol)}${timeframe ? ` ${TIMEFRAME_LABELS[timeframe] || timeframe}` : ' 全部周期'}`
      : '所有数据';
    if (!window.confirm(`确认删除 ${target} 的数据？此操作不可恢复。`)) return;
    try {
      const res = await dataSyncApi.deleteData({ exchange: selectedExchange, symbol, timeframe });
      showMsg(res.message || '删除完成', 'success');
      await loadData();
    } catch (e) {
      showMsg(`删除失败: ${getErrorMessage(e)}`, 'error');
    }
  };

  const handleDailyUpdate = async () => {
    try {
      setSyncing(true);
      showMsg('增量更新已启动（回溯7天补数据）...', 'info');
      await dataSyncApi.dailyUpdate(selectedExchange);
      setTimeout(loadData, 2000);
    } catch (e) {
      showMsg(`增量更新失败: ${getErrorMessage(e)}`, 'error');
      setSyncing(false);
    }
  };

  // ============================================
  // 数据聚合
  // ============================================

  const allTimeframes = config?.defaultTimeframes || ['5m', '15m', '1h', '4h', '1d'];
  const allSymbols: string[] = config?.defaultSymbols || [];

  const statMap = new Map<string, DataSyncTableStat>();
  for (const s of tableStats) {
    if (s.exchange !== selectedExchange) continue;
    const key = `${s.symbol}_${s.timeframe}`;
    const existing = statMap.get(key);
    if (!existing || s.tableName !== 'kline_history') {
      statMap.set(key, s);
    }
  }

  const metaMap = new Map<string, DataSyncMeta>();
  for (const m of syncMeta) {
    if (m.exchange !== selectedExchange) continue;
    metaMap.set(`${m.symbol}_${m.timeframe}`, m);
  }

  const filteredSymbols = allSymbols.filter((s) =>
    filterSymbol ? s.toLowerCase().includes(filterSymbol.toLowerCase()) : true
  );

  // 统计每个 symbol 的总数据量
  const symbolTotalRecords = (symbol: string): number => {
    let total = 0;
    for (const tf of allTimeframes) {
      const stat = statMap.get(`${symbol}_${tf}`);
      if (stat) total += stat.recordCount;
    }
    return total;
  };

  // 每个 symbol 有数据的周期数
  const symbolFilledTf = (symbol: string): number => {
    let count = 0;
    for (const tf of allTimeframes) {
      const stat = statMap.get(`${symbol}_${tf}`);
      if (stat && stat.recordCount > 0) count++;
    }
    return count;
  };

  // ============================================
  // 渲染
  // ============================================

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-80 gap-4">
        <div className="relative">
          <Database className="w-12 h-12 text-blue-500/30" />
          <Loader2 className="w-6 h-6 animate-spin text-blue-400 absolute -bottom-1 -right-1" />
        </div>
        <span className="text-gray-500 text-sm">加载数据管理...</span>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5 max-w-[1400px] mx-auto">
      {/* ========== 顶部标题栏 ========== */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Database className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">数据管理中心</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              {selectedExchange.toUpperCase()} · {allSymbols.length} 个交易对 · {allTimeframes.length} 个周期
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadData}
            className="h-9 px-3 rounded-lg bg-gray-800 border border-crypto-border text-gray-400 hover:text-white hover:bg-gray-700 transition text-sm flex items-center gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> 刷新
          </button>
          <button onClick={handleDailyUpdate} disabled={isRunning || syncing}
            className="h-9 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
            <Download className="w-3.5 h-3.5" /> 增量更新
          </button>
          <button onClick={() => setShowCustomSync(!showCustomSync)}
            className={`h-9 px-4 rounded-lg text-sm font-medium flex items-center gap-1.5 transition-all border ${
              showCustomSync
                ? 'bg-purple-600 hover:bg-purple-500 text-white border-purple-500'
                : 'bg-gray-800 border-crypto-border text-gray-300 hover:text-white hover:bg-gray-700'
            }`}>
            <Calendar className="w-3.5 h-3.5" /> 自定义同步
          </button>
          <button onClick={handleStartSync} disabled={isRunning || syncing}
            className="h-9 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
            {isRunning || syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            全量同步
          </button>
        </div>
      </div>

      {/* ========== 自定义同步面板 ========== */}
      {showCustomSync && (
        <div className="bg-crypto-card border border-purple-500/30 rounded-xl p-5 space-y-4 animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="w-4 h-4 text-purple-400" />
            <span className="text-sm font-semibold text-white">自定义同步</span>
            <span className="text-xs text-gray-500 ml-2">选择日期范围、币种和周期，精确补充历史数据</span>
          </div>

          {/* 日期选择器 */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400 w-16">开始日期</label>
              <input type="date" value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
                className="h-9 bg-gray-800 border border-crypto-border rounded-lg px-3 text-sm text-white focus:outline-none focus:border-purple-500 transition" />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400 w-16">结束日期</label>
              <input type="date" value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
                className="h-9 bg-gray-800 border border-crypto-border rounded-lg px-3 text-sm text-white focus:outline-none focus:border-purple-500 transition" />
            </div>
            {/* 快捷日期按钮 */}
            <div className="flex items-center gap-1.5 ml-2">
              {[
                { label: '近1月', days: 30 },
                { label: '近3月', days: 90 },
                { label: '近半年', days: 180 },
                { label: '近1年', days: 365 },
              ].map(({ label, days }) => (
                <button key={days} onClick={() => {
                  const end = new Date();
                  const start = new Date(); start.setDate(start.getDate() - days);
                  setCustomStartDate(start.toISOString().slice(0, 10));
                  setCustomEndDate(end.toISOString().slice(0, 10));
                }}
                  className="px-2.5 py-1 rounded-md text-xs bg-gray-800 border border-crypto-border text-gray-400 hover:text-white hover:bg-gray-700 transition">
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* 币种选择 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <label className="text-xs text-gray-400">交易对</label>
              <button onClick={() => setCustomSymbols(customSymbols.length === allSymbols.length ? [] : [...allSymbols])}
                className="text-[10px] text-purple-400 hover:text-purple-300 transition">
                {customSymbols.length === allSymbols.length ? '取消全选' : '全选'}
              </button>
              {customSymbols.length === 0 && (
                <span className="text-[10px] text-gray-600">（不选 = 全部）</span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {allSymbols.map((sym) => {
                const coin = getCoinBase(sym);
                const selected = customSymbols.includes(sym);
                const color = COIN_COLORS[coin] || '#8B8B8B';
                return (
                  <button key={sym} onClick={() =>
                    setCustomSymbols(selected
                      ? customSymbols.filter(s => s !== sym)
                      : [...customSymbols, sym]
                    )}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition border ${
                      selected
                        ? 'text-white border-opacity-50'
                        : 'text-gray-500 border-crypto-border hover:text-gray-300 bg-gray-800/50'
                    }`}
                    style={selected ? { backgroundColor: color + '22', borderColor: color + '66', color: '#fff' } : {}}>
                    {coin}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 周期选择 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <label className="text-xs text-gray-400">时间周期</label>
              <button onClick={() => setCustomTimeframes(customTimeframes.length === allTimeframes.length ? [] : [...allTimeframes])}
                className="text-[10px] text-purple-400 hover:text-purple-300 transition">
                {customTimeframes.length === allTimeframes.length ? '取消全选' : '全选'}
              </button>
              {customTimeframes.length === 0 && (
                <span className="text-[10px] text-gray-600">（不选 = 全部）</span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {allTimeframes.map((tf: string) => {
                const selected = customTimeframes.includes(tf);
                return (
                  <button key={tf} onClick={() =>
                    setCustomTimeframes(selected
                      ? customTimeframes.filter(t => t !== tf)
                      : [...customTimeframes, tf]
                    )}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition border ${
                      selected
                        ? `${TIMEFRAME_BADGE[tf] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`
                        : 'text-gray-500 border-crypto-border hover:text-gray-300 bg-gray-800/50'
                    }`}>
                    {TIMEFRAME_LABELS[tf] || tf}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 操作按钮 */}
          <div className="flex items-center justify-between pt-2 border-t border-crypto-border">
            <div className="text-xs text-gray-500">
              {customStartDate} ~ {customEndDate}
              {customSymbols.length > 0 ? ` · ${customSymbols.length} 个币种` : ' · 全部币种'}
              {customTimeframes.length > 0 ? ` · ${customTimeframes.join('/')}` : ' · 全部周期'}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setShowCustomSync(false)}
                className="h-8 px-4 rounded-lg bg-gray-800 border border-crypto-border text-gray-400 hover:text-white text-xs transition">
                取消
              </button>
              <button onClick={handleCustomSync} disabled={isRunning || syncing}
                className="h-8 px-5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
                {isRunning || syncing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                开始同步
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== 消息提示 ========== */}
      {syncMsg && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm animate-in fade-in slide-in-from-top-2 ${
          syncMsgType === 'success' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' :
          syncMsgType === 'error' ? 'bg-red-500/10 border-red-500/30 text-red-300' :
          'bg-blue-500/10 border-blue-500/30 text-blue-300'
        }`}>
          {syncMsgType === 'success' ? <CheckCircle className="w-4 h-4 flex-shrink-0" /> :
           syncMsgType === 'error' ? <AlertCircle className="w-4 h-4 flex-shrink-0" /> :
           <Info className="w-4 h-4 flex-shrink-0" />}
          <span className="flex-1">{syncMsg}</span>
          <button onClick={() => setSyncMsg('')} className="opacity-50 hover:opacity-100 transition">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ========== 统计概览 ========== */}
      <div className="grid grid-cols-5 gap-3">
        {/* 总记录数 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute top-3 right-3 opacity-5"><HardDrive className="w-10 h-10" /></div>
          <div className="text-xs text-gray-500 mb-1">总记录数</div>
          <div className="text-2xl font-bold text-white">{formatCount(totalRecords)}</div>
        </div>
        {/* 数据对数 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute top-3 right-3 opacity-5"><BarChart3 className="w-10 h-10" /></div>
          <div className="text-xs text-gray-500 mb-1">数据对数</div>
          <div className="text-2xl font-bold text-white">{totalPairs}</div>
        </div>
        {/* 同步状态 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute top-3 right-3 opacity-5"><Zap className="w-10 h-10" /></div>
          <div className="text-xs text-gray-500 mb-1">同步状态</div>
          <div className={`text-lg font-bold ${isRunning || syncing ? 'text-yellow-400' : 'text-emerald-400'}`}>
            {isRunning || syncing ? '同步中...' : '空闲'}
          </div>
        </div>
        {/* 交易对 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute top-3 right-3 opacity-5"><TrendingUp className="w-10 h-10" /></div>
          <div className="text-xs text-gray-500 mb-1">交易对</div>
          <div className="text-2xl font-bold text-white">{allSymbols.length}</div>
        </div>
        {/* 时间周期 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-4 relative overflow-hidden">
          <div className="absolute top-3 right-3 opacity-5"><Calendar className="w-10 h-10" /></div>
          <div className="text-xs text-gray-500 mb-1">时间周期</div>
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {allTimeframes.map((tf: string) => (
              <span key={tf} className={`text-[10px] px-1.5 py-0.5 rounded border ${TIMEFRAME_BADGE[tf] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
                {TIMEFRAME_LABELS[tf] || tf}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ========== 过滤和搜索 ========== */}
      <div className="flex items-center gap-3">
        <div className="relative flex-shrink-0">
          <Search className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input type="text" placeholder="搜索币种..."
            value={filterSymbol} onChange={(e) => setFilterSymbol(e.target.value)}
            className="h-9 bg-gray-800 border border-crypto-border rounded-lg pl-9 pr-3 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 transition w-44" />
        </div>
        <div className="flex items-center gap-1 bg-crypto-card rounded-lg p-1 border border-crypto-border">
          <button onClick={() => setFilterTf('')}
            className={`px-3 py-1 rounded-md text-xs font-medium transition ${!filterTf ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}>
            全部
          </button>
          {allTimeframes.map((tf: string) => (
            <button key={tf} onClick={() => setFilterTf(filterTf === tf ? '' : tf)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition ${filterTf === tf ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}>
              {TIMEFRAME_LABELS[tf] || tf}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <span className="text-xs text-gray-500">共 {filteredSymbols.length} 个交易对</span>
      </div>

      {/* ========== 交易对卡片列表 ========== */}
      <div className="space-y-2.5">
        {filteredSymbols.map((symbol) => {
          const coin = getCoinBase(symbol);
          const color = COIN_COLORS[coin] || '#8B8B8B';
          const total = symbolTotalRecords(symbol);
          const filled = symbolFilledTf(symbol);
          const isExpanded = expandedSymbol === symbol;
          const displayTfs = filterTf ? allTimeframes.filter((t: string) => t === filterTf) : allTimeframes;

          return (
            <div key={symbol} className="bg-crypto-card border border-crypto-border rounded-xl overflow-hidden hover:border-gray-600 transition-all">
              {/* 卡片头部 */}
              <div className="flex items-center px-5 py-3.5 cursor-pointer select-none gap-5"
                   onClick={() => setExpandedSymbol(isExpanded ? null : symbol)}>
                {/* 币种标识 */}
                <div className="flex items-center gap-3 w-32 flex-shrink-0">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white"
                       style={{ backgroundColor: color + '33', border: `1px solid ${color}55` }}>
                    {coin.slice(0, 2)}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{coin}</div>
                    <div className="text-[10px] text-gray-500">/USDT</div>
                  </div>
                </div>

                {/* 周期数据条 — 使用 grid 保证等宽布局，筛选单个时限制最大宽度 */}
                <div className={`grid gap-2.5 flex-1 ${
                  displayTfs.length === 1 ? 'grid-cols-3' :
                  displayTfs.length === 2 ? 'grid-cols-4' :
                  displayTfs.length === 3 ? 'grid-cols-3' :
                  displayTfs.length === 4 ? 'grid-cols-4' :
                  'grid-cols-5'
                }`}>
                  {displayTfs.map((tf: string) => {
                    const stat = statMap.get(`${symbol}_${tf}`);
                    const count = stat?.recordCount || 0;
                    const hasData = count > 0;
                    const freshness = getDataFreshness(stat?.lastTimestamp || null);
                    const coverage = getCoveragePercent(stat?.firstTimestamp || null, stat?.lastTimestamp || null, 365);

                    return (
                      <div key={tf} className={`rounded-lg border px-3 py-2 bg-gradient-to-br ${
                        hasData ? TIMEFRAME_COLORS[tf] || 'from-gray-500/10 border-gray-500/20' : 'from-transparent border-crypto-border'
                      } transition-all ${displayTfs.length === 1 ? 'col-span-1' : ''}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className={`text-[10px] font-medium ${hasData ? 'text-white/70' : 'text-gray-600'}`}>
                            {TIMEFRAME_LABELS[tf] || tf}
                          </span>
                          {hasData && (
                            <span className={`text-[10px] ${freshness.color}`}>
                              {freshness.label}
                            </span>
                          )}
                        </div>
                        {hasData ? (
                          <>
                            <div className="text-xs font-bold text-white">{formatCount(count)}</div>
                            <div className="h-0.5 bg-white/5 rounded-full mt-1.5 overflow-hidden">
                              <div className="h-full bg-white/30 rounded-full transition-all" style={{ width: `${coverage}%` }} />
                            </div>
                          </>
                        ) : (
                          <div className="text-[10px] text-gray-600 py-0.5">-</div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* 右侧汇总 */}
                <div className="flex items-center gap-4 w-40 flex-shrink-0 justify-end">
                  <div className="text-right">
                    <div className="text-xs text-gray-500">
                      {filled}/{allTimeframes.length} 周期
                    </div>
                    <div className="text-sm font-bold text-white">
                      {total > 0 ? formatCount(total) : '-'}
                    </div>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                </div>
              </div>

              {/* 展开详情 */}
              {isExpanded && (
                <div className="border-t border-crypto-border px-5 py-4 bg-crypto-bg/50">
                  {/* 日期选择器 */}
                  <div className="flex items-center gap-3 mb-4 pb-3 border-b border-crypto-border">
                    <Calendar className="w-3.5 h-3.5 text-gray-500" />
                    <span className="text-xs text-gray-500">同步范围:</span>
                    <input type="date" value={detailStartDate}
                      onChange={(e) => setDetailStartDate(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      className="h-7 bg-gray-800 border border-crypto-border rounded-md px-2 text-xs text-white focus:outline-none focus:border-blue-500 transition" />
                    <span className="text-xs text-gray-600">~</span>
                    <input type="date" value={detailEndDate}
                      onChange={(e) => setDetailEndDate(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      className="h-7 bg-gray-800 border border-crypto-border rounded-md px-2 text-xs text-white focus:outline-none focus:border-blue-500 transition" />
                    {[
                      { label: '1月', days: 30 },
                      { label: '3月', days: 90 },
                      { label: '半年', days: 180 },
                      { label: '1年', days: 365 },
                    ].map(({ label, days }) => (
                      <button key={days} onClick={(e) => {
                        e.stopPropagation();
                        const end = new Date();
                        const start = new Date(); start.setDate(start.getDate() - days);
                        setDetailStartDate(start.toISOString().slice(0, 10));
                        setDetailEndDate(end.toISOString().slice(0, 10));
                      }}
                        className="px-2 py-0.5 rounded text-[10px] bg-gray-800 border border-crypto-border text-gray-500 hover:text-white hover:bg-gray-700 transition">
                        {label}
                      </button>
                    ))}
                  </div>

                  <div className={`grid gap-3 ${
                    allTimeframes.length <= 5 ? 'grid-cols-5' : 'grid-cols-6'
                  }`}>
                    {allTimeframes.map((tf: string) => {
                      const key = `${symbol}_${tf}`;
                      const stat = statMap.get(key);
                      const meta = metaMap.get(key);
                      const count = stat?.recordCount || 0;
                      const hasData = count > 0;
                      const metaStatus = meta?.status || 'idle';
                      const metaLastSync = meta?.lastSyncAt || null;
                      const metaError = meta?.errorMessage || null;
                      const freshness = getDataFreshness(stat?.lastTimestamp || null);
                      const coverage = getCoveragePercent(stat?.firstTimestamp || null, stat?.lastTimestamp || null, 365);

                      return (
                        <div key={tf} className={`rounded-xl border p-3 bg-gradient-to-br ${
                          hasData ? TIMEFRAME_COLORS[tf] || 'from-gray-500/10 border-gray-500/20' : 'from-crypto-card border-crypto-border'
                        }`}>
                          <div className="flex items-center justify-between mb-2">
                            <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${TIMEFRAME_BADGE[tf] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
                              {TIMEFRAME_LABELS[tf] || tf}
                            </span>
                            {metaStatus === 'syncing' ? (
                              <Loader2 className="w-3.5 h-3.5 text-yellow-400 animate-spin" />
                            ) : metaStatus === 'completed' && hasData ? (
                              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                            ) : metaStatus === 'error' ? (
                              <XCircle className="w-3.5 h-3.5 text-red-400" />
                            ) : (
                              <Clock className="w-3.5 h-3.5 text-gray-500" />
                            )}
                          </div>

                          {hasData ? (
                            <div className="space-y-2">
                              <div className="text-lg font-bold text-white">{formatCount(count)}</div>
                              <div className="space-y-1 text-[10px] text-gray-500">
                                <div className="flex justify-between">
                                  <span>起始</span>
                                  <span className="text-white/70">{formatTs(stat?.firstTimestamp || null)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span>结束</span>
                                  <span className={freshness.color}>{formatTs(stat?.lastTimestamp || null)}</span>
                                </div>
                                {metaLastSync && (
                                  <div className="flex justify-between">
                                    <span>同步于</span>
                                    <span className="text-white/50">{metaLastSync}</span>
                                  </div>
                                )}
                              </div>
                              {/* 覆盖率 */}
                              <div>
                                <div className="flex items-center justify-between text-[10px] mb-0.5">
                                  <span className="text-gray-500">覆盖率</span>
                                  <span className="text-white/60">{coverage}%</span>
                                </div>
                                <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                                  <div className={`h-full rounded-full transition-all ${
                                    coverage >= 80 ? 'bg-emerald-400' : coverage >= 50 ? 'bg-yellow-400' : 'bg-red-400'
                                  }`} style={{ width: `${coverage}%` }} />
                                </div>
                              </div>
                              <div className="flex gap-1">
                                <button onClick={(e) => { e.stopPropagation(); handleSyncOne(symbol, tf); }}
                                  disabled={isRunning || syncing}
                                  className="flex-1 text-[10px] py-1 rounded-md bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white border border-crypto-border transition disabled:opacity-30">
                                  增量
                                </button>
                                <button onClick={(e) => { e.stopPropagation(); handleSyncOne(symbol, tf, detailStartDate, detailEndDate); }}
                                  disabled={isRunning || syncing}
                                  className="flex-1 text-[10px] py-1 rounded-md bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 hover:text-purple-200 border border-purple-500/20 transition disabled:opacity-30"
                                  title={`按日期同步 ${detailStartDate} ~ ${detailEndDate}`}>
                                  按日期
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="space-y-2">
                              <div className="text-sm text-gray-600 py-2">暂无数据</div>
                              {metaError && (
                                <div className="text-[10px] text-red-400 truncate" title={metaError}>
                                  {metaError}
                                </div>
                              )}
                              <button onClick={(e) => { e.stopPropagation(); handleSyncOne(symbol, tf, detailStartDate, detailEndDate); }}
                                disabled={isRunning || syncing}
                                className="w-full text-[10px] py-1.5 rounded-md bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 border border-blue-500/20 transition font-medium disabled:opacity-30">
                                开始同步
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {/* 底部操作 */}
                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-crypto-border">
                    <button onClick={(e) => { e.stopPropagation(); handleDelete(symbol); }}
                      className="text-xs text-red-400/70 hover:text-red-400 flex items-center gap-1 transition">
                      <Trash2 className="w-3 h-3" /> 删除 {coin} 全部数据
                    </button>
                    <button onClick={(e) => { e.stopPropagation();
                      allTimeframes.forEach((tf: string) => { if (!statMap.get(`${symbol}_${tf}`)?.recordCount) handleSyncOne(symbol, tf); }); }}
                      disabled={isRunning || syncing}
                      className="text-xs text-blue-400/70 hover:text-blue-400 flex items-center gap-1 transition disabled:opacity-30">
                      <Download className="w-3 h-3" /> 同步缺失周期
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ========== 说明面板 ========== */}
      <div className="bg-crypto-card border border-crypto-border rounded-xl p-4">
        <div className="flex items-start gap-3">
          <Info className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
          <div className="text-xs text-gray-500 space-y-1">
            <p><strong className="text-gray-300">全量同步</strong> — 拉取每个交易对最近 <strong className="text-gray-300">1 年</strong> 的 1m/5m/15m/1h/4h/1d 数据，首次需要较长时间</p>
            <p><strong className="text-gray-300">自定义同步</strong> — 选择日期范围、币种和周期，<strong className="text-gray-300">精确指定</strong>要拉取的历史数据</p>
            <p><strong className="text-gray-300">增量更新</strong> — 从上次同步位置继续拉取新数据，同时回溯 <strong className="text-gray-300">7 天</strong> 以防断档。适合日常使用</p>
            <p><strong className="text-gray-300">展开详情 → 按日期</strong> — 在每个交易对的展开面板中，通过顶部日期选择器指定范围后，点击"按日期"按钮同步</p>
            <p><strong className="text-gray-300">数据覆盖率</strong> — 绿色({'>'}80%) = 完整 / 黄色(50-80%) = 部分 / 红色({'<'}50%) = 缺失较多</p>
            <p><strong className="text-gray-300">分表存储</strong> — 每个周期独立表 (kline_1m, kline_5m, kline_15m, kline_1h, kline_4h, kline_1d)，查询性能更优</p>
          </div>
        </div>
      </div>
    </div>
  );
}
