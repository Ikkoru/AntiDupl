// Catches white flashes of AntiDupl's windows opening in dark mode: opens
// one window of a build over a black backdrop (so nothing behind it on the
// screen can count as white), captures the screen where it opens as fast
// as possible for 0.7 s, and counts the frames in which more than 2 % of
// the window's area is near-white (all channels over 0xD0). A flash is a
// few such frames at the start; white in most frames is something that
// stays light. Windows open on the screen, on top, for each run.
//
// Variants (the start window is StartFinishForm, shown without loading):
//   S1  start window as built         S2  S1 cloaked until painted
//   S3  empty dark window              S4  S1 without the progress bar
//   S5  S1 without the about panel     S6  S1 without both
//   S7  S1 with WS_EX_COMPOSITED       S8  S6, title never set
//   S9  S2, title never set            S10 S7, title never set
//   S11 S1 with its title set first    S12 S11 cloaked until painted
//   C1  Select columns (vertical)      C2  Select columns (horizontal;
//                                          needs the horizontal view mode)
// S2, S7, S9-S12 apply their change on top of the build, so on a build
// that already hides its windows until painted they show nothing new.
//
// Usage: flashprobe <bin\Release> <scratch user folder> <variant> <runs> [frame folder]
// The frame folder receives each run's whitest and last frame. Build with
// `dotnet build -c Release` (the .NET 10 SDK).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

