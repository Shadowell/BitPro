import { useState, useRef, useEffect } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  TrendingUp,
  ArrowLeftRight,
  Code2,
  FlaskConical,
  Bell,
  Settings,
  Bitcoin,
  Radio,
  Database,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { useSettingsStore, type ColorScheme } from '../stores/useSettingsStore';

const navItems = [
  { path: '/', icon: LayoutDashboard, label: '首页' },
  { path: '/market', icon: TrendingUp, label: '行情' },
  { path: '/trading', icon: ArrowLeftRight, label: '交易' },
  { path: '/strategy', icon: Code2, label: '策略' },
  { path: '/backtest', icon: FlaskConical, label: '回测' },
  { path: '/live', icon: Radio, label: '模拟/实盘' },
  { path: '/monitor', icon: Bell, label: '监控' },
  { path: '/data', icon: Database, label: '数据' },
];

/** 颜色方案预览卡片 */
function ColorSchemeCard({
  label,
  scheme,
  selected,
  onSelect,
}: {
  label: string;
  scheme: ColorScheme;
  selected: boolean;
  onSelect: () => void;
}) {
  const isRedUp = scheme === 'redUpGreenDown';
  const upColor = isRedUp ? '#FF1744' : '#00C853';
  const downColor = isRedUp ? '#00C853' : '#FF1744';

  return (
    <button
      onClick={onSelect}
      className={clsx(
        'flex flex-col items-center p-3 rounded-lg border-2 transition-all w-full',
        selected
          ? 'border-blue-500 bg-blue-500/10'
          : 'border-crypto-border hover:border-gray-500 bg-crypto-card'
      )}
    >
      {/* 迷你K线预览 */}
      <div className="flex items-end space-x-1 mb-2 h-10">
        {/* 涨 */}
        <div className="flex flex-col items-center">
          <div className="w-0.5 h-2" style={{ backgroundColor: upColor }} />
          <div className="w-3 h-5 rounded-sm" style={{ backgroundColor: upColor }} />
          <div className="w-0.5 h-1" style={{ backgroundColor: upColor }} />
        </div>
        {/* 跌 */}
        <div className="flex flex-col items-center">
          <div className="w-0.5 h-1" style={{ backgroundColor: downColor }} />
          <div className="w-3 h-4 rounded-sm" style={{ backgroundColor: downColor }} />
          <div className="w-0.5 h-2" style={{ backgroundColor: downColor }} />
        </div>
        {/* 涨 */}
        <div className="flex flex-col items-center">
          <div className="w-0.5 h-1.5" style={{ backgroundColor: upColor }} />
          <div className="w-3 h-6 rounded-sm" style={{ backgroundColor: upColor }} />
          <div className="w-0.5 h-1" style={{ backgroundColor: upColor }} />
        </div>
      </div>
      <span className="text-xs text-gray-300 font-medium">{label}</span>
      <div className="flex items-center space-x-2 mt-1 text-[10px]">
        <span style={{ color: upColor }}>▲ 涨</span>
        <span style={{ color: downColor }}>▼ 跌</span>
      </div>
    </button>
  );
}

export default function MainLayout() {
  const { colorScheme, setColorScheme } = useSettingsStore();
  const [showSettings, setShowSettings] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭设置面板
  useEffect(() => {
    if (!showSettings) return;
    const handleClick = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setShowSettings(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showSettings]);

  return (
    <div className="flex h-screen bg-crypto-bg">
      {/* 侧边栏 */}
      <aside className="w-16 shrink-0 bg-crypto-card border-r border-crypto-border flex flex-col overflow-hidden">
        {/* Logo */}
        <div className="h-16 flex items-center justify-center border-b border-crypto-border">
          <Bitcoin className="w-8 h-8 text-yellow-500" />
        </div>

        {/* 导航 */}
        <nav className="flex-1 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                clsx(
                  'flex flex-col items-center justify-center h-16 text-xs transition-colors overflow-hidden',
                  isActive
                    ? 'text-blue-500 bg-blue-500/10'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                )
              }
            >
              <item.icon className="w-5 h-5 mb-1" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* 底部: 交易所选择 + 设置 */}
        <div className="border-t border-crypto-border p-1 space-y-1">
          {/* 交易所标识 */}
          <div className="w-full flex items-center justify-center py-1.5 text-[10px] rounded bg-blue-600 text-white font-medium">
            OKX
          </div>
          <button
            onClick={() => setShowSettings(true)}
            className={clsx(
              'w-full flex flex-col items-center justify-center h-10 text-xs rounded transition-colors',
              showSettings
                ? 'text-blue-400 bg-blue-500/10'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
            )}
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>

      {/* 设置面板 */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div
            ref={settingsRef}
            className="bg-crypto-card border border-crypto-border rounded-xl shadow-2xl w-80 max-h-[80vh] overflow-y-auto"
          >
            {/* 头部 */}
            <div className="flex items-center justify-between p-4 border-b border-crypto-border">
              <h3 className="text-white font-semibold text-sm">设置</h3>
              <button
                onClick={() => setShowSettings(false)}
                className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 内容 */}
            <div className="p-4 space-y-4">
              {/* K线颜色方案 */}
              <div>
                <div className="text-xs text-gray-400 mb-3 font-medium">K线涨跌颜色</div>
                <div className="grid grid-cols-2 gap-3">
                  <ColorSchemeCard
                    label="红涨绿跌"
                    scheme="redUpGreenDown"
                    selected={colorScheme === 'redUpGreenDown'}
                    onSelect={() => setColorScheme('redUpGreenDown')}
                  />
                  <ColorSchemeCard
                    label="绿涨红跌"
                    scheme="greenUpRedDown"
                    selected={colorScheme === 'greenUpRedDown'}
                    onSelect={() => setColorScheme('greenUpRedDown')}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
