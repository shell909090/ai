undefined4 FUN_00104c00(uint param_1,FILE *param_2)
{
  char cVar1;
  void *__s1;
  byte bVar2;
  FILE *__stream;
  ulong uVar3;
  char cVar4;
  undefined1 uVar5;
  char cVar6;
  byte bVar7;
  int iVar8;
  int iVar9;
  uint uVar10;
  long lVar11;
  undefined8 *puVar12;
  void *pvVar13;
  undefined8 uVar14;
  undefined8 uVar15;
  ulong uVar16;
  size_t sVar17;
  size_t *psVar18;
  char *pcVar19;
  undefined **ppuVar20;
  long *__ptr;
  size_t *psVar21;
  char *pcVar22;
  undefined *puVar23;
  undefined8 *puVar24;
  undefined *in_R9;
  undefined8 *in_R10;
  undefined8 in_R11;
  char *pcVar25;
  long lVar26;
  size_t *psVar27;
  long in_FS_OFFSET;
  bool bVar28;
  int local_90;
  int local_8c;
  char *local_88;
  ulong local_80;
  undefined *local_78;
  int local_70;
  char *local_60;
  undefined8 local_58;
  undefined8 uStack_50;
  char local_44;
  char local_43;
  undefined1 local_42;
  long local_40;
  
  local_40 = *(long *)(in_FS_OFFSET + 0x28);
  FUN_00116460(*(undefined8 *)param_2);
  setlocale(6,"");
  bindtextdomain("coreutils","/usr/share/locale");
  textdomain("coreutils");
  DAT_001271f8 = 2;
  FUN_0011ace0(FUN_0010fe00);
  DAT_00128230 = 0;
  DAT_001282d8 = 1;
  DAT_001283a0 = (long *)0x0;
  local_80 = 0xffffffffffffffff;
  local_78 = (undefined *)0xffffffffffffffff;
  local_90 = -1;
  local_8c = -1;
  local_70 = -1;
  uVar10 = 0xffffffff;
  bVar28 = false;
  local_88 = (char *)0x0;
  DAT_00128390 = 0x8000000000000000;
  DAT_00128398 = 0xffffffffffffffff;
LAB_00104d00:
  ppuVar20 = &PTR_s_all_00126340;
  puVar23 = (undefined *)(ulong)param_1;
  local_58 = (undefined *)CONCAT44(local_58._4_4_,0xffffffff);
  puVar24 = &local_58;
  iVar8 = getopt_long(puVar23,param_2,"abcdfghiklmnopqrstuvw:xABCDFGHI:LNQRST:UXZ1");
  if (iVar8 != -1) {
    if (0x114 < iVar8 + 0x83U) goto switchD_00104d37_caseD_ffffff7f;
    switch(iVar8) {
    case 0x31:
      uVar10 = (uint)(uVar10 != 0);
      break;
    case 0x41:
      DAT_00128310 = 1;
      break;
    case 0x42:
      FUN_00106ce0(&DAT_0011d0ef);
      FUN_00106ce0(&DAT_0011d0ee);
      break;
    case 0x43:
      uVar10 = 2;
      break;
    case 0x44:
      in_R11 = 0;
      DAT_00128331 = 0;
      DAT_00128338 = 1;
      uVar10 = 0;
      break;
    case 0x46:
      if (optarg != (char *)0x0) {
        in_R9 = (undefined *)0x1;
        in_R10 = puVar24;
        lVar26 = FUN_0010f1d0("--classify",optarg,&PTR_s_always_00126200,&DAT_0011b680,4,
                              PTR_FUN_001271f0,1,puVar24);
        if ((*(int *)(&DAT_0011b680 + lVar26 * 4) != 1) &&
           ((*(int *)(&DAT_0011b680 + lVar26 * 4) != 2 || (cVar4 = FUN_00106e50(), cVar4 == '\0'))))
        break;
      }
      DAT_00128334 = 3;
      break;
    case 0x47:
      DAT_00127028 = 0;
      break;
    case 0x48:
      DAT_00128318 = 2;
      break;
    case 0x49:
      FUN_00106ce0(optarg);
      break;
    case 0x4c:
      DAT_00128318 = 4;
      break;
    case 0x4e:
      local_8c = 0;
      break;
    case 0x51:
      local_8c = 5;
      break;
    case 0x52:
      DAT_00128316 = 1;
      break;
    case 0x53:
      local_90 = 3;
      break;
    case 0x54:
      in_R9 = (undefined *)dcgettext(0,"invalid tab size",5);
      local_78 = (undefined *)FUN_0011a200(optarg,0,0,0x7fffffffffffffff,&DAT_0011cf4c,in_R9,2,0);
      break;
    case 0x55:
      local_90 = 6;
      break;
    case 0x58:
      local_90 = 1;
      break;
    case 0x5a:
      DAT_00128389 = 1;
      break;
    case 0x61:
      DAT_00128310 = 2;
      break;
    case 0x62:
      local_8c = 7;
      break;
    case 99:
      DAT_00128358 = 1;
      DAT_00128354 = '\x01';
      break;
    case 100:
      DAT_00128315 = '\x01';
      break;
    case 0x66:
      DAT_00128310 = 2;
      local_90 = 6;
      break;
    case 0x67:
      DAT_00127029 = 0;
    case 0x6c:
      uVar10 = 0;
      break;
    case 0x68:
      DAT_00128348 = 0xb0;
      DAT_0012833c = 0xb0;
      DAT_00128340 = 1;
      DAT_00127020 = 1;
      break;
    case 0x69:
      DAT_0012831c = 1;
      break;
    case 0x6b:
      bVar28 = true;
      break;
    case 0x6d:
      uVar10 = 4;
      break;
    case 0x6e:
      DAT_0012834d = 1;
      uVar10 = 0;
      break;
    case 0x6f:
      DAT_00127028 = 0;
      uVar10 = 0;
      break;
    case 0x70:
      DAT_00128334 = 1;
      break;
    case 0x71:
      local_70 = 1;
      break;
    case 0x72:
      DAT_0012834f = 1;
      break;
    case 0x73:
      DAT_0012834c = 1;
      break;
    case 0x74:
      local_90 = 5;
      break;
    case 0x75:
      DAT_00128358 = 2;
      DAT_00128354 = '\x01';
      break;
    case 0x76:
      goto switchD_00104d37_caseD_76;
    case 0x77:
      local_80 = FUN_00106de0(optarg);
      if (local_80 == 0xffffffffffffffff) {
        param_2 = (FILE *)FUN_00118c20(optarg);
        uVar14 = dcgettext(0,"invalid line width",5);
        error(2,0,"%s: %s",uVar14,param_2);
switchD_00104d37_caseD_76:
        local_90 = 4;
      }
      break;
    case 0x78:
      uVar10 = 3;
      break;
    case 0x80:
      DAT_0012834e = 1;
      break;
    case 0x81:
      iVar8 = FUN_00113490(optarg,&DAT_00128348,&DAT_00128340);
      if (iVar8 != 0) {
                    // WARNING: Subroutine does not return
        FUN_0011a470(iVar8,(ulong)local_58 & 0xffffffff,0,&PTR_s_all_00126340,optarg);
      }
      DAT_0012833c = DAT_00128348;
      DAT_00127020 = DAT_00128340;
      break;
    case 0x82:
      if (optarg == (char *)0x0) {
LAB_0010591d:
        bVar7 = 1;
      }
      else {
        in_R9 = PTR_FUN_001271f0;
        lVar26 = FUN_0010f1d0("--color",optarg,&PTR_s_always_00126200,&DAT_0011b680,4,
                              PTR_FUN_001271f0,1);
        if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 1) goto LAB_0010591d;
        bVar7 = 0;
        if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 2) {
          bVar7 = FUN_00106e50();
        }
      }
      DAT_00128332 = bVar7 & 1;
      break;
    case 0x83:
      DAT_00128318 = 3;
      break;
    case 0x84:
      DAT_00128334 = 2;
      break;
    case 0x85:
      in_R9 = puVar23;
      lVar26 = FUN_0010f1d0("--format",optarg,&PTR_s_verbose_00126300,&DAT_0011b710,4,
                            PTR_FUN_001271f0,1,puVar23);
      uVar10 = *(uint *)(&DAT_0011b710 + lVar26 * 4);
      break;
    case 0x86:
      uVar10 = 0;
      local_88 = "full-iso";
      break;
    case 0x87:
      DAT_00128314 = 1;
      break;
    case 0x88:
      puVar12 = (undefined8 *)FUN_00119d00(0x10);
      puVar24 = DAT_00128300;
      DAT_00128300 = puVar12;
      *puVar12 = optarg;
      puVar12[1] = puVar24;
      break;
    case 0x89:
      if (optarg == (char *)0x0) {
LAB_00105934:
        bVar7 = 1;
      }
      else {
        in_R9 = (undefined *)0x1;
        in_R10 = puVar24;
        lVar26 = FUN_0010f1d0("--hyperlink",optarg,&PTR_s_always_00126200,&DAT_0011b680,4,
                              PTR_FUN_001271f0,1,puVar24);
        if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 1) goto LAB_00105934;
        bVar7 = 0;
        if (*(int *)(&DAT_0011b680 + lVar26 * 4) == 2) {
          bVar7 = FUN_00106e50();
        }
      }
      DAT_00128331 = bVar7 & 1;
      break;
    case 0x8a:
      in_R9 = PTR_FUN_001271f0;
      lVar26 = FUN_0010f1d0("--indicator-style",optarg,&PTR_DAT_001268e0,"",4,PTR_FUN_001271f0,1,
                            ppuVar20);
      DAT_00128334 = *(uint *)("lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl" +
                              lVar26 * 4 + 0x30);
      break;
    case 0x8b:
      in_R9 = PTR_FUN_001271f0;
      lVar26 = FUN_0010f1d0("--quoting-style",optarg,&PTR_s_literal_001269a0,&DAT_00120220,4,
                            PTR_FUN_001271f0,1,in_R11);
      local_8c = *(int *)(&DAT_00120220 + lVar26 * 4);
      break;
    case 0x8c:
      goto switchD_00104d37_caseD_8c;
    case 0x8d:
      DAT_00128348 = 0x90;
      DAT_0012833c = 0x90;
      DAT_00128340 = 1;
      DAT_00127020 = 1;
      break;
    case 0x8e:
      in_R9 = PTR_FUN_001271f0;
      lVar26 = FUN_0010f1d0("--sort",optarg,&DAT_001262c0,&DAT_0011b6f0,4,PTR_FUN_001271f0,1,
                            (long)&switchD_00104d37::switchdataD_0011b174 +
                            (long)(int)(&switchD_00104d37::switchdataD_0011b174)[iVar8 + 0x83U]);
      local_90 = *(int *)(&DAT_0011b6f0 + lVar26 * 4);
      break;
    case 0x8f:
      in_R11 = 1;
      in_R9 = PTR_FUN_001271f0;
      lVar26 = FUN_0010f1d0("--time",optarg,&DAT_00126260,&DAT_0011b6c0,4,PTR_FUN_001271f0,1,in_R10)
      ;
      DAT_00128354 = '\x01';
      DAT_00128358 = *(undefined4 *)(&DAT_0011b6c0 + lVar26 * 4);
      break;
    case 0x90:
      goto switchD_00104d37_caseD_90;
    case 0x91:
      DAT_00127019 = '\0';
      in_R10 = (undefined8 *)0x0;
      DAT_00128332 = 0;
      uVar10 = (uint)(uVar10 != 0);
      local_8c = 0;
