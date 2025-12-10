<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { fetchTeacherDashboard } from '@/services/teacher-dashboard'
import type {
  TeacherDashboardResponse,
  TeacherBatchItem,
  BatchClientStatus,
} from '@/schemas/teacher-dashboard'

// State
const dashboardData = ref<TeacherDashboardResponse | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)

// Pagination
const currentPage = ref(1)
const pageSize = ref(20)

// Filter
const statusFilter = ref<BatchClientStatus | ''>('')

// Computed
const totalPages = computed(() => {
  if (!dashboardData.value) return 0
  return Math.ceil(dashboardData.value.total_count / pageSize.value)
})

// Calculate progress percentage client-side
function getProgressPercentage(batch: TeacherBatchItem): number {
  if (batch.total_essays === 0) return 0
  return Math.round((batch.completed_essays / batch.total_essays) * 100)
}

// Status display mapping (Swedish labels)
const STATUS_DISPLAY: Record<BatchClientStatus, { label: string; colorClass: string }> = {
  pending_content: { label: 'Vantar pa innehall', colorClass: 'bg-navy/20 text-navy' },
  ready: { label: 'Redo', colorClass: 'bg-navy/40 text-canvas' },
  processing: { label: 'Bearbetar', colorClass: 'bg-burgundy/40 text-canvas' },
  completed_successfully: { label: 'Klar', colorClass: 'bg-navy text-canvas' },
  completed_with_failures: { label: 'Klar med fel', colorClass: 'bg-burgundy/60 text-canvas' },
  failed: { label: 'Misslyckades', colorClass: 'bg-burgundy text-canvas' },
  cancelled: { label: 'Avbruten', colorClass: 'bg-navy/30 text-navy' },
}

// Fetch data
async function loadDashboard() {
  isLoading.value = true
  error.value = null

  try {
    const offset = (currentPage.value - 1) * pageSize.value
    dashboardData.value = await fetchTeacherDashboard({
      limit: pageSize.value,
      offset,
      status: statusFilter.value || undefined,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Ett fel uppstod'
  } finally {
    isLoading.value = false
  }
}

// Reset to page 1 when filter changes
watch(statusFilter, () => {
  currentPage.value = 1
  loadDashboard()
})

// Watch for pagination changes
watch(currentPage, () => {
  loadDashboard()
})

onMounted(() => {
  loadDashboard()
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-navy tracking-tightest">Inlamningar</h1>
        <p class="text-navy/60 text-sm mt-1">Hantera dina uppsatsinlamningar</p>
      </div>

      <!-- Status Filter -->
      <div class="flex items-center gap-4">
        <label for="status-filter" class="text-sm text-navy">Filtrera:</label>
        <select
          id="status-filter"
          v-model="statusFilter"
          class="px-3 py-2 border border-navy bg-canvas text-navy focus:outline-none focus:ring-2 focus:ring-burgundy"
        >
          <option value="">Alla</option>
          <option value="pending_content">Vantar pa innehall</option>
          <option value="ready">Redo</option>
          <option value="processing">Bearbetar</option>
          <option value="completed_successfully">Klar</option>
          <option value="completed_with_failures">Klar med fel</option>
          <option value="failed">Misslyckades</option>
          <option value="cancelled">Avbruten</option>
        </select>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="border border-navy p-8 shadow-brutal-sm text-center">
      <p class="text-navy/60">Laddar inlamningar...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="border border-burgundy p-6 shadow-brutal-sm">
      <h2 class="font-bold text-burgundy mb-2">Fel</h2>
      <p class="text-navy/80">{{ error }}</p>
      <button
        @click="loadDashboard"
        class="mt-4 px-4 py-2 border border-navy hover:bg-navy hover:text-canvas transition-colors"
      >
        Forsok igen
      </button>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="dashboardData && dashboardData.batches.length === 0"
      class="border border-navy p-8 shadow-brutal-sm text-center"
    >
      <h2 class="font-bold text-navy mb-2">Inga inlamningar</h2>
      <p class="text-navy/60">
        {{ statusFilter ? 'Inga inlamningar matchar ditt filter.' : 'Du har inga inlamningar annu.' }}
      </p>
    </div>

    <!-- Batch List -->
    <div v-else-if="dashboardData" class="space-y-4">
      <!-- Batch Cards -->
      <div
        v-for="batch in dashboardData.batches"
        :key="batch.batch_id"
        class="border border-navy p-4 shadow-brutal-sm batch-row cursor-pointer"
      >
        <div class="flex items-start justify-between gap-4">
          <!-- Left: Title and Class -->
          <div class="flex-grow min-w-0">
            <h3 class="font-bold text-navy truncate">{{ batch.title }}</h3>
            <p class="text-sm text-navy/60 mt-1">
              {{ batch.class_name ?? 'Gastinlamning' }}
            </p>
            <p class="text-xs text-navy/40 mt-2">
              Skapad: {{ new Date(batch.created_at).toLocaleDateString('sv-SE') }}
            </p>
          </div>

          <!-- Right: Status and Progress -->
          <div class="flex flex-col items-end gap-2 shrink-0">
            <!-- Status Badge -->
            <span
              class="px-2 py-1 text-xs font-semibold"
              :class="STATUS_DISPLAY[batch.status].colorClass"
            >
              {{ STATUS_DISPLAY[batch.status].label }}
            </span>

            <!-- Progress -->
            <div class="text-right">
              <span class="text-lg font-bold text-burgundy">
                {{ getProgressPercentage(batch) }}%
              </span>
              <p class="text-xs text-navy/40">
                {{ batch.completed_essays }}/{{ batch.total_essays }} uppsatser
              </p>
            </div>
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="mt-4 h-2 bg-navy/10 overflow-hidden">
          <div
            class="h-full bg-burgundy transition-all duration-300"
            :style="{ width: `${getProgressPercentage(batch)}%` }"
          ></div>
        </div>
      </div>

      <!-- Pagination -->
      <div
        v-if="totalPages > 1"
        class="flex items-center justify-between pt-4 border-t border-navy/20"
      >
        <p class="text-sm text-navy/60">
          Visar
          {{ dashboardData.offset + 1 }}-{{
            Math.min(dashboardData.offset + dashboardData.batches.length, dashboardData.total_count)
          }}
          av {{ dashboardData.total_count }}
        </p>

        <div class="flex gap-2">
          <button
            :disabled="currentPage === 1"
            @click="currentPage--"
            class="px-3 py-1 border border-navy text-sm disabled:opacity-40 hover:bg-navy hover:text-canvas transition-colors"
          >
            Foregaende
          </button>
          <span class="px-3 py-1 text-sm text-navy"> {{ currentPage }} / {{ totalPages }} </span>
          <button
            :disabled="currentPage === totalPages"
            @click="currentPage++"
            class="px-3 py-1 border border-navy text-sm disabled:opacity-40 hover:bg-navy hover:text-canvas transition-colors"
          >
            Nasta
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
