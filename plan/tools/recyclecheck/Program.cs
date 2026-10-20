// Checks that what a build's core deletes reaches the Recycle Bin, from a
// process like AntiDupl's own: a .NET program that, like AntiDupl, isn't long
// path aware (a long-path-aware one, such as Python, makes the shell delete a
// long path for good). Three cases, each in a folder of its own under
// SCRATCH, on two copies of a picture that pair up with the core's default
// options (Recycle Bin and undo queue on):
//   delete second                     the second image goes to the Recycle Bin
//   replace (rename first to second)  the first image takes the second's
//                                     name; the second, hidden for undo
//                                     first, goes when the engine closes
//   delete second, long path          as the first, with a path over 260
//                                     characters
// The test files stay in the Recycle Bin, named recycle-check-<token>-*.jpg.
// Prints ok/FAIL per case and PASS or FAIL.
//   recyclecheck <bin\Release> <scratch folder> <a JPEG>
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;

static class Program
{
    const int AD_PATH_SEARCH = 0, AD_TARGET_CURRENT = 0, AD_ACTION_ENABLE_DUPL_PAIR = 2;
    const int AD_LOCAL_ACTION_DELETE_SECOND = 2, AD_LOCAL_ACTION_RENAME_FIRST_TO_SECOND = 4;
    const int MAX_PATH_EX = 32768;

    [DllImport("AntiDupl.dll", CharSet = CharSet.Unicode)] static extern IntPtr adCreateW(string userPath);
    [DllImport("AntiDupl.dll")] static extern int adRelease(IntPtr handle);
    [DllImport("AntiDupl.dll")] static extern int adSearch(IntPtr handle);
    [DllImport("AntiDupl.dll")] static extern int adPathWithSubFolderSetW(IntPtr handle, int pathType, IntPtr paths, UIntPtr count);
    [DllImport("AntiDupl.dll")] static extern int adCurrentSet(IntPtr handle, UIntPtr index);
    [DllImport("AntiDupl.dll")] static extern int adSelectionSet(IntPtr handle, ref UIntPtr startFrom, UIntPtr size, int value);
    [DllImport("AntiDupl.dll")] static extern int adCanApply(IntPtr handle, int actionEnableType, out int enable);
    [DllImport("AntiDupl.dll")] static extern int adResultApplyTo(IntPtr handle, int localActionType, int targetType);
    [DllImport("ntdll.dll")] static extern byte RtlAreLongPathsEnabled();

    static int Main(string[] args)
    {
        string bin = Path.GetFullPath(args[0]), scratch = Path.GetFullPath(args[1]), image = args[2];
        NativeLibrary.SetDllImportResolver(Assembly.GetExecutingAssembly(), (name, assembly, search) =>
            name == "AntiDupl.dll" ? NativeLibrary.Load(Path.Combine(bin, name)) : IntPtr.Zero);
        Console.WriteLine($"this process uses long paths: {RtlAreLongPathsEnabled() != 0}");
        string token = Guid.NewGuid().ToString("N").Substring(0, 8);
        int failures = 0;
        foreach (var (name, action, longPath) in new[] {
            ("delete second", AD_LOCAL_ACTION_DELETE_SECOND, false),
            ("replace (rename first to second)", AD_LOCAL_ACTION_RENAME_FIRST_TO_SECOND, false),
            ("delete second, path over 260 characters", AD_LOCAL_ACTION_DELETE_SECOND, true) })
        {
            string folder = Path.Combine(scratch, $"recycle-check-{token}-{action}{(longPath ? "-long" : "")}");
            // A folder under Windows' 248-character limit for folders, file
            // names that take the whole path past 260.
            if (longPath)
                folder += new string('x', Math.Max(0, 230 - folder.Length));
            Directory.CreateDirectory(folder);
            string tail = longPath ? new string('y', 60) : "";
            string first = Path.Combine(folder, $"recycle-check-{token}-1{tail}.jpg");
            string second = Path.Combine(folder, $"recycle-check-{token}-2{tail}.jpg");
            File.Copy(image, first);
            // Through streams: GDI+ itself takes no path over 260 characters.
            using (var input = File.OpenRead(first))
            using (var bitmap = new Bitmap(input))
            using (var output = File.Create(second))
            {
                var jpeg = ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);
                var quality = new EncoderParameters(1);
                quality.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, 85L);
                bitmap.Save(output, jpeg, quality);
            }
            long secondSize = new FileInfo(second).Length;