switchD_00104d37_caseD_8c:
      local_70 = 0;
      break;
    case -0x83:
      uVar14 = FUN_00116520("David MacKenzie","David MacKenzie");
      uVar15 = FUN_00116520("Richard M. Stallman","Richard M. Stallman");
      pcVar25 = "ls";
      if ((DAT_001271e0 != 1) && (pcVar25 = "vdir", DAT_001271e0 == 2)) {
        pcVar25 = "dir";
      }
      FUN_00119b30(stdout,pcVar25,"GNU coreutils",PTR_DAT_001271e8,uVar15,uVar14,0,in_R9);
                    // WARNING: Subroutine does not return
      exit(0);
    case -0x82:
      goto switchD_00104d37_caseD_ffffff7e;
    default:
      goto switchD_00104d37_caseD_ffffff7f;
    }
    goto LAB_00104d00;
  }
  if (DAT_00128340 == 0) {
    pcVar25 = getenv("LS_BLOCK_SIZE");
    FUN_00113490(pcVar25,&DAT_00128348,&DAT_00128340);
    if ((pcVar25 != (char *)0x0) || (pcVar25 = getenv("BLOCK_SIZE"), pcVar25 != (char *)0x0)) {
      DAT_0012833c = DAT_00128348;
      DAT_00127020 = DAT_00128340;
    }
    if (bVar28) {
      DAT_00128340 = 0x400;
      DAT_00128348 = 0;
    }
  }
  if ((int)uVar10 < 0) {
    if (DAT_001271e0 == 1) goto LAB_001064c7;
    uVar10 = (uint)(DAT_001271e0 == 2) * 2;
  }
  do {
    uVar16 = local_80;
    DAT_0012835c = uVar10;
    uVar3 = local_80;
    if ((uVar10 - 2 < 3) || (DAT_00128332 != 0)) {
      if (local_80 == 0xffffffffffffffff) {
        cVar4 = FUN_00106e50();
        if ((cVar4 != '\0') && (iVar8 = ioctl(1,0x5413,&local_58), -1 < iVar8)) {
          uVar16 = (ulong)local_58._2_2_;
          uVar3 = uVar16;
          if (local_58._2_2_ != 0) goto LAB_00104db0;
        }
        pcVar25 = getenv("COLUMNS");
        if ((pcVar25 != (char *)0x0) && (*pcVar25 != '\0')) {
          local_80 = FUN_00106de0(pcVar25);
          uVar16 = local_80;
          uVar3 = local_80;
          if (local_80 != 0xffffffffffffffff) goto LAB_00104db0;
          uVar14 = FUN_00118c20(pcVar25);
          uVar15 = dcgettext(0,"ignoring invalid width in environment variable COLUMNS: %s",5);
          error(0,0,uVar15,uVar14);
        }
LAB_0010521e:
        uVar16 = 0x50;
        uVar3 = local_80;
      }
    }
    else if (local_80 == 0xffffffffffffffff) goto LAB_0010521e;
LAB_00104db0:
    local_80 = uVar3;
    DAT_00128220 = (uVar16 / 3 + 1) - (ulong)(uVar16 % 3 == 0);
    DAT_001282d0 = uVar16;
    puVar23 = DAT_001282e0;
    if ((DAT_0012835c - 2 < 3) && (puVar23 = local_78, (long)local_78 < 0)) {
      DAT_001282e0 = (undefined *)0x8;
      pcVar25 = getenv("TABSIZE");
      puVar23 = DAT_001282e0;
      if ((pcVar25 != (char *)0x0) &&
         (iVar8 = FUN_0011a540(pcVar25,0,0,&local_58,&DAT_0011cf4c), puVar23 = local_58, iVar8 != 0)
         ) {
        uVar14 = FUN_00118c20(pcVar25);
        uVar15 = dcgettext(0,"ignoring invalid tab size in environment variable TABSIZE: %s",5);
        error(0,0,uVar15,uVar14);
        puVar23 = DAT_001282e0;
      }
    }
    DAT_001282e0 = puVar23;
    bVar7 = (byte)local_70 & 1;
    if ((local_70 == -1) && (bVar7 = 0, DAT_001271e0 == 1)) {
      bVar7 = FUN_00106e50();
    }
    DAT_001282f8 = bVar7;
    if (local_8c < 0) {
      pcVar25 = getenv("QUOTING_STYLE");
      if (pcVar25 == (char *)0x0) goto LAB_00105a42;
      iVar8 = FUN_0010ee80(pcVar25,&PTR_s_literal_001269a0,&DAT_00120220,4);
      if (iVar8 < 0) goto LAB_0010670b;
      local_8c = *(int *)(&DAT_00120220 + (long)iVar8 * 4);
      if (local_8c < 0) goto LAB_00105a42;
    }
LAB_00104e16:
    FUN_00118160(0,local_8c);
    while( true ) {
      uVar10 = FUN_00118140(0);
      if (((DAT_0012835c == 0) || ((DAT_0012835c - 2 < 2 && (DAT_001282d0 != 0)))) && (uVar10 < 7))
      {
        if ((0x4aUL >> ((ulong)uVar10 & 0x3f) & 1) == 0) {
          DAT_001283c8 = 0;
          DAT_001282f0 = FUN_00118100(0);
        }
        else {
          DAT_001283c8 = 1;
          DAT_001282f0 = FUN_00118100(0);
        }
      }
      else {
        DAT_001283c8 = 0;
        DAT_001282f0 = FUN_00118100(0);
        if (uVar10 == 7) {
          FUN_00118180(DAT_001282f0,0x20,1);
        }
      }
      if (1 < DAT_00128334) {
        pcVar25 = &DAT_0011d1ab + (DAT_00128334 - 2);
        cVar4 = (&DAT_0011d1ab)[DAT_00128334 - 2];
        while (cVar4 != '\0') {
          pcVar25 = pcVar25 + 1;
          FUN_00118180(DAT_001282f0,(int)cVar4,1);
          cVar4 = *pcVar25;
        }
      }
      DAT_001282e8 = FUN_00118100(0);
      FUN_00118180(DAT_001282e8,0x3a,1);
      DAT_00128338 = (DAT_00128331 ^ 1) & DAT_0012835c == 0 & DAT_00128338;
      if ((int)(uint)DAT_00128338 <= (int)DAT_00127019) break;
LAB_001066e7:
      uVar14 = dcgettext(0,"--dired and --zero are incompatible",5);
      error(2,0,uVar14);
LAB_0010670b:
      uVar14 = FUN_00118c20();
      uVar15 = dcgettext(0,"ignoring invalid value of environment variable QUOTING_STYLE: %s",5);
      error(0,0,uVar15,uVar14);
LAB_00105a42:
      local_8c = 7;
      if (DAT_001271e0 != 1) goto LAB_00104e16;
      cVar4 = FUN_00106e50();
      if (cVar4 != '\0') goto code_r0x00105a64;
    }
    if (local_90 < 0) {
      if (DAT_0012835c == 0) {
        DAT_00128350 = 0;
        goto LAB_00104f1f;
      }
      if (DAT_00128354 == '\0') {
        DAT_00128350 = 0;
      }
      else {
        DAT_00128350 = 5;
      }
      goto LAB_00104f6a;
    }
    DAT_00128350 = local_90;
    if (DAT_0012835c != 0) goto LAB_00104f6a;
LAB_00104f1f:
    if ((local_88 == (char *)0x0) && (local_88 = getenv("TIME_STYLE"), local_88 == (char *)0x0)) {
      local_88 = "locale";
    }
    else {
      while (iVar8 = strncmp(local_88,"posix-",6), iVar8 == 0) {
        cVar4 = FUN_00111400(2);
        if (cVar4 == '\0') goto LAB_00104f6a;
        local_88 = local_88 + 6;
      }
    }
    if (*local_88 == '+') {
      pcVar25 = local_88 + 1;
      pcVar19 = strchr(pcVar25,10);
      pcVar22 = pcVar25;
      if (pcVar19 != (char *)0x0) {
        pcVar22 = strchr(pcVar19 + 1,10);
        if (pcVar22 != (char *)0x0) {
          param_2 = (FILE *)FUN_00118c20(pcVar25);
          uVar14 = dcgettext(0,"invalid time style format %s",5);
          error(2,0,uVar14,param_2);
          goto LAB_001066e7;
        }
        *pcVar19 = '\0';
        pcVar22 = pcVar19 + 1;
      }
      goto LAB_00106154;
    }
    ppuVar20 = &PTR_s_full_iso_00126920;
    lVar26 = FUN_0010ee80(local_88,&PTR_s_full_iso_00126920,&DAT_0011b7c0,4);
    if (-1 < lVar26) goto code_r0x00106124;
    param_1 = 0x11d1fa;
    FUN_0010f000("time style",local_88,lVar26);
    __stream = stderr;
    pcVar25 = (char *)dcgettext(0,"Valid arguments are:\n",5);
    fputs_unlocked(pcVar25,__stream);
    for (; param_2 = stderr, *ppuVar20 != (undefined *)0x0; ppuVar20 = ppuVar20 + 1) {
      __fprintf_chk(stderr,1,"  - [posix-]%s\n");
    }
    pcVar25 = (char *)dcgettext(0,"  - +FORMAT (e.g., +%H:%M) for a \'date\'-style format\n",5);
    fputs_unlocked(pcVar25,param_2);
switchD_00104d37_caseD_ffffff7f:
    FUN_0010e360();
switchD_00104d37_caseD_ffffff7e:
    FUN_0010e360(0);
LAB_001064c7:
    bVar7 = FUN_00106e50();
    uVar10 = bVar7 + 1;
  } while( true );
