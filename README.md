# ⚡ LLM & 多模态模型定价对比 Dashboard

> 跟踪全球主流大语言模型与多模态生成模型的 API 定价，每周自动更新。

## 功能特性

- **99 个模型** 覆盖 20 家厂商（OpenAI、Anthropic、Google、DeepSeek、Mistral、通义千问、智谱等）
- **5 种模型类型**：文本 LLM、多模态、图片生成、视频生成、语音/音频
- **价格对比图表**：直观展示各模型输入/输出价格（$/Mtok）
- **多维筛选**：按类型、厂商筛选，关键词搜索，价格/名称/上下文排序
- **明暗主题**切换，响应式设计支持移动端
- **GitHub Actions** 每周一自动抓取最新定价并提交

## 快速开始

### 本地预览

由于 Dashboard 通过 `fetch` 加载 JSON 数据，需要通过 HTTP 服务器访问（不能直接双击打开 HTML 文件）：

```bash
# 方式一：Python 内置服务器
python3 -m http.server 8099

# 方式二：Node.js
npx serve

# 然后浏览器打开 http://localhost:8099
```

### 部署到 GitHub Pages

1. 将本项目推送到 GitHub 仓库
2. 进入仓库 **Settings → Pages**
3. Source 选择 **GitHub Actions** 或 **Deploy from branch (main)**
4. 等待部署完成，访问 `https://<用户名>.github.io/<仓库名>/`

## 项目结构

```
.
├── index.html                      # Dashboard 主页面（纯静态）
├── data/
│   ├── pricing.json                # 规范化定价数据（Dashboard 数据源）
│   └── update_summary.txt          # 最近一次更新的变更摘要
├── scripts/
│   ├── normalize_data.py           # 数据规范化脚本（原始 → pricing.json）
│   └── update_pricing.py           # 定价自动抓取更新脚本
├── llm_pricing_data.json           # 原始调研数据（手动维护的基准）
├── .github/workflows/
│   └── weekly-update.yml           # GitHub Actions 每周自动更新
└── README.md
```

## 数据说明

### 价格单位

| 模型类型 | 价格单位 | 说明 |
|---------|---------|------|
| 文本 / 多模态 | $/Mtok（美元/百万 token） | 分输入价格和输出价格 |
| 图片生成 | $/image（美元/张） | 按画质档位（标准/高清/超清）区分 |
| 视频生成 | $/sec（美元/秒） | 按分辨率（720p/1080p/4K）区分 |
| 语音/音频 | $/1K chars 或 $/min | 文本转语音按字符，音乐生成按分钟 |

### 中国厂商汇率

中国厂商（通义千问、文心一言、智谱、月之暗面）原始定价为人民币，按 **1 USD ≈ 7.2 CNY** 换算为美元。原始价格保留在 `price_original` 字段中。

### 数据来源

所有价格来自各厂商官方定价页，完整来源列表见 [data/pricing.json](data/pricing.json) 的 `_meta.sources` 字段及 Dashboard 页脚。

## 自动更新机制

### GitHub Actions 工作流

项目配置了 `.github/workflows/weekly-update.yml`，每周一 UTC 02:00（北京时间 10:00）自动执行：

1. 运行 `scripts/update_pricing.py` 抓取各厂商最新定价
2. 运行 `scripts/normalize_data.py` 重新规范化数据
3. 如有价格变更，自动 git commit 并 push
4. 如无变更，仅刷新 `last_updated` 日期

也支持在 GitHub 仓库的 **Actions** 页面手动触发（`workflow_dispatch`）。

### 手动更新

```bash
# 安装依赖
pip install requests beautifulsoup4

# 抓取并更新（写入文件）
python3 scripts/update_pricing.py

# 仅预览变更（不写入）
python3 scripts/update_pricing.py --dry-run

# 仅更新指定厂商
python3 scripts/update_pricing.py --vendor openai

# 手动编辑原始数据后重新规范化
python3 scripts/normalize_data.py
```

### 添加新模型

1. 在 `llm_pricing_data.json` 的 `models` 数组中添加新条目
2. 运行 `python3 scripts/normalize_data.py` 重新生成 `data/pricing.json`
3. 刷新 Dashboard 页面

模型条目格式：

```json
{
  "model": "模型名称",
  "vendor": "厂商",
  "type": "text | multimodal | image | video | audio",
  "input_price_usd_per_mtok": 2.5,
  "output_price_usd_per_mtok": 10.0,
  "context_window": "128K",
  "is_open_source": false,
  "status": "current | deprecated",
  "pricing_url": "https://官方定价页URL",
  "notes": "备注说明"
}
```

## 技术栈

- **前端**：纯 HTML + CSS + JavaScript（零依赖，单文件）
- **数据**：JSON 格式，前后端分离
- **自动化**：Python 脚本 + GitHub Actions
- **部署**：GitHub Pages（免费静态托管）

## ⚠️ 免责声明

- 定价数据仅供参考，实际计费请以各厂商官网为准
- 自动抓取脚本可能因厂商页面结构变更而失效，需定期维护
- 部分厂商定价页有反爬机制，脚本已做容错处理（失败不影响其他厂商）
