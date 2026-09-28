# 本地开发与验证

需要 Python 3.12+、uv。在仓库根目录开始：

```bash
cd apps/subscriptions
uv sync --locked
export SUBSCRIPTIONS_DATABASE_URL=sqlite+aiosqlite:///subscriptions.db
uv run alembic upgrade head
uv run uvicorn subscription_service.bootstrap.app:create_app --factory --host 127.0.0.1 --port 8000
```

这是服务目录下独立的本地数据库，不是旧 information 库。启动不会自动建表或加载根目录 .env。
交互文档为 `http://127.0.0.1:8000/api/docs`；OpenAPI 为 `/api/openapi.json`。
当前无鉴权，仅本地运行或放在有鉴权的可信网关后，不直接暴露公网。

## 常见问题

| 现象 | 检查方向 |
| --- | --- |
| 表不存在 | 是否先迁移；迁移和服务是否使用同一 URL 和工作目录 |
| 409 | 看错误 code 区分地址重复和版本冲突，重新读取后判断 |
| 422 | 检查字段类型、空值、地址格式和版本范围 |
| 创建成功但无文章 | 当前只有来源 HTTP 管理，没有网络采集入口 |
| 配置 RSSHub 后未请求它 | 目前仅接受 rsshub 地址值对象，固定部署适配器尚未接入 |

测试命令和数据库隔离要求见 [测试入口](../testing/README.md)。
迁移与 PostgreSQL 说明见 [持久化](../implementation/persistence.md)。降级到 base 会删除业务表及数据，只能在明确可销毁的库上操作。
