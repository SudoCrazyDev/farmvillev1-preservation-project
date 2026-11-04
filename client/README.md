# FarmVille desktop client

A standalone window that plays FarmVille with Flash Player built in, so players need neither an
old browser nor a Flash install. Built on Electron 11.5.0, the last Electron that can load the
Pepper (PPAPI) Flash plugin.

## Security

Electron 11 ships an old, unpatched Chromium. The client is locked to the game server set in
`config.json`: it cannot navigate anywhere else, pop-ups are blocked, and every request to any
other host is cancelled. Only point it at a server you trust.

## Building

You need Node.js and the Flash Player 32.0.0.371 PPAPI plugin, `pepflashplayer64_32_0_0_371.dll`
(from the `flashplayer32_0r0_371_winpep.exe` installer in Adobe's Flash Player archive; see
[FLASH.md](../FLASH.md)). The plugin is not in this repository.

1. Copy `pepflashplayer64_32_0_0_371.dll` into `client/plugins/`.
2. Build:

   ```bash
   cd client
   npm install
   npm run package
   ```

3. Zip `client/dist/FarmVille-win32-x64/` and hand it out.

Note: Adobe's Flash Player license does not allow redistributing the plugin.

## Playing

1. Extract the zip and run `FarmVille.exe`.
2. To use a server other than `http://127.0.0.1:5500`, edit `serverUrl` in `config.json` next to
   `FarmVille.exe`. The server's `--public-url` (`PUBLIC_URL` in docker-compose.yml) must be the
   same address.

Keys: F5 reload, F11 fullscreen, F12 developer tools.
