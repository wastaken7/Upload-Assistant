# Upload Assistant — WebUI Quick Start

This page covers the shortest path from starting the WebUI to running an upload. For the complete workspace, configuration, security, and troubleshooting guide, see the [full WebUI guide](web-ui.md).

## 1. Start the WebUI

Pass one or more directories to browse, followed by `--webui`:

```bash
python upload.py "/path/to/media" --webui 127.0.0.1:5000
```

Then open <http://127.0.0.1:5000>.

`127.0.0.1:5000` is the default address. Bind to another interface only when other devices need to connect and the network is trusted or protected by an authenticated reverse proxy.

### Browse roots

The File Browser only exposes configured browse roots. They can be supplied as:

- positional paths before `--webui`; or
- a comma-separated `UA_BROWSE_ROOTS` environment variable, which takes precedence.

`UA_BROWSE_ROOTS` is required for the normal Docker setup because its command starts the WebUI without positional paths. Use container-side paths, not host-side paths. See [Docker WebUI setup](docker-gui.md).

## 2. Create the local account

The first visit opens account setup. Choose the username and a strong password for the single local WebUI account. Later visits open the sign-in page.

The account can optionally use Remember me, authenticator-app two-factor authentication (2FA), and one-time recovery codes.

## 3. Configure Upload Assistant

Open **Configuration** and work through the relevant sections. At minimum, configure the metadata services, clients, image hosts, and trackers required by your workflow.

Edits are staged in **Pending changes**. Review them, then choose **Save Config**. Closing the page or using a discard action does not save those edits.

## 4. Run an upload

1. Return to **Upload** and select a file or folder in **File Browser**.
2. Add optional CLI flags through **Arguments**, the command field, or a saved argument preset.
3. Select the trackers for this run.
4. Choose **Execute Upload**.
5. Follow the live output and answer any interactive prompt at the bottom of the output panel.

During a run, the workspace also exposes binary progress and current media information. When available, **Screenshots** and **Description** let you review generated assets before the upload continues. **Kill** stops the active run.

## 5. Secure remote access

- Prefer a localhost binding when the WebUI is only used on the same machine.
- Restrict `UA_BROWSE_ROOTS` to the directories the application genuinely needs.
- Use a stable `SESSION_SECRET` or `SESSION_SECRET_FILE`, especially in containers.
- Put internet-facing access behind an authenticated HTTPS reverse proxy and appropriate firewall rules.
- Run Upload Assistant as an unprivileged user.

See [Security and administration](web-ui.md#security-and-administration) for 2FA, API tokens, IP controls, and access logging.

## Related documentation

- [Full WebUI guide](web-ui.md)
- [Docker WebUI / Unraid setup](docker-gui.md)
- [Configuration reference](example-config.md)
- [CLI arguments](cli-args.md)
- [WebUI API reference](web-ui-api.md)
