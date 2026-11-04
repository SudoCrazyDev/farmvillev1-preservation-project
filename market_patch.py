# Market "Sort By" menu: adds a "Can Buy First" option to the seed, tree and building tabs.
#
# client ref.: src/Classes/MarketConfigSettings.as (getSortOptions), src/Classes/MarketWindow.as (refreshMenus),
# src/Managers/FarmGameSettingsManager.as (iinit, getItemSortFunction, sortByRequiredLevel)
# The menu is not built into the client: MarketWindow lists whatever <categorization><type><sortTypes> in
# MarketData.xml names, and sorts with the function FarmGameSettingsManager registered for that "by" key.
# "level" (sortByRequiredLevel) is one of those keys but no tab lists it. Sorted ascending it puts every item
# the player has unlocked ahead of the locked ones, lowest level first.
# The menu label is the locale string Dialogs/sort_<by>_<dir>, and en_US.swf has no sort_level_asc, so the
# entry is added there too (see _patch_locale_swf).
#
# Both patched files are written once into CACHE_DIR and served in place of the originals (see server.py).
import os
import re
import struct
import zlib

from bundle import XML_DIR, CACHE_DIR

SORT_BY = "level"
SORT_DIR = "asc"
SORT_LABEL = "Unlocked First"
SORT_TYPES = ("seed", "tree", "building")
# The Sort By menu shows at most 12 rows (it does not scroll), and the seed tab already fills them
# ("world" is listed too but only shown with more than one world). Super Crops makes room: the
# super-crop feature is not served, so that sort is a no-op here.
SORT_REMOVE = {"seed": ('<sort by="superCrop" dir="desc"/>',)}
# Bump when the output changes: the patched files are cached on the data volume and kept across rebuilds.
PATCH_VERSION = 2

MARKET_DATA = os.path.join(XML_DIR, "gz/v855098/MarketData.xml.gz")
LOCALE_SWF = os.path.join(XML_DIR, "gz/v855098/en_US.swf")
PATCHED_MARKET_DATA = os.path.join(CACHE_DIR, f"gz_v855098_MarketData_sort_p{PATCH_VERSION}.xml.gz")
PATCHED_LOCALE_SWF = os.path.join(CACHE_DIR, f"gz_v855098_en_US_sort_p{PATCH_VERSION}.swf")

# MarketData.xml.gz is a zlib stream, not gzip, like the other files in xml/gz.
def _patch_market_data() -> None:
    xml = zlib.decompress(open(MARKET_DATA, 'rb').read()).decode('utf-8')
    sort_tag = f'<sort by="{SORT_BY}" dir="{SORT_DIR}"/>'
    added = 0
    for type_name in SORT_TYPES:
        # The default entry comes first in each list; the new one goes right after it.
        rx = re.compile(r'(<type name="' + re.escape(type_name) + r'"[^>]*>\s*<sortTypes>\s*<sort by="default" dir="asc"/>)')
        xml, n = rx.subn(lambda m: m.group(1) + "\n                " + sort_tag, xml, count=1)
        added += n
        for tag in SORT_REMOVE.get(type_name, ()):
            # only inside this tab's <sortTypes> list
            rx = re.compile(r'(<type name="' + re.escape(type_name) + r'"[^>]*>\s*<sortTypes>(?:(?!</sortTypes>).)*?)\s*'
                            + re.escape(tag), re.S)
            xml = rx.sub(lambda m: m.group(1), xml, count=1)
    _write(PATCHED_MARKET_DATA, zlib.compress(xml.encode('utf-8')))
    print(f" * Market sort: '{SORT_LABEL}' added to {added} market tabs")

# --- en_US.swf ---------------------------------------------------------------------------------------
# The locale is one class, Locale_en_US, whose constructor builds every string as a single nested object
# literal: pushstring bundle, (pushstring key, pushstring 'original', pushstring text, newobject 1)...,
# newobject <entries>, ..., newobject <bundles>, initproperty text. The code is straight-line (no branches,
# no exception handlers), so an entry can be spliced into the Dialogs bundle without fixing any offsets:
# add the two new strings to the constant pool, insert the entry after the bundle's key, bump the bundle's
# newobject count and the method's max_stack.

