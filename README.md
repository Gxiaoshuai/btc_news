# 加密货币新闻服务端

一个轻量级、实时的加密货币新闻服务端，支持新闻推送、AI 分析、情绪判断和自动清理功能。

## 功能特性

1. **新闻推送**：通过 API 接口接收外部爬虫推送的新闻数据
2. **智能分析**：使用 DeepSeek API 自动分析新闻，提取摘要、情绪、得分和相关币种
3. **新闻查询**：提供 API 接口查询过去1小时内的已分析新闻
4. **智能过滤**：默认只返回摘要，重大新闻（情绪得分极高或极低）才返回原文
5. **市场情绪**：提供整体市场情绪参考指标
6. **自动清理**：自动清理1小时前的旧数据

## 技术栈

- **后端框架**: FastAPI
- **数据库**: SQLite
- **ORM**: SQLModel
- **AI 模型**: DeepSeek API
- **爬虫**: Selenium + Chrome WebDriver

## 快速开始

### 1. 环境配置

复制 `.env.example` 为 `.env` 并填入配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置 DeepSeek API Key：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行服务

```bash
# 开发模式
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或直接运行
python main.py
```

服务启动后，访问 http://localhost:8000/docs 查看 API 文档。

## Docker 部署

### 构建镜像

```bash
docker build -t crypto-news-server .
```

### 运行容器

```bash
docker run -d \
  -p 8000:8000 \
  -v ./db:/app/db \
  -v ./.env:/app/.env \
  --name news-server \
  crypto-news-server
```

重要参数说明：
- `-p 8000:8000`: 端口映射
- `-v ./db:/app/db`: 数据持久化（SQLite 数据库文件）
- `-v ./.env:/app/.env`: 环境变量配置

## API 接口

### 1. POST /push_news

推送新闻并自动分析。

**请求体**:
```json
{
  "content": "这里是新闻的完整内容...",
  "source_url": "https://example.com/news/123"
}
```

**响应**:
```json
{
  "status": "success",
  "message": "News received and analyzed.",
  "id": 123
}
```

### 2. GET /get_news

查询过去1小时内的所有新闻。

**响应**:
```json
[
  {
    "id": 123,
    "summary": "AI 生成的摘要...",
    "sentiment": "positive",
    "sentiment_score": 0.85,
    "mentioned_coins": ["BTC", "SOL"],
    "source_url": "https://example.com/news/123",
    "received_at": "2025-10-29T17:01:00.000Z",
    "is_major": true,
    "original_content": "这是一条重大利好新闻的原文..."
  }
]
```

### 3. GET /get_new_detail/{id}

获取新闻详情。

### 4. GET /get_market_sentiment

获取过去1小时内的整体市场情绪。

**响应**:
```json
{
  "market_sentiment_normalized": 0.62,
  "news_count": 5,
  "max_score": 0.85,
  "min_score": 0.35,
  "max_score_news_id": 123,
  "min_score_news_id": 124
}
```

## 爬虫使用

### 使用爬虫脚本

```bash
python crawler.py --accounts https://x.com/user1 https://x.com/user2 --api-url http://localhost:8000
```

### 在代码中使用

```python
from crawler import TwitterCrawler

# 创建爬虫实例
crawler = TwitterCrawler(api_url="http://localhost:8000")

# 登录（首次使用需要手动登录）
crawler.login()

# 爬取并推送（自动去重）
account_urls = ["https://x.com/crypto_user1", "https://x.com/crypto_user2"]
crawler.crawl_and_push(account_urls)

# 关闭浏览器
crawler.close()
```

## 项目结构

```
.
├── main.py                 # FastAPI 主应用
├── models.py               # 数据模型
├── database.py             # 数据库配置
├── deepseek_client.py      # DeepSeek API 客户端
├── crawler.py              # 推特爬虫
├── config.py               # 配置文件
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 镜像配置
├── webdriver/              # WebDriver 相关代码
│   └── chrome.py
└── db/                     # 数据库文件目录
    └── news.db
```

## 配置说明

主要配置项（在 `.env` 文件中设置）：

- `DEEPSEEK_API_KEY`: DeepSeek API 密钥（必需）
- `DEEPSEEK_API_BASE`: DeepSeek API 基础 URL（默认: https://api.deepseek.com/v1）
- `DATABASE_URL`: 数据库连接字符串（默认: sqlite:///./db/news.db）
- `NEWS_RETENTION_HOURS`: 新闻保留时间（小时，默认: 1）
- `MAJOR_NEWS_THRESHOLD_LOW`: 重大利空阈值（默认: 0.2）
- `MAJOR_NEWS_THRESHOLD_HIGH`: 重大利好阈值（默认: 0.8）

## 重大新闻判定

- `sentiment_score < 0.2`: 重大利空
- `sentiment_score > 0.8`: 重大利好
- 重大新闻在 `/get_news` 接口中会返回原文内容

## 去重机制

爬虫端实现了内容相似度去重：
- 使用 `difflib.SequenceMatcher` 计算相似度
- 默认阈值: 80% 相似度
- 只保留最近2小时内的新闻缓存用于去重

## 注意事项

1. 首次使用爬虫时需要手动登录推特账号
2. 确保 Chrome 浏览器和 ChromeDriver 已正确安装（Docker 镜像已包含）
3. DeepSeek API Key 是必需的，请确保有效
4. 数据库文件会保存在 `./db/news.db`，注意备份

## 许可证

MIT License

