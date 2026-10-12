#!/bin/bash
# Builds test cases for pixel identity (T8), one folder per case, each a
# pair (run core_search.py on each folder):
#   byte      the same file twice                        -> 0
#   meta      JPEG and a copy without metadata           -> same pixels, 1e-6
#   prog      JPEG and a lossless progressive re-save    -> same pixels, 1e-6
#   jpgpng    JPEG and a PNG of its decoded pixels       -> same pixels, 1e-6
#   jxl       PNG and a lossless JPEG XL of it           -> same pixels, 1e-6
#   onepixel  PNG and a copy with one pixel changed      -> different, >= 1e-4
#   mirror    PNG and its mirror image (run with --transformed) -> found as a
#             mirrored copy, never as identical
# The reduced images of onepixel are equal (the change is below the reduced
# image's resolution), so before pixel identity it came out 1e-6 like the
# same-pixel cases.
#
# Usage: bash make_identity_cases.sh <source image, 1000 px or larger> <output folder>
# Needs magick, exiftool, jpegtran, djpeg, cjxl (or EXIFTOOL / TJ_DIR / CJXL).
set -euo pipefail
src="$1"
out="$2"
TJ_DIR="${TJ_DIR:-/c/vcpkg/installed/x64-windows-static/tools/libjpeg-turbo}"
EXIFTOOL="${EXIFTOOL:-exiftool}"
CJXL="${CJXL:-cjxl}"
MAGICK="${MAGICK:-magick}"

mkdir -p "$out"/{byte,meta,prog,jpgpng,jxl,onepixel,mirror}
# A PNG at 2000 px wide (no alpha), and a baseline JPEG with EXIF from it.
"$MAGICK" "$src" -resize 2000x -alpha off -define png:color-type=2 "$out/base.png"
"$MAGICK" "$out/base.png" -quality 90 -set comment "identity test" "$out/base.jpg"
"$EXIFTOOL" -q -overwrite_original -Artist="Test" -Software="identity test" "$out/base.jpg"

cp "$out/base.png" "$out/byte/a.png"
cp "$out/base.png" "$out/byte/b.png"

cp "$out/base.jpg" "$out/meta/a.jpg"
"$EXIFTOOL" -q -all= -o "$out/meta/b.jpg" "$out/base.jpg"

cp "$out/base.jpg" "$out/prog/a.jpg"
"$TJ_DIR/jpegtran.exe" -copy all -progressive -outfile "$out/prog/b.jpg" "$out/base.jpg"

# djpeg decodes like AntiDupl's TurboJPEG path (accurate integer IDCT, fancy
# upsampling); the PNG stores those pixels losslessly.
cp "$out/base.jpg" "$out/jpgpng/a.jpg"
"$TJ_DIR/djpeg.exe" -outfile "$out/jpgpng/b.ppm" "$out/base.jpg"
"$MAGICK" "$out/jpgpng/b.ppm" -define png:color-type=2 "$out/jpgpng/b.png"
rm "$out/jpgpng/b.ppm"

cp "$out/base.png" "$out/jxl/a.png"
"$CJXL" -d 0 --quiet "$out/base.png" "$out/jxl/b.jxl"

cp "$out/base.png" "$out/onepixel/a.png"
"$MAGICK" "$out/base.png" -fill "rgb(1,2,3)" -draw "point 1000,700" -define png:color-type=2 "$out/onepixel/b.png"

cp "$out/base.png" "$out/mirror/a.png"
"$MAGICK" "$out/base.png" -flop -define png:color-type=2 "$out/mirror/b.png"

rm "$out/base.png" "$out/base.jpg"
echo "cases in $out"
