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

## 进程职责

- `api`：同步管理 API、管理员鉴权和 OpenAPI。
- `scheduler`：Celery Beat；每 30 分钟产生到期 Feed 认领任务，每分钟触发 outbox 派发。
- `worker`：处理 Feed、工作流和 webhook 队列；任务 late-ack，worker 异常后可重新投递。
- `postgres`：业务事实、幂等键、运行记录和 outbox，是可恢复的唯一事实来源。
- `redis`：短期任务传输；启用 AOF，但不替代 PostgreSQL。
- `frontend`：静态控制台与同源反向代理。

## RSSHub 实例

在控制台的“RSSHub”页面注册一个或多个 HTTP(S) 实例。第一个启用的实例会自动成为活动
实例，也可以显式切换。订阅保存的是 `rsshub://twitter/user/vista8` 这样的逻辑路由，worker
只在抓取前组合活动实例的 Base URL 和可选 Access Key。

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

### webhook 失败

目标必须解析为公网地址，且重定向不会被自动跟随。签名头格式为
`X-ZeroMind-Signature: sha256=<hex>`，签名输入是排序键、无多余空白的 JSON 原始请求体。
每个终点最多重试 1–5 次，耗尽后保留结果供人工排查。

## 安全边界

- 只允许单组织管理员；生产环境应在 TLS 反向代理后运行。
- 所有出站原文与 webhook URL 在请求前解析 DNS 并拒绝非公网 IP；原文重定向逐跳复检。
- OPML 使用禁用外部实体的解析器；工作流使用 `yaml.safe_load` 和受限 `$.path` 映射。
- 原文正文仅存在于单次工作流进程内存，运行步骤持久化前会移除 transient document 的正文。
- 定期轮换管理员令牌密钥、Provider 密钥和 webhook secret。RSSHub Access Key 可以在页面
  直接替换；应用凭证加密密钥必须按上面的重新加密流程轮换。
