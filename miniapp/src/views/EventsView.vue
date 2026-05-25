<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api, type Event } from "../api";

const router = useRouter();
const events = ref<Event[]>([]);
const loading = ref(false);
const showForm = ref(false);

const form = ref({ title: "", date: "", guests_count: 1, notes: "" });

// Telegram WebApp user id (if launched from inside Telegram)
function getTelegramUserId(): number | null {
  const tg = (window as any).Telegram?.WebApp;
  return tg?.initDataUnsafe?.user?.id ?? null;
}

async function load() {
  loading.value = true;
  try { events.value = await api.events.list(); } finally { loading.value = false; }
}

async function createEvent() {
  if (!form.value.title.trim()) return;
  await api.events.create({
    title: form.value.title,
    date: form.value.date || null,
    guests_count: form.value.guests_count,
    notes: form.value.notes || undefined,
    telegram_user_id: getTelegramUserId() ?? undefined,
  });
  showForm.value = false;
  form.value = { title: "", date: "", guests_count: 1, notes: "" };
  await load();
}

function formatDate(d: string | null) {
  if (!d) return "";
  return new Date(d).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

onMounted(() => { load(); });
</script>

<template>
  <div class="p-4">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-semibold text-gray-800">Мои события</h1>
      <button @click="showForm = !showForm"
        class="bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium">
        + Создать
      </button>
    </div>

    <!-- Create event form -->
    <div v-if="showForm" class="bg-white rounded-xl border border-gray-200 p-4 mb-4 space-y-3">
      <h2 class="font-medium text-gray-800">Новое событие</h2>
      <input v-model="form.title" placeholder="Название" class="input" />
      <input v-model="form.date" type="datetime-local" class="input" />
      <input v-model.number="form.guests_count" type="number" min="1" placeholder="Гостей" class="input" />
      <textarea v-model="form.notes" placeholder="Заметки (необязательно)" class="input h-16 resize-none" />
      <div class="flex gap-2">
        <button @click="createEvent" class="btn-primary flex-1">Создать</button>
        <button @click="showForm = false" class="btn-ghost flex-1">Отмена</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-8 text-gray-500">Загрузка...</div>

    <!-- Empty -->
    <div v-else-if="!events.length" class="text-center py-12 text-gray-400">
      <p class="text-4xl mb-2">🎉</p>
      <p>Событий пока нет. Создай первое!</p>
    </div>

    <!-- List -->
    <div v-else class="space-y-3">
      <div v-for="event in events" :key="event.id"
        @click="router.push(`/events/${event.id}`)"
        class="bg-white rounded-xl border border-gray-200 p-4 cursor-pointer hover:border-green-300 transition-colors">
        <div class="flex justify-between items-start">
          <h3 class="font-medium text-gray-800">{{ event.title }}</h3>
          <span class="text-xs text-gray-400">{{ event.event_recipes.length }} рецептов</span>
        </div>
        <div class="mt-1 text-sm text-gray-500 flex gap-3">
          <span v-if="event.date">📅 {{ formatDate(event.date) }}</span>
          <span>👥 {{ event.guests_count }} чел.</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input { @apply w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-green-400; }
.btn-primary { @apply bg-green-600 text-white py-2 rounded-lg text-sm font-medium; }
.btn-ghost { @apply border border-gray-200 text-gray-600 py-2 rounded-lg text-sm; }
</style>
