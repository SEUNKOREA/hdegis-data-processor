import os
import sys
from typing import Tuple, Optional, List

from google import genai
from google.genai.types import EmbedContentConfig

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from config import EMBEDDING_MODEL


def get_text_embedding(text: str, client: genai.Client) -> List[float]:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[text],
        config=EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
            title="Content of Document"
        )
    )
    return response.embeddings[0].values


if __name__ == "__main__":
    ############### 함수 동작 테스트 ###############
    from config import PROJECT_ID, GENAI_LOCATION
    genai_client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=GENAI_LOCATION,
    )

    res = get_text_embedding(text="안녕하세요", client=genai_client)
    print(f"length: {len(res)}")
    print(res[:5])