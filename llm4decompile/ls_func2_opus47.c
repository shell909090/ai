/*
 * 由 Claude Opus 4.7 在 llm4decompile 输出的基础上整理而来。
 *
 * 原始符号映射：
 *   FUN_00119130        -> pool_intern
 *   FUN_00119090        -> pool_chunk_alloc_with（在另一文件中定义）
 *   param_1 / VAR_0     -> pool   (链表头节点)
 *   param_2 / VAR_1     -> entry  (待驻留的条目)
 *   __s2    / VAR_2     -> name
 *   __s1    / VAR_4     -> slot
 *   param_1[1] 的低字节 -> first_locked
 *
 * 数据结构推断：
 *   - pool 是一个 *字符串驻留池 (string interning pool)*。
 *   - 池由单向链表组成；每个节点 (chunk) 共 128 字节 (0x80)：
 *       offset 0     struct chunk *next;       8 字节
 *       offset 8     char first_locked;        1 字节，非零表示首槽被外部锁定
 *       offset 9..   char buf[119];            紧密排列的 NUL 结尾字符串，
 *                                              块内末尾以双 NUL 标记结束
 *   - entry 持有一个 SBO (small string buffer):
 *       offset 0x00..0x2F   内联存储 (48 字节)
 *       offset 0x30         char *name;  指向 inline_buf 或池中拷贝
 *       offset 0x38         内联区域结束
 *
 * 函数语义：
 *   把 entry->name 规范化到 pool 中。
 *     1. name == NULL，或已位于 entry 自身内联存储中 —— 无需驻留，直接返回 1。
 *     2. 空串 —— 重定向到只读字面量 ""。
 *     3. 否则沿链表逐块扫描；命中则把 entry->name 改写到池中那一份；未命中则
 *        尝试追加到当前块剩余空间，剩余不够时调用 pool_chunk_alloc_with 申请
 *        新块挂在链尾。
 *   返回值：除分配新块失败时返回 0，其余路径均返回 1。
 *
 * 关于 first_locked：
 *   只在 slot 处于块的第一个槽位时才被检查，非零时禁止在该处写入。新分配的
 *   块在挂入链表后会被显式置 0，这样首次使用就能写入第一个槽。
 */

#include <string.h>

#define CHUNK_BYTES 128

struct chunk {
    struct chunk *next;        /* offset 0  */
    char  first_locked;        /* offset 8  */
    char  buf[119];            /* offset 9..127 */
};

struct entry {
    char  inline_buf[0x30];    /* 0..0x2F: SBO 内联存储 */
    char *name;                /* 0x30:    指向 inline_buf 或池中拷贝 */
    /* 0x38: 内联区结束 */
};

extern struct chunk *pool_chunk_alloc_with(const char *s);

int pool_intern(struct chunk *pool, struct entry *entry)
{
    char *name = entry->name;
    char *inline_end = (char *)entry + 0x38;

    /* NULL 或已经位于 entry 自身内联存储中：无需驻留 */
    if (name == NULL || (name >= (char *)entry && name < inline_end))
        return 1;

    char *slot;

    if (*name == '\0') {
        /* 空串映射到只读字面量，避免占用池空间 */
        slot = "";
    } else {
        struct chunk *cur = pool;
        slot = cur->buf;

        /* 外层：当 slot 指向的字符串与 name 不等时继续扫描 */
        while (strcmp(slot, name) != 0) {
            /* 内层：在链表上推进 slot；通过 break 回到外层重新比较 strcmp */
            for (;;) {
                int at_first = (slot == cur->buf);

                /* 找到一个可用空槽 */
                if (*slot == '\0' && (!at_first || cur->first_locked == '\0')) {
                    size_t need = strlen(name) + 1;
                    long   room = (char *)cur + CHUNK_BYTES - slot;

                    if ((long)need < room) {
                        /* 当前块空间够，直接拷贝并写入末尾哨兵 NUL */
                        memcpy(slot, name, need);
                        slot[need] = '\0';
                    } else {
                        /* 当前块装不下，分配新块并挂到链尾 */
                        struct chunk *fresh = pool_chunk_alloc_with(name);
                        cur->next = fresh;
                        if (fresh == NULL)
                            return 0;
                        fresh->first_locked = '\0';
                        slot = fresh->buf;
                    }
                    goto done;
                }

                /* 跳过当前已存条目 */
                slot += strlen(slot) + 1;

                /* 仍在当前块内，且下一条目非空：回到外层重新 strcmp */
                if (*slot != '\0')
                    break;

                /* 当前块扫到末尾，且无下一块：链表耗尽，回到外层（外层会再次
                 * 进入内层，进入 add 分支） */
                if (cur->next == NULL)
                    break;

                /* 进入下一块继续扫描 */
                cur  = cur->next;
                slot = cur->buf;
                if (strcmp(slot, name) == 0)
                    goto done;
            }
        }
    }

done:
    entry->name = slot;
    return 1;
}
