# 灵犀输入 — LingXi Input

> **Talk your way. We'll style it.**
>
> 语音转录 × AI 风格引擎。你说的每句话，都会以最合适的语气和风格呈现。

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-252%20passed-brightgreen)](tests/)

---

## 📖 项目简介

灵犀输入是一款以「个性化沟通风格」为核心差异化的跨平台语音输入产品。它不仅转录语音，更感知你的情绪、理解你与谁对话，自动将口述转为恰如其分的文字。

### 核心特色

| 特性 | 说明 |
|------|------|
| 🎚️ **五维风格配置** | 正式度、亲密度、幽默度、直接度、简练度 — 滑块控制，所见即所得 |
| 🎭 **6 套预设风格** | 敬重 / 亲热 / 诙谐 / 严谨 / 日常 / 极简，开箱即用 |
| 💬 **情绪感知微调** | ASR 识别情绪，实时调整文字风格，让文字「有温度」 |
| 🖥️ **跨平台** | Windows / macOS / Linux，PySide6 原生桌面界面 |
| 🔒 **隐私优先** | 默认本地推理，音频数据不出设备 |
| 🔌 **多引擎** | SenseVoice / FunASR / faster-whisper / OpenAI Whisper |
| 🤖 **离线可用** | 支持 Ollama 本地 LLM，全程零网络 |
| 🌐 **开源** | MIT 协议，完全开源 |

---

## 🚀 快速开始

### 环境要求

