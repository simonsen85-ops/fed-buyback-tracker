#!/usr/bin/env python3
"""
Generates index.html from data.json.
Embeds the JSON data directly into the HTML template.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data.json"
OUTPUT_FILE = ROOT / "index.html"

def build():
    with open(DATA_FILE) as f:
        data = json.load(f)

    # Minify data for embedding
    data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Built {OUTPUT_FILE} with {len(data['announcements'])} announcements")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fast Ejendom Danmark — Aktietilbagekøbs-Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=JetBrains+Mono:wght@400;500;600&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#0a0e17;--bg2:#111827;--bg3:#1a2332;--bdr:#1e293b;--tx:#e2e8f0;--tx2:#94a3b8;--tx3:#64748b;--tx4:#475569;--grn:#10b981;--grn2:#059669;--amb:#f59e0b;--blu:#38bdf8;--ind:#6366f1;--red:#ef4444;--pur:#a78bfa}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;overflow-x:hidden}
.noise{position:fixed;top:0;left:0;width:100%;height:100%;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");pointer-events:none;z-index:0}
.gorb{position:fixed;border-radius:50%;filter:blur(120px);pointer-events:none;z-index:0}
.gorb.g{width:500px;height:500px;background:rgba(16,185,129,0.06);top:-100px;right:-100px}
.gorb.a{width:400px;height:400px;background:rgba(245,158,11,0.04);bottom:100px;left:-100px}
.c{max-width:1320px;margin:0 auto;padding:24px 20px;position:relative;z-index:1}
.hdr{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:28px;flex-wrap:wrap;gap:16px}
.hdr h1{font-family:'DM Serif Display',serif;font-size:2rem;font-weight:400;letter-spacing:-0.5px;background:linear-gradient(135deg,#e2e8f0,#94a3b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .sub{font-size:.82rem;color:var(--tx3);margin-top:4px;font-family:'JetBrains Mono',monospace}
.hdr-r{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.badge{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:20px;font-size:.73rem;font-family:'JetBrains Mono',monospace;font-weight:500}
.badge.live{background:rgba(16,185,129,.12);color:var(--grn);border:1px solid rgba(16,185,129,.25)}
.badge.live::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--grn);animation:pulse 2s infinite}
.badge.nav{background:rgba(56,189,248,.1);color:var(--blu);border:1px solid rgba(56,189,248,.2)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:24px}
.kpi{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:16px 18px;transition:all .25s}
.kpi:hover{border-color:rgba(16,185,129,.3);background:var(--bg3)}
.kpi .l{font-size:.7rem;color:var(--tx3);text-transform:uppercase;letter-spacing:1.1px;font-weight:500}
.kpi .v{font-family:'JetBrains Mono',monospace;font-size:1.45rem;font-weight:600;margin-top:5px;line-height:1}
.kpi .s{font-size:.73rem;color:var(--tx4);margin-top:5px;font-family:'JetBrains Mono',monospace}
.grn{color:var(--grn)}.amb{color:var(--amb)}.blu{color:var(--blu)}.ind{color:var(--ind)}.pur{color:var(--pur)}.red{color:var(--red)}
.vc-card{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:20px;margin-bottom:24px}
.vc-card h3{font-size:.9rem;font-weight:600;margin-bottom:16px}
.vc-grid{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:12px;align-items:center}
@media(max-width:700px){.vc-grid{grid-template-columns:1fr}}
.vc-box{background:rgba(16,185,129,.05);border:1px solid rgba(16,185,129,.15);border-radius:10px;padding:16px;text-align:center}
.vc-box.total{background:rgba(16,185,129,.1);border-color:rgba(16,185,129,.3)}
.vc-box .vl{font-family:'JetBrains Mono',monospace;font-size:1.3rem;font-weight:600;color:var(--grn)}
.vc-box .vl.pur{color:var(--pur)}.vc-box .vl.amb{color:var(--amb)}
.vc-box .vt{font-size:.72rem;color:var(--tx3);margin-top:4px;text-transform:uppercase;letter-spacing:.8px}
.vc-box .vd{font-size:.73rem;color:var(--tx4);margin-top:6px;font-family:'JetBrains Mono',monospace;line-height:1.5}
.vc-op{font-size:1.4rem;color:var(--tx4);font-weight:300;text-align:center}
@media(max-width:700px){.vc-op{display:none}}
.pbar-card{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:20px;margin-bottom:24px}
.pbar-bg{height:28px;background:rgba(30,41,59,.8);border-radius:14px;overflow:hidden;margin-top:12px}
.pbar-fill{height:100%;border-radius:14px;background:linear-gradient(90deg,#059669,var(--grn),#34d399);transition:width 1s;position:relative}
.pbar-fill::after{content:attr(data-pct);position:absolute;right:12px;top:50%;transform:translateY(-50%);font-family:'JetBrains Mono',monospace;font-size:.72rem;font-weight:600;color:#fff}
.pbar-labels{display:flex;justify-content:space-between;margin-top:8px;font-size:.73rem;color:var(--tx3);font-family:'JetBrains Mono',monospace}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
@media(max-width:860px){.charts{grid-template-columns:1fr}}
.chc{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:20px}
.chc h3{font-size:.88rem;font-weight:600;margin-bottom:14px}.chc h3 span{color:var(--tx3);font-weight:400}
.chw{position:relative;height:280px}
.tc{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:20px;margin-bottom:24px}
.tc h3{font-size:.88rem;font-weight:600;margin-bottom:14px}
.ts{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--bdr);font-family:'JetBrains Mono',monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.8px;color:var(--tx3);font-weight:500;white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid rgba(30,41,59,.5);font-family:'JetBrains Mono',monospace;font-size:.76rem;white-space:nowrap}
tr:hover td{background:rgba(16,185,129,.03)}
.pos{color:var(--grn)}.neg{color:var(--red)}
.foot{text-align:center;padding:20px 0;font-size:.7rem;color:var(--tx4);font-family:'JetBrains Mono',monospace;border-top:1px solid var(--bdr);margin-top:20px}
.foot a{color:var(--grn);text-decoration:none}
.sbar{text-align:center;padding:8px;font-size:.73rem;color:var(--tx3);font-family:'JetBrains Mono',monospace}
</style>
</head>
<body>
<div class="noise"></div><div class="gorb g"></div><div class="gorb a"></div>
<div class="c">
<div class="hdr">
  <div><h1>Fast Ejendom Danmark A/S</h1><div class="sub">Aktietilbagekøbsprogram — Safe Harbour Tracker</div></div>
  <div class="hdr-r"><span class="badge nav" id="navB"></span><span class="badge live" id="krsB"></span></div>
</div>
<div class="kpis" id="kpis"></div>
<div class="vc-card"><h3>Værdiskabelse for aktionærer — to lag</h3><div class="vc-grid" id="vcG"></div></div>
<div class="pbar-card"><h3>Programfremgang <span style="color:var(--tx3);font-weight:400">— maks. 10,0 mio. DKK</span></h3><div class="pbar-bg"><div class="pbar-fill" id="pF"></div></div><div class="pbar-labels"><span>0 DKK</span><span id="pL"></span><span>10.000.000 DKK</span></div></div>
<div class="charts">
  <div class="chc"><h3>Akkumulerede aktier <span>— tilbagekøbt</span></h3><div class="chw"><canvas id="ch1"></canvas></div></div>
  <div class="chc"><h3>Værdiskabelse & ROIC <span>— akkumuleret</span></h3><div class="chw"><canvas id="ch2"></canvas></div></div>
  <div class="chc"><h3>Ugentlig købskurs vs. NAV <span>— DKK</span></h3><div class="chw"><canvas id="ch3"></canvas></div></div>
  <div class="chc"><h3>ROIC på tilbagekøb <span>— akkumuleret %</span></h3><div class="chw"><canvas id="ch4"></canvas></div></div>
</div>
<div class="tc"><h3>Alle ugentlige meddelelser — verificeret fra fastejendom.dk</h3>
<div class="ts"><table><thead><tr>
  <th>#</th><th>Dato</th><th>Aktier</th><th>Gns.kurs</th><th>Beløb</th>
  <th>Akk.aktier</th><th>Akk.beløb</th><th>NAV</th><th>Rabat</th>
  <th>Lag 1</th><th>Lag 2</th><th>Total</th><th>ROIC</th>
</tr></thead><tbody id="tb"></tbody></table></div></div>
<div class="sbar" id="sbar"></div>
<div class="foot">
  Kilde: <a href="https://fastejendom.dk/investor/selskabsmeddelelser/" target="_blank">fastejendom.dk</a> ·
  Automatisk opdateret via GitHub Actions ·
  Senest: <span id="upd"></span>
</div>
</div>
<script>
const DATA = __DATA_JSON__;
const TS = DATA.total_shares;

function getNav(d) {
  let n = DATA.nav_history[0].nav;
  for (const e of DATA.nav_history) { if (d >= e.from) n = e.nav; }
  return n;
}

function calc() {
  const rows = [];
  let accDVC = 0;
  for (const a of DATA.announcements) {
    const nav = getNav(a.announcement_date);
    const wAvg = a.week_shares > 0 ? a.week_amount / a.week_shares : 0;
    const accAvg = a.acc_shares > 0 ? a.acc_amount / a.acc_shares : 0;
    const dvc = a.week_shares * (nav - wAvg);
    accDVC += dvc;
    const tEq = nav * TS;
    const nEq = tEq - a.acc_amount;
    const nSh = TS - a.acc_shares;
    const nNAV = nEq / nSh;
    const navAcc = nNAV - nav;
    const accVal = navAcc * nSh;
    const totalVC = accDVC + accVal;
    const roic = a.acc_amount > 0 ? totalVC / a.acc_amount * 100 : 0;
    rows.push({
      date:a.announcement_date, ps:a.period_start, pe:a.period_end,
      wS:a.week_shares, wA:a.week_amount, wAvg, aS:a.acc_shares, aA:a.acc_amount, accAvg,
      nav, dvc, accDVC, navAcc, accVal, totalVC, nNAV, roic
    });
  }
  return rows;
}

function fmtDK(n){return n.toLocaleString('da-DK')}
function fmtM(n){return (n/1e6).toFixed(2)+' mio.'}
function fmtK(n){return (n/1e3).toFixed(0)+'K'}

function render() {
  const rows = calc();
  const R = rows[rows.length - 1];
  const curNav = R.nav;
  const curKurs = 222; // Latest traded price — update if needed
  const pctUsed = R.aA / DATA.program_max * 100;
  const discBuy = (curNav - R.accAvg) / curNav * 100;
  const discMkt = (curNav - curKurs) / curNav * 100;
  const vcPS = R.totalVC / (TS - R.aS);

  document.getElementById('navB').textContent = `NAV ${curNav.toFixed(2)}`;
  document.getElementById('krsB').textContent = `KURS ${curKurs}`;

  document.getElementById('kpis').innerHTML = [
    {l:'Tilbagekøbt i alt',v:fmtDK(R.aS)+' stk.',s:`${(R.aS/TS*100).toFixed(2)}% af udstedte`,c:''},
    {l:'Beløb brugt',v:fmtM(R.aA),s:`${pctUsed.toFixed(1)}% af 10 mio. ramme`,c:'amb'},
    {l:'Gns. købskurs',v:R.accAvg.toFixed(2)+' DKK',s:`${discBuy.toFixed(1)}% rabat til NAV`,c:'blu'},
    {l:'Total værdiskabelse',v:fmtM(R.totalVC),s:`${vcPS.toFixed(2)} DKK pr. aktie`,c:'grn'},
    {l:'ROIC på tilbagekøb',v:R.roic.toFixed(1)+'%',s:`Afkast pr. investeret krone`,c:'amb'},
    {l:'NAV-accretion',v:'+'+R.navAcc.toFixed(2)+' DKK',s:`Ny NAV: ${R.nNAV.toFixed(2)}`,c:'pur'},
    {l:'Rabat til indre værdi',v:discMkt.toFixed(1)+'%',s:`Kurs ${curKurs} vs. NAV ${curNav.toFixed(2)}`,c:'ind'},
  ].map(k=>`<div class="kpi"><div class="l">${k.l}</div><div class="v ${k.c}">${k.v}</div><div class="s">${k.s}</div></div>`).join('');

  document.getElementById('vcG').innerHTML = `
    <div class="vc-box">
      <div class="vl">${fmtM(R.accDVC)}</div>
      <div class="vt">Lag 1 — Direkte rabat</div>
      <div class="vd">Σ (NAV − købskurs) × aktier<br>Køb under indre værdi</div>
    </div>
    <div class="vc-op">+</div>
    <div class="vc-box">
      <div class="vl pur">${fmtM(R.accVal)}</div>
      <div class="vt">Lag 2 — Annulleringseffekt</div>
      <div class="vd">NAV +${R.navAcc.toFixed(2)} DKK/aktie<br>× ${fmtDK(TS-R.aS)} resterende</div>
    </div>
    <div class="vc-op">=</div>
    <div class="vc-box total">
      <div class="vl amb">${fmtM(R.totalVC)}</div>
      <div class="vt">Total aktionærværdi</div>
      <div class="vd">${vcPS.toFixed(2)} DKK pr. aktie<br>ROIC: ${R.roic.toFixed(1)}%</div>
    </div>`;

  const fill = document.getElementById('pF');
  fill.style.width = Math.min(pctUsed,100)+'%';
  fill.setAttribute('data-pct',pctUsed.toFixed(1)+'%');
  document.getElementById('pL').textContent = `Brugt: ${fmtM(R.aA)} DKK`;

  const labels = rows.map(r=>{const d=new Date(r.date);return d.toLocaleDateString('da-DK',{day:'numeric',month:'short'})});
  const cO=(x={})=>({responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false,...(x.lg||{})},tooltip:{backgroundColor:'#1e293b',titleFont:{family:'JetBrains Mono',size:11},bodyFont:{family:'JetBrains Mono',size:11},borderColor:'#334155',borderWidth:1,padding:10,cornerRadius:8,callbacks:{label:ctx=>{let v=ctx.parsed.y;return(ctx.dataset.label?ctx.dataset.label+': ':'')+((ctx.dataset.pct)?v.toFixed(1)+'%':v>=1e6?fmtM(v):v>=1e3?fmtK(v):v.toFixed(0))}}}},scales:{x:{ticks:{color:'#475569',font:{family:'JetBrains Mono',size:9},maxRotation:45},grid:{color:'rgba(30,41,59,.5)'}},y:{ticks:{color:'#475569',font:{family:'JetBrains Mono',size:10},callback:v=>v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v,...(x.yt||{})},grid:{color:'rgba(30,41,59,.3)'},...(x.y||{})}}});

  new Chart(document.getElementById('ch1'),{type:'line',data:{labels,datasets:[{data:rows.map(r=>r.aS),borderColor:'#10b981',backgroundColor:'rgba(16,185,129,.08)',borderWidth:2.5,fill:true,tension:.3,pointRadius:3,pointBackgroundColor:'#10b981'}]},options:cO()});

  new Chart(document.getElementById('ch2'),{type:'line',data:{labels,datasets:[
    {label:'Total (Lag 1+2)',data:rows.map(r=>Math.round(r.totalVC)),borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,.06)',borderWidth:2.5,fill:true,tension:.3,pointRadius:3,pointBackgroundColor:'#f59e0b'},
    {label:'Lag 1 (direkte)',data:rows.map(r=>Math.round(r.accDVC)),borderColor:'#10b981',backgroundColor:'rgba(16,185,129,.06)',borderWidth:2,fill:true,tension:.3,pointRadius:2,pointBackgroundColor:'#10b981'},
    {label:'Lag 2 (annullering)',data:rows.map(r=>Math.round(r.accVal)),borderColor:'#a78bfa',borderDash:[4,3],borderWidth:2,tension:.3,pointRadius:2,pointBackgroundColor:'#a78bfa'}
  ]},options:cO({lg:{display:true,labels:{color:'#94a3b8',font:{family:'Outfit',size:11},boxWidth:12,padding:12}}})});

  new Chart(document.getElementById('ch3'),{type:'line',data:{labels,datasets:[
    {label:'NAV pr. aktie',data:rows.map(r=>r.nav),borderColor:'#38bdf8',borderWidth:2,borderDash:[6,3],pointRadius:2,pointBackgroundColor:'#38bdf8'},
    {label:'Ugentlig købskurs',data:rows.map(r=>Math.round(r.wAvg*100)/100),borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,.06)',borderWidth:2.5,fill:true,tension:.3,pointRadius:3,pointBackgroundColor:'#ef4444'}
  ]},options:cO({lg:{display:true,labels:{color:'#94a3b8',font:{family:'Outfit',size:11},boxWidth:12,padding:12}}})});

  new Chart(document.getElementById('ch4'),{type:'line',data:{labels,datasets:[{
    label:'ROIC %',data:rows.map(r=>Math.round(r.roic*10)/10),
    borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,.08)',borderWidth:2.5,fill:true,tension:.3,
    pointRadius:3,pointBackgroundColor:'#f59e0b',pct:true
  }]},options:cO({y:{beginAtZero:true},yt:{callback:v=>v+'%'}})});

  document.getElementById('tb').innerHTML = rows.map((r,i)=>{
    const disc=(r.nav-r.wAvg)/r.nav*100;
    return `<tr><td>${i+1}</td><td>${new Date(r.date).toLocaleDateString('da-DK',{day:'numeric',month:'short'})}</td><td>${fmtDK(r.wS)}</td><td>${r.wAvg.toFixed(2)}</td><td>${fmtK(r.wA)}</td><td><b>${fmtDK(r.aS)}</b></td><td>${fmtM(r.aA)}</td><td>${r.nav.toFixed(2)}</td><td class="pos">${disc.toFixed(1)}%</td><td class="pos">+${fmtK(r.dvc)}</td><td class="pos">+${fmtK(r.accVal)}</td><td class="pos"><b>+${fmtM(r.totalVC)}</b></td><td class="amb">${r.roic.toFixed(1)}%</td></tr>`;
  }).join('');

  document.getElementById('sbar').textContent = `${DATA.announcements.length} meddelelser · Automatisk opdateret · Sidst: ${DATA.last_updated||'ukendt'}`;
  document.getElementById('upd').textContent = DATA.last_updated ? new Date(DATA.last_updated).toLocaleString('da-DK') : 'ukendt';
}

render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
