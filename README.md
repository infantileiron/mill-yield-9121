# 青禾 · 磨坊出粉率分布复核

为青禾制粉厂的 3 条生产线提供原粮批次、检验记录、分布诊断和复核签核，质量分析员每天把原粮检验变成可追溯的交班结论。

## 真实业务场景

青禾质量组原来把供应商批次写进 `原粮到货-1115.xlsx`，检验员录入不同工作簿，分析员手算四分位数，负责人在群里确认。问题是样本与批次容易错位、计算口径随人员变化、签核意见无法回到当时的数据。本项目承接原粮入厂检验，输出带冻结样本和 SHA-256 的复核 CSV，供产线负责人安排复测。

- 批次台账：供应商、产线、吨数、日期、样本数，唯一业务编号。
- 检验录入：出粉率、水分、检验员，范围校验和重复编号阻断。
- 分布诊断：按产线冻结快照，Redis 排队由独立 Python worker 计算，显示完整样本直方图、分位数、IQR 异常点和分组均值。
- 复核报告：负责人签核意见，分析员与观察员可下载含原始样本的 CSV。
- 月度归档：按原粮到货月份把检验样本从在线区迁入归档区；归档前逐批核对样本数与逐行内容校验，损坏或缺失的归档阻止诊断并指出月份。跨月诊断、报告与 CSV 仍可读取归档样本。
- JWT 三角色、写操作审计、每分钟请求限流、可恢复的错误提示。

## 账号与权限

密码均为 `Demo123!`。

| 角色 | 账号 | 权限 | 典型动作 |
|---|---|---|---|
| admin | admin@demo.local | 全部业务读写与签核、审计读取 | 核对异常点并签核 |
| analyst | analyst@demo.local | 录入、提交计算、读取和导出；不可签核 | 新增样本并发起复核 |
| viewer | viewer@demo.local | 只读与导出；后端拒绝业务写入与任务提交 | 下载交班报告 |

## 快速启动

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

