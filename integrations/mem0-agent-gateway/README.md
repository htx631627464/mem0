# Mem0 Agent Gateway

Self-hosted compatibility gateway for Codex/OpenCode Mem0 plugins.

It exposes:

- Hosted-compatible REST subset used by Mem0 SDKs and hooks.
- MCP Streamable HTTP-style JSON-RPC endpoint at `/mcp`.
- No cloud fallback. All memory traffic is forwarded to a configured self-hosted `server/` instance.

Required environment:

```env
MEM0_GATEWAY_TOKEN=<token exposed to Codex/OpenCode>
MEM0_SERVER_URL=http://127.0.0.1:8888
MEM0_SERVER_API_KEY=<self-hosted server api key>
```

Run locally:

```bash
uvicorn mem0_agent_gateway.app:create_app_from_env --factory --host 0.0.0.0 --port 8765
```
