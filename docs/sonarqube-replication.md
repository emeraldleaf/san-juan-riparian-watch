# SonarQube Local Setup Guide

This guide explains how to add local static code analysis (SonarQube) to any project.
It uses a **Docker-based server** and supports **multi-language scanning** (Python, TypeScript, C#, etc.).

---

## 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- (Optional) `.NET 8.0 SDK` if scanning C# code.

---

## 2. Setup

Copy these two files to the root of your project.

### File 1: `docker-compose.sonar.yml`
*Defines the SonarQube server and its database.*

```yaml
services:
  sonarqube:
    image: sonarqube:community
    container_name: local-sonarqube
    ports:
      - "9000:9000"
    environment:
      # Disable strict bootstrap checks for local dev
      SONAR_ES_BOOTSTRAP_CHECKS_DISABLE: "true"
      SONAR_JDBC_URL: jdbc:postgresql://sonarqube-db:5432/sonarqube
      SONAR_JDBC_USERNAME: sonarqube
      SONAR_JDBC_PASSWORD: sonarqube
    volumes:
      - sonarqube-data:/opt/sonarqube/data
    depends_on:
      - sonarqube-db
    restart: unless-stopped

  sonarqube-db:
    image: postgres:16-alpine
    container_name: local-sonarqube-db
    environment:
      POSTGRES_USER: sonarqube
      POSTGRES_PASSWORD: sonarqube
      POSTGRES_DB: sonarqube
    volumes:
      - sonarqube-pgdata:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  sonarqube-data:
  sonarqube-pgdata:
```

### File 2: `sonar-project.properties`
*Configures the scanner for non-.NET languages (JS, TS, Python, CSS, etc).*

```properties
# Project Identification
sonar.projectKey=my-new-project
sonar.projectName=My New Project
sonar.projectVersion=1.0

# Source Directories (comma-separated)
# Example: "src" or "frontend,backend"
sonar.sources=src

# Exclusions (Glob patterns)
sonar.exclusions=**/node_modules/**,**/dist/**,**/bin/**,**/obj/**,**/*.test.js

# Language Specifics
sonar.python.version=3.12
sonar.sourceEncoding=UTF-8
```

---

## 3. Running the Server

Start SonarQube in the background:

```bash
docker compose -f docker-compose.sonar.yml up -d
```

> **First Run:** Wait ~1-2 minutes for the server to initialize.
> Access the dashboard at [http://localhost:9000](http://localhost:9000).
> **Login:** `admin` / `admin` (you will be prompted to change the password).

---

## 4. Running a Scan

You need a **User Token** to run scans.
1. Go to **User Icon > My Account > Security**.
2. Type a name (e.g., "local-scanner") and click **Generate**.
3. Copy the token.

### Option A: Generic Scanner (Python, JS, TS, Go, etc.)

Run the official Docker-based scanner. It will read your `sonar-project.properties`.

```bash
# Replace "YOUR_TOKEN_HERE" with the generated token
docker run --rm \
    --network host \
    -v "$PWD:/usr/src" \
    sonarsource/sonar-scanner-cli \
    -Dsonar.projectKey="my-new-project" \
    -Dsonar.token="YOUR_TOKEN_HERE"
```
*(Note: on macOS/Windows, `--network host` might not work; use `-Dsonar.host.url="http://host.docker.internal:9000"` instead).*

### Option B: .NET Scanner (C#)

C# projects require the "Begin -> Build -> End" workflow.

1. **Install Global Tool** (once):
   ```bash
   dotnet tool install --global dotnet-sonarscanner
   ```

2. **Run Analysis**:
   ```bash
   # 1. Begin
   dotnet sonarscanner begin \
     /k:"my-new-project" \
     /d:sonar.host.url="http://localhost:9000" \
     /d:sonar.token="YOUR_TOKEN_HERE"

   # 2. Build (must happen between begin/end)
   dotnet build --no-incremental

   # 3. End (This submits the results)
   dotnet sonarscanner end /d:sonar.token="YOUR_TOKEN_HERE"
   ```

---

## 5. View Results

Refresh [http://localhost:9000](http://localhost:9000) to see your code quality report, bugs, vulnerabilities, and code smells.
