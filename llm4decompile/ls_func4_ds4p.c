/*
 * GNU coreutils ls — main() 函数
 *
 * 功能: 解析命令行选项、环境变量，然后列出目录内容。
 *
 * 符号对应关系:
 *   FUN_00104c00   → main
 *   FUN_00116460   → flockfile          (锁定 stdout)
 *   FUN_0011ace0   → atexit            (注册退出回调)
 *   FUN_0010fe00   → close_stdout       (退出时关闭 stdout)
 *   FUN_00106ce0   → ignore_list_add    (向忽略列表追加 pattern)
 *   FUN_00106e50   → isatty             (判断 stdout 是否为终端)
 *   FUN_00106de0   → strtoul            (字符串→ulong)
 *   FUN_00118c20   → quotearg_n         (生成用于错误信息的引用串)
 *   FUN_0010f1d0   → XARGMATCH          (参数名→枚举值匹配)
 *   FUN_0010ee80   → XARGMATCH 变体     (字符串匹配)
 *   FUN_00113490   → human_options      (解析 human-readable 大小)
 *   FUN_0011a540   → xstrtoumax         (字符串→uintmax)
 *   FUN_0011a200   → xdectoumax         (带范围检查的字符串→uintmax)
 *   FUN_00118160   → set_quoting_style
 *   FUN_00118140   → get_quoting_style
 *   FUN_00118100   → init_output_buf    (初始化输出字符串缓冲区)
 *   FUN_00118180   → output_buf_addchar (向输出缓冲区追加字符)
 *   FUN_00111400   → locale_support     (检查 locale 是否可用)
 *   FUN_00119d00   → xmalloc
 *   FUN_00119e00   → xcalloc
 *   FUN_00119b30   → version_etc        (输出版本信息)
 *   FUN_00116520   → author_name        (格式化作者姓名)
 *   FUN_0010ca80   → process_file       (处理文件/目录参数)
 *   FUN_001071c0   → list_current_dir   (列出当前目录, 无参数时默认)
 *   FUN_001087c0   → init_file_array    (初始化文件列表)
 *   FUN_00108e30   → sort_files
 *   FUN_00109530   → print_files
 *   FUN_0010c650   → print_total
 *   FUN_00106920   → parse_LS_COLORS    (解析 LS_COLORS 中的一个字段)
 *   FUN_0011a180   → xstrdup
 *   FUN_0010f000   → argmatch_invalid   (报错: 无效参数)
 *   FUN_0010e360   → usage              (输出用法并退出)
 *   FUN_0011a470   → die                (报错退出)
 *   FUN_0011a1c0   → xalloc_die         (内存耗尽)
 *   FUN_0010dc80   → print_file_entry   (输出单个文件条目)
 *   FUN_00111e30   → hash_initialize
 *   FUN_001161c0   → obstack_init
 *   FUN_00111900   → hash_get_n_entries
 *   FUN_00111ff0   → hash_free
 *   FUN_00112530   → hash_delete
 *   FUN_00119090   → xstrdup            (来自 func2)
 *   FUN_00106880   → dev_ino_hash       (设备号+inode 哈希函数)
 *   FUN_00106890   → dev_ino_compare    (设备号+inode 比较函数)
 *   FUN_00107670   → write_dired        (输出 dired 信息)
 *   FUN_001077e0   → restore_terminal   (恢复终端颜色)
 *   FUN_00107990   → reset_color        (重置颜色属性)
 *   FUN_001068c0   → has_capability     (检查终端能力)
 *   FUN_00106e80   → init_time_format   (初始化时间格式)
 *
 * 核心全局变量:
 *   DAT_001271f8 / DAT_00128230 → exit_status
 *   DAT_001271e0 → program_mode    (1=ls, 2=dir)
 *   DAT_0012835c → format           (输出格式: 0默认 1长格式 2...)
 *   DAT_00128318 → listing_format   长格式子类型
 *   DAT_00128334 → indicator_style  指示符样式
 *   DAT_00128310 → sort_type
 *   DAT_00128332 → print_color      是否彩色输出
 *   DAT_00128314 → print_with_color 强制彩色
 *   DAT_00128315 → immediate_dirs   立即列出目录
 *   DAT_00128316 → recursive
 *   DAT_00128331 → hyperlink        超链接输出
 *   DAT_00128338 → dired            Emacs dired 模式
 *   DAT_0012831d → color_enabled    颜色功能已启用
 *   DAT_00128340 → block_size       块大小
 *   DAT_00128348 → human_output_opts 人类可读选项
 *   DAT_0012833c → output_block_size 输出块大小
 *   DAT_00128350 → time_type        排序时间类型
 *   DAT_00128354 → use_time_flag
 *   DAT_00128358 → time_style
 *   DAT_001283a0 → file_queue       待处理文件队列(链表)
 *   DAT_001283a8 → hostname         本机主机名(超链接用)
 *   DAT_001283e8 → active_dir_set   活动目录哈希表(递归用)
 *   DAT_001282d0 → line_length      行宽
 *   DAT_00128220 → max_idx          列索引上限
 *   DAT_001282e0 → tab_size
 *   DAT_001282f0 → quoting_prefix   引用前缀输出缓冲
 *   DAT_001282e8 → quoting_sep      引用分隔符(":")
 *   DAT_001282f8 → zero_flag        --zero 标志
 *   DAT_001283c8 → hide_sep         隐藏分隔符标志
 *   DAT_001283d0 → files_processed  已处理的文件计数
 *   DAT_001283d8 → init_buf_size    初始缓冲区大小(=100)
 *   DAT_001283e0 → file_array       文件列表数组
 *   DAT_001282c0 / _c1 / _c2 → 标志组
 *   DAT_00128100 → dev_ino_obstack
 *   DAT_001281c0 → dired_obstack
 *   DAT_00128160 → subdired_obstack
 *   DAT_00128000 → url_escape_tab    URL 转义字符表
 *   DAT_00127040 / _27048 → long_time_format / regular_time_format
 *   DAT_00127020 → human_output_opts 备份
 *   DAT_00128389 → print_inode
 *   DAT_0012834c → print_block_size
 *   DAT_0012834d → numeric_ids
 *   DAT_0012834e → print_owner
 *   DAT_0012834f → print_group
 *   DAT_0012831c → print_inode
 *   DAT_001283b0 → target_indicator
 *   DAT_00128300 → ignore_patterns  (忽略模式链表头)
 *   DAT_00128320 → LS_COLORS_str    (xstrdup of LS_COLORS)
 *   DAT_00128328 → LS_COLORS_ext_list (扩展链表)
 *   DAT_00127028 → print_group_before_name
 *   DAT_00127029 → no_group
 *   DAT_00128218 → count
 *   DAT_00128234 → signal_count
 *   DAT_00128238 → signal_num
 *   DAT_001270d8 → color_indicator_name
 *   DAT_001270d0 → len
 *   PTR_DAT_00127068 → color_indicator_values[]
 *   DAT_00127060 → left_code
 *   DAT_00127070 → right_code
 *   DAT_00127078 → type_indicator
 *   DAT_001271f0 → argmatch_die (回调)
 *   DAT_00128330 → color_initialized
 *   DAT_00127019 → check_dired_flag
 *   DAT_00128398 → ?
 *   DAT_00128390 → ?
 *   DAT_0011cf4c → "" (空字符串常量)
 *   DAT_0011d277 → "." (当前目录)
 *   DAT_0011d0ef / _1d0ee → 忽略 pattern 字符串
 *   DAT_0011d1ab → 指示符样式字符串表
 *
 * 局部变量:
 *   local_40 → stack_canary  (栈金丝雀)
 *   local_90 → sort_type     排序类型
 *   local_8c → quoting_style 引用风格
 *   local_88 → time_style_str 时间格式字符串
 *   local_80 → line_width    行宽
 *   local_78 → tab_size_val  tab 大小值
 *   local_70 → zero         --zero 选项
 *   local_60 → lscolors     LS_COLORS 字符串(工作指针)
 *   local_58 → winsize / tmp (winsize 结构体 / 临时值)
 */

