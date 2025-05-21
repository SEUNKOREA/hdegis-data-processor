import os
import sys
from typing import List, Dict, Tuple, Optional, Any
import warnings
from urllib3.exceptions import InsecureRequestWarning

# InsecureRequestWarning 경고 무시
warnings.simplefilter("ignore", InsecureRequestWarning)

from elasticsearch import Elasticsearch

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from utils.logger import get_logger
from config import LOG_LEVEL

logger = get_logger(__name__, LOG_LEVEL)



class ESConnector:
    def __init__(self, hosts: str, credentials: Tuple[str, str]):
        self.hosts = [hosts]
        self.credentials = credentials
        self.conn = self._create_es_connections()

    def _create_es_connections(self):
        username, password = self.credentials
        es = Elasticsearch(
            hosts=self.hosts,
            basic_auth=(username, password),
            verify_certs=False,
        )
        return es

    def ping(self):
        if self.es.ping():
            logger.info("Ping successful: Connected to Elasticsearch!")
        else:
            logger.info("Ping unsuccessful: Elasticsearch is not available!")