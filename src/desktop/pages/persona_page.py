import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from storage.persona_registry import get_persona, list_personas, upsert_persona
from utils.tts_client import load_cosyvoice_config_from_env, synthesize_text_mock

# Try to import cosyvoice synthesis, fallback to mock if not available
try:
    from utils.tts_client import synthesize_text_cosyvoice

    HAS_COSYVOICE = True
except ImportError:
    synthesize_text_cosyvoice = None
    HAS_COSYVOICE = False

COSYVOICE_MODES = ["zero_shot", "sft", "cross_lingual", "instruct", "instruct2"]
SUPPORTED_AUDIO_FORMATS = ["wav", "mp3", "flac"]


def _set_cell(table: QTableWidget, row: int, col: int, value: Any) -> None:
    item = QTableWidgetItem("" if value is None else str(value))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    table.setItem(row, col, item)


class TTSSynthesisWorker(QThread):
    """Background worker for TTS synthesis."""

    finished = Signal(bool, str, str)  # success, message, audio_path

    def __init__(self, text: str, persona_id: str, output_path: str):
        super().__init__()
        self.text = text
        self.persona_id = persona_id
        self.output_path = output_path

    def run(self):
        try:
            # Get persona config
            persona = get_persona(self.persona_id)
            if not persona:
                self.finished.emit(False, f"Persona '{self.persona_id}' not found", "")
                return

            # Check audio source mode
            audio_mode = (os.getenv("AUDIO_SOURCE_MODE") or "mock").strip().lower()

            if audio_mode == "mock":
                # Use mock TTS
                duration = asyncio.run(
                    synthesize_text_mock(self.text, self.output_path)
                )
                self.finished.emit(
                    True, f"Mock audio generated: {duration:.2f}s", self.output_path
                )
            elif audio_mode == "cosyvoice":
                # Use CosyVoice
                if not HAS_COSYVOICE or synthesize_text_cosyvoice is None:
                    self.finished.emit(False, "CosyVoice support not available", "")
                    return

                config = load_cosyvoice_config_from_env()
                # Update config with persona settings
                if persona.get("voice"):
                    config.voice = persona["voice"]
                if persona.get("cosyvoice_mode"):
                    config.mode = persona["cosyvoice_mode"]
                if persona.get("prompt_text"):
                    config.prompt_text = persona["prompt_text"]
                if persona.get("prompt_wav_path"):
                    config.prompt_wav_path = persona["prompt_wav_path"]
                if persona.get("instruct_text"):
                    config.instruct_text = persona["instruct_text"]

                duration = asyncio.run(
                    synthesize_text_cosyvoice(self.text, self.output_path, config)
                )
                self.finished.emit(
                    True, f"Audio synthesized: {duration:.2f}s", self.output_path
                )
            else:
                self.finished.emit(False, f"Unsupported audio mode: {audio_mode}", "")

        except Exception as e:
            self.finished.emit(False, str(e), "")


class PersonaPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.tts_worker: Optional[TTSSynthesisWorker] = None
        self.media_player: QMediaPlayer = QMediaPlayer(self)
        self.audio_output: QAudioOutput = QAudioOutput(self)
        self.current_audio_path: Optional[str] = None

        self._init_ui()
        self._init_media_player()
        self.reload_data()

    def _init_media_player(self):
        """Initialize media player for audio playback."""
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.errorOccurred.connect(self._on_media_error)

    def _on_media_error(self, error, error_string):
        """Handle media player errors."""
        self._set_status(f"播放失败：{error_string}", ok=False)

    def select_prompt_wav_file(self):
        """Select prompt wav/audio file for current persona form."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择声音文件",
            "",
            "音频文件 (*.wav *.mp3 *.flac);;所有文件 (*)",
        )
        if not file_path:
            return

        normalized_path = str(Path(file_path).resolve())
        self.prompt_wav_input.setText(normalized_path)
        self._set_status(f"已选择声音文件：{Path(normalized_path).name}", ok=True)

    def _init_ui(self):
        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        title = QLabel("人设音色管理")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.reload_data)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_btn)

        # Persona table
        self.table = QTableWidget(0, 13)  # Added action column
        self.table.setHorizontalHeaderLabels(
            [
                "人设 ID",
                "名称",
                "模式",
                "音色",
                "参考音频路径",
                "提示词",
                "指令词",
                "音频格式",
                "采样率",
                "语速",
                "默认停顿(ms)",
                "启用",
                "操作",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(12, 100)  # Action column
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # Preview section
        preview_box = QGroupBox("音色试听")
        preview_layout = QVBoxLayout()

        preview_form = QHBoxLayout()
        preview_form.addWidget(QLabel("试听文本："))
        self.preview_text_input = QTextEdit()
        self.preview_text_input.setPlaceholderText("输入要试听的文本...")
        self.preview_text_input.setMaximumHeight(80)
        preview_form.addWidget(self.preview_text_input)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.preview_btn = QPushButton("合成试听")
        self.preview_btn.clicked.connect(self.preview_selected_persona)
        self.preview_btn.setEnabled(False)

        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self.play_audio)
        self.play_btn.setEnabled(False)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_audio)
        self.stop_btn.setEnabled(False)

        self.pick_audio_btn = QPushButton("选择声音文件...")
        self.pick_audio_btn.clicked.connect(self.select_prompt_wav_file)

        btn_layout.addWidget(self.preview_btn)
        btn_layout.addWidget(self.play_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.pick_audio_btn)
        btn_layout.addStretch()

        preview_layout.addLayout(preview_form)
        preview_layout.addLayout(btn_layout)
        preview_box.setLayout(preview_layout)

        # Form for add/update
        form_box = QGroupBox("新增 / 更新人设")
        form_layout = QFormLayout()
        self.persona_id_input = QLineEdit("host")
        self.name_input = QLineEdit("主持人")
        self.mode_input = QComboBox()
        self.mode_input.addItems(COSYVOICE_MODES)
        self.voice_input = QLineEdit("")
        self.prompt_wav_input = QLineEdit("")
        self.prompt_text_input = QLineEdit("")
        self.instruct_text_input = QLineEdit("")
        self.audio_format_input = QComboBox()
        self.audio_format_input.addItems(SUPPORTED_AUDIO_FORMATS)
        self.sample_rate_input = QLineEdit("22050")
        self.base_speed_input = QLineEdit("1.0")
        self.pause_input = QLineEdit("260")
        self.enabled_input = QCheckBox()
        self.enabled_input.setChecked(True)

        save_btn = QPushButton("保存人设")
        save_btn.clicked.connect(self.save_persona)

        prompt_wav_row = QWidget()
        prompt_wav_layout = QHBoxLayout(prompt_wav_row)
        prompt_wav_layout.setContentsMargins(0, 0, 0, 0)
        prompt_wav_layout.setSpacing(8)
        prompt_wav_layout.addWidget(self.prompt_wav_input)

        select_prompt_wav_btn = QPushButton("浏览...")
        select_prompt_wav_btn.clicked.connect(self.select_prompt_wav_file)
        prompt_wav_layout.addWidget(select_prompt_wav_btn)

        form_layout.addRow("人设 ID", self.persona_id_input)
        form_layout.addRow("名称", self.name_input)
        form_layout.addRow("CosyVoice 模式", self.mode_input)
        form_layout.addRow("音色", self.voice_input)
        form_layout.addRow("参考音频文件", prompt_wav_row)
        form_layout.addRow("提示词", self.prompt_text_input)
        form_layout.addRow("指令词", self.instruct_text_input)
        form_layout.addRow("音频格式", self.audio_format_input)
        form_layout.addRow("采样率", self.sample_rate_input)
        form_layout.addRow("语速", self.base_speed_input)
        form_layout.addRow("默认停顿(ms)", self.pause_input)
        form_layout.addRow("启用", self.enabled_input)

        prompt_wav_hint = QLabel(
            "提示：zero_shot / cross_lingual / instruct2 模式通常需要参考音频；推荐使用绝对路径。"
        )
        prompt_wav_hint.setWordWrap(True)
        prompt_wav_hint.setStyleSheet("color: #4b5563;")
        form_layout.addRow(prompt_wav_hint)
        form_layout.addRow(save_btn)
        form_box.setLayout(form_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #0f766e;")

        add_audio_guide = QLabel(
            "新增声音文件入口：在下方“新增 / 更新人设”的“参考音频文件”里点击“浏览...”。"
        )
        add_audio_guide.setWordWrap(True)
        add_audio_guide.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 8px; color: #111827;"
        )

        layout.addLayout(header)
        layout.addWidget(self.table)
        layout.addWidget(add_audio_guide)
        layout.addWidget(preview_box)
        layout.addWidget(form_box)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def _set_status(self, message: str, ok: bool) -> None:
        color = "#0f766e" if ok else "#b91c1c"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)

    def _get_selected_persona_id(self) -> Optional[str]:
        """Get the persona_id of the currently selected row."""
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.table.item(row, 0)
        if item:
            return item.text()
        return None

    def _add_preview_button(self, row: int, persona_id: str):
        """Add a preview button to the actions column."""
        btn = QPushButton("试听")
        btn.clicked.connect(lambda: self._on_preview_button_clicked(persona_id))
        self.table.setCellWidget(row, 12, btn)

    def _on_preview_button_clicked(self, persona_id: str):
        """Handle preview button click."""
        # Select the row
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == persona_id:
                self.table.selectRow(row)
                break

        # Set default preview text if empty
        if not self.preview_text_input.toPlainText().strip():
            self.preview_text_input.setPlainText(
                f"你好，这是一段 {persona_id} 人设音色的试听文本。"
            )

        self.preview_selected_persona()

    def reload_data(self) -> None:
        personas: List[Dict[str, Any]] = list_personas()
        self.table.setRowCount(len(personas))
        for row, persona in enumerate(personas):
            _set_cell(self.table, row, 0, persona.get("persona_id"))
            _set_cell(self.table, row, 1, persona.get("name"))
            _set_cell(self.table, row, 2, persona.get("cosyvoice_mode"))
            _set_cell(self.table, row, 3, persona.get("voice"))
            _set_cell(self.table, row, 4, persona.get("prompt_wav_path"))
            _set_cell(self.table, row, 5, persona.get("prompt_text"))
            _set_cell(self.table, row, 6, persona.get("instruct_text"))
            _set_cell(self.table, row, 7, persona.get("audio_format"))
            _set_cell(self.table, row, 8, persona.get("sample_rate"))
            _set_cell(self.table, row, 9, persona.get("base_speed"))
            _set_cell(self.table, row, 10, persona.get("default_pause_ms"))
            _set_cell(self.table, row, 11, persona.get("enabled"))
            self._add_preview_button(row, persona.get("persona_id", ""))

        self._on_selection_changed()

    def _on_selection_changed(self):
        """Handle table selection change."""
        has_selection = self._get_selected_persona_id() is not None
        self.preview_btn.setEnabled(has_selection)

    def preview_selected_persona(self):
        """Synthesize audio for the selected persona."""
        persona_id = self._get_selected_persona_id()
        if not persona_id:
            QMessageBox.warning(self, "未选择人设", "请先在表格中选择一个人设再试听")
            return

        text = self.preview_text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "缺少文本", "请输入要合成试听的文本")
            return

        # Create temp file for audio output
        temp_dir = tempfile.gettempdir()
        audio_path = os.path.join(temp_dir, f"myavatar_preview_{persona_id}.wav")

        # Disable buttons during synthesis
        self.preview_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self._set_status(f"正在为 '{persona_id}' 合成试听音频...", ok=True)

        # Start worker thread
        self.tts_worker = TTSSynthesisWorker(text, persona_id, audio_path)
        self.tts_worker.finished.connect(self._on_tts_finished)
        self.tts_worker.start()

    def _on_tts_finished(self, success: bool, message: str, audio_path: str):
        """Handle TTS synthesis completion."""
        self.preview_btn.setEnabled(True)

        if success:
            self.current_audio_path = audio_path
            self.play_btn.setEnabled(True)
            self._set_status(f"{message}。点击“播放”即可试听。", ok=True)
        else:
            self._set_status(f"合成失败：{message}", ok=False)
            QMessageBox.critical(self, "合成失败", message)

    def play_audio(self):
        """Play the synthesized audio."""
        if not self.current_audio_path or not os.path.exists(self.current_audio_path):
            QMessageBox.warning(
                self, "没有可播放音频", "请先合成试听音频，再点击播放。"
            )
            return

        from PySide6.QtCore import QUrl

        url = QUrl.fromLocalFile(self.current_audio_path)
        self.media_player.setSource(url)
        self.media_player.play()
        self.stop_btn.setEnabled(True)
        self._set_status("正在播放音频...", ok=True)

    def stop_audio(self):
        """Stop audio playback."""
        self.media_player.stop()
        self.stop_btn.setEnabled(False)
        self._set_status("已停止播放", ok=True)

    def save_persona(self) -> None:
        persona_id = self.persona_id_input.text().strip()
        if not persona_id:
            self._set_status("人设 ID 不能为空。", ok=False)
            return

        prompt_wav_path = self.prompt_wav_input.text().strip()
        if prompt_wav_path and not Path(prompt_wav_path).is_file():
            self._set_status("参考音频文件不存在，请重新选择。", ok=False)
            return

        try:
            upsert_persona(
                {
                    "persona_id": persona_id,
                    "name": self.name_input.text().strip() or persona_id,
                    "cosyvoice_mode": self.mode_input.currentText(),
                    "voice": self.voice_input.text().strip(),
                    "prompt_wav_path": prompt_wav_path,
                    "prompt_text": self.prompt_text_input.text().strip(),
                    "instruct_text": self.instruct_text_input.text().strip(),
                    "audio_format": self.audio_format_input.currentText(),
                    "sample_rate": int(
                        self.sample_rate_input.text().strip() or "22050"
                    ),
                    "base_speed": float(self.base_speed_input.text().strip() or "1.0"),
                    "default_pause_ms": int(self.pause_input.text().strip() or "260"),
                    "enabled": self.enabled_input.isChecked(),
                }
            )
            self.reload_data()
            self._set_status(f"已保存人设：{persona_id}", ok=True)
        except Exception as exc:
            self._set_status(f"保存人设失败：{exc}", ok=False)
