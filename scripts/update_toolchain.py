#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Toolchain updater for the eMudhra / emSign CA incident (2026-10).

1. uv on PATH: compare each installation with the latest release on PyPI and
   update it with the method it was installed with (scoop / winget / standalone / pip).
2. System Python interpreters: update pip (and certifi).
3. Project .venv: update pip (and certifi).

Minimum safe versions (python.org security advisory):
    uv >= 0.13.4, pip >= 26.2.2, certifi >= 2026.10.19

pip older than 26.2.2 trusts its own vendored CA bundle, so it is first upgraded
from a wheel pinned by SHA-256 (from the advisory, verified against PyPI) and only
then upgraded normally.

Usage:
    python scripts/update_toolchain.py            # check and update
    python scripts/update_toolchain.py --check    # report only, change nothing
    python scripts/update_toolchain.py --venv D:/bot/.venv   # other venv(s)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

SAFE_VERSIONS = {"uv": "0.13.4", "pip": "26.2.2", "certifi": "2026.10.19"}

# pip 26.2.2 wheel pinned by hash (python.org advisory; same digest as PyPI JSON API)
PIP_WHEEL = ("https://files.pythonhosted.org/packages/3f/06/"
             "3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl"
             "#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70")
PIP_PINNED_REQ = f"pip @ {PIP_WHEEL}"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_ONLY = False
summary = []  # (status, item, detail)


# ---------------------------------------------------------------- helpers

def vtuple(version):
    return tuple(int(x) for x in re.findall(r"\d+", version or "")) or (0,)


def run(cmd, env=None, timeout=900):
    """Run a command, return (returncode, combined output)."""
    # Resolve .cmd/.bat shims (e.g. scoop.cmd) that CreateProcess cannot find by bare name
    resolved = cmd[0] if os.path.isabs(cmd[0]) else shutil.which(cmd[0])
    if resolved:
        cmd = [resolved] + list(cmd[1:])
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=timeout)
        return proc.returncode, proc.stdout.strip()
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def latest_on_pypi(name):
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=20) as resp:
            return json.load(resp)["info"]["version"]
    except Exception as e:
        print(f"  [warn] could not query PyPI for {name}: {e}")
        return None


def target_version(name):
    """Version to reach: the latest on PyPI, never below the safe minimum."""
    latest = latest_on_pypi(name)
    safe = SAFE_VERSIONS[name]
    if latest is None or vtuple(latest) < vtuple(safe):
        return safe, latest
    return latest, latest


def where_all(exe):
    code, out = run(["where", exe])
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def norm(path):
    return os.path.normcase(os.path.realpath(path))


def record(status, item, detail):
    summary.append((status, item, detail))
    print(f"  => [{status}] {detail}")


def short(text, lines=6):
    parts = text.splitlines()
    return "\n".join("     " + p for p in parts[-lines:])


# ---------------------------------------------------------------- 1. uv

def uv_version(path):
    code, out = run([path, "--version"])
    m = re.search(r"uv (\d+\.\d+\.\d+)", out)
    return m.group(1) if code == 0 and m else None


def uv_update_command(path):
    low = path.lower()
    if "\\scoop\\" in low:
        return ["scoop", "update", "uv"], "scoop"
    if "\\winget\\" in low:
        return ["winget", "upgrade", "--id", "astral-sh.uv", "-e",
                "--accept-source-agreements", "--accept-package-agreements"], "winget"
    parent = os.path.dirname(path)
    if os.path.basename(parent).lower() == "scripts":
        py = os.path.join(os.path.dirname(parent), "python.exe")
        if os.path.exists(py):
            return [py, "-m", "pip", "install", "--upgrade", "uv"], "pip"
    return [path, "self", "update"], "standalone (uv self update)"


def update_uv():
    print("\n=== 1. uv ===")
    target, latest = target_version("uv")
    print(f"  latest on PyPI: {latest or 'unknown'}   minimum safe: {SAFE_VERSIONS['uv']}")
    paths = where_all("uv")
    if not paths:
        record("MISSING", "uv", "uv not found on PATH (start.bat installs it on first run)")
        return
    seen = set()
    for path in paths:
        key = norm(path)
        if key in seen:
            continue
        seen.add(key)
        current = uv_version(path)
        cmd, method = uv_update_command(path)
        print(f"\n  {path}\n    version {current or 'unknown'}, installed via {method}")
        if current and vtuple(current) >= vtuple(target):
            record("OK", "uv", f"{path}: {current} is up to date")
            continue
        if CHECK_ONLY:
            record("UPDATE NEEDED", "uv", f"{path}: {current} -> {target} ({' '.join(cmd)})")
            continue
        env = dict(os.environ, UV_SYSTEM_CERTS="true")  # advisory: use the (updated) OS trust store
        code, out = run(cmd, env=env)
        new = uv_version(path)
        if new and vtuple(new) >= vtuple(SAFE_VERSIONS["uv"]) and (code == 0 or new != current):
            record("UPDATED", "uv", f"{path}: {current} -> {new}")
        else:
            record("FAILED", "uv", f"{path}: still {new}; command: {' '.join(cmd)}\n{short(out)}")


