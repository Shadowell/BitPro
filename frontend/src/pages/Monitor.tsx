import { useState, useEffect } from 'react';
import {
  Bell, Activity, Plus, Trash2, ToggleLeft, ToggleRight, X,
  BarChart3,
  RefreshCw, Zap, DollarSign, Eye,
} from 'lucide-react';
import clsx from 'clsx';
import { marketApi, monitorApi } from '../api/client';

interface Alert {
  id: number;
  name: string;
  type: string;
  exchange: string;
  symbol: string;
  condition: { threshold?: number };
  enabled: boolean;
  last_triggered_at?: string;
}

interface RunningStrategy {
  strategyId: number;
  name: string;
  status: string;
  exchange: string;
  symbols: string[];
  pnl: number;
  totalTrades: number;
}

interface MarketSentiment {
  longShortRatio: number | null;
  openInterest: number | null;
  openInterestChange: number | null;
  fundingRate: number | null;
  fearGreedIndex: number | null;
}

export default function Monitor() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [runningStrategies, setRunningStrategies] = useState<RunningStrategy[]>([]);
  const [showCreateAlert, setShowCreateAlert] = useState(false);
  const [sentiment, setSentiment] = useState<MarketSentiment>({
    longShortRatio: null, openInterest: null, openInterestChange: null,
    fundingRate: null, fearGreedIndex: null,
  });
  const [sentimentLoading, setSentimentLoading] = useState(false);

  const [alertForm, setAlertForm] = useState({
    name: '', type: 'price_above', exchange: 'okx', symbol: 'BTC/USDT',
    threshold: 100000, telegram_bot_token: '', telegram_chat_id: '',
  });

  useEffect(() => {
    fetchAlerts();
    fetchRunningStrategies();
    fetchMarketSentiment();
    const interval = setInterval(() => { fetchRunningStrategies(); fetchMarketSentiment(); }, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchAlerts = async () => {
    try {
      const data = await monitorApi.getAlerts();
      setAlerts(data);
    } catch {}
  };

  const fetchRunningStrategies = async () => {
    try {
      const data = await monitorApi.getRunningStrategies();
      setRunningStrategies(data);
    } catch {}
  };

  const fetchMarketSentiment = async () => {
    setSentimentLoading(true);
    try {
      // 并行请求多个数据源
      const [lsRes, oiRes, _frRes] = await Promise.allSettled([
        monitorApi.getLongShortRatio('okx', 'BTC/USDT:USDT'),
        monitorApi.getOpenInterest('okx', 'BTC/USDT:USDT'),
        marketApi.getTicker('okx', 'BTC/USDT'),
      ]);

      setSentiment({
        longShortRatio: lsRes.status === 'fulfilled' ? (lsRes.value.ratio ?? lsRes.value.longShortRatio ?? null) : null,
        openInterest: oiRes.status === 'fulfilled' ? (oiRes.value.openInterest ?? null) : null,
        openInterestChange: oiRes.status === 'fulfilled' ? (oiRes.value.change ?? oiRes.value.changePct ?? null) : null,
        fundingRate: null, // 后续可扩展
        fearGreedIndex: null,
      });
    } catch {
      // 保持默认
    } finally {
      setSentimentLoading(false);
    }
  };

  const createAlert = async () => {
    try {
      await monitorApi.createAlert({
        name: alertForm.name,
        type: alertForm.type,
        exchange: alertForm.exchange,
        symbol: alertForm.symbol,
        threshold: alertForm.threshold,
        telegramBotToken: alertForm.telegram_bot_token || undefined,
        telegramChatId: alertForm.telegram_chat_id || undefined,
      });
      setShowCreateAlert(false); fetchAlerts();
      setAlertForm({ name: '', type: 'price_above', exchange: 'okx', symbol: 'BTC/USDT', threshold: 100000, telegram_bot_token: '', telegram_chat_id: '' });
    } catch {}
  };

  const toggleAlert = async (id: number, enabled: boolean) => {
    try {
      await monitorApi.toggleAlert(id, !enabled);
      fetchAlerts();
    } catch {}
  };

  const deleteAlert = async (id: number) => {
    if (!confirm('确定删除此告警?')) return;
    try {
      await monitorApi.deleteAlert(id);
      fetchAlerts();
    } catch {}
  };

  const alertTypeLabels: Record<string, string> = {
    price_above: '价格高于', price_below: '价格低于', price_change: '价格变动%',
    funding_above: '费率高于', funding_below: '费率低于',
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Eye className="w-6 h-6 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">监控中心</h1>
        </div>
        <button onClick={fetchMarketSentiment} disabled={sentimentLoading}
          className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-400 hover:text-white bg-crypto-card border border-crypto-border rounded-xl transition-colors">
          <RefreshCw className={clsx('w-3.5 h-3.5', sentimentLoading && 'animate-spin')} />刷新数据
        </button>
      </div>

      {/* ====== 市场情绪指标卡片 ====== */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <SentimentCard
          label="多空比 (BTC)"
          value={sentiment.longShortRatio != null ? sentiment.longShortRatio.toFixed(2) : '--'}
          icon={<BarChart3 className="w-4 h-4" />}
          color={sentiment.longShortRatio != null ? (sentiment.longShortRatio > 1 ? 'green' : sentiment.longShortRatio < 1 ? 'red' : 'gray') : 'gray'}
          sub={sentiment.longShortRatio != null ? (sentiment.longShortRatio > 1 ? '多头占优' : sentiment.longShortRatio < 1 ? '空头占优' : '多空均衡') : '获取中...'}
        />
        <SentimentCard
          label="持仓量 (BTC)"
          value={sentiment.openInterest != null ? `$${(sentiment.openInterest / 1e8).toFixed(2)}亿` : '--'}
          icon={<DollarSign className="w-4 h-4" />}
          color="blue"
          sub={sentiment.openInterestChange != null ? `${sentiment.openInterestChange >= 0 ? '+' : ''}${sentiment.openInterestChange.toFixed(2)}%` : '-'}
        />
        <SentimentCard
          label="运行中策略"
          value={String(runningStrategies.length)}
          icon={<Activity className="w-4 h-4" />}
          color={runningStrategies.length > 0 ? 'green' : 'gray'}
          sub={runningStrategies.length > 0 ? `${runningStrategies.reduce((s, r) => s + r.totalTrades, 0)} 笔交易` : '暂无运行'}
        />
        <SentimentCard
          label="活跃告警"
          value={String(alerts.filter(a => a.enabled).length)}
          icon={<Bell className="w-4 h-4" />}
          color={alerts.filter(a => a.enabled).length > 0 ? 'yellow' : 'gray'}
          sub={`共 ${alerts.length} 条规则`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ====== 运行中的策略 ====== */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl">
          <div className="p-4 border-b border-crypto-border flex items-center gap-2">
            <Activity className="w-4 h-4 text-green-400" />
            <h2 className="text-sm font-semibold text-white">运行中的策略</h2>
            <span className="text-[10px] text-gray-500 ml-auto">{runningStrategies.length} 个</span>
          </div>
          <div className="p-4">
            {runningStrategies.length > 0 ? (
              <div className="space-y-3">
                {runningStrategies.map(s => (
                  <div key={s.strategyId} className="bg-crypto-bg rounded-xl p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                        <span className="text-sm text-white font-medium">{s.name}</span>
                      </div>
                      <span className={clsx('text-sm font-bold', s.pnl >= 0 ? 'text-up' : 'text-down')}>
                        {s.pnl >= 0 ? '+' : ''}{s.pnl.toFixed(2)} USDT
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-3 text-[11px] text-gray-500">
                      <span className="px-1.5 py-0.5 bg-gray-800 rounded">{s.exchange?.toUpperCase()}</span>
                      {s.symbols?.map(sym => <span key={sym}>{sym}</span>)}
                      <span className="ml-auto">{s.totalTrades} 笔交易</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <Activity className="w-12 h-12 text-gray-700 mx-auto mb-3" />
                <p className="text-gray-500 text-sm">暂无运行中的策略</p>
                <p className="text-gray-600 text-xs mt-1">前往"模拟/实盘"页面启动策略</p>
              </div>
            )}
          </div>
        </div>

        {/* ====== 告警配置 ====== */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl">
          <div className="p-4 border-b border-crypto-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell className="w-4 h-4 text-yellow-400" />
              <h2 className="text-sm font-semibold text-white">告警配置</h2>
            </div>
            <button onClick={() => setShowCreateAlert(true)}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg transition-colors">
              <Plus className="w-3 h-3" />添加
            </button>
          </div>
          <div className="p-4">
            {alerts.length > 0 ? (
              <div className="space-y-2">
                {alerts.map(alert => (
                  <div key={alert.id} className="flex items-center justify-between py-3 px-3 bg-crypto-bg rounded-xl">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white font-medium truncate">{alert.name}</div>
                      <div className="text-[11px] text-gray-500 mt-0.5">
                        {alert.symbol} · {alertTypeLabels[alert.type] || alert.type} {alert.condition?.threshold}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 ml-3">
                      <button onClick={() => toggleAlert(alert.id, alert.enabled)}
                        className={clsx('p-1 rounded transition-colors', alert.enabled ? 'text-green-400 hover:bg-green-500/10' : 'text-gray-500 hover:bg-gray-500/10')}>
                        {alert.enabled ? <ToggleRight className="w-5 h-5" /> : <ToggleLeft className="w-5 h-5" />}
                      </button>
                      <button onClick={() => deleteAlert(alert.id)} className="p-1 text-red-400 hover:bg-red-500/10 rounded transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <Bell className="w-12 h-12 text-gray-700 mx-auto mb-3" />
                <p className="text-gray-500 text-sm">暂无告警配置</p>
                <p className="text-gray-600 text-xs mt-1">支持价格告警和资金费率告警</p>
              </div>
            )}
          </div>
        </div>

        {/* ====== 告警类型说明 ====== */}
        <div className="bg-crypto-card border border-crypto-border rounded-xl p-5 lg:col-span-2">
          <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Zap className="w-4 h-4 text-purple-400" />
            告警类型说明
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { type: 'price_above', label: '价格高于', desc: '当价格突破阈值时触发', color: 'text-green-400' },
              { type: 'price_below', label: '价格低于', desc: '当价格跌破阈值时触发', color: 'text-red-400' },
              { type: 'price_change', label: '价格变动', desc: '价格变动超过阈值%时触发', color: 'text-yellow-400' },
              { type: 'funding_above', label: '费率高于', desc: '资金费率超过阈值时触发', color: 'text-blue-400' },
              { type: 'funding_below', label: '费率低于', desc: '资金费率低于阈值时触发', color: 'text-purple-400' },
            ].map(item => (
              <div key={item.type} className="bg-crypto-bg rounded-xl p-3">
                <div className={clsx('text-xs font-semibold mb-1', item.color)}>{item.label}</div>
                <div className="text-[10px] text-gray-500 leading-relaxed">{item.desc}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl flex items-start gap-2">
            <Zap className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
            <div className="text-xs text-blue-300/80">
              支持 Telegram 推送通知，在创建告警时配置 Bot Token 和 Chat ID 即可接收实时消息提醒。
            </div>
          </div>
        </div>
      </div>

      {/* 创建告警对话框 */}
      {showCreateAlert && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-crypto-card border border-crypto-border rounded-xl w-full max-w-md">
            <div className="p-4 border-b border-crypto-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">新建告警</h3>
              <button onClick={() => setShowCreateAlert(false)} className="text-gray-400 hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-4 space-y-3">
              <div><label className="block text-xs text-gray-400 mb-1">告警名称</label>
                <input type="text" value={alertForm.name} onChange={e => setAlertForm({ ...alertForm, name: e.target.value })} placeholder="BTC 突破 10万"
                  className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" /></div>
              <div><label className="block text-xs text-gray-400 mb-1">告警类型</label>
                <select value={alertForm.type} onChange={e => setAlertForm({ ...alertForm, type: e.target.value })}
                  className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white">
                  <option value="price_above">价格高于</option><option value="price_below">价格低于</option>
                  <option value="price_change">价格变动%</option><option value="funding_above">费率高于</option>
                  <option value="funding_below">费率低于</option>
                </select></div>
              <div className="grid grid-cols-2 gap-2">
                <div><label className="block text-xs text-gray-400 mb-1">交易对</label>
                  <input type="text" value={alertForm.symbol} onChange={e => setAlertForm({ ...alertForm, symbol: e.target.value })}
                    className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" /></div>
                <div><label className="block text-xs text-gray-400 mb-1">阈值</label>
                  <input type="number" value={alertForm.threshold} onChange={e => setAlertForm({ ...alertForm, threshold: Number(e.target.value) })}
                    className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" /></div>
              </div>
              <div className="border-t border-crypto-border pt-3">
                <div className="text-xs text-gray-500 mb-2">Telegram 通知（可选）</div>
                <input type="text" value={alertForm.telegram_bot_token} onChange={e => setAlertForm({ ...alertForm, telegram_bot_token: e.target.value })} placeholder="Bot Token"
                  className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white mb-2" />
                <input type="text" value={alertForm.telegram_chat_id} onChange={e => setAlertForm({ ...alertForm, telegram_chat_id: e.target.value })} placeholder="Chat ID"
                  className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white" />
              </div>
            </div>
            <div className="p-4 border-t border-crypto-border flex justify-end gap-2">
              <button onClick={() => setShowCreateAlert(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">取消</button>
              <button onClick={createAlert} className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg">创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================
// 情绪指标卡片
// ============================================
function SentimentCard({ label, value, icon, color, sub }: {
  label: string; value: string; icon: React.ReactNode; color: 'green' | 'red' | 'blue' | 'yellow' | 'gray'; sub: string;
}) {
  const colorMap = {
    green: { bg: 'bg-green-500/10', border: 'border-green-500/20', text: 'text-green-400' },
    red: { bg: 'bg-red-500/10', border: 'border-red-500/20', text: 'text-red-400' },
    blue: { bg: 'bg-blue-500/10', border: 'border-blue-500/20', text: 'text-blue-400' },
    yellow: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', text: 'text-yellow-400' },
    gray: { bg: 'bg-gray-500/10', border: 'border-gray-500/20', text: 'text-gray-400' },
  };
  const c = colorMap[color];
  return (
    <div className={clsx('rounded-xl p-4 border', c.bg, c.border)}>
      <div className="flex items-center gap-1.5 mb-2">
        <span className={c.text}>{icon}</span>
        <span className="text-[11px] text-gray-500">{label}</span>
      </div>
      <div className={clsx('text-xl font-bold', c.text)}>{value}</div>
      <div className="text-[10px] text-gray-500 mt-1">{sub}</div>
    </div>
  );
}
