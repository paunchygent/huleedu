---
type: runbook
service: global
severity: high
last_reviewed: '2026-02-01'
---
# Hemma alpha rollout (Days 1-3)

Executable rollout steps for making HuleEdu publicly reachable on Hemma (DNS/TLS +
nginx-proxy routing) and establishing the first repeatable “git pull + compose up”
deployment workflow.

This runbook intentionally focuses on Days 1–3 of:
- `TASKS/programs/huledu_alpha_launch/hub.md`

## Preconditions

- Hemma already runs the shared reverse proxy stack (nginx-proxy + Let’s Encrypt) used
  by Skriptoteket.
- An external Docker network exists for cross-app routing (called `hule-network` in the
  HuleEdu repo).
- You can SSH to Hemma as non-root.

## Day 1 — DNS + TLS surface (public)

### 1. DNS records

Create/verify public DNS A/AAAA records pointing to Hemma’s public IP:
- `api.huleedu.hule.education`
- `huleedu.hule.education`
- `ws.huleedu.hule.education`

Verify from your dev machine:
```bash
dig +short api.huleedu.hule.education
dig +short huleedu.hule.education
dig +short ws.huleedu.hule.education
```

### 2. Reverse proxy stack health

Verify that Hemma’s proxy stack is running and listening on 80/443:
```bash
ssh hemma 'sudo ss -lntp | rg \":(80|443)\" || true'
ssh hemma 'sudo docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\" | rg -i \"nginx|proxy|letsencrypt\" || true'
```

### 3. Certificate issuance readiness

We rely on nginx-proxy auto-discovery (container env vars). HuleEdu production overrides
already declare:
- `VIRTUAL_HOST`
- `VIRTUAL_PORT`
- `LETSENCRYPT_HOST`

See `docker-compose.prod.yml` in this repo for the authoritative hostnames.

## Day 2 — First HuleEdu deploy workflow on Hemma

### 0. Decide the Hemma checkout location

Canonical convention (mirror Skriptoteket):

- Repo checkout: `~/apps/huleedu`

### 1. Create external network (once)

HuleEdu production overrides assume an external network:
```bash
ssh hemma 'sudo docker network create hule-network || true'
ssh hemma 'sudo docker network ls | rg \"\\bhule-network\\b\"'
```

### 2. Mirror the repo on Hemma

First-time setup (example):
```bash
ssh hemma 'mkdir -p ~/apps'
ssh hemma 'cd ~/apps && git clone <YOUR_GIT_REMOTE> huleedu'
```

Subsequent updates:
```bash
ssh hemma 'cd ~/apps/huleedu && git pull'
```

### 3. Create Hemma `.env` for production

`docker-compose.prod.yml` documents required variables at the top of the file. At
minimum you will need the production DB password, JWT secret, and internal API key.

Create/edit:
```bash
ssh hemma 'cd ~/apps/huleedu && nano .env'
```

### 4. Shared DB prerequisites (if using shared-postgres)

`docker-compose.prod.yml` includes the SQL block needed to create databases in
`shared-postgres`.

Run on Hemma:
```bash
ssh hemma 'sudo docker exec -it shared-postgres psql -U postgres -c \"\\l\"'
```

(Optional) create missing databases (copy the SQL block from `docker-compose.prod.yml`).

### 5. First deploy (build + start)

Use prod overrides on top of base compose:
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml up -d --build'
```

### 6. Verify service health (container-level)

```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose ps'
```

Health endpoints inside the stack (examples; adjust ports if configured differently):
```bash
ssh hemma 'curl -fsS http://127.0.0.1:8080/healthz || true'   # api gateway if bound to host
ssh hemma 'curl -fsS http://127.0.0.1:4101/healthz || true'   # bff
```

### 7. Verify reverse proxy routing + TLS

From your dev machine:
```bash
curl -fsSI https://api.huleedu.hule.education/healthz
curl -fsSI https://huleedu.hule.education/healthz
curl -fsSI https://ws.huleedu.hule.education/healthz
```

If TLS issuance is still pending, tail the proxy logs on Hemma until cert provisioning
completes.

## Day 3 — `language_tool_service` on Hemma for research (tunneled)

We deploy HuleEdu’s `language_tool_service` in Docker and keep it localhost-only on
Hemma, then tunnel it to the dev machine.

### 1. Deploy language_tool_service

If the main HuleEdu stack is up, the service may already be running. Verify first:
```bash
ssh hemma 'sudo docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\" | rg \"language_tool\" || true'
```

Deploy with Hemma overrides to keep the service localhost-only on the host:
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d --build language_tool_service'
```

