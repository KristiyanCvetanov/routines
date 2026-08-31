# -*- coding: utf-8 -*-
"""Email for watch-list offers that clear the alert threshold.

Sent through Resend's HTTP API rather than a Claude connector: a cloud routine
can only attach connectors the account has authorised, and Gmail is not among
them. An HTTP call needs nothing but the key.

Configuration, all from the environment:

    RESEND_API_KEY   required; without it send() reports and returns False
    ALERT_TO         recipient
    ALERT_FROM       sender, default onboarding@resend.dev

Resend only accepts a `from` on a domain you have verified. Until a domain is
added, `onboarding@resend.dev` is the one usable sender and it can only deliver
to the address that owns the Resend account.
"""
import json
import os
import urllib.error
import urllib.request

ENDPOINT = "https://api.resend.com/emails"
DEFAULT_FROM = "onboarding@resend.dev"


def render(alerts):
    """alerts: [(rule_name, offer)] -> (subject, body)."""
    best = max(o["discount"] for _, o in alerts)
    subject = "eBag: %d оферти от списъка, до -%d%%" % (len(alerts), best)

    lines = ["Нови оферти по следените критерии:", ""]
    for rule, offer in sorted(alerts, key=lambda a: -a[1]["discount"]):
        hit = offer["hit"]
        pack = hit.get("unit_weight_text_value_bg") or ""
        kind = "мултипак" if offer["kind"] == "multipack" else "промоция"
        lines.append("  -%d%%  %s%s" % (offer["discount"], hit["name_bg"],
                                        (", " + pack) if pack else ""))
        lines.append("        %.2f EUR  (%s, %s)"
                     % (hit["current_price_eur"], kind, rule))
        period = hit.get("promo_period")
        if period:
            lines.append("        промо период: %s" % period)
        slug = hit.get("url_slug_bg")
        if slug:
            lines.append("        https://www.ebag.bg/%s/%s" % (slug, hit["id"]))
        lines.append("")
    lines.append("Всяка оферта се праща веднъж на промоционален прозорец.")
    return subject, "\n".join(lines)


def deliver(subject, body, to=None):
    """Post one message. Returns True when Resend accepted it."""
    key = os.environ.get("RESEND_API_KEY")
    recipient = to or os.environ.get("ALERT_TO")
    if not key or not recipient:
        print("RESEND_API_KEY / ALERT_TO not set; would have sent:\n%s\n\n%s"
              % (subject, body))
        return False

    payload = json.dumps({
        "from": os.environ.get("ALERT_FROM", DEFAULT_FROM),
        "to": [recipient],
        "subject": subject,
        "text": body,
    }).encode()
    request = urllib.request.Request(
        ENDPOINT, data=payload,
        headers={"Authorization": "Bearer %s" % key,
                 "Content-Type": "application/json",
                 # Resend sits behind Cloudflare, which answers the default
                 # Python-urllib agent with 403 / error code 1010.
                 "User-Agent": "grocery-deal-ebag/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        print("emailed %s (resend id %s)" % (recipient, result.get("id")))
        return True
    except urllib.error.HTTPError as exc:
        print("resend refused (%s): %s" % (exc.code, exc.read().decode()[:300]))
        return False


def send(alerts):
    """True when a message actually went out."""
    if not alerts:
        return False
    subject, body = render(alerts)
    return deliver(subject, body)
