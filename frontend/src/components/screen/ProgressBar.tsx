import { useScreenStore } from '../../stores/screenStore'

export function ProgressBar() {
  const { progress, total, matched, errors, status } = useScreenStore()
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm font-medium text-gray-700">
            {status === 'pending' ? '启动中...' : '扫描中...'}
          </span>
        </div>
        <span className="text-sm text-gray-500">{pct}%</span>
      </div>

      {/* 进度条 */}
      <div className="w-full bg-gray-200 rounded-full h-2.5 mb-4">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* 统计 */}
      <div className="flex gap-6 text-sm">
        <div>
          <span className="text-gray-500">已处理</span>
          <span className="ml-2 font-semibold text-gray-800">{progress}</span>
          <span className="text-gray-400"> / {total}</span>
        </div>
        <div>
          <span className="text-gray-500">匹配</span>
          <span className="ml-2 font-semibold text-green-600">{matched}</span>
        </div>
        {errors > 0 && (
          <div>
            <span className="text-gray-500">错误</span>
            <span className="ml-2 font-semibold text-red-500">{errors}</span>
          </div>
        )}
      </div>
    </div>
  )
}
