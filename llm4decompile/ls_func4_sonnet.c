/*
 * 原始符号：FUN_00104c00(uint param_1, FILE *param_2)
 * 推测符号：main(int argc, char **argv)
 * 来源：GNU coreutils src/ls.c
 *
 * 确认依据：
 *   - assert 字符串中直接出现 "src/ls.c"、"main"、"dev_ino_pop"
 *   - bindtextdomain("coreutils", "/usr/share/locale")
 *   - 作者名 "David MacKenzie"、"Richard M. Stallman"
 *   - 短选项串 "abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1" 与 ls 源码完全吻合
 *   - getenv("LS_COLORS")、getenv("COLUMNS")、getenv("TABSIZE") 等 ls 专用环境变量
 *
 * ghidra 的主要错误：
 *   - param_2 类型被错推为 FILE *，实际是 char **argv
 *   - case -0x83 / case -0x82：即 GETOPT_VERSION_CHAR(-131) /
 *     GETOPT_HELP_CHAR(-130)，gnulib 中用 (char)-131 / (char)-130 编码
 *   - 函数尾部的 do { ... } while(true) 是 goto 密集导致的假循环结构，
 *     实际是顺序执行的初始化代码
 *
 * ── 参数说明 ──────────────────────────────────────────────────────────
 *   param_1  = argc  (uint，ghidra 丢失了 int 符号)
 *   param_2  = argv  (char **，被错推为 FILE *)
 *
 * ── 局部变量映射 ──────────────────────────────────────────────────────
 *   local_90  = sort_type_opt    排序方式（-1=未设置）
 *   local_8c  = quoting_style    引用风格（-1=未设置，7=literal）
 *   local_88  = time_style       时间显示格式字符串
 *   local_80  = line_length      终端列宽（-1=未检测）
 *   local_78  = tabsize_opt      制表符宽度（-1=未设置）
 *   local_70  = ignore_mode      控制字符处理（-1=自动，0=显示，1=隐藏为?）
 *   local_60  = ls_colors_ptr    解析中的 LS_COLORS 当前位置
 *   uVar10    = format           输出格式（见 enum format，-1=未决定）
 *   bVar28    = kibibytes        -k 选项：强制以 1024 为块单位
 *
 * ── 全局变量映射（地址 → 逻辑名）────────────────────────────────────
 *   DAT_001271e0   ls_mode            (0=ls, 1=vdir, 2=dir)
 *   DAT_00128230   exit_status        (函数返回值)
 *   DAT_001282d8   print_dir_name     (多目录时是否打印目录标题行)
 *   DAT_001283a0   pending_dirs       (待处理目录链表头)
 *   DAT_0012835c   format             (当前输出格式，从 uVar10 写入)
 *   DAT_00128310   all_files          (0=默认, 1=almost-all, 2=all)
 *   DAT_00128316   recursive          (-R)
 *   DAT_00128318   dereference        (符号链接解引用模式)
 *   DAT_0012831c   print_inode        (-i)
 *   DAT_0012831d   check_symlink_color
 *   DAT_00128314   directories_first  (--group-directories-first)
 *   DAT_00128315   directory_as_plain (directories_as_plain_files, -d)
 *   DAT_00128332   print_with_color   (--color)
 *   DAT_00128331   print_hyperlink    (--hyperlink)
 *   DAT_00128334   indicator_style    (0=none,1=slash,2=file-type,3=classify)
 *   DAT_00128338   dired              (--dired/-D)
 *   DAT_0012834c   print_block_size   (-s)
 *   DAT_0012834d   numeric_ids        (-n)
 *   DAT_0012834f   sort_reverse       (-r)
 *   DAT_00128350   sort_type          (最终写入的排序方式)
 *   DAT_00128354   time_type_explicit (time 字段是否被显式指定)
 *   DAT_00128358   time_type          (mtime/atime/ctime/…)
 *   DAT_00128389   print_scontext     (-Z, SELinux context)
 *   DAT_001283e8   active_dir_set     (递归去重 hash set)
 *   DAT_001282c8   localtz            (时区缓存)
 *   DAT_001283a8   hostname_str       (hyperlink 用主机名)
 *
 * ── 输出格式枚举（enum format）────────────────────────────────────────
 *   long_format   = 0   // -l 及其隐含 -l 的选项
 *   one_per_line  = 1   // -1
 *   many_per_line = 2   // -C
 *   across        = 3   // -x
 *   with_commas   = 4   // -m
 *
 * ── 内部函数推测 ──────────────────────────────────────────────────────
 *   FUN_00116460  set_program_name(argv[0])         gnulib
 *   FUN_0011ace0  atexit_wrapper
 *   FUN_0010fe00  close_stdout                      gnulib
 *   FUN_00106ce0  add_ignore_pattern(pattern)
 *   FUN_0010f1d0  xargmatch(opt,arg,names,vals,n)   解析枚举参数(always/auto/never等)
 *   FUN_00106e50  isatty(STDOUT_FILENO)
 *   FUN_0011a200  xstrtoimax(s,…)                  带错误提示的整数解析
 *   FUN_00113490  human_options(s,&opts,&block_size) 解析 block-size 字符串
 *   FUN_00116520  proper_name(name)                 gnulib，作者名处理
 *   FUN_00119b30  version_etc(out,prog,suite,…)     gnulib，打印版本
 *   FUN_0011a180  xstrdup(ls_colors_str)
 *   FUN_00106920  parse_ls_color_token(…)           解析 LS_COLORS 一段
 *   FUN_0010f3c0  fnmatch_casefold / strcasecmp
 *   FUN_00119d00  xmalloc(size)
 *   FUN_00118160  set_quoting_style(opts, style)
 *   FUN_00118140  get_quoting_style(opts)
 *   FUN_00118100  clone_quoting_options(opts)
 *   FUN_00118180  set_char_quoting(opts, char, val)
 *   FUN_00106de0  parse_integer(s)                  带范围检查的整数解析
 *   FUN_00119090  tzalloc(tz_env)                   缓存时区
 *   FUN_00111400  is_locale_posix()                 检测当前 locale
 *   FUN_00111e30  hash_initialize(…)
 *   FUN_001161c0  obstack_init(obstack)
 *   FUN_001071c0  gobble_file(name, type, cmd_arg, path)
 *   FUN_0010ca80  gobble_file_with_prefix(…)
 *   FUN_00108e30  sort_files()
 *   FUN_00109530  print_current_files(qo, newline)
 *   FUN_0010c650  queue_directory(name, realname, cmd_arg)
 *   FUN_0010dc80  print_dir(name, realname, cmd_arg)
 *   FUN_00112530  hash_delete(set, entry)
 *   FUN_00107670  dired_dump_obstack(header, obstack)
 *   FUN_001087c0  initialize_pad_buf()
 *   FUN_001077e0  restore_default_color(fd)
 *   FUN_00107990  put_indicator(indicator)
 *   FUN_001068c0  get_color_indicator(type)
 *   FUN_0011a360  xgethostname()                    见 func1_opus47.c
 *   FUN_0010ee80  argmatch(arg, names, vals, n)     非致命版匹配
 *   FUN_0010f000  argmatch_die(…)                   打印合法值并退出
 *   FUN_0010e360  usage(status)
 */

