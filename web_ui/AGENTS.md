# WEB UI KNOWLEDGE BASE

## OVERVIEW

`web_ui` is a Flask/Waitress backend coupled to template-loaded React scripts. It owns local-user auth, encrypted persisted credentials, browse-root confinement, configuration editing, execution control, and progress streaming.

## STRUCTURE

```text
web_ui/
├── server.py              # Flask app, middleware, pages, APIs, execution workers
├── auth.py                # Session secret, Argon2 user, AES-GCM protected fields
├── access_log.py          # Denied/access event logging with secret redaction
├── templates/             # React CDN shells plus login/recovery forms
└── static/
    ├── js/app.js          # Browse, arguments, queue, execution, screenshots
    ├── js/config_app.js   # Config editor and security administration
    ├── js/shared_utils.js # Theme/storage, CSRF fetch, HTML sanitization
    └── css/theme.css      # Shared visual tokens and components
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Startup boundary | `../upload.py` | `--webui` sets browse roots and starts Waitress; server has no `__main__` |
| Request security | `server.py` | IP controls -> auth -> same-origin/CSRF -> route handler |
| Browse/path safety | `server.py` | `_sanitize_relpath`, `_get_browse_roots`, `_assert_safe_resolved_path` |
| Secrets and users | `auth.py` | Secret resolution, password/TOTP/recovery/API-token storage |
| Config mutations | `server.py` | Restricts config files to repository `data/*.py`; `/api/config_update` writes audit records |
| Main browser flow | `templates/index.html`, `static/js/app.js` | SSE/output, browse, arguments, queue, screenshots |
| Security/config UI | `templates/config.html`, `static/js/config_app.js` | Config, 2FA, tokens, access logs, IP controls |
| Shared browser API | `static/js/shared_utils.js` | CSRF-aware same-origin fetch and sanitizer |

## CONVENTIONS

- `upload.py` is the server launcher. WebUI execution later invokes `upload.main()` in-process or starts `upload.py` as a subprocess.
- Configured browse roots come from `UA_BROWSE_ROOTS` or runtime setup. For `webui_queue_*.txt`, `_resolve_user_path` narrowly adds repository `tmp/` before the empty-root check. Resolve real paths and require exact-root/descendant membership before reading or writing.
- API auth supports persisted-user session, Basic auth, or bearer API token as defined by middleware; keep IP access control ahead of authentication.
- Session secrets must be at least 32 bytes and stable. Never overwrite an unreadable existing secret: encrypted WebUI credentials would become unrecoverable.
- State-changing session requests use same-origin and CSRF protections. Route additions should follow neighboring decorators/helpers and response shapes.
- The frontend has no bundler: templates load CDN React/Babel/Tailwind/DOMPurify and then globals. Load `shared_utils.js` before either application script.
- Send API calls through `uaApiFetch`/the existing CSRF wrapper. Sanitize rich or streamed HTML before `innerHTML`; use `textContent` for ordinary text.
- `app.js` and `config_app.js` are paired with backend endpoint schemas. Change request/response fields on both surfaces and update API docs where public.
- Frontend tooling runs from `web_ui/static/js`: `npm run lint:react` and `npm run format:check`. There is no browser test harness.

## ANTI-PATTERNS

- Do not default an empty browse-root set to repository root or filesystem root. Outside the queue-file exception, empty means browsing is disabled; `tmp/` is mutable runtime state, not source.
- Do not accept arbitrary config paths or execute config Python. The editor confines files to `data` and parses the `config` literal with AST rules.
- Do not bypass auth/CSRF helpers for a new JSON endpoint or mark a write endpoint as health/public traffic.
- Do not render SSE, tracker, provider, or user-controlled HTML without the shared sanitizer and dangerous-scheme filtering.
- Do not change persisted auth/session formats without preserving permissions, encryption-key derivation, and existing-user readability.
- Do not introduce module/bundler-only JavaScript syntax unless templates and deployment tooling are changed together.
