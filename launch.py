"""Open the local Windows app once its HTTP server is ready."""
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser


def ready(url):
    try:
        with urllib.request.urlopen(url + "api/config", timeout=1) as response:
            config = json.load(response)
        return isinstance(config, dict) and {"municipality_name", "election_datetime_iso"} <= config.keys()
    except (OSError, ValueError):
        return False


def show(url):
    print(f"Open CiviConnect at {url}", flush=True)
    if sys.stdout.isatty():
        webbrowser.open(url)


def main():
    port = int(os.environ.get("UVICORN_PORT", "8000"))
    url = f"http://127.0.0.1:{port}/"
    if ready(url):
        print("CiviConnect is already running.")
        show(url)
        return 0
    print(f"Starting the server on {url}", flush=True)
    with subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host",
                           "127.0.0.1", "--port", str(port), "--log-level", "warning"]) as server:
        try:
            deadline = time.monotonic() + 60
            while server.poll() is None:
                if ready(url):
                    print("Keep this window open while using the app.")
                    show(url)
                    return server.wait()
                if time.monotonic() >= deadline:
                    raise RuntimeError("The server did not become ready within 60 seconds.")
                time.sleep(0.25)
            return server.returncode
        except KeyboardInterrupt:
            return 0
        finally:
            if server.poll() is None:
                server.terminate()


if __name__ == "__main__":
    sys.exit(main())
