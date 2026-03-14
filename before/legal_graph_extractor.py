# -*- coding: utf-8 -*-
"""
Neo4j Legal KG Builder (Async + OpenAI SDK)

ENV (.env):
  # Neo4j
  NEO4J_URI=bolt://localhost:7687
  NEO4J_USERNAME=neo4j
  NEO4J_PASSWORD=password
  NEO4J_DATABASE=neo4j

  # OpenAI
  OPENAI_API_KEY=YOUR_OPENAI_KEY
  OPENAI_MODEL=gpt-4o-mini    # hoặc gpt-4.1-mini / gpt-4o / ...

  # Rate-limit & batching
  LLM_BATCH_SIZE=3
  LLM_RPM_BUDGET=10
  LLM_MAX_RETRIES=4
  LLM_RETRY_BASE_DELAY=2.0
  LLM_CACHE_PATH=kg_cache.sqlite

Run:
  python legal_graph_extractor.py --selftest
  python legal_graph_extractor.py --jsonl laws_chunks_1_MH.jsonl --batch 200
"""

import os
import re
import json
import time
import asyncio
import hashlib
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

# OpenAI SDK (>=1.0)
try:
    from openai import OpenAI
    from openai import APIError, RateLimitError, BadRequestError
except Exception:  # fallback for older package names
    from openai import OpenAI  # type: ignore
    from openai import error as _openai_error  # type: ignore
    APIError = getattr(_openai_error, 'APIError', Exception)
    RateLimitError = getattr(_openai_error, 'RateLimitError', Exception)
    BadRequestError = getattr(_openai_error, 'InvalidRequestError', Exception)

# -------------------- ENV --------------------
load_dotenv()

NEO4J_URI       = os.getenv("NEO4J_URI")
NEO4J_USER      = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD  = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE  = os.getenv("NEO4J_DATABASE", None)

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

LLM_BATCH_SIZE      = int(os.getenv("LLM_BATCH_SIZE", "5"))
LLM_RPM_BUDGET      = max(1, int(os.getenv("LLM_RPM_BUDGET", "10")))
LLM_MAX_RETRIES     = max(0, int(os.getenv("LLM_MAX_RETRIES", "4")))
LLM_RETRY_BASE      = float(os.getenv("LLM_RETRY_BASE_DELAY", "2.0"))
LLM_CACHE_PATH      = os.getenv("LLM_CACHE_PATH", "kg_cache.sqlite")

if not OPENAI_API_KEY:
    raise RuntimeError("Thiếu OPENAI_API_KEY")

# -------------------- Reference Types --------------------
_VALID_REF_TYPES = {
    "internal",    # dẫn chiếu trong cùng văn bản
    "external",    # dẫn chiếu sang văn bản khác
    "cites",       # trích dẫn/viện dẫn
    "amends",      # sửa đổi
    "repeals",     # bãi bỏ
    "clarifies",   # hướng dẫn/làm rõ
}

# -------------------- Text Cleaning Utils --------------------
STOPWORDS = set("""
và hoặc nhưng là được bị của các những về theo tại trong trên dưới từ đến khi nếu thì với bởi do để như không rất đang đã sẽ việc
quy định căn cứ cơ quan tổ chức cá nhân ngày tháng năm theo quy
""".split())
BAD_SUBPHRASES = {
    "hiểm xã", "bảo hiểm xã", "động công dân việt", "động công dân",
    "khoản điều", "điểm khoản", "mức phạt quy"
}

