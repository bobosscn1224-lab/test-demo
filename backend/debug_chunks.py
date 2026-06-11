import sys; sys.path.insert(0, '.')
from app.utils.file_parser import parse_file_sync
from app.utils.text_chunker import chunk_text

text = parse_file_sync(r'D:\数字分身\本地知识库\M11.1 验证商机流程说明文件-V1.0.pdf')
if text:
    chunks = chunk_text(text, 500, 50)
    with open(r'd:\数字分身\chunks_debug.txt', 'w', encoding='utf-8') as f:
        for i, c in enumerate(chunks[:10]):
            f.write(f'=== Chunk {i} ({len(c)} chars) ===\n')
            f.write(c[:600])
            f.write('\n\n')
    print(f'Done: {len(chunks)} chunks')
else:
    print('No text extracted')
