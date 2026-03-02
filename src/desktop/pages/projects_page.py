import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


IMAGE_FILE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _projects_dir() -> Path:
    return _repo_root() / "workspace" / "projects"


def _get_project_inputs_dir(project_name: str) -> Path:
    return _projects_dir() / project_name / "inputs"


def _get_project_runs_dir(project_name: str) -> Path:
    return _projects_dir() / project_name / "runs"


NODE_SEQUENCE = [
    "n1c_hybrid_content_writer",
    "n3_browser_capture",
    "n2b_hybrid_slide_generator",
    "n4_tts_synthesizer",
    "n5_ffmpeg_assembler",
]

NODE_LABELS = {
    "n1c_hybrid_content_writer": "N1C 脚本生成",
    "n3_browser_capture": "N3 网页截图",
    "n2b_hybrid_slide_generator": "N2B 幻灯片生成",
    "n4_tts_synthesizer": "N4 语音合成",
    "n5_ffmpeg_assembler": "N5 视频合成",
}


NODE_ALIASES = {
    "n1c_hybrid_content_writer": "n1c_hybrid_content_writer",
    "node 1c": "n1c_hybrid_content_writer",
    "hybrid scriptwriter": "n1c_hybrid_content_writer",
    "n3_browser_capture": "n3_browser_capture",
    "node 3": "n3_browser_capture",
    "browser capture": "n3_browser_capture",
    "n2b_hybrid_slide_generator": "n2b_hybrid_slide_generator",
    "node 2b": "n2b_hybrid_slide_generator",
    "hybrid generator": "n2b_hybrid_slide_generator",
    "n4_tts_synthesizer": "n4_tts_synthesizer",
    "node 4": "n4_tts_synthesizer",
    "tts synthesizer": "n4_tts_synthesizer",
    "n5_ffmpeg_assembler": "n5_ffmpeg_assembler",
    "node 5": "n5_ffmpeg_assembler",
    "ffmpeg assembler": "n5_ffmpeg_assembler",
}


def _parse_meta_file(meta_path: Path) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if not meta_path.is_file():
        return meta

    for line in meta_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        meta[key.strip()] = value.strip()
    return meta


def _extract_node_bracket_text(line: str) -> str:
    match = re.search(r"\[(.*?)\]", line)
    return match.group(1).strip() if match else ""


def _normalize_node_name(raw_text: str) -> Optional[str]:
    lowered = raw_text.strip().lower()
    if not lowered:
        return None
    for alias, canonical in NODE_ALIASES.items():
        if alias in lowered:
            return canonical
    return None


def _detect_node_status(line: str) -> Optional[str]:
    lowered = line.lower()
    if "error" in lowered:
        return "error"
    if any(
        keyword in lowered
        for keyword in [
            "success",
            "successfully",
            "done.",
            "done ",
            "audio ready",
            "finished",
            "complete",
        ]
    ):
        return "complete"
    if any(keyword in lowered for keyword in ["start", "starting"]):
        return "running"
    if "[node" in lowered and "]" in lowered:
        return "running"
    return None


def list_projects() -> List[Dict[str, Any]]:
    """List all projects with their metadata."""
    projects = []
    projects_root = _projects_dir()

    if not projects_root.exists():
        return projects

    for project_path in sorted(projects_root.iterdir()):
        if project_path.is_dir():
            inputs_dir = project_path / "inputs"
            runs_dir = project_path / "runs"

            # Count inputs
            input_count = 0
            if inputs_dir.exists():
                input_count = len([f for f in inputs_dir.iterdir() if f.is_file()])

            # Count runs
            run_count = 0
            if runs_dir.exists():
                run_count = len([d for d in runs_dir.iterdir() if d.is_dir()])

            projects.append(
                {
                    "name": project_path.name,
                    "path": str(project_path),
                    "input_count": input_count,
                    "run_count": run_count,
                    "created": project_path.stat().st_ctime,
                }
            )

    return projects


