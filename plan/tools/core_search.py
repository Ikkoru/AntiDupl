"""Run AntiDupl's core (AntiDupl.dll) on a folder and print the duplicate pairs.

Usage:
    python core_search.py DLL_DIR USER_DIR SEARCH_DIR [--size N] [--threshold N]
                          [--turbo 0|1] [--algorithm 0|1] [--runs N] [--use-db]

DLL_DIR     folder holding AntiDupl.dll (e.g. bin\\Release of a build)
USER_DIR    the engine's user folder (settings, image database); created if
            missing. Never point it at the real %LOCALAPPDATA%\\AntiDupl.NET\\user.
SEARCH_DIR  folder to search (subfolders included), with compare-inside-one-
            folder on.
--size      reduced image size (AntiDupl's default 32; the user's 128)
--threshold threshold difference in % (default 1)
--turbo     use libjpeg-turbo (default 1)
--algorithm 0 = mean square, 1 = SSIM (default 1)
--runs      repeat the search N times in one engine (float-noise checks)
--use-db    like the GUI's "use database of image": load the image database
            from USER_DIR\\images\\<size>x<size> before each search and save it
            after, so a later run (another build, too) starts from the cache

Prints one line per pair: difference with full precision, the 2-decimal value
the UI shows, and the two file names. Output is ASCII-only.
"""
import argparse
import ctypes
import os
import sys

MAX_PATH_EX = 32768
MAX_EXIF_SIZE = 260
AD_OPTIONS_COMPARE, AD_OPTIONS_ADVANCED = 1, 3
AD_PATH_SEARCH = 0
AD_FILE_IMAGE_DATA_BASE = 3
AD_SORT_BY_DIFFERENCE = 38
AD_RESULT_DUPL_IMAGE_PAIR = 2


class CompareOptions(ctypes.Structure):
    _fields_ = [("checkOnEquality", ctypes.c_int32), ("transformedImage", ctypes.c_int32),
                ("sizeControl", ctypes.c_int32), ("typeControl", ctypes.c_int32),
                ("ratioControl", ctypes.c_int32), ("thresholdDifference", ctypes.c_int32),
                ("minimalImageSize", ctypes.c_int32), ("maximalImageSize", ctypes.c_int32),
                ("compareInsideOneFolder", ctypes.c_int32), ("compareInsideOneSearchPath", ctypes.c_int32),
                ("algorithmComparing", ctypes.c_int32)]


class AdvancedOptions(ctypes.Structure):
    _fields_ = [("deleteToRecycleBin", ctypes.c_int32), ("mistakeDataBase", ctypes.c_int32),
                ("ratioResolution", ctypes.c_int32), ("compareThreadCount", ctypes.c_int32),
                ("collectThreadCount", ctypes.c_int32), ("reducedImageSize", ctypes.c_int32),
                ("undoQueueSize", ctypes.c_int32), ("resultCountMax", ctypes.c_int32),
                ("ignoreFrameWidth", ctypes.c_int32), ("useLibJpegTurbo", ctypes.c_int32)]


class ExifInfoW(ctypes.Structure):
    _fields_ = [("isEmpty", ctypes.c_int32)] + [
        (n, ctypes.c_wchar * MAX_EXIF_SIZE) for n in
        ("imageDescription", "equipMake", "equipModel", "softwareUsed", "dateTime", "artist", "userComment")]


class ImageInfoW(ctypes.Structure):
    _fields_ = [("id", ctypes.c_size_t), ("path", ctypes.c_wchar * MAX_PATH_EX),
                ("size", ctypes.c_uint64), ("time", ctypes.c_uint64), ("hash", ctypes.c_uint32),
                ("type", ctypes.c_int32), ("width", ctypes.c_uint32), ("height", ctypes.c_uint32),
                ("blockiness", ctypes.c_double), ("blurring", ctypes.c_double), ("exifInfo", ExifInfoW)]


class ResultW(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int32), ("first", ImageInfoW), ("second", ImageInfoW),
                ("defect", ctypes.c_int32), ("difference", ctypes.c_double), ("transform", ctypes.c_int32),
                ("group", ctypes.c_size_t), ("groupSize", ctypes.c_size_t), ("hint", ctypes.c_int32)]