switchD_00104d37_caseD_90:
  local_88 = optarg;
  goto LAB_00104d00;
code_r0x00106124:
  if (lVar26 == 2) {
    PTR_DAT_00127040 = s__Y__m__d_0011d231;
    PTR_s__b__e__H__M_00127048 = &DAT_0011d225;
    pcVar25 = PTR_DAT_00127040;
    pcVar22 = PTR_s__b__e__H__M_00127048;
  }
  else if (lVar26 < 3) {
    if (lVar26 == 0) {
      PTR_DAT_00127040 = s__Y__m__d__H__M__S__N__z_0011d20a;
      PTR_s__b__e__H__M_00127048 = s__Y__m__d__H__M__S__N__z_0011d20a;
      pcVar25 = PTR_DAT_00127040;
      pcVar22 = PTR_s__b__e__H__M_00127048;
    }
    else {
      PTR_DAT_00127040 = &DAT_0011d222;
      PTR_s__b__e__H__M_00127048 = &DAT_0011d222;
      pcVar25 = PTR_DAT_00127040;
      pcVar22 = PTR_s__b__e__H__M_00127048;
    }
  }
  else {
    pcVar25 = PTR_DAT_00127040;
    pcVar22 = PTR_s__b__e__H__M_00127048;
    if ((lVar26 == 3) &&
       (cVar4 = FUN_00111400(2), pcVar25 = PTR_DAT_00127040, pcVar22 = PTR_s__b__e__H__M_00127048,
       cVar4 != '\0')) {
      PTR_DAT_00127040 = (undefined *)dcgettext(0,PTR_DAT_00127040,2);
      pcVar22 = (char *)dcgettext(0,PTR_s__b__e__H__M_00127048,2);
      pcVar25 = PTR_DAT_00127040;
    }
  }
