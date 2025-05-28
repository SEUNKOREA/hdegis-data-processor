import os
import sys
from sqlalchemy import inspect

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from db.models import Base
from db.session import engine
from utils.logger import get_logger
from config import LOG_LEVEL, TABLENAME_PDFDOCUMENTS, TABLENAME_PDFPAGES

logger = get_logger(__name__, LOG_LEVEL)


def print_table_infos():
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print("\n현재 DB 테이블 및 컬럼 정보:")
    for table in tables:
        print(f"\nTABLE NAME: {table}")
        columns = inspector.get_columns(table)
        for col in columns:
            name = col['name']
            type_ = col['type']
            nullable = col['nullable']
            default = col.get('default', None)
            print(f"  - {name} ({type_}){' NULL' if nullable else ' NOT NULL'}"
                  f"{' DEFAULT ' + str(default) if default is not None else ''}")
    return tables

def initialize_tables():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # 최소한의 기준 테이블 존재 여부 판단
    if TABLENAME_PDFPAGES not in existing_tables or TABLENAME_PDFDOCUMENTS not in existing_tables:
        logger.info(" ┌── There is no tables → Try to create tables")
        Base.metadata.create_all(bind=engine)
        logger.info(" └── Created tables!")
    else:
        logger.info(" └── Already exists all tables")
    
    # print_table_infos()


if __name__ == "__main__":
   initialize_tables()