"""Run the whole test suite with network access disabled, as the CI checks do.

Any attempt to open a connection fails, so a test that would fetch prices
from a shop fails instead of reaching the network. Skipped tests also fail
the run: in CI the dashboard dependencies are installed, and a skip means
they are missing.

Usage:
    python tests/offline.py
"""

import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _no_network(*args, **kwargs):
    raise OSError("network access is disabled in the test run")


def main():
    socket.socket.connect = _no_network
    socket.socket.connect_ex = _no_network
    socket.create_connection = _no_network
    socket.getaddrinfo = _no_network

    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print(f"{len(result.skipped)} tests skipped; install requirements-dashboard.txt", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
