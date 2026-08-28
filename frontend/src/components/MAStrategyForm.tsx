import { useState } from 'react'

interface Props {
  onScreen: (params: {
    min_price: number
    max_price: number
    min_volume: number
    min_market_cap: number
    exclude_st: boolean
    min_above: number
  }) => void
  loading: boolean
}

export default function MAStrategyForm({ onScreen, loading }: Props) {
  const [minPrice, setMinPrice] = useState(0)
  const [maxPrice, setMaxPrice] = useState(99999)
  const [minVolume, setMinVolume] = useState(0)
  const [minMarketCap, setMinMarketCap] = useState(0)
  const [excludeSt, setExcludeSt] = useState(true)
  const [minAbove, setMinAbove] = useState(4)

  const handleSubmit = () => {
    onScreen({
      min_price: minPrice,
      max_price: maxPrice,
      min_volume: minVolume,
      min_market_cap: minMarketCap,
      exclude_st: excludeSt,
      min_above: minAbove,
    })
  }

  return (
    <div className="screen-panel">
      <h2>📈 MA 均线多头策略（1小时K线）</h2>

      {/* 策略说明 */}
      <div style={{
        background: '#f0f7ff',
        border: '1px solid #b3d4fc',
        borderRadius: 8,
        padding: '12px 16px',
        marginBottom: 16,
        fontSize: 13,
        color: '#1a5276',
        lineHeight: 1.6,
      }}>
        <strong>策略逻辑：</strong>使用 1 小时K线，计算 MA12 / MA60 / MA144 / MA169 四条均线。
        当股价站上指定数量的均线时，视为开仓信号。全部站上（4/4）为最强信号，同时均线多头排列（MA12 {'>'} MA60 {'>'} MA144 {'>'} MA169）更佳。
      </div>

      {/* 均线参数展示 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        {[
          { period: 12, color: '#ff6b6b', label: 'MA12 (短期)' },
          { period: 60, color: '#ffa502', label: 'MA60 (中期)' },
          { period: 144, color: '#4361ee', label: 'MA144 (中长期)' },
          { period: 169, color: '#2ed573', label: 'MA169 (长期)' },
        ].map(ma => (
          <div key={ma.period} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            background: '#f8f9fa',
            borderRadius: 6,
            border: `2px solid ${ma.color}`,
            fontSize: 13,
            fontWeight: 500,
          }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: ma.color }} />
            {ma.label}
          </div>
        ))}
      </div>

      {/* 开仓阈值 */}
      <div className="filter-row">
        <div className="filter-group">
          <label>最少站上均线数（开仓阈值）</label>
          <select value={minAbove} onChange={e => setMinAbove(Number(e.target.value))} style={{ width: 180 }}>
            <option value={1}>≥ 1 条（宽松）</option>
            <option value={2}>≥ 2 条</option>
            <option value={3}>≥ 3 条</option>
            <option value={4}>≥ 4 条（全部站上，最强信号）</option>
          </select>
        </div>
      </div>

      {/* 基础过滤 */}
      <div className="filter-row">
        <div className="filter-group">
          <label>最低股价 (元)</label>
          <input type="number" value={minPrice} onChange={e => setMinPrice(Number(e.target.value))} />
        </div>
        <div className="filter-group">
          <label>最高股价 (元)</label>
          <input type="number" value={maxPrice} onChange={e => setMaxPrice(Number(e.target.value))} />
        </div>
        <div className="filter-group">
          <label>最小成交量 (手)</label>
          <input type="number" value={minVolume} onChange={e => setMinVolume(Number(e.target.value))} />
        </div>
        <div className="filter-group">
          <label>最小市值 (亿)</label>
          <input type="number" value={minMarketCap} onChange={e => setMinMarketCap(Number(e.target.value))} />
        </div>
        <label className="checkbox-label">
          <input type="checkbox" checked={excludeSt} onChange={e => setExcludeSt(e.target.checked)} />
          排除 ST
        </label>
      </div>

      {/* 提交 */}
      <button className="btn btn-primary" onClick={handleSubmit} disabled={loading} style={{ padding: '10px 32px' }}>
        {loading ? '筛选中...' : '📈 MA 均线策略选股'}
      </button>
    </div>
  )
}
