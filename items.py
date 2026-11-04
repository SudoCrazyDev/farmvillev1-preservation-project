import os
import zlib
import pyamf
from pyamf.amf3 import Decoder, TYPE_OBJECT
import json

from bundle import XML_DIR, CACHE_DIR

ITEMS_AMF = os.path.join(XML_DIR, "gz/v855038/items_opt.amf")
CACHE_ITEMS_JSON = os.path.join(CACHE_DIR, "gz_v855038_items_opt.json")

_cached_items: dict = None

def _cache_items() -> None:
    # Read .amf file
    obj:bytes = open(ITEMS_AMF, 'rb').read()

    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Assert that it's an object
    assert obj_decomp[:1] == TYPE_OBJECT

    # Decode Object
    dec:Decoder = pyamf.get_decoder(pyamf.AMF3, obj_decomp)
    arr:dict = dec.readElement()

    # Save to cache as JSON
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    json.dump(arr, open(CACHE_ITEMS_JSON, 'w'))

def load_items() -> None:
    # If cache doesn't exist, create it
    if not os.path.exists(CACHE_ITEMS_JSON):
        print(" * No items cache found. Caching items...")
        _cache_items()

    # Load cache
    print(" * Loading items cache...")
    global _cached_items
    _cached_items = json.load(open(CACHE_ITEMS_JSON, 'r'))

    _apply_fast_grow()
    _write_patched_items_amf()

# Early-game seeds grow faster, so a new player is not left waiting hours on their first crops.
# client ref.: src/Classes/HarvestableResource.as (getGrowTime)
# The client times a crop as growTime (in-game days) * inGameDaySeconds (82800) * growMultiplier, reading
# growTime straight off the item in items_opt.amf. growMultiplier in gameSettingsCMS.xml would scale every
# crop, tree and animal alike, so instead growTime itself is cut on seeds up to FAST_GROW_MAX_LEVEL, and the
# client is served the patched items_opt.amf (see server.py). Wither time follows on its own: the client
# withers a crop at growTime * witherMultiplier.
FAST_GROW_MAX_LEVEL = 10
FAST_GROW_FACTOR = 0.05  # 20x faster

PATCHED_ITEMS_AMF = os.path.join(
    CACHE_DIR, f"gz_v855038_items_opt_fastgrow_L{FAST_GROW_MAX_LEVEL}_x{FAST_GROW_FACTOR}.amf")

def _required_level(item: dict) -> int:
    try:
        return int(item.get("requiredLevel", 1))
    except (TypeError, ValueError):
        return None

def _apply_fast_grow() -> None:
    count = 0
    for item in get_items():
        if item.get("type") != "seed" or "growTime" not in item:
            continue
        level = _required_level(item)
        if level is None or level > FAST_GROW_MAX_LEVEL:
            continue
        # growTime stays a string, as in the original data ("0.174")
        item["growTime"] = f"{float(item['growTime']) * FAST_GROW_FACTOR:.6g}"
        count += 1
    print(f" * Fast grow: {count} seeds up to level {FAST_GROW_MAX_LEVEL} grow {1 / FAST_GROW_FACTOR:g}x faster")

def _write_patched_items_amf() -> None:
    # Re-encoding the JSON cache with pyamf reproduces the original items_opt.amf byte for byte (checked
    # against v855038), so the only difference in the served file is the patched growTime values.
    if os.path.exists(PATCHED_ITEMS_AMF):
        return
    print(" * Writing patched items_opt.amf...")
    enc = pyamf.get_encoder(pyamf.AMF3)
    enc.writeElement(_cached_items)
    tmp_path = PATCHED_ITEMS_AMF + ".tmp"
    with open(tmp_path, 'wb') as f:
        f.write(zlib.compress(enc.stream.getvalue()))
    os.replace(tmp_path, PATCHED_ITEMS_AMF)

def get_items() -> list:
    global _cached_items
    return _cached_items["settings"]["items"]["item"]

def get_item_by_code(code:str) -> dict:
    for item in get_items():
        if item["code"] == code:
            return item
    return None

def get_item_by_name(name:str) -> dict:
    for item in get_items():
        if item["name"] == name:
            return item
    return None

def get_item_by_code(code:str) -> dict:
    for item in get_items():
        if item["code"] == code:
            return item
    return None

def item_has_feature(item_data: dict, feature_name: str) -> bool:
    # A single-feature item decodes to a plain dict instead of a one-element list.
    features = (item_data.get("features") or {}).get("feature")
    if features is None:
        return False
    if isinstance(features, dict):
        features = [features]
    return any(feature.get("name") == feature_name for feature in features)
