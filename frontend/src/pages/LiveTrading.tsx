import { useState, useEffect, useRef } from 'react';
import {
  Rocket, Square, Pause, Play, Settings2, Activity, ShieldCheck,
  TrendingUp, TrendingDown, AlertTriangle, CheckCircle2, XCircle,
  Zap, Clock, DollarSign, BarChart3, List, ChevronRight,
  Eye, Loader2, Wallet, FlaskConical, Radio, Plus,
} from 'lucide-react';
import * as echarts from 'echarts';
import { liveApi, paperApi, tradingApi } from '../api/client';
import { useStore } from '../stores/useStore';
import clsx from 'clsx';

// ============================================
// 类型定义
// ============================================
interface BacktestData {
  totalReturn?: number;
  annualReturn?: number;
  maxDrawdown?: number;
  sharpeRatio?: number;
  winRate?: number;
  totalTrades?: number;
  profitFactor?: number;
  backtestId?: number;
}

interface StrategyInfo {
  id: string | number;
  name: string;
  description: string;
  recommended?: boolean;
  riskLevel?: string;
  risk_level?: string;
  timeframe?: string;
  suitableFor?: string;
  backtest?: BacktestData;
}

interface DashboardData {
  system: {
    state: string;
    uptime: string;
    exchange: string;
    symbol: string;
    timeframe: string;
    strategy: string;
    dryRun: boolean;
    mode: string;
  };
  equity: {
    initial?: number;
    current?: number;
    peak?: number;
    change?: number;
    changePct?: number;
  };
  performance: {
    totalPnl?: number;
    totalPnlPct?: number;
    winRate?: number;
    totalTrades?: number;
    maxDrawdown?: number;
    sharpeRatio?: number;
  };
  risk: {
    circuitBreaker?: boolean;
    currentDrawdown?: number;
    dailyLoss?: number;
  };
  recentEvents: Array<{
    time: string;
    type: string;
    message: string;
    detail?: string;
  }>;
  telegram: {
    enabled: boolean;
    messagesSent: number;
  };
}

interface Balance {
  currency: string;
  free: number;
  used: number;
  total: number;
}

type TradeMode = 'paper' | 'live';
type Step = 'select' | 'configure' | 'preflight' | 'running';

// ============================================
// 常量
// ============================================
const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];
const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT',
  'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'LINK/USDT', 'UNI/USDT', 'NEAR/USDT'];

