#!/bin/sh
set -e

# Everything the server writes lives in the /data volume. The server reads it through
# symlinks at the paths bundle.py expects (next to server.py).
mkdir -p /data/saves /data/cache
for d in saves cache assets; do
    ln -sfn "/data/$d" "/app/$d"
done
ln -sfn /data/unhandled.log /app/unhandled.log

# First start: download and extract the WARC assets (~17 GB) straight into /data.
# assets.py removes and renames assets/ and tmp/, so they must be plain folders inside the
# volume (not mount points or symlinks), and on the same filesystem for the final rename.
python -c "
import bundle
bundle.ASSETS_DIR = '/data/assets'
bundle.TMP_DIR = '/data/tmp'
import assets
assets.check_assets()
"

exec python server.py --host 0.0.0.0 --port "$PORT" --public-url "$PUBLIC_URL" "$@"
