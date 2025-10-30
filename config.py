"""配置文件"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # DeepSeek API 配置
    deepseek_api_key: str = "your_deepseek_api_key_here"
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    
    # 数据库配置
    database_url: str = "sqlite:///./db/news.db"
    
    # 服务器配置
    app_name: str = "加密货币新闻服务端"
    app_version: str = "1.0.0"
    
    # 新闻处理配置
    news_retention_hours: int = 24
    
    # 重大新闻阈值
    major_news_threshold_low: float = 0.2  # 低于此值为重大利空
    major_news_threshold_high: float = 0.8  # 高于此值为重大利好
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()