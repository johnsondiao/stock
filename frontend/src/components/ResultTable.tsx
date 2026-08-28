import type { StockResult } from '../api/client'

interface Props {
  data: StockResult[]
  message: string
  onViewChart: (code: string, name: string) => void
}

export default function ResultTable({ data, message, onViewChart }: Props) {
  if (data.length === 0) {
    return (
      <div className="result-panel">
        <div className="empty-state">
          <div className="icon">📋</div>
          <p>{message || '设置筛选条件后点击「开始选股」'}</p>
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
        <h2>筛选结果</h2>
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
              <th>MACD(DIF/DEA)</th>
              <th>RSI(14)</th>
              <th>KDJ(K/D/J)</th>
              <th>MA5</th>
              <th>MA20</th>
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
                  <span className={stock.macd_dif! >= 0 ? 'up' : 'down'}>
                    {stock.macd_dif?.toFixed(3)}
                  </span>
                  {' / '}
                  <span className={stock.macd_dea! >= 0 ? 'up' : 'down'}>
                    {stock.macd_dea?.toFixed(3)}
                  </span>
                </td>
                <td className={stock.rsi! >= 50 ? 'up' : 'down'}>
                  {stock.rsi?.toFixed(1)}
                </td>
                <td>
                  {stock.k?.toFixed(1)} / {stock.d?.toFixed(1)} / {stock.j?.toFixed(1)}
                </td>
                <td>{stock.ma5?.toFixed(2)}</td>
                <td>{stock.ma20?.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
