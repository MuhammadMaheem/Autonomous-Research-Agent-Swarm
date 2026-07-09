"""Sandboxed execution of LLM-generated Python.

Layers: import allowlist (static scan) -> subprocess with rlimits (CPU/memory/file size)
-> network namespace isolation via `unshare -rn` when available -> hard wall-clock timeout.
Only LLM-generated code for math/data sub-questions runs here, never user-supplied code.
"""
import asyncio
import re
import resource
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

ALLOWED_IMPORTS = {
    "math", "statistics", "json", "random", "datetime", "itertools", "collections",
    "re", "functools", "fractions", "decimal", "heapq", "string", "textwrap", "numpy",
}

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", re.MULTILINE)

_unshare_ok: bool | None = None


def _unshare_available() -> bool:
    global _unshare_ok
    if _unshare_ok is None:
        _unshare_ok = bool(shutil.which("unshare")) and subprocess.run(
            ["unshare", "-rn", "true"], capture_output=True
        ).returncode == 0
    return _unshare_ok


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str


def check_imports(code: str) -> list[str]:
    return sorted({m for m in _IMPORT_RE.findall(code) if m not in ALLOWED_IMPORTS})


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (settings.sandbox_cpu_s, settings.sandbox_cpu_s))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))  # 1 GiB (numpy import headroom)
    resource.setrlimit(resource.RLIMIT_FSIZE, (5 << 20, 5 << 20))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


async def run_python(code: str) -> SandboxResult:
    disallowed = check_imports(code)
    if disallowed:
        return SandboxResult(False, "", f"Disallowed imports: {disallowed}. Allowed: {sorted(ALLOWED_IMPORTS)}")

    with tempfile.TemporaryDirectory(prefix="swarm-sbx-") as tmp:
        script = Path(tmp) / "task.py"
        script.write_text(code)
        cmd = [sys.executable, "-I", str(script)]
        if _unshare_available():
            cmd = ["unshare", "-rn", "--", *cmd]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=tmp,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=_limits,
            env={"PATH": "/usr/bin:/bin"},
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=settings.sandbox_timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return SandboxResult(False, "", f"timed out after {settings.sandbox_timeout_s}s")
    return SandboxResult(
        ok=proc.returncode == 0,
        stdout=out.decode(errors="replace")[:4000],
        stderr=err.decode(errors="replace")[:2000],
    )
