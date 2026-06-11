"""Test image description during file parsing."""
import asyncio, os, sys

async def main():
    from app.utils.file_parser import parse_file

    # Find a PDF with images
    watch_dir = r"D:\数字分身\本地知识库"
    for root, dirs, files in os.walk(watch_dir):
        for f in files:
            if f.lower().endswith('.pdf'):
                fpath = os.path.join(root, f)
                # Skip backup dirs
                if any(skip in fpath for skip in ['Backup0928', 'BACKUP1225', 'backup', 'BACKUP']):
                    continue
                print(f"Testing: {fpath}")
                text = await parse_file(fpath)
                if text:
                    has_images = '[文档图片' in text or '[图片:' in text
                    print(f"  Text length: {len(text)} chars")
                    print(f"  Contains image descriptions: {has_images}")
                    if has_images:
                        # Show image description sections
                        for line in text.split('\n'):
                            if '图片' in line and ('[文档图片' in line or '[图片:' in line or '[幻灯片图片' in line):
                                print(f"  IMG: {line}")
                    print(f"  Preview: {text[:300]}...")
                else:
                    print(f"  No text extracted")
                print()
                break  # Just test one file for now

asyncio.run(main())
