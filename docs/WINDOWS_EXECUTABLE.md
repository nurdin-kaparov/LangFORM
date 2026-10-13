# Windows executable

LangFORM remains Python software. The Windows companion packages its Python runtime,
bridge, document readers, and TLS certificates into `LangFORM.exe`. Users of that
executable do not install Python or download Python dependencies at startup.

## Build and verification

Build on Windows x64 with Python 3.11:

```powershell
./local-setup/build-windows.ps1
```

The script installs build dependencies, invokes PyInstaller, runs an offline
executable smoke check, and produces:

- `generated-artifacts/windows/LangFORM.exe`
- `generated-artifacts/windows/SHA256SUMS.txt`
- `generated-artifacts/LangFORM-windows-x64.zip`

These are generated build outputs and are excluded from Git and app deployment.
Do not commit binaries, credentials, user settings, or local source collections.

The GitHub Actions workflow `Build LangFORM Windows executable` runs the build on
`windows-2022`, verifies setup behavior, and runs the executable with Python removed
from `PATH`. A passing run provides a downloadable artifact for 30 days. It does
not create a public release, publish the web app, or change any database.

The Windows runtime check exercises bundled XLSX, DOCX, and PDF readers, TLS
certificates, Tcl, bridge capabilities, and a models-only scope without network
access. It is not an interactive Windows pairing or Ollama inference test.

## Running

Extract the ZIP and double-click `LangFORM.exe`. Enter the LangFORM website's HTTPS
origin, approve connecting, optionally grant a folder, and approve browser pairing.
The same existing bridge protocol handles model inventory and context jobs.
Ollama and model weights are not included.

To preconfigure a downloaded executable for a website, place this non-secret
configuration beside it:

```json
{"server": "https://YOUR-LANGFORM-WEBSITE"}
```

Save it as `langform-connection.json`. Never put bearer credentials in this file.
For a portable command-line launch:

```powershell
.\LangFORM.exe --server https://YOUR-LANGFORM-WEBSITE
.\LangFORM.exe --change-folder
.\LangFORM.exe --re-pair
```

The executable uses `%USERPROFILE%\.langform\companion-workspace`, preserving the
existing bridge's private credentials and data when the approved server matches.
It stores its server/folder preferences separately from the older Python launcher.
First native launch asks for consent again. A new server never inherits an old
server's folder approval.

## Distribution boundaries

This is an unsigned portable Windows x64 executable, not a signed installer or
background startup service. SmartScreen can warn. A checksum is not a publisher
signature; do not ask users to disable security software.

The web app's existing Python launcher remains unchanged until a successfully
built Windows binary is made available through an approved download channel.
Do not label that older ZIP as Python-free or claim an executable exists merely
because the packaging sources exist. macOS/Linux require separate builds.
