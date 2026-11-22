# CiviConnect

CiviConnect is a Greek-language civic information site for Athens. Residents can search for municipal representatives, ask questions about council activity, and follow source links. The homepage also shows videos from a configured YouTube channel and a municipal election countdown. Representatives can claim their public profile and add a biography, photo, and policy statements after an administrator verifies their identity.

The app runs locally on Windows with a FastAPI backend and a browser frontend built with HTML, CSS, and JavaScript. It uses local JSON files for records and SQLite for the search index.

## Run on Windows

Make Python 3.11 or newer available through the Windows Python launcher or on `PATH`. From the project folder, run:

```powershell
.\start.bat
```

The launcher creates `venv` and `config.json` as needed, installs dependencies, and refreshes the Athens directory from OpenCouncil. If the directory refresh fails, it starts with the saved roster. Once the server is ready it opens [the homepage](http://127.0.0.1:8000/) in the default browser and prints startup messages and requests in the same Command Prompt.

Press **Ctrl+C** or close that Command Prompt to stop the server. Restart it after editing configuration or Python code. The default listener is `127.0.0.1:8000`. Set `UVICORN_PORT` before launching to choose a different port.

| Command | Use |
| --- | --- |
| `.\start.bat status` | Identify the process listening on the configured port. |
| `.\start.bat stop` | Stop a listener verified as this workspace's CiviConnect server. Useful for an earlier instance with a missing console. |
| `.\start.bat reset` | Clear current records, profile photos, and search data, then refresh the directory and start the server. Use only when you intend to reset active data. |

## Configuration

[config.example.json](config.example.json) lists the supported settings. Keep the working `config.json` private. A nonempty environment variable with the uppercase form of a setting name takes precedence over its value in the file.

| Setting | Purpose |
| --- | --- |
| `municipality_name` | Municipality label shown on the homepage. The council data importer is scoped to Athens. |
| `election_datetime_iso` | Optional election countdown target in ISO 8601 format, including a timezone offset. |
| `youtube_channel_id` | Optional YouTube channel ID, such as a `UC…` channel identifier. The carousel shows public uploads and Shorts, skipping scheduled streams, active streams, and livestream replays. |
| `gemini_api_key` | Optional Gemini API key for conversational answers based on retrieved evidence. |
| `admin_username` | Local administrator username. The example uses `admin`. |
| `admin_password` | Administrator password. The app generates one in `config.json` if neither the file nor the environment supplies one. |
| `session_secret_key` | Key used to sign session cookies. The app generates one in `config.json` if needed. |

The default countdown is to the start of **26 November 2028** in Athens. This is the expected date for the current municipal cycle under the last-Sunday-of-November rule. The countdown uses a configured target when supplied. [Greek Ministry of the Interior, Article 35](https://ta.ypes.gov.gr/vivlio-a/meros-b/kefalaio-b/arthro-35)

## Refresh Athens data and search

The normal startup refreshes the representative directory and municipal groups. The meeting archive and search index have their own commands:

```powershell
.\venv\Scripts\python.exe .\py\manage.py sync-athens
.\venv\Scripts\python.exe .\py\manage.py sync-athens-evidence
.\venv\Scripts\python.exe .\py\manage.py build-athens-search
```

- `sync-athens` refreshes the active Athens roster from [OpenCouncil](https://opencouncil.gr/athens/people). It matches existing profiles by source ID and preserves local profile details and accounts.
- `sync-athens-evidence` downloads the last year of eligible public meetings and rebuilds the search index. It uses attributed agenda items, contribution summaries, and transcript excerpts when available.
- `build-athens-search` rebuilds the index from the saved evidence file. The first build downloads the tokenizer and quantized multilingual E5 model into `data/search_model/`. A completed index replaces the previous one after the build, allowing search to continue against the existing index during a rebuild.

### Search and news

- A recognized profile search is resolved against the public directory first. The homepage shows the matching profile and recent news, with a surname check on the displayed headlines. An ambiguous name prompts for a full name.
- Civic questions use keyword ranking and multilingual semantic retrieval over dated council evidence. Search can fall back to the saved evidence JSON while the index is unavailable. The local answer ranks people and parties by distinct meetings and includes citations.
- When configured, Gemini receives a shortlisted set of evidence and up to the first 500 characters of the question. Validated answers are cached locally. The local answer remains available if Gemini is unavailable, busy, or returns an unusable answer.
- The verification layer can use municipal decisions from Diavgeia, reporting from ERT, and Google News headlines. Its searches use public topic terms, published titles, explicit public decision identifiers, or public representative names.
- Profile pages show up to five distinct recent articles from the past 30 days. Names linked in civic answers can have up to two articles each.
- The homepage carousel supports portrait and landscape thumbnails and loops automatically. Starting a second video closes the first player.

## Profile claims and access

1. An unclaimed profile links to `/claim-profile.html`. The older `/submit.html` address redirects there with its query string.
2. The representative submits a verification email and any optional profile material. Uploaded photos support JPG, PNG, and WebP up to 8 MB. The server decodes and re-encodes accepted photos to strip metadata.
3. An administrator signs in at `/admin-login.html`, verifies the claimant through an official municipal contact, and approves or rejects the claim. Photos submitted with a claim stay private until approval.
4. Approval generates login credentials for the representative portal at `/politician-login.html`. The representative can then update their public profile.

The administrator dashboard also shows messages submitted through the footer contact form.

### Fictional demo profile

Copy [demo-profile.example.json](demo-profile.example.json) to `data/demo_profile.json` once to enable the fictional profile at `/profile.html?id=demo-fictional-profile`. Edit `data/demo_profile.json` for all subsequent changes. The open demo profile checks for saved edits every three seconds while visible. The directory reflects the changes when refreshed. For a photo, put the image file under `static/uploads/photos/` and set `photo_url` to the corresponding `/static/uploads/photos/...` URL. A link to an Instagram post can go in `socials.instagram`.

The demo is labeled as fictional and uses the regular Google News lookup by name. A fictional name can return an empty article list. OpenCouncil sync manages the imported roster independently of this file. Set `enabled` to `false` to hide the demo.

## Project layout

| Path | Contents |
| --- | --- |
| `start.bat` | Windows startup and server controls |
| `py/launch.py`, `py/app.py` | Console launcher and ASGI entry point |
| `py/manage.py` | Directory sync, evidence refresh, search rebuild, and reset commands |
| `py/civiconnect/` | API routes, storage, OpenCouncil integration, and search and verification code |
| `static/` | Public pages, CSS, JavaScript, and assets |
| `templates/` | Authenticated dashboards |
| `tests/` | Python and JavaScript regression suites |

The shared palette and responsive typography tokens live in [static/css/theme.css](static/css/theme.css). The homepage composer is the primary action on that page. Its styles are in [static/css/home.css](static/css/home.css).

### Local records

| Path | Contents |
| --- | --- |
| `data/politicians.json`, `data/opencouncil_parties.json` | Representative records, local claims and accounts, and imported groups |
| `data/contact_messages.json` | Private contact submissions |
| `data/claim_photos/`, `static/uploads/photos/` | Pending claim photos and public profile photos, respectively |
| `data/athens_1y_statements.json`, `data/athens_search.sqlite3` | Downloaded council evidence and its searchable index |
| `data/athens_entities.json` | Representative and group snapshot written by the evidence refresh |
| `data/search_model/`, `data/topic_cache.json` | Downloaded model files and cached Gemini answers |
| `data/submissions/`, `data/llm_research_feed.jsonl` | Historical records from the retired public submission workflow |

Back up `config.json`, `data/`, and `static/uploads/` before resetting or moving an installation. The reset command clears active records, claim and public photos, imported evidence and indexes, and the answer cache. It preserves configuration, the downloaded search model, and historical submissions. Journal recovery can still finish an interrupted write from the retired submission workflow.

## HTTP interface

The app serves an OpenAPI schema at `/openapi.json`. Useful routes include:

| Route | Purpose |
| --- | --- |
| `GET /api/config` | Public municipality and election settings |
| `GET /api/politicians`, `GET /api/parties` | Public roster and municipal groups |
| `GET /api/politicians/{id}` | Public profile |
| `GET /api/politicians/{id}/news?limit=5` | Recent news for one representative |
| `GET /api/video-replies` | Public YouTube uploads and Shorts |
| `POST /api/athens/answer` | Civic Q&A with source metadata |
| `POST /api/contact` | Submit a message from the contact form |
| `GET /api/health` | Build fingerprint used by the local launcher |

## Run the tests

Run the suites from the project root. The JavaScript suite requires Node.js.

```powershell
.\venv\Scripts\python.exe -m unittest
node --test tests/test_names.mjs
```

The Python suite covers civic evidence retrieval and verification. Tests requiring the Athens search index skip when the index has not been built. The JavaScript suite checks Greek name matching, ambiguous surnames, and the boundary between profile lookup and civic Q&A.
