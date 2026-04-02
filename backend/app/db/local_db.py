"""
BitPro 本地数据库
SQLite 数据库操作封装

优化:
- WAL 模式: 支持并发读写，读操作不阻塞写操作
- 线程安全连接池: 使用 threading.local 避免跨线程共享连接
- 连接复用: 同一线程内复用连接，减少创建/关闭开销
"""
import sqlite3
import os
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
import platform
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalDatabase:
    """本地 SQLite 数据库 (线程安全 + WAL 模式)"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            if settings.DB_PATH:
                db_path = settings.DB_PATH
            else:
                # 默认使用项目目录内的 data，避免系统目录权限导致启动失败
                project_root = Path(__file__).resolve().parents[3]
                db_path = str(project_root / "data" / "crypto_data.db")
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._local = threading.local()  # 线程局部存储
    
    def get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接 (线程安全)
        同一线程内复用连接，不同线程使用不同连接
        """
        conn = getattr(self._local, 'connection', None)
        
        # 检测连接是否仍然有效
        if conn is not None:
            try:
                conn.execute('SELECT 1')
            except Exception:
                conn = None
                self._local.connection = None
        
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row  # 支持字典访问
            
            # 启用 WAL 模式: 允许并发读写
            conn.execute('PRAGMA journal_mode=WAL')
            # 同步模式设为 NORMAL: 在 WAL 模式下兼顾性能和安全
            conn.execute('PRAGMA synchronous=NORMAL')
            # 增大缓存: 提高查询性能 (64MB)
            conn.execute('PRAGMA cache_size=-65536')
            # 启用外键约束
            conn.execute('PRAGMA foreign_keys=ON')
            # 增加 busy_timeout 防止 "database is locked"
            conn.execute('PRAGMA busy_timeout=5000')
            
            self._local.connection = conn
            logger.debug(f"New SQLite connection created for thread {threading.current_thread().name}")
        
        return conn
    
    def close_connection(self):
        """关闭当前线程的连接 (应用关闭时调用)"""
        conn = getattr(self._local, 'connection', None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.connection = None
    
    def init_db(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # ============================================
        # K线历史数据表 (旧统一表 — 保留兼容)
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kline_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL,
                trades_count INTEGER,
                UNIQUE(exchange, symbol, timeframe, timestamp)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_kline_symbol_time 
            ON kline_history(exchange, symbol, timeframe, timestamp)
        ''')

        # ============================================
        # K线分表 — 按 timeframe 拆分，提升查询性能
        # ============================================
        for tf in ['1m', '5m', '15m', '1h', '4h', '1d']:
            table = f'kline_{tf}'
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    quote_volume REAL,
                    UNIQUE(exchange, symbol, timestamp)
                )
            ''')
            cursor.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_{table}_sym_ts
                ON {table}(exchange, symbol, timestamp)
            ''')
        
        # ============================================
        # 资金费率历史表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS funding_rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                funding_rate REAL NOT NULL,
                mark_price REAL,
                UNIQUE(exchange, symbol, timestamp)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_funding_symbol_time 
            ON funding_rate_history(exchange, symbol, timestamp)
        ''')
        
        # ============================================
        # 资金费率实时表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS funding_rate_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                current_rate REAL,
                predicted_rate REAL,
                next_funding_time INTEGER,
                mark_price REAL,
                index_price REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(exchange, symbol)
            )
        ''')
        
        # ============================================
        # 持仓量历史表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS open_interest_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open_interest REAL NOT NULL,
                open_interest_value REAL,
                UNIQUE(exchange, symbol, timestamp)
            )
        ''')
        
        # ============================================
        # 爆仓历史表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS liquidation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                value REAL NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_liq_time 
            ON liquidation_history(timestamp)
        ''')
        
        # ============================================
        # 成交历史表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                trade_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                quote_quantity REAL,
                is_maker INTEGER,
                UNIQUE(exchange, symbol, trade_id)
            )
        ''')
        
        # ============================================
        # 策略表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                script_content TEXT NOT NULL,
                config TEXT,
                status TEXT DEFAULT 'stopped',
                exchange TEXT,
                symbols TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ============================================
        # 策略交易记录表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategy_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                order_id TEXT,
                timestamp INTEGER NOT NULL,
                side TEXT NOT NULL,
                type TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                fee REAL,
                fee_asset TEXT,
                pnl REAL,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_strategy_trades_id 
            ON strategy_trades(strategy_id, timestamp)
        ''')
        
        # ============================================
        # 回测结果表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                final_capital REAL,
                total_return REAL,
                annual_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                win_rate REAL,
                profit_factor REAL,
                total_trades INTEGER,
                trades_detail TEXT,
                status TEXT DEFAULT 'running',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        ''')
        
        # ============================================
        # 告警配置表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                symbol TEXT,
                condition TEXT NOT NULL,
                notification TEXT,
                enabled INTEGER DEFAULT 1,
                last_triggered_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ============================================
        # 交易所配置表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exchange_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL UNIQUE,
                api_key TEXT,
                api_secret TEXT,
                passphrase TEXT,
                testnet INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ============================================
        # 数据同步元数据表 — 记录每个交易对的同步进度
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                data_type TEXT NOT NULL DEFAULT 'kline',
                first_timestamp INTEGER,
                last_timestamp INTEGER,
                total_records INTEGER DEFAULT 0,
                status TEXT DEFAULT 'idle',
                last_sync_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(exchange, symbol, timeframe, data_type)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sync_meta
            ON sync_metadata(exchange, symbol, timeframe, data_type)
        ''')
        
        # ============================================
        # 行情缓存表 (Ticker)
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticker_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                last REAL,
                bid REAL,
                ask REAL,
                high REAL,
                low REAL,
                volume REAL,
                quote_volume REAL,
                change REAL,
                change_percent REAL,
                timestamp INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(exchange, symbol)
            )
        ''')
        
        # ============================================
        # Agent 任务表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_tasks (
                id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                goal_criteria TEXT,
                symbol TEXT,
                timeframe TEXT,
                backtest_start TEXT,
                backtest_end TEXT,
                max_iterations INTEGER DEFAULT 10,
                current_iteration INTEGER DEFAULT 0,
                best_iteration INTEGER,
                user_prompt TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # ============================================
        # Agent 迭代记录表
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_iterations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                strategy_name TEXT,
                strategy_code TEXT,
                setup_code TEXT,
                reasoning TEXT,
                backtest_metrics TEXT,
                analysis TEXT,
                suggestions TEXT,
                score REAL DEFAULT 0,
                meets_goal INTEGER DEFAULT 0,
                error TEXT DEFAULT '',
                created_at TEXT,
                FOREIGN KEY (task_id) REFERENCES agent_tasks(id)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_agent_iter_task
            ON agent_iterations(task_id, iteration)
        ''')

        conn.commit()
        conn.close()
    
    # ============================================
    # K线分表名映射
    # ============================================
    _KLINE_SPLIT_TABLES = {'1m', '5m', '15m', '1h', '4h', '1d'}

    def _kline_table(self, timeframe: str) -> str:
        """根据 timeframe 返回分表名，不支持的周期回退到旧统一表"""
        if timeframe in self._KLINE_SPLIT_TABLES:
            return f'kline_{timeframe}'
        return 'kline_history'

    # ============================================
    # K线数据操作
    # ============================================
    
    def insert_klines(self, exchange: str, symbol: str, timeframe: str, klines: List[Dict]):
        """批量插入K线数据 — 同时写入分表和旧统一表"""
        if not klines:
            return 0
        
        conn = self.get_connection()
        cursor = conn.cursor()

        # 1. 写入旧统一表 (兼容)
        legacy_data = [
            (
                exchange, symbol, timeframe,
                kline['timestamp'], kline['open'], kline['high'],
                kline['low'], kline['close'], kline['volume'],
                kline.get('quote_volume')
            )
            for kline in klines
        ]
        cursor.executemany('''
            INSERT OR IGNORE INTO kline_history
            (exchange, symbol, timeframe, timestamp, open, high, low, close, volume, quote_volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', legacy_data)

        # 2. 写入分表 (如果该 timeframe 有对应分表)
        inserted = 0
        if timeframe in self._KLINE_SPLIT_TABLES:
            table = self._kline_table(timeframe)
            split_data = [
                (
                    exchange, symbol,
                    kline['timestamp'], kline['open'], kline['high'],
                    kline['low'], kline['close'], kline['volume'],
                    kline.get('quote_volume')
                )
                for kline in klines
            ]
            cursor.executemany(f'''
                INSERT OR IGNORE INTO {table}
                (exchange, symbol, timestamp, open, high, low, close, volume, quote_volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', split_data)
            inserted = cursor.rowcount
        else:
            inserted = cursor.rowcount

        conn.commit()
        conn.close()
        return inserted
    
    def get_klines(self, exchange: str, symbol: str, timeframe: str, 
                   limit: int = 100, start: int = None, end: int = None) -> List[Dict]:
        """获取K线数据 — 优先从分表读取，回退到旧统一表"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 优先从分表读取
        if timeframe in self._KLINE_SPLIT_TABLES:
            table = self._kline_table(timeframe)
            query = f'''
                SELECT timestamp, open, high, low, close, volume, quote_volume
                FROM {table}
                WHERE exchange = ? AND symbol = ?
            '''
            params: list = [exchange, symbol]
        else:
            query = '''
                SELECT timestamp, open, high, low, close, volume, quote_volume
                FROM kline_history
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
            '''
            params = [exchange, symbol, timeframe]
        
        if start:
            query += ' AND timestamp >= ?'
            params.append(start)
        if end:
            query += ' AND timestamp <= ?'
            params.append(end)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = [dict(row) for row in rows][::-1]  # 按时间正序

        # 如果分表为空，回退到旧统一表
        if not result and timeframe in self._KLINE_SPLIT_TABLES:
            query2 = '''
                SELECT timestamp, open, high, low, close, volume, quote_volume
                FROM kline_history
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
            '''
            params2: list = [exchange, symbol, timeframe]
            if start:
                query2 += ' AND timestamp >= ?'
                params2.append(start)
            if end:
                query2 += ' AND timestamp <= ?'
                params2.append(end)
            query2 += ' ORDER BY timestamp DESC LIMIT ?'
            params2.append(limit)
            cursor.execute(query2, params2)
            rows2 = cursor.fetchall()
            result = [dict(row) for row in rows2][::-1]

        conn.close()
        return result
    
    # ============================================
    # 资金费率操作
    # ============================================
    
    def insert_funding_rate(self, exchange: str, symbol: str, timestamp: int, 
                           rate: float, mark_price: float = None):
        """插入资金费率历史"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO funding_rate_history
            (exchange, symbol, timestamp, funding_rate, mark_price)
            VALUES (?, ?, ?, ?, ?)
        ''', (exchange, symbol, timestamp, rate, mark_price))
        
        conn.commit()
        conn.close()
    
    def get_funding_history(self, exchange: str, symbol: str, limit: int = 100) -> List[Dict]:
        """获取资金费率历史"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, funding_rate as rate, mark_price
            FROM funding_rate_history
            WHERE exchange = ? AND symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (exchange, symbol, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_funding_realtime(self, exchange: str, symbol: str, data: Dict):
        """更新资金费率实时数据"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO funding_rate_realtime
            (exchange, symbol, current_rate, predicted_rate, next_funding_time, 
             mark_price, index_price, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            exchange, symbol,
            data.get('current_rate'),
            data.get('predicted_rate'),
            data.get('next_funding_time'),
            data.get('mark_price'),
            data.get('index_price')
        ))
        
        conn.commit()
        conn.close()
    
    def get_funding_realtime(self, exchange: str, symbol: str = None) -> List[Dict]:
        """获取资金费率实时数据"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if symbol:
            cursor.execute('''
                SELECT exchange, symbol, current_rate, predicted_rate, 
                       next_funding_time, mark_price, index_price
                FROM funding_rate_realtime
                WHERE exchange = ? AND symbol = ?
            ''', (exchange, symbol))
        else:
            cursor.execute('''
                SELECT exchange, symbol, current_rate, predicted_rate, 
                       next_funding_time, mark_price, index_price
                FROM funding_rate_realtime
                WHERE exchange = ?
                ORDER BY current_rate DESC
            ''', (exchange,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ============================================
    # 策略操作
    # ============================================
    
    def save_strategy(self, name: str, script_content: str, description: str = None,
                      config: Dict = None, exchange: str = None, symbols: List[str] = None) -> int:
        """保存策略"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        config_json = json.dumps(config) if config else None
        symbols_json = json.dumps(symbols) if symbols else None
        
        cursor.execute('''
            INSERT OR REPLACE INTO strategies
            (name, description, script_content, config, exchange, symbols, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (name, description, script_content, config_json, exchange, symbols_json))
        
        strategy_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return strategy_id
    
    def get_strategies(self) -> List[Dict]:
        """获取所有策略"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, description, script_content, config, status, 
                   exchange, symbols, created_at, updated_at
            FROM strategies
            ORDER BY updated_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            item = dict(row)
            if item.get('config'):
                item['config'] = json.loads(item['config'])
            if item.get('symbols'):
                item['symbols'] = json.loads(item['symbols'])
            result.append(item)
        
        return result
    
    def get_strategy_by_id(self, strategy_id: int) -> Optional[Dict]:
        """根据ID获取策略"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, description, script_content, config, status, 
                   exchange, symbols, created_at, updated_at
            FROM strategies
            WHERE id = ?
        ''', (strategy_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        item = dict(row)
        if item.get('config'):
            item['config'] = json.loads(item['config'])
        if item.get('symbols'):
            item['symbols'] = json.loads(item['symbols'])
        
        return item
    
    def update_strategy_status(self, strategy_id: int, status: str):
        """更新策略状态"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE strategies 
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
        ''', (status, strategy_id))
        
        conn.commit()
        conn.close()
    
    def delete_strategy(self, strategy_id: int) -> bool:
        """删除策略"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 先删除相关交易记录
        cursor.execute('DELETE FROM strategy_trades WHERE strategy_id = ?', (strategy_id,))
        # 删除回测结果
        cursor.execute('DELETE FROM backtest_results WHERE strategy_id = ?', (strategy_id,))
        # 删除策略
        cursor.execute('DELETE FROM strategies WHERE id = ?', (strategy_id,))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    # ============================================
    # 策略交易记录操作
    # ============================================
    
    def insert_strategy_trade(self, strategy_id: int, trade: Dict):
        """插入策略交易记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO strategy_trades
            (strategy_id, exchange, symbol, order_id, timestamp, side, type, 
             price, quantity, fee, fee_asset, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            strategy_id, trade['exchange'], trade['symbol'], trade.get('order_id'),
            trade['timestamp'], trade['side'], trade['type'],
            trade['price'], trade['quantity'],
            trade.get('fee'), trade.get('fee_asset'), trade.get('pnl')
        ))
        
        conn.commit()
        conn.close()
    
    def get_strategy_trades(self, strategy_id: int, limit: int = 50) -> List[Dict]:
        """获取策略交易记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, strategy_id, exchange, symbol, order_id, timestamp,
                   side, type, price, quantity, fee, fee_asset, pnl
            FROM strategy_trades
            WHERE strategy_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (strategy_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ============================================
    # Ticker 缓存操作
    # ============================================
    
    def update_ticker_cache(self, exchange: str, symbol: str, ticker: Dict):
        """更新 Ticker 缓存"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO ticker_cache
            (exchange, symbol, last, bid, ask, high, low, volume, quote_volume,
             change, change_percent, timestamp, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            exchange, symbol,
            ticker.get('last'), ticker.get('bid'), ticker.get('ask'),
            ticker.get('high'), ticker.get('low'), ticker.get('volume'),
            ticker.get('quote_volume'), ticker.get('change'),
            ticker.get('change_percent'), ticker.get('timestamp')
        ))
        
        conn.commit()
        conn.close()
    
    def get_ticker_cache(self, exchange: str, symbol: str = None) -> List[Dict]:
        """获取 Ticker 缓存"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if symbol:
            cursor.execute('''
                SELECT exchange, symbol, last, bid, ask, high, low, volume, 
                       quote_volume, change, change_percent, timestamp
                FROM ticker_cache
                WHERE exchange = ? AND symbol = ?
            ''', (exchange, symbol))
        else:
            cursor.execute('''
                SELECT exchange, symbol, last, bid, ask, high, low, volume, 
                       quote_volume, change, change_percent, timestamp
                FROM ticker_cache
                WHERE exchange = ?
            ''', (exchange,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]


    # ============================================
    # 同步元数据操作
    # ============================================
    
    def get_sync_metadata(self, exchange: str, symbol: str, timeframe: str,
                          data_type: str = 'kline') -> Optional[Dict]:
        """获取同步元数据"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT exchange, symbol, timeframe, data_type,
                   first_timestamp, last_timestamp, total_records,
                   status, last_sync_at, error_message
            FROM sync_metadata
            WHERE exchange = ? AND symbol = ? AND timeframe = ? AND data_type = ?
        ''', (exchange, symbol, timeframe, data_type))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def update_sync_metadata(self, exchange: str, symbol: str, timeframe: str,
                             data_type: str = 'kline', **kwargs):
        """更新同步元数据"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 先尝试获取已有记录
        cursor.execute('''
            SELECT id FROM sync_metadata
            WHERE exchange = ? AND symbol = ? AND timeframe = ? AND data_type = ?
        ''', (exchange, symbol, timeframe, data_type))
        
        row = cursor.fetchone()
        
        if row:
            # 构建动态 UPDATE
            set_clauses = ['updated_at = datetime("now")']
            params = []
            for key in ['first_timestamp', 'last_timestamp', 'total_records',
                        'status', 'last_sync_at', 'error_message']:
                if key in kwargs:
                    set_clauses.append(f'{key} = ?')
                    params.append(kwargs[key])
            
            params.extend([exchange, symbol, timeframe, data_type])
            cursor.execute(f'''
                UPDATE sync_metadata
                SET {", ".join(set_clauses)}
                WHERE exchange = ? AND symbol = ? AND timeframe = ? AND data_type = ?
            ''', params)
        else:
            # INSERT
            cursor.execute('''
                INSERT INTO sync_metadata
                (exchange, symbol, timeframe, data_type, first_timestamp, last_timestamp,
                 total_records, status, last_sync_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                exchange, symbol, timeframe, data_type,
                kwargs.get('first_timestamp'),
                kwargs.get('last_timestamp'),
                kwargs.get('total_records', 0),
                kwargs.get('status', 'idle'),
                kwargs.get('last_sync_at'),
                kwargs.get('error_message')
            ))
        
        conn.commit()
        conn.close()
    
    def get_all_sync_metadata(self, exchange: str = None) -> List[Dict]:
        """获取所有同步元数据"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if exchange:
            cursor.execute('''
                SELECT exchange, symbol, timeframe, data_type,
                       first_timestamp, last_timestamp, total_records,
                       status, last_sync_at, error_message, updated_at
                FROM sync_metadata
                WHERE exchange = ?
                ORDER BY symbol, timeframe
            ''', (exchange,))
        else:
            cursor.execute('''
                SELECT exchange, symbol, timeframe, data_type,
                       first_timestamp, last_timestamp, total_records,
                       status, last_sync_at, error_message, updated_at
                FROM sync_metadata
                ORDER BY exchange, symbol, timeframe
            ''')
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_kline_count(self, exchange: str, symbol: str, timeframe: str) -> int:
        """获取K线数据条数 — 优先查分表"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if timeframe in self._KLINE_SPLIT_TABLES:
            table = self._kline_table(timeframe)
            cursor.execute(f'''
                SELECT COUNT(*) as cnt
                FROM {table}
                WHERE exchange = ? AND symbol = ?
            ''', (exchange, symbol))
        else:
            cursor.execute('''
                SELECT COUNT(*) as cnt
                FROM kline_history
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
            ''', (exchange, symbol, timeframe))
        
        row = cursor.fetchone()
        cnt = row['cnt'] if row else 0

        # 如果分表为 0，尝试旧统一表
        if cnt == 0 and timeframe in self._KLINE_SPLIT_TABLES:
            cursor.execute('''
                SELECT COUNT(*) as cnt
                FROM kline_history
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
            ''', (exchange, symbol, timeframe))
            row2 = cursor.fetchone()
            cnt = row2['cnt'] if row2 else 0

        conn.close()
        return cnt
    
    def get_kline_time_range(self, exchange: str, symbol: str, timeframe: str) -> Optional[Dict]:
        """获取K线数据的时间范围 — 优先查分表"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if timeframe in self._KLINE_SPLIT_TABLES:
            table = self._kline_table(timeframe)
            cursor.execute(f'''
                SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts, COUNT(*) as cnt
                FROM {table}
                WHERE exchange = ? AND symbol = ?
            ''', (exchange, symbol))
        else:
            cursor.execute('''
                SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts, COUNT(*) as cnt
                FROM kline_history
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
            ''', (exchange, symbol, timeframe))
        
        row = cursor.fetchone()

        # 如果分表没数据，回退旧表
        if (not row or row['cnt'] == 0) and timeframe in self._KLINE_SPLIT_TABLES:
            cursor.execute('''
                SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts, COUNT(*) as cnt
                FROM kline_history
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
            ''', (exchange, symbol, timeframe))
            row = cursor.fetchone()

        conn.close()
        
        if row and row['cnt'] > 0:
            return {
                'first_timestamp': row['first_ts'],
                'last_timestamp': row['last_ts'],
                'count': row['cnt']
            }
        return None

    def get_kline_table_stats(self) -> List[Dict]:
        """获取所有分表的统计信息（供前端数据管理页面使用）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        result = []

        for tf in sorted(self._KLINE_SPLIT_TABLES):
            table = self._kline_table(tf)
            try:
                cursor.execute(f'''
                    SELECT exchange, symbol,
                           COUNT(*) as record_count,
                           MIN(timestamp) as first_ts,
                           MAX(timestamp) as last_ts
                    FROM {table}
                    GROUP BY exchange, symbol
                    ORDER BY exchange, symbol
                ''')
                for row in cursor.fetchall():
                    result.append({
                        'table_name': table,
                        'timeframe': tf,
                        'exchange': row['exchange'],
                        'symbol': row['symbol'],
                        'record_count': row['record_count'],
                        'first_timestamp': row['first_ts'],
                        'last_timestamp': row['last_ts'],
                    })
            except Exception:
                pass

        # 旧统一表统计
        try:
            cursor.execute('''
                SELECT exchange, symbol, timeframe,
                       COUNT(*) as record_count,
                       MIN(timestamp) as first_ts,
                       MAX(timestamp) as last_ts
                FROM kline_history
                GROUP BY exchange, symbol, timeframe
                ORDER BY exchange, symbol, timeframe
            ''')
            for row in cursor.fetchall():
                result.append({
                    'table_name': 'kline_history',
                    'timeframe': row['timeframe'],
                    'exchange': row['exchange'],
                    'symbol': row['symbol'],
                    'record_count': row['record_count'],
                    'first_timestamp': row['first_ts'],
                    'last_timestamp': row['last_ts'],
                })
        except Exception:
            pass

        conn.close()
        return result

    # ============================================
    # Agent 任务持久化
    # ============================================

    def save_agent_task(self, task_data: dict):
        """保存或更新 Agent 任务"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO agent_tasks
            (id, status, goal_criteria, symbol, timeframe,
             backtest_start, backtest_end, max_iterations,
             current_iteration, best_iteration, user_prompt,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_data['id'], task_data['status'],
            json.dumps(task_data.get('goal_criteria', {})),
            task_data['symbol'], task_data['timeframe'],
            task_data['backtest_start'], task_data['backtest_end'],
            task_data.get('max_iterations', 10),
            task_data.get('current_iteration', 0),
            task_data.get('best_iteration'),
            task_data.get('user_prompt', ''),
            task_data['created_at'], task_data['updated_at'],
        ))
        conn.commit()

    def save_agent_iteration(self, task_id: str, record: dict):
        """保存一条迭代记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO agent_iterations
            (task_id, iteration, strategy_name, strategy_code, setup_code,
             reasoning, backtest_metrics, analysis, suggestions,
             score, meets_goal, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id, record['iteration'],
            record.get('strategy_name', ''),
            record.get('strategy_code', ''),
            record.get('setup_code', ''),
            record.get('reasoning', ''),
            json.dumps(record.get('backtest_metrics', {})),
            record.get('analysis', ''),
            json.dumps(record.get('suggestions', [])),
            record.get('score', 0),
            1 if record.get('meets_goal') else 0,
            record.get('error', ''),
            record.get('created_at', ''),
        ))
        conn.commit()

    def get_agent_tasks(self, limit: int = 50) -> list:
        """获取 Agent 任务列表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT ?',
            (limit,),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('goal_criteria'):
                d['goal_criteria'] = json.loads(d['goal_criteria'])
            result.append(d)
        return result

    def get_agent_task(self, task_id: str) -> Optional[dict]:
        """获取单个 Agent 任务"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM agent_tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get('goal_criteria'):
            d['goal_criteria'] = json.loads(d['goal_criteria'])
        return d

    def get_agent_iterations(self, task_id: str) -> list:
        """获取某任务的所有迭代记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM agent_iterations WHERE task_id = ? ORDER BY iteration',
            (task_id,),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('backtest_metrics'):
                d['backtest_metrics'] = json.loads(d['backtest_metrics'])
            if d.get('suggestions'):
                d['suggestions'] = json.loads(d['suggestions'])
            result.append(d)
        return result


# 全局数据库实例
db_instance = LocalDatabase()
