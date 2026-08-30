import { useState, useMemo } from 'react'
import { useScreenStore } from '../../stores/screenStore'
import type { ScreenResult } from '../../api/client'

const PAGE_SIZE = 50

export function ResultTable() {
  const { result } = useScreenStore()
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState<string>('score')
  const [sortAsc, setSortAsc] = useState(false)

  if (!result) return null

  const { results, total_scanned, matched_count, errors, completed_at } = result

  // 排序
  const sorted = useMemo(() => {
    const arr = [...results]
    arr.sort((a, b) => {
      const va = (a as Record<string, unknown>)[sortKey] ?? 0
      const vb = (b as Record<string, unknown>)[sortKey] ?? 0
      if (typeof va === 'number' && typeof vb === 'number') {
        return sortAsc ? va - vb : vb - va
      }
      return 0
    })
    return arr
  }, [results, sortKey, sortAsc])

  // 分页
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const pageData = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc)
    } else {
      setSortKey(key)
      setSortAsc(false)
    }
  }

  const ThCell = ({ label, sortKey: sk }: { label: string; sortKey: string }) => (
    <th
      className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 cursor-pointer hover:text-gray-800 select-none"
      onClick={() => toggleSort(sk)}
    >
      {label}
      {sortKey === sk && (sortAsc ? ' ↑' : ' ↓')}
    </th>
  )

  const signalColor = (signal: string) => {
    if (signal.includes('strong_buy')) return 'text-red-600 font-bold'
    if (signal.includes('buy')) return 'text-red-500'
    if (signal.includes('sell')) return 'text-green-600'
    return 'text-gray-500'
  }

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      {/* 摘要 */}
      <div className="flex flex-wrap items-center justify-between mb-4 gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">选股结果</h2>
          <p className="text-xs text-gray-400 mt-1">
            扫描 {total_scanned} 只 → 匹配 {matched_count} 只
            {errors > 0 && ` · 错误 ${errors}`}
            {` · ${completed_at}`}
          </p>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-2 text-sm">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 rounded border text-gray-600 disabled:opacity-40"
            >
              上一页
            </button>
            <span className="text-gray-500">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 rounded border text-gray-600 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* 表格 */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500">代码</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500">名称</th>
              <ThCell label="价格" sortKey="price" />
              <ThCell label="涨跌%" sortKey="pct_change" />
              <ThCell label="评分" sortKey="score" />
              <ThCell label="信号" sortKey="signal" />
              <ThCell label="60分金叉" sortKey="hourly_cross_bars_ago" />
              <ThCell label="5分金叉" sortKey="min_cross_bars_ago" />
            </tr>
          </thead>
          <tbody>
            {pageData.map((s: ScreenResult) => (
              <tr key={s.code} className="border-b border-gray-50 hover:bg-blue-50/30">
                <td className="px-3 py-2.5 text-sm text-blue-600 font-medium">{s.code}</td>
                <td className="px-3 py-2.5 text-sm text-gray-800">{s.name}</td>
                <td className="px-3 py-2.5 text-sm">{s.price?.toFixed(2)}</td>
                <td className={`px-3 py-2.5 text-sm ${s.pct_change >= 0 ? 'text-red-500' : 'text-green-600'}`}>
                  {s.pct_change?.toFixed(2)}%
                </td>
                <td className="px-3 py-2.5 text-sm font-semibold">{s.score}</td>
                <td className={`px-3 py-2.5 text-sm ${signalColor(s.signal)}`}>
                  {s.signal}
                </td>
                <td className="px-3 py-2.5 text-sm">
                  {s.hourly_cross_bars_ago != null && (
                    <span className={s.hourly_fresh ? 'text-orange-500 font-semibold' : 'text-gray-500'}>
                      {s.hourly_cross_bars_ago}根前
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-sm">
                  {s.min_cross_bars_ago != null && (
                    <span className={s.min_fresh ? 'text-orange-500 font-semibold' : 'text-gray-500'}>
                      {s.min_cross_bars_ago}根前
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {results.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <div className="text-3xl mb-2">🔍</div>
          <p>未找到符合条件的股票</p>
        </div>
      )}
    </div>
  )
}
