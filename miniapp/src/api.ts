const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---------- Types ----------

export interface Ingredient {
  id: number; name: string; quantity: number | null; unit: string | null; normalized_grams: number | null;
}
export interface Recipe {
  id: number; title: string; source_url: string | null; base_servings: number;
  cook_time_min: number | null; prep_time_min: number | null; instructions: string[] | null;
  ingredients: Ingredient[];
}
export interface EventRecipe {
  recipe_id: number; servings_multiplier: number; recipe: Recipe;
}
export interface Event {
  id: number; title: string; date: string | null; guests_count: number; notes: string | null;
  event_recipes: EventRecipe[];
}
export interface ShoppingItem {
  id: number; event_id: number; ingredient_name: string;
  total_grams: number | null; total_display: string | null; bought: boolean;
}
export interface TimelineTask {
  id: number; event_id: number; recipe_id: number | null;
  offset_hours: number; action: string; duration_min: number | null;
}

// ---------- Events ----------

export const api = {
  events: {
    list: () => req<Event[]>("GET", "/events/"),
    get: (id: number) => req<Event>("GET", `/events/${id}`),
    create: (data: { title: string; date?: string | null; guests_count?: number; notes?: string }) =>
      req<Event>("POST", "/events/", data),
    update: (id: number, data: Partial<Event>) => req<Event>("PATCH", `/events/${id}`, data),
    delete: (id: number) => req<void>("DELETE", `/events/${id}`),
    addRecipe: (eventId: number, recipeId: number, multiplier = 1) =>
      req<Event>("POST", `/events/${eventId}/recipes`, { recipe_id: recipeId, servings_multiplier: multiplier }),
    updateMultiplier: (eventId: number, recipeId: number, multiplier: number) =>
      req<Event>("PATCH", `/events/${eventId}/recipes/${recipeId}`, { servings_multiplier: multiplier }),
    removeRecipe: (eventId: number, recipeId: number) =>
      req<Event>("DELETE", `/events/${eventId}/recipes/${recipeId}`),
  },

  recipes: {
    list: () => req<Recipe[]>("GET", "/recipes/"),
    get: (id: number) => req<Recipe>("GET", `/recipes/${id}`),
    import: (url: string) => req<Recipe>("POST", "/recipes/import", { url }),
  },

  shopping: {
    get: (eventId: number) => req<ShoppingItem[]>("GET", `/shopping/${eventId}`),
    toggle: (eventId: number, itemId: number, bought: boolean) =>
      req<ShoppingItem>("PATCH", `/shopping/${eventId}/items/${itemId}`, { bought }),
    exportText: (eventId: number) => req<string>("GET", `/shopping/${eventId}/export`),
  },

  timeline: {
    get: (eventId: number) => req<TimelineTask[]>("GET", `/timeline/${eventId}`),
    regenerate: (eventId: number) => req<TimelineTask[]>("POST", `/timeline/${eventId}/regenerate`),
  },

  calendar: {
    status: () => req<{ connected: boolean }>("GET", "/calendar/status"),
    sync: () => req<{ created: number; updated: number }>("POST", "/calendar/sync", {}),
    authStart: () => req<{ url: string }>("GET", "/calendar/oauth/start"),
  },
};
