<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api, fileToBase64, type Recipe, type Ingredient, type Event } from "../api";

function getTelegramUserId(): number | null {
  const tg = (window as any).Telegram?.WebApp;
  return tg?.initDataUnsafe?.user?.id ?? null;
}

const recipes = ref<Recipe[]>([]);
const loading = ref(false);
const showImport = ref(false);
const importMode = ref<"url" | "text" | "image">("url");
const importUrl = ref("");
const importText = ref("");
const importTitle = ref("");
const importImageFile = ref<File | null>(null);
const importImagePreview = ref<string | null>(null);
const importing = ref(false);
const expanded = ref<number | null>(null);

// Ingredient editing
const addingTo = ref<number | null>(null);
const newIng = ref({ name: "", quantity: "" as string | number, unit: "" });
const editingIng = ref<number | null>(null);
const editIng = ref({ name: "", quantity: "" as string | number, unit: "" });

// "Add to event" modal
const addToEventFor = ref<number | null>(null);
const userEvents = ref<Event[]>([]);
const addingToEventBusy = ref(false);

async function openAddToEvent(recipeId: number) {
  addToEventFor.value = recipeId;
  const uid = getTelegramUserId();
  userEvents.value = await api.events.list(uid ?? undefined);
}

async function attachToEvent(eventId: number, recipeId: number) {
  addingToEventBusy.value = true;
  try {
    await api.events.addRecipe(eventId, recipeId);
    addToEventFor.value = null;
    alert("✅ Рецепт добавлен в событие");
  } catch (e) {
    alert("Не получилось добавить: " + (e instanceof Error ? e.message : e));
  } finally {
    addingToEventBusy.value = false;
  }
}

const noTgUser = ref(false);

async function load() {
  loading.value = true;
  try {
    const uid = getTelegramUserId();
    if (!uid) {
      noTgUser.value = true;
      recipes.value = [];
      return;
    }
    noTgUser.value = false;
    recipes.value = await api.recipes.list(uid);
  } finally {
    loading.value = false;
  }
}

function onFileSelected(e: globalThis.Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  importImageFile.value = f;
  importImagePreview.value = URL.createObjectURL(f);
}

async function importRecipe() {
  importing.value = true;
  try {
    const uid = getTelegramUserId() ?? undefined;
    if (importMode.value === "url") {
      if (!importUrl.value.trim()) return;
      await api.recipes.import(importUrl.value.trim(), uid);
    } else if (importMode.value === "text") {
      if (!importText.value.trim()) return;
      await api.recipes.importText(importText.value, importTitle.value || undefined, uid);
    } else {
      if (!importImageFile.value) return;
      const b64 = await fileToBase64(importImageFile.value);
      await api.recipes.importImage(b64, importTitle.value || undefined, uid);
    }
    resetImport();
    showImport.value = false;
    await load();
  } catch {
    const labels = { url: "ссылку", text: "текст", image: "фото" };
    alert(`Не удалось распознать рецепт из ${labels[importMode.value]}.`);
  } finally {
    importing.value = false;
  }
}

function resetImport() {
  importUrl.value = "";
  importText.value = "";
  importTitle.value = "";
  importImageFile.value = null;
  importImagePreview.value = null;
}

function toggle(id: number) {
  expanded.value = expanded.value === id ? null : id;
  addingTo.value = null;
  editingIng.value = null;
}

async function deleteRecipe(id: number) {
  if (!confirm("Удалить рецепт навсегда? Он также будет убран из всех событий.")) return;
  try {
    await api.recipes.delete(id);
    expanded.value = null;
    await load();
  } catch (e) {
    alert("Не удалось удалить: " + (e instanceof Error ? e.message : e));
  }
}

// --- Ingredient editing ---

function startAdd(recipeId: number) {
  addingTo.value = recipeId;
  newIng.value = { name: "", quantity: "", unit: "" };
}

async function saveNewIngredient(recipeId: number) {
  if (!newIng.value.name.trim()) return;
  const qty = newIng.value.quantity === "" ? null : Number(newIng.value.quantity);
  await api.recipes.addIngredient(recipeId, {
    name: newIng.value.name.trim(),
    quantity: qty,
    unit: newIng.value.unit.trim() || null,
  });
  addingTo.value = null;
  await load();
  expanded.value = recipeId;
}

