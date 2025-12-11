<script setup lang="ts">
/**
 * AppLayout - Three-panel layout for authenticated app
 *
 * Structure:
 * [Header - full width]
 * [Sidebar | Main Content]
 *
 * Uses the brutalist ledger-frame pattern with strict grid alignment.
 */
import { RouterView, useRoute } from 'vue-router'
import { watch } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useNavigationStore } from '@/stores/navigation'

const route = useRoute()
const navigationStore = useNavigationStore()

// Sync navigation state with route
watch(
  () => route.path,
  (newPath) => {
    navigationStore.setSectionFromRoute(newPath)
  },
  { immediate: true }
)
</script>

<template>
  <div class="font-sans text-navy h-screen flex flex-col overflow-hidden selection:bg-burgundy selection:text-white">
    <!-- Header -->
    <AppHeader />

    <!-- Main container -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Sidebar -->
      <AppSidebar />

      <!-- Main content area -->
      <main class="flex-1 overflow-y-auto bg-grid">
        <RouterView />
      </main>
    </div>
  </div>
</template>
