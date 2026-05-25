<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api, type TimelineTask } from "../api";

const props = defineProps<{ id: string }>();
const router = useRouter();
const tasks = ref<TimelineTask[]>([]);
const loading = ref(false);
const regenerating = ref(false);
const eventDate = ref<string | null>(null);
const eventTitle = ref("");

async function load() {
  loading.value = true;
  try {
    const ev = await api.events.get(Number(props.id));
    eventTitle.value = ev.title;
    eventDate.value = ev.date;
    tasks.value = await api.timeline.get(Number(props.id));
  } finally {
    loading.value = false;
  }
}

async function regenerate() {
  regenerating.value = true;
  try {
    tasks.value = await api.timeline.regenerate(Number(props.id));
  } catch {
    alert("Ошибка генерации. Убедитесь что у события задана дата.");
  } finally {
    regenerating.value = false;
  }
}

function taskTime(offsetHours: number): string {
  if (!eventDate.value) return "";
  const feast = new Date(eventDate.value);
  const t = new Date(feast.getTime() + offsetHours * 3600 * 1000);
  return t.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function offsetLabel(h: number): string {
  if (h === 0) return "Время застолья";
  const abs = Math.abs(h);
  const hrs = Math.floor(abs);
  const mins = Math.round((abs - hrs) * 60);
  const parts = [];
  if (hrs) parts.push(`${hrs} ч`);
  if (mins) parts.push(`${mins} мин`);
  return h < 0 ? `За ${parts.join(" ")}` : `Через ${parts.join(" ")}`;
}

const sortedTasks = computed(() =>
  [...tasks.value].sort((a, b) => a.offset_hours - b.offset_hours)
);

onMounted(load);
</script>

<template>
  <div class="p-4">
    <div class="flex items-center gap-2 mb-4">
      <button @click="router.back()" class="text-gray-500 text-lg">←</button>
      <div class="flex-1">
        <h1 class="text-xl font-semibold text-gray-800">Таймлайн</h1>
        <p class="text-sm text-gray-500">{{ eventTitle }}</p>
      </div>
      <button @click="regenerate" :disabled="regenerating"
        class="text-sm text-blue-600 font-medium border border-blue-200 px-3 py-1 rounded-lg disabled:opacity-50">
        {{ regenerating ? "..." : "Обновить" }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-400">Генерирую таймлайн...</div>

    <div v-else-if="!tasks.length" class="text-center py-12 text-gray-400">
      <p class="text-4xl mb-2">⏱</p>
      <p>Таймлайн пуст. Нажми «Обновить» для генерации.</p>
    </div>

    <div v-else class="relative">
      <!-- Vertical line -->
      <div class="absolute left-[52px] top-0 bottom-0 w-px bg-gray-200"></div>

      <div class="space-y-4">
        <div v-for="task in sortedTasks" :key="task.id" class="flex gap-4 items-start">
          <!-- Time column -->
          <div class="w-[52px] flex-shrink-0 text-right">
            <p class="text-xs font-semibold text-gray-800">{{ taskTime(task.offset_hours) }}</p>
            <p class="text-xs text-gray-400 leading-tight">{{ offsetLabel(task.offset_hours) }}</p>
          </div>

          <!-- Dot -->
          <div class="relative z-10 w-3 h-3 rounded-full mt-1 flex-shrink-0 ring-2 ring-white"
            :class="task.offset_hours === 0 ? 'bg-red-500' : 'bg-green-400'"></div>

          <!-- Task card -->
          <div class="flex-1 bg-white rounded-xl border border-gray-200 p-3 min-w-0">
            <p class="text-sm text-gray-800">{{ task.action }}</p>
            <p v-if="task.duration_min" class="text-xs text-gray-400 mt-1">{{ task.duration_min }} мин</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
