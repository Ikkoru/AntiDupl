"""Checks the core's result sorting through AntiDupl.dll.

Usage: python sort_check.py DLL_DIR SEARCH_DIR USER_DIR

SEARCH_DIR needs pairs whose sort keys tie (e.g. files with byte-identical
copies in a second folder under the same names) and x_p1.jpg, x_p2.jpg,
x_p10.jpg, each with a copy. USER_DIR: a scratch user folder.

1. Sides: a sort that is not one of the vertical table's BySorted* types
   must not swap any pair's first and second image.
2. History: every sort type, both directions, gives the same rows (order
   and sides) whatever sort came before (for non-BySorted types: whatever
   non-BySorted sort came before, since BySorted sorts set the sides).
3. Natural order: sorting by first name puts x_p2 before x_p10.
4. Sides after the search: every pair has the lesser path first (numbers
   by value).
5. Ties: sorting by one image's directory orders rows with the same
   directory by the other image's directory (in the same direction), then
   by first path.
Prints PASS/FAIL lines; ASCII only.
"""
import ctypes
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_search as cs  # noqa: E402

SORTED = range(1, 13)
OTHER = [0] + list(range(13, 43))
failures = 0


def natural_key(path):
    """Upper-cased path with runs of digits compared by value."""
    parts = re.split(r"(\d+)", path.upper())
    return [int(part) if i % 2 else part for i, part in enumerate(parts)]


def check(ok, what):
    global failures
    if not ok:
        failures += 1
    print(("PASS " if ok else "FAIL ") + what)


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
            rel = lambda q: os.path.relpath(q, p)
            return [(rel(r.first.path), rel(r.second.path)) for r in results[:count.value]]

        def sort(t, inc):
            assert core.adResultSort(h, t, inc) == 0
            return rows()

        print(f"{len(rows())} results")

        # 4. Sides after the search (checked first, before any sort)
        wrong = [r for r in rows() if natural_key(r[1]) < natural_key(r[0])]
        check(not wrong, f"after the search every pair has the lesser path first ({len(wrong)} not)")
        # 5. Ties: the other image's same property, then first path.
        def dir_key(row, side):
            return natural_key(os.path.dirname(row[side]))

        for t, side, other in ((15, 0, 1), (27, 1, 0)):
            for inc in (1, 0):
                by_dir = sort(t, inc)
                pairs = [(a, b) for a, b in zip(by_dir, by_dir[1:]) if dir_key(a, side) == dir_key(b, side)]
                other_dir = all((dir_key(a, other) <= dir_key(b, other)) if inc else
                                (dir_key(a, other) >= dir_key(b, other)) for a, b in pairs)
                first_path = all(natural_key(a[0]) <= natural_key(b[0]) for a, b in pairs
                                 if dir_key(a, other) == dir_key(b, other))
                check(other_dir and first_path,
                      f"sort {t} inc={inc}: rows with the same directory go by the other image's"
                      f" directory (same direction), then first path")

        # 1. Sides
        for t in OTHER:
            for inc in (1, 0):
                before = set(rows())
                after = set(sort(t, inc))
                check(before == after, f"sort {t} inc={inc} keeps every pair's sides")
                if before != after:
                    print(f"     {len(before - after)} pairs changed sides")

        # 2. History
        # A BySorted* sort decides the sides on purpose, so the other types
        # are only checked after other types (the horizontal table's sorts).
        priors_all = [(38, 0), (15, 1), (27, 0), (3, 1), (2, 0), (40, 1)]
        priors_other = [(38, 0), (15, 1), (27, 0), (14, 1), (40, 1), (39, 0)]
        for t in list(SORTED) + OTHER:
            priors = priors_all if t in SORTED else priors_other
            for inc in (1, 0):
                outcomes = []
                for prior in priors:
                    sort(*prior)
                    sort(15, 0)
                    sort(*prior)
                    outcomes.append(sort(t, inc))
                same = all(o == outcomes[0] for o in outcomes)
                check(same, f"sort {t} inc={inc} same rows after {len(priors)} different earlier sorts")

        # 3. Natural order
        order = [r[0] for r in sort(14, 1) if os.path.basename(r[0]).startswith("x_p")]
        names = []
        for n in order:
            b = os.path.basename(n)
            if b not in names:
                names.append(b)
        check(names == ["x_p1.jpg", "x_p2.jpg", "x_p10.jpg"], f"first-name order {names}")
    finally:
        core.adRelease(h)
    print("ALL PASS" if failures == 0 else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
