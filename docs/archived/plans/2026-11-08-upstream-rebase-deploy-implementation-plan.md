# mem0 官方基底重放 + Bazzite 部署升级 Implementation Plan

**Goal:** 在新分支上以官方 `f1791daa` 为基底重放全部本地补丁并验证，随后升级部署 Bazzite 生产服务并确认存量数据兼容。
**Spec:** `docs/archived/specs/2026-11-08-upstream-rebase-deploy.md`

## Spec Traceability

| Requirement（SPEC §） | Task | Verification |
|---|---|---|
| §1.1 仓库切换官方基底 + 补丁重放 | Task 1–6 | V1–V5 |
| §4.1 分支策略（D7） | Task 1、Task 7 | V1 |
| §1.2 / §4.2 Bazzite 升级部署 | Task 8–11 | V6–V11 |
| §5 数据兼容与回滚约束 | Task 8（快照）、Task 10（验证）、Task 11（回滚锚点） | V7、V11 |
| §2 非目标（不重嵌入、不动其他服务） | 全程约束 | 部署冒烟仅查 memories 计数不变 |

## Codebase Evidence

- 官方对照仓库：`/Users/nerox/99-dev-projects/mem0-upstream`（f1791daa），本地 fork 已 fetch `upstream/main` 同一 commit，对象库共享。
- 补丁源：本地 `main` @ `cd0679d4`，与 Bazzite 运行态逐文件 sha256 一致（已核实）。
- 重放分析结论（四份子代理报告，已归档于本 workflow 上下文）：
  - `mem0/configs/prompts.py` 官方零改动 → 本地版整体覆盖零冲突。
  - `server/` 5 个新文件（config_builder、memory_policy、platform_api、test_server_config、docker 透传）依赖在官方新版签名兼容；唯一适配点 `verify_platform_auth` 的 DB session 作用域（官方 `9383e9a2` 模式）。
  - pi-agent-plugin 官方 0.3.2：重放 3 处（types.ts `baseUrl`、entry.ts `host`、config/index.ts file-wins + `MEM0_BASE_URL`）。
  - agent-plugin-core：`memory_core.py` search payload 加 `threshold`、`_search_filters`/`format_context` 加 STABLE_TYPES；`opencode-mem0.ts` 加 host、摘除 `%3` 自动捕获与 `%5` nudge；改 core 后须 `build/build.py <host> --sync`。
- 官方验证入口：根 `make lint`/`make test`（ruff+pytest）、`server/` 无 pytest 目录（本地 test_server_config.py 一并建立）、`integrations/mem0-agent-gateway/tests/test_gateway.py`（pytest）、`agent-plugin-core/conformance/run.py`。
- Bazzite 现状（已核实）：compose 项目 `mem0-dev` 4 容器健康；部署目录 `/var/home/nerox/00-dev/13-mem0/mem0-selfhosted/`（非 git）；override 启动命令含 PyPI force-reinstall + `/mem0-patches/` cp 补丁（本次废除）；postgres 两库 52MB+11MB；备份目录与 9 月迁移 dump 齐备。

## Feasibility Lab

### Experiment 1: 本地 fork 仓库能否直接基于 f1791daa 建分支而不破坏 main 历史？

- Evidence: 本地已配置 `upstream` remote 并 fetch（`git merge-base main upstream/main` = 2c796d14，对象完整）。
- Probe: `git switch -c rebase-official-base upstream/main` → 在分支上重放 → 完成后 `git checkout main && git merge --no-ff rebase-official-base`。
- Result: 可行（无需动 mem0-upstream 克隆，它仅作只读对照）。
- Plan impact: Task 1 直接可用；mem0-agent-gateway 从本地 main 提取（`git checkout main -- integrations/mem0-agent-gateway dev/docs`）。

### Experiment 2: 官方 dev.Dockerfile 构建链在源码方式下是否可用？

