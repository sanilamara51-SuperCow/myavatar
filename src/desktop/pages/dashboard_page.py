from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout()
        title = QLabel("Myavatar Desktop")
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        subtitle = QLabel(
            "Desktop control panel for provider routing, persona voice presets, "
            "and upcoming project asset/progress workflows."
        )
        subtitle.setStyleSheet("font-size: 14px; color: #4b5563;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
        self.setLayout(layout)
