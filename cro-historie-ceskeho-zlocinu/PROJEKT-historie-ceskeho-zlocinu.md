# Archivace podcastu "Historie českého zločinu" – shrnutí pro pokračování

Cíl: soukromý archiv všech dílů rozhlasového pořadu **Historie českého zločinu**
(Český rozhlas Dvojka), stahovaných výhradně z oficiálních zdrojů ČRo, jednotně
pojmenovaných a s ochranou proti duplicitám (reprízám). V budoucnu běh na
serveru přes cron, s automatickým dohledáváním nových dílů.

---

## 1. Ověřená fakta o zdrojích

### 1.1 Oficiální RSS feed (hlavní zdroj)

```
https://api.mujrozhlas.cz/rss/podcast/c9395a54-f2db-3013-8d5b-94bbc38617ce.rss
```

- Standardní podcast RSS 2.0, `<channel><item>` se standardními poli:
  `<title>`, `<pubDate>` (RFC 822, např. `Sun, 30 Aug 2026 18:05:00 +0200`),
  `<enclosure url="..." type="audio/mpeg" length="...">` (přímý mp3 odkaz,
  přes `dts.podtrac.com/redirect.mp3/...` - je třeba `curl -L`),
  `<guid isPermaLink="false">ČÍSLO</guid>`.
- `<ttl>1440</ttl>` = feed se cache/aktualizuje po 24 hodinách.
- **K 1. 9. 2026 obsahuje 65 položek**, nejstarší je "Rána v Jundrově..."
  (vysíláno 20. 3. 2021), nejnovější "Kasař, který si změnil tvář..."
  (30. 8. 2026). Feed evidentně **nezačíná od 1. dílu pořadu** - viz 1.3.
- U dílů, které jsou aktuálně v RSS, `<guid>` číselně odpovídá ID v URL na
  `dvojka.rozhlas.cz` (ověřeno: "Kapsářská brigáda" má guid `6942466` a URL
  `.../kapsarska-brigada-...-6942466`).

### 1.2 Web dvojka.rozhlas.cz (starší archiv, potenciální zdroj pro díly mimo RSS)

- `https://dvojka.rozhlas.cz/historie-ceskeho-zlocinu-6945272` - přehled
  pořadu s klasickým Drupal stránkováním `?page=0` až `?page=20` (21 stran,
  ověřeno funkční, robots.txt to nezakazuje).
- Každá stránka výpisu obsahuje název dílu, datum a odkaz na detail
  (`https://dvojka.rozhlas.cz/{slug}-{ID}`).
- **Problém:** na stránce jednotlivého dílu je přehrávač řešený přes
  JavaScript ("Spustit audio" je jen `#repeat` odkaz) - v syrovém HTML
  není přímá mp3 URL. Tu je nutné dohledat jinak, např.:
  - přes DevTools Network v prohlídeči při přehrání (**zatím neudělané -
    je potřeba jako první krok pro díly 1-84**),
  - případně přes interní API mujRozhlas s cestou `/rapi/view/episode/{uuid}`
    (viděno jako `<link>` v RSS položkách, ale **odpověď/formát nebyl
    ověřen** - nešlo mi to sondovat).
- `/ajax/*` cesty na `mujrozhlas.cz` jsou v robots.txt zakázané (ověřeno,
  fetch selhal s ROBOTS_DISALLOWED).

### 1.3 Neoficiální seznam dílů (alfabetaguma.cz)

```
https://alfabetaguma.cz/historie-ceskeho-zlocinu-neoficialni-seznam-dilu-poradu/
```

- Fanouškovský seznam všech dílů pořadu s pořadovými čísly od 1. dílu.
- **Robots.txt tuto stránku pro automatický fetch zakazuje** - nešlo mi ji
  stáhnout a naparsovat.
- Uživatel ověřil: "Rána v Jundrově" (nejstarší díl v RSS feedu) má na
  tomto seznamu **číslo 85**. Z toho plyne, že díly **1-84 předcházejí
  zavedení podcastového RSS feedu** a v něm nejsou a nebudou.
- Pro dohledání celého seznamu (názvy/čísla/data pro díly 1-84) bude
  nejspíš nutné, aby uživatel obsah stránky poskytl ručně (uložit
  jako HTML/text a nahrát, nebo zkopírovat), protože automatický fetch je
  blokovaný.

---

## 2. Aktuální stav skriptu

Soubor: **`stahni-historie-zlocinu.py`** (přiložen samostatně, funkční,
otestováno uživatelem - `--dry-run` proti reálnému feedu vypsal všech 65
položek se správnými názvy a URL).

### Co dělá