def _u30(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7f; v >>= 7
        if v: out.append(b | 0x80)
        else: out.append(b); return bytes(out)

class _R:
    def __init__(s, b, p=0): s.b = b; s.p = p
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def u30(s):
        r = 0; sh = 0
        while True:
            c = s.b[s.p]; s.p += 1; r |= (c & 0x7f) << sh; sh += 7
            if not c & 0x80 or sh >= 35: return r
    def skip(s, n): s.p += n

def _swf_tags(swf: bytes):
    nbits = swf[8] >> 3
    p = 8 + (5 + 4 * nbits + 7) // 8 + 4
    while p < len(swf):
        h = struct.unpack_from('<H', swf, p)[0]; code = h >> 6; ln = h & 0x3f; q = p + 2
        if ln == 0x3f: ln = struct.unpack_from('<I', swf, q)[0]; q += 4
        yield code, p, q, ln
        p = q + ln

def _parse_abc(abc: bytes) -> dict:
    r = _R(abc, 4)
    n = r.u30()
    for _ in range(max(0, n - 1)): r.u30()                 # ints (s32 has the same varint shape)
    n = r.u30()
    for _ in range(max(0, n - 1)): r.u30()                 # uints
    n = r.u30(); r.skip(8 * max(0, n - 1))                 # doubles
    str_count_at = r.p; n_strs = r.u30(); strs_at = r.p; strs = [None]
    for _ in range(max(0, n_strs - 1)):
        ln = r.u30(); strs.append(abc[r.p:r.p + ln]); r.skip(ln)
    strs_end = r.p
    for _ in range(max(0, r.u30() - 1)): r.u8(); r.u30()    # namespaces
    for _ in range(max(0, r.u30() - 1)):                    # namespace sets
        for _ in range(r.u30()): r.u30()
    for _ in range(max(0, r.u30() - 1)):                    # multinames
        k = r.u8()
        if k in (7, 0xD, 9, 0xE): r.u30(); r.u30()
        elif k in (0xF, 0x10, 0x1B, 0x1C): r.u30()
        elif k in (0x11, 0x12): pass
        elif k == 0x1D:
            r.u30()
            for _ in range(r.u30()): r.u30()
        else: raise ValueError(f"multiname kind {k}")
    n_methods = r.u30()
    for _ in range(n_methods):
        pc = r.u30(); r.u30()
        for _ in range(pc): r.u30()
        r.u30(); fl = r.u8()
        if fl & 8:
            for _ in range(r.u30()): r.u30(); r.u8()
        if fl & 0x80:
            for _ in range(pc): r.u30()
    for _ in range(r.u30()):                                # metadata
        r.u30()
        for _ in range(r.u30()): r.u30(); r.u30()
    def traits():
        for _ in range(r.u30()):
            r.u30(); k = r.u8(); kind = k & 0xf
            if kind in (0, 6):
                r.u30(); r.u30()
                if r.u30(): r.u8()
            else: r.u30(); r.u30()
            if k & 0x40:
                for _ in range(r.u30()): r.u30()
    n_classes = r.u30()
    iinits = []
    for _ in range(n_classes):
        r.u30(); r.u30(); fl = r.u8()
        if fl & 8: r.u30()
        for _ in range(r.u30()): r.u30()
        iinits.append(r.u30()); traits()
    for _ in range(n_classes): r.u30(); traits()
    for _ in range(r.u30()): r.u30(); traits()                # scripts
    bodies = {}
    for _ in range(r.u30()):
        start = r.p; m = r.u30(); max_stack_at = r.p; max_stack = r.u30()
        r.u30(); r.u30(); r.u30()
        code_len_at = r.p; code_len = r.u30(); code_at = r.p; r.skip(code_len)
        n_exc = r.u30()
        for _ in range(n_exc): r.u30(); r.u30(); r.u30(); r.u30(); r.u30()
        traits()
        bodies[m] = dict(start=start, max_stack_at=max_stack_at, max_stack=max_stack, code_len_at=code_len_at,
                         code_at=code_at, code_len=code_len, n_exc=n_exc, end=r.p)
    return dict(str_count_at=str_count_at, n_strs=n_strs, strs_at=strs_at, strs_end=strs_end, strs=strs,
                iinits=iinits, bodies=bodies)

# client ref.: src/Classes/LocalizerSWF.as (getString, getStringFromBucket, hashStringAdd)
# A bundle is not a flat key map: it is split into "length" buckets ("0".."15" plus length: "16"), and a key
# lives in bucket (sum of its char codes) & (length - 1).
def _bucket_of(key: bytes, n_buckets: int) -> int:
    units = key.decode('utf-8').encode('utf-16-le')              # charCodeAt counts UTF-16 code units
    return sum(struct.unpack(f'<{len(units) // 2}H', units)) & (n_buckets - 1)

# Walks the locale constructor and returns (offset just after the bucket-name pushstring, offset and count of
# the bucket's newobject) for the bucket of the named top-level bundle that `key` belongs in.
def _find_bundle(code: bytes, strs: list, bundle: bytes, key: bytes):
    r = _R(code)
    # per stack slot: ('s', string index, end offset) or ('o', newobject offset, count, pairs).
    # pairs (string key index, key end offset, value slot) are kept only for bucket containers (the objects
    # with a "length" key) and the top-level object, the only ones looked into.
    stack = []
    length_idx = strs.index(b'length')
    while r.p < len(code):
        at = r.p; op = r.u8()
        if op == 0x2c:                                          # pushstring
            stack.append(('s', r.u30(), r.p))
        elif op == 0x55:                                        # newobject
            n = r.u30()
            if n: popped = stack[-2 * n:]; del stack[-2 * n:]
            else: popped = []
            top_level = len(stack) == 1                         # [this] below it: the object of all bundles
            pairs = None
            if top_level or any(popped[i][0] == 's' and popped[i][1] == length_idx for i in range(0, len(popped), 2)):
                pairs = [(popped[i][1], popped[i][2], popped[i + 1]) for i in range(0, len(popped), 2)
                         if popped[i][0] == 's']
            stack.append(('o', at, n, pairs))
            if top_level:
                for key_idx, _, val in pairs:
                    if strs[key_idx] == bundle and val[0] == 'o' and val[3]:
                        buckets = {strs[k]: (end, v) for k, end, v in val[3]}
                        n_buckets = int(strs[buckets[b'length'][1][1]])
                        end, bucket = buckets[str(_bucket_of(key, n_buckets)).encode()]
                        return end, bucket[1], bucket[2]
        elif op == 0xd0: stack.append(('this',))               # getlocal0
        elif op == 0x30: stack.pop()                            # pushscope
        elif op == 0x68: r.u30(); stack.pop(); stack.pop()      # initproperty
        elif op == 0x49: r.u30(); stack.pop()                   # constructsuper 0
        elif op == 0x47: break                                  # returnvoid
        else: raise ValueError(f"unexpected opcode 0x{op:02x} at {at}")
    raise ValueError("bundle not found")

def _patch_locale_swf() -> None:
    raw = open(LOCALE_SWF, 'rb').read()
    swf = raw[:8] + zlib.decompress(raw[8:]) if raw[:3] == b'CWS' else raw
    key = f"sort_{SORT_BY}_{SORT_DIR}".encode('utf-8')
    for code, tag_at, body_at, ln in _swf_tags(swf):
        if code != 82: continue                                 # DoABC
        tag = swf[body_at:body_at + ln]
        abc_at = tag.index(b'\0', 4) + 1
        abc = tag[abc_at:]
        a = _parse_abc(abc)
        if key in a["strs"]:
            print(" * Market sort: locale already has the label")
            break
        body = a["bodies"][a["iinits"][0]]
        assert body["n_exc"] == 0
        code_b = abc[body["code_at"]:body["code_at"] + body["code_len"]]
        original_idx = a["strs"].index(b'original')
        insert_at, obj_at, count = _find_bundle(code_b, a["strs"], b'Dialogs', key)
        key_idx, label_idx = a["n_strs"], a["n_strs"] + 1
        entry = (b'\x2c' + _u30(key_idx) + b'\x2c' + _u30(original_idx) + b'\x2c' + _u30(label_idx) + b'\x55' + _u30(1))
        old_newobject = b'\x55' + _u30(count)
        assert code_b[obj_at:obj_at + len(old_newobject)] == old_newobject
        new_code = (code_b[:insert_at] + entry + code_b[insert_at:obj_at] + b'\x55' + _u30(count + 1)
                    + code_b[obj_at + len(old_newobject):])
        label = SORT_LABEL.encode('utf-8')
        new_abc = (abc[:a["str_count_at"]] + _u30(a["n_strs"] + 2) + abc[a["strs_at"]:a["strs_end"]]
                   + _u30(len(key)) + key + _u30(len(label)) + label
                   + abc[a["strs_end"]:body["max_stack_at"]] + _u30(body["max_stack"] + 2)
                   + abc[body["max_stack_at"] + len(_u30(body["max_stack"])):body["code_len_at"]]
                   + _u30(len(new_code)) + new_code + abc[body["code_at"] + body["code_len"]:])
        new_tag = tag[:abc_at] + new_abc
        new_swf = (swf[:tag_at] + struct.pack('<HI', (82 << 6) | 0x3f, len(new_tag)) + new_tag
                   + swf[body_at + ln:])
        new_swf = new_swf[:4] + struct.pack('<I', len(new_swf)) + new_swf[8:]
        _write(PATCHED_LOCALE_SWF, b'CWS' + new_swf[3:8] + zlib.compress(new_swf[8:]))
        print(f" * Market sort: locale label {key.decode()} = '{SORT_LABEL}' added")
        return
    _write(PATCHED_LOCALE_SWF, raw)

def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)

def build_patched_files() -> None:
    if not os.path.exists(PATCHED_MARKET_DATA):
        print(" * Writing patched MarketData.xml.gz...")
        _patch_market_data()
    if not os.path.exists(PATCHED_LOCALE_SWF):
        print(" * Writing patched en_US.swf...")
        _patch_locale_swf()
