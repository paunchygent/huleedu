<script setup lang="ts">
/**
 * MobileDrawer - Slide-out navigation drawer for mobile
 *
 * Features:
 * - Slide animation from left
 * - Dimmed backdrop (tap to close)
 * - Same nav items as AppSidebar
 * - Close on navigation
 */
import { RouterLink } from "vue-router";
import { useNavigationStore } from "@/stores/navigation";

const navigationStore = useNavigationStore();
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <Transition name="drawer-backdrop">
      <div
        v-if="navigationStore.isDrawerOpen"
        class="drawer-backdrop fixed inset-0 bg-navy/50 z-40 md:hidden"
        @click="navigationStore.closeDrawer"
      ></div>
    </Transition>

    <!-- Drawer panel -->
    <Transition name="drawer-slide">
      <nav
        v-if="navigationStore.isDrawerOpen"
        class="drawer-panel fixed top-0 left-0 bottom-0 w-64 bg-canvas border-r-2 border-navy z-50 flex flex-col md:hidden"
      >
        <!-- Header with close button -->
        <div class="h-16 border-b border-navy flex items-center justify-between px-6">
          <span class="font-serif font-bold text-xl tracking-tight">HuleEdu.</span>
          <button
            class="h-12 w-12 flex items-center justify-center text-navy -mr-3"
            aria-label="Stang meny"
            @click="navigationStore.closeDrawer"
          >
            <span class="text-2xl font-light">&#x2715;</span>
          </button>
        </div>

        <!-- Navigation links -->
        <div class="flex flex-col py-8">
          <RouterLink
            v-for="item in navigationStore.navItems"
            :key="item.id"
            :to="item.route"
            class="drawer-nav-item px-6 py-4 font-medium text-lg border-l-4 transition-colors min-h-[48px] flex items-center"
            :class="
              item.isActive
                ? 'font-bold border-navy bg-navy/5'
                : 'text-navy/60 border-transparent'
            "
            @click="navigationStore.closeDrawer"
          >
            {{ item.label }}
          </RouterLink>
        </div>

        <!-- Bottom CTA -->
        <div class="mt-auto p-6 border-t border-navy">
          <button
            class="btn-brutal w-full py-4 bg-navy text-white text-xs font-bold uppercase tracking-widest shadow-brutal transition-all duration-75 min-h-[48px]"
            @click="navigationStore.closeDrawer"
          >
            + Ny Bunt
          </button>
        </div>
      </nav>
    </Transition>
  </Teleport>
</template>
