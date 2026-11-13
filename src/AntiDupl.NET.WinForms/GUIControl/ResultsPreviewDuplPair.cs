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
using System.Text;
using System.Windows.Forms;
using System.Drawing;
using System.Diagnostics;
using System.IO;
using System.Threading;

using AntiDupl.NET.Core;
using AntiDupl.NET.Core.Original;

namespace AntiDupl.NET.WinForms
{
    /// <summary>
    /// Панель которая включает в себя две панели с просмотра изображений и панель инструментов для работы с дубликатами изображений.
    /// </summary>
    public class ResultsPreviewDuplPair : ResultsPreviewBase
    {
        private ImagePreviewPanel m_firstImagePreviewPanel;
        private ImagePreviewPanel m_secondImagePreviewPanel;
        private ToolStripButton m_deleteFirstButton;
        private ToolStripButton m_deleteSecondButton;
        private ToolStripButton m_renameFirstToSecondButton;
        private ToolStripButton m_renameSecondToFirstButton;
        private ToolStripButton m_deleteBothButton;
        private ToolStripButton m_mistakeButton;
        private ToolStripButton m_openBothFoldersButton;
        private ToolStripButton m_openBothImagesButton;
        private ToolStripButton m_openExternDiffImagesButton;
        private ToolStripButton m_openExternDiffImages2Button;

        private struct RectanglesWithSimilarity
        {
            public Rectangle rectangle;
            public float similarity;

            public RectanglesWithSimilarity(Rectangle rectangle, float similarity)
            {
                this.rectangle = rectangle;
                this.similarity = similarity;
            }
        }

        public ResultsPreviewDuplPair(CoreLib core, Options options, CoreOptions coreOptions, ResultsListView resultsListView)
            : base(core, options, coreOptions, resultsListView)
        {
            InitializeComponents();
            UpdateStrings();
            Resources.Strings.OnCurrentChange += new Resources.Strings.CurrentChangeHandler(UpdateStrings);
            OnOptionsChanged();
            m_options.OnChange += new Options.ChangeHandler(OnOptionsChanged);
            m_options.resultsOptions.OnHighlightDifferenceChange += new ResultsOptions.HighlightDifferenceChangeHandler(OnHighlightDifferenceChange);
        }

