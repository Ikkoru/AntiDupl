// The pair preview's highlighted differences on pairs with transparency,
// with the transparency option off and on (T48): how many of the 16 x 16
// fragments a build would mark, through the calls the preview makes
// (ResultsPreviewDuplPair.GetFragments and Similarity; with PERCEPTUAL
// defined, GetPixelPairs and PerceptualFragments, the personal branch's
// Ignore compression noise). The default highlight options; the
// perceptual mode counts past the "not if more than" limit.
//
//   highlight_transparency <bin\Release>
//       generated pairs, PASS/FAIL against what each should give (the
//       cases list in Main); exit code 1 on a FAIL.
//   highlight_transparency <bin\Release> <pairs.tsv> <out.tsv>
//       real pairs: the TSV's last two columns are the paths; pairs with
//       a transparent pixel on either side are run, one line each to
//       out.tsv, and a summary.
//
// The managed assemblies are the ones AntiDuplBin named at build time;
// <bin\Release> must be the same folder (the core is loaded from it).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using AntiDupl.NET.WinForms;

static class Program
{
    const int W = 300, H = 200;

    // A shape: an ellipse (cx, cy, rx, ry) or, with ry < 0, a rectangle
    // (x0, y0, x1, y1 in cx, cy, rx, -ry), and its colour (B, G, R).
    record Shape(double A, double B, double C, double D, bool Ellipse, byte[] Bgr);

    static readonly Shape[] Drawing =
    {
        new Shape(100, 100, 60, 45, true, new byte[] { 40, 40, 220 }),
        new Shape(170, 40, 260, 150, false, new byte[] { 200, 90, 30 }),
        new Shape(30, 160, 270, 175, false, new byte[] { 20, 20, 20 }),
    };
    static readonly Shape[] Moved =
    {
        new Shape(200, 110, 60, 45, true, new byte[] { 40, 40, 220 }),
        new Shape(20, 30, 110, 140, false, new byte[] { 200, 90, 30 }),
        new Shape(30, 160, 270, 175, false, new byte[] { 20, 20, 20 }),
    };
    static readonly Shape[] WhiteLines =
    {
        new Shape(20, 30, 280, 44, false, new byte[] { 255, 255, 255 }),
        new Shape(20, 90, 280, 104, false, new byte[] { 255, 255, 255 }),
        new Shape(150, 150, 90, 30, true, new byte[] { 255, 255, 255 }),
    };

    static Shape[] Black(Shape[] shapes) =>
        Array.ConvertAll(shapes, s => s with { Bgr = new byte[] { 0, 0, 0 } });

    static double Coverage(Shape s, double x, double y)
    {
        int inside = 0;
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
            {
                double px = x + (i + 0.5) / 4, py = y + (j + 0.5) / 4;
                bool hit = s.Ellipse
                    ? Math.Pow((px - s.A) / s.C, 2) + Math.Pow((py - s.B) / s.D, 2) <= 1
                    : px >= s.A && px <= s.C && py >= s.B && py <= s.D;
                if (hit) inside++;
            }
        return inside / 16.0;
    }

