#!/usr/bin/env python3
"""Generates index.html from data.json."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data.json"
OUTPUT_FILE = ROOT / "index.html"

def build():
    with open(DATA_FILE) as f:
        data = json.load(f)
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
<title>FED.CO — Tilbagekøbs-Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
/*
  TYPE HIERARCHY — 4 levels, strict usage:
  
  T1 (#f8fafc) = PRIMARY: numbers, data values, section titles
                 This is what the eye reads first.
  T2 (#b0bac9) = SECONDARY: KPI labels, axis ticks, table headers, subtexts
                 Clearly readable but visually subordinate to T1.
  T3 (#6b7a90) = TERTIARY: supplementary info (units after titles),
                 methodology notes, structural borders
  T4 (#3d4a5c) = STRUCTURAL: grid lines, card borders, dividers
                 Felt, not read.
  
  GREEN SPECTRUM for value judgments only:
  G1 (#6ee7b7) = subtle positive (discount %)
  G2 (#34d399) = medium (accretion)
  G3 (#10b981) = strong (value creation)
  G4 (#059669) = deepest (ROIC — the bottom line)
*/
:root{
  --bg:#0c1017;--bg2:#141a24;--bg3:#1a2230;
  --t1:#f8fafc;--t2:#b0bac9;--t3:#6b7a90;--t4:#3d4a5c;
  --g1:#6ee7b7;--g2:#34d399;--g3:#10b981;--g4:#059669;
  --amb:#f59e0b;--red:#ef4444;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'JetBrains Mono',monospace;background:var(--bg);color:var(--t1);min-height:100vh;font-size:13px;-webkit-font-smoothing:antialiased}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 70% 10%,rgba(16,185,129,.025),transparent 60%);pointer-events:none}
.c{max-width:1360px;margin:0 auto;padding:16px 20px;position:relative;z-index:1}

/* HEADER */
.hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 0;margin-bottom:16px;border-bottom:1px solid var(--t4)}
.hdr-l{display:flex;align-items:baseline;gap:12px}
.hdr-l h1{font-family:'Outfit',sans-serif;font-size:1.1rem;font-weight:600;color:var(--t1)}
.hdr-l .tk{color:var(--g3);font-weight:600;font-size:.85rem}
.hdr-l .tg{color:var(--t3);font-size:.75rem}
.hdr-r{display:flex;gap:20px;align-items:center;font-size:.8rem}
.hdr-r .pair .lb{color:var(--t2);font-size:.65rem;text-transform:uppercase;letter-spacing:.5px}
.hdr-r .pair .vl{color:var(--t1);font-weight:600}
.hdr-r .pair .vl.g{color:var(--g2)}

/* KPIs — tight Bloomberg grid */
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--t4);border:1px solid var(--t4);border-radius:4px;overflow:hidden;margin-bottom:16px}
@media(max-width:900px){.kpis{grid-template-columns:repeat(3,1fr)}}
@media(max-width:500px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--bg2);padding:12px 14px}
.kpi .l{font-size:.65rem;color:var(--t2);text-transform:uppercase;letter-spacing:.7px;font-weight:500;margin-bottom:6px}
.kpi .v{font-size:1.2rem;font-weight:700;line-height:1}
.kpi .s{font-size:.7rem;color:var(--t2);margin-top:4px}

/* SECTION TITLE — consistent everywhere */
.sh{font-family:'Outfit',sans-serif;font-size:.75rem;font-weight:600;color:var(--t1);text-transform:uppercase;letter-spacing:.6px;margin-bottom:12px}

/* VALUE CREATION */
.vc{background:var(--bg2);border:1px solid var(--t4);border-radius:4px;padding:14px 16px;margin-bottom:16px}
.vc-flow{display:grid;grid-template-columns:1fr 30px 1fr 30px 1fr;gap:8px;align-items:stretch}
@media(max-width:700px){.vc-flow{grid-template-columns:1fr}.vc-ar{transform:rotate(90deg)}}
.vb{border-radius:4px;padding:16px;text-align:center;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%}
.vb.a{background:rgba(248,250,252,.03);border:1px solid var(--t4)}
.vb.b{background:rgba(52,211,153,.04);border:1px solid rgba(52,211,153,.12)}
.vb.c{background:rgba(5,150,105,.07);border:1px solid rgba(5,150,105,.2)}
.vb .nm{font-size:1.3rem;font-weight:700}
.vb .lb{font-size:.63rem;color:var(--t2);margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.vb .dt{font-size:.7rem;color:var(--t2);margin-top:6px;line-height:1.5}
.vc-ar{font-size:1rem;color:var(--t3);display:flex;align-items:center;justify-content:center}
.vc-n{font-size:.67rem;color:var(--t3);margin-top:10px;line-height:1.5;padding-top:10px;border-top:1px solid var(--t4)}

/* PROGRESS */
.prog{background:var(--bg2);border:1px solid var(--t4);border-radius:4px;padding:14px 16px;margin-bottom:16px}
.prog-top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.prog-top .pct{font-size:.85rem;font-weight:700;color:var(--g3)}
.prog-bar{height:6px;background:var(--bg3);border-radius:3px;overflow:hidden}
.prog-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--g4),var(--g3));transition:width 1s}
.prog-lbl{display:flex;justify-content:space-between;margin-top:5px;font-size:.65rem;color:var(--t2)}

/* CHARTS */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
@media(max-width:860px){.charts{grid-template-columns:1fr}}
.chc{background:var(--bg2);border:1px solid var(--t4);border-radius:4px;padding:14px 16px}
.chc h3{font-family:'Outfit',sans-serif;font-size:.73rem;font-weight:600;margin-bottom:10px;color:var(--t1);text-transform:uppercase;letter-spacing:.5px}
.chc h3 span{font-weight:400;color:var(--t3)}
.chw{position:relative;height:260px}

/* TABLE */
.tc{background:var(--bg2);border:1px solid var(--t4);border-radius:4px;padding:14px 16px;margin-bottom:16px;overflow:hidden}
.ts{overflow-x:auto;max-width:100%}
table{width:100%;border-collapse:collapse}
th{text-align:right;padding:6px 8px;border-bottom:2px solid var(--t4);font-size:.63rem;text-transform:uppercase;letter-spacing:.5px;color:var(--t2);font-weight:600;white-space:nowrap;cursor:pointer;user-select:none;transition:color .15s}
th:hover{color:var(--t1)}
th .arrow{font-size:.55rem;margin-left:3px;opacity:.4}
th.active .arrow{opacity:1;color:var(--g3)}
th:first-child,th:nth-child(2){text-align:left}
th:first-child{width:28px}
th:nth-child(2){width:62px}
td{text-align:right;padding:5px 8px;border-bottom:1px solid rgba(61,74,92,.4);font-size:.72rem;white-space:nowrap;color:var(--t1)}
td:first-child,td:nth-child(2){text-align:left}
td:first-child{color:var(--t3)}
tr:hover td{background:rgba(16,185,129,.02)}

.foot{display:flex;justify-content:center;gap:16px;padding:14px 0;font-size:.65rem;color:var(--t3)}
.foot a{color:var(--g3);text-decoration:none}
</style>
</head>
<body>
<div class="c">

<div class="hdr">
  <div class="hdr-l">
    <h1>Fast Ejendom Danmark A/S</h1>
    <span class="tk">FED.CO</span>
    <span class="tg">Safe Harbour Tilbagekøb</span>
  </div>
  <div class="hdr-r">
    <div class="pair"><div class="lb">NAV</div><div class="vl g" id="hNav"></div></div>
    <div class="pair"><div class="lb">Kurs</div><div class="vl" id="hKrs"></div></div>
    <div class="pair"><div class="lb">Rabat</div><div class="vl g" id="hRab"></div></div>
  </div>
</div>

<div class="kpis" id="kpis"></div>

<div class="vc">
  <div class="sh">Værdiskabelse ved annullering</div>
  <div class="vc-flow" id="vcG"></div>
  <div class="vc-n" id="mn"></div>
</div>

<div class="prog">
  <div class="prog-top"><span class="sh" style="margin:0" id="pHdr">Programmer</span><span class="pct" id="pPct"></span></div>
  <div class="prog-bar"><div class="prog-fill" id="pF"></div></div>
  <div class="prog-lbl"><span>0</span><span id="pL"></span><span id="pMax">—</span></div>
  <div id="pDetail" style="margin-top:8px;display:flex;gap:20px;font-size:.65rem;color:var(--t2)"></div>
</div>

<div class="charts">
  <div class="chc"><h3>Købskurs vs. NAV <span>— DKK/aktie</span></h3><div class="chw"><canvas id="ch1"></canvas></div></div>
  <div class="chc"><h3>ROIC <span>— akkumuleret %</span></h3><div class="chw"><canvas id="ch2"></canvas></div></div>
  <div class="chc"><h3>Værdiskabelse <span>— akkumuleret DKK</span></h3><div class="chw"><canvas id="ch3"></canvas></div></div>
  <div class="chc"><h3>Handelsvolumen <span>— tilbagekøb vs. marked</span></h3><div class="chw"><canvas id="ch4"></canvas></div></div>
  <div class="chc" style="grid-column:1/-1"><h3>Tilbagekøb som % af markedsvolumen <span>— ugentlig</span></h3><div class="chw" style="height:200px"><canvas id="ch5"></canvas></div></div>
</div>

<div class="tc">
  <div class="sh">Ugentligt køb og likviditet</div>
  <div class="ts"><table id="tbl"><thead><tr>
    <th>#</th><th>Dato</th><th>Købt</th><th>Kurs</th><th>Beløb</th>
    <th>Mkt.vol</th><th>% af vol</th><th>Udnyttelse</th>
    <th>Akk.stk</th><th>Akk.DKK</th><th>NAV</th><th>Rabat</th>
    <th>Accr.</th><th>Værdi</th><th>ROIC</th>
  </tr></thead><tbody id="tb"></tbody></table></div>
</div>

<div class="foot">
  <span>Kilde: <a href="https://fastejendom.dk/investor/selskabsmeddelelser/" target="_blank">fastejendom.dk</a></span>
  <span>·</span><span>Auto-opdateret</span><span>·</span><span id="upd"></span>
</div>

</div>
<script>
const D=__DATA_JSON__,TS=D.total_shares;
function gN(d){let n=D.nav_history[0].nav;for(const e of D.nav_history)if(d>=e.from)n=e.nav;return n}

function calc(){
  const r=[];
  let grandShares=0, grandAmount=0;
  for(const a of D.announcements){
    // Grand total accumulates through all programs (for combined view)
    grandShares += a.week_shares;
    grandAmount += a.week_amount;

    const nav=gN(a.announcement_date),
      wA=a.week_shares>0?a.week_amount/a.week_shares:0,
      gA=grandShares>0?grandAmount/grandShares:0,  // Grand avg price
      disc=(nav-wA)/nav*100,
      nSh=TS-grandShares,  // Remaining shares after all buybacks
      nNAV=(nav*TS-grandAmount)/nSh,
      accr=nNAV-nav,
      vc=accr*nSh,
      roic=grandAmount>0?vc/grandAmount*100:0;
    r.push({
      d:a.announcement_date,
      wS:a.week_shares,wAmt:a.week_amount,wA,
      aS:grandShares,aAmt:grandAmount,aA:gA,  // Use grand totals as "akkumuleret"
      nav,disc,nNAV,accr,vc,nSh,roic,
      mVol:a.market_volume||0,bPct:a.buyback_pct_of_volume||0,
      maxW:a.max_allowed_week||0,util:a.utilization_pct||0
    });
  }
  return r;
}

function fD(n){return n.toLocaleString('da-DK')}
function fM(n){return(n/1e6).toFixed(2)}
function fK(n){return(n/1e3).toFixed(0)}

function render(){
  const rows=calc(),R=rows[rows.length-1],kurs=D.current_price||222,nav=R.nav,
    totMax=(D.programs||[{max_amount:D.program_max}]).reduce((s,p)=>s+p.max_amount,0),
    pU=R.aAmt/totMax*100,dB=(nav-R.aA)/nav*100,dM=(nav-kurs)/nav*100,vPS=R.vc/R.nSh;

  document.getElementById('hNav').textContent=nav.toFixed(2);
  document.getElementById('hKrs').textContent=kurs;
  document.getElementById('hRab').textContent=dM.toFixed(1)+'%';

  // KPIs: T1 white for facts, green spectrum for value metrics
  document.getElementById('kpis').innerHTML=[
    {l:'Tilbagekøbt',v:fD(R.aS),s:(R.aS/TS*100).toFixed(2)+'% af udstedte',c:''},
    {l:'Investeret',v:fM(R.aAmt)+' mio.',s:pU.toFixed(1)+'% af ramme',c:''},
    {l:'Gns. købskurs',v:R.aA.toFixed(2),s:dB.toFixed(1)+'% under NAV',c:''},
    {l:'NAV-accretion',v:'+'+R.accr.toFixed(2),s:nav.toFixed(0)+' → '+R.nNAV.toFixed(2),c:'color:var(--g2)'},
    {l:'Værdiskabelse',v:fM(R.vc)+' mio.',s:vPS.toFixed(2)+' DKK/aktie',c:'color:var(--g3)'},
    {l:'ROIC',v:R.roic.toFixed(1)+'%',s:'Afkast/inv. krone',c:'color:var(--g4)'},
  ].map(k=>`<div class="kpi"><div class="l">${k.l}</div><div class="v" style="${k.c}">${k.v}</div><div class="s">${k.s}</div></div>`).join('');

  document.getElementById('vcG').innerHTML=`
    <div class="vb a"><div class="nm">${fD(R.aS)} stk.</div><div class="lb">Tilbagekøbt til gns.</div><div class="dt">${R.aA.toFixed(2)} DKK/aktie · ${fM(R.aAmt)} mio. DKK</div></div>
    <div class="vc-ar">→</div>
    <div class="vb b"><div class="nm" style="color:var(--g2)">+${R.accr.toFixed(2)} DKK</div><div class="lb">NAV-accretion pr. aktie</div><div class="dt">${nav.toFixed(2)} → ${R.nNAV.toFixed(2)} ved annullering</div></div>
    <div class="vc-ar">→</div>
    <div class="vb c"><div class="nm" style="color:var(--g4)">${fM(R.vc)} mio.</div><div class="lb">Total værdiskabelse</div><div class="dt">${vPS.toFixed(2)} DKK/aktie · ROIC ${R.roic.toFixed(1)}%</div></div>`;

  document.getElementById('mn').textContent=
    'Ny NAV = (egenkapital − købsbeløb) / (udstedte − tilbagekøbte). Værdiskabelse = (ny NAV − nuv. NAV) × '+fD(R.nSh)+' resterende aktier.';

  // Progress bar — combined across all programs
  const progs = D.programs || [{id:1, max_amount:D.program_max}];
  const totalMax = progs.reduce((s,p)=>s+p.max_amount,0);
  const totalPct = R.aAmt/totalMax*100;
  document.getElementById('pHdr').textContent = `Programmer — ${fM(totalMax)} mio. DKK total`;
  document.getElementById('pF').style.width=Math.min(totalPct,100)+'%';
  document.getElementById('pPct').textContent=totalPct.toFixed(1)+'%';
  document.getElementById('pL').textContent=fM(R.aAmt)+' mio. brugt';
  document.getElementById('pMax').textContent=fD(totalMax);

  // Per-program detail
  let remaining = R.aAmt;
  document.getElementById('pDetail').innerHTML = progs.map(p=>{
    const used = Math.min(remaining, p.max_amount);
    remaining -= used;
    const pct = used/p.max_amount*100;
    const status = p.closed_on ? `<span style="color:var(--t3)">Afsluttet ${new Date(p.closed_on).toLocaleDateString('da-DK',{day:'numeric',month:'short'})}</span>` :
                   pct>=99.9 ? `<span style="color:var(--g3)">Afsluttet</span>` :
                   `<span style="color:var(--g2)">Aktivt</span>`;
    return `<div>Program ${p.id}: ${fM(used)} / ${fM(p.max_amount)} mio. (${pct.toFixed(1)}%) · ${status}</div>`;
  }).join('');

  // Chart config — T2 for axis ticks (readable), T4 for grid (structural)
  const lbl=rows.map(r=>new Date(r.d).toLocaleDateString('da-DK',{day:'numeric',month:'short'}));
  const cO=(x={})=>({responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false,...(x.lg||{})},
      tooltip:{backgroundColor:'#1a2230',titleFont:{family:'JetBrains Mono',size:11},
        bodyFont:{family:'JetBrains Mono',size:11},borderColor:'#3d4a5c',borderWidth:1,
        titleColor:'#f8fafc',bodyColor:'#b0bac9',
        padding:8,cornerRadius:3,
        callbacks:{label:c=>{let v=c.parsed.y;return(c.dataset.label?c.dataset.label+': ':'')+((c.dataset.pct)?v.toFixed(1)+'%':v>=1e6?fM(v)+' mio.':v>=1e3?fK(v)+'K':v.toFixed(2))}}}},
    scales:{
      x:{ticks:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},maxRotation:45},grid:{color:'rgba(61,74,92,.35)'}},
      y:{ticks:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},
        callback:v=>v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v,...(x.yt||{})},
        grid:{color:'rgba(61,74,92,.35)'},...(x.y||{})}}});

  // Chart 1: Price vs NAV — white=price (fact), green dashed=NAV (target)
  new Chart(document.getElementById('ch1'),{type:'line',data:{labels:lbl,datasets:[
    {label:'NAV',data:rows.map(r=>r.nav),borderColor:'#34d399',borderWidth:1.5,borderDash:[5,3],pointRadius:1.5,pointBackgroundColor:'#34d399',fill:false},
    {label:'Købskurs',data:rows.map(r=>Math.round(r.wA*100)/100),borderColor:'#f8fafc',backgroundColor:'rgba(248,250,252,.04)',borderWidth:2,fill:true,tension:.3,pointRadius:2.5,pointBackgroundColor:'#f8fafc'}
  ]},options:cO({lg:{display:true,labels:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},boxWidth:10,padding:12}}})});

  // Chart 2: ROIC
  new Chart(document.getElementById('ch2'),{type:'line',data:{labels:lbl,datasets:[{
    label:'ROIC',data:rows.map(r=>Math.round(r.roic*10)/10),
    borderColor:'#10b981',backgroundColor:'rgba(16,185,129,.06)',borderWidth:2,fill:true,tension:.3,
    pointRadius:2.5,pointBackgroundColor:'#10b981',pct:true
  }]},options:cO({y:{beginAtZero:true},yt:{callback:v=>v+'%'}})});

  // Chart 3: Value creation
  new Chart(document.getElementById('ch3'),{type:'line',data:{labels:lbl,datasets:[{
    label:'Værdiskabelse',data:rows.map(r=>Math.round(r.vc)),
    borderColor:'#059669',backgroundColor:'rgba(5,150,105,.08)',borderWidth:2,fill:true,tension:.3,
    pointRadius:2.5,pointBackgroundColor:'#059669'
  }]},options:cO()});

  // Chart 4: Volume — market volume (grey) vs buyback (white)
  // Skip first data point for y-axis max calc if it's a spike (>2x median)
  const hasMktVol = rows.some(r=>r.mVol>0);
  const volData = rows.map(r=>r.mVol);
  const buyData = rows.map(r=>r.wS);
  const ch4datasets = [{
    label:'Tilbagekøbt',
    data:buyData,backgroundColor:'rgba(248,250,252,.25)',borderColor:'rgba(248,250,252,.4)',
    borderWidth:1,borderRadius:2
  }];
  if(hasMktVol){
    ch4datasets.unshift({
      label:'Markedsvolumen',
      data:volData,backgroundColor:'rgba(176,186,201,.1)',borderColor:'rgba(176,186,201,.2)',
      borderWidth:1,borderRadius:2
    });
  }
  // Calculate a sensible y-max excluding outlier first week
  const allVols = hasMktVol ? volData.slice(1) : buyData.slice(1);
  const sugMax = Math.max(...allVols) * 1.2;
  new Chart(document.getElementById('ch4'),{type:'bar',data:{labels:lbl,datasets:ch4datasets},
    options:cO({y:{beginAtZero:true,suggestedMax:sugMax>0?sugMax:undefined},
      lg:{display:hasMktVol,labels:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},boxWidth:10,padding:12}}})});

  // Chart 5: Buyback as % of market volume — color-coded bars + average line + 25% limit
  if(hasMktVol){
    const pctData = rows.map(r=>r.bPct);
    const pctColors = pctData.map(p=>p>40?'rgba(239,68,68,.6)':p>20?'rgba(245,158,11,.6)':'rgba(16,185,129,.5)');
    // Cumulative average line
    let cumSum=0;
    const avgLine = pctData.map((p,i)=>{cumSum+=p;return Math.round(cumSum/(i+1)*10)/10});
    // 25% Safe Harbour limit line (constant across all announcements)
    const limitLine = pctData.map(()=>25);
    new Chart(document.getElementById('ch5'),{type:'bar',data:{labels:lbl,datasets:[
      {label:'% af volumen',data:pctData,backgroundColor:pctColors,borderColor:pctColors.map(c=>c.replace(/[\d.]+\)$/,'0.8)')),borderWidth:1,borderRadius:2,pct:true,order:3},
      {label:'Gennemsnit',data:avgLine,type:'line',borderColor:'#f8fafc',borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:.3,fill:false,pct:true,order:2},
      {label:'25% Safe Harbour loft',data:limitLine,type:'line',borderColor:'#f59e0b',borderWidth:1.5,borderDash:[8,4],pointRadius:0,fill:false,pct:true,order:1}
    ]},options:cO({y:{beginAtZero:true},yt:{callback:v=>v+'%'},
      lg:{display:true,labels:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},boxWidth:10,padding:12}}})});
  } else {
    // No volume data yet — show placeholder
    const ctx5=document.getElementById('ch5').getContext('2d');
    ctx5.fillStyle='#6b7a90';ctx5.font='12px JetBrains Mono';
    ctx5.textAlign='center';ctx5.fillText('Volume-data hentes ved næste automatiske opdatering',
      document.getElementById('ch5').width/2, 100);
  }

  // Sortable table
  const cols=[
    {k:'i',l:'#',left:true},
    {k:'d',l:'Dato',left:true},
    {k:'wS',l:'Købt'},
    {k:'wA',l:'Kurs'},
    {k:'wAmt',l:'Beløb'},
    {k:'mVol',l:'Mkt.vol'},
    {k:'bPct',l:'% af vol'},
    {k:'util',l:'Udnyttelse'},
    {k:'aS',l:'Akk.stk'},
    {k:'aAmt',l:'Akk.DKK'},
    {k:'nav',l:'NAV'},
    {k:'disc',l:'Rabat'},
    {k:'accr',l:'Accr.'},
    {k:'vc',l:'Værdi'},
    {k:'roic',l:'ROIC'}
  ];

  let sortCol='i', sortDir='desc'; // default: newest first

  function renderTable(){
    const sorted=[...rows].map((r,i)=>({...r,i:i+1}));
    sorted.sort((a,b)=>{
      let va=a[sortCol],vb=b[sortCol];
      if(sortCol==='d'){va=a.d;vb=b.d;}
      if(typeof va==='string')return sortDir==='asc'?va.localeCompare(vb):vb.localeCompare(va);
      return sortDir==='asc'?(va-vb):(vb-va);
    });

    // Update header arrows
    document.querySelectorAll('#tbl th').forEach((th,ci)=>{
      const col=cols[ci];
      const isActive=col.k===sortCol;
      th.className=isActive?'active':'';
      th.innerHTML=(col.left?'':'')+ col.l + `<span class="arrow">${isActive?(sortDir==='desc'?'▼':'▲'):'⇅'}</span>`;
      if(col.left)th.style.textAlign='left';
    });

    document.getElementById('tb').innerHTML=sorted.map(r=>`<tr>
      <td>${r.i}</td>
      <td>${new Date(r.d).toLocaleDateString('da-DK',{day:'numeric',month:'short'})}</td>
      <td>${fD(r.wS)}</td>
      <td>${r.wA.toFixed(2)}</td>
      <td>${fK(r.wAmt)}K</td>
      <td>${r.mVol>0?fD(r.mVol):'—'}</td>
      <td style="color:${r.bPct>40?'var(--red)':r.bPct>20?'var(--amb)':'var(--g3)'}">${r.bPct>0?r.bPct.toFixed(1)+'%':'—'}</td>
      <td style="color:${r.util>80?'var(--g3)':r.util>50?'var(--amb)':r.util>0?'var(--red)':'var(--t3)'}">${r.util>0?r.util.toFixed(0)+'%':'—'}</td>
      <td><b>${fD(r.aS)}</b></td>
      <td>${fM(r.aAmt)}M</td>
      <td>${r.nav.toFixed(2)}</td>
      <td style="color:var(--g1)">${r.disc.toFixed(1)}%</td>
      <td style="color:var(--g2)">+${r.accr.toFixed(2)}</td>
      <td style="color:var(--g3)"><b>${fM(r.vc)}M</b></td>
      <td style="color:var(--g4)">${r.roic.toFixed(1)}%</td>
    </tr>`).join('');
  }

  // Build header with click handlers
  const thead=document.getElementById('tbl').querySelector('thead tr');
  thead.innerHTML='';
  cols.forEach(col=>{
    const th=document.createElement('th');
    if(col.left)th.style.textAlign='left';
    th.addEventListener('click',()=>{
      if(sortCol===col.k){sortDir=sortDir==='desc'?'asc':'desc';}
      else{sortCol=col.k;sortDir='desc';}
      renderTable();
    });
    thead.appendChild(th);
  });

  renderTable();

  document.getElementById('upd').textContent='Sidst: '+(D.last_updated?new Date(D.last_updated).toLocaleDateString('da-DK',{day:'numeric',month:'short',year:'numeric'}):'—');
}
render();
</script>
<script data-goatcounter="https://kajsersoze.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