访问 [前端](http://localhost:18200)、[后端 API 文档](http://localhost:19200/docs)。PostgreSQL 映射端口 17700；Redis 不暴露宿主端口。网络固定为 `10.253.101.0/24`，可通过 `NETWORK_SUBNET` 修改以避开本机大量 Compose 栈的默认网段池限制。

```sh
docker compose down -v --remove-orphans
```

此命令会清除此项目演示数据。普通重启使用 `docker compose stop` / `docker compose start` 保留命名卷。

## 技术与环境变量

| 部分 | 技术 |
|---|---|
| 前端 | 原生 ES modules / HTML / CSS，Nginx 1.27 |
| API | Python 3.11、FastAPI 0.115.6、SQLAlchemy 2.0.36 |
| 数据库 | PostgreSQL 16 |
| 队列 | Redis 7、独立 Python worker 与心跳健康检查 |
| 认证 | PyJWT 2.10.1、PBKDF2-SHA256 密码哈希 |

`.env.example` 包含项目名、三个端口、数据库密码、JWT 密钥、演示 seed 开关、网络网段。演示密码和 JWT 密钥仅用于本地可复现运行，部署时自行替换。命名卷分别保存数据库、Redis AOF 和 worker 结果文件。恰好五个服务均配置健康检查，worker 等待 API seed 完成。

## 数据与计算口径

固定随机种子 `3101` 生成 40 批原粮、每批 15 条检验，共 600 条样本。首批是 `QH-1115-A`，检验员林洁。`seed_demo` 按批次和样本自然键检查后插入；重复执行不增加行数，也不覆盖已有用户数据。启动 `SEED_DEMO=true` 自动 seed，失败记录日志不阻塞进程。

出粉率范围 `(0,100]`，水分 `[0,30]`，NaN 与 Infinity 被拒绝。数据均为模拟数值，没有外部生产数据依赖。复核按提交时快照计算，后续录入不会改变既有报告。

- 至少 5 个有效样本，否则返回 422，不提交任务。
- 将出粉率排序，对 `p=0.25/0.5/0.75` 使用位置 `(n−1)p` 的相邻值线性插值得到 Q1、中位数、Q3。
- `IQR=Q3−Q1`，异常点为严格小于 `Q1−1.5×IQR` 或严格大于 `Q3+1.5×IQR` 的记录。边界上的点保留为非异常。常量样本 IQR=0，等于常量的样本不标异常。
- 标准差使用样本标准差 `n−1`。直方图区间固定为 0–100、步长 5 个百分点，最后一桶包含 100；展示区域自动覆盖全部非空桶并留一个相邻空桶，完整 0–100 桶计数保存在 API 结果中。
- 分组按原粮产线计算 n、均值、最小、最大。异常点不从总体统计中移除。
- 结果带样本快照 SHA-256，同一冻结输入可复现。统计异常只是核对线索，不自动判废。

后台 worker 从 Redis 消费复核 id，更新 queued→running→completed/failed，写结果至共享 artifacts 卷。重启时会扫描未完成任务并重新排队。负责人仅能签核 completed 状态，签核后不可重复签核。CSV 导出包含状态、口径值、签核意见和所有冻结样本。

### 月度归档与恢复

- 归档粒度是「到货月份」，迁移单元是「批次」。每批在单个事务内完成：写入归档表 → 逐行比对内容校验（含样本数）→ 通过后才按 id 删除在线行。任一步失败整批回滚，状态记为 `failed`，不会留下半批数据。
- 状态流转：`online → pending（待迁移）→ migrating → ready（可检索）`；恢复为 `ready → restoring → restored`。中断后 worker 启动时自动重新排队，也可在页面点击「续跑归档」；归档行按 `sample_code` 唯一，重试不重复写入。
- 诊断与查询通过一条 UNION ALL 查询读取「在线 ∪ 归档」，按 `sample_code` 去重，同一份样本只计一次；迁移期间新增的检验仍在在线区，下一次归档会被继续迁入，不会漏算。每次提交复核在同一查询内取完整快照，旧报告快照保持原样。
- `archives.checksum` 保存整月归档的逐行校验和汇总。`/archives/{month}` 与 `verify` 会重算逐行内容；样本数不符、内容变化、整月校验和不一致都判为 `corrupt`。诊断提交前会校验参与月份（含「全部」），发现损坏直接 409 并指出月份，绝不静默少算；损坏月份同样阻止继续归档与恢复。
- 归档样本编号仍占用全局唯一键：向已归档月份重复录入同一编号会返回 409，并提示先恢复该月，避免在线与归档出现同名样本。

| 方法与路径 | 作用 | 权限 |
|---|---|---|
| `GET /archives` | 月份一览：在线/归档样本数、进度、状态 | 登录用户 |
| `GET /archives/{month}` | 逐批核对明细与实时校验结果 | 登录用户 |
| `POST /archives` | 发起该月归档（`{"month":"2026-11"}`） | admin / analyst |
| `POST /archives/{month}/restore` | 把该月归档样本恢复到在线区 | admin / analyst |
| `POST /archives/{month}/verify` | 重算内容校验，不改变数据 | 登录用户 |

## 一天的工作剧本

1. 08:50 观察员登录查看 `QH-1115-A`，核对 15 个已有样本。
2. 09:00 分析员登记 `QH-1115-NEW`，供应商丰垦粮业，到货 28 吨。
3. 09:10 检验员林洁新增 `QH-1115-A-S16`，出粉率 73.20%、水分 12.80%。
4. 09:20 录入重复编号应报冲突；出粉率 101% 被范围校验拒绝。
5. 09:30 在分布诊断中选择一线并建立「11月15日产线出粉率复核」。
6. 09:40 独立 worker 完成计算，分析员核对 IQR 边界和异常样本。
7. 10:00 负责人切换 admin，记录复测安排并签核。
8. 10:20 观察员下载 `mill-yield-review-<id>.csv`，交给产线班长。
9. 11:00 交班前在「月度归档」把 10 月样本归档，逐批核对样本数与校验和；随后跨月诊断仍能读到 10 月样本，合计与归档前一致。

## 目录与本地开发

`backend/src` 按 routes/controllers/services/models/schemas/middlewares/utils/constants/config 分职责；`backend/scripts` 是幂等 seed；`backend/migrations` 记录初始 schema 约定，实际表结构由 SQLAlchemy `create_all` 应用。`frontend/src` 按 api/stores/types/components/common/hooks/pages/router/utils/constants 分模块。

本地 Python 开发：安装 `backend/requirements.txt`，配置 `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET`，在 backend 目录执行 `uvicorn src.main:app --reload` 与 `python -m src.worker`。静态前端通过 Nginx `/api/` 代理后端无前缀路由，不需要 Node 构建。

共享枚举：`backend/src/constants/enums.py` 与 `frontend/src/constants/enums.js` 中分别定义角色 Role、复核状态 ReviewStatus、产线 LINES；UI 角色标签、后端鉴权及状态迁移遵守这些值。

## 范围与已知差异

小型项目仅支持逐条录入，不提供 Excel 导入和外部检验仪器同步。原始检验记录采用追加留痕模式，没有删除/覆盖接口；错误记录须重新录入并在复核意见说明。签核是本地数据库留痕，不是电子签章。图形自动覆盖全部实际样本区间，完整 0–100 桶和所有样本在 API / CSV 中保留。演示时区在报告中显式标记 UTC。前端 Google Fonts 离线时回退宋体。

测试脚本、1440×900 页面截图与实测证据在源码外的 `test-artifacts/gb-3101/`。License：MIT。
