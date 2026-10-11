# 简历研判 · AI简历匹配与评分工具

Flask页面和Python后端，SQLite存储，OpenAI Responses API生成结构化匹配报告。支持岗位100分标准、简历解析、多岗位评分、人工推进、招聘进度和招聘看板。

## 启动（Windows / Python 3.11）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

打开 [本地工作台](http://127.0.0.1:5055)。首次访问创建管理员，密码至少10位，没有预置正式账户。应用启动时自动执行Alembic迁移。首次初始化只在本机进行，创建管理员后再开放给其他设备。

若5055端口已占用：

```powershell
$env:PORT="5057"
.\.venv\Scripts\python.exe run.py
```

本次开发的实际预览端口使用5055，正式数据在instance目录。也可用CLI创建管理员：`.\.venv\Scripts\python.exe -m flask --app run create-admin`。

## 配置OpenAI

登录后进入“模型设置”，填写账户可用的模型名和API密钥，默认地址为`https://api.openai.com/v1`。模型须支持Responses API、Structured Outputs和流式响应。密钥在服务端加密保存，不返回前端。密钥留空保存会保留现有值。

也可复制`.env.example`为`.env`，填写OPENAI_API_KEY、OPENAI_MODEL。数据库设置优先于环境变量。项目不附带API密钥，自动测试不调用真实API。

接入依据：[OpenAI结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)、[OpenAI流式响应](https://developers.openai.com/api/docs/guides/streaming-responses)。系统校验报告结构、逐项分数和简历引用；完整校验前不显示最终分数。模型拒绝或不完整输出会标记失败。

## 图片与扫描PDF OCR

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

使用PaddleOCR CPU识别中文及英文。首次使用会下载识别模型，需要网络；缓存默认放在本项目instance/ocr-cache，下载完成后复用。文本PDF、DOCX不需要OCR。支持PNG、JPG/JPEG、PDF、DOCX，旧版DOC需先转换。默认单次上传总大小20MB、最多5份、PDF最多30页；超限不截断。复杂多栏/表格需在解析文本中人工检查修正。

本次已验证的完整依赖版本保存在requirements.lock.txt，可在新的虚拟环境用`python -m pip install -r requirements.lock.txt`复现（包含OCR及测试依赖）。Windows CPU运行已关闭不兼容的MKL-DNN优化；Paddle框架可能另在用户缓存目录初始化运行文件。

## 使用流程

首次成功设置管理员账号时，自动初始化Java开发、Golang开发、Agent开发、大模型算法研发、技术运营、前端开发、测试开发、人力资源专员八个岗位（命令行创建管理员同样生效）。管理员与岗位在同一事务保存，失败时整体回滚，可重试；已有同名岗位保留。打开设置页或普通登录不会重复导入。也可以手动运行脚本：

```powershell
.\.venv\Scripts\python.exe scripts/seed_jobs.py --dry-run
.\.venv\Scripts\python.exe scripts/seed_jobs.py
```

默认读取项目`.env`中的`DATA_DIR`，未配置则使用`instance`；可传`--data-dir 路径`指定其他数据目录。脚本自动完成数据库迁移，新增岗位状态为招聘中。重复执行跳过所有同名岗位（包括已关闭岗位），保留现有JD、评分项和版本；所有新增岗位在同一事务提交。不会启动后台任务或调用大模型/OCR。

`--dry-run`仅校验评分并显示新增/跳过计划，不写入岗位；应用初始化仍会在指定目录创建数据库、迁移表结构及本地密钥。岗位JD依据公开招聘信息改写，四个必须项80分、两个加分项20分，分值由本工具设计，导入后可调整。模板数据见`scripts/job_seed_data.py`，[JD来源与适配说明](scripts/岗位JD来源.md)记录参考链接。

1. 建立岗位，粘贴或上传JD，手动填写或AI生成评分草稿，检查后保存。必须项和加分项满分合计100。
2. 上传简历，等待解析，检查Markdown，AI提取或手动填写候选人资料；重复候选人可关联已有资料。
3. 选择一个或多个岗位，进入对应报告查看流式分析。
4. 硬性要求不满足展示编号缺口，未提供则单独待核实；均可人工推进。
5. 在候选人进度中更新面试阶段。可跳阶段、回退；历史纠正会作废所选事件及后续事件，并同步修正统计。
6. 首页按岗位与首次成功评估日期筛选，查看人数、漏斗、当前阶段与岗位概览。

同一候选人多岗位独立评分和推进。重新评估生成新报告，岗位标准与简历文本保留快照，不覆盖原招聘进度或推进依据。撤回推进后不显示在候选人列表；恢复推进复用原记录及进度。

删除前显示影响范围，候选人删除会涉及所有岗位；执行中的任务完成前不能删除关联对象。原文件通过后台清理任务删除，失败可在模型设置页重试。

## 测试与演示

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check app/static/js/app.js
```

测试使用临时SQLite和模拟OpenAI事件，覆盖评分校验、快照、多岗位、推进防重、阶段纠正、流式回放、解析、删除及配置加密。真实模型质量需要配置密钥后使用少量脱敏简历验证。

可选合成数据预览（独立数据库，不写入正式instance）：

```powershell
.\.venv\Scripts\python.exe scripts/preview.py
```

打开 [合成示例预览](http://127.0.0.1:5056)，账户`demo`，密码`Preview-only-2026`。页面有演示标记，报告与候选人均为合成数据；演示环境不运行后台任务，真实评估请使用正式应用。

## 数据、运行及备份

- instance/app.sqlite3保存数据，instance/uploads保存原文件；instance/settings.key用于解密后台保存的API密钥，必须和数据一起保留。
- 默认仅监听127.0.0.1，Waitress单进程16线程，后台同时执行2个模型任务、1个解析任务。不要开启多Web进程或Flask自动重载。
- 任务写入SQLite，关闭页面不取消；SSE断线自动重连、按事件ID回放。服务重启将未完成模型任务标记失败，人工重试避免重复计费；文件清理任务自动恢复。
- 外部部署时设置独立SECRET_KEY和SETTINGS_ENCRYPTION_KEY、HTTPS与SESSION_COOKIE_SECURE=true；反向代理关闭SSE缓冲。简历、密钥、数据库及备份不进入Git。
- 停止应用后执行`.\.venv\Scripts\python.exe scripts/backup.py`，备份在backups目录。恢复时将成套数据库、uploads、密钥放回数据目录，再启动应用；不要只恢复数据库。

首版采用自定义轻量CSS、原生JavaScript、CSS统计图表，以及Flask Session登录与统一CSRF校验，减少前端外部依赖。数据模型中的岗位评分项采用JSON保存，适合当前小规模；数据库升级使用Alembic版本迁移。多角色、自动邀约、消息通知、面试预约等不在首版范围内。
