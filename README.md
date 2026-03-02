# Amazon 项目

本仓库使用 GitHub Pages 展示 Amazon 榜单静态日数据（不依赖线上后端 API）。

## 站点地址

`https://mapleyuan.github.io/amazon/`

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
4. 自动保留最近 30 天数据。
5. 若当天抓取失败，保留最近一次成功数据并在 `manifest` 中标记 `status=stale`。

## 本地手动兜底更新

当自动抓取失败时，可在本地手动执行并 push：

```bash
cd backend
python3 scripts/publish_static_data.py
cd ..
git add backend/app/web/data
git commit -m "chore(data): manual refresh static data"
git push origin main
```

只跑部分站点/榜单（快速模式）：

```bash
cd backend
AMAZON_CRAWL_CATEGORY_LIMIT=3 python3 scripts/publish_static_data.py --sites amazon.com --boards best_sellers
```

> 如需快速验证页面，可临时用 mock 数据：
>
> `AMAZON_MOCK_CRAWL=1 python3 scripts/publish_static_data.py`
