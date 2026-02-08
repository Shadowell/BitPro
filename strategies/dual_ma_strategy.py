"""
双均线策略
短期均线上穿长期均线时买入，下穿时卖出

使用方法:
1. 在策略管理页面创建新策略
2. 粘贴此代码
3. 配置参数: {"fast_period": 7, "slow_period": 25, "position_size": 0.01}
4. 启动策略
"""

# 策略配置
FAST_PERIOD = config.get('fast_period', 7)      # 快线周期
SLOW_PERIOD = config.get('slow_period', 25)     # 慢线周期
POSITION_SIZE = config.get('position_size', 0.01)
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT'

# 策略状态
position = 0  # 当前持仓: 0=无, 1=多
last_fast_ma = None
last_slow_ma = None

def calculate_ma(closes, period):
    """计算移动平均"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def on_init():
    """策略初始化"""
    log(f"双均线策略初始化")
    log(f"交易对: {TARGET_SYMBOL}")
    log(f"快线周期: {FAST_PERIOD}, 慢线周期: {SLOW_PERIOD}")
    log(f"仓位大小: {POSITION_SIZE}")

def on_tick(ticker):
    """行情更新回调"""
    global position, last_fast_ma, last_slow_ma
    
    symbol = ticker.get('symbol', '')
    if TARGET_SYMBOL not in symbol:
        return
    
    # 获取K线数据计算均线
    klines = get_klines(TARGET_SYMBOL, '1h', SLOW_PERIOD + 10)
    
    if not klines or len(klines) < SLOW_PERIOD:
        return
    
    # 提取收盘价
    closes = [k.get('close', 0) for k in klines]
    
    # 计算均线
    fast_ma = calculate_ma(closes, FAST_PERIOD)
    slow_ma = calculate_ma(closes, SLOW_PERIOD)
    
    if fast_ma is None or slow_ma is None:
        return
    
    current_price = ticker.get('last', 0)
    
    # 金叉 (快线上穿慢线)
    if last_fast_ma and last_slow_ma:
        if last_fast_ma <= last_slow_ma and fast_ma > slow_ma:
            if position == 0:
                log(f"金叉信号! 快线 {fast_ma:.2f} > 慢线 {slow_ma:.2f}")
                log(f"当前价格: {current_price:.2f}, 买入")
                
                order_id = buy(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
                if order_id:
                    position = 1
                    set_position(TARGET_SYMBOL, POSITION_SIZE)
        
        # 死叉 (快线下穿慢线)
        elif last_fast_ma >= last_slow_ma and fast_ma < slow_ma:
            if position == 1:
                log(f"死叉信号! 快线 {fast_ma:.2f} < 慢线 {slow_ma:.2f}")
                log(f"当前价格: {current_price:.2f}, 卖出")
                
                order_id = sell(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
                if order_id:
                    position = 0
                    set_position(TARGET_SYMBOL, 0)
    
    # 保存当前均线值
    last_fast_ma = fast_ma
    last_slow_ma = slow_ma

def on_funding(rate):
    """资金费率回调 (此策略不使用)"""
    pass
