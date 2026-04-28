/*
 * 原始符号：FUN_00116220
 * 推测符号：_obstack_newchunk(struct obstack *h, size_t length)
 *
 * 来源：glibc/gnulib obstack 模块（lib/obstack.c）。
 * 当 obstack 当前 chunk 剩余空间不足以容纳正在增长中的对象时被调用，
 * 申请一块更大的 chunk，把"未完成的对象"搬过去，更新句柄状态。
 *
 * obstack 内存模型（growing object 视图）：
 *
 *   [...chunk header...|<现有对象 obj_size 字节>|...剩余可用...]
 *                       ▲                       ▲              ▲
 *                  object_base             next_free      chunk_limit
 *
 * 对象通过 obstack_grow / obstack_1grow 不断向右追加；
 * 一旦 next_free 达到 chunk_limit，就调用本函数换大 chunk。
 *
 * param_1 即 struct obstack *h，字段按 8 字节索引：
 *   param_1[0]  = chunk_size        (最小 chunk 大小下限)
 *   param_1[1]  = chunk             (当前 chunk 指针)
 *   param_1[2]  = object_base
 *   param_1[3]  = next_free
 *   param_1[4]  = chunk_limit
 *   param_1[6]  = alignment_mask    (如 7 代表 8 字节对齐)
 *   param_1[7]  = chunkfun          (chunk 分配函数指针)
 *   param_1[8]  = freefun           (chunk 释放函数指针)
 *   param_1[9]  = extra_arg
 *   param_1[10] = flags bitfield
 *                   bit0 = use_extra_arg
 *                   bit1 = maybe_empty_object
 *
 * 注意：ghidra 输出中 obstack_alloc_failed_handler() 之后的代码（第 65-75 行）
 * 是不可达的死代码。该 handler 在 glibc 中声明为 __attribute_noreturn__，
 * ghidra 不知晓此属性，沿控制流走进了紧邻的下一个函数 _obstack_allocated_p
 * 的代码体，因此本文件中直接丢弃那段代码。
 */

#include <stdint.h>
#include <string.h>

/* _obstack_chunk 结构（二进制里与 param_1[1] 所指相同布局） */
struct _obstack_chunk {
    char *limit;              /* chunk 末尾地址 */
    struct _obstack_chunk *prev; /* 前一个 chunk，构成单链表 */
    char contents[];          /* 数据区起点，从此处开始存放对象 */
};

/* 对应 param_1[10] 中的 flag bits */
#define USE_EXTRA_ARG      (1u << 0)
#define MAYBE_EMPTY_OBJECT (1u << 1)

/* 全局失败回调，默认为 print_and_abort，应用可替换为 longjmp 等 */
extern void (*obstack_alloc_failed_handler)(void);

