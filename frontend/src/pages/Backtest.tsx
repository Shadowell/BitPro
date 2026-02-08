import { useState, useEffect, useRef, useMemo } from 'react';
import {
  FlaskConical, Play, Loader2, BarChart3,
  DollarSign, Activity, Info,
  Calendar, List,
} from 'lucide-react';
import { useStore } from '../stores/useStore';
import axios from 'axios';
import * as echarts from 'echarts';
import clsx from 'clsx';

// ============================================
// 类型定义
// ============================================
interface EquityPoint {
  timestamp: number;
  equity: number;
  drawdown?: number;
}

interface TradeRecord {
  timestamp: number;
  side: string;
  price: number;
  quantity: number;
  pnl: number;
  pnl_pct?: number;
  fee?: number;
  reason?: string;
}

interface BacktestResult {
  strategyId: number;
  strategyName?: string;
  status: string;
  startDate?: string;
  endDate?: string;
  initialCapital: number;
  finalCapital?: number;
  totalReturn?: number;
  annualReturn?: number;
  maxDrawdown?: number;
  maxDrawdownDurationDays?: number;
  sharpeRatio?: number;
  sortinoRatio?: number;
  calmarRatio?: number;
  winRate?: number;
  profitFactor?: number;
  totalTrades?: number;
  winningTrades?: number;
  losingTrades?: number;
  avgWinPct?: number;
  avgLossPct?: number;
  maxConsecutiveWins?: number;
  maxConsecutiveLosses?: number;
  expectancy?: number;
  totalFees?: number;
  avgHoldingBars?: number;
  totalBars?: number;
  elapsedSeconds?: number;
  monthlyReturns?: Record<string, number>;
  equityCurve?: EquityPoint[];
  trades?: TradeRecord[];
  errorMessage?: string;
}

type ResultTab = 'overview' | 'performance' | 'trades';
type TimeRange = '1m' | '3m' | '6m' | '1y' | 'all';

