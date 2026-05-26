import { createApp } from "vue";
import "./style.css";
import App from "./App.vue";
import router from "./router";

// Set page title
document.title = "Поляна";

// Initialize Telegram WebApp — expand to full height and signal ready
const tg = (window as any).Telegram?.WebApp;
if (tg) {
  try {
    tg.ready();
    tg.expand();
    // Disable vertical swipe-down dismiss (so scroll content doesn't close the app)
    if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
  } catch {
    // ignore — not all clients support all methods
  }
}

createApp(App).use(router).mount("#app");
