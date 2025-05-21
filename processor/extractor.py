import os
import sys
from typing import Tuple, Optional, List

from google import genai
from google.genai import types

PROJECT_PATH = os.path.dirname(os.path.dirname(__file__))
sys.path.append(PROJECT_PATH)

from processor.prompts import EXTRACT_TEXT_PROMPT, EXTRACT_SUMMARY_PROMPT_1, EXTRACT_SUMMARY_PROMPT_2, EXTRACT_SUMMARY_PROMPT_3
from config import EXTRACT_TEXT_MODEL, EXTRACT_SUMMARY_MODEL

def load_image_as_bytes(image_path: str) -> bytes:
    with open(image_path, "rb") as f:
        return f.read()


def extract_text(image_path: str, client: genai.Client) -> Tuple[Optional[str], Optional[str]]:
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
                    types.Part.from_text(text=prompt),
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
            model=EXTRACT_TEXT_MODEL,
            contents=contents,
            config=config
        )

        return result.text, None

    except Exception as e:
        return None, f"텍스트 추출 오류: {e}"


def extract_summary(target_image_path: str, context_image_paths: List[str], client: genai.Client) -> Tuple[Optional[str], Optional[str]]:
    """
    Gemini를 이용해 이미지 내용 요약/설명 추출
    """

    def get_description(file_name: str):
        description_mapping = {
            '1. International Standards': 'Includes international standard and specification documents required for high voltage circuit breaker design and testing. Refer to the technical specifications of global standardization organizations such as IEC and IEEE. Required data for product development and design standard establishment.',
            'IEC': 'Standard and specification documents on high-voltage equipment issued by the International Conference on Electrical Standards (IEC). Provide global standards for design, testing, safety standards, etc.',
            'IEEE': 'The American Institute of Electrical and Electronics (IEEE) specifications and standards, including market-focused design standards and testing procedures in North America.',
            '2. Type Test Reports': 'This is the type test result report of the actual manufactured circuit breaker. It is classified by model and year and details test items, insulation performance, and blocking performance.',
            '145SP-3': 'Type test data for circuit breaker model 145SP-3.',
            '145 kV 40 kA MS (2017)': 'A test report of a 145kV / 40kA class circuit breaker tested in 2017 of the model 145SP-3.',
            '300SR': 'Type test data for circuit breaker model 300SR.',
            '245 kV 50 kA MS (2020)': 'Test report of 245kV / 50kA circuit breaker tested in 2020 of Model 300SR.',
            '245 kV 63 kA MS (2024)': 'Test report of 245kV / 63kA circuit breaker carried out in 2024 of Model 300SR.',
            '3. Customer Standard Specifications': 'Standard Specifications by Country/Power Authority/Consumer.\nStandard Specification document provided by each country and customer. Refer to when delivering the product if you need a design that reflects customer requirements. This may include local application regulations and special requirements.',
            'Endeavour Energy': 'Standard specifications of Endeavour Energy, Power company in Australia.',
            'OETC': 'Standard specifications of OETC, Power company in Oman.',
            'SEC': 'Standard specifications of SEC, Power company in Saudi Arabia.',
            'Iberdrola': 'Standard specifications of Iberdrola, Power company in Spain.',
            'REE': 'Standard specifications of REE, Power company in Spain.',
        }
        keys = file_name.split('/')
        description = '\n'.join([description_mapping.get(k, "") for k in keys])
        return description

    try:
        parts = []

        prompt_1 = EXTRACT_SUMMARY_PROMPT_1.format(
            file_name=target_image_path,
            description=get_description(target_image_path)
        ).strip()
        parts.append(types.Part.from_text(text=prompt_1))

        for img_path in context_image_paths:
            image_bytes = load_image_as_bytes(img_path)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))

        prompt_2 = EXTRACT_SUMMARY_PROMPT_2.strip()
        parts.append(types.Part.from_text(text=prompt_2))

        image_bytes = load_image_as_bytes(target_image_path)
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
        
        prompt_3 = EXTRACT_SUMMARY_PROMPT_3.strip()
        parts.append(types.Part.from_text(text=prompt_3))

        contents = [
            types.Content(
                role="user",
                parts=parts,
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
            model=EXTRACT_SUMMARY_MODEL,
            contents=contents,
            config=config
        )

        return result.text, None

    except Exception as e:
        return None, f"요약 추출 오류: {e}"


if __name__ == "__main__":
    ###################### 함수동작 TEST ###################
    image_path = "sample.png"
    res = extract_text(image_path=image_path)
    print(res)