| 依赖 | 说明 | 安装方式 |
|------|------|----------|
| Python 3.11+ | 运行时 | [python.org](https://python.org) 或 `brew install python@3.11` |
| [uv](https://docs.astral.sh/uv/) | 包管理器 | `brew install uv` 或 `pip install uv` |
| 麦克风 | 硬件 | 内置/外接均可 |
| portaudio | PyAudio 的系统库（可选） | `brew install portaudio`（macOS）/ `apt install portaudio19-dev`（Linux） |

> **说明**：默认使用 `sounddevice` 录音，无需 `portaudio`。如需 PyAudio 后端，才需安装 portaudio 并执行 `uv sync --extra audio`。

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/Code-Eat-Rabbit/lingxi.git
cd lingxi

# 2. 安装依赖（首次约 5-10 分钟，需下载 ASR 和 UI 库）
uv sync

# 3. 启动应用
uv run lingxi
```

#### 可选：安装 PyAudio 后端

```bash
# macOS
brew install portaudio
uv sync --extra audio

# Linux (Debian/Ubuntu)
sudo apt install portaudio19-dev python3-pyaudio
uv sync --extra audio

# Windows
# PyAudio 提供预编译 wheel，直接执行：
uv sync --extra audio
```

#### 安装开发依赖（测试用）

```bash
uv sync --dev
uv run pytest tests/ -v    # 运行 252 个测试
```

---

## 📖 使用指南

### 1. 首次启动 — 4 步引导向导

首次打开灵犀时，会自动进入引导向导，帮你完成基本配置：

```
Step 1: 欢迎
  了解灵犀的核心能力

Step 2: 语音引擎选择
  ● SenseVoice（推荐） — 本地运行，隐私安全，~200MB
  ○ FunASR            — 本地运行，准确率最高，~500MB
  ○ faster-whisper    — 本地运行，CPU 优化好
  ○ 云端 Whisper       — 无需下载，需联网 + API Key

Step 3: 默认风格选择
  从 6 套预设中选一个作为日常默认风格

Step 4: 热键与权限
  录音快捷键 + 麦克风权限 + 辅助功能权限
```

> 如果中途关闭向导，下次启动时会从断点继续。

---

### 2. 日常使用流程

灵犀常驻系统托盘，使用**全局热键**触发：

| 平台 | 默认热键 |
|------|----------|
| macOS | `Fn + Command` |
| Windows / Linux | `Ctrl + Space` |

```
┌──────────────────────────────────────────────────┐
│  1. 打开任意输入框（微信 / 企业微信 / 编辑器等）    │
│                                                  │
│  2. 按住录音快捷键，开始说话                       │
│     └─ 屏幕中下方出现弹性胶囊 HUD                 │
│     └─ 实时显示转录文字                            │
│                                                  │
│  3. 松开快捷键                                    │
│     └─ ASR 转录 → 风格引擎 → LLM 转换             │
│     └─ 风格化文字自动注入到输入框                   │
│                                                  │
│  4. Overlay 显示结果 2 秒后自动消失                │
└──────────────────────────────────────────────────┘
```

#### 效果示例

| 口述原文 | 风格 | 输出 |
|----------|------|------|
| 「那个需求文档我写好了你看看吧」 | 💼 严谨 | 「XX 需求的技术方案文档已完成初稿，请您审阅。」 |
| 「我今天加班晚点回去」 | ❤️ 亲热 | 「今天要加会儿班，晚一小时到家，你们先吃别等我❤️」 |
| 「今天遇到一个奇葩」 | 😎 诙谐 | 「今日份的离谱人类观察👀 地铁上有人举着Switch打塞尔达你敢信」 |
| 「收到我马上去做」 | 📜 敬重 | 「收到，我尽快落实，有进展第一时间向您汇报。」 |
| 「那个事搞完了」 | ⚡ 极简 | 「搞定。」 |

---

### 3. 风格切换 — 4 种方式

灵犀支持 **4 级优先级** 的风格选择，从高到低：

| 优先级 | 触发方式 | 场景 |
|--------|----------|------|
| 1️⃣ 手动临时覆盖 | **长按**录音快捷键 → 弹出风格选择器 → ↑↓ 选择 → Enter 确认 | 偶尔换风格发一条消息 |
| 2️⃣ 应用绑定 | 设置中：微信→亲热，企业微信→严谨，邮件→敬重 | 固定场景自动切换 |
| 3️⃣ 联系人感知 | 自动识别聊天对象（v1.1，白名单应用） | 同一 App 内不同人 |
| 4️⃣ 全局默认 | 出厂「日常」，可在设置中更改 | 兜底风格 |

#### 长按选择风格

```
长按 `Fn + Command` 500ms (macOS) / `Ctrl + Space` (Win/Linux)
      │
      ▼
  ┌─────────────────────┐
  │  🎓 敬重 · 导师/领导  │  ← 当前生效（高亮）
  │  ❤️ 亲热 · 家人/挚友  │
  │  😎 诙谐 · 朋友/吐槽  │
  │  📊 严谨 · 同事/工作  │
  │  🍃 日常 · 通用默认   │
  │  ⚡ 极简 · 快速记录   │
  └─────────────────────┘
   ↑↓ 选择  Enter 确认  Esc 取消
```

此次录音使用临时风格，消息发送后自动恢复原风格。

---

### 4. 设置应用绑定

在系统托盘右键 → 设置 → 风格绑定：

```
应用名          绑定风格
──────────────────────────
微信            ❤️ 亲热
企业微信         📊 严谨
钉钉            📊 严谨
邮件            📜 敬重
Telegram        🍃 日常
VS Code         ⚡ 极简
```

每次切换到该应用时，风格自动切换，无需手动操作。

---

### 5. 自定义风格 — 风格构建器

系统托盘 → 设置 → 风格管理 → 「+ 新建风格」

三栏布局，所见即所得：

```
┌──────────┬────────────────┬──────────────────┐
│ 预设起点  │ 五维滑块        │ 实时预览          │
│          │                │                  │
│ ○ 从零    │ 正式度 [80%]   │ 输入: "今天加班"   │
│ ○ 敬重    │ 亲密度 [20%]   │                  │
│ ● 严谨    │ 幽默度 [0%]    │ → 输出:           │
│ ○ 日常    │ 直接度 [90%]   │ "今日需加班处理，  │
│          │ 简练度 [80%]   │  预计延后一小时到家" │
│          │                │                  │
│          │ 场景微调:       │                  │
│          │ 称呼: [您 ▾]   │                  │
│          │ 结尾: [此致敬礼]│                  │
│          │ 标点: [严谨 ▾] │                  │
│          │                │                  │
│          │ [保存]          │                  │
└──────────┴────────────────┴──────────────────┘
```

调整步骤：
1. **选基础**：从 6 套预设中选一个作为起点，或从零开始
2. **调滑块**：拖动 5 个维度的滑块（0-100），右侧实时预览效果
3. **微调场景**（可选）：设置称呼方式、结尾语、标点风格
4. **命名保存**：保存后会出现在风格列表中

---

### 6. 配置 LLM（大语言模型）

灵犀需要 LLM 来执行风格转换。支持两种方式：

#### 方案 A：云端 API（推荐，速度快）

1. 获取 API Key：[OpenAI](https://platform.openai.com/) 或任意兼容 API
2. 在设置中填入：

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "sk-xxxxxxxxxxxxx",
    "base_url": null
  }
}
```

> `base_url` 可指向任意 OpenAI 兼容 API（如 DeepSeek、通义千问等）。

#### 方案 B：本地 Ollama（隐私，无需网络）

1. 安装 [Ollama](https://ollama.com/)
2. 拉取推荐模型：

```bash
ollama pull qwen2.5:7b   # 首选，中文风格改写最佳
ollama pull qwen2.5:3b   # 低配机器备选
```

3. 灵犀会自动检测本地 Ollama 并使用

| 硬件 | 推荐模型 | 预计延迟 |
|------|----------|----------|
| M1 Max 及以上 | qwen2.5:7b | ~3s |
| M1 8GB / 16GB 无独显 | qwen2.5:3b | ~8s |
| RTX 3060+ | qwen2.5:7b (GPU) | ~2s |

---

### 7. 配置 ASR（语音识别引擎）

首次启动时选择，之后可在设置中更改：

| 引擎 | 模型大小 | 中文准确率 | 情绪输出 | 推荐场景 |
|------|----------|-----------|----------|----------|
| SenseVoice | ~200MB | ⭐⭐⭐⭐⭐ | ✅ 原生 | macOS（CoreML 加速） |
| FunASR | ~500MB | ⭐⭐⭐⭐⭐ | ✅ 情感分类 | Windows/Linux（GPU） |
| faster-whisper | ~500MB | ⭐⭐⭐⭐ | ❌ 需补充 | CPU 优化好，通用 |
| OpenAI Whisper | 0 (API) | ⭐⭐⭐⭐⭐ | ❌ | 不介意联网 |

> 模型首次使用时会自动下载到 `~/.lingxi/models/`。

---

## 🎬 Demo 视频

> 📹 演示视频链接：[待上传]

---

## 🧪 测试

```bash
uv sync --dev
uv run pytest tests/ -v                    # 运行全部
uv run pytest tests/ --cov=lingxi          # 查看覆盖率
uv run pytest tests/test_emotion.py -v     # 运行单个测试文件
```

当前测试覆盖：**252 个测试，全部通过** ✅

---

## 🏗️ 技术架构

```
┌── PySide6 UI Layer ──────────────────────────┐
│  OverlayHUD · StylePicker · CompareView      │
│  StyleBuilder (三栏布局)                       │
├── Style Engine ──────────────────────────────┤
│  StyleResolver (4 级优先级)                    │
│  StylePromptCompiler (五维→XML Prompt)        │
│  EmotionModulator (7 种情绪微调)               │
│  PostProcessor (验证 + 降级)                   │
├── ASR Pipeline ──────────────────────────────┤
│  ASREngine Protocol · FasterWhisperAdapter    │
│  Emotion Enum (7 种)                           │
├── LLM Pipeline ──────────────────────────────┤
│  OpenAIClient · OllamaClient                  │
├── I/O Layer ─────────────────────────────────┤
│  AudioRecorder · HotkeyManager · TextInjector │
├── Context Layer ─────────────────────────────┤
│  AppDetector · ContactDetector                │
└── Data Layer ────────────────────────────────┘
│  ConfigStore · HistoryStore                   │
```

### 数据流

```
用户口述 → 录音 → ASR Engine 转录
                    │
    TranscriptionResult (.text + .emotion)
                    │
    StyleResolver (4 级优先级解析风格)
                    │
    EmotionModulator (情绪微调五维参数)
                    │
    StylePromptCompiler (编译 XML Prompt)
                    │
    LLM Client (OpenAI / Ollama)
                    │
    PostProcessor (验证 + 降级)
                    │
    TextInjector (三级注入策略)
                    │
    目标应用输入框
```

---

## 🔧 常见问题

### 1. `uv sync` 失败：`fatal error: 'portaudio.h' file not found`

这是 PyAudio 需要系统库。默认不安装 PyAudio（使用 sounddevice），不影响使用。

如需 PyAudio：`brew install portaudio && uv sync --extra audio`

### 2. 启动后看不到 Overlay

- 检查是否授予了**辅助功能权限**（系统设置 → 隐私 → 辅助功能 → 添加终端/灵犀）
- 检查是否授予了**麦克风权限**

### 3. 录音后文字没有注入

- 确保目标窗口是**输入框**（不是只读区域）
- 切换输入法到**英文模式**重试
- 文字已自动复制到剪贴板，可手动 `Ctrl+V` 粘贴

### 4. 风格转换速度慢

- 云端 API 通常 1-3 秒
- 本地 Ollama 取决于硬件：M 系列芯片 3-15 秒，独显 2-5 秒
- 如需更快：换成更小的本地模型（qwen2.5:3b 或 1.5b）

### 5. 热键冲突

在设置中更换录音快捷键，或在系统托盘右键 → 手动触发录音。

---

## 📦 依赖清单

### Python 核心依赖

| 类别 | 包名 | 用途 |
|------|------|------|
| ASR | faster-whisper, funasr, numpy | 语音转录 |
| 音频 | sounddevice (默认) / PyAudio (可选) | 麦克风录音 |
| 输入 | pynput, pyautogui, pyperclip | 热键 + 文本注入 |
| LLM | openai, ollama, aiohttp | 云端/本地 LLM |
| UI | PySide6 | 桌面界面 |
| 上下文 | psutil | 进程检测 |
| 情绪 | text2emotion | 情绪补充分析 |
| 工具 | pydantic, jieba | 数据验证 + 中文分词 |

### 系统依赖（仅 PyAudio 需要）

| 平台 | 安装命令 |
|------|----------|
| macOS | `brew install portaudio` |
| Linux | `sudo apt install portaudio19-dev` |
| Windows | 无需（有预编译 wheel） |

---

## 📁 项目结构

```
lingxi/
├── lingxi/
│   ├── main.py               # 应用入口 + 系统托盘
│   ├── engine/               # ASR 引擎层
│   │   ├── asr_engine.py     # 协议定义
│   │   ├── asr_faster_whisper.py  # faster-whisper 适配
│   │   └── emotion.py        # 7 种情绪枚举 + 微调器
│   ├── style/                # 风格引擎
│   │   ├── profile.py        # 数据模型 + 7 个枚举
│   │   ├── presets.py        # 6 套预设风格
│   │   ├── store.py          # JSON 持久化
│   │   ├── compiler.py       # 五维→XML Prompt
│   │   ├── resolver.py       # 4 级优先级解析
│   │   └── post_processor.py # 验证 + 降级
│   ├── llm/                  # LLM 客户端
│   │   ├── client.py         # 协议 + 请求模型
│   │   ├── openai_client.py  # OpenAI 适配器
│   │   └── ollama_client.py  # Ollama 适配器
│   ├── io/                   # I/O 层
│   │   ├── audio_recorder.py # 录音（sounddevice/PyAudio）
│   │   ├── hotkey_manager.py # 全局热键（300ms 防抖）
│   │   ├── text_injector.py  # 文本注入（三级策略）
│   │   └── clipboard.py      # 剪贴板封装
│   ├── context/              # 上下文感知
│   │   ├── app_detector.py   # 跨平台应用检测
│   │   └── contact_detector.py  # 联系人感知
│   ├── data/                 # 数据存储
│   │   ├── config_store.py   # JSON 配置（~/.lingxi/）
│   │   └── history_store.py  # SQLite 历史
│   └── ui/                   # 界面
│       ├── overlay.py        # 弹性胶囊 HUD
│       ├── style_picker.py   # 风格选择器
│       ├── style_builder.py  # 三栏风格构建器
│       └── compare_view.py   # 风格对比视图
├── tests/                    # 252 个测试
├── pyproject.toml            # uv 配置
└── README.md
```

---

## 🎯 原创功能

本项目的核心创新点：

1. **五维风格滑块模型** — 将 AI 改写从「写 prompt」降维到「调滑块」
2. **情绪感知微调引擎** — 7 种情绪 × 5 维参数 = 35 条调制规则
3. **XML 结构化 Prompt 编译** — 五维参数 + 情绪 → LLM System Prompt
4. **4 级优先级风格解析** — 手动 > 应用绑定 > 联系人 > 默认
5. **PostProcessor 验证降级链** — 空值→拒绝检测→长度→实体，三重降级
6. **三级文本注入策略** — 剪贴板粘贴 → 逐字输入 → 手动复制，CJK 自动切换
7. **弹性胶囊 HUD** — 半透明毛玻璃，弹簧动画，情绪颜色边框

---

## 📝 灵感来源

灵犀输入从 [Typeflux](https://github.com/nousresearch/typeflux) 的架构设计中获得灵感，但**完全以 Python 重写**实现跨平台（Windows + macOS + Linux），并新增了风格引擎、情绪感知、多引擎支持等核心功能。

---

## 📄 License

MIT © 2025 Yutao Ma
