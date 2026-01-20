"""数据库连接和初始化"""
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text, event
from sqlalchemy.engine import Engine
import logging
from config import settings

logger = logging.getLogger(__name__)

# 创建 MySQL 数据库引擎
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # 自动检测连接是否有效
    pool_recycle=3600,   # 每小时回收连接
    pool_size=10,        # 连接池大小
    max_overflow=20,     # 最大溢出连接数
    echo=False
)


def init_db():
    """初始化数据库表"""
    # 创建所有表
    SQLModel.metadata.create_all(engine)
    
    # 创建全文索引（如果不存在）
    _create_fulltext_index()


def _create_fulltext_index():
    """创建全文索引"""
    with engine.connect() as conn:
        try:
            # 检查全文索引是否已存在
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.statistics 
                WHERE table_schema = :db_name 
                AND table_name = 'newsitem' 
                AND index_name = 'ft_news_content'
            """), {"db_name": settings.mysql_database})
            
            index_exists = result.scalar() > 0
            
            if index_exists:
                # 删除旧索引以便重建（包含 title 字段）
                conn.execute(text("ALTER TABLE newsitem DROP INDEX ft_news_content"))
                conn.commit()
                logger.info("删除旧的全文索引 ft_news_content")
            
            # 创建全文索引，包含 title, original_content, summary，使用 ngram 解析器支持中文
            conn.execute(text("""
                ALTER TABLE newsitem 
                ADD FULLTEXT INDEX ft_news_content (title, original_content, summary) 
                WITH PARSER ngram
            """))
            conn.commit()
            logger.info("全文索引 ft_news_content 创建成功（包含 title, original_content, summary）")
                
        except Exception as e:
            logger.warning(f"创建全文索引时发生错误: {e}")
            # 索引创建失败不影响程序运行


def fulltext_search(session: Session, search_term: str, cutoff_time, page: int = 1, page_size: int = 20, relevance_threshold: float = None):
    """
    使用全文索引搜索新闻
    
    Args:
        session: 数据库会话
        search_term: 搜索关键词
        cutoff_time: 截止时间
        page: 页码
        page_size: 每页数量
        relevance_threshold: 相关度阈值，只返回相关度大于等于此值的结果（可选）
    
    Returns:
        tuple: (新闻列表, 总数, 是否使用全文搜索)
    """
    from models import NewsItem
    
    offset = (page - 1) * page_size
    
    try:
        # 使用全文索引搜索，按相关度排序
        # MATCH...AGAINST 返回相关度分数，分数越高越相关
        # 搜索范围包含 title, original_content, summary
        
        # 根据是否有相关度阈值构建不同的查询
        if relevance_threshold is not None and relevance_threshold > 0:
            # 带相关度阈值的查询
            search_query = text("""
                SELECT *, MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE) AS relevance
                FROM newsitem 
                WHERE  MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE)
                HAVING relevance >= :threshold
                ORDER BY relevance DESC, received_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            count_query = text("""
                SELECT COUNT(*) FROM (
                    SELECT MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE) AS relevance
                    FROM newsitem 
                    WHERE  MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE)
                    HAVING relevance >= :threshold
                ) AS filtered_results
            """)
            
            query_params = {
                "search": search_term,
                # "cutoff_time": cutoff_time,
                "threshold": relevance_threshold,
                "limit": page_size,
                "offset": offset
            }
            
            count_params = {
                "search": search_term,
                "threshold": relevance_threshold
            }
        else:
            # 不带相关度阈值的查询
            search_query = text("""
                SELECT *, MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE) AS relevance
                FROM newsitem 
                WHERE MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE)
                ORDER BY relevance DESC, received_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            count_query = text("""
                SELECT COUNT(*) 
                FROM newsitem 
                WHERE MATCH(title, original_content, summary) AGAINST(:search IN NATURAL LANGUAGE MODE)
            """)
            
            query_params = {
                "search": search_term,
                "limit": page_size,
                "offset": offset
            }
            
            count_params = {
                "search": search_term,
            }
        
        # 执行搜索查询
        result = session.execute(search_query, query_params)
        
        # 将结果转换为 NewsItem 对象
        news_items = []
        for row in result:
            news_item = NewsItem(
                id=row.id,
                title=row.title,
                original_content=row.original_content,
                source_url=row.source_url,
                received_at=row.received_at,
                summary=row.summary,
                sentiment=row.sentiment,
                sentiment_score=row.sentiment_score,
                mentioned_coins=row.mentioned_coins,
                is_major=row.is_major
            )
            news_items.append(news_item)
        
        # 获取总数
        count_result = session.execute(count_query, count_params)
        total = count_result.scalar()
        
        return news_items, total, True
        
    except Exception as e:
        logger.warning(f"全文搜索失败，回退到 LIKE 搜索: {e}")
        # 全文搜索失败时回退到 LIKE 搜索
        return None, None, False


def get_session():
    """获取数据库会话"""
    with Session(engine) as session:
        yield session