- Evidence: 官方 `server/dev.Dockerfile` 走 `pip install -r requirements.txt` 后 `COPY . .`；现 Bazzite 部署 bind-mount 仓库并以 uvicorn `--reload` 运行。运行时实际 import 优先级待确认（服务器容器 `import mem0.__file__` 未实测——SPEC §6.10 已列为验收项）。
- Probe: 改造阶段新增 `server/selfhost.Dockerfile`：`pip install -e /app/mem0-pkg`（或 `COPY` + `pip install --no-deps /app`）确保镜像内 `mem0` 解析到仓库源码；本地 `docker build` 验证。
- Result: 有约束可行——不依赖官方 dev.Dockerfile 的隐式行为，自建 Dockerfile 显式源码安装。
- Plan impact: Task 6 产出独立 Dockerfile；Bazzite override 的启动 command 同步简化（去掉 pip + cp 步骤）。

### Experiment 3: alembic 链在旧库上前进是否安全？

- Evidence: `mem0_app.alembic_version` 现为服务器运行版（本地 fork server/alembic 与官方 2c796d14..HEAD 的差异未逐条核对）；官方新版 server 若有新 revision，`upgrade head` 只加不改。
- Probe: 部署前 Task 8 快照后，Task 9 先在 Bazzite 用新镜像起一次性容器跑 `alembic upgrade head`（compose 依赖顺序保持），失败则回滚快照。
- Result: 有约束可行——快照先行 + 只前进不回退（SPEC §5）。
- Plan impact: Task 8/9 顺序不可交换；冒烟含 alembic 结果检查。

## Delivery Scope

- **Paths（本地仓库，分支 rebase-official-base）**:
  - `mem0/configs/prompts.py`、`mem0/memory/utils.py`
  - `server/**`（main.py、config_builder.py、memory_policy.py、routers/platform_api.py、selfhost.Dockerfile、tests/、.env.example、requirements.txt、docker-compose*.yaml）
  - `integrations/pi-agent-plugin/src/{types,entry,config/index}.ts`
  - `integrations/agent-plugin-core/python/memory_core.py`、`integrations/opencode-plugin/opencode-mem0.ts` 及 `build.py --sync` 生成物（各 host `core/`、`skills/`）
  - `integrations/mem0-agent-gateway/**`（整目录搬入）
  - `dev/docs/**`（部署记录）
- **Shared surfaces**:
  - Bazzite：`/var/home/nerox/00-dev/13-mem0/`（mem0-selfhosted 新旧目录、backups、gateway.env）；gateway:8765 MCP 契约；postgres 两库。
  - 分支集成点：`main`（merge --no-ff）。
  - agent-plugin-core 生成链路（`build/build.py`），改 core 必须重新生成各 host 副本。

## Tasks

### Task 1: 建分支与基底准备

- Outcome: `rebase-official-base` 分支存在且指向 `f1791daa`，工作区干净。
- Files: 无（仅 git 操作）。
- Commands: `git switch -c rebase-official-base upstream/main`。
- Dependencies: 无。
- Verification: `git log --oneline -1` = f1791daa；`git status` 干净。

### Task 2: 整文件搬入（零冲突补丁）

- Outcome: 四组官方无对应的文件落盘。
- Files:
  - `git checkout main -- mem0/configs/prompts.py mem0/memory/utils.py`（覆盖官方版）
  - `git checkout main -- server/config_builder.py server/memory_policy.py server/routers/platform_api.py server/tests/test_server_config.py integrations/mem0-agent-gateway dev/docs`
  - `server/.env.example`、`server/docker-compose.yaml`：从 main 取增量段（DEEPSEEK/DASHSCOPE/透传变量），基于官方新版文件手工融合（.env.example 保留官方 gpt-5-mini 行，SPEC B2）。
- Constraints: 不引入 main 中对已删除 mem0-plugin/ 的引用。
- Dependencies: Task 1。
- Verification: 文件存在、无冲突标记；`git diff main -- mem0/configs/prompts.py` 为空（与 main 完全一致）。

### Task 3: server main.py 小补丁

