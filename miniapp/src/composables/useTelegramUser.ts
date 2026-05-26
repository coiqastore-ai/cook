/** Robust Telegram WebApp user-id extraction with fallback parsing of raw initData. */

export function getTelegramUserId(): number | null {
  const tg = (window as any).Telegram?.WebApp;
  if (!tg) return null;

  // Primary path
  const direct = tg.initDataUnsafe?.user?.id;
  if (typeof direct === "number" && direct > 0) return direct;

  // Fallback: parse raw initData query string (e.g. "user=%7B%22id%22%3A123…")
  const raw: string = tg.initData || "";
  if (raw) {
    try {
      const params = new URLSearchParams(raw);
      const userStr = params.get("user");
      if (userStr) {
        const user = JSON.parse(userStr);
        if (typeof user?.id === "number") return user.id;
      }
    } catch {}
  }
  return null;
}

export function telegramDebugInfo(): string {
  const tg = (window as any).Telegram?.WebApp;
  if (!tg) return "Telegram.WebApp = undefined";
  const info = {
    version: tg.version,
    platform: tg.platform,
    initDataLen: (tg.initData || "").length,
    hasUser: !!tg.initDataUnsafe?.user,
    userId: tg.initDataUnsafe?.user?.id ?? null,
    rawParsedUserId: (() => {
      try {
        const p = new URLSearchParams(tg.initData || "");
        const u = p.get("user");
        return u ? JSON.parse(u)?.id : null;
      } catch { return null; }
    })(),
  };
  return JSON.stringify(info, null, 2);
}
