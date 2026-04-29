/*
 * obstack_new_chunk — 为 obstack 分配新 chunk 并迁移已有数据。
 *
 * 对应 glibc/gnulib 中的 _obstack_newchunk。
 *
 * obstack 结构体字段布局 (64-bit, ulong 偏移):
 *   h[0]  = chunk_size          当前 chunk 的容量
 *   h[1]  = chunk               当前 chunk 指针 (struct _obstack_chunk *)
 *   h[2]  = object_base         当前对象起始地址
 *   h[3]  = next_free           下一空闲字节地址
 *   h[4]  = chunk_limit         当前 chunk 上界地址
 *   h[6]  = alignment_mask      对齐掩码
 *   h[7]  = chunkfun            分配 chunk 的回调函数
 *   h[8]  = freefun             释放 chunk 的回调函数
 *   h[9]  = extra_arg           回调额外参数
 *   h[10] = flags               标志位 (bit0: use_extra_arg, bit1: 内部标记)
 *
 * _obstack_chunk 结构 (64-bit):
 *   chunk + 0x00: limit  (上界指针)
 *   chunk + 0x08: prev   (前驱 chunk 指针)
 *   chunk + 0x10: data[] (数据区起址)
 *
 * 符号对应:
 *   FUN_00116220 → obstack_new_chunk
 */

void *
obstack_new_chunk(ulong *h, ulong length)
{
    ulong  obj_size;          /* __n         — 当前对象已占用字节 */
    ulong  new_size;          /* uVar5       — 所需新总字节 */
    ulong  old_chunk;         /* uVar1       — 旧 chunk 指针 */
    bool   carry_align;       /* bVar8       — 对齐加法进位 */
    ulong *chunk_sz;          /* puVar6      — 计算后的 chunk 大小 */
    ulong *overflow_half;     /* puVar4      — 高半部分/溢出标记, 多用途 */
    ulong *min_est;           /* puVar7      — chunk 最小估算值 */
    ulong *new_chunk;         /* puVar2      — 新 chunk 指针 */
    void  *old_base;          /* pvVar3(1)   — 旧 object_base */
    void  *dest;              /* __dest      — 对齐后的新数据区 */
    ulong  flags;             /* uVar5(2)    — 标志位 */
    void  *ret;               /* pvVar3(2)   — 返回值 */

    /* ---- 1. 计算所需 chunk 大小 ---- */

    obj_size     = h[3] - h[2];                          /* next_free - object_base */
    new_size     = length + obj_size;                    /* 所需总字节数 */
    old_chunk    = h[1];
    carry_align  = CARRY8(new_size, h[6]);               /* (new_size + align_mask) 是否进位 */
    chunk_sz     = (ulong *)(new_size + h[6]);           /* 对齐后大小 (低 64 位) */
    overflow_half = (ulong *)CONCAT71((int7)((ulong)h >> 8), carry_align);
    min_est      = (ulong *)((long)chunk_sz + (obj_size >> 3) + 100);

    if (chunk_sz < (ulong *)h[0])                        /* 不低于默认 chunk_size */
        chunk_sz = (ulong *)h[0];
    if (chunk_sz <= min_est)                             /* 不低于估算最小值 */
        chunk_sz = min_est;
    min_est = chunk_sz;                                  /* 保存阈值 (用于失败回退路径) */

    /* ---- 2. 尝试分配新 chunk (需无溢出 + 对齐不跨 64 位边界) ---- */

    if ((!CARRY8(length, obj_size))
        && (overflow_half = (ulong *)(ulong)carry_align,
            overflow_half == (ulong *)0)) {

        if ((h[10] & 1) == 0) {
            overflow_half = chunk_sz;
            new_chunk = (ulong *)(*(ulong (**)(ulong))h[7])((ulong)chunk_sz);
        } else {
            overflow_half = (ulong *)h[9];
            new_chunk = (ulong *)(*(ulong (**)(void *, ulong))h[7])((void *)h[9],
                                                                    (ulong)chunk_sz);
        }

        if (new_chunk != (ulong *)0) {

            /* ---- 3a. 初始化新 chunk 并迁移数据 ---- */

            h[1]           = (ulong)new_chunk;                /* h->chunk = new_chunk */
            new_chunk[1]   = old_chunk;                      /* new_chunk->prev = old_chunk */
            old_base       = (void *)h[2];                   /* 暂存 object_base */
            h[4]           = (long)new_chunk + (long)chunk_sz; /* h->chunk_limit */
            *new_chunk     = (long)new_chunk + (long)chunk_sz; /* new_chunk->limit */

            /* 计算对齐后的数据区起始地址: (chunk + 16) 向上对齐 */
            dest = (void *)((long)(new_chunk + 2)
                            + (-(long)(new_chunk + 2) & h[6]));

            /* 将旧对象数据复制到新 chunk */
            ret = memcpy(dest, old_base, obj_size);

            flags = h[10];

            if ((flags & 2) == 0) {
                /* 计算旧 chunk 对齐后的数据起点 */
                ret = (void *)(old_chunk + 0x10
                               + (-(old_chunk + 0x10) & h[6]));

                if ((void *)h[2] == ret) {
                    /*
                     * object_base 恰等于旧 chunk 的对齐起点 → 旧 chunk
                     * 中无其他对象，可直接释放。将新 chunk 链到旧 chunk 的前驱。
                     */
                    new_chunk[1] = *(ulong *)(old_chunk + 8);

                    if ((flags & 1) == 0) {
                        ret = (void *)(*(ulong (**)(ulong))h[8])(old_chunk);
                    } else {
                        ret = (void *)(*(ulong (**)(void *, ulong))h[8])((void *)h[9],
                                                                         old_chunk);
                    }
                }
            }

            /* 更新 obstack 状态 */
            h[2] = (ulong)dest;                               /* object_base = dest */
            *(byte *)(h + 10) = (byte)h[10] & 0xfd;           /* 清除 bit1 */
            h[3] = (long)dest + obj_size;                     /* next_free */

            return ret;
        }
    }

    /* ---- 3b. 分配失败: 调用全局处理函数 ---- */

    (*(void (**)(void))obstack_alloc_failed_handler)();

    /* 若处理函数意外返回，遍历现有 chunk 链寻找可用节点 */
    overflow_half = (ulong *)overflow_half[1];
    if (overflow_half == (ulong *)0)
        return (void *)0;

    while (min_est <= overflow_half
           || ((ulong *)*overflow_half < min_est)) {
        overflow_half = (ulong *)overflow_half[1];
        if (overflow_half == (ulong *)0)
            return (void *)0;
    }

    return (void *)1;
}
