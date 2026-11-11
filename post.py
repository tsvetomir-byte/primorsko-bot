"""Primorsko Bot - 1 prispevek denne na Facebook + Instagram stranky Balkanske potraviny Primorsko.
Sude dny produkt z e-shopu, liche dny recept z bp.bpprimorsko.cz/recepty/. Nic se neopakuje.
"""
import gzip, io, json, os, random, re, sys, time
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

SHOP = "https://bp.bpprimorsko.cz"
GRAPH = "https://graph.facebook.com/v21.0"
LOG = "posted.json"
POST_HOUR = int(os.environ.get("POST_HOUR", "11"))
UA = {"User-Agent": "Mozilla/5.0 (PrimorskoBot)"}
GREEN, DARK, WHITE = (46, 125, 50), (20, 60, 25), (255, 255, 255)
W, H = 1080, 1350

TAGS_PRODUCT = "#bulharskepotraviny #balkanskepotraviny #primorsko #praha7 #holesovice #bulharsko #balkan #bulharskyobchod #sirene #kaskaval #ljutenica #bulgaria #българи #българивпрага #българскихрани"
TAGS_RECIPE = "#bulharskerecepty #balkanskakuchyne #recept #vareni #bulharsko #balkan #primorsko #praha7 #holesovice #bulgarianfood #българскакухня #рецепта #българивчехия"
FOOTER = ("📍 Balkánské potraviny Primorsko\nPlynární 1364/4, Praha 7 – Holešovice (kousek od metra Nádraží Holešovice)\n"
          "🛒 E-shop s dovozem po celé ČR: bp.bpprimorsko.cz\n📞 +420 776 366 679")


def log(*a):
    print(*a, flush=True)


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=40, **kw)
    r.raise_for_status()
    return r


def clean(t):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def meta(html, name):
    m = re.search(r'<meta[^>]+(?:property|name|itemprop)="%s"[^>]*content="([^"]*)"' % re.escape(name), html) or \
        re.search(r'<meta[^>]+content="([^"]*)"[^>]+(?:property|name|itemprop)="%s"' % re.escape(name), html)
    return unescape(m.group(1)) if m else ""


# ------------------------------------------------------------------ produkty
def shop_urls():
    idx = get(SHOP + "/sitemap.xml").text
    urls = []
    for sm in re.findall(r"<loc>([^<]+)</loc>", idx):
        raw = get(sm).content
        if sm.endswith(".gz"):
            raw = gzip.decompress(raw)
        urls += re.findall(r"<loc>([^<]+)</loc>", raw.decode("utf-8", "ignore"))
    skip = ("/recepty", "/kontakty", "/obchodni-podminky", "/podminky", "/blog", "/clanky", "/formular", "/kosik", "/login", "/registrace")
    return [u for u in urls if u.startswith(SHOP) and u.count("/") == 4 and not any(s in u for s in skip)]


def product(url):
    html = get(url).text
    if "type-product" not in html:
        return None
    img = meta(html, "og:image").split("?")[0]
    price = meta(html, "price") or meta(html, "product:price:amount")
    avail = re.search(r'itemprop="availability"[^>]*href="([^"]+)"', html)
    name = clean(re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)) if re.search(r"<h1", html) else ""
    short = re.search(r'class="p-short-description"[^>]*>(.*?)</div>', html, re.S)
    if not (img and price and name) or "/user/shop/" not in img:
        return None
    try:
        price = float(price)
    except ValueError:
        return None
    if price <= 0:
        return None
    return {"url": url, "name": name, "img": img, "price": price, "short": clean(short.group(1)) if short else "",
            "in_stock": bool(avail and "InStock" in avail.group(1))}


def pick_product(done):
    urls = [u for u in shop_urls() if u not in done]
    random.shuffle(urls)
    backup = None
    for u in urls[:80]:
        try:
            p = product(u)
        except Exception as e:
            log("skip", u, e)
            continue
        if not p:
            continue
        if p["in_stock"]:
            return p
        backup = backup or p
    return backup


def product_caption(p):
    price = ("%.2f" % p["price"]).replace(".", ",") + " Kč"
    stock = "✅ Skladem v naší prodejně v Holešovicích" if p["in_stock"] else "📦 Rádi vám ho objednáme – stačí poslat poptávku"
    lines = ["🇧🇬 " + p["name"], "", p["short"] or "Pravá bulharská a balkánská chuť přímo v Praze.", "",
             "💰 Cena: " + price, stock, "👉 Objednat online: " + p["url"], "", FOOTER, "", TAGS_PRODUCT]
    return "\n".join(lines)


