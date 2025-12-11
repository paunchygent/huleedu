import { defineStore } from "pinia";
import { ref, computed } from "vue";

export interface User {
  id: string
  email: string
  name: string
  roles: string[]
}

export const useAuthStore = defineStore("auth", () => {
  // State
  const token = ref<string | null>(null);
  const user = ref<User | null>(null);

  // Getters
  const isAuthenticated = computed(() => token.value !== null);
  const userRoles = computed(() => user.value?.roles ?? []);

  // Actions
  function setAuth(newToken: string, newUser: User) {
    token.value = newToken;
    user.value = newUser;
  }

  function clearAuth() {
    token.value = null;
    user.value = null;
  }

  return {
    // State
    token,
    user,
    // Getters
    isAuthenticated,
    userRoles,
    // Actions
    setAuth,
    clearAuth,
  };
});
