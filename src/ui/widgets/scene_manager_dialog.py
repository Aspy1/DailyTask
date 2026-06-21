"""场景管理对话框 - 场景切换、存档管理"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QLineEdit,
    QDialogButtonBox, QMessageBox, QComboBox, QGroupBox,
    QFormLayout,
)
from PySide6.QtGui import QFont, QColor, QBrush

from src.models.scene_archive import SceneArchive
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_BODY_S, SIZE_BODY, SIZE_SUBTITLE


class SceneManagerDialog(QDialog):
    """场景管理对话框"""

    scene_switched = Signal(str)  # 切换场景时发出

    def __init__(self, scene_archive: SceneArchive, parent=None):
        super().__init__(parent)
        self._archive = scene_archive
        c = get_colors()

        self.setWindowTitle("场景管理")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c['bg_card']};
                color: {c['fg_primary']};
            }}
            QLabel {{
                color: {c['fg_primary']};
                background: transparent;
            }}
            QListWidget {{
                background-color: {c['bg_input']};
                color: {c['fg_primary']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {c['accent_bg']};
            }}
            QPushButton {{
                background-color: {c['accent']};
                color: #fff;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {c['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {c['accent_dim']};
            }}
            QLineEdit, QComboBox {{
                background-color: {c['bg_input']};
                color: {c['fg_primary']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel("场景管理")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE, 600))
        layout.addWidget(title)

        # 当前场景
        current = self._archive.get_current_scene()
        current_label = QLabel(f"当前场景：{current.get('name', '未知')}")
        current_label.setStyleSheet(f"font-size: 14px; font-weight: 500;")
        layout.addWidget(current_label)

        # 场景列表
        self._scene_list = QListWidget()
        self._refresh_scene_list()
        self._scene_list.itemDoubleClicked.connect(self._on_scene_double_clicked)
        layout.addWidget(self._scene_list)

        # 快速创建
        quick_group = QGroupBox("快速创建")
        quick_layout = QHBoxLayout()

        self._year_input = QLineEdit()
        self._year_input.setPlaceholderText("年份")
        self._year_input.setFixedWidth(80)
        self._year_input.setText(str(2024))
        quick_layout.addWidget(self._year_input)

        self._semester_combo = QComboBox()
        self._semester_combo.addItems(["上学期", "下学期"])
        quick_layout.addWidget(self._semester_combo)

        create_sem_btn = QPushButton("创建学期")
        create_sem_btn.clicked.connect(self._create_semester)
        quick_layout.addWidget(create_sem_btn)

        quick_layout.addSpacing(16)

        self._location_input = QLineEdit()
        self._location_input.setPlaceholderText("位置名称")
        self._location_input.setFixedWidth(100)
        quick_layout.addWidget(self._location_input)

        create_loc_btn = QPushButton("创建位置")
        create_loc_btn.clicked.connect(self._create_location)
        quick_layout.addWidget(create_loc_btn)

        quick_layout.addStretch()
        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)

        # 位置设置（经纬度）
        loc_group = QGroupBox("位置设置（用于天气预报）")
        loc_layout = QHBoxLayout()

        self._lat_edit = QLineEdit()
        self._lat_edit.setPlaceholderText("如: 31.23")
        self._lat_edit.setFixedWidth(100)
        loc_layout.addWidget(QLabel("纬度:"))
        loc_layout.addWidget(self._lat_edit)

        self._lon_edit = QLineEdit()
        self._lon_edit.setPlaceholderText("如: 121.47")
        self._lon_edit.setFixedWidth(100)
        loc_layout.addWidget(QLabel("经度:"))
        loc_layout.addWidget(self._lon_edit)

        save_loc_btn = QPushButton("保存位置")
        save_loc_btn.clicked.connect(self._save_location)
        loc_layout.addWidget(save_loc_btn)

        loc_layout.addStretch()
        loc_group.setLayout(loc_layout)
        layout.addWidget(loc_group)

        # 加载当前位置
        self._load_location()

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_location(self) -> None:
        """加载当前位置"""
        loc = self._archive.get_location()
        self._lat_edit.setText(str(loc["lat"]))
        self._lon_edit.setText(str(loc["lon"]))

    def _save_location(self) -> None:
        """保存位置"""
        try:
            lat = float(self._lat_edit.text().strip())
            lon = float(self._lon_edit.text().strip())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("经纬度超出范围")
            self._archive.set_location(lat, lon)
            QMessageBox.information(self, "保存成功", f"位置已保存：{lat}°N, {lon}°E")
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的经纬度数字\n纬度: -90~90\n经度: -180~180")

    def _refresh_scene_list(self) -> None:
        """刷新场景列表"""
        self._scene_list.clear()
        scenes = self._archive.list_scenes()
        current_id = self._archive.get_current_scene_id()

        for scene in scenes:
            scene_id = scene.get("id", "")
            name = scene.get("name", "未知")
            scene_type = scene.get("scene_type", "")
            is_active = (scene_id == current_id)

            type_text = {"semester": "学期", "location": "位置"}.get(scene_type, scene_type)
            display_text = f"{name} [{type_text}]"
            if is_active:
                display_text += " ✓"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, scene_id)
            if is_active:
                # 使用 QColor 设置背景色
                bg_color = QColor(176, 130, 58, 20)  # accent_bg 的近似颜色
                item.setBackground(QBrush(bg_color))
            self._scene_list.addItem(item)

    def _create_semester(self) -> None:
        """创建学期场景"""
        try:
            year = int(self._year_input.text())
            semester = self._semester_combo.currentIndex() + 1
            scene_id = self._archive.quick_create_semester(year, semester)
            self._refresh_scene_list()
            QMessageBox.information(self, "创建成功", f"已创建学期场景")
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的年份")

    def _create_location(self) -> None:
        """创建位置场景"""
        location = self._location_input.text().strip()
        if not location:
            QMessageBox.warning(self, "输入错误", "请输入位置名称")
            return
        scene_id = self._archive.quick_create_location(location)
        self._refresh_scene_list()
        QMessageBox.information(self, "创建成功", f"已创建位置场景：{location}")

    def _on_scene_double_clicked(self, item: QListWidgetItem) -> None:
        """双击切换场景"""
        scene_id = item.data(Qt.ItemDataRole.UserRole)
        if scene_id == self._archive.get_current_scene_id():
            return

        reply = QMessageBox.question(
            self,
            "确认切换",
            "切换场景将保存当前数据并加载新场景数据。\n确定要切换吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._archive.switch_scene(scene_id):
                self.scene_switched.emit(scene_id)
                self.accept()
            else:
                QMessageBox.warning(self, "切换失败", "场景切换失败")

    def get_selected_scene_id(self) -> str | None:
        """获取选中的场景 ID"""
        current_item = self._scene_list.currentItem()
        if current_item:
            return current_item.data(Qt.ItemDataRole.UserRole)
        return None