def normalize_vn(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def vn_no_diacritics(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = re.sub(r"[\u0300-\u036f]", "", s)
    s = s.replace("đ", "d").replace("Đ", "D")
    return s

def clean_name(name: str, min_words=2, max_words=12) -> Optional[str]:
    if not isinstance(name, str):
        return None
    n = normalize_vn(name.lower())
    wc = len(n.split())
    if wc < min_words or wc > max_words:
        return None
    if n in STOPWORDS or n in BAD_SUBPHRASES:
        return None
    first = n.split()[0]
    if first in STOPWORDS:
        return None
    n2 = re.sub(r"[^\w\sÀ-ỹĐđ\-]", "", n).strip()
    if not n2:
        return None
    return n2

def dedup_subphrases(terms: List[str], limit: int = 20) -> List[str]:
    acc: List[str] = []
    for t in sorted(terms, key=len, reverse=True):
        if not any((t != x and t in x) for x in acc):
            acc.append(t)
    return acc[:limit]

def clean_references(refs: List[Dict]) -> List[Dict]:
    results = []
    for r in refs or []:
        a = str(r.get("article_no") or "").strip()
        a = re.sub(r"\D", "", a)
        if not a:
            continue
        tdoc = normalize_vn(str(r.get("target_doc_number") or "")) or None
        if tdoc and not re.search(r"^[0-9]{1,4}/[0-9]{4}/[A-Za-zÀ-ỹĐđ\-]+$", tdoc):
            tdoc = None
        # Xác thực type dẫn chiếu
        ref_type = str(r.get("type") or "").strip().lower() or None
        if ref_type and ref_type not in _VALID_REF_TYPES:
            ref_type = None  # Nếu không hợp lệ, set null
        results.append({
          "article_no": a,
          "target_doc_number": tdoc,
          "ref_type": ref_type or "internal"  # Mặc định "internal" nếu null
        })
    seen, uniq = set(), []
    for x in results:
        k = (x["article_no"], x["target_doc_number"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq

# -------------------- Extractor (Batched + Robust) --------------------
@dataclass
class ExtractResult:
    legal_concepts: List[Dict[str, str]]
    events: List[Dict[str, str]]
    actors: List[Dict[str, str]]
    defines: List[Dict[str, str]]
    regulates: List[Dict[str, str]]
    prohibits: List[Dict[str, str]]
    allows: List[Dict[str, str]]
    penalties: List[Dict[str, Optional[str]]]
    references: List[Dict[str, Optional[str]]]

class RateLimiter:
    def __init__(self, rpm: int):
        self.interval = 60.0 / max(1, rpm)
        self._lock = asyncio.Lock()
        self._last = 0.0
    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self.interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

class SQLiteCache:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self._init()
    def _init(self):
        con = sqlite3.connect(self.path)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            con.commit()
        finally:
            con.close()
    def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]:
        if not keys:
            return {}
        con = sqlite3.connect(self.path)
        try:
            qmarks = ",".join(["?"]*len(keys))
            cur = con.execute(f"SELECT k, v FROM kv WHERE k IN ({qmarks})", keys)
            out = {k: None for k in keys}
            for k, v in cur.fetchall():
                out[k] = v
            return out
        finally:
            con.close()
    def put_many(self, items: Dict[str, str]):
        if not items:
            return
        con = sqlite3.connect(self.path)
        try:
            con.executemany("INSERT OR REPLACE INTO kv(k, v) VALUES(?, ?)", list(items.items()))
            con.commit()
        finally:
            con.close()

def _hash_text(s: str) -> str:
    return hashlib.sha1((s or '').encode('utf-8')).hexdigest()

class OpenAIExtractor:
    def __init__(self):
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        self._model = OPENAI_MODEL
        self._limiter = RateLimiter(LLM_RPM_BUDGET)
        self._cache   = SQLiteCache(LLM_CACHE_PATH)
        print(f"[OpenAIExtractor] Ready with model: {self._model}")

    async def aclose(self):
        # OpenAI client does not require explicit close
        return

    @staticmethod
    def _extract_json_maybe(raw: str) -> Dict:
        try:
            return json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw, flags=re.S)
            if not m:
                raise
            return json.loads(m.group(0))

    def _postprocess(self, data: Dict) -> ExtractResult:
        if not isinstance(data, dict):
            # Trả về rỗng nếu schema không hợp lệ
            return ExtractResult(
                legal_concepts=[], events=[], actors=[], defines=[], regulates=[], prohibits=[], allows=[], penalties=[], references=[]
            )
        # Tiết kiệm token: AI trả về string, CPU xử lý name_norm
        def _build_from_strings(str_list: List[str]) -> List[Dict[str, str]]:
            """Chuyển đổi list string thành list {name, name_norm} và làm sạch"""
            out = []
            tmp = []
            for s in (str_list or []):
                nn = clean_name(s)
                if nn:
                    tmp.append(nn)
            tmp = dedup_subphrases(tmp, limit=30)
            for n in tmp:
                out.append({"name": n, "name_norm": vn_no_diacritics(n)})
            return out

        legal_concepts = _build_from_strings(data.get("legal_concepts") or [])
        events         = _build_from_strings(data.get("events") or [])
        actors         = _build_from_strings(data.get("actors") or [])

        def _norm_names(nlist: List[str]) -> List[Dict[str, str]]:
            out = []
            for n in dedup_subphrases([normalize_vn(str(x).lower()) for x in (nlist or [])], limit=60):
                nn = clean_name(n)
                if nn:
                    out.append({"name": nn, "name_norm": vn_no_diacritics(nn)})
            return out

        defines   = _norm_names(data.get("defines") or [])
        regulates = _norm_names(data.get("regulates") or [])
        prohibits = _norm_names(data.get("prohibits") or [])
        allows    = _norm_names(data.get("allows") or [])

        penalties = []
        for p in (data.get("penalties") or []):
            name = clean_name(p.get("name") or "")
            if not name:
                continue
            pn = {
                "name": name,
                "name_norm": vn_no_diacritics(name),
                "amount_min": re.sub(r"\D", "", str(p.get("amount_min") or "")) or None,
                "amount_max": re.sub(r"\D", "", str(p.get("amount_max") or "")) or None,
                "unit": normalize_vn(p.get("unit") or "") or None,
                "notes": normalize_vn(p.get("notes") or "") or None,
                "event": None,
                "event_norm": None,
            }
            if p.get("event"):
                en = clean_name(p["event"], min_words=2, max_words=12)
                pn["event"] = en
                pn["event_norm"] = vn_no_diacritics(en) if en else None
            penalties.append(pn)

        references = clean_references(data.get("references") or [])

        return ExtractResult(
            legal_concepts=legal_concepts,
            events=events,
            actors=actors,
            defines=defines,
            regulates=regulates,
            prohibits=prohibits,
            allows=allows,
            penalties=penalties,
            references=references,
        )

    async def extract_batch(self, items: List[Tuple[str, str]]) -> Dict[str, ExtractResult]:
        # 1) Cache lookup
        keys = [_hash_text(c or "") for _, c in items]
        cached_map = self._cache.get_many(keys)
        id_to_key = {iid: k for (iid, _), k in zip(items, keys)}

        pending: List[Tuple[str, str]] = []
        results: Dict[str, ExtractResult] = {}

        for (iid, content) in items:
            k = id_to_key[iid]
            cached_val = cached_map.get(k)
            if cached_val:
                try:
                    data = json.loads(cached_val)
                    results[iid] = self._postprocess(data)
                    continue
                except Exception:
                    pass
            pending.append((iid, content))

        if not pending:
            return results

        # 2) Build payload
        input_payload = {"items": [{"id": iid, "content": (txt or "")} for (iid, txt) in pending]}
        system_prompt = (
            "Bạn là chuyên gia pháp luật Việt Nam. Với mỗi item trong 'items', trích xuất theo schema CHÍNH XÁC.\n"
            "Chỉ trả JSON hợp lệ:\n{\n \"results\": [ { \"id\": string, \"data\": {\n"
            " \"legal_concepts\": [string], \"events\": [string], \"actors\": [string], \n"
            " \"defines\": [string], \"regulates\": [string], \"prohibits\": [string], \"allows\": [string], \n"
            " \"penalties\": [{\"name\": string, \"amount_min\": string|null, \"amount_max\": string|null, \"unit\": string|null, \"notes\": string|null, \"event\": string|null}],\n"
            " \"references\": [{\"article_no\": string, \"target_doc_number\": string|null, \"type\": \"internal\"|\"external\"|\"cites\"|\"amends\"|\"repeals\"|\"clarifies\" hoặc chuỗi mô tả; cho null nếu không chắc}]\n } } ] }\n"
            "QUY TẮC:\n"
            "1. Chỉ cụm danh từ đầy đủ (2–12 từ), cấm subphrase như 'hiểm xã', 'bảo hiểm xã', 'động công dân'.\n"
            "2. Loại dẫn chiếu (type ở references): chọn từ {internal, external, cites, amends, repeals, clarifies} hoặc mô tả ngắn; null nếu không xác định.\n"
            "KHÔNG GIẢI THÍCH, chỉ JSON."
        )
        user_payload_text = json.dumps({"instruction": system_prompt, "input": input_payload}, ensure_ascii=False)

        # 3) Call OpenAI with retries & rate limit
        raw_text = None
        last_err = None

        for attempt in range(LLM_MAX_RETRIES + 1):
            await self._limiter.acquire()
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_payload_text},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},  # enforce JSON if model supports
                )
                raw_text = (resp.choices[0].message.content or "").strip()
                if raw_text:
                    break
                raise RuntimeError("Empty response text")
            except RateLimitError as e:
                delay = min(60, int(LLM_RETRY_BASE * (2 ** attempt)))
                print(f"[OpenAIExtractor] 429 RateLimit → sleep {delay}s")
                await asyncio.sleep(delay)
                last_err = e
                continue
            except BadRequestError as e:
                # Try again WITHOUT response_format enforcement
                try:
                    resp = self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": user_payload_text},
                        ],
                        temperature=0,
                    )
                    raw_text = (resp.choices[0].message.content or "").strip()
                    if raw_text:
                        break
                    raise RuntimeError("Empty response text (plain)")
                except Exception as e2:
                    delay = min(60, int(LLM_RETRY_BASE * (2 ** attempt)))
                    print(f"[OpenAIExtractor] 400/BadRequest fallback failed → sleep {delay}s: {e2}")
                    await asyncio.sleep(delay)
                    last_err = e2
                    continue
            except APIError as e:
                delay = min(60, int(LLM_RETRY_BASE * (2 ** attempt)))
                print(f"[OpenAIExtractor] APIError → sleep {delay}s")
                await asyncio.sleep(delay)
                last_err = e
                continue
            except Exception as e:
                delay = min(60, int(LLM_RETRY_BASE * (2 ** attempt)))
                print(f"[OpenAIExtractor] Runtime error → sleep {delay}s: {e}")
                await asyncio.sleep(delay)
                last_err = e
                continue
        else:
            raise RuntimeError(f"Không gọi được OpenAI model. Lỗi cuối: {last_err}")

        # 4) Parse JSON
        try:
            data = self._extract_json_maybe(raw_text)
        except Exception:
            raise RuntimeError(f"Model không trả JSON hợp lệ:\n{raw_text}")

        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise RuntimeError(f"JSON không có 'results' dạng list: {raw_text[:300]}…")

        # 5) Map back + cache
        cache_writes: Dict[str, str] = {}
        for entry in data.get("results", []):
            iid = entry.get("id")
            d = entry.get("data", {})
            if iid is None:
                continue
            try:
                results[iid] = self._postprocess(d)
                k = id_to_key.get(iid)
                if k:
                    cache_writes[k] = json.dumps(d, ensure_ascii=False)
            except Exception as ex:
                print(f"[OpenAIExtractor] WARNING postprocess failed for id={iid}: {ex}")
        if cache_writes:
            self._cache.put_many(cache_writes)

        for iid, _ in pending:
            if iid not in results:
                results[iid] = ExtractResult(
                    legal_concepts=[], events=[], actors=[],
                    defines=[], regulates=[], prohibits=[], allows=[],
                    penalties=[], references=[]
                )
        return results

