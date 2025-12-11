<script setup lang="ts">
/**
 * TeacherDashboardView - Main dashboard view
 *
 * Displays:
 * 1. Action items requiring attention (ActionCard)
 * 2. Ledger of all batches (LedgerTable + LedgerRow)
 *
 * Uses the dashboard store for state management.
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import type { DashboardBatch } from '@/stores/dashboard'
import SectionHeader from '@/components/dashboard/SectionHeader.vue'
import ActionCard from '@/components/dashboard/ActionCard.vue'
import LedgerTable from '@/components/dashboard/LedgerTable.vue'
import LedgerRow from '@/components/dashboard/LedgerRow.vue'

const dashboardStore = useDashboardStore()
const router = useRouter()

onMounted(() => {
  dashboardStore.fetchDashboard()
})

function handleBatchClick(batch: DashboardBatch) {
  router.push(`/app/batch/${batch.id}`)
}
</script>

<template>
  <div>
    <!-- Loading state -->
    <div v-if="dashboardStore.isLoading" class="p-10">
      <div class="flex items-center gap-3">
        <div class="h-2 w-2 rounded-full bg-navy animate-pulse"></div>
        <span class="text-xs font-bold uppercase tracking-widest text-navy/60">
          Laddar dashboard...
        </span>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="dashboardStore.error" class="p-10">
      <div class="bg-white border-2 border-burgundy p-6">
        <h2 class="font-bold text-burgundy mb-2">Fel vid inlasning</h2>
        <p class="text-navy/80 mb-4">{{ dashboardStore.error }}</p>
        <button
          @click="dashboardStore.fetchDashboard"
          class="border border-navy text-navy px-4 py-2 text-xs font-bold uppercase tracking-widest hover:bg-navy hover:text-white transition-colors"
        >
          Forsok igen
        </button>
      </div>
    </div>

    <!-- Dashboard content -->
    <template v-else>
      <!-- Section: Kraver atgard -->
      <div v-if="dashboardStore.hasActionItems" class="p-10 pb-6 max-w-6xl">
        <SectionHeader
          :title="'Kraver atgard'"
          :count="dashboardStore.attentionCount"
          variant="burgundy"
        />

        <ActionCard
          v-for="item in dashboardStore.actionItems"
          :key="item.batchId"
          :item="item"
        />
      </div>

      <!-- Section: Pagaende och Arkiverat -->
      <div class="p-10 pt-4 max-w-6xl">
        <SectionHeader
          title="Pagaende och Arkiverat"
          variant="navy"
          :show-border="true"
        />

        <LedgerTable>
          <LedgerRow
            v-for="batch in dashboardStore.ledgerBatches"
            :key="batch.id"
            :batch="batch"
            :is-animating="dashboardStore.isBatchAnimating(batch.id)"
            @click="handleBatchClick"
          />
        </LedgerTable>
      </div>

      <!-- Empty state -->
      <div
        v-if="!dashboardStore.hasActionItems && dashboardStore.ledgerBatches.length === 0"
        class="p-10 max-w-6xl"
      >
        <div class="bg-white border-2 border-navy p-8 text-center">
          <h2 class="font-bold text-navy mb-2">Inga inlamningar</h2>
          <p class="text-navy/60 mb-6">
            Du har inga batchar annu. Skapa en ny bunt for att komma igang.
          </p>
          <button
            class="btn-brutal bg-navy text-white px-6 py-3 text-xs font-bold uppercase tracking-widest hover:bg-burgundy shadow-brutal transition-all duration-75"
          >
            + Ny Bunt
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