static class Program
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool SetDllDirectory(string path);

    [DllImport("dwmapi.dll")]
    static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    [DllImport("user32.dll")]
    static extern bool RedrawWindow(IntPtr hwnd, IntPtr rect, IntPtr region, uint flags);

    static Assembly asm;
    static object core, options;

    [STAThread]
    static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(dir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        SetDllDirectory(dir);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.SetColorMode(SystemColorMode.Dark);
        asm = Assembly.LoadFrom(Path.Combine(dir, "AntiDupl.NET.WinForms.dll"));
        Assembly coreAsm = Assembly.LoadFrom(Path.Combine(dir, "AntiDupl.NET.Core.dll"));
        string real = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AntiDupl.NET");
        if (Path.GetFullPath(args[1]).StartsWith(real, StringComparison.OrdinalIgnoreCase))
        {
            Console.WriteLine("Refusing the real AntiDupl.NET user folder; give a scratch folder.");
            return 2;
        }
        Directory.CreateDirectory(args[1]);
        asm.GetType("AntiDupl.NET.WinForms.Resources", true).GetProperty("UserPath").SetValue(null, args[1]);
        asm.GetType("AntiDupl.NET.WinForms.Resources+Strings", true).GetMethod("Initialize").Invoke(null, null);
        core = Activator.CreateInstance(coreAsm.GetType("AntiDupl.NET.Core.CoreLib", true), args[1]);
        options = Activator.CreateInstance(asm.GetType("AntiDupl.NET.WinForms.Options", true));
        string variant = args[2];
        int runs = int.Parse(args[3]);

        Form probe = Make(variant);
        Size size = probe.Size;
        probe.Dispose();
        Rectangle area = Screen.PrimaryScreen.WorkingArea;
        Rectangle bounds = new Rectangle(area.Left + (area.Width - size.Width) / 2, area.Top + (area.Height - size.Height) / 2, size.Width, size.Height);

        Form backdrop = new Form { FormBorderStyle = FormBorderStyle.None, BackColor = Color.Black, StartPosition = FormStartPosition.Manual, Bounds = Rectangle.Inflate(bounds, 40, 40), ShowInTaskbar = false, TopMost = true };
        backdrop.Show();
        Settle(300);

        int flashed = 0;
        double worst = 0;
        for (int run = 0; run < runs; run++)
        {
            List<double> fractions = new List<double>();
            bool stop = false;
            Thread capture = new Thread(() =>
            {
                using (Bitmap bmp = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format32bppArgb))
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    while (!Volatile.Read(ref stop))
                    {
                        g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
                        double f = WhiteFraction(bmp);
                        if (args.Length > 4 && f > 0.02 && (fractions.Count == 0 || f > Max(fractions)))
                            bmp.Save(Path.Combine(args[4], $"{variant}_run{run + 1}.png"));
                        fractions.Add(f);
                    }
                    if (args.Length > 4)
                        bmp.Save(Path.Combine(args[4], $"{variant}_run{run + 1}_last.png"));
                }
            });
            capture.Start();
            Thread.Sleep(30);
            Form form = Make(variant);
            form.StartPosition = FormStartPosition.Manual;
            form.Location = bounds.Location;
            form.TopMost = true;
            form.Show();
            Settle(700);
            Volatile.Write(ref stop, true);
            capture.Join();
            form.Close();
            form.Dispose();
            Settle(200);
            int white = 0;
            double max = 0;
            foreach (double f in fractions)
            {
                if (f > 0.02) white++;
                max = Math.Max(max, f);
            }
            if (white > 0) flashed++;
            worst = Math.Max(worst, max);
            Console.WriteLine($"{variant} run {run + 1}: {fractions.Count} frames, {white} white, most white {max:P1}");
        }
        backdrop.Close();
        Console.WriteLine($"{variant}: flashed in {flashed} of {runs} runs, most white {worst:P1}");
        ((IDisposable)core).Dispose();
        return 0;
    }

    static double Max(List<double> values)
    {
        double max = 0;
        foreach (double v in values)
            max = Math.Max(max, v);
        return max;
    }

    static void Settle(int ms)
    {
        DateTime end = DateTime.Now.AddMilliseconds(ms);
        while (DateTime.Now < end)
        {
            Application.DoEvents();
            Thread.Sleep(5);
        }
    }

    static unsafe double WhiteFraction(Bitmap bmp)
    {
        BitmapData data = bmp.LockBits(new Rectangle(Point.Empty, bmp.Size), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        long white = 0;
        for (int y = 0; y < bmp.Height; y += 2)
        {
            byte* row = (byte*)data.Scan0 + y * data.Stride;
            for (int x = 0; x < bmp.Width; x += 2)
            {
                byte* p = row + x * 4;
                if (p[0] > 0xD0 && p[1] > 0xD0 && p[2] > 0xD0)
                    white++;
            }
        }
        bmp.UnlockBits(data);
        return white / (double)(((bmp.Height + 1) / 2) * ((bmp.Width + 1) / 2));
    }

    static Form Make(string variant)
    {
        switch (variant)
        {
            case "S2": return Cloaked(Splash());
            case "S3": return new Form { ClientSize = new Size(330, 380), FormBorderStyle = FormBorderStyle.FixedDialog, ControlBox = false, ShowInTaskbar = false, Text = "AntiDupl.NET" };
            case "S4": return Without(Splash(), typeof(ProgressBar));
            case "S5": return Without(Splash(), asm.GetType("AntiDupl.NET.WinForms.AboutProgramPanel", true));
            case "S6": return Without(Without(Splash(), typeof(ProgressBar)), asm.GetType("AntiDupl.NET.WinForms.AboutProgramPanel", true));
            // S7 composited window (WS_EX_COMPOSITED: the window and its
            // controls painted together, off screen); S8 S6 with the title
            // never changed; S9 cloaked, title never changed; S10 S7 with
            // the title never changed.
            case "S7": return Composited(Splash());
            case "S8": return NoTitleChange(Make("S6"));
            case "S9": return NoTitleChange(Cloaked(Splash()));
            case "S10": return NoTitleChange(Composited(Splash()));
            // S11 title set before it opens; S12 that and cloaked until
            // painted.
            // C1, C2: the Select columns windows (vertical, horizontal); the
            // results list is used only by OK.
            case "C1": return (Form)Activator.CreateInstance(asm.GetType("AntiDupl.NET.WinForms.SelectVerticalColumnsForm", true), null, options);
            case "C2": return (Form)Activator.CreateInstance(asm.GetType("AntiDupl.NET.WinForms.SelectHorizontalColumnsForm", true), null, options);
            case "S11": return Titled(Splash());
            case "S12": return Cloaked(Titled(Splash()));
            default: return Splash();
        }
    }

    static Form Splash()
    {
        return (Form)Activator.CreateInstance(asm.GetType("AntiDupl.NET.WinForms.StartFinishForm", true), core, options);
    }

    static Form Without(Form form, Type type)
    {
        Remove(form, type);
        return form;
    }

    static void Remove(Control parent, Type type)
    {
        foreach (Control c in new List<Control>(System.Linq.Enumerable.Cast<Control>(parent.Controls)))
        {
            if (type.IsInstanceOfType(c))
                parent.Controls.Remove(c);
            else
                Remove(c, type);
        }
    }

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
    static extern IntPtr GetWindowLongPtr(IntPtr hwnd, int index);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")]
    static extern IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr value);

    static Form Composited(Form form)
    {
        form.HandleCreated += (s, e) =>
        {
            long ex = GetWindowLongPtr(form.Handle, -20).ToInt64();
            SetWindowLongPtr(form.Handle, -20, new IntPtr(ex | 0x02000000));
        };
        return form;
    }

    static Form Titled(Form form)
    {
        form.Text = "AntiDupl.NET";
        return form;
    }

    // The start window's timer writes the loading step into its title.
    static Form NoTitleChange(Form form)
    {
        FieldInfo timer = form.GetType().GetField("m_timer", BindingFlags.NonPublic | BindingFlags.Instance);
        ((System.Windows.Forms.Timer)timer.GetValue(form)).Stop();
        return form;
    }

    static Form Cloaked(Form form)
    {
        form.HandleCreated += (s, e) =>
        {
            int on = 1;
            DwmSetWindowAttribute(form.Handle, 13, ref on, 4);
        };
        form.Shown += (s, e) => form.BeginInvoke(new Action(() =>
        {
            RedrawWindow(form.Handle, IntPtr.Zero, IntPtr.Zero, 0x0001 | 0x0080 | 0x0100);
            int off = 0;
            DwmSetWindowAttribute(form.Handle, 13, ref off, 4);
        }));
        return form;
    }
}
