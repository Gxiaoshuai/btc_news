"""数据库连接和初始化"""
from sqlmodel import SQLModel, create_engine, Session
import os
from config import settings

# 创建数据库目录
db_dir = os.path.dirname(settings.database_url.replace("sqlite:///", ""))
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# 创建数据库引擎
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite 需要此参数
    echo=False
)


def init_db():
    """初始化数据库表"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """获取数据库会话"""
    with Session(engine) as session:
        yield session

