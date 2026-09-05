import re

with open(r"d:\vibecoding\stock\板块轮动分析报告.pdf", "rb") as f:
    data = f.read()

print("文件头:", data[:8])
print("文件大小:", len(data), "bytes")
# 页数: 统计 /Type /Page (排除 /Pages)
pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
print("估计页数:", pages)
print("末尾有EOF:", b"%%EOF" in data[-1024:])
