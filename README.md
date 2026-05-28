# MiMo Monitor

MiMo 用量监控工具，支持实时查看套餐额度和补偿额度。

## 功能

- 实时监控 Mimo 套餐和补偿额度
- 悬浮窗模式，常驻桌面显示
- 可自定义刷新间隔（30秒 ~ 1小时）
- 系统托盘支持，最小化后继续运行
- 用量趋势图表

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python main.py
```

首次运行需要在设置中配置 Mimo Cookies。

## 配置

登录 [platform.xiaomimimo.com](https://platform.xiaomimimo.com) 后：

1. F12 打开开发者工具
2. Application → Cookies
3. 复制完整 cookie 值
4. 在监控器设置中粘贴
