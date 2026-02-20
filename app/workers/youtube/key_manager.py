"""
app/workers/youtube/key_manager.py

Manages a pool of YouTube Data API v3 keys across multiple Google Cloud projects.
Automatically rotates to the next available key when one hits 403 quota exhaustion.

SETUP in .env:
    YOUTUBE_API_KEY_1=AIzaSy...
    YOUTUBE_API_KEY_2=AIzaSy...
    ...
    YOUTUBE_API_KEY_20=AIzaSy...

TARGET: 20 keys × 10,000 units/day = 200,000 units/day
  → ~2,000 search.list calls/day
  → ~100,000 raw video results/day
"""

import os
import threading
from datetime import datetime, date


class APIKeyManager:
    """
    Thread-safe YouTube API key pool with:
    - Auto-rotation on 403 quota exceeded
    - Per-key usage tracking
    - Daily reset at midnight UTC
    - Exhaustion detection with logging
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._keys = self._load_keys()
        self._exhausted: set[str] = set()
        self._usage: dict[str, int] = {k: 0 for k in self._keys}
        self._current_index = 0
        self._reset_date = date.today()

        print(f"🔑 APIKeyManager initialized with {len(self._keys)} keys")

    # ------------------------------------------------------------------
    # PRIVATE
    # ------------------------------------------------------------------

    def _load_keys(self) -> list[str]:
        """
        Reads keys from environment.
        Supports both numbered keys (YOUTUBE_API_KEY_1..N)
        and the legacy single/backup key env vars.
        """
        keys = []

        # ── Numbered pool (primary method) ──
        i = 1
        while True:
            key = os.getenv(f"YOUTUBE_API_KEY_{i}")
            if not key:
                break
            keys.append(key.strip())
            i += 1

        # ── Legacy fallback ──
        for legacy in ["YOUTUBE_API_KEY", "EMERGENCY_BACKUP_KEY"]:
            val = os.getenv(legacy, "").strip()
            if val and val not in keys:
                keys.append(val)

        if not keys:
            raise EnvironmentError(
                "❌ No YouTube API keys found! "
                "Set YOUTUBE_API_KEY_1 ... YOUTUBE_API_KEY_N in your .env"
            )

        return keys

    def _daily_reset_if_needed(self):
        """Resets exhausted set + usage counters at the start of each UTC day."""
        today = date.today()
        if today != self._reset_date:
            self._exhausted.clear()
            self._usage = {k: 0 for k in self._keys}
            self._reset_date = today
            print(f"🔄 [{datetime.utcnow().strftime('%H:%M UTC')}] Daily key quota reset — all {len(self._keys)} keys active")

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------

    def get_key(self) -> str | None:
        """
        Returns the next available (non-exhausted) key.
        Cycles through the pool in round-robin order.
        Returns None if ALL keys are exhausted for today.
        """
        with self._lock:
            self._daily_reset_if_needed()

            available = [k for k in self._keys if k not in self._exhausted]
            if not available:
                print("💀 ALL API keys exhausted for today. Worker will halt.")
                return None

            # Round-robin from current index
            start = self._current_index % len(self._keys)
            for offset in range(len(self._keys)):
                idx = (start + offset) % len(self._keys)
                key = self._keys[idx]
                if key not in self._exhausted:
                    self._current_index = idx
                    self._usage[key] = self._usage.get(key, 0) + 1
                    return key

            return None

    def mark_exhausted(self, key: str):
        """
        Call this when a 403 response is received for a key.
        The key will be skipped for the rest of the day.
        """
        with self._lock:
            self._exhausted.add(key)
            remaining = len(self._keys) - len(self._exhausted)
            print(
                f"⚠️  Key ...{key[-8:]} exhausted. "
                f"{remaining}/{len(self._keys)} keys still active."
            )

    def status(self) -> dict:
        """Returns a snapshot of current pool health."""
        with self._lock:
            self._daily_reset_if_needed()
            return {
                "total_keys": len(self._keys),
                "exhausted": len(self._exhausted),
                "active": len(self._keys) - len(self._exhausted),
                "usage_per_key": dict(self._usage),
                "reset_date": str(self._reset_date),
            }