### 2. Health check on Hemma (localhost)

```bash
ssh hemma 'curl -fsS http://127.0.0.1:8085/healthz'
```

### 3. Persistent tunnels (recommended: `~/bin` + LaunchAgent)

This mirrors the Skriptoteket llama.cpp tunnel pattern: a small `~/bin` wrapper around
`autossh`, plus a LaunchAgent so it starts on login.

Install autossh on macOS:
```bash
brew install autossh
```

Create the tunnel helper script (local dev machine):
```bash
mkdir -p ~/bin
cat > ~/bin/hemma-huleedu-tunnel <<'SH'
#!/usr/bin/env bash
set -euo pipefail

# LaunchAgents default PATH does not include Homebrew.
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

HOST=hemma
PID_DIR="${HOME}/.cache/hemma-huleedu-tunnel"

LT_LOCAL_PORT=18085
LT_REMOTE_PORT=8085

EMBED_LOCAL_PORT=19000
EMBED_REMOTE_PORT=9000

mkdir -p "$PID_DIR"

start_tunnel() {
  local local_port=$1
  local remote_port=$2
  local name=$3
  local pid_file="${PID_DIR}/tunnel-${local_port}.pid"

  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "✓ ${name} tunnel already running (localhost:${local_port} -> hemma:${remote_port})"
      return
    fi
  fi

  autossh -M 0 -N \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -L ${local_port}:localhost:${remote_port} ${HOST} >/dev/null 2>&1 &

  echo $! > "$pid_file"
  echo "▶ Started ${name} tunnel (localhost:${local_port} -> hemma:${remote_port})"
}

start_launchd() {
  exec autossh -M 0 -N \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -L ${LT_LOCAL_PORT}:localhost:${LT_REMOTE_PORT} \
    -L ${EMBED_LOCAL_PORT}:localhost:${EMBED_REMOTE_PORT} \
    ${HOST}
}

stop_tunnel() {
  local local_port=$1
  local name=$2
  local pid_file="${PID_DIR}/tunnel-${local_port}.pid"
  local pid=""

  if [[ -f "$pid_file" ]]; then
    pid=$(cat "$pid_file" 2>/dev/null || true)
  fi

  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    echo "■ Stopped ${name} tunnel"
    return
  fi

  rm -f "$pid_file"
  echo "  ${name} tunnel not running"
}

status() {
  echo "=== Hemma HuleEdu Tunnels ==="
  for port in $LT_LOCAL_PORT $EMBED_LOCAL_PORT; do
    if nc -z -w 1 localhost ${port} 2>/dev/null; then
      if curl -fsS --connect-timeout 2 http://localhost:${port}/healthz >/dev/null 2>&1; then
        echo "✓ Port ${port}: connected"
      else
        echo "? Port ${port}: port open, service unreachable"
      fi
    else
      echo "✗ Port ${port}: not running"
    fi
  done
}

case "${1:-start}" in
  start)
    start_tunnel $LT_LOCAL_PORT $LT_REMOTE_PORT "language-tool-service"
    start_tunnel $EMBED_LOCAL_PORT $EMBED_REMOTE_PORT "essay-embed-offload"
    ;;
  start-launchd)
    start_launchd
    ;;
  start-language-tool)
    start_tunnel $LT_LOCAL_PORT $LT_REMOTE_PORT "language-tool-service"
    ;;
  start-embeddings)
    start_tunnel $EMBED_LOCAL_PORT $EMBED_REMOTE_PORT "essay-embed-offload"
    ;;
  stop)
    stop_tunnel $LT_LOCAL_PORT "language-tool-service"
    stop_tunnel $EMBED_LOCAL_PORT "essay-embed-offload"
    ;;
  stop-language-tool)
    stop_tunnel $LT_LOCAL_PORT "language-tool-service"
    ;;
  stop-embeddings)
    stop_tunnel $EMBED_LOCAL_PORT "essay-embed-offload"
    ;;
  restart)
    $0 stop
    sleep 1
    $0 start
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $(basename $0) {start|start-language-tool|start-embeddings|stop|stop-language-tool|stop-embeddings|restart|status}"
    exit 1
    ;;
esac
SH
chmod +x ~/bin/hemma-huleedu-tunnel
```