int
main(int argc, char **argv)
{
    /* ── 阶段 1：基础初始化 ─────────────────────────────────────────── */

    set_program_name(argv[0]);   /* FUN_00116460：供 error() 打印程序名 */
    setlocale(LC_ALL, "");       /* setlocale(6, "") */
    bindtextdomain("coreutils", "/usr/share/locale");
    textdomain("coreutils");

    /* DAT_001271f8 = 2：exit_failure 值 */
    initialize_exit_failure(EXIT_FAILURE);
    atexit(close_stdout);        /* FUN_0011ace0(FUN_0010fe00) */

    /* 全局状态清零 */
    exit_status    = EXIT_SUCCESS;       /* DAT_00128230 = 0 */
    print_dir_name = 1;                  /* DAT_001282d8 = 1 */
    pending_dirs   = NULL;               /* DAT_001283a0 = 0 */

    /* 局部选项：-1 表示"未被命令行指定，后续从环境变量或默认值决定" */
    int  sort_type_opt = -1;             /* local_90 */
    int  quoting_style = -1;             /* local_8c */
    char *time_style   = NULL;           /* local_88 */
    ulong line_length  = (ulong)-1;      /* local_80：终端宽度 */
    void *tabsize_opt  = (void *)-1;     /* local_78：tab 宽度 */
    int  ignore_mode   = -1;             /* local_70：控制字符处理 */
    uint format        = (uint)-1;       /* uVar10：输出格式 */
    bool kibibytes     = false;          /* bVar28 */

    /* DAT_00128390/398：block-size 内部哨兵初值 */

    /* ── 阶段 2：getopt_long 选项解析循环 ──────────────────────────── */
    /*
     * 短选项串与 coreutils ls.c 完全一致：
     *   "abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1"
     * 长选项 val 从 128(CHAR_MAX+1) 开始递增编码。
     */
    int opt;
    while ((opt = getopt_long(argc, argv,
            "abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1",
            long_options, NULL)) != -1) {
        switch (opt) {

        /* ── 单字符选项（按 ASCII 值排列）──────────────────────────── */

        case '1':  /* -1：每行一个文件；已是 long_format 则保持 */
            /* uVar10 = (uint)(uVar10 != 0)：long(0)→0, 其他→1 */
            format = (format != long_format) ? one_per_line : format;
            break;

        case 'A':  /* -A：显示除 . 和 .. 外的隐藏文件 */
            all_files = ALMOST_ALL_FILES;    /* DAT_00128310 = 1 */
            break;

        case 'B':  /* -B：忽略以 ~ 结尾的备份文件 */
            add_ignore_pattern("*~");        /* FUN_00106ce0(&DAT_0011d0ef) */
            add_ignore_pattern(".*~");       /* FUN_00106ce0(&DAT_0011d0ee) */
            break;

        case 'C':  /* -C：多列格式 */
            format = many_per_line;          /* uVar10 = 2 */
            break;

        case 'D':  /* --dired（等价于 -D）：Emacs dired 兼容模式 */
            /* DAT_00128331=0, DAT_00128338=1, uVar10=0 */
            print_hyperlink = 0;
            dired           = 1;
            format          = long_format;
            break;

        case 'F':  /* -F / --classify[=WHEN]：给文件追加类型指示符 */
            /*
             * 带 optarg 时通过 xargmatch 解析 always/auto/never：
             *   always(1) → 直接设 indicator_style=CLASSIFY
             *   auto(2)   → 需要 isatty() 为真才设
             *   never(0)  → 不设
             * 无 optarg（裸 -F）等同 always。
             */
            if (optarg != NULL) {
                long idx = xargmatch("--classify", optarg,
                                     classify_args, classify_vals, 4,
                                     usage_func, 1, NULL);
                /* vals[idx]==1(always) 或 vals[idx]==2(auto)&&isatty */
                if (classify_vals[idx] != CLASSIFY_ALWAYS &&
                    !(classify_vals[idx] == CLASSIFY_AUTO && isatty(1)))
                    break;
            }
            indicator_style = CLASSIFY;      /* DAT_00128334 = 3 */
            break;

        case 'G':  /* -G：长格式不显示组名 */
            print_group = false;             /* DAT_00127028 = 0 */
            break;

        case 'H':  /* -H：只解引用命令行给出的符号链接 */
            dereference = DEREF_COMMAND_LINE_ARGUMENTS; /* DAT_00128318 = 2 */
            break;

        case 'I':  /* -I PATTERN：忽略匹配 PATTERN 的文件 */
            add_ignore_pattern(optarg);
            break;

        case 'L':  /* -L：始终解引用符号链接 */
            dereference = DEREF_ALWAYS;      /* DAT_00128318 = 4 */
            break;

        case 'N':  /* -N：literal 引用（不转义） */
            quoting_style = literal_quoting_style; /* local_8c = 0 */
            break;

        case 'Q':  /* -Q：C 风格引用（双引号+转义） */
            quoting_style = c_quoting_style; /* local_8c = 5 */
            break;

        case 'R':  /* -R：递归列目录 */
            recursive = true;                /* DAT_00128316 = 1 */
            break;

        case 'S':  /* -S：按文件大小降序排列 */
            sort_type_opt = SORT_SIZE;       /* local_90 = 3 */
            break;

        case 'T':  /* -T COLS：设置制表符宽度 */
            /*
             * FUN_0011a200 = xstrtoimax，出错时用 dcgettext 取本地化错误串。
             * 结果写入 local_78（tabsize_opt）。
             */
            tabsize_opt = (void *)xstrtoimax(optarg, 0, 0,
                               INTMAX_MAX, NULL,
                               dcgettext(0, "invalid tab size", LC_MESSAGES),
                               2, 0);
            break;

        case 'U':  /* -U：不排序（目录原始顺序） */
            sort_type_opt = SORT_NONE;       /* local_90 = 6 */
            break;

        case 'X':  /* -X：按文件扩展名排序 */
            sort_type_opt = SORT_EXTENSION;  /* local_90 = 1 */
            break;

        case 'Z':  /* -Z：显示 SELinux 安全上下文 */
            print_scontext = true;           /* DAT_00128389 = 1 */
            break;

        case 'a':  /* -a：显示全部文件（含 . 和 ..） */
            all_files = ALL_FILES;           /* DAT_00128310 = 2 */
            break;

        case 'b':  /* -b：escape 风格引用（\n \t 等） */
            quoting_style = escape_quoting_style; /* local_8c = 7 */
            break;

        case 'c':  /* -c：使用 ctime；排序也按 ctime */
            time_type          = CTIME;      /* DAT_00128358 = 1 */
            time_type_explicit = true;       /* DAT_00128354 */
            break;

        case 'd':  /* -d：把目录本身当普通文件列（不展开内容） */
            directory_as_plain = true;       /* DAT_00128315 = 1 */
            break;

        case 'f':  /* -f：不排序 + 显示全部（隐含 -aU） */
            all_files     = ALL_FILES;       /* DAT_00128310 = 2 */
            sort_type_opt = SORT_NONE;       /* local_90 = 6 */
            break;

        case 'g':  /* -g：长格式但不显示所有者 */
            print_owner = false;             /* DAT_00127029 = 0 */
            /* fall through */
        case 'l':  /* -l：长格式 */
            format = long_format;            /* uVar10 = 0 */
            break;

        case 'h':  /* -h：human-readable 大小（1K=1024） */
            /*
             * DAT_00128348 = 0xb0 = human_autoscale|human_SI|human_base_1024
             * DAT_0012833c = 0xb0（目录显示同步）
             * DAT_00128340 = 1, DAT_00127020 = 1
             */
            human_output_opts      = HUMAN_AUTOSCALE | HUMAN_SI | HUMAN_BASE_1024;
            file_output_block_size = 1;
            break;

        case 'i':  /* -i：显示 inode 号 */
            print_inode = true;              /* DAT_0012831c = 1 */
            break;

        case 'k':  /* -k：以 1024 字节为块单位（兜底，在 env var 后覆盖） */
            kibibytes = true;                /* bVar28 = true */
            break;

        case 'm':  /* -m：逗号分隔格式 */
            format = with_commas;            /* uVar10 = 4 */
            break;

        case 'n':  /* -n：长格式 + 用数字显示 uid/gid */
            numeric_ids = true;              /* DAT_0012834d = 1 */
            format      = long_format;
            break;

        case 'o':  /* -o：长格式但不显示组名 */
            print_group = false;             /* DAT_00127028 = 0 */
            format      = long_format;
            break;

        case 'p':  /* -p：目录名后加 / */
            indicator_style = SLASH;         /* DAT_00128334 = 1 */
            break;

        case 'q':  /* -q：不可打印字符显示为 ? */
            ignore_mode = 1;                 /* local_70 = 1 */
            break;

        case 'r':  /* -r：逆序排列 */
            sort_reverse = true;             /* DAT_0012834f = 1 */
            break;

        case 's':  /* -s：显示每文件的分配块数 */
            print_block_size = true;         /* DAT_0012834c = 1 */
            break;

        case 't':  /* -t：按修改时间排序（最新在前） */
            sort_type_opt = SORT_TIME;       /* local_90 = 5 */
            break;

        case 'u':  /* -u：使用访问时间（atime） */
            time_type          = ATIME;      /* DAT_00128358 = 2 */
            time_type_explicit = true;
            break;

        case 'v':  /* -v：版本号自然排序 */
            sort_type_opt = SORT_VERSION;    /* local_90 = 4 */
            break;

        case 'w':  /* -w COLS：强制指定输出宽度 */
            /*
             * FUN_00106de0 = parse_integer，失败返回 -1。
             * FUN_00118c20 = quotearg（出错时引用原始参数）。
             */
            line_length = parse_integer(optarg); /* local_80 */
            if (line_length == (ulong)-1) {
                error(EXIT_FAILURE, 0, "%s: %s",
                      dcgettext(0, "invalid line width", LC_MESSAGES),
                      quotearg(optarg));
            }
            /* 注意：case 'w' 与 case 'v' 共用一段 goto switchD_caseD_76
             * 将 sort_type_opt 设为 SORT_VERSION (4)；
             * 对 -w 而言这段代码是 dead code（getopt 不会走到那里），
             * 是 ghidra 控制流分析的误合并。 */
            break;

        case 'x':  /* -x：多列横向排列 */
            format = across;                 /* uVar10 = 3 */
            break;

        /* ── 长选项（val 128+ 或 gnulib 特殊值）──────────────────── */

        case 0x80:  /* --dired：输出 Emacs dired 格式偏移信息 */
            dired = true;                    /* DAT_0012834e = 1 */
            break;

        case 0x81:  /* --block-size=SIZE */
            {
                /*
                 * FUN_00113490 = human_options，解析 SIZE（如 1K, 1M, 1G 等）。
                 * 出错时调用 FUN_0011a470（带选项名的错误打印）并退出。
                 */
                int err = human_options(optarg, &human_output_opts,
                                        &file_output_block_size);
                if (err != 0)
                    die_block_size_error(err, optarg);
                /* 同步给目录统计显示 */
                dir_output_block_size = human_output_opts;
            }
            break;

        case 0x82:  /* --color[=WHEN] */
            {
                /*
                 * optarg 为 NULL（裸 --color）→ 等同 "always"。
                 * xargmatch 解析 always/auto/never/tty。
                 * LAB_0010591d: bVar7=1（开色）。
                 * vals[idx]==2(auto) → 由 isatty() 决定。
                 */
                bool color;
                if (optarg == NULL) {
                    color = true;
                } else {
                    long idx = xargmatch("--color", optarg,
                                         color_args, color_vals, 4, usage_func, 1);
                    if (color_vals[idx] == ALWAYS)
                        color = true;
                    else if (color_vals[idx] == AUTO)
                        color = (bool)isatty(1);
                    else
                        color = false;
                }
                print_with_color = color;    /* DAT_00128332 */
            }
            break;

        case 0x83:  /* --file-type：追加类型指示符（不含 * 给可执行） */
            indicator_style = FILE_TYPE;     /* DAT_00128318 = 3 */
            break;

        case 0x84:  /* --classify（长选项形式，无参数） */
            indicator_style = CLASSIFY;      /* DAT_00128334 = 2 */
            break;

        case 0x85:  /* --format=WORD */
            {
                long idx = xargmatch("--format", optarg,
                                     format_args, format_vals, 4, usage_func, 1,
                                     NULL);
                format = format_vals[idx];
            }
            break;

        case 0x86:  /* --full-time：等同 -l --time-style=full-iso */
            format     = long_format;        /* uVar10 = 0 */
            time_style = "full-iso";         /* local_88 */
            break;

        case 0x87:  /* --group-directories-first */
            directories_first = true;        /* DAT_00128314 = 1 */
            break;

        case 0x88:  /* --hide=PATTERN：隐藏匹配项（不影响 -a/-A） */
            {
                /*
                 * 分配 16 字节节点，链入 hide_patterns 链表头。
                 * 节点布局：[0]=pattern, [1]=next。
                 */
                ulong *node = xmalloc(0x10);
                node[0]          = (ulong)optarg;
                node[1]          = (ulong)hide_patterns;
                hide_patterns    = node;     /* DAT_00128300 */
            }
            break;

        case 0x89:  /* --hyperlink[=WHEN]：文件名输出为 OSC 8 超链接 */
            {
                /* 逻辑同 --color：NULL/always→1, auto→isatty, never→0 */
                bool hl;
                if (optarg == NULL) {
                    hl = true;
                } else {
                    long idx = xargmatch("--hyperlink", optarg,
                                         color_args, color_vals, 4, usage_func, 1,
                                         NULL);
                    if (color_vals[idx] == ALWAYS)
                        hl = true;
                    else if (color_vals[idx] == AUTO)
                        hl = (bool)isatty(1);
                    else
                        hl = false;
                }
                print_hyperlink = hl;        /* DAT_00128331 */
            }
            break;

        case 0x8a:  /* --indicator-style=WORD */
            {
                /*
                 * 通过 xargmatch 将 WORD 映射到 indicator_style 枚举值。
                 * 内部用字符串表 PTR_DAT_001268e0 匹配。
                 * 结果从偏移表（"lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"+…）取出。
                 */
                long idx = xargmatch("--indicator-style", optarg,
                                     indicator_style_args, indicator_style_vals, 4,
                                     usage_func, 1, NULL);
                indicator_style = indicator_style_vals[idx]; /* DAT_00128334 */
            }
            break;

        case 0x8b:  /* --quoting-style=WORD */
            {
                long idx = xargmatch("--quoting-style", optarg,
                                     quoting_style_args, quoting_style_vals, 4,
                                     usage_func, 1, NULL);
                quoting_style = quoting_style_vals[idx]; /* local_8c */
            }
            break;

        case 0x8c:  /* --show-control-chars：显示原始控制字符 */
        /* （与 case 0x91 末尾共用 local_70=0） */
            ignore_mode = 0;                 /* local_70 = 0 */
            break;

        case 0x8d:  /* --si：human-readable，以 1000 为基 */
            /*
             * DAT_00128348 = 0x90 = human_autoscale|human_SI (无 base_1024)
             * DAT_0012833c = 0x90, DAT_00128340 = 1, DAT_00127020 = 1
             */
            human_output_opts      = HUMAN_AUTOSCALE | HUMAN_SI;
            file_output_block_size = 1;
            break;

        case 0x8e:  /* --sort=WORD */
            {
                long idx = xargmatch("--sort", optarg,
                                     sort_args, sort_vals, 4, usage_func, 1,
                                     NULL);
                sort_type_opt = sort_vals[idx]; /* local_90 */
            }
            break;

        case 0x8f:  /* --time=WORD (atime/mtime/ctime/birth/…) */
            {
                long idx = xargmatch("--time", optarg,
                                     time_args, time_vals, 4, usage_func, 1,
                                     NULL);
                time_type_explicit = true;   /* DAT_00128354 = 1 */
                time_type          = time_vals[idx]; /* DAT_00128358 */
            }
            break;

        case 0x90:  /* --time-style=STYLE */
            /* 先保存 optarg，跳回选项解析循环头（switchD_caseD_90） */
            time_style = optarg;             /* local_88 = optarg */
            break;

        case 0x91:  /* --zero / -0：用 NUL 作行分隔符 */
            /*
             * 隐含：关颜色、关 hyperlink、关 dired、
             * 若非 long_format 则改为 one_per_line、literal quoting、
             * 显示控制字符（ignore_mode=0）。
             * 与 --dired 不兼容（后面检查）。
             */
            use_nul_separator  = true;       /* DAT_00127019 */
            print_with_color   = false;
            dired              = false;
            format             = (format != long_format) ? one_per_line : format;
            quoting_style      = literal_quoting_style;
            ignore_mode        = 0;
            break;

        case GETOPT_VERSION_CHAR:  /* --version（gnulib val = (char)-131） */
            {
                /*
                 * DAT_001271e0 决定程序名：
                 *   0=ls, 1=vdir → "vdir", 2=dir → "dir"
                 * 注意 ghidra 输出里条件写反了，实际逻辑：
                 *   != 1 && != 2 → "ls"
                 *   == 2         → "dir"
                 *   == 1         → "vdir"
                 */
                const char *progname = "ls";
                if (ls_mode == 1) progname = "vdir";
                else if (ls_mode == 2) progname = "dir";
                version_etc(stdout, progname, "GNU coreutils", VERSION,
                            proper_name("Richard M. Stallman"),
                            proper_name("David MacKenzie"),
                            NULL);
                exit(EXIT_SUCCESS);
            }

        case GETOPT_HELP_CHAR:    /* --help（gnulib val = (char)-130） */
            usage(EXIT_SUCCESS);
            /* unreachable */

        default:                  /* 未知选项 */
            usage(EXIT_FAILURE);
        }
    } /* end getopt_long loop */

    /* ── 阶段 3：选项后处理 ─────────────────────────────────────────── */

    /*
     * 块大小：
     *   --block-size 未指定（file_output_block_size==0）时读环境变量。
     *   优先 LS_BLOCK_SIZE，其次 BLOCK_SIZE。
     *   -k 强制覆盖：block_size=1024，清除 human_opts（取消自动缩放）。
     */
    if (file_output_block_size == 0) {
        const char *bs = getenv("LS_BLOCK_SIZE");
        human_options(bs, &human_output_opts, &file_output_block_size);
        if (bs != NULL || (bs = getenv("BLOCK_SIZE")) != NULL) {
            /* 同步到目录统计显示 */
            dir_human_opts = human_output_opts;
        }
        if (kibibytes) {                     /* -k 优先级最高 */
            file_output_block_size = 1024;
            human_output_opts      = 0;
        }
    }

    /*
     * 输出格式默认值（format 仍为 -1，即未被选项指定）：
     *   ls   → stdout 是终端 ? many_per_line(2) : one_per_line(1)
     *   vdir → long_format(0)（总是）
     *   dir  → many_per_line(2)（总是）
     *
     * ghidra 里的跳转：
     *   ls_mode==1(vdir)  → LAB_001064c7 → uVar10 = isatty(1) + 1
     *                        isatty 返回 1 → uVar10=2(many_per_line)
     *                        isatty 返回 0 → uVar10=1(one_per_line)
     *   ls_mode==2(dir)   → uVar10 = (2==2)*2 = 2
     *   ls_mode==0(ls)    → uVar10 = (0==2)*2 = 0... 但实际 ls 也走 isatty
     */
    if ((int)format < 0) {
        if (ls_mode == LS_VDIR) {
            format = long_format;
        } else if (ls_mode == LS_DIR) {
            format = many_per_line;
        } else {
            format = isatty(STDOUT_FILENO) ? many_per_line : one_per_line;
        }
    }

    /* 把确定后的 format 写入全局 DAT_0012835c */
    output_format = format;

    /*
     * 终端列宽（line_length）：
     *   多列格式（many_per_line/across/with_commas）或开了颜色时才需要。
     *   优先级：-w > ioctl(TIOCGWINSZ) > $COLUMNS > 80（兜底）。
     *
     *   "(uVar10-2 < 3)" 等价于 uVar10 ∈ {2,3,4}，即三种多列格式。
     *
     *   ioctl 返回的 ws_col 在 local_58._2_2_ 位置（winsize 结构的 ws_col 字段）。
     */
    if ((format - 2 < 3) || print_with_color) {
        if (line_length == (ulong)-1) {
            struct winsize ws;
            if (isatty(1) && ioctl(1, TIOCGWINSZ, &ws) >= 0 && ws.ws_col != 0) {
                line_length = ws.ws_col;
            } else {
                const char *cols = getenv("COLUMNS");
                if (cols != NULL && *cols != '\0') {
                    line_length = parse_integer(cols);
                    if (line_length == (ulong)-1)
                        error(0, 0, dcgettext(0,
                            "ignoring invalid width in environment variable COLUMNS: %s",
                            LC_MESSAGES), quotearg(cols));
                }
                if (line_length == (ulong)-1)
                    line_length = 80;        /* 最终兜底：80 列 */
            }
        }
    } else if (line_length == (ulong)-1) {
        line_length = 80;
    }

    /*
     * DAT_00128220 = ceil(line_length / 3)：多列初始列数估算。
     * DAT_001282d0 = line_length（供后续精确计算使用）。
     */
    columns_estimate = (line_length / 3 + 1) - (line_length % 3 == 0);
    terminal_width   = line_length;

    /*
     * 制表符宽度（tabsize_opt）：
     *   -T 已指定（local_78 >= 0）→ 直接用。
     *   否则读 $TABSIZE，再兜底到 8。
     *   仅多列格式（format-2 < 3）时有意义。
     */
    if ((format - 2 < 3) && (long)tabsize_opt < 0) {
        tabsize = 8;                         /* DAT_001282e0 = 8 */
        const char *ts = getenv("TABSIZE");
        if (ts != NULL) {
            long v;
            int err = xstrtol(ts, NULL, 0, &v, NULL);
            if (err != 0)
                error(0, 0, dcgettext(0,
                    "ignoring invalid tab size in environment variable TABSIZE: %s",
                    LC_MESSAGES), quotearg(ts));
            else
                tabsize = (int)v;
        }
    } else {
        tabsize = (int)(long)tabsize_opt;
    }

    /*
     * 控制字符显示模式（qmark_funny_chars）：
     *   ignore_mode==1  → 显示为 ?（-q）
     *   ignore_mode==0  → 显示原字符（-N/--show-control-chars）
     *   ignore_mode==-1 → ls 模式且输出到终端时自动隐藏
     *
     *   bVar7 = (byte)local_70 & 1：取 bit0，ignore_mode==1 时为 1。
     */
    bool qmark_funny_chars;
    if (ignore_mode == -1) {
        qmark_funny_chars = (ls_mode == LS_LS) ? (bool)isatty(1) : false;
    } else {
        qmark_funny_chars = (ignore_mode == 1);
    }
    print_funny_chars = qmark_funny_chars;   /* DAT_001282f8 */

    /*
     * 引用风格：优先命令行，其次 $QUOTING_STYLE，最后兜底。
     * 兜底规则：
     *   ls 模式且输出到终端 → shell_escape_quoting_style(3)
     *   其他 → literal_quoting_style(7)
     */
    if (quoting_style < 0) {
        const char *qs_env = getenv("QUOTING_STYLE");
        if (qs_env != NULL) {
            int idx = argmatch(qs_env, quoting_style_args, quoting_style_vals, 4);
            if (idx < 0) {
                error(0, 0, dcgettext(0,
                    "ignoring invalid value of environment variable QUOTING_STYLE: %s",
                    LC_MESSAGES), quotearg(qs_env));
                /* LAB_0010670b → LAB_00105a42: quoting_style = 7(literal) */
                quoting_style = literal_quoting_style;
                if (ls_mode == LS_LS && isatty(1))
                    quoting_style = shell_escape_quoting_style;
            } else {
                quoting_style = quoting_style_vals[idx];
            }
        }
        if (quoting_style < 0)
            quoting_style = literal_quoting_style;
    }
    set_quoting_style(NULL, quoting_style);  /* FUN_00118160 */

    /*
     * 配置文件名的 quoting_options 对象（决定哪些字符需要引用）：
     *   FUN_00118140(0) = get_quoting_style(NULL) 取当前风格值。
     *   用 0x4a 位掩码（0b01001010）区分两组风格：
     *     bit 位为 1（风格=1/3/6）→ 文件名/目录名用同一引用选项
     *     bit 位为 0 → 目录名额外对 ':' 引用（防止混淆 host:path）
     *   indicator_style > SLASH 时把指示符字符加入引用集。
     *
     *   DAT_001282f0 = filename_quoting_options
     *   DAT_001282e8 = dirname_quoting_options
     */
    {
        int qs = get_quoting_style(NULL);
        quoting_options *fqo = clone_quoting_options(NULL); /* FUN_00118100 */
        /* 根据 indicator_style 设置需要引用的特殊字符 */
        if (indicator_style > SLASH) {
            /* 把 * @ | = 等指示符字符加入引用集 */
            const char *indicator_chars = &indicator_char_table[indicator_style - 2];
            for (const char *p = indicator_chars; *p; p++)
                set_char_quoting(fqo, *p, 1); /* FUN_00118180 */
        }
        filename_quoting_options = fqo;

        quoting_options *dqo = clone_quoting_options(NULL);
        if ((0x4aUL >> (qs & 0x3f) & 1) == 0) {
            /* 目录名额外引用冒号，避免 user@host:dir 歧义 */
            set_char_quoting(dqo, ':', 1);
        }
        dirname_quoting_options = dqo;       /* DAT_001282e8 */
    }

    /* --dired 与 --zero 不兼容 */
    /*
     * DAT_00128338(dired) 与 DAT_00127019(use_nul_separator) 同时为真 → 报错。
     * 原始表达式：(dired ^ 1) & (format==0) & dired
     * 即 dired 且 format==long_format 时才有效（dired 隐含 long_format）。
     */
    if (dired && use_nul_separator)
        error(EXIT_FAILURE, 0,
              dcgettext(0, "--dired and --zero are incompatible", LC_MESSAGES));

    /*
     * 排序方式默认值：
     *   long_format 且 time_type_explicit → SORT_TIME
     *   否则 → SORT_NAME
     */
    if (sort_type_opt < 0) {
        if (output_format == long_format)
            sort_type = time_type_explicit ? SORT_TIME : SORT_NAME;
        else
            sort_type = SORT_NAME;
    } else {
        sort_type = sort_type_opt;
    }
    /* 若 format==long_format 且 sort_type!=SORT_NAME，输出时需要 stat */

    /*
     * 时间格式（--time-style / $TIME_STYLE，仅 long_format 时有意义）：
     *
     * "posix-" 前缀处理：在 POSIX locale 下剥去前缀，
     * 非 POSIX locale 则直接跳过时间格式设置（保持默认）。
     * FUN_00111400(2) = is_locale_posix()。
     *
     * "+FORMAT[\nFORMAT2]" 形式：类似 date 命令的格式串，
     * 用 \n 分割"近期文件格式"和"旧文件格式"，超过一个 \n 报错。
     *
     * 命名样式索引（lVar26）：
     *   0 = full-iso  → "%Y-%m-%d %H:%M:%S.%N %z"（两段相同）
     *   1 = long-iso  → "%Y-%m-%d %H:%M"（两段相同）
     *   2 = iso       → recent: "%Y-%m-%d", old: " %b %e  %Y"
     *   3 = locale    → 从 LC_TIME 翻译格式串（FUN_00111400 检查是否 POSIX）
     *
     *   PTR_DAT_00127040 = long_time_format[0]（近期文件）
     *   PTR_s__b__e__H__M_00127048 = long_time_format[1]（旧文件）
     */
    if (output_format == long_format) {
        if (time_style == NULL)
            time_style = getenv("TIME_STYLE");
        if (time_style == NULL)
            time_style = "locale";

        /* 循环剥去 "posix-" 前缀 */
        while (strncmp(time_style, "posix-", 6) == 0) {
            if (!is_locale_posix())
                goto apply_time_format; /* 非 POSIX locale，跳过剩余前缀 */
            time_style += 6;
        }

        if (*time_style == '+') {
            /* "+FORMAT" 或 "+FORMAT1\nFORMAT2" */
            char *fmt = time_style + 1;
            char *nl  = strchr(fmt, '\n');
            char *fmt_recent = fmt, *fmt_old = fmt;
            if (nl != NULL) {
                if (strchr(nl + 1, '\n') != NULL)
                    error(EXIT_FAILURE, 0,
                          dcgettext(0, "invalid time style format %s", LC_MESSAGES),
                          quotearg(fmt));
                *nl     = '\0';
                fmt_old = nl + 1;
            }
            long_time_format[0] = fmt_recent;
            long_time_format[1] = fmt_old;
        } else {
            /* 命名样式匹配 */
            long idx = argmatch(time_style, time_style_args, time_style_vals, 4);
            if (idx < 0) {
                /* 非法值：打印合法列表并以错误码退出 */
                argmatch_die("time style", time_style, idx);
            }
            switch (idx) {
            case 0: /* full-iso */
                long_time_format[0] = long_time_format[1] = "%Y-%m-%d %H:%M:%S.%N %z";
                break;
            case 1: /* long-iso */
                long_time_format[0] = long_time_format[1] = "%Y-%m-%d %H:%M";
                break;
            case 2: /* iso */
                long_time_format[0] = "%Y-%m-%d ";
                long_time_format[1] = " %b %e  %Y";
                break;
            case 3: /* locale */
                if (is_locale_posix()) {
                    /* POSIX locale：通过 dcgettext 翻译格式串 */
                    long_time_format[0] = dcgettext(0, long_time_format[0], LC_TIME);
                    long_time_format[1] = dcgettext(0, long_time_format[1], LC_TIME);
                }
                break;
            }
        }
apply_time_format:
        init_time_display();             /* FUN_00106e80 */
    }

    /* ── 阶段 4：颜色初始化（LS_COLORS 解析）───────────────────────── */
    /*
     * 来源优先级：
     *   1. $LS_COLORS 非空 → 解析键值对，写入 color_indicator[] 和 color_ext_list
     *   2. $COLORTERM 非空 → 直接信任终端支持颜色
     *   3. $TERM 匹配内建 termcap 数据库 → 启用
     *   4. 都不匹配 → 关闭颜色（DAT_00128332 = 0）
     */
    if (print_with_color) {
        const char *ls_colors = getenv("LS_COLORS");
        if (ls_colors != NULL && *ls_colors != '\0') {
            color_buf = xstrdup(ls_colors); /* FUN_0011a180 */
            char *p   = color_buf;

            /*
             * LS_COLORS 解析循环（LAB_00105d12）：
             *
             * 格式：[TYPE_CODE=SGR:]*[*.EXT=SGR:]*
             *
             * 分支：
             *   p[0] == '*' → 扩展名规则（*.ext=SGR）：
             *       分配 0x30(48) 字节节点，布局：
             *         [0]=ext_len, [1]=ext_str, [2]=sgr_len, [3]=sgr_str
             *         [4]=ambiguous_flag, [5]=next（链表指针）
             *       链入 color_ext_list（DAT_00128328）头部。
             *       FUN_00106920 解析 ext/sgr 字段，失败跳 LAB_00105eeb。
             *
             *   p[0] == ':' → 分隔符，跳过。
             *
             *   p[0] == '\0' → 解析完成；
             *       对 color_ext_list 做去重：两两比较扩展名（大小写不敏感，
             *       FUN_0010f3c0 = fnmatch_casefold 或 strcasecmp），
             *       完全相同（memcmp 扩展名和 SGR 都相同）→ 删除后者（size=-1），
             *       扩展名相同但 SGR 不同且未标记 → 双方置 ambiguous=1。
             *
             *   否则 → 双字母类型代码（如 "di"、"ex"、"ln"…）：
             *       在内建代码表 "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"
             *       中查找（每两字节一个代码，共 0x18=24 个），
             *       写入对应 color_indicator[idx]。
             *       未找到 → 报错 "unrecognized prefix: %s"（LAB_00105eab）。
             *
             * 解析失败（LAB_00105eeb）：
             *   报 "unparsable value for LS_COLORS environment variable"，
             *   释放 color_buf 和整个 color_ext_list，关闭颜色。
             */
            parse_ls_colors(p);

            /*
             * DAT_001270d0 = color_indicator[C_LINK].len
             * PTR_DAT_001270d8 = color_indicator[C_LINK].string
             * 若 ln 颜色配置为 "target"（6字节），设 color_symlink_as_referent=1。
             */
            if (color_indicator[C_LINK].len == 6
                && strncmp(color_indicator[C_LINK].string, "target", 6) == 0)
                color_symlink_as_referent = true; /* DAT_001283b0 */

        } else {
            /* 无 $LS_COLORS，尝试 $COLORTERM */
            const char *colorterm = getenv("COLORTERM");
            if (colorterm == NULL || *colorterm == '\0') {
                /* 尝试 $TERM 与内建 termcap 数据库比对（fnmatch）*/
                const char *term = getenv("TERM");
                if (term == NULL || *term == '\0') {
                    print_with_color = false; /* LAB_0010656a */
                } else {
                    /*
                     * 遍历内建 dircolors 数据库字符串（编译进二进制）：
                     * 每行以 "TERM " 开头，后跟 glob pattern。
                     * strncmp(line,"TERM ",5)==0 && fnmatch(pattern,term,0)==0
                     *   → 匹配，启用颜色（goto LAB_00106215）。
                     * 超出数据库边界（pcVar22+-0x11b900 > 0x15ef）→ 未匹配，关颜色。
                     */
                    bool matched = match_term_in_database(term);
                    if (!matched)
                        print_with_color = false;
                }
            }
            /* $COLORTERM 非空 → 直接跳 LAB_00106215（使用内建默认颜色配置） */
        }
    }

    /* ── 阶段 5：最终准备 ───────────────────────────────────────────── */

    /*
     * 根据颜色配置决定 tab_size 显示行为：
     *   颜色模式下 tabsize 设为 0（不展开 tab），防止 ANSI 转义序列错位。
     */
    if (print_with_color)
        tabsize = 0;                         /* DAT_001282e0 = 0 */

    /*
     * check_symlink_color / need_fullname 等衍生标志：
     *
     *   DAT_0012831d = check_symlink_color：
     *     颜色模式下需要检查 ln 指向的目标类型，或开了 --group-directories-first，
     *     或 color_symlink_as_referent && (某颜色类型设置了) 时置 1。
     *
     *   DAT_001282c2 = need_stat：
     *     需要 stat() 的条件之一：-s / --hyperlink / -Z / long_format /
     *     sort_type ∈ {SORT_TIME, SORT_SIZE} 等。
     *     表达式：print_block_size | print_hyperlink | print_scontext |
     *             (format==0) | (sort_type-3 & ~2)==0
     *
     *   DAT_001282c1 = need_fullname：
     *     (print_scontext|recursive|print_with_color|directories_first|
     *      indicator_style!=NONE) & !need_stat
     *
     *   DAT_001282c0 = colorize_symlink_as_referent：
     *     print_with_color && get_color_indicator(C_CLR_TO_EOL) 非空
     */
    compute_derived_flags();

    /*
     * 解引用默认值（若未显式指定 -L/-H）：
     *   long_format 且 indicator_style 不是 CLASSIFY → 跟随符号链接到目录
     *   DAT_00128318 = 0 时设为 1（DEREF_COMMAND_LINE_SYMLINK_TO_DIR）；
     *   indicator_style != 3 且不是 long_format → 设为 3。
     */
    if (dereference == DEREF_UNDEFINED
        && directory_as_plain == '\0'
        && indicator_style != CLASSIFY
        && output_format != long_format)
        dereference = DEREF_COMMAND_LINE_SYMLINK_TO_DIR;
    if (dereference == DEREF_UNDEFINED)
        dereference = DEREF_COMMAND_LINE_SYMLINK_TO_DIR;
    if (output_format != long_format && indicator_style != CLASSIFY
        && output_format != 0)
        dereference = DEREF_ALWAYS;

    /*
     * 递归模式：创建 active_dir_set（hash set，dev+ino 作键，防止符号链接环路）。
     * 同时初始化 dev_ino_obstack（存放路径上各级目录的 {dev,ino} 对）。
     * FUN_00111e30 = hash_initialize(bucket_count=30, …, hash_fn, cmp_fn, free_fn)
     */
    if (recursive) {
        active_dir_set = hash_initialize(30, NULL,
                                         dev_ino_hash, dev_ino_compare, free);
        if (active_dir_set == NULL)
            xalloc_die();
        obstack_init(&dev_ino_obstack); /* FUN_001161c0(&DAT_00128100,…) */
    }

    /* 缓存时区（供 localtime_rz 使用，避免重复解析 TZ）*/
    localtz = tzalloc(getenv("TZ"));     /* FUN_00119090 */

    /* --dired 需要两个 obstack 记录文件名的字节偏移，供 Emacs 解析 */
    if (dired) {
        obstack_init(&dired_obstack);    /* FUN_001161c0(&DAT_001281c0,…) */
        obstack_init(&subdired_obstack); /* FUN_001161c0(&DAT_00128160,…) */
    }

    /*
     * --hyperlink：预计算 URL 合法字符位表（url_safe_chars[256]）。
     *
     * 合法字符（RFC 3986 unreserved + path 字符）：
     *   A-Z, a-z, 0-9, -, ., _, ~（unreserved）
     *   数字 0x30-0x39、大写 0x41-0x5a、连字符 0x2d、若干标点
     *   下划线 0x5f、a-z 0x61-0x7a、波浪号 0x7e
     *
     * 代码逻辑（uVar16 从 0 到 0xff 逐字节）：
     *   0x30-0x39（'0'-'9'）、0x41-0x5a（'A'-'Z'）、0x2d('-')、
     *   0x5f('_')、0x61-0x7a('a'-'z')、0x7e('~') → 置位 1
     *   其余字节 → 保持不变（percent-encode 时转义）
     *
     * DAT_001283a8 = hostname_str（由 xgethostname() 获取，见 func1_opus47.c）
     */
    if (print_hyperlink) {
        for (unsigned i = 0; i < 256; i++) {
            bool safe = (i >= '0' && i <= '9')
                     || (i >= 'A' && i <= 'Z')
                     || (i >= 'a' && i <= 'z')
                     || i == '-' || i == '.' || i == '_' || i == '~';
            url_safe_chars[i] |= (unsigned char)safe;
        }
        hostname_str = xgethostname();   /* FUN_0011a360，见 func1_opus47.c */
        if (hostname_str == NULL)
            hostname_str = "";           /* DAT_0011cf4c：空字符串兜底 */
    }

    /* 分配初始文件数组（100 项，可扩容）*/
    max_entries = 100;                   /* DAT_001283d8 */
    files       = xmalloc(0x5140);      /* DAT_001283e0，FUN_00119d00 */

    /* 全局已排序文件数清零 */
    cwd_n_used = 0;                      /* DAT_001283d0 */

    initialize_pad_buf();               /* FUN_001087c0：预填充空格缓冲区 */

    /* ── 阶段 6：列文件 / 列目录 ────────────────────────────────────── */

    /*
     * argc - optind = 剩余非选项参数数量。
     * iVar8 = param_1 - optind（param_1 = argc）。
     */
    int n_args = argc - optind;

    if (n_args < 1) {
        /* 无路径参数：列当前目录 "." */
        if (directory_as_plain == '\0')
            gobble_file(".", directory, true, "");   /* FUN_001071c0 */
        else
            gobble_file_as_dir(".", 3, true, 0);     /* FUN_0010ca80 */

        if (cwd_n_used != 0)
            goto flush_pending;
    } else {
        /* 逐个处理命令行路径 */
        for (int i = optind; i < argc; i++)
            gobble_file(argv[i], unknown, true, "");

        if (cwd_n_used == 0)
            goto process_pending_dirs;

flush_pending:
        sort_files();                    /* FUN_00108e30 */
        if (directory_as_plain == '\0')
            print_current_files(0, true);/* FUN_00109530 */

        if (cwd_n_used != 0) {
            queue_directory(NULL, NULL, false); /* FUN_0010c650：入队 */
            if (pending_dirs != NULL) {
                /* 多目录间插入空行分隔 */
                output_line_count++;     /* DAT_00128218++ */
                putchar_unlocked('\n');
            }
        }
    }

process_pending_dirs:
    /*
     * 处理 pending_dirs 链表（待展开的目录队列）。
     * 链表节点布局（ghidra 中 __ptr[0..3]）：
     *   [0] = name（char *）
     *   [1] = realname（char *）
     *   [2] = command_line_arg（bool）
     *   [3] = next（struct pending *）
     */
    while (pending_dirs != NULL) {
        long *entry   = pending_dirs;    /* __ptr */
        pending_dirs  = (long *)entry[3];/* 推进到下一项 */

        if (active_dir_set == NULL || *entry != 0) {
            /* 非递归模式，或该目录未在 active_dir_set 中（未被追踪） */
            print_dir(entry[0], entry[1], (bool)entry[2]); /* FUN_0010dc80 */
            free((void *)entry[0]);
            free((void *)entry[1]);
            free(entry);
            print_dir_name = true;
        } else {
            /*
             * 递归模式：从 dev_ino_obstack 弹出当前目录的 {dev,ino}，
             * 然后从 active_dir_set 中删除（允许将来再次进入同层目录）。
             *
             * assert 保证 obstack 至少有 16 字节（一个 {dev,ino} 条目）：
             * "dev_ino_size <= obstack_object_size(&dev_ino_obstack)"
             * 见 src/ls.c:0x442 "dev_ino_pop"。
             */
            if ((ulong)(dev_ino_top - dev_ino_base) < 0x10)
                __assert_fail(
                    "dev_ino_size <= ...",
                    "src/ls.c", 0x442, "dev_ino_pop");
            dev_ino_entry saved;
            saved = *(dev_ino_entry *)(dev_ino_top - 0x10);
            dev_ino_top -= 0x10;

            void *found = hash_delete(active_dir_set, &saved); /* FUN_00112530 */
            if (found == NULL)
                __assert_fail("found", "src/ls.c", 0x73d, "main");
            free(found);
            print_dir(entry[0], entry[1], (bool)entry[2]);
            free((void *)entry[0]);
            free((void *)entry[1]);
            free(entry);
        }
    }

    /* ── 清理与尾部输出 ─────────────────────────────────────────────── */

    /*
     * 颜色重置：若最后输出了颜色转义序列，需发送 SGR 0 复位。
     * DAT_00128330 = used_color_this_time（标记本次运行用过了颜色）。
     *
     * 复位逻辑：
     *   若当前颜色不是"默认色"（即 color_indicator[C_LEFT/C_RESET] 不是标准
     *   ESC[0m），则先用 put_indicator 输出重置序列（FUN_00107990）。
     *   判断条件（ghidra）：DAT_00127060 != 2 ||
     *     *(short*)color_indicator[0].string != 0x5b1b ||  ("ESC[")
     *     color_indicator[1].len != 1 ||
     *     *color_indicator[1].string != 'm'
     *   即若 lc/rc 不是标准 "ESC[" / "m"，则需显式输出重置。
     *
     * SIGTSTP 处理：若进程曾被 SIGTSTP 暂停（DAT_00128234 次），
     *   补发对应次数的 SIGTSTP，让 shell 感知（raise(SIGTSTP)）。
     * 其他信号：DAT_00128238 非 0 时补发该信号。
     */
    if (print_with_color && used_color_this_time) {
        if (color_indicator_not_default()) {
            put_indicator(&color_indicator[C_LEFT]);  /* FUN_00107990 */
            put_indicator(&color_indicator[C_RESET]);
        }
        fflush_unlocked(stdout);
        restore_default_color(0);        /* FUN_001077e0 */

        for (int i = tstp_count; i != 0; i--)
            raise(SIGTSTP);              /* raise(0x13) */
        if (exit_signal)
            raise(exit_signal);          /* DAT_00128238 */
    }

    /*
     * --dired 尾部输出：
     *   "//DIRED// offset1 len1 offset2 len2 ..."（文件名在输出中的字节偏移）
     *   "//SUBDIRED// ..."（子目录名的偏移）
     *   "//DIRED-OPTIONS// --quoting-style=STYLE"
     * 供 Emacs dired-mode 精确解析文件名，实现交互操作。
     */
    if (dired) {
        dired_dump_obstack("//DIRED//",    &dired_obstack);  /* FUN_00107670 */
        dired_dump_obstack("//SUBDIRED//", &subdired_obstack);
        printf("//DIRED-OPTIONS// --quoting-style=%s\n",
               quoting_style_args[get_quoting_style(filename_quoting_options)]);
    }

    /*
     * 递归模式：断言 active_dir_set 已空（所有目录都已处理完毕，
     * 否则说明有目录被跳过，是 bug）。
     * assert 字符串："hash_get_n_entries (active_dir_set) == 0"
     * 来自 src/ls.c:0x771 "main"。
     */
    if (active_dir_set != NULL) {
        if (hash_get_n_entries(active_dir_set) != 0) /* FUN_00111900 */
            __assert_fail(
                "hash_get_n_entries (active_dir_set) == 0",
                "src/ls.c", 0x771, "main");
        hash_free(active_dir_set);       /* FUN_00111ff0 */
    }

    /* 栈保护检查（local_40 = *(FS+0x28) 金丝雀）*/
    /* if (local_40 != *(long *)(in_FS_OFFSET + 0x28)) __stack_chk_fail(); */

    return exit_status;                  /* DAT_00128230 */
}