# ---------------------------------------------------------------- 2. / 3. pip

PROBE = ("import sys, json\n"
         "try:\n    import certifi; c = certifi.__version__\nexcept Exception:\n    c = None\n"
         "try:\n    import pip; p = pip.__version__\nexcept Exception:\n    p = None\n"
         "print(json.dumps({'version': sys.version.split()[0], 'venv': sys.prefix != sys.base_prefix,"
         " 'exe': sys.executable, 'pip': p, 'certifi': c}))")


def probe_python(path):
    code, out = run([path, "-c", PROBE], timeout=60)
    if code != 0:
        return None
    try:
        return json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return None


def pip_install(py, args):
    """Install with the interpreter's own pip; retry for externally managed (uv-managed) Pythons."""
    code, out = run([py, "-m", "pip", "install", "--disable-pip-version-check"] + args)
    if code != 0 and "externally-managed" in out.lower():
        code, out = run([py, "-m", "pip", "install", "--disable-pip-version-check",
                         "--break-system-packages"] + args)
    return code, out


def update_python_pip(py, info, pip_target, certifi_target):
    pip_v, certifi_v = info["pip"], info["certifi"]
    label = f"Python {info['version']} ({py})"
    if not pip_v:
        record("SKIPPED", "pip", f"{label}: no pip installed (not affected by pip's CA bundle)")
        return
    if vtuple(pip_v) >= vtuple(pip_target) and (not certifi_v or vtuple(certifi_v) >= vtuple(certifi_target)):
        record("OK", "pip", f"{label}: pip {pip_v}, certifi {certifi_v or '-'}")
        return
    if CHECK_ONLY:
        record("UPDATE NEEDED", "pip", f"{label}: pip {pip_v} -> {pip_target}, certifi {certifi_v or '-'}")
        return
    if vtuple(pip_v) < vtuple(SAFE_VERSIONS["pip"]):
        # Old pip trusts a vulnerable bundle: bootstrap from the hash-pinned wheel first
        code, out = pip_install(py, [PIP_PINNED_REQ])
        if code != 0:
            hint = " (try running as administrator)" if "access is denied" in out.lower() or "permission" in out.lower() else ""
            record("FAILED", "pip", f"{label}: pinned pip install failed{hint}\n{short(out)}")
            return
    pkgs = ["--upgrade", "pip"] + (["certifi"] if certifi_v else [])
    code, out = pip_install(py, pkgs)
    new = probe_python(py) or {}
    if code == 0 and vtuple(new.get("pip")) >= vtuple(SAFE_VERSIONS["pip"]):
        record("UPDATED", "pip", f"{label}: pip {pip_v} -> {new.get('pip')}, certifi {certifi_v or '-'} -> {new.get('certifi') or '-'}")
    else:
        record("FAILED", "pip", f"{label}: pip now {new.get('pip')}\n{short(out)}")


def system_pythons():
    exe_pattern = re.compile(r"([A-Za-z]:\\.*?python3?(?:\.\d+)?\.exe)", re.I)
    candidates = []
    for cmd in (["py", "-0p"], ["uv", "python", "list", "--only-installed"]):
        code, out = run(cmd)
        if code == 0:
            candidates += [m.group(1) for line in out.splitlines() for m in exe_pattern.finditer(line)]
    candidates += where_all("python") + where_all("python3")
    result, seen = [], set()
    for path in candidates:
        if "windowsapps" in path.lower() or not os.path.exists(path):
            continue  # Microsoft Store alias stubs
        info = probe_python(path)
        if not info or info["venv"]:
            continue
        key = norm(info["exe"])
        if key in seen:
            continue
        seen.add(key)
        result.append((info["exe"], info))
    return result