# -------------------- Neo4j schema --------------------
CONSTRAINTS = [
    "CREATE CONSTRAINT doc_key_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_key IS UNIQUE",
    "CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE",
    "CREATE CONSTRAINT clause_key_unique IF NOT EXISTS FOR (k:Clause) REQUIRE (k.article_id, k.clause_no) IS UNIQUE",
    "CREATE CONSTRAINT point_key_unique IF NOT EXISTS FOR (p:Point) REQUIRE (p.article_id, p.clause_no, p.point_letter) IS UNIQUE",
    "CREATE CONSTRAINT span_id_unique IF NOT EXISTS FOR (s:Span) REQUIRE s.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT legalconcept_norm_unique IF NOT EXISTS FOR (c:LegalConcept) REQUIRE c.name_norm IS UNIQUE",
    "CREATE CONSTRAINT actor_norm_unique IF NOT EXISTS FOR (a:Actor) REQUIRE a.name_norm IS UNIQUE",
    "CREATE CONSTRAINT event_norm_unique IF NOT EXISTS FOR (e:Event) REQUIRE e.name_norm IS UNIQUE",
    "CREATE CONSTRAINT penalty_norm_unique IF NOT EXISTS FOR (p:Penalty) REQUIRE p.name_norm IS UNIQUE",
]
CONSTRAINTS += [
    "CREATE INDEX event_name IF NOT EXISTS FOR (e:Event) ON (e.name_norm)",
    "CREATE INDEX concept_name IF NOT EXISTS FOR (c:LegalConcept) ON (c.name_norm)",
    "CREATE INDEX span_order IF NOT EXISTS FOR (s:Span) ON (s.order_index)",
]

