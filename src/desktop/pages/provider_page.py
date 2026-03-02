from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from storage.provider_registry import (
    list_models,
    list_node_model_overrides,
    list_project_model_routes,
    list_provider_profiles,
    supported_capabilities,
    supported_node_names,
    upsert_model_spec,
    upsert_node_model_override,
    upsert_project_model_route,
    upsert_provider_profile,
)

PROVIDER_KINDS = [
    "openai_compatible",
    "anthropic_compatible",
    "gemini_compatible",
    "local_ollama",
    "custom_http",
]


def _set_cell(table: QTableWidget, row: int, col: int, value: Any) -> None:
    item = QTableWidgetItem("" if value is None else str(value))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    table.setItem(row, col, item)


class ProviderPage(QWidget):
    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout()
        header_layout = QHBoxLayout()
        title = QLabel("Model Provider Registry")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.reload_data)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)

        self.providers_table = QTableWidget(0, 6)
        self.providers_table.setHorizontalHeaderLabels(
            ["provider_id", "name", "kind", "base_url", "api_key_env", "enabled"]
        )
        self.providers_table.horizontalHeader().setStretchLastSection(True)

        self.models_table = QTableWidget(0, 7)
        self.models_table.setHorizontalHeaderLabels(
            [
                "model_id",
                "provider_id",
                "model_name",
                "capability",
                "supports_vision",
                "supports_json_mode",
                "enabled",
            ]
        )
        self.models_table.horizontalHeader().setStretchLastSection(True)

        self.project_routes_table = QTableWidget(0, 4)
        self.project_routes_table.setHorizontalHeaderLabels(
            [
                "project_name",
                "default_text_model_id",
                "default_vision_model_id",
                "default_reflection_model_id",
            ]
        )
        self.project_routes_table.horizontalHeader().setStretchLastSection(True)

        self.node_override_table = QTableWidget(0, 3)
        self.node_override_table.setHorizontalHeaderLabels(["project_name", "node_name", "model_id"])
        self.node_override_table.horizontalHeader().setStretchLastSection(True)

        layout.addLayout(header_layout)
        layout.addWidget(QLabel("Providers"))
        layout.addWidget(self.providers_table)
        layout.addWidget(QLabel("Models"))
        layout.addWidget(self.models_table)
        layout.addWidget(QLabel("Project Defaults"))
        layout.addWidget(self.project_routes_table)
        layout.addWidget(QLabel("Node Overrides"))
        layout.addWidget(self.node_override_table)
        layout.addWidget(self._build_provider_form())
        layout.addWidget(self._build_model_form())
        layout.addWidget(self._build_project_route_form())
        layout.addWidget(self._build_node_override_form())

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #0f766e;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self.reload_data()

    def _build_provider_form(self) -> QGroupBox:
        box = QGroupBox("Add or Update Provider")
        form = QFormLayout()

        self.provider_id_input = QLineEdit()
        self.provider_name_input = QLineEdit()
        self.provider_kind_input = QComboBox()
        self.provider_kind_input.addItems(PROVIDER_KINDS)
        self.provider_base_url_input = QLineEdit()
        self.provider_api_key_env_input = QLineEdit()
        self.provider_headers_input = QLineEdit("{}")
        self.provider_enabled_input = QCheckBox()
        self.provider_enabled_input.setChecked(True)

        save_btn = QPushButton("Save Provider")
        save_btn.clicked.connect(self.save_provider)

        form.addRow("provider_id", self.provider_id_input)
        form.addRow("name", self.provider_name_input)
        form.addRow("kind", self.provider_kind_input)
        form.addRow("base_url", self.provider_base_url_input)
        form.addRow("api_key_env", self.provider_api_key_env_input)
        form.addRow("extra_headers_json", self.provider_headers_input)
        form.addRow("enabled", self.provider_enabled_input)
        form.addRow(save_btn)
        box.setLayout(form)
        return box

    def _build_model_form(self) -> QGroupBox:
        box = QGroupBox("Add or Update Model")
        form = QFormLayout()

        self.model_id_input = QLineEdit()
        self.model_provider_id_input = QLineEdit()
        self.model_name_input = QLineEdit()
        self.model_capability_input = QComboBox()
        self.model_capability_input.addItems(supported_capabilities())
        self.model_context_window_input = QLineEdit("0")
        self.model_supports_vision_input = QCheckBox()
        self.model_supports_json_input = QCheckBox()
        self.model_supports_json_input.setChecked(True)
        self.model_enabled_input = QCheckBox()
        self.model_enabled_input.setChecked(True)

        save_btn = QPushButton("Save Model")
        save_btn.clicked.connect(self.save_model)

        form.addRow("model_id", self.model_id_input)
        form.addRow("provider_id", self.model_provider_id_input)
        form.addRow("model_name", self.model_name_input)
        form.addRow("capability", self.model_capability_input)
        form.addRow("context_window", self.model_context_window_input)
        form.addRow("supports_vision", self.model_supports_vision_input)
        form.addRow("supports_json_mode", self.model_supports_json_input)
        form.addRow("enabled", self.model_enabled_input)
        form.addRow(save_btn)
        box.setLayout(form)
        return box

    def _build_project_route_form(self) -> QGroupBox:
        box = QGroupBox("Set Project Defaults")
        form = QFormLayout()

        self.project_name_input = QLineEdit()
        self.project_default_text_input = QLineEdit()
        self.project_default_vision_input = QLineEdit()
        self.project_default_reflection_input = QLineEdit()

        save_btn = QPushButton("Save Project Defaults")
        save_btn.clicked.connect(self.save_project_defaults)

        form.addRow("project_name", self.project_name_input)
        form.addRow("default_text_model_id", self.project_default_text_input)
        form.addRow("default_vision_model_id", self.project_default_vision_input)
        form.addRow("default_reflection_model_id", self.project_default_reflection_input)
        form.addRow(save_btn)
        box.setLayout(form)
        return box

    def _build_node_override_form(self) -> QGroupBox:
        box = QGroupBox("Set Node Model Override")
        form = QFormLayout()

        self.override_project_name_input = QLineEdit()
        self.override_node_name_input = QComboBox()
        self.override_node_name_input.addItems(supported_node_names())
        self.override_model_id_input = QLineEdit()

        save_btn = QPushButton("Save Node Override")
        save_btn.clicked.connect(self.save_node_override)

        form.addRow("project_name", self.override_project_name_input)
        form.addRow("node_name", self.override_node_name_input)
        form.addRow("model_id", self.override_model_id_input)
        form.addRow(save_btn)
        box.setLayout(form)
        return box

    def _set_status(self, message: str, ok: bool) -> None:
        color = "#0f766e" if ok else "#b91c1c"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)

    def reload_data(self) -> None:
        providers: List[Dict[str, Any]] = list_provider_profiles()
        models: List[Dict[str, Any]] = list_models()
        project_routes: List[Dict[str, Any]] = list_project_model_routes()
        node_overrides: List[Dict[str, Any]] = list_node_model_overrides()

        self.providers_table.setRowCount(len(providers))
        for row, provider in enumerate(providers):
            _set_cell(self.providers_table, row, 0, provider.get("provider_id"))
            _set_cell(self.providers_table, row, 1, provider.get("name"))
            _set_cell(self.providers_table, row, 2, provider.get("kind"))
            _set_cell(self.providers_table, row, 3, provider.get("base_url"))
            _set_cell(self.providers_table, row, 4, provider.get("api_key_env"))
            _set_cell(self.providers_table, row, 5, provider.get("enabled"))

        self.models_table.setRowCount(len(models))
        for row, model in enumerate(models):
            _set_cell(self.models_table, row, 0, model.get("model_id"))
            _set_cell(self.models_table, row, 1, model.get("provider_id"))
            _set_cell(self.models_table, row, 2, model.get("model_name"))
            _set_cell(self.models_table, row, 3, model.get("capability"))
            _set_cell(self.models_table, row, 4, model.get("supports_vision"))
            _set_cell(self.models_table, row, 5, model.get("supports_json_mode"))
            _set_cell(self.models_table, row, 6, model.get("enabled"))

        self.project_routes_table.setRowCount(len(project_routes))
        for row, item in enumerate(project_routes):
            _set_cell(self.project_routes_table, row, 0, item.get("project_name"))
            _set_cell(self.project_routes_table, row, 1, item.get("default_text_model_id"))
            _set_cell(self.project_routes_table, row, 2, item.get("default_vision_model_id"))
            _set_cell(self.project_routes_table, row, 3, item.get("default_reflection_model_id"))

        self.node_override_table.setRowCount(len(node_overrides))
        for row, item in enumerate(node_overrides):
            _set_cell(self.node_override_table, row, 0, item.get("project_name"))
            _set_cell(self.node_override_table, row, 1, item.get("node_name"))
            _set_cell(self.node_override_table, row, 2, item.get("model_id"))

    def save_provider(self) -> None:
        provider_id = self.provider_id_input.text().strip()
        if not provider_id:
            self._set_status("provider_id is required.", ok=False)
            return

        try:
            upsert_provider_profile(
                {
                    "provider_id": provider_id,
                    "name": self.provider_name_input.text().strip() or provider_id,
                    "kind": self.provider_kind_input.currentText(),
                    "base_url": self.provider_base_url_input.text().strip(),
                    "api_key_env": self.provider_api_key_env_input.text().strip(),
                    "extra_headers_json": self.provider_headers_input.text().strip() or "{}",
                    "enabled": self.provider_enabled_input.isChecked(),
                }
            )
            self.reload_data()
            self._set_status(f"Provider saved: {provider_id}", ok=True)
        except Exception as exc:
            self._set_status(f"Failed to save provider: {exc}", ok=False)

    def save_model(self) -> None:
        model_id = self.model_id_input.text().strip()
        provider_id = self.model_provider_id_input.text().strip()
        if not model_id or not provider_id:
            self._set_status("model_id and provider_id are required.", ok=False)
            return

        try:
            upsert_model_spec(
                {
                    "model_id": model_id,
                    "provider_id": provider_id,
                    "model_name": self.model_name_input.text().strip() or model_id,
                    "capability": self.model_capability_input.currentText(),
                    "context_window": int(self.model_context_window_input.text().strip() or "0"),
                    "supports_vision": self.model_supports_vision_input.isChecked(),
                    "supports_json_mode": self.model_supports_json_input.isChecked(),
                    "enabled": self.model_enabled_input.isChecked(),
                }
            )
            self.reload_data()
            self._set_status(f"Model saved: {model_id}", ok=True)
        except Exception as exc:
            self._set_status(f"Failed to save model: {exc}", ok=False)

    def save_project_defaults(self) -> None:
        project_name = self.project_name_input.text().strip()
        if not project_name:
            self._set_status("project_name is required.", ok=False)
            return

        try:
            upsert_project_model_route(
                project_name=project_name,
                default_text_model_id=self.project_default_text_input.text().strip(),
                default_vision_model_id=self.project_default_vision_input.text().strip(),
                default_reflection_model_id=self.project_default_reflection_input.text().strip(),
            )
            self.reload_data()
            self._set_status(f"Project defaults saved: {project_name}", ok=True)
        except Exception as exc:
            self._set_status(f"Failed to save project defaults: {exc}", ok=False)

    def save_node_override(self) -> None:
        project_name = self.override_project_name_input.text().strip()
        model_id = self.override_model_id_input.text().strip()
        node_name = self.override_node_name_input.currentText().strip()
        if not project_name or not model_id:
            self._set_status("project_name and model_id are required.", ok=False)
            return

        try:
            upsert_node_model_override(
                project_name=project_name,
                node_name=node_name,
                model_id=model_id,
            )
            self.reload_data()
            self._set_status(
                f"Node override saved: {project_name} / {node_name} -> {model_id}",
                ok=True,
            )
        except Exception as exc:
            self._set_status(f"Failed to save node override: {exc}", ok=False)
