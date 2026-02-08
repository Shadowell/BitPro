"""
资金费率套利策略
当资金费率 > 阈值时，做空永续合约，赚取费率收入

使用方法:
1. 在策略管理页面创建新策略
2. 粘贴此代码
3. 配置参数: {"min_rate": 0.0001, "position_size": 0.01}
4. 启动策略
"""

# 策略配置 (从 config 获取或使用默认值)
MIN_RATE = config.get('min_rate', 0.0001)       # 最小费率阈值
POSITION_SIZE = config.get('position_size', 0.01)  # 仓位大小
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT:USDT'

# 策略状态
in_position = False
entry_rate = 0

def on_init():
    """策略初始化"""
    log(f"资金费率套利策略初始化")
    log(f"交易所: {exchange_name}")
    log(f"交易对: {TARGET_SYMBOL}")
    log(f"最小费率阈值: {MIN_RATE:.4%}")
    log(f"仓位大小: {POSITION_SIZE}")

def on_tick(ticker):
    """行情更新回调"""
    # 套利策略主要关注资金费率，这里仅监控价格
    pass

def on_funding(rate):
    """资金费率更新回调"""
    global in_position, entry_rate
    
    symbol = rate.get('symbol', '')
    current_rate = rate.get('current_rate', 0) or 0
    next_time = rate.get('next_funding_time', 0)
    
    log(f"{symbol} 资金费率: {current_rate:.4%}")
    
    # 如果费率 > 阈值且未持仓，开空套利
    if current_rate > MIN_RATE and not in_position:
        log(f"检测到高费率机会: {current_rate:.4%}")
        log(f"开空仓位: {POSITION_SIZE}")
        
        # 做空永续合约
        order_id = sell(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
        
        if order_id:
            in_position = True
            entry_rate = current_rate
            set_position(TARGET_SYMBOL, -POSITION_SIZE)
            log(f"开仓成功，订单ID: {order_id}")
    
    # 如果费率转负或显著下降，平仓
    elif in_position and (current_rate < 0 or current_rate < entry_rate * 0.3):
        log(f"费率下降，平仓: 当前 {current_rate:.4%} vs 开仓时 {entry_rate:.4%}")
        
        # 平空仓 (买入平仓)
        order_id = buy(TARGET_SYMBOL, POSITION_SIZE, order_type='market')
        
        if order_id:
            in_position = False
            entry_rate = 0
            set_position(TARGET_SYMBOL, 0)
            log(f"平仓成功，订单ID: {order_id}")
