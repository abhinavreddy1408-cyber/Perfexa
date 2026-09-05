"""
Docker Detection and Dual-Mode Execution Utilities.
Detects whether Docker daemon is installed and actively running.
Provides host/URL resolution between container network (target-app:8001)
and native localhost (127.0.0.1:8001).
"""

import logging
import os
import shutil
import subprocess
import time
from typing import Optional

from backend.app.config import TARGET_APP_URL, LOCAL_TARGET_APP_URL

logger = logging.getLogger("docker_utils")

_cached_docker_status: Optional[bool] = None
_last_check_time: float = 0.0
_CHECK_CACHE_TTL = 10.0  # Cache for 10 seconds to avoid repeated subprocess calls


def is_docker_running() -> bool:
    """
    Checks if Docker CLI is installed AND Docker daemon is actively running and responsive.
    Caches result for 10 seconds to keep performance high.
    """
    global _cached_docker_status, _last_check_time
    now = time.time()
    if _cached_docker_status is not None and (now - _last_check_time < _CHECK_CACHE_TTL):
        return _cached_docker_status

    docker_bin = shutil.which("docker")
    if not docker_bin:
        _cached_docker_status = False
        _last_check_time = now
        return False

    try:
        proc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2.5
        )
        _cached_docker_status = (proc.returncode == 0)
    except Exception as e:
        logger.debug(f"Docker availability check failed: {e}")
        _cached_docker_status = False

    _last_check_time = now
    return _cached_docker_status


def get_effective_target_url(explicit_url: Optional[str] = None) -> str:
    """
    Returns the appropriate target URL based on Docker's active runtime state.
    - If Docker is running: defaults to container hostname (http://target-app:8001).
    - If Docker is absent/down: defaults to native localhost (http://127.0.0.1:8001).
    - If an explicit URL is provided (e.g. containing target-app:8001) but Docker is not running,
      it automatically normalizes it to 127.0.0.1:8001 so native k6 execution succeeds.
    """
    has_docker = is_docker_running()
    
    if explicit_url and explicit_url.strip():
        url = explicit_url.strip()
        if not has_docker:
            # Normalize container host to local host
            url = (
                url
                .replace("target-app:8001", "127.0.0.1:8001")
                .replace("http://target-app", "http://127.0.0.1:8001")
                .replace("localhost:8001", "127.0.0.1:8001")
            )
        return url

    if has_docker:
        return TARGET_APP_URL
    else:
        return LOCAL_TARGET_APP_URL.replace("localhost:8001", "127.0.0.1:8001")


def normalize_script_target_urls(script_code: str) -> str:
    """
    Ensures that script code targets 127.0.0.1:8001 if Docker is not running,
    or target-app:8001 if Docker is running inside perf-net.
    """
    if not is_docker_running():
        return (
            script_code
            .replace("target-app:8001", "127.0.0.1:8001")
            .replace("http://target-app", "http://127.0.0.1:8001")
            .replace("localhost:8001", "127.0.0.1:8001")
        )
    return script_code
