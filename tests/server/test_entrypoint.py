"""Smoke test for `python -m vlogkit.server`."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.timeout(30)
def test_module_entrypoint_starts_and_responds(tmp_path: Path) -> None:
    port = _free_port()
    token = "smoke-test-token"
    registry = tmp_path / "projects.json"

    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vlogkit.server",
            "--port",
            str(port),
            "--token",
            token,
            "--registry",
            str(registry),
            "--bind",
            "127.0.0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Poll /healthz
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            stdout, stderr = proc.communicate(timeout=2)
            pytest.fail(
                f"server never became ready. stdout={stdout!r} stderr={stderr!r}"
            )

        # Auth'd /projects
        r = httpx.get(
            f"http://127.0.0.1:{port}/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        assert r.status_code == 200
        assert r.json() == []
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.timeout(30)
def test_module_entrypoint_reads_token_from_env(tmp_path: Path) -> None:
    port = _free_port()
    token = "env-token-xyz"
    registry = tmp_path / "projects.json"

    env = os.environ.copy()
    env["VLOGKIT_TOKEN"] = token
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "vlogkit.server",
            "--port", str(port),
            "--registry", str(registry),
            "--bind", "127.0.0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            stdout, stderr = proc.communicate(timeout=2)
            pytest.fail(f"server never became ready. stdout={stdout!r} stderr={stderr!r}")

        r = httpx.get(
            f"http://127.0.0.1:{port}/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        assert r.status_code == 200
        assert r.json() == []
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
