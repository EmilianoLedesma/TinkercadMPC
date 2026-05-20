"""
LED Blink circuit — headless Playwright.
Topology: Arduino D13 -> Resistor -> LED anode, LED cathode -> GND rail,
          Arduino GND -> GND rail.
Fix: reload editor after placement so Tinkercad fits all into view (no negative coords).
"""
import asyncio, json, math, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["TINKERCAD_HEADLESS"] = "true"
os.environ["PYTHONIOENCODING"] = "utf-8"

import tinkercad_mcp.api as api
from tinkercad_mcp.browser import BrowserManager

SEP = "-" * 60

# ── JS: scan all interactive pins (screen coords) ──────────────────────────
SCAN_ALL_JS = """
() => {
    const all = Array.from(document.querySelectorAll('svg rect,svg circle'))
        .filter(el => {
            try{return Object.keys(jQuery._data(el,'events')||{}).includes('mousedown');}
            catch(e){return false;}
        })
        .map(el => {
            const r = el.getBoundingClientRect();
            if(!r.width) return null;
            return { sx: r.x+r.width/2, sy: r.y+r.height/2, w: Math.round(r.width) };
        }).filter(Boolean);
    return all;
}
"""

# ── JS: scan breadboard holes (screen coords) ──────────────────────────────
SCAN_BB_JS = """
() => {
    const circles = Array.from(document.querySelectorAll('[class*="breadboard-round"] circle'));
    if(!circles.length) return null;
    const pts=[], seen=new Set();
    for(const c of circles){
        const r=c.getBoundingClientRect();
        if(!r.width)continue;
        const sx=Math.round(r.x+r.width/2), sy=Math.round(r.y+r.height/2);
        const k=`${sx},${sy}`;
        if(!seen.has(k)){seen.add(k);pts.push({sx,sy});}
    }
    const sxs=[...new Set(pts.map(p=>p.sx))].sort((a,b)=>a-b);
    const sys_=[...new Set(pts.map(p=>p.sy))].sort((a,b)=>a-b);

    // Group rows by gap > 8px
    const rowGroups=[];let grp=[sys_[0]];
    for(let i=1;i<sys_.length;i++){
        if(sys_[i]-sys_[i-1]>8){rowGroups.push(grp);grp=[];}
        grp.push(sys_[i]);
    }
    rowGroups.push(grp);

    // Name rows: groups of 2 = power rails, groups of 5 = main rows a-e / f-j
    const ROW='abcdefghij'.split('');
    const namedRows={};
    let rowIdx=0;
    for(const g of rowGroups){
        if(g.length===2){
            const midY=sys_[Math.floor(sys_.length/2)];
            const label=g[0]<midY?'pwr_top':'pwr_bot';
            namedRows[label+'_pos']=g[0];
            namedRows[label+'_neg']=g[1];
        } else {
            for(let i=0;i<g.length;i++){
                if(rowIdx<ROW.length) namedRows[ROW[rowIdx++]]=g[i];
            }
        }
    }

    const grid={};
    for(const [rn,ry] of Object.entries(namedRows)){
        sxs.forEach((x,i)=>{
            if(pts.some(p=>p.sx===x&&p.sy===ry)) grid[`${rn}${i+1}`]={sx:x,sy:ry};
        });
    }
    return {grid, cols:sxs.length, rowKeys:Object.keys(namedRows)};
}
"""

