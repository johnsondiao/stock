import { create } from 'zustand'
import {
  fetchStrategies, startScreen,
  type StrategyInfo, type ScreenResultData, type PrefilterParams,
} from '../api/client'

interface ScreenState {
  // 策略
  strategies: StrategyInfo[]
  selectedStrategy: string
  params: Record<string, unknown>
  prefilter: PrefilterParams

  // 执行状态（同步: 点击后等待结果直接返回）
  status: 'idle' | 'running' | 'completed' | 'failed'
  errorMsg: string | null

  // 结果
  result: ScreenResultData | null

  // 操作
  loadStrategies: () => Promise<void>
  setSelectedStrategy: (name: string) => void
  setParam: (key: string, value: unknown) => void
  setPrefilter: (prefilter: PrefilterParams) => void
  runScreen: () => Promise<void>
  reset: () => void
}

export const useScreenStore = create<ScreenState>((set, get) => ({
  // 初始状态
  strategies: [],
  selectedStrategy: '',
  params: {},
  prefilter: { exclude_st: true },

  status: 'idle',
  errorMsg: null,

  result: null,

  // 加载策略列表
  loadStrategies: async () => {
    try {
      const strategies = await fetchStrategies()
      const selected = strategies.length > 0 ? strategies[0].name : ''
      // 用默认参数初始化
      const params: Record<string, unknown> = {}
      const first = strategies[0]
      if (first) {
        for (const [key, schema] of Object.entries(first.params_schema)) {
          params[key] = schema.default
        }
      }
      set({ strategies, selectedStrategy: selected, params })
    } catch (err) {
      console.error('加载策略列表失败:', err)
    }
  },

  // 切换策略
  setSelectedStrategy: (name) => {
    const { strategies } = get()
    const strategy = strategies.find(s => s.name === name)
    const params: Record<string, unknown> = {}
    if (strategy) {
      for (const [key, schema] of Object.entries(strategy.params_schema)) {
        params[key] = schema.default
      }
    }
    set({ selectedStrategy: name, params, result: null, status: 'idle' })
  },

  // 修改参数
  setParam: (key, value) => {
    set(state => ({ params: { ...state.params, [key]: value } }))
  },

  // 修改预筛条件
  setPrefilter: (prefilter) => {
    set({ prefilter })
  },

  // 同步执行选股: 数据由后台更新服务保持新鲜，这里只读缓存快速返回
  runScreen: async () => {
    const { selectedStrategy, params, prefilter } = get()
    if (!selectedStrategy) return

    try {
      set({ status: 'running', result: null, errorMsg: null })
      const result = await startScreen({
        strategy: selectedStrategy,
        params,
        prefilter,
      })
      set({ result, status: 'completed' })
    } catch (err) {
      console.error('选股失败:', err)
      const msg = err instanceof Error ? err.message : '未知错误'
      set({ status: 'failed', errorMsg: msg })
    }
  },

  // 重置
  reset: () => {
    set({ status: 'idle', result: null, errorMsg: null })
  },
}))
