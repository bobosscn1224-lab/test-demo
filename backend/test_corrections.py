"""Test correction flow end-to-end.
1. Add correction via API
2. Verify it appears in search results
3. Verify list endpoint works
4. Delete and verify cleanup
"""
import httpx, json, asyncio, sys

BASE = "http://localhost:8001"

async def main():
    all_ok = True

    async with httpx.AsyncClient(timeout=30) as c:

        # 1. List corrections (should start empty or with some)
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        data = r.json()
        before_count = data["count"]
        print(f"[1] Initial corrections: {before_count}")

        # 2. Add a correction: "MO流程的L2PO是谁" → "曹曦"
        r = await c.post(f"{BASE}/api/knowledge/corrections", json={
            "question": "MO流程的L2PO是谁",
            "correct_answer": "MO流程的L2 PO是曹曦，由曹曦负责该流程的审批和管理工作",
        })
        data = r.json()
        cid = data["id"]
        print(f"[2] Added correction: id={cid}")

        # 3. List again — should have 1 more
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        data = r.json()
        print(f"[3] Corrections after add: {data['count']} (was {before_count})")
        if data["count"] != before_count + 1:
            print("   FAIL: count didn't increase!")
            all_ok = False

        # 4. Search knowledge — correction should appear first
        r = await c.get(f"{BASE}/api/knowledge/search", params={"q": "MO流程的L2PO是谁", "top_k": 5})
        data = r.json()
        first = data["results"][0] if data["results"] else {}
        has_correction = "[已校正]" in first.get("content", "") or "correction" in first.get("metadata", {}).get("source", "")
        print(f"[4] First search result: source={first.get('metadata', {}).get('source', '?')} score={first.get('score', 0)}")
        if has_correction:
            print("   OK: Correction appears as first result!")
        else:
            print("   FAIL: Correction not found in results!")
            all_ok = False

        # 5. Search corrections directly
        r = await c.get(f"{BASE}/api/knowledge/search", params={"q": "MO L2PO是谁", "top_k": 3})
        data = r.json()
        found_correction = False
        for r_item in data["results"]:
            if r_item.get("metadata", {}).get("source") == "correction":
                found_correction = True
                print(f"[5] Found correction in search: score={r_item['score']}")
                break
        if not found_correction:
            print("   FAIL: Correction not found for rephrased query!")
            all_ok = False

        # 6. Delete correction
        r = await c.delete(f"{BASE}/api/knowledge/corrections/{cid}")
        print(f"[6] Deleted correction: {r.json()}")

        # 7. Verify deleted
        r = await c.get(f"{BASE}/api/knowledge/corrections")
        data = r.json()
        print(f"[7] Final count: {data['count']} (expected {before_count})")
        if data["count"] != before_count:
            print("   FAIL: count didn't go back!")
            all_ok = False

    print(f"\n{'ALL PASSED' if all_ok else 'SOME FAILED'}")

asyncio.run(main())