void
_obstack_newchunk(struct obstack *h, size_t length)
{
    struct _obstack_chunk *old_chunk = h->chunk; /* param_1[1] */
    size_t obj_size = h->next_free - h->object_base; /* param_1[3] - param_1[2] */

    /*
     * 计算新 chunk 大小，三段叠加策略：
     *
     *   sum1     = obj_size + length          现有对象 + 新增需求
     *   sum2     = sum1 + alignment_mask      对齐补偿（最坏情况额外浪费 mask 字节）
     *   new_size = sum2 + obj_size/8 + 100   12.5% 增长余量 + 100 字节最小填充
     *
     * 取 max(new_size, chunk_size, sum2) 作为最终大小：
     *   - 不低于用户设置的 chunk_size 下限
     *   - 不低于 sum2（防止溢出回绕时 new_size < sum2 的极端情况）
     */
    size_t sum1 = obj_size + length;
    size_t sum2 = sum1 + h->alignment_mask;         /* puVar6 初值 */
    size_t new_size = sum2 + (obj_size >> 3) + 100; /* puVar7 */

    if (new_size < h->chunk_size) new_size = h->chunk_size; /* 不低于 chunk_size */
    if (new_size < sum2)          new_size = sum2;           /* 不低于 sum2 */

    /*
     * 溢出检查：sum1 或 sum2 任一发生无符号回绕即为溢出。
     * ghidra 里用 CARRY8() 内部函数表示进位标志：
     *   bVar8 = CARRY8(sum1, alignment_mask)  即 sum2 是否溢出
     *   整体条件：!CARRY8(length, obj_size) && !bVar8
     */
    bool overflow = (sum1 < obj_size) /* length+obj_size 溢出 */
                 || (sum2 < sum1);    /* +alignment_mask 溢出 */

    struct _obstack_chunk *new_chunk = NULL;
    if (!overflow) {
        /*
         * 调用用户提供的 chunk 分配函数，两种约定：
         *   use_extra_arg=0:  new_chunk = chunkfun(new_size)
         *   use_extra_arg=1:  new_chunk = chunkfun(extra_arg, new_size)
         *
         * ghidra 输出里看到对同一函数指针调用两次（if/else 分支），
         * 差异仅在是否把 extra_arg 作为第一个参数传入。
         */
        if (h->flags & USE_EXTRA_ARG)
            new_chunk = h->chunkfun(h->extra_arg, new_size);
        else
            new_chunk = h->chunkfun(new_size);
    }

    if (new_chunk == NULL) {
        /*
         * 分配失败：调用全局 noreturn 错误处理器。
         * 正常情况下这里不会返回；ghidra 因不知晓 noreturn 属性，
         * 在此之后错误拼接了 _obstack_allocated_p 的代码——已丢弃。
         */
        (*obstack_alloc_failed_handler)();
        /* unreachable */
    }

    /* 把新 chunk 接到链头 */
    h->chunk         = new_chunk;
    new_chunk->prev  = old_chunk;
    /* param_1[4] 和 new_chunk[0]（limit 字段）都设为 chunk 末尾 */
    new_chunk->limit = (char *)new_chunk + new_size;
    h->chunk_limit   = new_chunk->limit;

    /*
     * 在新 chunk 的 contents 区域内向上对齐，找到对象起点：
     *
     *   object_base = contents + ((-contents) & alignment_mask)
     *
     * 等价于 (contents + mask) & ~mask，即"向上取整到 (mask+1) 的倍数"。
     * 使用 (-p & mask) 写法是为了避免对 int 类型 ~mask 时的符号扩展陷阱。
     */
    char *object_base =
        (char *)new_chunk->contents
        + ((-(uintptr_t)new_chunk->contents) & (uintptr_t)h->alignment_mask);

    /* 把"未完成的对象"从旧 chunk 搬到新 chunk 的对齐起点 */
    memcpy(object_base, h->object_base, obj_size);

    /*
     * 判断旧 chunk 是否可以立即释放：
     * 条件1：maybe_empty_object 未置位（确保没人持有指向旧 chunk 里空对象的引用）
     * 条件2：h->object_base 恰好在旧 chunk contents 的对齐起点
     *        ——说明旧 chunk 中除刚搬走的对象之外没有其他已 finalized 的对象
     *
     * 若两个条件都满足，从链表摘掉旧 chunk 并释放，
     * 防止"每次扩容都泄漏一块旧 chunk"。
     */
    if (!(h->flags & MAYBE_EMPTY_OBJECT)) {
        char *old_aligned =
            (char *)old_chunk->contents
            + ((-(uintptr_t)old_chunk->contents) & (uintptr_t)h->alignment_mask);

        if (h->object_base == old_aligned) {
            /* 把旧 chunk 从链表中摘掉，然后释放 */
            new_chunk->prev = old_chunk->prev;
            if (h->flags & USE_EXTRA_ARG)
                h->freefun(h->extra_arg, old_chunk);
            else
                h->freefun(old_chunk);
        }
    }

    /* 更新句柄，使其指向新 chunk 中迁移后的对象 */
    h->object_base = object_base;
    h->next_free   = object_base + obj_size;
    /*
     * 清除 maybe_empty_object 标志（反编译里是 & 0xfd，即 & ~0x02）：
     * 新 chunk 刚分配，里面肯定没有空对象。
     */
    h->flags &= ~MAYBE_EMPTY_OBJECT;
}
