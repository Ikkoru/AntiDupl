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

using AntiDupl.NET.Core;
using AntiDupl.NET.Core.Original;

namespace AntiDupl.NET.WinForms
{
    /// <summary>
    /// Records what the user decides about result pairs, for the settings
    /// study (plan 07): each action on pairs (delete, mistake, hint,
    /// rename, move) with the pairs it was applied to, each pair the user
    /// looks at, and undo and redo, one JSON object per line in
    /// decisions.jsonl in the user folder. A pair that was looked at and
    /// got no action was left as it was. Writing errors are ignored: the
    /// log must never get in the way of the work.
    /// </summary>
    static public class DecisionLog
    {
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
                if (coreOptions != null)
                {
                    w.WriteStartObject("settings");
                    w.WriteString("algorithm", coreOptions.compareOptions.algorithmComparing.ToString());
                    w.WriteNumber("threshold", coreOptions.compareOptions.thresholdDifference);
                    w.WriteNumber("reducedImageSize", coreOptions.advancedOptions.reducedImageSize);
                    w.WriteEndObject();
                }
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
            try
            {
                using (MemoryStream stream = new MemoryStream())
                {
                    using (Utf8JsonWriter w = new Utf8JsonWriter(stream, new JsonWriterOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }))
                    {
                        w.WriteStartObject();
                        w.WriteString("time", DateTime.Now.ToString("o"));
                        body(w);
                        w.WriteEndObject();
                    }
                    stream.WriteByte((byte)'\n');
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
