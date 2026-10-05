#!/bin/bash
# Builds JPEG decoder test cases from one JPEG: one folder per case, each
# holding two files whose pixels are identical, so every case shows up as
# a pair in a search (core_search.py --details).
#
# Usage: make_jpeg_cases.sh SOURCE.jpg OUT_DIR
#
# Needs djpeg/cjpeg (libjpeg-turbo), exiftool and magick (ImageMagick) on
# PATH, or their folders in TJ_DIR / EXIFTOOL / MAGICK.
#
# Cases:
#   s444 s422 s420 s440 gray prog arith
#               *_e0.jpg: cjpeg's output (JFIF APP0 first); *_e1.jpg: the
#               same scan data with JFIF removed and EXIF added (APP1 first)
#   exif        all seven EXIF fields AntiDupl shows, and an exact copy
#   jfifexif    EXIF after a JFIF segment, and an exact copy
#   cmyk        CMYK JPEG (libjpeg-turbo can't decode it into BGRA)
#   trunc       the first 60 % of a baseline JPEG
set -e
[ $# -eq 2 ] || { echo "usage: $0 SOURCE.jpg OUT_DIR" >&2; exit 2; }
SRC=$1
OUT=$2
DJPEG=${TJ_DIR:+$TJ_DIR/}djpeg
CJPEG=${TJ_DIR:+$TJ_DIR/}cjpeg
EXIF=${EXIFTOOL:-exiftool}
MAGICK=${MAGICK:-magick}

mkdir -p "$OUT"
"$DJPEG" -ppm -outfile "$OUT/src.ppm" "$SRC"

variant() {
  name=$1; shift
  mkdir -p "$OUT/$name"
  "$CJPEG" "$@" -outfile "$OUT/$name/${name}_e0.jpg" "$OUT/src.ppm"
  "$EXIF" -q -JFIF:all= -Make=TestMake -Model=TestModel \
    -o "$OUT/$name/${name}_e1.jpg" "$OUT/$name/${name}_e0.jpg"
}
variant s444 -quality 90 -sample 1x1
variant s422 -quality 90 -sample 2x1
variant s420 -quality 90 -sample 2x2
variant s440 -quality 90 -sample 1x2
variant gray -quality 90 -grayscale
variant prog -quality 90 -progressive
variant arith -quality 90 -arithmetic

mkdir -p "$OUT/exif"
"$EXIF" -q -JFIF:all= -ImageDescription=TestDescription -Make=TestMake \
  -Model=TestModel -Software=TestSoftware -ModifyDate="2020:01:02 03:04:05" \
  -Artist=TestArtist -UserComment=TestComment \
  -o "$OUT/exif/exif_a.jpg" "$OUT/s420/s420_e0.jpg"
cp "$OUT/exif/exif_a.jpg" "$OUT/exif/exif_b.jpg"

mkdir -p "$OUT/jfifexif"
"$EXIF" -q -Make=TestMake -Artist=TestArtist \
  -o "$OUT/jfifexif/jfifexif_a.jpg" "$OUT/s420/s420_e0.jpg"
cp "$OUT/jfifexif/jfifexif_a.jpg" "$OUT/jfifexif/jfifexif_b.jpg"

mkdir -p "$OUT/cmyk"
"$MAGICK" "$OUT/src.ppm" -colorspace CMYK -quality 90 "$OUT/cmyk/cmyk_a.jpg"
cp "$OUT/cmyk/cmyk_a.jpg" "$OUT/cmyk/cmyk_b.jpg"

mkdir -p "$OUT/trunc"
size=$(wc -c < "$OUT/s420/s420_e0.jpg")
head -c $((size * 6 / 10)) "$OUT/s420/s420_e0.jpg" > "$OUT/trunc/trunc_a.jpg"
cp "$OUT/trunc/trunc_a.jpg" "$OUT/trunc/trunc_b.jpg"

rm "$OUT/src.ppm"
