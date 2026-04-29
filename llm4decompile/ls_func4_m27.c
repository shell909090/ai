/* 00104c00: ls 命令的主函数
 * 对应关系:
 *   FUN_00104c00 -> main (ls命令入口)
 *   FUN_00106ce0 -> print_delimiter (打印分隔符,推测)
 *   FUN_00106de0 -> parse_positive_integer (解析无符号整数)
 *   FUN_00106e50 -> isatty (检查是否为终端)
 *   FUN_001068c0 -> check_terminal_mode (检查终端模式)
 *   FUN_0010f1d0 -> get_enum_value (解析枚举选项值)
 *   FUN_0010ee80 -> get_sort_style_value (解析排序风格)
 *   FUN_00113490 -> parse_size_string (解析大小字符串如"1K")
 *   FUN_00118160 -> set_quoting_style (设置引用风格)
 *   FUN_00118140 -> get_format_index (获取格式索引)
 *   FUN_00118100 -> create_output_stream (创建输出流)
 *   FUN_00118180 -> write_char (写字符)
 *   FUN_00111e30 -> hash_init (初始化哈希表)
 *   FUN_001161c0 -> obstack_init (初始化obstack)
 *   FUN_00119090 -> set_timezone (设置时区)
 *   FUN_0011a360 -> get_hostname_alloc (获取主机名,前一个文件已分析)
 *   FUN_00119d00 -> malloc_wrapper (分配内存)
 *   FUN_0011ace0 -> install_signal_handler (安装信号处理)
 *   FUN_0011a180 -> parse_ls_colors (解析LS_COLORS)
 *   FUN_00106920 -> parse_color_sequence (解析颜色序列)
 *   FUN_00107670 -> print_dired_tag (打印DIRED标记)
 *   FUN_00107990 -> print_escape_sequence (打印转义序列)
 *   FUN_001087c0 -> initial_file_scan (初始文件扫描)
 *   FUN_00108e30 -> sort_and_print_files (排序并打印文件)
 *   FUN_00109530 -> print_files_long_format (长格式打印)
 *   FUN_0010dc80 -> free_dir_entry (释放目录条目)
 *   FUN_001071c0 -> print_dir_header (打印目录头部)
 *   FUN_0010ca80 -> print_file_entry (打印文件条目)
 *   FUN_0010c650 -> finish_output (完成输出)
 *   FUN_00111900 -> hash_get_entries (获取哈希条目数)
 *   FUN_00111ff0 -> hash_free (释放哈希表)
 *   FUN_00116460 -> file_stream_init (文件流初始化)
 *   FUN_00116520 -> author_string_alloc (分配作者字符串)
 *   FUN_00119b30 -> print_version (打印版本信息)
 *   FUN_00118c20 -> error_message_alloc (分配错误消息)
 *   FUN_0011a470 -> print_error_and_exit (打印错误并退出)
 *   FUN_0011a1c0 -> xalloc_die (内存分配失败处理)
 *   FUN_0011a200 -> parse_tab_size (解析tab大小)
 *   FUN_0011a540 -> parse_tab_size_full (解析tab大小完整版)
 *   FUN_00110f000 -> invalid_option_error (无效选项错误)
 *   FUN_0010e360 -> usage_error (用法错误)
 *   FUN_001077e0 -> reset_terminal (重置终端)
 *   FUN_00111400 -> is_posix_mode (检查POSIX模式)
 *   FUN_00112530 -> hash_lookup (哈希查找)
 *   FUN_0010f3c0 -> strcoll_compare (字符串排序比较)
 *
 * 全局变量对应(推测):
 *   DAT_001271f8 -> sort_options (排序选项)
 *   DAT_00128230 -> exit_status (退出状态)
 *   DAT_001282d8 -> files_index (文件索引)
 *   DAT_001283a0 -> pending_directories (待处理目录链表)
 *   DAT_00128390 -> max_depth (最大遍历深度)
 *   DAT_00128398 -> sentinel_value (哨兵值)
 *   DAT_00128310 -> all_flag (all选项标志)
 *   DAT_00128318 -> format_mode (格式模式:long/single/col)
 *   DAT_0012831c -> inode_flag (显示inode)
 *   DAT_0012831d -> indicator_style_flag (指标样式)
 *   DAT_00128314 -> recursive_flag (递归标志)
 *   DAT_00128315 -> dereference_flag (dereference选项)
 *   DAT_00128316 -> sort_reverse (反向排序)
 *   DAT_00128332 -> color_flag (颜色标志)
 *   DAT_00128334 -> classify_mode (分类模式)
 *   DAT_00128331 -> hyperlink_flag (超链接标志)
 *   DAT_00128389 -> zero_terminated (零终止输出)
 *   DAT_00128338 -> dired_flag (DIRED输出标志)
 *   DAT_00128348 -> block_size (块大小)
 *   DAT_0012833c -> output_width (输出宽度)
 *   DAT_00128340 -> use_custom_blocksize (使用自定义块大小)
 *   DAT_0012834c -> show_sort_time (显示排序时间)
 *   DAT_0012834d -> numeric_uid_gid (数字UID/GID)
 *   DAT_0012834f -> show_size (显示大小)
 *   DAT_00128350 -> time_style (时间格式风格)
 *   DAT_00128354 -> time_style_posix (时间风格POSIX标志)
 *   DAT_00128358 -> sort_type (排序类型)
 *   DAT_0012835c -> sort_key (排序关键字)
 *   DAT_00128300 -> ignore_patterns (忽略模式链表)
 *   DAT_00128320 -> color_parsed (解析后的颜色)
 *   DAT_00128328 -> color_patterns (颜色模式链表)
 *   DAT_00127020 -> block_size_override (块大小覆盖)
 *   DAT_00127028 -> follow_symlinks (跟随符号链接)
 *   DAT_00127029 -> literal_flag (字面量标志)
 *   DAT_00127019 -> literal_mode (字面模式)
 *   DAT_00127060 -> term_escape_start (终端转义序列开始)
 *   DAT_00127068 -> term_color_table (终端颜色表)
 *   DAT_00127070 -> term_escape_end (终端转义序列结束)
 *   DAT_001270d0 -> check_target_mode (检查target模式)
 *   DAT_001270d8 -> target_string (target字符串)
 *   DAT_001271e0 -> program_mode (程序模式:ls/vdir/dir)
 *   DAT_001271e8 -> version_urls (版本URL)
 *   DAT_00128100 -> dir_obstack (目录obstack)
 *   DAT_001281c0 -> dired_obstack (dired输出obstack)
 *   DAT_00128160 -> subdired_obstack (子目录dired-obstack)
 *   DAT_00128118 -> dev_ino_ptr (设备inode指针)
 *   DAT_00128218 -> file_count (文件计数)
 *   DAT_00128220 -> line_count (行数)
 *   DAT_00128234 -> signal_number (信号编号)
 *   DAT_00128238 -> second_signal (第二个信号)
 *   DAT_001282c8 -> timezone_info (时区信息)
 *   DAT_001282c2 -> context_bits (上下文位)
 *   DAT_001282c1 -> style_bits (样式位)
 *   DAT_001282c0 -> quote_char (引用字符)
 *   DAT_001282d0 -> terminal_columns (终端列数)
 *   DAT_001282e0 -> tab_size (tab大小)
 *   DAT_001282f0 -> format_stream (格式输出流)
 *   DAT_001282f8 -> single_column (单列标志)
 *   DAT_001283c8 -> indicator_flag (指标标志)
 *   DAT_001283e8 -> dir_hash_table (目录哈希表)
 *   DAT_001283e0 -> error_buffer (错误缓冲区)
 *   DAT_001283d8 -> buffer_size (缓冲区大小)
 *   DAT_001283d0 -> error_count (错误计数)
 *   DAT_001283a8 -> hostname (主机名,用于超链接)
 *   DAT_00128000 -> char_class_table (字符分类表)
 *   DAT_001283b0 -> status_printed (状态已打印)
 *   DAT_00128330 -> color_used (颜色已使用)
 *   DAT_001282e8 -> current_pos (当前位置)
 *   PTR_s_all_00126340 -> "all" 字符串指针
 *   PTR_s_always_00126200 -> "always" 字符串指针
 *   PTR_s_verbose_00126300 -> "verbose" 字符串指针
 *   PTR_s_literal_001269a0 -> "literal" 字符串指针
 *   PTR_s_full_iso_00126920 -> "full-iso" 字符串指针
 *   PTR_FUN_001271f0 -> print_function (打印函数)
 *   PTR_DAT_001268e0 -> indicator_style_table (指标样式表)
 */

