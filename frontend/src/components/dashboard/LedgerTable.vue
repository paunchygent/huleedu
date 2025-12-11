<script setup lang="ts">
/**
 * LedgerTable - Container with 12-column grid header
 *
 * Provides the table structure for bunt rows.
 * Header matches prototype columns: Uppgift | Status | Process | Tid
 */
</script>

<template>
  <div class="bg-white border-2 border-navy">
    <!-- Table Header - hidden on mobile -->
    <div class="hidden md:grid grid-cols-12 border-b-2 border-navy bg-canvas">
      <div class="col-span-5 p-4 border-r border-navy">
        <span class="text-xs font-bold uppercase tracking-widest text-navy">Uppgift</span>
      </div>
      <div class="col-span-2 p-4 border-r border-navy">
        <span class="text-xs font-bold uppercase tracking-widest text-navy">Status</span>
      </div>
      <div class="col-span-4 p-4 border-r border-navy">
        <span class="text-xs font-bold uppercase tracking-widest text-navy">Process</span>
      </div>
      <div class="col-span-1 p-4 text-right">
        <span class="text-xs font-bold uppercase tracking-widest text-navy">Tid</span>
      </div>
    </div>

    <!-- Rows slot -->
    <slot></slot>
  </div>
</template>
