import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore, type User } from '@/stores/auth'
import { apiClient } from '@/lib/api-client'
import { ApiError } from '@/lib/api-error'

export interface LoginCredentials {
  email: string
  password: string
}

export interface LoginResponse {
  token: string
  user: User
}

export function useAuth() {
  const router = useRouter()
  const authStore = useAuthStore()

  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function login(credentials: LoginCredentials): Promise<boolean> {
    isLoading.value = true
    error.value = null

    try {
      const response = await apiClient.post<LoginResponse>('/v1/auth/login', credentials)
      authStore.setAuth(response.token, response.user)

      // Redirect to intended destination or dashboard
      const redirect = router.currentRoute.value.query.redirect as string
      await router.push(redirect ?? '/app/dashboard')

      return true
    } catch (e) {
      if (e instanceof ApiError) {
        error.value = e.message
      } else {
        error.value = 'An unexpected error occurred'
      }
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function logout(): Promise<void> {
    authStore.clearAuth()
    await router.push('/login')
  }

  // Dev-only mock login for testing
  function devLogin(): void {
    const mockUser: User = {
      id: 'dev-user-1',
      email: 'dev@huleedu.se',
      name: 'Developer',
      roles: ['teacher', 'admin'],
    }
    authStore.setAuth('dev-token-12345', mockUser)
  }

  return {
    isLoading,
    error,
    login,
    logout,
    devLogin,
  }
}
