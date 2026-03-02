# GitHub Pages Static Daily Data Design

## Background

目标是将当前项目改为纯 GitHub Pages 静态展示模式：
- 不依赖线上后端 API
- 每天自动更新结果
- 页面支持访问与筛选
- 自动失败时保留最近一次成功数据
- 本地可手动兜底生成并推送

## Confirmed Requirements

1. 数据更新通道同时支持：
- GitHub Actions 定时自动更新
- 本地手动更新后 push 兜底

2. 页面数据保留策略：
- 默认保留最近 30 天

3. 自动失败策略：
- 保留最近一次成功数据
- 页面可看到最后成功更新时间

4. 部署模式：
- 继续使用 GitHub Pages（GitHub Actions Source）
- 不部署线上后端服务

## Architecture

采用“离线抓取 + 静态数据分片 + 前端本地筛选”架构：

1. 数据生成层（Python）
- 在仓库中新增静态数据发布脚本
- 每次运行抓取当日数据并产出标准 JSON
- 维护 manifest 元数据和 30 天保留窗口

2. 数据存储层（Git 仓库）
- `backend/app/web/data/manifest.json`
- `backend/app/web/data/daily/YYYY-MM-DD.json`
- 所有历史版本通过 Git 保留，可追溯

3. 展示层（GitHub Pages 前端）
- 前端加载 manifest + 选定日期日文件
- 全部筛选在浏览器内存完成
- 不再请求 `/api/*`

4. 调度层（GitHub Actions）
- 每日 cron 执行数据发布脚本
- 变更数据文件后自动 commit/push
- 触发现有 Pages 部署工作流

## Data Design

### manifest.json

```json
{
  "generated_at": "2026-03-02T13:00:00Z",
  "last_success_date": "2026-03-02",
  "last_success_at": "2026-03-02T13:00:00Z",
  "last_attempt_at": "2026-03-02T13:00:00Z",
  "status": "success",
  "message": "",
  "retention_days": 30,
  "available_dates": ["2026-03-02", "2026-03-01"],
  "default_filters": {
    "site": "amazon.com",
    "board_type": "best_sellers",
    "has_price": "1",
    "top_n": 100,
    "sort_by": "rank",
    "sort_order": "asc"
  }
}
```

### daily/YYYY-MM-DD.json

```json
{
  "snapshot_date": "2026-03-02",
  "generated_at": "2026-03-02T13:00:00Z",
  "stats": {
    "total_items": 1234,
    "sites": 3,
    "boards": 3,
    "categories": 45
  },
  "categories": [
    {
      "site": "amazon.com",
      "board_type": "best_sellers",
      "category_key": "cat-xxxx",
      "category_name": "Electronics",
      "item_count": 100
    }
  ],
  "items": [
    {
      "snapshot_date": "2026-03-02",
      "site": "amazon.com",
      "board_type": "best_sellers",
      "category_key": "cat-xxxx",
      "category_name": "Electronics",
      "rank": 1,
      "asin": "B000000001",
      "title": "Product",
      "brand": "Brand",
      "price_text": "$9.99",
      "rating": 4.5,
      "review_count": 120,
      "detail_url": "https://www.amazon.com/dp/B000000001"
    }
  ]
}
```

## Update Flows

### Auto Daily Flow (GitHub Actions)

1. 定时触发工作流
2. 执行静态数据发布脚本
3. 成功时写入当日日文件、更新 manifest、清理 30 天外旧文件
4. 提交并 push 数据文件变更
5. 触发 Pages 部署工作流发布

### Local Manual Fallback Flow

1. 本地运行同一发布脚本
2. 生成/更新 data 文件
3. 手动 git add/commit/push
4. 触发 Pages 部署发布

## Failure Handling

1. 当次抓取失败时：
- 不覆盖已存在日文件
- manifest 保留 `last_success_date`
- manifest 记录 `status=stale`、`last_attempt_at`、`message`

2. 前端在 `status=stale` 时显示提示：
- 使用最近一次成功数据
- 显示最后成功更新时间

## Frontend Behavior

1. 初始加载：
- 读取 `data/manifest.json`
- 默认加载 `last_success_date` 对应日文件

2. 筛选项保留：
- site
- board_type
- category_key
- has_price
- top_n
- sort_by
- sort_order
- keyword

3. 导出：
- 前端导出 CSV
- 不再依赖后端导出接口

## Acceptance Criteria

1. 每日自动成功后，仓库新增/更新当日日文件
2. Pages 可直接展示并筛选，无需 API Base
3. 自动失败时页面仍可显示最近成功数据
4. 本地手动运行脚本后 push，Pages 数据同步更新
5. 连续运行后仅保留最近 30 天文件

## Risks and Mitigations

1. Amazon 反爬导致自动失败
- 通过 stale 策略保证展示可用
- 通过本地手动通道兜底

2. 数据体积增长
- 按天分片 + 30 天保留
- 后续如需可再按 site/board 二级分片

3. Workflow 提交冲突
- 仅提交 `backend/app/web/data/**`
- 冲突时 rebase 重试
