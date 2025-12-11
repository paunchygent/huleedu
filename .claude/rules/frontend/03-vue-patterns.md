# Vue 3 Patterns

## Composition API

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

// Reactive state
const count = ref(0)

// Computed
const doubled = computed(() => count.value * 2)

// Props
const props = defineProps<{
  title: string
}>()

// Emits
const emit = defineEmits<{
  (e: 'update', value: number): void
}>()

// Lifecycle
onMounted(() => {
  console.log('mounted')
})
</script>
```

## Pinia Store Pattern

```typescript
import { defineStore } from 'pinia'

export const useCounterStore = defineStore('counter', () => {
  const count = ref(0)
  const doubled = computed(() => count.value * 2)
  function increment() { count.value++ }
  return { count, doubled, increment }
})
```

## Prefer
- `<script setup>` over Options API
- TypeScript with `defineProps<T>()`
- Composition API for complex logic
