# Upload Assistant — WebUI Guide

The Upload Assistant WebUI provides a browser-based upload workspace, configuration editor, live execution monitor, and local administration tools. It uses the same Upload Assistant configuration and upload engine as the CLI.

For a minimal first run, see the [WebUI Quick Start](web-ui-basic.md). Docker and Unraid users should also read [Docker WebUI setup](docker-gui.md).

## Contents

- [Starting the WebUI](#starting-the-webui)
- [Account setup and sign-in](#account-setup-and-sign-in)
- [Interface overview](#interface-overview)
- [Upload workspace](#upload-workspace)
- [Monitoring and reviewing a run](#monitoring-and-reviewing-a-run)
- [Configuration workspace](#configuration-workspace)
- [Security and administration](#security-and-administration)
- [Appearance, Help, and Changelog](#appearance-help-and-changelog)
- [Mobile layout](#mobile-layout)
- [Troubleshooting](#troubleshooting)

## Starting the WebUI

Start Upload Assistant with one or more directories followed by `--webui`:

```bash
python upload.py "/path/to/media" --webui 127.0.0.1:5000
```

Open <http://127.0.0.1:5000> in a browser. The address defaults to `127.0.0.1:5000`; include `HOST:PORT` only when overriding it.

### Browse roots

Browse roots define the parts of the filesystem visible in the File Browser. They do not grant access to unrelated directories.

There are two ways to configure them:

- **Command-line paths:** Paths supplied before `--webui` become browse roots when `UA_BROWSE_ROOTS` is unset.
- **`UA_BROWSE_ROOTS`:** A comma-separated list of directories. This takes precedence over command-line paths.

Example:

```bash
UA_BROWSE_ROOTS=/media/movies,/media/tv python upload.py --webui 127.0.0.1:5000
```

On Windows PowerShell:

```powershell
$env:UA_BROWSE_ROOTS = "D:\Movies,E:\TV Shows"
python upload.py --webui 127.0.0.1:5000
```

Docker deployments normally start the WebUI without positional paths, so `UA_BROWSE_ROOTS` is required. Its values must be the container-side paths from the volume mappings. See [Docker WebUI setup](docker-gui.md).

### Relevant environment variables

| Variable                | Purpose                                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `UA_BROWSE_ROOTS`       | Comma-separated directories exposed by the File Browser.                                                               |
| `UA_WEBUI_CORS_ORIGINS` | Comma-separated origins allowed to call `/api/*` from a different origin. It is not needed for normal same-origin use. |
| `SESSION_SECRET`        | Stable session/encryption secret of at least 32 bytes.                                                                 |
| `SESSION_SECRET_FILE`   | Path to a readable file containing the stable session secret.                                                          |

Provide either `SESSION_SECRET` or `SESSION_SECRET_FILE`, not both. If neither is set, the application creates and persists a secret in its configuration directory. Container deployments must persist that directory or secret across recreations.

## Account setup and sign-in

The WebUI supports one local account.

On the first visit:

1. Enter a username and strong password.
2. Choose **Create account**.
3. Sign in with the new credentials if prompted.

The normal sign-in page provides:

- **Remember me** for a longer-lived browser session;
- a **2FA code** field when two-factor authentication is enabled;
- **recovery login** for a saved one-time recovery code; and
- password-reset guidance under **Forgot password?**.

The sign-in and recovery pages use the color theme, light/dark mode, and corner style saved by the browser.

## Interface overview

The desktop interface has three main areas:

1. **Application rail:** switches between Upload and Configuration and opens Changelog, Help, Appearance, or Log out.
2. **Workspace navigation:** File Browser on the Upload page or the settings navigation on the Configuration page.
3. **Main workspace:** upload controls, execution output, configuration fields, or administration tools.

The Arguments or live media sidebar occupies the right side of the Upload workspace. On desktop, the File Browser and right sidebar can be widened but cannot be resized below their designed minimum widths.

## Upload workspace

### Select files and folders

The File Browser lists only content inside the configured browse roots. Use it to:

- search the currently available files and folders;
- sort by name, date, size, or a custom order;
- select or deselect individual entries; and
- select all currently listed entries.

Normal browsing shows non-hidden files and folders inside the permitted roots so that video, disc, book, game, ISO, and other supported upload types remain available. The separate description-file picker is limited to `.txt`, `.nfo`, and `.md` files.

#### Custom root order

Choose **Custom** in **Sort by**, then choose **Reorder**. Drag root folders into position or use the movement controls. The list previews its new position while dragging. Choose **Done** when finished; the ordering controls are hidden outside reorder mode. **Reset** clears the saved custom ordering.

The custom order is stored in that browser and does not alter folders on disk.

### Build the command

The Upload workspace offers several ways to build the upload command:

- type flags directly into **Additional Arguments**;
- choose an entry in the searchable **Arguments** sidebar;
- choose trackers in **Select Trackers (`-tk`)**; or
- load a saved argument preset.

To save a preset, enter a name and choose **Save**. Saving an existing name updates it. **Delete** removes the selected preset. Presets are shared through the WebUI data directory, while the selected file-browser order is browser-local.

Argument controls update the same command field, so advanced users can still edit the resulting string directly. The [CLI arguments reference](cli-args.md) explains each available flag.

### Start the upload

After selecting content and reviewing the command:

1. Confirm the intended tracker buttons are selected.
2. Choose **Execute Upload**.
3. Follow the streamed **Execution Output**.
4. Answer prompts with the input controls shown at the bottom of the output panel.

The WebUI runs the upload controller in an isolated subprocess so that **Kill** can stop its process tree and interactive input can be forwarded to it.

## Monitoring and reviewing a run

While an upload is active, the workspace changes from setup controls to live run information.

### Execution status

- The page header shows the current state and selected path.
- **Execution Output** streams the Upload Assistant console.
- **Binary Progress** reports progress from external tools when available.
- **Now Processing** shows the current media poster, identifiers, technical details, overview, and source path when metadata is available.
- **Kill** terminates the active run.

### Generated screenshots

When screenshot capture has completed, open **Screenshots** to review frames before image hosting. Screenshots are grouped for the main title and any additional discs or playlists.

Depending on the screenshot state, you can:

- expand a frame for a larger view;
- **Replace** it with a frame captured at another point;
- add another frame to the relevant group;
- delete an eligible local or pending frame; or
- undo a pending replacement and restore the original remote frame.

The grid adapts to the available panel width, from one column in a narrow sidebar to multiple columns in a wider review panel.

### Description review

Open **Description** when a generated description is available. The review panel can show source versions, switch between edit and preview views, apply common BBCode formatting, save edits, and restore a source version.

Changes made here affect the active upload's generated description; they do not rewrite the global description configuration.

## Configuration workspace

Configuration is arranged by task rather than mirroring the raw Python dictionary. The sidebar groups settings as follows:

| Group          | Page                   | Includes                                                                                   |
| -------------- | ---------------------- | ------------------------------------------------------------------------------------------ |
| Settings       | General                | Main settings, logging, and external tool paths.                                           |
| Settings       | Torrent Clients        | qBittorrent, rTorrent, Deluge, Transmission, and related client definitions.               |
| Settings       | Metadata Services      | Metadata credentials, Arr integration, caching, and music metadata.                        |
| Settings       | Image Hosting          | Image-host priority and host credentials.                                                  |
| Settings       | Screenshot Handling    | Capture, processing, enhancements, disc menus, and contact sheets.                         |
| Settings       | Description Formatting | General descriptions, packs, headers, Blu-ray details, spectrograms, and HDR plots.        |
| Settings       | Upload Workflow        | Tracker search/import, tracker checks, torrent creation, upload, and post-upload behavior. |
| Settings       | Usenet Uploads         | Usenet-specific services and upload configuration.                                         |
| Trackers       | Default Trackers       | The trackers selected by default for uploads.                                              |
| Trackers       | Configured Trackers    | Existing tracker credentials and overrides.                                                |
| Trackers       | Available Trackers     | Templates for adding supported trackers.                                                   |
| Administration | Security               | Two-factor authentication and API tokens.                                                  |
| Administration | Access Log             | IP controls, logging level, and recent access activity.                                    |

Hover or focus an information icon beside a setting to read its description. The [configuration reference](example-config.md) remains the authoritative detailed reference for defaults and implementation notes.

The editor combines bundled defaults from `data/example_config.py` with overrides from the user-state `data/config.py`. If no usable `config.py` exists, the interface displays the example defaults and warns that they have not yet been saved. Successful configuration writes are recorded in `data/config_audit.log`; sensitive values are redacted from that audit trail.

### Personal release groups

Under **Configuration → General → Main Settings**, enter a release-group name in **Personal Release Groups** and press Space, Enter, or comma to add it. Each group appears as a compact tag; select its **×** button to remove it. Matching is case-insensitive, and a detected matching group automatically marks the upload as a personal release.

### Pending changes

Configuration edits are staged in the browser instead of being written immediately.

- The header reports the number of unsaved changes.
- Open **Pending changes** to review compact, human-readable summaries.
- **Discard** restores one setting to its last saved value.
- **Discard all changes** restores every staged value after confirmation.
- **Save Config** writes the complete staged set.

Tracker setup changes are grouped by tracker in the summary so that adding several fields does not fill the panel with every credential. Sensitive values are never printed there.

### Image-host priority

Each priority selector continues to list all configured image hosts, including hosts already selected in another position. This makes it possible to swap priorities before saving. Resolve any duplicate selections before choosing **Save Config**.

### Trackers

- Use **Default Trackers** to choose the normal starting set shown on the Upload page.
- Use **Configured Trackers** to review, rename, edit, or remove existing tracker entries.
- Use **Available Trackers** to add a supported tracker from its template.

New trackers and tracker edits remain pending until the configuration is saved.

## Security and administration

### Two-factor authentication

Open **Configuration → Security** to set up authenticator-app 2FA:

1. Start setup.
2. Scan the QR code or enter the displayed secret manually.
3. Store the recovery codes somewhere separate from the Upload Assistant host.
4. Enter a current authenticator code to enable 2FA.

Recovery codes are one-time credentials. Disabling 2FA clears its secret and recovery-code hashes.

### API tokens

API tokens allow supported programmatic requests to use `Authorization: Bearer <token>`.

1. Enter a descriptive label and generate a token.
2. Copy the token while it is visible.
3. Choose **Store** to persist it.
4. Revoke tokens that are no longer needed.

Token-management and other sensitive administration endpoints still require an authenticated browser session with CSRF protection. Bearer tokens are accepted only by the supported subset of API endpoints; see the [WebUI API reference](web-ui-api.md).

### IP controls and access logging

Open **Configuration → Access Log** to manage:

- the IP whitelist and blacklist;
- access logging level (`Access denied`, `Access`, or `Disabled`); and
- recent access-log entries.

The blacklist takes precedence over the whitelist. Repeated failed API access attempts may add the source IP to the blacklist. Review IP changes carefully so that you do not lock out the device or reverse proxy used to administer the WebUI.

The local account, encrypted credentials, token metadata, 2FA state, IP controls, and access-log level are stored in `webui_auth.json`. Access events are written to `access_log.log` in the same application configuration directory. The generated `session_secret` is also stored there unless `SESSION_SECRET` or `SESSION_SECRET_FILE` overrides it.

## Appearance, Help, and Changelog

### Appearance

Appearance is shared by the Upload, Configuration, sign-in, and recovery interfaces. Choose:

- a color theme: Amethyst, Charcoal, Evergreen, Graphite, Midnight, or Obsidian;
- Rounded or Square corners; and
- Light or Dark mode.

These preferences are stored in the browser, so another browser or device can use different choices.

### Help & Resources

Help links to the documentation home, this WebUI guide, configuration and CLI references, description-builder guidance, and platform installation guides. Links open the current `development` documentation on GitHub in a new tab.

### Updates and changelog

When update notifications are enabled, the WebUI checks GitHub when the page loads or becomes visible and polls again every 30 minutes while it remains open. A successful result is reused for `update_notification_cache_hours` (four hours by default), so polling does not normally make a new GitHub request every time. An available update is shown on the application rail.

Open **Help & Resources** and choose **Check now** to bypass the normal cache. **View changelog** opens release history with filters for WebUI, Core, Trackers, and Configuration changes. A separate, collapsed **Development — Unreleased** panel lists commits merged into the development branch since the latest official release; its commits use the same area filters and change-type badges as released entries, but may change before publication. The current installed release and latest release have separate badges. If GitHub cannot be reached, cached or bundled release information is used when available.

The changelog is derived from the normal Upload Assistant releases; WebUI changes are categorized within those releases rather than using a separate version number.

## Mobile layout

The same functions are reorganized for smaller screens:

- Upload and Configuration are available in the compact workspace navigation.
- Files, Upload, and Arguments move to bottom navigation.
- During a run, those destinations adapt to Progress, media information, Screenshots, and Description when available.
- Help, Changelog, and Appearance open as viewport-sized dialogs with their own scrolling content.
- Configuration uses a compact settings navigator while preserving pending-change and save controls.

Phones retain the tabbed Upload workspace and compact Configuration navigator in landscape, using the additional width for the active panel. On supported mobile browsers, requesting the desktop site opts back into the desktop workspace.

Resizable desktop sidebar widths do not change the mobile layout.

## Troubleshooting

### The File Browser is empty

- For a source install, pass at least one path before `--webui` or set `UA_BROWSE_ROOTS`.
- For Docker, set `UA_BROWSE_ROOTS` to the container-side paths and confirm matching volumes are mounted.
- Confirm the runtime user can read the selected directories.

### `CSRF/Origin validation failed`

- Refresh the page and sign in again if requested.
- Use one consistent hostname or IP address; changing between them creates a different browser origin.
- If a reverse proxy is used, preserve the original host and scheme so the request `Origin` matches the public WebUI address.
- Clear the site's stored data and sign in again if an old tab retained stale session data.

### Update checking does not finish or reports an error

A manual GitHub check can take up to about 15 seconds. Confirm the host can reach GitHub and that a proxy or firewall is not blocking the request. Cached release history remains available after a successful earlier check.

### Cloudflare proxy caching

Cloudflare is not required and normally needs no WebUI-specific setting. If a proxied WebUI loads stale assets or behaves differently from a direct connection, the original WebUI guidance recommended disabling Cloudflare **Real User Measurements** and purging its cache. Treat those as troubleshooting steps rather than mandatory setup:

- first bypass or clear caching for the WebUI's HTML and static assets;
- disable Real User Measurements if injected monitoring still interferes; and
- confirm the proxy preserves the public host and scheme through `Host`, `X-Forwarded-Proto`, or Cloudflare's `Cf-Visitor` header.

Prefer a targeted cache purge when possible; **Purge Everything** is the broad fallback described by the original guidance.

### The interface still shows an older layout

Perform a hard refresh or clear the site's cached files after updating Upload Assistant. This is especially relevant when testing a branch that changes JavaScript or CSS assets.

### Account or 2FA recovery

Use a saved recovery code when possible. If the account cannot be recovered, stop the WebUI and remove `webui_auth.json` from the application configuration directory to return to first-run account setup.

This reset removes the local account, API tokens, 2FA secret, and remaining recovery codes. Keep the persisted session secret intact unless you intentionally need to invalidate encrypted state.

Common authentication-state locations are:

- Windows: `%APPDATA%\upload-assistant\`
- Linux or macOS with XDG configured: `$XDG_CONFIG_HOME/upload-assistant/`
- Linux or macOS default: `~/.config/upload-assistant/`
- legacy source setups: the repository `data/` directory

## Related documentation

- [WebUI Quick Start](web-ui-basic.md)
- [Docker WebUI / Unraid setup](docker-gui.md)
- [Configuration reference](example-config.md)
- [CLI arguments](cli-args.md)
- [Description builder](description-builder.md)
- [WebUI API reference](web-ui-api.md)
