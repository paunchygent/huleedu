<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="ledger-frame min-h-screen flex flex-col">
    <header class="h-16 border-b border-navy shrink-0 flex items-center justify-between px-6">
      <span class="text-xl font-bold tracking-tightest">HuleEdu</span>
      <nav class="flex gap-4">
        <RouterLink to="/login" class="text-navy hover:text-burgundy transition-colors">
          Login
        </RouterLink>
      </nav>
    </header>

    <main class="flex-grow flex flex-col items-center justify-center p-6">
      <h1 class="text-4xl font-bold text-navy mb-4 tracking-tightest">
        HuleEdu
      </h1>
      <p class="text-lg text-navy/60 mb-8 text-center max-w-md">
        Professionella verktyg for larare och elever
      </p>
      <RouterLink
        to="/login"
        class="bg-navy text-canvas px-6 py-3 font-semibold shadow-brutal hover:bg-burgundy transition-colors"
      >
        Kom igang
      </RouterLink>
    </main>

    <footer class="border-t border-navy py-4 text-center shrink-0">
      <p class="text-xs text-navy/40">2025 HuleEdu</p>
    </footer>
  </div>
</template>
