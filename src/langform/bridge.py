"""Outbound-only paired bridge. Run with python -m langform.bridge --help."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
from .bridge_local import LocalBridge
from .storage import JSONStore
from .models import OllamaSLM

BRIDGE_VERSION = "1.0.0"
SUPPORTED_OBJECTIVES = ("processing", "packaging")
SUPPORTED_OPERATIONS = (
    "classify_project_prompt", "resolve_project_sources", "summarize_project",
    "process_project_asset", "package_project_context", "list_sources",
    "register_sources", "import_assets", "list_assets", "analyze_asset",
    "frame_index", "asset_structure", "inspect_frame", "refine_frame",
    "edit_frame", "split_frame", "merge_frames", "lock_frame", "get_package",
    "prepare_context", "baseline_context", "long_context",
)

def capability_report() -> dict:
    """Bridge protocol version, separate from the installed Python package version."""
    return {"bridgeVersion": BRIDGE_VERSION, "supportedObjectives": list(SUPPORTED_OBJECTIVES),
            "supportedOperations": list(SUPPORTED_OPERATIONS)}

def ollama_report(base_url: str, previous_models: list[str]) -> dict:
    """Bound the health probe separately from inference; never transmit errors or URLs."""
    try:
        installed = OllamaSLM(base_url=base_url, timeout=5).list_models()
        models = [item["name"] for item in installed
                  if isinstance(item.get("name"), str) and 0 < len(item["name"]) <= 150][:128]
        report = {"ollamaStatus": "reachable", "models": models}
        mappings = OllamaSLM(base_url=base_url, timeout=5).model_mappings(installed)
        # Old exact-only reports remain wire compatible.
        if any((m["runtimeTag"] == "gemma3" or m["runtimeTag"].startswith("gemma3:"))
               and m["runtimeTag"] != "gemma3:4b" and not m["runtimeTag"].startswith("gemma3:4b-")
               for m in mappings):
            report["modelMappings"] = mappings
        return report
    except Exception:
        # A failed inventory query cannot establish that any model is absent.
        return {"ollamaStatus": "unreachable", "models": previous_models[:128]}


class Transport:
    def __init__(self, server: str, token: str | None = None):
        parsed = urlparse(server)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Server URL cannot contain credentials, query parameters, or fragments.")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("Use HTTPS, except for local loopback Development testing.")
        self.server, self.token = server.rstrip("/"), token

    def call(self, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(f"{self.server}/api/harness/bridge/{path}", data=data, headers=headers)
        # Never redirect a bridge bearer credential to another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=25) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError("Bridge response exceeds the eight-megabyte budget.")
            return json.loads(raw)


def pairing_url(server: str, code: str | None = None) -> str:
    # Codes stay in the fragment, not server logs or referrer query strings.
    return f"{server}/connections" + (f"#pair={code}" if code else "")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pair a local Context SLM with LangFORM projects. No inbound port is opened.")
    parser.add_argument("--server", required=True, help="HTTPS address of your LangFORM app")
    parser.add_argument("--workspace", default=".langform", help="Private local LangFORM data directory")
    parser.add_argument("--allow", action="append", default=[], help="Explicit file or folder grant; omit for models-only access")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--label", default="Local Context SLM")
    parser.add_argument("--re-pair", action="store_true", help="Request a new pairing code and renew the 90-day device authorization")
    parser.add_argument("--open-browser", action="store_true", help="Open Local Connections; pairing still requires browser approval")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    bridge = LocalBridge(workspace, [Path(path) for path in args.allow], args.ollama_url)
    transport = Transport(args.server)
    credential_path = workspace / "bridge" / "device.json"
    credential = JSONStore(credential_path, {})
    stored = credential.load()
    browser_url = pairing_url(transport.server)
    reuse = stored.get("server") == transport.server and stored.get("deviceToken") and not args.re_pair
    if reuse and args.open_browser:
        transport.token = stored["deviceToken"]
        try:
            state = transport.call("heartbeat", {**ollama_report(args.ollama_url, []),
                                   "grantedRoots": [str(path) for path in bridge.grants], **capability_report()})
            if not state.get("paired"):
                # Re-open an unfinished pairing, rather than hiding its code on restart.
                code = stored.get("pairingCode")
                if code:
                    print(f"Pairing code: {code}")
                    browser_url = pairing_url(transport.server, code)
                else:
                    reuse = False
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise
            reuse = False  # Expired/revoked credentials still require browser approval.
    if reuse:
        transport.token = stored["deviceToken"]
    else:
        registration = transport.call("register", {"label": args.label, "grantedRoots": [str(path) for path in bridge.grants], **capability_report()})
        transport.token = registration["deviceToken"]
        credential.save({"server": transport.server, "deviceToken": transport.token,
                         "bridgeId": registration["bridgeId"], "pairingCode": registration["pairingCode"]})
        os.chmod(credential_path, 0o600)
        print(f"Pairing code: {registration['pairingCode']} (expires in five minutes)")
        browser_url = pairing_url(transport.server, registration["pairingCode"])
        print("Open Local Connections and approve pairing. Device credentials are stored privately, never printed.")
    if args.open_browser:
        try:
            if not webbrowser.open(browser_url):
                print("Browser could not open. Open Local Connections and enter the printed code.")
        except Exception:
            print("Browser could not open. Open Local Connections and enter the printed code.")
    stop = threading.Event()

    def heartbeat():
        models = []
        while not stop.is_set():
            try:
                health = ollama_report(args.ollama_url, models)
                models = health["models"]
                transport.call("heartbeat", {**health, "grantedRoots": [str(path) for path in bridge.grants], **capability_report()})
            except Exception:
                pass
            stop.wait(15)

    threading.Thread(target=heartbeat, daemon=True).start()
    print("Bridge running. Only granted files and explicitly imported hosted Assets are accessible. No model is downloaded automatically.")
    cache = JSONStore(workspace / "bridge" / "completed-jobs.json", {})
    pending = None
    try:
        while True:
            try:
                if pending:
                    job_id, completion = pending
                    transport.call(f"jobs/{job_id}/complete", completion)
                    pending = None
                    continue
                response = transport.call("jobs")
                job = response.get("job")
                if not job:
                    time.sleep(1.5)
                    continue
                completed = cache.load()
                result = completed.get(job["id"])
                if result is None:
                    try:
                        def report_progress(event):
                            try:
                                transport.call(f"jobs/{job['id']}/progress", {"event": event})
                            except urllib.error.HTTPError as error:
                                if error.code in {401, 404, 409}:
                                    raise ValueError("Local context operation cancelled or invalidated.") from error
                                print("Progress delivery unavailable; local processing continues.", file=sys.stderr)
                            except Exception:
                                print("Progress delivery unavailable; local processing continues.", file=sys.stderr)
                        bridge.on_progress = report_progress
                        output = bridge.execute(job["operation"], job["args"])
                        result = {"result": output, "error": None}
                        if len(json.dumps(result).encode()) > 900_000:
                            result = {"result": None, "error": "Local result exceeds the bridge payload budget. Narrow the scope or use smaller Frames."}
                    except Exception as error:
                        # Local errors contain no device/provider credentials.
                        safe = str(error) if isinstance(error, (ValueError, PermissionError, KeyError)) else "Local operation failed. Check Ollama and the granted source files."
                        result = {"result": None, "error": safe[:500]}
                    finally:
                        bridge.on_progress = None
                    completed[job["id"]] = result
                    cache.save(dict(list(completed.items())[-100:]))
                # Retry delivery, not the operation, after a connection loss.
                pending = (job["id"], result)
            except urllib.error.HTTPError as error:
                if error.code in (404, 409) and pending:
                    pending = None  # Already delivered, cancelled, or interrupted.
                    continue
                if error.code == 401:
                    print("Bridge expired or revoked. Run the setup launcher again, or restart python -m langform.bridge with --re-pair and the same --server, --workspace and --allow arguments. Enter the new code in Local Connections, then select the new connection in project Configuration.")
                    return 1
                print("Server request failed; retrying without exposing credentials.")
                time.sleep(3)
            except (OSError, ValueError):
                print("Connection unavailable; retrying.")
                time.sleep(3)
    except KeyboardInterrupt:
        print("Bridge stopped.")
        return 0
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
