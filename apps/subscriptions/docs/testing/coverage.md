# 功能—实现—自动化映射

函数名对应当前源码，可在链接文件内查找。参数化测试的多个输入不等于多个业务功能。

| 功能/用例 | 实现流程 | 测试文件与函数 |
| --- | --- | --- |
| SUB-001 / 001-01 | [创建](../implementation/sequences/create-source.md) | [API](../../tests/test_api.py)：test_create_detail_patch_disable_enable_persist_across_requests |
| SUB-001 / 001-02 | 创建冲突 | [API](../../tests/test_api.py)：test_duplicate_creation_returns_409_and_does_not_add_row |
| SUB-001 / 001-03 | 输入校验 | [API](../../tests/test_api.py)：test_create_rejects_invalid_fields_without_leaking_input |
| SUB-002 / 002-01 | [查询](../implementation/sequences/query-sources.md) | [API](../../tests/test_api.py)：test_list_filter_pagination_and_query_validation |
| SUB-002 / 002-02；004-03 | 不存在与非法 UUID | [API](../../tests/test_api.py)：test_missing_source_and_invalid_id_have_distinct_errors |
| SUB-003 / 003-01、02 | [修改](../implementation/sequences/update-source.md) | [API](../../tests/test_api.py)：test_failed_address_change_rolls_back_name_change |
| SUB-003 / 003-03；004-02 | 旧客户端版本 | [API](../../tests/test_api.py)：test_stale_version_returns_conflict_without_changing_data |
| SUB-003 / 003-04 | PATCH 校验 | [API](../../tests/test_api.py)：test_patch_rejects_ambiguous_or_unknown_fields |
| SUB-003 / 003-05 | 幂等修改 | [API](../../tests/test_api.py)：test_noop_patch_does_not_change_configuration_version |
| SUB-004 / 004-01 | [启停](../implementation/sequences/toggle-source.md) | [API](../../tests/test_api.py)：test_create_detail_patch_disable_enable_persist_across_requests |
| SUB-006 / 006-01、02 | [条目与修订](../implementation/sequences/item-revisions.md) | [仓储](../../tests/test_persistence.py)：test_item_roundtrip_revisions_and_unchanged_observation；[领域](../../tests/test_domain.py)：test_observation_creates_revision_only_for_changed_metadata |
| SUB-006 / 006-03 | 拒绝过期/异属修订 | [领域](../../tests/test_domain.py)：test_stale_or_foreign_revision_cannot_mutate_item |
| SUB-006 / 006-04；SUB-007 / 007-01 | 身份范围与条目/历史读取 | [仓储](../../tests/test_persistence.py)：test_duplicate_item_and_foreign_key_are_not_confused、test_pagination_and_cross_source_identity_scope、test_item_roundtrip_revisions_and_unchanged_observation |
| SUB-006 / 006-05 | 竞争修订 | [仓储](../../tests/test_persistence.py)：test_conflicting_item_revision_rolls_back_entire_transaction |
| SUB-006 / 006-06 | 修订配对 | [仓储](../../tests/test_persistence.py)：test_new_revision_must_accompany_version_change、test_repository_rejects_detached_entities_and_revision_overwrite |
| SUB-008 / 008-01、02 | 检查点领域方法 | [领域](../../tests/test_domain.py)：test_old_address_checkpoint_rejected_but_rename_does_not_invalidate_request、test_naive_time_and_backwards_checkpoint_rejected |
| TC-DB-001 | 事务回滚 | [仓储](../../tests/test_persistence.py)：test_missing_commit_and_exception_rollback_all_changes、test_item_and_revision_rollback_together |
| TC-DB-002 | 外键与检查约束 | [仓储](../../tests/test_persistence.py)：test_duplicate_item_and_foreign_key_are_not_confused、test_database_constraints_reject_invalid_revision |
| TC-DB-003 | 仓储身份映射 | [仓储](../../tests/test_persistence.py)：test_repository_rejects_detached_entities_and_revision_overwrite |
| TC-DB-004 | 迁移与生命周期 | [迁移](../../tests/test_migration_cli.py)：test_migration_cli_uses_explicit_url_and_handles_percent_in_path；[启动](../../tests/test_bootstrap.py)：test_factory_uses_configured_database_and_persists_after_restart |
| SUB-005 / 005-01～12 | [OPML 导入](../implementation/sequences/opml-import.md) | [独立用例及函数映射](opml-cases.md)，包括真实导入、重复跳过、安全边界、并发和中断重试 |

## 明确的覆盖缺口

SUB-005 已覆盖本地 XML 与 SQLite HTTP 导入，未覆盖真实代理或数据库断网；SUB-006 未覆盖自动身份推导和采集编排；SUB-007 无应用/HTTP 覆盖；SUB-008 仅检查点领域方法有测试。
条目与修订列表的多页边界尚无专门断言；现有分页测试主要验证来源列表。
候选领域事件、Outbox、跨服务调用、RSSHub 和运行调度没有自动化覆盖。
更多底层断言见各测试文件，以上是业务追踪入口，不以表格行数统计覆盖率。
