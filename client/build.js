// Packages the client into dist/FarmVille-win32-x64/, a portable folder to zip and hand out.
// The Flash plugin is not in this repo: put pepflashplayer64_32_0_0_371.dll in client/plugins/
// before packaging, and it is copied next to FarmVille.exe.

const { packager } = require("@electron/packager");
const fs = require("fs");
const path = require("path");

(async () => {
    const [outDir] = await packager({
        dir: __dirname,
        out: path.join(__dirname, "dist"),
        name: "FarmVille",
        executableName: "FarmVille",
        platform: "win32",
        arch: "x64",
        overwrite: true,
        asar: true,
        icon: path.join(__dirname, "..", "build", "icon.ico"),
        ignore: [/^\/dist($|\/)/, /^\/plugins($|\/)/, /^\/config\.json$/, /^\/build\.js$/],
    });

    const pluginsSrc = path.join(__dirname, "plugins");
    const pluginsDst = path.join(outDir, "plugins");
    fs.mkdirSync(pluginsDst, { recursive: true });
    const dlls = fs.existsSync(pluginsSrc) ? fs.readdirSync(pluginsSrc).filter((f) => /\.dll$/i.test(f)) : [];
    for (const dll of dlls) fs.copyFileSync(path.join(pluginsSrc, dll), path.join(pluginsDst, dll));

    fs.writeFileSync(path.join(outDir, "config.json"),
        JSON.stringify({ serverUrl: "http://127.0.0.1:5500" }, null, 4) + "\n");

    console.log(`Packaged to ${outDir}`);
    if (!dlls.length) console.warn("WARNING: no Flash plugin in client/plugins/ - the client will not run the game.");
})().catch((e) => {
    console.error(e);
    process.exit(1);
});
