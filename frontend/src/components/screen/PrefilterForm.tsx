import { useScreenStore } from '../../stores/screenStore'

export function PrefilterForm() {
  const { prefilter, setPrefilter, runScreen, status } = useScreenStore()
  const isRunning = status === 'running'

  const update = (key: string, value: unknown) => {
    setPrefilter({ ...prefilter, [key]: value })
  }

  return (
    <div className="border-t border-gray-100 pt-5">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">最低价</label>
          <input
            type="number"
            value={prefilter.min_price ?? ''}
            placeholder="不限"
            onChange={e => update('min_price', e.target.value ? Number(e.target.value) : undefined)}
            className="w-28 px-3 py-2 border border-gray-300 rounded-lg text-sm
                       focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">最高价</label>
          <input
            type="number"
            value={prefilter.max_price ?? ''}
            placeholder="不限"
            onChange={e => update('max_price', e.target.value ? Number(e.target.value) : undefined)}
            className="w-28 px-3 py-2 border border-gray-300 rounded-lg text-sm
                       focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">最小市值(万)</label>
          <input
            type="number"
            value={prefilter.min_market_cap ?? ''}
            placeholder="不限"
            onChange={e => update('min_market_cap', e.target.value ? Number(e.target.value) : undefined)}
            className="w-32 px-3 py-2 border border-gray-300 rounded-lg text-sm
                       focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>
        <label className="flex items-center gap-2 cursor-pointer pb-2">
          <input
            type="checkbox"
            checked={prefilter.exclude_st ?? true}
            onChange={e => update('exclude_st', e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-sm text-gray-600">排除 ST</span>
        </label>

        <button
          onClick={runScreen}
          disabled={isRunning}
          className={`px-6 py-2.5 rounded-lg text-sm font-semibold transition-all ${
            isRunning
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm hover:shadow'
          }`}
        >
          {isRunning ? '选股中...' : '开始选股'}
        </button>
      </div>
    </div>
  )
}
