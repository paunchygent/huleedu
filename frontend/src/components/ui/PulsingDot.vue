<script setup lang="ts">
/**
 * PulsingDot - Animated activity indicator
 *
 * A minimal pulsing dot to indicate ongoing activity.
 * Used in processing states and attention rows.
 */

interface Props {
  variant?: "navy" | "burgundy"
  size?: "sm" | "md"
}

const props = withDefaults(defineProps<Props>(), {
  variant: "burgundy",
  size: "md",
});

const sizeClass = props.size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";

const colorClass = props.variant === "burgundy" ? "bg-burgundy" : "bg-navy/40";
</script>

<template>
  <div class="rounded-full animate-pulse" :class="[sizeClass, colorClass]"></div>
</template>
