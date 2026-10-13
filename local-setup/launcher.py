"""User-approved local setup. Distributed with a code-only package payload."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urlparse
import venv
import zlib

APP_SERVER = "__LANGFORM_SERVER__"
PACKAGE = "__LF_PACKAGE__"


def validate_server(value: str) -> str:
    parsed = urlparse(value)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or not parsed.hostname):
        raise ValueError("The app address must be a plain HTTPS origin.")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("HTTPS is required except for loopback development.")
    return value.rstrip("/")


def unpack_package(destination: Path, payload: str = PACKAGE) -> None:
    files = json.loads(zlib.decompress(base64.b64decode(payload)))
    root = destination.resolve()
    for name, content in files.items():
        target = (root / name).resolve()
        if not target.is_relative_to(root) or "\\" in name:
            raise ValueError("Invalid setup package path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def ask(question: str) -> bool:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        try:
            return messagebox.askyesno("LangFORM local setup", question, parent=root)
        finally:
            root.destroy()
    except (ImportError, RuntimeError):
        return input(f"{question}\nApprove? [y/N] ").strip().lower() in {"y", "yes"}
    except Exception as error:
        # Headless Linux may have tkinter installed but no display.
        if error.__class__.__name__ != "TclError":
            raise
        return input(f"{question}\nApprove? [y/N] ").strip().lower() in {"y", "yes"}


def choose_folder() -> str | None:
    if not ask("Allow LangFORM to read a folder you choose?\n\n"
               "Choose No to connect Ollama without any local-file access. "
               "Run this launcher with --change-folder to change folder access later."):
        return None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try:
            selected = filedialog.askdirectory(title="Choose an approved evidence folder", parent=root)
        finally:
            root.destroy()
    except Exception as error:
        if not isinstance(error, (ImportError, RuntimeError)) and error.__class__.__name__ != "TclError":
            raise
        selected = input("Approved folder path (blank cancels file access): ").strip().strip('"')
    if not selected:
        return None
    folder = Path(selected).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Select an existing folder.")
    return str(folder)


def ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def existing_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required. Install it from https://www.python.org/downloads/ and run again.")
        return 1
    server = validate_server(APP_SERVER)
    home = Path.home() / ".langform"
    settings_path = home / "companion-settings.json"
    settings = {}
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            print("Saved setup settings are unreadable. Asking for fresh approval.")
    fingerprint = hashlib.sha256(PACKAGE.encode()).hexdigest()
    same_setup = settings.get("server") == server and settings.get("packageHash") == fingerprint
    if not same_setup and not ask(f"Connect this PC to {server}?\n\n"
               "Install/update the LangFORM bridge in a private local Python environment. "
               "Python dependencies may be downloaded from PyPI. Existing Ollama and models "
               "will be reused; no model is downloaded. No administrator access is requested."):
        print("Setup cancelled. No installation or file access was performed.")
        return 0
    source = home / "companion-source"
    environment = home / "companion-python"
    workspace = home / "companion-workspace"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install_needed = not same_setup or not python.is_file()
    if install_needed:
        unpack_package(source)
    if not python.is_file():
        print("Preparing the isolated local Python environment…")
        venv.EnvBuilder(with_pip=True).create(environment)
    if install_needed:
        print("Installing/updating the local bridge. Existing Ollama models are not modified.")
        subprocess.run([str(python), "-m", "pip", "install", "--no-input",
                        "--disable-pip-version-check", "--upgrade",
                        f"{source}[ollama,documents]"], check=True)
    if not ollama_reachable():
        command = existing_ollama()
        if command and ask("Ollama is installed but not responding. Start your existing Ollama server?"):
            subprocess.Popen([command, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("Open Ollama on this PC. The connection page will show when it becomes reachable.")
    if same_setup and "--change-folder" not in sys.argv:
        folder = settings.get("folder")
        if folder and not Path(folder).is_dir():
            print("Previously approved folder is unavailable. No file grant will be made.")
            folder = None
    else:
        folder = choose_folder()
    settings_path.write_text(json.dumps({"server": server, "packageHash": fingerprint, "folder": folder}), encoding="utf-8")
    os.chmod(settings_path, 0o600)
    arguments = [str(python), "-m", "langform.bridge", "--server", server,
                 "--workspace", str(workspace), "--open-browser"]
    if folder:
        arguments += ["--allow", folder]
    print("Starting the local connection. Keep this window open; Ctrl+C disconnects.")
    # Pairing and device credentials remain owned by the bridge, not this launcher.
    return subprocess.call(arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Setup stopped.")
        raise SystemExit(0)
    except Exception as error:
        print(f"Setup failed: {error}\nNothing was paired automatically. Check internet access and Python, then run again.")
        raise SystemExit(1)
