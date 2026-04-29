/* [LLM4Decompile REFINED] */
char *
FUN_0011a360 (void)
{
  char *hostname = NULL;
  char *hostname_buf = NULL;
  size_t hostname_buf_size = 100;
  size_t hostname_len;
  int *err = __errno_location ();

  while (1)
    {
      hostname_buf[hostname_buf_size - 1] = '\0';
      *err = 0;
      if (!gethostname (hostname_buf, hostname_buf_size - 1))
 {
   hostname_len = strlen (hostname_buf);
   if (hostname_len + 1 < hostname_buf_size - 1)
     {
       if (!hostname)
  hostname = FUN_0011a100 (hostname_buf, hostname_len + 1);
       break;
     }
 }
      free (hostname);
      hostname = NULL;
      if (*err > 36 || *err == -1 || *err == -2)
 break;
      hostname_buf = FUN_00119f30 (NULL, &hostname_buf_size, 1, -1, 1);
    }
  return hostname;
}
