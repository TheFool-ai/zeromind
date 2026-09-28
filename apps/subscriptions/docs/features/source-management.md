# 来源管理功能

状态：已实现。[API 契约](../implementation/api.md) · [测试用例](../testing/source-cases.md)

## SUB-001 手动创建

输入名称、Feed 地址及可选分类；默认启用。名称和分类去除首尾空白，分类去重。
来源地址规范化后唯一；同地址重复创建返回 409，不自动复用旧对象。
HTTP/HTTPS 和 rsshub 地址均可录入，但创建不测试可达性、不解析 Feed，也不立即抓取。
成功返回来源详情及 Location。失败不留下新来源。
时序见 [创建](../implementation/sequences/create-source.md)。

## SUB-002 查询来源

按 UUID 查询详情，不存在返回 404。列表可按 enabled 筛选，按 created_at、id 升序分页。
默认 limit=100、offset=0，limit 为 1～1000；返回当前页、limit、offset，不返回总数。
列表和详情不加载条目、不访问网络。空列表不是错误。
时序见 [查询](../implementation/sequences/query-sources.md)。

## SUB-003 修改配置

PATCH 可修改名称、分类、地址。未提供字段保留旧值，空分类数组表示清空；显式 null、未知字段和空修改被拒绝。
地址变化意味着同一来源迁移：来源 ID 和历史条目保留，检查点清空，地址版本与配置版本推进。
规范化后相同的值不推进版本。同时修改名称/分类和地址可能推进两次配置版本，不能把版本当请求次数。
地址冲突或其他字段失败时整笔更新回滚，不允许只保存名称。
可提供 expected_configuration_version 防止旧页面覆盖新配置；不提供时仍有仓储事务级乐观锁。
时序见 [修改与冲突](../implementation/sequences/update-source.md)。

## SUB-004 启用与关闭

启停通过独立接口修改 enabled，不删除来源、历史条目或检查点。
重复启用/关闭幂等；但显式提交的旧配置版本仍返回冲突。
启用不等于立即启动任务，关闭不等于取消在途任务；当前尚无采集与任务运行入口。
时序见 [启停](../implementation/sequences/toggle-source.md)。

## 不包含

没有删除、用户关注关系、租户隔离、批量启停或自动来源发现功能。
不要依据数据库中存在某个字段就推断已经存在对应 HTTP 功能。