        private void InitializeComponents()
        {
            m_firstImagePreviewPanel = new ImagePreviewPanel(m_core, m_options, m_resultsListView, ImagePreviewPanel.Position.Top);
            m_secondImagePreviewPanel = new ImagePreviewPanel(m_core, m_options, m_resultsListView, ImagePreviewPanel.Position.Bottom);

            m_deleteFirstButton = InitFactory.ToolButton.Create("DeleteFirstVerticalButton", CoreDll.LocalActionType.DeleteFirst, OnButtonClicked);
            m_deleteSecondButton = InitFactory.ToolButton.Create("DeleteSecondVerticalButton", CoreDll.LocalActionType.DeleteSecond, OnButtonClicked);
            m_deleteBothButton = InitFactory.ToolButton.Create("DeleteBothVerticalButton", CoreDll.LocalActionType.DeleteBoth, OnButtonClicked);
            m_renameFirstToSecondButton = InitFactory.ToolButton.Create("RenameFirstToSecondVerticalButton", CoreDll.LocalActionType.RenameFirstToSecond, OnButtonClicked);
            m_renameSecondToFirstButton = InitFactory.ToolButton.Create("RenameSecondToFirstVerticalButton", CoreDll.LocalActionType.RenameSecondToFirst, OnButtonClicked);
            m_mistakeButton = InitFactory.ToolButton.Create("MistakeButton", CoreDll.LocalActionType.Mistake, OnButtonClicked);
            m_openBothFoldersButton = InitFactory.ToolButton.Create("OpenBothFoldersButton.png", null, OnOpenBothFoldersButtonClicked);
            m_openBothImagesButton = InitFactory.ToolButton.Create("OpenBothImagesButton.png", null, OnOpenBothImagesButtonClicked);
            m_openExternDiffImagesButton = InitFactory.ToolButton.Create("OpenExternDiffImagesButton.png", null, OnOpenExternDiffImagesClicked);
            m_openExternDiffImages2Button = InitFactory.ToolButton.Create("OpenExternDiffImages2Button.png", null, OnOpenExternDiffImages2Clicked);

            /* m_difrentNumericUpDown = new System.Windows.Forms.NumericUpDown();
            m_difrentNumericUpDown.Size = new System.Drawing.Size(62, 17);
            m_difrentNumericUpDown.Location = new System.Drawing.Point(102, 0);
            m_difrentNumericUpDown.Margin = new Padding(0);
            m_difrentNumericUpDown.DecimalPlaces = 2;
            m_difrentNumericUpDown.Increment = new decimal(new int[] { 1, 0, 0, 65536 });
            m_difrentNumericUpDown.Minimum = new decimal(new int[] { 0, 0, 0, 0 });
            m_difrentNumericUpDown.Value = new decimal(m_options.resultsOptions.DiffrentThreshold);
            m_difrentNumericUpDown.ValueChanged += new System.EventHandler(m_difrentNumericUpDown_ValueChanged);

            m_checkBoxDiffrent = new System.Windows.Forms.CheckBox();
            m_checkBoxDiffrent.AutoSize = true;
            //this.checkBox1.Location = new System.Drawing.Point(321, 459);
            //this.checkBox1.Name = "checkBox1";
            m_checkBoxDiffrent.Size = new System.Drawing.Size(80, 17);
            //this.checkBox1.TabIndex = 6;
            m_checkBoxDiffrent.Text = "Highlight";
            m_checkBoxDiffrent.UseVisualStyleBackColor = true;
            m_checkBoxDiffrent.Checked = m_options.resultsOptions.HighlightDiffrent; //TODO
            m_checkBoxDiffrent.CheckedChanged += new System.EventHandler(checkBoxDiffrent_CheckedChanged);

            m_difrentPanel = new System.Windows.Forms.Panel();
            m_difrentPanel.Controls.Add(m_checkBoxDiffrent);
            m_difrentPanel.Controls.Add(m_difrentNumericUpDown);
            //m_difrentPanel.Location = new System.Drawing.Point(225, 459);
            //m_difrentPanel.AutoSize = true;
            m_difrentPanel.Size = new System.Drawing.Size(200, 20);*/
        }

