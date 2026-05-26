<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api, fileToBase64, type Event, type Recipe } from "../api";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function getTelegramUserId(): number | null {
  const tg = (window as any).Telegram?.WebApp;
  return tg?.initDataUnsafe?.user?.id ?? null;
}

const props = defineProps<{ id: string }>();
const router = useRouter();
const event = ref<Event | null>(null);
const allRecipes = ref<Recipe[]>([]);
const showImport = ref(false);
const showLibrary = ref(false);
const importMode = ref<"url" | "text" | "image">("url");
const importUrl = ref("");
const importText = ref("");
const importTitle = ref("");
const importImageFile = ref<File | null>(null);
const importImagePreview = ref<string | null>(null);
const importing = ref(false);

const pdfUrl = computed(() => `${API_BASE.replace(/\/$/, "")}/events/${props.id}/menu.pdf`);

const BOT_USERNAME = "reciptesbot";  // ⚠ change if bot username changes

function shareWithFriend() {
  const deepLink = `https://t.me/${BOT_USERNAME}?start=event_${props.id}`;
  const title = encodeURIComponent(event.value?.title ?? "событию");
  const url = `https://t.me/share/url?url=${encodeURIComponent(deepLink)}&text=Присоединяйся%20к%20${title}%20в%20Поляне`;
  const tg = (window as any).Telegram?.WebApp;
  if (tg && typeof tg.openTelegramLink === "function") {
    tg.openTelegramLink(url);
  } else {
    window.open(url, "_blank");
  }
}

async function removeCollaborator(uid: number) {
  if (!confirm("Убрать друга из события?")) return;
  await api.events.removeCollaborator(Number(props.id), uid);
  await load();
}

function onFileSelected(e: globalThis.Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  importImageFile.value = f;
  importImagePreview.value = URL.createObjectURL(f);
}

async function load() {
  event.value = await api.events.get(Number(props.id));
}

async function importRecipe() {
  importing.value = true;
  try {
    const uid = getTelegramUserId() ?? undefined;
    let recipe;
    if (importMode.value === "url") {
      if (!importUrl.value.trim()) return;
      recipe = await api.recipes.import(importUrl.value.trim(), uid);
    } else if (importMode.value === "text") {
      if (!importText.value.trim()) return;
      recipe = await api.recipes.importText(importText.value, importTitle.value || undefined, uid);
    } else {
      if (!importImageFile.value) return;
      const b64 = await fileToBase64(importImageFile.value);
      recipe = await api.recipes.importImage(b64, importTitle.value || undefined, uid);
    }
    await api.events.addRecipe(Number(props.id), recipe.id);
    importUrl.value = "";
    importText.value = "";
    importTitle.value = "";
    importImageFile.value = null;
    importImagePreview.value = null;
    showImport.value = false;
    await load();
  } catch {
    const labels = { url: "ссылке", text: "тексту", image: "фото" };
    alert(`Не удалось распознать рецепт по ${labels[importMode.value]}.`);
  } finally {
    importing.value = false;
  }
}

async function addFromLibrary(recipeId: number) {
  await api.events.addRecipe(Number(props.id), recipeId);
  showLibrary.value = false;
  await load();
}

async function updateServings(recipeId: number, value: string, baseServings: number) {
  const target = parseFloat(value);
  if (isNaN(target) || target <= 0 || !baseServings) return;
  const multiplier = target / baseServings;
  await api.events.updateMultiplier(Number(props.id), recipeId, multiplier);
  await load();
}

async function removeRecipe(recipeId: number) {
  if (!confirm("Убрать рецепт из события? (рецепт останется в библиотеке)")) return;
  try {
    await api.events.removeRecipe(Number(props.id), recipeId);
    await load();
  } catch (e) {
    alert("Не удалось убрать: " + (e instanceof Error ? e.message : e));
  }
}

async function openLibrary() {
  const uid = getTelegramUserId() ?? undefined;
  allRecipes.value = await api.recipes.list(uid);
  showLibrary.value = true;
}

