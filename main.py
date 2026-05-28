import json
import os
import sys
import time

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QDialog,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from api import mimo
from database import save_snapshot, get_history
from chart import TrendChart

APP_NAME = "MiMoMonitor"
if os.name == 'nt':  # Windows
    CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), APP_NAME)
else:
    CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config', APP_NAME)
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
REFRESH_INTERVAL_MS = 5 * 60 * 1000

CARD_STYLE = """
QFrame#card {
    background: rgba(30, 30, 50, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 16px;
}
"""

GLOBAL_STYLE = """
QMainWindow {
    background: transparent;
}
QLabel {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}
QPushButton {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    background: rgba(30, 30, 50, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 12px;
    padding: 10px 24px;
    font-size: 13px;
    color: white;
}
QPushButton:hover {
    background: rgba(40, 40, 60, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.35);
}
QPushButton:pressed {
    background: rgba(25, 25, 45, 0.5);
}
QPushButton#primary {
    background: rgba(102, 126, 234, 0.6);
    color: white;
    border: 1px solid rgba(102, 126, 234, 0.8);
    font-weight: bold;
}
QPushButton#primary:hover {
    background: rgba(102, 126, 234, 0.7);
}
QPushButton#refresh {
    background: rgba(56, 239, 125, 0.4);
    color: white;
    border: 1px solid rgba(56, 239, 125, 0.6);
    font-weight: bold;
}
QPushButton#refresh:hover {
    background: rgba(56, 239, 125, 0.5);
}
QPushButton#refresh:disabled {
    background: rgba(56, 239, 125, 0.2);
}
QProgressBar {
    border: none;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.15);
    height: 14px;
    text-align: center;
    font-size: 10px;
    color: white;
}
QProgressBar::chunk {
    border-radius: 8px;
    background: rgba(102, 126, 234, 0.7);
}
QDialog {
    background: rgba(30, 30, 50, 0.85);
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}
QLineEdit {
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 12px;
    padding: 10px 16px;
    font-size: 13px;
    background: rgba(30, 30, 50, 0.5);
    color: white;
}
QLineEdit:focus {
    border: 2px solid rgba(102, 126, 234, 0.6);
    background: rgba(30, 30, 50, 0.6);
}
"""


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def format_tokens(n) -> str:
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _fmt_short(n) -> str:
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def make_shadow():
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(30)
    shadow.setOffset(0, 4)
    shadow.setColor(QColor(102, 126, 234, 50))
    return shadow


def make_card() -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(CARD_STYLE)
    card.setGraphicsEffect(make_shadow())
    return card


def make_info_row(label_text: str, color: str = "rgba(255, 255, 255, 0.7)") -> tuple:
    """创建一行：标签 + 数值"""
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"font-size: 13px; color: rgba(255, 255, 255, 0.5);")
    val = QLabel("--")
    val.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
    val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row.addWidget(lbl)
    row.addWidget(val)
    return row, val


def make_section_bar(title: str, color: str) -> tuple:
    """创建一个带标题、大数字、进度条、详情行的区域"""
    container = QFrame()
    container.setObjectName("card")
    container.setStyleSheet(CARD_STYLE)
    container.setGraphicsEffect(make_shadow())

    layout = QVBoxLayout(container)
    layout.setContentsMargins(20, 14, 20, 14)
    layout.setSpacing(8)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
    layout.addWidget(title_lbl)

    big = QLabel("--")
    big.setStyleSheet(f"font-size: 32px; font-weight: bold; color: white;")
    big.setAlignment(Qt.AlignCenter)
    layout.addWidget(big)

    sub = QLabel("")
    sub.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.5);")
    sub.setAlignment(Qt.AlignCenter)
    layout.addWidget(sub)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.setStyleSheet(f"""
        QProgressBar {{ background: rgba(255, 255, 255, 0.1); border-radius: 4px; }}
        QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}
    """)
    layout.addWidget(bar)

    row_used_layout, used_lbl = make_info_row("已用")
    row_limit_layout, limit_lbl = make_info_row("总额")
    row_remain_layout, remain_lbl = make_info_row("剩余", color)
    layout.addLayout(row_used_layout)
    layout.addLayout(row_limit_layout)
    layout.addLayout(row_remain_layout)

    return container, big, sub, bar, used_lbl, limit_lbl, remain_lbl


