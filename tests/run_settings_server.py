"""Disposable API + migrated Postgres for browser tests; never uses the developer DB."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from testcontainers.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[1]


def main():
    process = None

    def stop(signum, frame):
        if process is not None:
            process.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        env = os.environ | {
            "DATABASE_URL": pg.get_connection_url(),
            "LLM_CONFIG_API_KEY_SECRET": "browser-test-only-key-not-for-production",
            "TEXT_QUALITY_DEFAULT_MIN_THAI_PERCENT": "43",
            "TEXT_QUALITY_DEFAULT_MAX_GARBLED_THAI_PERCENT": "7",
            "TEXT_QUALITY_DEFAULT_MIN_TEXT_CHARS": "64",
            "TEXT_QUALITY_DEFAULT_MAX_IMAGE_PERCENT": "81",
        }
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "check"], cwd=ROOT, env=env, check=True
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.settings_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                os.environ.get("SETTINGS_TEST_API_PORT", "8011"),
            ],
            cwd=ROOT,
            env=env,
        )
        try:
            process.wait()
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
