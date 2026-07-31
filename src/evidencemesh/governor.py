"""Fail-closed, process-shared dispatch budgets for the closed alpha.

The governor stores only pseudonymous session identifiers and bounded counters.
It never stores queries, URLs, response data, credentials, or exception text.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import stat
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, TypeVar

import httpx

from evidencemesh.errors import BudgetConfigurationError, BudgetExceededError

_SCHEMA_VERSION: Final = "evidencemesh.closed-alpha-governor.v1"
_PARTICIPANT_PATTERN: Final = re.compile(r"^p-[0-9a-f]{16}$")
_SESSION_PATTERN: Final = re.compile(r"^s-[0-9a-f]{32}$")
_PROVIDER_PATTERN: Final = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_INTENT_KINDS: Final = frozenset({"provider", "fetch", "robots", "redirect"})
_ENV_LEDGER: Final = "EVIDENCEMESH_CLOSED_ALPHA_LEDGER"
_ENV_PARTICIPANT: Final = "EVIDENCEMESH_CLOSED_ALPHA_PARTICIPANT"
_ENV_SESSION: Final = "EVIDENCEMESH_CLOSED_ALPHA_SESSION"
_ENV_PROFILE: Final = "EVIDENCEMESH_CLOSED_ALPHA_PROFILE"
_ENV_NAMES: Final = (_ENV_LEDGER, _ENV_PARTICIPANT, _ENV_SESSION, _ENV_PROFILE)
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class ClosedAlphaPolicy:
    """Frozen A0 ceilings. Limits are maxima, never targets."""

    sessions_total_max: int = 40
    sessions_per_participant_max: int = 5
    provider_attempts_per_session_max: int = 6
    provider_attempts_total_max: int = 240
    tavily_attempts_community_session_max: int = 0
    tavily_attempts_quality_session_max: int = 4
    tavily_attempts_total_max: int = 40
    concurrent_sessions_max: int = 2
    request_starts_per_minute_max: int = 10

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values.values()
        ):
            raise BudgetConfigurationError(
                "closed-alpha policy limits must be non-negative integers"
            )
        positive = (
            self.sessions_total_max,
            self.sessions_per_participant_max,
            self.provider_attempts_per_session_max,
            self.provider_attempts_total_max,
            self.concurrent_sessions_max,
            self.request_starts_per_minute_max,
        )
        if any(value < 1 for value in positive):
            raise BudgetConfigurationError("closed-alpha primary policy limits must be positive")
        if self.sessions_per_participant_max > self.sessions_total_max:
            raise BudgetConfigurationError("participant session limit exceeds the global limit")
        if self.provider_attempts_per_session_max > self.provider_attempts_total_max:
            raise BudgetConfigurationError("session attempt limit exceeds the global limit")
        if self.tavily_attempts_quality_session_max > self.provider_attempts_per_session_max:
            raise BudgetConfigurationError("Tavily session limit exceeds the session attempt limit")
        if self.tavily_attempts_total_max > self.provider_attempts_total_max:
            raise BudgetConfigurationError("Tavily global limit exceeds the global attempt limit")
        if self.tavily_attempts_community_session_max != 0:
            raise BudgetConfigurationError("community Tavily attempts must remain disabled")

    @property
    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ClosedAlphaSession:
    """Pseudonymous execution context for one single-task alpha session."""

    participant_code: str
    session_code: str
    profile: str

    def __post_init__(self) -> None:
        if _PARTICIPANT_PATTERN.fullmatch(self.participant_code) is None:
            raise BudgetConfigurationError("closed-alpha participant code is invalid")
        if _SESSION_PATTERN.fullmatch(self.session_code) is None:
            raise BudgetConfigurationError("closed-alpha session code is invalid")
        if self.profile not in {"community", "quality"}:
            raise BudgetConfigurationError("closed-alpha profile must be community or quality")


@dataclass(frozen=True, slots=True)
class DispatchIntent:
    """One outbound start to reserve without retaining its destination."""

    kind: str
    provider: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _INTENT_KINDS:
            raise BudgetConfigurationError("closed-alpha dispatch intent kind is invalid")
        if self.kind == "provider":
            if self.provider is None or _PROVIDER_PATTERN.fullmatch(self.provider) is None:
                raise BudgetConfigurationError(
                    "provider dispatch intent requires a safe provider name"
                )
        elif self.provider is not None:
            raise BudgetConfigurationError("non-provider dispatch intents cannot name a provider")


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    """Opaque single-use authorization bound to one governor and session."""

    token: str
    session_code: str
    kind: str
    provider: str | None
    _governor_id: str = field(repr=False)


class SQLiteBudgetGovernor:
    """Atomic local coordinator for CLI/MCP processes sharing one SQLite ledger.

    This is deliberately a single-host scope. Independent ledgers on multiple
    machines do not form a global budget and must never be described as one.
    """

    _AUDITED_PROVIDERS: Final = {
        "evidencemesh.providers.arxiv.ArxivProvider": "arxiv",
        "evidencemesh.providers.crossref.CrossrefProvider": "crossref",
        "evidencemesh.providers.github.GitHubProvider": "github",
        "evidencemesh.providers.searxng.SearxngProvider": "searxng",
        "evidencemesh.providers.tavily.TavilyProvider": "tavily",
        "evidencemesh.providers.wikipedia.WikipediaProvider": "wikipedia",
    }

    def __init__(
        self,
        ledger_path: Path,
        session: ClosedAlphaSession,
        policy: ClosedAlphaPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.session = session
        self.policy = policy or ClosedAlphaPolicy()
        self._clock = clock
        self._owner_id = secrets.token_hex(16)
        self._governor_id = secrets.token_hex(16)
        self._active_permit: ContextVar[DispatchPermit | None] = ContextVar(
            f"evidencemesh_closed_alpha_permit_{self._governor_id}",
            default=None,
        )
        self._lock = asyncio.Lock()
        self._attached_clients: dict[int, httpx.AsyncClient] = {}
        self._opened = False
        self._closed = False
        self._poisoned = False
        self._prepare_ledger_file()
        self._initialize_database()

    @property
    def enabled(self) -> bool:
        return not self._closed

    @property
    def scope(self) -> str:
        return "single_host_shared_sqlite"

    @classmethod
    def environment_requested(cls) -> bool:
        return any(os.getenv(name) is not None for name in _ENV_NAMES)

    @classmethod
    def from_env(cls) -> SQLiteBudgetGovernor | None:
        values = {name: os.getenv(name) for name in _ENV_NAMES}
        if all(value is None for value in values.values()):
            return None
        if any(value is None or not value for value in values.values()):
            raise BudgetConfigurationError("closed-alpha governor environment is incomplete")
        ledger = Path(str(values[_ENV_LEDGER]))
        if not ledger.is_absolute():
            raise BudgetConfigurationError("closed-alpha ledger path must be absolute")
        return cls(
            ledger,
            ClosedAlphaSession(
                participant_code=str(values[_ENV_PARTICIPANT]),
                session_code=str(values[_ENV_SESSION]),
                profile=str(values[_ENV_PROFILE]),
            ),
        )

    @classmethod
    def validate_provider_configuration(
        cls,
        provider_names: Sequence[str],
        searxng_fallback_urls: Sequence[str],
    ) -> None:
        """Reject configurations that cannot build only audited providers."""

        audited_names = frozenset(cls._AUDITED_PROVIDERS.values())
        unsupported = sorted(set(provider_names) - audited_names)
        if unsupported:
            raise BudgetConfigurationError(
                "closed-alpha mode accepts only audited single-dispatch HTTPX providers"
            )
        if searxng_fallback_urls:
            raise BudgetConfigurationError(
                "closed-alpha mode forbids automatic SearXNG fallback dispatches"
            )

    def validate_provider(self, provider: object, client: httpx.AsyncClient) -> str:
        provider_type = f"{type(provider).__module__}.{type(provider).__qualname__}"
        expected_name = self._AUDITED_PROVIDERS.get(provider_type)
        actual_name = getattr(provider, "name", None)
        if expected_name is None or actual_name != expected_name:
            raise BudgetConfigurationError(
                "closed-alpha mode accepts only audited single-dispatch HTTPX providers"
            )
        if getattr(provider, "client", None) is not client:
            raise BudgetConfigurationError(
                "closed-alpha provider does not use the governed HTTPX client"
            )
        return expected_name

    def attach_client(self, client: httpx.AsyncClient) -> None:
        if self._closed:
            raise BudgetConfigurationError("closed-alpha governor is closed")
        client_id = id(client)
        if client_id in self._attached_clients:
            return
        client.event_hooks["request"].insert(0, self._on_request)
        self._attached_clients[client_id] = client

    async def reserve_batch(
        self,
        intents: Sequence[DispatchIntent],
    ) -> list[DispatchPermit]:
        if self._closed:
            raise BudgetConfigurationError("closed-alpha governor is closed")
        if self._poisoned:
            raise BudgetConfigurationError("closed-alpha governor is fail-closed")
        frozen = tuple(intents)
        if not frozen:
            raise BudgetConfigurationError("dispatch reservation batch cannot be empty")
        now = self._clock()
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            self._poisoned = True
            raise BudgetConfigurationError("closed-alpha governor clock is invalid")
        tokens = tuple(secrets.token_hex(16) for _ in frozen)
        await self._database_call(lambda: self._reserve_sync(frozen, tokens, float(now)))
        self._opened = True
        return [
            DispatchPermit(
                token=token,
                session_code=self.session.session_code,
                kind=intent.kind,
                provider=intent.provider,
                _governor_id=self._governor_id,
            )
            for intent, token in zip(frozen, tokens, strict=True)
        ]

    @contextmanager
    def capture(self, permit: DispatchPermit) -> Iterator[None]:
        if self._closed or self._poisoned:
            raise BudgetConfigurationError("closed-alpha governor is not dispatchable")
        if permit._governor_id != self._governor_id:
            raise BudgetConfigurationError("dispatch permit belongs to another governor")
        if permit.session_code != self.session.session_code:
            raise BudgetConfigurationError("dispatch permit belongs to another session")
        if self._active_permit.get() is not None:
            raise BudgetConfigurationError("nested dispatch permits are forbidden")
        token = self._active_permit.set(permit)
        try:
            yield
        finally:
            self._active_permit.reset(token)

    async def snapshot(self) -> dict[str, int | str | bool]:
        return await self._database_call(self._snapshot_sync)

    async def aclose(self) -> None:
        if self._closed:
            return
        try:
            if self._opened and not self._poisoned:
                await self._database_call(self._close_session_sync)
        finally:
            # Keep the request hook attached as a poison pill. A shared client
            # must not become ungoverned merely because its session was closed.
            self._closed = True

    async def _on_request(self, _: httpx.Request) -> None:
        if self._closed or self._poisoned:
            self._poisoned = True
            raise BudgetConfigurationError("closed-alpha governor is not dispatchable")
        permit = self._active_permit.get()
        if permit is None:
            self._poisoned = True
            raise BudgetConfigurationError("HTTP dispatch has no closed-alpha permit")
        now = self._clock()
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            self._poisoned = True
            raise BudgetConfigurationError("closed-alpha governor clock is invalid")
        await self._database_call(lambda: self._consume_sync(permit, float(now)))

    async def _database_call(self, operation: Callable[[], _T]) -> _T:
        async with self._lock:
            if self._closed or self._poisoned:
                raise BudgetConfigurationError("closed-alpha governor is fail-closed")
            try:
                self._assert_ledger_safe()
                return await asyncio.to_thread(operation)
            except BudgetExceededError:
                raise
            except BudgetConfigurationError:
                self._poisoned = True
                raise
            except (OSError, sqlite3.Error) as exc:
                self._poisoned = True
                raise BudgetConfigurationError("closed-alpha ledger operation failed") from exc

    def _prepare_ledger_file(self) -> None:
        if not self.ledger_path.is_absolute():
            raise BudgetConfigurationError("closed-alpha ledger path must be absolute")
        parent = self.ledger_path.parent
        if not parent.exists():
            try:
                parent.mkdir(mode=0o700, parents=False)
            except OSError as exc:
                raise BudgetConfigurationError(
                    "cannot create closed-alpha ledger directory"
                ) from exc
        try:
            parent_metadata = parent.lstat()
        except OSError as exc:
            raise BudgetConfigurationError("cannot inspect closed-alpha ledger directory") from exc
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent.is_symlink()
            or stat.S_IMODE(parent_metadata.st_mode) & 0o077
        ):
            raise BudgetConfigurationError("closed-alpha ledger directory is not private")
        try:
            if parent.resolve(strict=True) != parent.absolute():
                raise BudgetConfigurationError("closed-alpha ledger directory uses a symlink")
        except OSError as exc:
            raise BudgetConfigurationError("cannot resolve closed-alpha ledger directory") from exc
        if self.ledger_path.exists() or self.ledger_path.is_symlink():
            self._assert_ledger_safe()
            return
        try:
            descriptor = os.open(
                self.ledger_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.close(descriptor)
        except OSError as exc:
            raise BudgetConfigurationError("cannot create closed-alpha ledger") from exc
        self._assert_ledger_safe()

    def _assert_ledger_safe(self) -> None:
        try:
            metadata = self.ledger_path.lstat()
        except OSError as exc:
            raise BudgetConfigurationError("closed-alpha ledger is missing") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or self.ledger_path.is_symlink()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise BudgetConfigurationError("closed-alpha ledger permissions are unsafe")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.ledger_path,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize_database(self) -> None:
        try:
            with contextlib.closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_code TEXT PRIMARY KEY,
                        participant_code TEXT NOT NULL,
                        profile TEXT NOT NULL CHECK (profile IN ('community', 'quality')),
                        owner_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
                        opened_at REAL NOT NULL,
                        closed_at REAL
                    );
                    CREATE TABLE IF NOT EXISTS attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token TEXT NOT NULL UNIQUE,
                        session_code TEXT NOT NULL REFERENCES sessions(session_code),
                        kind TEXT NOT NULL,
                        provider TEXT,
                        reserved_at REAL NOT NULL,
                        dispatched INTEGER NOT NULL DEFAULT 0 CHECK (dispatched IN (0, 1)),
                        dispatched_at REAL
                    );
                    CREATE INDEX IF NOT EXISTS attempts_session_idx
                        ON attempts(session_code);
                    CREATE INDEX IF NOT EXISTS attempts_rate_idx
                        ON attempts(reserved_at);
                    """
                )
                expected = {
                    "schema_version": _SCHEMA_VERSION,
                    "policy_fingerprint": self.policy.fingerprint,
                    "policy": self.policy.canonical_json,
                }
                rows = {
                    str(row["key"]): str(row["value"])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
                if rows:
                    if any(rows.get(key) != value for key, value in expected.items()):
                        raise BudgetConfigurationError(
                            "closed-alpha ledger policy or schema drifted"
                        )
                else:
                    connection.executemany(
                        "INSERT INTO metadata(key, value) VALUES (?, ?)",
                        tuple(expected.items()),
                    )
                connection.commit()
        except BudgetConfigurationError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise BudgetConfigurationError("cannot initialize closed-alpha ledger") from exc
        self._assert_ledger_safe()

    def _reserve_sync(
        self,
        intents: tuple[DispatchIntent, ...],
        tokens: tuple[str, ...],
        now: float,
    ) -> None:
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                last_clock_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'last_clock'"
                ).fetchone()
                if last_clock_row is not None and now < float(last_clock_row["value"]):
                    raise BudgetConfigurationError("closed-alpha governor clock moved backwards")

                session_row = connection.execute(
                    "SELECT * FROM sessions WHERE session_code = ?",
                    (self.session.session_code,),
                ).fetchone()
                if session_row is None:
                    total_sessions = int(
                        connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                    )
                    participant_sessions = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE participant_code = ?",
                            (self.session.participant_code,),
                        ).fetchone()[0]
                    )
                    active_sessions = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
                        ).fetchone()[0]
                    )
                    if total_sessions >= self.policy.sessions_total_max:
                        raise BudgetExceededError("closed-alpha global session budget exhausted")
                    if participant_sessions >= self.policy.sessions_per_participant_max:
                        raise BudgetExceededError(
                            "closed-alpha participant session budget exhausted"
                        )
                    if active_sessions >= self.policy.concurrent_sessions_max:
                        raise BudgetExceededError(
                            "closed-alpha concurrent session budget exhausted"
                        )
                    connection.execute(
                        """
                        INSERT INTO sessions(
                            session_code, participant_code, profile, owner_id,
                            status, opened_at, closed_at
                        ) VALUES (?, ?, ?, ?, 'active', ?, NULL)
                        """,
                        (
                            self.session.session_code,
                            self.session.participant_code,
                            self.session.profile,
                            self._owner_id,
                            now,
                        ),
                    )
                else:
                    if (
                        session_row["participant_code"] != self.session.participant_code
                        or session_row["profile"] != self.session.profile
                    ):
                        raise BudgetConfigurationError("closed-alpha session identity drifted")
                    if (
                        session_row["status"] != "active"
                        or session_row["owner_id"] != self._owner_id
                    ):
                        raise BudgetConfigurationError(
                            "closed-alpha session is not owned by this process"
                        )

                batch_size = len(intents)
                session_attempts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE session_code = ?",
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_attempts = int(
                    connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
                )
                if session_attempts + batch_size > self.policy.provider_attempts_per_session_max:
                    raise BudgetExceededError("closed-alpha session dispatch budget exhausted")
                if global_attempts + batch_size > self.policy.provider_attempts_total_max:
                    raise BudgetExceededError("closed-alpha global dispatch budget exhausted")

                tavily_batch = sum(intent.provider == "tavily" for intent in intents)
                session_tavily = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE session_code = ? AND provider = 'tavily'
                        """,
                        (self.session.session_code,),
                    ).fetchone()[0]
                )
                global_tavily = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE provider = 'tavily'"
                    ).fetchone()[0]
                )
                tavily_session_max = (
                    self.policy.tavily_attempts_quality_session_max
                    if self.session.profile == "quality"
                    else self.policy.tavily_attempts_community_session_max
                )
                if session_tavily + tavily_batch > tavily_session_max:
                    raise BudgetExceededError("closed-alpha Tavily session budget exhausted")
                if global_tavily + tavily_batch > self.policy.tavily_attempts_total_max:
                    raise BudgetExceededError("closed-alpha global Tavily budget exhausted")

                recent_starts_or_slots = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM attempts
                        WHERE (dispatched = 0 AND reserved_at > ?)
                           OR (dispatched_at IS NOT NULL AND dispatched_at > ?)
                        """,
                        (now - 60.0, now - 60.0),
                    ).fetchone()[0]
                )
                if recent_starts_or_slots + batch_size > self.policy.request_starts_per_minute_max:
                    raise BudgetExceededError("closed-alpha rolling request-start budget exhausted")

                connection.executemany(
                    """
                    INSERT INTO attempts(
                        token, session_code, kind, provider, reserved_at, dispatched
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        (
                            token,
                            self.session.session_code,
                            intent.kind,
                            intent.provider,
                            now,
                        )
                        for intent, token in zip(intents, tokens, strict=True)
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(now),),
                )
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise

    def _consume_sync(self, permit: DispatchPermit, now: float) -> None:
        rate_denied = False
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                last_clock_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'last_clock'"
                ).fetchone()
                if last_clock_row is not None and now < float(last_clock_row["value"]):
                    raise BudgetConfigurationError("closed-alpha governor clock moved backwards")

                attempt = connection.execute(
                    """
                    SELECT id FROM attempts
                    WHERE token = ? AND session_code = ? AND kind = ?
                      AND provider IS ? AND dispatched = 0
                    """,
                    (
                        permit.token,
                        permit.session_code,
                        permit.kind,
                        permit.provider,
                    ),
                ).fetchone()
                if attempt is None:
                    raise BudgetExceededError("closed-alpha dispatch permit is invalid or consumed")

                recent_starts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM attempts WHERE dispatched_at > ?",
                        (now - 60.0,),
                    ).fetchone()[0]
                )
                rate_denied = recent_starts >= self.policy.request_starts_per_minute_max
                connection.execute(
                    """
                    UPDATE attempts
                    SET dispatched = 1, dispatched_at = ?
                    WHERE id = ? AND dispatched = 0
                    """,
                    (None if rate_denied else now, int(attempt["id"])),
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(now),),
                )
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
        if rate_denied:
            raise BudgetExceededError(
                "closed-alpha rolling request-start budget exhausted; permit consumed"
            )

    def _snapshot_sync(self) -> dict[str, int | str | bool]:
        with contextlib.closing(self._connect()) as connection:
            session_attempts = int(
                connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE session_code = ?",
                    (self.session.session_code,),
                ).fetchone()[0]
            )
            global_attempts = int(connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
            session_tavily = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM attempts
                    WHERE session_code = ? AND provider = 'tavily'
                    """,
                    (self.session.session_code,),
                ).fetchone()[0]
            )
            global_tavily = int(
                connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE provider = 'tavily'"
                ).fetchone()[0]
            )
            dispatched = int(
                connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE dispatched_at IS NOT NULL"
                ).fetchone()[0]
            )
            active_sessions = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
                ).fetchone()[0]
            )
        return {
            "scope": self.scope,
            "distributed_global_guarantee": False,
            "session_attempts": session_attempts,
            "global_attempts": global_attempts,
            "session_tavily_attempts": session_tavily,
            "global_tavily_attempts": global_tavily,
            "dispatched_attempts": dispatched,
            "active_sessions": active_sessions,
        }

    def _close_session_sync(self) -> None:
        now = self._clock()
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            raise BudgetConfigurationError("closed-alpha governor clock is invalid")
        with contextlib.closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                last_clock_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'last_clock'"
                ).fetchone()
                if last_clock_row is not None and now < float(last_clock_row["value"]):
                    raise BudgetConfigurationError("closed-alpha governor clock moved backwards")
                cursor = connection.execute(
                    """
                    UPDATE sessions SET status = 'closed', closed_at = ?
                    WHERE session_code = ? AND owner_id = ? AND status = 'active'
                    """,
                    (float(now), self.session.session_code, self._owner_id),
                )
                if cursor.rowcount != 1:
                    raise BudgetConfigurationError("closed-alpha session cannot be closed safely")
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('last_clock', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (repr(float(now)),),
                )
                connection.commit()
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.rollback()
                raise
