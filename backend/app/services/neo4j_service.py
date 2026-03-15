# app/services/neo4j_service.py
from typing import List, Dict, Any
from app.core.neo4j import get_driver, get_db

class Neo4jService:

    async def expand_from_articles(self, article_ids: List[str], limit_spans: int = 30) -> Dict[str, List[Dict[str, Any]]]:
        """
        Input: article_ids = ["docKey_D12", ...]
        Return: {
          "owner_spans": [...],
          "references": [...],
          "semantics": {"concepts":[...], "events":[...], "actors":[...], "penalties":[...]},
          "mention_spans": [...]
        }
        """
        if not article_ids:
            return {"owner_spans":[], "references":[], "semantics":{"concepts":[],"events":[],"actors":[],"penalties":[]}, "mention_spans":[]}

        q_owner = """
        UNWIND $article_ids AS aid
        MATCH (a:Article {article_id: aid})
        OPTIONAL MATCH (s1:Span)-[:BELONGS_TO]->(:Point  {article_id: a.article_id})
        WITH a, aid, collect(s1)[..$limit] AS s1s
        OPTIONAL MATCH (s2:Span)-[:BELONGS_TO]->(:Clause {article_id: a.article_id})
        WITH a, aid, s1s, collect(s2)[..$limit] AS s2s
        OPTIONAL MATCH (s3:Span)-[:BELONGS_TO]->(a)
        WITH a, aid, s1s, s2s, collect(s3)[..$limit] AS s3s
        WITH a, aid, s1s + s2s + s3s AS allSpans
        UNWIND allSpans AS s
        WITH a, aid, collect(DISTINCT s)[..$limit] AS spans
        RETURN a.article_id AS article_id,
            [x IN spans | {chunk_id:x.chunk_id, content:x.content, order_index:x.order_index}] AS spans
        """

        q_refs = """
        UNWIND $article_ids AS aid
        MATCH (a:Article {article_id: aid})-[:REFERENCES]->(b:Article)<-[:HAS_ARTICLE]-(d:Document)
        RETURN aid AS src, b.article_id AS dst, d.doc_key AS dst_doc_key
        """

        q_sem = """
        UNWIND $article_ids AS aid
        MATCH (a:Article {article_id: aid})
        OPTIONAL MATCH (a)-[:DEFINES]->(c:LegalConcept)
        WITH aid, a, collect(DISTINCT {name:c.name, name_norm:c.name_norm}) AS concepts
        OPTIONAL MATCH (a)-[:REGULATES|PROHIBITS|ALLOWS]->(ev:Event)
        WITH aid, a, concepts, collect(DISTINCT {name:ev.name, name_norm:ev.name_norm}) AS events
        OPTIONAL MATCH (a)-[:PENALIZES]->(pn:Penalty)
        WITH aid, concepts, events,
            collect(DISTINCT {name:pn.name, name_norm:pn.name_norm, amount_min:pn.amount_min, amount_max:pn.amount_max, unit:pn.unit}) AS penalties
        RETURN aid AS article_id, concepts, events, penalties
        """


        q_mentions = """
        UNWIND $article_ids AS aid
        MATCH (s:Span)-[:BELONGS_TO]->(:Article {article_id: aid})
        OPTIONAL MATCH (s)-[:MENTIONS]->(e:Event)
        OPTIONAL MATCH (s)-[:MENTIONS]->(r:Actor)
        WITH aid, s,
            collect(DISTINCT {type:'Event', name:e.name, name_norm:e.name_norm}) +
            collect(DISTINCT {type:'Actor', name:r.name, name_norm:r.name_norm}) AS ms
        WHERE size(ms) > 0
        RETURN aid AS article_id,
            {chunk_id:s.chunk_id, content:s.content, mentions: ms} AS span_mention
        """


        drv = get_driver()
        async with drv.session(**get_db()) as sess:
            owner_res = await sess.run(q_owner, {"article_ids": article_ids, "limit": limit_spans})
            owner_map = {r["article_id"]: r["spans"] for r in await owner_res.data()}

            ref_res = await sess.run(q_refs, {"article_ids": article_ids})
            refs = [dict(r) for r in await ref_res.data()]

            sem_res = await sess.run(q_sem, {"article_ids": article_ids})
            sem_map = {r["article_id"]:
                       {"concepts": r["concepts"], "events": r["events"], "penalties": r["penalties"]}
                       for r in await sem_res.data()}

            men_res = await sess.run(q_mentions, {"article_ids": article_ids})
            mention_map = {}
            for r in await men_res.data():
                mention_map.setdefault(r["article_id"], []).append(r["span_mention"])

        # Flatten
        owner_spans = []
        for aid, spans in owner_map.items():
            for s in spans:
                owner_spans.append({"article_id": aid, **s})

        mention_spans = []
        for aid, arr in mention_map.items():
            for s in arr:
                s["article_id"] = aid
                mention_spans.append(s)

        # Build semantics union
        sem_concepts, sem_events, sem_penalties = [], [], []
        for aid, sem in sem_map.items():
            for c in sem.get("concepts", []): sem_concepts.append(c | {"article_id": aid})
            for e in sem.get("events", []):   sem_events.append(e | {"article_id": aid})
            for p in sem.get("penalties", []):sem_penalties.append(p | {"article_id": aid})

        return {
            "owner_spans": owner_spans,
            "references": refs,
            "semantics": {"concepts": sem_concepts, "events": sem_events, "actors": [], "penalties": sem_penalties},
            "mention_spans": mention_spans
        }

    async def article_ids_from_qdrant_hits(self, hits: List[Any]) -> List[str]:
        """Map Qdrant payload -> article_id used in graph."""
        ids = []
        for h in hits or []:
            md = h.payload.get("metadata", {})
            di = md.get("doc_info", {})
            hrc = md.get("hierarchy", {})
            # doc_key giống lúc ingest graph: dùng doc_number nếu có, else doc_id
            doc_number = di.get("doc_number")
            doc_id = di.get("doc_id")
            doc_key = (doc_number or doc_id or "UNKNOWN").strip()
            article_no = str(hrc.get("article_no") or "")
            ids.append(f"{doc_key}_D{article_no}")
        # unique & keep order
        seen = set(); out=[]
        for x in ids:
            if x not in seen:
                seen.add(x); out.append(x)
        return out

neo4j_service = Neo4jService()