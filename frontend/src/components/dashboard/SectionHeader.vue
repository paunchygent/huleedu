<script setup lang="ts">
/**
 * SectionHeader - Section title with dot indicator
 *
 * Used for dashboard sections like "Kräver åtgärd" and "Pågående och Arkiverat"
 */

interface Props {
  title: string
  count?: number
  variant?: 'burgundy' | 'navy'
  showBorder?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'navy',
  showBorder: false,
})

const dotClass = props.variant === 'burgundy' ? 'bg-burgundy' : 'bg-navy'
</script>

<template>
  <div
    class="flex items-center gap-3 mb-6 pl-1"
    :class="showBorder ? 'border-b border-navy pb-2 mb-4' : ''"
  >
    <div class="w-2 h-2 rounded-full" :class="dotClass"></div>
    <h2 class="text-xs font-bold uppercase tracking-widest text-navy">
      {{ title }}
      <template v-if="count !== undefined"> ({{ count }}) </template>
    </h2>
  </div>
</template>
