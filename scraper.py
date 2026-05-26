import requests
import re
import time
import os
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

NOTION_KEY  = os.environ["NOTION_KEY"]
DAILY_ID    = "36a6eb3913128021a75fe83e975a34eb"
DATABASE_ID = "36a6eb391312803e8429ecdd22a80bef"
MAX         = 1000

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

WEB_HEADER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TG_BLACKLIST = {"telegram","share","msg","iv","joinchat","addstickers","botfather","durov","tgstat","combot"}

# ============================================================
# UTILITAIRES
# ============================================================

def get_json(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            return r.json()
        except:
            time.sleep(2)
    return None

def get_html(url, timeout=6):
    try:
        r = requests.get(url, timeout=timeout, headers=WEB_HEADER)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

def find_telegram(text):
    if not text:
        return None
    for slug in re.findall(r'https?://(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{4,})', text):
        if slug.lower() not in TG_BLACKLIST and not slug.startswith("+"):
            return f"https://t.me/{slug}"
    return None

def age_hours(ts):
    if not ts:
        return None
    return (datetime.now(tz=timezone.utc) - datetime.fromtimestamp(ts/1000, tz=timezone.utc)).total_seconds() / 3600

def get_social(socials, kind):
    for s in (socials or []):
        u = s.get("url","")
        if kind == "telegram" and ("t.me" in u or "telegram" in u.lower()):
            slug = u.rstrip("/").split("/")[-1]
            if slug.lower() not in TG_BLACKLIST:
                return u
        if kind == "twitter" and ("twitter.com" in u or "x.com" in u):
            return u
    return None

def get_website(pair):
    sites = (pair.get("info") or {}).get("websites") or []
    return sites[0].get("url") if sites else None

# ============================================================
# NOTION
# ============================================================

def setup_databases():
    props = {
        "Nom":         {"title": {}},
        "Ticker":      {"rich_text": {}},
        "Chain":       {"select": {}},
        "Telegram":    {"url": {}},
        "Website":     {"url": {}},
        "X":           {"url": {}},
        "DexScreener": {"url": {}},
    }
    for db_id in [DAILY_ID, DATABASE_ID]:
        requests.patch(f"https://api.notion.com/v1/databases/{db_id}", headers=NOTION_HEADERS, json={"properties": props})
    print("   Colonnes OK")

def clear_daily():
    url, payload, n = f"https://api.notion.com/v1/databases/{DAILY_ID}/query", {"page_size": 100}, 0
    while True:
        data = requests.post(url, headers=NOTION_HEADERS, json=payload).json()
        for page in data.get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=NOTION_HEADERS, json={"archived": True})
            n += 1
            time.sleep(0.1)
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    print(f"   {n} entrees supprimees")

def get_contacted():
    url, contacted, payload = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", set(), {"page_size": 100}
    while True:
        data = requests.post(url, headers=NOTION_HEADERS, json=payload).json()
        for page in data.get("results", []):
            dex = (page.get("properties",{}).get("DexScreener") or {}).get("url")
            if dex:
                contacted.add(dex)
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    print(f"   {len(contacted)} deja contactes")
    return contacted

def update_telegram_in_notion(page_id, telegram_url):
    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=NOTION_HEADERS, json={
        "properties": {"Telegram": {"url": telegram_url}}
    })

def add_to_db(db_id, p):
    props = {
        "Nom":         {"title":     [{"text": {"content": p["nom"]}}]},
        "Ticker":      {"rich_text": [{"text": {"content": p["ticker"]}}]},
        "Chain":       {"select":    {"name": p["chain"]}},
        "DexScreener": {"url":       p["dexscreener"]},
    }
    if p.get("telegram"):
        props["Telegram"] = {"url": p["telegram"]}
    if p.get("website"):
        props["Website"]  = {"url": p["website"]}
    if p.get("x"):
        props["X"]        = {"url": p["x"]}
    r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json={
        "parent": {"database_id": db_id}, "properties": props
    })
    return r.status_code == 200, r.json().get("id")

# ============================================================
# DEXSCREENER
# ============================================================

def fetch_pairs():
    all_pairs = []

    # Profils + boosted
    for ep in ["https://api.dexscreener.com/token-profiles/latest/v1",
               "https://api.dexscreener.com/token-boosts/latest/v1",
               "https://api.dexscreener.com/token-boosts/top/v1"]:
        data = get_json(ep)
        if data:
            items = data if isinstance(data, list) else data.get("data", [])
            for item in items:
                addr = item.get("tokenAddress","")
                if addr:
                    r = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{addr}")
                    if r:
                        all_pairs.extend(r.get("pairs",[]))
                    time.sleep(0.15)

    # Recherche par termes
    terms = [
        "token","coin","protocol","dao","finance","swap","inu","pepe","ai","meme",
        "moon","cat","dog","doge","chad","based","gem","defi","nft","web3","pump",
        "rocket","baby","floki","shib","wojak","bonk","wif","brett","frog","apu",
        "trump","grok","turbo","ponke","pnut","goat","moodeng","vine","launch","safe",
        "elon","mega","ultra","super","hyper","alpha","sigma","network","chain","labs",
        "fund","capital","yield","stake","vault","bridge","layer","zero","fire","water",
        "sky","star","sun","dark","light","fast","rich","king","queen","god","dragon",
        "wolf","bear","bull","fish","bird","lion","tiger","fox","rabbit","snake","horse",
        "whale","shark","ape","panda","seal","gaming","play","space","future","real","gold"
    ]
    for term in terms:
        r = get_json(f"https://api.dexscreener.com/latest/dex/search?q={term}")
        if r:
            all_pairs.extend(r.get("pairs",[]))
        time.sleep(0.25)

    # Deduplication par token
    seen, unique = set(), []
    for pair in all_pairs:
        key = f"{pair.get('chainId','')}_{pair.get('baseToken',{}).get('address','')}"
        if key and key not in seen:
            seen.add(key)
            unique.append(pair)

    print(f"   {len(unique)} tokens uniques")
    return unique

