"""Checks the core's result sorting through AntiDupl.dll.

Usage: python sort_check.py DLL_DIR SEARCH_DIR USER_DIR

SEARCH_DIR needs pairs whose sort keys tie (e.g. files with byte-identical
copies in a second folder under the same names) and x_p1.jpg, x_p2.jpg,
x_p10.jpg, each with a copy. USER_DIR: a scratch user folder.

Sort types are AntiDupl's adSortType values. An "image sort" looks at one
image of each pair: 1-12 (vertical table) and 13-24 the first image, 25-36
the second; the others (0, 37-42) are "pair sorts" (type, difference ...).

1. After the search every pair has the lesser path first.
2. Pair sorts keep every pair's sides.
3. Image sorts put in the sorted image's place the image that comes first
   in the sort's direction by that property, on a tie by path.
4. Row order: image sorts go by the sorted image's property, the other
   image's property, the sorted image's path, the other image's path, all
   in the sort's direction; pair sorts by their key in the sort's direction,
   then first path and second path ascending.
5. History: an image sort gives the same rows whatever sort came before; a
   pair sort, whatever pair sort came before (image sorts set the sides).
6. Natural order: sorting by first name puts x_p2 before x_p10.
Prints PASS/FAIL lines; ASCII only.
"""
import ctypes
import os
import re
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_search as cs  # noqa: E402

IMAGE_SORTS = range(1, 37)
PAIR_SORTS = [0] + list(range(37, 43))
failures = 0


def natural_key(text):
    """Upper-cased text with runs of digits compared by value."""
    parts = re.split(r"(\d+)", text.upper())
    return [int(part) if i % 2 else part for i, part in enumerate(parts)]


def sorted_image(t):
    return 1 if 1 <= t <= 24 else 2 if 25 <= t <= 36 else 0


def image_sort_type(t):
    return t - 24 if t >= 25 else t - 12 if t >= 13 else t


def property_key(img, s):
    """The value an AD_SORT_BY_SORTED_* type compares, as AntiDupl does."""
    return {
        1: lambda: natural_key(img["path"]),
        2: lambda: natural_key(os.path.basename(img["path"])),
        3: lambda: natural_key(os.path.dirname(img["path"])),
        4: lambda: img["size"],
        5: lambda: img["time"],
        6: lambda: img["type"],
        7: lambda: img["width"],
        8: lambda: img["height"],
        9: lambda: img["width"] * img["height"],
        10: lambda: Fraction(img["width"], img["height"]),
        11: lambda: img["blockiness"],
        12: lambda: img["blurring"],
    }[s]()


def cmp(a, b):
    return (a > b) - (a < b)


def check(ok, what):
    global failures
    if not ok:
        failures += 1
    print(("PASS " if ok else "FAIL ") + what)


def image(info):
    return {"path": info.path, "size": info.size, "time": info.time, "type": info.type,
            "width": info.width, "height": info.height, "blockiness": info.blockiness,
            "blurring": info.blurring}