# ── JS: draw wire via jQuery two-click (screen coords) ────────────────────
WIRE_JS = """
async ([ssx, ssy, dsx, dsy]) => {
    const fire=(el,t,x,y)=>{
        if(!el)return;
        jQuery(el).trigger(jQuery.Event(t,{clientX:x,clientY:y,pageX:x,pageY:y,which:1,button:0}));
    };
    const nearest=(tx,ty,r=16)=>{
        const els=Array.from(document.querySelectorAll('svg rect,svg circle'))
            .filter(e=>{try{return Object.keys(jQuery._data(e,'events')||{}).includes('mousedown');}catch{return false;}});
        let best=null,bd=Infinity;
        for(const e of els){
            const br=e.getBoundingClientRect();if(!br.width)continue;
            const cx=br.x+br.width/2,cy=br.y+br.height/2;
            const d=Math.hypot(cx-tx,cy-ty);
            if(d<bd&&d<=r){best=e;bd=d;}
        }
        return best;
    };
    document.dispatchEvent(new KeyboardEvent('keydown',{keyCode:27,bubbles:true}));
    await new Promise(r=>setTimeout(r,150));
    const src=nearest(ssx,ssy)||document.elementFromPoint(ssx,ssy);
    const sr=src?.getBoundingClientRect();
    const ax=sr?sr.x+sr.width/2:ssx, ay=sr?sr.y+sr.height/2:ssy;
    fire(src,'mousedown',ax,ay);await new Promise(r=>setTimeout(r,80));
    fire(src,'mouseup',ax,ay);fire(src,'click',ax,ay);
    await new Promise(r=>setTimeout(r,400));
    fire(document,'mousemove',dsx,dsy);await new Promise(r=>setTimeout(r,200));
    const dst=nearest(dsx,dsy)||document.elementFromPoint(dsx,dsy);
    const dr=dst?.getBoundingClientRect();
    const bx=dr?dr.x+dr.width/2:dsx, by=dr?dr.y+dr.height/2:dsy;
    fire(dst,'mousedown',bx,by);await new Promise(r=>setTimeout(r,80));
    fire(dst,'mouseup',bx,by);fire(dst,'click',bx,by);
    return {srcEl:src?.tagName, dstEl:dst?.tagName};
}
"""


async def wire(page, sx, sy, dx, dy, label=""):
    r = await page.evaluate(WIRE_JS, [sx, sy, dx, dy])
    ok = isinstance(r, dict) and r.get("dstEl") == "rect"
    print(f"  [{'OK  ' if ok else 'WARN'}] {label:40s}  dst={r.get('dstEl','?') if isinstance(r,dict) else r}")
    await asyncio.sleep(0.6)
    return ok


def cluster(pins, radius=60):
    used, groups = set(), []
    for i, p in enumerate(pins):
        if i in used: continue
        g = [p]; used.add(i)
        for j, q in enumerate(pins):
            if j in used: continue
            if math.hypot(p["sx"]-q["sx"], p["sy"]-q["sy"]) <= radius:
                g.append(q); used.add(j)
        groups.append(g)
    return sorted(groups, key=lambda g: sum(p["sx"] for p in g)/len(g))


