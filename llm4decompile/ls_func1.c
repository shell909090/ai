char * FUN_0011a360(void)
{
  int iVar1;
  uint *puVar2;
  char *__name;
  long lVar3;
  size_t sVar4;
  char *__ptr;
  long in_FS_OFFSET;
  long local_a0;
  char local_98 [104];
  long local_30;
  
  local_30 = *(long *)(in_FS_OFFSET + 0x28);
  __name = local_98;
  local_a0 = 100;
  puVar2 = (uint *)__errno_location();
  lVar3 = 100;
  __ptr = (char *)0x0;
  while( true ) {
    __name[lVar3 + -1] = '\0';
    *puVar2 = 0;
    iVar1 = gethostname(__name,lVar3 - 1U);
    if (iVar1 == 0) {
      sVar4 = strlen(__name);
      if ((long)(sVar4 + 1) < (long)(lVar3 - 1U)) {
        if (__ptr == (char *)0x0) {
          __ptr = (char *)FUN_0011a100(__name,sVar4 + 1);
        }
        goto LAB_0011a429;
      }
      *puVar2 = 0;
    }
    free(__ptr);
    if ((0x24 < *puVar2) || ((0xffffffefffbfeffeU >> ((ulong)*puVar2 & 0x3f) & 1) != 0)) break;
    __name = (char *)FUN_00119f30(0,&local_a0,1,0xffffffffffffffff,1);
    lVar3 = local_a0;
    __ptr = __name;
  }
  __ptr = (char *)0x0;
LAB_0011a429:
  if (local_30 == *(long *)(in_FS_OFFSET + 0x28)) {
    return __ptr;
  }
                    // WARNING: Subroutine does not return
  __stack_chk_fail();
}
