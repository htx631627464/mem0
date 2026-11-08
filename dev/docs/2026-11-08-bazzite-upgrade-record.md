# Bazzite 生产升级记录 — 2026-11-08/09

- **Workflow**: wf-20261108-upstream-rebase-deploy
- **代码版本**: `ad63e077`（main；= 官方 f1791daa + 自托管补丁集 + 2 个部署修复）
- **服务器**: nerox-bazzite，部署目录 `/var/home/nerox/00-dev/13-mem0/mem0-selfhosted-new/`（旧目录原地保留）
- **停机窗口**: 约 22:40–00:35（构建期间旧服务持续在线，实际 down→up 停机约 1 分钟）

## 升级内容

- 官方基底 2c796d14 → f1791daa（418 提交：CVE 安全修复、agent-plugin-core 插件重构、server 加固）
- mem0ai 2.0.19（PyPI + 启动 cp 补丁）→ 仓库源码构建镜像（中文提取 prompt 进镜像）
- mem0 容器启动不再运行时 `pip force-reinstall` 与 `/mem0-patches/` 覆盖

## 部署中的问题与修复

| 问题 | 修复 |
|---|---|
| 直连 pypi 构建超时 | selfhost.Dockerfile 增加 `PIP_INDEX_URL` build-arg（override 配清华源）→ commit `f0e9…`（ad63e077 前置） |
| mem0 容器崩溃：`sqlite3.OperationalError: unable to open database file` | Fedora/SELinux 要求 bind mount 带 `:Z`；compose history 挂载补 `:Z`（ad63e077） |
| history 目录缺失导致首次启动失败 | 从旧目录复制 `history/history.db`（3.2MB 历史记录保留） |
| 新 .env 缺 `OPENAI_BASE_URL`/`OPENAI_API_KEY`（DashScope 兼容路径依赖 env 级变量） | .env 追加 `OPENAI_BASE_URL=dashscope compatible-mode`，`OPENAI_API_KEY=$DASHSCOPE_API_KEY` |

## 冒烟验证结果（全部通过）

| 项 | 结果 |
|---|---|
| V6 容器 | 4 容器 Up（postgres/mem0/dashboard healthy），alembic 无错误 |
| V7 存量检索 | "ragflow Authorization 透传" → 3 条语义相关中文记忆（1224 条存量向量 + 1536 维兼容） |
| V8 写删闭环 | add(infer=false) → 搜索命中 → `/v1/memories/{id}/` DELETE → 复检不存在 |
| V9 Dashboard | `127.0.0.1:3000/api/health` 200 |
| V10 源码生效 | 容器内 `import mem0` → site-packages（源码安装）；`ADDITIVE_EXTRACTION_PROMPT` 含中文示例 |
| Gateway MCP | `POST /mcp` initialize → 200 |
| 业务恢复 | 升级后 `22-workflow-monitor` 经网关正常写入 3 条记忆 |

## 运行时配置要点

- LLM/embedder 走 OpenAI 兼容路径：`deepseek-v4.1-flash` + `text-embedding-v4`@1536，均经 DashScope compatible-mode（`OPENAI_BASE_URL` + `DASHSCOPE_API_KEY`）
- 内存 limit：mem0 192m / dashboard 96m / gateway 96m / postgres 192m（未动）
- compose override（服务器侧 `server/docker-compose.override.yml`）：端口绑定、内存限制、mem0 构建的清华 pip 源

## 回滚方案（5 分钟内）

```bash
cd /var/home/nerox/00-dev/13-mem0/mem0-selfhosted-new/server && podman compose down
cd /var/home/nerox/00-dev/13-mem0/mem0-selfhosted/server && podman compose up -d
# 数据如需回退（本次 alembic 无新迁移，通常不需要）：
# gunzip -c ../backups/pre-upgrade-20261108/pg-all-databases.dump.gz | podman exec -i mem0-dev-postgres-1 psql -U postgres
```

回滚资产：`backups/pre-upgrade-20261108/`（pg-all-databases.dump.gz 13MB 已 gzip -t 校验、旧目录整树、mem0-patches 快照）+ 旧目录 `mem0-selfhosted/` 原地保留。

## 待办（用户确认后）

- 观察数天后清理旧目录 `mem0-selfhosted/` 与旧镜像
- 可选：request_logs（21000+ 条）归档清理
- 编辑器侧插件（Codex/OpenCode/Pi）切换到官方新插件 + `MEM0_API_URL` 指向 gateway 的后续工作（独立任务）
