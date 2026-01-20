"""FastAPI 主应用"""
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, func, desc, asc, or_
from datetime import datetime, timedelta
from typing import List, Optional
import logging

from config import settings
from database import engine, init_db, get_session, fulltext_search
from models import (
    NewsItem, NewsItemCreate, NewsItemResponse, NewsItemDetailResponse,
    PushNewsResponse, MarketSentimentResponse, NewsListResponse
)
from deepseek_client import analyze_news_with_deepseek

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """应用启动时初始化数据库"""
    init_db()
    logger.info("数据库初始化完成")


def cleanup_old_news(session: Session):
    """清理1小时前的旧新闻数据"""
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=settings.news_retention_hours)
        statement = select(NewsItem).where(NewsItem.received_at < cutoff_time)
        old_news = session.exec(statement).all()
        
        for news in old_news:
            session.delete(news)
        
        session.commit()
        logger.info(f"清理了 {len(old_news)} 条旧新闻")
    except Exception as e:
        logger.error(f"清理旧新闻时发生错误: {e}")
        session.rollback()


@app.post("/push_news", response_model=PushNewsResponse)
async def push_news(
    news_data: NewsItemCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    接收爬虫推送的新闻并进行 AI 分析
    """
    try:
        # 1. 根据配置决定是否调用 AI 分析
        if settings.enable_ai_analysis:
            # 调用 DeepSeek API 分析新闻
            analysis_result = analyze_news_with_deepseek(news_data.content)
            summary = analysis_result["summary"]
            sentiment = analysis_result["sentiment"]
            sentiment_score = analysis_result["sentiment_score"]
            mentioned_coins = analysis_result["mentioned_coins"]
            logger.info("使用 AI 分析新闻")
        else:
            # 不使用 AI 分析，使用默认值
            summary = news_data.content[:200] if len(news_data.content) > 200 else news_data.content
            sentiment = "neutral"
            sentiment_score = 0.5
            mentioned_coins = []
            logger.info("跳过 AI 分析，使用默认值")
        
        # 2. 判断是否为重大新闻
        is_major = (sentiment_score < settings.major_news_threshold_low or
                   sentiment_score > settings.major_news_threshold_high)
        
        # 3. 创建新闻项
        news_item = NewsItem(
            title=news_data.title,
            original_content=news_data.content,
            source_url=news_data.source_url,
            summary=summary,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            is_major=is_major
        )
        news_item.set_mentioned_coins_list(mentioned_coins)
        
        # 4. 保存到数据库
        session.add(news_item)
        session.commit()
        session.refresh(news_item)
        
        # 5. 触发后台清理任务
        background_tasks.add_task(cleanup_old_news, session)
        
        logger.info(f"接收到新新闻 ID: {news_item.id}, 情绪得分: {sentiment_score}, 是否重大: {is_major}")
        
        return PushNewsResponse(
            status="success",
            message="News received and analyzed.",
            id=news_item.id
        )
        
    except Exception as e:
        logger.error(f"处理新闻推送时发生错误: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=f"处理新闻时发生错误: {str(e)}")


@app.get("/get_news", response_model=NewsListResponse)
async def get_news(
    search: Optional[str] = None,
    relevance_threshold: Optional[float] = None,
    page: int = 1,
    page_size: int = 20,
    session: Session = Depends(get_session)
):
    """
    查询过去1小时内的新闻，支持全文索引搜索和分页
    - search: 搜索关键词（可选），使用MySQL全文索引在新闻标题和内容中搜索，按相关度排序
    - relevance_threshold: 相关度阈值（可选），只返回相关度大于等于此值的结果，取值范围通常为0-10+
    - page: 页码，默认第1页
    - page_size: 每页数量，默认20条
    """
    try:
        # 查询过去指定时间内的新闻
        cutoff_time = None
        
        news_items = []
        total = 0
        
        # 如果提供了搜索关键词，使用全文索引搜索
        if search:
            # 尝试使用全文索引搜索
            ft_result, ft_total, used_fulltext = fulltext_search(
                session, search, cutoff_time, page, page_size
            )
            
            if used_fulltext and ft_result is not None:
                # 全文搜索成功，按相关度排序
                news_items = ft_result
                total = ft_total
                logger.info(f"使用全文索引搜索，关键词: {search}, 结果数: {total}")
            else:
                # 回退到 LIKE 搜索
                search_pattern = f"%{search}%"
                statement = select(NewsItem).where(
                    NewsItem.received_at >= cutoff_time
                ).where(
                    or_(
                        NewsItem.title.like(search_pattern),
                        NewsItem.original_content.like(search_pattern),
                        NewsItem.summary.like(search_pattern)
                    )
                )
                
                # 获取总数
                count_statement = select(func.count(NewsItem.id)).where(
                    NewsItem.received_at >= cutoff_time
                ).where(
                    or_(
                        NewsItem.title.like(search_pattern),
                        NewsItem.original_content.like(search_pattern),
                        NewsItem.summary.like(search_pattern)
                    )
                )
                total = session.exec(count_statement).one()
                
                # 添加排序和分页
                offset = (page - 1) * page_size
                statement = statement.order_by(desc(NewsItem.received_at))
                statement = statement.offset(offset).limit(page_size)
                news_items = session.exec(statement).all()
                logger.info(f"使用 LIKE 搜索，关键词: {search}, 结果数: {total}")
        else:
            # 无搜索关键词，查询所有新闻
            statement = select(NewsItem).where(
                NewsItem.received_at >= cutoff_time
            )
            
            # 获取总数
            count_statement = select(func.count(NewsItem.id)).where(
                NewsItem.received_at >= cutoff_time
            )
            total = session.exec(count_statement).one()
            
            # 添加排序和分页
            offset = (page - 1) * page_size
            statement = statement.order_by(desc(NewsItem.received_at))
            statement = statement.offset(offset).limit(page_size)
            news_items = session.exec(statement).all()
        
        # 构建响应列表
        result = []
        for news in news_items:
            response_item = NewsItemResponse(
                id=news.id,
                title=news.title,
                summary=news.summary,
                sentiment=news.sentiment,
                sentiment_score=news.sentiment_score,
                mentioned_coins=news.get_mentioned_coins_list(),
                source_url=news.source_url,
                received_at=news.received_at,
                is_major=news.is_major,
                original_content=news.original_content  # 所有新闻都包含原始内容
            )
            
            result.append(response_item)
        
        # 计算总页数
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return NewsListResponse(
            items=result,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except Exception as e:
        logger.error(f"查询新闻时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"查询新闻时发生错误: {str(e)}")


@app.get("/get_new_detail/{news_id}", response_model=NewsItemDetailResponse)
async def get_new_detail(news_id: int, session: Session = Depends(get_session)):
    """
    获取新闻详情
    """
    try:
        statement = select(NewsItem).where(NewsItem.id == news_id)
        news_item = session.exec(statement).first()
        
        if not news_item:
            raise HTTPException(status_code=404, detail=f"未找到 ID 为 {news_id} 的新闻")
        
        return NewsItemDetailResponse(
            id=news_item.id,
            title=news_item.title,
            original_content=news_item.original_content,
            source_url=news_item.source_url,
            received_at=news_item.received_at,
            summary=news_item.summary,
            sentiment=news_item.sentiment,
            sentiment_score=news_item.sentiment_score,
            mentioned_coins=news_item.get_mentioned_coins_list(),
            is_major=news_item.is_major
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询新闻详情时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"查询新闻详情时发生错误: {str(e)}")


@app.get("/get_market_sentiment", response_model=MarketSentimentResponse)
async def get_market_sentiment(session: Session = Depends(get_session)):
    """
    获取过去1小时内的整体市场情绪
    """
    try:
        # 查询过去1小时内的新闻
        cutoff_time = datetime.utcnow() - timedelta(hours=settings.news_retention_hours)
        statement = select(NewsItem).where(
            NewsItem.received_at >= cutoff_time
        )
        
        news_items = session.exec(statement).all()
        
        if not news_items:
            # 如果没有新闻，返回中性值
            return MarketSentimentResponse(
                market_sentiment_normalized=0.5,
                news_count=0
            )
        
        # 计算平均值、最大值和最小值
        scores = [news.sentiment_score for news in news_items]
        avg_score = sum(scores) / len(scores)
        
        max_score = max(scores)
        min_score = min(scores)
        
        # 找到对应的新闻 ID
        max_news = next(news for news in news_items if news.sentiment_score == max_score)
        min_news = next(news for news in news_items if news.sentiment_score == min_score)
        
        return MarketSentimentResponse(
            market_sentiment_normalized=round(avg_score, 4),
            news_count=len(news_items),
            max_score=max_score,
            min_score=min_score,
            max_score_news_id=max_news.id,
            min_score_news_id=min_news.id
        )
        
    except Exception as e:
        logger.error(f"查询市场情绪时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"查询市场情绪时发生错误: {str(e)}")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "加密货币新闻服务端",
        "version": settings.app_version,
        "endpoints": {
            "push_news": "POST /push_news",
            "get_news": "GET /get_news",
            "get_new_detail": "GET /get_new_detail/{id}",
            "get_market_sentiment": "GET /get_market_sentiment",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