            string error = Run(Path.Combine(scratch, $"recycle-check-{token}-user"), folder, action);
            bool recycled = InRecycleBin(folder, token, secondSize);
            string[] left = Directory.GetFiles(folder).Select(Path.GetFileName).ToArray();
            bool stillThere = action == AD_LOCAL_ACTION_DELETE_SECOND && File.Exists(second);
            bool ok = error == null && recycled && !left.Any(f => f.StartsWith("~~adt"));
            if (!ok)
                failures++;
            Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {name}: " + (error ?? (recycled ? "the second image is in the Recycle Bin" :
                stillThere ? "the second image wasn't deleted" : "the second image is gone, NOT in the Recycle Bin")) +
                $"; folder: {string.Join(", ", left.Select(f => tail.Length > 0 ? f.Replace(tail, "y...") : f))}");
        }
        Console.WriteLine(failures == 0 ? "PASS" : $"FAIL ({failures})");
        return failures;
    }

    // Searches the folder, applies the action to its pair, closes the engine
    // (which recycles what it hid for undo); null, or what went wrong.
    static string Run(string userPath, string folder, int action)
    {
        Directory.CreateDirectory(userPath);
        IntPtr h = adCreateW(userPath);
        if (h == IntPtr.Zero)
            return "adCreateW failed";
        try
        {
            IntPtr path = Marshal.AllocHGlobal(MAX_PATH_EX * 2 + 4);
            try
            {
                byte[] zero = new byte[MAX_PATH_EX * 2 + 4];
                Marshal.Copy(zero, 0, path, zero.Length);
                byte[] text = Encoding.Unicode.GetBytes(folder);
                Marshal.Copy(text, 0, path, text.Length);
                Marshal.WriteInt32(path, MAX_PATH_EX * 2, 1); // with subfolders
                if (adPathWithSubFolderSetW(h, AD_PATH_SEARCH, path, (UIntPtr)1) != 0)
                    return "setting the search folder failed";
            }
            finally { Marshal.FreeHGlobal(path); }
            if (adSearch(h) != 0)
                return "the search failed";
            // adCanApply looks at the selected results.
            UIntPtr start = UIntPtr.Zero;
            if (adCurrentSet(h, UIntPtr.Zero) != 0 || adSelectionSet(h, ref start, (UIntPtr)1, 1) != 0 ||
                adCanApply(h, AD_ACTION_ENABLE_DUPL_PAIR, out int pair) != 0 || pair == 0)
                return "the two images didn't pair up";
            if (adResultApplyTo(h, action, AD_TARGET_CURRENT) != 0)
                return "the action failed";
            return null;
        }
        finally { adRelease(h); }
    }

    // A Recycle Bin entry of the current user with this size whose original
    // path is in the folder; the $I files hold version 2, the size, the
    // deletion time, the path's length and the path.
    static bool InRecycleBin(string folder, string token, long size)
    {
        string bin = Path.Combine(Path.GetPathRoot(folder), "$Recycle.Bin", WindowsIdentity.GetCurrent().User.Value);
        foreach (string info in Directory.GetFiles(bin, "$I*"))
        {
            byte[] b = File.ReadAllBytes(info);
            if (b.Length < 28 || BitConverter.ToInt64(b, 0) != 2 || BitConverter.ToInt64(b, 8) != size)
                continue;
            int length = BitConverter.ToInt32(b, 24);
            string original = Encoding.Unicode.GetString(b, 28, Math.Min(length * 2, b.Length - 28)).TrimEnd('\0');
            if (original.Contains(token) && Path.GetFileName(Path.GetDirectoryName(original.Replace(@"\\?\", ""))) == Path.GetFileName(folder))
                return true;
        }
        return false;
    }
}
