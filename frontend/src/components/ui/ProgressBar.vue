<script setup lang="ts">
/**
 * ProgressBar - Track/fill pattern for processing states
 *
 * Uses the brutalist progress bar pattern: flat track with solid fill,
 * no border-radius. A bar is a bar.
 */

interface Props {
  percent: number
  variant?: "navy" | "burgundy"
}

const props = withDefaults(defineProps<Props>(), {
  variant: "navy",
});

const fillClass = props.variant === "burgundy" ? "bg-burgundy" : "bg-navy";
</script>

<template>
  <div class="progress-track w-full">
    <div class="progress-fill" :class="fillClass" :style="{ width: `${percent}%` }"></div>
  </div>
</template>