int main(int argc, char **argv)
{
    char cVar1;
    void *__s1;
    byte bVar2;
    FILE *__stream;
    ulong uVar3;
    char cVar4;
    undefined1 uVar5;
    char cVar6;
    byte bVar7;
    int iVar8;
    int iVar9;
    uint uVar10;
    long lVar11;
    undefined8 *puVar12;
    void *pvVar13;
    undefined8 uVar14;
    undefined8 uVar15;
    ulong uVar16;
    size_t sVar17;
    size_t *psVar18;
    char *pcVar19;
    undefined **ppuVar20;
    long *__ptr;
    size_t *psVar21;
    char *pcVar22;
    undefined *puVar23;
    undefined8 *puVar24;
    undefined *in_R9;
    undefined8 *in_R10;
    undefined8 in_R11;
    char *pcVar25;
    long lVar26;
    size_t *psVar27;
    long in_FS_OFFSET;
    bool bVar28;
    int local_90;
    int local_8c;
    char *local_88;
    ulong local_80;
    undefined *local_78;
    int local_70;
    char *local_60;
    undefined8 local_58;
    undefined8 uStack_50;
    char local_44;
    char local_43;
    undefined1 local_42;
    long local_40;

    /* Stack canary check */
    local_40 = *(long *)(in_FS_OFFSET + 0x28);

    /* === 初始化阶段 === */
    file_stream_init(*(undefined8 *)argv);      /* 初始化文件流 */
    setlocale(6, "");                          /* 设置locale: LC_ALL=0 */
    bindtextdomain("coreutils", "/usr/share/locale");
    textdomain("coreutils");
    sort_options = 2;                          /* 默认排序选项 */
    install_signal_handler(signal_handler);
    exit_status = 0;
    files_index = 1;
    pending_directories = (long *)0x0;

    /* 初始化默认值 */
    local_80 = 0xffffffffffffffff;            /* line_width 未设置 */
    local_78 = (undefined *)0xffffffffffffffff; /* tab_size 未设置 */
    local_90 = -1;                             /* time_style 未设置 */
    local_8c = -1;                             /* quoting_style 未设置 */
    local_70 = -1;                             /* format 未设置 */
    uVar10 = 0xffffffff;
    bVar28 = false;
    local_88 = (char *)0x0;
    max_depth = 0x8000000000000000;
    sentinel_value = 0xffffffffffffffff;

    /* === 命令行参数解析循环 === */
    LAB_00104d00:
    ppuVar20 = &PTR_s_all_00126340;
    puVar23 = (undefined *)(ulong)argc;
    local_58 = (undefined *)CONCAT44(local_58._4_4_, 0xffffffff);
    puVar24 = &local_58;

    /* getopt_long: 解析命令行选项 */
    iVar8 = getopt_long(puVar23, argv,
        "abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1",  /* 选项字符串 */
        NULL,  /* long_options */
        NULL); /* option_index */

    if (iVar8 != -1) {
        /* 选项值范围检查,跳转到对应处理分支 */
        if (0x114 < iVar8 + 0x83U) goto switchD_00104d37_caseD_ffffff7f;

        switch(iVar8) {
        case '1':  /* 单列输出 */
            uVar10 = (uint)(uVar10 != 0);
            break;

        case 'A':  /* almost-all: 不显示 . 和 .. */
            DAT_00128310 = 1;
            break;

        case 'B':  /* escape: 不打印文件名控制字符 */
            print_delimiter(&DAT_0011d0ef);
            print_delimiter(&DAT_0011d0ee);
            break;

        case 'C':  /* 多列输出 */
            uVar10 = 2;
            break;

        case 'D':  /* dired 模式 */
            in_R11 = 0;
            DAT_00128331 = 0;
            DAT_00128338 = 1;
            uVar10 = 0;
            break;

        case 'F':  /* classify: 在文件名后加类型标识 */
            if (optarg != (char *)0x0) {
                in_R9 = (undefined *)0x1;
                in_R10 = puVar24;
                lVar26 = get_enum_value("--classify", optarg, &PTR_s_always_00126200,
                    &DAT_0011b680, 4, print_function, 1, puVar24);
                if ((*(int *)(&DAT_0011b680 + lVar26 * 4) != 1) &&
                   ((*(int *)(&DAT_0011b680 + lVar26 * 4) != 2 ||
                    (cVar4 = isatty(), cVar4 == '\0'))))
                    break;
            }
            DAT_00128334 = 3;
            break;

        case 'G':  /* no-group: 不显示组信息 */
            DAT_00127028 = 0;
            break;

        case 'H':  /* numeric-uid-gid: 数字UID/GID */
            DAT_00128318 = 2;
            break;

        case 'I':  /* ignore: 忽略指定模式的文件 */
            print_delimiter(optarg);
            break;

        case 'L':  /* dereference: 跟随符号链接 */
            DAT_00128318 = 4;
            break;

        case 'N':  /* literal: 不引用文件名 */
            local_8c = 0;
            break;

        case 'Q':  /* quoting-style: 设置引用风格 */
            local_8c = 5;
            break;

        case 'R':  /* recursive: 递归列出子目录 */
            DAT_00128316 = 1;
            break;

        case 'S':  /* sort by size */
            local_90 = 3;
            break;

        case 'T':  /* tabsize: 设置tab宽度 */
            in_R9 = (undefined *)dcgettext(0, "invalid tab size", 5);
            local_78 = (undefined *)parse_tab_size(optarg, 0, 0, 0x7fffffffffffffff,
                &DAT_0011cf4c, in_R9, 2, 0);
            break;

        case 'U':  /* sort by none (unsorted) */
            local_90 = 6;
            break;

        case 'X':  /* sort by extension */
            local_90 = 1;
            break;

        case 'Z':  /* context: SELinux安全上下文 */
            DAT_00128389 = 1;
            break;

        case 'a':  /* all: 显示所有文件 */
            DAT_00128310 = 2;
            break;

        case 'b':  /* escape: 转义不可打印字符 */
            local_8c = 7;
            break;

        case 'c':  /* change: 使用ctime排序 */
            DAT_00128358 = 1;
            DAT_00128354 = '\x01';
            break;

        case 'd':  /* directory: 只显示目录本身 */
            DAT_00128315 = '\x01';
            break;

        case 'f':  /* sorts only by name, disable sort */
            DAT_00128310 = 2;
            local_90 = 6;
            break;

        case 'g':  /* like -l, but without owner */
            DAT_00127029 = 0;
        case 'l':  /* long listing format */
            uVar10 = 0;
            break;

        case 'h':  /* human-readable: 人类可读大小 */
            DAT_00128348 = 0xb0;  /* 176 = 1024 进制 */
            DAT_0012833c = 0xb0;
            DAT_00128340 = 1;
            DAT_00127020 = 1;
            break;

        case 'i':  /* inode: 显示inode号 */
            DAT_0012831c = 1;
            break;

        case 'k':  /* kibibytes: 使用1024字节块 */
            bVar28 = true;
            break;

        case 'm':  /* comma: 逗号分隔列表 */
            uVar10 = 4;
            break;

        case 'n':  /* numeric-uid-gid: 数字UID/GID */
            DAT_0012834d = 1;
            uVar10 = 0;
            break;

        case 'o':  /* like -l but without group */
            DAT_00127028 = 0;
            uVar10 = 0;
            break;

        case 'p':  /* indicator-style=slash: 目录加/ */
            DAT_00128334 = 1;
            break;

        case 'q':  /* hide-control: 用?代替控制字符 */
            local_70 = 1;
            break;

        case 'r':  /* reverse: 反向排序 */
            DAT_0012834f = 1;
            break;

        case 's':  /* size: 显示文件大小 */
            DAT_0012834c = 1;
            break;

        case 't':  /* sort by time */
            local_90 = 5;
            break;

        case 'u':  /* use time of access */
            DAT_00128358 = 2;
            DAT_00128354 = '\x01';
            break;

        case 'v':  /* sort by version */
            goto switchD_00104d37_caseD_76;

        case 'w':  /* width: 指定输出宽度 */
            local_80 = parse_positive_integer(optarg);
            if (local_80 == 0xffffffffffffffff) {
                argv[1] = (char *)error_message_alloc(optarg);
                uVar14 = dcgettext(0, "invalid line width", 5);
                error(2, 0, "%s: %s", uVar14, argv[1]);
switchD_00104d37_caseD_76:
                local_90 = 4;
            }
            break;

        case 'x':  /* horizontal: 逐行显示 */
            uVar10 = 3;
            break;

        case 0x80:  /* 128, 可能是 --dired */
            DAT_0012834e = 1;
            break;

        case 0x81:  /* 129, --block-size */
            iVar8 = parse_size_string(optarg, &DAT_00128348, &DAT_00128340);
            if (iVar8 != 0) {
                print_error_and_exit(iVar8, (ulong)local_58 & 0xffffffff, 0,
                    &PTR_s_all_00126340, optarg);
            }
            DAT_0012833c = DAT_00128348;
            DAT_00127020 = DAT_00128340;
            break;

        case 0x82:  /* 130, --color */
            if (optarg == (char *)0x0) {
LAB_0010591d:
                bVar7 = 1;
            } else {
                in_R9 = PTR_FUN_001271f0;
                lVar26 = get_enum_value("--color", optarg, &PTR_s_always_00126200,
                    &DAT_0011b680, 4, PTR_FUN_001271f0, 1);
                if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 1) goto LAB_0010591d;
                bVar7 = 0;
                if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 2) {
                    bVar7 = isatty();
                }
            }
            DAT_00128332 = bVar7 & 1;
            break;

        case 0x83:  /* 131, --indicator-style */
            DAT_00128318 = 3;
            break;

        case 0x84:  /* 132, --indicator-style=slash */
            DAT_00128334 = 2;
            break;

        case 0x85:  /* 133, --format */
            in_R9 = puVar23;
            lVar26 = get_enum_value("--format", optarg, &PTR_s_verbose_00126300,
                &DAT_0011b710, 4, PTR_FUN_001271f0, 1, puVar23);
            uVar10 = *(uint *)(&DAT_0011b710 + lVar26 * 4);
            break;

        case 0x86:  /* 134, --time-style */
            uVar10 = 0;
            local_88 = "full-iso";
            break;

        case 0x87:  /* 135, --group-directories-first */
            DAT_00128314 = 1;
            break;

        case 0x88:  /* 136, --hide */
            puVar12 = (undefined8 *)malloc_wrapper(0x10);
            puVar24 = DAT_00128300;
            DAT_00128300 = puVar12;
            *puVar12 = optarg;
            puVar12[1] = puVar24;
            break;

        case 0x89:  /* 137, --hyperlink */
            if (optarg == (char *)0x0) {
LAB_00105934:
                bVar7 = 1;
            } else {
                in_R9 = (undefined *)0x1;
                in_R10 = puVar24;
                lVar26 = get_enum_value("--hyperlink", optarg, &PTR_s_always_00126200,
                    &DAT_0011b680, 4, PTR_FUN_001271f0, 1, puVar24);
                if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 1) goto LAB_00105934;
                bVar7 = 0;
                if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 2) {
                    bVar7 = isatty();
                }
            }
            DAT_00128331 = bVar7 & 1;
            break;

        case 0x8a:  /* 138, --indicator-style */
            in_R9 = PTR_FUN_001271f0;
            lVar26 = get_enum_value("--indicator-style", optarg, &PTR_DAT_001268e0, "",
                4, PTR_FUN_001271f0, 1, ppuVar20);
            DAT_00128334 = *(uint *)("lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl" +
                lVar26 * 4 + 0x30);
            break;

        case 0x8b:  /* 139, --quoting-style */
            in_R9 = PTR_FUN_001271f0;
            lVar26 = get_enum_value("--quoting-style", optarg, &PTR_s_literal_001269a0,
                &DAT_00120220, 4, PTR_FUN_001271f0, 1, in_R11);
            local_8c = *(int *)(&DAT_00120220 + lVar26 * 4);
            break;

        case 0x8c:  /* 140, --no-group */
            goto switchD_00104d37_caseD_8c;

        case 0x8d:  /* 141, --numeric-uid-gid */
            DAT_00128348 = 0x90;  /* 144 = 1024 进制 */
            DAT_0012833c = 0x90;
            DAT_00128340 = 1;
            DAT_00127020 = 1;
            break;

        case 0x8e:  /* 142, --sort */
            in_R9 = PTR_FUN_001271f0;
            lVar26 = get_enum_value("--sort", optarg, &DAT_001262c0, &DAT_0011b6f0, 4,
                PTR_FUN_001271f0, 1,
                (long)&switchD_00104d37::switchdataD_0011b174 +
                (long)(int)(&switchD_00104d37::switchdataD_0011b174)[iVar8 + 0x83U]);
            local_90 = *(int *)(&DAT_0011b6f0 + lVar26 * 4);
            break;

        case 0x8f:  /* 143, --time */
            in_R11 = 1;
            in_R9 = PTR_FUN_001271f0;
            lVar26 = get_enum_value("--time", optarg, &DAT_00126260, &DAT_0011b6c0, 4,
                PTR_FUN_001271f0, 1, in_R10);
            DAT_00128354 = '\x01';
            DAT_00128358 = *(undefined4 *)(&DAT_0011b6c0 + lVar26 * 4);
            break;

        case 0x90:  /* 144, --hide */
            goto switchD_00104d37_caseD_90;

        case 0x91:  /* 145, --quoting-style=literal */
            DAT_00127019 = '\0';
            in_R10 = (undefined8 *)0x0;
            DAT_00128332 = 0;
            uVar10 = (uint)(uVar10 != 0);
            local_8c = 0;
