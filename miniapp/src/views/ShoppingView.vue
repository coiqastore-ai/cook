<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api, type ShoppingItem } from "../api";

const props = defineProps<{ id: string }>();
const router = useRouter();
const items = ref<ShoppingItem[]>([]);
const loading = ref(false);
const eventTitle = ref("");

const bought = computed(() => items.value.filter(i => i.bought).length);
const total = computed(() => items.value.length);

async function load() {
  loading.value = true;
  try {
    const [ev, list] = await Promise.all([
      api.events.get(Number(props.id)),
      api.shopping.get(Number(props.id)),
    ]);
    eventTitle.value = ev.title;
    items.value = list;
  } finally {
    loading.value = false;
  }
}

async function toggle(item: ShoppingItem) {
  item.bought = !item.bought;
  await api.shopping.toggle(Number(props.id), item.id, item.bought);
}

async function exportText() {
  const text = await api.shopping.exportText(Number(props.id));
  if (navigator.share) {
    await navigator.share({ title: "Список закупки", text });
  } else {
    await navigator.clipboard.writeText(text);
    alert("Скопировано в буфер обмена!");
  }
}

onMounted(load);
</script>

<template>
  <div class="p-4">
    <div class="flex items-center gap-2 mb-4">
      <button @click="router.back()" class="text-gray-500 text-lg">←</button>
      <div class="flex-1">
        <h1 class="text-xl font-semibold text-gray-800">Закупка</h1>
        <p class="text-sm text-gray-500">{{ eventTitle }}</p>
      </div>
      <button @click="exportText" class="text-sm text-green-600 font-medium border border-green-200 px-3 py-1 rounded-lg">
        Экспорт
      </button>
    </div>

    <!-- Progress bar -->
    <div v-if="total" class="mb-4">
      <div class="flex justify-between text-xs text-gray-500 mb-1">
        <span>Куплено: {{ bought }} / {{ total }}</span>
        <span>{{ Math.round(bought / total * 100) }}%</span>
      </div>
      <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div class="h-full bg-green-500 rounded-full transition-all duration-300"
          :style="{ width: `${(bought / total) * 100}%` }" />
      </div>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-400">Загрузка...</div>

    <div v-else-if="!items.length" class="text-center py-12 text-gray-400">
      <p class="text-4xl mb-2">🛒</p>
      <p>Список пуст. Добавь рецепты к событию.</p>
    </div>

    <div v-else class="space-y-2">
      <div v-for="item in items" :key="item.id"
        @click="toggle(item)"
        class="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3 cursor-pointer transition-opacity"
        :class="{ 'opacity-50': item.bought }">
        <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors"
          :class="item.bought ? 'bg-green-500 border-green-500' : 'border-gray-300'">
          <span v-if="item.bought" class="text-white text-xs">✓</span>
        </div>
        <div class="flex-1">
          <span class="text-gray-800 text-sm" :class="{ 'line-through': item.bought }">
            {{ item.ingredient_name }}
          </span>
        </div>
        <span class="text-sm font-medium text-gray-600">{{ item.total_display }}</span>
      </div>
    </div>
  </div>
</template>
