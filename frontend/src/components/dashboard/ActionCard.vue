<script setup lang="ts">
/**
 * ActionCard - Primary action card with countdown timer
 *
 * Used in the "Kraver atgard" section for items requiring teacher attention.
 * Matches the prototype primary action card layout.
 */
import type { ActionItem } from '@/stores/dashboard'
import { useRouter } from 'vue-router'
import PulsingDot from '@/components/ui/PulsingDot.vue'

interface Props {
  item: ActionItem
}

const props = defineProps<Props>()
const router = useRouter()

function handlePrimaryAction() {
  router.push(props.item.primaryAction.route)
}

function handleSecondaryAction() {
  router.push(props.item.secondaryAction.route)
}
</script>

<template>
  <div class="bg-white border-2 border-navy shadow-brutal flex flex-col md:flex-row">
    <!-- Main content -->
    <div class="p-8 flex-1">
      <div class="flex items-center justify-between mb-4">
        <span class="text-xs font-mono text-navy/40 uppercase tracking-wide">
          Elevmatchning #{{ item.batchCode }}
        </span>
        <PulsingDot variant="burgundy" />
      </div>

      <h3 class="font-serif font-bold text-3xl mb-2 text-navy">
        {{ item.className }} &middot; {{ item.title }}
      </h3>
      <p class="font-serif text-lg text-navy/80 leading-relaxed max-w-2xl">
        {{ item.description }}
      </p>

      <div class="mt-8 flex gap-4">
        <button
          @click="handlePrimaryAction"
          class="btn-brutal bg-burgundy text-white px-6 py-3 text-xs font-bold uppercase tracking-widest hover:bg-navy shadow-brutal-sm transition-all duration-75"
        >
          {{ item.primaryAction.label }}
        </button>
        <button
          @click="handleSecondaryAction"
          class="border border-navy text-navy px-6 py-3 text-xs font-bold uppercase tracking-widest hover:bg-navy hover:text-white transition-colors"
        >
          {{ item.secondaryAction.label }}
        </button>
      </div>
    </div>

    <!-- Countdown sidebar -->
    <div
      class="border-t md:border-t-0 md:border-l border-navy bg-canvas p-8 md:w-64 flex flex-col justify-center items-center text-center"
    >
      <span class="text-[10px] font-bold text-navy/50 uppercase tracking-widest mb-2">
        Autobekräftas om
      </span>
      <span class="font-mono text-3xl font-bold text-burgundy tracking-tight">
        {{ item.autoConfirmCountdown }}
      </span>
      <span class="text-xs text-navy/40 font-mono mt-1">timmar</span>
    </div>
  </div>
</template>
