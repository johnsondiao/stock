import { useState } from 'react'
import type { Condition } from '../api/client'

/** 可选的技术指标字段 */
const INDICATOR_OPTIONS = [
  { value: 'macd', label: 'MACD柱' },
  { value: 'dif', label: 'DIF (MACD)' },
  { value: 'dea', label: 'DEA (MACD)' },
  { value: 'rsi14', label: 'RSI(14)' },
  { value: 'k', label: 'KDJ - K' },
  { value: 'd', label: 'KDJ - D' },
  { value: 'j', label: 'KDJ - J' },
  { value: 'ma5', label: 'MA5' },
  { value: 'ma10', label: 'MA10' },
  { value: 'ma20', label: 'MA20' },
  { value: 'ma60', label: 'MA60' },
  { value: 'boll_upper', label: '布林上轨' },
  { value: 'boll_lower', label: '布林下轨' },
]

const OPERATOR_OPTIONS = [
  { value: 'gt', label: '>' },
  { value: 'lt', label: '<' },
  { value: 'gte', label: '>=' },
  { value: 'lte', label: '<=' },
  { value: 'between', label: '区间' },
]

/** 常用策略预设 */
const PRESETS = [
  {
    name: 'MACD金叉',
    conditions: [
      { field: 'dif', operator: 'gt', value: 0 },
      { field: 'dea', operator: 'gt', value: 0 },
      { field: 'macd', operator: 'gt', value: 0 },
    ] as Condition[],
  },
  {
    name: 'RSI超卖反弹',
    conditions: [
      { field: 'rsi14', operator: 'lt', value: 40 },
    ] as Condition[],
  },
  {
    name: 'KDJ金叉',
    conditions: [
      { field: 'k', operator: 'gt', value: 20 },
      { field: 'k', operator: 'lt', value: 80 },
      { field: 'j', operator: 'gt', value: 0 },
    ] as Condition[],
  },
  {
    name: '均线多头排列',
    conditions: [
      { field: 'ma5', operator: 'gt', value: 0 },
      { field: 'ma20', operator: 'gt', value: 0 },
    ] as Condition[],
  },
]

interface Props {
  onScreen: (params: {
    conditions: Condition[]
    min_price: number
    max_price: number
    min_volume: number
    min_market_cap: number
    exclude_st: boolean
  }) => void
  loading: boolean
}

export default function ScreenForm({ onScreen, loading }: Props) {
  const [conditions, setConditions] = useState<Condition[]>([
    { field: 'macd', operator: 'gt', value: 0 },
  ])
  const [minPrice, setMinPrice] = useState(0)
  const [maxPrice, setMaxPrice] = useState(99999)
  const [minVolume, setMinVolume] = useState(0)
  const [minMarketCap, setMinMarketCap] = useState(0)
  const [excludeSt, setExcludeSt] = useState(true)

  const addCondition = () => {
    setConditions([...conditions, { field: 'macd', operator: 'gt', value: 0 }])
  }

  const removeCondition = (index: number) => {
    setConditions(conditions.filter((_, i) => i !== index))
  }

  const updateCondition = (index: number, key: keyof Condition, value: string | number) => {
    const updated = [...conditions]
    updated[index] = { ...updated[index], [key]: value }
    setConditions(updated)
  }

  const applyPreset = (preset: Condition[]) => {
    setConditions([...preset])
  }

  const handleSubmit = () => {
    onScreen({
      conditions,
      min_price: minPrice,
      max_price: maxPrice,
      min_volume: minVolume,
      min_market_cap: minMarketCap,
      exclude_st: excludeSt,
    })
  }

  return (
    <div className="screen-panel">
      <h2>📊 技术指标选股</h2>

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

      {/* 策略预设 */}
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: '#888', lineHeight: '28px' }}>快捷策略：</span>
        {PRESETS.map(p => (
          <button key={p.name} className="btn btn-sm btn-add" onClick={() => applyPreset(p.conditions)}>
            {p.name}
          </button>
        ))}
      </div>

      {/* 条件构建器 */}
      <div className="condition-builder">
        <h3>筛选条件</h3>
        {conditions.map((cond, i) => (
          <div className="condition-row" key={i}>
            <select value={cond.field} onChange={e => updateCondition(i, 'field', e.target.value)}>
              {INDICATOR_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <select value={cond.operator} onChange={e => updateCondition(i, 'operator', e.target.value)}>
              {OPERATOR_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <input
              type="number"
              value={cond.value}
              onChange={e => updateCondition(i, 'value', Number(e.target.value))}
              placeholder="值"
            />
            {conditions.length > 1 && (
              <button className="btn btn-sm btn-danger" onClick={() => removeCondition(i)}>删除</button>
            )}
          </div>
        ))}
        <button className="btn btn-sm btn-add" onClick={addCondition} style={{ marginTop: 4 }}>
          + 添加条件
        </button>
      </div>

      {/* 提交 */}
      <button className="btn btn-primary" onClick={handleSubmit} disabled={loading} style={{ padding: '10px 32px' }}>
        {loading ? '筛选中...' : '🔍 开始选股'}
      </button>
    </div>
  )
}
