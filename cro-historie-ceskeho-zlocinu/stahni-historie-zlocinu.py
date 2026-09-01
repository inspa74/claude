#!/usr/bin/env python3
"""
Stáhne všechny díly podcastu "Historie českého zločinu" z oficiálního RSS
feedu Českého rozhlasu a pojmenuje je jednotně:

    XXXX_YYYYMMDD_Plny nazev dilu.mp3

kde:
    XXXX     = pořadové číslo (chronologicky od nejstaršího dílu = 0000)
    YYYYMMDD = datum vysílání (z <pubDate> ve feedu)
    Nazev    = plný název epizody (z <title> ve feedu, jen očištěný
               o znaky nevhodné pro souborový systém)

Použití:
    python3 stahni-historie-zlocinu.py                    # stáhne vše, co chybí
    python3 stahni-historie-zlocinu.py --dry-run           # jen vypíše seznam, nestahuje
    python3 stahni-historie-zlocinu.py --outdir /mnt/nas/podcasty
    python3 stahni-historie-zlocinu.py --sleep 2           # delší pauza mezi stahováními

Skript je idempotentní - když soubor v cílovém adresáři už existuje (a má
nenulovou velikost), přeskočí ho. Lze ho tedy klidně spouštět opakovaně
(např. přes cron), aby dotahoval nově vydané díly - feed se aktualizuje
sám, jak Český rozhlas přidává nové epizody.

POZNÁMKA: RSS feed u některých podcastů Českého rozhlasu nemusí obsahovat
úplně všechny historické díly (na webu mujRozhlas.cz může být zobrazeno
o něco víc/míň, protože web má vlastní stránkování). Skript na konci
vypíše, kolik položek ve feedu našel - to si porovnejte s počtem na webu.
Pokud by tam pár nejnovějších dílů chybělo, stačí skript spustit znovu
o něco později (feed má TTL 24 hodin).
"""

import argparse
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

FEED_URL = "https://api.mujrozhlas.cz/rss/podcast/c9395a54-f2db-3013-8d5b-94bbc38617ce.rss"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) stahni-historie-zlocinu/1.0"


def fetch_feed(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def sanitize_filename(name: str) -> str:
    """Odstraní/nahradí znaky nevhodné pro souborový systém (i kvůli
    přenositelnosti na Windows/exFAT - kdyby se archiv kopíroval i tam)."""
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)   # znaky zakázané na Windows
    name = re.sub(r"\s+", " ", name)           # sjednocení bílých znaků
    return name[:180]                          # rozumný limit délky názvu


def parse_items(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item"):
        title_el = item.find("title")
        pubdate_el = item.find("pubDate")
        enclosure_el = item.find("enclosure")

        if enclosure_el is None or title_el is None or pubdate_el is None:
            print("  přeskakuji položku bez title/pubDate/enclosure", file=sys.stderr)
            continue

        title = title_el.text or "bez_nazvu"
        url = enclosure_el.get("url")

        try:
            dt = parsedate_to_datetime(pubdate_el.text)
        except Exception:
            print(f"  nelze naparsovat datum '{pubdate_el.text}' u '{title}', přeskakuji", file=sys.stderr)
            continue

        items.append((dt, title, url))

    # seřadit od nejstaršího - podle toho se přiděluje pořadové číslo 0000, 0001, ...
    items.sort(key=lambda x: x[0])
    return items


def build_filename(index: int, dt, title: str) -> str:
    return f"{index:04d}_{dt.strftime('%Y%m%d')}_{sanitize_filename(title)}.mp3"


def download(url: str, dest_path: str) -> bool:
    """Stáhne soubor přes curl (podporuje dokončení přerušeného stahování
    díky -C -), vrátí True při úspěchu."""
    tmp_path = dest_path + ".part"
    cmd = [
        "curl", "-L", "--fail", "--retry", "3", "--retry-delay", "5",
        "-A", USER_AGENT,
        "-C", "-",
        "-o", tmp_path,
        url,
    ]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        os.replace(tmp_path, dest_path)
        return True
    return False


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--outdir", default="./historie-ceskeho-zlocinu", help="cílový adresář (výchozí: ./historie-ceskeho-zlocinu)")
    ap.add_argument("--dry-run", action="store_true", help="jen vypsat seznam a názvy souborů, nic nestahovat")
    ap.add_argument("--sleep", type=float, default=1.0, help="pauza mezi jednotlivými stahováními v sekundách (výchozí 1.0)")
    ap.add_argument("--start-index", type=int, default=0, help="číslo, kterým se očísluje nejstarší díl ve feedu (výchozí 0). Feed 'Historie českého zločinu' aktuálně začíná dílem, který má na neoficiálním seznamu číslo 85 - pro zarovnání číslování s tímto seznamem použijte --start-index 85")
    args = ap.parse_args()

    print(f"Stahuji RSS feed: {FEED_URL}")
    xml_bytes = fetch_feed(FEED_URL)
    items = parse_items(xml_bytes)
    print(f"Nalezeno {len(items)} položek ve feedu.\n")

    os.makedirs(args.outdir, exist_ok=True)

    stazeno, preskoceno, chyby = 0, 0, 0

    for offset, (dt, title, url) in enumerate(items):
        idx = args.start_index + offset
        filename = build_filename(idx, dt, title)
        dest = os.path.join(args.outdir, filename)

        if args.dry_run:
            print(f"{filename}\n    <- {url}")
            continue

        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[{idx:04d}] přeskakuji (už existuje): {filename}")
            preskoceno += 1
            continue

        print(f"[{idx:04d}] stahuji: {filename}")
        if download(url, dest):
            stazeno += 1
        else:
            print(f"  !! stažení selhalo: {url}", file=sys.stderr)
            chyby += 1

        time.sleep(args.sleep)

    if not args.dry_run:
        print(f"\nHotovo. Staženo: {stazeno}, přeskočeno (už existovalo): {preskoceno}, chyby: {chyby}")


if __name__ == "__main__":
    main()