switchD_00104d37_caseD_8c:
            local_70 = 0;
            break;

        case -0x83:  /* --help */
            uVar14 = author_string_alloc("David MacKenzie", "David MacKenzie");
            uVar15 = author_string_alloc("Richard M. Stallman", "Richard M. Stallman");
            pcVar25 = "ls";
            if ((DAT_001271e0 != 1) && (pcVar25 = "vdir", DAT_001271e0 == 2)) {
                pcVar25 = "dir";
            }
            print_version(stdout, pcVar25, "GNU coreutils", PTR_DAT_001271e8,
                uVar15, uVar14, 0, in_R9);
            exit(0);

        case -0x82:  /* --version */
            goto switchD_00104d37_caseD_ffffff7e;

        default:
            goto switchD_00104d37_caseD_ffffff7f;
        }
        goto LAB_00104d00;  /* 继续解析下一个选项 */
    }

    /* === 环境变量处理 === */
    if (DAT_00128340 == 0) {  /* BLOCK_SIZE 未被命令行设置 */
        pcVar25 = getenv("LS_BLOCK_SIZE");
        parse_size_string(pcVar25, &DAT_00128348, &DAT_00128340);
        if ((pcVar25 != (char *)0x0) ||
            (pcVar25 = getenv("BLOCK_SIZE"), pcVar25 != (char *)0x0)) {
            DAT_0012833c = DAT_00128348;
            DAT_00127020 = DAT_00128340;
        }
        if (bVar28) {  /* -k 选项 */
            DAT_00128340 = 0x400;  /* 1024 */
            DAT_00128348 = 0;
        }
    }

    if ((int)uVar10 < 0) {  /* format 未设置 */
        if (DAT_001271e0 == 1) goto LAB_001064c7;
        uVar10 = (uint)(DAT_001271e0 == 2) * 2;
    }

    /* === 终端属性检测 === */
    do {
        uVar16 = local_80;
        DAT_0012835c = uVar10;
        uVar3 = local_80;

        if ((uVar10 - 2 < 3) || (DAT_00128332 != 0)) {  /* 需要检查终端宽度 */
            if (local_80 == 0xffffffffffffffff) {
                cVar4 = isatty();
                if ((cVar4 != '\0') && (iVar8 = ioctl(1, 0x5413, &local_58), -1 < iVar8)) {
                    /* TIOCGWINSZ: 获取终端窗口大小 */
                    uVar16 = (ulong)local_58._2_2_;
                    uVar3 = uVar16;
                    if (local_58._2_2_ != 0) goto LAB_00104db0;
                }
                pcVar25 = getenv("COLUMNS");
                if ((pcVar25 != (char *)0x0) && (*pcVar25 != '\0')) {
                    local_80 = parse_positive_integer(pcVar25);
                    uVar16 = local_80;
                    uVar3 = local_80;
                    if (local_80 != 0xffffffffffffffff) goto LAB_00104db0;
                    argv[1] = error_message_alloc(pcVar25);
                    uVar14 = dcgettext(0,
                        "ignoring invalid width in environment variable COLUMNS: %s", 5);
                    error(0, 0, uVar14, argv[1]);
                }
LAB_0010521e:
                uVar16 = 0x50;  /* 默认 80 列 */
                uVar3 = local_80;
            }
        } else if (local_80 == 0xffffffffffffffff) goto LAB_0010521e;

LAB_00104db0:
        local_80 = uVar3;
        /* 计算每行列数: (宽度/3 + 1) 向下取整调整 */
        DAT_00128220 = (uVar16 / 3 + 1) - (ulong)(uVar16 % 3 == 0);
        DAT_001282d0 = uVar16;

        /* Tab size 处理 */
        puVar23 = DAT_001282e0;
        if ((DAT_0012835c - 2 < 3) && (puVar23 = local_78, (long)local_78 < 0)) {
            DAT_001282e0 = (undefined *)0x8;  /* 默认 tab=8 */
            pcVar25 = getenv("TABSIZE");
            puVar23 = DAT_001282e0;
            if ((pcVar25 != (char *)0x0) &&
               (iVar8 = parse_tab_size_full(pcVar25, 0, 0, &local_58, &DAT_0011cf4c),
                puVar23 = local_58, iVar8 != 0)) {
                argv[1] = error_message_alloc(pcVar25);
                uVar14 = dcgettext(0,
                    "ignoring invalid tab size in environment variable TABSIZE: %s", 5);
                error(0, 0, uVar14, argv[1]);
                puVar23 = DAT_001282e0;
            }
        }
        DAT_001282e0 = puVar23;

        /* 检查是否使用单列输出 */
        bVar7 = (byte)local_70 & 1;
        if ((local_70 == -1) && (bVar7 = 0, DAT_001271e0 == 1)) {
            bVar7 = isatty();
        }
        DAT_001282f8 = bVar7;

        /* Quoting style 处理 */
        if (local_8c < 0) {
            pcVar25 = getenv("QUOTING_STYLE");
            if (pcVar25 == (char *)0x0) goto LAB_00105a42;
            iVar8 = get_sort_style_value(pcVar25, &PTR_s_literal_001269a0, &DAT_00120220, 4);
            if (iVar8 < 0) goto LAB_0010670b;
            local_8c = *(int *)(&DAT_00120220 + (long)iVar8 * 4);
            if (local_8c < 0) goto LAB_00105a42;
        }

LAB_00104e16:
        set_quoting_style(0, local_8c);

        /* 格式化输出设置循环 */
        while (true) {
            uVar10 = get_format_index(0);
            if (((DAT_0012835c == 0) ||
                ((DAT_0012835c - 2 < 2 && (DAT_001282d0 != 0)))) && (uVar10 < 7)) {
                /* 位图检查: 0x4a = 01001010, 选择性地打印指标 */
                if ((0x4aUL >> ((ulong)uVar10 & 0x3f) & 1) == 0) {
                    DAT_001283c8 = 0;
                    DAT_001282f0 = create_output_stream(0);
                } else {
                    DAT_001283c8 = 1;
                    DAT_001282f0 = create_output_stream(0);
                }
            } else {
                DAT_001283c8 = 0;
                DAT_001282f0 = create_output_stream(0);
                if (uVar10 == 7) {
                    write_char(DAT_001282f0, 0x20, 1);
                }
            }

            /* 输出指标样式 */
            if (1 < DAT_00128334) {
                pcVar25 = &DAT_0011d1ab + (DAT_00128334 - 2);
                cVar4 = (&DAT_0011d1ab)[DAT_00128334 - 2];
                while (cVar4 != '\0') {
                    pcVar25 = pcVar25 + 1;
                    write_char(DAT_001282f0, (int)cVar4, 1);
                    cVar4 = *pcVar25;
                }
            }
            DAT_001282e8 = create_output_stream(0);
            write_char(DAT_001282e8, 0x3a, 1);

            /* dired 和 zero 互斥检查 */
            DAT_00128338 = (DAT_00128331 ^ 1) & DAT_0012835c == 0 & DAT_00128338;
            if ((int)(uint)DAT_00128338 <= (int)DAT_00127019) break;

LAB_001066e7:
            uVar14 = dcgettext(0, "--dired and --zero are incompatible", 5);
            error(2, 0, uVar14);

LAB_0010670b:
            argv[1] = error_message_alloc();
            uVar15 = dcgettext(0,
                "ignoring invalid value of environment variable QUOTING_STYLE: %s", 5);
            error(0, 0, uVar15, argv[1]);

LAB_00105a42:
            local_8c = 7;
            if (DAT_001271e0 != 1) goto LAB_00104e16;
            cVar4 = isatty();
            if (cVar4 != '\0') goto code_r0x00105a64;
        }

        /* Time style 处理 */
        if (local_90 < 0) {
            if (DAT_0012835c == 0) {
                DAT_00128350 = 0;
                goto LAB_00104f1f;
            }
            if (DAT_00128354 == '\0') {
                DAT_00128350 = 0;
            } else {
                DAT_00128350 = 5;
            }
            goto LAB_00104f6a;
        }
        DAT_00128350 = local_90;
        if (DAT_0012835c != 0) goto LAB_00104f6a;

LAB_00104f1f:
        /* TIME_STYLE 环境变量处理 */
        if ((local_88 == (char *)0x0) &&
            (local_88 = getenv("TIME_STYLE"), local_88 == (char *)0x0)) {
            local_88 = "locale";
        } else {
            while (iVar8 = strncmp(local_88, "posix-", 6), iVar8 == 0) {
                cVar4 = is_posix_mode(2);
                if (cVar4 == '\0') goto LAB_00104f6a;
                local_88 = local_88 + 6;
            }
        }

        /* 处理 +FORMAT 格式 (类似 date 命令) */
        if (*local_88 == '+') {
            pcVar25 = local_88 + 1;
            pcVar19 = strchr(pcVar25, 10);
            pcVar22 = pcVar25;
            if (pcVar19 != (char *)0x0) {
                pcVar22 = strchr(pcVar19 + 1, 10);
                if (pcVar22 != (char *)0x0) {
                    argv[1] = (char *)error_message_alloc(pcVar25);
                    uVar14 = dcgettext(0, "invalid time style format %s", 5);
                    error(2, 0, uVar14, argv[1]);
                    goto LAB_001066e7;
                }
                *pcVar19 = '\0';
                pcVar22 = pcVar19 + 1;
            }
            goto LAB_00106154;
        }

        /* 查找时间格式匹配 */
        ppuVar20 = &PTR_s_full_iso_00126920;
        lVar26 = get_sort_style_value(local_88, &PTR_s_full_iso_00126920,
            &DAT_0011b7c0, 4);
        if (-1 < lVar26) goto code_r0x00106124;

        /* 无效格式,打印可用格式列表 */
        argv[0] = (char *)0x11d1fa;
        invalid_option_error("time style", local_88, lVar26);
        __stream = stderr;
        pcVar25 = (char *)dcgettext(0, "Valid arguments are:\n", 5);
        fputs_unlocked(pcVar25, __stream);
        for (; argv[1] = stderr, *ppuVar20 != (undefined *)0x0; ppuVar20 = ppuVar20 + 1) {
            __fprintf_chk(stderr, 1, "  - [posix-]%s\n");
        }
        pcVar25 = (char *)dcgettext(0,
            "  - +FORMAT (e.g., +%H:%M) for a 'date'-style format\n", 5);
        fputs_unlocked(pcVar25, argv[1]);

switchD_00104d37_caseD_ffffff7f:
        usage_error();
switchD_00104d37_caseD_ffffff7e:
        usage_error(0);

LAB_001064c7:
        bVar7 = isatty();
        uVar10 = bVar7 + 1;
    } while (true);

