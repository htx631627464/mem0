# SPEC: mem0 官方基底重放 + Bazzite 部署升级

- **Workflow ID**: wf-20261108-upstream-rebase-deploy
- **日期**: 2026-11-08
- **状态**: 待确认
- **基线**: 本地 fork `main` @ `cd0679d4`（基于官方 `2c796d14`）；官方新基底 `f1791daa`（mem0ai/mem0 upstream/main）

## 1. 目标

1. 将本地 mem0 仓库从 fork 基线（`2c796d14`，落后 418 个提交）切换到官方最新基底 `f1791daa`，以官方为主，本地 15 个二开提交按补丁集方式重放融入官方新结构。
2. 升级部署 Bazzite 服务器（`nerox-bazzite`）上正在使用的自托管 mem0 服务（`mem0-dev` compose 项目，4 容器），存量数据（1224 条记忆、pgvector 1536 维）保持兼容、无需重嵌入。

## 2. 非目标

- **不**做 git merge（46 个冲突文件的三向合并）——已评估并否决，改用新基底 + 补丁重放。
- **不**把旧 `integrations/mem0-plugin/`（官方已删除该目录）的全部改动逐一移植到官方新插件结构；自托管路由与保守捕获大部分由官方原生配置替代（见 D2）。
- **不**保留 pi-agent-plugin 的 dream 功能（官方 0.3.x 已整体删除，跟随官方）。
- **不**启用 graph memory / Neo4j（服务器未部署，官方 server compose 中的 neo4j 不启用）。
- **不**重嵌入存量记忆（embedding 模型 text-embedding-v4@1536 不变）。
- **不**触碰 Bazzite 上 dify / ragflow / cppai 等其他服务。
- 延期：request_logs（21695 条 / 约 11MB）清理——部署验证通过后的独立可选步骤，不影响本次交付；清理方式不得破坏 request_logs 表结构。

## 3. 交付 scope

### 本地仓库（`/Users/nerox/99-dev-projects/mem0`）

| 路径 | 内容 |
|---|---|
| `mem0/configs/prompts.py`、`mem0/memory/utils.py` | 中文提取 prompt 整体覆盖 + runtime date refresh 补丁 |
| `server/`（main.py、config_builder.py、memory_policy.py、routers/platform_api.py、tests/、docker 相关） | 自托管 server 补丁集 |
| `integrations/pi-agent-plugin/`（3 个文件） | 自托管适配重放 |
| `integrations/agent-plugin-core/` + `integrations/opencode-plugin/` | 官方共享运行时小补丁（threshold、STABLE_TYPES、opencode host） |
| `integrations/mem0-agent-gateway/` | 自研网关，原样搬入（官方无对应） |
| `dev/docs/` | 部署文档与升级记录 |

### 共享影响面（非仓库路径）

- Bazzite 生产服务 `mem0-dev`（mem0 API :18888、postgres :8432、dashboard :3000、agent-gateway :8765），部署目录 `/var/home/nerox/00-dev/13-mem0/mem0-selfhosted/`。
- gateway:8765 对外 MCP 接口契约（消费端为各编辑器插件，token 鉴权，接口不变）。
- postgres 两库：`postgres`（memories 向量库 52MB）、`mem0_app`（用户/API key/日志 11MB）。

## 4. 关键流程

### 4.1 代码改造（新基底 + 补丁重放）

```
新分支 rebase-official-base（起点 upstream/main @ f1791daa）
  → 整文件搬入：中文 prompts.py、server 5 个新文件、mem0-agent-gateway/
  → 小补丁：server/main.py（3 处）、pi-agent-plugin（3 文件）、
            memory_core.py（threshold + STABLE_TYPES）、opencode-mem0.ts（host + 去自动捕获）
  → build.py --sync 同步各 host 的 core/skills 生成物
  → 本地验证（server pytest + 相关包 lint/test）
  → 合回 main（保留 fork 历史与官方历史的 merge commit）
```

### 4.2 Bazzite 部署升级

```
快照（pg_dump 两库 + mem0-patches 目录 + 旧 compose 目录保留为回滚锚点）
→ rsync 新代码到新目录
→ 重建 3 个镜像（mem0 API 改源码构建；dashboard、gateway 照旧本地构建）
→ compose down && up（alembic upgrade head 自动执行）
→ 冒烟验证（见 §6）
→ 通过后旧目录保留 N 天，用户确认后清理
```

## 5. 约束

