<script setup lang="ts">
/**
 * LedgerRow - Table row with state variants
 *
 * States: attention, processing, complete, archived
 * Uses the ledger-row hover pattern from main.css
 */
import { computed } from 'vue'
import type { DashboardBatch } from '@/stores/dashboard'
import ProgressBar from '@/components/ui/ProgressBar.vue'
import PulsingDot from '@/components/ui/PulsingDot.vue'

interface Props {
  batch: DashboardBatch
  isAnimating?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isAnimating: false,
})

const emit = defineEmits<{
  (e: 'click', batch: DashboardBatch): void
}>()

// Compute the display title with optional class name
const displayTitle = computed(() => {
  if (props.batch.className) {
    return props.batch.className + ' \u00B7 ' + props.batch.title
  }
  return props.batch.title
})

// Compute the subtitle based on state
const subtitle = computed(() => {
  if (props.batch.state === 'attention' && props.batch.deviationCount) {
    return props.batch.deviationCount + ' avvikelser kraver atgard'
  }
  const suffix = props.batch.progressLabel ? ' \u00B7 ' + props.batch.progressLabel : ''
  return props.batch.totalEssays + ' texter' + suffix
})

// Get row classes based on state
const rowClasses = computed(() => {
  const base = 'grid grid-cols-12 ledger-row cursor-pointer bg-white'
  const batch = props.batch

  switch (batch.state) {
    case 'attention':
      return base + ' border-b-2 border-burgundy bg-burgundy/[0.02]'
    case 'processing':
      return base + ' border-b border-navy'
    default:
      return base + ' border-b border-navy'
  }
})

// Processing state left border color
const processingBorderClass = computed(() => {
  if (props.batch.state !== 'processing') return ''
  return props.batch.isHighPriority ? 'border-l-4 border-l-burgundy' : 'border-l-4 border-l-navy'
})

// Get status label color
const statusColor = computed(() => {
  const batch = props.batch
  switch (batch.state) {
    case 'attention':
      return 'text-burgundy font-bold'
    case 'processing':
      return batch.isHighPriority ? 'text-burgundy' : 'text-navy/60'
    case 'complete':
      return 'text-navy/40'
    case 'archived':
      return 'text-navy/30'
    default:
      return 'text-navy/40'
  }
})

// Get title opacity based on state
const titleOpacity = computed(() => {
  switch (props.batch.state) {
    case 'complete':
      return 'text-navy/70'
    case 'archived':
      return 'text-navy/60'
    default:
      return 'text-navy'
  }
})

// Get subtitle color
const subtitleColor = computed(() => {
  if (props.batch.state === 'attention') {
    return 'text-burgundy'
  }
  switch (props.batch.state) {
    case 'archived':
      return 'text-navy/30'
    case 'complete':
      return 'text-navy/40'
    default:
      return 'text-navy/50'
  }
})

// Get progress message for complete/archived states
const progressMessage = computed(() => {
  if (props.batch.progressLabel) {
    return props.batch.progressLabel
  }
  return 'Redo for export'
})

// Progress bar variant
const progressVariant = computed(() => {
  return props.batch.isHighPriority ? 'burgundy' : 'navy'
})

// Pulsing dot variant
const dotVariant = computed(() => {
  return props.batch.isHighPriority ? 'burgundy' : 'navy'
})
</script>

<template>
  <div
    :class="rowClasses"
    :data-state="batch.state"
    :data-state-changed="isAnimating ? '' : undefined"
    @click="emit('click', batch)"
  >
    <!-- Column 1: Title (5 cols) -->
    <div class="col-span-5 p-4 border-r border-navy flex flex-col justify-center" :class="processingBorderClass">
      <span class="ledger-title font-bold text-sm" :class="titleOpacity">
        {{ displayTitle }}
      </span>
      <span class="text-xs font-mono mt-1" :class="subtitleColor">
        {{ subtitle }}
      </span>
    </div>

    <!-- Column 2: Status (2 cols) -->
    <div class="col-span-2 p-4 border-r border-navy flex items-center">
      <span class="font-mono text-xs uppercase tracking-wide" :class="statusColor">
        {{ batch.statusLabel }}
      </span>
    </div>

    <!-- Column 3: Progress/Message (4 cols) -->
    <div class="col-span-4 p-4 border-r border-navy flex flex-col justify-center gap-2">
      <template v-if="batch.state === 'processing'">
        <ProgressBar :percent="batch.progressPercent" :variant="progressVariant" />
        <span class="text-[10px] font-mono text-navy/40 uppercase">
          {{ batch.progressLabel }}
        </span>
      </template>
      <template v-else-if="batch.state === 'attention'">
        <span class="text-xs text-burgundy">Hantera innan autobekraftelse &#8594;</span>
      </template>
      <template v-else-if="batch.state === 'complete'">
        <span class="text-xs text-navy/50">{{ progressMessage }} &#8594;</span>
      </template>
      <template v-else>
        <span class="text-xs text-navy/30">&#8212;</span>
      </template>
    </div>

    <!-- Column 4: Time/Indicator (1 col) -->
    <div class="col-span-1 p-4 flex items-center justify-end">
      <template v-if="batch.state === 'processing'">
        <PulsingDot :variant="dotVariant" />
      </template>
      <template v-else-if="batch.state === 'attention'">
        <span class="font-mono text-sm font-bold text-burgundy">{{ batch.timeDisplay }}</span>
      </template>
      <template v-else>
        <span
          class="font-mono text-xs"
          :class="batch.state === 'archived' ? 'text-navy/30' : 'text-navy/40'"
        >
          {{ batch.timeDisplay }}
        </span>
      </template>
    </div>
  </div>
</template>
