# DKAI - AI Development Container

For Chinese documentation, see `README.cn.md`.

A Debian 13-based Docker container with ttyd web terminal access, designed for continuous agent usage from remote devices.

## Quick Start

### 1. Build the image

```bash
make build
# or
docker build -t dkai .
```

### 2. Create profile config

Unified config directory: `~/.config/dkai`

Each profile uses two files:
- `~/.config/dkai/<profile>.env`: env-file passed to the container
- `~/.config/dkai/<profile>.root`: symlink to the host directory mounted into the container

Example (profile name: `ai`):

```bash
mkdir -p ~/.config/dkai

cat > ~/.config/dkai/ai.env <<'ENV'
PASSWORD=your-secure-password
LANG=en_US.UTF-8

# Optional API keys
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ENV

ln -s /path/to/your/workspace ~/.config/dkai/ai.root
```

### 3. Start container

```bash
./dkai start ai
```

### 4. Access

Open: `http://localhost:<host-port>` (default `8484`)
- Username: `shell`
- Password: `PASSWORD` from the selected profile `.env`

## Important Notes

### Path masking strategy

- This repo does not store your real host paths.
- Real paths are injected through `~/.config/dkai/<profile>.root`.
- Secrets and runtime settings are injected through `~/.config/dkai/<profile>.env`.

### Privilege model and risks (important)

- Inside the container, user `shell` can elevate to root via `sudo` by design, so agents can install/adjust components.
- You accept the risk of environment corruption, operator mistakes, or malicious commands inside the container.
- Risk is usually concentrated in mounted host directories and their contents.

### Docker isolation boundary (important)

- Docker provides isolation, not an absolute security boundary.
- Do not treat the container as a strong sandbox; kernel vulnerabilities, misconfiguration, and high-privilege runtime options can expand blast radius.
- If exposed to the public internet, add reverse proxy, TLS, access control, and least-privilege mounts.

## Components

Check `packages.txt` and `Dockerfile` for installed components.

## Common Commands

```bash
# Start a profile
./dkai start ai

# Stop a profile
./dkai stop ai

# Follow logs
docker logs -f dkai-ai

# Enter container
docker exec -it dkai-ai bash
```

## Architecture

- Base image: `debian:13-slim`
- ttyd: `1.7.7` (prebuilt binary downloaded from GitHub)
- Runtime user: `shell` (`sudo` passwordless)
- Entrypoint: `/usr/bin/run_agent`

## Advanced Configuration

### In-container environment

`run_agent` tries to load `.env` from the container working directory if present.

### Custom startup arguments

Pass extra args through profile `.env`:

```bash
TMUX_ARGS=-f /home/shell/.tmux.conf
TTYD_ARGS=--client-option fontSize=16
```

Note: for `docker run --env-file`, prefer raw `KEY=value` format. Do not wrap values in extra quotes.

### tunable `dkai` script variables

- `DKAI_HOST_PORT`: host-side mapped port (default `8484`)
- `DKAI_IMAGE`: image name (default `dkai`)
- `DKAI_NAME_PREFIX`: container name prefix (default `dkai`)
- `DKAI_CONFIG_HOME`: profile config dir (default `~/.config/dkai`)

Notes:
- Container port is fixed at `8484` (aligned with image entrypoint contract).
- In-container mount target is fixed at `/home/shell`.

## Customization

- Add system packages: edit `packages.txt`
- Change sudo policy: edit `sudoers`
- Change startup behavior: edit `run_agent`
