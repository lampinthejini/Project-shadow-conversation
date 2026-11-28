"""측정 환경 기록. 얻지 못한 값은 None으로 두고 절차서대로 손으로 적는다.

AMD GPU의 VRAM은 Windows에서 정확히 읽을 방법이 마땅치 않아 수동 기록 대상이다.
"""

import ctypes
import os
import platform
import shutil
import subprocess
import sys


def runCommand(args, timeoutSec=10):
    if not shutil.which(args[0]):
        return None
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeoutSec)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or "").strip()
    return output or None


def totalRamGb():
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / 1024**3, 1)
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as memInfo:
            kb = int(memInfo.readline().split()[1])
        return round(kb / 1024**2, 1)
    except (OSError, ValueError, IndexError):
        return None


def cpuName():
    if sys.platform == "win32":
        name = runCommand(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]
        )
        if name:
            return name
    return platform.processor() or None


def gpuNames():
    nvidia = runCommand(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
    )
    if nvidia:
        return {"source": "nvidia-smi", "value": nvidia}
    if sys.platform == "win32":
        names = runCommand(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' / driver ' + $_.DriverVersion }) -join '; '",
            ]
        )
        if names:
            return {"source": "Win32_VideoController (VRAM은 수동 기록)", "value": names}
    return None


def vramSnapshot():
    """측정 중 VRAM 사용량. nvidia-smi가 없으면 None (Windows 작업 관리자 값을 손으로 적는다)."""
    used = runCommand(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"])
    ollamaPs = runCommand(["ollama", "ps"])
    return {"nvidiaSmi": used, "ollamaPs": ollamaPs}


def collect(api=None):
    info = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpuName(),
        "cpuLogicalCores": os.cpu_count(),
        "ramGb": totalRamGb(),
        "gpu": gpuNames(),
    }
    if api == "ollama":
        info["engineVersion"] = runCommand(["ollama", "--version"])
    return info


if __name__ == "__main__":
    import json

    print(json.dumps(collect(api="ollama"), ensure_ascii=False, indent=2))
