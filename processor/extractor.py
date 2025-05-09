from typing import Tuple, Optional
import base64
import pathlib
from google import genai
from google.genai import types

from config import PROJECT_ID, LOCATION
from prompts import EXTRACT_TEXT_PROMPT, EXTRACT_DESCRIPTION_PROMPT


# Vertex AI용 클라이언트 설정
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID, 
    location=LOCATION
)

model_name = "gemini-2.0-flash-001"


def load_image_as_bytes(image_path: str) -> bytes:
    with open(image_path, "rb") as f:
        return f.read()


def extract_text_with_gemini(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Gemini를 이용해 이미지에서 Markdown 기반 텍스트 추출
    """
    try:
        prompt = EXTRACT_TEXT_PROMPT.strip()

        image_bytes = load_image_as_bytes(image_path)

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ]
            )
        ]

        config = types.GenerateContentConfig(
            temperature=0,
            top_p=0.95,
            max_output_tokens=8192,
            response_modalities=["TEXT"],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ]
        )

        result = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )

        return result.text.strip(), None

    except Exception as e:
        return None, f"텍스트 추출 오류: {e}"


def extract_description_with_gemini(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Gemini를 이용해 이미지 내용 요약/설명 추출
    """
    try:
        prompt = EXTRACT_DESCRIPTION_PROMPT.strip()

        image_bytes = load_image_as_bytes(image_path)

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ]
            )
        ]

        config = types.GenerateContentConfig(
            temperature=0.2,
            top_p=0.9,
            max_output_tokens=512,
            response_modalities=["TEXT"],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ]
        )

        result = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )

        return result.text.strip(), None

    except Exception as e:
        return None, f"설명 추출 오류: {e}"