LAB_00106154:
  PTR_s__b__e__H__M_00127048 = pcVar22;
  PTR_DAT_00127040 = pcVar25;
  FUN_00106e80();
LAB_00104f6a:
  bVar7 = DAT_00128332;
  iVar8 = optind;
  if (DAT_00128332 == 0) goto LAB_00104f82;
  local_60 = getenv("LS_COLORS");
  if ((local_60 != (char *)0x0) && (*local_60 != '\0')) {
    DAT_00128320 = (undefined *)FUN_0011a180(local_60);
    local_58 = DAT_00128320;
    goto LAB_00105d12;
  }
  pcVar25 = getenv("COLORTERM");
  if ((pcVar25 != (char *)0x0) && (*pcVar25 != '\0')) goto LAB_00106215;
  pcVar25 = getenv("TERM");
  if ((pcVar25 == (char *)0x0) || (*pcVar25 == '\0')) goto LAB_0010656a;
  pcVar22 = "# Configuration file for dircolors, a utility to help you set the";
  goto LAB_001062c5;
LAB_00105d12:
  pcVar25 = local_60;
  cVar4 = *local_60;
  if (cVar4 == '*') {
    psVar18 = (size_t *)FUN_00119d00(0x30);
    *(undefined1 *)(psVar18 + 4) = 0;
    local_60 = pcVar25 + 1;
    psVar18[5] = (size_t)DAT_00128328;
    psVar18[1] = (size_t)local_58;
    DAT_00128328 = psVar18;
    cVar4 = FUN_00106920(&local_58,&local_60,1,psVar18);
    pcVar25 = local_60;
    if ((cVar4 == '\0') || (pcVar25 = local_60 + 1, *local_60 != '=')) goto LAB_00105eeb;
    psVar18[3] = (size_t)local_58;
    local_60 = local_60 + 1;
    cVar4 = FUN_00106920(&local_58,&local_60,0,psVar18 + 2);
    pcVar25 = local_60;
    if (cVar4 == '\0') goto LAB_00105eeb;
    goto LAB_00105d12;
  }
  if (cVar4 == ':') {
    local_60 = local_60 + 1;
  }
  else {
    if (cVar4 == '\0') {
      psVar18 = DAT_00128328;
      if (DAT_00128328 != (size_t *)0x0) {
        while (psVar21 = psVar18, psVar18 = (size_t *)psVar21[5], psVar18 != (size_t *)0x0) {
          bVar2 = 0;
          psVar27 = psVar18;
          do {
            sVar17 = *psVar27;
            if ((sVar17 != 0xffffffffffffffff) && (sVar17 == *psVar21)) {
              pvVar13 = (void *)psVar27[1];
              __s1 = (void *)psVar21[1];
              iVar9 = memcmp(__s1,pvVar13,sVar17);
              if (iVar9 == 0) {
                *psVar27 = 0xffffffffffffffff;
              }
              else {
                iVar9 = FUN_0010f3c0(__s1,pvVar13,sVar17);
                if (iVar9 == 0) {
                  if ((bVar2 == 0) &&
                     ((psVar21[2] != psVar27[2] ||
                      (iVar9 = memcmp((void *)psVar21[3],(void *)psVar27[3],psVar21[2]), iVar9 != 0)
                      ))) {
                    *(undefined1 *)(psVar21 + 4) = 1;
                    *(undefined1 *)(psVar27 + 4) = 1;
                  }
                  else {
                    *psVar27 = 0xffffffffffffffff;
                    bVar2 = bVar7;
                  }
                }
              }
            }
            psVar27 = (size_t *)psVar27[5];
          } while (psVar27 != (size_t *)0x0);
        }
      }
      goto LAB_001063ca;
    }
    cVar1 = local_60[1];
    pcVar25 = local_60 + 1;
    if ((cVar1 == '\0') || (pcVar25 = local_60 + 3, local_60[2] != '=')) goto LAB_00105eeb;
    lVar26 = 0;
    while ((local_60 = pcVar25,
           cVar4 != "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"[lVar26 * 2] ||
           (cVar1 != "lcrcecrsnofidilnpisobdcdmiorexdosusgstowtwcamhcl"[lVar26 * 2 + 1]))) {
      lVar26 = lVar26 + 1;
      if (lVar26 == 0x18) goto LAB_00105eab;
    }
    (&PTR_DAT_00127068)[(long)(int)lVar26 * 2] = local_58;
    cVar6 = FUN_00106920(&local_58,&local_60,0);
    if (cVar6 == '\0') goto LAB_00105eab;
  }
  goto LAB_00105d12;
