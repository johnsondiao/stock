import type { MAResult } from '../api/client'

interface Props {
  data: MAResult[]
  message: string
  onViewChart: (code: string, name: string) => void
}

export default function MAResultTable({ data, message, onViewChart }: Props) {
  if (data.length === 0) {
    return (
      <div className="result-panel">
        <div className="empty-state">
          <div className="icon">📈</div>
          <p>{message || '点击「MA 均线策略选股」开始筛选'}</p>
        </div>
      </div>
    )
  }

  const fmtPct = (v: number) => {
    const sign = v >= 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }

  const fmtVol = (v: number) => {
    if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
    if (v >= 1e4) return (v / 1e4).toFixed(1) + '万'
    return v.toFixed(0)
  }

  return (
    <div className="result-panel">
      <div className="result-header">
        <h2>MA 均线策略结果</h2>
        <span className="result-count">{message}</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="stock-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>最新价</th>
              <th>涨跌幅</th>
              <th>成交量</th>
              <th>站上均线</th>
              <th>开仓信号</th>
              <th>多头排列</th>
              <th style={{ color: '#ff6b6b' }}>MA12</th>
              <th style={{ color: '#ffa502' }}>MA60</th>
              <th style={{ color: '#4361ee' }}>MA144</th>
              <th style={{ color: '#2ed573' }}>MA169</th>
              <th>偏离详情</th>
            </tr>
          </thead>
          <tbody>
            {data.map(stock => (
              <tr key={stock.code}>
                <td>
                  <span className="code" onClick={() => onViewChart(stock.code, stock.name)}>
                    {stock.code}
                  </span>
                </td>
                <td>{stock.name}</td>
                <td>{stock.price?.toFixed(2)}</td>
                <td className={stock.pct_change >= 0 ? 'up' : 'down'}>
                  {fmtPct(stock.pct_change)}
                </td>
                <td>{fmtVol(stock.volume)}</td>
                <td>
                  <span style={{
                    fontWeight: 700,
                    color: stock.above_count === 4 ? '#ff4757' : stock.above_count === 3 ? '#ffa502' : '#666',
                  }}>
                    {stock.above_count}/{stock.total_ma}
                  </span>
                </td>
                <td>
                  {stock.open_signal ? (
                    <span style={{
                      background: '#ff4757',
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                    }}>开仓</span>
                  ) : (
                    <span style={{ color: '#aaa' }}>—</span>
                  )}
                </td>
                <td>
                  {stock.ma_aligned ? (
                    <span style={{
                      background: '#2ed573',
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                    }}>多头</span>
                  ) : (
                    <span style={{ color: '#aaa' }}>—</span>
                  )}
                </td>
                <td>{stock.ma12?.toFixed(2)}</td>
                <td>{stock.ma60?.toFixed(2)}</td>
                <td>{stock.ma144?.toFixed(2)}</td>
                <td>{stock.ma169?.toFixed(2)}</td>
                <td>
                  <div style={{ fontSize: 11, lineHeight: 1.4 }}>
                    {stock.ma_details?.map(d => (
                      <div key={d.period}>
                        <span style={{ color: d.price_above ? '#ff4757' : '#2ed573' }}>
                          MA{d.period}: {d.price_above ? '▲' : '▼'}
                        </span>
                        {d.deviation != null && (
                          <span style={{ color: '#888', marginLeft: 4 }}>
                            {d.deviation >= 0 ? '+' : ''}{d.deviation}%
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
