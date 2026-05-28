# Token 消耗监控器 设计文档

## 概述
桌面应用，用于监控 DeepSeek 和 Mimo 两个AI平台的API剩余量和token使用情况。

## 技术栈
- Python 3 + PyQt5（桌面UI）
- requests（API调用）
- PyInstaller（打包exe）

## 功能需求

### DeepSeek 面板
- 显示账户余额（美元）
- 显示token已用量

### Mimo 面板
- 显示已用token数
- 显示总token额度
- 显示剩余额度和百分比
- 进度条可视化

### 通用功能
- 手动刷新按钮
- API Key配置（首次使用时设置，保存到本地config.json）
- 错误提示（网络错误、API Key无效等）

## 界面设计

```
┌──────────────────────────────┐
│     Token 消耗监控器          │
│──────────────────────────────│
│  DeepSeek                    │
│  余额: $12.50                │
│  已用tokens: 1,234,567       │
│──────────────────────────────│
│  Mimo                        │
│  已用: 500,000               │
│  总额: 2,000,000             │
│  剩余: 1,500,000 (75%)       │
│  [████████████░░░░] 75%      │
│──────────────────────────────│
│  [设置API Key]  [刷新]        │
└──────────────────────────────┘
```

## 文件结构

```
监控器/
├── main.py              # 程序入口 + 主窗口
├── api/
│   ├── __init__.py
│   ├── deepseek.py      # DeepSeek API调用
│   └── mimo.py          # Mimo API调用
├── config.json          # API Key存储（运行时生成）
└── requirements.txt
```

## API 调用方式

### DeepSeek
- 查询余额和用量的API端点（待确认具体endpoint）

### Mimo
- 查询套餐用量的API端点（待确认具体endpoint）

## 数据存储
- API Key 保存在本地 config.json
- 不存储历史数据，每次刷新实时查询
