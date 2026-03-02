# Amazon 项目

本仓库已配置 GitHub Pages 自动部署工作流，发布目录为 `backend/app/web`。

## 本地运行后端

```bash
cd backend
python3 -m app.main
```

默认地址：`http://127.0.0.1:8000`

## GitHub Pages 发布（Quickstart 方式）

1. 推送 `main` 分支（包含 `.github/workflows/deploy-pages.yml`）。
2. 打开仓库 `Settings -> Pages`。
3. 在 `Build and deployment` 中选择 `Source: GitHub Actions`。
4. 等待 `Actions` 中 `Deploy GitHub Pages` 工作流成功。
5. 访问站点：`https://<github-username>.github.io/amazon/`。

## 前端 API 地址

Pages 只托管静态页面，后端 API 需要单独部署。

页面中新增了 `接口配置` 区域，可填写你的后端地址，例如：

`https://your-backend.example.com`

保存后会写入浏览器本地存储，并用于调用 `/api/*` 接口和导出链接。