CYPHER_BATCH_UPSERT = """
UNWIND $rows AS row

MERGE (d:Document {doc_key: row.doc_key})
  ON CREATE SET d.doc_id = row.doc_id, d.doc_number = row.doc_number,
                d.title = row.doc_title, d.type = row.doc_type, d.year = row.year

MERGE (a:Article {article_id: row.article_id})
  ON CREATE SET a.no = row.article_no, a.title = row.article_title
MERGE (d)-[:HAS_ARTICLE]->(a)

FOREACH (_ IN CASE WHEN row.clause_no IS NULL THEN [] ELSE [1] END |
  MERGE (k:Clause {article_id: row.article_id, clause_no: toString(row.clause_no)})
  MERGE (a)-[:HAS_CLAUSE]->(k)
)

FOREACH (_ IN CASE WHEN row.point_letter IS NULL OR row.clause_no IS NULL THEN [] ELSE [1] END |
  MERGE (pt:Point {article_id: row.article_id, clause_no: toString(row.clause_no), point_letter: toString(row.point_letter)})
  MERGE (k:Clause {article_id: row.article_id, clause_no: toString(row.clause_no)})
  MERGE (k)-[:HAS_POINT]->(pt)
)

MERGE (s:Span {chunk_id: row.chunk_id})
  ON CREATE SET s.content = row.content, s.order_index = row.order_index,
                s.chunk_part = row.chunk_part, s.chapter = row.chapter, s.section = row.section

FOREACH (_ IN CASE WHEN row.point_letter IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pt:Point {article_id: row.article_id, clause_no: row.clause_no, point_letter: row.point_letter})
  MERGE (s)-[:BELONGS_TO]->(pt)
)
FOREACH (_ IN CASE WHEN row.point_letter IS NULL AND row.clause_no IS NOT NULL THEN [1] ELSE [] END |
  MERGE (k:Clause {article_id: row.article_id, clause_no: row.clause_no})
  MERGE (s)-[:BELONGS_TO]->(k)
)
FOREACH (_ IN CASE WHEN row.point_letter IS NULL AND row.clause_no IS NULL THEN [1] ELSE [] END |
  MERGE (a:Article {article_id: row.article_id})
  MERGE (s)-[:BELONGS_TO]->(a)
)

FOREACH (lc IN row.legal_concepts |
  MERGE (c:LegalConcept {name_norm: lc.name_norm})
    ON CREATE SET c.name = lc.name
  MERGE (a)-[:DEFINES]->(c)
)

FOREACH (ev IN row.events |
  MERGE (e:Event {name_norm: ev.name_norm})
    ON CREATE SET e.name = ev.name
)

FOREACH (ac IN row.actors |
  MERGE (r:Actor {name_norm: ac.name_norm})
    ON CREATE SET r.name = ac.name
)

FOREACH (ev IN row.events |
  MERGE (e:Event {name_norm: ev.name_norm})
  MERGE (s)-[:MENTIONS]->(e)
)
FOREACH (ac IN row.actors |
  MERGE (r:Actor {name_norm: ac.name_norm})
  MERGE (s)-[:MENTIONS]->(r)
)

FOREACH (ac IN row.actors |
  MERGE (r:Actor {name_norm: ac.name_norm})
  MERGE (s)-[:INVOLVES]->(r)
)

FOREACH (name IN row.regulates |
  MERGE (e:Event {name_norm: name.name_norm})
    ON CREATE SET e.name = name.name
  MERGE (a)-[:REGULATES]->(e)
)
FOREACH (name IN row.prohibits |
  MERGE (e:Event {name_norm: name.name_norm})
    ON CREATE SET e.name = name.name
  MERGE (a)-[:PROHIBITS]->(e)
)
FOREACH (name IN row.allows |
  MERGE (e:Event {name_norm: name.name_norm})
    ON CREATE SET e.name = name.name
  MERGE (a)-[:ALLOWS]->(e)
)

FOREACH (p IN row.penalties |
  MERGE (pn:Penalty {name_norm: p.name_norm})
    ON CREATE SET pn.name = p.name
  SET pn.amount_min = p.amount_min, pn.amount_max = p.amount_max,
      pn.unit = p.unit, pn.notes = p.notes
  MERGE (a)-[:PENALIZES]->(pn)
  FOREACH (_ IN CASE WHEN p.event_norm IS NULL THEN [] ELSE [1] END |
    MERGE (e:Event {name_norm: p.event_norm})
      ON CREATE SET e.name = p.event
    MERGE (e)-[:HAS_PENALTY]->(pn)
  )
)

FOREACH (rf IN row.references |
  MERGE (td:Document {doc_key: coalesce(rf.target_doc_key, row.doc_key)})
  MERGE (ta:Article {article_id: coalesce(rf.target_doc_key, row.doc_key) + '_D' + rf.article_no})
    ON CREATE SET ta.no = rf.article_no
  MERGE (td)-[:HAS_ARTICLE]->(ta)
  MERGE (a)-[ref_rel:REFERENCES]->(ta)
  SET ref_rel.type = rf.type
)
"""

