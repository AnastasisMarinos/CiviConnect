"""Run the local CiviConnect server in the calling console."""
import argparse
import json
import os
import socket
import sys
import urllib.request
import webbrowser
from threading import Event, Thread

from civiconnect.local_process import control_server
from civiconnect.runtime_build import build_identifier

HOST = "127.0.0.1"


def running_build(url):
    try:
        with urllib.request.urlopen(url + "api/health", timeout=1) as response:
            health = json.load(response)
        if health["app"] == "CiviConnect" and isinstance(health["build"], str):
            return health["build"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def port_available(port):
    with socket.socket() as listener:
        try:
            listener.bind((HOST, port))
        except OSError:
            return False
    return True


def open_when_ready(server, url, stopped):
    while not stopped.wait(0.1):
        if not server.started or server.should_exit:
            continue
        try:
            if webbrowser.open(url):
                return
        except (OSError, webbrowser.Error):
            pass
        print(f"Could not open the browser. Open {url} manually.", flush=True)
        return


def main(action="start"):
    port = int(os.environ.get("UVICORN_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("UVICORN_PORT must be between 1 and 65535.")
    if action != "start":
        result = control_server(port, action)
        if result.stdout:
            print(result.stdout, end="", flush=True)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr, flush=True)
        return result.returncode

    url = f"http://{HOST}:{port}/"
    build = build_identifier()
    if not port_available(port):
        found = running_build(url)
        occupant = f"CiviConnect build {found}" if found else "an older server or another app"
        print(f"Port {port} is in use by {occupant}.", flush=True)
        print("Use start.bat status to identify it. For CiviConnect, close its console or run start.bat stop.", flush=True)
        return 1

    import uvicorn

    print(f"Starting CiviConnect build {build} on {url}", flush=True)
    print("Keep this window open. Press Ctrl+C to stop the server.", flush=True)
    server = uvicorn.Server(uvicorn.Config("app:app", host=HOST, port=port, log_level="info"))
    stopped = Event()
    Thread(target=open_when_ready, args=(server, url, stopped), daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        return 0
    finally:
        stopped.set()
    return 0 if server.started else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", type=str.lower, default="start", choices=("start", "status", "stop"))
    sys.exit(main(parser.parse_args().action))
