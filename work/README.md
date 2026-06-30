# BOSS Browser MCP Agent

一个基于 Chrome DevTools MCP、页面文本快照解析和本地 LLM 的 BOSS 直聘自动检索 Agent。

这个项目的主运行链路不是“截图识别 + 坐标点击”，而是：

1. 通过 `chrome-devtools-mcp` 连接 Chrome
2. 读取页面快照和部分 DOM 文本
3. 解析职位卡片和职位详情
4. 使用 LLM 判断岗位是否匹配
5. 对匹配岗位执行“立即沟通”

## 项目简介

当前运行模式是 `browser_mcp_text_only`。

主流程如下：

```text
用户输入求职目标
-> 目标解析
-> 连接 Chrome DevTools MCP
-> 打开或复用 BOSS 页面
-> 搜索职位
-> 读取页面快照文本
-> 解析职位列表和职位详情
-> LLM 语义评估
-> 可选执行“立即沟通”
```

## 核心特性

- 通过 `chrome-devtools-mcp` 控制 Chrome
- 通过 Ollama 提供本地 LLM 能力
- 使用显式状态机驱动完整流程
- 结合快照解析和 DOM 回退提取
- 做 LLM 语义判断
- 输出完整的调试日志、MCP 调用日志和快照日志

## 架构说明

### 入口文件

- [run_agent.py]

负责读取命令行目标，创建 Agent，并启动异步主流程。

## LLM 在项目中的作用

LLM 在这个项目里不是浏览器操作者，它不会自己点击按钮。

当前主流程中的真实行为是：

- 目标解析阶段在主链路里默认启用 LLM
- 职位评估阶段启用 LLM

LLM 实际接收的是结构化文本，而不是截图。通常包括：

- 用户目标 JSON
- 规则预检查结果 JSON
- 职位详情 JSON

最终是否“立即沟通”，当前实现本质上是：是llm给出建议，然后agent去实行


## 运行环境

这个项目依赖三层环境：

### Python 环境

依赖文件：[requirements.txt]

- `mcp[cli]`
- `ollama`
- `openai`
- `pydantic`
- `python-dotenv`
- `loguru`
- `PyYAML`

### 本地 LLM

默认通过 Ollama 提供模型能力：

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=Qwen3:8B
LLM_API_KEY=ollama
```

### 浏览器控制层

默认 MCP 启动命令：

```env
MCP_COMMAND=cmd
MCP_ARGS=/c,npx,-y,chrome-devtools-mcp@latest,--autoConnect
```

### 浏览器设置

使用谷歌浏览器，但是搜索引擎使用bing，同时不要翻墙
这样才能保证boss直聘网页快速加载避免程序出错


## 快速开始

### 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 2. 配置 `.env`

推荐配置：

```env
RUN_MODE=browser_mcp_text_only
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=Qwen3:8B
LLM_API_KEY=ollama
MCP_COMMAND=cmd
MCP_ARGS=/c,npx,-y,chrome-devtools-mcp@latest,--autoConnect
BOSS_HOME_URL=https://www.zhipin.com/
MAX_COMMUNICATIONS=2
MAX_JOB_SCAN=80
MAX_STEPS=120
ACTION_TIMEOUT_MS=15000
SNAPSHOT_VERBOSE=false
DEBUG_DUMP=true
LOGS_ROOT=logs
```

如果 `--autoConnect` 不稳定，可以改成：

```env
MCP_ARGS=/c,npx,-y,chrome-devtools-mcp@latest,--browser-url=http://127.0.0.1:9222
```

### 3. 准备依赖环境

运行前请确认本地已具备：

- Node.js
- npm
- npx
- Chrome
- Ollama
- `Qwen3:8B` 模型

### 4. 启动

打开谷歌浏览器

```powershell
python run_agent.py
```

## 示例目标

```text
查找前端实习，日薪大于200，符合的话点击立即沟通
```

通常会被解析成类似意图：

- 搜索关键词：`前端 实习`
- 薪资要求：`日薪 > 200`
- 是否需要沟通：`true`

## 日志输出

运行后会生成这些调试产物：

- `logs/agent/YYYYMMDD/run_*.log`
- `logs/mcp/YYYYMMDD/mcp_*.jsonl`
- `logs/debug/latest_snapshot.txt`
- `logs/debug/latest_pages.json`
- `logs/debug/latest_console.json`
- `logs/debug/latest_network.json`
- `logs/debug/latest_state.json`
- `logs/debug/latest_summary.json`

这些日志适合排查：

- MCP 到底调用了哪些浏览器工具
- Agent 当时看到了什么快照文本
- 当前状态机运行到了哪一步
- 岗位为什么被跳过或为什么被命中

