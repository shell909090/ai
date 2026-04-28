/* [LLM4Decompile REFINED] */
char *
FUN_001074c0 (const char *s, char escape_slash)
{
  char *p, *q;
  int c;

  p = FUN_00119e00 (3, strlen (s) + 1);
  q = p;
  while ((c = *s++) != '\0')
    {
      if (c == '/' && escape_slash)
	*q++ = '/';
      else if (FUN_001074e0[c] != '\0')
	*q++ = c;
      else
	__sprintf_chk (q, 1, -1, "%%%02x", c);
      q += 3;
    }
  *q = '\0';
  return p;
}
