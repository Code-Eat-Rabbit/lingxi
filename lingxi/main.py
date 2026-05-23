"""
灵犀输入 — 应用入口 + 系统托盘
"""

import sys
import signal
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt

# 配置路径
APP_NAME = "灵犀输入"
APP_DIR = Path.home() / ".lingxi"
CONFIG_FILE = APP_DIR / "config.json"
PROFILES_FILE = APP_DIR / "profiles.json"
HISTORY_DB = APP_DIR / "history.db"
MODELS_DIR = APP_DIR / "models"

logger = logging.getLogger(__name__)


def ensure_app_dirs() -> None:
    """确保应用目录存在。"""
    for d in [APP_DIR, MODELS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def create_app_icon() -> QIcon:
    """创建应用图标（使用内置资源或默认图标）。"""
    # TODO: v1.0 替换为真实图标资源
    return QApplication.style().standardIcon(
        QApplication.style().StandardPixmap.SP_MediaVolume
    )


class SystemTray:
    """系统托盘管理。"""

    def __init__(self, app: QApplication):
        self.app = app
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_app_icon())
        self.tray.setToolTip(APP_NAME)

        # 菜单
        menu = QMenu()

        # 风格切换子菜单
        self.style_menu = QMenu("风格切换")
        menu.addMenu(self.style_menu)

        menu.addSeparator()

        # 设置
        settings_action = QAction("设置...", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

        # 左键点击打开设置
        self.tray.activated.connect(self._on_tray_activated)

        logger.info("系统托盘已启动")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._open_settings()

    def _open_settings(self) -> None:
        """打开设置窗口。"""
        # TODO: v1.0 实现设置窗口
        logger.info("打开设置窗口（未实现）")

    def _quit(self) -> None:
        """退出应用。"""
        logger.info("用户请求退出")
        self.app.quit()

    def update_styles_menu(self, styles: list[dict]) -> None:
        """更新风格切换菜单。"""
        self.style_menu.clear()
        for style in styles:
            action = QAction(f"{style.get('icon', '🍃')} {style.get('name', '未知')}", self.style_menu)
            # TODO: 绑定切换事件
            self.style_menu.addAction(action)


def main() -> None:
    """应用主入口。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(f"{APP_NAME} 启动中...")

    ensure_app_dirs()

    # 检查是否为 Qt 平台插件环境
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，托盘常驻

    # macOS 特定设置
    if sys.platform == "darwin":
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    # 启动系统托盘
    tray = SystemTray(app)

    # 信号处理
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    signal.signal(signal.SIGTERM, lambda sig, frame: app.quit())

    logger.info(f"{APP_NAME} 就绪 — 系统托盘常驻")

    exit_code = app.exec()
    logger.info(f"{APP_NAME} 已退出 (code={exit_code})")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
