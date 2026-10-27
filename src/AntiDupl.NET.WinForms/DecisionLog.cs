/*
* AntiDupl.NET Program (http://ermig1979.github.io/AntiDupl).
*
* Copyright (c) 2002-2018 Yermalayeu Ihar.
*
* Permission is hereby granted, free of charge, to any person obtaining a copy
* of this software and associated documentation files (the "Software"), to deal
* in the Software without restriction, including without limitation the rights
* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
* copies of the Software, and to permit persons to whom the Software is
* furnished to do so, subject to the following conditions:
*
* The above copyright notice and this permission notice shall be included in
* all copies or substantial portions of the Software.
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
* SOFTWARE.
*/
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Windows.Forms;

using AntiDupl.NET.Core;
using AntiDupl.NET.Core.Original;

namespace AntiDupl.NET.WinForms
{
    /// <summary>
    /// Records what the user decides about result pairs, for the settings
    /// study (plan 07): each action on pairs (delete, mistake, hint,
    /// rename, move) with the pairs it was applied to, each pair the user
    /// looks at, undo and redo, each search with every result it found,
    /// each hot key press (HotKeyWatcher), and the program's start and
    /// close, one JSON object per line in decisions.jsonl in the user
    /// folder. A pair that was looked at and got no action was left as it
    /// was. Writing errors are ignored: the log must never get in the way
    /// of the work. The format is described in plan/decision-log.md, which
    /// other programs read it by: a change to a field bumps SCHEMA there
    /// and here.
    /// </summary>
    static public class DecisionLog
    {
        // Written on every line; lines without it are version 1.
        public const int SCHEMA = 2;

        static private string m_lastViewed;

        static private string FilePath { get { return Path.Combine(Resources.UserPath, "decisions.jsonl"); } }

