import { useEffect, useState } from 'react';
import {
  Trash2, Plus, Code2, Save, X, FileCode, Copy, Search,
  ChevronRight, Edit3, Zap, TrendingUp,
  BarChart3, Layers, BookOpen, Loader2, CheckCircle2,
  XCircle, ArrowLeft, Clock,
} from 'lucide-react';
import { useStore } from '../stores/useStore';
import { strategyApi } from '../api/client';
import type { Strategy as StrategyType } from '../types';
import clsx from 'clsx';

// ============================================
// 策略模板
// ============================================
const STRATEGY_TEMPLATES = [
  {
    key: 'dual_ma',
    name: '双均线交叉策略',
    category: '趋势跟踪',
    difficulty: '入门',
    description: '短期均线上穿长期均线时买入（金叉），下穿时卖出（死叉）。经典的趋势跟随策略。',
    tags: ['均线', '趋势', '入门'],
    code: `"""
双均线策略
短期均线上穿长期均线时买入，下穿时卖出
"""

# 策略配置
FAST_PERIOD = config.get('fast_period', 7)
SLOW_PERIOD = config.get('slow_period', 25)
POSITION_SIZE = config.get('position_size', 0.01)
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT'

# 策略状态
position = 0
last_fast_ma = None
last_slow_ma = None

def calculate_ma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def on_init():
    log(f"双均线策略初始化")
    log(f"交易对: {TARGET_SYMBOL}")
    log(f"快线周期: {FAST_PERIOD}, 慢线周期: {SLOW_PERIOD}")

def on_tick(ticker):
    global position, last_fast_ma, last_slow_ma
    
    symbol = ticker.get('symbol', '')
    if TARGET_SYMBOL not in symbol:
        return
    
    klines = get_klines(TARGET_SYMBOL, '1h', SLOW_PERIOD + 10)
    if not klines or len(klines) < SLOW_PERIOD:
        return
    
    closes = [k.get('close', 0) for k in klines]
    fast_ma = calculate_ma(closes, FAST_PERIOD)
    slow_ma = calculate_ma(closes, SLOW_PERIOD)
    
    if fast_ma is None or slow_ma is None:
        return
    
    if last_fast_ma and last_slow_ma:
        # 金叉买入
        if last_fast_ma <= last_slow_ma and fast_ma > slow_ma:
            if position == 0:
                log(f"金叉信号! 买入")
                order_id = buy(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
                if order_id:
                    position = 1
        # 死叉卖出
        elif last_fast_ma >= last_slow_ma and fast_ma < slow_ma:
            if position == 1:
                log(f"死叉信号! 卖出")
                order_id = sell(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
                if order_id:
                    position = 0
    
    last_fast_ma = fast_ma
    last_slow_ma = slow_ma

def on_funding(rate):
    pass
`,
    defaultConfig: { fast_period: 7, slow_period: 25, position_size: 0.01 },
  },
  {
    key: 'funding_arb',
    name: '资金费率套利策略',
    category: '套利',
    difficulty: '进阶',
    description: '监控永续合约资金费率，当费率超过阈值时做空赚取费率收入。属于低风险中收益策略。',
    tags: ['资金费率', '套利', '低风险'],
    code: `"""
资金费率套利策略
当资金费率 > 阈值时，做空永续合约，赚取费率收入
"""

# 策略配置
MIN_RATE = config.get('min_rate', 0.0001)
POSITION_SIZE = config.get('position_size', 0.01)
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT:USDT'

# 策略状态
in_position = False
entry_rate = 0

def on_init():
    log(f"资金费率套利策略初始化")
    log(f"交易对: {TARGET_SYMBOL}")
    log(f"最小费率阈值: {MIN_RATE:.4%}")

def on_tick(ticker):
    pass

def on_funding(rate):
    global in_position, entry_rate
    
    symbol = rate.get('symbol', '')
    current_rate = rate.get('current_rate', 0) or 0
    
    log(f"{symbol} 资金费率: {current_rate:.4%}")
    
    if current_rate > MIN_RATE and not in_position:
        log(f"检测到高费率机会: {current_rate:.4%}")
        order_id = sell(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
        if order_id:
            in_position = True
            entry_rate = current_rate
    
    elif in_position and (current_rate < 0 or current_rate < entry_rate * 0.3):
        log(f"费率下降，平仓")
        order_id = buy(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
        if order_id:
            in_position = False
            entry_rate = 0
`,
    defaultConfig: { min_rate: 0.0001, position_size: 0.01 },
  },
  {
    key: 'grid',
    name: '网格交易策略',
    category: '震荡',
    difficulty: '入门',
    description: '在价格区间内设置等间距买卖网格，低买高卖。适合震荡市场，稳定收益。',
    tags: ['网格', '震荡', '稳定'],
    code: `"""
网格交易策略
在价格区间内设置买卖网格，低买高卖
"""

# 策略配置
PRICE_LOW = config.get('price_low', 90000)
PRICE_HIGH = config.get('price_high', 100000)
GRID_NUM = config.get('grid_num', 10)
ORDER_AMOUNT = config.get('order_amount', 0.001)
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT'

# 策略状态
grid_prices = []
grid_status = {}

def on_init():
    global grid_prices, grid_status
    
    step = (PRICE_HIGH - PRICE_LOW) / GRID_NUM
    grid_prices = [round(PRICE_LOW + i * step, 2) for i in range(GRID_NUM + 1)]
    
    for price in grid_prices:
        grid_status[price] = None
    
    log(f"网格交易策略初始化")
    log(f"交易对: {TARGET_SYMBOL}")
    log(f"价格区间: {PRICE_LOW} - {PRICE_HIGH}")
    log(f"网格数量: {GRID_NUM}")

def on_tick(ticker):
    symbol = ticker.get('symbol', '')
    if TARGET_SYMBOL not in symbol:
        return
    
    current_price = ticker.get('last', 0)
    
    if current_price < PRICE_LOW or current_price > PRICE_HIGH:
        return
    
    for i, grid_price in enumerate(grid_prices):
        if i == 0:
            continue
        
        lower_grid = grid_prices[i - 1]
        upper_grid = grid_price
        
        if abs(current_price - lower_grid) / lower_grid < 0.001:
            if grid_status.get(lower_grid) != 'buy':
                log(f"触及网格 {lower_grid}, 买入")
                order_id = buy(TARGET_SYMBOL, ORDER_AMOUNT, price=lower_grid, order_type='limit')
                if order_id:
                    grid_status[lower_grid] = 'buy'
        
        elif abs(current_price - upper_grid) / upper_grid < 0.001:
            if grid_status.get(upper_grid) != 'sell':
                log(f"触及网格 {upper_grid}, 卖出")
                order_id = sell(TARGET_SYMBOL, ORDER_AMOUNT, price=upper_grid, order_type='limit')
                if order_id:
                    grid_status[upper_grid] = 'sell'

def on_funding(rate):
    pass
`,
    defaultConfig: { price_low: 90000, price_high: 100000, grid_num: 10, order_amount: 0.001 },
  },
  {
    key: 'rsi_reversal',
    name: 'RSI 反转策略',
    category: '震荡',
    difficulty: '入门',
    description: 'RSI 超卖时买入，超买时卖出。利用市场过度反应获取均值回归收益。',
    tags: ['RSI', '超买超卖', '均值回归'],
    code: `"""
RSI 反转策略
RSI 低于30买入，RSI 高于70卖出
"""

PERIOD = config.get('rsi_period', 14)
OVERBOUGHT = config.get('overbought', 70)
OVERSOLD = config.get('oversold', 30)
POSITION_SIZE = config.get('position_size', 0.01)
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT'

position = 0

def calc_rsi(closes, period):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def on_init():
    log(f"RSI 反转策略初始化: 周期={PERIOD}, 超买={OVERBOUGHT}, 超卖={OVERSOLD}")

def on_tick(ticker):
    global position
    symbol = ticker.get('symbol', '')
    if TARGET_SYMBOL not in symbol:
        return
    
    klines = get_klines(TARGET_SYMBOL, '1h', PERIOD + 10)
    if not klines or len(klines) < PERIOD + 1:
        return
    
    closes = [k.get('close', 0) for k in klines]
    rsi = calc_rsi(closes, PERIOD)
    
    if rsi is None:
        return
    
    if rsi < OVERSOLD and position == 0:
        log(f"RSI={rsi:.1f} 超卖，买入")
        order_id = buy(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
        if order_id:
            position = 1
    elif rsi > OVERBOUGHT and position == 1:
        log(f"RSI={rsi:.1f} 超买，卖出")
        order_id = sell(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
        if order_id:
            position = 0

def on_funding(rate):
    pass
`,
    defaultConfig: { rsi_period: 14, overbought: 70, oversold: 30, position_size: 0.01 },
  },
  {
    key: 'empty',
    name: '空白策略',
    category: '自定义',
    difficulty: '自定义',
    description: '从零开始编写您的专属交易策略。提供基础回调框架和 API 接口。',
    tags: ['自定义', '灵活'],
    code: `"""
自定义策略
"""

# 策略配置
POSITION_SIZE = config.get('position_size', 0.01)
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT'

def on_init():
    """策略初始化"""
    log(f"策略初始化")
    log(f"交易对: {TARGET_SYMBOL}")

def on_tick(ticker):
    """行情更新回调"""
    symbol = ticker.get('symbol', '')
    price = ticker.get('last', 0)
    # 在这里编写交易逻辑
    pass

def on_funding(rate):
    """资金费率回调"""
    pass
`,
    defaultConfig: { position_size: 0.01 },
  },
];