LAB_001062c5:
  if ((char *)0x15ef < pcVar22 + -0x11b900) goto LAB_0010656a;
  iVar9 = strncmp(pcVar22,"TERM ",5);
  if ((iVar9 == 0) && (iVar9 = fnmatch(pcVar22 + 5,pcVar25,0), iVar9 == 0)) goto LAB_00106215;
  sVar17 = strlen(pcVar22);
  pcVar22 = pcVar22 + sVar17 + 1;
  goto LAB_001062c5;
LAB_0010656a:
  DAT_00128332 = 0;
  goto LAB_00106215;
code_r0x00105a64:
  local_8c = 3;
  goto LAB_00104e16;
LAB_00105eab:
  local_42 = 0;
  local_44 = cVar4;
  local_43 = cVar1;
  uVar14 = FUN_00118c20(&local_44);
  uVar15 = dcgettext(0,"unrecognized prefix: %s",5);
  error(0,0,uVar15,uVar14);
  pcVar25 = local_60;
LAB_00105eeb:
  local_60 = pcVar25;
  uVar14 = dcgettext(0,"unparsable value for LS_COLORS environment variable",5);
  error(0,0,uVar14);
  free(DAT_00128320);
  psVar18 = DAT_00128328;
  while (psVar18 != (size_t *)0x0) {
    psVar21 = (size_t *)psVar18[5];
    free(psVar18);
    psVar18 = psVar21;
  }
  DAT_00128332 = 0;
