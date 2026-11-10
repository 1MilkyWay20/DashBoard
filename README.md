# 外卖门店销售数据看板

多品牌连锁门店的销售数据可视化系统。用户登录后按品牌查看 KPI、趋势与排行；管理员负责创建账号并分配可见品牌。

本地可用 `backend/seed_demo.py` 生成近 30 天演示数据（SQLite），无需连接真实业务库即可跑通。演示品牌 / 门店 / 商品名已脱敏为「品牌1」「门店1」「商品1」等占位。

## 设计要点

- **前后端分离**：Vue 3 + FastAPI；生产由 Nginx 托管前端静态资源，`/api` 反代到 uvicorn
- **双库隔离**：业务库只读；用户、品牌授权、门店配置、登录日志落独立程序库
- **品牌级权限**：每个看板接口经 `authorize_brand()` 校验；前端隐藏菜单不能代替后端授权
- **配置驱动多品牌**：表名与中文列名映射集中在 `backend/app/config.py`，查询层使用逻辑列名，不写死具体品牌表
- **指标口径**：销售额、订单、收入、佣金、商补、客单价、实收率等；比率类指标在聚合之后计算
- **筛选**：日期、平台、门店机构树；程序库中停用的门店不会出现在筛选树中
- **扩展**：可选 AI 问答（仅白名单聚合工具，不向模型暴露 SQL / 订单明细）；可选本机 Playwright 任务 worker

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Vue Router、Pinia、Element Plus、ECharts |
| 后端 | FastAPI、SQLAlchemy 2、PyJWT、bcrypt、PyMySQL |
| 数据 | MySQL（生产）/ SQLite（本地演示） |
| 部署 | Nginx + uvicorn |

## 本地启动

依赖：Python 3、Node.js。

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

演示环境保持 SQLite：

```env
DATABASE_URL=sqlite:///./demo.db
APP_DB_URL=sqlite:///./app.db
JWT_SECRET=change-me-in-production
```

```bash
.venv/bin/python seed_demo.py
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- 健康检查：http://127.0.0.1:8000/api/health
- 程序库无用户时自动创建管理员：`admin` / `admin123`（仅本地；生产请立即修改密码与 `JWT_SECRET`）

`seed_demo.py` 按 `config.BRANDS` 写入各品牌 account / order / product / exposure / info 等表，金额与订单量为脚本内随机生成。

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173 。开发服务器将 `/api` 代理到 `http://127.0.0.1:8000`。

## 功能

| 路径 | 说明 | 权限 |
| --- | --- | --- |
| `/login` | 登录 | 公开 |
| `/home` | 品牌入口 | 已登录 |
| `/dashboard/:brand` | 品牌看板 | 已登录且已授权该品牌 |
| `/dashboard/:brand/stores` | 门店启停与平台 ID | 管理员 |
| `/admin/users` | 用户管理 | 管理员 |
| `/admin/login-logs` | 登录记录（成功 / 失败） | 管理员 |

看板：日期 / 平台 / 门店筛选；KPI 与环比；按天趋势；平台对比；门店排行；三餐时段；商品 TOP；部分品牌另有活动、异常订单等模块。

## 目录

```
dataviz/
├── backend/                  # FastAPI（独立 .venv）
│   ├── app/                  # 路由薄，查询进 services/
│   ├── seed_demo.py          # SQLite 演示数据
│   └── .env.example
├── frontend/                 # Vue 3
├── qualification_worker/     # 可选：本机 Playwright worker
└── DataProcess 2/            # 可选：CSV / Excel → MySQL 导入
```

品牌与列映射见 `backend/app/config.py` 的 `BRANDS` / `COLUMNS`。

## 数据与权限约定

1. 网站对业务表只做 `SELECT`；生产建议使用只读账号。
2. 程序表（`users`、`user_brands`、`brand_stores`、`login_logs` 等）与业务表分库。
3. 品牌分表形如 `{brand}_account`、`{brand}_order`；SQL 使用逻辑列名。
4. 时间过滤为半开区间 `[start, end+1day)`，便于走复合索引。
5. AI（若开启）只调用已有看板聚合；筛选条件由请求锁定，密钥放在 `.env`。

## 配置

`backend/.env.example` → `.env`：

| 变量 | 含义 |
| --- | --- |
| `DATABASE_URL` | 业务库 |
| `APP_DB_URL` | 程序库 |
| `JWT_SECRET` | JWT 密钥 |
| `JWT_EXPIRE_HOURS` | Token 有效小时数 |
| `AI_ENABLED` / `AI_API_*` | 可选 AI |

真实 `.env`、业务原始文件、证件图片不要提交到仓库。

## 对接真实 MySQL（可选）

将 `DATABASE_URL` / `APP_DB_URL` 改为 MySQL 连接串，通过 `DataProcess 2/dataprocess` 按日区间先删后插导入。应用本身不写业务库。

## API 概览

除登录外需 `Authorization: Bearer <JWT>`。

- `POST /api/auth/login`、`GET /api/auth/me`
- `GET /api/meta/brands`、`/platforms`、`/stores`
- `GET /api/dashboard/*`（参数：`brand`、`start`、`end`、`platforms`、`store_ids`）
- `GET/POST/PUT/DELETE /api/admin/users`
- `GET /api/admin/login-logs`
- `GET/POST/PUT /api/stores`

## 可选：资质更换 Worker

`qualification_worker/` 为独立本机进程：前端提交任务后，worker 轮询领取，并用 Playwright 在商家后台填表；浏览器不在服务器上运行。本地演示看板不必启动该模块，配置见其 `.env.example`。
