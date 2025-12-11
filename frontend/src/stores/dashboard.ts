import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createMockBatches, createMockActionItems, MOCK_CREDITS } from '@/mocks/dashboard-mocks'

export type BatchState = 'attention' | 'processing' | 'complete' | 'archived'

export interface DashboardBatch {
  id: string
  batchCode: string
  title: string
  className: string | null
  state: BatchState
  status: string
  statusLabel: string
  totalEssays: number
  completedEssays: number
  progressPercent: number
  progressLabel: string | null
  timeDisplay: string
  deviationCount?: number
  autoConfirmCountdown?: string
  isHighPriority: boolean
  createdAt: string
}

export interface ActionItem {
  batchId: string
  batchCode: string
  className: string
  title: string
  description: string
  deviationCount: number
  autoConfirmCountdown: string
  primaryAction: { label: string; route: string }
  secondaryAction: { label: string; route: string }
}

export const useDashboardStore = defineStore('dashboard', () => {
  // State
  const batches = ref<DashboardBatch[]>([])
  const actionItems = ref<ActionItem[]>([])
  const credits = ref<number | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdated = ref<string | null>(null)
  const animatingBatchIds = ref<Set<string>>(new Set())

  // Getters
  const attentionBatches = computed(() =>
    batches.value.filter((b) => b.state === 'attention')
  )

  const processingBatches = computed(() =>
    batches.value.filter((b) => b.state === 'processing')
  )

  const completedBatches = computed(() =>
    batches.value.filter((b) => b.state === 'complete' || b.state === 'archived')
  )

  const attentionCount = computed(() => attentionBatches.value.length)

  const ledgerBatches = computed(() => [
    ...attentionBatches.value,
    ...processingBatches.value,
    ...completedBatches.value,
  ])

  const hasActionItems = computed(() => actionItems.value.length > 0)

  // Actions
  async function fetchDashboard() {
    isLoading.value = true
    error.value = null

    try {
      // Use mock data for now - replace with actual BFF call when available
      await new Promise((resolve) => setTimeout(resolve, 300))

      batches.value = createMockBatches()
      actionItems.value = createMockActionItems()
      credits.value = MOCK_CREDITS
      lastUpdated.value = new Date().toISOString()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch dashboard'
    } finally {
      isLoading.value = false
    }
  }

  function triggerStateChangeAnimation(batchId: string) {
    animatingBatchIds.value.add(batchId)

    setTimeout(() => {
      animatingBatchIds.value.delete(batchId)
    }, 400)
  }

  function isBatchAnimating(batchId: string): boolean {
    return animatingBatchIds.value.has(batchId)
  }

  function updateBatchFromWebSocket(batchId: string, updates: Partial<DashboardBatch>) {
    const index = batches.value.findIndex((b) => b.id === batchId)
    if (index !== -1) {
      batches.value[index] = { ...batches.value[index], ...updates }
      triggerStateChangeAnimation(batchId)
    }
  }

  function clearDashboard() {
    batches.value = []
    actionItems.value = []
    credits.value = null
    error.value = null
    lastUpdated.value = null
  }

  return {
    // State
    batches,
    actionItems,
    credits,
    isLoading,
    error,
    lastUpdated,
    // Getters
    attentionBatches,
    processingBatches,
    completedBatches,
    attentionCount,
    ledgerBatches,
    hasActionItems,
    // Actions
    fetchDashboard,
    triggerStateChangeAnimation,
    isBatchAnimating,
    updateBatchFromWebSocket,
    clearDashboard,
  }
})
