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

## 代码质量（铁律）

### 前端 HTML 日报/月报
- 制作日报/月报 HTML 时，使用 Codex 原版结构（函数名 `create`、变量名 `revPts`/`prfPts`、变量缩写风格一致）
- 数据用 `const data = [...]` 内嵌数组，不用 JSON.parse
- 突破节点标注 8 个以内，每节点三行文字标注：
  - 第一行 `M/D  Rev X,XXX`（`colors.ink` 黑色）
  - 第二行 `毛利 X,XXX`（`colors.profit` 红色）
  - 第三行里程碑描述（`colors.amber` 黄色）
- 标注框高度 `lh = 58`，文字 Y 位置分别 +17、+34、+51
- 完成后验证括号配对（`{ vs }`、`( vs )`），确保 `render()` 被调用且无语法错误

### 通用
- 编辑前对 `oldString` 用 grep 确认只匹配唯一 1 处
- 绝不 commit 有语法错误的代码

## 文件管理
- 只保留最新版本一份文件，多余旧文件/副本一律删除
- 删除/搜索时扫描父目录，不能只搜当前工作目录

## Git 同步
- 本地文件变更后自动 commit，**默认不 push**
- 可以提醒用户 push，但未经用户明确允许，绝不 push（含 force push）

## 信息展示
- 对用户说的内容必须严谨，未经数据库确认的数据不做假设

## 数据核实（教训）
- 以数据库实际查询结果为准，即使与用户观点冲突，也要坚持事实
- 用户提出质疑时，先查库验证，用数据说话；数据支持用户观点就承认，不支持就如实说明
- 严禁"顺着用户的意思找理由"——不要因为用户坚持就动摇，更不要编造论证去迎合
- 快照表（snapshot_8/snapshot_6）与主表采集时间不同，数据差异属正常，先核实再下结论
- 引用证据时给出具体字段（id、mid、src、revenue、snapshot_at 等），便于用户复核

## 自动推送
- 使用 GitHub Actions + 飞书 Webhook 方案
- 脚本中未知 pub 应主动检测并飞书提醒用户补充
- Secrets 配好即生效，用户手动更新 Secret 即可扩展
