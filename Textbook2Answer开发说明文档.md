# Textbook2Answer (教辅级参考答案生成系统) \- 开发文档

## 1\. 项目概述

本项目旨在开发一个全自动化的 Agentic Workflow 系统，将大学理工科教材（PDF格式）自动转化为“教辅级”的高质量 LaTeX 参考答案文档。

系统采用 Human-in-the-loop 的设计，由用户输入“章节-页码”映射，系统完成从 PDF 图像切片、VLM 题目提取、大模型多模态推理求解，到 Jinja2 组装 LaTeX 源码的全流程。

目标用户：大学生、科研人员。

核心价值：不仅提供答案，还提供详细解析、知识点总结、一题多解和高阶拓展（教辅级体验）。

## 2\. 目录与文件结构说明

当前工作目录为 Textbook2Answer/，初始状态下仅包含 api\_config.json。

期望 Cursor 最终构建出如下结构：

Textbook2Answer/  
├── api\_config.json          \# \[已存在\] 存储所有大模型的 API 密钥和 Base URL  
├── input/  
│   ├── textbook.pdf         \# 用户放入的教材源文件  
│   └── chapter\_config.json  \# 用户定义：章节与PDF物理页码的映射  
├── output/                  \# 运行结果输出目录  
│   ├── images/              \# 存放 PDF 切割出的页面图片  
│   ├── extracted\_tasks.json \# VLM 提取出的习题结构化数据  
│   ├── solved\_answers.json  \# 推理模型解答后的数据  
│   └── final\_solution.tex   \# 最终生成的 LaTeX 源码文件  
├── src/  
│   ├── api\_client.py        \# 统一的 LLM/VLM API 调用封装 (当前优先使用 Gemini)  
│   ├── pdf\_processor.py     \# 处理 PDF 转图片  
│   ├── vlm\_extractor.py     \# 负责调用视觉模型提取习题  
│   ├── reasoning\_solver.py  \# 负责调用推理模型解答题目  
│   └── latex\_builder.py     \# 负责读取 JSON 和模板，生成最终 .tex 文件  
├── templates/  
│   └── main\_template.tex    \# LaTeX Jinja2 模板文件  
└── main.py                  \# 主程序入口

## 3\. 核心数据结构 (Data Schemas)

为了确保各模块解耦且 LLM 输出稳定，系统依赖以下三种核心 JSON 结构。

### 3.1 输入配置 (input/chapter\_config.json)

由用户手动编写，规避复杂的目录识别难题。

{  
  "book\_title": "数学物理方法",  
  "author\_model": "deepseek-v3-2-251201 / gemini-3-pro-preview",  
  "chapters": \[  
    {  
      "chapter\_name": "第一章 复变函数",  
      "pages": \[15, 16, 17\]   
    }  
  \]  
}

### 3.2 提取出的习题集 (output/extracted\_tasks.json)

由 vlm\_extractor.py 生成，必须严格遵守此格式。

\[  
  {  
    "chapter\_name": "第一章 复变函数",  
    "question\_id": "1-1",  
    "content": "求下列复数的模和辐角...",  
    "has\_image": false,  
    "page\_num": 15,  
    "image\_path": "output/images/page\_15.png"  
  },  
  {  
    "chapter\_name": "第一章 复变函数",  
    "question\_id": "1-2",  
    "content": "如图所示的积分路径...",  
    "has\_image": true,  
    "page\_num": 16,  
    "image\_path": "output/images/page\_16.png"  
  }  
\]

(注：has\_image 是核心字段。如果是纯文字题且图片仅为装饰，设为 false；如果图片包含电路、几何、图表等解题必需信息，设为 true。)

### 3.3 最终解答集 (output/solved\_answers.json)

由 reasoning\_solver.py 生成，体现“教辅级”质量。

\[  
  {  
    "question\_id": "1-1",  
    "solution\_process": "解答过程的 LaTeX 源码...",  
    "knowledge\_points": "本题考查复数的基本概念...",  
    "alternative\_methods": "解法二：利用指数形式化简...",  
    "extensions": "引理：欧拉公式在复平面旋转中的几何意义..."  
  }  
\]

## 4\. 各核心模块开发规范与 Prompt 设定

### 4.1 api\_client.py (模型通信)

* 要求：读取 api\_config.json，实现一个通用的请求类。当前优先支持 gemini 配置节点（使用 gemini-3-pro-preview 或可用模型）。  
* 注意：必须支持多模态（传入 base64 图片或图片路径 \+ 文本）。

### 4.2 vlm\_extractor.py (视觉提取模块)

* 输入：chapter\_config.json \+ output/images/ 下的图片。  
* System Prompt 核心要求：  
  1. “你是一个专业的教材解析专家。你的任务是从教材页面图片中提取所有的课后习题。”  
  2. “必须输出纯净的 JSON 数组，包含 question\_id, content, has\_image。”  
  3. “如果题目旁边的配图是解题不可或缺的（如电路图、几何图形、数据图表），将 has\_image 设为 true，否则设为 false。”

