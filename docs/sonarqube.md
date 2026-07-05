# Code Quality — SonarQube

Detail doc paired with the one-paragraph headline in CLAUDE.md "Code Quality".
SonarQube is the Tier-3 static-analysis gate in the encoding-loop enforcement
spectrum (CodeRabbit is the Tier-2 AI-review surface; see `.coderabbit.yaml`).
See CLAUDE.md.

## Overview
SonarQube provides static code analysis for Python, TypeScript, SQL, and C#. It runs as a
local Docker container with a web dashboard. The VS Code extension ("SonarQube for IDE")
provides real-time in-editor analysis via connected mode.

## Architecture
- **Server**: SonarQube Community Edition in Docker (`docker-compose.sonar.yml`)
- **Database**: Separate PostgreSQL 16 container (not embedded H2 — survives restarts)
- **Scanner**: `sonar-scanner` CLI for Python/TS/SQL; `dotnet-sonarscanner` for C#
- **IDE**: SonarQube for IDE extension in VS Code (connected mode to local server)

## Quick Commands
```bash
./dev.sh --sonar          # Start SonarQube server (first start takes ~2 min)
./dev.sh --sonar-stop     # Stop SonarQube server
./dev.sh --lint           # Scan Python + TypeScript + SQL (requires SONAR_TOKEN)
./dev.sh --lint-dotnet    # Scan C# .NET code
```

## First-Time Setup
1. Start server: `./dev.sh --sonar`
2. Wait for startup (~90 seconds), then open http://localhost:9000
3. Log in with default credentials: `admin` / `admin` (change on first login)
4. Generate a token: **Administration → Security → Users → Tokens → Generate**
5. Save token to `.env`: `SONAR_TOKEN=squ_your_token_here`
6. `dev.sh` auto-sources `.env` on every run

## Running Analysis

**Python + TypeScript + SQL** (via `sonar-scanner`):
```bash
./dev.sh --lint
# Or manually:
sonar-scanner -Dsonar.token=$SONAR_TOKEN
```
This uses `sonar-project.properties` which scans `python-etl/`, `frontend/src/`, and `sql/`.

**C# .NET** (via `dotnet-sonarscanner`):
```bash
./dev.sh --lint-dotnet
# Or manually:
dotnet sonarscanner begin /k:"riparian-poc" /d:sonar.token="$SONAR_TOKEN" /d:sonar.host.url="http://localhost:9000"
dotnet build RiparianPoc.sln
dotnet sonarscanner end /d:sonar.token="$SONAR_TOKEN"
```

## In-Editor Analysis (Copilot / AI Agent)
The "SonarQube for IDE" VS Code extension exposes analysis tools that Copilot can invoke
directly. Use these instead of Codacy for code quality checks:

```
# Analyze a single file (results appear in VS Code Problems panel):
sonarqube_analyze_file  → pass the absolute file path

# Check security hotspots and taint vulnerabilities:
sonarqube_list_potential_security_issues  → pass the absolute file path

# Exclude files/folders from analysis:
sonarqube_exclude_from_analysis  → pass a glob pattern (e.g. **/test/**)
```

When asking Copilot to check code quality, say **"run SonarQube"** or
**"analyze with SonarQube"** — do NOT use Codacy.

## Dashboard
- URL: http://localhost:9000
- Project key: `riparian-poc`
- View issues, code smells, security hotspots, and coverage per file

## VS Code Integration (Connected Mode)
The SonarQube for IDE extension is configured in `.vscode/settings.json`:
```json
{
  "sonarlint.connectedMode.project": {
    "connectionId": "riparian-vs-extension",
    "projectKey": "riparian-poc"
  }
}
```
- The connection token is stored in VS Code's secure storage (macOS Keychain)
- To set up: **Cmd+Shift+P → SonarQube: Connect to SonarQube Server** → enter `http://localhost:9000` and your token
- Once connected, issues appear inline in the editor as you type (no need to run `--lint`)
- The extension syncs rules and quality profiles from the server

## What Gets Scanned
| Language   | Source Path           | Scanner                |
|------------|-----------------------|------------------------|
| Python     | `python-etl/`        | `sonar-scanner`        |
| TypeScript | `frontend/src/`      | `sonar-scanner`        |
| SQL        | `sql/`               | `sonar-scanner`        |
| C#         | `RiparianPoc.Api/`   | `dotnet-sonarscanner`  |

## Exclusions (in `sonar-project.properties`)
`node_modules/`, `dist/`, `bin/`, `obj/`, `__pycache__/`, minified files.

## Token Storage
- `.env` file (gitignored): `SONAR_TOKEN=squ_...`
- `dev.sh` auto-sources `.env` on startup
- VS Code extension token: stored in macOS Keychain (not in any file)
- Token types: `squ_` = User Token (read+write, needed for the VS Code extension /
  connected mode); `sqp_` = Project Analysis Token (write-only, for CI scans)

