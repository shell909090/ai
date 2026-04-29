/* 00119130: 在字符串链表中查找/插入字符串
 * 对应关系:
 *   FUN_00119130 -> name_collated_table_insert (推测,类似glibc中的collated_path_compare)
 *   FUN_00119090 -> 可能是一个链表节点结构体,包含字符串指针和next指针
 *
 * 该函数在排序后的路径名链表中查找或插入一个字符串,保持字典序
 */

int name_collated_table_insert(struct collate_entry *node, struct collate_entry *search_key)
{
    char *current_name = search_key->name;           /* 要查找的字符串 */
    char *search_end = search_key->name + 12;        /* 搜索范围上界(推测) */
    char *name_ptr = node->name;                     /* 当前节点的字符串 */
    char *node_end = node->name + 12;                /* 当前节点范围上界 */

    if (current_name == NULL || current_name < search_key || current_name >= search_end)
        return 1;  /* 无效输入 */

    if (*current_name == '\0') {
        name_ptr = "";  /* 空字符串,直接置为空 */
    } else {
        while (strcmp(name_ptr, current_name)) {  /* 字符串不匹配,继续找 */
            if (*name_ptr == '\0') {  /* 当前节点字符串结束 */
                if (name_ptr == node->name && node->terminator == '\0') {
                    /* 到达链表末尾,需要插入新节点 */
                    size_t name_len = strlen(current_name) + 1;
                    size_t remaining = (size_t)(&search_key->name) - (size_t)(name_ptr);
                    if (name_len < remaining) {
                        /* 当前节点有足够空间,直接复制 */
                        memcpy(name_ptr, current_name, name_len);
                        name_ptr[name_len] = '\0';
                    } else {
                        /* 空间不足,分配新节点 */
                        node = collate_entry_alloc(current_name);
                        if (node == NULL)
                            return 0;
                        node->terminator = '\0';
                        name_ptr = node->name;
                    }
                    break;
                }
                name_ptr += strlen(name_ptr) + 1;  /* 跳到下一个字符串 */
                if (*name_ptr == '\0') {  /* 当前块结束,移动到下一个节点 */
                    struct collate_entry *next = node->next;
                    if (next == NULL)
                        break;
                    node = next;
                    name_ptr = node->name;
                }
            } else {
                name_ptr += strlen(name_ptr) + 1;  /* 跳到下一个字符串 */
            }
        }
    }

    search_key->name = name_ptr;  /* 返回找到/插入的位置 */
    return 1;
}

/* 推测的 collate_entry 结构体:
 * struct collate_entry {
 *     char *name;           // 字符串指针
 *     char terminator;      // 结束符标志
 *     struct collate_entry *next;  // 下一个节点
 * };
 */
