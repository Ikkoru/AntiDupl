// Timing/score harness for the standalone google/butteraugli C++ implementation.
// Build (Linux/macOS/MSYS2):
//   git clone --depth 1 https://github.com/google/butteraugli.git
//   g++ -O2 -std=c++14 -I butteraugli -o bh main.cc butteraugli/butteraugli/butteraugli.cc
// Input: two raw files = uint32 width, uint32 height, then width*height*3 bytes of sRGB (R,G,B).
// Output: "<max-norm score> <milliseconds>"
#include "butteraugli/butteraugli.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>

using namespace butteraugli;

static bool Load(const char* fn, std::vector<ImageF>& planes, uint32_t& w, uint32_t& h) {
  FILE* f = fopen(fn, "rb");
  if (!f) return false;
  bool ok = fread(&w, 4, 1, f) == 1 && fread(&h, 4, 1, f) == 1;
  std::vector<unsigned char> buf(ok ? size_t(w) * h * 3 : 0);
  ok = ok && fread(buf.data(), 1, buf.size(), f) == buf.size();
  fclose(f);
  if (!ok) return false;
  // butteraugli expects linear intensities scaled to 0..255
  float lut[256];
  for (int i = 0; i < 256; ++i) {
    double c = i / 255.0;
    lut[i] = float(255.0 * (c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4)));
  }
  planes = CreatePlanes<float>(w, h, 3);
  for (uint32_t y = 0; y < h; ++y)
    for (int c = 0; c < 3; ++c) {
      float* row = planes[c].Row(y);
      for (uint32_t x = 0; x < w; ++x) row[x] = lut[buf[(size_t(y) * w + x) * 3 + c]];
    }
  return true;
}

int main(int argc, char** argv) {
  if (argc < 3) { printf("usage: bh a.raw b.raw\n"); return 2; }
  std::vector<ImageF> a, b;
  uint32_t w, h, w2, h2;
  if (!Load(argv[1], a, w, h) || !Load(argv[2], b, w2, h2) || w != w2 || h != h2) {
    printf("load error\n");
    return 1;
  }
  ImageF diffmap;
  double score = 0;
  auto t0 = std::chrono::steady_clock::now();
  ButteraugliInterface(a, b, 1.0f, diffmap, score);
  auto t1 = std::chrono::steady_clock::now();
  printf("%f %.1f\n", score, std::chrono::duration<double, std::milli>(t1 - t0).count());
  return 0;
}