switchD_00104d37_caseD_90:
    local_88 = optarg;
    goto LAB_00104d00;

/* 时间格式处理代码 */
code_r0x00106124:
    if (lVar26 == 2) {  /* iso */
        PTR_DAT_00127040 = s__Y__m__d_0011d231;
        PTR_s__b__e__H__M_00127048 = &DAT_0011d225;
        pcVar25 = PTR_DAT_00127040;
        pcVar22 = PTR_s__b__e__H__M_00127048;
    } else if (lVar26 < 3) {
        if (lVar26 == 0) {  /* full-iso */
            PTR_DAT_00127040 = s__Y__m__d__H__M__S__N__z_0011d20a;
            PTR_s__b__e__H__M_00127048 = s__Y__m__d__H__M__S__N__z_0011d20a;
            pcVar25 = PTR_DAT_00127040;
            pcVar22 = PTR_s__b__e__H__M_00127048;
        } else {  /* locale */
            PTR_DAT_00127040 = &DAT_0011d222;
            PTR_s__b__e__H__M_00127048 = &DAT_0011d222;
            pcVar25 = PTR_DAT_00127040;
            pcVar22 = PTR_s__b__e__H__M_00127048;
        }
    } else {
        pcVar25 = PTR_DAT_00127040;
        pcVar22 = PTR_s__b__e__H__M_00127048;
        if ((lVar26 == 3) &&  /* long-iso */
           (cVar4 = is_posix_mode(2), pcVar25 = PTR_DAT_00127040,
            pcVar22 = PTR_s__b__e__H__M_00127048, cVar4 != '\0')) {
            PTR_DAT_00127040 = (undefined *)dcgettext(0, PTR_DAT_00127040, 2);
            pcVar22 = (char *)dcgettext(0, PTR_s__b__e__H__M_00127048, 2);
            pcVar25 = PTR_DAT_00127040;
        }
    }