def main():
    dll_dir, search_dir, user_dir = sys.argv[1:4]
    os.makedirs(user_dir, exist_ok=True)
    os.add_dll_directory(os.path.abspath(dll_dir))
    core = ctypes.CDLL(os.path.join(os.path.abspath(dll_dir), "AntiDupl.dll"))
    core.adCreateW.restype = ctypes.c_void_p
    core.adCreateW.argtypes = [ctypes.c_wchar_p]
    for name in ("adRelease", "adSearch"):
        getattr(core, name).argtypes = [ctypes.c_void_p]
    core.adOptionsGet.argtypes = core.adOptionsSet.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p]
    core.adPathWithSubFolderSetW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    core.adResultSort.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32]
    core.adResultGetW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_size_t)]

    h = core.adCreateW(os.path.abspath(user_dir))
    try:
        cmp_ = cs.CompareOptions()
        core.adOptionsGet(h, cs.AD_OPTIONS_COMPARE, ctypes.byref(cmp_))
        cmp_.thresholdDifference = 5
        cmp_.compareInsideOneFolder = 1
        cmp_.checkOnEquality = 1
        assert core.adOptionsSet(h, cs.AD_OPTIONS_COMPARE, ctypes.byref(cmp_)) == 0
        adv = cs.AdvancedOptions()
        core.adOptionsGet(h, cs.AD_OPTIONS_ADVANCED, ctypes.byref(adv))
        adv.mistakeDataBase = 0
        assert core.adOptionsSet(h, cs.AD_OPTIONS_ADVANCED, ctypes.byref(adv)) == 0
        buf = (ctypes.c_wchar * (cs.MAX_PATH_EX + 1))()
        p = os.path.abspath(search_dir)
        buf[:len(p)] = p
        buf[cs.MAX_PATH_EX] = "\x01"
        assert core.adPathWithSubFolderSetW(h, cs.AD_PATH_SEARCH, ctypes.byref(buf), 1) == 0
        assert core.adSearch(h) == 0

        def rows():
            start, count = ctypes.c_size_t(0), ctypes.c_size_t(1024)
            results = (cs.ResultW * 1024)()
            core.adResultGetW(h, ctypes.byref(start), results, ctypes.byref(count))
            return [{"first": image(r.first), "second": image(r.second), "difference": r.difference}
                    for r in results[:count.value] if r.type == cs.AD_RESULT_DUPL_IMAGE_PAIR]

        def sides(rs):
            return [(r["first"]["path"], r["second"]["path"]) for r in rs]

        def sort(t, inc):
            assert core.adResultSort(h, t, inc) == 0
            return rows()

        def sorted_other(r, t):
            return (r["first"], r["second"]) if sorted_image(t) == 1 else (r["second"], r["first"])

        def row_key_cmp(a, b, t, inc):
            """Compares two rows by the documented order; returns -1/0/1."""
            if sorted_image(t):
                s = image_sort_type(t)
                (xa, ya), (xb, yb) = sorted_other(a, t), sorted_other(b, t)
                for ka, kb in ((property_key(xa, s), property_key(xb, s)),
                               (property_key(ya, s), property_key(yb, s)),
                               (natural_key(xa["path"]), natural_key(xb["path"])),
                               (natural_key(ya["path"]), natural_key(yb["path"]))):
                    c = cmp(ka, kb)
                    if c:
                        return c if inc else -c
                return 0
            if t == 38:
                c = cmp(a["difference"], b["difference"])
                if c:
                    return c if inc else -c
            for ka, kb in ((natural_key(a["first"]["path"]), natural_key(b["first"]["path"])),
                           (natural_key(a["second"]["path"]), natural_key(b["second"]["path"]))):
                c = cmp(ka, kb)
                if c:
                    return c
            return 0

        print(f"{len(rows())} pairs")

        # 1. After the search
        wrong = [r for r in rows() if natural_key(r["second"]["path"]) < natural_key(r["first"]["path"])]
        check(not wrong, f"after the search every pair has the lesser path first ({len(wrong)} not)")

        # 2. Pair sorts keep the sides
        sort(15, 1)
        for t in PAIR_SORTS:
            for inc in (1, 0):
                before = set(sides(rows()))
                after = set(sides(sort(t, inc)))
                check(before == after, f"pair sort {t} inc={inc} keeps every pair's sides")

        for t in IMAGE_SORTS:
            s = image_sort_type(t)
            for inc in (1, 0):
                rs = sort(t, inc)
                # 3. Orientation
                bad = 0
                for r in rs:
                    x, y = sorted_other(r, t)
                    c = cmp(property_key(x, s), property_key(y, s)) or \
                        cmp(natural_key(x["path"]), natural_key(y["path"]))
                    if (c if inc else -c) > 0:
                        bad += 1
                check(bad == 0, f"image sort {t} inc={inc}: the sorted place holds the image that comes"
                                f" first ({bad} pairs not)")
                # 4. Row order
                out = sum(row_key_cmp(a, b, t, inc) > 0 for a, b in zip(rs, rs[1:]))
                check(out == 0, f"image sort {t} inc={inc}: row order ({out} rows out of order)")
        for t in PAIR_SORTS:
            for inc in (1, 0):
                rs = sort(t, inc)
                out = sum(row_key_cmp(a, b, t, inc) > 0 for a, b in zip(rs, rs[1:]))
                check(out == 0, f"pair sort {t} inc={inc}: row order ({out} rows out of order)")

        # 5. History
        priors_all = [(38, 0), (15, 1), (27, 0), (3, 1), (2, 0), (40, 1)]
        priors_pair = [(38, 0), (40, 1), (39, 0), (0, 1), (42, 0), (41, 1)]
        for t in list(IMAGE_SORTS) + PAIR_SORTS:
            priors = priors_all if sorted_image(t) else priors_pair
            for inc in (1, 0):
                outcomes = []
                for prior in priors:
                    sort(*prior)
                    sort(40 if not sorted_image(t) else 15, 0)
                    sort(*prior)
                    outcomes.append(sides(sort(t, inc)))
                same = all(o == outcomes[0] for o in outcomes)
                check(same, f"sort {t} inc={inc} same rows after {len(priors)} different earlier sorts")

        # 6. Natural order
        names = []
        for first, _ in sides(sort(14, 1)):
            b = os.path.basename(first)
            if b.startswith("x_p") and b not in names:
                names.append(b)
        check(names == ["x_p1.jpg", "x_p2.jpg", "x_p10.jpg"], f"first-name order {names}")
    finally:
        core.adRelease(h)
    print("ALL PASS" if failures == 0 else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
