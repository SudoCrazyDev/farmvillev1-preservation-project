// Account service for the FarmVille server.
//
// Only the game server talks to this Worker. Every request carries
// `Authorization: Bearer <AUTH_API_KEY>`. Signup and login also carry the player's Turnstile
// token, which is verified here (siteverify) before anything touches the database.
//
//   POST /signup            {email, password, turnstileToken, remoteIp} -> {user}
//   POST /login             {email, password, turnstileToken, remoteIp} -> {user}
//   GET  /users/:id/villages                                              -> {villages: [uid]}
//   POST /users/:id/villages {uid}                                        -> {ok}
//
// Errors are {error: "<code>"} with a 4xx status. The game server maps codes to messages.

const PBKDF2_ITERATIONS = 100_000; // the Workers runtime's maximum for PBKDF2
const MAX_BODY_BYTES = 8 * 1024;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const UID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export default {
    async fetch(request, env) {
        try {
            if (!(await authorized(request, env))) return error("unauthorized", 401);
            return await route(request, env);
        } catch (e) {
            if (e instanceof HttpError) return error(e.code, e.status);
            console.error("unhandled", e);
            return error("internal", 500);
        }
    },
};

async function route(request, env) {
    const url = new URL(request.url);
    const method = request.method;

    if (method === "POST" && url.pathname === "/signup") return signup(await readJson(request), env);
    if (method === "POST" && url.pathname === "/login") return login(await readJson(request), env);

    const m = url.pathname.match(/^\/users\/(\d+)\/villages$/);
    if (m && method === "GET") return listVillages(Number(m[1]), env);
    if (m && method === "POST") return addVillage(Number(m[1]), await readJson(request), env);

    return error("not_found", 404);
}

// --- handlers ---

async function signup(body, env) {
    const email = normalizeEmail(body.email);
    const password = body.password;
    if (!email) throw new HttpError("invalid_email");
    if (typeof password !== "string" || password.length < 8 || password.length > 128) {
        throw new HttpError("invalid_password");
    }
    await verifyTurnstile(body, "signup", env);

    const hash = await hashPassword(password);
    const now = Date.now();
    try {
        const row = await env.DB.prepare(
            "INSERT INTO users (email, password_hash, created_at, last_login_at) VALUES (?, ?, ?, ?) RETURNING id, email",
        ).bind(email, hash, now, now).first();
        return json({ user: row });
    } catch (e) {
        if (String(e.message).includes("UNIQUE")) throw new HttpError("email_taken", 409);
        throw e;
    }
}

async function login(body, env) {
    const email = normalizeEmail(body.email);
    const password = typeof body.password === "string" ? body.password : "";
    await verifyTurnstile(body, "login", env);

    const row = email
        ? await env.DB.prepare("SELECT id, email, password_hash FROM users WHERE email = ?").bind(email).first()
        : null;
    // Hash even when the user doesn't exist, so response time doesn't reveal registered emails.
    const ok = await verifyPassword(password, row ? row.password_hash : DUMMY_HASH);
    if (!row || !ok) throw new HttpError("invalid_credentials", 401);

    await env.DB.prepare("UPDATE users SET last_login_at = ? WHERE id = ?").bind(Date.now(), row.id).run();
    return json({ user: { id: row.id, email: row.email } });
}

async function listVillages(userId, env) {
    const { results } = await env.DB.prepare(
        "SELECT uid FROM villages WHERE user_id = ? ORDER BY created_at",
    ).bind(userId).all();
    return json({ villages: results.map((r) => r.uid) });
}

async function addVillage(userId, body, env) {
    if (typeof body.uid !== "string" || !UID_RE.test(body.uid)) throw new HttpError("invalid_uid");
    const user = await env.DB.prepare("SELECT id FROM users WHERE id = ?").bind(userId).first();
    if (!user) throw new HttpError("user_not_found", 404);

    const max = Number(env.MAX_VILLAGES_PER_USER || 3);
    const { n } = await env.DB.prepare("SELECT COUNT(*) AS n FROM villages WHERE user_id = ?").bind(userId).first();
    if (n >= max) throw new HttpError("village_limit", 409);

    try {
        await env.DB.prepare("INSERT INTO villages (uid, user_id, created_at) VALUES (?, ?, ?)")
            .bind(body.uid, userId, Date.now()).run();
    } catch (e) {
        if (String(e.message).includes("UNIQUE")) throw new HttpError("village_taken", 409);
        throw e;
    }
    return json({ ok: true });
}

