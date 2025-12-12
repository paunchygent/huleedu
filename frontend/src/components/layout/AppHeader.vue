<script setup lang="ts">
/**
 * AppHeader - Three-section header matching prototype
 *
 * Structure (Desktop):
 * [Logo Section | Page Title | Spacer | Credits | User | Logout]
 *
 * Structure (Mobile):
 * [Hamburger | Logo | Page Title | Spacer | Logout]
 */
import { useAuth } from "@/composables/useAuth";
import { useAuthStore } from "@/stores/auth";
import { useDashboardStore } from "@/stores/dashboard";
import { useNavigationStore } from "@/stores/navigation";

const { logout } = useAuth();
const authStore = useAuthStore();
const dashboardStore = useDashboardStore();
const navigationStore = useNavigationStore();

// Get user initials
function getUserInitials(): string {
  const user = authStore.user;
  if (!user?.email) return "?";
  const name = user.email.split("@")[0];
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.substring(0, 2).toUpperCase();
}

function formatCredits(credits: number | null): string {
  if (credits === null) return "---";
  return `${credits} SEK`;
}
</script>

<template>
  <header class="h-16 flex-none border-b border-navy bg-canvas flex items-center z-50">
    <!-- Mobile: Hamburger + Compact logo -->
    <div class="md:hidden h-full border-r border-navy flex items-center">
      <button
        class="h-full px-4 border-r border-navy flex items-center justify-center min-w-[48px]"
        aria-label="Oppna meny"
        @click="navigationStore.toggleDrawer"
      >
        <span class="text-xl">&#x2630;</span>
      </button>
      <div class="px-4 flex items-center">
        <span class="font-serif font-bold text-xl tracking-tight">HuleEdu.</span>
      </div>
    </div>

    <!-- Desktop: Full logo section -->
    <div class="hidden md:flex w-64 shrink-0 h-full border-r border-navy px-6 items-center">
      <span class="font-serif font-bold text-2xl tracking-tight">HuleEdu.</span>
    </div>

    <!-- Right sections -->
    <div class="flex-1 flex h-full">
      <!-- Page title -->
      <div class="h-full border-r border-navy px-4 md:px-6 flex items-center">
        <h1 class="text-xs font-bold uppercase tracking-widest text-navy">Lärarpanel</h1>
      </div>

      <!-- Spacer -->
      <div class="flex-1 border-r border-navy"></div>

      <!-- Credits display - desktop only -->
      <div
        class="hidden md:flex h-full border-r border-navy px-6 items-center gap-2 hover:bg-navy/5 cursor-help transition-colors"
      >
        <div class="h-2 w-2 rounded-full bg-burgundy"></div>
        <span class="font-mono text-sm font-bold">{{ formatCredits(dashboardStore.credits) }}</span>
        <span class="text-xs text-navy/40 uppercase tracking-widest font-bold ml-1">Krediter</span>
      </div>

      <!-- User section - desktop only -->
      <div
        class="hidden md:flex h-full border-r border-navy px-6 items-center gap-3 hover:bg-navy/5 cursor-pointer transition-colors"
      >
        <span class="text-sm font-bold">{{ authStore.user?.email?.split('@')[0] ?? 'Användare' }}</span>
        <div
          class="h-8 w-8 bg-navy text-canvas flex items-center justify-center text-xs font-bold"
        >
          {{ getUserInitials() }}
        </div>
      </div>

      <!-- Logout -->
      <button
        class="h-full px-4 md:px-6 flex items-center justify-center hover:bg-navy hover:text-white cursor-pointer transition-colors"
        @click="logout"
      >
        <span class="text-xs font-bold uppercase tracking-widest">Logga ut</span>
      </button>
    </div>
  </header>
</template>
