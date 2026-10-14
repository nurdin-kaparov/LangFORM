LangFORM for Windows (x64)

1. Extract the ZIP, then double-click LangFORM.exe.
2. Enter the HTTPS address of your LangFORM website when asked.
3. Approve connecting to that website.
4. Optionally approve a folder. Choose No to connect models only.
5. Approve the pairing code in the website's Local Connections page.
6. Keep the LangFORM window open while using your local SLM.

Python and document-reading dependencies are included in the executable.
Ollama and a supported SLM must be installed separately. Existing models are reused;
no model weights are downloaded automatically. No administrator access is required.

This is an unsigned portable executable, not a signed installer or background
startup service. Windows may show a SmartScreen warning. Verify the download's
origin and SHA256SUMS.txt before deciding whether to run it; do not disable your
security software. The checksum verifies file consistency, not publisher identity.

Advanced:
  LangFORM.exe --server https://YOUR-LANGFORM-WEBSITE
  LangFORM.exe --change-folder
  LangFORM.exe --re-pair
  LangFORM.exe --help

To avoid entering the website address, put langform-connection.json beside the
executable with this content (replace the address):
  {"server": "https://YOUR-LANGFORM-WEBSITE"}
The configuration must not contain device tokens or any other credentials.

Settings and device credentials remain under %USERPROFILE%\.langform.
Never share companion-workspace, which contains your private device credential.
The bridge makes outbound connections; it does not open an inbound server port.
Source files stay local. Prompts, returned metadata, and evidence are stored by
the hosted app under your account. Stop with Ctrl+C or close the window.
Changing the folder does not silently expand existing project source selections.

macOS and Linux need separately built executables; this file is Windows x64 only.
