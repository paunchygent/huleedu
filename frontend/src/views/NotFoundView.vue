<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="ledger-frame min-h-screen flex flex-col">
    <header class="h-16 border-b border-navy shrink-0 flex items-center px-6">
      <RouterLink to="/" class="text-xl font-bold tracking-tightest hover:text-burgundy">
        HuleEdu
      </RouterLink>
    </header>

    <main class="flex-grow flex flex-col items-center justify-center p-6">
      <h1 class="text-6xl font-bold text-navy mb-4 tracking-tightest">404</h1>
      <p class="text-lg text-navy/60 mb-8">Sidan kunde inte hittas</p>
      <RouterLink
        to="/"
        class="bg-navy text-canvas px-6 py-3 font-semibold shadow-brutal hover:bg-burgundy transition-colors"
      >
        Tillbaka till start
      </RouterLink>
    </main>
  </div>
</template>
