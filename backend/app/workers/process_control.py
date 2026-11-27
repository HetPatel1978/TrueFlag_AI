"""Native Windows child containment and bounded pipe IPC; no provider/DB authority."""

import ctypes
import os
import queue
import subprocess
import threading
import time
from ctypes import wintypes
from uuid import uuid4


class ProcessTimeout(Exception):
    pass


class ProcessOutputLimit(Exception):
    pass


class ProcessCancelled(Exception):
    pass


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class IOCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IOCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("usage", wintypes.DWORD),
        ("thread_id", wintypes.DWORD),
        ("process_id", wintypes.DWORD),
        ("priority", wintypes.LONG),
        ("delta", wintypes.LONG),
        ("flags", wintypes.DWORD),
    ]


def kernel():
    if os.name != "nt":
        raise RuntimeError("windows_process_required")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, args, result in (
        ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        (
            "SetInformationJobObject",
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        (
            "QueryInformationJobObject",
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
            wintypes.BOOL,
        ),
        ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ("OpenJobObjectW", [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        ("GetCurrentProcess", [], wintypes.HANDLE),
        ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        ("Thread32First", [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)], wintypes.BOOL),
        ("Thread32Next", [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)], wintypes.BOOL),
        ("OpenThread", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        ("ResumeThread", [wintypes.HANDLE], wintypes.DWORD),
        (
            "IsProcessInJob",
            [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)],
            wintypes.BOOL,
        ),
    ):
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


class WindowsJob:
    """Non-inheritable handle: parent death closes it and kills every contained child."""

    def __init__(self, *, memory_bytes, cpu_seconds, processes=2):
        self.api, self.handle = kernel(), None
        self.name = "Local\\TrueFlagChild-" + uuid4().hex
        handle = self.api.CreateJobObjectW(None, self.name)
        if not handle:
            raise OSError("windows_job_creation_failed")
        self.handle = handle
        limits = ExtendedLimits()
        limits.basic.flags = (
            0x2000 | 0x100 | 0x200 | 0x8
        )  # kill-on-close, process/job memory, active count
        limits.basic.active_processes = processes
        limits.process_memory = limits.job_memory = memory_bytes
        if cpu_seconds:
            limits.basic.flags |= 0x2
            limits.basic.process_time = int(cpu_seconds * 10_000_000)
        if not self.api.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise OSError("windows_job_limits_failed")

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(
            self.handle, wintypes.HANDLE(int(process._handle))
        ):
            raise OSError("windows_job_assignment_failed")

    def terminate(self):
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def start_in_job(job, command, **kwargs):
    """Assign while suspended, before even the Windows venv launcher can spawn a child."""
    process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW | 0x4, **kwargs)
    try:
        job.assign(process)
        api = job.api
        snapshot = api.CreateToolhelp32Snapshot(0x4, 0)
        if snapshot in (None, wintypes.HANDLE(-1).value):
            raise OSError("windows_thread_snapshot_failed")
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = []
            active = api.Thread32First(snapshot, ctypes.byref(entry))
            while active:
                if entry.process_id == process.pid:
                    found.append(entry.thread_id)
                active = api.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            api.CloseHandle(snapshot)
        if len(found) != 1:
            raise OSError("windows_primary_thread_ambiguous")
        thread = api.OpenThread(0x2, False, found[0])
        if not thread:
            raise OSError("windows_primary_thread_unavailable")
        try:
            if api.ResumeThread(thread) != 1:
                raise OSError("windows_primary_thread_resume_failed")
        finally:
            api.CloseHandle(thread)
        return process
    except BaseException:
        process.kill()
        process.wait(timeout=5)
        raise


def require_windows_child_limits(memory_bytes):
    api, limits = kernel(), ExtendedLimits()
    name = os.environ.get("TRUEFLAG_CHILD_JOB", "")
    if (
        not name.startswith("Local\\TrueFlagChild-")
        or len(name) != len("Local\\TrueFlagChild-") + 32
    ):
        raise RuntimeError("windows_job_required")
    handle = api.OpenJobObjectW(0x4, False, name)  # Query-only, never inherited.
    if not handle:
        raise RuntimeError("windows_job_required")
    try:
        member = wintypes.BOOL()
        if (
            not api.IsProcessInJob(api.GetCurrentProcess(), handle, ctypes.byref(member))
            or not member.value
        ):
            raise RuntimeError("windows_job_membership_required")
        if not api.QueryInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits), None
        ):
            raise RuntimeError("windows_job_required")
        required = 0x2000 | 0x100 | 0x200 | 0x8
        if (
            limits.basic.flags & required != required
            or not 0 < limits.process_memory <= memory_bytes
        ):
            raise RuntimeError("windows_job_limits_required")
    finally:
        api.CloseHandle(handle)  # Parent remains sole owner before credentials are consumed.


def child_environment(values):
    """Only Windows loader/temp variables supplement the caller's explicit allowlist."""
    return {
        **{k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP") if k in os.environ},
        **values,
    }


def run_windows(
    command,
    payload,
    *,
    environment,
    timeout,
    max_output,
    memory_bytes,
    cpu_seconds,
    cancelled=None,
    tick=None,
):
    if cancelled and cancelled.is_set():
        raise ProcessCancelled()
    job = WindowsJob(memory_bytes=memory_bytes, cpu_seconds=cpu_seconds)
    process = None
    stopped, output_queue = threading.Event(), queue.Queue(maxsize=8)
    reader = writer = None
    deadline = time.monotonic() + timeout
    try:
        process = start_in_job(
            job,
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=child_environment({**environment, "TRUEFLAG_CHILD_JOB": job.name}),
            close_fds=True,
        )
        if cancelled and cancelled.is_set():
            raise ProcessCancelled()

        def send():
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (OSError, ValueError):
                pass

        def receive():
            try:
                while not stopped.is_set():
                    chunk = os.read(process.stdout.fileno(), 16384)
                    while not stopped.is_set():
                        try:
                            output_queue.put(chunk, timeout=0.1)
                            break
                        except queue.Full:
                            continue
                    if not chunk:
                        return
            except (OSError, ValueError):
                return

        reader = threading.Thread(target=receive, daemon=True)
        writer = threading.Thread(target=send, daemon=True)
        reader.start()
        writer.start()
        result, eof = bytearray(), False
        while not eof or process.poll() is None:
            if cancelled and cancelled.is_set():
                raise ProcessCancelled()
            if time.monotonic() >= deadline:
                raise ProcessTimeout()
            if tick:
                tick()
            try:
                chunk = output_queue.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if not chunk:
                eof = True
            result.extend(chunk)
            if len(result) > max_output:
                raise ProcessOutputLimit()
        return process.returncode, bytes(result)
    finally:
        stopped.set()
        job.terminate()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        for thread in (writer, reader):
            if thread is not None:
                thread.join(timeout=2)
        if process is not None:
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        job.close()