def ascii(s):
    return s.encode("ascii", "replace").decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll_dir")
    ap.add_argument("user_dir")
    ap.add_argument("search_dir")
    ap.add_argument("--size", type=int, default=32)
    ap.add_argument("--threshold", type=int, default=1)
    ap.add_argument("--turbo", type=int, default=1)
    ap.add_argument("--algorithm", type=int, default=1)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--use-db", action="store_true")
    a = ap.parse_args()

    real = os.path.normcase(os.path.join(os.environ.get("LOCALAPPDATA", ""), "AntiDupl.NET"))
    if os.path.normcase(os.path.abspath(a.user_dir)).startswith(real):
        sys.exit("refusing to use the real AntiDupl user folder")
    os.makedirs(a.user_dir, exist_ok=True)

    os.add_dll_directory(os.path.abspath(a.dll_dir))
    core = ctypes.CDLL(os.path.join(os.path.abspath(a.dll_dir), "AntiDupl.dll"))
    core.adCreateW.restype = ctypes.c_void_p
    core.adCreateW.argtypes = [ctypes.c_wchar_p]
    for name in ("adRelease", "adSearch"):
        getattr(core, name).argtypes = [ctypes.c_void_p]
    core.adOptionsGet.argtypes = core.adOptionsSet.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p]
    core.adPathWithSubFolderSetW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    core.adResultSort.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32]
    core.adResultGetW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_size_t)]
    core.adSaveW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_wchar_p]
    core.adLoadW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_wchar_p, ctypes.c_int32]
    core.adClear.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    db_dir = os.path.join(os.path.abspath(a.user_dir), "images", f"{a.size}x{a.size}")

    h = core.adCreateW(os.path.abspath(a.user_dir))
    if not h:
        sys.exit("adCreateW failed")
    try:
        cmp_ = CompareOptions()
        core.adOptionsGet(h, AD_OPTIONS_COMPARE, ctypes.byref(cmp_))
        cmp_.thresholdDifference = a.threshold
        cmp_.algorithmComparing = a.algorithm
        cmp_.compareInsideOneFolder = 1
        cmp_.checkOnEquality = 1
        assert core.adOptionsSet(h, AD_OPTIONS_COMPARE, ctypes.byref(cmp_)) == 0
        adv = AdvancedOptions()
        core.adOptionsGet(h, AD_OPTIONS_ADVANCED, ctypes.byref(adv))
        adv.reducedImageSize = a.size
        adv.useLibJpegTurbo = a.turbo
        adv.mistakeDataBase = 0
        assert core.adOptionsSet(h, AD_OPTIONS_ADVANCED, ctypes.byref(adv)) == 0

        buf = (ctypes.c_wchar * (MAX_PATH_EX + 1))()
        p = os.path.abspath(a.search_dir)
        buf[:len(p)] = p
        buf[MAX_PATH_EX] = "\x01"                       # include subfolders
        assert core.adPathWithSubFolderSetW(h, AD_PATH_SEARCH, ctypes.byref(buf), 1) == 0

        for run in range(a.runs):
            if a.use_db:                                # same order as SearchExecuterForm
                os.makedirs(db_dir, exist_ok=True)
                core.adLoadW(h, AD_FILE_IMAGE_DATA_BASE, db_dir, 0)
            err = core.adSearch(h)
            if err:
                sys.exit(f"adSearch error {err}")
            if a.use_db:
                err = core.adSaveW(h, AD_FILE_IMAGE_DATA_BASE, db_dir)
                if err:
                    sys.exit(f"saving the image database failed: error {err}")
                core.adClear(h, AD_FILE_IMAGE_DATA_BASE)
            core.adResultSort(h, AD_SORT_BY_DIFFERENCE, 1)
            start, count = ctypes.c_size_t(0), ctypes.c_size_t(64)
            results = (ResultW * 64)()
            core.adResultGetW(h, ctypes.byref(start), results, ctypes.byref(count))
            if a.runs > 1:
                print(f"-- run {run + 1}")
            for r in results[:count.value]:
                if r.type != AD_RESULT_DUPL_IMAGE_PAIR:
                    continue
                n1, n2 = os.path.basename(r.first.path), os.path.basename(r.second.path)
                print(f"{r.difference:.9f}  shows {r.difference:.2f}  {ascii(n1)} | {ascii(n2)}")
    finally:
        core.adRelease(h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
