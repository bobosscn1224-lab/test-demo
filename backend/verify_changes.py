"""Verify all changes: prompt, chunker, and chat."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, json
from app.utils.text_chunker import chunk_text

# 1. Test chunker with Chinese document text
print("=== Test 1: Semantic Chunker ===")
sample = """一、项目背景与目标

本项目旨在优化MO管理商机流程，提升端到端业务效率。

二、核心流程设计

2.1 立项评审阶段
立项评审是MO流程的关键节点。项目进入漏斗后需在7天内完成立项评审，确定项目组成员。

2.2 方案验证阶段
方案验证包括POC测试和技术评审，需要多部门协同完成。

三、关键角色与职责

L2PO负责端到端流程的协调与推动，主要职责包括跨部门资源协调、流程卡点识别、推动解决方案落地。

L3PO负责具体流程节点的执行与优化，确保每个环节按时交付。

四、考核与度量

每月对关键任务执行情况进行评分，未完成的节点扣减QBC考核分值。
"""

chunks = chunk_text(sample, chunk_size=600, overlap=50)
print(f"Input: {len(sample)} chars")
print(f"Chunks: {len(chunks)}")
for i, c in enumerate(chunks):
    print(f"  [{i}] {len(c)} chars — {c[:80]}...")

# 2. Test chat with knowledge
print("\n=== Test 2: Chat with strict prompt ===")
import httpx

async def test_chat():
    async with httpx.AsyncClient(timeout=60) as client:
        # Ask a knowledge-based question
        body = {"message": "MO流程的L2PO是谁？", "session_id": None, "persona_slug": "default"}
        full = ""
        async with client.stream("POST", "http://localhost:8001/api/chat/stream", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event["type"] == "token":
                            full += event["data"]
                    except Exception:
                        pass
        print(f"Q: MO流程的L2PO是谁？")
        print(f"A: {full[:400]}")
        print(f"  Contains 曹曦: {'曹曦' in full}")
        print(f"  Contains source: {'M11' in full or '《' in full}")

    # 3. Verify persona template in DB
    print("\n=== Test 3: Persona Template ===")
    r = await client.get("http://localhost:8001/api/personas/active")
    p = r.json()
    tpl = p.get("system_prompt_template", "")
    has_strict = "唯一依据" in tpl
    print(f"  Persona: {p.get('name')} — strict rules: {has_strict}")

asyncio.run(test_chat())
