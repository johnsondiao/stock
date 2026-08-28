import { useScreenStore } from '../../stores/screenStore'

export function ParamForm() {
  const { strategies, selectedStrategy, params, setParam } = useScreenStore()
  const strategy = strategies.find(s => s.name === selectedStrategy)
  if (!strategy) return null

  const schema = strategy.params_schema

  return (
    <div className="mb-5">
      <label className="block text-sm font-medium text-gray-700 mb-3">策略参数</label>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Object.entries(schema).map(([key, field]) => (
          <div key={key}>
            <label className="block text-xs text-gray-500 mb-1" title={field.description}>
              {field.label}
            </label>
            {field.type === 'integer' || field.type === 'number' ? (
              <input
                type="number"
                value={Number(params[key] ?? field.default)}
                min={field.min}
                max={field.max}
                onChange={e => setParam(key, Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                           focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
            ) : field.type === 'boolean' ? (
              <label className="flex items-center gap-2 mt-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(params[key] ?? field.default)}
                  onChange={e => setParam(key, e.target.checked)}
                  className="w-4 h-4"
                />
                <span className="text-sm text-gray-600">启用</span>
              </label>
            ) : (
              <input
                type="text"
                value={String(params[key] ?? field.default)}
                onChange={e => setParam(key, e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                           focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
