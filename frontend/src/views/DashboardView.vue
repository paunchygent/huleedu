<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold text-navy mb-2 tracking-tightest">Dashboard</h1>
    <p class="text-navy/60 mb-6">
      Valkommen, {{ authStore.user?.name ?? 'Anvandare' }}!
    </p>

    <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      <!-- Batches Card -->
      <div class="border border-navy p-6 shadow-brutal-sm">
        <h2 class="font-bold text-lg mb-2">Batchar</h2>
        <p class="text-navy/60 text-sm mb-4">Hantera dina uppsatsbatchar</p>
        <div class="text-3xl font-bold text-burgundy">0</div>
        <p class="text-xs text-navy/40 mt-1">Aktiva batchar</p>
      </div>

      <!-- Classes Card -->
      <div class="border border-navy p-6 shadow-brutal-sm">
        <h2 class="font-bold text-lg mb-2">Klasser</h2>
        <p class="text-navy/60 text-sm mb-4">Dina registrerade klasser</p>
        <div class="text-3xl font-bold text-burgundy">0</div>
        <p class="text-xs text-navy/40 mt-1">Totalt antal klasser</p>
      </div>

      <!-- Recent Activity Card -->
      <div class="border border-navy p-6 shadow-brutal-sm">
        <h2 class="font-bold text-lg mb-2">Senaste aktivitet</h2>
        <p class="text-navy/60 text-sm">Ingen aktivitet annu</p>
      </div>
    </div>
  </div>
</template>