LAB_001063ca:
  if ((DAT_001270d0 == 6) && (iVar9 = strncmp(PTR_DAT_001270d8,"target",6), iVar9 == 0)) {
    DAT_001283b0 = '\x01';
  }
LAB_00106215:
  if (DAT_00128332 == 0) {
LAB_00104f82:
    if (DAT_00128314 != 0) goto LAB_00104f8b;
  }
  else {
    DAT_001282e0 = (undefined *)0x0;
    if ((((DAT_00128314 != 0) || (cVar4 = FUN_001068c0(0xd), cVar4 != '\0')) ||
        ((cVar4 = FUN_001068c0(0xe), cVar4 != '\0' && (DAT_001283b0 != '\0')))) ||
       ((cVar4 = FUN_001068c0(0xc), cVar4 != '\0' && (DAT_0012835c == 0)))) {
LAB_00104f8b:
      DAT_0012831d = 1;
    }
  }
  lVar26 = (long)iVar8;
  if ((((DAT_00128318 == 0) && (DAT_00128318 = 1, DAT_00128315 == '\0')) && (DAT_00128334 != 3)) &&
     (DAT_0012835c != 0)) {
    DAT_00128318 = 3;
  }
  if (DAT_00128316 != 0) {
    DAT_001283e8 = FUN_00111e30(0x1e,0,FUN_00106880,FUN_00106890,free);
    if (DAT_001283e8 == 0) {
                    // WARNING: Subroutine does not return
      FUN_0011a1c0();
    }
    FUN_001161c0(&DAT_00128100,0,0,malloc,free);
  }
  pcVar25 = getenv("TZ");
  DAT_001282c8 = FUN_00119090(pcVar25);
  DAT_001282c2 = DAT_0012834c | DAT_00128331 | DAT_00128389 | DAT_0012835c == 0 |
                 (DAT_00128350 - 3U & 0xfffffffd) == 0;
  DAT_001282c1 = (DAT_00128389 | DAT_00128316 | DAT_00128332 | DAT_00128314 | DAT_00128334 != 0) &
                 (DAT_001282c2 ^ 1);
  uVar5 = 0;
  if (DAT_00128332 != 0) {
    uVar5 = FUN_001068c0(0x15);
  }
  DAT_001282c0 = uVar5;
  if (DAT_00128338 != 0) {
    FUN_001161c0(&DAT_001281c0,0,0,malloc,free);
    FUN_001161c0(&DAT_00128160,0,0,malloc,free);
  }
  if (DAT_00128331 != 0) {
    uVar16 = 0;
    do {
      while (iVar9 = (int)uVar16, uVar16 < 0x5b) {
        if (((uVar16 < 0x41) && (9 < iVar9 - 0x30U)) && (1 < iVar9 - 0x2dU)) {
          uVar16 = uVar16 + 1;
        }
        else {
          (&DAT_00128000)[uVar16] = (&DAT_00128000)[uVar16] | 1;
          uVar16 = uVar16 + 1;
        }
      }
      bVar28 = true;
      if ((0x19 < iVar9 - 0x61U) && (uVar16 != 0x7e)) {
        bVar28 = iVar9 == 0x5f;
      }
      (&DAT_00128000)[uVar16] = (&DAT_00128000)[uVar16] | bVar28;
      uVar16 = uVar16 + 1;
    } while (uVar16 != 0x100);
    DAT_001283a8 = (undefined *)FUN_0011a360();
    if (DAT_001283a8 == (undefined *)0x0) {
      DAT_001283a8 = &DAT_0011cf4c;
    }
  }
  DAT_001283d8 = 100;
  DAT_001283e0 = FUN_00119d00(0x5140);
  iVar8 = param_1 - iVar8;
  DAT_001283d0 = 0;
  FUN_001087c0();
  if (iVar8 < 1) {
    if (DAT_00128315 == '\0') {
      FUN_001071c0(&DAT_0011d277,0,1);
    }
    else {
      FUN_0010ca80(&DAT_0011d277,3,1,0);
    }
    if (DAT_001283d0 != 0) goto LAB_00105fba;
LAB_00105a9f:
    if (DAT_001283a0 == (long *)0x0) goto LAB_00105194;
    __ptr = DAT_001283a0;
    if (DAT_001283a0[3] == 0) {
      DAT_001282d8 = 0;
    }
  }
  else {
    do {
      lVar11 = lVar26 * 2;
      lVar26 = lVar26 + 1;
      FUN_0010ca80(*(undefined8 *)(&param_2->_flags + lVar11),0,1,0);
    } while ((int)lVar26 < (int)param_1);
    if (DAT_001283d0 == 0) {
LAB_00105129:
      if (1 < iVar8) goto LAB_00105188;
      goto LAB_00105a9f;
    }
LAB_00105fba:
    FUN_00108e30();
    if (DAT_00128315 == '\0') {
      FUN_00109530(0,1);
    }
    if (DAT_001283d0 == 0) goto LAB_00105129;
    FUN_0010c650();
    if (DAT_001283a0 == (long *)0x0) goto LAB_00105194;
    DAT_00128218 = DAT_00128218 + 1;
    pcVar25 = stdout->_IO_write_ptr;
    if (stdout->_IO_write_end <= pcVar25) {
      __overflow(stdout,10);
      goto LAB_00105188;
    }
    stdout->_IO_write_ptr = pcVar25 + 1;
    *pcVar25 = '\n';
    __ptr = DAT_001283a0;
  }
  do {
    DAT_001283a0 = (long *)__ptr[3];
    if ((DAT_001283e8 == 0) || (*__ptr != 0)) {
      FUN_0010dc80(*__ptr,__ptr[1],(char)__ptr[2]);
      free((void *)*__ptr);
      free((void *)__ptr[1]);
      free(__ptr);
      DAT_001282d8 = 1;
    }
    else {
      if ((ulong)(DAT_00128118 - _DAT_00128110) < 0x10) {
                    // WARNING: Subroutine does not return
        __assert_fail("dev_ino_size <= __extension__ ({ struct obstack const *__o = (&dev_ino_obstack); (size_t) (__o->next_free - __o->object_base); })"
                      ,"src/ls.c",0x442,"dev_ino_pop");
      }
      local_58 = *(undefined **)(DAT_00128118 + -0x10);
      uStack_50 = *(undefined8 *)(DAT_00128118 + -8);
      DAT_00128118 = DAT_00128118 + -0x10;
      pvVar13 = (void *)FUN_00112530(DAT_001283e8,&local_58);
      if (pvVar13 == (void *)0x0) {
                    // WARNING: Subroutine does not return
        __assert_fail("found","src/ls.c",0x73d,"main");
      }
      free(pvVar13);
      free((void *)*__ptr);
      free((void *)__ptr[1]);
      free(__ptr);
    }
LAB_00105188:
    __ptr = DAT_001283a0;
  } while (DAT_001283a0 != (long *)0x0);