# -------------------- Builder --------------------
@dataclass
class Row:
    doc_key: str
    doc_id: Optional[str]
    doc_number: Optional[str]
    doc_title: Optional[str]
    doc_type: Optional[str]
    year: Optional[int]

    article_id: str
    article_no: str
    article_title: Optional[str]

    clause_no: Optional[str]
    point_letter: Optional[str]

    chunk_id: str
    chunk_part: Optional[int]
    order_index: Optional[int]
    content: str
    chapter: Optional[str]
    section: Optional[str]

    legal_concepts: List[Dict[str, str]]
    events: List[Dict[str, str]]
    actors: List[Dict[str, str]]
    regulates: List[Dict[str, str]]
    prohibits: List[Dict[str, str]]
    allows: List[Dict[str, str]]
    penalties: List[Dict[str, Optional[str]]]
    references: List[Dict[str, Optional[str]]]

def _doc_key(doc_type: Optional[str], doc_number: Optional[str], doc_id: Optional[str]) -> str:
    if doc_type and doc_number:
        return f"{doc_type.lower()}:{doc_number}".strip()
    if doc_number:
        return f"doc:{doc_number}".strip()
    if doc_id:
        return f"id:{doc_id}".strip()
    raise ValueError("Document must have doc_number or doc_id")

