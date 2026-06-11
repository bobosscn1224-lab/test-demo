import sys; sys.path.insert(0, r'd:\数字分身\backend')
from app.utils.file_parser import parse_file_sync

pdf_path = r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf'
text = parse_file_sync(pdf_path).replace('​', '')

with open(r'd:\数字分身\backend\m11_1_extracted.txt', 'w', encoding='utf-8') as f:
    f.write(text)

print(f"Total: {len(text)} chars")
idx = text.find('L2')
if idx > 0:
    print(f"'L2' at position {idx}")
    print(text[max(0,idx-30):idx+60])
