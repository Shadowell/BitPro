import { useEffect, useRef, useMemo } from 'react';
import * as echarts from 'echarts';
import type { Kline } from '../types';
import { useSettingsStore } from '../stores/useSettingsStore';

interface KlineChartProps {
  data: Kline[];
  symbol: string;
  height?: number;
  theme?: 'dark' | 'light';
  showVolume?: boolean;
  showMA?: boolean;
  maperiods?: number[];
}

export default function KlineChart({
  data,
  symbol,
  height = 500,
  theme = 'dark',
  showVolume = true,
  showMA = true,
  maperiods = [5, 10, 20, 30],
}: KlineChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const { upColor, downColor } = useSettingsStore((s) => s.getColors());

  // 计算移动平均线
  const calculateMA = (dayCount: number, data: Kline[]) => {
    const result: (number | '-')[] = [];
    for (let i = 0; i < data.length; i++) {
      if (i < dayCount - 1) {
        result.push('-');
        continue;
      }
      let sum = 0;
      for (let j = 0; j < dayCount; j++) {
        sum += data[i - j].close;
      }
      result.push(+(sum / dayCount).toFixed(2));
    }
    return result;
  };

  // 处理数据
  const chartData = useMemo(() => {
    if (!data || data.length === 0) {
      return { dates: [], values: [], volumes: [], ma: {} };
    }

    const dates = data.map((item) =>
      new Date(item.timestamp).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    );

    // K线数据: [open, close, low, high]
    const values = data.map((item) => [
      item.open,
      item.close,
      item.low,
      item.high,
    ]);

    // 成交量
    const volumes = data.map((item, index) => ({
      value: item.volume,
      itemStyle: {
        color: data[index].close >= data[index].open ? upColor : downColor,
      },
    }));

    // 移动平均线
    const ma: Record<string, (number | '-')[]> = {};
    if (showMA) {
      maperiods.forEach((period) => {
        ma[`MA${period}`] = calculateMA(period, data);
      });
    }

    return { dates, values, volumes, ma };
  }, [data, showMA, maperiods, upColor, downColor]);

  // 配置项
  const option = useMemo(() => {

    const maColors = ['#FFD700', '#00BFFF', '#FF69B4', '#00E676'];

    // MA 系列
    const maSeries = showMA
      ? maperiods.map((period, index) => ({
          name: `MA${period}`,
          type: 'line',
          data: chartData.ma[`MA${period}`] || [],
          smooth: true,
          lineStyle: {
            width: 1,
            color: maColors[index % maColors.length],
          },
          showSymbol: false,
        }))
      : [];

    return {
      backgroundColor: theme === 'dark' ? '#161B22' : '#fff',
      animation: false,
      legend: {
        data: showMA ? maperiods.map((p) => `MA${p}`) : [],
        top: 10,
        left: 'center',
        textStyle: {
          color: theme === 'dark' ? '#8b949e' : '#333',
        },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
        },
        backgroundColor: 'rgba(22, 27, 34, 0.9)',
        borderColor: '#30363D',
        textStyle: {
          color: '#e6edf3',
        },
        formatter: (params: any) => {
          const kline = params.find((p: any) => p.seriesName === symbol);
          if (!kline) return '';

          const [open, close, low, high] = kline.data;
          const change = ((close - open) / open * 100).toFixed(2);
          const color = close >= open ? upColor : downColor;

          return `
            <div style="font-size: 12px;">
              <div style="margin-bottom: 4px;">${kline.axisValue}</div>
              <div>开: ${open.toFixed(2)}</div>
              <div>高: ${high.toFixed(2)}</div>
              <div>低: ${low.toFixed(2)}</div>
              <div>收: <span style="color:${color}">${close.toFixed(2)}</span></div>
              <div>涨跌: <span style="color:${color}">${change}%</span></div>
            </div>
          `;
        },
      },
      axisPointer: {
        link: [{ xAxisIndex: 'all' }],
        label: {
          backgroundColor: '#30363D',
        },
      },
      grid: showVolume
        ? [
            { left: 60, right: 20, top: 60, height: '55%' },
            { left: 60, right: 20, top: '72%', height: '18%' },
          ]
        : [{ left: 60, right: 20, top: 60, bottom: 50 }],
      xAxis: showVolume
        ? [
            {
              type: 'category',
              data: chartData.dates,
              gridIndex: 0,
              axisLine: { lineStyle: { color: '#30363D' } },
              axisLabel: { color: '#8b949e', fontSize: 10 },
              axisTick: { show: false },
            },
            {
              type: 'category',
              data: chartData.dates,
              gridIndex: 1,
              axisLine: { lineStyle: { color: '#30363D' } },
              axisLabel: { show: false },
              axisTick: { show: false },
            },
          ]
        : [
            {
              type: 'category',
              data: chartData.dates,
              axisLine: { lineStyle: { color: '#30363D' } },
              axisLabel: { color: '#8b949e', fontSize: 10 },
            },
          ],
      yAxis: showVolume
        ? [
            {
              scale: true,
              gridIndex: 0,
              splitLine: { lineStyle: { color: '#21262d' } },
              axisLine: { lineStyle: { color: '#30363D' } },
              axisLabel: { color: '#8b949e' },
            },
            {
              scale: true,
              gridIndex: 1,
              splitNumber: 2,
              splitLine: { show: false },
              axisLine: { show: false },
              axisLabel: { show: false },
            },
          ]
        : [
            {
              scale: true,
              splitLine: { lineStyle: { color: '#21262d' } },
              axisLine: { lineStyle: { color: '#30363D' } },
              axisLabel: { color: '#8b949e' },
            },
          ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: showVolume ? [0, 1] : [0],
          start: 50,
          end: 100,
        },
        {
          show: true,
          xAxisIndex: showVolume ? [0, 1] : [0],
          type: 'slider',
          bottom: 10,
          start: 50,
          end: 100,
          height: 20,
          borderColor: '#30363D',
          backgroundColor: '#161B22',
          fillerColor: 'rgba(88, 166, 255, 0.2)',
          handleStyle: {
            color: '#58a6ff',
          },
          textStyle: {
            color: '#8b949e',
          },
        },
      ],
      series: [
        {
          name: symbol,
          type: 'candlestick',
          data: chartData.values,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: upColor,
            color0: downColor,
            borderColor: upColor,
            borderColor0: downColor,
          },
        },
        ...maSeries,
        ...(showVolume
          ? [
              {
                name: '成交量',
                type: 'bar',
                data: chartData.volumes,
                xAxisIndex: 1,
                yAxisIndex: 1,
              },
            ]
          : []),
      ],
    };
  }, [chartData, symbol, theme, showVolume, showMA, maperiods, upColor, downColor]);

  // 初始化图表
  useEffect(() => {
    if (!chartRef.current) return;

    chartInstance.current = echarts.init(chartRef.current, theme);
    chartInstance.current.setOption(option);

    const handleResize = () => {
      chartInstance.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chartInstance.current?.dispose();
    };
  }, []);

  // 更新数据
  useEffect(() => {
    if (chartInstance.current) {
      chartInstance.current.setOption(option);
    }
  }, [option]);

  return (
    <div
      ref={chartRef}
      style={{ width: '100%', height }}
      className="kline-chart"
    />
  );
}
