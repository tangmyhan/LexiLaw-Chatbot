# -*- coding: utf-8 -*-

"""
LLM Legal Graph Extractor
Extract structured legal information from law text.

Output schema:
{
 "legal_concepts": [],
 "actors": [],
 "events": [],
 "penalties": [],
 "relations":[
   {"type":"REGULATES","event":"tai nạn lao động"},
 ],
 "references":[
   {"doc_id":"84_2015_QH13","article":"10"}
 ]
}
"""

import os
import json
import asyncio
import re
from dataclasses import dataclass
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

USE_GEMINI = bool(GEMINI_API_KEY)


@dataclass
class ExtractionResult:
    concepts: List[str]
    actors: List[str]
    events: List[str]
    penalties: List[str]
    relations: List[Dict]
    references: List[Dict]


def normalize_text(text: str):
    text = text.lower()
    text = re.sub(r"[^\w\sà-ỹđ]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class GeminiLegalExtractor:

    def __init__(self):

        if USE_GEMINI:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(GEMINI_MODEL)

    def build_prompt(self, content: str):

        return f"""
Bạn là chuyên gia luật Việt Nam.

Phân tích đoạn luật sau và trích xuất thông tin pháp lý.

Trả JSON với schema:

{{
 "legal_concepts": [],
 "actors": [],
 "events": [],
 "penalties": [],
 "relations":[
    {{"type":"DEFINES|REGULATES|PROHIBITS|ALLOWS|PENALIZES","event":""}}
 ],
 "references":[
    {{"doc_id":"","article":""}}
 ]
}}

Chỉ trả JSON hợp lệ.

Nội dung luật:

{content}
"""

    def _infer_sync(self, content):

        try:

            prompt = self.build_prompt(content)

            resp = self.model.generate_content(prompt)

            text = resp.text.strip()

            try:
                data = json.loads(text)
            except:

                m = re.search(r"\{.*\}", text, re.S)

                if m:
                    data = json.loads(m.group())

                else:
                    data = {}

            return ExtractionResult(
                concepts=data.get("legal_concepts", []),
                actors=data.get("actors", []),
                events=data.get("events", []),
                penalties=data.get("penalties", []),
                relations=data.get("relations", []),
                references=data.get("references", []),
            )

        except:

            return ExtractionResult([], [], [], [], [], [])

    async def extract(self, content):

        if not USE_GEMINI:

            return ExtractionResult([], [], [], [], [], [])

        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(None, self._infer_sync, content)