LAB_00106154:
    PTR_s__b__e__H__M_00127048 = pcVar22;
    PTR_DAT_00127040 = pcVar25;
    setup_time_format();

LAB_00104f6a:
    bVar7 = DAT_00128332;
    iVar8 = optind;

    if (DAT_00128332 == 0) goto LAB_00104f82;

    /* LS_COLORS 处理 */
    local_60 = getenv("LS_COLORS");
    if ((local_60 != (char *)0x0) && (*local_60 != '\0')) {
        DAT_00128320 = (undefined *)parse_ls_colors(local_60);
        local_58 = DAT_00128320;
        goto LAB_00105d12;
    }

    pcVar25 = getenv("COLORTERM");
    if ((pcVar25 != (char *)0x0) && (*pcVar25 != '\0')) goto LAB_00106215;

    pcVar25 = getenv("TERM");
    if ((pcVar25 == (char *)0x0) || (*pcVar25 == '\0')) goto LAB_0010656a;

    pcVar22 = "# Configuration file for dircolors, a utility to help you set the";
    goto LAB_001062c5;

/* LS_COLORS 解析循环 */
LAB_00105d12:
    pcVar25 = local_60;
    cVar4 = *local_60;
    if (cVar4 == '*') {
        /* 通配符模式: *.ext=color */
        psVar18 = (size_t *)malloc_wrapper(0x30);
        *(undefined1 *)(psVar18 + 4) = 0;
        local_60 = pcVar25 + 1;
        psVar18[5] = (size_t)DAT_00128328;
        psVar18[1] = (size_t)local_58;
        DAT_00128328 = psVar18;
        cVar4 = parse_color_sequence(&local_58, &local_60, 1, psVar18);
        pcVar25 = local_60;
        if ((cVar4 == '\0') || (pcVar25 = local_60 + 1, *local_60 != '='))
            goto LAB_00105eeb;
        psVar18[3] = (size_t)local_58;
        local_60 = local_60 + 1;
        cVar4 = parse_color_sequence(&local_58, &local_60, 0, psVar18 + 2);
        pcVar25 = local_60;
        if (cVar4 == '\0') goto LAB_00105eeb;
        goto LAB_00105d12;
    }

    if (cVar4 == ':') {
        local_60 = local_60 + 1;
    } else {
        if (cVar4 == '\0') {
            /* 结束处理: 检查重复项 */
            psVar18 = DAT_00128328;
            if (DAT_00128328 != (size_t *)0x0) {
                while (psVar21 = psVar18, psVar18 = (size_t *)psVar21[5],
                       psVar18 != (size_t *)0x0) {
                    bVar2 = 0;
                    psVar27 = psVar18;
                    do {
                        sVar17 = *psVar27;
                        if ((sVar17 != 0xffffffffffffffff) && (sVar17 == *psVar21)) {
                            pvVar13 = (void *)psVar27[1];
                            __s1 = (void *)psVar21[1];
                            iVar9 = memcmp(__s1, pvVar13, sVar17);
                            if (iVar9 == 0) {
                                *psVar27 = 0xffffffffffffffff;
                            } else {
                                iVar9 = strcoll_compare(__s1, pvVar13, sVar17);
                                if (iVar9 == 0) {
                                    if ((bVar2 == 0) &&
                                       ((psVar21[2] != psVar27[2] ||
                                        (iVar9 = memcmp((void *)psVar21[3],
                                            (void *)psVar27[3], psVar21[2]), iVar9 != 0)))) {
                                        *(undefined1 *)(psVar21 + 4) = 1;
                                        *(undefined1 *)(psVar27 + 4) = 1;
                                    } else {
                                        *psVar27 = 0xffffffffffffffff;
                                        bVar2 = bVar7;
                                    }
                                }
                            }
                        }
                        psVar27 = (size_t *)psVar27[5];
                    } while (psVar27 != (size_t *)0x0);
                }
            }
            goto LAB_001063ca;
        }

        cVar1 = local_60[1];
        pcVar25 = local_60 + 1;
        if ((cVar1 == '\0') || (pcVar25 = local_60 + 3, local_60[2] != '='))
            goto LAB_00105eeb;

        /* 解析文件类型代码 (di, ln, etc.) */
        lVar26 = 0;
        while ((local_60 = pcVar25,
               cVar4 != "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"[lVar26 * 2] ||
               (cVar1 != "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"[lVar26 * 2 + 1]))) {
            lVar26 = lVar26 + 1;
            if (lVar26 == 0x18) goto LAB_00105eab;
        }
        (&PTR_DAT_00127068)[(long)(int)lVar26 * 2] = local_58;
        cVar6 = parse_color_sequence(&local_58, &local_60, 0);
        if (cVar6 == '\0') goto LAB_00105eab;
    }
    goto LAB_00105d12;

