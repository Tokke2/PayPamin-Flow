"""Per-user single-instance ownership and local window activation.

A platform lock prevents duplicate application processes. A loopback-only,
token-authenticated channel lets a later start ask the existing app to show its
window, including when the window is hidden in the system tray.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path


class SingleInstance:
    """Own the application instance for one user's data directory."""

    def __init__(self, data_dir: str | Path, on_activate) -> None:
        self.data_dir = Path(data_dir)
        self.lock_path = self.data_dir / "instance.lock"
        self.state_path = self.data_dir / "instance.json"
        self.on_activate = on_activate
        self.activated_existing = False
        self._owned = False
        self._lock_file = None
        self._mutex_handle = None
        self._server = None
        self._thread = None
        self._token = ""
        self._stop = threading.Event()

    @property
    def owned(self) -> bool:
        return self._owned

    def _acquire_platform_lock(self) -> bool:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            import ctypes

            identity = hashlib.sha256(
                os.path.normcase(str(self.data_dir.resolve())).encode("utf-8")
            ).hexdigest()[:24]
            kernel32 = ctypes.windll.kernel32
            create_mutex = kernel32.CreateMutexW
            create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            create_mutex.restype = ctypes.c_void_p
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle.restype = ctypes.c_int
            handle = create_mutex(None, 0, f"Local\\PayPaminFlow-{identity}")
            if not handle:
                raise OSError("CreateMutexW failed for PayPamin Flow")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                close_handle(handle)
                return False
            self._mutex_handle = handle
            return True

        import fcntl

        self._lock_file = self.lock_path.open("a+b")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            self._lock_file = None
            return False
        return True

    def _release_platform_lock(self) -> None:
        if self._mutex_handle is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None
        if self._lock_file is not None:
            try:
                import fcntl

                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self._lock_file.close()
            except OSError:
                pass
            self._lock_file = None

    def _read_state(self) -> dict | None:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            port = int(state["port"])
            token = str(state["token"])
            pid = int(state["pid"])
            if not 1 <= port <= 65535 or len(token) < 32 or pid <= 0:
                return None
            return {"port": port, "token": token, "pid": pid}
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def owner_pid(self) -> int | None:
        """Return the published owner PID, used only for update diagnostics."""
        state = self._read_state()
        return state["pid"] if state else None

    def _write_state(self, port: int) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".instance.", dir=self.data_dir,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {"port": port, "pid": os.getpid(), "token": self._token},
                    handle,
                    separators=(",", ":"),
                )
            os.replace(temporary, self.state_path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _start_activation_server(self) -> None:
        self._token = secrets.token_hex(32)
        self._stop.clear()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(8)
            server.settimeout(0.2)
            self._server = server
            self._write_state(server.getsockname()[1])
            self._thread = threading.Thread(
                target=self._serve,
                name="paypamin-instance-activation",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            try:
                server.close()
            except OSError:
                pass
            self._server = None
            raise

    def _serve(self) -> None:
        while not self._stop.is_set():
            server = self._server
            if server is None:
                return
            try:
                client, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                client.settimeout(1.0)
                data = b""
                while len(data) < 4096 and b"\n" not in data:
                    chunk = client.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                request = json.loads(data.decode("utf-8"))
                valid = (
                    request.get("command") == "activate"
                    and hmac.compare_digest(str(request.get("token", "")), self._token)
                )
                if not valid:
                    raise ValueError("Invalid activation request")
                self.on_activate()
                response = {"ok": True}
            except Exception:
                response = {"ok": False}
            try:
                client.sendall(json.dumps(response).encode("ascii") + b"\n")
            except OSError:
                pass
            finally:
                try:
                    client.close()
                except OSError:
                    pass

    def activate_existing(self) -> bool:
        """Ask the published owner to show its window; never send data elsewhere."""
        state = self._read_state()
        if not state:
            return False
        request = json.dumps(
            {"command": "activate", "token": state["token"]},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        try:
            with socket.create_connection(("127.0.0.1", state["port"]), timeout=0.75) as client:
                client.settimeout(0.75)
                client.sendall(request)
                response = json.loads(client.recv(1024).decode("utf-8"))
            return response.get("ok") is True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def try_acquire(self) -> bool:
        """Try to become owner without activating another instance."""
        if self._owned:
            return True
        if not self._acquire_platform_lock():
            return False
        try:
            self._start_activation_server()
        except Exception:
            self._release_platform_lock()
            raise
        self._owned = True
        return True

    def acquire(self, timeout: float = 8.0) -> bool:
        """Become owner, or activate the existing app and return ``False``."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        self.activated_existing = False
        while True:
            if self.try_acquire():
                return True
            if self.activate_existing():
                self.activated_existing = True
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def release(self) -> None:
        """Release IPC and platform ownership; safe to call more than once."""
        self._stop.set()
        server, self._server = self._server, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        if self._owned and self._token:
            state = self._read_state()
            if state and hmac.compare_digest(state["token"], self._token):
                try:
                    self.state_path.unlink()
                except OSError:
                    pass
        self._owned = False
        self._token = ""
        self._release_platform_lock()
