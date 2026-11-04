import os
import requests

# Player accounts live in Cloudflare D1, behind the auth Worker in auth-worker/. This server is the
# Worker's only client: it forwards the player's Turnstile token and IP, and the Worker verifies
# the token, hashes passwords and keeps track of which villages each account owns.

AUTH_API_URL = os.environ.get("AUTH_API_URL", "http://127.0.0.1:8787").rstrip("/")
AUTH_API_KEY = os.environ.get("AUTH_API_KEY", "")
TURNSTILE_SITEKEY = os.environ.get("TURNSTILE_SITEKEY", "")

# Worker error codes -> what the player sees
MESSAGES = {
    "invalid_email": "Please enter a valid email address.",
    "invalid_password": "Passwords must be 8 to 128 characters long.",
    "email_taken": "An account with that email already exists.",
    "invalid_credentials": "Wrong email or password.",
    "turnstile_failed": "The security check failed. Please try again.",
    "village_limit": "You have reached the maximum number of villages.",
    "unavailable": "The account service is unavailable. Please try again later.",
}

class AuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.message = MESSAGES.get(code, "Something went wrong. Please try again.")

def _call(method: str, path: str, body: dict = None) -> dict:
    try:
        r = requests.request(method, AUTH_API_URL + path, json=body, timeout=15,
                             headers={"Authorization": f"Bearer {AUTH_API_KEY}"})
    except requests.RequestException as e:
        print(f"[!] Auth service unreachable: {e}")
        raise AuthError("unavailable")
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        code = data.get("error", "unavailable")
        if code in ("unauthorized", "internal", "not_found"):
            print(f"[!] Auth service error: {r.status_code} {code}")
            code = "unavailable"
        raise AuthError(code)
    return data

def signup(email: str, password: str, turnstile_token: str, remote_ip: str) -> dict:
    return _call("POST", "/signup", {"email": email, "password": password,
                                     "turnstileToken": turnstile_token, "remoteIp": remote_ip})["user"]

def login(email: str, password: str, turnstile_token: str, remote_ip: str) -> dict:
    return _call("POST", "/login", {"email": email, "password": password,
                                    "turnstileToken": turnstile_token, "remoteIp": remote_ip})["user"]

def villages(user_id: int) -> list:
    return _call("GET", f"/users/{int(user_id)}/villages")["villages"]

def add_village(user_id: int, uid: str) -> None:
    _call("POST", f"/users/{int(user_id)}/villages", {"uid": uid})
