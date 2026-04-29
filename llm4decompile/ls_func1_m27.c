/* 0011a360: 获取主机名并返回新分配的字符串
 * 对应关系:
 *   FUN_0011a360 -> get_hostname_alloc (推测)
 *   FUN_0011a100 -> strdup (推测)
 *   FUN_00119f30 -> 可能是内存分配相关的封装函数
 */

char * get_hostname_alloc(void)
{
    char *hostname = NULL;             /* 最终返回的主机名字符串 */
    char *hostname_buf = NULL;         /* 临时工作缓冲区 */
    size_t hostname_buf_size = 100;    /* 初始缓冲区大小 */
    size_t hostname_len;               /* gethostname返回的实际长度 */
    int *err = __errno_location();     /* errno 指针 */

    while (1) {
        hostname_buf[hostname_buf_size - 1] = '\0';  /* 放哨兵，检测缓冲区是否够用 */
        *err = 0;

        if (gethostname(hostname_buf, hostname_buf_size - 1) == 0) {  /* 调用成功 */
            hostname_len = strlen(hostname_buf);
            /* 长度+1(算null terminator)小于等于缓冲区大小-1(给哨兵留一位)，说明缓冲区够用 */
            if (hostname_len + 1 <= hostname_buf_size - 1) {
                if (!hostname)
                    hostname = strdup(hostname_buf);  /* 首次成功，复制结果 */
                break;
            }
        }

        /* 调用失败，清理并准备重试 */
        free(hostname);
        hostname = NULL;

        /* 特定错误码表示不需要重试，直接退出 */
        if (*err > 36 || *err == -1 || *err == -2)
            break;

        /* 重新分配更大缓冲区后重试 */
        hostname_buf = FUN_00119f30(NULL, &hostname_buf_size, 1, -1, 1);
    }

    return hostname;
}
