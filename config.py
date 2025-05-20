from dotenv import load_dotenv
import os

load_dotenv()

GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
PROJECT_ID: str = os.getenv("PROJECT_ID")

GCS_SOURCE_BUCKET: str = os.getenv("GCS_SOURCE_BUCKET")
GCS_PROCESSED_BUCKET: str = os.getenv("GCS_PROCESSED_BUCKET")

GENAI_LOCATION: str = os.getenv("GENAI_LOCATION")

EXTRACT_TEXT_MODEL: str = os.getenv("EXTRACT_TEXT_MODEL")
EXTRACT_SUMMARY_MODEL: str = os.getenv("EXTRACT_SUMMARY_MODEL")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL")



MYSQL_HOST: str = os.getenv("MYSQL_HOST")
MYSQL_PORT: int = int(os.getenv("MYSQL_PORT"))
MYSQL_USER: str = os.getenv("MYSQL_USER")
MYSQL_PWD: str = os.getenv("MYSQL_PWD")
MYSQL_CHARSET: str = os.getenv("MYSQL_CHARSET")
MYSQL_DB: str = os.getenv("MYSQL_DB")

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")