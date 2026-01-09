# 项目核心定位

功能：基于 ComfyUI 工作流，为不同设备分辨率批量生成 AI 壁纸。
技术栈：Python, ComfyUI API (comfy-api-simplified), uv (包管理), Pillow。
核心理念：模块化工作流，将 ComfyUI 的 JSON 配置硬编码在 Python 模块中作为字符串，实现“代码即工作流”。

# 代码规范

* 禁止自动git提交
* 编码规范遵循PEP-8。
* 强制执行 Type Annotations。
* 公有函数必须包含详尽的 Docstrings (Args, Returns, Raises)。
* 环境使用uv管理
* 函数的McCabe复杂度尽量不要超过10。
* 使用 ruff 进行静态检查，配置 McCabe 复杂度阈值为 10。
* 测试和构建过程使用Makefile控制
* 每次修改源码后，如果需要，更新README.md。
* 删除无用代码，删除头部无效import
* 使用logging处理日志。
* 每种workflow一个py文件，JSON格式的workflow以字符串形式保存其中。提供一个或多个函数，供外部调用。
* 断点续算：跑的时候总有中断的情况。所以万一中断了，那么跑出来的中间文件，就不必再跑了。所以各种文件生成中，如果目标已经存在，跳过。

# workflow规范

工作流嵌入：禁止使用外部 JSON 文件，必须将工作流 JSON 以 WORKFLOW_STR 常量形式写在 Python 模块内。

# 分辨率和裁切规范

* 对于所有图片，下采样可以认为是低损失的。超分和裁切不得已而为之。
* 所有模型都有分辨率极限，在总像素（width*height）超过特定值（估计在1024\*1024到2048\*2048之间，取1.5\*1024\*1024，称为临界尺寸）之后，容易出现图片扭曲，断肢等现象。

裁切采用四桶方案。全球所有设备，都规约到这四个分辨率桶上，根据纵横比（ar）选择。

* 896 x 1920: 适配ar<0.6的情况
* 1088 x 1472: 适配0.6<=ar<1.15的情况
* 1536 x 1024: 适配1.15<=ar<1.65的情况
* 1728 x 960: 适配ar>=1.65的情况

# 文件和用途

* envs: 忽略，本地变量
* gen_images.py: 批量生成图片。
* libs: 目录，公共库。
  * aurasr.py: 超分workflow。重绘。
  * outpaint.py: 扩图workflow。
  * upscale.py: 超分workflow。这里只用模型超分，不重绘，也不调整分辨率，只负责直接扩大4倍。
  * usdu.py: 超分workflow。重绘，调整分辨率。
  * zit.py: z-image-turbo图片生成workflow。
  * *.py: 公共库。
* Makefile: 管理项目常用指令。目前主要是测试指令。
* *.csv: 都是分辨率定义文件。
* README.md: 使用文档，每次代码更新都要跟随更新。
* upscale.py: 批量超分放大。
* test\_theme.txt/test\_variations.txt: 测试用的theme和variations。
* wf.py: workflow的入口脚本。从命令行读取多种参数，调用对应workflow执行。

## wf细节

* 支持五种workflows: zit, usdu, upscale, aurasr, outpaint
* 五种workflows所需的参数，都暴露给命令行。

## upscale，USDU和AuraSR的说明

三者均是放大，但是原理和用途各自不同。

* upscale.py: GAN放大器，会锐化图像。有三个选择，RealESRGAN\_x2.pth, RealESRGAN\_x4.pth, 4x-UltraSharp.pth。分别放大图像两倍，四倍，四倍。
* usdu.py: 在GAN放大器后面，接一个重绘器。重绘器会修复被锐化后变形的线条，和缺失的细节。重绘器会将图片切分成1024x1024的小块，分别重绘。所以比较费时。
* aurasr.py: 在GAN放大器后面，接一个图像空间重绘器。速度更快。

## gen_images的核心逻辑

gen\_images只出四张母图，对应上面的四个分辨率。其他分辨率的图，都从这4张母图上超分放大，适配裁切。gen\_images的合成逻辑如下：