/* 解析 TERMCAP/TERM 配置 */
LAB_001062c5:
    if ((char *)0x15ef < pcVar22 + -0x11b900) goto LAB_0010656a;
    iVar9 = strncmp(pcVar22, "TERM ", 5);
    if ((iVar9 == 0) && (iVar9 = fnmatch(pcVar22 + 5, pcVar25, 0), iVar9 == 0))
        goto LAB_00106215;
    sVar17 = strlen(pcVar22);
    pcVar22 = pcVar22 + sVar17 + 1;
    goto LAB_001062c5;

LAB_0010656a:
    DAT_00128332 = 0;
    goto LAB_00106215;

code_r0x00105a64:
    local_8c = 3;
    goto LAB_00104e16;

LAB_00105eab:
    local_42 = 0;
    local_44 = cVar4;
    local_43 = cVar1;
    argv[1] = error_message_alloc(&local_44);
    uVar15 = dcgettext(0, "unrecognized prefix: %s", 5);
    error(0, 0, uVar15, argv[1]);
    pcVar25 = local_60;

LAB_00105eeb:
    local_60 = pcVar25;
    uVar14 = dcgettext(0,
        "unparsable value for LS_COLORS environment variable", 5);
    error(0, 0, uVar14);
    free(DAT_00128320);
    psVar18 = DAT_00128328;
    while (psVar18 != (size_t *)0x0) {
        psVar21 = (size_t *)psVar18[5];
        free(psVar18);
        psVar18 = psVar21;
    }
    DAT_00128332 = 0;