LAB_00105194:
  if ((DAT_00128332 != 0) && (DAT_00128330 != '\0')) {
    if ((DAT_00127060 != 2) ||
       (((*(short *)PTR_DAT_00127068 != 0x5b1b || (DAT_00127070 != 1)) || (*PTR_DAT_00127078 != 'm')
        ))) {
      FUN_00107990(&DAT_00127060);
      FUN_00107990(&DAT_00127070);
    }
    fflush_unlocked(stdout);
    FUN_001077e0(0);
    for (iVar8 = DAT_00128234; iVar8 != 0; iVar8 = iVar8 + -1) {
      raise(0x13);
    }
    if (DAT_00128238 != 0) {
      raise(DAT_00128238);
    }
  }
  if (DAT_00128338 != 0) {
    FUN_00107670("//DIRED//",&DAT_001281c0);
    FUN_00107670("//SUBDIRED//",&DAT_00128160);
    uVar10 = FUN_00118140(DAT_001282f0);
    __printf_chk(1,"//DIRED-OPTIONS// --quoting-style=%s\n",(&PTR_s_literal_001269a0)[uVar10]);
  }
  lVar26 = DAT_001283e8;
  if (DAT_001283e8 != 0) {
    lVar11 = FUN_00111900(DAT_001283e8);
    if (lVar11 != 0) {
                    // WARNING: Subroutine does not return
      __assert_fail("hash_get_n_entries (active_dir_set) == 0","src/ls.c",0x771,"main");
    }
    FUN_00111ff0(lVar26);
  }
  if (local_40 != *(long *)(in_FS_OFFSET + 0x28)) {
                    // WARNING: Subroutine does not return
    __stack_chk_fail();
  }
  return DAT_00128230;
}
