import { useEffect } from 'react'
import { useScreenStore } from '../stores/screenStore'
import { StrategySelector } from '../components/screen/StrategySelector'
import { ParamForm } from '../components/screen/ParamForm'
import { PrefilterForm } from '../components/screen/PrefilterForm'
import { ProgressBar } from '../components/screen/ProgressBar'
import { ResultTable } from '../components/screen/ResultTable'

export default function Screener() {
  const { status, loadStrategies } = useScreenStore()

  useEffect(() => {
    loadStrategies()
  }, [loadStrategies])

  const isRunning = status === 'pending' || status === 'running'

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-slate-900 to-slate-800 text-white px-8 py-5 shadow-lg">
        <h1 className="text-xl font-semibold">A 股选股系统</h1>
        <p className="text-xs text-slate-400 mt-1">策略插件化 · SQLite 缓存 · 增量更新</p>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-5">
        {/* 策略选择 + 参数 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <StrategySelector />
          <ParamForm />
          <PrefilterForm />
        </div>

        {/* 进度条 */}
        {isRunning && <ProgressBar />}

        {/* 错误提示 */}
        {status === 'failed' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
            选股任务执行失败，请检查后端服务是否正常运行。
          </div>
        )}

        {/* 结果表格 */}
        {status === 'completed' && <ResultTable />}

        {/* 空状态 */}
        {status === 'idle' && (
          <div className="text-center py-20 text-gray-400">
            <div className="text-5xl mb-4">📈</div>
            <p>选择策略，配置参数，点击"开始选股"</p>
          </div>
        )}
      </main>
    </div>
  )
}
