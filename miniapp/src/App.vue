<script setup lang="ts">
import TimerPanel from "./components/TimerPanel.vue";
</script>

<template>
  <div class="min-h-dvh bg-gray-50">
    <nav class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex justify-around z-50 max-w-[480px] mx-auto">
      <RouterLink to="/" class="nav-tab" :class="{ active: $route.path === '/' }">
        <span class="text-xl">📅</span>
        <span class="text-xs">События</span>
      </RouterLink>
      <RouterLink to="/recipes" class="nav-tab" :class="{ active: $route.path === '/recipes' }">
        <span class="text-xl">📖</span>
        <span class="text-xs">Рецепты</span>
      </RouterLink>
    </nav>
    <div class="pb-24">
      <RouterView />
    </div>
    <TimerPanel />
  </div>
</template>

<style scoped>
.nav-tab {
  @apply flex flex-col items-center py-2 px-4 text-gray-500 flex-1;
}
.nav-tab.active {
  @apply text-green-600;
}
</style>
