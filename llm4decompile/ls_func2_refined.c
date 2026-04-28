/* [LLM4Decompile REFINED] */
int FUN_00119130(struct FUN_00119090 *VAR_0, struct FUN_00119090 *VAR_1)
{
    char *VAR_2 = VAR_1->VAR_00000000;
    char *VAR_3 = VAR_1->VAR_00000000 + 12;
    char *VAR_4 = VAR_0->VAR_00000000;
    char *VAR_5 = VAR_0->VAR_00000000 + 12;

    if (VAR_2 == NULL || VAR_2 < VAR_1 || VAR_2 >= VAR_3)
        return 1;

    if (*VAR_2 == '\0')
        VAR_4 = "";
    else
    {
        while (strcmp(VAR_4, VAR_2))
        {
            if (*VAR_4 == '\0')
            {
                if (VAR_4 == VAR_0->VAR_00000000 && VAR_0->VAR_00000001 == '\0')
                {
                    size_t VAR_6 = strlen(VAR_2) + 1;
                    if (VAR_6 < (size_t)((size_t)(&VAR_1->VAR_00000000) - (size_t)(VAR_4)))
                    {
                        memcpy(VAR_4, VAR_2, VAR_6);
                        VAR_4[VAR_6] = '\0';
                    }
                    else
                    {
                        VAR_0 = FUN_00119090(VAR_2);
                        if (VAR_0 == NULL)
                            return 0;
                        VAR_0->VAR_00000001 = '\0';
                        VAR_4 = VAR_0->VAR_00000000;
                    }
                    break;
                }
                VAR_4 += strlen(VAR_4) + 1;
                if (*VAR_4 == '\0')
                {
                    struct FUN_00119090 *VAR_7 = VAR_0->VAR_00000001;
                    if (VAR_7 == NULL)
                        break;
                    VAR_0 = VAR_7;
                    VAR_4 = VAR_0->VAR_00000000;
                }
            }
            else
                VAR_4 += strlen(VAR_4) + 1;
        }
    }

    VAR_1->VAR_00000000 = VAR_4;
    return 1;
}
