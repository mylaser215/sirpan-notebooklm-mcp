# Known Issues and Fragility

This document describes known limitations and potential failure points in the NotebookLM MCP. Since this project uses undocumented internal APIs, certain breakages are expected over time.

---

## 1. Build Label (`bl`) Parameter

### What it is
The `bl` (build label) parameter is a frontend version identifier required by NotebookLM's batchexecute API. It looks like:
```
boq_labs-tailwind-frontend_20260219.16_p2
```

### Current status (v0.3.11+)
**Resolved.** The `bl` value is now auto-extracted from the NotebookLM page during `nlm login` and during CSRF token refresh. It stays current automatically without manual intervention.

### Manual override
If you need to force a specific value, set the `NOTEBOOKLM_BL` environment variable:

```bash
export NOTEBOOKLM_BL="boq_labs-tailwind-frontend_YYYYMMDD.XX_pN"
```

The priority order is: env var > auto-extracted > hardcoded fallback.

---

## 2. Cookie Expiration

### What it is
Authentication uses browser cookies extracted from an active Chrome session. These cookies have a limited lifespan.

### When it breaks
Cookies typically expire after 2-4 weeks. Symptoms:
- `ValueError: Cookies have expired. Please re-authenticate...`
- API calls redirect to Google login page
- Authentication errors on previously working operations

### How to fix
Re-extract fresh cookies using one of these methods:

**Option A: nlm login CLI (recommended)**

The built-in authentication CLI automatically launches Chrome, navigates to NotebookLM, and extracts cookies:

```bash
nlm login
```

If Chrome is not running, it will be launched automatically. If you're not logged in, the CLI waits for you to complete login in the browser window. Tokens are cached to your profile directory.

**Option B: Chrome DevTools MCP**

If your AI assistant has Chrome DevTools MCP available:
1. Navigate to `notebooklm.google.com` in Chrome
2. Use Chrome DevTools MCP to extract cookies from any network request
3. Call `save_auth_tokens(cookies=<cookie_header>)`

**Option C: Manual extraction**
1. Open Chrome DevTools on `notebooklm.google.com`
2. Network tab → find any request → copy Cookie header
3. Set `NOTEBOOKLM_COOKIES` environment variable

---

## 3. Rate Limits

### What it is
The free tier of NotebookLM has usage limits enforced server-side.

### Current limits
- ~50 queries per day (approximate, not officially documented)
- Studio content generation may have separate limits

### Symptoms when exceeded
- API returns rate limit errors
- Operations start failing mid-session

### Mitigation
- Space out operations when possible
- Avoid tight polling loops
- Consider batching queries where the API supports it

---

## 4. API Instability (Undocumented Internal APIs)

### What it is
This MCP uses internal, undocumented APIs that Google can change at any time without notice.

### What can break
- RPC IDs (e.g., `wXbhsf` for list notebooks) may be renamed
- Request/response structure may change
- New required parameters may be added
- Endpoints may be deprecated or moved

### Symptoms
- Parsing errors (unexpected response shape)
- `None` results from previously working operations
- New error messages from the API

### What to do when it breaks
1. Check if the issue is widespread (Google may have deployed changes)
2. Use Chrome DevTools to capture current request/response format
3. Update the relevant RPC handling in `api_client.py`
4. Submit a PR or issue if you discover the fix

---

## 5. CSRF Token and Session ID

### What it is
The MCP auto-extracts CSRF token (`SNlM0e`) and session ID (`FdrFJe`) from the NotebookLM homepage on first use.

### When it breaks
- If the homepage structure changes, extraction may fail
- Tokens are per-session and must be refreshed if the page is not accessible

### Symptoms
- `ValueError: Could not extract CSRF token from page`
- Debug HTML saved to `~/.notebooklm-mcp-cli/debug_page.html`

### How to fix
If auto-extraction fails:
1. Manually extract tokens from Chrome DevTools Network tab
2. Pass them via `save_auth_tokens(cookies=..., request_body=..., request_url=...)`

---

## 6. Source vs Note Backend Split (resolved in v3)

### What it is
NotebookLM backend stores two distinct object kinds with separate RPCs:

- **Source** (external docs: PDF, URL, pasted text, Drive, audio, video, image)
  - Add: `izAoDd` / `ozz5Z`
  - Get summary: `tr032e` (RPC_GET_SOURCE_GUIDE)
  - Get content: `hizoJc` (RPC_GET_SOURCE)
  - Rename: `b7Wfje` (RPC_RENAME_SOURCE)
  - Delete: `tGMBJ` (RPC_DELETE_SOURCE)

- **Note** (saved AI responses, mind maps — `source_type=8` / `generated_text`)
  - Create: `CYK0Xb`
  - List + read body: `cFji9` (RPC_GET_NOTES — body comes inline, no per-note get RPC)
  - Update (content+title): `cYAfTb` (RPC_UPDATE_NOTE)
  - Delete: `AH0mwd` (RPC_DELETE_NOTE)

Calling a Source-only RPC against a Note ID returns generic `Failed to ...` errors.

### Symptoms (before fix)
```python
# Note ID passed to Source-only tools — all reject:
source_describe(note_id)         # "Failed to get source summary."
source_get_content(note_id)      # "Failed to get source content."
source_rename(nb, note_id, ...)  # "Failed to rename source."
source_delete(note_id, confirm=True)  # "Failed to delete source."
```

### Current status (v3 — resolved 2026-05-06)
The four affected tools (`source_delete`, `source_describe`, `source_get_content`, `source_rename`) now auto-detect the object kind and route accordingly when `notebook_id` is provided:

```python
# Pass notebook_id for Notes — auto-routes to the correct backend RPC
source_describe(note_id, notebook_id=nb)         # → list_notes content as summary
source_get_content(note_id, notebook_id=nb)      # → list_notes content + title
source_rename(nb, note_id, "New title")          # → update_note (title-only) cYAfTb
source_delete(note_id, notebook_id=nb, confirm=True)  # → delete_note AH0mwd

# Or use the explicit Note tool:
note(action="update", note_id=..., title="...", notebook_id=nb)
note(action="delete", note_id=..., notebook_id=nb, confirm=True)
```

### Backward compatibility
All new arguments are optional. Calls without `notebook_id` keep the original Source-only behavior; the error message now includes a hint to pass `notebook_id` when the target is a Note.

### Implementation
- Helper: `core/sources._is_note_type(source_type)` — single source of truth for Note vs Source dispatch (extensible to future Note subtypes)
- Helper: `services/sources._resolve_source_type(client, notebook_id, source_id)` — sources→notes fallback lookup, shared across the four tools
- Note `describe` and `get_content` reuse `list_notes` (cFji9), since NotebookLM has no per-Note summary or get-by-id RPC
- Note `rename` delegates to `update_note` with title-only change, preserving body content

History: v1 (login auth, 2026-04) → v2 (`source_delete`, 2026-05-06) → v3 (`source_describe`/`source_get_content`/`source_rename`, 2026-05-06). 80 unit tests cover routing + fallback. End-to-end verified against a temporary notebook (6/6 scenarios: 3 tools × {regular source, generated_text note}).

---

## 7. Chrome Cookies Path Migration (Chrome 96+, resolved 2026-05-11)

### What it is
`utils/cdp.has_chrome_profile()` checked only the legacy `Default/Cookies` location. Chrome 96+ (Dec 2021) moved cookies to `Default/Network/Cookies` to bundle them with network-state data.

### When it broke
Any user whose Chrome had migrated to the new layout. `has_chrome_profile()` returned `False` even when a valid login profile existed → `run_headless_auth()` short-circuited to `None` at line 1118 → `refresh_auth` silently fell back to disk reload of stale cookies, defeating the session-29 RTS expiry fix (`3c48a50`). User-visible symptom: repeated `Authentication expired` responses despite a working `nlm login`.

### How it was fixed
`has_chrome_profile()` now checks both `Default/Network/Cookies` (preferred) and `Default/Cookies` (legacy). When neither exists but `Default/` is present, a `WARNING` is logged so a future Chrome path move is detected immediately instead of failing silently.

### Future-proof note
If Chrome relocates cookies again, the warning surfaces on first headless attempt. Other Chrome assets verified safe in 2026-05-11 audit: `Local State` (User Data root, unchanged), `Login Data` (legacy location retained). Re-audit when Chrome major version jumps cross 120+.

---

## Reporting Issues

When reporting issues, include:
1. The specific tool/operation that failed
2. The error message (redact any sensitive info)
3. Whether the operation worked before
4. The current date (to correlate with potential Google deployments)

