<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const { login, devLogin, isLoading, error } = useAuth()

const email = ref('')
const password = ref('')

async function handleSubmit() {
  await login({ email: email.value, password: password.value })
}

function handleDevLogin() {
  devLogin()
  router.push('/app/dashboard')
}
</script>

<template>
  <div class="ledger-frame min-h-screen flex flex-col">
    <header class="h-16 border-b border-navy shrink-0 flex items-center px-6">
      <RouterLink to="/" class="text-xl font-bold tracking-tightest hover:text-burgundy">
        HuleEdu
      </RouterLink>
    </header>

    <main class="flex-grow flex items-center justify-center p-6">
      <div class="w-full max-w-sm">
        <h1 class="text-2xl font-bold text-navy mb-6 tracking-tightest">Login</h1>

        <form @submit.prevent="handleSubmit" class="space-y-4">
          <div>
            <label for="email" class="block text-sm font-medium text-navy mb-1">
              E-post
            </label>
            <input
              id="email"
              v-model="email"
              type="email"
              required
              class="w-full px-3 py-2 border border-navy bg-canvas focus:outline-none focus:ring-2 focus:ring-burgundy"
              placeholder="din@epost.se"
            />
          </div>

          <div>
            <label for="password" class="block text-sm font-medium text-navy mb-1">
              Losenord
            </label>
            <input
              id="password"
              v-model="password"
              type="password"
              required
              class="w-full px-3 py-2 border border-navy bg-canvas focus:outline-none focus:ring-2 focus:ring-burgundy"
              placeholder="********"
            />
          </div>

          <div v-if="error" class="text-burgundy text-sm">
            {{ error }}
          </div>

          <button
            type="submit"
            :disabled="isLoading"
            class="w-full bg-navy text-canvas py-3 font-semibold shadow-brutal hover:bg-burgundy transition-colors disabled:opacity-50"
          >
            {{ isLoading ? 'Laddar...' : 'Logga in' }}
          </button>
        </form>

        <!-- Dev login button -->
        <div class="mt-6 pt-6 border-t border-navy/20">
          <button
            type="button"
            @click="handleDevLogin"
            class="w-full border border-navy/40 text-navy py-2 text-sm hover:bg-navy/5 transition-colors"
          >
            Dev Login (bypass auth)
          </button>
        </div>
      </div>
    </main>
  </div>
</template>