        /// <summary>
        /// An action about to be applied to the given pairs (the current one
        /// or the selected ones); detail: e.g. the new name of a rename.
        /// </summary>
        static public void Action(string action, string target, IList<CoreResult> results, int row, int rows, CoreOptions coreOptions, string detail = null)
        {
            Write(w =>
            {
                w.WriteString("event", "action");
                w.WriteString("action", action);
                w.WriteString("target", target);
                if (detail != null)
                    w.WriteString("detail", detail);
                w.WriteNumber("row", row);
                w.WriteNumber("rows", rows);
                WriteSettings(w, coreOptions);
                w.WriteStartArray("pairs");
                foreach (CoreResult result in results)
                {
                    w.WriteStartObject();
                    WritePair(w, result);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        static public void View(CoreResult result, int row, int rows)
        {
            if (result == null)
                return;
            string key = result.first.path + "\n" + (result.second != null ? result.second.path : "");
            if (key == m_lastViewed)
                return;
            m_lastViewed = key;
            Write(w =>
            {
                w.WriteString("event", "view");
                w.WriteNumber("row", row);
                w.WriteNumber("rows", rows);
                WritePair(w, result);
            });
        }

        static public void Event(string name)
        {
            Write(w => w.WriteString("event", name));
        }

        /// <summary>
        /// The program started: its version, the time its executable was
        /// built (the version alone is the same for every personal build),
        /// and its settings folder.
        /// </summary>
        static public void Start()
        {
            string built = "";
            try
            {
                built = File.GetLastWriteTimeUtc(Application.ExecutablePath).ToString("o");
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
            Write(w =>
            {
                w.WriteString("event", "start");
                w.WriteString("version", Application.ProductVersion);
                w.WriteString("built", built);
                w.WriteString("userFolder", Resources.UserPath);
            });
        }

        /// <summary>The program is closing, with this many results left in the list.</summary>
        static public void Close(uint resultsLeft)
        {
            Write(w =>
            {
                w.WriteString("event", "close");
                w.WriteNumber("resultsLeft", resultsLeft);
            });
        }

        /// <summary>
        /// A finished (or stopped) search: its folders and settings, how many
        /// images it looked at, and what it found, so a search that found
        /// nothing leaves a trace too; then one line per result, in the order
        /// the list shows them first.
        /// </summary>
        static public void Search(CoreOptions coreOptions, CoreStatistic statistic, TimeSpan duration, CoreResult[] results)
        {
            Write(w =>
            {
                w.WriteString("event", "search");
                WriteSettings(w, coreOptions, true);
                w.WriteStartArray("folders");
                foreach (CorePathWithSubFolder path in coreOptions.searchPath)
                    w.WriteStringValue(path.path);
                w.WriteEndArray();
                w.WriteStartArray("ignore");
                foreach (CorePathWithSubFolder path in coreOptions.ignorePath)
                    w.WriteStringValue(path.path);
                w.WriteEndArray();
                w.WriteBoolean("commandLineFolders", coreOptions.profileSearchPath != null);
                w.WriteNumber("images", statistic.searchedImageNumber);
                w.WriteNumber("pairs", statistic.duplImagePairNumber);
                w.WriteNumber("defects", statistic.defectImageNumber);
                w.WriteNumber("seconds", Math.Round(duration.TotalSeconds, 1));
            });
            if (results == null)
                return;
            var lines = new List<Action<Utf8JsonWriter>>();
            for (int i = 0; i < results.Length; i++)
            {
                int row = i;
                CoreResult result = results[i];
                lines.Add(w =>
                {
                    w.WriteString("event", "result");
                    w.WriteNumber("row", row);
                    w.WriteNumber("group", result.group);
                    w.WriteNumber("groupSize", result.groupSize);
                    WritePair(w, result);
                });
            }
            Write(lines);
        }

        /// <summary>
        /// Every press of a configured hot key, whatever has the keyboard
        /// focus, so a press that did nothing can be traced: the control and
        /// window it went to, and whether an action's progress window was
        /// open (it takes the focus and drops every key). Only hot keys and
        /// undo and redo are noted, never other typing.
        /// </summary>
        public sealed class HotKeyWatcher : IMessageFilter
        {
            private const int WM_KEYDOWN = 0x0100, WM_SYSKEYDOWN = 0x0104;
            private readonly Options m_options;

            public HotKeyWatcher(Options options)
            {
                m_options = options;
            }

            public bool PreFilterMessage(ref Message m)
            {
                if (m.Msg != WM_KEYDOWN && m.Msg != WM_SYSKEYDOWN)
                    return false;
                Keys key = (Keys)(int)(long)m.WParam | Control.ModifierKeys;
                string hotKey = HotKeyName(key);
                if (hotKey == null)
                    return false;
                Control target = Control.FromChildHandle(m.HWnd);
                Form form = target?.FindForm();
                bool busy = false;
                foreach (Form open in Application.OpenForms)
                    busy |= open is ProgressForm;
                bool repeat = ((long)m.LParam & 0x40000000) != 0; // held down
                Write(w =>
                {
                    w.WriteString("event", "key");
                    w.WriteString("key", key.ToString());
                    w.WriteString("hotKey", hotKey);
                    w.WriteString("to", target != null ? target.GetType().Name : "");
                    w.WriteString("window", form != null ? form.GetType().Name : "");
                    w.WriteBoolean("progressWindowOpen", busy);
                    if (repeat)
                        w.WriteBoolean("repeat", true);
                });
                return false;
            }

            // The hot key's action, as ResultsListView.MakeAction(Keys) picks it, or null.
            private string HotKeyName(Keys key)
            {
                if (key == (Keys.Z | Keys.Control))
                    return "Undo";
                if (key == (Keys.Y | Keys.Control))
                    return "Redo";
                for (HotKeyOptions.Action a = 0; a < HotKeyOptions.Action.Size; a++)
                    if (m_options.hotKeyOptions.Get(a) == key)
                        return a.ToString();
                return null;
            }
        }

        // The comparison settings; full adds the rest of what decides which
        // pairs a search finds, once per search rather than on every action.
        static private void WriteSettings(Utf8JsonWriter w, CoreOptions coreOptions, bool full = false)
        {
            if (coreOptions == null)
                return;
            CoreCompareOptions compare = coreOptions.compareOptions;
            w.WriteStartObject("settings");
            w.WriteString("algorithm", compare.algorithmComparing.ToString());
            w.WriteNumber("threshold", compare.thresholdDifference);
            w.WriteNumber("reducedImageSize", coreOptions.advancedOptions.reducedImageSize);
            if (compare.algorithmComparing == AntiDupl.NET.Core.Enums.AlgorithmComparing.Butteraugli)
                w.WriteNumber("butteraugliSize", compare.butteraugliSize);
            if (full)
            {
                w.WriteBoolean("checkOnEquality", compare.checkOnEquality);
                w.WriteBoolean("transformedImage", compare.transformedImage);
                w.WriteBoolean("sizeControl", compare.sizeControl);
                w.WriteBoolean("typeControl", compare.typeControl);
                w.WriteBoolean("ratioControl", compare.ratioControl);
                w.WriteNumber("minimalImageSize", compare.minimalImageSize);
                w.WriteNumber("maximalImageSize", compare.maximalImageSize);
                w.WriteBoolean("compareInsideOneFolder", compare.compareInsideOneFolder);
                w.WriteBoolean("compareInsideOneSearchPath", compare.compareInsideOneSearchPath);
                w.WriteNumber("ignoreFrameWidth", coreOptions.advancedOptions.ignoreFrameWidth);
                w.WriteBoolean("mistakeDataBase", coreOptions.advancedOptions.mistakeDataBase);
                w.WriteBoolean("deleteToRecycleBin", coreOptions.advancedOptions.deleteToRecycleBin);
            }
            w.WriteEndObject();
        }

        static private void WritePair(Utf8JsonWriter w, CoreResult result)
        {
            w.WriteString("type", result.type.ToString());
            w.WriteNumber("difference", result.difference);
            w.WriteString("transform", result.transform.ToString());
            w.WriteString("hint", result.hint.ToString());
            WriteImage(w, "first", result.first);
            if (result.type == CoreDll.ResultType.DuplImagePair)
                WriteImage(w, "second", result.second);
            else
                w.WriteString("defect", result.defect.ToString());
        }

        static private void WriteImage(Utf8JsonWriter w, string name, CoreImageInfo image)
        {
            w.WriteStartObject(name);
            w.WriteString("path", image.path);
            w.WriteNumber("size", image.size);
            w.WriteString("modified", ModifiedTime(image.time));
            w.WriteString("format", image.type.ToString());
            w.WriteNumber("width", image.width);
            w.WriteNumber("height", image.height);
            w.WriteNumber("blockiness", Math.Round(image.blockiness, 4));
            w.WriteNumber("blurring", Math.Round(image.blurring, 4));
            w.WriteEndObject();
        }

        // The core keeps the file time as a FILETIME.
        static private string ModifiedTime(ulong fileTime)
        {
            try
            {
                return DateTime.FromFileTimeUtc((long)fileTime).ToString("o");
            }
            catch (ArgumentOutOfRangeException)
            {
                return "";
            }
        }

        static private void Write(Action<Utf8JsonWriter> body)
        {
            Write(new Action<Utf8JsonWriter>[] { body });
        }

        // One line per body, appended with a single write.
        static private void Write(IEnumerable<Action<Utf8JsonWriter>> bodies)
        {
            try
            {
                using (MemoryStream stream = new MemoryStream())
                {
                    foreach (Action<Utf8JsonWriter> body in bodies)
                    {
                        using (Utf8JsonWriter w = new Utf8JsonWriter(stream, new JsonWriterOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }))
                        {
                            w.WriteStartObject();
                            w.WriteString("time", DateTime.Now.ToString("o"));
                            w.WriteNumber("schema", SCHEMA);
                            body(w);
                            w.WriteEndObject();
                        }
                        stream.WriteByte((byte)'\n');
                    }
                    using (FileStream file = new FileStream(FilePath, FileMode.Append, FileAccess.Write, FileShare.Read))
                        stream.WriteTo(file);
                }
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }
}
