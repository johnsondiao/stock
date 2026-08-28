import { useScreenStore } from '../../stores/screenStore'

export function StrategySelector() {
  const { strategies, selectedStrategy, setSelectedStrategy } = useScreenStore()

  return (
    <div className="mb-5">
      <label className="block text-sm font-medium text-gray-700 mb-2">选股策略</label>
      <div className="flex flex-wrap gap-3">
        {strategies.map(s => (
          <button
            key={s.name}
            onClick={() => setSelectedStrategy(s.name)}
            className={`px-4 py-3 rounded-lg border-2 text-left transition-all ${
              selectedStrategy === s.name
                ? 'border-blue-500 bg-blue-50 shadow-sm'
                : 'border-gray-200 hover:border-gray-300 bg-white'
            }`}
          >
            <div className={`text-sm font-semibold ${
              selectedStrategy === s.name ? 'text-blue-700' : 'text-gray-800'
            }`}>
              {s.name}
            </div>
            <div className="text-xs text-gray-500 mt-1 max-w-xs">{s.description}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