- **接口兼容**：gateway:8765 的 MCP 接口与 token 鉴权不变；mem0 API 对 gateway 的 `/v3/memories/*` platform 路由行为不变；dashboard 环境变量沿用。
- **数据兼容**：pgvector schema（id/vector/payload，1536 维）不变；embedding 模型不变；`mem0_app` 库 alembic 迁移前必须先备份；alembic 链只前进（`upgrade head`），不 down。
- **运行时**：mem0ai 版本跟随官方基底（仓库内源码 2.2.1 基底），废除 PyPI `mem0ai==2.0.19` 运行时安装与 `/mem0-patches/` 启动 cp 补丁机制；中文 prompt 进镜像。
- **资源**：Bazzite 容器内存 limit 沿用现状（mem0 192m / dashboard 96m / gateway 96m / postgres 192m），源码构建消除运行时 pip 后如仍紧张，允许上调 mem0 至 256m 并记录。
- **回滚**：旧部署目录 + 双库 dump 快照，回滚 = 旧目录 compose up（必要时 restore dump），要求 5 分钟内可完成。
- **安全**：不在仓库提交任何密钥（gateway.env、server/.env 留在服务器）；diff 检查不含凭证。

## 6. 验收标准

**代码改造完成后（本地）：**
1. `git log` 显示官方历史 + 补丁提交，无合并冲突残留；`docs/` 无冲突标记。
2. `server/` pytest 通过（含 test_server_config.py 33 用例与 platform/memory_policy 相关测试）。
3. mem0 核心包 ruff lint 通过；mem0-agent-gateway 测试通过。
4. 官方新插件目录（agent-plugin-core 等）的补丁落盘且 `build.py --sync` 产物一致。
5. mem0 API 镜像本地构建成功，`docker run` 后 `/docs` 可访问、健康检查通过。

**Bazzite 部署完成后（生产）：**
6. 4 容器 Up 且 healthy；`alembic upgrade head` 无错误。
7. 存量 1224 条记忆可检索：经 gateway:8765 MCP 搜索返回结果且语义相关。
8. 写入→检索闭环：新增一条测试记忆，搜索命中，随后删除。
9. dashboard:3000 可登录、记忆列表非空。
10. 容器内 `import mem0` 指向镜像内源码（非 PyPI site-packages），中文 prompt 生效（检查 `ADDITIVE_EXTRACTION_PROMPT` 含中文示例）。
11. 回滚路径演练：确认旧目录 compose 文件可解析、dump 存在（不实际切换）。

## 7. 已解决的关键决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 新基底 + 补丁重放，不做 merge | merge 有 46 个冲突文件且大量是官方已删除目录的 modify/delete；重放后真正要改官方代码的仅约 10 个文件 |
| D2 | 旧 mem0-plugin 目录放弃；自托管改用官方 `MEM0_API_URL`；保守捕获改用官方 `MEM0_CODE_AUTO_FLUSH=false` + `MEM0_CODE_SEARCH_ONCE_PER_SESSION=true` | 官方新插件结构原生支持，配置化优于维护 fork |
| D3 | pi-agent-plugin 重放 3 处补丁（baseUrl→host、file-wins-over-env、MEM0_BASE_URL），放弃 dream | 官方 0.3.2 无这些能力；dream 已被官方删除，回移成本高 |
| D4 | prompts.py 整体覆盖（官方对它零改动），不用 custom_instructions 注入 | 官方无 system prompt 替换机制，注入会与官方提取激励对抗 |
| D5 | server 5 个新文件整文件重放；platform_api 的 verify_platform_auth 跟进官方短作用域 session 模式 | 依赖全部兼容；官方 9383e9a2 的连接池修复是正确方向 |
| D6 | 废除运行时 pip + cp 补丁，改源码构建镜像 | 根治慢启动与内存压力；官方 2.2.1 prompts.py 与本地基线零差异，补丁内容无需重对齐 |
| D7 | 分支策略：新分支 `rebase-official-base` 从 f1791daa 起，完成后 merge 回 main（保留双方历史） | 不改写历史，官方后续更新可继续 fetch 合并 |

## 8. 待用户确认事项

- B1：Bazzite 部署窗口（服务今晨仍在活跃使用，需要用户指定低峰时段或确认可短暂停机，预计 down→up 全程 10–20 分钟）。
- B2：dashboard 默认 LLM 展示值跟随官方 `gpt-5-mini`（仅展示回退值，实际 LLM 由 config_builder 决定 qwen-flash）——默认跟随官方，如需改动请在确认时说明。
