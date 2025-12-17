"""数据模型"""
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import String, DateTime, Boolean, Float
import json


class NewsItem(SQLModel, table=True):
    """新闻数据模型"""
    __tablename__ = "newsitem"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    original_content: str = Field(sa_column=Column("original_content", type_=String, nullable=False))
    source_url: str = Field(sa_column=Column("source_url", type_=String, nullable=False))
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column("received_at", type_=DateTime, nullable=False, index=True)
    )
    summary: str = Field(sa_column=Column("summary", type_=String, nullable=False))
    sentiment: str = Field(sa_column=Column("sentiment", type_=String, nullable=False))  # 'positive', 'negative', 'neutral'
    sentiment_score: float = Field(sa_column=Column("sentiment_score", type_=Float, nullable=False))
    mentioned_coins: str = Field(sa_column=Column("mentioned_coins", type_=String, nullable=False))  # JSON 字符串
    is_major: bool = Field(default=False, sa_column=Column("is_major", type_=Boolean, nullable=False))
    
    def get_mentioned_coins_list(self) -> List[str]:
        """将 JSON 字符串转换为列表"""
        try:
            return json.loads(self.mentioned_coins)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_mentioned_coins_list(self, coins: List[str]):
        """将列表转换为 JSON 字符串"""
        self.mentioned_coins = json.dumps(coins, ensure_ascii=False)


class NewsItemCreate(SQLModel):
    """创建新闻的请求模型"""
    content: str
    source_url: str


class NewsItemResponse(SQLModel):
    """新闻响应模型"""
    id: int
    summary: str
    sentiment: str
    sentiment_score: float
    mentioned_coins: List[str]
    source_url: str
    received_at: datetime
    is_major: bool
    original_content: Optional[str] = None


class NewsItemDetailResponse(SQLModel):
    """新闻详情响应模型"""
    id: int
    original_content: str
    source_url: str
    received_at: datetime
    summary: str
    sentiment: str
    sentiment_score: float
    mentioned_coins: List[str]
    is_major: bool


class PushNewsResponse(SQLModel):
    """推送新闻响应模型"""
    status: str
    message: str
    id: int


class MarketSentimentResponse(SQLModel):
    """市场情绪响应模型"""
    market_sentiment_normalized: float
    news_count: int
    max_score: Optional[float] = None
    min_score: Optional[float] = None
    max_score_news_id: Optional[int] = None
    min_score_news_id: Optional[int] = None


class NewsListResponse(SQLModel):
    """新闻列表分页响应模型"""
    items: List[NewsItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
