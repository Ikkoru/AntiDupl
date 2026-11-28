/* jpegcoef: a JPEG's quantised DCT coefficients and tables, out to a file
 * and back, for the research on how much of a JPEG's loss can be
 * restored (plan 07, T40) and whether a JPEG decoded to a lossless file
 * can be turned back into its JPEG (T40b).
 *
 *   jpegcoef dump  <in.jpg> <out.jcf>   the coefficients as stored
 *   jpegcoef write <in.jcf> <out.jpg>   a baseline JPEG holding exactly
 *                                       those coefficients and tables
 *
 * The .jcf layout (little-endian), read by jpegcoef.py beside it:
 *   "JCF1", int32 width, height, components
 *   per component: int32 h_samp, v_samp, table, width_in_blocks,
 *                  height_in_blocks
 *   4 x (int32 present, 64 x uint16 steps in natural order)
 *   per component: int16 coefficients [height_in_blocks][width_in_blocks][64],
 *                  natural order
 * Only greyscale and YCbCr files: the writer can't recreate an Adobe or
 * CMYK file's colour transform.
 *
 * Build: build.cmd beside it (libjpeg-turbo from vcpkg's
 * x64-windows-static, toolset v143).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "jpeglib.h"

#define JCF_COMPONENTS 4

static void fail(const char *what)
{
    fprintf(stderr, "jpegcoef: %s\n", what);
    exit(1);
}

static void put32(FILE *f, int v) { if (fwrite(&v, 4, 1, f) != 1) fail("write failed"); }
static int get32(FILE *f) { int v; if (fread(&v, 4, 1, f) != 1) fail("short .jcf file"); return v; }

static int dump(const char *in, const char *out)
{
    struct jpeg_decompress_struct d;
    struct jpeg_error_mgr err;
    FILE *fi = fopen(in, "rb"), *fo;
    jvirt_barray_ptr *arrays;
    int c, t, i, row;
    if (!fi) fail("can't open the JPEG");
    d.err = jpeg_std_error(&err);
    jpeg_create_decompress(&d);
    jpeg_stdio_src(&d, fi);
    jpeg_read_header(&d, TRUE);
    if (d.num_components != 1 && d.num_components != 3) fail("only greyscale and YCbCr");
    if (d.num_components == 3 && d.jpeg_color_space != JCS_YCbCr) fail("only greyscale and YCbCr");
    arrays = jpeg_read_coefficients(&d);
    fo = fopen(out, "wb");
    if (!fo) fail("can't create the .jcf file");
    fwrite("JCF1", 1, 4, fo);
    put32(fo, (int)d.image_width);
    put32(fo, (int)d.image_height);
    put32(fo, d.num_components);
    for (c = 0; c < d.num_components; c++) {
        jpeg_component_info *ci = &d.comp_info[c];
        put32(fo, ci->h_samp_factor);
        put32(fo, ci->v_samp_factor);
        put32(fo, ci->quant_tbl_no);
        put32(fo, (int)ci->width_in_blocks);
        put32(fo, (int)ci->height_in_blocks);
    }
    for (t = 0; t < 4; t++) {
        JQUANT_TBL *q = d.quant_tbl_ptrs[t];
        put32(fo, q != NULL);
        for (i = 0; i < DCTSIZE2; i++) {
            unsigned short s = q ? q->quantval[i] : 0;
            fwrite(&s, 2, 1, fo);
        }
    }
    for (c = 0; c < d.num_components; c++) {
        jpeg_component_info *ci = &d.comp_info[c];
        for (row = 0; row < (int)ci->height_in_blocks; row++) {
            JBLOCKARRAY b = (*d.mem->access_virt_barray)((j_common_ptr)&d, arrays[c], row, 1, FALSE);
            /* JCOEF is short: a row of blocks is height_in_blocks' row as stored. */
            if (fwrite(b[0], sizeof(JBLOCK), ci->width_in_blocks, fo) != ci->width_in_blocks)
                fail("write failed");
        }
    }
    jpeg_finish_decompress(&d);
    jpeg_destroy_decompress(&d);
    fclose(fi);
    fclose(fo);
    return 0;
}