### 4.3 reasoning\_solver.py (推理求解模块)

* 工作流：遍历 extracted\_tasks.json，如果 has\_image 为 true，则将题目文本 content 和对应的 image\_path 图片一起发送给大模型；若为 false，则只发送文本。  
* System Prompt 核心要求 (Crucial)：  
  1. 角色：你是一个顶级的大学理科教授，负责编写“教辅级”参考答案。  
  2. 格式限制：严格输出 JSON 格式（包含过程、知识点、多解、拓展）。  
  3. LaTeX 规范 (防冲突)：  
     * 不要使用任何 \\usepackage，不要输出 \\begin{document}。  
     * 命名空间隔离：当你使用 \\label{} 时，必须带有题号前缀。例如解答题 2-1 时，公式标签必须写为 \\label{eq:2-1-1}，避免全局标签冲突。  
  4. 优雅降级 (Graceful Degradation)：  
     * 如果题目内容引用了正文的公式（如“证明式 3.16”），而你没有正文上下文，请基于你的专业知识推断最可能的公式进行解答，并在答案开头加粗注明：“注：本解答假设式 3.16 为 \[你推断的公式\]”。

### 4.4 latex\_builder.py (组装模块)

* 负责将解析结果注入到 main\_template.tex。  
* 防公式编号累加技巧：在 Jinja2 模板的循环中，在生成每道题的 \\subsection\*{题号} 之后，注入以下 LaTeX 代码重置计数器：  
  \\setcounter{equation}{0}  
  \\renewcommand{\\theequation}{题号-\\arabic{equation}}

  (这样公式编号会自动变成 (1-1-1), (1-1-2) 的精美格式，且不会全局累加。)

## 5\. LaTeX 模板要求 (templates/main\_template.tex)

系统使用 Jinja2 渲染模板。在用户提供的基础模板上，必须添加 tcolorbox 或 mdframed 宏包，用于美化“教辅级”字段。

核心结构示例：

% ... 前置导言区 (使用用户提供的配置) ...  
\\usepackage{tcolorbox} % 新增：用于精美排版教辅内容

\\begin{document}  
\\maketitle  
\\tableofcontents  
\\newpage

% Jinja2 循环开始  
% for chapter in chapters:  
\\section{ {{ chapter.chapter\_name }} }

  % for task in chapter.tasks:  
  \\subsection\*{ {{ task.question\_id }} }  
  \\setcounter{equation}{0}  
  \\renewcommand{\\theequation}{ {{ task.question\_id }}-\\arabic{equation} }  
    
  \\textbf{【题目】} {{ task.content }}  
    
  \\textbf{【解答】}  
  {{ task.solution\_process }}  
    
  \\begin{tcolorbox}\[colback=blue\!5\!white,colframe=blue\!75\!black,title=知识点总结\]  
  {{ task.knowledge\_points }}  
  \\end{tcolorbox}  
    
  % if task.alternative\_methods:  
  \\begin{tcolorbox}\[colback=green\!5\!white,colframe=green\!75\!black,title=一题多解\]  
  {{ task.alternative\_methods }}  
  \\end{tcolorbox}  
  % endif  
    
  % if task.extensions:  
  \\begin{tcolorbox}\[colback=red\!5\!white,colframe=red\!75\!black,title=高阶拓展与引理\]  
  {{ task.extensions }}  
  \\end{tcolorbox}  
  % endif

  % endfor  
% endfor  
\\end{document}

## 6\. Cursor Vibecoding 执行阶段 (Phases)

请 Cursor 按照以下阶段逐步实现，每完成一个阶段请让我测试确认：

* Phase 1: 环境与 API 测试  
  * 读取 api\_config.json。  
  * 编写 tests/test\_gemini\_api.py，测试基本的文本对话，以及发送一张本地测试图片给 Gemini 进行识别。确保连通性。  
* Phase 2: PDF 切片模块  
  * 实现 pdf\_processor.py，能够读取 input/chapter\_config.json，使用 PyMuPDF (fitz) 将指定的页码渲染为高质量 PNG 图片，并保存到 output/images/。  
* Phase 3: 视觉提取模块 (VLM)  
  * 实现 vlm\_extractor.py，根据 Phase 2 产生的图片，调用 API 生成 extracted\_tasks.json。注意校验输出的 JSON 格式。  
* Phase 4: 推理求解模块  
  * 实现 reasoning\_solver.py。读取提取的 JSON，实现带图片或不带图片的 prompt 分发，生成 solved\_answers.json。  
* Phase 5: LaTeX 渲染与最终集成  
  * 实现 latex\_builder.py，编写 Jinja2 模板。  
  * 编写 main.py 串联所有流程。

