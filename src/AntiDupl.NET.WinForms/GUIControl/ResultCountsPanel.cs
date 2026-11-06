using System;
using System.Drawing;
using System.Windows.Forms;

namespace AntiDupl.NET.WinForms
{
    /// <summary>
    /// The status bar's counts, for the bar beside the preview's buttons: side
    /// by side, or stacked for the vertical view's narrow bar, right-aligned
    /// and cut off at its left edge.
    /// </summary>
    public class ResultCountsPanel : Control
    {
        private const int GAP = 12;
        private const TextFormatFlags FLAGS = TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine | TextFormatFlags.NoPadding;

        private string[] m_titles = { "", "", "" };
        private string[] m_values = { "0", "0", "0" };
        private bool m_stacked;

        public ResultCountsPanel()
        {
            DoubleBuffered = true;
            ForeColor = ThemeColors.Text;
            Margin = new Padding(0);
        }

        public bool Stacked
        {
            get { return m_stacked; }
            set { m_stacked = value; Fit(); }
        }

        public void SetTitles(string total, string current, string selected)
        {
            m_titles = new string[] { total, current, selected };
            Fit();
        }

        public void SetCounts(int total, int current, int selected)
        {
            m_values = new string[] { total.ToString(), current.ToString(), selected.ToString() };
            Fit();
        }

        private int Measure(string text)
        {
            return TextRenderer.MeasureText(text, Font, Size.Empty, FLAGS).Width;
        }

        private int ColumnWidth(int i)
        {
            return Math.Max(Measure(m_titles[i]), Measure(m_values[i]));
        }

        // Side by side the panel is as large as its text; stacked it takes
        // the bar's width from the layout, and adds nothing to it.
        private void Fit()
        {
            if (!m_stacked)
            {
                int width = 2 * GAP;
                for (int i = 0; i < 3; i++)
                    width += ColumnWidth(i);
                Size = new Size(width + 1, 2 * Font.Height);
            }
            Invalidate();
        }

        private void DrawRight(Graphics graphics, string text, int right, int top)
        {
            TextRenderer.DrawText(graphics, text, Font, new Point(right - Measure(text), top), ForeColor, FLAGS);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            int line = Font.Height;
            if (m_stacked)
            {
                for (int i = 0; i < 3; i++)
                {
                    DrawRight(e.Graphics, m_titles[i], ClientSize.Width, i * 3 * line);
                    DrawRight(e.Graphics, m_values[i], ClientSize.Width, (i * 3 + 1) * line);
                }
                return;
            }
            int right = 0;
            for (int i = 0; i < 3; i++)
            {
                right += ColumnWidth(i);
                DrawRight(e.Graphics, m_titles[i], right, 0);
                DrawRight(e.Graphics, m_values[i], right, line);
                right += GAP;
            }
        }
    }
}