每次合成有4个关键参数，主题，变奏，随机数，分辨率。合成逻辑如下：

1. 命令行参数theme，读取主题文件。
2. 命令行参数variations，读取变奏文件。每行一个变奏，和主题混合，生成提示词。
3. 每个提示词，给一个序列ID，作为文件编号。对于同一个序列ID，提示词一样。
4. 每个提示词，可以生成多个批次。每个批次，给一个批次ID。同时生成一个随机数。每一个序列ID的每一个批次ID，随机数一样。
5. 对于上述主题，变奏，提示词，序列ID，批次ID，随机数。每种组合配合四张母图的分辨率，生成四张母图/原图。母图文件名约定为`{文件编号}_{批次编号}_base_{width}x{height}.png`。

流程：
1. 第一轮计算，使用zit生成母图/原图。
2. 浏览图，如果不满意，删了重新生成。

四个标准分辨率应有开关可以控制，可以选择只生成四个分辨率桶里面特定几个。默认四个全生成。

## upscale的核心逻辑

* 放大使用超分过程。目前有三个可选，upscale，USDU，aurasr。
* upscale过程速度快，效果好，但是只能放大两倍。因此最大像素数只有4\*1.5\*1024\*1024=6Mpx。
* USDU运算速度慢，且可能出现扭曲。但是最大可以支持24Mpx的图片。
* aurasr运算速度快，效果好，只能放大4倍。
* 因此需要智能选择放大过程。我们约定目标width/原图width和目标height/原图height中的最大值, 为放大倍率factor。如果factor<=2，那么使用upscale过程+RealESRGAN\_x2.pth。如果factor>2，使用aurasr过程。放大后的文件，称为放大图。
* 由于母图只有4种，所以放大图最多只有8种。对于给定分辨率表，可以很容易的算出这8张放大图是否激活（activate）。没有分辨率需要的放大图称为未激活，就不用生成了。
* 对于任意一种分辨率组合，根据放大图，算出目标尺寸。
* 由于ComfyUI的特性，频繁切换模型性能极低。因此zit，upscale超分和aurasr超分需要按顺序跑。

upscale流程。
1. 一定需要指定设备分辨率清单。根据清单，计算出激活的放大图有哪些，生成任务清单。
2. 恢复gen\_images的任务列表，计算“有多少图片需要放大”。方法是在目标目录里面找有多少个符合原图规范的文件，从中算出有多少个文件编号和批次编号的组合。结合任务清单，就能算出需要多少次运算。
3. 计算所有upscale+RealESRGAN\_x2.pth超分。文件名约定为`{文件编号}_{批次编号}_upscale2x_{width}x{height}.png`。
4. 计算所有aurasr超分。文件名约定为`{文件编号}_{批次编号}_aurasr_{width}x{height}.png`。
5. 根据目标设备设备尺寸，找到最合适的放大图。（先根据ar算出最合适原图，再根据factor算出放大图）
6. 放大图尺寸一定大于目标分辨率，但是长宽比可能发生变形。使用PIL的ImageOps.fit来适应，具体算法是。保持放大图长宽比固定，将其缩放至“能够覆盖目标尺寸”的最小尺寸。此时一边刚好和目标对齐，而另一边会超出目标。将超出部分从两边裁切(crop)掉即可。
7. 如果目标图尺寸甚至超过了最大放大图尺寸，例如目标尺寸大于24Mpx。那么在ImageOps.fit的时候强行放大。
8. 将目标文件转换为jpg格式。文件约定为`{文件编号}_{批次编号}_{device_id}.png`。

同时，超分过程应当有args flag控制。分为以下几种状态：
1. 智能控制，逻辑如上。（默认值，等于智能使用upscale2x或aurasr）
2. 锁定使用upscale2x。等于upscale+RealESRGAN\_x2.pth。
3. 锁定使用upscale4x。等于upscale+RealESRGAN\_x4.pth。
5. 锁定使用aurasr。
6. 锁定使用usdu。
7. 锁定不使用超分，直接生成目标图片。

不清理原图和放大图。