def create_project(project_name: str) -> Path:
    """Create a new project with standard directory structure."""
    if not project_name or not project_name.strip():
        raise ValueError("Project name is required")

    project_name = project_name.strip()
    project_path = _projects_dir() / project_name

    if project_path.exists():
        raise ValueError(f"Project '{project_name}' already exists")

    # Create directory structure
    (project_path / "inputs").mkdir(parents=True)
    (project_path / "runs").mkdir(parents=True)

    return project_path


def get_project_assets(project_name: str) -> List[Dict[str, Any]]:
    """Get all assets in a project's inputs directory."""
    inputs_dir = _get_project_inputs_dir(project_name)
    assets = []

    if not inputs_dir.exists():
        return assets

    for file_path in sorted(inputs_dir.iterdir()):
        if file_path.is_file():
            stat = file_path.stat()
            assets.append(
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "type": file_path.suffix.lower(),
                }
            )

    return assets


def get_project_runs(project_name: str) -> List[Dict[str, Any]]:
    """Get all runs for a project."""
    runs_dir = _get_project_runs_dir(project_name)
    runs = []

    if not runs_dir.exists():
        return runs

    for run_path in sorted(runs_dir.iterdir(), reverse=True):
        if run_path.is_dir():
            stat = run_path.stat()
            # Check for output
            output_file = run_path / "output.mp4"
            has_output = output_file.exists()

            runs.append(
                {
                    "id": run_path.name,
                    "path": str(run_path),
                    "created": stat.st_ctime,
                    "has_output": has_output,
                }
            )

    return runs


def _is_supported_image_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in IMAGE_FILE_SUFFIXES


def _copy_file_to_inputs_with_dedup(src: Path, inputs_dir: Path) -> Path:
    dst = inputs_dir / src.name
    counter = 1
    while dst.exists():
        dst = inputs_dir / f"{src.stem}_{counter:03d}{src.suffix}"
        counter += 1
    shutil.copy2(src, dst)
    return dst


class ScriptWorkbenchEditor(QTextEdit):
    image_files_dropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _extract_image_paths_from_event(self, event: Any) -> List[str]:
        mime_data = event.mimeData()
        if not mime_data or not mime_data.hasUrls():
            return []

        file_paths: List[str] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_file() and _is_supported_image_file(path):
                file_paths.append(str(path.resolve()))
        return file_paths

    def dragEnterEvent(self, event):
        image_paths = self._extract_image_paths_from_event(event)
        if image_paths:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        image_paths = self._extract_image_paths_from_event(event)
        if image_paths:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        image_paths = self._extract_image_paths_from_event(event)
        if image_paths:
            if hasattr(event, "position"):
                drop_pos = event.position().toPoint()
            else:
                drop_pos = event.pos()
            self.setTextCursor(self.cursorForPosition(drop_pos))
            self.image_files_dropped.emit(image_paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class ProjectWorker(QThread):
    """Background worker for project operations."""

    finished = Signal(bool, str)

    def __init__(self, operation: str, **kwargs):
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        try:
            if self.operation == "create":
                project_name = self.kwargs.get("project_name", "")
                create_project(project_name)
                self.finished.emit(
                    True, f"Project '{project_name}' created successfully"
                )
            elif self.operation == "import_assets":
                project_name = self.kwargs.get("project_name", "")
                file_paths = self.kwargs.get("file_paths", [])
                inputs_dir = _get_project_inputs_dir(project_name)

                imported = 0
                for src_path in file_paths:
                    src = Path(src_path)
                    if src.exists():
                        _copy_file_to_inputs_with_dedup(src, inputs_dir)
                        imported += 1

                self.finished.emit(True, f"Imported {imported} assets")
            else:
                self.finished.emit(False, f"Unknown operation: {self.operation}")
        except Exception as e:
            self.finished.emit(False, str(e))


class PipelineWorker(QThread):
    """Background worker for running the video generation pipeline."""

    progress = Signal(str)  # Log message
    finished = Signal(bool, str)  # success, message
    node_progress = Signal(str, str)  # node_name, status

    def __init__(self, project_name: str, template_id: str = ""):
        super().__init__()
        self.project_name = project_name
        self.template_id = template_id
        self._is_running = True

    def stop(self):
        """Request the pipeline to stop gracefully."""
        self._is_running = False

    def run(self):
        try:
            # Build command
            cmd = [
                sys.executable,
                str(_repo_root() / "src" / "main.py"),
                "--project",
                self.project_name,
            ]

            if self.template_id:
                cmd.extend(["--template-id", self.template_id])

            self.progress.emit(f"Starting pipeline: {' '.join(cmd)}")

            # Run pipeline with real-time output capture
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(_repo_root()),
            )
            stdout_stream = process.stdout
            if stdout_stream is None:
                raise RuntimeError("Failed to capture pipeline stdout.")

            # Parse output for progress
            active_node: Optional[str] = None
            completed_nodes = set()
            errored_nodes = set()

            for line in stdout_stream:
                if not self._is_running:
                    process.terminate()
                    self.finished.emit(False, "Pipeline stopped by user")
                    return

                line = line.strip()
                if line:
                    self.progress.emit(line)

                    # Detect node progress from output
                    if "[Node" in line and "]" in line:
                        bracket_text = _extract_node_bracket_text(line)
                        canonical_node = _normalize_node_name(
                            bracket_text
                        ) or _normalize_node_name(line)
                        status = _detect_node_status(line)
                        if not canonical_node or not status:
                            continue

                        if status == "running":
                            if (
                                active_node
                                and active_node != canonical_node
                                and active_node not in completed_nodes
                                and active_node not in errored_nodes
                            ):
                                completed_nodes.add(active_node)
                                self.node_progress.emit(active_node, "complete")
                            active_node = canonical_node
                            self.node_progress.emit(canonical_node, "running")
                        elif status == "complete":
                            completed_nodes.add(canonical_node)
                            self.node_progress.emit(canonical_node, "complete")
                            if active_node == canonical_node:
                                active_node = None
                        elif status == "error":
                            errored_nodes.add(canonical_node)
                            self.node_progress.emit(canonical_node, "error")
                            if active_node == canonical_node:
                                active_node = None

            process.wait()

            if process.returncode == 0:
                if (
                    active_node
                    and active_node not in completed_nodes
                    and active_node not in errored_nodes
                ):
                    self.node_progress.emit(active_node, "complete")
                self.finished.emit(True, "Pipeline completed successfully")
            else:
                self.finished.emit(
                    False, f"Pipeline failed with exit code {process.returncode}"
                )

        except Exception as e:
            self.finished.emit(False, f"Pipeline error: {str(e)}")


