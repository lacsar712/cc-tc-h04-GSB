# 隧道收敛测缝台

测量员登记里程桩号与收敛毫米值。接口进程内后台线程认领待判行（不另起 worker 容器），按绝对值是否不超过 3.0 mm 给出合格或超限。页面是 Svelte。

## 技术栈

- 后端：Flask、Gunicorn、SQLAlchemy、进程内认领线程
- 前端：Svelte、Vite、nginx 反代 `/api`
- 数据库：PostgreSQL 16

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3201 |
| 接口 | http://localhost:8201 |
| PostgreSQL | localhost:54401（库名 `tunnelconv`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| surveyor | surv123456 | 可提交 |
| inspector | insp123456 | 只读（巡检员） |
| supervisor | supv123456 | 只读（监理） |

巡检员、监理均只能查看，不能报送测缝单。

## 排序与编号口径

- 落库顺序即自增 `id`，新单调取最大 `id`。
- 总表 `GET /api/logs` 固定按 `id` 倒序：最新一单在最上。
- 按断面取最新 `GET /api/chainages/<桩号>/latest` 同样取该断面最大 `id` 的一单；
  该断面一单都没有时返回 `404`，不编造编号。
- 三处（落库、总表、按断面取最新）共用同一口径，不得各自再排一次。

## 启动

```bash
cd projects/21-tunnel-convergence-desk
docker compose up --build
```

健康检查：`GET http://localhost:8201/api/health`

## 种子

| 桩号 | 收敛 | 结论 |
|------|------|------|
| K12+180 | 1.2 mm | 合格 |
| K18+040 | 5.6 mm | 超限 |
