# Amazon 项目

本仓库使用 GitHub Pages 展示 Amazon 榜单静态日数据（不依赖线上后端 API）。

## 站点地址

`https://mapleyuan.github.io/amazon/`

## 页面结构（已拆分）

- `backend/app/web/index.html`：排行榜页（筛选、对比昨日、趋势弹窗、CSV 导出）
- `backend/app/web/insights.html`：竞品洞察页（评论/关键词/月销量/款式趋势 + 导出）
- `backend/app/web/product.html`：单品分析页（URL 支持直达 ASIN，自动聚焦单品）
- `backend/app/web/app.js`：共享数据加载与筛选逻辑，按 `body[data-page]` 自动适配页面

## GitHub Pages 部署

1. 确保仓库 `Settings -> Pages -> Source` 选择 `GitHub Actions`。
2. `main` 分支变更 `backend/app/web/**` 后会触发 `.github/workflows/deploy-pages.yml`。
3. 工作流成功后，最新静态页面自动发布。

## 每日自动更新数据

工作流：`.github/workflows/daily-static-data.yml`

1. 每天 UTC `02:20` 定时执行抓取与静态数据生成。
2. 工作流默认设置 `AMAZON_CRAWL_CATEGORY_LIMIT=5`，控制每个站点/榜单抓取的类目数量，避免任务超时。
3. 生成文件：
   - `backend/app/web/data/manifest.json`
   - `backend/app/web/data/daily/YYYY-MM-DD.json`
4. 当前配置为长期保留历史（`retention_days=0`）。
5. 若当天抓取失败，保留最近一次成功数据并在 `manifest` 中标记 `status=stale`。

## 洞察数据（真实报表优先，免费评论兜底）

前端“竞品洞察”模块会优先读取：

- `backend/app/web/data/insights/YYYY-MM-DD.json`

该文件可由脚本生成：

```bash
cd backend
python3 scripts/refresh_official_insights.py --snapshot-date 2026-03-03
```

若没有官方报表文件，工作流会自动尝试“免费公开评论抓取”生成评论痛点洞察；其余维度回退到估算模式。

默认会尝试获取：

1. 竞品评论好评/差评痛点：Customer Feedback API（review topics）
2. 关键词流量与转化：Search Query Performance 报表
3. 各月销量：Sales and Traffic 报表（月粒度 + ASIN 粒度）
4. 款式趋势：优先官方 style 报表，缺失时基于官方关键词自动聚合

无付费 API 的默认兜底脚本：

```bash
cd backend
python3 scripts/refresh_public_review_insights.py --snapshot-date 2026-03-03 --site amazon.com
```

该脚本会读取当日 `daily` 数据中的 Top ASIN，抓取公开评论页并归纳正负向主题词，写入：

- `backend/app/web/data/insights/YYYY-MM-DD.json`（`source=public_reviews`）
- 包含更多评论字段：`avg_rating`、`rating_distribution`、`sentiment`、`positive_snippets`、`negative_snippets`

另外，免费关键词流量/转化近似可用：

```bash
cd backend
python3 scripts/refresh_public_keyword_insights.py --snapshot-date 2026-03-03 --site amazon.com
```

该脚本会基于当日商品标题自动生成候选词，抓取公开搜索结果页并写入关键词洞察（`source` 会带上 `public_search_keywords`）。

前端“竞品洞察”支持：

- 分析范围切换：`当前筛选竞品` / `单个竞品(ASIN)`
- 评论深度图表：评分结构、情感分布、评论摘录
- 月销量/款式趋势明细导出 CSV

## 本地手动兜底更新

当自动抓取失败时，可在本地手动执行并 push：

```bash
cd backend
python3 scripts/publish_static_data.py --source manual
cd ..
git add backend/app/web/data
git commit -m "chore(data): manual refresh static data"
git push origin main
```

只跑部分站点/榜单（快速模式）：

```bash
cd backend
AMAZON_CRAWL_CATEGORY_LIMIT=3 python3 scripts/publish_static_data.py --source manual --sites amazon.com --boards best_sellers
```

> 如需快速验证页面，可临时用 mock 数据：
>
> `AMAZON_MOCK_CRAWL=1 python3 scripts/publish_static_data.py --source manual`