# ============================================================
# FILTRES
# ============================================================

def passes(pair, contacted):
    labels = [l.lower() for l in pair.get("labels",[])]
    if "scam" in labels or "honeypot" in labels:
        return False
    h = age_hours(pair.get("pairCreatedAt"))
    if not h or h > 30*24:
        return False
    if (pair.get("marketCap") or 0) < 10_000:
        return False
    if ((pair.get("volume") or {}).get("h24") or 0) < 1_000:
        return False
    if ((pair.get("liquidity") or {}).get("usd") or 0) < 5_000:
        return False
    holders = (pair.get("info") or {}).get("holders") or 0
    if holders > 0 and holders < 50:
        return False
    if pair.get("url","") in contacted:
        return False
    socials = (pair.get("info") or {}).get("socials") or []
    tg      = get_social(socials, "telegram")
    tw      = get_social(socials, "twitter")
    ws      = get_website(pair)
    if not tg and not tw and not ws:
        return False
    return True

# ============================================================
# RECHERCHE TELEGRAM
# ============================================================

def search_telegram(website, twitter):
    # Site web
    if website:
        base = website.rstrip("/")
        for path in ["", "/community", "/about", "/social", "/links", "/contact", "/join", "/socials"]:
            html = get_html(base + path)
            tg   = find_telegram(html)
            if tg:
                return tg
            time.sleep(0.15)

    # Twitter via Nitter
    if twitter:
        handle = twitter.rstrip("/").split("/")[-1].lstrip("@")
        for base in ["https://nitter.net", "https://nitter.privacydev.net"]:
            html = get_html(f"{base}/{handle}", timeout=5)
            tg   = find_telegram(html)
            if tg:
                return tg
            time.sleep(0.2)

    return None

# ============================================================
# MAIN
# ============================================================

def main():
    print(f"\n{'='*50}")
    print(f"  CRYPTO PROSPECTOR — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    print("1. Configuration Notion...")
    setup_databases()

    print("\n2. Vidage Daily Projects...")
    clear_daily()

    print("\n3. Projets deja contactes...")
    contacted = get_contacted()

    print("\n4. Recuperation DexScreener...")
    pairs = fetch_pairs()

    # Filtrage
    print(f"\n5. Filtrage ({len(pairs)} tokens)...")
    candidates, seen_names = [], set()
    for pair in pairs:
        if not passes(pair, contacted):
            continue
        name = pair.get("baseToken",{}).get("name","Unknown")
        key  = name.lower().strip()
        if key in seen_names:
            continue
        seen_names.add(key)
        socials = (pair.get("info") or {}).get("socials") or []
        candidates.append({
            "nom":         name,
            "ticker":      "$" + pair.get("baseToken",{}).get("symbol","???"),
            "chain":       pair.get("chainId","unknown").capitalize(),
            "telegram":    get_social(socials, "telegram"),
            "website":     get_website(pair),
            "x":           get_social(socials, "twitter"),
            "dexscreener": pair.get("url",""),
        })
    print(f"   {len(candidates)} projets retenus")
    print(f"   {len([c for c in candidates if c['telegram']])} ont deja Telegram")

    # Ajout dans Database Projects
    print(f"\n6. Ajout dans Database Projects...")
    db_pages = {}
    for c in candidates:
        ok, page_id = add_to_db(DATABASE_ID, c)
        if ok and page_id:
            db_pages[c["dexscreener"]] = page_id
        time.sleep(0.3)
    print(f"   {len(db_pages)} projets ajoutes")

    # Ajout dans Daily Projects
    print(f"\n7. Ajout dans Daily Projects...")
    daily_pages = {}
    for c in candidates[:MAX]:
        ok, page_id = add_to_db(DAILY_ID, c)
        if ok and page_id:
            daily_pages[c["dexscreener"]] = {"page_id": page_id, "project": c}
        time.sleep(0.3)
    print(f"   {len(daily_pages)} projets ajoutes")

    # Recherche Telegram pour ceux qui n'en ont pas
    no_tg = [c for c in candidates[:MAX] if not c["telegram"]]
    print(f"\n8. Recherche Telegram ({len(no_tg)} projets sans Telegram)...")
    found = 0
    for c in no_tg:
        tg = search_telegram(c["website"], c["x"])
        if tg:
            c["telegram"] = tg
            found += 1
            # Met a jour dans les deux bases
            dex_url = c["dexscreener"]
            if dex_url in db_pages:
                update_telegram_in_notion(db_pages[dex_url], tg)
            if dex_url in daily_pages:
                update_telegram_in_notion(daily_pages[dex_url]["page_id"], tg)
            print(f"   Trouve : {tg}")
        time.sleep(0.2)
    print(f"   {found} Telegrams trouves")

    print(f"\n{'='*50}")
    print(f"  TERMINE")
    print(f"  {len(candidates)} projets dans Database Projects")
    print(f"  {len(daily_pages)} projets dans Daily Projects")
    print(f"  {len([c for c in candidates if c.get('telegram')])} avec Telegram")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
ENDOFFILE
