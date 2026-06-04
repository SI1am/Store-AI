#!/usr/bin/env python3
"""
StoreLens - Unified Launcher
===================================================
Starts backend services with a single command:
  1. FastAPI REST API Server     (port 8000)
  2. Detection Stream Server     (port 8001)

Usage:
    python launch.py              # Start all services
    python launch.py --api        # Start API only
    python launch.py --stream     # Start stream server only

Press Ctrl+C to gracefully stop all services.
"""

import os
import sys
import signal
import subprocess
import argparse
import time
from pathlib import Path

# Enable ANSI escape codes on Windows 10+
if sys.platform == "win32":
    os.system("")

# --- Configuration ---

ROOT_DIR = Path(__file__).resolve().parent

SERVICES = {
    "api": {
        "name": "API Server",
        "cmd": [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
        "cwd": str(ROOT_DIR),
        "url": "http://127.0.0.1:8000",
        "color": "\033[96m",  # Cyan
    },
    "stream": {
        "name": "Stream Server",
        "cmd": [sys.executable, "detection/stream_server.py"],
        "cwd": str(ROOT_DIR),
        "url": "http://127.0.0.1:8001",
        "color": "\033[93m",  # Yellow
    },
}

# --- Colors ---

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"

# --- Process Management ---

processes: dict[str, subprocess.Popen] = {}


def print_banner():
    """Display startup banner."""
    print(f"""
{MAGENTA}{BOLD}  +-------------------------------------------------------+
  |              StoreLens                                 |
  |         Unified Service Launcher                       |
  +-------------------------------------------------------+{RESET}
""")


def start_service(key: str) -> subprocess.Popen | None:
    """Start a single service by key."""
    svc = SERVICES[key]
    color = svc["color"]
    name = svc["name"]

    print(f"  {color}> Starting {name}...{RESET}")
    print(f"    Command : {' '.join(svc['cmd'])}")
    print(f"    Work Dir: {svc['cwd']}")
    print(f"    URL     : {svc['url']}")

    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        # Let child processes inherit the console so their output flows directly
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=svc["cwd"],
            **kwargs,
        )
        print(f"    {GREEN}[OK] {name} started (PID: {proc.pid}){RESET}\n")
        return proc

    except FileNotFoundError as e:
        print(f"    {RED}[FAIL] Failed to start {name}: {e}{RESET}")
        print(f"    {YELLOW}  Hint: Make sure dependencies are installed.{RESET}\n")
        return None
    except Exception as e:
        print(f"    {RED}[FAIL] Failed to start {name}: {e}{RESET}\n")
        return None


def stop_all():
    """Gracefully terminate all running processes."""
    print(f"\n{YELLOW}{BOLD}[STOP] Shutting down all services...{RESET}")

    for key, proc in processes.items():
        svc = SERVICES[key]
        if proc and proc.poll() is None:
            print(f"  {svc['color']}[-] Stopping {svc['name']} (PID: {proc.pid})...{RESET}", end=" ")
            try:
                if sys.platform == "win32":
                    proc.terminate()
                else:
                    proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=5)
                print(f"{GREEN}done{RESET}")
            except subprocess.TimeoutExpired:
                print(f"{RED}force killing...{RESET}", end=" ")
                proc.kill()
                proc.wait()
                print(f"{GREEN}done{RESET}")
            except Exception as e:
                print(f"{RED}error: {e}{RESET}")

    print(f"\n{GREEN}{BOLD}[OK] All services stopped.{RESET}\n")


def signal_handler(signum, frame):
    """Handle Ctrl+C."""
    stop_all()
    sys.exit(0)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="StoreLens Unified Launcher - Start all services with one command"
    )
    parser.add_argument("--api", action="store_true", help="Start only the API server")
    parser.add_argument("--stream", action="store_true", help="Start only the stream server")
    args = parser.parse_args()

    # If no flags, start everything
    start_all = not (args.api or args.stream)
    services_to_start = []

    if start_all or args.api:
        services_to_start.append("api")
    if start_all or args.stream:
        services_to_start.append("stream")

    # Register signal handler for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print_banner()

    # Preflight checks
    print(f"{CYAN}[*] Preflight Checks{RESET}")
    print(f"    Python  : {sys.version.split()[0]}")
    print(f"    Platform: {sys.platform}")
    print(f"    Root Dir: {ROOT_DIR}")

    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        print(f"\n  {YELLOW}[!] .env file not found. Using defaults.{RESET}")
        print(f"  {YELLOW}    Copy .env.example to .env and configure your settings.{RESET}")

    # Start services
    print(f"\n{CYAN}[*] Starting Services{RESET}\n")

    for key in services_to_start:
        proc = start_service(key)
        if proc:
            processes[key] = proc
        time.sleep(2)  # Stagger service startup

    if not processes:
        print(f"\n{RED}[FAIL] No services were started. Check the errors above.{RESET}")
        sys.exit(1)

    # Summary
    print(f"{GREEN}{BOLD}==================================================={RESET}")
    print(f"{GREEN}{BOLD}  All services are running!{RESET}")
    print(f"{GREEN}{BOLD}==================================================={RESET}\n")

    for key in processes:
        svc = SERVICES[key]
        print(f"  {svc['color']}* {svc['name']:20s} -> {svc['url']}{RESET}")

    print(f"\n  {YELLOW}Press Ctrl+C to stop all services.{RESET}\n")

    # Wait for any child to exit
    try:
        while True:
            for key, proc in list(processes.items()):
                ret = proc.poll()
                if ret is not None:
                    svc = SERVICES[key]
                    if ret != 0:
                        print(f"\n  {RED}[FAIL] {svc['name']} exited with code {ret}{RESET}")
                    else:
                        print(f"\n  {YELLOW}[INFO] {svc['name']} exited normally.{RESET}")
                    del processes[key]

            if not processes:
                print(f"\n{YELLOW}All services have exited.{RESET}")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    main()