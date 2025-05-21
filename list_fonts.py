import matplotlib.font_manager as fm
all_fonts = set()
for f in fm.fontManager.ttflist:
    # 只印出跟中文字型有關的名字與檔案路徑
    if "CJK" in f.name or "Hei" in f.name or "Kai" in f.name or "Ming" in f.name or "Zen" in f.name or "TC" in f.name:
        print(f.name, "|", f.fname)
        all_fonts.add(f.name)
print("你能用的字型名：", all_fonts)
