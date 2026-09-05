# ZeroMind 运维手册

## 部署与升级

生产环境必须替换 `.env.example` 中的所有占位值。Provider 与 webhook 密钥以环境变量形式
注入容器；数据库只保存变量名。RSSHub Access Key 使用
`ZEROMIND_CREDENTIAL_SECRET` 加密后存入数据库。不要把 `.env` 提交到 Git。

```bash
docker compose pull
docker compose build
docker compose run --rm migrate
docker compose up -d
docker compose ps
```

迁移在 API、worker 和 scheduler 启动前完成。升级前先备份 PostgreSQL；应用版本回退并不自动
回退数据库。需要回退迁移时，先停止写入服务并针对目标 revision 执行
`docker compose run --rm migrate alembic downgrade <revision>`。

### 分析与笔记迁移

| revision | 新增事实 | 安全回滚目标 | 回滚影响 |
| --- | --- | --- | --- |
| `0008_content_analyses` | `content_analyses`、`content_analysis_tags`、`analysis_decision_overrides` | `0007_rsshub_instances` | 删除全部结构化分析、标签和人工改判历史 |
| `0009_notes` | `notes` 及用户/引用、用户/分析索引 | `0008_content_analyses` | 删除全部用户阅读笔记，保留分析 |

从包含 `0009_notes` 的版本回退到 `0007_rsshub_instances` 必须先导出笔记和分析。不要在旧
应用仍写入时执行 downgrade。升级完成后用下列命令确认当前 revision：

```bash
docker compose exec -T postgres psql -U zeromind -d zeromind -Atc \
  "select version_num from alembic_version"
```

## 进程职责

- `api`：同步管理 API 和 OpenAPI。
- `scheduler`：Celery Beat；每 30 分钟产生到期 Feed 认领任务，每分钟触发 outbox 派发。
- `worker`：处理 Feed、工作流和 webhook 队列；任务 late-ack，worker 异常后可重新投递。
- `postgres`：业务事实、幂等键、运行记录和 outbox，是可恢复的唯一事实来源。
- `redis`：短期任务传输；启用 AOF，但不替代 PostgreSQL。
- `frontend`：静态控制台与同源反向代理。

## 历史引用分析回填

升级并注册“信息分析工作流”后，先预览范围，再以小批量验证 Provider、Agent 会话和状态流转，
最后提交全量回填：

```bash
docker compose run --rm api python scripts/backfill_reference_analysis.py --all --dry-run
docker compose run --rm api python scripts/backfill_reference_analysis.py --all --limit 5 --generation lifecycle-v1-smoke
docker compose run --rm api python scripts/backfill_reference_analysis.py --all --generation lifecycle-v1
```

同一 `generation` 对相同引用修订和工作流版本生成稳定请求 ID，可安全重复执行；需要有意重新
分析时使用新的 generation。命令只写入 outbox，不在命令进程中直接调用 Provider。执行后观察
引用状态、失败工作流和 Agent 会话，确认小批量全部到达终态后再运行全量命令。

## RSSHub 实例

在控制台的“RSSHub”页面注册一个或多个 HTTP(S) 实例。第一个启用的实例会自动成为活动
实例，也可以显式切换。订阅保存的是 `rsshub://twitter/user/vista8` 这样的逻辑路由，worker
只在抓取前组合活动实例的 Base URL 和可选 Access Key。

### 内置 Compose 实例

默认 Compose 栈包含 `diygod/rsshub:latest`，但不发布宿主机端口。打开控制台后注册一次：

```text
名称：Built-in RSSHub
Base URL：http://rsshub:1200
Access Key：留空
鉴权模式：key
启用：是
```

ZeroMind 容器通过 Compose DNS 访问 `http://rsshub:1200`。RSSHub 缓存复用 Redis 数据库
`1`，Celery 任务传输继续使用数据库 `0`，两类键不会混用。

`ZEROMIND_RSSHUB_PRIVATE_HOSTS=rsshub` 只为定时 Feed 抓取精确放行主机名 `rsshub`；它不会
放行其他 Compose 服务、`localhost` 或私网 IP 字面量。删除或清空该变量后，内置地址会再次被
出站网络策略阻止。

默认 RSSHub 镜像不包含 Chromium。需要浏览器的路由可把镜像改为
`diygod/rsshub:chromium-bundled`，代价是更高的磁盘和内存使用。`TWITTER_AUTH_TOKEN` 等
路由 Provider 凭证应加入 `compose.yaml` 的 `rsshub.environment`，不能写入 ZeroMind 的实例
Access Key 或订阅地址。

RSSHub 的实例 Access Key 与 Twitter 等上游凭证属于不同边界：

- 实例 Access Key 在 ZeroMind 页面写入，由 `ZEROMIND_CREDENTIAL_SECRET` 加密，接口只返回
  `has_access_key`。
- `TWITTER_AUTH_TOKEN`、Twitter Developer API Key 等上游凭证必须配置在 RSSHub 部署中，
  不要写入 ZeroMind 的订阅地址或实例 Access Key。
- 活动实例不能直接停用或删除；先激活另一个实例。
- 当前版本不会自动故障转移，避免实例版本、缓存和上游账号差异造成内容漂移。

`ZEROMIND_CREDENTIAL_SECRET` 必须使用高熵随机值并在所有 API/worker 副本中保持一致。
数据库中仍有 RSSHub 密文时不能直接轮换该值，否则历史 Access Key 将无法解密。需要轮换时，
先逐个重新写入实例 Access Key，再以受控迁移方式重新加密。

## 备份与恢复

备份：

