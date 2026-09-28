# OPML 导入测试用例

状态：已实现自动化。HTTP 集成使用真实临时 SQLite；解析器直接测试防止绕过 HTTP 限制。

| 编号 | 场景与操作 | 预期 | 自动化函数 |
| --- | --- | --- | --- |
| TC-SUB-005-01 | 嵌套文件夹、重复分类、中文标题、RSSHub 地址，连续导入两次 | 首次创建；第二次全部跳过，原记录不变 | test_import_maps_nested_categories_and_reimport_skips_existing |
| TC-SUB-005-02 | 已关闭来源，再导入相同地址和非法长名称 | 跳过，不覆盖名称/分类或重新启用 | test_existing_source_is_skipped_without_overwriting_or_reenabling |
| TC-SUB-005-03 | 文件内重复、非法地址、缺地址和普通网页混合 | 逐项报告，合法项提交；非 Feed 不计入总数 | test_file_duplicates_skip_and_invalid_entries_do_not_block_valid_ones |
| TC-SUB-005-04 | 首项名称非法，后项同地址合法 | 首项失败不阻挡后项创建 | test_invalid_first_occurrence_does_not_block_later_valid_same_address |
| TC-SUB-005-05 | 截断 XML、错误根、重复 body、非法结构、DTD/实体 | 422，整份无写入 | test_invalid_or_unsafe_document_is_rejected_before_any_write |
| TC-SUB-005-06 | outline 数量、XML 深度超限 | 整份拒绝，无前缀写入 | test_complexity_limits_reject_whole_document |
| TC-SUB-005-07 | 无 Content-Length 分块上传超 1 MiB | 413，无写入 | test_streamed_size_limit_is_enforced_without_content_length |
| TC-SUB-005-08 | 合法空目录、UTF-16 中文文件 | 零项结果或正确录入 | test_empty_valid_file_and_encoding_are_supported |
| TC-SUB-005-09 | 地址带凭据、上传 JSON | 错误不回显凭据；JSON 415 | test_errors_do_not_echo_credentials_and_non_xml_media_is_rejected |
| TC-SUB-005-10 | 第二项触发真实 SQLite 写入错误，解除后重试 | 503 保留首项并停止后续；重试跳过首项 | test_database_failure_reports_committed_progress_and_stops |
| TC-SUB-005-11 | 两请求均查无记录后并发插入同地址 | 一次创建、一次跳过，仅一条记录 | test_concurrent_import_unique_conflict_becomes_skip |
| TC-SUB-005-12 | 直接解析 1 MiB 边界、1000 文件夹、深度边界、海量 head 元素及 UTF-16 实体 | 边界内接受，越界/实体拒绝 | 解析器测试文件内各 test 函数 |

代码：[HTTP 集成测试](../../tests/test_opml_api.py)、[解析器测试](../../tests/test_opml_reader.py)。
OpenAPI 另外验证原始 XML 请求体契约。并发测试只同步真实 SELECT 的完成时间点，不模拟唯一约束。
未覆盖真实代理上传、客户端断线时序、生产数据库断网的提交不确定性或高并发负载。
