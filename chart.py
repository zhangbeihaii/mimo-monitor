from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QFont, QLinearGradient, QBrush
from PyQt5.QtWidgets import QWidget
import time
import calendar
import math


MODEL_COLORS = {
    "mimo-v2.5-pro": "#FF6B35",
    "mimo-v2.5": "#5B8DEF",
    "mimo-v2-pro": "#E84393",
    "mimo-v2-omni": "#00B894",
}


def _nice_step(max_val: float) -> float:
    if max_val <= 0:
        return 1
    raw = max_val / 4
    mag = 10 ** math.floor(math.log10(raw))
    residual = raw / mag
    if residual <= 1:
        nice = 1
    elif residual <= 2:
        nice = 2
    elif residual <= 5:
        nice = 5
    else:
        nice = 10
    return nice * mag


def _fill_missing_days(data: list, days_in_month: int, year: int, month: int) -> list:
    if not data:
        return data
    day_map = {}
    for ts, val in data:
        day_map[time.localtime(ts).tm_mday] = val
    result = []
    for day in range(1, days_in_month + 1):
        ts = time.mktime((year, month, day, 0, 0, 0, 0, 0, -1))
        result.append((ts, day_map.get(day, 0)))
    return result


class TrendChart(QWidget):
    """多线折线图，支持按模型分色显示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets = []  # [(name, color, [(ts, val), ...]), ...]
        self.label = ""
        self.setMinimumHeight(220)
        self.setMinimumWidth(400)
        self.setMouseTracking(True)
        self._hover_index = -1
        self._all_points = {}  # {name: [QPointF, ...]}
        self._display_data = {}
        self._year = 0
        self._month = 0
        self._days_in_month = 30
        self._real_days = {}  # {name: set(day)}

    def set_multi_data(self, models: dict, label: str = ""):
        """models: {"model_name": [(ts, val), ...], ...}"""
        self.label = label
        self.datasets = []
        self._all_points = {}
        self._display_data = {}
        self._real_days = {}
        self._hover_index = -1

        if not models:
            self.update()
            return

        # 确定月份
        first_model = next(iter(models.values()))
        if first_model:
            t = time.localtime(first_model[0][0])
            self._year, self._month = t.tm_year, t.tm_mon
            self._days_in_month = calendar.monthrange(self._year, self._month)[1]

        for i, (model_name, data) in enumerate(models.items()):
            color = MODEL_COLORS.get(model_name, ["#FF6B35", "#5B8DEF", "#E84393", "#00B894"][i % 4])
            real = {time.localtime(ts).tm_mday for ts, _ in data}
            filled = _fill_missing_days(data, self._days_in_month, self._year, self._month)
            self.datasets.append((model_name, QColor(color), filled))
            self._real_days[model_name] = real

        self.update()

    def set_data(self, data: list, label: str = "", color: str = "#4A90D9"):
        """单线模式兼容"""
        if data:
            t = time.localtime(data[0][0])
            self._year, self._month = t.tm_year, t.tm_mon
            self._days_in_month = calendar.monthrange(self._year, self._month)[1]
        self.set_multi_data({"total": data} if data else {}, label)

    def mouseMoveEvent(self, event):
        if not self._all_points:
            self._hover_index = -1
            super().mouseMoveEvent(event)
            return
        mx, my = event.x(), event.y()
        best_idx = -1
        best_dist = 30
        for name, pts in self._all_points.items():
            for i, pt in enumerate(pts):
                dist = ((pt.x() - mx) ** 2 + (pt.y() - my) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
        if best_idx != self._hover_index:
            self._hover_index = best_idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 75, 20, 35, 40
        chart_w = w - margin_l - margin_r
        chart_h = h - margin_t - margin_b

        p.fillRect(self.rect(), QColor("#FAFAFA"))

        if self.label:
            p.setPen(QPen(QColor("#333")))
            p.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            p.drawText(QRectF(margin_l, 5, chart_w, 22), Qt.AlignLeft, self.label)

        if not self.datasets or chart_w <= 0 or chart_h <= 0:
            p.setPen(QPen(QColor("#999")))
            p.setFont(QFont("Microsoft YaHei", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            p.end()
            return

        # 计算全局Y轴范围
        all_vals = []
        for _, _, data in self.datasets:
            all_vals.extend(v for _, v in data)
        v_max = max(all_vals) if all_vals and max(all_vals) > 0 else 1

        step = _nice_step(v_max)
        y_ticks = []
        v = 0
        while v <= v_max * 1.1:
            y_ticks.append(v)
            v += step
        if not y_ticks:
            y_ticks = [0, 1]
        y_max = y_ticks[-1]

        # Y轴网格
        grid_pen = QPen(QColor("#E8E8E8"), 1, Qt.DashLine)
        for tick in y_ticks:
            y = margin_t + chart_h * (1 - tick / y_max)
            p.setPen(grid_pen)
            p.drawLine(int(margin_l), int(y), int(w - margin_r), int(y))
            p.setPen(QPen(QColor("#999")))
            p.setFont(QFont("Microsoft YaHei", 8))
            p.drawText(QRectF(0, y - 10, margin_l - 8, 20), Qt.AlignRight | Qt.AlignVCenter, self._fmt_y(tick))

        # X轴
        month_start = time.mktime((self._year, self._month, 1, 0, 0, 0, 0, 0, -1))
        month_end = time.mktime((self._year, self._month, self._days_in_month, 0, 0, 0, 0, 0, -1))

        def ts_to_x(ts):
            if month_end == month_start:
                return margin_l
            return margin_l + chart_w * (ts - month_start) / (month_end - month_start)

        p.setPen(QPen(QColor("#999")))
        p.setFont(QFont("Microsoft YaHei", 8))
        x_step = max(1, self._days_in_month // 8)
        for day in range(1, self._days_in_month + 1, x_step):
            ts = time.mktime((self._year, self._month, day, 0, 0, 0, 0, 0, -1))
            x = ts_to_x(ts)
            p.drawText(QRectF(x - 20, h - margin_b + 5, 40, 20), Qt.AlignCenter, f"{self._month}/{day}")

        # 绘制每条线
        self._all_points = {}
        for name, color, data in self.datasets:
            points = []
            for ts, val in data:
                x = ts_to_x(ts)
                y = margin_t + chart_h * (1 - val / y_max) if y_max > 0 else margin_t + chart_h
                points.append(QPointF(x, y))
            self._all_points[name] = points

            if len(points) < 2:
                continue

            # 渐变填充
            path = QPainterPath()
            path.moveTo(points[0].x(), margin_t + chart_h)
            for pt in points:
                path.lineTo(pt)
            path.lineTo(points[-1].x(), margin_t + chart_h)
            path.closeSubpath()

            grad = QLinearGradient(0, margin_t, 0, margin_t + chart_h)
            fill = QColor(color)
            fill.setAlpha(20)
            grad.setColorAt(0, fill)
            grad.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillPath(path, grad)

            # 折线
            p.setPen(QPen(color, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for i in range(len(points) - 1):
                p.drawLine(points[i], points[i + 1])

            # 数据点
            real = self._real_days.get(name, set())
            for i, pt in enumerate(points):
                day = i + 1
                if i == self._hover_index:
                    p.setBrush(color)
                    p.setPen(QPen(Qt.white, 2.5))
                    p.drawEllipse(pt, 6, 6)
                elif day in real:
                    p.setBrush(color)
                    p.setPen(QPen(Qt.white, 2))
                    p.drawEllipse(pt, 4, 4)
                else:
                    p.setBrush(QColor("#FAFAFA"))
                    p.setPen(QPen(color, 1.5))
                    p.drawEllipse(pt, 3, 3)

        # 悬停提示
        if 0 <= self._hover_index < self._days_in_month:
            day = self._hover_index + 1
            ts = time.mktime((self._year, self._month, day, 0, 0, 0, 0, 0, -1))
            date_str = f"{self._month}月{day}日"

            # 收集这天所有模型的值
            lines = [(date_str, None)]
            for name, color, data in self.datasets:
                if self._hover_index < len(data):
                    _, val = data[self._hover_index]
                    real = self._real_days.get(name, set())
                    short = name.replace("mimo-", "").replace("-", ".")
                    if day in real:
                        lines.append((f"{short}: {val:,}", color))
                    else:
                        lines.append((f"{short}: 0", QColor("#999")))

            # 定位
            ref_pts = list(self._all_points.values())[0] if self._all_points else []
            if ref_pts and self._hover_index < len(ref_pts):
                pt = ref_pts[self._hover_index]
                th = 20 + len(lines) * 18
                tw = max(150, max(len(l[0]) for l in lines) * 8 + 20)
                tx = pt.x() - tw / 2
                ty = pt.y() - th - 14
                if tx < margin_l:
                    tx = margin_l
                if tx + tw > w - margin_r:
                    tx = w - margin_r - tw
                if ty < margin_t:
                    ty = pt.y() + 18

                # 阴影
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 25))
                p.drawRoundedRect(QRectF(tx + 2, ty + 2, tw, th), 8, 8)

                # 背景
                p.setBrush(QColor(30, 30, 30, 230))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(tx, ty, tw, th), 8, 8)

                # 小三角
                tri = QPainterPath()
                tri.moveTo(pt.x() - 6, ty + th)
                tri.lineTo(pt.x(), ty + th + 6)
                tri.lineTo(pt.x() + 6, ty + th)
                tri.closeSubpath()
                p.fillPath(tri, QBrush(QColor(30, 30, 30, 230)))

                # 文字
                y_off = 4
                for i, (text, clr) in enumerate(lines):
                    if i == 0:
                        p.setPen(QPen(QColor("#CCC")))
                        p.setFont(QFont("Microsoft YaHei", 9))
                    else:
                        p.setPen(QPen(clr if clr else QColor("#FFF")))
                        p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
                    p.drawText(QRectF(tx + 10, ty + y_off, tw - 20, 18), Qt.AlignLeft, text)
                    y_off += 18

        # 图例
        if len(self.datasets) > 1:
            lx = margin_l
            ly = h - 8
            for name, color, _ in self.datasets:
                short = name.replace("mimo-", "").replace("-", ".")
                p.setBrush(color)
                p.setPen(Qt.NoPen)
                p.drawEllipse(int(lx), int(ly - 4), 8, 8)
                p.setPen(QPen(QColor("#666")))
                p.setFont(QFont("Microsoft YaHei", 8))
                p.drawText(QRectF(lx + 12, ly - 8, 100, 16), Qt.AlignLeft | Qt.AlignVCenter, short)
                lx += len(short) * 7 + 30

        p.end()

    def _fmt_y(self, val):
        if val >= 1_000_000_000:
            return f"{val / 1_000_000_000:.0f}B"
        if val >= 1_000_000:
            return f"{val / 1_000_000:.0f}M"
        if val >= 1_000:
            return f"{val / 1_000:.0f}K"
        return f"{val:,.0f}"
