void * FUN_00116220(ulong *param_1,ulong param_2)
{
  ulong uVar1;
  ulong *puVar2;
  void *pvVar3;
  ulong *puVar4;
  ulong uVar5;
  ulong *puVar6;
  ulong *puVar7;
  ulong __n;
  void *__dest;
  bool bVar8;
  
  __n = param_1[3] - param_1[2];
  uVar5 = param_2 + __n;
  uVar1 = param_1[1];
  bVar8 = CARRY8(uVar5,param_1[6]);
  puVar6 = (ulong *)(uVar5 + param_1[6]);
  puVar4 = (ulong *)CONCAT71((int7)((ulong)param_1 >> 8),bVar8);
  puVar7 = (ulong *)((long)puVar6 + (__n >> 3) + 100);
  if (puVar6 < (ulong *)*param_1) {
    puVar6 = (ulong *)*param_1;
  }
  if (puVar6 <= puVar7) {
    puVar6 = puVar7;
  }
  puVar7 = puVar6;
  if ((!CARRY8(param_2,__n)) && (puVar4 = (ulong *)(ulong)bVar8, puVar4 == (ulong *)0x0)) {
    if ((param_1[10] & 1) == 0) {
      puVar4 = puVar6;
      puVar2 = (ulong *)(*(code *)param_1[7])();
    }
    else {
      puVar4 = (ulong *)param_1[9];
      puVar2 = (ulong *)(*(code *)param_1[7])();
    }
    if (puVar2 != (ulong *)0x0) {
      param_1[1] = (ulong)puVar2;
      puVar2[1] = uVar1;
      pvVar3 = (void *)param_1[2];
      param_1[4] = (long)puVar2 + (long)puVar6;
      *puVar2 = (long)puVar2 + (long)puVar6;
      __dest = (void *)((long)(puVar2 + 2) + (-(long)(puVar2 + 2) & param_1[6]));
      pvVar3 = memcpy(__dest,pvVar3,__n);
      uVar5 = param_1[10];
      if ((uVar5 & 2) == 0) {
        pvVar3 = (void *)(uVar1 + 0x10 + (-(uVar1 + 0x10) & param_1[6]));
        if ((void *)param_1[2] == pvVar3) {
          puVar2[1] = *(ulong *)(uVar1 + 8);
          if ((uVar5 & 1) == 0) {
            pvVar3 = (void *)(*(code *)param_1[8])(uVar1);
          }
          else {
            pvVar3 = (void *)(*(code *)param_1[8])(param_1[9],uVar1);
          }
        }
      }
      param_1[2] = (ulong)__dest;
      *(byte *)(param_1 + 10) = (byte)param_1[10] & 0xfd;
      param_1[3] = (long)__dest + __n;
      return pvVar3;
    }
  }
  (*(code *)obstack_alloc_failed_handler)();
  puVar4 = (ulong *)puVar4[1];
  if (puVar4 == (ulong *)0x0) {
    return (void *)0x0;
  }
  while ((puVar7 <= puVar4 || ((ulong *)*puVar4 < puVar7))) {
    puVar4 = (ulong *)puVar4[1];
    if (puVar4 == (ulong *)0x0) {
      return (void *)0x0;
    }
  }
  return (void *)0x1;
}
