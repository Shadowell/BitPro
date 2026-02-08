"""
网格交易策略
在价格区间内设置买卖网格，低买高卖

使用方法:
1. 在策略管理页面创建新策略
2. 粘贴此代码
3. 配置参数: {"price_low": 90000, "price_high": 100000, "grid_num": 10, "order_amount": 0.001}
4. 启动策略
"""

# 策略配置
PRICE_LOW = config.get('price_low', 90000)      # 网格下限
PRICE_HIGH = config.get('price_high', 100000)   # 网格上限
GRID_NUM = config.get('grid_num', 10)           # 网格数量
ORDER_AMOUNT = config.get('order_amount', 0.001) # 每格交易量
TARGET_SYMBOL = symbols[0] if symbols else 'BTC/USDT'

# 策略状态
grid_prices = []
grid_status = {}  # price -> 'buy'/'sell'/None

def on_init():
    """策略初始化"""
    global grid_prices, grid_status
    
    # 计算网格价格
    step = (PRICE_HIGH - PRICE_LOW) / GRID_NUM
    grid_prices = [round(PRICE_LOW + i * step, 2) for i in range(GRID_NUM + 1)]
    
    # 初始化网格状态
    for price in grid_prices:
        grid_status[price] = None
    
    log(f"网格交易策略初始化")
    log(f"交易对: {TARGET_SYMBOL}")
    log(f"价格区间: {PRICE_LOW} - {PRICE_HIGH}")
    log(f"网格数量: {GRID_NUM}")
    log(f"每格交易量: {ORDER_AMOUNT}")
    log(f"网格价格: {grid_prices}")

def on_tick(ticker):
    """行情更新回调"""
    symbol = ticker.get('symbol', '')
    if TARGET_SYMBOL not in symbol:
        return
    
    current_price = ticker.get('last', 0)
    
    if current_price < PRICE_LOW or current_price > PRICE_HIGH:
        # 价格超出网格范围
        return
    
    # 找到当前价格所在的网格
    for i, grid_price in enumerate(grid_prices):
        if i == 0:
            continue
        
        lower_grid = grid_prices[i - 1]
        upper_grid = grid_price
        
        # 检查当前价格是否触及网格线
        if abs(current_price - lower_grid) / lower_grid < 0.001:  # 0.1% 误差
            # 触及下方网格线，买入
            if grid_status.get(lower_grid) != 'buy':
                log(f"触及网格 {lower_grid}, 买入 {ORDER_AMOUNT}")
                order_id = buy(TARGET_SYMBOL, ORDER_AMOUNT, price=lower_grid, order_type='limit')
                if order_id:
                    grid_status[lower_grid] = 'buy'
        
        elif abs(current_price - upper_grid) / upper_grid < 0.001:
            # 触及上方网格线，卖出
            if grid_status.get(upper_grid) != 'sell':
                log(f"触及网格 {upper_grid}, 卖出 {ORDER_AMOUNT}")
                order_id = sell(TARGET_SYMBOL, ORDER_AMOUNT, price=upper_grid, order_type='limit')
                if order_id:
                    grid_status[upper_grid] = 'sell'

def on_funding(rate):
    """资金费率回调 (此策略不使用)"""
    pass
