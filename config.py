from dotenv import load_dotenv
import os

load_dotenv()

GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GCS_SOURCE_BUCKET: str = os.getenv("GCS_SOURCE_BUCKET")
GCS_PROCESSED_BUCKET: str = os.getenv("GCS_PROCESSED_BUCKET")
PROJECT_ID: str = os.getenv("PROJECT_ID")
LOCATION: str = os.getenv("LOCATION")

MYSQL_HOST: str = os.getenv("MYSQL_HOST")
MYSQL_PORT: int = int(os.getenv("MYSQL_PORT"))
MYSQL_USER: str = os.getenv("MYSQL_USER")
MYSQL_PWD: str = os.getenv("MYSQL_PWD")
MYSQL_CHARSET: str = os.getenv("MYSQL_CHARSET")
MYSQL_DB: str = os.getenv("MYSQL_DB")

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")