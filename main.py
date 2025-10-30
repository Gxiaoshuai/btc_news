"""FastAPI 主应用"""
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, func, desc, asc
from datetime import datetime, timedelta
from typing import List
import logging

from config import settings
from database import engine, init_db, get_session
from models import (
    NewsItem, NewsItemCreate, NewsItemResponse, NewsItemDetailResponse,
    PushNewsResponse, MarketSentimentResponse
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
        # 1. 调用 DeepSeek API 分析新闻
        analysis_result = analyze_news_with_deepseek(news_data.content)
        
        # 2. 判断是否为重大新闻
        sentiment_score = analysis_result["sentiment_score"]
        is_major = (sentiment_score < settings.major_news_threshold_low or
                   sentiment_score > settings.major_news_threshold_high)
        
        # 3. 创建新闻项
        news_item = NewsItem(
            original_content=news_data.content,
            source_url=news_data.source_url,
            summary=analysis_result["summary"],
            sentiment=analysis_result["sentiment"],
            sentiment_score=sentiment_score,
            is_major=is_major
        )
        news_item.set_mentioned_coins_list(analysis_result["mentioned_coins"])
        
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


@app.get("/get_news", response_model=List[NewsItemResponse])
async def get_news(session: Session = Depends(get_session)):
    """
    查询过去1小时内的所有新闻
    """
    try:
        # 查询过去1小时内的新闻
        cutoff_time = datetime.utcnow() - timedelta(hours=settings.news_retention_hours)
        statement = select(NewsItem).where(
            NewsItem.received_at >= cutoff_time
        ).order_by(desc(NewsItem.received_at))
        
        news_items = session.exec(statement).all()
        
        # 构建响应列表
        result = []
        for news in news_items:
            response_item = NewsItemResponse(
                id=news.id,
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
        
        return result
        
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

