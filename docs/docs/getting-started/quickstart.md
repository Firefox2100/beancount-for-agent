---
title: Quickstart
---

This runs the service in Docker, with the MCP endpoint on, a bearer token, and your ledgers in a folder you own.

## 1. Build the image

The image is built from the repository. There is no published image yet.

```bash
git clone <repository> beancount-for-agent
cd beancount-for-agent
docker build -t beancount-mcp:local --build-arg VERSION=0.1.0 .
```

`VERSION` is only a label. The build has no git history to read a version from, so it is passed in.

## 2. Choose where the data lives

Create two folders: one for the ledgers, one for the deployment files.

```bash
mkdir -p ~/finance/data ~/finance/service
```

The container runs as user id `1000` and writes to the data folder, so the folder must be writable by that user.

## 3. Write the settings

Create `~/finance/service/.env`. Generate the token with any random source:

```bash
cat > ~/finance/service/.env <<EOF
BEANCOUNT_MCP_AUTH_TOKEN=$(openssl rand -hex 24)
BEANCOUNT_MCP_MCP_ENABLED=true
BEANCOUNT_MCP_LAYOUT=yearly
BEANCOUNT_MCP_AGENT_APPROVAL_REQUIRED=true
EOF
chmod 600 ~/finance/service/.env
```

The token guards the whole service. Keep it secret: the agent must never see it. See [Security](../concepts/security.md).

## 4. Write the compose file

```yaml title="~/finance/service/compose.yaml"
services:
  beancount-mcp:
    image: beancount-mcp:local
    restart: unless-stopped
    env_file: .env
    ports:
      - "127.0.0.1:8421:8000"
    volumes:
      - /home/you/finance/data:/data
```

The port is bound to `127.0.0.1` on purpose. Expose it beyond the machine only behind something that adds TLS and your own access control.

## 5. Start it and check it

```bash
cd ~/finance/service
docker compose up -d
```

Without the token the API refuses you, and with it you get an empty list:

```bash
curl -s localhost:8421/ledgers                              # 401, missing or invalid bearer token
curl -s -H "authorization: Bearer <token>" localhost:8421/ledgers   # []
```

The web interface is at `http://127.0.0.1:8421/ui/`. Sign in with the same token.

## Running from source

For development, or if you prefer no container:

```bash
uv sync
cp .env.example .env     # then edit it
uv run beancount-mcp
```

The service listens on `127.0.0.1:8000` by default. See [Configuration](configuration.md) for every setting.

## Next

[Create your first ledger](first-ledger.md).