class LegalGraphIngest:
    def __init__(self, jsonl_path: str, batch_size: int = 200):
        self.jsonl_path = jsonl_path
        self.batch_size = max(10, batch_size)
        self.driver = None
        if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
            self.driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.extractor = OpenAIExtractor()
        self.rows_lock = asyncio.Lock()

    async def close(self):
        await self.extractor.aclose()
        if self.driver:
            await self.driver.close()

    async def init_constraints(self):
        if not self.driver:
            return
        async with self.driver.session(database=NEO4J_DATABASE) as s:
            for q in CONSTRAINTS:
                await s.run(q)

    def _make_row(self, rec: Dict, ext: ExtractResult) -> Row:
        md = rec["metadata"]
        di = md["doc_info"]
        h  = md["hierarchy"]

        dkey = _doc_key(di.get("doc_type"), di.get("doc_number"), di.get("doc_id"))
        article_no = str(h.get("article_no") or "")
        article_id = f"{dkey}_D{article_no}"

        refs = []
        for r in ext.references:
            tdoc = r.get("target_doc_number")
            target_doc_key = _doc_key(None, tdoc, None) if tdoc else None
            refs.append({
                "article_no": r["article_no"],
                "target_doc_key": target_doc_key,
                "type": r.get("ref_type", "refers")
            })

        return Row(
            doc_key=dkey,
            doc_id=di.get("doc_id"),
            doc_number=di.get("doc_number"),
            doc_title=di.get("title"),
            doc_type=di.get("doc_type"),
            year=di.get("year"),

            article_id=article_id,
            article_no=article_no,
            article_title=h.get("article_title"),

            clause_no=h.get("clause_no"),
            point_letter=h.get("point"),

            chunk_id=rec["id"],
            chunk_part=int(h.get("chunk_part") or 1),
            order_index=int(md.get("order_index") or 0),
            content=rec.get("content") or "",
            chapter=h.get("chapter"),
            section=h.get("section"),

            legal_concepts=ext.legal_concepts,
            events=ext.events,
            actors=ext.actors,
            regulates=ext.regulates,
            prohibits=ext.prohibits,
            allows=ext.allows,
            penalties=ext.penalties,
            references=refs,
        )

    async def _merge_batch(self, tx, rows: List[Dict]):
        await tx.run(CYPHER_BATCH_UPSERT, rows=rows)

    async def run(self):
        await self.init_constraints()
        print(f"🚀 Start ingest (db_batch={self.batch_size}, llm_batch={LLM_BATCH_SIZE})")

        rows_buf: List[Dict] = []
        processed = 0

        async def flush():
            nonlocal rows_buf, processed
            if not rows_buf:
                return
            if self.driver:
                async with self.driver.session(database=NEO4J_DATABASE) as session:
                    await session.execute_write(self._merge_batch, rows_buf)
                processed += len(rows_buf)
                print(f"  → wrote +{len(rows_buf)} rows (total {processed})")
            else:
                print(f"  (dry-run) prepared +{len(rows_buf)} rows")
            rows_buf = []

        pending_llm: List[Tuple[str, Dict]] = []  # (chunk_id, rec)

        async def process_pending_llm():
            nonlocal rows_buf
            if not pending_llm:
                return
            items = [(cid, rec.get("content") or "") for cid, rec in pending_llm]
            ext_map = await self.extractor.extract_batch(items)
            for cid, rec in pending_llm:
                ext = ext_map.get(cid)
                if not ext:
                    ext = ExtractResult(
                        legal_concepts=[], events=[], actors=[],
                        defines=[], regulates=[], prohibits=[], allows=[],
                        penalties=[], references=[]
                    )
                row = self._make_row(rec, ext)
                rows_buf.append(row.__dict__)
            pending_llm.clear()

            if len(rows_buf) >= self.batch_size:
                await flush()

        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                cid = rec.get("id")
                if not cid:
                    continue
                pending_llm.append((cid, rec))
                if len(pending_llm) >= LLM_BATCH_SIZE:
                    await process_pending_llm()

            await process_pending_llm()
            await flush()

        print("✅ Done.")
        await self.close()