1. Stáhne a naparsuje RSS feed (`xml.etree.ElementTree`, jen stdlib).
2. Seřadí položky chronologicky od nejstarší.
3. Pojmenuje `XXXX_YYYYMMDD_Plny nazev dilu.mp3` (číslo dle pořadí,
   volitelně posunuté o `--start-index`).
4. Stáhne přes `curl -L -C -` (resume, retry), idempotentně - existující
   soubory přeskočí.

### Rozhraní (CLI)

| Parametr | Výchozí | Význam |
|---|---|---|
| `--outdir` | `./historie-ceskeho-zlocinu` | cílový adresář pro mp3 |
| `--dry-run` | vypnuto | jen vypíše seznam, nestahuje |
| `--sleep` | `1.0` | pauza mezi stahováními (s) |
| `--start-index` | `0` | číslo nejstaršího dílu ve feedu; pro zarovnání s neoficiálním seznamem použít `85` |

### Známé limity (k řešení - viz sekce 3)

- `--outdir` má relativní výchozí hodnotu - pro cron je potřeba absolutní.
- Žádný perzistentní "manifest" mezi běhy - o tom, co už bylo stažené, ví
  jen podle existence souboru na disku (podle názvu). Repríza téhož dílu
  s jiným `<guid>`/datem by se stáhla znovu pod jiným názvem.
- Negeneruje se žádný textový přehled/seznam dílů.
- Neřeší díly mimo RSS feed (1-84).

### Plný zdrojový kód (aktuální verze)

```python
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
```

---

## 3. Požadavky na rozšíření (zadání pro Claude Code)

### 3.1 Textový přehled dílů (manifest)

- Skript má vedle stahování udržovat čitelný textový (nebo CSV/TSV -
  ať se to snáz parsuje i čte) soubor se seznamem všech známých dílů:
  pořadové číslo, datum vysílání, název, název souboru, zdrojová URL,
  případně datum stažení.
- Tento soubor by měl fungovat i jako **perzistentní "databáze" mezi
  jednotlivými spuštěními** (viz 3.3) - ne se jen přepisovat od nuly
  podle aktuálního obsahu RSS feedu, protože feed sám o sobě neobsahuje
  historii (staré díly z něj po čase mohou zase vypadnout - to není
  ověřeno, ale je to riziko, se kterým je třeba počítat).

### 3.2 Detekce repríz / duplicit

- Rozhlas dané díly občas reprízuje - ve feedu se pak může objevit
  stejný obsah s novým `<guid>`, novým datem a jinou enclosure URL.
- Nechceme stahovat znovu pod novým číslem/datem - je třeba porovnávat
  podle **normalizovaného názvu** (ořezané mezery, sjednocená velikost
  písmen, případně odstranění diakritiky pro jistotu) proti manifestu
  z 3.1, a pokud název už v archivu je, díl přeskočit (zalogovat jako
  "repríza, přeskočeno", zachovat původní datum prvního vysílání v
  manifestu).

### 3.3 Inkrementální běh / příprava na cron

- Při každém spuštění: načíst RSS, porovnat s manifestem (podle
  normalizovaného názvu, viz 3.2, ne podle indexu - ten se řídí
  pořadím ve feedu a `--start-index`, ne stabilním klíčem), stáhnout
  jen nové položky, doplnit je do manifestu.
- Mělo by být bezpečné spouštět opakovaně bez zásahu (žádné interaktivní
  potvrzování), s rozumným logováním (do stdout/stderr, ať to jde
  zachytit v cron logu).

### 3.4 Cílový adresář pro mp3

- Nastavit rozumnou **výchozí absolutní cestu** (ne relativní `./...`,
  to je pro cron nespolehlivé) a zachovat možnost přepsat přes `--outdir`.
  Konkrétní výchozí cestu nechávám na domluvě při implementaci (např.
  `~/Podcasty/Historie_ceskeho_zlocinu` nebo dle zvyklostí na cílovém
  serveru).

### 3.5 (Samostatný úkol) Dohledání dílů 1-84

- Viz sekce 1.2 a 1.3 - je potřeba:
  1. Zjistit skutečnou URL, ze které si JS přehrávač na `dvojka.rozhlas.cz`
     bere audio (přes DevTools Network v prohlížeči u jednoho starého dílu).
  2. Získat obsah neoficiálního seznamu z alfabetaguma.cz (automatický
     fetch je zablokovaný robots.txt - buď ruční export stránky, nebo
     ověřit, jestli jde stáhnout jinak v souladu s robots.txt).
  3. Napsat scraper pro `dvojka.rozhlas.cz` stránkování (21 stran),
     spárovat s (2) a stáhnout audio přes vzorec zjištěný v (1).
  4. Zapracovat do stejného manifestu/pojmenování jako díly 85+.