# ------------------------------------------------------------------ recepty
def recipes():
    html = get(SHOP + "/recepty/").text
    out = []
    for block in re.split(r'(?=<[a-z]+[^>]*class="bpr-card)', html)[1:]:
        name = re.search(r'class="bpr-name"[^>]*>(.*?)</', block, re.S)
        if not name:
            continue
        name = clean(name.group(1))
        desc = re.search(r'class="bpr-desc"[^>]*>(.*?)</', block, re.S)
        metai = re.search(r'class="bpr-meta"[^>]*>(.*?)</div>', block, re.S)
        lbl = re.search(r'class="bpr-lbl"[^>]*>(.*?)</', block, re.S)
        imgs = [i.split("?")[0] for i in re.findall(r'<img[^>]+src="([^"]+/user/shop/[^"]+)"', block)]
        ingr = re.search(r"Suroviny</h3>(.*?)</(?:ul|ol)>", block, re.S)
        ingr = [clean(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", ingr.group(1), re.S)] if ingr else []
        prods = []
        for href, txt in re.findall(r'<a[^>]+href="(/[^"#?]+/)"[^>]*>(.*?)</a>', block, re.S):
            txt = clean(txt)
            if txt and (href, txt) not in prods:
                prods.append((href, txt))
        out.append({"name": name, "desc": clean(desc.group(1)) if desc else "", "meta": clean(metai.group(1)) if metai else "",
                    "label": clean(lbl.group(1)) if lbl else "", "img": imgs[0] if imgs else "", "ingr": ingr, "prods": prods[:5]})
    return out


def pick_recipe(done):
    allr = [r for r in recipes() if r["name"] not in done]
    withimg = [r for r in allr if r["img"]]
    pool = withimg or allr
    return random.choice(pool) if pool else None


def recipe_caption(r):
    lines = ["🍲 RECEPT DNE: " + r["name"], ""]
    if r["desc"]:
        lines += [r["desc"], ""]
    if r["meta"]:
        lines += [r["meta"], ""]
    if r["ingr"]:
        lines += ["🧺 Suroviny:"] + ["• " + i for i in r["ingr"][:12]] + [""]
    lines += ["👩‍🍳 Celý postup najdete na webu: " + SHOP + "/recepty/"]
    if r["prods"]:
        lines += ["", "🛒 Nákupní seznam – suroviny koupíte u nás:"] + ["• %s – %s%s" % (t, SHOP, h) for h, t in r["prods"]]
    lines += ["", FOOTER, "", TAGS_RECIPE]
    return "\n".join(lines)


# ------------------------------------------------------------------ obrazek
def font(name, size):
    try:
        return ImageFont.truetype("fonts/%s.ttf" % name, size)
    except OSError:
        return ImageFont.load_default()


def wrap(d, text, f, max_w, max_lines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(",.–- ") + "…"
    return lines


def render(img_url, kicker, title, sub, out="post.jpg"):
    canvas = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(canvas)
    band_h = 360
    if img_url:
        ph = Image.open(io.BytesIO(get(img_url).content)).convert("RGB")
        ph = ImageOps.contain(ph, (W - 120, H - band_h - 140))
        canvas.paste(ph, ((W - ph.width) // 2, 70 + (H - band_h - 140 - ph.height) // 2))
    d.rectangle([0, H - band_h, W, H], fill=GREEN)
    d.rectangle([0, 0, W, 14], fill=GREEN)
    fk, ft, fs = font("Poppins-Medium", 34), font("Poppins-Bold", 54), font("Poppins-Medium", 30)
    y = H - band_h + 34
    d.text((60, y), kicker.upper(), font=fk, fill=(200, 230, 201))
    y += 56
    for line in wrap(d, title, ft, W - 120, 2):
        d.text((60, y), line, font=ft, fill=WHITE)
        y += 66
    d.text((60, H - 60), sub, font=fs, fill=WHITE, anchor="ls")
    canvas.save(out, "JPEG", quality=92)
    return out


# ------------------------------------------------------------------ publikace
def host_image(path):
    gh, repo = os.environ["GH_TOKEN"], os.environ["GITHUB_REPOSITORY"]
    h = {"Authorization": "Bearer " + gh, "Accept": "application/vnd.github+json"}
    api = "https://api.github.com/repos/" + repo
    rel = requests.get(api + "/releases/tags/posts", headers=h, timeout=30)
    if rel.status_code == 404:
        rel = requests.post(api + "/releases", headers=h, timeout=30, json={"tag_name": "posts", "name": "Obrázky příspěvků"})
    rel.raise_for_status()
    name = "post-%s.jpg" % datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    with open(path, "rb") as fh:
        up = requests.post("https://uploads.github.com/repos/%s/releases/%d/assets" % (repo, rel.json()["id"]),
                           params={"name": name}, headers=dict(h, **{"Content-Type": "image/jpeg"}), data=fh, timeout=120)
    up.raise_for_status()
    return up.json()["browser_download_url"]


def post_facebook(path, cap):
    page, tok = os.environ["FB_PAGE_ID"], os.environ["PAGE_TOKEN"]
    with open(path, "rb") as fh:
        r = requests.post("%s/%s/photos" % (GRAPH, page), data={"message": cap, "access_token": tok},
                          files={"source": fh}, timeout=120).json()
    if "id" not in r:
        raise RuntimeError("Facebook: %s" % r)
    return r.get("post_id", r["id"])


def post_instagram(url, cap):
    ig, tok = os.environ.get("IG_USER_ID"), os.environ["PAGE_TOKEN"]
    if not ig:
        log("IG_USER_ID není nastaveno - Instagram přeskočen")
        return None
    cap = cap[:2150]
    r = requests.post("%s/%s/media" % (GRAPH, ig), data={"image_url": url, "caption": cap, "access_token": tok}, timeout=60).json()
    if "id" not in r:
        raise RuntimeError("Instagram container: %s" % r)
    for _ in range(12):
        s = requests.get("%s/%s" % (GRAPH, r["id"]), params={"fields": "status_code", "access_token": tok}, timeout=30).json()
        if s.get("status_code") in ("FINISHED", None):
            break
        time.sleep(5)
    p = requests.post("%s/%s/media_publish" % (GRAPH, ig), data={"creation_id": r["id"], "access_token": tok}, timeout=60).json()
    if "id" not in p:
        raise RuntimeError("Instagram publish: %s" % p)
    return p["id"]


def main():
    now = datetime.now(ZoneInfo("Europe/Prague"))
    force, dry = os.environ.get("FORCE") == "1", os.environ.get("DRY_RUN") == "1"
    if not dry and not os.environ.get("PAGE_TOKEN"):
        log("PAGE_TOKEN není nastaven - nic se nepublikuje")
        return
    if not force and now.hour != POST_HOUR:
        log("Není čas příspěvku (%d:00 Praha), teď %s" % (POST_HOUR, now.strftime("%H:%M")))
        return
    data = json.load(open(LOG)) if os.path.exists(LOG) else {"days": {}, "products": [], "recipes": []}
    day = now.strftime("%Y-%m-%d")
    if not force and day in data["days"]:
        log("Dnes už bylo publikováno")
        return
    kind = os.environ.get("KIND") or ("product" if now.toordinal() % 2 == 0 else "recipe")
    if kind == "recipe":
        r = pick_recipe(data["recipes"])
        if not r:
            data["recipes"], r = [], pick_recipe([])
        cap = recipe_caption(r)
        render(r["img"], "Recept dne · " + (r["label"] or "Balkánská kuchyně"), r["name"], "bp.bpprimorsko.cz/recepty")
        key = r["name"]
    else:
        p = pick_product(data["products"])
        if not p:
            data["products"], p = [], pick_product([])
        cap = product_caption(p)
        render(p["img"], "Balkánské potraviny Primorsko", p["name"], ("%.2f" % p["price"]).replace(".", ",") + " Kč · Praha 7 – Holešovice")
        key = p["url"]
    log("Typ:", kind, "|", key)
    log(cap)
    if dry:
        log("DRY RUN - nepublikuji (obrázek je v artefaktu post-image)")
        return
    fb = post_facebook("post.jpg", cap)
    log("Facebook OK", fb)
    ig = None
    try:
        ig = post_instagram(host_image("post.jpg"), cap)
        log("Instagram OK", ig)
    except Exception as e:
        log("Instagram chyba:", e)
    data["products" if kind == "product" else "recipes"].append(key)
    data["days"][day] = {"kind": kind, "item": key, "fb": fb, "ig": ig, "at": now.isoformat()}
    json.dump(data, open(LOG, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("CHYBA:", e)
        sys.exit(1)
