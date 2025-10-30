"""DeepSeek API 客户端"""
import json
from typing import Dict, List, Optional
from openai import OpenAI
from config import settings
import logging

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """DeepSeek API 客户端"""
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_api_base
        )
        self.model = settings.deepseek_model
        
        # JSON Schema 用于约束输出格式
        self.json_schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "sentiment": {"type": "string"},
                "sentiment_score": {"type": "number"},
                "mentioned_coins": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["summary", "sentiment", "sentiment_score", "mentioned_coins"]
        }
        
        self.system_prompt = """你是一个专业的加密货币金融分析师。请分析以下新闻内容。
你需要提供：
1. 'summary': 对新闻的简明中文摘要。
2. 'sentiment': 判断新闻情绪是 'positive' (利好), 'negative' (利空), 还是 'neutral' (中性)。
3. 'sentiment_score': 情绪的归一化得分，0.0代表极度利空，1.0代表极度利好，0.5代表中性。
4. 'mentioned_coins': 提及的具体加密货币代码（例如 BTC, ETH, SOL）。如果没有，返回空列表。
请严格按照请求的 JSON 格式输出。"""
    
    def analyze_news(self, content: str) -> Dict:
        """
        使用 DeepSeek API 分析新闻
        
        Args:
            content: 新闻内容
            
        Returns:
            包含 summary, sentiment, sentiment_score, mentioned_coins 的字典
            
        Raises:
            Exception: API 调用失败时抛出异常
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"请分析以下新闻：\n\n{content}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content
            
            # 解析 JSON 响应
            result = json.loads(result_text)
            
            # 验证必需字段
            required_fields = ["summary", "sentiment", "sentiment_score", "mentioned_coins"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"API 返回结果缺少必需字段: {field}")
            
            # 验证 sentiment 值
            if result["sentiment"] not in ["positive", "negative", "neutral"]:
                logger.warning(f"非标准的 sentiment 值: {result['sentiment']}，将其标准化")
                # 根据 sentiment_score 推断 sentiment
                score = result["sentiment_score"]
                if score > 0.6:
                    result["sentiment"] = "positive"
                elif score < 0.4:
                    result["sentiment"] = "negative"
                else:
                    result["sentiment"] = "neutral"
            
            # 验证 sentiment_score 范围
            score = float(result["sentiment_score"])
            if not 0.0 <= score <= 1.0:
                logger.warning(f"Sentiment score out of range: {score}, clamping to [0.0, 1.0]")
                result["sentiment_score"] = max(0.0, min(1.0, score))
            
            # 确保 mentioned_coins 是列表
            if not isinstance(result["mentioned_coins"], list):
                result["mentioned_coins"] = []
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 原始响应: {result_text}")
            raise ValueError(f"API 返回的 JSON 格式无效: {e}")
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            raise


# 创建全局实例
deepseek_client = DeepSeekClient()


def analyze_news_with_deepseek(content: str) -> Dict:
    """
    分析新闻的便捷函数
    
    Args:
        content: 新闻内容
        
    Returns:
        包含 summary, sentiment, sentiment_score饰, mentioned_coins 的字典
    """
    return deepseek_client.analyze_news(content)