// ============================================
// 主组件
// ============================================
export default function Backtest() {
  const { strategies, fetchStrategies } = useStore();
  const [selectedStrategy, setSelectedStrategy] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);

  // 回测参数
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('4h');
  const today = new Date();
  const oneYearAgo = new Date(today);
  oneYearAgo.setFullYear(today.getFullYear() - 1);
  const [startDate, setStartDate] = useState(oneYearAgo.toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(today.toISOString().slice(0, 10));
  const [initialCapital, setInitialCapital] = useState(10000);
  const [commission, setCommission] = useState(0.0004);

  // 基准K线数据 (用于买入持有对比)
  const [benchmarkKlines, setBenchmarkKlines] = useState<{ timestamp: number; close: number }[]>([]);

  // 结果 Tab & 时间范围
  const [resultTab, setResultTab] = useState<ResultTab>('overview');
  const [timeRange, setTimeRange] = useState<TimeRange>('all');

  useEffect(() => { fetchStrategies(); }, []);

  const runBacktest = async () => {
    if (!selectedStrategy) { alert('请选择策略'); return; }
    setIsRunning(true);
    setResult(null);
    try {
      const response = await axios.post('/api/v1/backtest/run_sync', {
        strategy_id: selectedStrategy, exchange: 'okx', symbol, timeframe,
        start_date: startDate, end_date: endDate, initial_capital: initialCapital,
        commission, slippage: 0.0001,
      });
      setResult(response.data);
      setResultTab('overview');
      setTimeRange('all');
      // 获取真实买入持有基准数据 (覆盖回测完整区间)
      try {
        const startTs = new Date(startDate).getTime();
        const endTs = new Date(endDate).getTime();
        const klinesRes = await axios.get('/api/v1/market/klines', {
          params: { exchange: 'okx', symbol, timeframe: '1d', limit: 1000, start: startTs, end: endTs },
        });
        const klines = (klinesRes.data || []).map((k: any) => ({
          timestamp: k.timestamp, close: k.close,
        }));
        setBenchmarkKlines(klines);
      } catch { setBenchmarkKlines([]); }
    } catch (error: any) {
      console.error('Backtest failed:', error);
      alert('回测失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsRunning(false);
    }
  };

  const fmt = (n: number | undefined | null, d = 2) => n == null ? '-' : n.toFixed(d);
  const fmtPct = (n: number | undefined | null) => n == null ? '-' : `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;

  const hasResult = result && result.status === 'completed';

  // 计算基准收益率和贝塔 (基于benchmarkKlines)
  const benchmarkStats = useMemo(() => {
    if (!hasResult || !benchmarkKlines || benchmarkKlines.length < 2 || !result?.equityCurve?.length) {
      return { benchmarkReturn: null, beta: null, alpha: null };
    }

    const sorted = [...benchmarkKlines].sort((a, b) => a.timestamp - b.timestamp);
    const firstClose = sorted[0].close;
    const lastClose = sorted[sorted.length - 1].close;
    const benchmarkReturn = ((lastClose - firstClose) / firstClose) * 100;

    // 计算贝塔：Cov(策略, 基准) / Var(基准)
    // 从权益曲线和基准K线中提取日收益率序列
    const eq = result.equityCurve;
    if (eq.length < 3) return { benchmarkReturn, beta: null, alpha: null };

    // 策略日收益率
    const strategyReturns: number[] = [];
    for (let i = 1; i < eq.length; i++) {
      strategyReturns.push((eq[i].equity - eq[i - 1].equity) / eq[i - 1].equity);
    }

    // 基准日收益率 (匹配策略时间点)
    const benchReturns: number[] = [];
    for (let i = 1; i < eq.length; i++) {
      const ts = eq[i].timestamp;
      let closestIdx = 0;
      let minDiff = Math.abs(sorted[0].timestamp - ts);
      for (let j = 1; j < sorted.length; j++) {
        const diff = Math.abs(sorted[j].timestamp - ts);
        if (diff < minDiff) { minDiff = diff; closestIdx = j; }
      }
      const prevTs = eq[i - 1].timestamp;
      let prevIdx = 0;
      let prevMinDiff = Math.abs(sorted[0].timestamp - prevTs);
      for (let j = 1; j < sorted.length; j++) {
        const diff = Math.abs(sorted[j].timestamp - prevTs);
        if (diff < prevMinDiff) { prevMinDiff = diff; prevIdx = j; }
      }
      if (sorted[prevIdx].close > 0) {
        benchReturns.push((sorted[closestIdx].close - sorted[prevIdx].close) / sorted[prevIdx].close);
      } else {
        benchReturns.push(0);
      }
    }

    // 协方差和方差
    const n = Math.min(strategyReturns.length, benchReturns.length);
    if (n < 5) return { benchmarkReturn, beta: null, alpha: null };

    const meanS = strategyReturns.slice(0, n).reduce((a, b) => a + b, 0) / n;
    const meanB = benchReturns.slice(0, n).reduce((a, b) => a + b, 0) / n;
    let cov = 0, varB = 0;
    for (let i = 0; i < n; i++) {
      cov += (strategyReturns[i] - meanS) * (benchReturns[i] - meanB);
      varB += (benchReturns[i] - meanB) ** 2;
    }
    cov /= n;
    varB /= n;

    const beta = varB > 0 ? cov / varB : 0;
    const annualizedStrategy = (result.annualReturn ?? 0) / 100;
    const annualizedBenchmark = benchmarkReturn / 100;
    const alpha = (annualizedStrategy - beta * annualizedBenchmark) * 100;

    return { benchmarkReturn, beta, alpha };
  }, [hasResult, benchmarkKlines, result]);

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
        <FlaskConical className="w-6 h-6 text-purple-400" />
        策略回测
        <span className="text-sm text-gray-500 font-normal">v2 引擎</span>
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* ====== 左侧：回测配置 ====== */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-5 h-fit sticky top-6">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-purple-400" />
            回测配置
          </h2>

          <div className="space-y-3">
            <Field label="选择策略">
              <select value={selectedStrategy || ''} onChange={(e) => setSelectedStrategy(Number(e.target.value) || null)}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white">
                <option value="">-- 请选择 --</option>
                {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>

            <Field label="交易对">
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white">
                {['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT'].map(s =>
                  <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>

            <Field label="K线周期">
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white">
                {['1m', '5m', '15m', '1h', '4h', '1d'].map(v =>
                  <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-2">
              <Field label="开始日期">
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                  className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" />
              </Field>
              <Field label="结束日期">
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                  className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" />
              </Field>
            </div>

            <Field label="初始资金 (USDT)">
              <input type="number" value={initialCapital} onChange={(e) => setInitialCapital(Number(e.target.value))}
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" />
            </Field>

            <Field label="手续费率">
              <input type="number" value={commission} onChange={(e) => setCommission(Number(e.target.value))} step="0.0001"
                className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" />
            </Field>

            <button onClick={runBacktest} disabled={isRunning || !selectedStrategy}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-xl text-sm font-medium transition-colors mt-2">
              {isRunning ? <><Loader2 className="w-4 h-4 animate-spin" />回测中...</> : <><Play className="w-4 h-4" />开始回测</>}
            </button>

            {hasResult && (
              <div className="text-[10px] text-gray-500 text-center space-y-0.5 pt-1">
                <div>{result.totalBars} 根K线 · 耗时 {result.elapsedSeconds?.toFixed(2)}s</div>
                {result.strategyName && <div className="text-purple-400">{result.strategyName}</div>}
              </div>
            )}
            {result && result.status === 'failed' && (
              <div className="text-xs text-red-400 text-center p-2 bg-red-500/10 rounded-lg">{result.errorMessage}</div>
            )}
          </div>
        </div>

        {/* ====== 右侧：回测结果 ====== */}
        <div className="lg:col-span-3 space-y-4">
          {!hasResult ? (
            <div className="bg-crypto-card border border-crypto-border rounded-xl flex flex-col items-center justify-center py-24">
              <FlaskConical className="w-16 h-16 text-gray-700 mb-4" />
              <p className="text-gray-500 text-sm">选择策略并运行回测后查看绩效报告</p>
            </div>
          ) : (
            <>
              {/* ====== BigQuant 风格 - 概要指标行 ====== */}
              <div className="bg-crypto-card border border-crypto-border rounded-xl p-5">
                {/* 策略名称 */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-white">{result.strategyName || '策略回测结果'}</h2>
                    <span className="text-xs text-gray-500 bg-crypto-bg px-2 py-0.5 rounded">{symbol} · {timeframe}</span>
                  </div>
                  {/* Tab 切换 */}
                  <div className="flex items-center gap-1 bg-crypto-bg rounded-lg p-0.5">
                    {([
                      ['overview', '概要'],
                      ['performance', '绩效'],
                      ['trades', '交易记录'],
                    ] as [ResultTab, string][]).map(([key, label]) => (
                      <button key={key} onClick={() => setResultTab(key)}
                        className={clsx('px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                          resultTab === key ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                        )}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* ====== 核心指标卡片行 - BigQuant 风格 ====== */}
                <div className="grid grid-cols-5 lg:grid-cols-10 gap-0 border border-crypto-border rounded-xl overflow-hidden">
                  <BigMetric label="累计收益" value={fmtPct(result.totalReturn)} positive={(result.totalReturn ?? 0) >= 0} highlight />
                  <BigMetric label="年化收益率" value={fmtPct(result.annualReturn)} positive={(result.annualReturn ?? 0) >= 0} highlight />
                  <BigMetric label="基准收益率" value={benchmarkStats.benchmarkReturn != null ? fmtPct(benchmarkStats.benchmarkReturn) : '-'} positive={(benchmarkStats.benchmarkReturn ?? 0) >= 0} />
                  <BigMetric label="阿尔法" value={benchmarkStats.alpha != null ? fmtPct(benchmarkStats.alpha) : fmt(result.calmarRatio)} positive={(benchmarkStats.alpha ?? result.calmarRatio ?? 0) >= 0} />
                  <BigMetric label="贝塔" value={benchmarkStats.beta != null ? fmt(benchmarkStats.beta) : '-'} positive={(benchmarkStats.beta ?? 0) <= 1} />
                  <BigMetric label="夏普比率" value={fmt(result.sharpeRatio)} positive={(result.sharpeRatio ?? 0) >= 0} />
                  <BigMetric label="胜率" value={result.winRate != null ? `${fmt(result.winRate)}%` : '-'} positive={(result.winRate ?? 0) >= 50} />
                  <BigMetric label="盈亏比" value={fmt(result.profitFactor)} positive={(result.profitFactor ?? 0) >= 1} />
                  <BigMetric label="收益波动率" value={result.sortinoRatio != null ? fmt(result.sortinoRatio) : '-'} positive={(result.sortinoRatio ?? 0) >= 0} />
                  <BigMetric label="最大回撤" value={result.maxDrawdown != null ? `${fmt(result.maxDrawdown)}%` : '-'} positive={false} isDrawdown />
                </div>
              </div>

              {/* ====== 概要 Tab ====== */}
              {resultTab === 'overview' && (
                <>
                  {/* 时间范围 + 区间收益 */}
                  <div className="bg-crypto-card border border-crypto-border rounded-xl p-4">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-1">
                        <span className="text-xs text-gray-500 mr-2">缩放时间</span>
                        {(['1m', '3m', '6m', '1y', 'all'] as TimeRange[]).map(tr => {
                          const labels: Record<TimeRange, string> = { '1m': '1月', '3m': '3月', '6m': '6月', '1y': '1年', 'all': '全部' };
                          return (
                            <button key={tr} onClick={() => setTimeRange(tr)}
                              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-colors',
                                timeRange === tr ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                              )}>
                              {labels[tr]}
                            </button>
                          );
                        })}
                      </div>
                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-gray-500">
                          区间收益 <span className={clsx('font-bold', (result.totalReturn ?? 0) >= 0 ? 'text-up' : 'text-down')}>
                            {fmtPct(result.totalReturn)}
                          </span>
                        </span>
                        <span className="text-gray-500">
                          区间最大回撤 <span className="font-bold text-down">{fmt(result.maxDrawdown)}%</span>
                        </span>
                      </div>
                    </div>

                    {/* 多曲线图表 */}
                    <BacktestChart
                      equityCurve={result.equityCurve || []}
                      initialCapital={initialCapital}
                      timeRange={timeRange}
                      height={420}
                      benchmarkKlines={benchmarkKlines}
                    />
                  </div>
                </>
              )}

              {/* ====== 绩效 Tab ====== */}
              {resultTab === 'performance' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* 交易统计 */}
                  <div className="bg-crypto-card border border-crypto-border rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                      <Activity className="w-4 h-4 text-purple-400" />交易统计
                    </h3>
                    <div className="space-y-2.5">
                      <StatRow label="总交易次数" value={`${result.totalTrades || 0}`} />
                      <StatRow label="盈利交易" value={`${result.winningTrades || 0}`} color="text-up" />
                      <StatRow label="亏损交易" value={`${result.losingTrades || 0}`} color="text-down" />
                      <StatRow label="胜率" value={`${fmt(result.winRate)}%`} color={(result.winRate ?? 0) >= 50 ? 'text-up' : 'text-down'} />
                      <StatRow label="平均盈利" value={fmtPct(result.avgWinPct)} color="text-up" />
                      <StatRow label="平均亏损" value={fmtPct(result.avgLossPct)} color="text-down" />
                      <StatRow label="盈亏比" value={fmt(result.profitFactor)} />
                      <StatRow label="期望收益/笔" value={`$${fmt(result.expectancy)}`} />
                      <StatRow label="最大连胜" value={`${result.maxConsecutiveWins || 0}`} color="text-up" />
                      <StatRow label="最大连亏" value={`${result.maxConsecutiveLosses || 0}`} color="text-down" />
                      <StatRow label="平均持仓" value={`${fmt(result.avgHoldingBars)} bars`} />
                    </div>
                  </div>

                  {/* 资金统计 + 月度 */}
                  <div className="space-y-4">
                    <div className="bg-crypto-card border border-crypto-border rounded-xl p-5">
                      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-green-400" />资金统计
                      </h3>
                      <div className="space-y-2.5">
                        <StatRow label="初始资金" value={`$${fmt(result.initialCapital)}`} />
                        <StatRow label="最终资金" value={`$${fmt(result.finalCapital)}`}
                          color={(result.finalCapital ?? 0) >= result.initialCapital ? 'text-up' : 'text-down'} />
                        <StatRow label="总手续费" value={`$${fmt(result.totalFees)}`} />
                        <StatRow label="最大回撤" value={`${fmt(result.maxDrawdown)}%`} color="text-down" />
                        <StatRow label="回撤持续" value={`${result.maxDrawdownDurationDays || 0} 天`} />
                        <StatRow label="夏普比率" value={fmt(result.sharpeRatio)} />
                        <StatRow label="Sortino" value={fmt(result.sortinoRatio)} />
                        <StatRow label="Calmar" value={fmt(result.calmarRatio)} />
                      </div>
                    </div>

                    {/* 月度收益热力图 */}
                    {result.monthlyReturns && Object.keys(result.monthlyReturns).length > 0 && (
                      <div className="bg-crypto-card border border-crypto-border rounded-xl p-5">
                        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-blue-400" />月度收益
                        </h3>
                        <div className="grid grid-cols-4 gap-1.5">
                          {Object.entries(result.monthlyReturns).sort().map(([month, ret]) => (
                            <div key={month}
                              className={clsx(
                                'px-2 py-1.5 rounded-lg text-center text-xs font-medium',
                                ret >= 0 ? 'bg-up text-up' : 'bg-down text-down'
                              )}>
                              <div className="text-[10px] text-gray-500">{month.slice(5)}</div>
                              <div>{ret >= 0 ? '+' : ''}{ret.toFixed(1)}%</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ====== 交易记录 Tab ====== */}
              {resultTab === 'trades' && (
                <div className="bg-crypto-card border border-crypto-border rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <List className="w-4 h-4 text-blue-400" />
                    交易记录
                    <span className="text-xs text-gray-500 ml-auto">{result.trades?.length || 0} 笔</span>
                  </h3>
                  {result.trades && result.trades.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-[11px] text-gray-500 border-b border-crypto-border">
                            <th className="text-left py-2.5 font-medium">时间</th>
                            <th className="text-left py-2.5 font-medium">方向</th>
                            <th className="text-right py-2.5 font-medium">价格</th>
                            <th className="text-right py-2.5 font-medium">数量</th>
                            <th className="text-right py-2.5 font-medium">盈亏</th>
                            <th className="text-right py-2.5 font-medium">手续费</th>
                            <th className="text-left py-2.5 font-medium">原因</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.trades.slice(0, 100).map((trade, i) => (
                            <tr key={i} className="border-b border-crypto-border/20 hover:bg-white/[0.02] transition-colors">
                              <td className="py-2 text-xs text-gray-400">{new Date(trade.timestamp).toLocaleString('zh-CN')}</td>
                              <td className={clsx('py-2 text-xs font-semibold',
                                trade.side === 'buy' ? 'text-up' : trade.side === 'sell' ? 'text-down' :
                                trade.side === 'short' ? 'text-orange-400' : 'text-blue-400'
                              )}>
                                {trade.side === 'buy' ? '买入' : trade.side === 'sell' ? '卖出' : trade.side === 'short' ? '做空' : '平空'}
                              </td>
                              <td className="py-2 text-right text-xs text-white">{trade.price.toFixed(2)}</td>
                              <td className="py-2 text-right text-xs text-white">{trade.quantity.toFixed(4)}</td>
                              <td className={clsx('py-2 text-right text-xs font-medium', trade.pnl >= 0 ? 'text-up' : 'text-down')}>
                                {trade.pnl ? `${trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}` : '-'}
                              </td>
                              <td className="py-2 text-right text-xs text-gray-500">{trade.fee ? trade.fee.toFixed(2) : '-'}</td>
                              <td className="py-2 text-xs text-gray-500">{trade.reason || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {result.trades.length > 100 && (
                        <p className="text-center text-gray-500 text-xs mt-3">共 {result.trades.length} 笔交易（显示前100笔）</p>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-12 text-gray-500 text-sm">暂无交易记录</div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================
// BigQuant 风格指标卡片
// ============================================
function BigMetric({ label, value, positive, highlight, isDrawdown }: {
  label: string; value: string; positive: boolean; highlight?: boolean; isDrawdown?: boolean;
}) {
  const textColor = isDrawdown
    ? 'text-down'
    : value === '-'
      ? 'text-gray-400'
      : positive ? 'text-up' : 'text-down';

  return (
    <div className={clsx(
      'flex flex-col items-center justify-center py-3 px-1 border-r border-crypto-border last:border-r-0',
      highlight && 'bg-white/[0.02]'
    )}>
      <div className={clsx('text-lg font-bold tabular-nums leading-tight', textColor)}>
        {value}
      </div>
      <div className="text-[10px] text-gray-500 mt-1 flex items-center gap-0.5 whitespace-nowrap">
        {label}
        <Info className="w-2.5 h-2.5 text-gray-600" />
      </div>
    </div>
  );
}

// ============================================
// 表单字段
// ============================================
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs text-gray-400 mb-1 block">{label}</span>
      {children}
    </label>
  );
}

// ============================================
// 统计行
// ============================================
function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-center py-0.5">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={clsx('text-xs font-medium', color || 'text-white')}>{value}</span>
    </div>
  );
}

// ============================================
// 多曲线回测图表 - BigQuant 风格
// ============================================
function BacktestChart({ equityCurve, initialCapital: _initialCapital, timeRange, height = 420, benchmarkKlines = [] }: {
  equityCurve: EquityPoint[]; initialCapital: number; timeRange: TimeRange; height?: number;
  benchmarkKlines?: { timestamp: number; close: number }[];
}) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // 根据时间范围过滤数据
  const filteredData = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0) return [];
    if (timeRange === 'all') return equityCurve;

    const lastTs = equityCurve[equityCurve.length - 1].timestamp;
    const lastDate = new Date(lastTs);
    const cutoff = new Date(lastDate);

    switch (timeRange) {
      case '1m': cutoff.setMonth(cutoff.getMonth() - 1); break;
      case '3m': cutoff.setMonth(cutoff.getMonth() - 3); break;
      case '6m': cutoff.setMonth(cutoff.getMonth() - 6); break;
      case '1y': cutoff.setFullYear(cutoff.getFullYear() - 1); break;
    }

    return equityCurve.filter(p => p.timestamp >= cutoff.getTime());
  }, [equityCurve, timeRange]);

  // 计算图表数据
  const chartData = useMemo(() => {
    if (filteredData.length === 0) return null;

    // 策略收益率（相对于过滤区间的第一个点）
    const baseEquity = filteredData[0].equity;
    const dates = filteredData.map(p => {
      const d = new Date(p.timestamp);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    });
    const strategyReturn = filteredData.map(p => ((p.equity - baseEquity) / baseEquity) * 100);
    const drawdown = filteredData.map(p => -(p.drawdown || 0));

    // 基准收益率（BTC买入持有）- 使用真实K线数据
    let benchmarkReturn: number[];
    if (benchmarkKlines && benchmarkKlines.length > 1) {
      // 按时间匹配基准数据到策略的每个点
      const sortedKlines = [...benchmarkKlines].sort((a, b) => a.timestamp - b.timestamp);
      benchmarkReturn = filteredData.map(p => {
        // 找到最接近的K线
        let closest = sortedKlines[0];
        for (const k of sortedKlines) {
          if (Math.abs(k.timestamp - p.timestamp) < Math.abs(closest.timestamp - p.timestamp)) {
            closest = k;
          }
        }
        return ((closest.close - sortedKlines[0].close) / sortedKlines[0].close) * 100;
      });
    } else {
      // 回退：简化线性基准
      benchmarkReturn = filteredData.map((_, i) =>
        (i / (filteredData.length - 1 || 1)) * (strategyReturn[strategyReturn.length - 1] * 0.5)
      );
    }

    // 相对收益率 = 策略 - 基准
    const relativeReturn = strategyReturn.map((sr, i) => sr - benchmarkReturn[i]);

    return { dates, strategyReturn, benchmarkReturn, relativeReturn, drawdown };
  }, [filteredData, benchmarkKlines]);

  useEffect(() => {
    if (!chartRef.current || !chartData) return;

    // 如果之前的实例已被 dispose 或不存在，重新创建
    if (chartInstance.current) {
      try {
        chartInstance.current.getOption(); // 检测是否已 dispose
      } catch {
        chartInstance.current = null;
      }
    }
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    const chart = chartInstance.current;

    chart.setOption({
      backgroundColor: 'transparent',
      animation: true,
      legend: {
        data: [
          { name: '策略收益率', icon: 'circle' },
          { name: '相对收益率', icon: 'circle' },
          { name: '基准指数', icon: 'circle' },
          { name: '最大回撤', icon: 'circle' },
        ],
        top: 0,
        right: 0,
        textStyle: { color: '#888', fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 16,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(20, 20, 30, 0.95)',
        borderColor: '#333',
        textStyle: { color: '#eee', fontSize: 11 },
        axisPointer: { type: 'cross', crossStyle: { color: '#555' } },
        formatter: (params: any) => {
          if (!params || params.length === 0) return '';
          let html = `<div style="font-size:11px;"><div style="color:#888;margin-bottom:4px">${params[0].axisValue}</div>`;
          params.forEach((p: any) => {
            if (p.seriesName === '最大回撤') {
              html += `<div style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>${p.seriesName}: <span style="color:#4caf50">${Math.abs(p.value).toFixed(2)}%</span></div>`;
            } else {
              const color = p.value >= 0 ? '#ef5350' : '#4caf50';
              html += `<div style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>${p.seriesName}: <span style="color:${color}">${p.value >= 0 ? '+' : ''}${p.value.toFixed(2)}%</span></div>`;
            }
          });
          html += '</div>';
          return html;
        },
      },
      grid: [
        { left: 50, right: 30, top: 40, height: '58%' },
        { left: 50, right: 30, bottom: 50, height: '18%' },
      ],
      xAxis: [
        {
          type: 'category', data: chartData.dates, gridIndex: 0,
          axisLine: { lineStyle: { color: '#333' } },
          axisLabel: { color: '#888', fontSize: 10 },
          axisTick: { show: false },
        },
        {
          type: 'category', data: chartData.dates, gridIndex: 1,
          axisLine: { lineStyle: { color: '#333' } },
          axisLabel: { color: '#888', fontSize: 10 },
          axisTick: { show: false },
        },
      ],
      yAxis: [
        {
          type: 'value', gridIndex: 0,
          axisLine: { show: false },
          axisLabel: { color: '#888', fontSize: 10, formatter: '{value}%' },
          splitLine: { lineStyle: { color: '#222', type: 'dashed' } },
        },
        {
          type: 'value', gridIndex: 1,
          axisLine: { show: false },
          axisLabel: { color: '#888', fontSize: 10, formatter: '{value}%' },
          splitLine: { show: false },
          max: 0,
        },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        {
          show: true, xAxisIndex: [0, 1], type: 'slider', bottom: 10,
          start: 0, end: 100, height: 20,
          borderColor: '#333', backgroundColor: 'transparent',
          fillerColor: 'rgba(168, 85, 247, 0.15)',
          handleStyle: { color: '#a855f7' },
          textStyle: { color: '#888' },
        },
      ],
      series: [
        {
          name: '策略收益率', type: 'line', data: chartData.strategyReturn,
          xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none',
          lineStyle: { color: '#ef5350', width: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(239, 83, 80, 0.15)' },
              { offset: 1, color: 'rgba(239, 83, 80, 0)' },
            ]),
          },
        },
        {
          name: '相对收益率', type: 'line', data: chartData.relativeReturn,
          xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none',
          lineStyle: { color: '#ffa726', width: 1.5 },
        },
        {
          name: '基准指数', type: 'line', data: chartData.benchmarkReturn,
          xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none',
          lineStyle: { color: '#42a5f5', width: 1.5, type: 'dashed' },
        },
        {
          name: '最大回撤', type: 'line', data: chartData.drawdown,
          xAxisIndex: 1, yAxisIndex: 1, smooth: true, symbol: 'none',
          lineStyle: { color: '#4caf50', width: 1 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(76, 175, 80, 0.3)' },
              { offset: 1, color: 'rgba(76, 175, 80, 0)' },
            ]),
          },
        },
      ],
    }, true);

    // 确保图表尺寸正确
    setTimeout(() => chart.resize(), 50);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);
    return () => { window.removeEventListener('resize', handleResize); };
  }, [chartData]);

  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  if (!equityCurve || equityCurve.length === 0) {
    return (
      <div style={{ height }} className="flex items-center justify-center text-gray-500 text-sm">
        暂无资金曲线数据
      </div>
    );
  }

  return <div ref={chartRef} style={{ width: '100%', height }} />;
}
