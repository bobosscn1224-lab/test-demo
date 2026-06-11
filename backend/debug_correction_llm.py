"""Debug: test correction detection directly with LLM."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio, json
from app.services.llm_service import llm_service

async def main():
    # Simulate the extraction prompt
    context = """用户: MO流程中L2PO的角色是什么？
助手: (a long response about L2PO)"""

    prompt = f"""判断用户最新消息是否在纠正助手之前的回答。如果是，提取被纠正的原始问题（用户问的问题）和正确答案。

对话历史：
{context}

用户最新消息: 不对，MO流程的L2PO是曹曦，L3 PO是汪霏

返回严格JSON格式，不要带markdown代码块标记：
如果用户是在纠正：{{"is_correction": true, "question": "原始问题", "correct_answer": "正确答案"}}
如果不是纠正：{{"is_correction": false, "question": null, "correct_answer": null}}"""

    print("Prompt:", prompt[:200])
    print("---")

    try:
        response = await llm_service.chat(
            system_prompt="你是一个对话分析助手。只返回严格JSON格式的结果。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        print(f"Raw response: {text}")

        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        print(f"Parsed: {data}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
