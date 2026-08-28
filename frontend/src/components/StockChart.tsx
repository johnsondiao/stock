import { useEffect, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { CandlestickChart, BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getStockHistory, type HistoryRecord } from '../api/client'

echarts.use([
  CandlestickChart, BarChart, LineChart,
  TitleComponent, TooltipComponent, GridComponent,
  DataZoomComponent, LegendComponent, CanvasRenderer,
])

interface Props {
  code: string
  name: string
  onClose: () => void
}

export default function StockChart({ code, name, onClose }: Props) {
  const [data, setData] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getStockHistory(code, 120)
      .then(res => setData(res.data))
      .finally(() => setLoading(false))
  }, [code])

  if (loading) {
    return (
      <div className="chart-modal" onClick={onClose}>
        <div className="chart-content" onClick={e => e.stopPropagation()}>
          <div className="loading">
            <div className="loading-spinner" />
            <p>加载 {name}({code}) 行情数据...</p>
          </div>
        </div>
      </div>
    )
  }

  const dates = data.map(d => d.date)
  const ohlc = data.map(d => [d.open, d.close, d.low, d.high])
  const volumes = data.map(d => d.volume)
  const ma5 = data.map(d => d.ma5)
  const ma20 = data.map(d => d.ma20)
  const macdBars = data.map(d => d.macd)
  const dif = data.map(d => d.dif)
  const dea = data.map(d => d.dea)

  const option: echarts.EChartsOption = {
    title: { text: `${name} (${code})`, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['MA5', 'MA20', 'DIF', 'DEA', 'MACD'], top: 30, textStyle: { fontSize: 11 } },
    grid: [
      { left: 60, right: 30, top: 70, height: '40%' },   // K线
      { left: 60, right: 30, top: '56%', height: '14%' }, // 成交量
      { left: 60, right: 30, top: '74%', height: '16%' }, // MACD
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
      { type: 'category', data: dates, gridIndex: 2 },
    ],
    yAxis: [
      { gridIndex: 0, scale: true, splitNumber: 3, axisLabel: { fontSize: 10 } },
      { gridIndex: 1, scale: true, splitNumber: 2, axisLabel: { fontSize: 10 } },
      { gridIndex: 2, scale: true, splitNumber: 2, axisLabel: { fontSize: 10 } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], start: 50, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2], bottom: 5, height: 16 },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: '#ff4757',        // 阳线填充
          color0: '#2ed573',       // 阴线填充
          borderColor: '#ff4757',
          borderColor0: '#2ed573',
        },
      },
      { name: 'MA5', type: 'line', data: ma5, xAxisIndex: 0, yAxisIndex: 0, smooth: true, lineStyle: { width: 1 }, symbol: 'none' },
      { name: 'MA20', type: 'line', data: ma20, xAxisIndex: 0, yAxisIndex: 0, smooth: true, lineStyle: { width: 1 }, symbol: 'none' },
      {
        name: '成交量',
        type: 'bar',
        data: volumes,
        xAxisIndex: 1,
        yAxisIndex: 1,
        itemStyle: { color: '#4361ee44' },
      },
      {
        name: 'MACD',
        type: 'bar',
        data: macdBars,
        xAxisIndex: 2,
        yAxisIndex: 2,
        itemStyle: {
          color: (params: any) => params.data >= 0 ? '#ff4757' : '#2ed573',
        },
      },
      { name: 'DIF', type: 'line', data: dif, xAxisIndex: 2, yAxisIndex: 2, symbol: 'none', lineStyle: { width: 1 } },
      { name: 'DEA', type: 'line', data: dea, xAxisIndex: 2, yAxisIndex: 2, symbol: 'none', lineStyle: { width: 1 } },
    ],
  }

  return (
    <div className="chart-modal" onClick={onClose}>
      <div className="chart-content" onClick={e => e.stopPropagation()}>
        <button className="chart-close" onClick={onClose}>✕</button>
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ height: 500 }}
          notMerge
        />
      </div>
    </div>
  )
}