```bash
docker compose exec -T postgres pg_dump -U zeromind -Fc zeromind > zeromind.dump
```

备份必须覆盖 `content_analyses`、`content_analysis_tags`、
`analysis_decision_overrides` 和 `notes`；它们分别保存生成结果、检索标签、人工决定历史和
用户笔记。使用上面的整库 `pg_dump` 会包含这些表。若采用表级备份，必须显式纳入四张表及
它们引用的 `subscriptions`、`content_references`、`workflow_definitions` 和
`workflow_runs`。

恢复到空数据库：

```bash
docker compose stop api worker scheduler
docker compose exec -T postgres dropdb -U zeromind --if-exists zeromind
docker compose exec -T postgres createdb -U zeromind zeromind
docker compose exec -T postgres pg_restore -U zeromind -d zeromind --clean --if-exists < zeromind.dump
docker compose up -d
```

Redis 丢失后可以从 PostgreSQL 的到期订阅、未派发 outbox 和过期租约恢复。恢复后先确认
只有一个 Beat 实例，避免重复调度；边界幂等仍会阻止重复业务结果。

## 监控

- 存活：`GET /health/live`。
- 就绪：`GET /health/ready`，依赖状态不是全部 `up` 时返回 503。
- 关注：连续 Feed 失败数、pending/processing outbox 年龄、失败工作流比例、webhook exhaustion、
  worker 队列深度、PostgreSQL 磁盘空间。
- 分析漏斗应记录初筛通过率、细筛通过率、因初筛而节省的全文解析/模型调用比例，以及
  人工改判率。按工作流版本和 Agent 版本分组，避免配置变更掩盖趋势。
- 日志中禁止输出 Provider 密钥、RSSHub Access Key、webhook secret、Bearer token 和解析出的
  正文。

## 故障处理

### Feed 连续失败

检查订阅的 `health`、`last_checked_at` 和 `consecutive_failures`。失败会指数退避，重新启用订阅
会使其立即到期。确认目标为公开 HTTP(S) 地址，且响应小于 10 MiB。对于 `rsshub://` 订阅，
还要确认存在启用的活动实例、实例 Access Key 正确，并在 RSSHub 服务端配置了对应路由所需的
上游 Provider 凭证。

### outbox 长时间 pending

确认 `worker` 正在监听 `events` 队列。processing 事件的 5 分钟租约到期后会自动被再次认领。
同一 `idempotency_key` 不会生成第二条业务事件。

### Pi 执行失败

确认 Agent 引用的 Provider Profile 已启用、对应环境变量已注入 worker，并检查
`ZEROMIND_PI_COMMAND`。Pi 运行时禁用 shell、文件系统和内置工具，输出还必须通过 Agent 的
JSON Schema。

Provider 不可用、凭证缺失、Pi 超时或输出 Schema 不匹配时，工作流失败且不会写入部分
`ContentAnalysis`。修复 Provider 后使用相同业务触发重新执行；幂等键会避免已经成功的运行
重复产生分析。

### Agent Schema mismatch

日志或运行记录出现 `AgentInputError` / `AgentOutputError` 时：

1. 对照 `apps/information/docs/examples/screening-agent.json` 或 `analysis-agent.json` 检查 required、
   `additionalProperties`、整数范围和数组上限；
2. 确认工作流传给初筛 Agent 的只有 `metadata`、`audience`，传给分析 Agent 的是
   `metadata`、`document`、`audience` 和可选 `maximum_quotes`；
3. 新建或更新 Agent 会产生新版本，重新校验工作流后再激活。

不要通过放宽投影 Schema 来容忍不完整结果；应修复 Agent prompt 或输出契约。

### analysis_projection_invalid

该错误表示工作流已经正常运行，但最终输出不能安全投影。系统会把运行标记为失败，清除运行
输出和步骤输出，因此不会暴露正文或留下半成品分析。检查：

- 工作流声明必须是 `projection: content_analysis_v1`；
- 三种终止路径都必须输出 `schema_version`、`status`、`reference` 和 `screening`；
- `fine_rejected` / `qualified` 还必须输出 `content` 与由 `score` 节点生成的 `score`；
- 触发器中的 `reference_id`、`revision` 必须与输出引用一致；
- 内容评分维度必须与确定性评分维度完全一致。

### 门禁操作数类型错误

`gate predicate operands are not comparable`（或同类类型错误）是工作流配置/Agent 契约故障，
不是业务拒绝。确认初筛 `score` 和细筛 `total` 都是 0–100 的整数，阈值没有写成字符串。
门禁失败不会被投影成“初筛拒绝”或“细筛拒绝”，以免把系统错误伪装成内容判断。

### webhook 失败

目标必须解析为公网地址，且重定向不会被自动跟随。签名头格式为
`X-ZeroMind-Signature: sha256=<hex>`，签名输入是排序键、无多余空白的 JSON 原始请求体。
每个终点最多重试 1–5 次，耗尽后保留结果供人工排查。

## 安全边界

- 当前管理控制台和 API 无需登录，笔记共享访问；生产环境应在 TLS 反向代理后运行。
- 所有出站原文与 webhook URL 在请求前解析 DNS 并拒绝非公网 IP；原文重定向逐跳复检。
- OPML 使用禁用外部实体的解析器；工作流使用 `yaml.safe_load` 和受限 `$.path` 映射。
- 原文正文仅存在于单次工作流进程内存，运行步骤持久化前会移除 transient document 的正文。
- 定期轮换 Provider 密钥和 webhook secret。RSSHub Access Key 可以在页面
  直接替换；应用凭证加密密钥必须按上面的重新加密流程轮换。
