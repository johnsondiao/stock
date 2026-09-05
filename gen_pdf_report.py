# Markdown → 精美HTML → Chrome headless 打印PDF
import io
import re
import html as html_lib

CSS = """
@page { size: A4; margin: 18mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "SimHei", sans-serif; font-size: 10.5pt;
       line-height: 1.65; color: #1a2332; max-width: 100%; }
.cover { page-break-after: always; padding-top: 120px; text-align: center; }
.cover h1 { font-size: 26pt; color: #0b3d91; border: none; margin-bottom: 8px; }
.cover .sub { font-size: 13pt; color: #556; margin-top: 18px; }
.cover .meta { margin-top: 70px; font-size: 10.5pt; color: #778;
               border-top: 1px solid #ccd; display: inline-block; padding-top: 12px; }
h1 { font-size: 17pt; color: #0b3d91; border-bottom: 3px solid #0b3d91;
     padding-bottom: 6px; margin-top: 26px; page-break-after: avoid; }
h2 { font-size: 13.5pt; color: #0b3d91; margin-top: 22px;
     border-left: 5px solid #2f6fdb; padding-left: 10px; page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #1d4f91; margin-top: 16px; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.5pt;
        page-break-inside: avoid; }
th { background: #0b3d91; color: #fff; padding: 6px 8px; text-align: left; }
td { border: 1px solid #c8d2e0; padding: 5px 8px; }
tr:nth-child(even) td { background: #f2f6fc; }
code { font-family: Consolas, monospace; background: #eef2f8; padding: 1px 5px;
       border-radius: 3px; font-size: 9.5pt; color: #b03060; }
pre { background: #0e1626; color: #d7e3f4; padding: 12px 14px; border-radius: 6px;
      font-size: 9pt; line-height: 1.5; overflow-x: hidden; page-break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
blockquote { border-left: 4px solid #f0a830; background: #fff8ec; margin: 10px 0;
             padding: 8px 14px; color: #5c4a1e; page-break-inside: avoid; }
hr { border: none; border-top: 1px dashed #aab; margin: 18px 0; }
ul, ol { padding-left: 22px; }
li { margin: 3px 0; }
strong { color: #0b3d91; }
.section { page-break-before: always; }
"""


def inline(s: str) -> str:
    s = html_lib.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append("<pre><code>" + html_lib.escape("\n".join(buf)) +
                       "</code></pre>")
            i += 1
            continue
        if ln.strip().startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><tr>" +
                 "".join(f"<th>{inline(h)}</th>" for h in header) + "</tr>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>"
                                          for c in r) + "</tr>")
            t.append("</table>")
            out.append("".join(t))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if re.match(r"^\s*([-*])\s+", ln):
            buf = []
            while i < len(lines) and re.match(r"^\s*([-*])\s+", lines[i]):
                buf.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "",
                                                  lines[i])) + "</li>")
                i += 1
            out.append("<ul>" + "".join(buf) + "</ul>")
            continue
        if re.match(r"^\s*\d+\.\s+", ln):
            buf = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                buf.append("<li>" + inline(re.sub(r"^\s*\d+\.\s+", "",
                                                  lines[i])) + "</li>")
                i += 1
            out.append("<ol>" + "".join(buf) + "</ol>")
            continue
        if ln.strip().startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(inline(re.sub(r"^\s*>\s?", "", lines[i])))
                i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>")
            continue
        if re.match(r"^\s*-{3,}\s*$", ln):
            out.append("<hr>")
            i += 1
            continue
        if ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


with io.open(r"d:\vibecoding\stock\板块轮动分析报告.md",
             encoding="utf-8") as f:
    md1 = f.read()
with io.open(r"d:\vibecoding\stock\当前与下一轮板块判断_20260831.md",
             encoding="utf-8") as f:
    md2 = f.read()

# 去掉md内的一级标题(用封面+节标题代替), 正文标题层级提升由CSS控制
body1 = re.sub(r"^#[^#].*\n", "", md1, count=1)
body2 = re.sub(r"^#[^#].*\n", "", md2, count=1)

cover = """
<div class="cover">
  <h1>A股板块轮动分析报告</h1>
  <div class="sub">基于 ma_combo 多周期均线共振策略的信号回放</div>
  <div class="meta">
    分析区间 2025-01 ~ 2026-08（87周） · 49个行业板块 · 2161只主板股票<br>
    生成日期 2026-09-01 · 数据源: 本地SQLite全市场K线 + 新浪行业分类
  </div>
</div>
"""

html_doc = f"""<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><style>{CSS}</style></head><body>
{cover}
<div class="section"><h1>第一部分 轮动规律分析</h1>{md_to_html(body1)}</div>
<div class="section"><h1>第二部分 当前轮次判断（2026-08-31）</h1>{md_to_html(body2)}</div>
</body></html>"""

with io.open(r"d:\vibecoding\stock\板块轮动分析报告.html", "w",
             encoding="utf-8") as f:
    f.write(html_doc)
print("HTML saved")