# -------------------- Self-test --------------------
SAMPLE_ITEMS = [
    {"id": "41/2024/QH15_D1_P1", "metadata": {"doc_info": {"doc_id": "41_2024_QH15", "doc_number": "41/2024/QH15", "doc_type": "LAW", "issuing_body": "Quốc hội", "year": 2024, "title": "LUẬT BẢO HIỂM XÃ HỘI", "effective_date": None}, "hierarchy": {"chapter": "Chương I NHỮNG QUY ĐỊNH CHUNG", "section": None, "article_no": "1", "article_title": "Phạm vi điều chỉnh", "clause_no": None, "point": None, "chunk_part": 1}, "order_index": 1}, "content": "Điều 1. Phạm vi điều chỉnh \nLuật này quy định về quyền, trách nhiệm của cơ quan, tổ chức, cá nhân đối với bảo hiểm xã hội và tổ chức thực hiện bảo hiểm xã hội; trợ cấp hưu trí xã hội; đăng ký tham gia và quản lý thu, đóng bảo hiểm xã hội; các chế độ, chính sách bảo hiểm xã hội bắt buộc, bảo hiểm xã hội tự nguyện; quỹ bảo hiểm xã hội; bảo hiểm hưu trí bổ sung; khiếu nại, tố cáo và xử lý vi phạm về bảo hiểm xã hội; quản lý nhà nước về bảo hiểm xã hội."},
    {"id": "41/2024/QH15_D9_K1_P1", "metadata": {"doc_info": {"doc_id": "41_2024_QH15", "doc_number": "41/2024/QH15", "doc_type": "LAW", "issuing_body": "Quốc hội", "year": 2024, "title": "LUẬT BẢO HIỂM XÃ HỘI", "effective_date": None}, "hierarchy": {"chapter": "Chương I NHỮNG QUY ĐỊNH CHUNG", "section": None, "article_no": "9", "article_title": "Các hành vi bị nghiêm cấm", "clause_no": "1", "point": None, "chunk_part": 1}, "order_index": 79}, "content": "Chậm đóng, trốn đóng bảo hiểm xã hội bắt buộc, bảo hiểm thất nghiệp."},
    {"id": "84/2015/QH13_D28_K1_P1", "metadata": {"doc_info": {"doc_id": "84_2015_QH13", "doc_number": "84/2015/QH13", "doc_type": "LAW", "issuing_body": "Quốc hội", "year": 2015, "title": "LUẬT AN TOÀN, VỆ SINH LAO ĐỘNG", "effective_date": None}, "hierarchy": {"chapter": "Chương II CÁC BIỆN PHÁP PHÒNG, CHỐNG CÁC YẾU TỐ NGUY HIỂM, YẾU TỐ CÓ HẠI CHO NGƯỜI LAO ĐỘNG", "section": "Mục 4. QUẢN LÝ MÁY, THIẾT BỊ, VẬT TƯ, CHẤT CÓ YÊU CẦU NGHIÊM NGẶT VỀ AN TOÀN, VỆ SINH LAO ĐỘNG", "article_no": "28", "article_title": "Máy, thiết bị, vật tư, chất có yêu cầu nghiêm ngặt về an toàn, vệ sinh lao động", "clause_no": "1", "point": None, "chunk_part": 1}, "order_index": 154}, "content": "Máy, thiết bị, vật tư, chất có yêu cầu nghiêm ngặt về an toàn, vệ sinh lao động là máy, thiết bị, vật tư, chất trong điều kiện lưu giữ, vận chuyển, bảo quản, sử dụng hợp lý, đúng mục đích và đúng theo hướng dẫn của nhà sản xuất nhưng trong quá trình lao động, sản xuất vẫn tiềm ẩn khả năng xảy ra tai nạn lao động, bệnh nghề nghiệp, gây hậu quả nghiêm trọng đến sức khỏe, tính mạng con người."}
]

