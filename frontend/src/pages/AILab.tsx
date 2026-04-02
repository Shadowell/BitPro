import { useState, useEffect, useRef } from 'react';
import {
  Cpu, Play, Square, AlertCircle, ChevronRight, Download,
  RefreshCw, Sparkles, Target, FileText, GitBranch, RotateCcw,
  ArrowRight, Zap,
} from 'lucide-react';
import axios from 'axios';

const api = axios.create({ baseURL: '/api/v2', timeout: 120000 });
api.interceptors.response.use((r) => r.data, (e) => Promise.reject(e));

/* ---------- types ---------- */

interface GoalCriteria {
  min_sharpe_ratio: number;
  max_drawdown_pct: number;
  min_win_rate_pct: number;
  min_total_return_pct: number;
  min_total_trades: number;
  min_profit_factor: number;
}

interface EvalScores {
  risk_control: number;
  profitability: number;
  robustness: number;
  strategy_logic: number;
  originality: number;
  total_score: number;
}

interface SprintContract {
  strategy_direction: string;
  key_indicators: string[];
  entry_logic_desc: string;
  exit_logic_desc: string;
  risk_management_desc: string;
  acceptance_criteria: string[];
  action: string;
}

interface Iteration {
  iteration: number;
  strategy_name: string;
  strategy_code: string;
  setup_code: string;
  reasoning: string;
  backtest_metrics: Record<string, any>;
  eval_scores: EvalScores | null;
  analysis: string;
  suggestions: string[];
  score: number;
  meets_goal: boolean;
  error: string;
  created_at: string;
  contract: SprintContract | null;
  action: string;
}

interface StrategySpec {
  market_analysis: string;
  strategy_candidates: { name: string; description: string; pros: string; cons: string }[];
  recommended_approach: string;
  risk_considerations: string;
  iteration_plan: string;
}

interface TaskInfo {
  task_id: string;
  status: string;
  symbol: string;
  timeframe: string;
  current_iteration: number;
  max_iterations: number;
  best_iteration: number | null;
  best_score: number | null;
  best_metrics: Record<string, any> | null;
  best_eval_scores: EvalScores | null;
  goal: GoalCriteria;
  strategy_spec: StrategySpec | null;
  iterations_count: number;
  created_at: string;
  updated_at: string;
}

/* ---------- constants ---------- */

const DEFAULT_GOAL: GoalCriteria = {
  min_sharpe_ratio: 1.0,
  max_drawdown_pct: 20.0,
  min_win_rate_pct: 45.0,
  min_total_return_pct: 10.0,
  min_total_trades: 10,
  min_profit_factor: 1.2,
};

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  new: { label: '全新', color: 'text-blue-400' },
  refine: { label: '优化', color: 'text-green-400' },
  pivot: { label: '转向', color: 'text-orange-400' },
};

/* ---------- Radar chart (pure CSS/SVG) ---------- */

function RadarChart({ scores }: { scores: EvalScores }) {
  const dims = [
    { key: 'risk_control', label: '风控' },
    { key: 'profitability', label: '盈利' },
    { key: 'robustness', label: '稳健' },
    { key: 'strategy_logic', label: '逻辑' },
    { key: 'originality', label: '原创' },
  ] as const;
  const n = dims.length;
  const cx = 80, cy = 80, R = 60;

  const angleOf = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const ptAt = (i: number, r: number) => {
    const a = angleOf(i);
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  const gridLevels = [0.25, 0.5, 0.75, 1.0];
  const values = dims.map((d) => (scores[d.key as keyof EvalScores] as number) / 100);
  const dataPoints = values.map((v, i) => ptAt(i, R * v));
  const dataPath = dataPoints.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ') + 'Z';

  return (
    <svg viewBox="0 0 160 160" className="w-full max-w-[200px] mx-auto">
      {gridLevels.map((lv) => {
        const pts = dims.map((_, i) => ptAt(i, R * lv));
        const d = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ') + 'Z';
        return <path key={lv} d={d} fill="none" stroke="#374151" strokeWidth={0.5} />;
      })}
      {dims.map((_, i) => {
        const [ex, ey] = ptAt(i, R);
        return <line key={i} x1={cx} y1={cy} x2={ex} y2={ey} stroke="#374151" strokeWidth={0.5} />;
      })}
      <path d={dataPath} fill="rgba(59,130,246,0.2)" stroke="#3b82f6" strokeWidth={1.5} />
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={2.5} fill="#3b82f6" />
      ))}
      {dims.map((d, i) => {
        const [lx, ly] = ptAt(i, R + 16);
        return (
          <text key={d.key} x={lx} y={ly} textAnchor="middle" dominantBaseline="central"
            className="fill-gray-400 text-[9px]">
            {d.label} {Math.round(scores[d.key as keyof EvalScores] as number)}
          </text>
        );
      })}
    </svg>
  );
}

