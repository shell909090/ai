undefined8 FUN_00119130(long *param_1,char *param_2)
{
  char *__s2;
  long *plVar1;
  int iVar2;
  size_t sVar3;
  long lVar4;
  char *__s1;
  
  __s2 = *(char **)(param_2 + 0x30);
  if ((__s2 != (char *)0x0) && ((__s2 < param_2 || (param_2 + 0x38 <= __s2)))) {
    __s1 = (char *)((long)param_1 + 9);
    if (*__s2 == '\0') {
      __s1 = "";
    }
    else {
      while (iVar2 = strcmp(__s1,__s2), iVar2 != 0) {
        while( true ) {
          if ((*__s1 == '\0') &&
             ((__s1 != (char *)((long)param_1 + 9) || ((char)param_1[1] == '\0')))) {
            sVar3 = strlen(__s2);
            if ((long)(sVar3 + 1) < (long)param_1 + (0x80 - (long)__s1)) {
              memcpy(__s1,__s2,sVar3 + 1);
              __s1[sVar3 + 1] = '\0';
            }
            else {
              lVar4 = FUN_00119090(__s2);
              *param_1 = lVar4;
              if (lVar4 == 0) {
                return 0;
              }
              *(undefined1 *)(lVar4 + 8) = 0;
              __s1 = (char *)(lVar4 + 9);
            }
            goto LAB_001191d0;
          }
          sVar3 = strlen(__s1);
          __s1 = __s1 + sVar3 + 1;
          if ((*__s1 != '\0') || (plVar1 = (long *)*param_1, plVar1 == (long *)0x0)) break;
          __s1 = (char *)((long)plVar1 + 9);
          iVar2 = strcmp(__s1,__s2);
          param_1 = plVar1;
          if (iVar2 == 0) goto LAB_001191d0;
        }
      }
    }
LAB_001191d0:
    *(char **)(param_2 + 0x30) = __s1;
  }
  return 1;
}
