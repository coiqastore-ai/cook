import { ref } from "vue";

export interface Timer {
  id: number;
  name: string;
  durationSec: number;       // total duration when started
  endsAt: number;            // unix ms when timer should fire
  paused: boolean;
  pausedRemainingSec?: number;
  firedAt?: number;          // when expired (to keep showing briefly)
}

const STORAGE_KEY = "polyana_timers_v2";
const timers = ref<Timer[]>([]);
const tick = ref(0);          // increments every second, drives reactivity

let nextId = 1;
const notifiedIds = new Set<number>();

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      timers.value = JSON.parse(raw);
      nextId = Math.max(0, ...timers.value.map(t => t.id)) + 1;
    }
  } catch {}
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(timers.value));
}

export function addTimer(name: string, minutes: number) {
  const dur = Math.max(1, Math.round(minutes * 60));
  timers.value.push({
    id: nextId++,
    name: name.trim() || "Таймер",
    durationSec: dur,
    endsAt: Date.now() + dur * 1000,
    paused: false,
  });
  save();
}

export function removeTimer(id: number) {
  timers.value = timers.value.filter(t => t.id !== id);
  notifiedIds.delete(id);
  save();
}

export function togglePause(id: number) {
  const t = timers.value.find(x => x.id === id);
  if (!t) return;
  if (t.paused) {
    t.endsAt = Date.now() + (t.pausedRemainingSec ?? 0) * 1000;
    t.paused = false;
    t.pausedRemainingSec = undefined;
  } else {
    t.pausedRemainingSec = Math.max(0, Math.round((t.endsAt - Date.now()) / 1000));
    t.paused = true;
  }
  save();
}

export function remaining(t: Timer): number {
  if (t.paused) return t.pausedRemainingSec ?? 0;
  return Math.max(0, Math.round((t.endsAt - Date.now()) / 1000));
}

export function isDone(t: Timer): boolean {
  return !t.paused && t.endsAt <= Date.now();
}

export function fmt(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// Small beep via WebAudio — no asset needed
function beep() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start();
    osc.stop(ctx.currentTime + 0.6);
  } catch {}
}

function notifyDone(t: Timer) {
  beep(); beep();
  const tg = (window as any).Telegram?.WebApp;
  try { tg?.HapticFeedback?.notificationOccurred?.("success"); } catch {}
  try { tg?.showAlert?.(`⏰ Готово: ${t.name}`); } catch {
    alert(`⏰ Готово: ${t.name}`);
  }
  try {
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification("⏰ Поляна — таймер", { body: t.name });
    }
  } catch {}
}

function startTicking() {
  setInterval(() => {
    tick.value++;
    for (const t of timers.value) {
      if (isDone(t) && !notifiedIds.has(t.id)) {
        notifiedIds.add(t.id);
        t.firedAt = Date.now();
        notifyDone(t);
        save();
      }
    }
  }, 1000);
}

// Init once on module load
load();
startTicking();
try {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
} catch {}

export function useTimers() {
  return { timers, tick };
}