Start tunnels:
```bash
~/bin/hemma-huleedu-tunnel start
```

Auto-start on login (LaunchAgent):
```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.hemma.huleedu-tunnel.plist <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hemma.huleedu-tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/bin/hemma-huleedu-tunnel</string>
        <string>start-launchd</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/hemma-huleedu-tunnel.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/hemma-huleedu-tunnel.log</string>
</dict>
</plist>
XML

launchctl unload ~/Library/LaunchAgents/com.hemma.huleedu-tunnel.plist >/dev/null 2>&1 || true
launchctl load ~/Library/LaunchAgents/com.hemma.huleedu-tunnel.plist
```

Note: replace `YOUR_USERNAME` with your macOS username (e.g. `/Users/olofs_mba/...`).

Verify locally:
```bash
curl -fsS http://127.0.0.1:18085/healthz
curl -fsS http://127.0.0.1:19000/healthz
```

Manual one-off alternative:
```bash
autossh -M 0 -N \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -L 18085:localhost:8085 hemma
```

### 4. Smoke test `POST /v1/check`

```bash
curl -fsS http://127.0.0.1:18085/v1/check \
  -H 'Content-Type: application/json' \
  -d '{\"text\":\"This are bad.\",\"language\":\"en-US\"}' | head
```

## Day 3 (optional) — DeBERTa embedding offload server (tunneled)

This is the research-scoped embedding server under:
- `scripts/ml_training/essay_scoring/offload/`

It returns embeddings as a binary `.npy` float32 matrix for throughput.

### 1. Build the image on Hemma

Recommended (compose profile; keeps it localhost-only by default):
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-offload up -d --build essay_embed_offload'
```

Recommended: use the repo script (handles ROCm base image + cache mounts):
```bash
ssh hemma 'cd ~/apps/huleedu && ./scripts/ml_training/essay_scoring/offload/hemma_offload_deploy.sh'
```

Manual alternative (keep for debugging):

GPU (ROCm) build: use a ROCm-enabled PyTorch base image that already provides `torch`.
```bash
ssh hemma 'cd ~/apps/huleedu && sudo docker build -f scripts/ml_training/essay_scoring/offload/Dockerfile --build-arg BASE_IMAGE=rocm/pytorch:latest -t huleedu-essay-embed-offload:dev .'
```

### 2. Run the container (localhost-only on Hemma)

Recommended: the deploy script runs the container with `-p 127.0.0.1:9000:9000` and
mounts a persistent Hugging Face cache.

Manual alternative (keep for debugging):
```bash
ssh hemma 'sudo docker rm -f huleedu_essay_embed_offload || true'
ssh hemma 'sudo docker run -d --name huleedu_essay_embed_offload --restart unless-stopped \
  -p 127.0.0.1:9000:9000 \
  -e OFFLOAD_HTTP_PORT=9000 \
  -e OFFLOAD_TORCH_DEVICE=${OFFLOAD_TORCH_DEVICE:-cuda} \
  -v /srv/scratch/huleedu/cache/huggingface:/cache/huggingface \
  -e HF_HOME=/cache/huggingface \
  -e TRANSFORMERS_CACHE=/cache/huggingface \
  huleedu-essay-embed-offload:dev'
```

### 3. Health check on Hemma

```bash
ssh hemma 'curl -fsS http://127.0.0.1:9000/healthz'
```

### 4. Tunnel to local port

If you created `~/bin/hemma-huleedu-tunnel` above, it already manages this tunnel.

Start (embeddings only):
```bash
~/bin/hemma-huleedu-tunnel start-embeddings
```

Verify locally:
```bash
curl -fsS http://127.0.0.1:19000/healthz
```

### 5. Run the research pipeline against Hemma

Example:
```bash
pdm run essay-scoring-research ablation \
  --dataset-path /tmp/ielts_small_ablation.csv \
  --language-tool-service-url http://127.0.0.1:18085 \
  --embedding-service-url http://127.0.0.1:19000
```

## Notes

- Keep “public” surface area limited to the three entrypoint domains (API/BFF/WS).
- Keep heavy research/offload endpoints localhost-only on Hemma and accessed via tunnels.

## Symptoms

## Diagnosis

## Resolution

## Prevention
