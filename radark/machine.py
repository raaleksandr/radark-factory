"""Machine-wide layer shared by the dispatcher instances of one OS user on one computer (machine-wide-instances):
the machine directory, OS file locks, the machine limits, instance and repository records, session and test-run
slots, the shared usage record and the `test-slot` command. Stores no hub path and calls no `ho` (design D11)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SESSIONS = 2  # product decision (design D2)
DEFAULT_TEST_RUNS = 1
USAGE_LOCK_S = 10.0  # bound on waiting for usage.lock; then the instance uses its own reading (design D3)
TEST_POLL_S = 2.0  # test-slot polling and waiting-line period (design D8)
TEST_NOTE_S = 60.0
CLAIM_WAIT_S = 1.0  # a claim retries this long: a `status` / `dry-run` probe holds a free lock only for an instant
WRAPPER = "radark-test-slot"


class MachineError(Exception):
    pass


# -- directory (design D1) ------------------------------------------------------------------

def machine_dir(env=None, name: str | None = None) -> Path:
    """`RADARK_MACHINE_DIR`, else `%LOCALAPPDATA%\\radark\\machine` on Windows and
    `${XDG_STATE_HOME:-~/.local/state}/radark/machine` elsewhere. Not created here."""
    env = os.environ if env is None else env
    name = name or os.name
    if env.get("RADARK_MACHINE_DIR"):
        return Path(env["RADARK_MACHINE_DIR"])
    if name == "nt":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = env.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "radark" / "machine"


def norm(path) -> str:
    """A path as a comparable key: resolved, and case-insensitive with one separator on Windows."""
    return os.path.normcase(os.path.realpath(str(path)))


def inside(child, parent) -> bool:
    c, p = norm(child), norm(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def prepare_dir(directory: Path, run_dir: Path | None = None, repos=()) -> Path:
    """Create the machine directory and check it can be written and lies outside the run directory and every team
    repository; returns its resolved path or raises MachineError naming it (design D1)."""
    directory = Path(directory)
    if run_dir is not None and inside(directory, run_dir):
        raise MachineError(f"machine directory {directory} lies inside the run directory {run_dir}; "
                           "set RADARK_MACHINE_DIR to a directory outside it")
    for repo in repos:
        if inside(directory, repo):
            raise MachineError(f"machine directory {directory} lies inside the team repository {repo}; "
                               "set RADARK_MACHINE_DIR to a directory outside it")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".write-check-{os.getpid()}-{threading.get_ident()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise MachineError(f"machine directory {directory} cannot be created or written: {exc}") from exc
    return Path(os.path.realpath(directory))


# -- limits (design D2) ---------------------------------------------------------------------

@dataclass(frozen=True)
class Limits:
    sessions: int = DEFAULT_SESSIONS
    test_runs: int = DEFAULT_TEST_RUNS

    def text(self) -> str:
        return (f"{self.sessions} session{'' if self.sessions == 1 else 's'}, "
                f"{self.test_runs} test run{'' if self.test_runs == 1 else 's'}")


def load_limits(directory: Path) -> Limits:
    """`[machine] sessions` / `test_runs` of `<dir>/machine.toml`; defaults for a missing file or key."""
    path = Path(directory) / "machine.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Limits()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise MachineError(f"{path}: cannot be read: {exc}") from exc
    section = data.get("machine", {})
    if not isinstance(section, dict):
        raise MachineError(f"{path}: [machine] must be a table")
    values = {}
    for key, default in (("sessions", DEFAULT_SESSIONS), ("test_runs", DEFAULT_TEST_RUNS)):
        value = section.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise MachineError(f"{path}: machine.{key} must be an integer of at least 1, not {value!r}")
        values[key] = value
    return Limits(**values)


# -- OS locks and records (design D4) -------------------------------------------------------

if os.name == "nt":  # imported once: a later stand-in for the module (tests of a key press) does not matter
    import msvcrt as _msvcrt
else:
    import fcntl as _fcntl


def _os_lock(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)
    else:
        _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)


def _os_unlock(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
    else:
        _fcntl.flock(fd, _fcntl.LOCK_UN)


class FileLock:
    """A non-blocking OS lock on byte 0 of a file; the OS releases it when the process ends in any way. Each claim
    has its own file and handle, so two threads of one process never share one."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.fd: int | None = None

    @property
    def held(self) -> bool:
        return self.fd is not None

    def try_acquire(self) -> bool:
        if self.fd is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _os_lock(fd)
        except OSError:
            os.close(fd)
            return False
        self.fd = fd
        return True

    def acquire(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while True:
            if self.try_acquire():
                return True
            if time.monotonic() >= end:
                return False
            time.sleep(0.05)

    def release(self) -> None:
        fd, self.fd = self.fd, None
        if fd is None:
            return
        try:
            _os_unlock(fd)
        except OSError:
            pass
        os.close(fd)


def record_path(lock_path: Path) -> Path:
    return lock_path.with_suffix(".json")


def write_record(path: Path, data: dict) -> None:
    """Atomic replace; retried briefly on Windows, where a reader holding the file open blocks a replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    for attempt in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 39:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.025)


def read_record(path: Path) -> dict | None:
    for attempt in range(3):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except PermissionError:
            time.sleep(0.02)
        except (OSError, ValueError):
            return None
    return None


def probe(lock_path: Path, remove_lock: bool = False) -> bool:
    """True when another holder has the lock. A free lock's record is stale: it is removed (and the lock file too
    when `remove_lock`, for files named by a unique id)."""
    lock_path = Path(lock_path)
    if not lock_path.exists():
        record_path(lock_path).unlink(missing_ok=True)
        return False
    lock = FileLock(lock_path)
    try:
        if not lock.try_acquire():
            return True
    except OSError:
        return False
    try:
        record_path(lock_path).unlink(missing_ok=True)
    except OSError:
        pass
    lock.release()
    if remove_lock:
        try:
            lock_path.unlink()
        except OSError:
            pass
    return False


def repo_key(repo) -> str:
    """SHA-256 (first 16 hex) of the resolved, normcased repository path (design D1)."""
    return hashlib.sha256(norm(repo).encode("utf-8")).hexdigest()[:16]


def local_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def slot_number(path: Path) -> int | None:
    try:
        return int(path.stem.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


# -- the machine layer of one instance --------------------------------------------------------

class Machine:
    """The claims of one dispatcher instance in the machine directory. `report(event, text, **fields)` receives
    one-off problems (`machine_config_invalid`, `machine_usage_unavailable`)."""

    def __init__(self, directory: Path, config_path=None, run_dir=None, report=None, strict: bool = True):
        """`strict`: an invalid `machine.toml` raises MachineError (refused at start, design D2); otherwise the
        defaults are used (`status`, which only reads)."""
        self.dir = Path(directory)
        self.config_path = str(config_path) if config_path else None
        self.run_dir = str(run_dir) if run_dir else None
        self.report = report or (lambda event, text, **fields: None)
        self._invalid: str | None = None
        try:
            self._limits = load_limits(self.dir)
        except MachineError as exc:
            if strict:
                raise
            self._limits, self._invalid = Limits(), str(exc)
        self._usage_warned = False
        self._lock = threading.RLock()
        self.pid = os.getpid()
        # the instance's start in ms: unique per instance, also for several instances of one process in tests
        self.id = f"{self.pid}-{int(time.time() * 1000)}"
        self.started = local_now()
        self.instance: FileLock | None = None
        self.repos: list[FileLock] = []
        self.slots: dict[int, FileLock] = {}

    # ---- limits

    def limits(self) -> Limits:
        """Re-read at each slot request; an invalid file keeps the last valid limits, reported once per error."""
        try:
            new = load_limits(self.dir)
        except MachineError as exc:
            if self._invalid != str(exc):
                self._invalid = str(exc)
                self.report("machine_config_invalid", f"{exc}; keeping {self._limits.text()}", error=str(exc))
            return self._limits
        self._invalid = None
        self._limits = new
        return new

    # ---- instance record (design D1, D4, D5)

    def _instance_lock(self, iid: str | None = None) -> Path:
        return self.dir / "instances" / f"{iid or self.id}.lock"

    def enter(self) -> None:
        with self._lock:
            while True:
                lock = FileLock(self._instance_lock())
                if lock.acquire(CLAIM_WAIT_S):
                    break
                self.id = f"{self.pid}-{max(int(time.time() * 1000), int(self.id.rsplit('-', 1)[1]) + 1)}"
            self.instance = lock
            self._write_instance()

    def _write_instance(self) -> None:
        if self.instance is None:
            return
        write_record(record_path(self._instance_lock()), {
            "id": self.id, "config": self.config_path, "run_dir": self.run_dir, "pid": self.pid,
            "started": self.started, "sessions": len(self.slots)})

    def instances(self) -> list[dict]:
        """Records of the other running instances; stale records and their lock files are removed."""
        out = []
        folder = self.dir / "instances"
        if not folder.is_dir():
            return out
        for lock_path in sorted(folder.glob("*.lock")):
            if lock_path.stem == self.id and self.instance is not None:
                continue
            if probe(lock_path, remove_lock=True):
                rec = read_record(record_path(lock_path)) or {}
                rec.setdefault("id", lock_path.stem)
                out.append(rec)
        for rec_path in folder.glob("*.json"):  # a record without a lock file
            if not rec_path.with_suffix(".lock").exists():
                rec_path.unlink(missing_ok=True)
        return out

    def others_running(self) -> bool:
        return bool(self.instances())

    def close(self) -> None:
        """Release every claim, records first (design D4)."""
        with self._lock:
            for n in list(self.slots):
                self.release_session_slot(n, update=False)
            self.release_repos()
            if self.instance is not None:
                path = self._instance_lock()
                record_path(path).unlink(missing_ok=True)
                self.instance.release()
                self.instance = None
                try:
                    path.unlink()
                except OSError:
                    pass

    # ---- repositories (design D6)

    def _repo_lock(self, repo) -> Path:
        return self.dir / "repos" / f"{repo_key(repo)}.lock"

    @staticmethod
    def _unique(repos) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for repo in repos:
            out.setdefault(repo_key(repo), Path(repo))
        return out

    def claim_repos(self, repos) -> tuple[str, dict] | None:
        """Claim every repository; on a conflict release what was claimed and return (repository, the holder's
        record)."""
        with self._lock:
            for key, repo in self._unique(repos).items():
                path = self.dir / "repos" / f"{key}.lock"
                lock = FileLock(path)
                if not lock.acquire(CLAIM_WAIT_S):
                    holder = read_record(record_path(path)) or {}
                    self.release_repos()
                    return os.path.realpath(repo), holder
                self.repos.append(lock)
                write_record(record_path(path), {"repo": os.path.realpath(repo), "config": self.config_path,
                                                 "instance": self.id, "pid": self.pid})
            return None

    def release_repos(self) -> None:
        with self._lock:
            for lock in self.repos:
                record_path(lock.path).unlink(missing_ok=True)
                lock.release()
            self.repos = []

    def repo_conflicts(self, repos) -> list[tuple[str, dict]]:
        """Repositories held by another running pipeline (another configuration); probes only (design D5, D6)."""
        out = []
        mine = norm(self.config_path) if self.config_path else None
        for key, repo in self._unique(repos).items():
            path = self.dir / "repos" / f"{key}.lock"
            if any(lock.path == path for lock in self.repos) or not probe(path):
                continue
            holder = read_record(record_path(path)) or {}
            if mine and holder.get("config") and norm(holder["config"]) == mine:
                continue
            out.append((os.path.realpath(repo), holder))
        return out

    # ---- session slots (design D7)

    def _slot_lock(self, kind: str, n: int) -> Path:
        return self.dir / "slots" / f"{kind}-{n}.lock"

    def try_session_slot(self, kind: str = "session") -> int | None:
        """Take the first free `slots/session-<n>.lock`, n up to the limit; None when none is free."""
        with self._lock:
            limit = self.limits().sessions
            for n in range(1, limit + 1):
                if n in self.slots:
                    continue
                lock = FileLock(self._slot_lock("session", n))
                if lock.try_acquire():
                    self.slots[n] = lock
                    write_record(record_path(lock.path), {"instance": self.id, "config": self.config_path,
                                                          "kind": kind, "pid": self.pid, "started": local_now()})
                    self._write_instance()
                    return n
            return None

    def release_session_slot(self, n: int, update: bool = True) -> None:
        with self._lock:
            lock = self.slots.pop(n, None)
            if lock is None:
                return
            record_path(lock.path).unlink(missing_ok=True)
            lock.release()
            if update:
                self._write_instance()

    def held(self, kind: str) -> int:
        """Slots of `kind` (`session` / `test`) held by others (stale records are removed)."""
        folder = self.dir / "slots"
        if not folder.is_dir():
            return 0
        own = {lock.path for lock in self.slots.values()} if kind == "session" else set()
        return sum(1 for p in folder.glob(f"{kind}-*.lock") if p not in own and probe(p))

    def session_counts(self) -> tuple[int, int, int]:
        """(own, other, limit) session slots."""
        with self._lock:
            return len(self.slots), self.held("session"), self.limits().sessions

    # ---- shared usage (design D3)

    @contextmanager
    def _usage_lock(self):
        lock = FileLock(self.dir / "usage.lock")
        ok = lock.acquire(USAGE_LOCK_S)
        try:
            if not ok and not self._usage_warned:
                self._usage_warned = True
                self.report("machine_usage_unavailable",
                            f"the shared usage record {self.dir / 'usage.json'} is busy; using this pipeline's own "
                            "usage reading", path=str(self.dir / "usage.json"))
            yield ok
        finally:
            lock.release()

    def read_usage(self) -> dict | None:
        """`usage.json` ({"windows": ..., "hold": ...}); None when unavailable."""
        with self._usage_lock() as ok:
            if not ok:
                return None
            return read_record(self.dir / "usage.json") or {}

    def merge_usage(self, readings: dict, seen_ts: float | None = None) -> bool:
        """Merge readings {window: {utilization, resets_at, status}} seen at `seen_ts`; the newest per window wins."""
        seen_ts = time.time() if seen_ts is None else seen_ts
        with self._usage_lock() as ok:
            if not ok:
                return False
            data = read_record(self.dir / "usage.json") or {}
            windows = data.get("windows") if isinstance(data.get("windows"), dict) else {}
            changed = False
            for window, r in readings.items():
                old = windows.get(window)
                if isinstance(old, dict) and (old.get("seen_ts") or 0) > seen_ts:
                    continue
                windows[window] = {"utilization": r.get("utilization"), "resets_at": r.get("resets_at"),
                                   "status": r.get("status"), "seen_ts": seen_ts}
                changed = True
            if changed:
                data["windows"] = windows
                write_record(self.dir / "usage.json", data)
            return True

    def write_hold(self, until: float, window: str | None, cause: str = "limit_hit") -> bool:
        """Set the shared hold when `until` is later than the stored one."""
        with self._usage_lock() as ok:
            if not ok:
                return False
            data = read_record(self.dir / "usage.json") or {}
            hold = data.get("hold") if isinstance(data.get("hold"), dict) else None
            if hold and (hold.get("until") or 0) >= until:
                return True
            data["hold"] = {"until": until, "window": window, "cause": cause, "by": self.id,
                            "config": self.config_path}
            write_record(self.dir / "usage.json", data)
            return True


# -- the test-run slot (design D8) -------------------------------------------------------------

def wrapper_path(run_dir: Path) -> Path:
    return Path(run_dir) / "bin" / (WRAPPER + (".cmd" if os.name == "nt" else ""))


def write_wrappers(run_dir: Path, python: str | None = None) -> Path:
    """`<run_dir>/bin/radark-test-slot(.cmd)`, rewritten only when changed. `-P`: the session's working directory
    (a repository that may hold another `radark`) is not put on sys.path, so the installed release runs."""
    python = python or sys.executable
    folder = Path(run_dir) / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    files = {folder / (WRAPPER + ".cmd"): f'@"{python}" -P -m radark test-slot %*\r\n',
             folder / WRAPPER: f'#!/bin/sh\nexec "{python}" -P -m radark test-slot "$@"\n'}
    for path, text in files.items():
        try:
            same = path.read_bytes() == text.encode("utf-8")
        except OSError:
            same = False
        if not same:
            path.write_bytes(text.encode("utf-8"))
        if not path.suffix:
            try:
                path.chmod(0o755)
            except OSError:
                pass
    return wrapper_path(run_dir)


def _run_command(cmd: list[str], env: dict, err) -> int:
    exe = shutil.which(cmd[0], path=env.get("PATH")) or cmd[0]
    try:
        return subprocess.run([exe, *cmd[1:]], env=env).returncode
    except OSError as exc:
        print(f"radark-test-slot: cannot start {cmd[0]}: {exc}", file=err, flush=True)
        return 127


def run_test_slot(cmd: list[str], env=None, err=None, poll: float = TEST_POLL_S, note: float = TEST_NOTE_S) -> int:
    """`python -m radark test-slot [--] <command...>`: run the command holding a machine test-run slot and return
    its exit code (127 when it cannot start)."""
    err = err or sys.stderr
    env = dict(os.environ if env is None else env)
    if cmd[:1] == ["--"]:
        cmd = cmd[1:]
    if not cmd:
        print("usage: python -m radark test-slot [--] <command> [args...]", file=err, flush=True)
        return 2
    if env.get("HARNESS_TEST_SLOT_HELD"):  # nested inside a command run through it: no deadlock
        return _run_command(cmd, env, err)
    directory = machine_dir(env)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"radark-test-slot: machine directory {directory} cannot be created ({exc}); running without a slot",
              file=err, flush=True)
        return _run_command(cmd, env, err)
    limits, warned, next_note = Limits(), None, 0.0
    lock = None
    while lock is None:
        try:
            limits = load_limits(directory)
        except MachineError as exc:
            if warned != str(exc):
                warned = str(exc)
                print(f"radark-test-slot: {exc}; using {limits.test_runs} test run(s)", file=err, flush=True)
        for n in range(1, limits.test_runs + 1):
            candidate = FileLock(directory / "slots" / f"test-{n}.lock")
            if candidate.try_acquire():
                lock = candidate
                break
        if lock is not None:
            break
        if time.monotonic() >= next_note:
            k = sum(1 for p in (directory / "slots").glob("test-*.lock") if probe(p))
            print(f"radark-test-slot: waiting - {k} test run{'' if k == 1 else 's'} in progress on this computer",
                  file=err, flush=True)
            next_note = time.monotonic() + note
        time.sleep(poll)
    try:
        write_record(record_path(lock.path), {"pid": os.getpid(), "started": local_now(),
                                              **({"instance": env["RADARK_INSTANCE"]}
                                                 if env.get("RADARK_INSTANCE") else {})})
        env["HARNESS_TEST_SLOT_HELD"] = "1"
        return _run_command(cmd, env, err)
    finally:
        record_path(lock.path).unlink(missing_ok=True)
        lock.release()
