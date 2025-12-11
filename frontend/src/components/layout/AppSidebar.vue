<script setup lang="ts">
/**
 * AppSidebar - Navigation sidebar matching prototype
 *
 * Structure:
 * [Navigation links]
 * [Spacer]
 * [Ny Bunt button]
 */
import { RouterLink } from "vue-router";
import { useNavigationStore } from "@/stores/navigation";

const navigationStore = useNavigationStore();
</script>

<template>
  <nav class="hidden md:flex w-64 flex-none border-r border-navy bg-canvas flex-col">
    <!-- Navigation links -->
    <div class="flex flex-col py-8">
      <RouterLink
        v-for="item in navigationStore.navItems"
        :key="item.id"
        :to="item.route"
        class="px-6 py-3 font-medium text-lg border-l-4 transition-colors"
        :class="
          item.isActive
            ? 'font-bold border-navy bg-navy/5'
            : 'text-navy/60 hover:text-navy hover:bg-navy/5 border-transparent'
        "
      >
        {{ item.label }}
      </RouterLink>
    </div>

    <!-- Bottom action -->
    <div class="mt-auto p-6 border-t border-navy">
      <button
        class="btn-brutal w-full py-4 bg-navy text-white text-xs font-bold uppercase tracking-widest hover:bg-burgundy shadow-brutal transition-all duration-75"
      >
        + Ny Bunt
      </button>
    </div>
  </nav>
</template>
