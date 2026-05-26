<script setup lang="ts">
import { ref } from "vue";
import { useTimers, addTimer, removeTimer, togglePause, remaining, isDone, fmt, type Timer } from "../composables/useTimers";

const { timers, tick } = useTimers();
const visible = ref(false);
const showForm = ref(false);
const newName = ref("");
const newMinutes = ref<number | string>(15);

function open() { visible.value = true; }
function close() { visible.value = false; showForm.value = false; }

function submit() {
  const min = typeof newMinutes.value === "string" ? parseFloat(newMinutes.value) : newMinutes.value;
  if (!min || min <= 0) return;
  addTimer(newName.value || "Таймер", min);
  newName.value = "";
  newMinutes.value = 15;
  showForm.value = false;
}

function quickAdd(name: string, min: number) {
  addTimer(name, min);
  showForm.value = false;
}

// Active timers count for FAB badge (tick is intentionally referenced for reactivity)
function activeCount(): number {
  void tick.value;
  return timers.value.filter(t => !isDone(t)).length;
}

function rem(t: Timer): number {
  void tick.value;
  return remaining(t);
}

function done(t: Timer): boolean {
  void tick.value;
  return isDone(t);
}

defineExpose({ open });
</script>

<template>
  <!-- Floating Action Button -->
  <button @click="open"
    class="fixed right-3 bottom-24 z-40 w-14 h-14 rounded-full bg-orange-500 text-white shadow-lg flex items-center justify-center max-w-[calc(480px-12px)]"
    style="left: auto;">
    <span class="text-2xl">⏲</span>
    <span v-if="activeCount() > 0"
      class="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full min-w-[20px] h-5 px-1 flex items-center justify-center">
      {{ activeCount() }}
    </span>
  </button>

  <!-- Bottom sheet -->
  <div v-if="visible" class="fixed inset-0 bg-black/40 z-50 flex items-end" @click.self="close">
    <div class="bg-white rounded-t-2xl w-full max-h-[80dvh] overflow-y-auto p-4 max-w-[480px] mx-auto">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold text-gray-800">⏲ Таймеры</h3>
        <button @click="close" class="text-gray-400 text-lg">✕</button>
      </div>

      <!-- Quick presets -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        <button @click="quickAdd('Варка', 5)" class="quick-btn">5м</button>
        <button @click="quickAdd('Варка', 10)" class="quick-btn">10м</button>
        <button @click="quickAdd('Жарка', 15)" class="quick-btn">15м</button>
        <button @click="quickAdd('Выпечка', 30)" class="quick-btn">30м</button>
        <button @click="quickAdd('Запекание', 45)" class="quick-btn">45м</button>
        <button @click="showForm = !showForm" class="quick-btn bg-orange-500 text-white border-orange-500">+ Свой</button>
      </div>

      <!-- Custom timer form -->
      <div v-if="showForm" class="bg-gray-50 rounded-lg p-3 mb-3 space-y-2">
        <input v-model="newName" placeholder="Название (напр. Варить яйца)"
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
        <div class="flex gap-2 items-center">
          <input v-model.number="newMinutes" type="number" step="0.5" min="0.5" placeholder="Минут"
            class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          <button @click="submit"
            class="bg-orange-500 text-white px-4 py-2 rounded-lg text-sm font-medium">Запустить</button>
        </div>
      </div>

      <!-- Timers list -->
      <div v-if="!timers.length" class="text-center py-8 text-gray-400 text-sm">
        Нет активных таймеров.<br>Жми пресет выше или «+ Свой».
      </div>

      <div v-else class="space-y-2">
        <div v-for="t in timers" :key="t.id"
          class="rounded-xl border p-3 flex items-center gap-3"
          :class="done(t) ? 'bg-green-50 border-green-300' : 'bg-white border-gray-200'">
          <div class="text-3xl">
            {{ done(t) ? "✅" : (t.paused ? "⏸" : "⏲") }}
          </div>
          <div class="flex-1 min-w-0">
            <p class="font-medium text-gray-800 truncate">{{ t.name }}</p>
            <p class="text-xl font-mono" :class="done(t) ? 'text-green-700' : (t.paused ? 'text-gray-400' : 'text-orange-600')">
              {{ done(t) ? "Готово!" : fmt(rem(t)) }}
            </p>
          </div>
          <div class="flex gap-1">
            <button v-if="!done(t)" @click="togglePause(t.id)"
              class="text-xs px-2.5 py-1 border border-gray-300 rounded-lg">
              {{ t.paused ? "▶" : "⏸" }}
            </button>
            <button @click="removeTimer(t.id)"
              class="text-xs px-2.5 py-1 border border-gray-300 rounded-lg text-red-500">✕</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quick-btn {
  @apply px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-700 bg-white;
}
</style>