# ---------- 数据获取线程 ----------

class FetchWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, mimo_cookies: str):
        super().__init__()
        self.mimo_cookies = mimo_cookies

    def run(self):
        result = {}
        try:
            if self.mimo_cookies:
                result["mimo"] = mimo.get_usage(self.mimo_cookies)
        except Exception as e:
            result["mimo_error"] = str(e)

        # 获取Mimo历史数据
        try:
            if self.mimo_cookies:
                result["mimo_history"] = mimo.get_history(self.mimo_cookies)
        except Exception as e:
            result["mimo_history_error"] = str(e)

        # 获取Mimo套餐详情
        try:
            if self.mimo_cookies:
                result["mimo_detail"] = mimo.get_plan_detail(self.mimo_cookies)
        except Exception as e:
            result["mimo_detail_error"] = str(e)

        self.finished.emit(result)


# ---------- 标签页按钮 ----------

class TabButton(QPushButton):
    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self.color = color
        self._active = False
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self.setMinimumWidth(120)
        self._update_style()

    def set_active(self, active: bool):
        self._active = active
        self.setChecked(active)
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {self.color};
                    color: white;
                    border: none;
                    border-radius: 18px;
                    padding: 6px 24px;
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #E8E8ED;
                    color: #666;
                    border: none;
                    border-radius: 18px;
                    padding: 6px 24px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #D1D1D6;
                }
            """)


# ---------- 设置对话框 ----------

class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(460)
        self.config = config

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("API 配置")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.mimo_input = QLineEdit(config.get("mimo_cookies", ""))
        self.mimo_input.setPlaceholderText("userId=xxx; api-platform_slh=xxx; api-platform_ph=xxx")
        # 自动去除双引号
        self.mimo_input.textChanged.connect(lambda text: self.mimo_input.setText(text.replace('"', '')) if '"' in text else None)
        form.addRow("Mimo Cookies:", self.mimo_input)

        # 获取教程按钮
        help_btn_layout = QHBoxLayout()
        help_btn = QPushButton("查看获取教程")
        help_btn.setStyleSheet("""
            QPushButton { background: #5856D6; color: white; border: none; border-radius: 6px;
                          padding: 8px 16px; font-size: 13px; }
            QPushButton:hover { background: #4A48B8; }
        """)
        help_btn.clicked.connect(self.show_cookie_tutorial)
        help_btn_layout.addWidget(help_btn)
        help_btn_layout.addStretch()
        form.addRow("", help_btn_layout)

        hint = QLabel(
            "点击「查看获取教程」查看详细步骤"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        layout.addLayout(form)

        # 关闭行为
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E8E8ED;")
        layout.addWidget(sep)

        close_label = QLabel("关闭窗口时:")
        close_label.setStyleSheet("font-size: 13px; color: #333;")
        layout.addWidget(close_label)

        self.close_combo = QComboBox()
        self.close_combo.addItems(["最小化到托盘", "彻底退出程序"])
        current = config.get("close_action", "minimize")
        self.close_combo.setCurrentIndex(0 if current == "minimize" else 1)
        self.close_combo.setStyleSheet("""
            QComboBox { border: 1px solid #D1D1D6; border-radius: 8px; padding: 6px 12px; font-size: 13px; }
        """)
        layout.addWidget(self.close_combo)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def show_cookie_tutorial(self):
        """显示获取 Cookies 的教程"""
        QMessageBox.information(self, "获取 Cookies 教程",
            "请按以下步骤获取 Cookies：\n\n"
            "1. 打开浏览器，访问：\n"
            "   https://platform.xiaomimimo.com/console/plan-manage\n\n"
            "2. 登录你的 Mimo 账号\n\n"
            "3. 按 F12 打开开发者工具\n\n"
            "4. 切换到「Network」（网络）标签\n\n"
            "5. 刷新页面（按 F5）\n\n"
            "6. 在请求列表中找到「usage」请求\n\n"
            "7. 点击该请求，查看「Headers」\n\n"
            "8. 找到「Cookie」字段，复制其值\n\n"
            "9. 粘贴到下方输入框（会自动去除双引号）")

    def save(self):
        self.config["mimo_cookies"] = self.mimo_input.text().strip()
        self.config["close_action"] = "minimize" if self.close_combo.currentIndex() == 0 else "exit"
        save_config(self.config)
        self.accept()


# ---------- Mimo 详情面板 ----------

class MimoDetail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_plan_used = None
        self.last_comp_used = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 本次新增卡片
        delta_card = QFrame()
        delta_card.setObjectName("card")
        delta_card.setStyleSheet(CARD_STYLE)
        delta_card.setGraphicsEffect(make_shadow())
        delta_layout = QHBoxLayout(delta_card)
        delta_layout.setContentsMargins(16, 12, 16, 12)

        delta_plan_lbl = QLabel("套餐本次新增:")
        delta_plan_lbl.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.5);")
        delta_layout.addWidget(delta_plan_lbl)
        self.delta_plan_val = QLabel("--")
        self.delta_plan_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffd43b;")
        delta_layout.addWidget(self.delta_plan_val)

        delta_layout.addStretch()

        delta_comp_lbl = QLabel("补偿本次新增:")
        delta_comp_lbl.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.5);")
        delta_layout.addWidget(delta_comp_lbl)
        self.delta_comp_val = QLabel("--")
        self.delta_comp_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #748ffc;")
        delta_layout.addWidget(self.delta_comp_val)

        layout.addWidget(delta_card)

        # 套餐总量
        self.plan_section, self.plan_big, self.plan_sub, self.plan_bar, \
            self.plan_used, self.plan_limit, self.plan_remain = make_section_bar("套餐总量", "#FF9500")
        layout.addWidget(self.plan_section)

        # 补偿额度
        self.comp_section, self.comp_big, self.comp_sub, self.comp_bar, \
            self.comp_used, self.comp_limit, self.comp_remain = make_section_bar("补偿额度", "#5856D6")
        layout.addWidget(self.comp_section)

        # 套餐信息行
        info_card = QFrame()
        info_card.setObjectName("card")
        info_card.setStyleSheet(CARD_STYLE)
        info_card.setGraphicsEffect(make_shadow())
        info_layout = QHBoxLayout(info_card)
        info_layout.setContentsMargins(16, 10, 16, 10)

        self.plan_name_lbl = QLabel("套餐: --")
        self.plan_name_lbl.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.6);")
        info_layout.addWidget(self.plan_name_lbl)

        info_layout.addStretch()

        self.expire_lbl = QLabel("有效期: --")
        self.expire_lbl.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.6);")
        info_layout.addWidget(self.expire_lbl)

        layout.addWidget(info_card)

        # 图表
        self.chart = TrendChart()
        chart_card = make_card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(8, 8, 8, 8)
        chart_layout.addWidget(self.chart)
        layout.addWidget(chart_card)

        layout.addStretch()

    def update_data(self, data: dict, history: list = None, detail: dict = None):
        if "error" in data:
            self.plan_big.setText("--")
            self.plan_sub.setText(data["error"])
            self.plan_sub.setStyleSheet("font-size: 12px; color: #ff6b6b;")
            self.plan_bar.setValue(0)
            self.comp_big.setText("--")
            self.comp_bar.setValue(0)
            return

        info = data

        # 套餐
        plan_used = info["plan_used"]
        plan_limit = info["plan_limit"]
        plan_remain = plan_limit - plan_used
        plan_pct_used = info.get("plan_percent", 0)
        plan_pct_display = round(plan_pct_used * 100, 2)
        save_snapshot("mimo_plan", used=plan_used, total=plan_limit)

        # 计算套餐本次新增
        if self.last_plan_used is not None:
            delta_plan = plan_used - self.last_plan_used
            if delta_plan >= 0:
                self.delta_plan_val.setText(f"+{delta_plan:,}")
                self.delta_plan_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff6b6b;")
            else:
                self.delta_plan_val.setText(f"{delta_plan:,}")
                self.delta_plan_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #69db7c;")
        self.last_plan_used = plan_used

        self.plan_big.setText(f"{plan_remain:,}")
        self.plan_sub.setText(f"套餐剩余  (已用 {plan_pct_display}%)")
        self.plan_sub.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.5);")
        self.plan_bar.setValue(int((1 - plan_pct_used) * 100) if plan_limit > 0 else 0)
        self.plan_used.setText(f"{plan_used:,}")
        self.plan_limit.setText(f"{plan_limit:,}")
        self.plan_remain.setText(f"{plan_remain:,}")

        # 补偿额度
        comp_used = info["comp_used"]
        comp_limit = info["comp_limit"]
        comp_remain = comp_limit - comp_used
        comp_pct_used = info.get("comp_percent", 0)
        comp_pct_display = round(comp_pct_used * 100, 2)
        save_snapshot("mimo_comp", used=comp_used, total=comp_limit)

        # 计算补偿本次新增
        if self.last_comp_used is not None:
            delta_comp = comp_used - self.last_comp_used
            if delta_comp >= 0:
                self.delta_comp_val.setText(f"+{delta_comp:,}")
                self.delta_comp_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff6b6b;")
            else:
                self.delta_comp_val.setText(f"{delta_comp:,}")
                self.delta_comp_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #69db7c;")
        self.last_comp_used = comp_used

        self.comp_big.setText(f"{comp_remain:,}")
        self.comp_sub.setText(f"补偿剩余  (已用 {comp_pct_display}%)")
        self.comp_sub.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.5);")
        self.comp_bar.setValue(int((1 - comp_pct_used) * 100) if comp_limit > 0 else 0)
        self.comp_used.setText(f"{comp_used:,}")
        self.comp_limit.setText(f"{comp_limit:,}")
        self.comp_remain.setText(f"{comp_remain:,}")

        # 图表 - 优先用API历史数据（多模型）
        if history and isinstance(history, dict) and any(history.values()):
            self.chart.set_multi_data(history, "Mimo 各模型用量 (本月)")
        elif history and isinstance(history, list) and len(history) >= 2:
            self.chart.set_data(history, "Mimo 用量 (本月)")
        else:
            local_history = get_history("mimo_plan", days=30)
            if len(local_history) >= 2:
                chart_data = [(row[0], row[1]) for row in local_history]
                self.chart.set_data(chart_data, "Mimo 用量")

        # 套餐详情
        if detail:
            self.plan_name_lbl.setText(f"套餐: {detail.get('plan_name', '--')}")
            end = detail.get("period_end", "")
            if end:
                self.expire_lbl.setText(f"有效期至: {end[:10]}")
                expired = detail.get("expired", False)
                self.expire_lbl.setStyleSheet(f"font-size: 12px; color: {'#FF3B30' if expired else '#555'};")
        else:
            self.plan_name_lbl.setText("套餐: --")
            self.expire_lbl.setText("有效期: --")

    def set_unconfigured(self):
        self.plan_big.setText("--")
        self.plan_sub.setText("请在设置中填写 Mimo Cookies")
        self.plan_sub.setStyleSheet("font-size: 12px; color: #ffd43b;")
        self.plan_bar.setValue(0)
        self.plan_used.setText("--")
        self.plan_limit.setText("--")
        self.plan_remain.setText("--")
        self.comp_big.setText("--")
        self.comp_bar.setValue(0)
        self.comp_used.setText("--")
        self.comp_limit.setText("--")
        self.comp_remain.setText("--")


# ---------- 主窗口 ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MiMo Monitor v1.2")
        self.setMinimumSize(580, 680)
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.config = load_config()
        self.worker = None
        self.auto_refresh = True
        self._last_data = {}
        self.float_win = FloatingWindow(self)

        # 启用 Windows 毛玻璃效果
        self.enable_blur_behind()

        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 12, 20, 20)
        main_layout.setSpacing(12)

        # 顶部标题栏
        header = QHBoxLayout()
        title = QLabel("MiMo Monitor")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
        header.addWidget(title)
        header.addStretch()

        self.float_btn = QPushButton("悬浮窗")
        self.float_btn.setFixedHeight(30)
        self.float_btn.setStyleSheet("""
            QPushButton { background: rgba(30, 30, 50, 0.5); border: 1px solid rgba(255, 255, 255, 0.25);
                          border-radius: 8px; padding: 6px 16px; font-size: 12px; color: white; }
            QPushButton:hover { background: rgba(40, 40, 60, 0.6); }
        """)
        self.float_btn.clicked.connect(self.switch_to_float)
        header.addWidget(self.float_btn)

        self.settings_btn = QPushButton("⚙ 设置")
        self.settings_btn.clicked.connect(self.open_settings)
        header.addWidget(self.settings_btn)
        main_layout.addLayout(header)

        # 内容区 - 直接显示Mimo详情
        self.mimo_detail = MimoDetail()
        main_layout.addWidget(self.mimo_detail, 1)

        # 底部状态栏
        footer = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.7);")
        footer.addWidget(self.status_label)

        footer.addStretch()

        # 刷新间隔选择
        self.interval_label = QLabel("自动刷新时间：")
        self.interval_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.7);")
        footer.addWidget(self.interval_label)

        self.interval_combo = QComboBox()
        self.interval_combo.setFixedWidth(100)
        self.interval_options = [
            ("30秒", 30 * 1000),
            ("1分钟", 60 * 1000),
            ("2分钟", 2 * 60 * 1000),
            ("5分钟", 5 * 60 * 1000),
            ("10分钟", 10 * 60 * 1000),
            ("30分钟", 30 * 60 * 1000),
            ("1小时", 60 * 60 * 1000),
        ]
        for label, _ in self.interval_options:
            self.interval_combo.addItem(label)
        # 从配置读取上次选择的间隔
        saved_interval = self.config.get("refresh_interval", 5 * 60 * 1000)
        for i, (_, ms) in enumerate(self.interval_options):
            if ms == saved_interval:
                self.interval_combo.setCurrentIndex(i)
                break
        self.interval_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11px;
                background: rgba(30, 30, 50, 0.5);
                color: white;
            }
        """)
        self.interval_combo.currentIndexChanged.connect(self.on_interval_changed)
        footer.addWidget(self.interval_combo)

        self.toggle_btn = QPushButton("暂停")
        self.toggle_btn.setFixedWidth(50)
        self.toggle_btn.setStyleSheet("""
            font-size: 11px; padding: 6px 12px;
            background: rgba(30, 30, 50, 0.5);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.25);
        """)
        self.toggle_btn.clicked.connect(self.toggle_auto)
        footer.addWidget(self.toggle_btn)

        self.refresh_btn = QPushButton("↻ 刷新")
        self.refresh_btn.setObjectName("refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        footer.addWidget(self.refresh_btn)

        main_layout.addLayout(footer)

        # 定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.current_interval = self.interval_options[self.interval_combo.currentIndex()][1]
        self.timer.start(self.current_interval)

        # 系统托盘
        self.setup_tray()

        # 首次加载
        QTimer.singleShot(500, self.refresh)

    def enable_blur_behind(self):
        """启用 Windows 毛玻璃效果"""
        try:
            import ctypes
            from ctypes import wintypes

            # Windows DWM API
            dwmapi = ctypes.windll.dwmapi

            # DWM_BLURBEHIND 结构
            class DWM_BLURBEHIND(ctypes.Structure):
                _fields_ = [
                    ("dwFlags", wintypes.DWORD),
                    ("fEnable", wintypes.BOOL),
                    ("hRgnBlur", wintypes.HRGN),
                    ("fTransitionOnMaximized", wintypes.BOOL),
                ]

            # 获取窗口句柄
            hwnd = int(self.winId())

            # 启用模糊
            bb = DWM_BLURBEHIND()
            bb.dwFlags = 0x00000001  # DWM_BB_ENABLE
            bb.fEnable = True
            bb.hRgnBlur = None
            bb.fTransitionOnMaximized = False

            dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(bb))

        except Exception as e:
            print(f"启用毛玻璃效果失败: {e}")

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._make_tray_icon())
        self.tray.setToolTip("MiMo Monitor")

        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("显示窗口")
        show_action.triggered.connect(self.show_and_raise)
        refresh_action = self.tray_menu.addAction("立即刷新")
        refresh_action.triggered.connect(self.refresh)
        self.tray_menu.addSeparator()
        self.pin_action = self.tray_menu.addAction("取消固定悬浮窗")
        self.pin_action.triggered.connect(self._toggle_float_pin)
        self.pin_action.setVisible(False)
        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("退出")
        quit_action.triggered.connect(self.quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def _toggle_float_pin(self):
        self.float_win.set_pinned(False)

    def _update_tray_pin_text(self):
        is_pinned = self.float_win._pinned
        self.pin_action.setVisible(is_pinned)

    def _make_tray_icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        # 备用方案：程序生成图标
        pix = QPixmap(32, 32)
        pix.fill(QColor(0, 122, 255))
        p = QPainter(pix)
        p.setPen(QPen(Qt.white, 2))
        p.setFont(QFont("Arial", 16, QFont.Bold))
        p.drawText(pix.rect(), Qt.AlignCenter, "M")
        p.end()
        return QIcon(pix)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_and_raise()

    def show_and_raise(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def switch_to_float(self):
        self.hide()
        self.float_win.move(self.x(), self.y())
        self.float_win.show()
        if self._last_data:
            self.float_win.update_data(self._last_data)

    def quit_app(self):
        self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self.config.get("close_action", "minimize") == "exit":
            self.tray.hide()
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.tray.showMessage("MiMo Monitor", "已最小化到系统托盘", QSystemTrayIcon.Information, 1500)

    def on_interval_changed(self, index):
        self.current_interval = self.interval_options[index][1]
        self.config["refresh_interval"] = self.current_interval
        save_config(self.config)
        if self.auto_refresh:
            self.timer.start(self.current_interval)

    def toggle_auto(self):
        self.auto_refresh = not self.auto_refresh
        if self.auto_refresh:
            self.timer.start(self.current_interval)
            self.toggle_btn.setText("暂停")
            self.interval_combo.setEnabled(True)
        else:
            self.timer.stop()
            self.toggle_btn.setText("恢复")
            self.interval_combo.setEnabled(False)

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.config
            self.refresh()

    def refresh(self):
        if self.worker and self.worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("获取中...")
        self.status_label.setText("正在获取数据...")
        self.status_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.7);")

        self.worker = FetchWorker(
            self.config.get("mimo_cookies", ""),
        )
        self.worker.finished.connect(self.on_data)
        self.worker.start()

    def on_data(self, data: dict):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("↻ 刷新")
        now_str = time.strftime("%H:%M:%S")
        self.status_label.setText(f"上次更新: {now_str}")
        self.status_label.setStyleSheet("font-size: 11px; color: #38ef7d;")

        self._last_data = data
        self._update_panels(data)
        self.float_win.update_data(data)

    def _update_panels(self, data: dict):
        # Mimo
        mimo_history = data.get("mimo_history", [])
        mimo_detail = data.get("mimo_detail")
        if "mimo_error" in data:
            self.mimo_detail.update_data({"error": data["mimo_error"]}, mimo_history, mimo_detail)
        elif "mimo" in data:
            self.mimo_detail.update_data(data["mimo"], mimo_history, mimo_detail)
        else:
            self.mimo_detail.set_unconfigured()


# ---------- 悬浮窗 ----------

class FloatProgressBar(QWidget):
    """悬浮窗专用进度条，颜色随百分比变化"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._pct = 0

    def set_percent(self, pct: float):
        self._pct = max(0, min(100, pct))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 背景
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(0, 0, w, h, 3, 3)

        # 填充
        fill_w = int(w * self._pct / 100)
        if self._pct <= 50:
            color = QColor("#34C759")
        elif self._pct <= 80:
            color = QColor("#FF9500")
        else:
            color = QColor("#FF3B30")
        p.setBrush(color)
        p.drawRoundedRect(0, 0, fill_w, h, 3, 3)
        p.end()


class FloatingWindow(QWidget):
    def __init__(self, main_window: MainWindow):
        super().__init__()
        self.main_window = main_window
        self._drag_pos = None
        self._pinned = False

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(220, 120)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self.setStyleSheet("""
            QWidget#floatbg {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(40,40,50,245), stop:1 rgba(25,25,35,245));
                border: 1px solid rgba(255,255,255,18);
                border-radius: 14px;
            }
            QLabel { color: #EEE; font-family: "Microsoft YaHei", sans-serif; }
        """)

        bg = QFrame()
        bg.setObjectName("floatbg")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(bg)

        inner = QVBoxLayout(bg)
        inner.setContentsMargins(14, 8, 14, 8)
        inner.setSpacing(4)

        # 标题行：Mimo Pro | 补偿额度
        header = QHBoxLayout()
        self.title_lbl = QLabel("Mimo")
        self.title_lbl.setStyleSheet("font-size: 13px; color: #FF9500; font-weight: bold;")
        header.addWidget(self.title_lbl)
        self.plan_name_lbl = QLabel("")
        self.plan_name_lbl.setStyleSheet("font-size: 13px; color: #CCC; font-weight: bold;")
        header.addWidget(self.plan_name_lbl)
        header.addStretch()
        self.type_lbl = QLabel("--")
        self.type_lbl.setStyleSheet("font-size: 11px; color: #BBB;")
        header.addWidget(self.type_lbl)
        inner.addLayout(header)

        # 进度条
        self.bar = FloatProgressBar()
        inner.addWidget(self.bar)

        # 数值 | 百分比
        val_row = QHBoxLayout()
        self.val_lbl = QLabel("--")
        self.val_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFF;")
        val_row.addWidget(self.val_lbl)
        val_row.addStretch()
        self.pct_lbl = QLabel("--")
        self.pct_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #DDD;")
        val_row.addWidget(self.pct_lbl)
        inner.addLayout(val_row)

        # 今日用量 | 有效期
        info_row = QHBoxLayout()
        self.today_lbl = QLabel("今日: --")
        self.today_lbl.setStyleSheet("font-size: 10px; color: #BBB;")
        info_row.addWidget(self.today_lbl)
        info_row.addStretch()
        self.expire_lbl = QLabel("")
        self.expire_lbl.setStyleSheet("font-size: 10px; color: #999;")
        info_row.addWidget(self.expire_lbl)
        inner.addLayout(info_row)

        # 更新时间
        self.status_lbl = QLabel("--")
        self.status_lbl.setStyleSheet("font-size: 9px; color: #777;")
        inner.addWidget(self.status_lbl)

    def update_data(self, data: dict):
        now_str = time.strftime("%H:%M")
        self.status_lbl.setText(f"更新于 {now_str}")

        # 有效期 + 套餐名
        detail = data.get("mimo_detail")
        if detail:
            self.plan_name_lbl.setText(f" {detail.get('plan_name', '')}")
            if detail.get("period_end"):
                self.expire_lbl.setText(f"有效期至 {detail['period_end'][:10]}")
            else:
                self.expire_lbl.setText("")
        else:
            self.plan_name_lbl.setText("")
            self.expire_lbl.setText("")

        # 昨日用量
        history = data.get("mimo_history", {})
        yesterday_ts = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) - 86400
        yesterday_str = ""
        if isinstance(history, dict):
            for model, entries in history.items():
                for ts, val in entries:
                    if int(ts) == int(yesterday_ts):
                        yesterday_str = f"{_fmt_short(val)}" if not yesterday_str else yesterday_str
                        break
        self.today_lbl.setText(f"昨日: {yesterday_str}" if yesterday_str else "昨日: 暂无数据")

        if "mimo" in data:
            info = data["mimo"]
            comp_used = info.get("comp_used", 0)
            comp_limit = info.get("comp_limit", 0)
            plan_used = info.get("plan_used", 0)
            plan_limit = info.get("plan_limit", 0)

            if comp_limit > 0 and comp_used < comp_limit:
                self.type_lbl.setText("补偿额度")
                used = comp_used
                limit = comp_limit
                pct_used = info.get("comp_percent", 0)
            else:
                self.type_lbl.setText("套餐额度")
                used = plan_used
                limit = plan_limit
                pct_used = info.get("plan_percent", 0)

            pct_display = round(pct_used * 100, 1)
            self.val_lbl.setText(f"{_fmt_short(used)} / {_fmt_short(limit)}")
            self.pct_lbl.setText(f"{pct_display}%")
            self.bar.set_percent(pct_display)
        elif "mimo_error" in data:
            self.val_lbl.setText("错误")
            self.pct_lbl.setText("")
            self.bar.set_percent(0)
            self.type_lbl.setText("")
        else:
            self.val_lbl.setText("未配置")
            self.pct_lbl.setText("")
            self.bar.set_percent(0)
            self.type_lbl.setText("")

    def _show_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2C2C2E; color: #EEE; border: 1px solid #444; border-radius: 6px; padding: 4px; font-size: 12px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #007AFF; }
        """)
        expand_action = menu.addAction("展开主窗口")
        refresh_action = menu.addAction("立即刷新")

        # 固定选项
        menu.addSeparator()
        pin_text = "取消固定" if self._pinned else "固定悬浮窗"
        pin_action = menu.addAction(pin_text)
        if not self._pinned:
            hint = menu.addAction("  取消方式: 右键托盘图标")
            hint.setEnabled(False)

        # 透明度子菜单
        menu.addSeparator()
        opacity_menu = menu.addMenu("透明度")
        opacity_menu.setStyleSheet(menu.styleSheet())
        opacities = [("100%", 1.0), ("80%", 0.8), ("60%", 0.6), ("40%", 0.4)]
        opacity_actions = {}
        for label, val in opacities:
            a = opacity_menu.addAction(label)
            opacity_actions[a] = val

        menu.addSeparator()
        close_action = menu.addAction("关闭悬浮窗")

        action = menu.exec_(self.mapToGlobal(pos))
        if action == expand_action:
            self.expand()
        elif action == refresh_action:
            self.main_window.refresh()
        elif action == pin_action:
            self.set_pinned(not self._pinned)
        elif action == close_action:
            self.quit_app()
        elif action in opacity_actions:
            self.set_opacity(opacity_actions[action])

    def expand(self):
        self.set_pinned(False)
        self.hide()
        self.main_window.show_and_raise()

    def set_pinned(self, pinned: bool):
        self._pinned = pinned
        if pinned:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput
            )
        else:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
            )
        self.show()
        self.main_window._update_tray_pin_text()

    def set_opacity(self, opacity: float):
        self.setWindowOpacity(opacity)

    def quit_app(self):
        self.hide()
        if self.main_window.config.get("close_action", "minimize") == "exit":
            self.main_window.tray.hide()
            QApplication.instance().quit()
        else:
            self.main_window.tray.showMessage("MiMo Monitor", "已关闭悬浮窗，程序仍在托盘运行", QSystemTrayIcon.Information, 1500)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_STYLE)
    app.setQuitOnLastWindowClosed(False)
    # 设置应用图标
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
