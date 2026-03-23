import asyncio
from app.core.neo4j import get_driver, get_db
from app.services.qdrant_service import qdrant_legal_service
from app.services.neo4j_service import neo4j_service

async def check_consistency(query: str):
    print(f"\n--- ĐANG KIỂM TRA VỚI CÂU HỎI: '{query}' ---")
    
    # 1. Lấy kết quả từ Qdrant
    hits = await qdrant_legal_service.hybrid_search(query, top_k=3)
    if not hits:
        print("❌ Lỗi: Qdrant không trả về kết quả nào.")
        return

    # 2. Sinh ID theo logic code hiện tại
    article_ids = await neo4j_service.article_ids_from_qdrant_hits(hits)
    print(f"👉 ID code sinh ra: {article_ids}")

    drv = get_driver()
    async with drv.session(**get_db()) as sess:
        # 3. Lấy mẫu ID thực tế trong Neo4j để đối chiếu
        sample_res = await sess.run("MATCH (a:Article) RETURN a.article_id AS aid LIMIT 5")
        # Dùng data() để lấy list dict cho dễ đọc
        sample_data = await sample_res.data()
        samples = [r["aid"] for r in sample_data]
        
        print(f"✅ ID mẫu thực tế trong Neo4j: {samples}")

        # 4. Kiểm tra xem ID code sinh có tồn tại không
        check_res = await sess.run(
            "MATCH (a:Article) WHERE a.article_id IN $ids RETURN a.article_id AS aid", 
            {"ids": article_ids}
        )
        match_data = await check_res.data()
        matches = [r["aid"] for r in match_data]

    print("-" * 50)
    if matches:
        print(f"🎉 KHỚP THÀNH CÔNG: {matches}")
    else:
        print("❌ THẤT BẠI: Không tìm thấy ID nào khớp.")
        if samples and article_ids:
            print("\nPHÂN TÍCH LỖI:")
            print(f"Mẫu DB: '{samples[0]}'")
            print(f"Code sinh: '{article_ids[0]}'")
            # Kiểm tra các lỗi thường gặp
            if article_ids[0].replace("_", "/") == samples[0]:
                print("💡 Gợi ý: Code dùng '_', DB dùng '/'")
            elif article_ids[0].upper() == samples[0].upper():
                print("💡 Gợi ý: Lỗi hoa/thường")

if __name__ == "__main__":
    asyncio.run(check_consistency("Đối tượng tham gia bảo hiểm xã hội bắt buộc"))