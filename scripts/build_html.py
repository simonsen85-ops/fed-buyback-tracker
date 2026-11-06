#!/usr/bin/env python3
"""Generates index.html from data.json (+ the Gæld tab model from scripts/debt.py)."""
import json
import traceback
from pathlib import Path

from debt import build_model

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data.json"
OUTPUT_FILE = ROOT / "index.html"

def build():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    try:
        debt = build_model(data)
    except Exception:
        # The buyback page must still build; the Gæld tab then shows a notice.
        print("WARNING: Gæld tab model failed — tab will show a notice:")
        traceback.print_exc()
        debt = None
    debt_json = json.dumps(debt, ensure_ascii=False, separators=(',', ':'), default=str)
    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json).replace("__DEBT_JSON__", debt_json)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Built {OUTPUT_FILE} with {len(data['announcements'])} announcements"
          + (f"; Gæld tab: {debt['loans_count']} loans" if debt else "; Gæld tab: NO DATA"))

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
/* Buyback tab: two decision cards only (the value boxes below hold the rest) */
.kpis.k2{grid-template-columns:repeat(2,1fr)}
.kpis.k2 .kpi{padding:14px 18px}
.kpis.k2 .kpi .v{font-size:1.6rem}
@media(max-width:500px){.kpis.k2{grid-template-columns:1fr}}
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
th:first-child{text-align:left;width:62px}
td{text-align:right;padding:5px 8px;border-bottom:1px solid rgba(61,74,92,.4);font-size:.72rem;white-space:nowrap;color:var(--t1)}
td:first-child{text-align:left}
tr:hover td{background:rgba(16,185,129,.02)}

.foot{display:flex;justify-content:center;gap:16px;padding:14px 0;font-size:.65rem;color:var(--t3)}
.foot a{color:var(--g3);text-decoration:none}

/* TABS */
.tabs{display:flex;gap:4px;margin:-6px 0 16px;border-bottom:1px solid var(--t4)}
.tabs button{font-family:'Outfit',sans-serif;font-size:.78rem;font-weight:600;letter-spacing:.4px;text-transform:uppercase;
  background:none;border:0;border-bottom:2px solid transparent;color:var(--t2);padding:8px 14px;cursor:pointer;margin-bottom:-1px}
.tabs button:hover{color:var(--t1)}
.tabs button.on{color:var(--t1);border-bottom-color:var(--g3)}
.tabs button:focus-visible{outline:2px solid var(--g3);outline-offset:2px}

