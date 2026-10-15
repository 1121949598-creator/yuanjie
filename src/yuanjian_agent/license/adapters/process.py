"""The only executable License boundary: bounded, host-selected ScanCode CLI."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from ...external.process import ProcessRequest


@dataclass(slots=True)
class BoundedProcessResult:
    exit_code: int | None
    reason_code: str = "ok"
    stdout: bytes = field(default=b"", repr=False)


def controlled_environment(workspace: Path, executable: Path) -> dict[str, str]:
    env = {"HOME": str(workspace), "USERPROFILE": str(workspace), "TMP": str(workspace),
           "TEMP": str(workspace), "TMPDIR": str(workspace), "XDG_CONFIG_HOME": str(workspace),
           "XDG_CACHE_HOME": str(workspace), "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
           "PYTHONIOENCODING": "utf-8", "LC_ALL": "C", "LANG": "C"}
    paths = [str(executable.parent)]
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        env["SystemRoot"] = system_root
        env["WINDIR"] = system_root
        paths.append(str(Path(system_root) / "System32"))
    else:
        paths.extend(["/usr/bin", "/bin"])
    env["PATH"] = os.pathsep.join(paths)
    return env


class ScanCodeProcessRunner:
    """Resource control, not an OS network sandbox. No inherited credentials.

    stderr is drained with a size limit but never retained or returned.
    """

    def command(self, request: ProcessRequest) -> list[str]:
        return [request.executable, *request.arguments]

    def run(self, request: ProcessRequest, *, env: dict[str, str], max_stream_bytes: int,
            output_path: Path | None = None, max_output_bytes: int = 0) -> BoundedProcessResult:
        overflow = threading.Event()
        done = [threading.Event(), threading.Event()]
        captured = bytearray()

        def drain(stream, index):
            total = 0
            try:
                while chunk := stream.read1(4096):
                    total += len(chunk)
                    if total > max_stream_bytes:
                        overflow.set()
                    elif index == 0:
                        captured.extend(chunk)
            except (OSError, ValueError):
                overflow.set()
            finally:
                stream.close()
                done[index].set()

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                self.command(request), shell=False, cwd=request.cwd, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=flags, start_new_session=os.name != "nt", close_fds=True,
            )
        except OSError:
            return BoundedProcessResult(None, "execution_failed")
        threads = [threading.Thread(target=drain, args=(stream, i), daemon=True)
                   for i, stream in enumerate((process.stdout, process.stderr))]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + request.timeout_seconds
        reason = "ok"
        try:
            while True:
                if overflow.is_set():
                    reason = "output_limit"
                    break
                if output_path is not None:
                    try:
                        if output_path.is_symlink() or (output_path.exists() and output_path.stat().st_size > max_output_bytes):
                            reason = "output_limit"
                            break
                    except OSError:
                        reason = "invalid_output"
                        break
                if process.poll() is not None and all(event.is_set() for event in done):
                    break
                if time.monotonic() >= deadline:
                    reason = "timeout"
                    break
                time.sleep(0.01)
        finally:
            if reason != "ok":
                self._terminate(process, request.cwd, env)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            for thread in threads:
                thread.join(timeout=1)
        if overflow.is_set() and reason == "ok":
            reason = "output_limit"
        return BoundedProcessResult(process.returncode, reason, bytes(captured) if reason == "ok" else b"")

    @staticmethod
    def _terminate(process, cwd: Path, env: dict[str, str]) -> None:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
            try:
                with subprocess.Popen(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"], shell=False,
                    cwd=cwd, env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
                ) as killer:
                    try:
                        killer.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        killer.kill()
            except OSError:
                pass
            if process.poll() is None:
                process.kill()