// --- Turnstile ---

async function verifyTurnstile(body, expectedAction, env) {
    const token = body.turnstileToken;
    const hostnames = new Set(String(env.TURNSTILE_HOSTNAMES || "").split(",").map((h) => h.trim()).filter(Boolean));
    if (typeof token !== "string" || token.length === 0 || token.length > 2048 || hostnames.size === 0) {
        throw new HttpError("turnstile_failed", 403);
    }

    const form = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token });
    if (typeof body.remoteIp === "string" && body.remoteIp) form.set("remoteip", body.remoteIp);

    let result;
    try {
        const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: form,
            signal: AbortSignal.timeout(10_000),
        });
        if (!r.ok) throw new Error(`siteverify ${r.status}`);
        result = await r.json();
    } catch (e) {
        console.error("siteverify failed", e);
        throw new HttpError("turnstile_failed", 403); // fail closed
    }
    // Turnstile's test keys answer with hostname "example.com" and no action. Accept that only
    // when ALLOW_TURNSTILE_TEST_KEYS is set (local .dev.vars); production always rejects it.
    const testKeyResult = result.metadata?.result_with_testing_key === true;
    if (testKeyResult) {
        if (env.ALLOW_TURNSTILE_TEST_KEYS === "true" && result.success) return;
        throw new HttpError("turnstile_failed", 403);
    }
    if (!result.success || result.action !== expectedAction || !hostnames.has(result.hostname)) {
        throw new HttpError("turnstile_failed", 403);
    }
}

// --- passwords: PBKDF2-SHA256, stored as pbkdf2$<iterations>$<salt b64>$<hash b64> ---

const DUMMY_HASH = "pbkdf2$100000$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

async function hashPassword(password) {
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const hash = await pbkdf2(password, salt, PBKDF2_ITERATIONS);
    return `pbkdf2$${PBKDF2_ITERATIONS}$${b64(salt)}$${b64(hash)}`;
}

async function verifyPassword(password, stored) {
    const [scheme, iter, saltB64, hashB64] = stored.split("$");
    if (scheme !== "pbkdf2") return false;
    const expected = unb64(hashB64);
    const actual = await pbkdf2(password, unb64(saltB64), Number(iter));
    return actual.byteLength === expected.byteLength && crypto.subtle.timingSafeEqual(actual, expected);
}

async function pbkdf2(password, salt, iterations) {
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
    const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, key, 256);
    return new Uint8Array(bits);
}

// --- helpers ---

async function authorized(request, env) {
    const header = request.headers.get("Authorization") || "";
    const given = new TextEncoder().encode(header.replace(/^Bearer /, ""));
    const expected = new TextEncoder().encode(env.AUTH_API_KEY || "");
    if (expected.byteLength < 32 || given.byteLength !== expected.byteLength) return false;
    return crypto.subtle.timingSafeEqual(given, expected);
}

async function readJson(request) {
    const text = await request.text();
    if (text.length > MAX_BODY_BYTES) throw new HttpError("body_too_large", 413);
    try {
        const body = JSON.parse(text);
        if (body && typeof body === "object") return body;
    } catch {}
    throw new HttpError("invalid_json");
}

function normalizeEmail(email) {
    if (typeof email !== "string") return null;
    const e = email.trim().toLowerCase();
    return e.length <= 254 && EMAIL_RE.test(e) ? e : null;
}

const b64 = (bytes) => btoa(String.fromCharCode(...bytes));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const json = (data, status = 200) => Response.json(data, { status });
const error = (code, status = 400) => json({ error: code }, status);

class HttpError extends Error {
    constructor(code, status = 400) {
        super(code);
        this.code = code;
        this.status = status;
    }
}
