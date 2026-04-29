/* [LLM4Decompile REFINED] */
/* 重命名对应关系:
 *   FUN_00119130          -> string_pool_intern_or_copy
 *   struct FUN_00119090   -> string_pool_chunk
 *   VAR_0                 -> dst_pool
 *   VAR_1                 -> src_entry
 *   VAR_2                 -> src_str
 *   VAR_3                 -> src_end
 *   VAR_4                 -> dst_str
 *   VAR_5                 -> dst_end
 *   VAR_6                 -> src_len
 *   VAR_7                 -> next_chunk
 *   FUN_00119090          -> string_pool_alloc_new_chunk
 *   VAR_00000000          -> data (字符串数据区指针)
 *   VAR_00000001          -> is_first_chunk (标记是否为第一个chunk)
 */

struct string_pool_chunk {
    char *data;
    char is_first_chunk;
};

struct string_pool_chunk *string_pool_alloc_new_chunk(const char *str);

int string_pool_intern_or_copy(struct string_pool_chunk *dst_pool, struct string_pool_chunk *src_entry)
{
    char *src_str = src_entry->data;
    char *src_end = src_entry->data + 12;
    char *dst_str = dst_pool->data;
    char *dst_end = dst_pool->data + 12;

    if (src_str == NULL || src_str < (char *)src_entry || src_str >= src_end)
        return 1;

    if (*src_str == '\0')
        dst_str = "";
    else
    {
        while (strcmp(dst_str, src_str))
        {
            if (*dst_str == '\0')
            {
                if (dst_str == dst_pool->data && dst_pool->is_first_chunk == '\0')
                {
                    size_t src_len = strlen(src_str) + 1;
                    if (src_len < (size_t)((size_t)(&dst_pool->data) - (size_t)(dst_str)))
                    {
                        memcpy(dst_str, src_str, src_len);
                        dst_str[src_len] = '\0';
                    }
                    else
                    {
                        dst_pool = string_pool_alloc_new_chunk(src_str);
                        if (dst_pool == NULL)
                            return 0;
                        dst_pool->is_first_chunk = '\0';
                        dst_str = dst_pool->data;
                    }
                    break;
                }
                dst_str += strlen(dst_str) + 1;
                if (*dst_str == '\0')
                {
                    struct string_pool_chunk *next_chunk = (struct string_pool_chunk *)dst_pool->is_first_chunk;
                    if (next_chunk == NULL)
                        break;
                    dst_pool = next_chunk;
                    dst_str = dst_pool->data;
                }
            }
            else
                dst_str += strlen(dst_str) + 1;
        }
    }

    src_entry->data = dst_str;
    return 1;
}
