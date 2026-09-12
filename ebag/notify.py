# -*- coding: utf-8 -*-
"""Push notification for watch-list offers that clear the alert threshold.

These were emails once, sent through Resend's HTTP API. They are now web push
notifications, delivered by the grocery-deal app (Mirellla/grocery_deal) which
already owns the device subscriptions, the VAPID keys and an in-app notification
history -- see its `lib/ebag-alerts.ts` and `app/api/push/ebag/route.ts`. A push
lands on the phone that does the shopping, and the app keeps the alert readable
afterwards, which an email in a rarely-read inbox did not.

What this posts is the offers, not their wording. The app renders the message,
so it follows the reader's language like every other notification it sends, and
a tap lands on the deal's own row.

Configuration, all from the environment:

    EBAG_PUSH_URL         https://<app>/api/push/ebag; without it send()
                          reports what it would have sent and returns False
    PUSH_DISPATCH_SECRET  shared secret, the same one the app's other
                          pipeline-facing endpoint authenticates with

Only a 2xx counts as sent, and the caller writes `ebag_alerts` on that alone --
so the app being down, its VAPID keys unset or the secret rotated all leave
these offers unrecorded, and the next run announces them again rather than
losing the one notification an offer gets.

A reply saying `delivered: 0` is *not* a failure. The app records the
notification whether or not a device receives it, which is what makes a broken
push configuration distinguishable from a quiet week.
"""
import json
import os
import urllib.error
import urllib.request

import load

TIMEOUT = 30


def payload(alerts, deal_ids):
    """alerts: [(rule_name, offer)], steepest discount first.

    `deal_ids` maps the `deals.product` this run wrote onto its row id, so the
    notification can deep-link into the app. A missing id is sent as null and
    the app opens the deals page unfiltered.
    """
    offers = []
    for rule, offer in sorted(alerts, key=lambda a: -a[1]["discount"]):
        hit = offer["hit"]
        product = load.display(hit)
        offers.append({
            "rule": rule,
            "product": product,
            "discount": offer["discount"],
            "price": hit["current_price_eur"],
            "dealId": deal_ids.get(product),
        })
    return {"offers": offers}


def deliver(body):
    """Post one alert. Returns True when the app accepted it."""
    url = os.environ.get("EBAG_PUSH_URL")
    secret = os.environ.get("PUSH_DISPATCH_SECRET")
    if not url or not secret:
        print("EBAG_PUSH_URL / PUSH_DISPATCH_SECRET not set; would have sent:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return False

    request = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer %s" % secret,
                 "Content-Type": "application/json",
                 # Names this collector in the app's request log.
                 "User-Agent": "grocery-deal-ebag/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        print("app refused the alert (%s): %s" % (exc.code, exc.read().decode()[:300]))
        return False
    except urllib.error.URLError as exc:
        print("could not reach the app: %s" % exc.reason)
        return False

    note = "" if result.get("pushed", True) else " (alerts switched off; recorded only)"
    print("notified %d device(s)%s" % (result.get("delivered", 0), note))
    return True


def send(alerts, deal_ids):
    """True when the app accepted the alert."""
    if not alerts:
        return False
    return deliver(payload(alerts, deal_ids))
