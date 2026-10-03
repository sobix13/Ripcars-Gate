"""Keeping the bot alive and letting someone check on it.

Four things live here. A systemd watchdog so a hung process gets restarted
instead of sitting there looking healthy, a daily database backup with
retention, a small ring buffer of recent errors, and the snapshot behind the
Health screen.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import sqlite3
import time
import traceback
import secrets
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("ripcarsgate.health")

STARTED_AT = time.monotonic()
STARTED_WALL = datetime.now(timezone.utc)

BACKUP_KEEP = 7
BACKUP_INTERVAL_HOURS = 24


# ---------------------------------------------------------------- watchdog

class Watchdog:
    """Talks to systemd over NOTIFY_SOCKET.

    Restart=always only catches a process that dies. A bot that deadlocks
    stays 'running' forever. With Type=notify plus WatchdogSec, systemd kills
    and restarts the process as soon as the heartbeat stops arriving.
    """

    def __init__(self) -> None:
        raw = os.environ.get("NOTIFY_SOCKET", "")
        self.address = ("\0" + raw[1:]) if raw.startswith("@") else raw
        self.enabled = bool(self.address)
        self.interval = self._interval()
        self._sock: socket.socket | None = None
        if self.enabled:
            try:
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            except OSError as exc:
                log.warning("watchdog socket unavailable: %s", exc)
                self.enabled = False

    @staticmethod
    def _interval() -> float:
        usec = os.environ.get("WATCHDOG_USEC")
        if not usec or not usec.isdigit():
            return 30.0
        # systemd expects a ping at least twice per window
        return max(5.0, int(usec) / 1_000_000 / 2)

    def send(self, message: str) -> None:
        if not self.enabled or self._sock is None:
            return
        try:
            self._sock.sendto(message.encode("utf-8"), self.address)
        except OSError as exc:
            log.warning("watchdog send failed: %s", exc)

    def ready(self) -> None:
        self.send("READY=1")

    def beat(self) -> None:
        self.send("WATCHDOG=1")

    def status(self, text: str) -> None:
        self.send(f"STATUS={text[:200]}")

    def stopping(self) -> None:
        self.send("STOPPING=1")


# ------------------------------------------------------------- error buffer

class ErrorLog:
    """The last few failures, so Health can show them without an SSH session."""

    def __init__(self, size: int = 20) -> None:
        self.entries: deque[dict] = deque(maxlen=size)
        self.total = 0

    def record(self, where: str, exc: BaseException) -> dict:
        self.total += 1
        entry = {
            "id": "RCG-" + datetime.now(timezone.utc).strftime("%y%m%d-")
                  + secrets.token_hex(3).upper(),
            "at": datetime.now(timezone.utc),
            "where": where,
            "type": type(exc).__name__,
            "message": str(exc)[:300],
            "trace": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-1500:],
        }
        self.entries.append(entry)
        log.error(
            "recorded error id=%s where=%s type=%s message=%s",
            entry["id"], entry["where"], entry["type"], entry["message"],
        )
        return entry

    def recent(self, count: int = 5) -> list[dict]:
        return list(self.entries)[-count:][::-1]

    def since(self, hours: int = 24) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return sum(1 for e in self.entries if e["at"] >= cutoff)


# ----------------------------------------------------------------- backups

def backup_path(db_path: str, when: datetime | None = None) -> Path:
    when = when or datetime.now(timezone.utc)
    source = Path(db_path)
    folder = source.parent / "backups"
    stamp = when.strftime("%Y%m%d-%H%M%S")
    return folder / f"{source.stem}-{stamp}.sqlite3"


def run_backup(db_path: str, keep: int = BACKUP_KEEP,
               when: datetime | None = None) -> Path | None:
    """Copy the database with sqlite's own backup API, then prune old copies.

    A plain file copy of a live database can capture a half written page. The
    backup API takes a consistent snapshot while the bot keeps writing.
    """
    source = Path(db_path)
    if not source.exists():
        return None

    target = backup_path(db_path, when)
    target.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    prune_backups(db_path, keep)
    return target


def list_backups(db_path: str) -> list[Path]:
    source = Path(db_path)
    folder = source.parent / "backups"
    if not folder.is_dir():
        return []
    found = sorted(folder.glob(f"{source.stem}-*.sqlite3"))
    return found


def prune_backups(db_path: str, keep: int = BACKUP_KEEP) -> list[Path]:
    found = list_backups(db_path)
    removed = []
    for old in found[:-keep] if keep > 0 else found:
        try:
            old.unlink()
            removed.append(old)
        except OSError as exc:
            log.warning("could not remove %s: %s", old, exc)
    return removed


# ------------------------------------------------------------------ health

def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_size(num: int) -> str:
    step = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if step < 1024 or unit == "GB":
            return f"{step:.0f} {unit}" if unit == "B" else f"{step:.1f} {unit}"
        step /= 1024
    return f"{step:.1f} GB"


def latency_ms(raw: float | None) -> int | None:
    """discord.py reports nan before the first heartbeat lands."""
    if raw is None:
        return None
    if raw != raw or raw in (float("inf"), float("-inf")):
        return None
    return int(raw * 1000)


async def db_probe(db) -> tuple[bool, int | None]:
    """One real query. Reports whether it worked and how long it took."""
    start = time.perf_counter()
    try:
        await db.query("SELECT 1 AS ok")
    except Exception:  # noqa: BLE001 - any failure means unhealthy
        return False, None
    return True, int((time.perf_counter() - start) * 1000)


async def snapshot(bot, guild_id: int | None = None) -> dict:
    db_ok, db_ms = await db_probe(bot.db)
    path = Path(getattr(bot, "db_path", "") or bot.db.path)
    size = path.stat().st_size if path.exists() else 0
    backups = list_backups(str(path))

    pending = 0
    try:
        rows = await bot.db.query("SELECT COUNT(*) AS waiting FROM sessions WHERE verified=0")
        pending = rows[0]["waiting"]
    except Exception:  # noqa: BLE001
        db_ok = False

    errors = getattr(bot, "errors", None)
    watchdog = getattr(bot, "watchdog", None)
    verification = None
    if guild_id is not None:
        try:
            verification = await bot.db.verification_stats(guild_id)
        except Exception:  # noqa: BLE001
            db_ok = False

    return {
        "uptime": time.monotonic() - STARTED_AT,
        "version": getattr(bot, "version", "unknown"),
        "started": STARTED_WALL,
        "guilds": len(bot.guilds),
        "latency_ms": latency_ms(getattr(bot, "latency", None)),
        "db_ok": db_ok,
        "db_ms": db_ms,
        "db_size": size,
        "db_path": str(path),
        "backups": len(backups),
        "last_backup": backups[-1].name if backups else None,
        "pending": pending,
        "verification": verification,
        "errors_total": errors.total if errors else 0,
        "errors_24h": errors.since(24) if errors else 0,
        "recent_errors": errors.recent(3) if errors else [],
        "watchdog": bool(watchdog and watchdog.enabled),
        "watchdog_interval": watchdog.interval if watchdog else None,
        "healthy": db_ok and not bot.is_closed(),
    }


# ------------------------------------------------------------ background

async def _wait_ready(bot) -> bool:
    """False means the client never came up, so the loop should stand down."""
    try:
        await bot.wait_until_ready()
        return True
    except RuntimeError:
        return False


async def heartbeat_loop(bot) -> None:
    """Ping systemd only while the bot can still answer a database query."""
    watchdog: Watchdog = bot.watchdog
    if not watchdog.enabled:
        log.info("watchdog disabled, NOTIFY_SOCKET is not set")
        return
    if not await _wait_ready(bot):
        return
    watchdog.ready()
    while not bot.is_closed():
        try:
            ok, _ = await db_probe(bot.db)
            if ok and bot.is_ready() and latency_ms(bot.latency) is not None:
                watchdog.beat()
                watchdog.status(f"{len(bot.guilds)} guilds")
            else:
                log.error("heartbeat withheld, bot is not answering")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # A crash here would end the loop and leave a hung bot looking fine.
            log.exception("heartbeat check failed")
            if getattr(bot, "errors", None):
                entry = bot.errors.record("heartbeat", exc)
                reporter = getattr(bot, "alerts", None)
                if getattr(type(reporter), "notify_all", None):
                    await reporter.notify_all("heartbeat", entry)
        await asyncio.sleep(watchdog.interval)


async def backup_loop(bot) -> None:
    if not await _wait_ready(bot):
        return
    while not bot.is_closed():
        try:
            target = await asyncio.to_thread(run_backup, bot.db.path)
            coordination = getattr(bot, "coordination_path", None)
            if coordination:
                await asyncio.to_thread(run_backup, coordination)
            if target:
                log.info("backup written to %s", target)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("backup failed")
            if getattr(bot, "errors", None):
                entry = bot.errors.record("backup", exc)
                reporter = getattr(bot, "alerts", None)
                if getattr(type(reporter), "notify_all", None):
                    await reporter.notify_all("backup", entry)
        await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
