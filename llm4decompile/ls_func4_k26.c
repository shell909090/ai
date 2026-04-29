/* [LLM4Decompile REFINED] */
/* 重命名对应关系:
 *   FUN_00104c00          -> ls_main
 *   param_1               -> argc
 *   param_2               -> argv
 *   cVar1                 -> next_char
 *   __s1                  -> compare_ptr
 *   bVar2                 -> matched_flag
 *   __stream              -> err_stream
 *   uVar3                 -> width_temp
 *   cVar4                 -> bool_result
 *   uVar5                 -> unused_ret
 *   cVar6                 -> parse_result
 *   bVar7                 -> byte_result
 *   iVar8                 -> opt / idx / ret
 *   iVar9                 -> ret2 / cmp_result
 *   uVar10                -> format / temp
 *   lVar11                -> arg_idx
 *   puVar12               -> new_node
 *   pvVar13               -> tmp_ptr
 *   uVar14                -> msg1
 *   uVar15                -> msg2
 *   uVar16                -> term_width
 *   sVar17                -> len
 *   psVar18               -> color_rule
 *   pcVar19               -> time_format2
 *   ppuVar20              -> option_table
 *   __ptr                 -> dir_node
 *   psVar21               -> prev_rule
 *   pcVar22               -> time_format1
 *   puVar23               -> tab_size_ptr
 *   puVar24               -> time_style_opt
 *   in_R9                 -> arg9 (寄存器传参)
 *   in_R10                -> arg10 (寄存器传参)
 *   in_R11                -> arg11 (寄存器传参)
 *   pcVar25               -> str_temp
 *   lVar26                -> long_temp / choice
 *   psVar27               -> rule_iter
 *   in_FS_OFFSET          -> fs_offset (栈保护)
 *   bVar28                -> human_readable
 *   local_90              -> sort_type
 *   local_8c              -> quoting_style
 *   local_88              -> time_style
 *   local_80              -> line_width
 *   local_78              -> tab_size
 *   local_70              -> print_dir_name
 *   local_60              -> ls_colors_ptr
 *   local_58              -> parse_result1
 *   uStack_50             -> parse_result2
 *   local_44              -> prefix_buf[0]
 *   local_43              -> prefix_buf[1]
 *   local_42              -> prefix_buf[2]
 *   local_40              -> stack_guard
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <locale.h>
#include <libintl.h>
#include <error.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <fnmatch.h>
#include <stdbool.h>
#include <stddef.h>

extern void FUN_00116460(void);
extern void FUN_0011ace0(void *);
extern void FUN_00106ce0(void *);
extern long FUN_0010f1d0(const char *, char *, void *, void *, int, void *, int, void *);
extern char FUN_00106e50(void);
extern long FUN_0011a200(char *, int, int, long, void *, void *, int, int);
extern long FUN_0010ee80(char *, void *, void *, int);
extern void FUN_0010f000(const char *, char *, long);
extern void FUN_00119b30(FILE *, char *, char *, void *, void *, void *, int, void *);
extern void FUN_00113490(char *, void *, void *);
extern long FUN_00106de0(char *);
extern char *FUN_00118c20(char *);
extern void FUN_0011a540(char *, int, int, void *, void *);
extern void FUN_00118160(int, int);
extern int FUN_00118140(int);
extern void *FUN_00118100(int);
extern void FUN_00118180(void *, int, int);
extern void FUN_00106e80(void);
extern void *FUN_00119d00(size_t);
extern char FUN_00106920(void *, char **, int, void *);
extern int FUN_0010f3c0(void *, void *, size_t);
extern char FUN_00111400(int);
extern void FUN_001161c0(void *, int, int, void *, void *);
extern void *FUN_00111e30(int, int, void *, void *, void *);
extern void FUN_0011a1c0(void);
extern void *FUN_0011a360(void);
extern void FUN_001087c0(void);
extern void FUN_001071c0(void *, int, int);
extern void FUN_0010ca80(void *, int, int, int);
extern void FUN_00108e30(void);
extern void FUN_00109530(int, int);
extern void FUN_0010c650(void);
extern void FUN_0010dc80(void *, void *, char);
extern void FUN_00107990(void *);
extern void FUN_001077e0(int);
extern void FUN_00107670(char *, void *);
extern long FUN_00111900(void *);
extern void FUN_00111ff0(long);
extern void *__assert_fail(const char *, const char *, int, const char *);
extern void *__stack_chk_fail(void);
extern void *FUN_00112530(void *, void *);

extern int DAT_001271f8;
extern int DAT_00128230;
extern int DAT_001282d8;
extern long *DAT_001283a0;
extern long DAT_00128390;
extern long DAT_00128398;
extern int DAT_00128310;
extern int DAT_001271e0;
extern int DAT_00128331;
extern int DAT_00128338;
extern int DAT_00128334;
extern int DAT_00127028;
extern int DAT_00128318;
extern int DAT_00128316;
extern int DAT_0012834d;
extern int DAT_0012834f;
extern int DAT_0012834c;
extern int DAT_00128389;
extern int DAT_00128348;
extern int DAT_0012833c;
extern int DAT_00128340;
extern int DAT_00127020;
extern int DAT_0012831c;
extern int DAT_00128358;
extern char DAT_00128354;
extern int DAT_00128315;
extern int DAT_00128314;
extern int DAT_00128332;
extern int DAT_00127019;
extern int DAT_0012835c;
extern int DAT_00128220;
extern int DAT_001282d0;
extern void *DAT_001282e0;
extern int DAT_001282f8;
extern int DAT_001283c8;
extern void *DAT_001282f0;
extern void *DAT_001282e8;
extern void *DAT_00128300;
extern void *DAT_00128328;
extern void *DAT_00128320;
extern void *PTR_DAT_00127040;
extern void *PTR_s__b__e__H__M_00127048;
extern int DAT_00128350;
extern char DAT_001283b0;
extern void *DAT_001283e8;
extern void *DAT_00128100;
extern void *DAT_001282c8;
extern char DAT_001282c2;
extern char DAT_001282c1;
extern char DAT_001282c0;
extern void *DAT_001281c0;
extern void *DAT_00128160;
extern void *DAT_001283a8;
extern int DAT_001283d8;
extern void *DAT_001283e0;
extern int DAT_001283d0;
extern int DAT_00128218;
extern int DAT_00128234;
extern int DAT_00128238;
extern int DAT_00127060;
extern void *PTR_DAT_00127068;
extern int DAT_00127070;
extern void *PTR_DAT_00127078;

extern char *optarg;
extern int optind;

int
ls_main(int argc, FILE *argv)
{
    char next_char;
    void *compare_ptr;
    byte matched_flag;
    FILE *err_stream;
    ulong width_temp;
    char bool_result;
    undefined1 unused_ret;
    char parse_result;
    byte byte_result;
    int opt, idx, ret;
    int ret2, cmp_result;
    uint format, temp;
    long arg_idx;
    undefined8 *new_node;
    void *tmp_ptr;
    undefined8 msg1;
    undefined8 msg2;
    ulong term_width;
    size_t len;
    size_t *color_rule;
    char *time_format2;
    undefined **option_table;
    long *dir_node;
    size_t *prev_rule;
    char *time_format1;
    undefined *tab_size_ptr;
    undefined8 *time_style_opt;
    undefined *arg9;
    undefined8 *arg10;
    undefined8 arg11;
    char *str_temp;
    long long_temp, choice;
    size_t *rule_iter;
    long in_FS_OFFSET;
    bool human_readable;
    int sort_type;
    int quoting_style;
    char *time_style;
    ulong line_width;
    undefined *tab_size;
    int print_dir_name;
    char *ls_colors_ptr;
    undefined8 parse_result1;
    undefined8 parse_result2;
    char prefix_buf[3];
    long stack_guard;

    stack_guard = *(long *)(in_FS_OFFSET + 0x28);
    FUN_00116460(*(undefined8 *)argv);
    setlocale(6, "");
    bindtextdomain("coreutils", "/usr/share/locale");
    textdomain("coreutils");
    DAT_001271f8 = 2;
    FUN_0011ace0(FUN_0010fe00);
    DAT_00128230 = 0;
    DAT_001282d8 = 1;
    DAT_001283a0 = (long *)0x0;
    line_width = 0xffffffffffffffff;
    tab_size = (undefined *)0xffffffffffffffff;
    sort_type = -1;
    quoting_style = -1;
    print_dir_name = -1;
    format = 0xffffffff;
    human_readable = false;
    time_style = (char *)0x0;
    DAT_00128390 = 0x8000000000000000;
    DAT_00128398 = 0xffffffffffffffff;

parse_options:
    option_table = &PTR_s_all_00126340;
    tab_size_ptr = (undefined *)(ulong)argc;
    parse_result1 = (undefined *)CONCAT44(parse_result1._4_4_, 0xffffffff);
    time_style_opt = &parse_result1;
    opt = getopt_long(tab_size_ptr, argv, "abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1");
    if (opt != -1) {
        if (0x114 < opt + 0x83U) goto invalid_option;
        switch(opt) {
        case 0x31:
            format = (uint)(format != 0);
            break;
        case 0x41:
            DAT_00128310 = 1;
            break;
        case 0x42:
            FUN_00106ce0(&DAT_0011d0ef);
            FUN_00106ce0(&DAT_0011d0ee);
            break;
        case 0x43:
            format = 2;
            break;
        case 0x44:
            arg11 = 0;
            DAT_00128331 = 0;
            DAT_00128338 = 1;
            format = 0;
            break;
        case 0x46:
            if (optarg != (char *)0x0) {
                arg9 = (undefined *)0x1;
                arg10 = time_style_opt;
                long_temp = FUN_0010f1d0("--classify", optarg, &PTR_s_always_00126200, &DAT_0011b680, 4,
                                      PTR_FUN_001271f0, 1, time_style_opt);
                if ((*(int *)(&DAT_0011b680 + long_temp * 4) != 1) &&
                   ((*(int *)(&DAT_0011b680 + long_temp * 4) != 2 || (bool_result = FUN_00106e50(), bool_result == '\0'))))
                break;
            }
            DAT_00128334 = 3;
            break;
        case 0x47:
            DAT_00127028 = 0;
            break;
        case 0x48:
            DAT_00128318 = 2;
            break;
        case 0x49:
            FUN_00106ce0(optarg);
            break;
        case 0x4c:
            DAT_00128318 = 4;
            break;
        case 0x4e:
            quoting_style = 0;
            break;
        case 0x51:
            quoting_style = 5;
            break;
        case 0x52:
            DAT_00128316 = 1;
            break;
        case 0x53:
            sort_type = 3;
            break;
        case 0x54:
            arg9 = (undefined *)dcgettext(0, "invalid tab size", 5);
            tab_size = (undefined *)FUN_0011a200(optarg, 0, 0, 0x7fffffffffffffff, &DAT_0011cf4c, arg9, 2, 0);
            break;
        case 0x55:
            sort_type = 6;
            break;
        case 0x58:
            sort_type = 1;
            break;
        case 0x5a:
            DAT_00128389 = 1;
            break;
        case 0x61:
            DAT_00128310 = 2;
            break;
        case 0x62:
            quoting_style = 7;
            break;
        case 99:
            DAT_00128358 = 1;
            DAT_00128354 = '\x01';
            break;
        case 100:
            DAT_00128315 = '\x01';
            break;
        case 0x66:
            DAT_00128310 = 2;
            sort_type = 6;
            break;
        case 0x67:
            DAT_00127029 = 0;
        case 0x6c:
            format = 0;
            break;
        case 0x68:
            DAT_00128348 = 0xb0;
            DAT_0012833c = 0xb0;
            DAT_00128340 = 1;
            DAT_00127020 = 1;
            break;
        case 0x69:
            DAT_0012831c = 1;
            break;
        case 0x6b:
            human_readable = true;
            break;
        case 0x6d:
            format = 4;
            break;
        case 0x6e:
            DAT_0012834d = 1;
            format = 0;
            break;
        case 0x6f:
            DAT_00127028 = 0;
            format = 0;
            break;
        case 0x70:
            DAT_00128334 = 1;
            break;
        case 0x71:
            print_dir_name = 1;
            break;
        case 0x72:
            DAT_0012834f = 1;
            break;
        case 0x73:
            DAT_0012834c = 1;
            break;
        case 0x74:
            sort_type = 5;
            break;
        case 0x75:
            DAT_00128358 = 2;
            DAT_00128354 = '\x01';
            break;
        case 0x76:
            goto set_sort_version;
        case 0x77:
            line_width = FUN_00106de0(optarg);
            if (line_width == 0xffffffffffffffff) {
                argv = (FILE *)FUN_00118c20(optarg);
                msg1 = dcgettext(0, "invalid line width", 5);
                error(2, 0, "%s: %s", msg1, argv);
set_sort_version:
                sort_type = 4;
            }
            break;
        case 0x78:
            format = 3;
            break;
        case 0x80:
            DAT_0012834e = 1;
            break;
        case 0x81:
            opt = FUN_00113490(optarg, &DAT_00128348, &DAT_00128340);
            if (opt != 0) {
                FUN_0011a470(opt, (ulong)parse_result1 & 0xffffffff, 0, &PTR_s_all_00126340, optarg);
            }
            DAT_0012833c = DAT_00128348;
            DAT_00127020 = DAT_00128340;
            break;
        case 0x82:
            if (optarg == (char *)0x0) {
set_color_always:
                byte_result = 1;
            }
            else {
                arg9 = PTR_FUN_001271f0;
                long_temp = FUN_0010f1d0("--color", optarg, &PTR_s_always_00126200, &DAT_0011b680, 4,
                                      PTR_FUN_001271f0, 1);
                if (*(int *)(&DAT_0011b680 + long_temp * 4) == 1) goto set_color_always;
                byte_result = 0;
                if (*(int *)(&DAT_0011b680 + long_temp * 4) == 2) {
                    byte_result = FUN_00106e50();
                }
            }
            DAT_00128332 = byte_result & 1;
            break;
        case 0x83:
            DAT_00128318 = 3;
            break;
        case 0x84:
            DAT_00128334 = 2;
            break;
        case 0x85:
            arg9 = tab_size_ptr;
            long_temp = FUN_0010f1d0("--format", optarg, &PTR_s_verbose_00126300, &DAT_0011b710, 4,
                                  PTR_FUN_001271f0, 1, tab_size_ptr);
            format = *(uint *)(&DAT_0011b710 + long_temp * 4);
            break;
        case 0x86:
            format = 0;
            time_style = "full-iso";
            break;
        case 0x87:
            DAT_00128314 = 1;
            break;
        case 0x88:
            new_node = (undefined8 *)FUN_00119d00(0x10);
            time_style_opt = DAT_00128300;
            DAT_00128300 = new_node;
            *new_node = optarg;
            new_node[1] = time_style_opt;
            break;
        case 0x89:
            if (optarg == (char *)0x0) {
set_hyperlink_always:
                byte_result = 1;
            }
            else {
                arg9 = (undefined *)0x1;
                arg10 = time_style_opt;
                long_temp = FUN_0010f1d0("--hyperlink", optarg, &PTR_s_always_00126200, &DAT_0011b680, 4,
                                      PTR_FUN_001271f0, 1, time_style_opt);
                if (*(int *)(&DAT_0011b680 + long_temp * 4) == 1) goto set_hyperlink_always;
                byte_result = 0;
                if (*(int *)(&DAT_0011b680 + long_temp * 4) == 2) {
                    byte_result = FUN_00106e50();
                }
            }
            DAT_00128331 = byte_result & 1;
            break;
        case 0x8a:
            arg9 = PTR_FUN_001271f0;
            long_temp = FUN_0010f1d0("--indicator-style", optarg, &PTR_DAT_001268e0, "", 4, PTR_FUN_001271f0, 1,
                                  option_table);
            DAT_00128334 = *(uint *)("lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl" +
                                  long_temp * 4 + 0x30);
            break;
        case 0x8b:
            arg9 = PTR_FUN_001271f0;
            long_temp = FUN_0010f1d0("--quoting-style", optarg, &PTR_s_literal_001269a0, &DAT_00120220, 4,
                                  PTR_FUN_001271f0, 1, arg11);
            quoting_style = *(int *)(&DAT_00120220 + long_temp * 4);
            break;
        case 0x8c:
            goto set_zero_and_literal;
        case 0x8d:
            DAT_00128348 = 0x90;
            DAT_0012833c = 0x90;
            DAT_00128340 = 1;
            DAT_00127020 = 1;
            break;
        case 0x8e:
            arg9 = PTR_FUN_001271f0;
            long_temp = FUN_0010f1d0("--sort", optarg, &DAT_001262c0, &DAT_0011b6f0, 4, PTR_FUN_001271f0, 1,
                                  (long)&switchD_00104d37::switchdataD_0011b174 +
                                  (long)(int)(&switchD_00104d37::switchdataD_0011b174)[opt + 0x83U]);
            sort_type = *(int *)(&DAT_0011b6f0 + long_temp * 4);
            break;
        case 0x8f:
            arg11 = 1;
            arg9 = PTR_FUN_001271f0;
            long_temp = FUN_0010f1d0("--time", optarg, &DAT_00126260, &DAT_0011b6c0, 4, PTR_FUN_001271f0, 1, arg10);
            DAT_00128354 = '\x01';
            DAT_00128358 = *(undefined4 *)(&DAT_0011b6c0 + long_temp * 4);
            break;
        case 0x90:
            goto set_time_style_opt;
        case 0x91:
            DAT_00127019 = '\0';
            arg10 = (undefined8 *)0x0;
            DAT_00128332 = 0;
            format = (uint)(format != 0);
            quoting_style = 0;
set_zero_and_literal:
            print_dir_name = 0;
            break;
        case -0x83:
            msg1 = FUN_00116520("David MacKenzie", "David MacKenzie");
            msg2 = FUN_00116520("Richard M. Stallman", "Richard M. Stallman");
            str_temp = "ls";
            if ((DAT_001271e0 != 1) && (str_temp = "vdir", DAT_001271e0 == 2)) {
                str_temp = "dir";
            }
            FUN_00119b30(stdout, str_temp, "GNU coreutils", PTR_DAT_001271e8, msg2, msg1, 0, arg9);
            exit(0);
        case -0x82:
            goto print_help;
        default:
            goto invalid_option;
        }
        goto parse_options;
    }
    if (DAT_00128340 == 0) {
        str_temp = getenv("LS_BLOCK_SIZE");
        FUN_00113490(str_temp, &DAT_00128348, &DAT_00128340);
        if ((str_temp != (char *)0x0) || (str_temp = getenv("BLOCK_SIZE"), str_temp != (char *)0x0)) {
            DAT_0012833c = DAT_00128348;
            DAT_00127020 = DAT_00128340;
        }
        if (human_readable) {
            DAT_00128340 = 0x400;
            DAT_00128348 = 0;
        }
    }
    if ((int)format < 0) {
        if (DAT_001271e0 == 1) goto default_format_ls;
        format = (uint)(DAT_001271e0 == 2) * 2;
    }
    do {
        term_width = line_width;
        DAT_0012835c = format;
        width_temp = line_width;
        if ((format - 2 < 3) || (DAT_00128332 != 0)) {
            if (line_width == 0xffffffffffffffff) {
                bool_result = FUN_00106e50();
                if ((bool_result != '\0') && (ret = ioctl(1, 0x5413, &parse_result1), -1 < ret)) {
                    term_width = (ulong)parse_result1._2_2_;
                    width_temp = term_width;
                    if (parse_result1._2_2_ != 0) goto got_width;
                }
                str_temp = getenv("COLUMNS");
                if ((str_temp != (char *)0x0) && (*str_temp != '\0')) {
                    line_width = FUN_00106de0(str_temp);
                    term_width = line_width;
                    width_temp = line_width;
                    if (line_width != 0xffffffffffffffff) goto got_width;
                    msg1 = FUN_00118c20(str_temp);
                    msg2 = dcgettext(0, "ignoring invalid width in environment variable COLUMNS: %s", 5);
                    error(0, 0, msg2, msg1);
                }
default_width:
                term_width = 0x50;
                width_temp = line_width;
            }
        }
        else if (line_width == 0xffffffffffffffff) goto default_width;
got_width:
        line_width = width_temp;
        DAT_00128220 = (term_width / 3 + 1) - (ulong)(term_width % 3 == 0);
        DAT_001282d0 = term_width;
        tab_size_ptr = DAT_001282e0;
        if ((DAT_0012835c - 2 < 3) && (tab_size_ptr = tab_size, (long)tab_size < 0)) {
            DAT_001282e0 = (undefined *)0x8;
            str_temp = getenv("TABSIZE");
            tab_size_ptr = DAT_001282e0;
            if ((str_temp != (char *)0x0) &&
               (ret = FUN_0011a540(str_temp, 0, 0, &parse_result1, &DAT_0011cf4c), tab_size_ptr = parse_result1, ret != 0)
               ) {
                msg1 = FUN_00118c20(str_temp);
                msg2 = dcgettext(0, "ignoring invalid tab size in environment variable TABSIZE: %s", 5);
                error(0, 0, msg2, msg1);
                tab_size_ptr = DAT_001282e0;
            }
        }
        DAT_001282e0 = tab_size_ptr;
        byte_result = (byte)print_dir_name & 1;
        if ((print_dir_name == -1) && (byte_result = 0, DAT_001271e0 == 1)) {
            byte_result = FUN_00106e50();
        }
        DAT_001282f8 = byte_result;
        if (quoting_style < 0) {
            str_temp = getenv("QUOTING_STYLE");
            if (str_temp == (char *)0x0) goto default_quoting;
            ret = FUN_0010ee80(str_temp, &PTR_s_literal_001269a0, &DAT_00120220, 4);
            if (ret < 0) goto invalid_quoting;
            quoting_style = *(int *)(&DAT_00120220 + (long)ret * 4);
            if (quoting_style < 0) goto default_quoting;
        }
set_quoting:
        FUN_00118160(0, quoting_style);
        while (true) {
            temp = FUN_00118140(0);
            if (((DAT_0012835c == 0) || ((DAT_0012835c - 2 < 2 && (DAT_001282d0 != 0)))) && (temp < 7))
            {
                if ((0x4aUL >> ((ulong)temp & 0x3f) & 1) == 0) {
                    DAT_001283c8 = 0;
                    DAT_001282f0 = FUN_00118100(0);
                }
                else {
                    DAT_001283c8 = 1;
                    DAT_001282f0 = FUN_00118100(0);
                }
            }
            else {
                DAT_001283c8 = 0;
                DAT_001282f0 = FUN_00118100(0);
                if (temp == 7) {
                    FUN_00118180(DAT_001282f0, 0x20, 1);
                }
            }
            if (1 < DAT_00128334) {
                str_temp = &DAT_0011d1ab + (DAT_00128334 - 2);
                bool_result = (&DAT_0011d1ab)[DAT_00128334 - 2];
                while (bool_result != '\0') {
                    str_temp = str_temp + 1;
                    FUN_00118180(DAT_001282f0, (int)bool_result, 1);
                    bool_result = *str_temp;
                }
            }
            DAT_001282e8 = FUN_00118100(0);
            FUN_00118180(DAT_001282e8, 0x3a, 1);
            DAT_00128338 = (DAT_00128331 ^ 1) & DAT_0012835c == 0 & DAT_00128338;
            if ((int)(uint)DAT_00128338 <= (int)DAT_00127019) break;
incompatible_options:
            msg1 = dcgettext(0, "--dired and --zero are incompatible", 5);
            error(2, 0, msg1);
invalid_quoting:
            msg1 = FUN_00118c20();
            msg2 = dcgettext(0, "ignoring invalid value of environment variable QUOTING_STYLE: %s", 5);
            error(0, 0, msg2, msg1);
default_quoting:
            quoting_style = 7;
            if (DAT_001271e0 != 1) goto set_quoting;
            bool_result = FUN_00106e50();
            if (bool_result != '\0') goto set_quoting_shell;
        }
        if (sort_type < 0) {
            if (DAT_0012835c == 0) {
                DAT_00128350 = 0;
                goto set_time_style;
            }
            if (DAT_00128354 == '\0') {
                DAT_00128350 = 0;
            }
            else {
                DAT_00128350 = 5;
            }
            goto setup_done;
        }
        DAT_00128350 = sort_type;
        if (DAT_0012835c != 0) goto setup_done;
set_time_style:
        if ((time_style == (char *)0x0) && (time_style = getenv("TIME_STYLE"), time_style == (char *)0x0)) {
            time_style = "locale";
        }
        else {
            while (ret = strncmp(time_style, "posix-", 6), ret == 0) {
                bool_result = FUN_00111400(2);
                if (bool_result == '\0') goto setup_done;
                time_style = time_style + 6;
            }
        }
        if (*time_style == '+') {
            str_temp = time_style + 1;
            time_format2 = strchr(str_temp, 10);
            time_format1 = str_temp;
            if (time_format2 != (char *)0x0) {
                time_format1 = strchr(time_format2 + 1, 10);
                if (time_format1 != (char *)0x0) {
                    argv = (FILE *)FUN_00118c20(str_temp);
                    msg1 = dcgettext(0, "invalid time style format %s", 5);
                    error(2, 0, msg1, argv);
                    goto incompatible_options;
                }
                *time_format2 = '\0';
                time_format1 = time_format2 + 1;
            }
            goto set_time_format;
        }
        option_table = &PTR_s_full_iso_00126920;
        long_temp = FUN_0010ee80(time_style, &PTR_s_full_iso_00126920, &DAT_0011b7c0, 4);
        if (-1 < long_temp) goto got_time_style;
        argc = 0x11d1fa;
        FUN_0010f000("time style", time_style, long_temp);
        err_stream = stderr;
        str_temp = (char *)dcgettext(0, "Valid arguments are:\n", 5);
        fputs_unlocked(str_temp, err_stream);
        for (; argv = stderr, *option_table != (undefined *)0x0; option_table = option_table + 1) {
            __fprintf_chk(stderr, 1, "  - [posix-]%s\n");
        }
        str_temp = (char *)dcgettext(0, "  - +FORMAT (e.g., +%H:%M) for a \'date\'-style format\n", 5);
        fputs_unlocked(str_temp, argv);
invalid_option:
        FUN_0010e360();
print_help:
        FUN_0010e360(0);
default_format_ls:
        byte_result = FUN_00106e50();
        format = byte_result + 1;
    } while (true);

set_time_style_opt:
    time_style = optarg;
    goto parse_options;

got_time_style:
    if (long_temp == 2) {
        PTR_DAT_00127040 = s__Y__m__d_0011d231;
        PTR_s__b__e__H__M_00127048 = &DAT_0011d225;
        str_temp = PTR_DAT_00127040;
        time_format2 = PTR_s__b__e__H__M_00127048;
    }
    else if (long_temp < 3) {
        if (long_temp == 0) {
            PTR_DAT_00127040 = s__Y__m__d__H__M__S__N__z_0011d20a;
            PTR_s__b__e__H__M_00127048 = s__Y__m__d__H__M__S__N__z_0011d20a;
            str_temp = PTR_DAT_00127040;
            time_format2 = PTR_s__b__e__H__M_00127048;
        }
        else {
            PTR_DAT_00127040 = &DAT_0011d222;
            PTR_s__b__e__H__M_00127048 = &DAT_0011d222;
            str_temp = PTR_DAT_00127040;
            time_format2 = PTR_s__b__e__H__M_00127048;
        }
    }
    else {
        str_temp = PTR_DAT_00127040;
        time_format2 = PTR_s__b__e__H__M_00127048;
        if ((long_temp == 3) &&
           (bool_result = FUN_00111400(2), str_temp = PTR_DAT_00127040, time_format2 = PTR_s__b__e__H__M_00127048,
           bool_result != '\0')) {
            PTR_DAT_00127040 = (undefined *)dcgettext(0, PTR_DAT_00127040, 2);
            time_format2 = (char *)dcgettext(0, PTR_s__b__e__H__M_00127048, 2);
            str_temp = PTR_DAT_00127040;
        }
    }
set_time_format:
    PTR_s__b__e__H__M_00127048 = time_format2;
    PTR_DAT_00127040 = str_temp;
    FUN_00106e80();
setup_done:
    byte_result = DAT_00128332;
    idx = optind;
    if (DAT_00128332 == 0) goto no_color;
    ls_colors_ptr = getenv("LS_COLORS");
    if ((ls_colors_ptr != (char *)0x0) && (*ls_colors_ptr != '\0')) {
        DAT_00128320 = (undefined *)FUN_0011a180(ls_colors_ptr);
        parse_result1 = DAT_00128320;
        goto parse_ls_colors;
    }
    str_temp = getenv("COLORTERM");
    if ((str_temp != (char *)0x0) && (*str_temp != '\0')) goto color_setup_done;
    str_temp = getenv("TERM");
    if ((str_temp == (char *)0x0) || (*str_temp == '\0')) goto disable_color;
    time_format1 = "# Configuration file for dircolors, a utility to help you set the";
    goto match_term;

parse_ls_colors:
    str_temp = ls_colors_ptr;
    bool_result = *ls_colors_ptr;
    if (bool_result == '*') {
        color_rule = (size_t *)FUN_00119d00(0x30);
            *(undefined1 *)(color_rule + 4) = 0;
        ls_colors_ptr = str_temp + 1;
        color_rule[5] = (size_t)DAT_00128328;
        color_rule[1] = (size_t)parse_result1;
        DAT_00128328 = color_rule;
        bool_result = FUN_00106920(&parse_result1, &ls_colors_ptr, 1, color_rule);
        str_temp = ls_colors_ptr;
        if ((bool_result == '\0') || (str_temp = ls_colors_ptr + 1, *ls_colors_ptr != '=')) goto ls_colors_error;
        color_rule[3] = (size_t)parse_result1;
        ls_colors_ptr = ls_colors_ptr + 1;
        bool_result = FUN_00106920(&parse_result1, &ls_colors_ptr, 0, color_rule + 2);
        str_temp = ls_colors_ptr;
        if (bool_result == '\0') goto ls_colors_error;
        goto parse_ls_colors;
    }
    if (bool_result == ':') {
        ls_colors_ptr = ls_colors_ptr + 1;
    }
    else {
        if (bool_result == '\0') {
            color_rule = DAT_00128328;
            if (DAT_00128328 != (size_t *)0x0) {
                while (prev_rule = color_rule, color_rule = (size_t *)prev_rule[5], color_rule != (size_t *)0x0) {
                    matched_flag = 0;
                    rule_iter = color_rule;
                    do {
                        len = *rule_iter;
                        if ((len != 0xffffffffffffffff) && (len == *prev_rule)) {
                            tmp_ptr = (void *)rule_iter[1];
                            compare_ptr = (void *)prev_rule[1];
                            ret2 = memcmp(compare_ptr, tmp_ptr, len);
                            if (ret2 == 0) {
                                *rule_iter = 0xffffffffffffffff;
                            }
                            else {
                                ret2 = FUN_0010f3c0(compare_ptr, tmp_ptr, len);
                                if (ret2 == 0) {
                                    if ((matched_flag == 0) &&
                                       ((prev_rule[2] != rule_iter[2] ||
                                        (ret2 = memcmp((void *)prev_rule[3], (void *)rule_iter[3], prev_rule[2]), ret2 != 0)
                                        ))) {
                                        *(undefined1 *)(prev_rule + 4) = 1;
                                        *(undefined1 *)(rule_iter + 4) = 1;
                                    }
                                    else {
                                        *rule_iter = 0xffffffffffffffff;
                                        matched_flag = byte_result;
                                    }
                                }
                            }
                        }
                        rule_iter = (size_t *)rule_iter[5];
                    } while (rule_iter != (size_t *)0x0);
                }
            }
            goto ls_colors_parsed;
        }
        next_char = ls_colors_ptr[1];
        str_temp = ls_colors_ptr + 1;
        if ((next_char == '\0') || (str_temp = ls_colors_ptr + 3, ls_colors_ptr[2] != '=')) goto ls_colors_error;
        long_temp = 0;
        while ((ls_colors_ptr = str_temp,
               bool_result != "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"[long_temp * 2] ||
               (next_char != "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"[long_temp * 2 + 1]))) {
            long_temp = long_temp + 1;
            if (long_temp == 0x18) goto ls_colors_unrecognized;
        }
        (&PTR_DAT_00127068)[(long)(int)long_temp * 2] = parse_result1;
        parse_result = FUN_00106920(&parse_result1, &ls_colors_ptr, 0);
        if (parse_result == '\0') goto ls_colors_unrecognized;
    }
    goto parse_ls_colors;

match_term:
    if ((char *)0x15ef < time_format1 + -0x11b900) goto disable_color;
    ret2 = strncmp(time_format1, "TERM ", 5);
    if ((ret2 == 0) && (ret2 = fnmatch(time_format1 + 5, str_temp, 0), ret2 == 0)) goto color_setup_done;
    len = strlen(time_format1);
    time_format1 = time_format1 + len + 1;
    goto match_term;

disable_color:
    DAT_00128332 = 0;
    goto color_setup_done;

set_quoting_shell:
    quoting_style = 3;
    goto set_quoting;

ls_colors_unrecognized:
    prefix_buf[2] = 0;
    prefix_buf[0] = bool_result;
    prefix_buf[1] = next_char;
    msg1 = FUN_00118c20(prefix_buf);
    msg2 = dcgettext(0, "unrecognized prefix: %s", 5);
    error(0, 0, msg2, msg1);
    str_temp = ls_colors_ptr;
ls_colors_error:
    ls_colors_ptr = str_temp;
    msg1 = dcgettext(0, "unparsable value for LS_COLORS environment variable", 5);
    error(0, 0, msg1);
    free(DAT_00128320);
    color_rule = DAT_00128328;
    while (color_rule != (size_t *)0x0) {
        prev_rule = (size_t *)color_rule[5];
        free(color_rule);
        color_rule = prev_rule;
    }
    DAT_00128332 = 0;
ls_colors_parsed:
    if ((DAT_001270d0 == 6) && (ret2 = strncmp(PTR_DAT_001270d8, "target", 6), ret2 == 0)) {
        DAT_001283b0 = '\x01';
    }
color_setup_done:
    if (DAT_00128332 == 0) {
no_color:
        if (DAT_00128314 != 0) goto set_print_inode;
    }
    else {
        DAT_001282e0 = (undefined *)0x0;
        if ((((DAT_00128314 != 0) || (bool_result = FUN_001068c0(0xd), bool_result != '\0')) ||
            ((bool_result = FUN_001068c0(0xe), bool_result != '\0' && (DAT_001283b0 != '\0')))) ||
           ((bool_result = FUN_001068c0(0xc), bool_result != '\0' && (DAT_0012835c == 0)))) {
set_print_inode:
            DAT_0012831d = 1;
        }
    }
    long_temp = (long)idx;
    if ((((DAT_00128318 == 0) && (DAT_00128318 = 1, DAT_00128315 == '\0')) && (DAT_00128334 != 3)) &&
       (DAT_0012835c != 0)) {
        DAT_00128318 = 3;
    }
    if (DAT_00128316 != 0) {
        DAT_001283e8 = FUN_00111e30(0x1e, 0, FUN_00106880, FUN_00106890, free);
        if (DAT_001283e8 == 0) {
            FUN_0011a1c0();
        }
        FUN_001161c0(&DAT_00128100, 0, 0, malloc, free);
    }
    str_temp = getenv("TZ");
    DAT_001282c8 = FUN_00119090(str_temp);
    DAT_001282c2 = DAT_0012834c | DAT_00128331 | DAT_00128389 | DAT_0012835c == 0 |
                   (DAT_00128350 - 3U & 0xfffffffd) == 0;
    DAT_001282c1 = (DAT_00128389 | DAT_00128316 | DAT_00128332 | DAT_00128314 | DAT_00128334 != 0) &
                   (DAT_001282c2 ^ 1);
    unused_ret = 0;
    if (DAT_00128332 != 0) {
        unused_ret = FUN_001068c0(0x15);
    }
    DAT_001282c0 = unused_ret;
    if (DAT_00128338 != 0) {
        FUN_001161c0(&DAT_001281c0, 0, 0, malloc, free);
        FUN_001161c0(&DAT_00128160, 0, 0, malloc, free);
    }
    if (DAT_00128331 != 0) {
        term_width = 0;
        do {
            while (ret2 = (int)term_width, term_width < 0x5b) {
                if (((term_width < 0x41) && (9 < ret2 - 0x30U)) && (1 < ret2 - 0x2dU)) {
                    term_width = term_width + 1;
                }
                else {
                    (&DAT_00128000)[term_width] = (&DAT_00128000)[term_width] | 1;
                    term_width = term_width + 1;
                }
            }
            human_readable = true;
            if ((0x19 < ret2 - 0x61U) && (term_width != 0x7e)) {
                human_readable = ret2 == 0x5f;
            }
            (&DAT_00128000)[term_width] = (&DAT_00128000)[term_width] | human_readable;
            term_width = term_width + 1;
        } while (term_width != 0x100);
        DAT_001283a8 = (undefined *)FUN_0011a360();
        if (DAT_001283a8 == (undefined *)0x0) {
            DAT_001283a8 = &DAT_0011cf4c;
        }
    }
    DAT_001283d8 = 100;
    DAT_001283e0 = FUN_00119d00(0x5140);
    idx = argc - idx;
    DAT_001283d0 = 0;
    FUN_001087c0();
    if (idx < 1) {
        if (DAT_00128315 == '\0') {
            FUN_001071c0(&DAT_0011d277, 0, 1);
        }
        else {
            FUN_0010ca80(&DAT_0011d277, 3, 1, 0);
        }
        if (DAT_001283d0 != 0) goto process_dirs;
no_args_done:
        if (DAT_001283a0 == (long *)0x0) goto cleanup;
        dir_node = DAT_001283a0;
        if (DAT_001283a0[3] == 0) {
            DAT_001282d8 = 0;
        }
    }
    else {
        do {
            arg_idx = long_temp * 2;
            long_temp = long_temp + 1;
            FUN_0010ca80(*(undefined8 *)(&argv->_flags + arg_idx), 0, 1, 0);
        } while ((int)long_temp < (int)argc);
        if (DAT_001283d0 == 0) {
args_no_dirs:
            if (1 < idx) goto process_dir_list;
            goto no_args_done;
        }
process_dirs:
        FUN_00108e30();
        if (DAT_00128315 == '\0') {
            FUN_00109530(0, 1);
        }
        if (DAT_001283d0 == 0) goto args_no_dirs;
        FUN_0010c650();
        if (DAT_001283a0 == (long *)0x0) goto cleanup;
        DAT_00128218 = DAT_00128218 + 1;
        str_temp = stdout->_IO_write_ptr;
        if (stdout->_IO_write_end <= str_temp) {
            __overflow(stdout, 10);
            goto process_dir_list;
        }
        stdout->_IO_write_ptr = str_temp + 1;
        *str_temp = '\n';
        dir_node = DAT_001283a0;
    }
    do {
        DAT_001283a0 = (long *)dir_node[3];
        if ((DAT_001283e8 == 0) || (*dir_node != 0)) {
            FUN_0010dc80(*dir_node, dir_node[1], (char)dir_node[2]);
            free((void *)*dir_node);
            free((void *)dir_node[1]);
            free(dir_node);
            DAT_001282d8 = 1;
        }
        else {
            if ((ulong)(DAT_00128118 - _DAT_00128110) < 0x10) {
                __assert_fail("dev_ino_size <= __extension__ ({ struct obstack const *__o = (&dev_ino_obstack); (size_t) (__o->next_free - __o->object_base); })",
                              "src/ls.c", 0x442, "dev_ino_pop");
            }
            parse_result1 = *(undefined **)(DAT_00128118 + -0x10);
            parse_result2 = *(undefined8 *)(DAT_00128118 + -8);
            DAT_00128118 = DAT_00128118 + -0x10;
            tmp_ptr = (void *)FUN_00112530(DAT_001283e8, &parse_result1);
            if (tmp_ptr == (void *)0x0) {
                __assert_fail("found", "src/ls.c", 0x73d, "main");
            }
            free(tmp_ptr);
            free((void *)*dir_node);
            free((void *)dir_node[1]);
            free(dir_node);
        }
process_dir_list:
        dir_node = DAT_001283a0;
    } while (DAT_001283a0 != (long *)0x0);
cleanup:
    if ((DAT_00128332 != 0) && (DAT_00128330 != '\0')) {
        if ((DAT_00127060 != 2) ||
           (((*(short *)PTR_DAT_00127068 != 0x5b1b || (DAT_00127070 != 1)) || (*PTR_DAT_00127078 != 'm')
            ))) {
            FUN_00107990(&DAT_00127060);
            FUN_00107990(&DAT_00127070);
        }
        fflush_unlocked(stdout);
        FUN_001077e0(0);
        for (idx = DAT_00128234; idx != 0; idx = idx + -1) {
            raise(0x13);
        }
        if (DAT_00128238 != 0) {
            raise(DAT_00128238);
        }
    }
    if (DAT_00128338 != 0) {
        FUN_00107670("//DIRED//", &DAT_001281c0);
        FUN_00107670("//SUBDIRED//", &DAT_00128160);
        temp = FUN_00118140(DAT_001282f0);
        __printf_chk(1, "//DIRED-OPTIONS// --quoting-style=%s\n", (&PTR_s_literal_001269a0)[temp]);
    }
    long_temp = DAT_001283e8;
    if (DAT_001283e8 != 0) {
        arg_idx = FUN_00111900(DAT_001283e8);
        if (arg_idx != 0) {
            __assert_fail("hash_get_n_entries (active_dir_set) == 0", "src/ls.c", 0x771, "main");
        }
        FUN_00111ff0(long_temp);
    }
    if (stack_guard != *(long *)(in_FS_OFFSET + 0x28)) {
        __stack_chk_fail();
    }
    return DAT_00128230;
}
