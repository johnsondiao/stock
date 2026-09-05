# 手机版大字结论报告: 直接回答"买哪个板块"
import io
import subprocess

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
@page { size: 108mm 210mm; margin: 7mm 6mm; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Microsoft YaHei", sans-serif; font-size: 13pt;
       line-height: 1.5; color: #111; }
.date { font-size: 10pt; color: #888; margin-bottom: 4px; }
h1 { font-size: 17pt; margin-bottom: 8px; }
.answer { background: #0b3d91; color: #fff; border-radius: 10px;
          padding: 12px 14px; margin: 8px 0; }
.answer .big { font-size: 24pt; font-weight: bold; }
.answer .why { font-size: 11pt; margin-top: 6px; opacity: .92; }
h2 { font-size: 13pt; margin: 12px 0 6px; color: #0b3d91; }
table { border-collapse: collapse; width: 100%; font-size: 11.5pt; }
td, th { padding: 6px 4px; border-bottom: 1px solid #dde; }
th { text-align: left; color: #556; font-size: 10pt; }
b.up { color: #c00; }
.warn { background: #fff3e0; border-left: 5px solid #f57c00;
        padding: 8px 10px; margin-top: 12px; font-size: 11.5pt;
        border-radius: 4px; }
.note { margin-top: 10px; font-size: 9.5pt; color: #999; }
</style></head><body>

<div class="date">2026-09-01 开盘实时 · ma_combo 轮动信号</div>
<h1>今天买什么？</h1>

<div class="answer">
  <div>主线板块</div>
  <div class="big">有色金属 ★★★</div>
  <div class="why">石油 8/25 见顶 → 按历史传导（滞后1周）轮到有色；
  今晨选股 17 只中有色独占 4 只（比昨日还多 1 只），主线正在确认</div>
</div>

<h2>具体标的（今晨实时信号）</h2>
<table>
<tr><th>股票</th><th>现价</th><th>信号</th></tr>
<tr><td><b>江西铜业</b> 600362</td><td>48.40</td><td>双周期多头持续</td></tr>
<tr><td><b>西部矿业</b> 601168</td><td>39.40</td><td>小时金叉刚发生</td></tr>
<tr><td><b>铜陵有色</b> 000630</td><td>6.67</td><td>90分 双周期多头</td></tr>
<tr><td><b>驰宏锌锗</b> 600497</td><td>10.47</td><td>昨日98分 趋势延续</td></tr>
</table>

<h2>次选</h2>
<table>
<tr><td><b>金融</b>：国金证券 600109</td><td>今晨98分新共振，补涨主线惯性中</td></tr>
<tr><td><b>物资外贸</b>：上海物贸 600822</td><td>连续两日在榜，跟随观察</td></tr>
</table>

<div class="warn"><b>别碰：</b>公路桥梁 / 水泥 / 钢铁 —— 8/28 已见顶退潮，
今晨选股榜已完全消失，追高必站岗</div>

<div class="note">依据：87周轮动回测（传导链 石油→有色 相关0.85）+
今晨全市场扫描 3047 只命中 17 只。普涨广度仍在（昨信号股 1161 只），
若跌破 900 只则减半执行。</div>

</body></html>"""

with io.open(r"d:\vibecoding\stock\今日买入_手机版.html", "w",
             encoding="utf-8") as f:
    f.write(HTML)

subprocess.run([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
    "--print-to-pdf=d:\\vibecoding\\stock\\今日买入_手机版.pdf",
    "file:///d:/vibecoding/stock/今日买入_手机版.html",
], check=True)
print("done")