LAB_001063ca:
    if ((DAT_001270d0 == 6) && (iVar9 = strncmp(PTR_DAT_001270d8, "target", 6), iVar9 == 0)) {
        DAT_001283b0 = '\x01';
    }

LAB_00106215:
    if (DAT_00128332 == 0) {
LAB_00104f82:
        if (DAT_00128314 != 0) goto LAB_00104f8b;
    } else {
        DAT_001282e0 = (undefined *)0x0;
        if ((((DAT_00128314 != 0) || (cVar4 = check_terminal_mode(0xd), cVar4 != '\0')) ||
            ((cVar4 = check_terminal_mode(0xe), cVar4 != '\0' && (DAT_001283b0 != '\0')))) ||
           ((cVar4 = check_terminal_mode(0xc), cVar4 != '\0' && (DAT_0012835c == 0)))) {
LAB_00104f8b:
            DAT_0012831d = 1;
        }
    }

    lVar26 = (long)iVar8;

    /* 延迟初始化某些选项 */
    if ((((DAT_00128318 == 0) && (DAT_00128318 = 1, DAT_00128315 == '\0')) &&
        (DAT_00128334 != 3)) && (DAT_0012835c != 0)) {
        DAT_00128318 = 3;
    }

    /* 初始化哈希表 (用于目录去重) */
    if (DAT_00128316 != 0) {
        DAT_001283e8 = hash_init(0x1e, 0, FUN_00106880, FUN_00106890, free);
        if (DAT_001283e8 == 0) {
            xalloc_die();
        }
        obstack_init(&DAT_00128100, 0, 0, malloc, free);
    }

    /* 时区设置 */
    pcVar25 = getenv("TZ");
    DAT_001282c8 = set_timezone(pcVar25);

    /* 计算各种标志组合 */
    DAT_001282c2 = DAT_0012834c | DAT_00128331 | DAT_00128389 | DAT_0012835c == 0 |
                   (DAT_00128350 - 3U & 0xfffffffd) == 0;
    DAT_001282c1 = (DAT_00128389 | DAT_00128316 | DAT_00128332 | DAT_00128314 |
                   DAT_00128334 != 0) & (DAT_001282c2 ^ 1);
    uVar5 = 0;
    if (DAT_00128332 != 0) {
        uVar5 = check_terminal_mode(0x15);
    }
    DAT_001282c0 = uVar5;

    /* 初始化dired输出相关 */
    if (DAT_00128338 != 0) {
        obstack_init(&DAT_001281c0, 0, 0, malloc, free);
        obstack_init(&DAT_00128160, 0, 0, malloc, free);
    }

    /* 超链接: 初始化主机名 */
    if (DAT_00128331 != 0) {
        uVar16 = 0;
        do {
            while (iVar9 = (int)uVar16, uVar16 < 0x5b) {
                if (((uVar16 < 0x41) && (9 < iVar9 - 0x30U)) && (1 < iVar9 - 0x2dU)) {
                    uVar16 = uVar16 + 1;
                } else {
                    (&DAT_00128000)[uVar16] = (&DAT_00128000)[uVar16] | 1;
                    uVar16 = uVar16 + 1;
                }
            }
            bVar28 = true;
            if ((0x19 < iVar9 - 0x61U) && (uVar16 != 0x7e)) {
                bVar28 = iVar9 == 0x5f;
            }
            (&DAT_00128000)[uVar16] = (&DAT_00128000)[uVar16] | bVar28;
            uVar16 = uVar16 + 1;
        } while (uVar16 != 0x100);

        DAT_001283a8 = (undefined *)get_hostname_alloc();
        if (DAT_001283a8 == (undefined *)0x0) {
            DAT_001283a8 = &DAT_0011cf4c;
        }
    }

    DAT_001283d8 = 100;
    DAT_001283e0 = malloc_wrapper(0x5140);
    iVar8 = argc - iVar8;
    DAT_001283d0 = 0;

    /* 初始文件扫描 */
    initial_file_scan();

    /* 主循环: 处理文件列表 */
    if (iVar8 < 1) {
        if (DAT_00128315 == '\0') {
            print_dir_header(&DAT_0011d277, 0, 1);
        } else {
            print_file_entry(&DAT_0011d277, 3, 1, 0);
        }
        if (DAT_001283d0 != 0) goto LAB_00105fba;

LAB_00105a9f:
        if (DAT_001283a0 == (long *)0x0) goto LAB_00105194;
        __ptr = DAT_001283a0;
        if (DAT_001283a0[3] == 0) {
            DAT_001282d8 = 0;
        }
    } else {
        do {
            lVar11 = lVar26 * 2;
            lVar26 = lVar26 + 1;
            print_file_entry(*(undefined8 *)(&argv[1]->_flags + lVar11), 0, 1, 0);
        } while ((int)lVar26 < (int)argc);

        if (DAT_001283d0 == 0) {
LAB_00105129:
            if (1 < iVar8) goto LAB_00105188;
            goto LAB_00105a9f;
        }

LAB_00105fba:
        sort_and_print_files();

        if (DAT_00128315 == '\0') {
            print_files_long_format(0, 1);
        }
        if (DAT_001283d0 == 0) goto LAB_00105129;

        finish_output();

        if (DAT_001283a0 == (long *)0x0) goto LAB_00105194;
        DAT_00128218 = DAT_00128218 + 1;
        pcVar25 = stdout->_IO_write_ptr;
        if (stdout->_IO_write_end <= pcVar25) {
            __overflow(stdout, 10);
            goto LAB_00105188;
        }
        stdout->_IO_write_ptr = pcVar25 + 1;
        *pcVar25 = '\n';
        __ptr = DAT_001283a0;
    }

    /* 清理: 释放目录条目 */
    do {
        DAT_001283a0 = (long *)__ptr[3];
        if ((DAT_001283e8 == 0) || (*__ptr != 0)) {
            free_dir_entry(*__ptr, __ptr[1], (char)__ptr[2]);
            free((void *)*__ptr);
            free((void *)__ptr[1]);
            free(__ptr);
            DAT_001282d8 = 1;
        } else {
            if ((ulong)(DAT_00128118 - _DAT_00128110) < 0x10) {
                __assert_fail(
                    "dev_ino_size <= __extension__ ({ struct obstack const *__o = "
                    "(&dev_ino_obstack); (size_t) (__o->next_free - __o->object_base); })",
                    "src/ls.c", 0x442, "dev_ino_pop");
            }
            local_58 = *(undefined **)(DAT_00128118 + -0x10);
            uStack_50 = *(undefined8 *)(DAT_00128118 + -8);
            DAT_00128118 = DAT_00128118 + -0x10;
            pvVar13 = (void *)hash_lookup(DAT_001283e8, &local_58);
            if (pvVar13 == (void *)0x0) {
                __assert_fail("found", "src/ls.c", 0x73d, "main");
            }
            free(pvVar13);
            free((void *)*__ptr);
            free((void *)__ptr[1]);
            free(__ptr);
        }

LAB_00105188:
        __ptr = DAT_001283a0;
    } while (DAT_001283a0 != (long *)0x0);