int
main(uint argc, char *argv[])
{
    int      opt;             /* iVar8   — getopt_long 返回值 */
    uint     format;          /* uVar10  — 输出格式 */
    uint     sort_type;       /* local_90 */
    int      quoting_style;   /* local_8c */
    char    *time_style_str;  /* local_88 */
    ulong    line_width;      /* local_80, uVar16, uVar3 */
    void    *tab_size_val;    /* local_78 */
    int      zero;            /* local_70 */
    char    *lscolors;        /* local_60 */
    long     stack_canary;    /* local_40 */

    struct winsize {
        ushort ws_row;
        ushort ws_col;
        /* ... */
    } winsize;                /* local_58 */
    ulong   uStack_50;

    /* LS_COLORS 解析用临时变量 */
    char     prefix_ch0;      /* local_44 */
    char     prefix_ch1;      /* local_43 */
    char     prefix_nul;      /* local_42 */

    /* 其他 */
    char    cVar1;            /* cVar1 */
    void   *s1;               /* __s1 */
    byte    bVar2;            /* bVar2 */
    FILE   *stream;           /* __stream */
    char    cVar4;            /* cVar4 */
    char    cVar6;            /* cVar6 */
    byte    bVar7;            /* bVar7 */
    int     iVar8, iVar9;     /* iVar8, iVar9 */
    long    lVar11, lVar26;   /* lVar11, lVar26 */
    void   *puVar12;          /* puVar12 */
    void   *pvVar13;          /* pvVar13 */
    char   *pcVar19, *pcVar22, *pcVar25;
    void   *puVar23, *puVar24;
    void  **ppuVar20;
    long   *file_ptr;         /* __ptr   — file_queue 节点指针 */
    size_t *psVar18;          /* psVar18 */
    size_t *psVar21, *psVar27;
    size_t  sVar17;           /* sVar17 */
    ulong   uVar16;           /* uVar16 */
    ulong   uVar3;            /* uVar3 */
    bool    bVar28;           /* bVar28 */
    char    uVar5;            /* uVar5 */

    /* undefined8 (64-bit) 临时变量 */
    ulong   uVar14, uVar15;   /* uVar14, uVar15 (对应 dcgettext/quotearg 返回值) */

    /* ================================================================ */
    /*  1. 初始化                                                        */
    /* ================================================================ */

    stack_canary = *(long *)(FS_OFFSET + 0x28);   /* 栈保护金丝雀 */

    flockfile(*(ulong *)stdout);                   /* FUN_00116460 */
    setlocale(LC_ALL, "");
    bindtextdomain("coreutils", "/usr/share/locale");
    textdomain("coreutils");

    exit_status       = 2;                         /* DAT_001271f8 */
    atexit(close_stdout);                          /* FUN_0011ace0(FUN_0010fe00) */
    DAT_00128230       = 0;
    DAT_001282d8       = 1;
    file_queue         = NULL;                     /* DAT_001283a0 */
    line_width         = -1;
    tab_size_val       = (void *)-1;
    sort_type          = -1;
    quoting_style      = -1;
    zero               = -1;
    format             = -1;
    bVar28             = false;
    time_style_str     = NULL;
    DAT_00128390       = 0x8000000000000000;
    DAT_00128398       = -1;

    /* ================================================================ */
    /*  2. 解析命令行选项 (getopt_long)                                   */
    /* ================================================================ */

opt_loop:
    ppuVar20           = &all_args_ptr;            /* PTR_s_all_00126340 */
    puVar23            = (void *)(ulong)argc;
    *(uint *)((char *)&winsize + 4) = -1;           /* winsize 高 32 位置 -1 */
    puVar24            = &winsize;

    opt = getopt_long(argc, argv,
                      "abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1");
    if (opt == -1)
        goto post_options;

    /* 长选项值域检测 (opt + 0x83 > 0x114 → 非法) */
    if (0x114 < (uint)(opt + 0x83))
        goto usage_error;

    switch (opt) {

    /* '1' — 单列输出 */
    case 0x31:
        format = (format != 0);
        break;

    /* 'A' — 按名称排序 */
    case 'A':
        sort_type = 1;                             /* DAT_00128310 = 1 */
        break;

    /* 'B' — 忽略 ~ 和 .# 结尾的备份文件 */
    case 'B':
        ignore_list_add("~");                      /* DAT_0011d0ef */
        ignore_list_add(".#");                     /* DAT_0011d0ee */
        break;

    /* 'C' — 按列输出 */
    case 'C':
        format = 2;
        break;

    /* 'D' — Emacs dired 模式 */
    case 'D':
        /* in_R11 = 0; */
        hyperlink        = 0;                      /* DAT_00128331 */
        dired            = 1;                      /* DAT_00128338 */
        format           = 0;
        break;

    /* 'F' — 指示符 (--classify) */
    case 'F':
        if (optarg != NULL) {
            lVar26 = XARGMATCH("--classify", optarg,
                               always_args,       /* &PTR_s_always_00126200 */
                               classify_vals,     /* &DAT_0011b680 */
                               4, argmatch_die, 1, &winsize);
            if (classify_vals[lVar26] != 1
                && (classify_vals[lVar26] != 2
                    || ((cVar4 = isatty(), cVar4) == '\0')))
                break;
        }
        indicator_style  = 3;                      /* DAT_00128334 */
        break;

    /* 'G' — 不显示组名 */
    case 'G':
        print_group_before_name = 0;               /* DAT_00127028 */
        break;

    /* 'H' — 跟随符号链接 (命令行参数) */
    case 'H':
        listing_format   = 2;                      /* DAT_00128318 */
        break;

    /* 'I' — 忽略匹配 pattern 的文件 */
    case 'I':
        ignore_list_add(optarg);
        break;

    /* 'L' — 跟随所有符号链接 */
    case 'L':
        listing_format   = 4;                      /* DAT_00128318 */
        break;

    /* 'N' — 字面值引用风格 */
    case 'N':
        quoting_style    = 0;
        break;

    /* 'Q' — C 风格引用 (双引号) */
    case 'Q':
        quoting_style    = 5;
        break;

    /* 'R' — 递归 */
    case 'R':
        recursive        = 1;                      /* DAT_00128316 */
        break;

    /* 'S' — 按大小排序 */
    case 'S':
        sort_type        = 3;
        break;

    /* 'T' — tab 大小 */
    case 'T':
        uVar14           = dcgettext(NULL, "invalid tab size", LC_MESSAGES);
        tab_size_val     = xdectoumax(optarg, 0, 0, 0x7fffffffffffffff,
                                      "",            /* &DAT_0011cf4c */
                                      uVar14, 2, 0);
        break;

    /* 'U' — 不排序 */
    case 'U':
        sort_type        = 6;
        break;

    /* 'X' — 按扩展名排序 */
    case 'X':
        sort_type        = 1;
        break;

    /* 'Z' — 显示 SELinux 上下文 */
    case 'Z':
        print_context    = 1;                      /* DAT_00128389 */
        break;

    /* 'a' — 显示隐藏文件 */
    case 'a':
        sort_type        = 2;                      /* DAT_00128310 = 2 (all) */
        break;

    /* 'b' — 八进制转义 */
    case 'b':
        quoting_style    = 7;
        break;

    /* 'c' — 按 ctime 排序/显示 */
    case 'c':
        time_style        = 1;                     /* DAT_00128358 */
        use_time_flag     = 1;                     /* DAT_00128354 */
        break;

    /* 'd' — 只列出目录本身 */
    case 'd':
        immediate_dirs   = 1;                      /* DAT_00128315 */
        break;

    /* 'f' — 无排序, 显示所有, 无颜色 */
    case 'f':
        sort_type        = 2;                      /* DAT_00128310 = 2 */
        /* local_90 */    = 6;                     /* sort_type = none */
        break;

    /* 'g' — 长格式无所有者 */
    case 'g':
        no_group         = 0;                      /* DAT_00127029 */
        /* fall through */

    /* 'l' — 长格式 */
    case 'l':
        format           = 0;
        break;

    /* 'h' — 人类可读 */
    case 'h':
        human_output_opts = 0xb0;                   /* DAT_00128348 */
        output_block_size = 0xb0;                   /* DAT_0012833c */
        block_size        = 1;                      /* DAT_00128340 */
        human_output_opts_2 = 1;                    /* DAT_00127020 */
        break;

    /* 'i' — 显示 inode */
    case 'i':
        print_inode_2    = 1;                      /* DAT_0012831c */
        break;

    /* 'k' — 1K 块大小 */
    case 'k':
        bVar28           = true;
        break;

    /* 'm' — 逗号分隔 */
    case 'm':
        format           = 4;
        break;

    /* 'n' — 数字 UID/GID */
    case 'n':
        numeric_ids      = 1;                      /* DAT_0012834d */
        format           = 0;
        break;

    /* 'o' — 长格式无组 */
    case 'o':
        print_group_before_name = 0;               /* DAT_00127028 */
        format           = 0;
        break;

    /* 'p' — 目录后加 '/' */
    case 'p':
        indicator_style  = 1;                      /* DAT_00128334 */
        break;

    /* 'q' — 非打印字符显示为 '?' */
    case 'q':
        zero             = 1;
        break;

    /* 'r' — 反向排序 */
    case 'r':
        reverse_sort     = 1;                      /* DAT_0012834f */
        break;

    /* 's' — 显示块大小 */
    case 's':
        print_block_size_2 = 1;                    /* DAT_0012834c */
        break;

    /* 't' — 按修改时间排序 */
    case 't':
        sort_type        = 5;
        break;

    /* 'u' — 按 atime 排序/显示 */
    case 'u':
        time_style        = 2;                     /* DAT_00128358 */
        use_time_flag     = 1;                     /* DAT_00128354 */
        break;

    /* 'v' — 自然排序 */
    case 'v':
        goto case_v;

    /* 'w' — 设置行宽 */
    case 'w':
        line_width       = strtoul(optarg);         /* FUN_00106de0 */
        if (line_width == -1) {
            uVar14       = quotearg_n(optarg);
            uVar15       = dcgettext(NULL, "invalid line width", LC_MESSAGES);
            error(2, 0, "%s: %s", uVar15, uVar14);
        case_v:
            sort_type    = 4;
        }
        break;

    /* 'x' — 按行输出 (非按列) */
    case 'x':
        format           = 3;
        break;

    /* 长选项 --show-control-chars */
    case 0x80:
        print_owner_2    = 1;                      /* DAT_0012834e */
        break;

    /* 长选项 --block-size=SIZE */
    case 0x81:
        iVar8 = human_options(optarg, &human_output_opts, &block_size);
        if (iVar8 != 0)
            die(iVar8, (ulong)winsize & 0xffffffff, 0, &all_args_ptr, optarg);
        output_block_size = human_output_opts;     /* DAT_0012833c = DAT_00128348 */
        human_output_opts_2 = block_size;          /* DAT_00127020 = DAT_00128340 */
        break;

    /* --color */
    case 0x82:
        if (optarg == NULL) {
    color_always:
            bVar7    = 1;
        } else {
            lVar26 = XARGMATCH("--color", optarg, always_args, color_vals,
                               /* &DAT_0011b680 */ 4, argmatch_die, 1);
            if (color_vals[lVar26] == 1)
                goto color_always;
            bVar7 = 0;
            if (color_vals[lVar26] == 2)
                bVar7 = isatty();
        }
        print_color      = bVar7 & 1;              /* DAT_00128332 */
        break;

    /* --dereference (-H) */
    case 0x83:
        listing_format   = 3;                      /* DAT_00128318 */
        break;

    /* --directory */
    case 0x84:
        indicator_style  = 2;                      /* DAT_00128334 */
        break;

    /* --format=WORD */
    case 0x85:
        lVar26 = XARGMATCH("--format", optarg, verbose_args,
                           /* &DAT_0011b710 */ format_vals, 4, argmatch_die, 1, argc);
        format = format_vals[lVar26];
        break;

    /* --full-time */
    case 0x86:
        format           = 0;
        time_style_str   = "full-iso";
        break;

    /* --group-directories-first */
    case 0x87:
        print_with_color = 1;                      /* DAT_00128314 */
        break;

    /* --hide=PATTERN */
    case 0x88:
        puVar12          = xmalloc(0x10);
        puVar24          = ignore_patterns;        /* DAT_00128300 */
        ignore_patterns  = puVar12;
        *(void **)puVar12     = optarg;
        *((void **)puVar12+1) = puVar24;
        break;

    /* --hyperlink */
    case 0x89:
        if (optarg == NULL) {
    hyperlink_always:
            bVar7    = 1;
        } else {
            lVar26 = XARGMATCH("--hyperlink", optarg, always_args,
                               color_vals, 4, argmatch_die, 1, &winsize);
            if (color_vals[lVar26] == 1)
                goto hyperlink_always;
            bVar7 = 0;
            if (color_vals[lVar26] == 2)
                bVar7 = isatty();
        }
        hyperlink        = bVar7 & 1;              /* DAT_00128331 */
        break;

    /* --indicator-style=WORD */
    case 0x8a:
        lVar26 = XARGMATCH("--indicator-style", optarg,
                           indicator_args,         /* &PTR_DAT_001268e0 */
                           "", 4, argmatch_die, 1, ppuVar20);
        indicator_style  = *(uint *)("lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"
                                     + lVar26 * 4 + 0x30);
        break;

    /* --quoting-style=WORD */
    case 0x8b:
        lVar26 = XARGMATCH("--quoting-style", optarg,
                           quoting_args,          /* &PTR_s_literal_001269a0 */
                           quoting_vals,          /* &DAT_00120220 */
                           4, argmatch_die, 1, /* in_R11 */ 0);
        quoting_style    = quoting_vals[lVar26];   /* *(int *)(&DAT_00120220 + lVar26*4) */
        break;

    /* --show-control-chars → goto zero=0 case */
    case 0x8c:
        goto case_8c;

    /* --si (SI 单位, 1000 进制) */
    case 0x8d:
        human_output_opts = 0x90;                  /* DAT_00128348 */
        output_block_size = 0x90;                  /* DAT_0012833c */
        block_size        = 1;                     /* DAT_00128340 */
        human_output_opts_2 = 1;                   /* DAT_00127020 */
        break;

    /* --sort=WORD */
    case 0x8e:
        lVar26 = XARGMATCH("--sort", optarg,
                           sort_args,              /* &DAT_001262c0 */
                           sort_vals,              /* &DAT_0011b6f0 */
                           4, argmatch_die, 1,
                           (long)&switchdata + (long)(int)switchdata[opt + 0x83]);
        sort_type        = sort_vals[lVar26];
        break;

    /* --time=WORD */
    case 0x8f:
        /* in_R11 = 1; */
        lVar26 = XARGMATCH("--time", optarg,
                           time_args,              /* &DAT_00126260 */
                           time_vals,              /* &DAT_0011b6c0 */
                           4, argmatch_die, 1, /* in_R10 */ &winsize);
        use_time_flag    = 1;                     /* DAT_00128354 */
        time_style       = time_vals[lVar26];     /* DAT_00128358 */
        break;

    /* --time-style=STYLE */
    case 0x90:
        goto case_90;

    /* --zero */
    case 0x91:
        check_dired_flag = 0;                      /* DAT_00127019 */
        /* in_R10 = NULL; */
        print_color      = 0;                      /* DAT_00128332 */
        format           = (format != 0);
        quoting_style    = 0;
    case_8c:
        zero             = 0;
        break;

    /* --version */
    case -0x83:
        uVar14           = author_name("David MacKenzie", "David MacKenzie");
        uVar15           = author_name("Richard M. Stallman", "Richard M. Stallman");
        pcVar25           = "ls";
        if (program_mode != 1) {                   /* DAT_001271e0 */
            pcVar25 = (program_mode == 2) ? "vdir" : "dir";
        }
        version_etc(stdout, pcVar25, "GNU coreutils",
                    PTR_DAT_001271e8, uVar15, uVar14, NULL, /* in_R9 */ NULL);
        exit(0);

    /* --help */
    case -0x82:
        goto help_only;

    /* 非法选项 */
    default:
    usage_error:
        usage();                                   /* FUN_0010e360() */
    help_only:
        usage(0);                                  /* FUN_0010e360(0) */
    }

    goto opt_loop;

    /* ================================================================ */
    /*  3. 选项解析后处理                                                */
    /* ================================================================ */

post_options:

    /* 3a. 块大小 (LS_BLOCK_SIZE / BLOCK_SIZE 环境变量) */
    if (block_size == 0) {
        pcVar25 = getenv("LS_BLOCK_SIZE");
        human_options(pcVar25, &human_output_opts, &block_size);
        if (pcVar25 != NULL
            || (pcVar25 = getenv("BLOCK_SIZE"), pcVar25 != NULL)) {
            output_block_size = human_output_opts;
            human_output_opts_2 = block_size;
        }
        if (bVar28) {
            block_size          = 0x400;
            human_output_opts   = 0;
        }
    }

    /* 3b. 格式回退 (无显式 --format 时根据 program_mode 决定) */
    if ((int)format < 0) {
        if (program_mode == 1)
            goto mode_ls_default;           /* LAB_001064c7: use isatty */
        format = (program_mode == 2) ? 2 : 0;
    }

    /* ================================================================ */
    /*  4. 终端宽度 / Tab / 引用风格 / 时间格式 配置循环                  */
    /* ================================================================ */

    do {
        uVar16 = line_width;
        format_global = format;                   /* DAT_0012835c */
        uVar3 = line_width;

        /* 4a. 终端宽度检测 */
        if ((format - 2 < 3) || (print_color != 0)) {
            if (line_width == -1) {
                cVar4 = isatty();
                if (cVar4 != '\0'
                    && (iVar8 = ioctl(STDOUT_FILENO, TIOCGWINSZ, &winsize),
                        iVar8 >= 0)) {
                    uVar16 = winsize.ws_col;
                    uVar3  = uVar16;
                    if (winsize.ws_col != 0)
                        goto width_done;
                }
                pcVar25 = getenv("COLUMNS");
                if (pcVar25 != NULL && *pcVar25 != '\0') {
                    line_width = strtoul(pcVar25);
                    uVar16     = line_width;
                    uVar3      = line_width;
                    if (line_width != -1)
                        goto width_done;
                    uVar14 = quotearg_n(pcVar25);
                    uVar15 = dcgettext(NULL,
                            "ignoring invalid width in environment variable"
                            " COLUMNS: %s", LC_MESSAGES);
                    error(0, 0, uVar15, uVar14);
                }
        width_default:
                uVar16 = 0x50;       /* 默认 80 列 */
                uVar3  = line_width;
            }
        } else {
            if (line_width == -1)
                goto width_default;
        }

    width_done:
        line_width      = uVar3;                  /* local_80 */
        max_idx         = (uVar16 / 3 + 1) - (uVar16 % 3 == 0); /* DAT_00128220 */
        line_length     = uVar16;                  /* DAT_001282d0 */

        /* 4b. Tab 大小 */
        puVar23         = tab_size;               /* DAT_001282e0 */
        if ((format_global - 2 < 3)
            && (puVar23 = tab_size_val, (long)tab_size_val < 0)) {
            tab_size    = (void *)0x8;
            pcVar25     = getenv("TABSIZE");
            puVar23     = tab_size;
            if (pcVar25 != NULL
                && (iVar8 = xstrtoumax(pcVar25, 0, 0, &winsize, ""),
                    puVar23 = winsize, iVar8 != 0)) {
                uVar14  = quotearg_n(pcVar25);
                uVar15  = dcgettext(NULL,
                         "ignoring invalid tab size in environment variable"
                         " TABSIZE: %s", LC_MESSAGES);
                error(0, 0, uVar15, uVar14);
                puVar23 = tab_size;
            }
        }
        tab_size        = puVar23;                /* DAT_001282e0 */

        /* 4c. --zero / dired 模式 */
        bVar7           = (byte)zero & 1;
        if (zero == -1
            && (bVar7 = 0, program_mode == 1)) {
            bVar7       = isatty();
        }
        zero_flag       = bVar7;                  /* DAT_001282f8 */

        /* 4d. 引用风格 (QUOTING_STYLE 环境变量) */
        if (quoting_style < 0) {
            pcVar25     = getenv("QUOTING_STYLE");
            if (pcVar25 == NULL)
                goto quoting_default;
            iVar8 = XARGMATCH_str(pcVar25,
                                  quoting_args,    /* &PTR_s_literal_001269a0 */
                                  quoting_vals,    /* &DAT_00120220 */
                                  4);
            if (iVar8 < 0)
                goto quoting_invalid;
            quoting_style = quoting_vals[iVar8];
            if (quoting_style < 0)
                goto quoting_default;
        }

    set_quoting:
        set_quoting_style(0, quoting_style);       /* FUN_00118160 */

        /* 4e. 构建引用前缀 (用于 --indicator-style 和 --quoting-style 输出) */
        for (;;) {
            format = get_quoting_style(0);         /* FUN_00118140 */

            if ((format_global == 0
                 || (format_global - 2 < 2 && line_length != 0))
                && format < 7) {
                if ((0x4aUL >> (format & 0x3f) & 1) == 0) {
                    hide_sep    = 0;              /* DAT_001283c8 */
                    quoting_prefix = init_output_buf(0); /* DAT_001282f0,FUN_00118100 */
                } else {
                    hide_sep    = 1;              /* DAT_001283c8 */
                    quoting_prefix = init_output_buf(0);
                }
            } else {
                hide_sep        = 0;
                quoting_prefix  = init_output_buf(0);
                if (format == 7) {
                    output_buf_addchar(quoting_prefix, ' ', 1);
                }
            }

            /* 附加指示符样式后缀 */
            if (1 < indicator_style) {
                pcVar25 = indicator_style_chars    /* &DAT_0011d1ab */
                          + (indicator_style - 2);
                cVar4   = indicator_style_chars[indicator_style - 2];
                while (cVar4 != '\0') {
                    pcVar25++;
                    output_buf_addchar(quoting_prefix, (int)cVar4, 1);
                    cVar4 = *pcVar25;
                }
            }

            quoting_sep     = init_output_buf(0);  /* DAT_001282e8 */
            output_buf_addchar(quoting_sep, ':', 1);

            /* dired 与 hyperlink 不兼容 */
            dired = (hyperlink ^ 1) & (format_global == 0) & dired;
            if ((int)(uint)dired <= (int)check_dired_flag)
                break;

    dired_incompat:
            uVar14 = dcgettext(NULL,
                     "--dired and --zero are incompatible", LC_MESSAGES);
            error(2, 0, uVar14);

    quoting_invalid:
            uVar14 = quotearg_n(NULL);
            uVar15 = dcgettext(NULL,
                     "ignoring invalid value of environment variable"
                     " QUOTING_STYLE: %s", LC_MESSAGES);
            error(0, 0, uVar15, uVar14);

    quoting_default:
            quoting_style = 7;
            if (program_mode != 1)
                goto set_quoting;
            cVar4 = isatty();
            if (cVar4 != '\0')
                goto quoting_ttl_default;
        }

        /* 4f. 排序/时间类型 */
        if (sort_type < 0) {
            if (format_global == 0) {
                time_type = 0;                    /* DAT_00128350 */
                goto time_style_block;
            }
            if (use_time_flag == '\0') {
                time_type = 0;
            } else {
                time_type = 5;
            }
            goto post_time_style;
        }
        time_type = sort_type;                    /* DAT_00128350 = local_90 */
        if (format_global != 0)
            goto post_time_style;

    time_style_block:
        /* TIME_STYLE 环境变量 */
        if ((time_style_str == NULL)
            && (time_style_str = getenv("TIME_STYLE"),
                time_style_str == NULL)) {
            time_style_str = "locale";
        } else {
            while ((iVar8 = strncmp(time_style_str, "posix-", 6),
                    iVar8 == 0)) {
                cVar4 = locale_support(2);         /* FUN_00111400 */
                if (cVar4 == '\0')
                    goto post_time_style;
                time_style_str += 6;
            }
        }

        if (*time_style_str == '+') {
            /* 自定义 date 格式: +FORMAT */
            pcVar25 = time_style_str + 1;
            pcVar19 = strchr(pcVar25, '\n');
            pcVar22 = pcVar25;
            if (pcVar19 != NULL) {
                pcVar22 = strchr(pcVar19 + 1, '\n');
                if (pcVar22 != NULL) {
                    uVar14 = quotearg_n(pcVar25);
                    uVar15 = dcgettext(NULL,
                             "invalid time style format %s", LC_MESSAGES);
                    error(2, 0, uVar15, (FILE *)uVar14);
                    goto dired_incompat;
                }
                *pcVar19 = '\0';
                pcVar22  = pcVar19 + 1;
            }
            goto time_style_set;
        }

        ppuVar20 = &time_style_args;              /* &PTR_s_full_iso_00126920 */
        lVar26 = XARGMATCH_str(time_style_str,
                               time_style_args,   /* &PTR_s_full_iso_00126920 */
                               time_style_vals,   /* &DAT_0011b7c0 */
                               4);
        if (lVar26 >= 0)
            goto time_style_by_idx;

        artmatch_invalid("time style", time_style_str, lVar26);
        stream  = stderr;
        pcVar25 = dcgettext(NULL, "Valid arguments are:\n", LC_MESSAGES);
        fputs_unlocked(pcVar25, stream);
        for (; *ppuVar20 != NULL; ppuVar20++) {
            __fprintf_chk(stderr, 1, "  - [posix-]%s\n");
        }
        pcVar25 = dcgettext(NULL,
                  "  - +FORMAT (e.g., +%H:%M) for a 'date'-style format\n",
                  LC_MESSAGES);
        fputs_unlocked(pcVar25, stderr);

        /* --help (usage 不返回) */
        usage_error:
            usage();
        help_only:
            usage(0);

    mode_ls_default:
        bVar7  = isatty();
        format = (uint)(bVar7 + 1);
    } while (true);

    /* ================================================================ */
    /*  TIME_STYLE 标签: 时间格式选择                                    */
    /* ================================================================ */

case_90:
    time_style_str = optarg;
    goto opt_loop;

time_style_by_idx:
    if (lVar26 == 2) {
        /* long-iso */
        long_time_format     = "%Y-%m-%d  ";      /* s__Y__m__d_0011d231 */
        regular_time_format  = "%b %e %H:%M";      /* &DAT_0011d225 */
        pcVar25              = long_time_format;
        pcVar22              = regular_time_format;
    } else if (lVar26 < 3) {
        if (lVar26 == 0) {
            /* full-iso */
            long_time_format    = "%Y-%m-%d %H:%M:%S.%N %z";
            regular_time_format = "%Y-%m-%d %H:%M:%S.%N %z";
            pcVar25             = long_time_format;
            pcVar22             = regular_time_format;
        } else {
            /* iso */
            long_time_format    = "%Y-%m-%d  ";     /* &DAT_0011d222 */
            regular_time_format = "%Y-%m-%d  ";
            pcVar25             = long_time_format;
            pcVar22             = regular_time_format;
        }
    } else {
        /* locale */
        pcVar25 = long_time_format;
        pcVar22 = regular_time_format;
        if (lVar26 == 3
            && (cVar4 = locale_support(2),
                pcVar25 = long_time_format,
                pcVar22 = regular_time_format,
                cVar4 != '\0')) {
            long_time_format    = dcgettext(NULL, long_time_format, 2);
            pcVar22             = dcgettext(NULL, regular_time_format, 2);
            pcVar25             = long_time_format;
        }
    }
time_style_set:
    regular_time_format = pcVar22;                /* PTR_s__b__e__H__M_00127048 */
    long_time_format    = pcVar25;                /* PTR_DAT_00127040 */
    init_time_format();                           /* FUN_00106e80 */

post_time_style:

    /* ================================================================ */
    /*  5. LS_COLORS / 颜色配置                                         */
    /* ================================================================ */

    bVar7 = print_color;
    iVar8 = optind;

    if (print_color == 0)
        goto color_off;

    /* 5a. LS_COLORS 环境变量解析 */
    lscolors = getenv("LS_COLORS");
    if (lscolors != NULL && *lscolors != '\0') {
        LS_COLORS_str = xstrdup(lscolors);         /* DAT_00128320 */
        winsize       = (ulong)LS_COLORS_str;
        goto parse_lscolors_loop;
    }

    /* 5b. COLORTERM 检测 */
    pcVar25 = getenv("COLORTERM");
    if (pcVar25 != NULL && *pcVar25 != '\0')
        goto color_detect_done;

    /* 5c. TERM + dircolors 数据库检测 */
    pcVar25 = getenv("TERM");
    if (pcVar25 == NULL || *pcVar25 == '\0')
        goto color_disable;
    pcVar22 = "# Configuration file for dircolors, a utility to help you set the";
    goto dircolors_db_scan;

dircolors_db_scan:
    if ((char *)0x15ef < pcVar22 + -0x11b900)
        goto color_disable;
    iVar9 = strncmp(pcVar22, "TERM ", 5);
    if (iVar9 == 0
        && (iVar9 = fnmatch(pcVar22 + 5, pcVar25, 0), iVar9 == 0))
        goto color_detect_done;
    sVar17 = strlen(pcVar22);
    pcVar22 = pcVar22 + sVar17 + 1;
    goto dircolors_db_scan;

color_disable:
    print_color = 0;
    goto color_detect_done;

quoting_ttl_default:
    quoting_style = 3;
    goto set_quoting;

    /* ================================================================ */
    /*  LS_COLORS 主解析循环                                             */
    /* ================================================================ */

parse_lscolors_loop:
    pcVar25 = lscolors;
    cVar4   = *lscolors;

    if (cVar4 == '*') {
        /* 扩展条目: *.ext=color */
        psVar18     = xmalloc(0x30);
        *((char *)psVar18 + 4) = 0;
        lscolors    = pcVar25 + 1;
        psVar18[5]  = (size_t)LS_COLORS_ext_list;
        psVar18[1]  = (size_t)winsize;             /* local_58 = LS_COLORS_str */
        LS_COLORS_ext_list = psVar18;              /* DAT_00128328 */

        cVar4 = parse_LS_COLORS(&winsize, &lscolors, 1, psVar18);
        pcVar25 = lscolors;
        if (cVar4 == '\0'
            || (pcVar25 = lscolors + 1, *lscolors != '='))
            goto lscolors_error;

        psVar18[3] = (size_t)winsize;
        lscolors++;
        cVar4 = parse_LS_COLORS(&winsize, &lscolors, 0, psVar18 + 2);
        pcVar25 = lscolors;
        if (cVar4 == '\0')
            goto lscolors_error;
        goto parse_lscolors_loop;
    }

    if (cVar4 == ':') {
        /* 跳过冒号分隔符 */
        lscolors++;
    } else if (cVar4 == '\0') {
        /* 到达字符串末尾，处理扩展列表去重 */
        psVar18 = LS_COLORS_ext_list;
        if (LS_COLORS_ext_list != NULL) {
            while ((psVar21 = psVar18,
                    psVar18 = (size_t *)psVar21[5],
                    psVar18 != NULL)) {
                bVar2  = 0;
                psVar27 = psVar18;
                do {
                    sVar17 = *psVar27;
                    if (sVar17 != -1 && sVar17 == *psVar21) {
                        pvVar13 = (void *)psVar27[1];
                        s1      = (void *)psVar21[1];
                        iVar9   = memcmp(s1, pvVar13, sVar17);
                        if (iVar9 == 0) {
                            *psVar27 = -1;         /* 标记为已删除 */
                        } else {
                            iVar9 = FUN_0010f3c0(s1, pvVar13, sVar17);
                            if (iVar9 == 0) {
                                if (bVar2 == 0
                                    && (psVar21[2] != psVar27[2]
                                        || (iVar9 = memcmp((void *)psVar21[3],
                                                           (void *)psVar27[3],
                                                           psVar21[2]),
                                            iVar9 != 0))) {
                                    *(char *)(psVar21 + 4) = 1;
                                    *(char *)(psVar27 + 4) = 1;
                                } else {
                                    *psVar27 = -1;
                                    bVar2    = bVar7;
                                }
                            }
                        }
                    }
                    psVar27 = (size_t *)psVar27[5];
                } while (psVar27 != NULL);
            }
        }
        goto lscolors_done;
    } else {
        /* 双字符类型指示符: XX=color */
        prefix_ch0 = lscolors[1];
        pcVar25    = lscolors + 1;
        if (prefix_ch0 == '\0'
            || (pcVar25 = lscolors + 3, lscolors[2] != '='))
            goto lscolors_error;

        lVar26 = 0;
        while (cVar4 != indicator_type_names[lVar26 * 2]
               || prefix_ch0 != indicator_type_names[lVar26 * 2 + 1]) {
            lVar26++;
            if (lVar26 == 0x18)
                goto lscolors_bad_prefix;
        }
        color_indicator_values[lVar26 * 2] = winsize; /* local_58 */

        cVar6 = parse_LS_COLORS(&winsize, &lscolors, 0);
        if (cVar6 == '\0')
            goto lscolors_bad_prefix;
    }
    goto parse_lscolors_loop;

lscolors_bad_prefix:
    prefix_nul = 0;
    uVar14     = quotearg_n(&prefix_ch0);
    uVar15     = dcgettext(NULL, "unrecognized prefix: %s", LC_MESSAGES);
    error(0, 0, uVar15, uVar14);
    pcVar25    = lscolors;

lscolors_error:
    lscolors   = pcVar25;
    uVar14     = dcgettext(NULL,
                 "unparsable value for LS_COLORS environment variable",
                 LC_MESSAGES);
    error(0, 0, uVar14);
    free(LS_COLORS_str);
    psVar18 = LS_COLORS_ext_list;
    while (psVar18 != NULL) {
        psVar21 = (size_t *)psVar18[5];
        free(psVar18);
        psVar18 = psVar21;
    }
    print_color = 0;

lscolors_done:
    if (color_indicator_len == 6                     /* DAT_001270d0 */
        && (iVar9 = strncmp(color_indicator_name,    /* PTR_DAT_001270d8 */
                            "target", 6),
            iVar9 == 0)) {
        target_indicator = 1;                        /* DAT_001283b0 */
    }

color_detect_done:

    /* ================================================================ */
    /*  6. 颜色/超链接/格式最终决定                                      */
    /* ================================================================ */

    if (print_color == 0) {
color_off:
        if (print_with_color == 0)
            goto check_listing_format;
    } else {
        tab_size = NULL;                             /* 彩色模式下 tab_size 清零 */
        if (print_with_color != 0
            || (cVar4 = has_capability(0xd), cVar4 != '\0')
            || (cVar4 = has_capability(0xe), cVar4 != '\0' && target_indicator != '\0')
            || (cVar4 = has_capability(0xc), cVar4 != '\0' && format_global == 0)) {
    enable_color:
            color_enabled = 1;                       /* DAT_0012831d */
        }
    }

check_listing_format:
    lVar26 = (long)optind;
    if (listing_format == 0
        && (listing_format = 1, immediate_dirs == '\0')
        && indicator_style != 3
        && format_global != 0) {
        listing_format = 3;
    }

    /* ================================================================ */
    /*  7. 递归 / TZ / 标志计算 / Hyperlink / 文件数组                    */
    /* ================================================================ */

    /* 7a. 递归: 初始化哈希表 */
    if (recursive != 0) {
        active_dir_set = hash_initialize(30, 0, dev_ino_hash, dev_ino_compare, free);
        if (active_dir_set == NULL)
            xalloc_die();
        obstack_init(&dev_ino_obstack, 0, 0, malloc, free);
    }

    /* 7b. 保存 TZ 环境变量 */
    pcVar25    = getenv("TZ");
    saved_tz   = xstrdup(pcVar25);                   /* DAT_001282c8 */

    /* 7c. 标志位计算 */
    flag_c2 = (print_block_size_2 | hyperlink | print_context
               | (format_global == 0)
               | ((time_type - 3U & 0xfffffffd) == 0));
    flag_c1 = (print_context | recursive | print_color
               | print_with_color | (indicator_style != 0))
              & (flag_c2 ^ 1);

    uVar5 = 0;
    if (print_color != 0)
        uVar5 = has_capability(0x15);
    flag_c0 = uVar5;                                 /* DAT_001282c0 */

    /* 7d. Dired: 初始化 obstack */
    if (dired != 0) {
        obstack_init(&dired_obstack, 0, 0, malloc, free);
        obstack_init(&subdired_obstack, 0, 0, malloc, free);
    }

    /* 7e. Hyperlink: 构建 URL 安全字符表 + 获取主机名 */
    if (hyperlink != 0) {
        uVar16 = 0;
        do {
            /* 标记 0-9, A-Z, a-z, -._~ 为安全字符 */
            while ((iVar9 = (int)uVar16, uVar16 < 0x5b)) {
                if ((uVar16 < 0x41
                     && (9 < iVar9 - 0x30U))
                    && (1 < iVar9 - 0x2dU)) {
                    uVar16++;
                } else {
                    url_escape_tab[uVar16] |= 1;
                    uVar16++;
                }
            }
            bVar28 = true;
            if ((0x19 < iVar9 - 0x61U) && (uVar16 != 0x7e))
                bVar28 = (iVar9 == 0x5f);
            url_escape_tab[uVar16] |= bVar28;
            uVar16++;
        } while (uVar16 != 0x100);

        hostname = get_hostname();                    /* FUN_0011a360 (来自 func1) */
        if (hostname == NULL)
            hostname = "";                           /* &DAT_0011cf4c */
    }

    /* 7f. 分配文件列表数组 */
    init_buf_size = 100;                             /* DAT_001283d8 */
    file_array    = xmalloc(0x5140);                  /* DAT_001283e0 */
    iVar8         = (int)(argc - optind);            /* 剩余参数数量 */
    files_processed = 0;                             /* DAT_001283d0 */
    init_file_array();                               /* FUN_001087c0 */

    /* ================================================================ */
    /*  8. 处理文件参数                                                  */
    /* ================================================================ */

    if (iVar8 < 1) {
        /* 无参数: 列出当前目录 */
        if (immediate_dirs == '\0')
            list_current_dir(".", 0, 1);             /* FUN_001071c0 */
        else
            process_file(".", 3, 1, 0);              /* FUN_0010ca80 */
        if (files_processed != 0)
            goto sort_and_print;
    no_files:
        if (file_queue == NULL)
            goto cleanup;
        file_ptr = file_queue;
        if (file_queue[3] == 0)
            DAT_001282d8 = 0;
    } else {
        /* 有参数: 逐个处理 */
        do {
            lVar11  = lVar26 * 2;
            lVar26++;
            process_file(*(void **)((char *)&argv->flags + lVar11), 0, 1, 0);
        } while ((int)lVar26 < (int)argc);

        if (files_processed == 0) {
            if (iVar8 > 1)
                goto print_loop;
            goto no_files;
        }

    sort_and_print:
        sort_files();                                 /* FUN_00108e30 */
        if (immediate_dirs == '\0')
            print_files(0, 1);                       /* FUN_00109530 */
        if (files_processed == 0)
            goto print_loop;
        print_total();                                /* FUN_0010c650 */

        if (file_queue == NULL)
            goto cleanup;

        count++;                                      /* DAT_00128218++ */
        pcVar25 = stdout->_IO_write_ptr;
        if (stdout->_IO_write_end <= pcVar25) {
            __overflow(stdout, '\n');
            goto print_loop;
        }
        stdout->_IO_write_ptr = pcVar25 + 1;
        *pcVar25 = '\n';
        file_ptr = file_queue;
    }

    /* ================================================================ */
    /*  9. 打印主循环: 遍历 file_queue 逐个输出                            */
    /* ================================================================ */

print_loop:
    do {
        file_queue = (long *)file_ptr[3];

        if (active_dir_set == NULL || *file_ptr != 0) {
            /* 普通文件/目录 */
            print_file_entry(*file_ptr, file_ptr[1], (char)file_ptr[2]);
            free((void *)*file_ptr);
            free((void *)file_ptr[1]);
            free(file_ptr);
            DAT_001282d8 = 1;
        } else {
            /* 目录已被递归处理过，从 dev_ino_obstack 弹出并清理 */
            if ((ulong)(dev_ino_next_free - dev_ino_object_base) < 0x10)
                __assert_fail(
                    "dev_ino_size <= __extension__ ({ struct obstack const"
                    " *__o = (&dev_ino_obstack); (size_t) (__o->next_free"
                    " - __o->object_base); })",
                    "src/ls.c", 0x442, "dev_ino_pop");

            winsize   = *(void **)(dev_ino_next_free - 0x10);
            uStack_50 = *(ulong *)(dev_ino_next_free - 0x8);
            dev_ino_next_free -= 0x10;

            pvVar13 = hash_delete(active_dir_set, &winsize);
            if (pvVar13 == NULL)
                __assert_fail("found", "src/ls.c", 0x73d, "main");
            free(pvVar13);
            free((void *)*file_ptr);
            free((void *)file_ptr[1]);
            free(file_ptr);
        }

        file_ptr = file_queue;
    } while (file_queue != NULL);

    /* ================================================================ */
    /* 10. 清理与输出                                                    */
    /* ================================================================ */

cleanup:
    /* 10a. 颜色重置 & 信号恢复 */
    if (print_color != 0 && color_initialized != '\0') {
        if (left_code != 2                          /* DAT_00127060 */
            || (*(short *)color_indicator_values != 0x5b1b
                || right_code != 1                   /* DAT_00127070 */
                || *type_indicator != 'm')) {        /* *PTR_DAT_00127078 */
            reset_color(&left_code);                 /* FUN_00107990 */
            reset_color(&right_code);
        }
        fflush_unlocked(stdout);
        restore_terminal(0);                         /* FUN_001077e0 */
        for (iVar8 = signal_count; iVar8 != 0; iVar8--)
            raise(SIGCONT);                          /* 0x13 */
        if (signal_num != 0)
            raise(signal_num);
    }

    /* 10b. Dired 输出 */
    if (dired != 0) {
        write_dired("//DIRED//", &dired_obstack);
        write_dired("//SUBDIRED//", &subdired_obstack);
        format = get_quoting_style(quoting_prefix);  /* FUN_00118140(DAT_001282f0) */
        __printf_chk(1, "//DIRED-OPTIONS// --quoting-style=%s\n",
                     quoting_args[format]);          /* &PTR_s_literal_001269a0 */
    }

    /* 10c. 释放哈希表 */
    lVar26 = (long)active_dir_set;
    if (active_dir_set != NULL) {
        lVar11 = hash_get_n_entries(active_dir_set);
        if (lVar11 != 0)
            __assert_fail(
                "hash_get_n_entries (active_dir_set) == 0",
                "src/ls.c", 0x771, "main");
        hash_free(active_dir_set);
    }

    /* 10d. 栈金丝雀校验 */
    if (stack_canary != *(long *)(FS_OFFSET + 0x28))
        __stack_chk_fail();

    return DAT_00128230;  /* 返回 exit_status */
}
