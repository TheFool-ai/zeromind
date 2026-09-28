# 旧项目归档与恢复

## 归档位置

- 分支：`archive/pre-rebuild`
- 标签：`pre-rebuild-2026-09-28`
- 快照提交：`8f8976384b471b349a7ea236f82c1c5b81a51cb6`
- 重构分支：`codex/rebuild`

快照包含旧 information 后端、web 前端、agent-runtime、knowledge 预留目录、Compose、环境变量示例、历史设计文档，以及当时创建的订阅服务骨架。

归档分支和标签目前仅在本地创建，尚未推送。Git 归档可恢复旧文件，但不能代替数据库备份。

## 查阅旧代码

无需切换分支即可读取归档文件，例如：

```bash
git show archive/pre-rebuild:README.md
git show archive/pre-rebuild:apps/information/src/zeromind/subscriptions/domain/aggregates/subscription.py
git ls-tree -r --name-only archive/pre-rebuild
```

需要独立查阅或运行旧版本时，可在新的空路径建立 worktree：

```bash
git worktree add --detach ../zeromind-legacy pre-rebuild-2026-09-28
```

旧版本启动仍需自行配置环境文件及数据连接；不得未经检查连接现有生产数据库。

## 本地状态

`.env`、`.env.save` 和已有 `.worktrees/` 保留原位，不加入快照。没有操作 Docker 容器、镜像、数据卷或外部数据库，也没有执行数据库迁移。

重构分支移除了旧应用和旧部署文件，不再支持旧 README 中的启动命令。需要旧命令时请查阅归档版本。
