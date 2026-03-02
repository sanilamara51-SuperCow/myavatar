from PySide6.QtWidgets import QMainWindow, QTabWidget

from desktop.pages.dashboard_page import DashboardPage
from desktop.pages.persona_page import PersonaPage
from desktop.pages.projects_page import ProjectsPage
from desktop.pages.provider_page import ProviderPage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Myavatar 桌面控制台")
        self.resize(1280, 820)

        tabs = QTabWidget()
        tabs.addTab(DashboardPage(), "概览")
        tabs.addTab(ProjectsPage(), "项目管理")
        tabs.addTab(ProviderPage(), "模型供应商")
        tabs.addTab(PersonaPage(), "人设音色")

        self.setCentralWidget(tabs)