LAB_00105194:
    /* 输出结束序列 (如果是彩色模式) */
    if ((DAT_00128332 != 0) && (DAT_00128330 != '\0')) {
        if ((DAT_00127060 != 2) ||
           (((*(short *)PTR_DAT_00127068 != 0x5b1b || (DAT_00127070 != 1)) ||
            (*PTR_DAT_00127078 != 'm')))) {
            print_escape_sequence(&DAT_00127060);
            print_escape_sequence(&DAT_00127070);
        }
        fflush_unlocked(stdout);
        reset_terminal(0);
        for (iVar8 = DAT_00128234; iVar8 != 0; iVar8 = iVar8 + -1) {
            raise(0x13);  /* SIGPWR */
        }
        if (DAT_00128238 != 0) {
            raise(DAT_00128238);
        }
    }

    /* 输出 dired 标记 */
    if (DAT_00128338 != 0) {
        print_dired_tag("//DIRED//", &DAT_001281c0);
        print_dired_tag("//SUBDIRED//", &DAT_00128160);
        uVar10 = get_format_index(DAT_001282f0);
        __printf_chk(1, "//DIRED-OPTIONS// --quoting-style=%s\n",
            (&PTR_s_literal_001269a0)[uVar10]);
    }

    /* 清理哈希表 */
    lVar26 = DAT_001283e8;
    if (DAT_001283e8 != 0) {
        lVar11 = hash_get_entries(DAT_001283e8);
        if (lVar11 != 0) {
            __assert_fail("hash_get_n_entries (active_dir_set) == 0",
                "src/ls.c", 0x771, "main");
        }
        hash_free(lVar26);
    }

    /* Stack canary check */
    if (local_40 != *(long *)(in_FS_OFFSET + 0x28)) {
        __stack_chk_fail();
    }

    return DAT_00128230;
}
