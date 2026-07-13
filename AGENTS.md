# AGENTS.md - 全局规则

## 用户偏好
- 沟通语言：中文
- 需要用户操作时，给出明确步骤和 URL 路径
- 主动推进但重大操作前需确认

## 环境信息
- Git 路径：`D:\AGW\OpenCode\git\bin\git.exe`
- GitHub 账号：`hezhe888`
- 主仓库：`hezhe888/AXzong`（单一仓库模式，所有子项目放目录下，不拆独立仓库）
- 运行 Python 用 `py` 命令

## 安全红线（全局）
- 数据库连接信息（IP、端口、用户、密码、库名）禁止写入文件，只通过环境变量/GitHub Secrets 传递
- pub name 禁止明文出现在 GitHub 仓库中，通过本地文件 `pub_mapping.json`（已 gitignore）存储，CI 环境通过 Secret `PUB_MAPPING` 注入
- adv name 禁止明文出现在 GitHub 仓库中，通过本地文件 `adv_mapping.json`（已 gitignore）存储，CI 环境通过 Secret `ADV_MAPPING` 注入
- 飞书 Webhook 可以明文写在 workflow 中
- 发现代码中有任何敏感信息立即清理并 force push 覆盖历史

## 数据查询
- 数据以数据库实际查询结果为准，不推算、不猜测、不臆断
- 缺失 pub name 时主动询问用户补充名称，更新 `pub_mapping.json`（本地）/ `PUB_MAPPING` Secret（CI）
- 缺失 adv name 时主动询问用户补充名称，更新 `adv_mapping.json`（本地）/ `ADV_MAPPING` Secret（CI）
- JK 频道通过 `pub_mapping.json` / `PUB_MAPPING` 中 pub name 包含 "jk" 自动识别（规则匹配，不硬编码 mid 列表）
- 前端页面自动检测未知 Pub ID 和 Adv ID，在页面顶部显示黄色告警条，提示用户补充

## 映射表管理
- Pub 名称映射：`pub_mapping.json`（格式：`{"mid":"pub_name", ...}`），后端 API `/api/pubnames` 提供服务
- Adv 名称映射：`adv_mapping.json`（格式：`{"src":"adv_name", ...}`），后端 API `/api/advnames` 提供服务
- 两个映射文件均已 gitignore，仅本地开发使用；生产环境通过环境变量注入
- 新增未知 ID 时，Agent 应主动向用户询问名称并更新映射文件

## 文件管理
- 只保留最新版本一份文件，多余旧文件/副本一律删除
- 删除/搜索时扫描父目录，不能只搜当前工作目录

## Git 同步
- 本地文件变更后自动 commit + push，不做手动留给用户单独操作

## 信息展示
- 对用户说的内容必须严谨，未经数据库确认的数据不做假设

## 自动推送
- 使用 GitHub Actions + 飞书 Webhook 方案
- 脚本中未知 pub 应主动检测并飞书提醒用户补充
- Secrets 配好即生效，用户手动更新 Secret 即可扩展