/* ---------- Main component ---------- */

export default function AILab() {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('4h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [maxIter, setMaxIter] = useState(10);
  const [userPrompt, setUserPrompt] = useState('');
  const [goal, setGoal] = useState<GoalCriteria>({ ...DEFAULT_GOAL });

  const [task, setTask] = useState<TaskInfo | null>(null);
  const [iterations, setIterations] = useState<Iteration[]>([]);
  const [selectedIter, setSelectedIter] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showSpec, setShowSpec] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isRunning = task?.status === 'running' || task?.status === 'pending';

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const startPolling = (taskId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const [t, iters] = await Promise.all([
          api.get(`/agent/tasks/${taskId}`),
          api.get(`/agent/tasks/${taskId}/iterations`),
        ]);
        setTask(t as any);
        setIterations(iters as any);
        if ((t as any).status !== 'running' && (t as any).status !== 'pending') {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* ignore */ }
    }, 3000);
  };

  const handleStart = async () => {
    setError('');
    setLoading(true);
    try {
      const res: any = await api.post('/agent/tasks', {
        symbol, timeframe,
        backtest_start: startDate,
        backtest_end: endDate,
        max_iterations: maxIter,
        user_prompt: userPrompt,
        goal,
      });
      const taskId = res.task_id;
      const t: any = await api.get(`/agent/tasks/${taskId}`);
      setTask(t);
      setIterations([]);
      setSelectedIter(null);
      setShowSpec(false);
      startPolling(taskId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || '启动失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    if (!task) return;
    try {
      await api.post(`/agent/tasks/${task.task_id}/stop`);
      setTask({ ...task, status: 'stopped' });
      if (pollRef.current) clearInterval(pollRef.current);
    } catch { /* ignore */ }
  };

  const handleAccept = async () => {
    if (!task) return;
    try {
      const res: any = await api.post(`/agent/tasks/${task.task_id}/accept`);
      alert(`策略已保存! ID: ${res.strategy_id}, 名称: ${res.strategy_name}`);
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败');
    }
  };

  const sel = selectedIter !== null ? iterations.find(i => i.iteration === selectedIter) : null;

  return (
    <div className="p-4 h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Sparkles className="text-yellow-400" size={28} />
          AI 策略研发 <span className="text-xs font-normal text-gray-500 ml-2">v2 Multi-Agent</span>
        </h1>
        <div className="flex items-center gap-3">
          {task?.strategy_spec && (
            <button onClick={() => setShowSpec(!showSpec)}
              className="text-xs px-3 py-1 rounded border border-crypto-border hover:border-blue-500 text-gray-400 hover:text-blue-400 flex items-center gap-1">
              <FileText size={12} /> {showSpec ? '隐藏规格书' : '查看规格书'}
            </button>
          )}
          {task && (
            <span className={`px-3 py-1 rounded-full text-xs font-bold ${
              task.status === 'running' ? 'bg-blue-500/20 text-blue-400 animate-pulse' :
              task.status === 'completed' ? 'bg-green-500/20 text-green-400' :
              task.status === 'failed' ? 'bg-red-500/20 text-red-400' :
              task.status === 'stopped' ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-gray-500/20 text-gray-400'
            }`}>
              {task.status === 'running' ? `运行中 (${task.current_iteration + 1}/${task.max_iterations})` :
               task.status === 'completed' ? '已完成' :
               task.status === 'failed' ? '失败' :
               task.status === 'stopped' ? '已停止' : task.status}
            </span>
          )}
        </div>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-2 rounded mb-4">{error}</div>}

      {/* Strategy Spec Panel */}
      {showSpec && task?.strategy_spec && (
        <div className="bg-crypto-card border border-blue-500/30 rounded-lg p-4 mb-4">
          <h3 className="text-sm font-semibold text-blue-400 mb-3 flex items-center gap-1">
            <FileText size={14} /> Planner 策略规格书
          </h3>
          <div className="grid grid-cols-2 gap-4 text-xs text-gray-400">
            <div>
              <h4 className="text-gray-300 font-medium mb-1">市场分析</h4>
              <p className="whitespace-pre-wrap leading-relaxed">{task.strategy_spec.market_analysis}</p>
            </div>
            <div>
              <h4 className="text-gray-300 font-medium mb-1">推荐方向</h4>
              <p className="whitespace-pre-wrap leading-relaxed">{task.strategy_spec.recommended_approach}</p>
            </div>
            {task.strategy_spec.strategy_candidates?.length > 0 && (
              <div className="col-span-2">
                <h4 className="text-gray-300 font-medium mb-2">候选策略方向</h4>
                <div className="grid grid-cols-3 gap-2">
                  {task.strategy_spec.strategy_candidates.map((c, i) => (
                    <div key={i} className="bg-crypto-bg rounded p-2 border border-crypto-border">
                      <div className="font-medium text-gray-300 mb-1">{c.name}</div>
                      <p className="text-[10px] leading-relaxed">{c.description}</p>
                      <div className="flex gap-2 mt-1">
                        <span className="text-green-400 text-[10px]">+{c.pros}</span>
                        <span className="text-red-400 text-[10px]">-{c.cons}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div>
              <h4 className="text-gray-300 font-medium mb-1">风险提示</h4>
              <p className="whitespace-pre-wrap leading-relaxed">{task.strategy_spec.risk_considerations}</p>
            </div>
            <div>
              <h4 className="text-gray-300 font-medium mb-1">迭代计划</h4>
              <p className="whitespace-pre-wrap leading-relaxed">{task.strategy_spec.iteration_plan}</p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        {/* Left: Config Panel */}
        <div className="col-span-3 space-y-3">
          <div className="bg-crypto-card border border-crypto-border rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-1"><Target size={14} /> 任务配置</h3>

            <div>
              <label className="text-xs text-gray-400">交易对</label>
              <select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={isRunning}
                className="w-full bg-crypto-bg border border-crypto-border rounded px-2 py-1.5 text-sm mt-1">
                {['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT','DOGE/USDT'].map(s =>
                  <option key={s} value={s}>{s}</option>
                )}
              </select>
            </div>

            <div>
              <label className="text-xs text-gray-400">K线周期</label>
              <select value={timeframe} onChange={e => setTimeframe(e.target.value)} disabled={isRunning}
                className="w-full bg-crypto-bg border border-crypto-border rounded px-2 py-1.5 text-sm mt-1">
                {['15m','1h','4h','1d'].map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-400">开始日期</label>
                <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} disabled={isRunning}
                  className="w-full bg-crypto-bg border border-crypto-border rounded px-2 py-1.5 text-sm mt-1" />
              </div>
              <div>
                <label className="text-xs text-gray-400">结束日期</label>
                <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} disabled={isRunning}
                  className="w-full bg-crypto-bg border border-crypto-border rounded px-2 py-1.5 text-sm mt-1" />
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-400">最大迭代轮数</label>
              <input type="number" min={1} max={30} value={maxIter} onChange={e => setMaxIter(+e.target.value)} disabled={isRunning}
                className="w-full bg-crypto-bg border border-crypto-border rounded px-2 py-1.5 text-sm mt-1" />
            </div>

            <div>
              <label className="text-xs text-gray-400">策略偏好描述 (可选)</label>
              <textarea value={userPrompt} onChange={e => setUserPrompt(e.target.value)} disabled={isRunning} rows={2}
                placeholder="例如: 偏好动量突破类策略，关注成交量确认..."
                className="w-full bg-crypto-bg border border-crypto-border rounded px-2 py-1.5 text-sm mt-1 resize-none" />
            </div>
          </div>

          <div className="bg-crypto-card border border-crypto-border rounded-lg p-4 space-y-2">
            <h3 className="text-sm font-semibold text-gray-300">绩效目标</h3>
            {([
              ['min_sharpe_ratio', '夏普比率 ≥', 0.1],
              ['max_drawdown_pct', '最大回撤 ≤ %', 1],
              ['min_win_rate_pct', '胜率 ≥ %', 1],
              ['min_total_return_pct', '总收益率 ≥ %', 1],
              ['min_profit_factor', '盈亏比 ≥', 0.1],
              ['min_total_trades', '交易次数 ≥', 1],
            ] as [keyof GoalCriteria, string, number][]).map(([key, label, step]) => (
              <div key={key} className="flex items-center justify-between">
                <label className="text-xs text-gray-400 w-28">{label}</label>
                <input type="number" step={step} value={goal[key]} disabled={isRunning}
                  onChange={e => setGoal({ ...goal, [key]: +e.target.value })}
                  className="w-20 bg-crypto-bg border border-crypto-border rounded px-2 py-1 text-sm text-right" />
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            {!isRunning ? (
              <button onClick={handleStart} disabled={loading}
                className="flex-1 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm font-medium flex items-center justify-center gap-1 disabled:opacity-50">
                <Play size={14} /> {loading ? '启动中...' : '启动研发'}
              </button>
            ) : (
              <button onClick={handleStop}
                className="flex-1 bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded text-sm font-medium flex items-center justify-center gap-1">
                <Square size={14} /> 停止
              </button>
            )}
            {task && task.best_iteration !== null && !isRunning && (
              <button onClick={handleAccept}
                className="bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded text-sm font-medium flex items-center gap-1">
                <Download size={14} /> 保存最佳策略
              </button>
            )}
          </div>

          {/* Architecture diagram */}
          <div className="bg-crypto-card border border-crypto-border rounded-lg p-3">
            <h4 className="text-[10px] font-semibold text-gray-500 mb-2">v2 架构流程</h4>
            <div className="flex flex-col items-center gap-1 text-[10px]">
              <div className="flex items-center gap-1 text-blue-400">
                <FileText size={10} /> Planner <span className="text-gray-600">(规格书)</span>
              </div>
              <ArrowRight size={10} className="text-gray-600 rotate-90" />
              <div className="flex items-center gap-1 text-yellow-400">
                <GitBranch size={10} /> 合约协商 <span className="text-gray-600">(生成器↔评估器)</span>
              </div>
              <ArrowRight size={10} className="text-gray-600 rotate-90" />
              <div className="flex items-center gap-1 text-green-400">
                <Zap size={10} /> Strategist <span className="text-gray-600">(生成代码)</span>
              </div>
              <ArrowRight size={10} className="text-gray-600 rotate-90" />
              <div className="flex items-center gap-1 text-purple-400">
                <Cpu size={10} /> Backtester <span className="text-gray-600">(执行回测)</span>
              </div>
              <ArrowRight size={10} className="text-gray-600 rotate-90" />
              <div className="flex items-center gap-1 text-orange-400">
                <Target size={10} /> Evaluator <span className="text-gray-600">(独立评估)</span>
              </div>
              <RotateCcw size={10} className="text-gray-600 mt-1" />
            </div>
          </div>
        </div>

        {/* Middle: Iteration Timeline */}
        <div className="col-span-3">
          <div className="bg-crypto-card border border-crypto-border rounded-lg p-4 h-full overflow-auto">
            <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-1">
              <RefreshCw size={14} className={isRunning ? 'animate-spin' : ''} /> 迭代时间线
            </h3>
            {iterations.length === 0 && (
              <p className="text-xs text-gray-500 text-center mt-8">
                {isRunning ? '等待 Planner 生成规格书...' : '启动任务后将在此显示迭代进度'}
              </p>
            )}
            <div className="space-y-2">
              {iterations.map((it) => {
                const isBest = task?.best_iteration === it.iteration;
                const m = it.backtest_metrics;
                const act = ACTION_LABELS[it.action] || ACTION_LABELS['new'];
                return (
                  <button key={it.iteration}
                    onClick={() => setSelectedIter(it.iteration)}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      selectedIter === it.iteration
                        ? 'border-blue-500 bg-blue-500/10'
                        : 'border-crypto-border bg-crypto-bg hover:border-gray-600'
                    }`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-gray-300 flex items-center gap-1">
                        {isBest && <span className="text-yellow-400">★</span>}
                        第 {it.iteration + 1} 轮
                        <span className={`text-[10px] ${act.color}`}>[{act.label}]</span>
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        it.meets_goal ? 'bg-green-500/20 text-green-400' :
                        it.error ? 'bg-red-500/20 text-red-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {it.meets_goal ? '达标' : it.error ? '错误' : `${it.score.toFixed(0)}分`}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 truncate">{it.strategy_name || '生成中...'}</p>
                    {m && m.total_return_pct !== undefined && (
                      <div className="flex gap-2 mt-1 text-[10px]">
                        <span className={m.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}>
                          收益 {m.total_return_pct?.toFixed(1)}%
                        </span>
                        <span className="text-gray-500">夏普 {m.sharpe_ratio?.toFixed(2)}</span>
                        <span className="text-gray-500">回撤 {m.max_drawdown_pct?.toFixed(1)}%</span>
                      </div>
                    )}
                    {/* Mini score bar */}
                    {it.eval_scores && !it.error && (
                      <div className="mt-1.5 flex gap-0.5">
                        {(['risk_control','profitability','robustness','strategy_logic','originality'] as const).map(k => {
                          const v = it.eval_scores![k];
                          const color = v >= 70 ? 'bg-green-500' : v >= 50 ? 'bg-yellow-500' : 'bg-red-500';
                          return (
                            <div key={k} className="flex-1 h-1 bg-gray-700 rounded-full overflow-hidden" title={`${k}: ${v}`}>
                              <div className={`h-full ${color} rounded-full`} style={{ width: `${v}%` }} />
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right: Detail Panel */}
        <div className="col-span-6">
          {sel ? (
            <div className="space-y-3">
              {/* Eval Scores Radar + Metrics */}
              <div className="grid grid-cols-3 gap-3">
                {sel.eval_scores && (
                  <div className="bg-crypto-card border border-crypto-border rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-gray-400 mb-1 text-center">多维度评分</h4>
                    <RadarChart scores={sel.eval_scores} />
                    <div className="text-center mt-1">
                      <span className="text-lg font-bold text-blue-400">{sel.eval_scores.total_score.toFixed(0)}</span>
                      <span className="text-xs text-gray-500">/100</span>
                    </div>
                  </div>
                )}
                <div className={`${sel.eval_scores ? 'col-span-2' : 'col-span-3'}`}>
                  <div className="grid grid-cols-4 gap-2">
                    <MetricCard label="总收益率" value={`${sel.backtest_metrics.total_return_pct?.toFixed(1)}%`}
                      positive={sel.backtest_metrics.total_return_pct >= 0} />
                    <MetricCard label="夏普比率" value={sel.backtest_metrics.sharpe_ratio?.toFixed(2)}
                      positive={sel.backtest_metrics.sharpe_ratio >= goal.min_sharpe_ratio} />
                    <MetricCard label="最大回撤" value={`${sel.backtest_metrics.max_drawdown_pct?.toFixed(1)}%`}
                      positive={sel.backtest_metrics.max_drawdown_pct <= goal.max_drawdown_pct} />
                    <MetricCard label="胜率" value={`${sel.backtest_metrics.win_rate_pct?.toFixed(1)}%`}
                      positive={sel.backtest_metrics.win_rate_pct >= goal.min_win_rate_pct} />
                    <MetricCard label="盈亏比" value={sel.backtest_metrics.profit_factor?.toFixed(2)}
                      positive={sel.backtest_metrics.profit_factor >= goal.min_profit_factor} />
                    <MetricCard label="总交易数" value={sel.backtest_metrics.total_trades}
                      positive={sel.backtest_metrics.total_trades >= goal.min_total_trades} />
                    <MetricCard label="年化收益" value={`${sel.backtest_metrics.annual_return_pct?.toFixed(1)}%`}
                      positive={sel.backtest_metrics.annual_return_pct > 0} />
                    <MetricCard label="评分" value={`${sel.score.toFixed(0)}/100`}
                      positive={sel.meets_goal} />
                  </div>
                </div>
              </div>

              {/* Sprint Contract */}
              {sel.contract && (
                <div className="bg-crypto-card border border-yellow-500/20 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-yellow-400 mb-2 flex items-center gap-1">
                    <GitBranch size={14} /> Sprint 合约
                    <span className={`text-xs ml-2 ${ACTION_LABELS[sel.action]?.color || ''}`}>
                      [{ACTION_LABELS[sel.action]?.label || sel.action}]
                    </span>
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs text-gray-400">
                    <div>
                      <span className="text-gray-500">策略方向:</span> {sel.contract.strategy_direction}
                    </div>
                    <div>
                      <span className="text-gray-500">核心指标:</span> {sel.contract.key_indicators?.join(', ')}
                    </div>
                    <div><span className="text-gray-500">进场:</span> {sel.contract.entry_logic_desc}</div>
                    <div><span className="text-gray-500">出场:</span> {sel.contract.exit_logic_desc}</div>
                    <div className="col-span-2"><span className="text-gray-500">风控:</span> {sel.contract.risk_management_desc}</div>
                    {sel.contract.acceptance_criteria?.length > 0 && (
                      <div className="col-span-2">
                        <span className="text-gray-500">验收标准:</span>
                        <ul className="mt-1 space-y-0.5">
                          {sel.contract.acceptance_criteria.map((c, i) => (
                            <li key={i} className="flex items-start gap-1">
                              <ChevronRight size={10} className="text-yellow-400 mt-0.5 shrink-0" /> {c}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Analysis */}
              {sel.analysis && (
                <div className="bg-crypto-card border border-crypto-border rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-1">
                    <AlertCircle size={14} /> Evaluator 分析报告
                  </h4>
                  <p className="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">{sel.analysis}</p>
                  {sel.suggestions.length > 0 && (
                    <div className="mt-3">
                      <h5 className="text-xs font-semibold text-yellow-400 mb-1">优化建议:</h5>
                      <ul className="space-y-1">
                        {sel.suggestions.map((s, i) => (
                          <li key={i} className="text-xs text-gray-400 flex items-start gap-1">
                            <ChevronRight size={12} className="text-yellow-400 mt-0.5 shrink-0" />
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Reasoning */}
              {sel.reasoning && (
                <div className="bg-crypto-card border border-crypto-border rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-gray-300 mb-2">设计思路</h4>
                  <p className="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">{sel.reasoning}</p>
                </div>
              )}

              {/* Strategy Code */}
              {sel.strategy_code && (
                <div className="bg-crypto-card border border-crypto-border rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-1">
                    <Cpu size={14} /> 策略代码
                  </h4>
                  <pre className="bg-crypto-bg rounded p-3 text-xs text-green-300 overflow-auto max-h-80 font-mono leading-relaxed">
                    {sel.strategy_code}
                  </pre>
                  {sel.setup_code && sel.setup_code !== 'def setup(ctx):\n    pass' && (
                    <>
                      <h5 className="text-xs font-semibold text-gray-400 mt-3 mb-1">Setup 代码:</h5>
                      <pre className="bg-crypto-bg rounded p-3 text-xs text-blue-300 overflow-auto max-h-40 font-mono leading-relaxed">
                        {sel.setup_code}
                      </pre>
                    </>
                  )}
                </div>
              )}

              {/* Error */}
              {sel.error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-red-400 mb-1">错误</h4>
                  <p className="text-xs text-red-300">{sel.error}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-crypto-card border border-crypto-border rounded-lg p-8 flex flex-col items-center justify-center h-full text-gray-500">
              <Sparkles size={48} className="mb-4 opacity-30" />
              <p className="text-sm">在左侧选择迭代轮次查看详情</p>
              <p className="text-xs mt-2 text-gray-600 max-w-md text-center">
                v2 架构: Planner 规格书 → Sprint 合约协商 → Strategist 生成 → Backtester 回测 → Evaluator 独立评估，循环迭代
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, positive }: { label: string; value: any; positive: boolean }) {
  return (
    <div className={`bg-crypto-card border rounded-lg p-3 ${positive ? 'border-green-500/30' : 'border-crypto-border'}`}>
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className={`text-sm font-bold mt-0.5 ${positive ? 'text-green-400' : 'text-gray-300'}`}>
        {value ?? '--'}
      </div>
    </div>
  );
}
