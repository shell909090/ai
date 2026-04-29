# 简介

[LLM4Decompile](https://github.com/albertan017/LLM4Decompile)是一个使用AI来实现反编译的项目。其包含两个模式。v1.5通过反向的汇编代码工作，v2通过ghidra伪代码工作。后者效果好于前者。本文档描述了实测该项目的结果。

# ghidra反编译

[ghidra](https://github.com/nationalsecurityagency/ghidra)是一个NSA资助的项目，用于反向二进制代码。其安装过程并不复杂。先装一套OpenJDK17以上的Java，然后下载项目里的发行包就行。操作也很简单，import目标代码，然后export C/C++文件。

# LLM4Decompile

[LLM4Decompile](https://github.com/albertan017/LLM4Decompile)项目也不复杂。git clone下来，然后uv init，uv pip install -r requirements.txt。期间会安装vllm和torch。最终推理其实是在vllm上完成的。ollama.com上有[llm4decompile-22b-v2](https://ollama.com/MHKetbi/llm4decompile-22b-v2)的镜像，直接提交原始数据，拿到结果。但是我没测试那个。话说ollama上有不少有意思的封装，开始逐步从专用大语言模型推理工具，变成一个通用推理平台。

运行的时候会从huggingface上下载模型，请确保执行时有网。

LLM4Decompile是为了处理单个函数优化的。上面ghidra的输出，需要被裁切为多个函数，每个函数单独反编译。反编译并不能自动推理出符号名字，而是会带着原始符号。

LLM4Decompile自身是通过"反向执行率"来评估反汇编效果的，即产生的输出能否通过原始代码的单元测试。这是一种颇为聪明的测试方法，不过一般不符合我们的预期——其实我对反向代码是否具备可执行能力并不关心，更关心的是是否能从反向代码中提炼出知识来。

# llm4decompile-6.7b-v2

llm4decompile有不同级别的模型，我在测试中使用[llm4decompile-6.7b-v2](https://huggingface.co/LLM4Binary/llm4decompile-6.7b-v2/tree/main)模型。根据llm4decompile的报告，这个模型在O0级别有74%的通过率，在O3级别只有42%。但是模型的输出效果我颇为满意。

在使用中，主要问题有两点。一个是尺寸问题。由于模型其实还是一个transformer架构的“翻译”程序，因此输入-输出其实是要匹配到context window里的。而模型的开销颇大，目前我的显卡（22G显存）只能跑1.2k尺寸的函数。再大就会爆显存了。第二个是性能问题。一个函数的反编译处理时间奇长无比。这两点决定了，llm4decompile-6.7b-v2在真实业务场景里，是没有太大实用性的。不过请注意到，这是一个2024年的项目。按照目前AI的发展速度，预期几年内商用级别的模型能够顺利反向相当尺寸的单个函数，且代价可以接受。

# claude opus优化

通过claude code+opus阅读llm4decompile的输出，优化结果。价格颇贵，但是对某些关键段落有效果。特别是，opus经常能指出llm4decompile的输出在哪里有问题。这一方面说明了llm4decompile目前还不稳定，另一方面则是说明了opus4.7的强大。我甚至怀疑，它其实是能直接反向ghidra的输出的。效果未必比处理llm4decompile差。我甚至跑了一个测试，来分析opus直接分析ghidra输出。

注意，测试例子是反向的ls程序，其自身是开源代码工具。因此claude已经向模型投喂过其原始代码。ls依赖的底层是glibc，更是如此。因此反向效果并不能很好的表征一般实践结果。opus甚至能直接告诉我，这是来自哪个源码文件。这是彻底把我整不会了。但是要获得有效输出，需要反向claude绝对未曾投喂过的代码，而且也不能来自AI工具的输出。这基本就是要我自己去写个C项目，或者直接违反版权法。实在懒得写一个项目来评估了。

# 结论

按照目前AI辅助反汇编的效果，在不计成本的前提下，基本可以有效的反向大部分没有经过特别处理的函数。预估3-5年内，未经特殊处理的C代码编译结果将不能有效保护原始代码。

当然，这里要多说一句。依靠编译屏障和二进制复杂性来保护项目价值本身就是不可靠的，AI只是把反向成本降到了一个相当的程度而已。

# 引用

| 模型 | func1 | func2 | func3 | func4 | func5 |
|------|-------|-------|-------|-------|-------|
| ghidra | [ls_func1.c](ls_func1.c) | [ls_func2.c](ls_func2.c) | [ls_func3.c](ls_func3.c) | [ls_func4.c](ls_func4.c) | [ls_func5.c](ls_func5.c) |
| llm4decompile | [ls_func1_refined.c](ls_func1_refined.c) | [ls_func2_refined.c](ls_func2_refined.c) | - | - | [ls_func5_refined.c](ls_func5_refined.c) |
| opus4.7 | [ls_func1_opus47.c](ls_func1_opus47.c) | [ls_func2_opus47.c](ls_func2_opus47.c) | [ls_func3_opus47.c](ls_func3_opus47.c) | - | - |
| sonnet4.7 | - | - | - | [ls_func4_sonnet.c](ls_func4_sonnet.c) | - |
| deepseek-v4-pro | [ls_func1_ds4p.c](ls_func1_ds4p.c) | [ls_func2_ds4p.c](ls_func2_ds4p.c) | [ls_func3_ds4p.c](ls_func3_ds4p.c) | [ls_func5_ds4p.c](ls_func5_ds4p.c) | [ls_func5_ds4p.c](ls_func5_ds4p.c) |
| minimax m2.7 | [ls_func1_m27.c](ls_func1_m27.c) | [ls_func2_m27.c](ls_func2_m27.c) | [ls_func3_m27.c](ls_func3_m27.c) | [ls_func4_m27.c](ls_func4_m27.c) | [ls_func5_m27.c](ls_func5_m27.c) |
| kimi k2.6 | - | - | - | - | - |

* 注意：func3和func4是直接反向ghidra输出得到的结果，未经llm4decompile处理。llm4decompile在跑这两个集合的时候，显存OOM炸了。
* ls.c: [ghidra输出](ls.c.gz)。
