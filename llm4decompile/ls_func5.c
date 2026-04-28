byte * FUN_001074c0(byte *param_1,char param_2)
{
  byte bVar1;
  byte *pbVar2;
  size_t sVar3;
  byte *pbVar4;
  
  sVar3 = strlen((char *)param_1);
  pbVar4 = (byte *)FUN_00119e00(3,sVar3 + 1);
  bVar1 = *param_1;
  pbVar2 = pbVar4;
  do {
    while( true ) {
      if (bVar1 == 0) {
        *pbVar2 = 0;
        return pbVar4;
      }
      param_1 = param_1 + 1;
      if ((bVar1 != 0x2f) || (param_2 == '\0')) break;
      *pbVar2 = 0x2f;
LAB_0010750f:
      bVar1 = *param_1;
      pbVar2 = pbVar2 + 1;
    }
    if ((&DAT_00128000)[bVar1] != '\0') {
      *pbVar2 = bVar1;
      goto LAB_0010750f;
    }
    __sprintf_chk(pbVar2,1,0xffffffffffffffff,"%%%02x",bVar1);
    bVar1 = *param_1;
    pbVar2 = pbVar2 + 3;
  } while( true );
}