## Per-File Analysis (via Copilot / SonarQube for IDE)
Two capabilities Copilot can invoke without the server running or a `sonar-scanner` CLI:

**Analyze a single file** — runs SonarQube rules locally; issues appear in the Problems
panel. Useful after editing a file to verify no new code smells or bugs:
```
"Run SonarQube analysis on python-etl/raster_processor.py"
"Analyze this file with SonarQube"
```

**List security hotspots and taint vulnerabilities** — scans for SQL injection, SSRF, path
traversal, etc. plus taint flows:
```
"Check this file for security issues with SonarQube"
"Run SonarQube taint analysis on GeoDataServices.cs"
```
Taint Vulnerabilities require connected mode with a SonarQube Server/Cloud analysis to
detect cross-file flows.

**Typical workflow after code changes:** edit → ask Copilot to run SonarQube analysis on
each changed file → ask Copilot to check changed files for security issues → fix → run
`./dev.sh --lint` for the full project scan (catches cross-file issues).

## Replicating SonarQube for Other Projects

Self-contained and portable. To add the same setup to a different project:

**Prerequisites (host machine):** Docker Desktop (or Docker Engine + Compose V2); .NET SDK
8+ (only for scanning C#); VS Code with **SonarQube for IDE** (`SonarSource.sonarlint-vscode`).

**Step 1 — Copy the infrastructure files:**
```
cp docker-compose.sonar.yml  /path/to/new-project/
cp sonar-project.properties  /path/to/new-project/
```

**Step 2 — Edit `sonar-project.properties`:**
```properties
sonar.projectKey=my-new-project        # unique key (no spaces)
sonar.projectName=My New Project        # display name in dashboard
sonar.sources=src,lib                   # comma-separated source dirs
sonar.exclusions=**/node_modules/**,**/dist/**,**/__pycache__/**
sonar.python.version=3.12               # adjust to your Python version
sonar.sourceEncoding=UTF-8
```

**Step 3 — Start the server:**
```bash
docker compose -f docker-compose.sonar.yml up -d
# Wait ~90 seconds for first-time initialization
```

**Step 4 — First-time login and token:** open http://localhost:9000 → log in `admin`/`admin`
(change password) → **My Account → Security → Generate Token** (User Token) → save to `.env`
(`echo 'SONAR_TOKEN=squ_your_token' >> .env`; add `.env` to `.gitignore`).

**Step 5 — Run analysis:**
```bash
export SONAR_TOKEN=$(grep SONAR_TOKEN .env | cut -d= -f2)

# Python / TypeScript / SQL (via Docker scanner):
docker run --rm -v "$PWD:/usr/src" \
  sonarsource/sonar-scanner-cli:latest \
  -Dsonar.host.url="http://host.docker.internal:9000" \
  -Dsonar.token="$SONAR_TOKEN"

# C# .NET (via dotnet tool on host):
dotnet tool install --global dotnet-sonarscanner   # first time only
dotnet sonarscanner begin /k:"my-new-project" \
  /d:sonar.host.url="http://localhost:9000" \
  /d:sonar.token="$SONAR_TOKEN"
dotnet build MySolution.sln --no-incremental
dotnet sonarscanner end /d:sonar.token="$SONAR_TOKEN"
```

**Step 6 — VS Code connected mode (optional):** install `SonarSource.sonarlint-vscode` →
**Cmd+Shift+P → SonarQube: Connect to SonarQube Server** → enter `http://localhost:9000` +
token → add the `sonarlint.connectedMode.project` block (above) to `.vscode/settings.json`.

**Troubleshooting:**
| Problem | Fix |
|---------|-----|
| Port 9000 already in use | Change the port mapping in `docker-compose.sonar.yml`: `"9001:9000"` |
| Elasticsearch crash on Linux | `sudo sysctl -w vm.max_map_count=262144` (not needed on macOS) |
| Scanner can't reach server (macOS) | Use `host.docker.internal:9000` (not `localhost`) inside Docker |
| Scanner can't reach server (Linux) | Add `--network host` to the `docker run` command |
| First login redirects in a loop | Clear cookies for localhost:9000, or use incognito |
| `dotnet-sonarscanner` conflicts with `sonar-project.properties` | Temporarily rename/move it during .NET scans (see `dev.sh`) |
| Token expired or revoked | Generate a new token in the SonarQube UI and update `.env` |
| SonarQube 26+ API auth | Uses `issueStatuses` param (not `statuses`) and Bearer auth (not Basic) |

**What you get:** dashboard at http://localhost:9000 with per-file issues, security
hotspots, duplication, complexity; data survives restarts (Docker named volumes);
`docker compose -f docker-compose.sonar.yml down -v` to fully reset; VS Code inline
highlighting in connected mode.