    // hidden: the colour stored under fully transparent pixels; background:
    // when set, the picture flattened over it (opaque), a function of x, y.
    static Bitmap Render(Shape[] shapes, byte[] hidden, Func<int, int, byte[]> background, bool allClear = false)
    {
        byte[] bgra = new byte[W * H * 4];
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
            {
                double cover = 0;
                double[] colour = new double[3];
                foreach (Shape s in shapes)
                {
                    double c = Coverage(s, x, y);
                    // Later shapes are drawn over earlier ones.
                    for (int k = 0; k < 3; k++)
                        colour[k] = colour[k] * (1 - c) * cover / Math.Max(1e-9, cover + c - cover * c) +
                                    s.Bgr[k] * c / Math.Max(1e-9, cover + c - cover * c);
                    cover = cover + c - cover * c;
                }
                int i = (y * W + x) * 4;
                if (background != null)
                {
                    byte[] bg = background(x, y);
                    for (int k = 0; k < 3; k++)
                        bgra[i + k] = (byte)Math.Round(colour[k] * cover + bg[k] * (1 - cover));
                    bgra[i + 3] = 255;
                }
                else
                {
                    for (int k = 0; k < 3; k++)
                        bgra[i + k] = cover > 0 ? (byte)Math.Round(colour[k]) : hidden[k];
                    bgra[i + 3] = allClear ? (byte)0 : (byte)Math.Round(255 * cover);
                }
            }
        Bitmap bitmap = new Bitmap(W, H, PixelFormat.Format32bppArgb);
        BitmapData data = bitmap.LockBits(new Rectangle(0, 0, W, H), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
        for (int y = 0; y < H; y++)
            Marshal.Copy(bgra, y * W * 4, data.Scan0 + y * data.Stride, W * 4);
        bitmap.UnlockBits(data);
        return bitmap;
    }

    // The transparency options: both off; Improve transparent image
    // comparison on; and Ignore areas with transparency in both images too.
    enum Mode { Off, On, Masked }

#if PERCEPTUAL
    // The personal branch's perceptual highlight (Ignore compression
    // noise): Butteraugli's difference maps through the core.
    static AntiDupl.NET.Core.CoreLib Core;

    static int Marked(Bitmap a, Bitmap b, Mode mode, ResultsOptions options)
    {
        options.NotHighlightIfFragmentsMoreThan = false;
        options.HighlightAllDifferences = true;
        var pairs = ResultsPreviewDuplPair.GetPixelPairs(a, b, mode != Mode.Off, mode == Mode.Masked);
        if (!ResultsPreviewDuplPair.PerceptualFragments(Core, options, pairs, out var chosen1, out var chosen2))
            return -1;
        return Math.Max(chosen1.Count, chosen2.Count);
    }
#else
    static int Marked(Bitmap a, Bitmap b, Mode mode, ResultsOptions options)
    {
        var fa = new List<ComparableBitmap[]>();
        var fb = new List<ComparableBitmap[]>();
        ResultsPreviewDuplPair.GetFragments(a, b, options, mode != Mode.Off, mode == Mode.Masked, fa, fb);
        int marked = 0;
        for (int i = 0; i < fa[0].Length; i++)
            if (ResultsPreviewDuplPair.Similarity(fa, fb, i) < options.DifferenceThreshold)
                marked++;
        return marked;
    }
#endif

    static bool HasAlpha(Bitmap b)
    {
        if (!Image.IsAlphaPixelFormat(b.PixelFormat) && (b.PixelFormat & PixelFormat.Indexed) == 0)
            return false;
        BitmapData data = b.LockBits(new Rectangle(0, 0, b.Width, b.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        byte[] bytes = new byte[data.Stride * b.Height];
        Marshal.Copy(data.Scan0, bytes, 0, bytes.Length);
        b.UnlockBits(data);
        for (int i = 3; i < bytes.Length; i += 4)
            if (bytes[i] < 255) return true;
        return false;
    }

    // Real pairs: a TSV whose last two columns are the two paths (header
    // skipped). Pairs with transparency on either side are run; one line
    // each to out, and a summary.
    static int RunPairs(string tsv, string output)
    {
        ResultsOptions options = new ResultsOptions();
        int max = options.NotHighlightMaxFragments;
        Mode[] modes = { Mode.Off, Mode.On, Mode.Masked };
        int n = 0;
        int[] shown = new int[3], none = new int[3];
        long[] sums = new long[3];
        using var writer = new System.IO.StreamWriter(output, false, new System.Text.UTF8Encoding(false));
        writer.WriteLine("off\ton\tmasked\tfirst\tsecond");
        foreach (string line in System.IO.File.ReadLines(tsv, System.Text.Encoding.UTF8))
        {
            string[] f = line.Split('\t');
            if (f.Length < 2 || f[^1] == "second") continue;
            string p1 = f[^2], p2 = f[^1];
            static bool Jpeg(string p) => p.EndsWith(".jpg", StringComparison.OrdinalIgnoreCase) ||
                                          p.EndsWith(".jpeg", StringComparison.OrdinalIgnoreCase);
            if (Jpeg(p1) && Jpeg(p2)) continue;
            Bitmap a, b;
            try { a = new Bitmap(p1); b = new Bitmap(p2); }
            catch { continue; }
            using (a) using (b)
            {
                if (!HasAlpha(a) && !HasAlpha(b)) continue;
                int[] marked = Array.ConvertAll(modes, m => Marked(a, b, m, options));
                n++;
                for (int m = 0; m < 3; m++)
                {
                    sums[m] += marked[m];
                    if (marked[m] <= max) shown[m]++;
                    if (marked[m] == 0) none[m]++;
                }
                writer.WriteLine($"{marked[0]}\t{marked[1]}\t{marked[2]}\t{p1}\t{p2}");
            }
        }
        Console.WriteLine($"pairs with transparency: {n}; off / on / masked:");
        Console.WriteLine($"marked fragments, mean: {string.Join(" / ", Array.ConvertAll(sums, s => (s / (double)Math.Max(1, n)).ToString("F1")))}");
        Console.WriteLine($"none marked: {string.Join(" / ", none)}");
        Console.WriteLine($"at most {max} marked (so the marks show): {string.Join(" / ", shown)}");
        return 0;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool SetDllDirectory(string path);

    static int Main(string[] args)
    {
        if (args.Length != 1 && args.Length != 3)
        {
            Console.Error.WriteLine("usage: highlight_transparency <bin\\Release> [<pairs.tsv> <out.tsv>]");
            return 2;
        }
#if PERCEPTUAL
        SetDllDirectory(args[0]);
        // The core's own files: a folder of its own beside this program.
        string user = System.IO.Path.Combine(AppContext.BaseDirectory, "core-user");
        System.IO.Directory.CreateDirectory(user);
        Core = new AntiDupl.NET.Core.CoreLib(user);
#endif
        if (args.Length == 3)
            return RunPairs(args[1], args[2]);
        byte[] white = { 255, 255, 255 }, black = { 0, 0, 0 }, tan = { 100, 150, 200 };
        Func<int, int, byte[]> Plain(byte[] c) => (x, y) => c;
        Random random = new Random(1);
        byte[][] noise = new byte[W * H][];
        for (int i = 0; i < noise.Length; i++)
        {
            byte v = (byte)random.Next(60, 200);
            noise[i] = new byte[] { v, (byte)(255 - v), (byte)random.Next(256) };
        }
        Func<int, int, byte[]> busy = (x, y) => noise[y * W + x];

        Bitmap overWhiteHiddenWhite = Render(Drawing, white, null);
        // A picture to lay a drawing over: the moved drawing over the pattern.
        Bitmap sceneBitmap = Render(Moved, null, busy);
        Func<int, int, byte[]> scene = (x, y) =>
        {
            Color c = sceneBitmap.GetPixel(x, y);
            return new byte[] { c.B, c.G, c.R };
        };
        // Expected marks with the option on, and with transparent areas
        // ignored as well: none, some, or the same as in the setting before.
        var cases = new List<(string name, Bitmap a, Bitmap b, string expectOn, string expectMasked)>
        {
            ("hidden white vs hidden black", overWhiteHiddenWhite, Render(Drawing, black, null), "none", "none"),
            ("transparent vs flattened over white", overWhiteHiddenWhite, Render(Drawing, null, Plain(white)), "none", "none"),
            ("transparent vs flattened over black", overWhiteHiddenWhite, Render(Drawing, null, Plain(black)), "none", "none"),
            ("transparent vs flattened over tan", Render(Drawing, black, null), Render(Drawing, null, Plain(tan)), "none", "none"),
            ("flattened over tan vs transparent", Render(Drawing, null, Plain(tan)), Render(Drawing, black, null), "none", "none"),
            ("transparent vs over a patterned background", overWhiteHiddenWhite, Render(Drawing, null, busy), "some", "none"),
            ("transparent vs laid over another picture", overWhiteHiddenWhite, Render(Drawing, null, scene), "some", "none"),
            ("another drawing over the pattern", overWhiteHiddenWhite, Render(Moved, null, busy), "some", "some"),
            ("white lines on transparency vs plain white", Render(WhiteLines, white, null), Render(Array.Empty<Shape>(), null, Plain(white)), "some", "some"),
            ("two different drawings on transparency", overWhiteHiddenWhite, Render(Moved, white, null), "some", "some"),
            ("two different black drawings on transparency", Render(Black(Drawing), black, null), Render(Black(Moved), black, null), "some", "some"),
            ("alpha 0 everywhere vs the same opaque", Render(Drawing, white, Plain(tan)), Render(Drawing, null, Plain(tan)), "none", "none"),
            ("opaque vs the same moved", Render(Drawing, null, Plain(white)), Render(Moved, null, Plain(white)), "same", "same"),
        };
        // The alpha-0 case: the flattened pixels with their alpha cleared.
        {
            Bitmap b = cases.Find(c => c.name.StartsWith("alpha 0")).a;
            BitmapData data = b.LockBits(new Rectangle(0, 0, W, H), ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
            byte[] bytes = new byte[data.Stride * H];
            Marshal.Copy(data.Scan0, bytes, 0, bytes.Length);
            for (int i = 3; i < bytes.Length; i += 4) bytes[i] = 0;
            Marshal.Copy(bytes, 0, data.Scan0, bytes.Length);
            b.UnlockBits(data);
        }

        ResultsOptions options = new ResultsOptions();
        int failures = 0;
        static bool Meets(string expect, int marked, int before) =>
            expect switch { "none" => marked == 0, "some" => marked > 0, _ => marked == before };
        Console.WriteLine($"{"pair",-45} {"off",4} {"on",4} {"mask",4}  expected on, masked");
        foreach (var c in cases)
        {
            int off = Marked(c.a, c.b, Mode.Off, options), on = Marked(c.a, c.b, Mode.On, options);
            int masked = Marked(c.a, c.b, Mode.Masked, options);
            bool pass = Meets(c.expectOn, on, off) && Meets(c.expectMasked, masked, on);
            if (!pass) failures++;
            Console.WriteLine($"{c.name,-45} {off,4} {on,4} {masked,4}  {c.expectOn + ", " + c.expectMasked,-12} {(pass ? "PASS" : "FAIL")}");
        }
        Console.WriteLine(failures == 0 ? "all pass" : $"{failures} FAIL");
        return failures == 0 ? 0 : 1;
    }
}
