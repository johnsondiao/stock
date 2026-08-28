import { create } from 'zustand'
import {
  fetchStrategies, startScreen, fetchTaskStatus, fetchTaskResult,
  type StrategyInfo, type ScreenResultData, type PrefilterParams,
} from '../api/client'

interface ScreenState {
  // 策略
  strategies: StrategyInfo[]
  selectedStrategy: string
  params: Record<string, unknown>
  prefilter: PrefilterParams

  // 任务
  taskId: string | null
  status: 'idle' | 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  total: number
  matched: number
  errors: number

  // 结果
  result: ScreenResultData | null

  // 操作
  loadStrategies: () => Promise<void>
  setSelectedStrategy: (name: string) => void
  setParam: (key: string, value: unknown) => void
  setPrefilter: (prefilter: PrefilterParams) => void
  runScreen: () => Promise<void>
  pollProgress: () => void
  reset: () => void
}

export const useScreenStore = create<ScreenState>((set, get) => ({
  // 初始状态
  strategies: [],
  selectedStrategy: '',
  params: {},
  prefilter: { exclude_st: true },

  taskId: null,
  status: 'idle',
  progress: 0,
  total: 0,
  matched: 0,
  errors: 0,

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

  // 启动选股
  runScreen: async () => {
    const { selectedStrategy, params, prefilter } = get()
    if (!selectedStrategy) return

    try {
      set({ status: 'pending', progress: 0, total: 0, matched: 0, errors: 0, result: null })
      const { task_id } = await startScreen({
        strategy: selectedStrategy,
        params,
        prefilter,
      })
      set({ taskId: task_id, status: 'running' })

      // 开始轮询进度
      get().pollProgress()
    } catch (err) {
      console.error('启动选股失败:', err)
      set({ status: 'failed' })
    }
  },

  // 轮询进度
  pollProgress: () => {
    const { taskId, status } = get()
    if (!taskId || status !== 'running') return

    const poll = async () => {
      try {
        const task = await fetchTaskStatus(taskId!)
        set({
          progress: task.progress,
          total: task.total,
          matched: task.matched,
          errors: task.errors,
        })

        if (task.status === 'completed') {
          // 获取结果
          const result = await fetchTaskResult(taskId!)
          set({ result, status: 'completed' })
        } else if (task.status === 'failed') {
          set({ status: 'failed' })
        } else {
          // 继续轮询
          setTimeout(poll, 2000)
        }
      } catch (err) {
        console.error('轮询进度失败:', err)
        setTimeout(poll, 5000)
      }
    }

    setTimeout(poll, 1000)
  },

  // 重置
  reset: () => {
    set({
      taskId: null, status: 'idle', progress: 0, total: 0,
      matched: 0, errors: 0, result: null,
    })
  },
}))