// ============================================
// 主组件
// ============================================
export default function LiveTrading() {
  const { selectedExchange } = useStore();

  // ---- 模式 Tab ----
  const [tradeMode, setTradeMode] = useState<TradeMode>('paper');

  // 步骤控制
  const [step, setStep] = useState<Step>('select');

  // 策略数据
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string | number>('');
  const [loading, setLoading] = useState(false);

  // 配置表单
  const [config, setConfig] = useState({
    symbol: 'BTC/USDT',
    timeframe: '4h',
    initialEquity: 1000,
    loopInterval: 60,
    riskPerTrade: 0.03,
    maxDailyLoss: 0.05,
    maxTotalLoss: 0.15,
  });

  // 实盘余额
  const [balances, setBalances] = useState<Balance[]>([]);
  const [balanceLoading, setBalanceLoading] = useState(false);

  // 飞行检查
  const [preflightResult, setPreflightResult] = useState<any>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);

  // 运行监控
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [equityCurve, setEquityCurve] = useState<any[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  // 模拟盘结果 (当前选中查看的)
  const [paperResult, setPaperResult] = useState<any>(null);
  const [paperLoading, setPaperLoading] = useState(false);

  // 模拟盘实例列表
  const [paperInstances, setPaperInstances] = useState<any[]>([]);

  // 实盘确认对话框
  const [showLiveConfirm, setShowLiveConfirm] = useState(false);

  const isDryRun = tradeMode === 'paper';

  // 获取当前选中策略的中文名称
  const selectedStrategyName = strategies.find(s => s.id === selectedStrategy)?.name || String(selectedStrategy);

  // ---- 切换模式时重置 ----
  const handleModeChange = (mode: TradeMode) => {
    if (isRunning || isPaused) return;
    setTradeMode(mode);
    setStep('select');
    setPreflightResult(null);
    setPaperResult(null);
  };

  // 加载模拟盘实例列表
  const loadPaperInstances = async () => {
    try {
      const res = await paperApi.getInstances();
      setPaperInstances(res.instances || []);
    } catch (err) {
      console.error('加载模拟盘实例失败:', err);
    }
  };

  // 删除模拟盘实例
  const handleDeleteInstance = async (instanceId: string) => {
    try {
      await paperApi.deleteInstance(instanceId);
      loadPaperInstances();
    } catch (err) {
      console.error('删除实例失败:', err);
    }
  };

  // 加载策略列表和实例
  useEffect(() => {
    loadStrategies();
    loadPaperInstances();
    checkRunningStatus();
  }, []);

  // 实盘模式自动获取余额
  useEffect(() => {
    if (tradeMode === 'live') {
      fetchBalance();
    }
  }, [tradeMode, selectedExchange]);

  const fetchBalance = async () => {
    setBalanceLoading(true);
    try {
      const payload = await tradingApi.getBalance(selectedExchange);
      setBalances(payload.balance || []);
    } catch (err) {
      console.error('获取余额失败:', err);
    } finally {
      setBalanceLoading(false);
    }
  };

  const loadStrategies = async () => {
    try {
      const res = await liveApi.getStrategies();
      const raw = res.strategies || [];
      let list: StrategyInfo[];
      if (Array.isArray(raw)) {
        list = raw;
      } else {
        list = Object.entries(raw).map(([key, val]: [string, any]) => ({
          ...val,
          id: key,
        }));
      }
      setStrategies(list);
      if (res.recommended && !selectedStrategy) {
        setSelectedStrategy(res.recommended);
      }
    } catch (err) {
      console.error('加载策略列表失败:', err);
    }
  };

  const checkRunningStatus = async () => {
    try {
      const dash = await liveApi.getDashboard();
      if (dash?.system?.state === 'running' || dash?.system?.state === 'paused') {
        setDashboard(dash);
        setIsRunning(dash.system.state === 'running');
        setIsPaused(dash.system.state === 'paused');
        setTradeMode(dash.system.dryRun !== false ? 'paper' : 'live');
        setStep('running');
      }
    } catch {
      // 未运行
    }
  };

  // USDT 余额
  const usdtBalance = balances.find(b => b.currency === 'USDT');

  // ============================================
  // Step 1: 选择策略
  // ============================================
  const renderSelectStep = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Rocket className="w-6 h-6 text-blue-400" />
        <h2 className="text-xl font-bold text-white">选择交易策略</h2>
      </div>

      {/* 实盘模式 - 显示账户余额 */}
      {tradeMode === 'live' && (
        <div className="bg-gradient-to-r from-orange-600/10 to-red-600/10 border border-orange-500/30 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Wallet className="w-5 h-5 text-orange-400" />
              <div>
                <div className="text-sm font-semibold text-white">
                  实盘账户 · {selectedExchange.toUpperCase()}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">
                  将使用您的真实资金进行交易
                </div>
              </div>
            </div>
            <div className="text-right">
              {balanceLoading ? (
                <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
              ) : usdtBalance ? (
                <>
                  <div className="text-lg font-bold text-white">${usdtBalance.total.toFixed(2)}</div>
                  <div className="text-[10px] text-gray-500">
                    可用: ${usdtBalance.free.toFixed(2)} · 冻结: ${usdtBalance.used.toFixed(2)}
                  </div>
                </>
              ) : (
                <div className="text-sm text-gray-500">无余额数据</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 模拟盘：已运行实例列表 */}
      {isDryRun && paperInstances.length > 0 && (
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-purple-400" />
              运行中的模拟盘 ({paperInstances.length})
            </h3>
            {paperInstances.length > 1 && (
              <button
                onClick={async () => { await paperApi.clearInstances(); loadPaperInstances(); }}
                className="text-[10px] text-gray-500 hover:text-red-400 transition-colors"
              >全部清空</button>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {paperInstances.map((inst: any) => (
              <div key={inst.instanceId || inst.instance_id} className="bg-crypto-bg rounded-lg p-3 border border-crypto-border">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-white truncate pr-2">{inst.strategyName || inst.strategy_name}</span>
                  <button
                    onClick={() => handleDeleteInstance(inst.instanceId || inst.instance_id)}
                    className="text-gray-600 hover:text-red-400 transition-colors flex-shrink-0"
                  ><XCircle className="w-3.5 h-3.5" /></button>
                </div>
                <div className="text-[10px] text-gray-500 mb-2">{inst.symbol} · {inst.timeframe} · {inst.daysBack || inst.days_back}天</div>
                <div className="grid grid-cols-3 gap-1 text-center">
                  <div>
                    <div className={clsx('text-xs font-bold', (inst.totalReturnPct ?? inst.total_return_pct ?? 0) >= 0 ? 'text-up' : 'text-down')}>
                      {(inst.totalReturnPct ?? inst.total_return_pct ?? 0).toFixed(1)}%
                    </div>
                    <div className="text-[8px] text-gray-600">收益</div>
                  </div>
                  <div>
                    <div className="text-xs font-bold text-white">{(inst.sharpeRatio ?? inst.sharpe_ratio ?? 0).toFixed(2)}</div>
                    <div className="text-[8px] text-gray-600">夏普</div>
                  </div>
                  <div>
                    <div className="text-xs font-bold text-red-300">{(inst.maxDrawdownPct ?? inst.max_drawdown_pct ?? 0).toFixed(1)}%</div>
                    <div className="text-[8px] text-gray-600">回撤</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {strategies.map((s) => {
          const sid = s.id;
          const isSelected = selectedStrategy === sid;
          const bt = s.backtest;
          const riskLevel = s.riskLevel || s.risk_level;
          const riskColor = riskLevel === '低' ? 'text-green-400' : riskLevel === '中' ? 'text-yellow-400' : riskLevel === '中低' ? 'text-green-300' : riskLevel === '中高' ? 'text-orange-400' : 'text-gray-400';

          return (
            <button
              key={sid}
              onClick={() => setSelectedStrategy(sid)}
              className={clsx(
                'relative p-5 rounded-xl border text-left transition-all',
                isSelected
                  ? 'border-blue-500 bg-blue-500/10 ring-1 ring-blue-500/30'
                  : 'border-crypto-border bg-crypto-card hover:border-gray-600'
              )}
            >
              <div className="absolute top-3 right-3 flex items-center gap-1.5">
                {s.recommended && (
                  <span className="px-2 py-0.5 text-[10px] font-bold bg-green-500/20 text-green-400 rounded-full">推荐</span>
                )}
                {riskLevel && (
                  <span className={clsx('px-2 py-0.5 text-[10px] font-bold rounded-full bg-gray-700/50', riskColor)}>
                    {riskLevel}风险
                  </span>
                )}
              </div>
              <h3 className="text-sm font-semibold text-white mb-1.5 pr-24">{s.name || sid}</h3>
              <p className="text-xs text-gray-400 leading-relaxed">{s.description}</p>
              <div className="mt-2.5 flex items-center gap-3 text-[10px] text-gray-500">
                {s.timeframe && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{s.timeframe}</span>}
                {s.suitableFor && <span className="flex items-center gap-1"><Zap className="w-3 h-3" />{s.suitableFor}</span>}
              </div>
              {bt && (
                <div className="mt-3 pt-3 border-t border-crypto-border">
                  <div className="text-[10px] text-gray-500 mb-2 flex items-center gap-1"><BarChart3 className="w-3 h-3" />回测绩效</div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="text-center">
                      <div className={clsx('text-xs font-bold', (bt.totalReturn ?? 0) >= 0 ? 'text-up' : 'text-down')}>
                        {bt.totalReturn != null ? `${bt.totalReturn >= 0 ? '+' : ''}${bt.totalReturn.toFixed(1)}%` : '-'}
                      </div>
                      <div className="text-[9px] text-gray-600">总收益</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs font-bold text-white">{bt.sharpeRatio != null ? bt.sharpeRatio.toFixed(2) : '-'}</div>
                      <div className="text-[9px] text-gray-600">夏普</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs font-bold text-red-300">{bt.maxDrawdown != null ? `${bt.maxDrawdown.toFixed(1)}%` : '-'}</div>
                      <div className="text-[9px] text-gray-600">最大回撤</div>
                    </div>
                  </div>
                </div>
              )}
              {!bt && (
                <div className="mt-3 pt-3 border-t border-crypto-border">
                  <div className="text-[10px] text-gray-600 flex items-center gap-1"><BarChart3 className="w-3 h-3" />暂无回测数据</div>
                </div>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex justify-end pt-4">
        <button
          disabled={!selectedStrategy}
          onClick={() => setStep('configure')}
          className={clsx(
            'flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-medium transition-colors',
            selectedStrategy ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-700 text-gray-500 cursor-not-allowed'
          )}
        >
          下一步: 配置参数<ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  // ============================================
  // Step 2: 配置参数
  // ============================================
  const handleRunPaper = async () => {
    setPaperLoading(true);
    setPaperResult(null);
    try {
      const res = await paperApi.run({
        strategy: String(selectedStrategy),
        exchange: selectedExchange,
        symbol: config.symbol,
        timeframe: config.timeframe,
        initial_capital: config.initialEquity,
        stop_loss: 0.05,
        days_back: 30,
      });
      setPaperResult(res);
      // 刷新实例列表
      loadPaperInstances();
    } catch (err: any) {
      setPaperResult({ error: err?.response?.data?.detail || err.message || '模拟盘失败' });
    } finally {
      setPaperLoading(false);
    }
  };

  const renderConfigStep = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Settings2 className="w-6 h-6 text-blue-400" />
        <h2 className="text-xl font-bold text-white">配置参数</h2>
        <span className="px-3 py-1 text-xs bg-blue-500/20 text-blue-400 rounded-full">{selectedStrategyName}</span>
        <span className={clsx('px-3 py-1 text-xs rounded-full', isDryRun ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400')}>
          {isDryRun ? '模拟盘' : '实盘'}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 左: 交易配置 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-blue-400" />
            交易配置
          </h3>

          <div className="space-y-3">
            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">交易对</span>
              <select
                value={config.symbol}
                onChange={(e) => setConfig({ ...config, symbol: e.target.value })}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white"
              >
                {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>

            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">K线周期</span>
              <select
                value={config.timeframe}
                onChange={(e) => setConfig({ ...config, timeframe: e.target.value })}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white"
              >
                {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>

            {/* 资金配置 - 根据模式不同 */}
            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">
                {isDryRun ? '模拟初始资金 (USDT)' : '投入资金 (USDT)'}
              </span>
              <input
                type="number"
                value={config.initialEquity}
                onChange={(e) => setConfig({ ...config, initialEquity: Number(e.target.value) })}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white"
              />
              {!isDryRun && usdtBalance && (
                <div className="mt-1.5 flex items-center justify-between text-xs">
                  <span className="text-gray-500">
                    账户可用: <span className="text-green-400">${usdtBalance.free.toFixed(2)}</span>
                  </span>
                  <div className="flex gap-2">
                    {[25, 50, 75, 100].map(pct => (
                      <button
                        key={pct}
                        onClick={() => setConfig({ ...config, initialEquity: Math.floor(usdtBalance.free * pct / 100) })}
                        className="px-2 py-0.5 bg-gray-800 text-gray-400 rounded hover:bg-gray-700 hover:text-white text-[10px]"
                      >
                        {pct}%
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </label>

            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">检查间隔 (秒)</span>
              <input
                type="number"
                value={config.loopInterval}
                onChange={(e) => setConfig({ ...config, loopInterval: Number(e.target.value) })}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white"
              />
            </label>

            {/* 模式展示（只读） */}
            <div className="flex items-center justify-between py-2 px-3 bg-crypto-bg rounded-lg border border-crypto-border">
              <div>
                <span className="text-xs text-gray-400 block">运行模式</span>
                <span className={clsx('text-sm font-medium', isDryRun ? 'text-yellow-400' : 'text-red-400')}>
                  {isDryRun ? '模拟模式 (不实际下单)' : '实盘模式 (真实下单)'}
                </span>
              </div>
              <div className={clsx('w-3 h-3 rounded-full', isDryRun ? 'bg-yellow-400' : 'bg-red-400')} />
            </div>
          </div>
        </div>

        {/* 右: 风控配置 */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-green-400" />
            风控配置
          </h3>

          <div className="space-y-3">
            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">单笔风险比例</span>
              <div className="flex items-center gap-2">
                <input type="range" min="0.01" max="0.1" step="0.01" value={config.riskPerTrade}
                  onChange={(e) => setConfig({ ...config, riskPerTrade: Number(e.target.value) })} className="flex-1" />
                <span className="text-sm text-white w-12 text-right">{(config.riskPerTrade * 100).toFixed(0)}%</span>
              </div>
            </label>

            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">单日最大亏损</span>
              <div className="flex items-center gap-2">
                <input type="range" min="0.02" max="0.2" step="0.01" value={config.maxDailyLoss}
                  onChange={(e) => setConfig({ ...config, maxDailyLoss: Number(e.target.value) })} className="flex-1" />
                <span className="text-sm text-white w-12 text-right">{(config.maxDailyLoss * 100).toFixed(0)}%</span>
              </div>
            </label>

            <label className="block">
              <span className="text-xs text-gray-400 mb-1 block">总最大亏损 (熔断线)</span>
              <div className="flex items-center gap-2">
                <input type="range" min="0.05" max="0.5" step="0.01" value={config.maxTotalLoss}
                  onChange={(e) => setConfig({ ...config, maxTotalLoss: Number(e.target.value) })} className="flex-1" />
                <span className="text-sm text-white w-12 text-right">{(config.maxTotalLoss * 100).toFixed(0)}%</span>
              </div>
            </label>
          </div>

          {/* 模拟盘快速验证 */}
          <div className="mt-4 pt-4 border-t border-crypto-border">
            <h4 className="text-xs text-gray-400 mb-3">快速验证 (最近30天模拟盘)</h4>
            <button
              onClick={handleRunPaper}
              disabled={paperLoading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-600/20 text-purple-400 border border-purple-500/30 rounded-lg text-sm hover:bg-purple-600/30 transition-colors disabled:opacity-50"
            >
              {paperLoading ? <><Loader2 className="w-4 h-4 animate-spin" />运行模拟盘中...</> : <><Eye className="w-4 h-4" />运行模拟盘验证</>}
            </button>
            {paperResult && !paperResult.error && (
              <div className="mt-3 space-y-3">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-crypto-bg rounded-lg p-2">
                    <div className={clsx('text-sm font-bold', (paperResult.totalReturnPct ?? paperResult.total_return_pct ?? 0) >= 0 ? 'text-up' : 'text-down')}>
                      {((paperResult.totalReturnPct ?? paperResult.total_return_pct ?? 0)).toFixed(1)}%
                    </div>
                    <div className="text-[10px] text-gray-500">收益率</div>
                  </div>
                  <div className="bg-crypto-bg rounded-lg p-2">
                    <div className="text-sm font-bold text-white">{(paperResult.sharpeRatio ?? paperResult.sharpe_ratio ?? 0).toFixed(2)}</div>
                    <div className="text-[10px] text-gray-500">夏普比率</div>
                  </div>
                  <div className="bg-crypto-bg rounded-lg p-2">
                    <div className="text-sm font-bold text-red-400">{(paperResult.maxDrawdownPct ?? paperResult.max_drawdown_pct ?? 0).toFixed(1)}%</div>
                    <div className="text-[10px] text-gray-500">最大回撤</div>
                  </div>
                </div>
                {/* 继续新建按钮 */}
                <button
                  onClick={() => { setStep('select'); setPaperResult(null); }}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-lg text-xs hover:bg-blue-600/30 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />再启动一个模拟盘
                </button>
              </div>
            )}
            {paperResult?.error && (
              <div className="mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400">{paperResult.error}</div>
            )}
          </div>
        </div>
      </div>

      <div className="flex justify-between pt-4">
        <button onClick={() => setStep('select')} className="px-6 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white transition-colors">返回</button>
        <button
          onClick={() => setStep('preflight')}
          className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          下一步: 飞行检查<ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  // ============================================
  // Step 3: 飞行检查
  // ============================================
  const runPreFlight = async () => {
    setPreflightLoading(true);
    setPreflightResult(null);
    try {
      const res = await liveApi.preFlight({
        strategy: String(selectedStrategy),
        symbol: config.symbol,
        timeframe: config.timeframe,
        capital_pct: 0.1,
        total_capital: config.initialEquity,
      });
      setPreflightResult(res);
    } catch (err: any) {
      setPreflightResult({
        allPassed: false,
        all_passed: false,
        checks: [{ item: '飞行检查执行失败', passed: false, detail: err?.response?.data?.detail || err.message }],
      });
    } finally {
      setPreflightLoading(false);
    }
  };

  const handleLaunch = async () => {
    // 实盘模式需要二次确认
    if (!isDryRun && !showLiveConfirm) {
      setShowLiveConfirm(true);
      return;
    }
    setShowLiveConfirm(false);
    setLoading(true);
    try {
      // 使用第一个策略 (实盘只支持单策略)
      await liveApi.configure({
        exchange: selectedExchange,
        strategy_type: String(selectedStrategy),
        symbol: config.symbol,
        timeframe: config.timeframe,
        initial_equity: config.initialEquity,
        dry_run: isDryRun,
        loop_interval: config.loopInterval,
        risk_config: {
          risk_per_trade_pct: config.riskPerTrade,
          max_daily_loss_pct: config.maxDailyLoss,
          max_total_loss_pct: config.maxTotalLoss,
        },
      });
      await liveApi.start();
      setIsRunning(true);
      setStep('running');
    } catch (err: any) {
      alert('启动失败: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const renderPreflightStep = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <ShieldCheck className="w-6 h-6 text-green-400" />
        <h2 className="text-xl font-bold text-white">飞行检查</h2>
      </div>

      {/* 配置摘要 */}
      <div className="bg-crypto-card border border-crypto-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3">配置摘要</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div><span className="text-[10px] text-gray-500 block">策略</span><span className="text-sm text-white">{selectedStrategyName}</span></div>
          <div><span className="text-[10px] text-gray-500 block">交易对</span><span className="text-sm text-white">{config.symbol}</span></div>
          <div><span className="text-[10px] text-gray-500 block">周期</span><span className="text-sm text-white">{config.timeframe}</span></div>
          <div>
            <span className="text-[10px] text-gray-500 block">模式</span>
            <span className={clsx('text-sm font-medium', isDryRun ? 'text-yellow-400' : 'text-red-400')}>
              {isDryRun ? '模拟盘' : '实盘'}
            </span>
          </div>
          <div><span className="text-[10px] text-gray-500 block">{isDryRun ? '模拟资金' : '投入资金'}</span><span className="text-sm text-white">${config.initialEquity}</span></div>
          <div><span className="text-[10px] text-gray-500 block">单笔风险</span><span className="text-sm text-white">{(config.riskPerTrade * 100).toFixed(0)}%</span></div>
          <div><span className="text-[10px] text-gray-500 block">日损限额</span><span className="text-sm text-white">{(config.maxDailyLoss * 100).toFixed(0)}%</span></div>
          <div><span className="text-[10px] text-gray-500 block">熔断线</span><span className="text-sm text-white">{(config.maxTotalLoss * 100).toFixed(0)}%</span></div>
        </div>
      </div>

      {/* 实盘警告 */}
      {!isDryRun && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-semibold text-red-400">实盘交易风险警告</div>
            <div className="text-xs text-red-300/70 mt-1 leading-relaxed">
              即将使用您在 {selectedExchange.toUpperCase()} 的真实资金进行交易。策略将自动下单，
              可能造成本金亏损。请确保您已充分了解策略风险，并设置了合理的止损参数。
            </div>
          </div>
        </div>
      )}

      {/* 检查结果 */}
      {!preflightResult && !preflightLoading && (
        <div className="text-center py-8">
          <button onClick={runPreFlight}
            className="inline-flex items-center gap-2 px-8 py-3 bg-green-600/20 text-green-400 border border-green-500/30 rounded-xl text-sm font-medium hover:bg-green-600/30 transition-colors">
            <ShieldCheck className="w-5 h-5" />运行飞行检查
          </button>
          <p className="text-xs text-gray-500 mt-3">在正式上线前验证系统环境、数据、连接状态</p>
        </div>
      )}

      {preflightLoading && (
        <div className="text-center py-8">
          <Loader2 className="w-8 h-8 text-blue-400 animate-spin mx-auto mb-3" />
          <p className="text-sm text-gray-400">正在进行飞行检查...</p>
        </div>
      )}

      {preflightResult && (
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 mb-4">
            {(preflightResult.allPassed ?? preflightResult.all_passed) ? (
              <><CheckCircle2 className="w-5 h-5 text-green-400" /><span className="text-green-400 font-semibold text-sm">全部通过</span></>
            ) : (
              <><AlertTriangle className="w-5 h-5 text-yellow-400" /><span className="text-yellow-400 font-semibold text-sm">存在未通过项</span></>
            )}
          </div>
          {(preflightResult.checks || []).map((check: any, i: number) => (
            <div key={i} className={clsx('flex items-start gap-3 p-3 rounded-lg', check.passed ? 'bg-green-500/5' : 'bg-red-500/5')}>
              {check.passed ? <CheckCircle2 className="w-4 h-4 text-green-400 mt-0.5 shrink-0" /> : <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />}
              <div>
                <div className="text-sm text-white">{check.item}</div>
                {check.detail && <div className="text-xs text-gray-500 mt-0.5">{check.detail}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-between pt-4">
        <button onClick={() => setStep('configure')} className="px-6 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white transition-colors">返回</button>
        <button onClick={handleLaunch} disabled={loading}
          className={clsx(
            'flex items-center gap-2 px-8 py-2.5 rounded-lg text-sm font-medium transition-colors',
            isDryRun ? 'bg-yellow-600 text-white hover:bg-yellow-700' : 'bg-red-600 text-white hover:bg-red-700'
          )}>
          {loading ? <><Loader2 className="w-4 h-4 animate-spin" />启动中...</> : <><Rocket className="w-4 h-4" />{isDryRun ? '启动模拟运行' : '启动实盘交易'}</>}
        </button>
      </div>

      {/* 实盘二次确认 */}
      {showLiveConfirm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-crypto-card border border-red-500/50 rounded-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-8 h-8 text-red-400" />
              <h3 className="text-lg font-bold text-white">确认启动实盘交易</h3>
            </div>
            <div className="space-y-2 text-sm text-gray-300">
              <p>您即将启动<span className="text-red-400 font-bold">实盘交易</span>，系统将使用您在 <span className="text-white font-medium">{selectedExchange.toUpperCase()}</span> 的真实资金。</p>
              <div className="bg-crypto-bg rounded-lg p-3 space-y-1">
                <div className="flex justify-between"><span className="text-gray-500">策略</span><span className="text-white">{selectedStrategyName}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">交易对</span><span className="text-white">{config.symbol}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">投入资金</span><span className="text-white">${config.initialEquity}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">熔断线</span><span className="text-red-400">{(config.maxTotalLoss * 100).toFixed(0)}% (亏损 ${(config.initialEquity * config.maxTotalLoss).toFixed(0)})</span></div>
              </div>
              <p className="text-red-300/80 text-xs">策略交易存在风险，过去的回测表现不代表未来收益。</p>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowLiveConfirm(false)} className="flex-1 px-4 py-2.5 text-gray-400 border border-gray-700 rounded-lg hover:text-white hover:border-gray-500 text-sm">取消</button>
              <button onClick={handleLaunch} className="flex-1 px-4 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium">
                确认启动实盘
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // ============================================
  // Step 4: 运行监控
  // ============================================
  const equityChartRef = useRef<HTMLDivElement>(null);
  const equityChartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (step !== 'running') return;
    const fetchDashboard = async () => {
      try {
        const [dash, evts] = await Promise.all([liveApi.getDashboard(), liveApi.getEvents(30)]);
        setDashboard(dash);
        setEvents(Array.isArray(evts) ? evts : evts?.events || []);
        setIsRunning(dash?.system?.state === 'running');
        setIsPaused(dash?.system?.state === 'paused');
        try {
          const curve = await liveApi.getEquityCurve();
          if (Array.isArray(curve) && curve.length > 0) setEquityCurve(curve);
        } catch {}
      } catch (err) {
        console.error('刷新仪表盘失败:', err);
      }
    };
    fetchDashboard();
    const timer = setInterval(fetchDashboard, 10000);
    return () => clearInterval(timer);
  }, [step]);

  useEffect(() => {
    if (!equityChartRef.current || equityCurve.length === 0) return;
    if (!equityChartInstance.current) equityChartInstance.current = echarts.init(equityChartRef.current);
    const chart = equityChartInstance.current;
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { top: 20, right: 20, bottom: 30, left: 60 },
      xAxis: {
        type: 'category',
        data: equityCurve.map((p: any) => {
          const d = new Date(p.timestamp || p.time);
          return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
        }),
        axisLine: { lineStyle: { color: '#333' } }, axisLabel: { color: '#888', fontSize: 10 },
      },
      yAxis: { type: 'value', axisLine: { lineStyle: { color: '#333' } }, axisLabel: { color: '#888', fontSize: 10, formatter: '${value}' }, splitLine: { lineStyle: { color: '#222' } } },
      tooltip: { trigger: 'axis', backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#fff', fontSize: 12 } },
      series: [{ type: 'line', data: equityCurve.map((p: any) => p.equity ?? p.value), smooth: true, lineStyle: { color: '#3b82f6', width: 2 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(59,130,246,0.3)' }, { offset: 1, color: 'rgba(59,130,246,0)' }]) }, showSymbol: false }],
    });
  }, [equityCurve]);

  useEffect(() => { return () => { equityChartInstance.current?.dispose(); }; }, []);

  const handleStop = async () => {
    if (!confirm('确定要停止策略运行吗?')) return;
    try { await liveApi.stop(); setIsRunning(false); setIsPaused(false); } catch (err: any) { alert('停止失败: ' + (err?.response?.data?.detail || err.message)); }
  };

  const handlePauseResume = async () => {
    try {
      if (isPaused) { await liveApi.resume(); setIsPaused(false); } else { await liveApi.pause(); setIsPaused(true); }
    } catch (err: any) { alert('操作失败: ' + (err?.response?.data?.detail || err.message)); }
  };

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'signal': return <Zap className="w-3.5 h-3.5 text-blue-400" />;
      case 'order': return <DollarSign className="w-3.5 h-3.5 text-green-400" />;
      case 'close': return <TrendingDown className="w-3.5 h-3.5 text-yellow-400" />;
      case 'error': return <XCircle className="w-3.5 h-3.5 text-red-400" />;
      case 'system': return <Settings2 className="w-3.5 h-3.5 text-gray-400" />;
      default: return <Activity className="w-3.5 h-3.5 text-gray-500" />;
    }
  };

  const renderRunningStep = () => {
    const sys = dashboard?.system;
    const equity = dashboard?.equity;
    const perf = dashboard?.performance;
    const risk = dashboard?.risk;
    const pnl = perf?.totalPnl ?? perf?.totalPnlPct ?? 0;
    const state = sys?.state || 'idle';
    const runningDryRun = sys?.dryRun !== false;

    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={clsx('w-3 h-3 rounded-full animate-pulse',
              state === 'running' ? 'bg-green-400' : state === 'paused' ? 'bg-yellow-400' : state === 'circuit_breaker' ? 'bg-red-400' : 'bg-gray-500'
            )} />
            <h2 className="text-lg font-bold text-white">
              {state === 'running' ? '运行中' : state === 'paused' ? '已暂停' : state === 'circuit_breaker' ? '风控熔断' : state === 'stopped' ? '已停止' : '空闲'}
            </h2>
            <span className={clsx('px-2 py-0.5 text-[10px] font-bold rounded-full',
              runningDryRun ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'
            )}>
              {runningDryRun ? '模拟盘' : '实盘'}
            </span>
            {sys && <span className="text-xs text-gray-500">{sys.strategy} · {sys.symbol} · {sys.timeframe}</span>}
          </div>
          <div className="flex items-center gap-2">
            {(isRunning || isPaused) && (
              <button onClick={handlePauseResume}
                className={clsx('flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm transition-colors',
                  isPaused ? 'bg-green-600/20 text-green-400 border border-green-500/30 hover:bg-green-600/30' : 'bg-yellow-600/20 text-yellow-400 border border-yellow-500/30 hover:bg-yellow-600/30'
                )}>
                {isPaused ? <><Play className="w-4 h-4" />恢复</> : <><Pause className="w-4 h-4" />暂停</>}
              </button>
            )}
            {(isRunning || isPaused) && (
              <button onClick={handleStop} className="flex items-center gap-1.5 px-4 py-2 bg-red-600/20 text-red-400 border border-red-500/30 rounded-lg text-sm hover:bg-red-600/30 transition-colors">
                <Square className="w-4 h-4" />停止
              </button>
            )}
            {!isRunning && !isPaused && (
              <button onClick={() => { setStep('select'); setPreflightResult(null); setPaperResult(null); }}
                className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors">
                <Rocket className="w-4 h-4" />重新配置
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard label="当前权益" value={`$${(equity?.current ?? config.initialEquity).toLocaleString()}`} icon={<DollarSign className="w-4 h-4" />} color="blue" />
          <MetricCard label="总盈亏" value={`${pnl >= 0 ? '+' : ''}${typeof pnl === 'number' ? pnl.toFixed(2) : pnl}%`} icon={pnl >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />} color={pnl >= 0 ? 'up' : 'down'} />
          <MetricCard label="胜率" value={`${(perf?.winRate ?? 0).toFixed(1)}%`} icon={<BarChart3 className="w-4 h-4" />} color="blue" />
          <MetricCard label="总交易" value={String(perf?.totalTrades ?? 0)} icon={<Activity className="w-4 h-4" />} color="blue" />
          <MetricCard label="最大回撤" value={`${(perf?.maxDrawdown ?? risk?.currentDrawdown ?? 0).toFixed(1)}%`} icon={<AlertTriangle className="w-4 h-4" />} color="red" />
          <MetricCard label="运行时间" value={sys?.uptime || '-'} icon={<Clock className="w-4 h-4" />} color="gray" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 bg-crypto-card border border-crypto-border rounded-xl p-4">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-blue-400" />权益曲线</h3>
            {equityCurve.length > 0 ? <div ref={equityChartRef} style={{ width: '100%', height: 280 }} /> : (
              <div className="flex items-center justify-center h-[280px] text-gray-500 text-sm">暂无权益数据，策略运行后将自动显示</div>
            )}
          </div>
          <div className="bg-crypto-card border border-crypto-border rounded-xl p-4">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <List className="w-4 h-4 text-blue-400" />操作记录
              <span className="text-[10px] text-gray-500 ml-auto">{events.length} 条</span>
            </h3>
            <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
              {events.length === 0 && <div className="text-center text-gray-500 text-xs py-8">暂无操作记录</div>}
              {events.map((evt, i) => {
                const details = evt.details || {};
                const msg = evt.message || details.message || details.action || '';
                const reason = evt.detail || details.reason || '';
                const price = details.price;
                return (
                  <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-crypto-bg">
                    {getEventIcon(evt.type)}
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-white truncate">{msg}{price ? ` @ $${Number(price).toLocaleString()}` : ''}</div>
                      {reason && <div className="text-[10px] text-gray-500 truncate mt-0.5">{reason}</div>}
                      <div className="text-[10px] text-gray-600 mt-0.5">{evt.time || ''}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {risk && (
          <div className="bg-crypto-card border border-crypto-border rounded-xl p-4">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-green-400" />风控状态</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-crypto-bg rounded-lg p-3">
                <div className="text-[10px] text-gray-500 mb-1">熔断状态</div>
                <div className={clsx('text-sm font-bold', risk.circuitBreaker ? 'text-red-400' : 'text-green-400')}>{risk.circuitBreaker ? '已触发' : '正常'}</div>
              </div>
              <div className="bg-crypto-bg rounded-lg p-3">
                <div className="text-[10px] text-gray-500 mb-1">当前回撤</div>
                <div className="text-sm font-bold text-white">{(risk.currentDrawdown ?? 0).toFixed(2)}%</div>
              </div>
              <div className="bg-crypto-bg rounded-lg p-3">
                <div className="text-[10px] text-gray-500 mb-1">今日亏损</div>
                <div className="text-sm font-bold text-white">{(risk.dailyLoss ?? 0).toFixed(2)}%</div>
              </div>
              <div className="bg-crypto-bg rounded-lg p-3">
                <div className="text-[10px] text-gray-500 mb-1">Telegram</div>
                <div className={clsx('text-sm font-bold', dashboard?.telegram?.enabled ? 'text-green-400' : 'text-gray-500')}>
                  {dashboard?.telegram?.enabled ? `已启用 (${dashboard.telegram.messagesSent}条)` : '未启用'}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ============================================
  // 渲染主体
  // ============================================
  const canSwitchMode = !isRunning && !isPaused;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* ====== 顶部模式切换 Tab ====== */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center bg-crypto-card border border-crypto-border rounded-xl p-1">
          <button
            onClick={() => handleModeChange('paper')}
            className={clsx(
              'flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all',
              tradeMode === 'paper'
                ? 'bg-yellow-500/20 text-yellow-400 shadow-sm'
                : canSwitchMode
                  ? 'text-gray-500 hover:text-gray-300'
                  : 'text-gray-600 cursor-not-allowed'
            )}
          >
            <FlaskConical className="w-4 h-4" />
            模拟盘
          </button>
          <button
            onClick={() => handleModeChange('live')}
            className={clsx(
              'flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all',
              tradeMode === 'live'
                ? 'bg-red-500/20 text-red-400 shadow-sm'
                : canSwitchMode
                  ? 'text-gray-500 hover:text-gray-300'
                  : 'text-gray-600 cursor-not-allowed'
            )}
          >
            <Radio className="w-4 h-4" />
            实盘
          </button>
        </div>

        {/* 交易所标识 */}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="px-2 py-1 bg-crypto-card border border-crypto-border rounded-lg">
            {selectedExchange.toUpperCase()}
          </span>
        </div>
      </div>

      {/* ====== 步骤导航 ====== */}
      <div className="flex items-center gap-2 mb-8">
        {(['select', 'configure', 'preflight', 'running'] as Step[]).map((s, i) => {
          const labels = ['选择策略', '配置参数', '飞行检查', '运行监控'];
          const icons = [Rocket, Settings2, ShieldCheck, Activity];
          const Icon = icons[i];
          const isActive = s === step;
          const stepOrder = ['select', 'configure', 'preflight', 'running'];
          const isPast = stepOrder.indexOf(s) < stepOrder.indexOf(step);

          return (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && <div className={clsx('w-8 h-px', isPast || isActive ? 'bg-blue-500' : 'bg-gray-700')} />}
              <button
                onClick={() => { if (isPast) setStep(s); }}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  isActive ? 'bg-blue-500/20 text-blue-400' : isPast ? 'text-gray-400 hover:text-white cursor-pointer' : 'text-gray-600 cursor-default'
                )}
              >
                <Icon className="w-3.5 h-3.5" />{labels[i]}
              </button>
            </div>
          );
        })}
      </div>

      {/* ====== 步骤内容 ====== */}
      {step === 'select' && renderSelectStep()}
      {step === 'configure' && renderConfigStep()}
      {step === 'preflight' && renderPreflightStep()}
      {step === 'running' && renderRunningStep()}
    </div>
  );
}

// ============================================
// 指标卡片组件
// ============================================
function MetricCard({ label, value, icon, color }: { label: string; value: string; icon: React.ReactNode; color: 'blue' | 'green' | 'red' | 'yellow' | 'gray' | 'up' | 'down' }) {
  const colorMap: Record<string, string> = { blue: 'text-blue-400', green: 'text-green-400', red: 'text-red-400', yellow: 'text-yellow-400', gray: 'text-gray-400', up: 'text-up', down: 'text-down' };
  return (
    <div className="bg-crypto-card border border-crypto-border rounded-xl p-3">
      <div className="flex items-center gap-1.5 mb-1"><span className={colorMap[color]}>{icon}</span><span className="text-[10px] text-gray-500">{label}</span></div>
      <div className={clsx('text-lg font-bold', colorMap[color])}>{value}</div>
    </div>
  );
}
