"""Background reminder loop. Sends "tomorrow is event X" notifications via Telegram Bot API."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, select

from app.config import settings
from app.db import async_session_factory
from app.models import Event

log = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 60  # how often to scan for due reminders
REMIND_BEFORE = timedelta(hours=24)  # send "tomorrow!" 24h before event


async def _send_telegram(chat_id: int, text: str) -> bool:
    if not settings.bot_token:
        return False
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            })
            return r.status_code == 200
    except Exception as e:
        log.warning("Failed to send Telegram reminder: %s", e)
        return False


async def _check_and_send_due_reminders() -> int:
    """Find events with date within [now+REMIND_BEFORE-window, now+REMIND_BEFORE]
    that haven't been notified yet. Send notification, mark reminder_sent=True."""
    now = datetime.now(timezone.utc)
    target_min = now + REMIND_BEFORE - timedelta(minutes=5)  # 5-min lookback for safety
    target_max = now + REMIND_BEFORE

    sent = 0
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(
                and_(
                    Event.date.isnot(None),
                    Event.date >= target_min,
                    Event.date <= target_max,
                    Event.reminder_sent.is_(False),
                    Event.telegram_user_id.isnot(None),
                )
            )
        )
        events = result.scalars().all()

        for ev in events:
            text = (
                f"⏰ Напоминание!\n\n"
                f"Завтра у тебя мероприятие — *{ev.title}*\n"
                f"📅 {ev.date.strftime('%d.%m.%Y %H:%M')}\n"
                f"👥 Гостей: {ev.guests_count}\n\n"
                f"Открой Mini App чтобы посмотреть закупку и таймлайн 👇"
            )
            if await _send_telegram(ev.telegram_user_id, text):
                ev.reminder_sent = True
                sent += 1

        if sent:
            await session.commit()
    return sent


async def reminder_loop():
    """Run forever, checking for due reminders every CHECK_INTERVAL_SEC seconds."""
    log.info("Reminder loop started (check every %ds, remind %s before)", CHECK_INTERVAL_SEC, REMIND_BEFORE)
    while True:
        try:
            n = await _check_and_send_due_reminders()
            if n:
                log.info("Sent %d reminders", n)
        except Exception as e:
            log.exception("Reminder loop iteration failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SEC)