async def main():
    print(SEP)
    print("  LED Blink — headless")
    print(SEP)

    # Session
    status = await api.get_session_status()
    print(f"\n[1] {status[:80]}")
    if "invalid" in status.lower():
        print(await api.login())

    # Create circuit
    print("\n[2] Creating circuit...")
    r = await api.create_circuit("LED Blink Auto")
    print(f"     {r[:120]}")
    if "error" in r.lower(): return
    await asyncio.sleep(4)

    mgr = await BrowserManager.get_instance()
    page = await mgr.get_page()
    editor_url = page.url
    print(f"     Editor URL: {editor_url}")

    # Place components
    print("\n[3] Placing components...")
    for comp, x, y in [
        ("breadboard",  360, 160),
        ("arduino_uno",  70, 230),
        ("led",         290,  55),
        ("resistor",    195,  55),
    ]:
        r = await api.add_component(comp, x=x, y=y)
        ok = "error" not in r.lower()
        print(f"     [{'OK' if ok else 'FAIL'}] {comp}")
        await asyncio.sleep(2.5)

    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)

    # ── KEY FIX: reload editor → Tinkercad auto-fits all components ──────
    print("\n[4] Reloading editor for stable view...")
    await page.goto(editor_url, wait_until="load", timeout=60_000)
    await asyncio.sleep(4)  # wait for Angular + circuit to render

    # Scan breadboard
    print("\n[5] Scanning breadboard grid...")
    bb = await page.evaluate(SCAN_BB_JS)
    if not bb:
        print("  [FAIL] No breadboard found"); return
    grid = bb["grid"]
    print(f"     {bb['cols']} cols, {len(grid)} holes, rows: {bb['rowKeys']}")

    # Scan all pins
    print("\n[6] Scanning component pins...")
    all_pins = await page.evaluate(SCAN_ALL_JS)

    # Separate breadboard pins from component pins
    # Breadboard holes are a dense regular grid; component pins are isolated
    bb_screen_xs = sorted(set(h["sx"] for h in grid.values()))
    bb_min_sx = min(bb_screen_xs) - 20 if bb_screen_xs else 9999
    bb_max_sx = max(bb_screen_xs) + 20 if bb_screen_xs else 9999
    bb_screen_ys = sorted(set(h["sy"] for h in grid.values()))
    bb_min_sy = min(bb_screen_ys) - 20 if bb_screen_ys else 9999
    bb_max_sy = max(bb_screen_ys) + 20 if bb_screen_ys else 9999

    def is_breadboard_pin(p):
        return (bb_min_sx <= p["sx"] <= bb_max_sx and
                bb_min_sy <= p["sy"] <= bb_max_sy)

    comp_pins = [p for p in all_pins if not is_breadboard_pin(p)]
    print(f"     Total: {len(all_pins)}, comp-side: {len(comp_pins)}")

    # Cluster component pins
    groups = cluster(comp_pins)
    # Drop clusters with >8 pins at same y = Arduino pin headers
    y_rows = {}
    for p in comp_pins:
        b = round(p["sy"] / 10) * 10
        y_rows.setdefault(b, []).append(p)
    ard_row_ys = {y: ps for y, ps in y_rows.items() if len(ps) >= 8}

    small = [g for g in groups if 1 <= len(g) <= 4 and
             not any(round(p["sy"]/10)*10 in ard_row_ys for p in g)]

    print(f"     Small clusters (LED/Resistor): {len(small)}")
    for i, g in enumerate(small):
        cx = round(sum(p["sx"] for p in g)/len(g))
        cy = round(sum(p["sy"] for p in g)/len(g))
        print(f"       grp{i}: {len(g)} pins @ center=({cx},{cy})")
    print(f"     Arduino header rows y~: {sorted(ard_row_ys.keys())}")

    if len(small) < 2:
        print("  [FAIL] Need at least 2 small clusters (LED+Resistor)")
        await _show(page, mgr, editor_url); return

    # Leftmost cluster = Resistor (placed at x=195), rightmost = LED (x=290)
    resistor_g = min(small, key=lambda g: sum(p["sx"] for p in g)/len(g))
    led_g      = max(small, key=lambda g: sum(p["sx"] for p in g)/len(g))
    res_pins = sorted(resistor_g, key=lambda p: p["sx"])
    led_pins = sorted(led_g,      key=lambda p: p["sx"])
    print(f"\n     Resistor: {[(p['sx'],p['sy']) for p in res_pins]}")
    print(f"     LED:      {[(p['sx'],p['sy']) for p in led_pins]}")

    # Arduino pins
    if not ard_row_ys:
        print("  [FAIL] Arduino headers not found")
        await _show(page, mgr, editor_url); return

    top_y  = min(ard_row_ys.keys())
    bot_y  = max(ard_row_ys.keys())
    top_row = sorted(ard_row_ys[top_y], key=lambda p: p["sx"])
    bot_row = sorted(ard_row_ys.get(bot_y, []), key=lambda p: p["sx"])

    # Arduino Uno top header (right→left): D13, D12 ... GND, AREF
    d13_pin = top_row[-1]   # rightmost = D13
    # Bottom header left→right: IOREF, RESET, 3.3V, 5V, GND, GND, VIN, A0-A5
    gnd_pin = bot_row[4] if len(bot_row) > 4 else bot_row[0]
    v5_pin  = bot_row[3] if len(bot_row) > 3 else None
    print(f"     D13: ({d13_pin['sx']:.0f},{d13_pin['sy']:.0f})")
    print(f"     GND: ({gnd_pin['sx']:.0f},{gnd_pin['sy']:.0f})")

    # Breadboard hole helpers
    def H(key):
        h = grid.get(key)
        if not h: print(f"     WARNING: '{key}' missing from grid")
        return h

    # Circuit topology (all in row-a/e of breadboard, same col = same strip):
    #   D13 → bb e5          (top half, col 5)
    #   Res[0] → bb a5       (same strip as e5 → connected to D13)
    #   Res[1] → bb a8
    #   LED anode → bb b8    (same strip as a8 → in series after Resistor)
    #   LED cathode → bb a11
    #   bb a11 → GND rail    (connect cathode strip to negative rail)
    #   Arduino GND → GND rail col1
    #   Arduino 5V  → PWR rail col1

    h_d13  = H("e5")
    h_r0   = H("a5")
    h_r1   = H("a8")
    h_la   = H("b8")
    h_lc   = H("a11")
    h_lc2  = H("a11")   # same, for bridge to rail
    h_gnd  = H("pwr_top_neg1")
    h_pwr  = H("pwr_top_pos1")

    # If no power rail, fall back to any row-pwr_bot
    if not h_gnd: h_gnd = H("pwr_bot_neg1")
    if not h_pwr: h_pwr = H("pwr_bot_pos1")

    missing = [n for n,h in [("e5",h_d13),("a5",h_r0),("a8",h_r1),
                               ("b8",h_la),("a11",h_lc)] if not h]
    if missing:
        print(f"  [FAIL] Missing holes: {missing}")
        await _show(page, mgr, editor_url); return

    # ── Wiring ────────────────────────────────────────────────────────────
    print("\n[7] Wiring circuit...")

    await wire(page, d13_pin["sx"], d13_pin["sy"],
               h_d13["sx"], h_d13["sy"],   "Arduino D13 → bb e5")

    await wire(page, res_pins[0]["sx"], res_pins[0]["sy"],
               h_r0["sx"], h_r0["sy"],     "Resistor[0] → bb a5")

    await wire(page, res_pins[-1]["sx"], res_pins[-1]["sy"],
               h_r1["sx"], h_r1["sy"],     "Resistor[1] → bb a8")

    await wire(page, led_pins[0]["sx"], led_pins[0]["sy"],
               h_la["sx"], h_la["sy"],     "LED anode   → bb b8")

    await wire(page, led_pins[-1]["sx"], led_pins[-1]["sy"],
               h_lc["sx"], h_lc["sy"],     "LED cathode → bb a11")

    # Bridge a11 to GND rail (if rail exists)
    if h_gnd:
        await wire(page, h_lc["sx"], h_lc["sy"],
                   h_gnd["sx"], h_gnd["sy"],   "bb a11     → GND rail")
        await wire(page, gnd_pin["sx"], gnd_pin["sy"],
                   h_gnd["sx"], h_gnd["sy"],   "Arduino GND→ GND rail")
    else:
        # No rail: wire LED cathode directly to GND pin (via another bb hole)
        h_direct = H("f11")
        if h_direct:
            await wire(page, h_lc["sx"], h_lc["sy"],
                       h_direct["sx"], h_direct["sy"], "a11 → f11 (bridge gap)")
            await wire(page, gnd_pin["sx"], gnd_pin["sy"],
                       h_direct["sx"], h_direct["sy"], "Arduino GND → f11")

    if v5_pin and h_pwr:
        await wire(page, v5_pin["sx"], v5_pin["sy"],
                   h_pwr["sx"], h_pwr["sy"],   "Arduino 5V  → PWR rail")

    # Screenshot
    print("\n[8] Screenshot...")
    ss = os.path.join(os.path.dirname(__file__), "circuit_result.png")
    await page.screenshot(path=ss)
    print(f"     {ss}")

    await _show(page, mgr, editor_url)


async def _show(page, mgr, url):
    print(f"\n{SEP}\n  Done — opening headed window\n{SEP}")
    os.environ["TINKERCAD_HEADLESS"] = "false"
    await mgr.close()
    await asyncio.sleep(1)
    mgr2 = await BrowserManager.get_instance()
    p2 = await mgr2.get_page(headless=False)
    await p2.goto(url, wait_until="load", timeout=60_000)
    print("  Browser open. Ctrl+C to exit.")
    try:
        await asyncio.sleep(9999)
    except KeyboardInterrupt:
        pass
    await mgr2.close()


if __name__ == "__main__":
    asyncio.run(main())
