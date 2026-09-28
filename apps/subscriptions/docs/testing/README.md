# 测试知识库

用例说明和自动化代码分工：文档说明目的、输入与预期，代码是可执行断言。

| 层级 | 测试文件 | 验证内容 |
| --- | --- | --- |
| 领域 | [test_domain.py](../../tests/test_domain.py) | 地址、时间、版本、幂等和修订规则 |
| 持久化集成 | [test_persistence.py](../../tests/test_persistence.py) | 真实迁移、约束、工作单元、回滚和乐观锁 |
| HTTP 集成 | [test_api.py](../../tests/test_api.py) | ASGI 请求经过应用层与临时 SQLite，不模拟仓储 |
| 启动生命周期 | [test_bootstrap.py](../../tests/test_bootstrap.py) | 显式配置、关闭重开后读取已提交数据 |
| 迁移命令 | [test_migration_cli.py](../../tests/test_migration_cli.py) | 独立进程升级与降级，路径含百分号 |
| OPML 导入 | [test_opml_api.py](../../tests/test_opml_api.py) | 实际写入、重复跳过、并发竞争、中断与重试 |
| XML 安全边界 | [test_opml_reader.py](../../tests/test_opml_reader.py) | 字节/节点/深度边界，UTF-16 实体拒绝 |

## 测试场景目录

- [来源管理用例](source-cases.md)
- [条目、检查点及仓储用例](item-cases.md)
- [OPML 导入用例](opml-cases.md)
- [功能与自动化覆盖映射](coverage.md)

## 运行

在 apps/subscriptions 下执行：

```bash
uv sync --locked
uv run pytest -q
uv run ruff check src tests migrations
```

默认使用临时 SQLite 并实际运行迁移，不读取根目录 .env。
PostgreSQL 仓储测试可通过 TEST_SUBSCRIPTIONS_DATABASE_URL 指向可销毁的专用测试库，数据库名必须以 test_ 开头。
该测试会重建表，禁止指向业务数据库。HTTP 和启动测试固定使用各自临时 SQLite，不能把 PostgreSQL 仓储验证说成 PostgreSQL HTTP 端到端验证。

## 覆盖边界

HTTP 测试使用进程内 ASGI，不是实际 TCP、反向代理或线上鉴权测试。
无真实 Feed、RSSHub、消息交付、调度或负载测试；规划用例不计入覆盖。
测试通过数量以实际执行结果为准，不在导航中固定承诺永久数量。
