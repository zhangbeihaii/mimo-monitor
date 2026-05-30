# MiMo Monitor

MiMo 用量监控工具，支持实时查看套餐额度和补偿额度。

## 功能

- 实时监控 Mimo 套餐和补偿额度
- 悬浮窗模式，常驻桌面显示
- 可自定义刷新间隔（30秒 ~ 1小时）
- 系统托盘支持，最小化后继续运行
- 用量趋势图表

## 下载

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/zhangbeihaii/mimo-monitor/releases) 页面下载最新版本的 `MiMo Monitor.exe`。

### 方式二：从源码运行

```bash
git clone https://github.com/zhangbeihaii/mimo-monitor.git
cd mimo-monitor
pip install -r requirements.txt
python main.py
```

## 配置

首次运行需要配置 Mimo Cookies：

1. 登录 [platform.xiaomimimo.com](https://platform.xiaomimimo.com)
2. F12 打开开发者工具
3. Application → Cookies
4. 复制完整 cookie 值
5. 在监控器设置中粘贴

## 打包 EXE

如需自行打包：

```bash
pip install pyinstaller
python build.py
```

打包完成后，EXE 文件在 `dist/` 目录中。
