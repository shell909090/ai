/* [LLM4Decompile REFINED] */
/* 重命名对应关系:
 *   FUN_001074c0          -> encode_uri_component
 *   s                     -> input_str (输入字符串)
 *   escape_slash          -> escape_slash (是否转义斜杠)
 *   p                     -> buf_start (缓冲区起始指针)
 *   q                     -> buf_ptr (当前写入位置)
 *   c                     -> ch (当前字符)
 *   FUN_00119e00          -> xmalloc (分配内存函数)
 *   FUN_001074e0          -> no_escape_table (不需要转义的字符表)
 */

#include <string.h>
#include <stdio.h>
#include <stdlib.h>

extern void *xmalloc(size_t size);
extern char no_escape_table[256];

char *
encode_uri_component (const char *input_str, char escape_slash)
{
  char *buf_start, *buf_ptr;
  int ch;

  buf_start = xmalloc (3, strlen (input_str) + 1);
  buf_ptr = buf_start;
  while ((ch = *input_str++) != '\0')
    {
      if (ch == '/' && escape_slash)
	*buf_ptr++ = '/';
      else if (no_escape_table[ch] != '\0')
	*buf_ptr++ = ch;
      else
	__sprintf_chk (buf_ptr, 1, -1, "%%%02x", ch);
      buf_ptr += 3;
    }
  *buf_ptr = '\0';
  return buf_start;
}