/* GÆLD TAB — series identity colours (validated against #141a24) */
#tab-gaeld{--s-fixed:#3987e5;--s-f5:#d95926;--s-cibor6:#199e70}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:baseline}
.sw.fixed{background:var(--s-fixed)}.sw.f5{background:var(--s-f5)}.sw.cibor6{background:var(--s-cibor6)}
.dnote{font-size:.67rem;color:var(--t3);line-height:1.55;margin-top:10px;padding-top:10px;border-top:1px solid var(--t4)}
.dnote p+p{margin-top:5px}
.dtbl td{white-space:nowrap}
.dtbl th{cursor:default;white-space:normal;vertical-align:bottom;line-height:1.35}
.dtbl td.l,.dtbl th.l{text-align:left}
.dtbl tr.sep td{border-top:2px solid var(--t4)}
.dtbl tr.sum td{border-top:2px solid var(--t4);font-weight:700}
.dtbl tr.cont td.pc{color:transparent}
#dProp tr.grp.x{cursor:pointer}
#dProp tr.grp.x:hover td{background:rgba(16,185,129,.03)}
.exp{background:none;border:0;color:var(--t2);cursor:pointer;font:inherit;width:14px;padding:0;margin-right:4px;text-align:left}
.exp:focus-visible{outline:2px solid var(--g3);outline-offset:1px}
.exp-sp{display:inline-block;width:14px;margin-right:4px}
#dProp tr.det td{background:rgba(248,250,252,.015);font-size:.68rem;padding-top:3px;padding-bottom:3px}
#dProp tr.det td:nth-child(5){padding-left:26px}
.tag{display:inline-block;font-size:.6rem;padding:1px 6px;border-radius:3px;letter-spacing:.4px;text-transform:uppercase;border:1px solid var(--t4);color:var(--t2)}
.tag.free{color:var(--t1);border-color:var(--t3)}
.ok{color:var(--g2)}.warn{color:var(--amb)}
.pos{color:var(--g3)}.neg{color:var(--red)}
#dKpis .kpi{display:flex;flex-direction:column}
.kpi .sens{margin-top:auto;padding-top:8px}
.kpi .sens .sb{border-top:1px solid var(--t4);margin-top:10px;padding-top:7px}
.kpi .sens .sl{font-size:.6rem;color:var(--t3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;white-space:nowrap}
.kpi .sens .sg{display:grid;grid-template-columns:auto auto;column-gap:16px;row-gap:1px;justify-content:start}
.kpi .sens .sg span{font-size:.6rem;color:var(--t3);white-space:nowrap}
.kpi .sens .sg b{font-size:.85rem;white-space:nowrap}
@media(min-width:901px){#dKpis{grid-template-columns:repeat(5,1fr)}}
.pend{color:var(--t3);font-style:italic}
.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
@media(max-width:860px){.dgrid{grid-template-columns:1fr}}
.dgrid>.tc{margin-bottom:0}
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

<nav class="tabs" role="tablist">
  <button role="tab" data-tab="tilbagekob" class="on" aria-selected="true">Tilbagekøb</button>
  <button role="tab" data-tab="gaeld" aria-selected="false">Gæld</button>
</nav>

<section id="tab-tilbagekob" class="tabp" role="tabpanel">
<div class="kpis k2" id="kpis"></div>

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
  <div class="chc"><h3>Afkast pr. krone <span>— ugentlig, %</span></h3><div class="chw"><canvas id="ch2"></canvas></div></div>
  <div class="chc"><h3>Værdi skabt v. køb <span>— akkumuleret DKK</span></h3><div class="chw"><canvas id="ch3"></canvas></div></div>
  <div class="chc"><h3>Udnyttelse af Safe Harbour-loft <span>— ugentlig, % af maks. tilladt</span></h3><div class="chw"><canvas id="ch4"></canvas></div></div>
  <div class="chc" style="grid-column:1/-1"><h3>Tilbagekøb som % af markedsvolumen <span>— ugentlig</span></h3><div class="chw" style="height:200px"><canvas id="ch5"></canvas></div></div>
</div>

<div class="tc">
  <div class="sh">Ugentligt køb og likviditet</div>
  <div class="ts"><table id="tbl"><thead><tr>
    <th>Dato</th><th>Købt</th><th>Gns. kurs</th><th>Beløb</th><th>NAV v. køb</th>
    <th>Afkast pr. krone</th><th>Markedsvolumen</th><th>Udnyttelse</th><th>Akk. investeret</th><th>Værdi skabt</th>
  </tr></thead><tbody id="tb"></tbody></table></div>
</div>
</section>

<section id="tab-gaeld" class="tabp" role="tabpanel" hidden>
<div class="kpis" id="dKpis"></div>

<div class="tc">
  <div class="sh">Lånetyper — afledt af tinglysningsdato · mio. DKK</div>
  <div class="ts"><table class="dtbl" id="dRec"></table></div>
  <div class="sh" style="margin-top:18px">Hvordan gælden er nedbragt · mio. DKK</div>
  <div class="ts"><table class="dtbl" id="dFall"></table></div>
  <div class="dnote" id="dRecN"></div>
</div>

<div class="dgrid">
  <div class="chc">
    <h3>Gældsmiks pr. kvartal <span>— FED's rapporterede fordeling, mio. DKK</span></h3>
    <div class="chw" style="height:240px"><canvas id="dCh1" aria-label="Gældsmiks pr. kvartal, stablet søjle" role="img"></canvas></div>
    <div class="dnote" id="dMixN"></div>
  </div>
  <div class="tc">
    <div class="sh">Afkast ved indfrielse vs. tilbagekøb</div>
    <div class="ts"><table class="dtbl" id="dYld"></table></div>
    <div class="dnote" id="dYldN"></div>
  </div>
</div>

<div class="tc">
  <div class="sh">Fast gæld — proxy-obligationer · mio. DKK</div>
  <div class="ts"><table class="dtbl" id="dBond"></table></div>
  <div class="dnote" id="dBondN"></div>
</div>

<div class="tc">
  <div class="sh">Ejendomme og tinglyste realkreditlån</div>
  <div class="ts"><table class="dtbl" id="dProp"></table></div>
  <div class="dnote" id="dPropN"></div>
</div>
</section>

<div class="foot">
  <span>Kilde: <a href="https://fastejendom.dk/investor/selskabsmeddelelser/" target="_blank">fastejendom.dk</a></span>
  <span>·</span><span>Auto-opdateret</span><span>·</span><span id="upd"></span>
</div>

</div>
<script>
const D=__DATA_JSON__,TS=D.total_shares;
// Shares outstanding (excl. treasury) before the programmes. FED's NAV/share is
// equity / shares OUTSTANDING, so this is the base for "NAV without buybacks".
const N0=D.shares_outstanding_start||2606979;
function gN(d){let n=D.nav_history[0].nav;for(const e of D.nav_history)if(d>=e.from)n=e.nav;return n}

// Every individual trade (daily where available, else the week booked at period_end)
const TR=D.announcements.flatMap(a=>{
  const dl=a.daily_transactions;
  if(dl&&dl.length)return dl.filter(x=>x.shares>0).map(x=>({d:x.date,s:x.shares,a:x.amount}));
  return a.week_shares>0?[{d:a.period_end||a.announcement_date,s:a.week_shares,a:a.week_amount}]:[];
}).sort((x,y)=>x.d.localeCompare(y.d));

// Balance-sheet date a NAV refers to: explicit period_end, else last quarter-end before publication
function qEnd(e){if(e.period_end)return e.period_end;
  const t=new Date(e.from+'T00:00:00Z'),q=Math.floor(t.getUTCMonth()/3);
  return new Date(Date.UTC(t.getUTCFullYear(),q*3,0)).toISOString().slice(0,10)}

// Reported NAV already contains the accretion from buybacks made before its balance-sheet
// date. Strip it out: NAVex = (NAV × shares outstanding + amount spent) / N0.
// Value created vs. "no buybacks" is then simply  shares bought × NAVex − amount paid.
const NX=D.nav_history.map(e=>{const qe=qEnd(e);let s=0,a=0;
  for(const t of TR)if(t.d<=qe){s+=t.s;a+=t.a}
  return {...e,qe,navEx:(e.nav*(N0-s)+a)/N0}});
function gX(d){let r=NX[0];for(const e of NX)if(d>=e.from)r=e;return r}

function calc(){
  const r=[];
  let grandShares=0, grandAmount=0, vAt=0, sNavAt=0;
  for(const a of D.announcements){
    grandShares += a.week_shares;
    grandAmount += a.week_amount;
    // Trades in this announcement, each valued at the ex-programme NAV known on the trade date
    const dl=(a.daily_transactions&&a.daily_transactions.length)?a.daily_transactions.filter(x=>x.shares>0).map(x=>({d:x.date,s:x.shares,a:x.amount}))
            :(a.week_shares>0?[{d:a.period_end||a.announcement_date,s:a.week_shares,a:a.week_amount}]:[]);
    let wNav=0;
    for(const t of dl){const nx=gX(t.d).navEx;wNav+=t.s*nx;vAt+=t.s*nx-t.a;sNavAt+=t.s*nx}
    const nav=gN(a.announcement_date),            // reported NAV known at announcement
      mk=gX(a.announcement_date),                 // latest NAV anchor, ex-programme
      wA=a.week_shares>0?a.week_amount/a.week_shares:0,
      gA=grandShares>0?grandAmount/grandShares:0,
      navAt=a.week_shares>0?wNav/a.week_shares:mk.navEx,   // ex-programme NAV at purchase (week avg)
      disc=navAt>0?(1-wA/navAt)*100:0,                   // discount to NAV at purchase
      nSh=N0-grandShares,                                // shares outstanding after buybacks
      vc=grandShares*mk.navEx-grandAmount,               // value created today (mark-to-NAV)
      accr=nSh>0?vc/nSh:0,                               // NAV/share uplift vs. no buybacks
      roiAt=grandAmount>0?vAt/grandAmount*100:0,         // ROI at purchase
      roic=grandAmount>0?vc/grandAmount*100:0,           // ROI today (mark-to-NAV)
      grw=roic-roiAt;                                    // NAV development since purchase, pp
    r.push({
      d:a.announcement_date,
      wS:a.week_shares,wAmt:a.week_amount,wA,
      aS:grandShares,aAmt:grandAmount,aA:gA,
      nav,navEx:mk.navEx,navAt,disc,accr,vc,vAt,nSh,roiAt,roic,grw,
      navAtAvg:grandShares>0?sNavAt/grandShares:0,
      mVol:a.market_volume||0,bPct:a.buyback_pct_of_volume||0,
      maxW:a.max_allowed_week||0,util:a.utilization_pct||0,
      avg20:a.avg_volume_20d||0,detail:a.daily_volume_detail||[]
    });
  }
  return r;
}

// Headline figures are marked at the LATEST NAV, even if it was published after the last buyback week
function markNow(R){const L=NX[NX.length-1];if(!(L.from>R.d))return R;
  const vc=R.aS*L.navEx-R.aAmt,roic=R.aAmt>0?vc/R.aAmt*100:0;
  return {...R,nav:L.nav,navEx:L.navEx,vc,accr:R.nSh>0?vc/R.nSh:0,roic,grw:roic-R.roiAt}}

function fD(n){return n.toLocaleString('da-DK')}
function fM(n){return(n/1e6).toFixed(2)}
function fK(n){return(n/1e3).toFixed(0)}
// Afkast pr. krone for one week: NAV v. køb / avg price − 1, in % (null if nothing was bought)
function aPK(r){return r.wA>0?(r.navAt/r.wA-1)*100:null}
// FED's average loan rate 4.06 % (Q3 2026 report) after 22 % tax ≈ 3.2 %: the alternative use of the krone
const DEBT_AT=3.2;

function render(){
  const rows=calc(),R=markNow(rows[rows.length-1]),kurs=D.current_price||222,nav=R.nav,
    totMax=(D.programs||[{max_amount:D.program_max}]).reduce((s,p)=>s+p.max_amount,0),
    pU=R.aAmt/totMax*100,dB=(1-R.aA/R.navAtAvg)*100,dM=(nav-kurs)/nav*100,vPS=R.vAt/R.nSh;

  document.getElementById('hNav').textContent=nav.toFixed(2);
  document.getElementById('hKrs').textContent=kurs;
  document.getElementById('hRab').textContent=dM.toFixed(1)+'%';

  // KPIs: only the two decision figures — how past purchases did, and whether to keep buying.
  // Everything else (shares, amount, avg price, value created) is in the value boxes below.
  document.getElementById('kpis').innerHTML=[
    {l:'ROI v. køb',v:R.roiAt.toFixed(1)+'%',s:'Værdi skabt pr. investeret krone, målt ved købet',c:'color:var(--g2)'},
    {l:'Afkast på næste krone',v:((nav/kurs-1)*100).toFixed(1)+'%',s:'vs. ~'+DEBT_AT.toFixed(1).replace('.',',')+'% efter skat ved gældsnedbringelse',c:'color:var(--g4)'},
  ].map(k=>`<div class="kpi"><div class="l">${k.l}</div><div class="v" style="${k.c}">${k.v}</div><div class="s">${k.s}</div></div>`).join('');

  // Value box: value created AT PURCHASE only. NAV development after purchase is
  // property performance, not a buyback effect, and is deliberately not shown.
  const dk=(n,d)=>n.toLocaleString('da-DK',{minimumFractionDigits:d,maximumFractionDigits:d});
  document.getElementById('vcG').innerHTML=`
    <div class="vb a"><div class="nm">${fD(R.aS)} stk.</div><div class="lb">Tilbagekøbt</div><div class="dt">${dk(R.aAmt/1e6,2)} mio. kr. til gns. ${dk(R.aA,2)} kr./aktie<br>${dk(R.aS/N0*100,2)} % af aktierne · ${dk(dB,1)} % under NAV v. køb</div></div>
    <div class="vc-ar">→</div>
    <div class="vb b"><div class="nm" style="color:var(--g2)">+${dk(vPS,2)} kr./aktie</div><div class="lb">Pr. aktie i omløb</div><div class="dt">${dk(R.vAt/1e6,2)} mio. / ${fD(R.nSh)} aktier i omløb</div></div>
    <div class="vc-ar">→</div>
    <div class="vb c"><div class="nm" style="color:var(--g4)">${dk(R.vAt/1e6,2)} mio.</div><div class="lb">Værdi skabt v. køb</div><div class="dt">Købte aktier × NAV v. køb − købsbeløb</div></div>`;

  document.getElementById('mn').textContent=
    'NAV uden tilbagekøb = (rapporteret NAV × aktier i omløb + beløb brugt før balancedagen) / '+fD(N0)+' (aktier i omløb før program). '+
    'Rapporteret NAV indeholder allerede tidligere tilbagekøbs accretion — den fjernes, så den ikke tælles dobbelt. '+
    'Værdi skabt v. køb = tilbagekøbte aktier × NAV uden tilbagekøb kendt på handelsdagen − købsbeløb; pr. aktie fordeles den på de '+fD(R.nSh)+' aktier i omløb i dag. '+
    'NAV-udvikling efter købet er ejendommenes afkast, ikke tilbagekøbets, og indgår derfor ikke.';

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

  // Chart 2: Afkast pr. krone per week vs. the after-tax return on paying down debt
  const lgO={display:true,labels:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},boxWidth:10,padding:12}};
  new Chart(document.getElementById('ch2'),{type:'bar',data:{labels:lbl,datasets:[
    {label:'Afkast pr. krone',data:rows.map(r=>{const v=aPK(r);return v===null?null:Math.round(v*10)/10}),
     backgroundColor:'rgba(110,231,183,.45)',borderColor:'rgba(110,231,183,.8)',borderWidth:1,borderRadius:2,pct:true,order:2},
    {label:'Gældsnedbringelse efter skat',data:rows.map(()=>DEBT_AT),type:'line',
     borderColor:'#b0bac9',borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false,pct:true,order:1}
  ]},options:cO({y:{beginAtZero:true},yt:{callback:v=>v+'%'},lg:lgO})});

  // Chart 3: Value created at purchase, cumulative
  new Chart(document.getElementById('ch3'),{type:'line',data:{labels:lbl,datasets:[
    {label:'Værdi skabt v. køb',data:rows.map(r=>Math.round(r.vAt)),
     borderColor:'#10b981',backgroundColor:'rgba(16,185,129,.08)',borderWidth:2,fill:true,tension:.3,
     pointRadius:2.5,pointBackgroundColor:'#10b981'}
  ]},options:cO()});

  // Chart 4: Safe Harbour utilisation — shares bought as % of the max allowed
  // (25 % of 20-day average daily volume × trading days), same colours as the table
  const hasMktVol = rows.some(r=>r.mVol>0);
  const utilCol=u=>u>100?'rgba(239,68,68,.6)':u>80?'rgba(16,185,129,.55)':u>50?'rgba(245,158,11,.6)':'rgba(239,68,68,.6)';
  new Chart(document.getElementById('ch4'),{type:'bar',data:{labels:lbl,datasets:[
    {label:'Udnyttelse',data:rows.map(r=>r.util>0?r.util:null),
     backgroundColor:rows.map(r=>utilCol(r.util)),borderColor:rows.map(r=>utilCol(r.util).replace(/[\d.]+\)$/,'0.9)')),
     borderWidth:1,borderRadius:2,pct:true,order:2},
    {label:'Loft (100 %)',data:rows.map(()=>100),type:'line',
     borderColor:'#f59e0b',borderWidth:1.5,borderDash:[8,4],pointRadius:0,fill:false,pct:true,order:1}
  ]},options:cO({y:{min:0,max:100},yt:{callback:v=>v+'%',stepSize:20},lg:lgO})});

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
    {k:'d',l:'Dato',left:true},
    {k:'wS',l:'Købt'},
    {k:'wA',l:'Gns. kurs'},
    {k:'wAmt',l:'Beløb'},
    {k:'navAt',l:'NAV v. køb',t:'Indre værdi pr. aktie på handelsdagene, renset for tidligere tilbagekøbs effekt (vægtet over ugens handler).'},
    {k:'apk',l:'Afkast pr. krone',t:'Indre værdi købt pr. betalt krone: NAV v. køb / gns. kurs − 1.'},
    {k:'mVol',l:'Markedsvolumen'},
    {k:'util',l:'Udnyttelse',t:'Ugens køb i % af Safe Harbour-loftet (25 % af 20-dages gns. volumen).'},
    {k:'aAmt',l:'Akk. investeret'},
    {k:'vAt',l:'Værdi skabt',t:'Akkumuleret værdi ved køb: købte aktier × NAV v. køb − betalt beløb.'}
  ];

  let sortCol='i', sortDir='desc'; // default: newest first

  function renderTable(){
    const sorted=[...rows].map((r,i)=>({...r,i:i+1,apk:aPK(r)??-1e9}));
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
      <td>${new Date(r.d).toLocaleDateString('da-DK',{day:'numeric',month:'short'})}</td>
      <td>${fD(r.wS)}</td>
      <td>${r.wA.toFixed(2)}</td>
      <td>${fK(r.wAmt)}K</td>
      <td>${r.navAt.toFixed(2)}</td>
      <td style="color:var(--g1)">${r.wA>0?aPK(r).toFixed(1)+'%':'—'}</td>
      <td>${r.mVol>0?fD(r.mVol):'—'}</td>
      <td style="color:${r.util>100?'var(--red)':r.util>80?'var(--g3)':r.util>50?'var(--amb)':r.util>0?'var(--red)':'var(--t3)'}" title="${r.avg20>0?`20-dages snit: ${fD(r.avg20)} aktier/dag\nMax tilladt i ugen: ${fD(r.maxW)} aktier (25% × snit × ${r.detail.length} dage)\nFaktisk købt: ${fD(r.wS)} aktier\nUdnyttelse: ${r.util.toFixed(1)}%`:'Ikke nok historik til 20-dages beregning'}">${r.util>0?r.util.toFixed(0)+'%':'—'}</td>
      <td>${fM(r.aAmt)}M</td>
      <td style="color:var(--g3)"><b>${fM(r.vAt)}M</b></td>
    </tr>`).join('');
  }

  // Build header with click handlers
  const thead=document.getElementById('tbl').querySelector('thead tr');
  thead.innerHTML='';
  cols.forEach(col=>{
    const th=document.createElement('th');
    if(col.left)th.style.textAlign='left';
    if(col.t)th.title=col.t;
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

// ============================================================
// GÆLD TAB — model computed in scripts/debt.py, rendered here
// ============================================================
const DB=__DEBT_JSON__;
const TYP=['fixed','f5','cibor6'],TL={fixed:'Fast 4 %',f5:'F5',cibor6:'CIBOR6'},
  SC={fixed:'#3987e5',f5:'#d95926',cibor6:'#199e70'};
function dn(v,d=1){return v==null?'—':v.toLocaleString('da-DK',{minimumFractionDigits:d,maximumFractionDigits:d})}
function dp(v,d=2){return v==null?'—':dn(v,d)+' %'}
function dm(v,d=1){return v==null?'—':dn(v,d)+' mio.'}
function sw(t){return `<span class="sw ${t}"></span>`}
function dDate(s){if(!s)return '—';const[y,m,d]=s.split('-');return `${d}.${m}.${y.slice(2)}`}
const PEND='<span class="pend">afventer</span>';

function renderDebt(){
  const root=document.getElementById('tab-gaeld');
  if(!DB||!DB.mix||!DB.mix.length){root.innerHTML='<div class="tc"><div class="sh">Gæld</div><p class="pend">Gæld-data kunne ikke indlæses ved seneste opdatering.</p></div>';return}
  const O=DB.outstanding_latest_m||{},F=DB.fixed,L=DB.latest_label,MX=DB.mix,ML=MX[MX.length-1];

  // KPI cards
  const prices=F.bonds.map(b=>b.price==null?'—':dn(b.price,2)).join(' / ');
  // NAV/share effect of a ±1 pp rate move for one loan type (debt at fair value, after tax)
  const sens=t=>{const x=(DB.sens||{})[t];if(!x)return '';
    const f=v=>`<b class="${v<0?'neg':'pos'}">${v<0?'−':'+'}${dn(Math.abs(v),2)}</b>`;
    return `<div class="sens" title="${x.method}"><div class="sb"><div class="sl">NAV/aktie ved rente</div>`+
      `<div class="sg"><span>+1 pp</span><span>−1 pp</span>${f(x.up)}${f(x.down)}</div></div></div>`};
  document.getElementById('dKpis').innerHTML=[
    {l:'Nominel prioritetsgæld',v:dm(DB.nominal_latest_m),s:'Rapporteret pr. '+L},
    {l:sw('fixed')+'Fast 4 %',v:dm(O.fixed),s:'ca. '+ML.pct.fixed+' % · FED\'s fordeling',x:sens('fixed')},
    {l:sw('f5')+'F5',v:dm(O.f5),s:'ca. '+ML.pct.f5+' % · tilpasning ca. april 2030',x:sens('f5')},
    {l:sw('cibor6')+'CIBOR6',v:dm(O.cibor6),s:'ca. '+ML.pct.cibor6+' % · tilpasning hvert halve år',x:sens('cibor6')},
    {l:'Markedsværdi fast gæld',v:dm(F.mv_m),s:'Kurs '+prices+' (proxy) · nominelt '+dn(F.outstanding_m,1)},
  ].map(k=>`<div class="kpi"><div class="l">${k.l}</div><div class="v">${k.v}</div><div class="s">${k.s}</div>${k.x||''}</div>`).join('');

  // Reconciliation: registered principal by derived type vs FED's reported split
  const R=DB.recon,ye=MX.find(m=>m.label==='31.12.25');
  const sum=k=>R.reduce((s,r)=>s+(r[k]||0),0),sumP=i=>R.reduce((s,r)=>s+r.periods_m[i],0);
  // Table 1: balances per type — registered principal vs FED's reported outstanding
  document.getElementById('dRec').innerHTML=
    `<thead><tr><th class="l">Type</th><th>Tinglyst hovedstol</th>${MX.map(m=>`<th title="${m.basis}">FED ${m.label}</th>`).join('')}<th title="Udestående ≤ tinglyst hovedstol (inden for FED's afrunding)">Afstemt</th></tr></thead><tbody>`+
    R.map(r=>`<tr><td class="l">${sw(r.type)}${r.label}</td><td>${dn(r.registered_m)}</td>${r.periods_m.map(v=>`<td>${dn(v)}</td>`).join('')}
      <td class="${r.ok_latest?'ok':'warn'}">${r.ok_latest?'✓ ≤ tinglyst':'✗ > tinglyst'}</td></tr>`).join('')+
    `<tr class="sum"><td class="l">I alt</td><td>${dn(sum('registered_m'))}</td>${MX.map((m,i)=>`<td>${dn(sumP(i))}</td>`).join('')}<td></td></tr></tbody>`;

  // Table 2: how the debt came down — 2026 fall split into sales / early redemption / ordinary repayments,
  // plus repayments before 2026; the last column = registered − outstanding (sold loans are on neither side)
  const FL=DB.flows_2026||{},hasF=R.every(r=>r.fall_2026_m!=null);
  const c=(v,b)=>`<td${b?' style="border-left:1px solid var(--t4)"':''}>${v==null?'—':Math.abs(v)<0.05?'—':dn(v)}</td>`;
  document.getElementById('dFall').innerHTML=!hasF?'':
    `<thead><tr><th class="l"></th><th colspan="4" style="text-align:center">Fald i 2026 (${ye.label} → ${L})</th><th colspan="2" style="text-align:center;border-left:1px solid var(--t4)">Nedbragt siden tinglysning</th></tr>`+
    `<tr><th class="l">Type</th><th title="Gæld på de fire ejendomme solgt pr. 1.7.26 — forsvinder fra porteføljen, men er ikke afdrag på de lån FED har tilbage">Salg af ejendomme</th>`+
    `<th title="Indfrielse af prioritetsgæld minus den salgsrelaterede del">Ekstraordinær indfrielse</th><th title="Restpost: fald minus salg minus ekstraordinær indfrielse">Ordinære afdrag*</th><th>I alt</th>`+
    `<th style="border-left:1px solid var(--t4)" title="Tinglyst hovedstol minus FED's udestående 31.12.25 på de nuværende ejendomme">Afdrag før 2026</th><th title="Tinglyst hovedstol minus FED's udestående pr. ${L} = afdrag før 2026 + ekstraordinær indfrielse + ordinære afdrag 2026">I alt</th></tr></thead><tbody>`+
    R.map(r=>`<tr><td class="l">${sw(r.type)}${r.label}</td>${c(r.fall_sale_m)}${c(r.fall_voluntary_m)}${c(r.fall_ordinary_m)}${c(r.fall_2026_m)}${c(r.paid_before_2026_m,1)}${c(r.gap_latest_m)}</tr>`).join('')+
    `<tr class="sum"><td class="l">I alt</td>${c(sum('fall_sale_m'))}${c(sum('fall_voluntary_m'))}${c(sum('fall_ordinary_m'))}${c(sum('fall_2026_m'))}${c(sum('paid_before_2026_m'),1)}${c(sum('gap_latest_m'))}</tr></tbody>`;
  document.getElementById('dRecN').innerHTML=
    `<p>* <b>Ordinære afdrag</b> er restposten pr. type: fald i 2026 minus salg minus ekstraordinær indfrielse. I alt ${dn(sum('fall_ordinary_m'))} mio. mod ${dn(FL.afdrag_m)} mio. rapporteret afdrag; forskellen skyldes FED's afrundede „ca.“-procenter (±0,5 pp ≈ ±3-4 mio. pr. type) og opkøb af obligationer under kurs 100.</p>`+
    `<p><b>Fald i 2026</b> er opdelt efter FED's pengestrømme (${FL.period||''}): <b>salg af ejendomme</b> ${dn(DB.sold_properties_debt_m)} mio. = gælden på de fire ejendomme solgt pr. 1.7.26 (15,3 mio. ekstraordinært afdrag i H1 + 34,7 mio. indfriet ved overtagelsen; passer med salgspris 86,9 mio. − ca. 37 mio. frigjort likviditet). <b>Ekstraordinær indfrielse</b> ${dn(FL.voluntary_m)} mio. = indfrielse ${dn(FL.indfrielse_m)} mio. minus den salgsrelaterede del. Fordelingen på typer er afledt: de solgte ejendommes lån henføres til F5 (pr. 31.12.25 lå F5 ${dn(DB.f5_ye_excess_m)} mio. over den tinglyste F5 på de nuværende ejendomme, og lånene blev omlagt sammen i maj/juni 2025); den ekstraordinære indfrielse til fast rente, som var uændret til 30.06.26 og faldt i 3. kvartal.</p>`+
    `<p><b>Nedbragt siden tinglysning</b> = tinglyst hovedstol minus FED's udestående pr. ${L}: pantebrevet står uændret, mens afdrag og indfrielser kun nedbringer det skyldige. Salg indgår ikke her, fordi de solgte ejendommes pantebreve er aflyst og hverken er med i det tinglyste eller det udestående.</p>`+
    `<p>Grundlaget for FED's procenter pr. 31.12.25 og 30.06.26 er den samlede portefølje inkl. aktiver bestemt for salg; pr. ${L} den nominelle gæld (${dn(DB.nominal_latest_m)} mio.).</p>`;

  // Chart: debt mix per quarter (stacked), FED's reported split
  new Chart(document.getElementById('dCh1'),{type:'bar',
    data:{labels:MX.map(m=>m.label),datasets:TYP.map((t,i)=>({label:TL[t],data:MX.map(m=>Math.round(m.amounts[t]*10)/10),
      backgroundColor:SC[t],borderColor:'#141a24',borderWidth:{top:i<2?2:0,bottom:0,left:0,right:0},borderSkipped:false,
      borderRadius:i===2?{topLeft:4,topRight:4}:0,maxBarThickness:90,pct:MX.map(m=>m.pct[t])}))},
    options:{responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true,labels:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},boxWidth:10,padding:12}},
        tooltip:{backgroundColor:'#1a2230',borderColor:'#3d4a5c',borderWidth:1,titleColor:'#f8fafc',bodyColor:'#b0bac9',
          titleFont:{family:'JetBrains Mono',size:11},bodyFont:{family:'JetBrains Mono',size:11},padding:8,cornerRadius:3,
          callbacks:{label:c=>`${c.dataset.label}: ${dn(c.parsed.y)} mio. (ca. ${c.dataset.pct[c.dataIndex]} %)`,
            footer:items=>'I alt: '+dn(MX[items[0].dataIndex].base_m)+' mio.'}}},
      scales:{x:{stacked:true,ticks:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10}},grid:{display:false}},
        y:{stacked:true,beginAtZero:true,ticks:{color:'#b0bac9',font:{family:'JetBrains Mono',size:10},callback:v=>v+' mio.'},grid:{color:'rgba(61,74,92,.35)'}}}}});
  document.getElementById('dMixN').innerHTML=
    `<p>Viser kvartaler hvor FED har oplyst fordelingen (${MX.map(m=>m.label).join(', ')}). 31.03.26 er ikke indlæst. Tal pr. type: se tabellen ovenfor.</p>`;

  // Redemption yields vs. buyback
  const bidragKnown=DB.bidrag_pct!=null;
  document.getElementById('dYld').innerHTML=
    `<thead><tr><th class="l">Anvendelse af 1 kr.</th><th title="Obligationsrente/kupon, ekskl. bidrag">Rente</th><th title="DLR's bidrag (gebyr på restgælden), estimeret">+ bidrag (est.)</th><th>I alt</th><th>Efter ${Math.round(DB.tax_rate*100)} % skat</th></tr></thead><tbody>`+
    DB.redemption.map(r=>`<tr><td class="l" title="${r.basis}">${sw(r.type)}Indfri ${r.label}</td>
      <td>${r.base_pct==null?PEND:dp(r.base_pct)}</td><td>${bidragKnown?dp(r.bidrag_pct):PEND}</td>
      <td>${r.total_pct==null?(r.base_pct==null?PEND:'—'):dp(r.total_pct)}</td>
      <td>${r.after_tax_pct==null?PEND:dp(r.after_tax_pct)+(bidragKnown?'':'*')}</td></tr>`).join('')+
    `<tr class="sep"><td class="l" title="NAV / aktiekurs − 1, jf. Tilbagekøb-fanen">Tilbagekøb: afkast på næste krone</td><td colspan="3">NAV ${dn(DB.nav,2)} / kurs ${dn(DB.kurs,2)} − 1</td>
      <td style="color:var(--g4)"><b>${dp(DB.next_krone_pct,1)}</b></td></tr></tbody>`;
  const c6=DB.cibor6||{};
  document.getElementById('dYldN').innerHTML=
    `<p>Rente + bidrag = det FED sparer pr. indfriet krone. Fast: effektiv rente ved opkøb til aktuel kurs · F5: låst til ca. april 2030 · CIBOR6: 6M CIBOR + tillæg. Bidrag er estimeret ud fra FED's gns. lånerente.</p>`+
    `<p>Afkast på næste krone er en engangsrabat til NAV, ikke en årlig rente.</p>`+
    (bidragKnown?'':`<p>* Ekskl. bidrag (afventer CIBOR6-input).</p>`);
  // Detail lives in tooltips: rows of the yield table
  const yTip={
    fixed:'Effektiv rente ved opkøb af proxy-obligationerne (DLR 4 B 2053 OA / 4 B 2053) til aktuel kurs.',
    f5:`Låst rente fra tinglysningen maj/juni 2025 (gns. ${dp(DB.redemption.find(r=>r.type==='f5').base_pct)}) til rentetilpasning ca. april 2030.`,
    cibor6:c6.fixing_pct!=null?`6M CIBOR ${dp(c6.fixing_pct,4)} pr. ${dDate(c6.as_of)} (DFBF, indtastet manuelt; gælder fra næste rentetilpasning) + tillæg ${DB.cibor6_margin_pp!=null?dn(DB.cibor6_margin_pp,2)+' pp (vægtet; tinglysningsrente minus fixing, 0,03-0,19 pp pr. lån). Tillægget er en del af kuponen, ikke DLR\'s bidrag.':'afventer.'}`:'Afventer CIBOR6-input.'};
  const bTip=bidragKnown?`Bidrag ≈ FED's gns. lånerente 1.-3. kvt. 2026 (4,06 %) minus vægtede kuponer = ${dp(DB.bidrag_pct)}${DB.bidrag_basis==='2026-fixings'?'.':'; foreløbigt — CIBOR6-kuponerne i 2026 er sat til den aktuelle fixing.'}`:'Afventer CIBOR6-input.';
  document.querySelectorAll('#dYld tbody tr').forEach((tr,i)=>{const r=DB.redemption[i];if(!r)return;
    tr.cells[0].title=yTip[r.type]||'';tr.cells[1].title=yTip[r.type]||'';tr.cells[2].title=bTip});

  // Proxy bonds for the fixed loans
  document.getElementById('dBond').innerHTML=
    `<thead><tr><th class="l">Lån</th><th class="l">Proxy-serie</th><th>Kurs</th><th>Eff. rente</th><th title="Varighed: den gennemsnitlige tid, til lånet er betalt tilbage (ca. 11 år for et 27-årigt annuitetslån). Kursen bevæger sig ca. varighed × renteændring — for en konvertibel obligation tæt på kurs 100 lidt mindre.">Kursfølsomhed</th><th title="FED's faste andel fordelt efter tinglyst hovedstol">Udestående*</th><th>Markedsværdi</th><th>Δ værdi +1 pp</th><th title="Kurs begrænset til 100 (konvertibel obligation)">Δ værdi −1 pp</th></tr></thead><tbody>`+
    F.bonds.map(b=>`<tr><td class="l">${b.property}</td><td class="l" title="${b.isin} · ${b.repayment} · udløb ${dDate(b.expiry)}">${b.bond}<br><span style="color:var(--t3)">${b.isin}${b.years_left!=null?'<br>'+dn(b.years_left,1)+' år til udløb':''}</span></td>
      <td>${b.price==null?PEND:dn(b.price,2)+'<br><span style="color:var(--t3)">'+dDate(b.price_date)+'</span>'}</td>
      <td>${b.yield_pct==null?PEND:dp(b.yield_pct)}</td>
      <td title="Varighed ca. ${b.macaulay_years==null?'—':dn(b.macaulay_years,1)} år · ${b.io_until?'antaget afdragsfri til '+dDate(b.io_until)+', derefter annuitet':'annuitet til udløb'}">${b.mod_duration==null?'—':'≈'+dn(b.mod_duration,1)+' %<br><span style="color:var(--t3)">pr. 1 pp</span>'}</td>
      <td>${dn(b.alloc_m)}</td><td>${dn(b.mv_m)}</td><td>${b.dmv_up1pp_m==null?'—':dn(b.dmv_up1pp_m)}</td>
      <td title="${b.price_down1pp_uncapped==null?'':'Uden kursloft: kurs '+dn(b.price_down1pp_uncapped,1)}">${b.dmv_down1pp_m==null?'—':'+'+dn(b.dmv_down1pp_m)}</td></tr>`).join('')+
    `<tr class="sum"><td class="l" colspan="2">I alt</td><td></td><td>${dp(F.yield_pct)}</td><td></td><td>${dn(F.outstanding_m)}</td><td>${dn(F.mv_m)}</td>
      <td>${dn(F.bonds.reduce((s,b)=>s+(b.dmv_up1pp_m||0),0))}</td><td>+${dn(F.bonds.reduce((s,b)=>s+(b.dmv_down1pp_m||0),0))}</td></tr></tbody>`;
  document.getElementById('dBondN').innerHTML=
    `<p>Proxy-obligationer: DLR 4 % 2053 (OA-serien for Baltorpvej); tingbogen angiver ikke serien, og *fordelingen af FED's faste gæld (ca. ${ML.pct.fixed} % af ${dn(DB.nominal_latest_m)} mio.) på de to lån er skønnet. `+
    `Stiger renten 1 pp, falder kursen op til ca. ${dn(Math.min(...F.bonds.map(b=>b.mod_duration||0)),0)}-${dn(Math.max(...F.bonds.map(b=>b.mod_duration||0)),0)} %, og NAV stiger op til ca. ${dn(F.nav_gain_per_share,1)} kr./aktie. `+
    `Falder renten, kan FED indfri til kurs 100, så NAV-tabet er begrænset til ca. ${dn(Math.abs(F.nav_down1pp_per_share),1)} kr./aktie.</p>`+
    `<p>FED’s egen følsomhed (ÅR 2025 note 28): +1 pp ≈ −39,7 mio., −1 pp ≈ +22,1 mio. Vi regner med fuld omprisning og loft ved kurs 100.</p>`;

  // Property table
  // One row per property × loan type (summed); the individual loans sit in collapsed detail rows.
  const pr=DB.properties,G='color:var(--t3)';
  const pdate=s=>{const[d,m,y]=s.split('.');return new Date(+y,+m-1,+d)};
  const dRange=ls=>{const ds=[...new Set(ls.map(l=>l.registered))].sort((a,b)=>pdate(a)-pdate(b));
    if(ds.length===1)return ds[0];const a=ds[0].split('.'),b=ds[ds.length-1].split('.');
    return a[2]===b[2]?`${a[0]}.${a[1]}.–${ds[ds.length-1]}`:`${ds[0]}–${ds[ds.length-1]}`};
  const extra=(bond,margin)=>(bond?`<br><span style="${G}">proxy: ${bond}</span>`:'')+
    (margin!=null?`<br><span style="${G}" title="Obligationstillæg i kuponen (tinglysningsrente minus CIBOR6-fixing). DLR's bidrag kommer oveni og står ikke i tingbogen.">kupon = CIBOR6 + ${dn(margin,2)} pp, ekskl. bidrag</span>`:'');
  const blank='<td class="l pc"></td><td class="pc"></td><td class="pc"></td><td class="pc"></td>';
  let rows='',gid=0;
  for(const p of pr){
    const head=`<td class="l"><b>${p.name}</b><br><span style="${G}">${p.by}</span></td><td class="l">${p.segment}</td><td>${fD(Math.round(p.m2))}</td><td class="l">${p.company}</td>`;
    if(p.mortgage_free){rows+=`<tr>${head}<td class="l"><span class="tag free">Gældfri</span></td><td>—</td><td>—</td><td>—</td><td class="l">—</td></tr>`;continue}
    const groups=[];
    for(const l of p.loans){let g=groups.find(x=>x.type===l.type);if(!g)groups.push(g={type:l.type,label:l.type_label,loans:[]});g.loans.push(l)}
    groups.forEach((g,gi)=>{
      const ls=g.loans,n=ls.length,sumP=ls.reduce((s,l)=>s+l.principal_m,0),
        rate=ls.reduce((s,l)=>s+l.rate_pct*l.principal_m,0)/sumP,
        spread=Math.max(...ls.map(l=>l.rate_pct))-Math.min(...ls.map(l=>l.rate_pct)),
        mg=ls.every(l=>l.margin_pp!=null)?ls.reduce((s,l)=>s+l.margin_pp*l.principal_m,0)/sumP:null,
        id='g'+(++gid),exp=n>1;
      rows+=`<tr class="grp${gi?' cont':''}${exp?' x':''}"${exp?` data-g="${id}"`:''}>${gi?blank:head}
        <td class="l">${exp?`<button class="exp" aria-expanded="false" aria-controls="${id}" title="Vis de ${n} lån">▸</button>`:'<span class="exp-sp"></span>'}${sw(g.type)}${g.label}</td>
        <td>${dn(sumP,2)}<br><span style="${G}">${n} lån</span></td>
        <td>${n>1&&spread>0.005?'gns. ':''}${dp(rate)}</td><td>${dRange(ls)}</td>
        <td class="l">${ls[0].reset}${extra(ls[0].bond,mg)}</td></tr>`;
      if(exp)ls.forEach(l=>{rows+=`<tr class="det" data-p="${id}" hidden>${blank}
        <td class="l"><span style="${G}">↳ ${l.ref}</span></td><td>${dn(l.principal_m,2)}</td><td>${dp(l.rate_pct)}</td><td>${l.registered}</td>
        <td class="l">${l.margin_pp!=null?`<span style="${G}">CIBOR6 + ${dn(l.margin_pp,2)} pp</span>`:`<span style="${G}">${l.reset}</span>`}</td></tr>`});
    });
  }
  const nFree=pr.filter(p=>p.mortgage_free).length;
  document.getElementById('dProp').innerHTML=
    `<thead><tr><th class="l">Ejendom</th><th class="l">Segment</th><th>m²</th><th class="l">Selskab</th><th class="l">Lånetype</th><th>Hovedstol, mio.</th><th>Rente v. tingl.</th><th>Tinglyst</th><th class="l">Rentetilpasning / udløb</th></tr></thead>`+
    `<tbody>${rows}<tr class="sum"><td class="l" colspan="5">I alt tinglyst · ${DB.loans_count} lån · ${nFree} gældfri ejendomme</td><td>${dn(DB.registered_total_m,1)}</td><td colspan="3" class="l">FED's nominelle gæld ${dm(DB.nominal_latest_m)} (${L})</td></tr></tbody>`;
  // Expand / collapse a property's loans of one type (row click or the ▸ button)
  document.getElementById('dProp').addEventListener('click',e=>{
    const tr=e.target.closest('tr.grp.x');if(!tr)return;
    const btn=tr.querySelector('button.exp'),open=btn.getAttribute('aria-expanded')!=='true';
    btn.setAttribute('aria-expanded',open);btn.textContent=open?'▾':'▸';
    document.querySelectorAll(`#dProp tr.det[data-p="${tr.dataset.g}"]`).forEach(r=>r.hidden=!open);
  });
  document.getElementById('dPropN').innerHTML=
    `<p>Tinglyste beløb er hovedstolen ved tinglysning og dermed en <b>øvre grænse</b>: afdrag og ekstraordinære indfrielser nedskriver ikke pantebrevet. Summen ligger ${dn(DB.registered_total_m-DB.nominal_latest_m)} mio. over FED's nominelle gæld.</p>`+
    `<p>De ca. 40 mio. ekstraordinære indfrielser i 2026 gik til de faste lån (Baltorpvej og Kærup Industrivej), men fordelingen mellem de to lån er ikke offentlig.</p>`+
    `<p>Gældfri = ingen tinglyste realkreditlån. Lånetype afledt af tinglysningsdato. Ejendomme solgt pr. 1.7.26 er ikke med.</p>`+
    `<p>Kilde: tinglysning.dk (udtræk 04.11.26, kun ejendomme ejet af FED-selskaber), FED's årsrapport 2025 og delårsrapport 1.-3. kvt. 2026, Nasdaq Copenhagen.</p>`;
}

// Tabs
let debtDone=false;
function showTab(id){
  document.querySelectorAll('.tabp').forEach(s=>s.hidden=(s.id!=='tab-'+id));
  document.querySelectorAll('.tabs button').forEach(b=>{const on=b.dataset.tab===id;b.classList.toggle('on',on);b.setAttribute('aria-selected',on)});
  if(id==='gaeld'&&!debtDone){debtDone=true;renderDebt()}
  if(location.hash!=='#'+id)history.replaceState(null,'','#'+id);
}
document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));
if(location.hash==='#gaeld')showTab('gaeld');
</script>
<script data-goatcounter="https://kajsersoze.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