function linkedIds() {
  return new Set(event.value?.event_recipes.map(er => er.recipe_id));
}

onMounted(load);
</script>

<template>
  <div class="p-4" v-if="event">
    <!-- Header -->
    <div class="flex items-center gap-2 mb-4">
      <button @click="router.back()" class="text-gray-500 text-lg">←</button>
      <h1 class="text-xl font-semibold text-gray-800 flex-1 truncate">{{ event.title }}</h1>
    </div>

    <!-- Event info -->
    <div class="bg-white rounded-xl border border-gray-200 p-4 mb-4 text-sm text-gray-600 space-y-1">
      <div v-if="event.date">📅 {{ new Date(event.date).toLocaleString("ru-RU") }}</div>
      <div>👥 Гостей: {{ event.guests_count }}</div>
      <div v-if="event.notes" class="text-gray-500">{{ event.notes }}</div>
    </div>

    <!-- Action buttons -->
    <div class="grid grid-cols-2 gap-2 mb-2">
      <button @click="router.push(`/events/${id}/shopping`)"
        class="bg-amber-50 border border-amber-200 text-amber-700 rounded-xl py-3 text-sm font-medium">
        🛒 Закупка
      </button>
      <button @click="router.push(`/events/${id}/timeline`)"
        class="bg-blue-50 border border-blue-200 text-blue-700 rounded-xl py-3 text-sm font-medium">
        ⏱ Таймлайн
      </button>
    </div>
    <!-- PDF + Share -->
    <div class="grid grid-cols-2 gap-2 mb-4">
      <a :href="pdfUrl" target="_blank"
        class="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl py-3 text-sm font-medium text-center">
        📄 Меню (PDF)
      </a>
      <button @click="shareWithFriend"
        class="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-xl py-3 text-sm font-medium">
        👥 Пригласить друга
      </button>
    </div>

    <!-- Collaborators -->
    <div v-if="event.collaborators?.length" class="bg-white rounded-xl border border-gray-200 p-3 mb-4">
      <p class="text-xs font-semibold text-gray-500 uppercase mb-2">Соавторы</p>
      <div class="space-y-1.5">
        <div v-for="c in event.collaborators" :key="c.telegram_user_id"
          class="flex items-center justify-between text-sm">
          <span class="text-gray-700">
            {{ c.name || "Без имени" }}
            <span v-if="c.username" class="text-gray-400">@{{ c.username }}</span>
          </span>
          <button @click="removeCollaborator(c.telegram_user_id)"
            class="text-gray-400 hover:text-red-500 text-xs">✕</button>
        </div>
      </div>
    </div>

    <!-- Recipes section -->
    <div class="flex items-center justify-between mb-3">
      <h2 class="font-medium text-gray-800">Рецепты ({{ event.event_recipes.length }})</h2>
      <div class="flex gap-2">
        <button @click="showImport = !showImport" class="text-sm text-green-600 font-medium">+ URL</button>
        <button @click="openLibrary" class="text-sm text-blue-600 font-medium">+ Библиотека</button>
      </div>
    </div>

    <!-- Import (URL or text) -->
    <div v-if="showImport" class="bg-white rounded-xl border border-gray-200 p-3 mb-3 space-y-2">
      <!-- Mode tabs -->
      <div class="flex gap-1 bg-gray-100 p-1 rounded-lg">
        <button @click="importMode = 'url'"
          class="flex-1 py-1.5 text-xs rounded-md transition-colors"
          :class="importMode === 'url' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'">
          🔗 URL
        </button>
        <button @click="importMode = 'text'"
          class="flex-1 py-1.5 text-xs rounded-md transition-colors"
          :class="importMode === 'text' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'">
          📝 Текст
        </button>
        <button @click="importMode = 'image'"
          class="flex-1 py-1.5 text-xs rounded-md transition-colors"
          :class="importMode === 'image' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'">
          📷 Фото
        </button>
      </div>

      <input v-if="importMode === 'url'" v-model="importUrl" placeholder="https://..." class="input" />

      <template v-else-if="importMode === 'text'">
        <input v-model="importTitle" placeholder="Название (опционально)" class="input" />
        <textarea v-model="importText"
          placeholder="Вставь рецепт текстом — ингредиенты + способ приготовления..."
          class="input h-32 resize-none" />
      </template>

      <template v-else>
        <input v-model="importTitle" placeholder="Название (опционально)" class="input" />
        <label class="block">
          <input type="file" accept="image/*" @change="onFileSelected" class="hidden" />
          <div class="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center text-gray-500 hover:border-green-400 cursor-pointer">
            <span v-if="!importImagePreview">📷 Нажми чтобы выбрать фото</span>
            <img v-else :src="importImagePreview" class="max-h-48 mx-auto rounded" />
          </div>
        </label>
      </template>

      <div class="flex gap-2">
        <button @click="importRecipe" :disabled="importing" class="btn-primary flex-1">
          {{ importing ? "Импортирую..." : "Импортировать" }}
        </button>
        <button @click="showImport = false" class="btn-ghost flex-1">Отмена</button>
      </div>
    </div>

    <!-- Library modal -->
    <div v-if="showLibrary" class="fixed inset-0 bg-black/40 z-40 flex items-end" @click.self="showLibrary = false">
      <div class="bg-white rounded-t-2xl w-full max-h-[70dvh] overflow-y-auto p-4">
        <h3 class="font-semibold text-gray-800 mb-3">Выбери рецепт</h3>
        <div v-if="!allRecipes.length" class="text-center py-6 text-gray-400">Рецептов нет. Импортируй сначала.</div>
        <div v-else class="space-y-2">
          <div v-for="r in allRecipes" :key="r.id"
            class="flex items-center justify-between p-3 border border-gray-200 rounded-lg">
            <div>
              <p class="font-medium text-sm text-gray-800">{{ r.title }}</p>
              <p class="text-xs text-gray-500">{{ r.base_servings }} порций · {{ r.ingredients.length }} ингредиентов</p>
            </div>
            <button
              v-if="!linkedIds().has(r.id)"
              @click="addFromLibrary(r.id)"
              class="text-sm text-green-600 font-medium px-3 py-1 border border-green-200 rounded-lg">
              Добавить
            </button>
            <span v-else class="text-xs text-gray-400">Добавлен</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Recipe list -->
    <div v-if="!event.event_recipes.length" class="text-center py-8 text-gray-400 text-sm">
      Рецепты не добавлены
    </div>
    <div v-else class="space-y-3">
      <div v-for="er in event.event_recipes" :key="er.recipe_id"
        class="bg-white rounded-xl border border-gray-200 p-4">
        <div class="flex justify-between items-start mb-2">
          <p class="font-medium text-gray-800 flex-1 pr-2">{{ er.recipe.title }}</p>
          <button @click="removeRecipe(er.recipe_id)" class="text-gray-400 hover:text-red-500 text-sm">✕</button>
        </div>
        <div class="text-xs text-gray-500 mb-3">
          {{ er.recipe.ingredients.length }} ингр. ·
          {{ er.recipe.cook_time_min ?? "?" }} мин готовки
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm text-gray-700">Готовлю на</span>
          <input type="number"
            :value="Math.round(er.servings_multiplier * er.recipe.base_servings)"
            min="1" step="1"
            @change="updateServings(er.recipe_id, ($event.target as HTMLInputElement).value, er.recipe.base_servings)"
            class="w-16 border border-gray-200 rounded-lg px-2 py-1 text-sm text-center" />
          <span class="text-sm text-gray-700">порц.</span>
          <span class="text-xs text-gray-400">(рецепт на {{ er.recipe.base_servings }})</span>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="flex items-center justify-center h-40 text-gray-400">Загрузка...</div>
</template>

<style scoped>
.input { @apply w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-green-400; }
.btn-primary { @apply bg-green-600 text-white py-2 rounded-lg text-sm font-medium disabled:opacity-50; }
.btn-ghost { @apply border border-gray-200 text-gray-600 py-2 rounded-lg text-sm; }
</style>
