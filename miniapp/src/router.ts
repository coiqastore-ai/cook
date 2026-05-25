import { createRouter, createWebHistory } from "vue-router";
import EventsView from "./views/EventsView.vue";
import EventDetailView from "./views/EventDetailView.vue";
import RecipesView from "./views/RecipesView.vue";
import ShoppingView from "./views/ShoppingView.vue";
import TimelineView from "./views/TimelineView.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: EventsView },
    { path: "/events/:id", component: EventDetailView, props: true },
    { path: "/recipes", component: RecipesView },
    { path: "/events/:id/shopping", component: ShoppingView, props: true },
    { path: "/events/:id/timeline", component: TimelineView, props: true },
  ],
});