        public void UpdateStrings()
        {
            Strings s = Resources.Strings.Current;

            m_deleteFirstButton.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_DeleteFirstButton_ToolTip_Text, HotKeyOptions.Action.CurrentDuplPairDeleteFirst);
            m_deleteSecondButton.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_DeleteSecondButton_ToolTip_Text, HotKeyOptions.Action.CurrentDuplPairDeleteSecond);
            m_deleteBothButton.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_DeleteBothButton_ToolTip_Text, HotKeyOptions.Action.CurrentDuplPairDeleteBoth);
            m_renameFirstToSecondButton.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_RenameFirstToSecondButton_ToolTip_Text, HotKeyOptions.Action.CurrentDuplPairRenameFirstToSecond);
            m_renameSecondToFirstButton.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_RenameSecondToFirstButton_ToolTip_Text, HotKeyOptions.Action.CurrentDuplPairRenameSecondToFirst);
            m_mistakeButton.ToolTipText = GetToolTip(s.ResultsPreviewDefect_MistakeButton_ToolTip_Text, HotKeyOptions.Action.CurrentMistake);
            m_openBothFoldersButton.ToolTipText = s.ResultsPreviewDuplPair_OpenBothFoldersButton_ToolTip_Text;
            m_openBothImagesButton.ToolTipText = s.ResultsPreviewDuplPair_OpenBothImagesButton_ToolTip_Text;
            m_openExternDiffImagesButton.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_ExternDiffImagesButton_ToolTip_Text, HotKeyOptions.Action.OpenImageDiff);
            m_openExternDiffImages2Button.ToolTipText = GetToolTip(s.ResultsPreviewDuplPair_ExternDiffImages2Button_ToolTip_Text, HotKeyOptions.Action.OpenImageDiff2);

            // Для обновления EXIF.
            if (m_currentSearchResult != null)
            {
                m_firstImagePreviewPanel.UpdateExifTooltip(m_currentSearchResult);
                m_secondImagePreviewPanel.UpdateExifTooltip(m_currentSearchResult);
            }
        }

        public void SetCurrentSearchResult(CoreResult currentSearchResult)
        {
            m_currentSearchResult = currentSearchResult;
            m_firstImagePreviewPanel.SetResult(m_currentSearchResult);
            m_secondImagePreviewPanel.SetResult(m_currentSearchResult);
            SetDifference();
            SetHint(m_currentSearchResult.hint);
            UpdateNextAndPreviousButtonEnabling();
        }

        static private Color MixColors(Color firstColor, int firstWeight, Color secondColor, int secondWeight)
        {
            int A = (firstColor.A * firstWeight + secondColor.A * secondWeight) / (firstWeight + secondWeight);
            int R = (firstColor.R * firstWeight + secondColor.R * secondWeight) / (firstWeight + secondWeight);
            int G = (firstColor.G * firstWeight + secondColor.G * secondWeight) / (firstWeight + secondWeight);
            int B = (firstColor.B * firstWeight + secondColor.B * secondWeight) / (firstWeight + secondWeight);
            return Color.FromArgb(A, R, G, B);
        }

        private void SetHint(CoreDll.HintType hint)
        {
            RemoveHint();
            Color hintColor = MixColors(BackColor, 2, Color.Red, 1);
            switch (hint)
            {
                case CoreDll.HintType.DeleteFirst:
                    m_deleteFirstButton.BackColor = hintColor;
                    break;
                case CoreDll.HintType.DeleteSecond:
                    m_deleteSecondButton.BackColor = hintColor;
                    break;
                case CoreDll.HintType.RenameFirstToSecond:
                    m_renameFirstToSecondButton.BackColor = hintColor;
                    break;
                case CoreDll.HintType.RenameSecondToFirst:
                    m_renameSecondToFirstButton.BackColor = hintColor;
                    break;
            }
        }

        private void RemoveHint()
        {
            m_deleteFirstButton.BackColor = BackColor;
            m_deleteSecondButton.BackColor = BackColor;
            m_renameFirstToSecondButton.BackColor = BackColor;
            m_renameSecondToFirstButton.BackColor = BackColor;
        }

        private void OnButtonClicked(object sender, System.EventArgs e)
        {
            ToolStripButton item = (ToolStripButton)sender;
            CoreDll.LocalActionType action = (CoreDll.LocalActionType)item.Tag;
            m_resultsListView.MakeAction(action, CoreDll.TargetType.Current);
        }

        private void OnImageDoubleClicked(object sender, System.EventArgs e)
        {
            PictureBox pictureBox = (PictureBox)sender;
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = pictureBox.ImageLocation;
            Process.Start(startInfo);
        }

        private void OnOpenBothFoldersButtonClicked(object sender, System.EventArgs e)
        {
            FolderOpener.OpenContainingFolder(m_firstImagePreviewPanel.CurrentImageInfo);
            FolderOpener.OpenContainingFolder(m_secondImagePreviewPanel.CurrentImageInfo);
        }

        private void OnOpenBothImagesButtonClicked(object sender, System.EventArgs e)
        {
            ImageOpener.OpenFile(m_firstImagePreviewPanel.CurrentImageInfo.path);
            ImageOpener.OpenFile(m_secondImagePreviewPanel.CurrentImageInfo.path);
        }

        private void OnOpenExternDiffImagesClicked(object sender, System.EventArgs e)
        {
            ImageDiffOpener.OpenFiles(m_firstImagePreviewPanel.CurrentImageInfo.path, 
                m_secondImagePreviewPanel.CurrentImageInfo.path, m_options.imageDiffExecutablePath, m_options.imageDiffExecutableArguments);
        }

        private void OnOpenExternDiffImages2Clicked(object sender, System.EventArgs e)
        {
            ImageDiffOpener.OpenFiles(m_firstImagePreviewPanel.CurrentImageInfo.path,
                m_secondImagePreviewPanel.CurrentImageInfo.path, m_options.imageDiff2ExecutablePath, m_options.imageDiff2ExecutableArguments);
        }

        private void OnOptionsChanged()
        {
            m_mistakeButton.Enabled = m_coreOptions.advancedOptions.mistakeDataBase;
            // The second tool is optional: its button shows once a path is set.
            m_openExternDiffImages2Button.Visible = !string.IsNullOrEmpty(m_options.imageDiff2ExecutablePath);
        }

        protected override void AddItems(ResultsOptions.ViewMode viewMode)
        {
            if (viewMode == ResultsOptions.ViewMode.VerticalPairTable)
            {
                m_firstImagePreviewPanel.SetPosition(ImagePreviewPanel.Position.Top);
                m_secondImagePreviewPanel.SetPosition(ImagePreviewPanel.Position.Bottom);

                m_imageLayout.Controls.Add(m_firstImagePreviewPanel, 0, 0);
                m_imageLayout.Controls.Add(m_secondImagePreviewPanel, 0, 1);

                m_deleteFirstButton.Image = Resources.Images.Get("DeleteFirstVerticalButton");
                m_deleteSecondButton.Image = Resources.Images.Get("DeleteSecondVerticalButton");
                m_deleteBothButton.Image = Resources.Images.Get("DeleteBothVerticalButton");
                m_renameFirstToSecondButton.Image = Resources.Images.Get("RenameFirstToSecondVerticalButton");
                m_renameSecondToFirstButton.Image = Resources.Images.Get("RenameSecondToFirstVerticalButton");
            }
            if (viewMode == ResultsOptions.ViewMode.HorizontalPairTable)
            {
                m_firstImagePreviewPanel.SetPosition(ImagePreviewPanel.Position.Left);
                m_secondImagePreviewPanel.SetPosition(ImagePreviewPanel.Position.Right);

                m_imageLayout.Controls.Add(m_firstImagePreviewPanel, 0, 0);
                m_imageLayout.Controls.Add(m_secondImagePreviewPanel, 1, 0);

                m_deleteFirstButton.Image = Resources.Images.Get("DeleteFirstHorizontalButton");
                m_deleteSecondButton.Image = Resources.Images.Get("DeleteSecondHorizontalButton");
                m_deleteBothButton.Image = Resources.Images.Get("DeleteBothHorizontalButton");
                m_renameFirstToSecondButton.Image = Resources.Images.Get("RenameFirstToSecondHorizontalButton");
                m_renameSecondToFirstButton.Image = Resources.Images.Get("RenameSecondToFirstHorizontalButton");
            }

            m_toolStrip.Items.Add(m_openBothImagesButton);
            m_toolStrip.Items.Add(m_openExternDiffImagesButton);
            m_toolStrip.Items.Add(m_openExternDiffImages2Button);
            m_toolStrip.Items.Add(m_openBothFoldersButton);
            m_toolStrip.Items.Add(new ToolStripSeparator());
            m_toolStrip.Items.Add(m_deleteBothButton);
            m_toolStrip.Items.Add(new ToolStripSeparator());
            m_toolStrip.Items.Add(m_renameFirstToSecondButton);
            m_toolStrip.Items.Add(m_deleteFirstButton);
            m_toolStrip.Items.Add(new ToolStripSeparator());
            m_toolStrip.Items.Add(m_previousButton);
            m_toolStrip.Items.Add(m_nextButton);
            m_toolStrip.Items.Add(new ToolStripSeparator());
            m_toolStrip.Items.Add(m_deleteSecondButton);
            m_toolStrip.Items.Add(m_renameSecondToFirstButton);
            m_toolStrip.Items.Add(new ToolStripSeparator());
            m_toolStrip.Items.Add(m_mistakeButton);
        }


        private void OnHighlightDifferenceChange()
        {
            SetDifference();
        }

        private delegate void HighlightCompleteDelegate(List<Rectangle> rectangles);
        private event HighlightCompleteDelegate HighlightCompleteEvent;
        private Thread _thread;
        private bool _highlightStop = false;
        // Counts the pairs highlighted: a perceptual result is drawn only
        // while its count is current, since Butteraugli can't be stopped
        // midway and moving to the next pair doesn't wait for it.
        private int m_highlightGeneration;
        private bool m_threadPerceptual;

        private void SetDifference()
        {
            m_highlightGeneration++;
            if (m_options.resultsOptions.HighlightDifference)
            {
                if (_thread != null && _thread.ThreadState == System.Threading.ThreadState.Running)
                {
                    HighlightCompleteEvent -= new HighlightCompleteDelegate(HighlightCompleteEventHandler);
                    _highlightStop = true;
                    if (!m_threadPerceptual)
                        _thread.Join();
                }
                _highlightStop = false;
                m_threadPerceptual = m_options.resultsOptions.IgnoreCompressionNoise;
                if (m_threadPerceptual)
                {
                    List<PixelPair> pairs = GetPixelPairs(m_firstImagePreviewPanel.GetBitmap(),
                        m_secondImagePreviewPanel.GetBitmap(), m_coreOptions.compareOptions.transparentAsShown);
                    int generation = m_highlightGeneration;
                    _thread = new Thread(
                         unused => CalculatePerceptualDifferences(generation, pairs));
                    _thread.Name = "Calculate rectangles of differences";
                    _thread.IsBackground = true;
                    _thread.Start();
                    return;
                }
                HighlightCompleteEvent += new HighlightCompleteDelegate(HighlightCompleteEventHandler);
                List<ComparableBitmap[]> bitmap1 = new List<ComparableBitmap[]>();
                List<ComparableBitmap[]> bitmap2 = new List<ComparableBitmap[]>();
                GetFragments(m_firstImagePreviewPanel.GetBitmap(), m_secondImagePreviewPanel.GetBitmap(),
                    m_options.resultsOptions, m_coreOptions.compareOptions.transparentAsShown, bitmap1, bitmap2);
                _thread = new Thread(
                     unused => CalculateRectanglesOfDifferences(bitmap1, bitmap2));
                _thread.Name = "Calculate rectangles of differences";
                _thread.Start();
            }
            else
            {
                m_firstImagePreviewPanel.ClearDifference();
                m_secondImagePreviewPanel.ClearDifference();
            }
        }

        // A picture's difference map keeps its shape; the grid stretches it to a square.
        private static Size DifferenceMapSize(int width, int height)
        {
            double scale = Math.Min(1.0, ResultsOptions.PERCEPTUAL_DIFFERENCE_SIZE / (double)Math.Max(width, height));
            return new Size(Math.Max(8, (int)Math.Round(width * scale)), Math.Max(8, (int)Math.Round(height * scale)));
        }

        // The fragments, on the same grid as GetImageFragments, where the
        // map's largest value exceeds the threshold; the rest as for the grey
        // comparison (the limits on how many). Empty when there are too many.
        private static List<Rectangle> MarkedFragments(ResultsOptions options, float[] map, Size mapSize)
        {
            int size = options.NormalizedSizeOfImage, columns = options.AmountOfFragmentsOnX, rows = options.AmountOfFragmentsOnY;
            int mapWidth = mapSize.Width, mapHeight = mapSize.Height;
            List<RectanglesWithSimilarity> rectangles = new List<RectanglesWithSimilarity>();
            int fragmentWidth = size / columns, fragmentHeight = size / rows;
            for (int row = 0; row < rows; row++)
            {
                for (int column = 0; column < columns; column++)
                {
                    int x0 = column * fragmentWidth * mapWidth / size, x1 = Math.Max(x0 + 1, (column + 1) * fragmentWidth * mapWidth / size);
                    int y0 = row * fragmentHeight * mapHeight / size, y1 = Math.Max(y0 + 1, (row + 1) * fragmentHeight * mapHeight / size);
                    float largest = 0;
                    for (int y = y0; y < y1 && y < mapHeight; y++)
                        for (int x = x0; x < x1 && x < mapWidth; x++)
                            largest = Math.Max(largest, map[y * mapWidth + x]);
                    if (largest > options.PerceptualDifferenceThreshold)
                        rectangles.Add(new RectanglesWithSimilarity(
                            new Rectangle(column * fragmentWidth, row * fragmentHeight, fragmentWidth, fragmentHeight), -largest));
                }
            }

            List<Rectangle> chosen = new List<Rectangle>();
            if (options.NotHighlightIfFragmentsMoreThan && rectangles.Count > options.NotHighlightMaxFragments)
                return chosen;
            rectangles.Sort((a, b) => a.similarity.CompareTo(b.similarity)); // the largest difference first
            int count = options.HighlightAllDifferences ? rectangles.Count : Math.Min(rectangles.Count, options.MaxFragmentsForHighlight);
            for (int i = 0; i < count; i++)
                chosen.Add(rectangles[i].rectangle);
            return chosen;
        }

        // A pair's two pictures as B, G, R, A bytes, copies a background
        // thread may read while the panels move on to another pair.
        public class PixelPair
        {
            public byte[] First, Second;
            public int FirstWidth, FirstHeight, SecondWidth, SecondHeight;
        }

        // The pictures as shown: one pair, or with the transparency option
        // one per background they are laid over (TransparentPair.Shown), at
        // full size. The core's difference maps read no alpha.
        public static List<PixelPair> GetPixelPairs(Bitmap first, Bitmap second, bool transparentAsShown)
        {
            List<PixelPair> pairs = new List<PixelPair>();
            if (first == null || second == null)
                return pairs;
            List<Bitmap[]> shown = transparentAsShown ? TransparentPair.Shown(first, second, bitmap => bitmap) :
                new List<Bitmap[]> { new Bitmap[] { first, second } };
            foreach (Bitmap[] pictures in shown)
            {
                PixelPair pair = new PixelPair();
                pair.First = ImagePreviewPanel.GetPixels(pictures[0], out pair.FirstWidth, out pair.FirstHeight);
                pair.Second = ImagePreviewPanel.GetPixels(pictures[1], out pair.SecondWidth, out pair.SecondHeight);
                pairs.Add(pair);
            }
            return pairs;
        }

        // Each value the larger of the two maps' (the first when there is no
        // second yet).
        private static float[] Largest(float[] map, float[] other)
        {
            if (map == null)
                return other;
            for (int i = 0; i < map.Length; i++)
                map[i] = Math.Max(map[i], other[i]);
            return map;
        }

        // Laid over each other first, so that a shift or a crop isn't taken
        // for a difference: then a fragment of one is not the same fragment of
        // the other, and each picture gets its own. A pair that doesn't align,
        // or needs no aligning, gets one map for both. Pictures shown over
        // several backgrounds get a map over each, and a point differs by the
        // most it does over any; one background that doesn't align makes
        // plain maps of all. False when there is nothing to compare.
        public static bool PerceptualFragments(CoreLib core, ResultsOptions options, List<PixelPair> pairs,
            out List<Rectangle> chosen1, out List<Rectangle> chosen2)
        {
            chosen1 = chosen2 = null;
            if (pairs.Count == 0 || options.NormalizedSizeOfImage <= 16 ||
                options.AmountOfFragmentsOnX <= 0 || options.AmountOfFragmentsOnY <= 0)
                return false;
            Size size1 = DifferenceMapSize(pairs[0].FirstWidth, pairs[0].FirstHeight);
            Size size2 = DifferenceMapSize(pairs[0].SecondWidth, pairs[0].SecondHeight);
            float[] map1 = null, map2 = null;
            bool aligned = true;
            foreach (PixelPair pair in pairs)
            {
                float[] pairMap1, pairMap2;
                if (!core.AlignedDifferenceMaps(pair.First, pair.FirstWidth, pair.FirstHeight,
                    pair.Second, pair.SecondWidth, pair.SecondHeight,
                    size1.Width, size1.Height, size2.Width, size2.Height, out pairMap1, out pairMap2))
                {
                    aligned = false;
                    break;
                }
                map1 = Largest(map1, pairMap1);
                map2 = Largest(map2, pairMap2);
            }
            if (aligned)
            {
                chosen1 = MarkedFragments(options, map1, size1);
                chosen2 = MarkedFragments(options, map2, size2);
                return true;
            }
            map1 = null;
            foreach (PixelPair pair in pairs)
            {
                float[] pairMap = core.DifferenceMap(pair.First, pair.FirstWidth, pair.FirstHeight,
                    pair.Second, pair.SecondWidth, pair.SecondHeight, size1.Width, size1.Height);
                if (pairMap == null)
                    return false;
                map1 = Largest(map1, pairMap);
            }
            chosen1 = chosen2 = MarkedFragments(options, map1, size1);
            return true;
        }

        private void CalculatePerceptualDifferences(int generation, List<PixelPair> pairs)
        {
            List<Rectangle> chosen1, chosen2;
            if (!PerceptualFragments(m_core, m_options.resultsOptions, pairs, out chosen1, out chosen2))
                return;
            if (chosen1.Count == 0 && chosen2.Count == 0)
                return;
            try
            {
                BeginInvoke(new Action(() =>
                {
                    if (generation != m_highlightGeneration)
                        return;
                    m_firstImagePreviewPanel.SetDifference(chosen1);
                    m_secondImagePreviewPanel.SetDifference(chosen2);
                }));
            }
            catch (InvalidOperationException) // the window is closing
            {
            }
        }

        /// <summary>
        /// The fragments of a pair's pictures to compare: one set each, or
        /// with the transparency option one set per background the pictures
        /// are laid over (TransparentPair.Shown), like the search. None when
        /// a picture is missing or the normalized size too small.
        /// </summary>
        public static void GetFragments(Bitmap first, Bitmap second, ResultsOptions options, bool transparentAsShown,
            List<ComparableBitmap[]> firstFragments, List<ComparableBitmap[]> secondFragments)
        {
            if (first == null || second == null)
                return;
            Func<Bitmap, Bitmap> normalize = bitmap => ImagePreviewPanel.Normalize(bitmap, options);
            List<Bitmap[]> pairs = transparentAsShown ? TransparentPair.Shown(first, second, normalize) :
                new List<Bitmap[]> { new Bitmap[] { normalize(first), normalize(second) } };
            foreach (Bitmap[] pair in pairs)
            {
                if (pair[0] == null || pair[1] == null)
                {
                    firstFragments.Clear();
                    secondFragments.Clear();
                    return;
                }
                firstFragments.Add(ImagePreviewPanel.GetImageFragments(pair[0], options));
                secondFragments.Add(ImagePreviewPanel.GetImageFragments(pair[1], options));
            }
        }

        /// <summary>
        /// The similarity of fragment i: the least over the sets, as the
        /// search takes the larger difference over white and over black.
        /// </summary>
        public static float Similarity(List<ComparableBitmap[]> first, List<ComparableBitmap[]> second, int i)
        {
            float similarity = float.MaxValue;
            for (int set = 0; set < first.Count; set++)
                similarity = Math.Min(similarity, Comparator.Similarity(first[set][i].GrayscaleData, second[set][i].GrayscaleData));
            return similarity;
        }

        private void CalculateRectanglesOfDifferences(List<ComparableBitmap[]> bitmap1, List<ComparableBitmap[]> bitmap2)
        {
            if (bitmap1.Count == 0 || bitmap2.Count == 0)
                return;

            List<RectanglesWithSimilarity> rectangles = new List<RectanglesWithSimilarity>();
            float similarity;
            for (int i = 0; i < bitmap1[0].Length; i++)
            {
                if (_highlightStop)
                    return;
                similarity = Similarity(bitmap1, bitmap2, i);
                if (similarity < m_options.resultsOptions.DifferenceThreshold)
                {
                    rectangles.Add(new RectanglesWithSimilarity(bitmap1[0][i].Rect, similarity));
                }
            }

            if (m_options.resultsOptions.NotHighlightIfFragmentsMoreThan && rectangles.Count > m_options.resultsOptions.NotHighlightMaxFragments)
                return;

            if (!m_options.resultsOptions.HighlightAllDifferences)
            {
                if (HighlightCompleteEvent != null)
                {
                    rectangles.Sort(delegate (RectanglesWithSimilarity a, RectanglesWithSimilarity b)
                    {
                        return a.similarity.CompareTo(b.similarity);
                    });
                    RectanglesWithSimilarity[] src = rectangles.ToArray();
                    List<Rectangle> dst = new List<Rectangle>();
                    for (int i = 0, n = Math.Min(src.Length, m_options.resultsOptions.MaxFragmentsForHighlight); i < n; ++i)
                        dst.Add(src[i].rectangle);
                    HighlightCompleteEvent(dst);
                }
            }

            if (HighlightCompleteEvent != null)
            {
                RectanglesWithSimilarity[] src = rectangles.ToArray();
                List<Rectangle> dst = new List<Rectangle>();
                for (int i = 0; i < src.Length; ++i)
                    dst.Add(src[i].rectangle);
                HighlightCompleteEvent(dst);
            }
        }

        private void HighlightCompleteEventHandler(List<Rectangle> rectangles)
        {
            if (InvokeRequired) // Проверяем в этом ли потоке нахождится созданый обьект 
            {
                object[] eventArgs = { rectangles };
                Invoke(new HighlightCompleteDelegate(HighlightCompleteEventHandler), eventArgs);
                return;
            }

            if (rectangles != null && rectangles.Count > 0)
            {
                m_firstImagePreviewPanel.SetDifference(rectangles);
                m_secondImagePreviewPanel.SetDifference(rectangles);
            }

            HighlightCompleteEvent -= new HighlightCompleteDelegate(HighlightCompleteEventHandler);
        }
    
    }
}
