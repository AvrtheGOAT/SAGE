"""Fires scheduled reminders into the main event queue and re-queues unanswered ones.
The main loop owns the mic/speaker, so this module never touches audio directly."""
import threading
import time
from datetime import datetime

import config


class ReminderScheduler(threading.Thread):
    def __init__(self, events_q):
        super().__init__(daemon=True)
        self.q = events_q
        self._fired_today: set[str] = set()
        self._day = datetime.now().date()

    def run(self):
        while True:
            now = datetime.now()
            if now.date() != self._day:          # new day: reset
                self._day, self._fired_today = now.date(), set()
            hhmm = now.strftime("%H:%M")
            for r in config.REMINDERS:
                key = f"{r.time}|{r.label}"
                if r.time == hhmm and key not in self._fired_today:
                    self._fired_today.add(key)
                    self.q.put(("reminder", r, 1))
            time.sleep(15)

    def retry_later(self, reminder, attempt: int):
        threading.Timer(config.REMINDER_RETRY_SECONDS,
                        lambda: self.q.put(("reminder", reminder, attempt))).start()

    def fire_now(self, reminder):
        """For demos: trigger a reminder immediately."""
        self.q.put(("reminder", reminder, 1))
