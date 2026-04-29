/* [LLM4Decompile REFINED] */
/* 重命名对应关系:
 *   FUN_00116220          -> obstack_grow_or_alloc
 *   param_1               -> obs (obstack结构体指针)
 *   param_2               -> additional_size (需要额外分配的大小)
 *   uVar1                 -> old_chunk_size
 *   puVar2                -> new_chunk
 *   pvVar3                -> old_object_base / result_ptr
 *   puVar4                -> temp_carry (进位相关临时变量)
 *   uVar5                 -> total_needed
 *   puVar6                -> new_size
 *   puVar7                -> min_size
 *   __n                   -> old_object_size (旧对象大小)
 *   __dest                -> new_object_base
 *   bVar8                 -> carry_flag
 */

#include <stddef.h>
#include <stdbool.h>
#include <string.h>

extern void obstack_alloc_failed_handler(void);

void *
obstack_grow_or_alloc(ulong *obs, ulong additional_size)
{
    ulong old_chunk_size;
    ulong *new_chunk;
    void *old_object_base;
    ulong *temp_carry;
    ulong total_needed;
    ulong *new_size;
    ulong *min_size;
    size_t old_object_size;
    void *new_object_base;
    bool carry_flag;

    old_object_size = obs[3] - obs[2];
    total_needed = additional_size + old_object_size;
    old_chunk_size = obs[1];
    carry_flag = __builtin_add_overflow(total_needed, obs[6], &new_size);
    temp_carry = (ulong *)(((ulong)new_size >> 8) | (carry_flag ? 0x100 : 0));
    min_size = (ulong *)((long)new_size + (old_object_size >> 3) + 100);
    if (new_size < (ulong *)*obs) {
        new_size = (ulong *)*obs;
    }
    if (new_size <= min_size) {
        new_size = min_size;
    }
    min_size = new_size;
    if ((!__builtin_add_overflow(additional_size, old_object_size, &new_size)) &&
        (temp_carry = (ulong *)(ulong)carry_flag, temp_carry == (ulong *)0x0)) {
        if ((obs[10] & 1) == 0) {
            temp_carry = new_size;
            new_chunk = (ulong *)(*(code *)obs[7])();
        }
        else {
            temp_carry = (ulong *)obs[9];
            new_chunk = (ulong *)(*(code *)obs[7])();
        }
        if (new_chunk != (ulong *)0x0) {
            obs[1] = (ulong)new_chunk;
            new_chunk[1] = old_chunk_size;
            old_object_base = (void *)obs[2];
            obs[4] = (long)new_chunk + (long)new_size;
            *new_chunk = (long)new_chunk + (long)new_size;
            new_object_base = (void *)((long)(new_chunk + 2) + (-(long)(new_chunk + 2) & obs[6]));
            old_object_base = memcpy(new_object_base, old_object_base, old_object_size);
            ulong flags = obs[10];
            if ((flags & 2) == 0) {
                old_object_base = (void *)(old_chunk_size + 0x10 + (-(old_chunk_size + 0x10) & obs[6]));
                if ((void *)obs[2] == old_object_base) {
                    new_chunk[1] = *(ulong *)(old_chunk_size + 8);
                    if ((flags & 1) == 0) {
                        old_object_base = (void *)(*(code *)obs[8])(old_chunk_size);
                    }
                    else {
                        old_object_base = (void *)(*(code *)obs[8])(obs[9], old_chunk_size);
                    }
                }
            }
            obs[2] = (ulong)new_object_base;
            *(byte *)(obs + 10) = (byte)obs[10] & 0xfd;
            obs[3] = (long)new_object_base + old_object_size;
            return old_object_base;
        }
    }
    (*(code *)obstack_alloc_failed_handler)();
    temp_carry = (ulong *)temp_carry[1];
    if (temp_carry == (ulong *)0x0) {
        return (void *)0x0;
    }
    while ((min_size <= temp_carry || ((ulong *)*temp_carry < min_size))) {
        temp_carry = (ulong *)temp_carry[1];
        if (temp_carry == (ulong *)0x0) {
            return (void *)0x0;
        }
    }
    return (void *)0x1;
}
