"""Primorsko Bot - hlidac dotazu: nove zpravy a komentare na FB strance (+ Instagram komentare)
posle e-mailem na bpprimorsko@gmail.com."""
import json, os, smtplib, sys
from email.mime.text import MIMEText

import requests

GRAPH = "https://graph.facebook.com/v21.0"
SEEN = "alerts_seen.json"
TO = os.environ.get("ALERT_TO", "bpprimorsko@gmail.com")


def ig_id():
    if os.environ.get("IG_USER_ID"):
        return os.environ["IG_USER_ID"]
    try:
        r = requests.get("%s/%s" % (GRAPH, os.environ["FB_PAGE_ID"]), params={"fields": "instagram_business_account",
                         "access_token": os.environ["PAGE_TOKEN"]}, timeout=30).json()
        return r.get("instagram_business_account", {}).get("id")
    except Exception:
        return None


def g(path, **params):
    params["access_token"] = os.environ["PAGE_TOKEN"]
    r = requests.get("%s/%s" % (GRAPH, path), params=params, timeout=40).json()
    if "error" in r:
        print("Graph chyba", path, r["error"].get("message"))
        return {}
    return r


def collect():
    page, ig = os.environ["FB_PAGE_ID"], ig_id()
    items = []
    for c in g(page + "/conversations", fields="id,updated_time,messages.limit(1){id,from,message,created_time}", limit=20).get("data", []):
        for m in c.get("messages", {}).get("data", []):
            if m.get("from", {}).get("id") != page:
                items.append((m["id"], "Zpráva na Facebooku", m.get("from", {}).get("name", "?"), m.get("message", ""),
                              "https://business.facebook.com/latest/inbox"))
    for p in g(page + "/posts", fields="id,permalink_url,comments.limit(25){id,from,message}", limit=15).get("data", []):
        for c in p.get("comments", {}).get("data", []):
            if c.get("from", {}).get("id") != page:
                items.append((c["id"], "Komentář na Facebooku", c.get("from", {}).get("name", "?"), c.get("message", ""), p.get("permalink_url", "")))
    if ig:
        for m in g(ig + "/media", fields="id,permalink,comments{id,username,text}", limit=15).get("data", []):
            for c in m.get("comments", {}).get("data", []):
                items.append((c["id"], "Komentář na Instagramu", c.get("username", "?"), c.get("text", ""), m.get("permalink", "")))
    return items


def send(new):
    body = "\n\n".join("%s od: %s\n„%s“\nOdkaz: %s" % (k, who, txt, link) for _, k, who, txt, link in new)
    msg = MIMEText("Nové dotazy na sociálních sítích Balkánské potraviny Primorsko:\n\n" + body, "plain", "utf-8")
    msg["Subject"] = "Primorsko: %d nových dotazů / komentářů" % len(new)
    msg["From"], msg["To"] = os.environ["SMTP_USER"], TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def main():
    if not os.environ.get("PAGE_TOKEN"):
        print("PAGE_TOKEN není nastaven")
        return
    seen = json.load(open(SEEN)) if os.path.exists(SEEN) else None
    items = collect()
    if seen is None:  # prvni spusteni: jen zapamatovat stav, neposilat stare veci
        json.dump([i[0] for i in items], open(SEEN, "w"))
        print("První spuštění, uloženo", len(items))
        return
    new = [i for i in items if i[0] not in seen]
    print("Nových:", len(new))
    if new and os.environ.get("SMTP_PASS"):
        send(new)
    elif new:
        print("SMTP_PASS chybí - e-mail neodeslán")
        return
    json.dump((seen + [i[0] for i in new])[-2000:], open(SEEN, "w"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("CHYBA:", e)
        sys.exit(1)
