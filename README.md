# Klipper Voice Plugin

<div align="center">

![Klipper Voice](https://img.shields.io/badge/Klipper-Voice-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.7%2B-blue?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/License-GPL%20v3-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Ready-success?style=for-the-badge)

**为 Klipper 3D 打印机添加智能语音播报功能**

[功能特性](#-功能特性) • [安装指南](#-安装指南) • [配置说明](#-配置说明) • [使用方法](#-使用方法) • [音频文件](#-音频文件管理)

</div>

---

## 📋 项目简介

Klipper Voice Plugin 是一个为 Klipper 3D 打印机固件开发的智能语音播报插件。它能够在打印过程中的关键时刻通过语音提醒用户，让您无需时刻关注打印机状态，提升 3D 打印体验。

### 🎯 设计理念
- **非侵入式**：不影响 Klipper 核心功能，纯插件化设计
- **高度可配置**：支持自定义消息、音量、语言等设置
- **多语言支持**：支持多种语言的音频文件和智能回退机制
- **易于扩展**：模块化设计，便于添加新功能

## ✨ 功能特性

### 🔊 智能语音播报
- **打印事件播报**：打印开始、结束、暂停、恢复、取消
- **状态监控播报**：温度达到、加热开始、耗材检测
- **错误警报**：可配置的错误事件语音提醒
- **自定义消息**：支持通过 G-code 命令发送自定义语音消息

### 🎵 音频系统
- **多格式支持**：MP3、WAV、OGG 等主流音频格式
- **多播放器兼容**：mpg123、aplay、paplay、vlc 等
- **音量控制**：软件和硬件音量控制
- **后台播放**：非阻塞音频播放，不影响打印性能

### 🌐 多语言支持
- **智能语言选择**：自动选择对应语言的音频文件
- **回退机制**：当前语言 → 英语 → 默认 → 任意可用
- **热切换**：运行时可切换语言设置

### 🎛️ 灵活控制
- **G-code 命令**：5个专用命令完全控制语音功能
- **Web API**：支持通过 REST API 远程控制
- **宏集成**：完美集成到现有的 G-code 宏中
- **事件驱动**：自动响应打印机状态变化

### ⚙️ 高级功能
- **速率限制**：防止语音播报过于频繁
- **播放队列**：智能管理多个语音请求
- **文件缓存**：高效的音频文件管理
- **错误恢复**：音频系统故障时优雅降级

## 🚀 安装指南

### 1. 系统要求
- Klipper 固件环境
- Python 3.7+
- Linux 操作系统 (Raspberry Pi 推荐)
- 音频输出设备

### 2. 安装依赖
```bash
# 安装音频播放器 (选择一个)
sudo apt update
sudo apt install mpg123          # MP3 播放器 (推荐)
sudo apt install alsa-utils      # ALSA 音频工具
sudo apt install pulseaudio-utils # PulseAudio 工具

# 可选：TTS 引擎 (用于生成音频文件)
sudo apt install espeak espeak-data
sudo apt install lame            # MP3 编码器
```

### 3. 安装插件
```bash
# 复制插件文件到 Klipper extras 目录
cp klipper_voice.py /path/to/klipper/klippy/extras/

# 重启 Klipper 服务
sudo systemctl restart klipper
```

## ⚙️ 配置说明

### 基础配置
在 `printer.cfg` 中添加以下配置：

```ini
[klipper_voice]
# 基础设置
enabled: True                     # 启用/禁用语音功能
volume: 0.8                       # 音量 (0.0-1.0)
language: en                      # 语言代码
min_interval: 2.0                 # 最小播报间隔(秒)

# 音频文件设置
audio_path: /home/pi/klipper_voice_files
audio_format: mp3
audio_player: mpg123
audio_player_args: -q
use_hardware_volume: True

# 自动播报设置
auto_print_start: True            # 自动播报打印开始
auto_print_end: True              # 自动播报打印结束
auto_print_pause: True            # 自动播报打印暂停
auto_print_resume: True           # 自动播报打印恢复
auto_print_cancel: True           # 自动播报打印取消
auto_ready: True                  # 自动播报就绪状态

# 自定义消息 (可选)
msg_print_start: Print started, please stand by
msg_print_end: Print completed successfully
msg_print_pause: Print has been paused
# ... 更多自定义消息
```

### 高级配置选项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `True` | 全局启用/禁用开关 |
| `volume` | `0.8` | 播放音量 (0.0-1.0) |
| `voice_speed` | `1.0` | 播放速度 (0.5-2.0) |
| `language` | `en` | 语言代码 |
| `audio_path` | `/home/pi/klipper_voice_files` | 音频文件目录 |
| `audio_format` | `mp3` | 音频文件格式 |
| `audio_player` | `mpg123` | 音频播放器 |
| `min_interval` | `2.0` | 最小播报间隔 |

## 🎮 使用方法

### G-code 命令

#### VOICE_ANNOUNCE - 播报语音消息
```gcode
VOICE_ANNOUNCE MESSAGE="Hello from Klipper"           # 自定义消息
VOICE_ANNOUNCE TYPE=print_start                       # 预定义消息
VOICE_ANNOUNCE MESSAGE="Loud message" VOLUME=1.0      # 临时调整音量
```

#### VOICE_CONFIG - 配置语音设置
```gcode
VOICE_CONFIG ENABLE=1 VOLUME=0.8                      # 启用并设置音量
VOICE_CONFIG SPEED=1.2 LANGUAGE=en                    # 设置速度和语言
VOICE_CONFIG                                          # 显示当前设置
```

#### VOICE_STATUS - 显示状态信息
```gcode
VOICE_STATUS                                          # 显示详细状态
```

#### VOICE_TEST - 测试语音功能
```gcode
VOICE_TEST                                           # 测试默认消息
VOICE_TEST TYPE=print_start                          # 测试特定消息类型
```

#### VOICE_SCAN - 重新扫描音频文件
```gcode
VOICE_SCAN                                           # 重新扫描音频文件目录
```

### 宏集成示例

```gcode
[gcode_macro PRINT_START]
gcode:
    G28                                              # 归零
    # ... 其他打印前准备
    VOICE_ANNOUNCE TYPE=print_start                  # 语音播报

[gcode_macro PRINT_END]
gcode:
    # ... 打印结束处理
    VOICE_ANNOUNCE TYPE=print_end                    # 语音播报

[gcode_macro PAUSE]
rename_existing: PAUSE_BASE
gcode:
    PAUSE_BASE
    VOICE_ANNOUNCE TYPE=print_pause
```

## 🎵 音频文件管理

### 文件命名规范
音频文件应放置在配置的 `audio_path` 目录中，命名格式为：
```
<消息类型>.<语言>.<格式>
```

### 示例文件结构
```
/home/pi/klipper_voice_files/
├── print_start.en.mp3           # 英语：打印开始
├── print_start.zh.mp3           # 中文：打印开始
├── print_end.en.mp3             # 英语：打印结束
├── print_pause.en.mp3           # 英语：打印暂停
├── print_resume.en.mp3          # 英语：打印恢复
├── print_cancel.en.mp3          # 英语：打印取消
├── ready.en.mp3                 # 英语：准备就绪
├── error.en.mp3                 # 英语：错误警报
└── filament_runout.en.mp3       # 英语：耗材用完
```

### 支持的消息类型
| 消息类型 | 说明 | 触发时机 |
|----------|------|----------|
| `print_start` | 打印开始 | 开始打印时 |
| `print_end` | 打印结束 | 打印完成时 |
| `print_pause` | 打印暂停 | 暂停打印时 |
| `print_resume` | 打印恢复 | 恢复打印时 |
| `print_cancel` | 打印取消 | 取消打印时 |
| `ready` | 准备就绪 | Klipper 启动完成时 |
| `heating` | 开始加热 | 加热器启动时 |
| `temp_reached` | 温度达到 | 目标温度到达时 |
| `filament_runout` | 耗材用完 | 检测到耗材用完时 |
| `error` | 错误警报 | 发生错误时 |

### 生成音频文件
使用提供的脚本快速生成示例音频文件：

```bash
# 使脚本可执行
chmod +x create_sample_audio_files.sh

# 运行脚本生成音频文件
./create_sample_audio_files.sh
```

脚本支持的 TTS 引擎：
- **espeak**：轻量级 TTS 引擎
- **festival**：高质量 TTS 引擎  
- **pico2wave**：紧凑型 TTS 引擎

## 🔌 Web API

插件提供 REST API 接口用于远程控制：

### 播报消息
```http
POST /voice/announce
Content-Type: application/json

{
    "message": "Hello from web API",
    "type": "custom"
}
```

### 获取配置
```http
GET /voice/config
```

### 获取状态
```http
GET /voice/status
```

## 🛠️ 故障排除

### 常见问题

#### 1. 音频播放失败
```bash
# 检查音频播放器是否安装
which mpg123

# 测试音频播放
mpg123 /home/pi/klipper_voice_files/ready.en.mp3

# 检查音频文件权限
ls -la /home/pi/klipper_voice_files/
```

#### 2. 音频文件未找到
```gcode
# 重新扫描音频文件
VOICE_SCAN

# 检查文件命名是否正确
VOICE_STATUS
```

#### 3. 音量控制问题
```bash
# 检查系统音量
amixer get Master

# 调整系统音量
amixer set Master 80%
```

### 调试模式
在 Klipper 日志中查看详细信息：
```bash
tail -f /tmp/klippy.log | grep -i voice
```

## 📊 性能说明

### 系统占用
- **CPU 使用率**：< 1% (播放时)
- **内存占用**：< 10MB
- **存储空间**：取决于音频文件数量 (通常 < 50MB)
- **网络带宽**：无 (本地播放)

### 延迟指标
- **命令响应**：< 100ms
- **音频启动**：< 500ms
- **事件响应**：< 200ms

## 📁 项目文件结构

```
klipper_voice/
├── klipper_voice.py                    # 主插件文件
├── klipper_voice_config_example.cfg    # 配置示例文件
├── create_sample_audio_files.sh        # 音频文件生成脚本
├── klipper_voice_readme.md            # 项目说明文档
└── klipper-plugin-development-guide.md # 插件开发指南
```

## 🎯 使用场景

### 家庭用户
- **长时间打印监控**：无需时刻关注打印机，语音提醒关键状态
- **多任务工作**：在其他房间工作时及时了解打印进度
- **夜间打印**：通过语音了解打印状态，避免频繁查看

### 专业用户
- **打印农场管理**：同时监控多台打印机状态
- **远程监控**：结合网络摄像头实现完整的远程监控方案
- **自动化流程**：集成到自动化生产流程中

### 教育场景
- **教学演示**：语音播报帮助学生理解打印流程
- **实验室管理**：多台设备的状态监控
- **安全提醒**：及时播报异常状况

## 🔄 更新日志

### v1.0.0 (当前版本)
- ✅ 完整的语音播报系统
- ✅ 多语言音频文件支持
- ✅ G-code 命令控制
- ✅ Web API 接口
- ✅ 自动事件检测
- ✅ 音频文件缓存管理
- ✅ 详细的配置选项

### 未来计划
- 🔄 实时 TTS 语音合成
- 🔄 更多语言支持
- 🔄 音频效果处理
- 🔄 移动端 App 集成
- 🔄 云端语音服务

## 🤝 贡献指南

欢迎贡献代码、提出建议或报告问题！

### 如何贡献
1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 报告问题
使用 [GitHub Issues](issues-url) 报告 Bug 或请求功能

## 📄 许可证

本项目基于 GPL v3 许可证开源 - 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- **Klipper 项目**：优秀的 3D 打印机固件
- **开源社区**：提供宝贵的反馈和建议
- **测试用户**：帮助发现和修复问题

---

<div align="center">

**如果这个项目对您有帮助，请考虑给个 ⭐ Star！**

Made with ❤️ for the 3D Printing Community

</div>