def update_system_pips():
    print("\n=== 2. System Python pip ===")
    pip_target, pip_latest = target_version("pip")
    certifi_target, certifi_latest = target_version("certifi")
    print(f"  latest pip: {pip_latest or 'unknown'}, certifi: {certifi_latest or 'unknown'}")
    pythons = system_pythons()
    if not pythons:
        record("MISSING", "pip", "no system Python interpreter found")
        return
    for py, info in pythons:
        print(f"\n  {py}\n    Python {info['version']}, pip {info['pip'] or '-'}, certifi {info['certifi'] or '-'}")
        update_python_pip(py, info, pip_target, certifi_target)


def update_venv_pips(venvs):
    print("\n=== 3. Virtual environment pip ===")
    pip_target, _ = target_version("pip")
    certifi_target, _ = target_version("certifi")
    uv = shutil.which("uv")
    for venv in venvs:
        py = os.path.join(venv, "Scripts", "python.exe")
        if not os.path.exists(py):
            record("MISSING", "venv", f"{venv}: no Scripts\\python.exe")
            continue
        info = probe_python(py)
        if not info:
            record("FAILED", "venv", f"{venv}: interpreter does not run")
            continue
        pip_v, certifi_v = info["pip"], info["certifi"]
        label = f"{venv} (Python {info['version']})"
        print(f"\n  {label}\n    pip {pip_v or '-'}, certifi {certifi_v or '-'}")
        pip_ok = pip_v and vtuple(pip_v) >= vtuple(pip_target)
        certifi_ok = not certifi_v or vtuple(certifi_v) >= vtuple(certifi_target)
        if pip_ok and certifi_ok:
            record("OK", "venv", f"{label}: pip {pip_v}, certifi {certifi_v or '-'}")
            continue
        if CHECK_ONLY:
            record("UPDATE NEEDED", "venv", f"{label}: pip {pip_v or '-'} -> {pip_target}, certifi {certifi_v or '-'}")
            continue
        if not uv:
            record("FAILED", "venv", f"{label}: uv not found on PATH")
            continue
        steps = []
        if not pip_v or vtuple(pip_v) < vtuple(SAFE_VERSIONS["pip"]):
            steps.append([uv, "pip", "install", "--python", py, PIP_PINNED_REQ])
        if vtuple(pip_target) > vtuple(SAFE_VERSIONS["pip"]):
            steps.append([uv, "pip", "install", "--python", py, "--upgrade", f"pip=={pip_target}"])
        if not certifi_ok:
            steps.append([uv, "pip", "install", "--python", py, "--upgrade", f"certifi>={SAFE_VERSIONS['certifi']}"])
        failed = None
        for cmd in steps:
            code, out = run(cmd)
            if code != 0:
                failed = (cmd, out)
                break
        new = probe_python(py) or {}
        if failed:
            record("FAILED", "venv", f"{label}: {' '.join(failed[0][:4])} ...\n{short(failed[1])}"
                   "\n     (close the bot first if files are in use)")
        else:
            record("UPDATED", "venv", f"{label}: pip {pip_v or '-'} -> {new.get('pip')}, "
                   f"certifi {certifi_v or '-'} -> {new.get('certifi') or '-'}")


# ---------------------------------------------------------------- main

def main():
    global CHECK_ONLY
    parser = argparse.ArgumentParser(description="Update uv, system pip and venv pip (eMudhra / emSign CA incident)")
    parser.add_argument("--check", action="store_true", help="Report only, do not change anything")
    parser.add_argument("--venv", action="append", help="Virtual environment folder (default: project .venv)")
    args = parser.parse_args()
    CHECK_ONLY = args.check
    venvs = args.venv or [os.path.join(ROOT, ".venv")]

    print("Toolchain update for the eMudhra / emSign CA incident")
    print(f"Minimum safe versions: uv {SAFE_VERSIONS['uv']}, pip {SAFE_VERSIONS['pip']}, certifi {SAFE_VERSIONS['certifi']}")
    if CHECK_ONLY:
        print("Mode: CHECK ONLY (no changes)")

    update_uv()
    update_system_pips()
    update_venv_pips(venvs)

    print("\n=== Summary ===")
    for status, item, detail in summary:
        print(f"  [{status:<13}] {item:<5} {detail.splitlines()[0]}")
    bad = [s for s in summary if s[0] in ("FAILED", "UPDATE NEEDED")]
    if bad:
        print(f"\n{len(bad)} item(s) need attention.")
        return 1
    print("\nAll checked tools are at or above the safe versions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
