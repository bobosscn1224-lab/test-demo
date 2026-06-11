import os, openpyxl

# Check both output directories
for subdir in ["", "test"]:
    output_dir = os.path.join(os.path.dirname(__file__), "..", "工作周报", "输出", subdir)
    if not os.path.isdir(output_dir):
        continue
    for f in os.listdir(output_dir):
        if "5.25-5.29" in f and f.endswith(".xlsx") and not f.startswith("~$"):
            fp = os.path.join(output_dir, f)
            print(f"File: {fp}")
            wb = openpyxl.load_workbook(fp)
            for sn in wb.sheetnames:
                if "5.25" in sn:
                    ws = wb[sn]
                    print(f"Sheet: {sn}, Rows: {ws.max_row}")
                    empty_count = 0
                    for r in range(2, 28):
                        d = (ws.cell(r, 4).value or "")
                        e = (ws.cell(r, 5).value or "")
                        if not str(d).strip() or not str(e).strip():
                            b = str(ws.cell(r, 2).value or "")
                            c = str(ws.cell(r, 3).value or "")
                            empty_count += 1
                            if not str(d).strip():
                                print(f"  Row {r}: B={b[:15]} C={c[:20]} D=EMPTY")
                            if not str(e).strip():
                                print(f"  Row {r}: B={b[:15]} C={c[:20]} E=EMPTY")
                    print(f"Total empty issues: {empty_count}")
                    if empty_count == 0:
                        print(">> ALL D/E CELLS FILLED!")
            wb.close()
            break