static int write_jpeg(const char *in, const char *out)
{
    struct jpeg_compress_struct e;
    struct jpeg_error_mgr err;
    FILE *fi = fopen(in, "rb"), *fo;
    char magic[4];
    int width, height, n, c, t, i, row;
    int hs[JCF_COMPONENTS], vs[JCF_COMPONENTS], tbl[JCF_COMPONENTS], wb[JCF_COMPONENTS], hb[JCF_COMPONENTS];
    int present[4];
    unsigned short steps[4][DCTSIZE2];
    jvirt_barray_ptr arrays[JCF_COMPONENTS];
    if (!fi) fail("can't open the .jcf file");
    if (fread(magic, 1, 4, fi) != 4 || memcmp(magic, "JCF1", 4)) fail("not a .jcf file");
    width = get32(fi);
    height = get32(fi);
    n = get32(fi);
    if (n != 1 && n != 3) fail("only greyscale and YCbCr");
    for (c = 0; c < n; c++) {
        hs[c] = get32(fi); vs[c] = get32(fi); tbl[c] = get32(fi); wb[c] = get32(fi); hb[c] = get32(fi);
    }
    for (t = 0; t < 4; t++) {
        present[t] = get32(fi);
        if (fread(steps[t], 2, DCTSIZE2, fi) != DCTSIZE2) fail("short .jcf file");
    }
    e.err = jpeg_std_error(&err);
    jpeg_create_compress(&e);
    fo = fopen(out, "wb");
    if (!fo) fail("can't create the JPEG");
    jpeg_stdio_dest(&e, fo);
    e.image_width = (JDIMENSION)width;
    e.image_height = (JDIMENSION)height;
    e.input_components = n;
    e.in_color_space = n == 3 ? JCS_YCbCr : JCS_GRAYSCALE;
    jpeg_set_defaults(&e);
    jpeg_set_colorspace(&e, n == 3 ? JCS_YCbCr : JCS_GRAYSCALE);
    for (t = 0; t < 4; t++) {
        if (!present[t])
            continue;
        if (!e.quant_tbl_ptrs[t])
            e.quant_tbl_ptrs[t] = jpeg_alloc_quant_table((j_common_ptr)&e);
        for (i = 0; i < DCTSIZE2; i++)
            e.quant_tbl_ptrs[t]->quantval[i] = steps[t][i];
        e.quant_tbl_ptrs[t]->sent_table = FALSE;
    }
    for (c = 0; c < n; c++) {
        e.comp_info[c].h_samp_factor = hs[c];
        e.comp_info[c].v_samp_factor = vs[c];
        e.comp_info[c].quant_tbl_no = tbl[c];
    }
    e.optimize_coding = TRUE;
    /* Rounded up to whole MCUs, as the reader allocates them: the
     * coefficient controller reads a whole MCU row at a time, past the
     * last row of blocks when the count isn't a multiple of the sampling
     * factor. The padding stays zero. */
    for (c = 0; c < n; c++)
        arrays[c] = (*e.mem->request_virt_barray)((j_common_ptr)&e, JPOOL_IMAGE, TRUE,
                                                 (JDIMENSION)((wb[c] + hs[c] - 1) / hs[c] * hs[c]),
                                                 (JDIMENSION)((hb[c] + vs[c] - 1) / vs[c] * vs[c]),
                                                 (JDIMENSION)vs[c]);
    jpeg_write_coefficients(&e, arrays);
    for (c = 0; c < n; c++) {
        if (e.comp_info[c].width_in_blocks != (JDIMENSION)wb[c] || e.comp_info[c].height_in_blocks != (JDIMENSION)hb[c])
            fail("block counts don't match the sampling factors");
        for (row = 0; row < hb[c]; row++) {
            JBLOCKARRAY b = (*e.mem->access_virt_barray)((j_common_ptr)&e, arrays[c], row, 1, TRUE);
            if (fread(b[0], sizeof(JBLOCK), wb[c], fi) != (size_t)wb[c]) fail("short .jcf file");
        }
    }
    jpeg_finish_compress(&e);
    jpeg_destroy_compress(&e);
    fclose(fi);
    fclose(fo);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 4 && !strcmp(argv[1], "dump"))
        return dump(argv[2], argv[3]);
    if (argc == 4 && !strcmp(argv[1], "write"))
        return write_jpeg(argv[2], argv[3]);
    fprintf(stderr, "usage: jpegcoef dump <in.jpg> <out.jcf> | jpegcoef write <in.jcf> <out.jpg>\n");
    return 2;
}
