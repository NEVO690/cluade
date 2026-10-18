# AVEN AI Desktop: release checklist

Work through this list on a clean **Windows 11 x64** machine for every public release.

## 1. Version and changelog
- [ ] Bump `__version__` and `VERSION_TUPLE` in `app/version.py`, and `version` in `pyproject.toml`
- [ ] Write the release notes: new features, fixes, known issues
- [ ] Make sure the database schema migrations in `app/storage/database.py` are additive (never edit an existing migration)

## 2. Quality gates
- [ ] `ruff check .` passes
- [ ] `python -m pytest -q` passes (the build script runs this)
- [ ] Search for secrets: no API keys in source, `.env`, test fixtures or `assets/`
  (for example `git grep -nE "sk-[A-Za-z0-9]{20,}"`)

## 3. Build
- [ ] Run `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1` from a clean checkout
- [ ] Confirm that `dist\AVEN AI\AVEN AI.exe` exists, shows the AVEN icon, and that *Properties → Details* shows the correct version
- [ ] Optional: `-OneFile` build, if you also publish a single-file version

## 4. Smoke test the packaged build
Run these on a machine **without Python installed** and **without** `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` set:
- [ ] First launch shows the setup card, and no console window appears
- [ ] Settings → AI Provider: save a key, then **Test connection** succeeds with a real key
- [ ] Test connection with a wrong key shows “Invalid API key”
- [ ] Send messages in AVEN and AVEN CODE. Streaming works, **Stop** works, **Copy code** works.
- [ ] Turn off the network and send a message: a clear “Connection problem” appears and Retry works once the network is back
- [ ] Rename, delete, restart the app: conversations persist
- [ ] Light, dark and match-Windows themes all render correctly. Resize the window down to its minimum size.
- [ ] Install the new build over the previous release: existing conversations are still there
- [ ] `%APPDATA%\AVEN AI\logs\aven.log` contains no message contents and no API keys

## 5. Code signing (removes the "Windows protected your PC" warning)
Unsigned executables trigger Windows SmartScreen warnings, and only a code-signing certificate removes them. Options:

- **Free, for open-source projects: [SignPath Foundation](https://signpath.org).** The project must be public with an OSI-approved licence (add a `LICENSE` file first). Apply on their site; once approved, they sign the release builds.
- **Microsoft Trusted Signing / Azure Artifact Signing.** A low monthly fee; identity verification required.
- **A standard OV or EV certificate** from a certificate authority (Sectigo, DigiCert, SSL.com, …). Paid yearly.

To make the CI build sign automatically with a `.pfx` certificate:
- [ ] Encode it: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx")) | Set-Clipboard`
- [ ] GitHub → **Settings → Secrets and variables → Actions → New repository secret**:
  - `AVEN_SIGN_PFX_BASE64` = the encoded certificate
  - `AVEN_SIGN_PFX_PASSWORD` = its password
- [ ] Run the workflow. The exe and the installer are signed and verified with `signtool`, and the log says "code-signed".
- [ ] Only describe the release as signed if these steps were actually done.

A new certificate still needs some download "reputation" before SmartScreen stops warning. EV certificates get it immediately.

## 6. Packaging for download
- [ ] Distribute `dist\AVEN-AI-Setup-<version>.exe` (the installer). Optionally also offer `dist\AVEN-AI-Desktop-<version>-win64.zip` as a portable version
- [ ] Check that the CI "Microsoft Defender scan" step reported no threats
- [ ] Publish SHA-256 checksums: `Get-FileHash .\dist\AVEN-AI-Desktop-<version>-win64.zip -Algorithm SHA256`
- [ ] Upload to the official AVEN AI website and check that the download link and checksum match
- [ ] The download page explains: AVEN Local runs on the user's PC with no key (the first model download is 1.3 GB or more), how to handle the "Windows protected your PC" prompt if the build is unsigned, that data is stored locally, and that there are no automatic updates

## 7. After release
- [ ] Tag the release in git (`git tag v<version>`)
- [ ] Archive the exact `requirements` versions used (`pip freeze > release-freeze.txt` from `.venv-build`)
