<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { useAuth } from '@/composables/useAuth'
import { useAuthStore } from '@/stores/auth'

const { logout } = useAuth()
const authStore = useAuthStore()
</script>

<template>
  <div class="ledger-frame min-h-screen flex flex-col">
    <!-- Header -->
    <header class="h-16 border-b border-navy shrink-0 flex items-center justify-between px-6">
      <div class="flex items-center gap-6">
        <RouterLink to="/app/dashboard" class="text-xl font-bold tracking-tightest hover:text-burgundy">
          HuleEdu
        </RouterLink>
        <nav class="hidden md:flex gap-4">
          <RouterLink
            to="/app/dashboard"
            class="text-sm text-navy hover:text-burgundy transition-colors"
            active-class="text-burgundy font-semibold"
          >
            Dashboard
          </RouterLink>
          <RouterLink
            to="/app/inlamningar"
            class="text-sm text-navy hover:text-burgundy transition-colors"
            active-class="text-burgundy font-semibold"
          >
            Inlamningar
          </RouterLink>
        </nav>
      </div>

      <div class="flex items-center gap-4">
        <span class="text-sm text-navy/60 hidden sm:inline">
          {{ authStore.user?.email }}
        </span>
        <button
          @click="logout"
          class="text-sm text-navy hover:text-burgundy transition-colors"
        >
          Logga ut
        </button>
      </div>
    </header>

    <!-- Main content -->
    <main class="flex-grow bg-canvas">
      <RouterView />
    </main>
  </div>
</template>
