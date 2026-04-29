/*
 * 在链式字符串表中查找或插入字符串。
 *
 * 数据结构 name_node:
 *   data[12]  — 内联字符串缓冲区 (12 字节)
 *   next      — 指向下一个 name_node 的指针
 *
 * 符号对应关系:
 *   FUN_00119130            → lookup_name
 *   FUN_00119090            → alloc_name_node  (推测为构造/分配新节点)
 *   struct FUN_00119090     → name_node
 *   VAR_00000000 (char*)    → data              (内联缓冲区起始)
 *   VAR_00000001 (pointer)  → next              (下一节点指针)
 *
 * 参数:
 *   head   — 链表头节点，在其中搜索/插入
 *   entry  — 包含待查找字符串的节点 (data 字段存储目标串)
 *
 * 返回值: 1=成功, 0=内存分配失败
 */
int
lookup_name(struct name_node *head, struct name_node *entry)
{
    char *needle      = entry->data;
    char *needle_end  = entry->data + 12;
    char *cursor      = head->data;
    char *cursor_end  = head->data + 12;

    /* 参数校验: needle 非法则直接返回 */
    if (needle == NULL || needle < (char *)entry || needle >= needle_end)
        return 1;

    if (*needle == '\0') {
        cursor = "";
    } else {
        while (strcmp(cursor, needle) != 0) {

            if (*cursor != '\0') {
                /* 当前串不匹配，跳到下一个串 */
                cursor += strlen(cursor) + 1;
                continue;
            }

            /* cursor 指向空串 —— 已到达缓冲区内的空闲位置 */

            if (cursor == head->data && head->next == NULL) {
                /* 位于首个节点的起始空闲位，尝试内联写入 */
                size_t len = strlen(needle) + 1;

                if (len < (size_t)((size_t)(&entry->data) - (size_t)(cursor))) {
                    /* 剩余空间足够 */
                    memcpy(cursor, needle, len);
                    cursor[len] = '\0';
                } else {
                    /* 剩余空间不足，分配新节点挂链 */
                    head = alloc_name_node(needle);
                    if (head == NULL)
                        return 0;
                    head->next = NULL;
                    cursor = head->data;
                }
                break;
            }

            /* 跳到当前节点内下一个串 */
            cursor += strlen(cursor) + 1;

            if (*cursor == '\0') {
                /* 当前节点已耗尽，尝试进入下一个节点 */
                struct name_node *next = head->next;
                if (next == NULL)
                    break;
                head   = next;
                cursor = head->data;
            }
        }
    }

    /* 回填找到/插入的位置 */
    entry->data = cursor;
    return 1;
}
