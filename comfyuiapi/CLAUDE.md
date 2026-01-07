# 项目核心定位

功能：基于 ComfyUI 工作流，为不同设备分辨率批量生成 AI 壁纸。
技术栈：Python, ComfyUI API (comfy-api-simplified), uv (包管理), Pillow。
核心理念：模块化工作流，将 ComfyUI 的 JSON 配置硬编码在 Python 模块中作为字符串，实现“代码即工作流”。

# 代码规范

* 使用logging处理日志。
* 每种workflow一个py文件，JSON格式的workflow以字符串形式保存其中。提供一个或多个函数，供外部调用。
* 测试和构建过程使用Makefile控制
* 环境使用uv管理
* 强制执行 Type Annotations。
* 公有函数必须包含详尽的 Docstrings (Args, Returns, Raises)。
* 函数的McCabe复杂度尽量不要超过10。
* 使用 ruff 进行静态检查，配置 McCabe 复杂度阈值为 10。
* 编码规范遵循PEP-8。
* 每次修改源码后，如果需要，更新README.md。

# 文件和用途

* envs: 忽略，本地变量
* gen-images.py: 批量生成图片。
* libs.py: 公共库。
* Makefile: 管理项目常用指令。目前主要是测试指令。
* outpaint.py: 扩图workflow。
* *.csv: 都是分辨率定义文件。
* README.md: 使用文档，每次代码更新都要跟随更新。
* test\_theme.txt/test\_variations.txt: 测试用的theme和variations。
* upscale.py: 超分workflow。这里只用模型超分，不重绘，也不调整分辨率，只负责直接扩大4倍。
* usdu.py: 超分workflow。重绘，调整分辨率。
* wf.py: workflow的入口脚本。从命令行读取多种参数，调用对应workflow执行。
* zit.py: z-image-turbo图片生成workflow。

## gen-images的核心逻辑

合成逻辑：
每次合成有4个关键参数，主题，变奏，随机数，分辨率。合成逻辑如下：
1. 命令行参数theme，读取主题。
2. 命令行参数variations，读取变奏。
3. 每行一个变奏，和主题混合，生成提示词。
4. 每个提示词，给一个序列ID，作为文件编号。对于同一个序列ID，提示词一样。
5. 每个提示词，可以生成多个批次。每个批次，给一个批次ID。同时生成一个随机数。每一个序列ID的每一个批次ID，随机数一样。
6. 如果指定了分辨率规范文件，读取里面所有分辨率。
7. 目标文件名为{文件编号}_{批次编号}_{device_id}.png，如果没有指定分辨率规范文件，{文件编号}_{批次编号}.png。

分辨率细节：
* 由于所有模型都有分辨率极限，因此在总像素（width*height）超过特定值（估计在1024\*1024到2048\*2048之间）之后，需要结合使用超分过程（upscale或USDU）。否则容易出现图片扭曲，断肢等现象。
* 由于ComfyUI的特性，频繁切换模型性能极低。因此超分需要在zit模型全部跑完之后。而且如果有多种超分过程，每种的所有执行需要连续。
* 断点续算：zit过程跑的时候总有中断的情况。所以万一中断了，那么跑出来的中间文件，就不必再跑了。

具体如下：
1. 拿到一张图，判断总像素是否超过了1.5\*1024\*1024。我们称之为临界尺寸。
2. 如果没超过，直接调用zit.zit生成。
3. 如果超过了，需要将图等比例缩放到临界尺寸以下。基本就是width*height=1.5\*1024\*1024。
4. 接着看放大倍率。我们约定目标width/中间width为放大倍率factor。如果factor<=2，那么使用upscale过程。如果factor>2，使用usdu过程。
5. 根据算出来的width和height，调用zit.zit，生成中间临时文件。
6. 全部图片/中间图片生成完之后，判断是否有临时文件需要放大。
7. 如果有，调用对应的超分workflow，生成目标图片。
8. 使用PIL，读取目标图片分辨率。如果不严格等于要求的分辨率，直接用PIL进行小幅缩放。
9. 清理所有临时文件。

同时，upscale超分过程，应当有args flag控制。分为以下几种状态：
1. 智能控制。逻辑如上。（默认值）
2. 锁定使用upscale。
3. 锁定使用usdu。
4. 锁定不使用超分，直接生成目标图片。

# workflow规范

工作流嵌入：禁止使用外部 JSON 文件，必须将工作流 JSON 以 WORKFLOW_STR 常量形式写在 Python 模块内。
