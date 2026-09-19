# Mindex Electron Packaging Plan

Mindex keeps the existing web UI as the renderer. Electron is only responsible for the desktop shell: stable Chromium runtime, native presenter windows, app updates, and later native helpers.

## Goals

- Same UI code as the web version.
- Windows-friendly installed app for non-technical users.
- Presenter output opens as a native fullscreen window, not a browser popup.
- Supabase remains the source of truth.
- Local storage is cache only and can be discarded when cache versions change.
- Updates should feel simple: notify, download, restart.

## Architecture

```text
Electron main process
├─ loads static app over mindex://app/index.html
├─ creates controller BrowserWindow
├─ creates fullscreen presenter BrowserWindow
├─ owns auto-update lifecycle
└─ exposes a small preload bridge

Renderer
├─ existing index.html/app.js UI
├─ Supabase client with anon key only
├─ BroadcastChannel presenter state
└─ optional Electron bridge when installed app is running
```

## Update Strategy

Mindex uses GitHub Releases (`gdwrchurch/Mindex`) through `electron-updater`.
Packaged apps check on startup, show an update prompt, download only after the
operator confirms, and install on restart. Set `MINDEX_DISABLE_UPDATES=1` only
when an installed test build must stay offline. Dev builds never check.

Every release must be built with `pnpm electron:release`. It stops before
publishing unless all of these are configured:

1. `GH_TOKEN` for the GitHub Release upload.
2. `CSC_LINK` and `CSC_KEY_PASSWORD` for the Developer ID Application certificate.
3. Apple notarization credentials: API key (`APPLE_API_KEY`, `APPLE_API_KEY_ID`,
   `APPLE_API_ISSUER`), Apple ID/app-specific password, or a keychain profile.

The macOS artifact must be Developer ID signed and notarized. A local
`electron:pack` build is for testing only and must not be distributed. The local
pack script clears the quarantine attribute from `dist/mac-arm64/Mindex.app`
after building, which reduces Gatekeeper trash/block prompts on the developer
machine. It is not a substitute for signing and notarization; shared or
downloaded builds still need `pnpm electron:release`.

Use `pnpm electron:pack:raw` only when the unsigned app bundle needs to be
inspected exactly as electron-builder produced it.

## Release Versioning

- Increase the semantic version in `package.json` before every public desktop
  release. An installed app only accepts a strictly newer version.
- Build and publish from the reviewed commit, then tag that same commit as
  `v<version>` in GitHub.
- The GitHub Release must include the installer/archive and electron-builder's
  update metadata. Do not hand-upload only a DMG.

## Data And Schema

Supabase is the primary database. Electron should not add a competing local database.

Local data is limited to:

- Supabase session/cache managed by the client.
- Last opened screen state.
- Media/cache files if needed later.

Schema changes should be backward-compatible first. Old cache can be invalidated by a cache version instead of migrated.

Do not embed service role keys or private Supabase secrets in the desktop app.
