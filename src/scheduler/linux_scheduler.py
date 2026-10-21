"""Linux sched_ext process manager.

Schedulers are launched as foreground scx binaries. Only child processes
started by this manager are stopped; externally managed schedulers are never
killed implicitly.
"""

import os
import atexit
import shutil
import subprocess
import time
import threading
from typing import Dict, List, Optional

from src.interfaces.scheduler_interface import ISchedulerManager


class LinuxSchedulerManager(ISchedulerManager):
    def __init__(self, available: List[str], default: str = "default",
                 startup_timeout: float = 8.0, state_path: str = "/sys/kernel/sched_ext/state",
                 ops_path: str = "/sys/kernel/sched_ext/root/ops"):
        if not sys_platform_linux():
            raise RuntimeError("Real scheduler management is supported on Linux only")
        self._available = list(available)
        self._default = default
        self._startup_timeout = startup_timeout
        self._state_path, self._ops_path = state_path, ops_path
        self._process: Optional[subprocess.Popen] = None
        self._current = default
        self._lock = threading.RLock()
        atexit.register(self.stop)
        if os.geteuid() != 0:
            raise PermissionError("Real scheduler mode requires root privileges to manage sched_ext")
        if self._is_enabled():
            raise RuntimeError("A sched_ext scheduler is already active; stop its service before AdaptiveSched")
        self._binaries: Dict[str, str] = {}
        for name in self._available:
            if name != default:
                if not name.startswith("scx_") or not name.replace("_", "").isalnum():
                    raise ValueError(f"Unsafe or unsupported sched_ext name: {name!r}")
                binary = shutil.which(name)
                if binary:
                    self._binaries[name] = binary
        if not self._binaries:
            raise FileNotFoundError("No configured sched_ext scheduler binaries are installed on PATH")

    def get_current(self) -> str:
        with self._lock:
            if self._process is not None and self._process.poll() is not None:
                self._process = None
                self._current = self._default
            if self._is_enabled() and self._process is None:
                return self._read_ops() or "external_sched_ext"
            return self._current

    def get_available(self) -> List[str]:
        return [name for name in self._available
                if name == self._default or name in self._binaries]

    def switch_to(self, scheduler_name: str) -> bool:
        with self._lock:
            if scheduler_name not in self._available:
                return False
            if scheduler_name == self.get_current():
                return True
            if os.geteuid() != 0:
                raise PermissionError("Real sched_ext management requires root/CAP_BPF and CAP_SYS_ADMIN")
            if not os.path.isfile(self._state_path):
                raise RuntimeError("sched_ext is unavailable: kernel state file is missing (requires CONFIG_SCHED_CLASS_EXT)")
            if self._process is None and self._is_enabled():
                raise RuntimeError("A sched_ext scheduler is already active outside this process; stop its service before AdaptiveSched")

            if not self._stop_owned_scheduler():
                return False
            if scheduler_name == self._default:
                self._current = self._default
                return True

            binary = self._binaries.get(scheduler_name)
            if not binary:
                raise FileNotFoundError(f"{scheduler_name} is not installed or not on PATH")
            proc = subprocess.Popen([binary], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    close_fds=True)
            self._process = proc
            deadline = time.monotonic() + self._startup_timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    self._process = None
                    raise RuntimeError(f"{scheduler_name} exited before activation; check its logs and kernel support")
                if self._is_enabled() and self._read_ops() == scheduler_name.removeprefix("scx_"):
                    self._current = scheduler_name
                    return True
                time.sleep(0.1)
            self._stop_owned_scheduler()
            raise TimeoutError(f"{scheduler_name} did not become active within {self._startup_timeout:g}s")

    def stop(self) -> None:
        """Stop the scheduler child owned by this manager, restoring fair scheduling."""
        with self._lock:
            self._stop_owned_scheduler()

    def _stop_owned_scheduler(self) -> bool:
        proc = self._process
        if proc is None:
            return not self._is_enabled()
        if proc.poll() is None:
            proc.terminate()  # sched_ext reverts to the fair scheduler on exit.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        self._process = None
        deadline = time.monotonic() + 3
        while self._is_enabled() and time.monotonic() < deadline:
            time.sleep(0.05)
        self._current = self._default
        return not self._is_enabled()

    def _is_enabled(self) -> bool:
        try:
            with open(self._state_path, encoding="ascii") as stream:
                return stream.read().strip() == "enabled"
        except OSError:
            return False

    def _read_ops(self) -> str:
        try:
            with open(self._ops_path, encoding="ascii") as stream:
                return stream.read().strip()
        except OSError:
            return ""


def sys_platform_linux() -> bool:
    return os.name == "posix" and os.path.exists("/proc/sys/kernel/ostype")
