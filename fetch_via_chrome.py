"""
Fetch MaxPreps game page using the system Chrome browser's remote debugging port.

Chrome must be started with --remote-debugging-port=9222, OR we can use
subprocess to launch it. This script uses the chrome remote debugger to
navigate to the page (which goes through Chrome's VPN extension) and extract
the RSC payload.

Alternative: just saves the page HTML by opening Chrome and fetching the 
already-open tab's source.

Usage: python fetch_via_chrome.py
"""
import json
import sys
import time
import subprocess
import urllib.request
import urllib.error

GAME_URL = (
    "https://www.maxpreps.com/tx/basketball/game/"
    "allen-vs-dallas-jesuit/11-14-2025/"
    "?c=5dfde36d-7b8e-485d-9473-f57c74d44cc6&tab=Stats"
)

DEVTOOLS_PORT = 9222


def get_open_tabs():
    """Get list of open tabs from Chrome DevTools."""
    try:
        with urllib.request.urlopen(f"http://localhost:{DEVTOOLS_PORT}/json", timeout=3) as r:
            return json.loads(r.read())
    except Exception as e:
        return None


def check_devtools():
    tabs = get_open_tabs()
    if tabs is None:
        print(f"Chrome DevTools not available on port {DEVTOOLS_PORT}")
        print("Chrome needs to be started with --remote-debugging-port=9222")
        print("Or the script below will launch Chrome with that flag.")
        return False
    print(f"Chrome DevTools found! {len(tabs)} tabs open:")
    for t in tabs[:5]:
        print(f"  [{t.get('id', '?')}] {t.get('title', '?')[:60]} — {t.get('url', '')[:80]}")
    return True


def launch_chrome_with_debug():
    """Launch Chrome with remote debugging enabled."""
    import os
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    chrome_exe = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_exe = p
            break
    
    if not chrome_exe:
        print("Chrome not found at standard paths. Please start Chrome manually with:")
        print('  chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\ChromeDebug')
        return False
    
    print(f"Launching Chrome with remote debugging: {chrome_exe}")
    import tempfile
    debug_dir = tempfile.mkdtemp(prefix="chrome_debug_")
    subprocess.Popen([
        chrome_exe,
        f"--remote-debugging-port={DEVTOOLS_PORT}",
        f"--user-data-dir={debug_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        GAME_URL
    ])
    print("Waiting 5s for Chrome to start...")
    time.sleep(5)
    return True


def fetch_rsc_via_devtools(tab_id):
    """Use Chrome DevTools protocol to get page HTML."""
    import socket
    import struct
    import hashlib
    import base64
    import threading
    
    ws_url = f"ws://localhost:{DEVTOOLS_PORT}/devtools/page/{tab_id}"
    print(f"\nConnecting to DevTools WebSocket: {ws_url}")
    
    # Use websocket-client if available, else urllib
    try:
        import websocket
        
        result_html = [None]
        done = threading.Event()
        
        def on_message(ws, msg):
            data = json.loads(msg)
            if data.get("id") == 1:
                result_html[0] = data.get("result", {}).get("outerHTML", "")
                done.set()
        
        def on_open(ws):
            # Get document HTML
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True
            }}))
        
        ws_conn = websocket.WebSocketApp(ws_url, on_message=on_message, on_open=on_open)
        t = threading.Thread(target=ws_conn.run_forever)
        t.daemon = True
        t.start()
        done.wait(timeout=15)
        ws_conn.close()
        return result_html[0]
    except ImportError:
        print("websocket-client not installed. Trying alternative...")
        return None


def try_cdp_navigate_and_get(url):
    """Navigate to URL via CDP and get the RSC-payload."""
    tabs = get_open_tabs()
    if not tabs:
        return None
    
    # Find a suitable tab or use the first page tab
    page_tabs = [t for t in tabs if t.get("type") == "page"]
    if not page_tabs:
        print("No page tabs found")
        return None
    
    tab = page_tabs[0]
    tab_id = tab["id"]
    print(f"\nUsing tab: {tab.get('title', '?')[:50]} | {tab.get('url', '')[:70]}")
    
    html = fetch_rsc_via_devtools(tab_id)
    return html


