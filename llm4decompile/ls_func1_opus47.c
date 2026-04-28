/*
 * 原始符号：FUN_0011a360
 * 推测符号：xgethostname (gnulib lib/xgethostname.c)
 *
 * 功能：返回当前主机名的堆拷贝，失败时返回 NULL。
 * 调用者负责 free() 返回值。
 *
 * 依赖的两个内部符号：
 *   FUN_0011a100(p, n)  => xmemdup(void const *p, size_t n)
 *                          申请 n 字节并拷贝，返回堆指针
 *   FUN_00119f30(p, &n, n_incr_min, n_max, s)
 *                       => xpalloc(void *pa, idx_t *pn, idx_t n_incr_min,
 *                                  ptrdiff_t n_max, idx_t s)
 *                          几何增长式 realloc（gnulib），pa=NULL 时等价新分配
 *
 * 编译器优化说明：
 *   原代码中的 errno 条件判断（ENOMEM/EINVAL/ENAMETOOLONG）被 gcc 折叠成
 *   一张 64-bit 位掩码 0xffffffefffbfeffe，对应 bit 0/12/22/36 为 0，
 *   即 errno ∈ {0, ENOMEM(12), EINVAL(22), ENAMETOOLONG(36)} 时继续重试。
 */

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* gnulib 提供的辅助函数，这里仅做声明以供参考 */
extern void *xmemdup (void const *p, size_t n);
extern void *xpalloc (void *pa, size_t *pn, size_t n_incr_min,
                      long n_max, size_t s);

char *
xgethostname (void)
{
    enum { INITIAL_HOSTNAME_LENGTH = 100 };

    /* 先用栈缓冲尝试，绝大多数主机名远小于 100 字节，可省一次 malloc */
    char  stack_buf[INITIAL_HOSTNAME_LENGTH];
    char *buf      = stack_buf;
    size_t size    = INITIAL_HOSTNAME_LENGTH;

    /* heap_buf 非 NULL 时表示当前正在使用堆缓冲（已超过栈缓冲大小） */
    char *heap_buf = NULL;

    while (1) {
        /* 强制末尾写 '\0'：绕过早年 SunOS gethostname 不补零的 bug，
         * 确保即使 gethostname 填满整个缓冲区也有终止符 */
        buf[size - 1] = '\0';

        /* 传入 size-1 而非 size，为上面那个强制 '\0' 留出位置 */
        errno = 0;
        if (gethostname (buf, size - 1) == 0) {
            size_t len = strlen (buf);

            /* 严格小于（而非 <=）：若主机名恰好占满 size-2 字节，
             * 仍视为"可能被截断"，继续放大缓冲区重试 */
            if (len + 1 < size - 1) {
                if (heap_buf == NULL)
                    /* 快路径：主机名在栈缓冲里，复制一份紧凑的堆字符串返回 */
                    return xmemdup (buf, len + 1);
                else
                    /* 慢路径：已使用堆缓冲，直接返回（无需再次拷贝） */
                    return heap_buf;
            }

            /* 走到这里说明 gethostname 成功但缓冲区不够大（被截断）。
             * 清掉 errno，防止下面的错误判断被上一次调用的残留值误导 */
            errno = 0;
        }

        /* 本轮失败，释放上一轮可能申请的堆缓冲 */
        free (heap_buf);
        heap_buf = NULL;

        /* 只有"缓冲区太小"这一类错误才值得重试，其余错误直接放弃：
         *   ENAMETOOLONG: 预期信号，hostname 比缓冲区长
         *   EINVAL      : 部分 BSD/macOS 在缓冲不足时返回此值
         *   ENOMEM / 0  : 偶发情况，保守地继续尝试而不是直接失败 */
        if (errno != 0
            && errno != ENOMEM
            && errno != EINVAL
            && errno != ENAMETOOLONG)
            return NULL;

        /* 几何增长：xpalloc 将 size 翻倍（或更多），并返回新堆缓冲区；
         * 第一个参数为 NULL 因为上面已经 free 了旧缓冲 */
        heap_buf = xpalloc (NULL, &size, 1, -1, 1);
        buf      = heap_buf;
    }
}