async def selftest():
    print("[SELFTEST] Batching 3 sample items in ONE request…")
    gx = OpenAIExtractor()
    items = [(x["id"], x.get("content") or "") for x in SAMPLE_ITEMS]
    res = await gx.extract_batch(items)
    for iid, out in res.items():
        print("---", iid)
        print(json.dumps({
            "legal_concepts": out.legal_concepts,
            "events": out.events,
            "actors": out.actors,
            "defines": out.defines,
            "regulates": out.regulates,
            "prohibits": out.prohibits,
            "allows": out.allows,
            "penalties": out.penalties,
            "references": out.references,
        }, ensure_ascii=False, indent=2))

# -------------------- CLI --------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Neo4j Legal KG builder (OpenAI, batched, rate-limited)")
    p.add_argument("--jsonl", help="Path to JSONL (parser output)")
    p.add_argument("--batch", type=int, default=int(os.getenv("BATCH_SIZE", "200")), help="DB batch size (rows per write)")
    p.add_argument("--selftest", action="store_true", help="Run a single batched call on embedded samples (no DB write)")
    args = p.parse_args()

    if args.selftest:
        asyncio.run(selftest())
    else:
        if not args.jsonl:
            raise SystemExit("--jsonl is required unless --selftest is used")
        app = LegalGraphIngest(jsonl_path=args.jsonl, batch_size=args.batch)
        asyncio.run(app.run())
