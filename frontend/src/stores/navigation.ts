import { defineStore } from "pinia";
import { ref, computed } from "vue";

export type NavSection = "oversikt" | "klasser" | "arkiv"

export interface NavItem {
  id: NavSection
  label: string
  route: string
  isActive: boolean
}

export const useNavigationStore = defineStore("navigation", () => {
  // State
  const currentSection = ref<NavSection>("oversikt");
  const isDrawerOpen = ref(false);

  // Getters
  const navItems = computed<NavItem[]>(() => [
    {
      id: "oversikt",
      label: "Översikt",
      route: "/app/dashboard",
      isActive: currentSection.value === "oversikt",
    },
    {
      id: "klasser",
      label: "Klasser",
      route: "/app/klasser",
      isActive: currentSection.value === "klasser",
    },
    {
      id: "arkiv",
      label: "Arkiv",
      route: "/app/arkiv",
      isActive: currentSection.value === "arkiv",
    },
  ]);

  const activeNavItem = computed(() => navItems.value.find((item) => item.isActive));

  // Actions
  function setSection(section: NavSection) {
    currentSection.value = section;
  }

  function setSectionFromRoute(path: string) {
    if (path.includes("/dashboard") || path.includes("/inlamningar")) {
      currentSection.value = "oversikt";
    } else if (path.includes("/klasser")) {
      currentSection.value = "klasser";
    } else if (path.includes("/arkiv")) {
      currentSection.value = "arkiv";
    }
  }

  // Drawer actions
  function openDrawer() {
    isDrawerOpen.value = true;
  }

  function closeDrawer() {
    isDrawerOpen.value = false;
  }

  function toggleDrawer() {
    isDrawerOpen.value = !isDrawerOpen.value;
  }

  return {
    // State
    currentSection,
    isDrawerOpen,
    // Getters
    navItems,
    activeNavItem,
    // Actions
    setSection,
    setSectionFromRoute,
    openDrawer,
    closeDrawer,
    toggleDrawer,
  };
});
