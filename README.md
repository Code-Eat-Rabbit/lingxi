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

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器
- 麦克风设备

### 安装

```bash
# 克隆仓库
git clone https://github.com/Code-Eat-Rabbit/lingxi.git
cd lingxi

# 使用 uv 安装依赖
uv sync

# 安装开发依赖（如需运行测试）
uv sync --dev

# 运行
uv run lingxi
```

### 首次使用

首次启动会进入 4 步引导向导：
1. 选择语音识别引擎（推荐 SenseVoice，本地运行）
2. 选择默认沟通风格
3. 设置录音快捷键
4. 授权麦克风和辅助功能权限

---

## 🎬 Demo 视频

> 📹 演示视频链接：[待上传]

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
用户口述 → PyAudio 录音 → ASR Engine 转录
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

## 📦 依赖清单

### 核心依赖

| 类别 | 包名 | 版本 | 用途 |
|------|------|------|------|
| ASR | faster-whisper | >=1.0.0 | 本地语音转录 |
| ASR | funasr | >=1.0.0 | 中文语音识别 + 情感分类 |
| ASR | numpy | >=1.24.0 | 数值计算 |
| 音频 | PyAudio | >=0.2.13 | 麦克风录音 |
| 音频 | sounddevice | >=0.4.6 | 备选录音后端 |
| 输入 | pynput | >=1.7.6 | 全局热键监听 |
| 输入 | pyautogui | >=0.9.54 | 键盘模拟注入 |
| 输入 | pyperclip | >=1.8.2 | 剪贴板操作 |
| LLM | openai | >=1.30.0 | OpenAI API 客户端 |
| LLM | ollama | >=0.2.0 | Ollama 本地 LLM |
| LLM | aiohttp | >=3.9.0 | 异步 HTTP 客户端 |
| UI | PySide6 | >=6.7.0 | Qt 桌面界面 |
| 上下文 | psutil | >=5.9.0 | 进程检测 |
| 情绪 | text2emotion | >=0.0.5 | Whisper 情绪补充分析 |
| 验证 | pydantic | >=2.0 | 数据验证 |
| 分词 | jieba | >=0.42.1 | 中文分词 / 实体提取 |

### 开发依赖

| 包名 | 用途 |
|------|------|
| pytest | 测试框架 |
| pytest-asyncio | 异步测试支持 |
| pytest-mock | Mock 工具 |
| pytest-cov | 覆盖率报告 |
| pytest-qt | PySide6 组件测试 |

---

## 📁 项目结构

```
lingxi/
├── lingxi/                   # 源代码包
│   ├── main.py               # 应用入口 + 系统托盘
│   ├── engine/               # ASR 语音引擎层
│   │   ├── asr_engine.py     # 协议定义 + 数据模型
│   │   ├── asr_faster_whisper.py  # faster-whisper 适配器
│   │   └── emotion.py        # 情绪枚举 + EmotionModulator
│   ├── style/                # 风格配置与转换引擎
│   │   ├── profile.py        # 核心数据模型 + 枚举定义
│   │   ├── presets.py        # 6 套预设风格
│   │   ├── store.py          # JSON 持久化存储
│   │   ├── compiler.py       # 五维参数→XML Prompt 编译器
│   │   ├── resolver.py       # 4 级优先级风格解析器
│   │   ├── post_processor.py # LLM 输出验证 + 降级
│   │   └── previewer.py      # 风格效果预览
│   ├── llm/                  # LLM 客户端
│   │   ├── client.py         # 协议 + 请求模型
│   │   ├── openai_client.py  # OpenAI 适配器
│   │   └── ollama_client.py  # Ollama 适配器
│   ├── io/                   # I/O 层
│   │   ├── audio_recorder.py # PyAudio 录音
│   │   ├── hotkey_manager.py # 全局热键管理
│   │   ├── text_injector.py  # 文本注入（三级策略）
│   │   └── clipboard.py      # 剪贴板封装
│   ├── context/              # 上下文感知
│   │   ├── app_detector.py   # 当前应用检测
│   │   └── contact_detector.py  # 联系人感知
│   ├── data/                 # 数据层
│   │   ├── config_store.py   # JSON 配置存储
│   │   └── history_store.py  # SQLite 历史记录
│   └── ui/                   # 界面层
│       ├── overlay.py        # 弹性胶囊 HUD
│       ├── style_picker.py   # 风格选择器
│       ├── style_builder.py  # 三栏风格构建器
│       └── compare_view.py   # 风格对比视图
├── tests/                    # 测试
│   ├── test_emotion.py
│   ├── test_style_profile.py
│   ├── test_style_compiler.py
│   ├── test_style_resolver.py
│   ├── test_post_processor.py
│   ├── test_config_store.py
│   ├── test_history_store.py
│   └── test_app_detector.py
├── pyproject.toml            # 项目配置 (uv)
└── README.md
```

---

## 🧪 测试

```bash
# 安装开发依赖
uv sync --dev

# 运行全部测试
uv run pytest tests/ -v

# 查看覆盖率
uv run pytest tests/ --cov=lingxi --cov-report=term
```

当前测试覆盖：**252 个测试，全部通过** ✅

---

## 🎯 原创功能

本项目的核心创新点：

1. **五维风格滑块模型** — 全球桌面语音输入产品中首创，将 AI 改写从「写 prompt」降维到「调滑块」
2. **情绪感知微调引擎** — 利用 ASR 情绪输出实时调制文字风格（7 种情绪 × 5 维参数 = 35 条调制规则）
3. **XML 结构化 Prompt 编译** — 将五维参数 + 情绪编译为结构化的 LLM System Prompt
4. **4 级优先级风格解析** — 手动覆盖 > 应用绑定 > 联系人感知 > 全局默认
5. **PostProcessor 验证降级链** — 空值检测 → 拒绝检测 → 长度异常 → 实体保持，三重降级保证输出可用
6. **三级文本注入策略** — 剪贴板粘贴 → pynput 逐字 → 手动复制，跨平台 CJK 输入法自动切换
7. **弹性胶囊 HUD** — 半透明毛玻璃 Overlay，弹簧入场动画，情绪颜色边框

---

## 📝 灵感来源

灵犀输入从 [Typeflux](https://github.com/nousresearch/typeflux)（Swift/macOS 语音输入产品）的架构设计中获得灵感，但**完全以 Python 重写**以实现跨平台（Windows + macOS + Linux），并在其基础上新增了风格引擎、情绪感知、多引擎支持等核心功能。

---

## 📄 License

MIT © 2025 Yutao Ma
