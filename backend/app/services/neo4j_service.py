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
        ids = []
        for h in hits or []:
            md = h.payload.get("metadata", {})
            di = md.get("doc_info", {})
            hrc = md.get("hierarchy", {})
            
            # Lấy doc_number 
            doc_number = di.get("doc_number")
            doc_id = di.get("doc_id")
            doc_key = (doc_number or doc_id or "UNKNOWN").strip()
            
            article_no = str(hrc.get("article_no") or "")
            
            # Thêm tiền tố 'law:' để khớp với DB
            full_id = f"law:{doc_key}_D{article_no}"
            ids.append(full_id)
            
        return list(set(ids))

    # async def get_graph_visualization_data(self, article_ids: List[str]) -> Dict[str, Any]:
    #     print(f"Getting graph data for article_ids: {article_ids}")
    #     if not article_ids:
    #         return {"nodes": [], "edges": []}

    #     # Query lấy Article và mạng lưới liên kết lân cận (Clause, Document, Concept, Penalty, vv.)
    #     query = """
    #     UNWIND $ids AS aid
    #     MATCH (n:Article {article_id: aid})
    #     OPTIONAL MATCH (n)-[r]-(m)
    #     RETURN n, r, m
    #     """
        
    #     drv = get_driver()
    #     nodes = {}
    #     edges = []

    #     async with drv.session(**get_db()) as sess:
    #         res = await sess.run(query, {"ids": article_ids})
    #         async for record in res:
    #             n = record["n"]
    #             # Convert Neo4j Node to dict
    #             n_props = dict(n)
    #             n_id = n_props.get("article_id")
                
    #             # Lưu node nguồn
    #             if n_id not in nodes:
    #                 nodes[n_id] = {
    #                     "id": n_id,
    #                     "label": f"Điều {n_props.get('no', n_id)}", # Hiển thị 'Điều X'
    #                     "type": "Article",
    #                     "properties": n_props
    #                 }
                
    #             # Lưu node đích và cạnh
    #             if record["m"] and record["r"]:
    #                 m = record["m"]
    #                 r = record["r"]
                    
    #                 # Convert Neo4j Node to dict
    #                 m_props = dict(m)
    #                 m_id = m_props.get("article_id") or m_props.get("name_norm") or str(hash(str(m_props)))
                    
    #                 if m_id not in nodes:
    #                     # Xác định type dựa trên labels
    #                     m_labels = list(m.labels) if hasattr(m, 'labels') else []
    #                     m_type = m_labels[0] if m_labels else "Related"
                        
    #                     nodes[m_id] = {
    #                         "id": m_id,
    #                         "label": m_props.get("name") or m_props.get("no") or m_id,
    #                         "type": m_type,
    #                         "properties": m_props
    #                     }
                    
    #                 # Determine true edge direction
    #                 is_n_source = (r.start_node.id == n.id)
    #                 edge_source = n_id if is_n_source else m_id
    #                 edge_target = m_id if is_n_source else n_id

    #                 edges.append({
    #                     "source": edge_source,
    #                     "target": edge_target,
    #                     "label": r.type
    #                 })

    #     result = {"nodes": list(nodes.values()), "edges": edges}
    #     print(f"Graph data result: {len(result['nodes'])} nodes, {len(result['edges'])} edges")
    #     return result

    async def get_graph_visualization_data(self, article_ids: List[str]) -> Dict[str, Any]:
        """
        Truy vấn toàn bộ cấu trúc phân cấp và thực thể liên quan từ danh sách Article IDs.
        """
        if not article_ids:
            return {"nodes": [], "edges": []}

        # Lấy driver và cấu hình db từ helper
        drv = get_driver()
        db_config = get_db()
        db_name = db_config.get("database")

        query = """
        UNWIND $ids AS aid
        MATCH (a:Article {article_id: aid})
        
        // 1. Lấy toàn bộ cây cấu trúc: Document -> Article -> Clause -> Point
        OPTIONAL MATCH p_tree = (doc:Document)-[:HAS_ARTICLE]->(a)-[:HAS_CLAUSE*0..1]->(c:Clause)-[:HAS_POINT*0..1]->(pt:Point)
        
        // 2. Lấy các liên kết tham chiếu (REFERENCES) giữa các Article
        OPTIONAL MATCH p_ref = (a)-[r_ref:REFERENCES]-(other:Article)
        
        // 3. Lấy các thực thể Semantic nối vào các node cấu trúc
        WITH a, p_tree, p_ref
        OPTIONAL MATCH (structural_node)-[r_sem]->(sem)
        WHERE (structural_node IN nodes(p_tree)) 
        AND (sem:LegalConcept OR sem:Actor OR sem:Event OR sem:Penalty)
        
        // 4. Lấy các Span thuộc về các node cấu trúc
        OPTIONAL MATCH (s:Span)-[r_span:BELONGS_TO]->(target)
        WHERE target IN nodes(p_tree)

        WITH collect(p_tree) + collect(p_ref) AS paths, 
            collect({s: startNode(r_sem), r: r_sem, t: endNode(r_sem)}) + 
            collect({s: s, r: r_span, t: target}) AS rels
        
        RETURN paths, rels
        """

        nodes = {}
        edges = []

        def add_node(node):
            if node is None: return None
            # Trích xuất ID: ưu tiên article_id, name_norm, hoặc ID nội bộ của Neo4j
            n_props = dict(node)
            node_id = n_props.get("article_id") or n_props.get("name_norm") or n_props.get("chunk_id") or str(node.id)
            
            if node_id not in nodes:
                labels = list(node.labels)
                primary_label = labels[0] if labels else "Default"
                
                nodes[node_id] = {
                    "id": node_id,
                    "label": n_props.get("no") or n_props.get("name") or n_props.get("content") or node_id,
                    "type": primary_label,
                    "nodeType": primary_label,
                    "properties": n_props
                }
            return node_id

        # Sử dụng biến 'drv' và 'db_name' đã khởi tạo ở trên
        async with drv.session(database=db_name) as session:
            result = await session.run(query, ids=article_ids)
            record = await result.single()

            if record:
                # Parse các đường đi (Paths)
                if record["paths"]:
                    for path in record["paths"]:
                        if path is None: continue
                        for rel in path.relationships:
                            s_id = add_node(rel.start_node)
                            t_id = add_node(rel.end_node)
                            edges.append({
                                "source": s_id,
                                "target": t_id,
                                "label": rel.type
                            })

                # Parse các quan hệ rời (Rels)
                if record["rels"]:
                    for rel_obj in record["rels"]:
                        if rel_obj['r'] is None: continue
                        s_id = add_node(rel_obj['s'])
                        t_id = add_node(rel_obj['t'])
                        edges.append({
                            "source": s_id,
                            "target": t_id,
                            "label": rel_obj['r'].type
                        })

        # Loại bỏ cạnh trùng lặp
        unique_edges = []
        seen_edges = set()
        for e in edges:
            edge_key = (e["source"], e["target"], e["label"])
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                unique_edges.append(e)
        
        return {"nodes": list(nodes.values()), "edges": unique_edges}

neo4j_service = Neo4jService()