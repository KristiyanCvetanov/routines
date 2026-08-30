# -*- coding: utf-8 -*-
"""Email for watch-list offers that clear the alert threshold.

Sent over SMTP rather than through a Claude connector: the cloud routine can
only attach connectors the account has authorised, and Gmail is not among them
today, while SMTP works from any environment that has the credentials.

Configuration, all from the environment:

    SMTP_HOST      default smtp.gmail.com
    SMTP_PORT      default 587 (STARTTLS)
    SMTP_USER      the sending account
    SMTP_PASSWORD  a Gmail app password, NOT the account password
    ALERT_TO       recipient; defaults to SMTP_USER

With none of these set, send() reports what it would have sent and returns
False, so a run never fails just because mail is unconfigured.
"""
import email.message
import os
import smtplib


def _config():
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    if not user or not password:
        return None
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": user,
        "password": password,
        "to": os.environ.get("ALERT_TO", user),
    }


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
        until = hit.get("promo_period")
        if until:
            lines.append("        промо период: %s" % until)
        slug = hit.get("url_slug_bg")
        if slug:
            lines.append("        https://www.ebag.bg/%s/%s" % (slug, hit["id"]))
        lines.append("")
    lines.append("Всяка оферта се праща веднъж на промоционален прозорец.")
    return subject, "\n".join(lines)


def send(alerts):
    """True when a message actually went out."""
    if not alerts:
        return False
    subject, body = render(alerts)
    config = _config()
    if not config:
        print("SMTP not configured; would have sent:\n%s\n%s" % (subject, body))
        return False

    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = config["user"]
    message["To"] = config["to"]
    message.set_content(body)

    with smtplib.SMTP(config["host"], config["port"], timeout=30) as server:
        server.starttls()
        server.login(config["user"], config["password"])
        server.send_message(message)
    print("emailed %d alerts to %s" % (len(alerts), config["to"]))
    return True
