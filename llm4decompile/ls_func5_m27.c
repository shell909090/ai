/* 001074c0: 转义字符串中的不可打印字符
 * 对应关系:
 *   FUN_001074c0 -> quote_name (推测)
 *   FUN_00119e00 -> malloc_or_die (推测,带错误处理的分配)
 *   FUN_001074e0 -> printable_char_table (字符查表,判断是否可打印)
 *
 * 功能: 将字符串中的不可打印字符转换为 \xHH 格式的十六进制转义序列
 *       如果 escape_slash 为 true,还会对 '/' 字符进行转义
 */

char * quote_name(const char *s, char escape_slash)
{
    char *p, *q;
    int c;

    /* 分配输出缓冲区,假设最长可能为原来的4倍 (每个字符转义后最长 4 字节) */
    p = malloc_or_die(3, strlen(s) + 1);
    q = p;

    /* 逐字符处理输入字符串 */
    while ((c = *s++) != '\0') {
        if (c == '/' && escape_slash) {
            /* 如果是斜杠且需要转义斜杠,复制一份 */
            *q++ = '/';
        } else if (printable_char_table[c] != '\0') {
            /* 查表判断:如果是可打印字符,直接复制 */
            *q++ = c;
        } else {
            /* 不可打印字符,转换为 \xHH 格式 */
            __sprintf_chk(q, 1, -1, "%%%02x", c);
            q += 3;  /* %%02x 格式输出3个字符(%xx) */
        }
    }
    *q = '\0';

    return p;
}

/* printable_char_table 查表法:
 * 对于可打印ASCII字符 (0x20-0x7E),表中值为非零
 * 对于控制字符和其他不可打印字符,表中值为零
 * 使得可以用 if (table[c]) 来快速判断是否需要转义
 */
