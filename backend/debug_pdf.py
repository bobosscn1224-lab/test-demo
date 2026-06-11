"""Debug PDF extraction for M11.1"""
import fitz, json

pdf_path = r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf'
doc = fitz.open(pdf_path)
results = []
for i, page in enumerate(doc):
    words = page.get_text("words")
    page_info = {"page": i+1, "method1_lines": 0, "method2_lines": 0, "has_answer": False, "text_sample": ""}
    if words:
        words.sort(key=lambda w: (round(w[1], 0), w[0]))
        lines = []
        current_line = []
        current_y = round(words[0][1], 0) if words else 0
        for w in words:
            wy = round(w[1], 0)
            if abs(wy - current_y) > 3:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [w[4]]
                current_y = wy
            else:
                current_line.append(w[4])
        if current_line:
            lines.append(" ".join(current_line))
        result1 = "\n".join(lines)
        normal = [l for l in lines if len(l) > 5]
        page_info["method1_lines"] = len(lines)
        page_info["method1_normal"] = len(normal)
        if len(normal) > len(lines) * 0.5:
            page_info["text_sample"] = result1[:500]
    else:
        page_info["method1_lines"] = 0
        page_info["method1_normal"] = 0

    raw = page.get_text("text")
    lines = raw.split("\n")
    page_info["method2_lines"] = len(lines)
    if "流程L2 PO" in raw or "曹曦" in raw or "L2 PO" in raw:
        page_info["has_answer"] = True
    results.append(page_info)

doc.close()

with open(r'd:\数字分身\debug_pdf_result.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

for r in results:
    m1_pct = f"{r.get('method1_normal',0)/max(r.get('method1_lines',1),1)*100:.0f}%" if r['method1_lines'] > 0 else "N/A"
    marker = " *** ANSWER HERE ***" if r['has_answer'] else ""
    print(f"Page {r['page']:2d}: M1={r['method1_lines']} lines ({m1_pct} normal) M2={r['method2_lines']} lines{marker}")
