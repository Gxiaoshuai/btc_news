"""配置文件"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
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
    
    # AI 分析配置
    enable_ai_analysis: bool = True  # 是否启用AI进行新闻整理分析
    
    # 重大新闻阈值
    major_news_threshold_low: float = 0.2  # 低于此值为重大利空
    major_news_threshold_high: float = 0.8  # 高于此值为重大利好
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # 忽略额外的环境变量，而不是报错
    )
    
    @field_validator('enable_ai_analysis', mode='before')
    @classmethod
    def parse_bool(cls, v):
        """将字符串类型的布尔值转换为布尔类型"""
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v) if v is not None else True


settings = Settings()