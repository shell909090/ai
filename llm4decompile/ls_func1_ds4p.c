/*
 * 获取本机 hostname，带自动扩容重试机制。
 *
 * xrealloc: 推测为 x2realloc 类函数，传入 NULL 表示初始分配，
 *           同时更新 buf_size 为新大小。
 * strndup:  推测为 strndup / memcpy+alloc。
 *
 * 注意：这是 Ghidra 反编译输出，首轮迭代时 buf 为 NULL，
 *       原始二进制中首轮之前应有初始分配调用。
 */
char *
get_hostname(void)
{
    char   *hostname     = NULL;
    char   *buf          = NULL;
    size_t  buf_size     = 100;
    size_t  hostname_len;
    int    *err          = __errno_location();

    for (;;) {
        buf[buf_size - 1] = '\0';          /* 强制末字节为终止符 */
        *err = 0;

        if (gethostname(buf, buf_size - 1) == 0) {
            hostname_len = strlen(buf);

            /* 若 hostname 长度 + 终止符 小于 缓冲区末尾余量，说明完整装入 */
            if (hostname_len + 1 < buf_size - 1) {
                if (hostname == NULL) {
                    hostname = strndup(buf, hostname_len + 1);
                }
                break;
            }
        }

        free(hostname);
        hostname = NULL;

        /* 不可恢复的错误：errno > 36 (例如 ENAMETOOLONG) 或内部特殊错误码 -1/-2 */
        if (*err > 36 || *err == -1 || *err == -2) {
            break;
        }

        /* 扩容/重分配缓冲区 (传入 NULL 相当于重新 malloc) */
        buf = xrealloc(NULL, &buf_size, 1, -1, 1);
    }

    return hostname;
}