- Outcome: main.py 含 4 处改动：`BUNDLED_LLM_PROVIDERS` 加 `"deepseek"`、`DEFAULT_CONFIG = build_default_config()`、`include_router(platform_api_router.router)`、add 接口 `drop_user_narration` 钩子；尾部 uvicorn 开发入口。
- Files: `server/main.py`（基于官方 f1791daa 版打补丁，插入点：官方 367-382 行 add_memory）。
- Pseudocode:
  ```python
  from config_builder import build_default_config
  from memory_policy import drop_user_narration
  from routers import platform_api as platform_api_router
  BUNDLED_LLM_PROVIDERS = ("openai", "anthropic", "gemini", "deepseek")
  DEFAULT_CONFIG = build_default_config()
  # add_memory(): memory = get_memory_instance(); response = memory.add(...); response = drop_user_narration(memory, response)
  ```
- Dependencies: Task 2。
- Verification: V2（server pytest）+ `python -c "import main"` 冒烟（在 server/ 下）。

### Task 4: platform_api auth 作用域适配

- Outcome: `verify_platform_auth` 改为官方 `9383e9a2` 短作用域模式（仅 `_resolve_user_from_api_key` 分支内 `with SessionLocal() as db`），去掉整请求周期的 `db=Depends(get_db)`。
- Files: `server/routers/platform_api.py`。
- Dependencies: Task 2。
- Verification: V2 含 platform 路由测试；行为不变（token→用户解析、401 语义）。

### Task 5: pi-agent-plugin 与 agent-plugin-core/opencode 补丁

- Outcome:
  - pi：`types.ts` 加 `baseUrl?: string`；`entry.ts` `new MemoryClient({apiKey, ...(config.baseUrl ? {host: config.baseUrl} : {})})`；`config/index.ts` file-wins + `MEM0_BASE_URL` 兜底。
  - core：`memory_core.py` search payload 加 `"threshold": 0.45`；`_search_filters()`/`format_context()` 加 STABLE_TYPES（decision/bug_fix）过滤。
  - opencode：`opencode-mem0.ts` 加 host 参数、删除 `%3` 自动捕获块与 `%5` nudge 块。
  - 跑 `integrations/agent-plugin-core/build/build.py --sync` 同步各 host core/skills 生成物。
- Files: 见 Outcome；生成物：各 host 插件目录 `core/`、`skills/`。
- Constraints: 只改列入清单的文件；pi 的 `applySurfaceHeaders` 保留；`package-lock.json`（npm 产物）不搬入。
- Dependencies: Task 1。
- Verification: pi `pnpm typecheck`（或 `tsc --noEmit`）；core 改动后 `build.py --sync` 输出各 host diff 仅含预期文件；`conformance/run.py` 离线项通过。

### Task 6: 源码构建镜像

