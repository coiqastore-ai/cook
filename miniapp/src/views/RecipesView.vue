<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api, type Recipe } from "../api";

const recipes = ref<Recipe[]>([]);
const loading = ref(false);
const showImport = ref(false);
const importUrl = ref("");
const importing = ref(false);
const expanded = ref<number | null>(null);

async function load() {
  loading.value = true;
  try { recipes.value = await api.recipes.list(); } finally { loading.value = false; }
}

async function importRecipe() {
  if (!importUrl.value.trim()) return;
  importing.value = true;
  try {
    await api.recipes.import(importUrl.value.trim());
    importUrl.value = "";
    showImport.value = false;
    await load();
  } catch {
    alert("Не удалось импортировать. Проверьте ссылку.");
  } finally {
    importing.value = false;
  }
}

function toggle(id: number) {
  expanded.value = expanded.value === id ? null : id;
}

onMounted(load);
</script>

<template>
  <div class="p-4">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-semibold text-gray-800">Рецепты</h1>
      <button @click="showImport = !showImport"
        class="bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium">
        + Импорт
      </button>
    </div>

    <!-- Import form -->
    <div v-if="showImport" class="bg-white rounded-xl border border-gray-200 p-4 mb-4 space-y-2">
      <p class="text-sm text-gray-600">Вставь ссылку на рецепт:</p>
      <input v-model="importUrl" placeholder="https://eda.ru/..." class="input" />
      <div class="flex gap-2">
        <button @click="importRecipe" :disabled="importing" class="btn-primary flex-1">
          {{ importing ? "Импортирую..." : "Импортировать" }}
        </button>
        <button @click="showImport = false" class="btn-ghost flex-1">Отмена</button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-400">Загрузка...</div>

    <div v-else-if="!recipes.length" class="text-center py-12 text-gray-400">
      <p class="text-4xl mb-2">📖</p>
      <p>Библиотека пуста. Импортируй первый рецепт!</p>
    </div>

    <div v-else class="space-y-3">
      <div v-for="r in recipes" :key="r.id"
        class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div @click="toggle(r.id)" class="p-4 cursor-pointer flex justify-between items-start">
          <div class="flex-1 pr-2">
            <h3 class="font-medium text-gray-800">{{ r.title }}</h3>
            <div class="text-xs text-gray-500 mt-1 flex gap-3">
              <span>🍽 {{ r.base_servings }} порц.</span>
              <span>🥕 {{ r.ingredients.length }} ингр.</span>
              <span v-if="r.cook_time_min">⏱ {{ r.cook_time_min }} мин</span>
            </div>
          </div>
          <span class="text-gray-400 text-sm">{{ expanded === r.id ? "▲" : "▼" }}</span>
        </div>

        <!-- Expanded details -->
        <div v-if="expanded === r.id" class="border-t border-gray-100 px-4 pb-4 pt-3">
          <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Ингредиенты</p>
          <ul class="space-y-1">
            <li v-for="ing in r.ingredients" :key="ing.id" class="text-sm text-gray-700 flex justify-between">
              <span>{{ ing.name }}</span>
              <span class="text-gray-400">
                {{ ing.quantity ?? "" }} {{ ing.unit ?? "" }}
                <span v-if="ing.normalized_grams" class="text-gray-300">({{ Math.round(ing.normalized_grams) }} г)</span>
              </span>
            </li>
          </ul>
          <a v-if="r.source_url" :href="r.source_url" target="_blank"
            class="mt-3 inline-block text-xs text-green-600 underline">Открыть оригинал →</a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input { @apply w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-green-400; }
.btn-primary { @apply bg-green-600 text-white py-2 rounded-lg text-sm font-medium disabled:opacity-50; }
.btn-ghost { @apply border border-gray-200 text-gray-600 py-2 rounded-lg text-sm; }
</style>
