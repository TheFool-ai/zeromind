# 条目与获取能力

状态：部分实现。[领域模型](../domain/model.md) · [测试用例](../testing/item-cases.md)

## SUB-006 条目发现与修订

已实现 discover、observe 领域方法和条目仓储。
新条目从修订 1 开始，条目和首个修订必须同事务保存。
同来源、同类型、同身份只允许一个条目；不同来源可有相同身份。
观察时必须提供条目当前修订，不能使用其他条目或过期版本。
元数据规范化后相同，只推进 last_seen_at；内容改变才新增连续修订，历史不可覆盖。
摘要、标题、作者、原文链接和来源时间属于 Feed 元数据，不包含正文抓取或 AI 结果。

未实现：从 Feed 自动选择 GUID/URL/hash 的身份推导策略、Feed 解析、批量采集编排。
当前调用者必须显式构造 ItemIdentity，不能声称已有自动采集去重服务。
时序见 [条目与修订](../implementation/sequences/item-revisions.md)。

## SUB-007 条目和历史查询

仓储支持按来源分页列条目、按 ID 或身份查询、按修订号读取及分页列历史。
条目列表按 first_seen_at、id 升序；历史按 revision_number 升序。
仓储不存在结果为 None 或空元组，尚未定义面向客户端的错误、DTO 或 HTTP 路由。

## SUB-008 获取来源数据

已实现 record_fetch_success：成功检查点更新，不改变配置版本、启停状态或配置更新时间。
可通过 expected_address_version 拒绝旧地址请求的结果；改名不改变地址版本。
只提供聚合方法并不保证未来网络流程已正确调用该检查，应用层接入仍需实现。
304 时调用者需要保留已有条件请求头；失败不能伪造成功检查点。
网络安全、超时、条目接收事务边界及在途关闭规则尚待设计，见 [规划时序](../implementation/sequences/planned-flows.md)。