- Outcome: `server/selfhost.Dockerfile`（多阶段：装 server 依赖 → 安装仓库内 `mem0/` 源码 → COPY server/），本地构建成功且容器内 `import mem0` 指向源码。
- Files: `server/selfhost.Dockerfile`、`server/docker-compose.yaml`（mem0 服务 build 指向新 Dockerfile，去掉 PyPI force-reinstall command 模板）。
- Pseudocode:
  ```dockerfile
  FROM python:3.12-slim
  COPY server/requirements.txt /tmp/ && pip install -r /tmp/requirements.txt
  COPY mem0 /app/mem0-src/mem0 + pyproject 片段 → pip install --no-deps /app/mem0-src
  COPY server /app/server && WORKDIR /app/server
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
- Constraints: mem0 核心依赖需完整安装（不能用 --no-deps 丢依赖）；镜像内不再需要 `/mem0-patches/`。
- Dependencies: Task 3。
- Verification: V5（本地 docker build + run + /docs + `docker exec ... python -c "import mem0; print(mem0.__file__)"` 显示源码路径）。

### Task 7: 本地全量验证与合回 main

- Outcome: V1–V5 全过；`main` 合并 `rebase-official-base`（--no-ff）。
- Commands:
  - `make lint && make test`（根 SDK，ruff+pytest 全量）
  - `cd server && python -m pytest tests/ -q`
  - `cd integrations/mem0-agent-gateway && python -m pytest tests/ -q`
  - pi/core 包各自的 typecheck/test 入口
  - `git checkout main && git merge --no-ff rebase-official-base`
- Dependencies: Task 2–6。
- Verification: V1–V5 命令输出全绿；merge commit 无冲突。

### Task 8: Bazzite 预部署快照（生产，需窗口确认 B1）

- Outcome: 双库 pg_dump + patches 目录 + 旧目录只读保留，落 `/var/home/nerox/00-dev/13-mem0/backups/pre-upgrade-20261108/`。
- Commands（服务器）:
  ```bash
  podman exec mem0-dev-postgres-1 pg_dumpall -U postgres | gzip > .../postgres-all.dump.gz
  cp -a /var/home/nerox/00-dev/13-mem0/mem0-selfhosted .../mem0-selfhosted.bak-20261108/
  ```
- Constraints: 服务不停（dump 期间短锁可接受）；不覆盖既有备份。
- Dependencies: Task 7（代码就绪后再动生产）。
- Verification: dump 文件非空且 gzip -t 通过；备份目录清单核对。

### Task 9: 部署新代码与镜像重建

- Outcome: 新代码 rsync 到 `/var/home/nerox/00-dev/13-mem0/mem0-selfhosted-new/`（含 compose、override、selfhost.Dockerfile、gateway/）；服务器上重建 3 镜像；compose down（旧）→ up（新目录）。
- Files（服务器）: mem0-selfhosted-new/**；镜像 mem0-dev-mem0、mem0-dev-mem0-dashboard、mem0-agent-gateway 重建。
- Constraints: 端口映射、env_file（.env、../../gateway.env）、内存 limit、alembic 只前进；rsync 排除 .git（或包含 .git 以便服务器可追溯——采用排除 + 附 COMMIT 文件记录 commit hash）。
- Dependencies: Task 8。
- Verification: `podman ps` 4 容器 Up；`podman logs mem0-dev-mem0-1 | grep -i alembic` 无错误。

### Task 10: 生产冒烟验证

- Outcome: V6–V10 通过。
- Commands:
  ```bash
  # V7 存量检索（经 gateway MCP，token 从 gateway.env 读，不回显）
  # V8 写入→检索→删除闭环
  # V9 dashboard 登录
  # V10 docker exec mem0-dev-mem0-1 python -c "import mem0;print(mem0.__file__)" + 中文 prompt 检查
  ```
- Constraints: 测试记忆用 `metadata.type=decision`、写后即删；验证过程不产生永久数据。
- Dependencies: Task 9。
- Verification: 逐项记录结果到 dev/docs 部署记录。

### Task 11: 回滚锚点确认与收尾

- Outcome: V11；部署记录落盘 `dev/docs/2026-11-08-bazzite-upgrade-record.md`（含验证结果、commit hash、回滚步骤）；旧目录保留待用户确认清理。
- Dependencies: Task 10。
- Verification: 记录文件存在且引用路径有效；`podman ps` 稳定运行。

## Risks and Deferred Follow-ups

- **R1 mem0ai 2.0.19→2.2.x 行为差异**（filters/提取路径）：应对 = Task 10 冒烟覆盖搜索/写入/删除；失败走 Task 8 快照回滚。
- **R2 192MB limit 下新核心运行压力**：应对 = 源码镜像消除运行时 pip；冒烟观察 RSS，超限则上调至 256m（SPEC §5 允许）并记录。
- **R3 官方 alembic 新 revision 与旧库不兼容**：应对 = 快照先行 + 一次性容器先跑 migration 再放流量。
- **R4 agent-plugin-core 生成链路遗漏 sync**：应对 = Task 5 强制 `build.py --sync` 且核对各 host diff。
- 延期：request_logs 清理（SPEC §2）；mem0-upstream 只读克隆的后续处置（保留作对照或删除，不影响交付）。

## 准备度：可实施

- 影响架构/顺序/验收的开放决策：无（B1 部署窗口、B2 展示值已按 SPEC 处理为默认值 + 用户确认点，不阻塞代码改造阶段 Task 1–7）。
- Task 8 起进入生产操作，前置条件 = Task 7 全绿 + 用户确认窗口（B1）。