## 7.附录：在建立本项目时与AI的聊天记录：
```
有没有这样的项目，可以输出一本教材习题的答案？（比如输入习题对应的页码提取相应的pdf图片，发送给支持视觉模态的模型识别习题并转为json格式，得到json格式的习题集，再发送给推理模型给出每题的答案，latex代码输出到json中，最后用一个脚本将这些答案转为一个整的latex文件，编译pdf，得到答案文档）

Gemini said

你的思路非常清晰，逻辑闭环非常完美！可以说，你已经把这个自动化 Agent 系统的核心架构图给完整地设计出来了。

目前在开源社区（如 GitHub）上，完全按照你这个特定流程串联并封装好的、“开箱即用”的知名单体项目可能并不多，因为大部分现有的项目要么专注于“PDF解析”（只做提取），要么专注于“题目解答”（如拍题搜题 App 的后端）。

但是，基于你提出的蓝图，相关的开源组件已经非常成熟。很多开发者、科研人员或者学生，正是利用大模型时代的工具链，自己用 Python 写几百行代码把这些模块“缝合”起来使用的。

如果你想自己动手把这个项目搭出来，或者寻找相关的开源平替，以下是你这个蓝图的技术拆解与现有工具推荐：

🛠️ 核心步骤与推荐工具栈

1\. 输入页码，提取 PDF 为图片

成熟方案：PyMuPDF (即 fitz 库) 或 pdf2image。

实现逻辑：几行 Python 代码就可以根据传入的页码列表（如 pages=\[10, 11, 15\]），将指定的 PDF 页面渲染成高分辨率的 PNG 或 JPEG 图片。

2\. 视觉模态模型（VLM）识别习题并转为 JSON

难点：教材通常包含复杂的数学公式、电路图或化学结构式。

推荐大模型：

Gemini 1.5 Pro：在长文本和多模态视觉解析（尤其是理解复杂的图文混排）上表现极为出色。

GPT-4o 或 Qwen-VL-Max（通义千问视觉版）。

现有强力解析项目（可替代这部分逻辑）：

MinerU (Magic-PDF) 或 Marker：这是目前开源界顶级的 PDF 转 Markdown/LaTeX 工具。如果你不想用 VLM 截图识别，可以直接用它们把带公式的 PDF 完美转成 LaTeX 文本，然后再用正则或轻量级 LLM 切分成 JSON。

3\. 推理模型求解，并将答案以 LaTeX 格式输出到 JSON

推荐大模型：

涉及到复杂的理科习题，推荐使用具有深度思考能力的模型，如 DeepSeek-R1、OpenAI o1 或直接使用 Gemini 1.5 Pro。

提示词工程 (Prompting)：

在 System Prompt 中严格规定输出格式：{"question\_id": 1, "solution\_latex": "解题步骤的 LaTeX 源码"}，并要求模型在输出公式时使用标准的 LaTeX 语法。

4\. 脚本整合 LaTeX 并编译 PDF

成熟方案：

模板渲染：使用 Python 的 Jinja2 库。你可以预先写好一个 LaTeX 的导言区模板（包含 \\usepackage{amsmath} 等宏包），然后用 Jinja2 遍历你的 JSON 结果，把每一题的解答填充进去。

自动编译：使用 Python 的 subprocess 模块调用系统中的 xelatex 或者更现代、免安装庞大环境的 Tectonic 工具，直接一键将 .tex 文件编译为 .pdf。

💡 类似或相关的开源项目参考

虽然没有完全等同于你流程的项目，但你可以参考以下几类开源项目的源码来获得灵感：

Mathpix Markdown It / Mathpix API 示例：Mathpix 是公式识别的行业标杆，他们的 GitHub 仓库里有很多将图文转 LaTeX 的脚手架代码。

LLM Homework Solvers：在 GitHub 搜索 LLM homework solver 或 Math solver agent，会有很多基于 LangChain 或 AutoGen 编写的脚本，其核心逻辑就是“读取题目 \-\> 触发搜索引擎/代码解释器 \-\> 输出答案”。

ChatPaper / ChatPDF 衍生品：这类项目擅长处理 PDF 与大模型的交互，虽然主要是做总结，但其底层的 PDF 处理和 API 调用逻辑与你的需求高度一致。

🚀 下一步

你的这个想法不仅可行，而且在现阶段的 API 能力下，开发成本极低（大概只需 1-2 个 Python 脚本，几百行代码即可搞定），是一个极其优秀的周末实战项目。

需要我帮你把这个流程的 Python 核心骨架代码（包含 PDF 切片、调用视觉模型转 JSON、调用推理模型解答并生成 LaTeX）直接写出来吗？ 你只需要填入自己的 API Key 就可以跑通这个原型！

You said

我原本是打算输入一本pdf的教材，输出一本参考答案，但是一本pdf太大，而且有些pdf是文字，有些是图片，要准确识别出哪些页码是习题会比较困难，所以我打算人工输入pdf页码（不是书本的页码）。

还有一大困难是，不同的教材的习题编号不一样，有些是1,2,3，有些是2-1,2-2,2-3，等等。并且由于目标是一整本答案，需要方便按章节索引。我可能的想法是根据提供的页码自动进行章节划分，但是有些书可能第一章是序言，没有习题，是从第二章开始的。或许可以考虑提取目录，然后让大模型判断这一章的题目属于哪个章节，不过这可能会比较复杂，但最好是最后得到的答案文件中的目录有章节名和题号，这样方便用户索引。无论如何，应该能够得到按照章节顺序划分的json习题集，为了方便用户索引，可以保留教材中的编号，或者将教材中的编号视作题目的一部分，但是后面大模型输出答案的时候应该用subsection\*{}，要取消自动编号，然后将编号填入{}中，要避免模型乱填，这是个困难。

以及，有些题目是带有图片的，如果图片仅仅作为辅助是可以去掉的，但是有些图片中有关键信息，或许可以在视觉模型识别的时候就添加上图片描述，图片描述中需要包含没有歧义的，对解题有帮助的信息。

此外，还有一些教材在习题中会出现正文中的公式引用或者其它位置的题目的引用，如“如式3.16”“类比习题2-18”等，这也是一大困难，还没有比较好的解决方案。

我们还需要设计合适的json格式，还需要设计LaTeX的提取逻辑。我已经设计了一个LaTeX导言，但是我无法确保这些包够用，如何避免AI使用我没有提供的包是一个问题。

以上是我考虑到的一些困难

Defining the Core Problem

I've begun to break down the user's objective, focusing on specific challenges within the process.

Addressing Challenges Systematically

I've formulated a response strategy, validating manual page input and suggesting a strict JSON schema to prevent LLM errors.

Refining Image Processing

I've decided cropping images for direct reasoning or JSON/LaTeX embedding is better than descriptions.

Gemini said

你思考得非常深入！你列出的这些困难，完全切中了\*\*“基于大模型的复杂文档自动化处理”\*\*的核心痛点。从学术界的 PDF 解析（如 Nougat、MinerU）到工业界的 AI 辅助解题，开发者们都在和这些问题做斗争。

你从一个宏观的“概念设计”直接落地到了“工程细节”，这非常棒。针对你提出的这些具体挑战，我结合目前主流的 AI 工程化（Agentic Workflow）方案，提供一些破局的思路和具体的解决方案：

1\. 关于“页码输入”与“章节划分”

你的痛点：全书识别太难，手动输入页码可行，但章节对应和目录解析很复杂。

解决方案：半自动化的人机协同输入 (Human-in-the-loop)

既然你已经决定手动输入页码，不如在输入的源头就把章节信息带上。与其让 AI 去痛苦地猜目录，不如你提供一个简单的映射字典（配置文件），例如：

JSON

{

  "Chapter 2: 牛顿运动定律": \[45, 46, 47\],

  "Chapter 3: 动量守恒": \[78, 79, 81\]

}

你的 Python 脚本读取这个配置，按章节分批次发送图片给视觉模型（VLM）。这样，大模型在提取题目时，就已经明确知道这些题目属于“第2章”，直接写入 JSON 即可，完全避开了复杂的目录解析和章节推断。

2\. 关于“题号乱填”与 \\subsection\*{}

你的痛点：题号格式多变（1, 2-1等），需要取消自动编号，又怕大模型在 LaTeX 中乱填格式。

解决方案：严格的 JSON Schema 输出 \+ 代码模板渲染

绝对不要让大模型去写 \\subsection\*{2-1} 这样的排版代码！ 大模型只负责“提取内容”，排版交给你的 Python 代码（比如 Jinja2 模板）。

你需要强制视觉模型输出这样的结构化 JSON：

JSON

{

  "chapter\_name": "Chapter 2: 牛顿运动定律",

  "questions": \[

    {

      "original\_id": "2-1",

      "content": "质点在力F作用下..."

    },

    {

      "original\_id": "2-2",

      "content": "如图所示..."

    }

  \]

}

拿到这个 JSON 后，你的 Python 脚本自己去拼接字符串：latex\_str \= f"\\\\subsection\*{{{item\['original\_id'\]}}}\\n"。这样模型就绝对没有机会乱填 LaTeX 结构了。

3\. 关于“带有关键信息的图片”

你的痛点：有些图是装饰，有些图包含解题必须的几何/电路信息，如何转化？

解决方案：图文分离与多模态透传

单纯让 VLM 用文字描述复杂电路图或几何图，信息损失率极高。目前的最佳实践是：

VLM 的任务不仅是提取文字，还要“裁剪图片”。你可以提示视觉模型：“如果题目包含解题必需的插图，请给出该插图在原图中的近似边界框（Bounding Box），或者在 JSON 中标记 has\_image: true”。

如果不做边界框识别（有点复杂），更简单粗暴的方法是：把这一页的原始截图，连同提取出的题目文字，一起发送给“推理模型”（如 GPT-4o / Gemini 1.5 Pro）。

Prompt 示例：“这是第45页的截图，你要解答的题目是文字描述中的‘题2-3’。请结合文字和截图中的相关配图，给出详细解答。”

现代的多模态推理模型完全有能力在整页图片中自己找到对应的那张小图来辅助推理。

4\. 关于“正文公式引用（如式3.16）”

你的痛点：题目引用了非习题页的正文内容，导致推理模型缺少上下文。

解决方案：RAG（检索增强生成）或 优雅降级 (Graceful Degradation)

这是一个典型的上下文缺失问题。

低成本方案（优雅降级）：在系统提示词中告诉推理模型：“如果遇到诸如‘如式3.16’的正文引用且你不知道该公式，请基于你的物理/数学专业知识，推断最可能的通用公式进行解答，并在答案开头用粗体注明：注：本解答假设式 3.16 为 \[你推断的公式\]”。

高阶方案（RAG）：把整本 PDF 用简单的文本提取工具（不需要管排版）扫一遍，存入向量数据库（或者直接用全文搜索）。如果推理模型发现自己需要“式3.16”，你的 Agent 可以设计一个“工具调用（Tool Calling）”，让模型去搜索“式3.16”，把正文文本抓过来再继续解题。

5\. 关于“限制 LaTeX 宏包”

你的痛点：无法确保提供的导言区宏包够用，如何防止 AI 使用你没提供的包导致编译报错？

解决方案：System Prompt 强约束 \+ 自动报错修复 (Auto-correction)

强约束：在 System Prompt 中列出“白名单”。

“你生成的 LaTeX 代码只能使用以下宏包：amsmath, amssymb, graphicx。绝对禁止使用 tikz, pgfplots 等绘图包。如果需要画图，请用文字描述。不要输出任何 \\usepackage 命令。”

工程托底（非常重要）：写一个自动编译的循环。

Python 调用 xelatex 编译。

如果捕获到报错（Return code \!= 0），读取 .log 文件中的 Error 信息（比如 Undefined control sequence）。

把 Error 信息自动发回给大模型：“你的 LaTeX 代码编译失败，错误信息是 XXX，请修改你的代码使其只依赖我提供的宏包，并重新输出”。（通常循环 1-2 次就能修好）。

总结你的架构演进

经过你的思考，你的系统架构实际上应该演变成一个 Agentic Pipeline：

输入层：用户提供 PDF 路径 \+ 章节页码配置（JSON/Dict）。

提取层：Python 按照页码将 PDF 转图 \-\> 调用 VLM \-\> 提取出严格格式的 结构化习题 JSON。

解答层：遍历 JSON，将“题目文字 \+ 原页截图”一并交给强推理模型 \-\> 输出解答的 LaTeX 片段。

组装与自愈层：Python 用 Jinja2 模板将解答片段拼接入你写好的 .tex 模板 \-\> 调用系统命令编译 \-\> 如果报错则丢回给大模型修改 \-\> 最终输出 PDF 答案册。

你提到的每一个“困难”，其实都可以通过合理的\*\*工程设计（拆分任务、限制格式、人机协作）\*\*来化解，而不是单单指望大模型一次性完美解决所有问题。这个项目的可行性依然非常高！

You said

OK，我可以在输入的时候就把章节字典输入进去。现在是手动输入，到时候从命令行换成图像界面的时候这里也可以设计得方便一些。

输出这样的结构化json确实是个好主意，那么到时候大模型在回答的时候就不能有subsection了。但是我如果需要提高回答质量，比如我希望编写的不仅是答案，而且是教辅，每道题不仅有解答过程，还可以有基础知识点总结、一题多解多视角（如果有的话）、值得记忆的二级结论（这里还要再斟酌一下，因为二级结论这个词语来源于高中应试，指在“考纲”外的结论定理，但在大学科研语境下没有“考纲”一说，于是也没有“二级结论”，更多像是一些冷门的定理引理，但是和基础知识是有区别的），本项目的受众主要是大学生，因为很多教材没有答案，即使有也没有解析，即使有解析也有很多防御性证明，往往需要一道道地发送给大模型，很麻烦。最后的答案文档中应该有突出的答案（方便对答案）和详细地解析（方便学习巩固知识点）。

关于图片，确实可以在json中加入一个has\_image选项，如果一道题这个选项为false，发送给推理模型的就只有文本，如果为true，那么会将这一整页发送给大模型，这里就需要准确地找到这道题所对应pdf的页码所对应的图片，这就需要一开始发图片得习题集json的阶段就把题目对应的页码存在json中。当然，这里需要加一个检测，如果用户选择的大模型不支持图片上传，就不上传图片，改用之前VLM的图片文字描述，因此VLM的图片文字描述可以作为备用。

关于公式引用，RAG目前还比较复杂，可以先采用低成本方案，后续考虑增加RAG功能。

关于latex，我之前设计了一个模板，写在了合并脚本的一个字符串中：

\\documentclass\[12pt, a4paper\]{ctexart}

% \--- 页面与版式 \---

\\usepackage\[

    a4paper,

    top=1.2cm,      % 上边距

    bottom=2cm,   % 下边距

    left=2.6cm,       % 左边距

    right=2.6cm,      % 右边距

    bindingoffset=0.2cm  % 装订线 0.2cm（自动增加到左边距）

\]{geometry}

\\usepackage{fancyhdr}

\\usepackage{graphicx} % 用于插入图片

\\usepackage{float}    % 用于控制图片浮动位置

\\usepackage{caption}  % 用于设置图表标题

\\usepackage{booktabs} % 用于创建三线表

\\usepackage{threeparttable} % 用于创建带注释的表格

\\usepackage{subcaption}

\\usepackage{cancel}

\\usepackage{mathrsfs}

%\\usepackage{setspace} % 用于设置行间距

%\\onehalfspacing % 设置 1.5 倍行距

\\linespread{1}\\selectfont % 设置单倍行距

\\setlength{\\parindent}{2em} % 首行缩进两厘米

\\ctexset{

    abstractname \= {\\zihao{-4}\\heiti 摘\\quad 要}, % 设置摘要字体：黑体小四号

}

\\title{\\heiti\\zihao{-3} 数学物理方法参考答案生成集} % 自动添加了标题（这里可以考虑改成自动添加，或许可以在一开始的输入那里就让用户输入的json中包含书本名称）

\\author{\\kaishu\\zihao{5} deepseek-v3-2-251201} % 自动添加了作者（这里可以考虑改为自动添加模型名称）

\\date{\\today} %

% \--- 数学公式 \---

\\usepackage{amsmath}

\\usepackage{amssymb}

\\usepackage{amsfonts}

\\usepackage{esint}

\\usepackage{amsthm}  % 提供 proof 环境

% \--- 图表与浮动体 \---

\\usepackage{graphicx}

\\usepackage{subcaption}

\\usepackage{booktabs}

\\usepackage{float}

\\usepackage{minted}


\\usepackage{minted}


% \--- 参考文献 \---

\\usepackage{cite}

% \--- 代码与算法 \---

\\usepackage{listings}

\\usepackage{xcolor}

% \--- 其他 \---

\\usepackage{hyperref}

% \---------- 代码块样式定义 \----------

\\definecolor{codegreen}{rgb}{0,0.6,0}

\\definecolor{codegray}{rgb}{0.5,0.5,0.5}

\\definecolor{codepurple}{rgb}{0.58,0,0.82}

\\definecolor{backcolour}{rgb}{0.97,0.97,0.97}

\\lstdefinestyle{mystyle}{

    backgroundcolor=\\color{backcolour},


    commentstyle=\\color{codegreen},

    keywordstyle=\\color{magenta},

    numberstyle=\\tiny\\color{codegray},

    stringstyle=\\color{codepurple},

    basicstyle=\\ttfamily\\footnotesize,

    breakatwhitespace=false,      


    breaklines=true,              


    captionpos=b,                  


    keepspaces=true,              


    numbers=left,                  


    numbersep=5pt,                


    showspaces=false,              


    showstringspaces=false,

    showtabs=false,                


    tabsize=2

}

\\lstset{style=mystyle}

% \---------- 章节标题格式设置 \----------

\\ctexset{

    section \= {

        format \= \\heiti\\zihao{-4}\\raggedright, % 黑体小四号左对齐

        name \= {}, % 标题编号后跟中文顿号

        aftername \= {、},

        number \= \\chinese{section} % 中文数字编号

    }

}

\\ctexset{

    subsection \= {

        format \= \\heiti\\zihao{-4}\\raggedright,  % 黑体五号左对齐

        indent \= 2em,  % 缩进2字符

        number \= \\arabic{subsection},  % 阿拉伯数字编号

        aftername \= {.\~}  % 编号后跟点号和空格

    }

}

% \---------- 页眉页脚设置 \----------

\\pagestyle{fancy}

\\fancyhf{} % 清空所有页眉页脚

\\fancyfoot\[C\]{\\thepage} % 页脚居中，只有页码

\\renewcommand{\\headrulewidth}{0pt} % 去掉页眉的横线

\\renewcommand{\\footrulewidth}{0pt} % 去掉页脚的横线

\\begin{document}

\\maketitle

\\tableofcontents

\\newpage

但是依然可能存在包不足的问题，而且如果用自动编译循环的话，那么每轮问答都要编译一次，似乎有点慢了。实在不行的话最后输出一份tex文件，然后用户来手动编译，修复错误（通常是补上缺失的包）

此外，AI输出的答案latex中公式的编号可能会出一些问题，一个问题是如果公式有自动编号的话那最后的结果可能是到上千个公式。此外，公式要能被索引，但是有时候AI会在不同的题目中给不同的公式相同的label，这样索引会出问题，或许可以通过强制要求AI生成公式索引的时候带上随机数来规避？

好，这是我的一些想法和问题

Gemini said

你的系统设计已经从一个简单的“提取-回答”脚本，进化成了一个非常专业且工程化程度极高的 AI 辅助教材解析系统 (AI-Assisted Solution Manual Agent)。

你对“教辅级解析”、图片处理回退机制以及 LaTeX 编号冲突的思考，都非常切中实际开发中的痛点。我们来逐一攻克你提到的这些新问题：

1\. 教辅级解析的结构化输出

既然目标是不仅给答案，还要给“基础知识、一题多解、拓展引理”，我们可以在推理模型（如 DeepSeek-V3 或 Gemini 1.5 Pro）的输出阶段，再次引入严格的 JSON Schema 约束。

你可以让模型输出如下格式的 JSON。这样你的 Python 脚本就可以在渲染模板时，按照统一的样式（如用不同的醒目框 \\begin{mdframed}）来排版：

JSON

{

  "question\_id": "2-1",

  "solution\_process": "解答过程的 LaTeX 代码...",

  "knowledge\_points": "本题涉及的核心知识点总结...",

  "alternative\_methods": "（可选）多视角解法，如果没有则为空字符串",

  "extensions": "（可选）相关定理、引理或高阶拓展"

}

2\. 局部编译太慢？改为“生成源码 \+ 手动终审”

你提到“每轮问答都编译一次太慢”，这个判断非常正确。频繁调用底层进程，并且由于缺失宏包导致反复和 AI 交互，会极大浪费时间和 API Token。

最佳实践是：解耦生成与编译。

让你的脚本只负责将所有的 JSON 组装，生成一个最终的 final\_solution.tex 文件。作为使用者的你，拿到这个文件后，在本地的 TeXStudio、VSCode 或 Overleaf 中去编译它。这不仅免去了复杂的报错自动修复循环，还方便你进行最后的人工校对（补宏包、微调排版）。

3\. LaTeX 宏包与模板优化

仔细看了你设计的导言区模板，已经非常详尽且专业了！自动填入书名和模型名称的思路非常好（可以用 Jinja2 模板引擎实现：\\title{\\heiti\\zihao{-3} {{book\_title}} 参考答案}）。

给你两个小建议：

你在模板里写了两次 \\usepackage{minted}，可以删掉一个。

由于你加入了 amsmath 等宏包，为了配合后面的教辅排版，建议加上 mdframed 或 tcolorbox 宏包，这样你的“知识点总结”和“拓展引理”就可以放在漂亮的彩色方框里，极大提升阅读体验。

4\. 解决 LaTeX 公式编号爆炸与标签冲突

这是长文档自动化生成的经典 Bug。你提到的“公式自动编号到上千”和“Label 冲突”可以通过以下两种方法完美解决，不需要依赖 AI 生成随机数（AI 对随机数的生成往往有模式，且不可靠）：

方法 A：在 LaTeX 层面解决“公式编号爆炸”

你希望公式依然有编号，但不要一直累加到 1000。既然你的题目是用 \\subsection 来划分的，你可以在导言区加入这行代码：

Code snippet

\\numberwithin{equation}{subsection}

这会让公式编号变成类似于 (2.1.1) 的格式，每到新的一题（新的 subsection），公式编号自动从 1 开始。

方法 B：在 Prompt 层面解决“Label 冲突”（命名空间隔离）

不要让 AI 自由生成 \\label{eq:1}。在 System Prompt 中加入一条严格的命名规范指令：

Prompt 指令：“当你使用 \\label{} 和 \\ref{} 交叉引用公式时，必须将当前的题号作为前缀。例如，解答第 2-1 题时，公式标签必须写为 \\label{eq:2-1-1}，引用时写为 \\ref{eq:2-1-1}。”

这在软件工程中叫做命名空间隔离 (Namespace Isolation)，通过题号强绑定，100% 避免了不同题目之间的 \\label 重名导致索引错乱。

下一步：组合你的完整工作流

至此，你的逻辑拼图已经完整：

配置输入：人工填写包含章节、题号、页码的配置文件。

切片与 VLM：Python 根据页码提取图片，调用 VLM 输出带 has\_image 标记的习题集 JSON。

推理模型求解：Python 遍历题集，结合图片（如果有），让推理模型输出包含“解答、知识点、拓展”的解析集 JSON，并强制 label 附带题号前缀。

渲染组装：Jinja2 引擎将内容填入你写好的 .tex 模板，输出源码文件。

人工终审：你在本地编译 .tex 并检查。

这些环节中，第一步“利用 VLM 解析 PDF 生成习题集 JSON” 是目前最容易遇到提取格式不稳定的地方。需要我为你设计一段针对 VLM 的高级提取 System Prompt，确保它能稳定输出你想要的带有 has\_image 且格式纯净的 JSON 吗？

You said

我希望将以上的所有讨论都写进一份完整、全面、详细的开发文档，我将把这份文档发送给cursor然后vibecoding，所以这份开发文档务必要详细准确。

我的整个项目将在Textbook2Answer文件夹中，我已经提供了api\_config.json，格式为：

{

    "deepseek": {

        "base\_url": "https://ark.cn-beijing.volces.com/api/v3",

        "api\_key": "",

        "model": "deepseek-v3-2-251201"

    },

    "glm46": {

        "base\_url": "https://open.bigmodel.cn/api/paas/v4",

        "api\_key": "",

        "model": "glm-4.6v"

    },

    "gemini": {

        "base\_url": "https://generativelanguage.googleapis.com/v1beta/",

        "api\_key": "",

        "model": "gemini-3-pro-preview"

    },

    "gpt41": {

        "base\_url": "...",

        "api\_key": "...",

        "model": "gpt-4.1-2025-04-14"

    },

    "gpt5": {

        "base\_url": "...",

        "api\_key": "...",

        "model": "gpt-5-chat-2025-08-07"

    },

    "claude": {

        "base\_url": "...",

        "api\_key": "..."

    }

}

（现在是2026年2月22日，以上模型均存在，我打算先使用gemini）

（目前还是自行配置API，后续到了图形界面的时候还得单独设置API的配置逻辑）

我是否还需要提供一些API请求的测试脚本（比如向gemini发送图片的测试脚本），如果不用，那么我的目录当前只有一个api\_config.json

Defining the Document Scope

I'm now zeroing in on defining the precise scope for the "Textbook2Answer" Development Document. My focus is entirely on ensuring the document meets the requirements and goals. I am carefully considering the level of detail and accuracy required. I am making sure to provide a solid foundation for the subsequent stages.

Defining the Project Scope

I'm now detailing the project's scope, aiming for textbook PDF to LaTeX solution manual generation. Key features are manual chapter mapping (avoiding TOC parsing), VLM for exercise extraction to structured JSON, and image identification. The reasoning model will generate "Teaching Aid" style solutions with LaTeX formatting, using a predefined preamble with some tweaks, and avoiding auto-sectioning. I'll need to use named labels within the LaTeX document.

Refining the API Strategy

I'm now zeroing in on the API configuration and testing strategy. It's becoming clearer that I need to ensure foundational API calls, particularly multimodal ones, are working before diving into complex pipeline construction. I've decided to prioritize a minimal test script to validate this. The document will instruct Cursor to create these scripts as an initial phase. I'm also ensuring the API config is set up.

Defining the Document Content

I am now focusing on organizing the document's structure, aiming for clarity and completeness. I'm detailing the essential sections: a project overview, the core pipeline's workflow, and expected directory structures. I'm also ensuring the data structure schemas are precise for the LLMs, and specifying modules like config\_parser.py, pdf\_processor.py, vlm\_extractor.py, reasoning\_solver.py, and latex\_generator.py. I have included prompt engineering guidelines, a LaTeX template, and an implementation phase outline.

Detailing the Document Structure

I'm now detailing the content's sections and data structures. I'm noting the API configuration using api\_config.json with gemini-3-pro-preview as the starting point. I've defined schemas for the input config, extracted JSON, and solved JSON. System prompts are under development, with a focus on extraction and reasoning clarity. My LaTeX implementation includes packages like mdframed or tcolorbox, along with \\numberwithin. I'm starting from scratch.

Optimizing Equation Numbering

I've hit upon a solid LaTeX equation numbering strategy\! To ensure robustness with subsection headers, I'll insert \\renewcommand{\\theequation}{\<subsection\>-\<equation\_number\>} right after each subsection, using standard \\setcounter{equation}{0} within each subsection. This avoids custom counters. In addition, I will be using standard \\begin{equation} within the LLM generated output.

I'm now focusing on refining the output. I will be using Markdown extensively and resolving a key question about test scripts. Finally, I will be generating a comprehensive Markdown file to improve usability.

Gemini said

这是一个非常激动人心的项目！将这些深思熟虑的设计整理成一份标准的开发文档（PRD & Technical Specification），是进行 Cursor Vibecoding（让 AI 辅助甚至主导写代码）的最完美姿势。

针对你的问题：“是否还需要提供一些API请求的测试脚本？”

答案是：不需要你手动写。 但是，在开发文档的“执行阶段（Phases）”中，我们必须明确指示 Cursor 的第一步就是编写这些测试脚本。现代大模型 API（尤其是多模态）经常更新 SDK，让 Cursor 先写一个 test\_gemini\_vision.py 跑通你的 api\_config.json，能排查掉 80% 的底层环境问题，防止后面复杂的业务逻辑因为一个 API 传参错误而全盘崩溃。

为你生成这套完整的《Textbook2Answer 核心架构与开发说明文档》。你可以直接将下面生成的文件保存为 README\_Prompt.md 或直接作为 Cursor Composer / Chat 的全局 System Prompt 发送给它。
```