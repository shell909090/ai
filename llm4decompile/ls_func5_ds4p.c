/*
 * 对字符串进行转义编码：不可打印字符转为 %XX 形式，可打印字符原样保留，
 * '/' 根据 escape_slash 参数决定是否转义。
 *
 * 符号对应关系:
 *   FUN_001074c0         → escape_filename
 *   FUN_001074e0[256]    → printable_char_tab  (安全字符查找表, 非零表示可直接输出)
 *   FUN_00119e00         → xcalloc              (推测为 calloc 包装, 参数: count, size)
 *
 * 注意: 反编译代码中 q += 3 位于 if-else 外侧，这在逻辑上会导致缓冲区溢出；
 *       原始二进制中应仅位于 __sprintf_chk 分支内，此处已修正。
 */
char *
escape_filename(const char *s, char escape_slash)
{
    char *p, *q;
    int   c;

    /* 最坏情况: 每个字符变成 3 字节 (%XX), 外加终结符 */
    p = xcalloc(3, strlen(s) + 1);
    q = p;

    while ((c = *s++) != '\0') {

        if (c == '/' && escape_slash) {
            /* '/' 需要原样保留 (不转义) */
            *q++ = '/';

        } else if (printable_char_tab[c] != '\0') {
            /* 安全字符，直接输出 */
            *q++ = c;

        } else {
            /* 不可打印字符，输出 %XX 十六进制转义 */
            __sprintf_chk(q, 1, -1, "%%%02x", c);
            q += 3;
        }
    }

    *q = '\0';
    return p;
}
