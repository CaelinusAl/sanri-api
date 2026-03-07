import requests


def send_push(token: str, title: str, body: str):

    if not token:
        return

    payload = {
        "to": token,
        "sound": "default",
        "title": title,
        "body": body
    }

    requests.post(
        "https://exp.host/--/api/v2/push/send",
        json=payload,
        timeout=20
    )