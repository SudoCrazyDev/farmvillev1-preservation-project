// FarmVille desktop client.
// Electron 11 is the last Electron able to load the Pepper (PPAPI) Flash plugin, so this
// client is pinned to it. Its Chromium is old and unpatched: the window is locked to the
// configured game server and every request to any other host (except Turnstile) is blocked.

const { app, BrowserWindow, Menu, session, dialog } = require("electron");
const fs = require("fs");
const path = require("path");

const FLASH_VERSION = "32.0.0.371";
const DEFAULT_CONFIG = { serverUrl: "http://127.0.0.1:5500" };

// Packaged: config.json and plugins/ sit next to FarmVille.exe. Dev: next to this file.
const baseDir = app.isPackaged ? path.dirname(process.execPath) : __dirname;

function loadConfig() {
    const file = path.join(baseDir, "config.json");
    if (!fs.existsSync(file)) {
        fs.writeFileSync(file, JSON.stringify(DEFAULT_CONFIG, null, 4) + "\n");
        return { ...DEFAULT_CONFIG };
    }
    try {
        return { ...DEFAULT_CONFIG, ...JSON.parse(fs.readFileSync(file, "utf8")) };
    } catch (e) {
        dialog.showErrorBox("FarmVille", `Could not read ${file}:\n${e.message}`);
        app.exit(1);
    }
}

function findFlashPlugin() {
    const dir = path.join(baseDir, "plugins");
    const dll = fs.existsSync(dir) && fs.readdirSync(dir).find((f) => /^pepflashplayer.*\.dll$/i.test(f));
    return dll ? path.join(dir, dll) : null;
}

const config = loadConfig();
const serverOrigin = new URL(config.serverUrl).origin;
const flashPath = findFlashPlugin();

// Must be set before the app is ready.
if (flashPath) {
    app.commandLine.appendSwitch("ppapi-flash-path", flashPath);
    app.commandLine.appendSwitch("ppapi-flash-version", FLASH_VERSION);
}

function isServerUrl(url) {
    try {
        return new URL(url).origin === serverOrigin;
    } catch {
        return false;
    }
}

// Turnstile (the login/signup bot check) runs from Cloudflare in an iframe on the server's pages.
const TURNSTILE_ORIGIN = "https://challenges.cloudflare.com";

function isAllowedRequest(url) {
    if (isServerUrl(url)) return true;
    try {
        return new URL(url).origin === TURNSTILE_ORIGIN;
    } catch {
        return false;
    }
}

function lockToServer(win) {
    // Only http(s)/ws(s) traffic to the game server (and Turnstile) goes out. data:, blob:, devtools etc. pass.
    session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
        const remote = /^(https?|wss?):/i.test(details.url);
        const blocked = remote && !isAllowedRequest(details.url);
        if (blocked) console.log("[blocked]", details.url);
        callback({ cancel: blocked });
    });
    session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));

    win.webContents.on("will-navigate", (event, url) => {
        if (!isServerUrl(url)) event.preventDefault();
    });
    // Electron 11 has no setWindowOpenHandler yet.
    win.webContents.on("new-window", (event) => event.preventDefault());
}

function createWindow() {
    const win = new BrowserWindow({
        width: 1100,
        height: 860,
        title: "FarmVille",
        backgroundColor: "#ffffff",
        webPreferences: {
            plugins: true,
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
        },
    });
    lockToServer(win);

    win.webContents.on("before-input-event", (event, input) => {
        if (input.type !== "keyDown") return;
        if (input.key === "F5") {
            // On the "cannot reach server" page, retry the server instead of reloading the page.
            if (win.webContents.getURL().startsWith("data:")) win.loadURL(config.serverUrl);
            else win.webContents.reload();
        }
        else if (input.key === "F11") win.setFullScreen(!win.isFullScreen());
        else if (input.key === "F12") win.webContents.toggleDevTools();
        else return;
        event.preventDefault();
    });

    win.webContents.on("did-fail-load", (_e, code, desc, url) => {
        if (code === -3) return; // aborted, e.g. a redirect
        win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(
            `<body style="font-family:sans-serif;padding:2em">
             <h2>Cannot reach the FarmVille server</h2>
             <p>${url}: ${desc}</p>
             <p>Start the server, or set <code>serverUrl</code> in config.json next to FarmVille.exe. Press F5 to retry.</p>
             </body>`));
    });

    win.loadURL(config.serverUrl);
    return win;
}

Menu.setApplicationMenu(null);

app.whenReady().then(() => {
    const win = createWindow();
    if (!flashPath) {
        dialog.showMessageBox(win, {
            type: "warning",
            title: "FarmVille",
            message: "Flash Player plugin not found.",
            detail: "Put pepflashplayer64_32_0_0_371.dll in the plugins folder next to FarmVille.exe, then restart.",
        });
    }
});

app.on("window-all-closed", () => app.quit());