class ProjectsPage(QWidget):
    """Project management page for desktop app."""

    def __init__(self):
        super().__init__()
        self.current_project: Optional[str] = None
        self.worker: Optional[ProjectWorker] = None
        self.pipeline_worker: Optional[PipelineWorker] = None
        self._init_ui()
        self.refresh_projects()

        # Setup auto-refresh timer for runs
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh_runs)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds

        # Setup autosave timer for script editor
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave_script)
        self.autosave_timer.start(10000)  # Autosave every 10 seconds
        self._last_saved_text = ""  # Track last saved content

    def _init_ui(self):
        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        title = QLabel("项目管理")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_projects)

        new_btn = QPushButton("新建项目...")
        new_btn.clicked.connect(self.create_new_project)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_btn)
        header.addWidget(new_btn)

        layout.addLayout(header)

        # Splitter for project list and details
        splitter = QSplitter(Qt.Horizontal)

        # Left: Project list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.projects_table = QTableWidget(0, 4)
        self.projects_table.setHorizontalHeaderLabels(
            ["项目名", "输入素材", "运行次数", "路径"]
        )
        self.projects_table.horizontalHeader().setStretchLastSection(True)
        self.projects_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.projects_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.projects_table.setSelectionMode(QTableWidget.SingleSelection)
        self.projects_table.itemSelectionChanged.connect(self.on_project_selected)
        self.projects_table.itemDoubleClicked.connect(self.on_project_double_clicked)

        left_layout.addWidget(self.projects_table)

        # Right: Project details tabs
        self.details_tabs = QTabWidget()

        # Assets tab
        self.assets_widget = QWidget()
        assets_layout = QVBoxLayout(self.assets_widget)

        assets_header = QHBoxLayout()
        assets_header.addWidget(QLabel("输入素材"))
        assets_header.addStretch()

        import_btn = QPushButton("导入素材...")
        import_btn.clicked.connect(self.import_assets)
        assets_header.addWidget(import_btn)

        assets_layout.addLayout(assets_header)

        self.assets_tree = QTreeWidget()
        self.assets_tree.setHeaderLabels(["文件名", "类型", "大小"])
        self.assets_tree.setColumnWidth(0, 300)
        assets_layout.addWidget(self.assets_tree)

        self.details_tabs.addTab(self.assets_widget, "素材")

        # Runs tab
        self.runs_widget = QWidget()
        runs_layout = QVBoxLayout(self.runs_widget)

        runs_header = QHBoxLayout()
        runs_header.addWidget(QLabel("流程运行记录"))
        runs_header.addStretch()
        runs_layout.addLayout(runs_header)

        self.runs_table = QTableWidget(0, 3)
        self.runs_table.setHorizontalHeaderLabels(["运行 ID", "创建时间", "状态"])
        self.runs_table.horizontalHeader().setStretchLastSection(True)
        runs_layout.addWidget(self.runs_table)

        self.details_tabs.addTab(self.runs_widget, "运行")

        # Script Editor tab
        self.script_widget = QWidget()
        script_layout = QVBoxLayout(self.script_widget)

        script_splitter = QSplitter(Qt.Vertical)

        script_editor_panel = QWidget()
        script_editor_layout = QVBoxLayout(script_editor_panel)
        script_editor_layout.setContentsMargins(0, 0, 0, 0)

        script_header = QHBoxLayout()
        script_header.addWidget(QLabel("脚本写作台"))
        script_header.addStretch()

        insert_image_btn = QPushButton("插入截图...")
        insert_image_btn.clicked.connect(self.insert_script_images)
        script_header.addWidget(insert_image_btn)

        load_script_btn = QPushButton("从文件导入脚本...")
        load_script_btn.clicked.connect(self.load_script_from_file)
        script_header.addWidget(load_script_btn)

        save_script_btn = QPushButton("保存脚本")
        save_script_btn.clicked.connect(self.save_script)
        script_header.addWidget(save_script_btn)

        # Draft status indicator
        self.draft_status_label = QLabel("")
        self.draft_status_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
        script_header.addWidget(self.draft_status_label)

        script_header.addStretch()

        script_editor_layout.addLayout(script_header)

        script_hint = QLabel(
            "可直接把截图拖到编辑区任意段落位置，系统会自动复制到项目 inputs 并插入 [截图:文件名] 标记。\n"
            "运行时会优先参考这些标记顺序来对齐镜头与脚本。"
        )
        script_hint.setWordWrap(True)
        script_hint.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 8px; color: #1f2937; background: #f8fafc;"
        )
        script_editor_layout.addWidget(script_hint)

        self.script_editor = ScriptWorkbenchEditor()
        self.script_editor.image_files_dropped.connect(self.on_script_images_dropped)
        self.script_editor.textChanged.connect(self._update_draft_status)
        self.script_editor.setPlaceholderText(
            "在这里写你的整段视频脚本。\n\n"
            "建议每段讲一个画面，并把截图拖到该段落后方，例如：\n"
            "[截图:step_01.png]"
        )
        self.script_editor.setMinimumHeight(520)
        self.script_editor.setStyleSheet(
            "QTextEdit { font-size: 15px; line-height: 1.55; padding: 12px; "
            "border: 1px solid #cbd5e1; border-radius: 10px; background: #fefefe; color: #1f2937; }"
        )
        script_editor_layout.addWidget(self.script_editor)

        # Script metadata form
        script_meta = QGroupBox("脚本参数")
        script_meta_layout = QFormLayout()

        self.duration_input = QLineEdit("1.5")
        self.duration_input.setPlaceholderText("视频时长（分钟）")
        script_meta_layout.addRow("时长（分钟）:", self.duration_input)

        self.audience_input = QLineEdit()
        self.audience_input.setPlaceholderText("目标受众描述")
        script_meta_layout.addRow("目标受众:", self.audience_input)

        self.template_input = QLineEdit("tech_burst")
        self.template_input.setPlaceholderText("PPT 模板 ID")
        script_meta_layout.addRow("模板 ID:", self.template_input)

        script_meta.setLayout(script_meta_layout)
        script_editor_layout.addWidget(script_meta)

        script_splitter.addWidget(script_editor_panel)

        # Pipeline Run Control
        pipeline_control = QGroupBox("流程执行")
        pipeline_layout = QVBoxLayout()

        pipeline_btn_layout = QHBoxLayout()
        self.run_pipeline_btn = QPushButton("运行流程")
        self.run_pipeline_btn.setStyleSheet(
            "QPushButton { background-color: #0f766e; color: white; font-weight: bold; padding: 8px; }"
        )
        self.run_pipeline_btn.clicked.connect(self.run_pipeline)

        self.stop_pipeline_btn = QPushButton("停止")
        self.stop_pipeline_btn.clicked.connect(self.stop_pipeline)
        self.stop_pipeline_btn.setEnabled(False)

        pipeline_btn_layout.addWidget(self.run_pipeline_btn)
        pipeline_btn_layout.addWidget(self.stop_pipeline_btn)
        pipeline_btn_layout.addStretch()

        # Progress bar
        self.pipeline_progress = QProgressBar()
        self.pipeline_progress.setRange(0, 5)  # 5 nodes
        self.pipeline_progress.setValue(0)
        self.pipeline_progress.setTextVisible(True)
        self.pipeline_progress.setFormat("就绪")

        # Log viewer
        self.pipeline_log = QPlainTextEdit()
        self.pipeline_log.setPlaceholderText("流程日志会显示在这里...")
        self.pipeline_log.setMaximumBlockCount(1000)  # Keep last 1000 lines
        self.pipeline_log.setReadOnly(True)

        pipeline_layout.addLayout(pipeline_btn_layout)
        pipeline_layout.addWidget(self.pipeline_progress)
        pipeline_layout.addWidget(QLabel("流程日志："))
        pipeline_layout.addWidget(self.pipeline_log)
        pipeline_control.setLayout(pipeline_layout)

        script_splitter.addWidget(pipeline_control)
        script_splitter.setSizes([640, 260])

        script_layout.addWidget(script_splitter)

        self.details_tabs.addTab(self.script_widget, "脚本")

        # Add tabs to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(self.details_tabs)
        splitter.setSizes([320, 980])

        layout.addWidget(splitter)

        # Status bar
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def refresh_projects(self):
        """Refresh the project list."""
        projects = list_projects()

        self.projects_table.setRowCount(len(projects))
        for row, project in enumerate(projects):
            name_item = QTableWidgetItem(project["name"])
            name_item.setData(Qt.UserRole, project["name"])  # Store project name

            self.projects_table.setItem(row, 0, name_item)
            self.projects_table.setItem(
                row, 1, QTableWidgetItem(str(project["input_count"]))
            )
            self.projects_table.setItem(
                row, 2, QTableWidgetItem(str(project["run_count"]))
            )

            path_item = QTableWidgetItem(project["path"])
            path_item.setToolTip(project["path"])
            self.projects_table.setItem(row, 3, path_item)

        self.status_label.setText(f"共找到 {len(projects)} 个项目")

    def on_project_selected(self):
        """Handle project selection change."""
        selected = self.projects_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        project_item = self.projects_table.item(row, 0)
        if project_item is None:
            return
        project_name = project_item.data(Qt.UserRole)
        if not isinstance(project_name, str):
            return
        self.current_project = project_name

        self.load_project_details(project_name)

    def on_project_double_clicked(self, item):
        """Handle double click on project."""
        row = item.row()
        project_item = self.projects_table.item(row, 0)
        if project_item is None:
            return
        project_name = project_item.data(Qt.UserRole)
        if not isinstance(project_name, str):
            return
        self.current_project = project_name

        # Switch to script tab
        self.details_tabs.setCurrentIndex(2)  # Script tab
        self.load_project_details(project_name)

    def load_project_details(self, project_name: str):
        """Load details for the selected project."""
        self.status_label.setText(f"正在加载项目：{project_name}")

        assets = self._populate_assets_tree(project_name)
        runs = self._populate_runs_table(project_name)

        # Load script if exists
        script_path = _get_project_inputs_dir(project_name) / "script.txt"
        if script_path.exists():
            self.script_editor.setPlainText(script_path.read_text(encoding="utf-8"))
            self._last_saved_text = self.script_editor.toPlainText()
        else:
            self.script_editor.clear()
            self._last_saved_text = ""

        # Check for draft recovery
        self._check_for_draft_recovery()

        meta_path = _get_project_inputs_dir(project_name) / "meta.txt"
        meta = _parse_meta_file(meta_path)
        self.duration_input.setText(meta.get("duration_mins", "1.5"))
        self.audience_input.setText(meta.get("target_audience", ""))
        self.template_input.setText(meta.get("template_id", "tech_burst"))

        self.status_label.setText(
            f"项目：{project_name} | 资产 {len(assets)} 个 | 运行记录 {len(runs)} 条"
        )

    def _populate_assets_tree(self, project_name: str) -> List[Dict[str, Any]]:
        """Refresh assets tree for selected project only."""
        self.assets_tree.clear()
        assets = get_project_assets(project_name)
        for asset in assets:
            size_kb = asset["size"] / 1024
            size_str = (
                f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
            )

            item = QTreeWidgetItem(
                [
                    asset["name"],
                    asset["type"].upper() if asset["type"] else "未知",
                    size_str,
                ]
            )
            item.setToolTip(0, asset["path"])
            self.assets_tree.addTopLevelItem(item)
        return assets

    def _populate_runs_table(self, project_name: str) -> List[Dict[str, Any]]:
        """Refresh runs table for selected project only."""
        self.runs_table.setRowCount(0)
        runs = get_project_runs(project_name)
        self.runs_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            created = datetime.fromtimestamp(run["created"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            status = "已完成" if run["has_output"] else "进行中"

            self.runs_table.setItem(row, 0, QTableWidgetItem(run["id"]))
            self.runs_table.setItem(row, 1, QTableWidgetItem(created))
            self.runs_table.setItem(row, 2, QTableWidgetItem(status))
        return runs

    def create_new_project(self):
        """Show dialog to create a new project."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "新建项目", "项目名称：")

        if ok and name:
            self._run_worker("create", project_name=name)

    def insert_script_images(self):
        """Insert screenshots into script area and project inputs."""
        if not self.current_project:
            QMessageBox.warning(self, "未选择项目", "请先选择项目，再插入截图。")
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择截图",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All Files (*)",
        )
        if file_paths:
            self._import_images_to_script(file_paths)

    def on_script_images_dropped(self, file_paths: List[str]):
        """Handle screenshot files dropped into script editor."""
        if not self.current_project:
            QMessageBox.warning(
                self,
                "请先选择项目",
                "需要先在左侧选中项目，才能把截图拖到脚本里。",
            )
            return
        self._import_images_to_script(file_paths)

    def _import_images_to_script(self, file_paths: List[str]) -> None:
        """Copy image files to project inputs and insert markers in script."""
        if not self.current_project:
            return

        inputs_dir = _get_project_inputs_dir(self.current_project)
        imported_files: List[Path] = []

        for src_path in file_paths:
            src = Path(src_path)
            if not src.is_file() or not _is_supported_image_file(src):
                continue
            dst = _copy_file_to_inputs_with_dedup(src, inputs_dir)
            imported_files.append(dst)

        if not imported_files:
            QMessageBox.warning(self, "没有可导入截图", "仅支持常见图片格式。")
            return

        cursor = self.script_editor.textCursor()
        if not self.script_editor.toPlainText().endswith("\n"):
            cursor.insertText("\n")

        for file_path in imported_files:
            cursor.insertText(f"[截图:{file_path.name}]\n")

        self.script_editor.setTextCursor(cursor)
        self.refresh_projects()
        self._populate_assets_tree(self.current_project)
        self.status_label.setText(
            f"已插入 {len(imported_files)} 张截图标记，可继续在段落间拖拽排布。"
        )

    def import_assets(self):
        """Import assets into the current project."""
        if not self.current_project:
            QMessageBox.warning(self, "未选择项目", "请先选择项目")
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入素材",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All Files (*)",
        )

        if file_paths:
            self._run_worker(
                "import_assets",
                project_name=self.current_project,
                file_paths=file_paths,
            )

    def load_script_from_file(self):
        """Load script from a file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入脚本文件",
            "",
            "Text Files (*.txt);;Markdown (*.md);;All Files (*)",
        )

        if file_path:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                self.script_editor.setPlainText(content)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取文件失败：{e}")

    def _update_draft_status(self) -> None:
        """Update the draft status indicator when text changes."""
        if not self.current_project:
            return
        current_text = self.script_editor.toPlainText()
        if current_text != self._last_saved_text:
            self.draft_status_label.setText("● 未保存")
        else:
            self.draft_status_label.setText("")

    def _get_draft_path(self) -> Optional[Path]:
        """Get the path to the draft file for current project."""
        if not self.current_project:
            return None
        return _get_project_inputs_dir(self.current_project) / ".script.draft.txt"

    def _autosave_script(self) -> None:
        """Autosave script to draft file every 10 seconds."""
        if not self.current_project:
            return

        current_text = self.script_editor.toPlainText()
        if not current_text or current_text == self._last_saved_text:
            return  # No content or no changes

        try:
            draft_path = self._get_draft_path()
            if draft_path:
                draft_path.write_text(current_text, encoding="utf-8")
                self._last_saved_text = current_text
                # Update status bar briefly
                original_text = self.status_label.text()
                if "草稿" not in original_text:
                    self.status_label.setText(f"{original_text} (草稿已自动保存)")
                    # Reset after 3 seconds
                    QTimer.singleShot(
                        3000, lambda: self.status_label.setText(original_text)
                    )
        except Exception:
            pass  # Silent fail for autosave

    def _check_for_draft_recovery(self) -> None:
        """Check if there's a draft file and offer to restore it."""
        if not self.current_project:
            return

        draft_path = self._get_draft_path()
        script_path = _get_project_inputs_dir(self.current_project) / "script.txt"

        if not draft_path or not draft_path.exists():
            return

        # Check if draft is newer than saved script
        draft_mtime = draft_path.stat().st_mtime
        script_mtime = script_path.stat().st_mtime if script_path.exists() else 0

        if draft_mtime > script_mtime:
            reply = QMessageBox.question(
                self,
                "发现草稿",
                f"发现未保存的草稿（{datetime.fromtimestamp(draft_mtime).strftime('%H:%M:%S')}），\n"
                "是否恢复草稿内容？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    draft_content = draft_path.read_text(encoding="utf-8")
                    self.script_editor.setPlainText(draft_content)
                    self._last_saved_text = draft_content
                    self.status_label.setText("已恢复草稿内容")
                except Exception as e:
                    QMessageBox.warning(self, "恢复失败", f"无法读取草稿：{e}")
            else:
                # User chose not to restore, delete the draft
                try:
                    draft_path.unlink()
                except Exception:
                    pass

    def save_script(self, show_message: bool = True) -> bool:
        """Save the current script to the project."""
        if not self.current_project:
            QMessageBox.warning(self, "未选择项目", "请先选择项目")
            return False

        try:
            script_path = _get_project_inputs_dir(self.current_project) / "script.txt"
            content = self.script_editor.toPlainText()
            script_path.write_text(content, encoding="utf-8")
            self._last_saved_text = content

            # Clear draft after successful save
            draft_path = self._get_draft_path()
            if draft_path and draft_path.exists():
                try:
                    draft_path.unlink()
                except Exception:
                    pass
            self.draft_status_label.setText("")  # Clear unsaved indicator

            # Save metadata
            meta_path = _get_project_inputs_dir(self.current_project) / "meta.txt"
            meta_lines = [
                f"duration_mins={self.duration_input.text()}",
                f"target_audience={self.audience_input.text()}",
                f"template_id={self.template_input.text()}",
            ]
            meta_path.write_text("\n".join(meta_lines), encoding="utf-8")

            if show_message:
                QMessageBox.information(self, "保存成功", "脚本已保存")
            self.refresh_projects()
            return True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败：{e}")
            return False

    def _run_worker(self, operation: str, **kwargs):
        """Run a background worker operation."""
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "忙碌中", "当前已有操作在执行，请稍后。")
            return

        self.worker = ProjectWorker(operation, **kwargs)
        self.worker.finished.connect(self._on_worker_finished)
        self.status_label.setText(f"正在执行：{operation}...")
        self.worker.start()

    def _on_worker_finished(self, success: bool, message: str):
        """Handle worker completion."""
        if success:
            self.status_label.setText(message)
            self.refresh_projects()
            if self.current_project:
                self.load_project_details(self.current_project)
        else:
            self.status_label.setText(f"错误：{message}")
            QMessageBox.critical(self, "错误", message)

    # Pipeline methods
    def run_pipeline(self):
        """Start the video generation pipeline for the current project."""
        if not self.current_project:
            QMessageBox.warning(self, "未选择项目", "请先选择项目")
            return

        # Save script first
        if not self.save_script(show_message=False):
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "运行流程",
            f"确认开始为项目 '{self.current_project}' 生成视频吗？\n\n"
            "流程包括：\n"
            "1. AI 生成内容\n"
            "2. 生成幻灯片\n"
            "3. 合成语音\n"
            "4. 合成最终视频\n\n"
            "整个过程可能需要几分钟。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Clear log and reset progress
        self.pipeline_log.clear()
        self.pipeline_progress.setValue(0)
        self.pipeline_progress.setFormat("启动中...")

        # Update UI state
        self.run_pipeline_btn.setEnabled(False)
        self.stop_pipeline_btn.setEnabled(True)
        self.status_label.setText("流程运行中...")

        # Start pipeline worker
        template_id = self.template_input.text().strip()
        self.pipeline_worker = PipelineWorker(self.current_project, template_id)
        self.pipeline_worker.progress.connect(self._on_pipeline_progress)
        self.pipeline_worker.node_progress.connect(self._on_node_progress)
        self.pipeline_worker.finished.connect(self._on_pipeline_finished)
        self.pipeline_worker.start()

    def stop_pipeline(self):
        """Stop the running pipeline."""
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.pipeline_worker.stop()
            self._on_pipeline_progress("正在停止流程...")
            self.stop_pipeline_btn.setEnabled(False)

    def _on_pipeline_progress(self, message: str):
        """Handle pipeline log message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.pipeline_log.appendPlainText(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        scrollbar = self.pipeline_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_node_progress(self, node_name: str, status: str):
        """Handle node status update."""
        node_progress = {name: idx + 1 for idx, name in enumerate(NODE_SEQUENCE)}
        node_label = NODE_LABELS.get(node_name, node_name)

        if status == "running":
            self.pipeline_progress.setFormat(f"运行中：{node_label}")
        elif status == "complete":
            progress = node_progress.get(node_name, 0)
            self.pipeline_progress.setValue(progress)
            self.pipeline_progress.setFormat(f"已完成：{node_label}")
        elif status == "error":
            self.pipeline_progress.setFormat(f"异常：{node_label}")

    def _on_pipeline_finished(self, success: bool, message: str):
        """Handle pipeline completion."""
        self.run_pipeline_btn.setEnabled(True)
        self.stop_pipeline_btn.setEnabled(False)

        if success:
            self.pipeline_progress.setValue(5)
            self.pipeline_progress.setFormat("已完成")
            self.status_label.setText(f"流程完成：{message}")
            self._on_pipeline_progress(f"成功：{message}")
            QMessageBox.information(self, "流程完成", message)
        else:
            self.pipeline_progress.setFormat("失败")
            self.status_label.setText(f"流程失败：{message}")
            self._on_pipeline_progress(f"失败：{message}")
            QMessageBox.critical(self, "流程失败", message)

        # Refresh runs list
        if self.current_project:
            self.load_project_details(self.current_project)

    def _auto_refresh_runs(self):
        """Auto-refresh runs list every few seconds if pipeline is running."""
        if (
            self.current_project
            and self.pipeline_worker
            and self.pipeline_worker.isRunning()
        ):
            self.load_project_details(self.current_project)
