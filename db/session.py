from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from config import (
    MYSQL_USER, MYSQL_PWD, MYSQL_HOST,
    MYSQL_PORT, MYSQL_DB, MYSQL_CHARSET
)

# SQLAlchemy + PyMySQL 연결 문자열 생성
# DATABASE_URL: str = (
#     f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PWD}"
#     f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
#     f"?charset={MYSQL_CHARSET}"
# )
DATABASE_URL = "mysql+pymysql://hde_chat:dpdlcldecot1%40@10.100.79.63:23306/hde_chat?charset=utf8mb4"


# 엔진 생성 (pool_pre_ping=True 로 연결 끊김 방지)
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

# 세션 팩토리
SessionLocal: sessionmaker = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db_session() -> Generator[Session, None, None]:
    """
    Dependency 또는 직접 호출용으로,
    yield 후 반드시 .close() 되도록 설계.
    """
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()