type PageView = 'list' | 'editor' | 'detail';
type ListTab = 'my' | 'plaza';

// ============================================
// 主组件
// ============================================
export default function Strategy() {
  const { strategies, isLoadingStrategies, fetchStrategies } = useStore();
  const [_selectedStrategy, _setSelectedStrategy] = useState<StrategyType | null>(null);

  // 页面视图
  const [view, setView] = useState<PageView>('list');
  const [listTab, setListTab] = useState<ListTab>('my');
  const [searchQuery, setSearchQuery] = useState('');

  // 创建/编辑模式
  const [editMode, setEditMode] = useState<'create' | 'edit'>('create');
  const [editingStrategy, setEditingStrategy] = useState<StrategyType | null>(null);

  // 编辑器表单
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    scriptContent: STRATEGY_TEMPLATES[4].code,
    exchange: 'okx',
    symbols: 'BTC/USDT',
    config: JSON.stringify(STRATEGY_TEMPLATES[4].defaultConfig, null, 2),
  });

  // 状态
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { fetchStrategies(); }, []);

  // 消息自动关闭
  useEffect(() => {
    if (message) {
      const t = setTimeout(() => setMessage(null), 3000);
      return () => clearTimeout(t);
    }
  }, [message]);

  // ============================================
  // 操作函数
  // ============================================
  const handleCreateFromTemplate = (template: typeof STRATEGY_TEMPLATES[0]) => {
    setEditMode('create');
    setEditingStrategy(null);
    setFormData({
      name: template.name,
      description: template.description,
      scriptContent: template.code,
      exchange: 'okx',
      symbols: 'BTC/USDT',
      config: JSON.stringify(template.defaultConfig, null, 2),
    });
    setView('editor');
  };

  const handleEditStrategy = (strategy: StrategyType) => {
    setEditMode('edit');
    setEditingStrategy(strategy);
    setFormData({
      name: strategy.name,
      description: strategy.description || '',
      scriptContent: strategy.scriptContent || '',
      exchange: strategy.exchange || 'okx',
      symbols: strategy.symbols?.join(', ') || 'BTC/USDT',
      config: JSON.stringify(strategy.config || {}, null, 2),
    });
    setView('editor');
  };

  const handleSave = async () => {
    if (!formData.name.trim()) { setMessage({ type: 'error', text: '请输入策略名称' }); return; }
    if (!formData.scriptContent.trim()) { setMessage({ type: 'error', text: '请输入策略代码' }); return; }

    let configObj = {};
    try { configObj = JSON.parse(formData.config); } catch {
      setMessage({ type: 'error', text: '配置 JSON 格式错误' }); return;
    }

    setSaving(true);
    try {
      if (editMode === 'edit' && editingStrategy) {
        await strategyApi.update(editingStrategy.id, {
          name: formData.name,
          description: formData.description,
          scriptContent: formData.scriptContent,
          exchange: formData.exchange,
          symbols: formData.symbols.split(',').map(s => s.trim()).filter(Boolean),
          config: configObj,
        });
        setMessage({ type: 'success', text: '策略保存成功' });
      } else {
        await strategyApi.create({
          name: formData.name,
          description: formData.description,
          scriptContent: formData.scriptContent,
          exchange: formData.exchange,
          symbols: formData.symbols.split(',').map(s => s.trim()).filter(Boolean),
          config: configObj,
        });
        setMessage({ type: 'success', text: '策略创建成功' });
      }
      fetchStrategies();
      setView('list');
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || '操作失败' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除此策略吗？')) return;
    try { await strategyApi.delete(id); setMessage({ type: 'success', text: '策略已删除' }); fetchStrategies(); }
    catch { setMessage({ type: 'error', text: '删除失败' }); }
  };

  // 搜索过滤
  const filteredStrategies = strategies.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (s.description || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredTemplates = STRATEGY_TEMPLATES.filter(t =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.tags.some(tag => tag.includes(searchQuery.toLowerCase()))
  );

  // ============================================
  // 渲染：策略列表页
  // ============================================
  const renderListView = () => (
    <div className="space-y-6">
      {/* 顶部标题 + 操作 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Code2 className="w-6 h-6 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">策略中心</h1>
        </div>
        <button onClick={() => handleCreateFromTemplate(STRATEGY_TEMPLATES[4])}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium transition-colors">
          <Plus className="w-4 h-4" />新建策略
        </button>
      </div>

      {/* Tab + 搜索 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 bg-crypto-card border border-crypto-border rounded-xl p-1">
          <button onClick={() => setListTab('my')}
            className={clsx('px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              listTab === 'my' ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500 hover:text-gray-300')}>
            <span className="flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" />我的策略</span>
          </button>
          <button onClick={() => setListTab('plaza')}
            className={clsx('px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              listTab === 'plaza' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300')}>
            <span className="flex items-center gap-1.5"><BookOpen className="w-3.5 h-3.5" />策略广场</span>
          </button>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            placeholder="搜索策略..."
            className="bg-crypto-card border border-crypto-border rounded-xl pl-10 pr-4 py-2 text-sm text-white w-64 placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
        </div>
      </div>

      {/* 我的策略 Tab */}
      {listTab === 'my' && (
        <div>
          {isLoadingStrategies ? (
            <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-gray-500" /></div>
          ) : filteredStrategies.length === 0 ? (
            <div className="bg-crypto-card border border-crypto-border rounded-xl flex flex-col items-center justify-center py-20">
              <Code2 className="w-16 h-16 text-gray-700 mb-4" />
              <p className="text-gray-500 text-sm mb-1">暂无策略</p>
              <p className="text-gray-600 text-xs">从策略广场选择模板开始，或新建空白策略</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredStrategies.map(s => {
                const updatedAt = (s as any).updatedAt || (s as any).createdAt;
                const cfg = s.config || {} as any;
                const riskLevel = cfg.risk_level || cfg.riskLevel;
                const timeframe = cfg.timeframe;
                const suitableFor = cfg.suitable_for || cfg.suitableFor;
                const isRecommended = cfg.recommended;
                const riskColor = riskLevel === '低' ? 'text-green-400 bg-green-500/10 border-green-500/10'
                  : riskLevel === '中' ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/10'
                  : riskLevel === '中低' ? 'text-green-300 bg-green-500/10 border-green-500/10'
                  : riskLevel === '中高' ? 'text-orange-400 bg-orange-500/10 border-orange-500/10'
                  : 'text-gray-400 bg-gray-500/10 border-gray-500/10';
                return (
                  <div key={s.id} className="bg-crypto-card border border-crypto-border rounded-xl overflow-hidden hover:border-gray-600 transition-all group">
                    {/* 卡片头部 */}
                    <div className="p-5 pb-3">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className={clsx('w-2 h-2 rounded-full flex-shrink-0 mt-1',
                            s.status === 'running' ? 'bg-green-400 animate-pulse' : s.status === 'error' ? 'bg-red-400' : 'bg-gray-600'
                          )} />
                          <h3 className="text-sm font-semibold text-white truncate">{s.name}</h3>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {isRecommended && (
                            <span className="px-1.5 py-0.5 text-[10px] font-bold bg-green-500/20 text-green-400 rounded-full">推荐</span>
                          )}
                          <button onClick={() => handleDelete(s.id)}
                            className="opacity-0 group-hover:opacity-100 p-1 text-gray-600 hover:text-red-400 transition-all"
                            title="删除策略">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed ml-[18px] min-h-[2.25rem]">
                        {s.description || '暂无描述'}
                      </p>
                    </div>

                    {/* 标签区域 */}
                    <div className="px-5 pb-3 flex items-center gap-1.5 flex-wrap">
                      {s.exchange && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400/80 border border-blue-500/10">
                          {s.exchange.toUpperCase()}
                        </span>
                      )}
                      {riskLevel && (
                        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border', riskColor)}>
                          {riskLevel}风险
                        </span>
                      )}
                      {timeframe && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400/80 border border-purple-500/10">
                          {timeframe}
                        </span>
                      )}
                      {s.symbols?.map(sym => (
                        <span key={sym} className="text-[10px] px-1.5 py-0.5 rounded bg-crypto-bg text-gray-500 border border-crypto-border">
                          {sym.split('/')[0]}
                        </span>
                      ))}
                      {updatedAt && (
                        <span className="text-[10px] text-gray-600 flex items-center gap-0.5 ml-auto">
                          <Clock className="w-3 h-3" />
                          {new Date(updatedAt).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                        </span>
                      )}
                    </div>
                    {suitableFor && (
                      <div className="px-5 pb-3">
                        <span className="text-[10px] text-gray-600 flex items-center gap-1">
                          <Zap className="w-3 h-3" />适合: {suitableFor}
                        </span>
                      </div>
                    )}

                    {/* 底部操作 */}
                    <div className="border-t border-crypto-border flex">
                      <button onClick={() => handleEditStrategy(s)}
                        className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs text-gray-400 hover:text-blue-400 hover:bg-blue-500/5 transition-colors">
                        <Edit3 className="w-3 h-3" />查看/编辑
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 策略广场 Tab - 模板列表 */}
      {listTab === 'plaza' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTemplates.map(t => (
            <div key={t.key} className="bg-crypto-card border border-crypto-border rounded-xl overflow-hidden hover:border-purple-500/40 transition-all group cursor-pointer"
              onClick={() => handleCreateFromTemplate(t)}>
              <div className="p-5 pb-3">
                <div className="flex items-start justify-between mb-2.5">
                  <div className="flex items-center gap-2.5">
                    <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
                      t.category === '趋势跟踪' ? 'bg-blue-500/15 text-blue-400' :
                      t.category === '套利' ? 'bg-green-500/15 text-green-400' :
                      t.category === '震荡' ? 'bg-yellow-500/15 text-yellow-400' :
                      'bg-gray-500/15 text-gray-400'
                    )}>
                      {t.category === '趋势跟踪' ? <TrendingUp className="w-4 h-4" /> :
                       t.category === '套利' ? <Zap className="w-4 h-4" /> :
                       t.category === '震荡' ? <BarChart3 className="w-4 h-4" /> :
                       <Code2 className="w-4 h-4" />}
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-white">{t.name}</h3>
                      <span className="text-[10px] text-gray-500">{t.category}</span>
                    </div>
                  </div>
                  <span className={clsx('text-[10px] px-2 py-0.5 rounded-full flex-shrink-0',
                    t.difficulty === '入门' ? 'bg-green-500/15 text-green-400' :
                    t.difficulty === '进阶' ? 'bg-yellow-500/15 text-yellow-400' :
                    'bg-gray-500/15 text-gray-400'
                  )}>
                    {t.difficulty}
                  </span>
                </div>
                <p className="text-xs text-gray-400 leading-relaxed min-h-[2.25rem] line-clamp-2">{t.description}</p>
              </div>
              <div className="px-5 pb-3 flex items-center gap-1.5 flex-wrap">
                {t.tags.map(tag => (
                  <span key={tag} className="text-[10px] px-2 py-0.5 bg-crypto-bg text-gray-500 rounded border border-crypto-border">{tag}</span>
                ))}
              </div>
              <div className="border-t border-crypto-border px-5 py-2.5 flex items-center justify-between">
                <span className="text-[10px] text-gray-600">点击使用此模板</span>
                <ChevronRight className="w-4 h-4 text-gray-600 group-hover:text-purple-400 transition-colors" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // ============================================
  // 渲染：策略编辑器
  // ============================================
  const renderEditorView = () => (
    <div className="h-full flex flex-col">
      {/* 编辑器顶部工具栏 */}
      <div className="flex items-center justify-between px-2 py-3 border-b border-crypto-border shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => setView('list')}
            className="flex items-center gap-1 text-gray-400 hover:text-white text-sm transition-colors">
            <ArrowLeft className="w-4 h-4" />返回
          </button>
          <div className="w-px h-5 bg-crypto-border" />
          <FileCode className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-white">{editMode === 'edit' ? '编辑策略' : '新建策略'}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { navigator.clipboard.writeText(formData.scriptContent); setMessage({ type: 'success', text: '代码已复制' }); }}
            className="flex items-center gap-1 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-crypto-bg rounded-lg transition-colors">
            <Copy className="w-3 h-3" />复制
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-1.5 px-5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {/* 编辑器主体 */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-0 min-h-0 overflow-hidden">
        {/* 左侧：配置面板 */}
        <div className="lg:col-span-1 border-r border-crypto-border overflow-y-auto p-4 space-y-4 bg-crypto-card/50">
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">策略名称 <span className="text-red-400">*</span></label>
            <input type="text" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })}
              placeholder="输入策略名称"
              className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">策略描述</label>
            <textarea value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })}
              placeholder="简要描述策略逻辑..." rows={3}
              className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none resize-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">交易所</label>
            <select value={formData.exchange} onChange={e => setFormData({ ...formData, exchange: e.target.value })}
              className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white">
              <option value="okx">OKX</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">交易对（逗号分隔）</label>
            <input type="text" value={formData.symbols} onChange={e => setFormData({ ...formData, symbols: e.target.value })}
              placeholder="BTC/USDT, ETH/USDT"
              className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">策略参数 (JSON)</label>
            <textarea value={formData.config} onChange={e => setFormData({ ...formData, config: e.target.value })}
              rows={6}
              className="w-full bg-crypto-bg border border-crypto-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-blue-500 focus:outline-none resize-none" />
          </div>

          {/* API 提示 */}
          <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="text-[10px] text-blue-400 font-semibold mb-1.5">可用 API</div>
            <div className="text-[10px] text-gray-400 space-y-1 font-mono">
              <div><span className="text-green-400">buy</span>(symbol, amount)</div>
              <div><span className="text-red-400">sell</span>(symbol, amount)</div>
              <div><span className="text-blue-400">get_klines</span>(symbol, tf, n)</div>
              <div><span className="text-blue-400">get_ticker</span>(symbol)</div>
              <div><span className="text-yellow-400">log</span>(message)</div>
              <div><span className="text-gray-500">config</span> · <span className="text-gray-500">symbols</span></div>
            </div>
          </div>
        </div>

        {/* 右侧：代码编辑器 */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-4 py-2 bg-gray-900/50 border-b border-crypto-border shrink-0">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <FileCode className="w-3.5 h-3.5" />
              <span>strategy.py</span>
            </div>
            <span className="text-[10px] text-gray-600">Python</span>
          </div>
          <textarea
            value={formData.scriptContent}
            onChange={e => setFormData({ ...formData, scriptContent: e.target.value })}
            className="flex-1 w-full bg-gray-950 text-gray-300 font-mono text-sm leading-relaxed px-4 py-3 focus:outline-none resize-none"
            spellCheck={false}
            style={{ tabSize: 4 }}
          />
        </div>
      </div>
    </div>
  );

  // ============================================
  // 主渲染
  // ============================================
  return (
    <div className={clsx('h-full flex flex-col', view === 'list' ? 'p-6' : '')}>
      {/* 消息提示 */}
      {message && (
        <div className={clsx('fixed top-4 right-4 z-50 px-4 py-3 rounded-xl flex items-center gap-2 shadow-lg',
          message.type === 'success' ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'
        )}>
          {message.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          <span className="text-sm">{message.text}</span>
          <button onClick={() => setMessage(null)} className="ml-2"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {view === 'list' && renderListView()}
      {view === 'editor' && renderEditorView()}

      {/* 启动策略请前往「模拟/实盘」模块 */}
    </div>
  );
}
