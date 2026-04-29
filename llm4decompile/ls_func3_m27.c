/* 00116220: obstack_alloc - 从obstack分配内存
 * 对应关系:
 *   FUN_00116220 -> obstack_alloc (glibc obstack实现)
 *   param_1 -> struct obstack * (包含块头信息的结构体)
 *   param_2 -> size_t nbytes (要分配的大小)
 *   param_1[7] -> chunk_alloc function pointer
 *   param_1[8] -> chunk_free function pointer
 *   CARRY8 -> 整数溢出检查宏
 *
 * 这是一个内存分配器,类似glibc的obstack实现,支持栈式分配和释放
 */

void * obstack_alloc(ulong *obstack, ulong nbytes)
{
    ulong uVar1;
    ulong *puVar2;
    void *pvVar3;
    ulong *puVar4;
    ulong uVar5;
    ulong *puVar6;
    ulong *puVar7;
    ulong __n;
    void *__dest;
    bool overflow;

    __n = obstack[3] - obstack[2];        /* 当前块已用大小 */
    uVar5 = nbytes + __n;                  /* 分配后总大小 */
    uVar1 = obstack[1];                    /* 块起始位置 */
    overflow = CARRY8(uVar5, obstack[6]); /* 检查溢出 */
    puVar6 = (ulong *)(uVar5 + obstack[6]); /* 新块结束位置 */
    puVar4 = (ulong *)((ulong)overflow << 31);  /* 溢出标志 */
    puVar7 = (ulong *)((long)puVar6 + (__n >> 3) + 100);  /* 最小需要的块大小 */

    if (puVar6 < (ulong *)*obstack)       /* 不能小于起始位置 */
        puVar6 = (ulong *)*obstack;
    if (puVar6 <= puVar7)                  /* 取较大值 */
        puVar6 = puVar7;

    puVar7 = puVar6;
    if (!overflow && puVar4 == (ulong *)0x0) {  /* 没有溢出 */
        if ((obstack[10] & 1) == 0) {     /* 使用普通分配模式 */
            puVar4 = puVar6;
            puVar2 = (ulong *)(*(code *)obstack[7])();  /* 调用chunk_alloc */
        } else {                          /* 使用特殊模式 */
            puVar4 = (ulong *)obstack[9];
            puVar2 = (ulong *)(*(code *)obstack[7])();
        }

        if (puVar2 != (ulong *)0x0) {
            obstack[1] = (ulong)puVar2;          /* 更新块起始 */
            puVar2[1] = uVar1;                    /* 连接前一块 */
            pvVar3 = (void *)obstack[2];          /* 保存原数据位置 */
            obstack[4] = (long)puVar2 + (long)puVar6;  /* 设置新块结束 */
            *puVar2 = (long)puVar2 + (long)puVar6;
            /* 对齐到指定边界 */
            __dest = (void *)((long)(puVar2 + 2) + (-(long)(puVar2 + 2) & obstack[6]));
            pvVar3 = memcpy(__dest, pvVar3, __n);   /* 复制数据到新块 */

            uVar5 = obstack[10];
            if ((uVar5 & 2) == 0) {
                pvVar3 = (void *)((uVar1 + 0x10 + (-(uVar1 + 0x10) & obstack[6])));
                if ((void *)obstack[2] == pvVar3) {
                    puVar2[1] = *(ulong *)(uVar1 + 8);
                    if ((uVar5 & 1) == 0) {
                        pvVar3 = (void *)(*(code *)obstack[8])(uVar1);
                    } else {
                        pvVar3 = (void *)(*(code *)obstack[8])(obstack[9], uVar1);
                    }
                }
            }
            obstack[2] = (ulong)__dest;           /* 更新数据起始 */
            *(byte *)(obstack + 10) = (byte)obstack[10] & 0xfd;  /* 清除标志 */
            obstack[3] = (long)__dest + __n;      /* 更新数据结束 */
            return pvVar3;
        }
    }

    /* 分配失败,调用错误处理函数 */
    (*(code *)obstack_alloc_failed_handler)();

    puVar4 = (ulong *)puVar4[1];
    if (puVar4 == (ulong *)0x0) {
        return (void *)0x0;
    }
    /* 在空闲块链表中查找合适的块 */
    while ((puVar7 <= puVar4 || ((ulong *)*puVar4 < puVar7))) {
        puVar4 = (ulong *)puVar4[1];
        if (puVar4 == (ulong *)0x0) {
            return (void *)0x0;
        }
    }
    return (void *)0x1;
}

/* obstack 关键字段(推测):
 * [0] = 块起始指针
 * [1] = 当前块起始位置
 * [2] = 当前数据指针
 * [3] = 当前块结束位置
 * [4] = 下一个块位置
 * [6] = 对齐边界 (通常为 8 或 16)
 * [7] = chunk_alloc 函数指针
 * [8] = chunk_free 函数指针
 * [9] = 特殊模式参数
 * [10] = 标志位
 */