def analyze_rsc(html):
    """Analyze the RSC payload from HTML."""
    import re
    
    _RSC_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
    
    chunks = []
    for m in _RSC_PUSH_RE.finditer(html):
        try:
            chunks.append(json.loads(m.group(1)))
        except Exception:
            pass
    
    payload = "".join(chunks)
    print(f"\nRSC payload size: {len(payload):,} chars")
    
    if not payload:
        print("!! NO RSC payload found")
        # Check for __NEXT_DATA__
        nd_m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if nd_m:
            print("Found __NEXT_DATA__")
        return
    
    # Save full payload
    with open("rsc_payload_vpn.txt", "w", encoding="utf-8") as f:
        f.write(payload)
    print("Saved full RSC payload to: rsc_payload_vpn.txt")
    
    # Analyze structure
    patterns = {
        '"subgroups":':   payload.find('"subgroups":'),
        '"Shooting"':     payload.find('"Shooting"'),
        '"Totals"':       payload.find('"Totals"'),
        '"rows":':        payload.find('"rows":'),
        '"columns":':     payload.find('"columns":'),
        '"stats":':       payload.find('"stats":'),
        '"header":':      payload.find('"header":'),
        '"value":':       payload.find('"value":'),
        '"href":':        payload.find('"href":'),
        'athletes/':      payload.find('athletes/'),
        '"caption":':     payload.find('"caption":'),
    }
    
    print("\nKey patterns found at positions:")
    for k, v in patterns.items():
        print(f"  {k:20s} at {v}")
    
    # Show the first occurrence of "subgroups" with context
    sg_idx = payload.find('"subgroups":')
    if sg_idx >= 0:
        print(f"\n=== Snippet around 'subgroups' (500 chars) ===")
        print(payload[max(0, sg_idx-100):sg_idx+500])
    
    # Show shooting snippet
    sh_idx = payload.find('"Shooting"')
    if sh_idx >= 0:
        print(f"\n=== Snippet around 'Shooting' (600 chars) ===")
        print(payload[sh_idx:sh_idx+600])
    
    # Show athletes href snippet
    ath_idx = payload.find('athletes/')
    if ath_idx >= 0:
        print(f"\n=== Snippet around 'athletes/' (200 chars) ===")
        print(payload[max(0,ath_idx-50):ath_idx+200])
    
    # Try the current parser
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    from scrape_box_scores import _parse_rsc_stats
    result = _parse_rsc_stats(soup)
    print(f"\n_parse_rsc_stats() returned {len(result)} school keys: {list(result.keys())}")


if __name__ == "__main__":
    print("="*60)
    print("MaxPreps RSC Payload Inspector (via Chrome DevTools)")
    print("="*60)
    
    # Check if Chrome DevTools is already running
    if check_devtools():
        html = try_cdp_navigate_and_get(GAME_URL)
        if html:
            with open("page_via_chrome.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\nFull HTML saved to: page_via_chrome.html ({len(html):,} chars)")
            analyze_rsc(html)
        else:
            print("\nCould not get HTML from Chrome DevTools")
            print("Try installing: pip install websocket-client")
    else:
        print("\nChrome DevTools not running.")
        print("Please close Chrome and reopen it using this command:")
        print()
        print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^')
        print(f'  --remote-debugging-port={DEVTOOLS_PORT} ^')
        print(f'  "{GAME_URL}"')
        print()
        print("OR: try launching Chrome automatically...")
        if launch_chrome_with_debug():
            time.sleep(3)
            if check_devtools():
                html = try_cdp_navigate_and_get(GAME_URL)
                if html:
                    analyze_rsc(html)