function startEdit(ing: Ingredient) {
  editingIng.value = ing.id;
  editIng.value = {
    name: ing.name,
    quantity: ing.quantity ?? "",
    unit: ing.unit ?? "",
  };
}

async function saveEditIngredient(recipeId: number, ingredientId: number) {
  if (!editIng.value.name.trim()) return;
  const qty = editIng.value.quantity === "" ? null : Number(editIng.value.quantity);
  await api.recipes.updateIngredient(recipeId, ingredientId, {
    name: editIng.value.name.trim(),
    quantity: qty,
    unit: editIng.value.unit.trim() || null,
  });
  editingIng.value = null;
  await load();
  expanded.value = recipeId;
}

async function removeIngredient(recipeId: number, ingredientId: number) {
  if (!confirm("Удалить ингредиент?")) return;
  await api.recipes.deleteIngredient(recipeId, ingredientId);
  await load();
  expanded.value = recipeId;
}

onMounted(load);
</script>

<template>
  <div class="p-4">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-semibold text-gray-800">Рецепты</h1>
      <button @click="showImport = !showImport"
        class="bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium">
        + Добавить
      </button>
    </div>

    <!-- Import form -->
    <div v-if="showImport" class="bg-white rounded-xl border border-gray-200 p-4 mb-4 space-y-2">
      <div class="flex gap-1 bg-gray-100 p-1 rounded-lg">
        <button @click="importMode = 'url'"
          class="flex-1 py-1.5 text-xs rounded-md"
          :class="importMode === 'url' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'">
          🔗 URL
        </button>
        <button @click="importMode = 'text'"
          class="flex-1 py-1.5 text-xs rounded-md"
          :class="importMode === 'text' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'">
          📝 Текст
        </button>
        <button @click="importMode = 'image'"
          class="flex-1 py-1.5 text-xs rounded-md"
          :class="importMode === 'image' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'">
          📷 Фото
        </button>
      </div>

      <input v-if="importMode === 'url'" v-model="importUrl" placeholder="https://povarenok.ru/..." class="input" />

      <template v-else-if="importMode === 'text'">
        <input v-model="importTitle" placeholder="Название (опционально)" class="input" />
        <textarea v-model="importText"
          placeholder="Ингредиенты + способ приготовления..."
          class="input h-40 resize-none" />
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
          {{ importing ? "Распознаю..." : "Импортировать" }}
        </button>
        <button @click="showImport = false; resetImport()" class="btn-ghost flex-1">Отмена</button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-400">Загрузка...</div>

    <div v-else-if="noTgUser" class="text-center py-12 text-gray-400">
      <p class="text-4xl mb-2">🔒</p>
      <p>Открой это приложение через Telegram-бот <strong>@reciptesbot</strong></p>
    </div>

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
            <div class="text-xs text-gray-500 mt-1 flex gap-3 flex-wrap">
              <span>🍽 {{ r.base_servings }} порц.</span>
              <span>🥕 {{ r.ingredients.length }} ингр.</span>
              <span v-if="r.cook_time_min">⏱ {{ r.cook_time_min }} мин</span>
            </div>
          </div>
          <span class="text-gray-400 text-sm">{{ expanded === r.id ? "▲" : "▼" }}</span>
        </div>

        <div v-if="expanded === r.id" class="border-t border-gray-100 px-4 pb-4 pt-3 space-y-3">
          <!-- Ingredients header with + button -->
          <div class="flex items-center justify-between">
            <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Ингредиенты</p>
            <button v-if="addingTo !== r.id" @click="startAdd(r.id)"
              class="text-xs text-green-600 font-medium">+ Добавить</button>
          </div>

          <!-- Add new ingredient form -->
          <div v-if="addingTo === r.id" class="bg-gray-50 rounded-lg p-2 space-y-2">
            <input v-model="newIng.name" placeholder="Название (мука, лук...)" class="input text-sm" />
            <div class="flex gap-2">
              <input v-model="newIng.quantity" type="number" step="0.1" placeholder="Кол-во" class="input text-sm flex-1" />
              <input v-model="newIng.unit" placeholder="г / шт / ст.л." class="input text-sm flex-1" />
            </div>
            <div class="flex gap-2">
              <button @click="saveNewIngredient(r.id)" class="btn-primary flex-1 text-sm py-1.5">Сохранить</button>
              <button @click="addingTo = null" class="btn-ghost flex-1 text-sm py-1.5">Отмена</button>
            </div>
          </div>

          <!-- Ingredient list -->
          <ul v-if="r.ingredients.length" class="space-y-1.5">
            <li v-for="ing in r.ingredients" :key="ing.id" class="text-sm">
              <!-- Edit mode -->
              <div v-if="editingIng === ing.id" class="bg-amber-50 rounded-lg p-2 space-y-2">
                <input v-model="editIng.name" class="input text-sm" />
                <div class="flex gap-2">
                  <input v-model="editIng.quantity" type="number" step="0.1" placeholder="Кол-во" class="input text-sm flex-1" />
                  <input v-model="editIng.unit" placeholder="ед." class="input text-sm flex-1" />
                </div>
                <div class="flex gap-2">
                  <button @click="saveEditIngredient(r.id, ing.id)" class="btn-primary flex-1 text-sm py-1.5">Сохранить</button>
                  <button @click="editingIng = null" class="btn-ghost flex-1 text-sm py-1.5">Отмена</button>
                </div>
              </div>
              <!-- View mode -->
              <div v-else class="flex justify-between items-center gap-2 group">
                <span class="text-gray-700 flex-1">{{ ing.name }}</span>
                <span class="text-gray-400 text-xs">
                  {{ ing.quantity ?? "" }} {{ ing.unit ?? "" }}
                  <span v-if="ing.normalized_grams" class="text-gray-300">({{ Math.round(ing.normalized_grams) }} г)</span>
                </span>
                <button @click="startEdit(ing)" class="text-gray-400 hover:text-blue-500 text-xs">✏️</button>
                <button @click="removeIngredient(r.id, ing.id)" class="text-gray-400 hover:text-red-500 text-xs">✕</button>
              </div>
            </li>
          </ul>
          <p v-else class="text-xs text-gray-400 italic">Ингредиенты не указаны</p>

          <!-- Primary action: add to event -->
          <button @click="openAddToEvent(r.id)"
            class="w-full bg-green-600 text-white py-2 rounded-lg text-sm font-medium mt-2">
            ➕ Добавить в событие
          </button>

          <div class="flex gap-3 pt-2 border-t border-gray-100">
            <a v-if="r.source_url" :href="r.source_url" target="_blank"
              class="text-xs text-green-600 underline">Открыть оригинал →</a>
            <button @click="deleteRecipe(r.id)" class="text-xs text-red-500 ml-auto">Удалить рецепт</button>
          </div>
        </div>
      </div>
    </div>

    <!-- "Add to event" modal -->
    <div v-if="addToEventFor !== null" class="fixed inset-0 bg-black/40 z-40 flex items-end"
      @click.self="addToEventFor = null">
      <div class="bg-white rounded-t-2xl w-full max-h-[70dvh] overflow-y-auto p-4 max-w-[480px] mx-auto">
        <h3 class="font-semibold text-gray-800 mb-3">В какое событие добавить?</h3>
        <div v-if="!userEvents.length" class="text-center py-6 text-gray-400 text-sm">
          У тебя ещё нет событий. Создай событие на вкладке «События».
        </div>
        <div v-else class="space-y-2">
          <button v-for="ev in userEvents" :key="ev.id"
            :disabled="addingToEventBusy"
            @click="attachToEvent(ev.id, addToEventFor!)"
            class="w-full flex items-center justify-between p-3 border border-gray-200 rounded-lg text-left hover:border-green-300 disabled:opacity-50">
            <div>
              <p class="font-medium text-sm text-gray-800">{{ ev.title }}</p>
              <p class="text-xs text-gray-500">
                <span v-if="ev.date">{{ new Date(ev.date).toLocaleDateString("ru-RU") }} ·</span>
                {{ ev.event_recipes.length }} рецептов · {{ ev.guests_count }} гостей
              </p>
            </div>
            <span class="text-green-600 text-sm">→</span>
          </button>
        </div>
        <button @click="addToEventFor = null"
          class="w-full mt-3 border border-gray-200 text-gray-600 py-2 rounded-lg text-sm">Отмена</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input { @apply w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-green-400; }
.btn-primary { @apply bg-green-600 text-white py-2 rounded-lg text-sm font-medium disabled:opacity-50; }
.btn-ghost { @apply border border-gray-200 text-gray-600 py-2 rounded-lg text-sm; }
</style>
