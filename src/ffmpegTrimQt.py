version = "v2.2.1"
import sys
from configparser import ConfigParser
from pathlib import Path

from PySide6.QtCore import (
    Qt, QProcess, QUrl
)

from PySide6.QtGui import (
    QActionGroup, QTextCursor, QDesktopServices,
)

from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QFileDialog, QDialog,
    QLabel,
    QVBoxLayout, QHBoxLayout,
    QLineEdit, QPlainTextEdit,
    QWidget,
    QPushButton,
    QProgressBar,
    QToolButton,
    QStyle
)

# for executable
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

CONFIG_PATH = APP_DIR / "config.ini"
THEME_DIR = APP_DIR / "themes"
FFMPEG_PATH = APP_DIR / "ffmpeg" / "ffmpeg"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # generate config if missing
        if not Path(CONFIG_PATH).exists():
            generate_config()

        # import config
        self.config = ConfigParser()
        self.config.read(CONFIG_PATH)

        # ffmpeg process definition
        self.ffmpeg_process = QProcess()
        self.stdout_buffer = ""

        # window settings
        self.setWindowTitle(f"ffmpegTrimQt {version}")
        self.setFixedSize(640, 136)

        # load default theme if exists, otherwise do nothing
        default_theme_setting = self.config.get("qt", "default-theme")
        self.default_theme = Path(THEME_DIR / f"{default_theme_setting}.qss")
        if self.default_theme.is_file():
            self.load_theme(self.default_theme)

        # ui elements
        self.setup_ui()
        self.setup_menubar()

        # connections
        self.setup_connections()

    # helper functions
    def setup_ui(self):
        # target path input
        target_layout = QHBoxLayout()

        target_label = QLabel("Target:")
        self.path_line_edit = QLineEdit()
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))

        target_layout.addWidget(target_label)
        target_layout.addWidget(self.path_line_edit)
        target_layout.addWidget(self.browse_button)

        # timestamp input
        time_layout = QHBoxLayout()

        self.start_time_line_edit = QLineEdit()
        self.start_time_line_edit.setPlaceholderText("hh:mm:ss.mmm")

        to_label = QLabel("to")

        self.end_time_line_edit = QLineEdit()
        self.end_time_line_edit.setPlaceholderText("hh:mm:ss.mmm")

        time_layout.addWidget(self.start_time_line_edit)
        time_layout.addWidget(to_label)
        time_layout.addWidget(self.end_time_line_edit)

        # console detail dropdown
        self.console_dropdown_layout = QVBoxLayout()

        self.console_button = QToolButton()
        self.console_button.setText("_")
        self.console_button.setCheckable(True)
        self.console_button.setChecked(False)
        self.console_button.setArrowType(Qt.ArrowType.RightArrow)
        self.console_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setUndoRedoEnabled(False)
        self.console.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.console.hide()

        self.console_dropdown_layout.addWidget(self.console)

        # progress bar + console, clear & start button
        controls_layout = QHBoxLayout()

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setFixedWidth(64)
        self.start_button = QPushButton("Start")
        self.start_button.setFixedWidth(64)
        self.start_button.setObjectName("startButton")

        controls_layout.addWidget(self.progress)
        controls_layout.addWidget(self.console_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.start_button)

        # main layout
        main_layout = QVBoxLayout()

        main_layout.addLayout(target_layout)
        main_layout.addLayout(time_layout)
        main_layout.addLayout(controls_layout)
        main_layout.addLayout(self.console_dropdown_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        self.adjustSize()

    def setup_connections(self):
        self.browse_button.clicked.connect(self.browse_file)
        self.clear_button.clicked.connect(self.clear_line_edits)
        self.start_button.clicked.connect(self.run_ffmpeg)

        self.console_button.toggled.connect(self.console.setVisible)
        self.console_button.toggled.connect(self.expand_console)

        self.ffmpeg_process.started.connect(self.ffmpeg_started)
        self.ffmpeg_process.finished.connect(self.ffmpeg_finished)

        self.ffmpeg_process.readyReadStandardOutput.connect(
            self.parse_progress
        )

        self.ffmpeg_process.readyReadStandardError.connect(
            self.read_process_error
        )

    # console resizing
    def expand_console(self, expanded):
        self.console_button.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded
            else Qt.ArrowType.RightArrow
        )

        self.console_dropdown_layout.activate()
        self.console_dropdown_layout.invalidate()

        if expanded:
            self.setFixedSize(640, 502)
        else:
            self.setFixedSize(640, 136)

        self.adjustSize()

    # menu bar setup
    def setup_menubar(self):
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("File")
        self.setup_file_menu()
        self.theme_menu = menu_bar.addMenu("Themes")
        self.setup_theme_menu()
        self.help_menu = menu_bar.addMenu("Help")
        self.setup_help_menu()

    def setup_file_menu(self):
        open_config_action = self.file_menu.addAction("Open config.ini")
        exit_action = self.file_menu.addAction("Exit")

        open_config_action.triggered.connect(self.open_config)
        exit_action.triggered.connect(sys.exit)

    def open_config(self):
        config_path = Path(__file__).parent / "config.ini"

        QDesktopServices.openUrl(QUrl.fromLocalFile(config_path))

    def setup_theme_menu(self):
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        theme_directory = THEME_DIR

        for theme_path in theme_directory.glob("*.qss"):
            action = self.theme_menu.addAction(theme_path.stem)

            action.setCheckable(True)
            theme_group.addAction(action)

            if theme_path == self.default_theme:
                action.setChecked(True)

            action.triggered.connect(
                lambda checked=False, path=theme_path:
                self.load_theme(path)
            )

    def setup_help_menu(self):
        about_action = self.help_menu.addAction("About")
        about_action.triggered.connect(self.show_about)

    def show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def load_theme(self, theme_path):
        with open(theme_path, "r", encoding="utf-8") as theme:
            stylesheet = theme.read()

        QApplication.instance().setStyleSheet(stylesheet)

    # connection helper functions
    def browse_file(self):
        default_path = self.config.get(
            "qt",
            "default-path",
            fallback=str(Path.home())
        )

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            default_path,
            "Video Files (*.mp4 *.mkv *.mov *.avi);;All Files (*)"
        )

        if file_path:
            self.path_line_edit.setText(file_path)

    def clear_line_edits(self):
        self.path_line_edit.clear()
        self.start_time_line_edit.clear()
        self.end_time_line_edit.clear()

    def run_ffmpeg(self):
        self.console.clear()

        audio_codec     = self.config.get("audio", "codec")
        audio_quality   = self.config.get("audio", "quality")
        video_codec     = self.config.get("video", "codec")
        video_quality   = self.config.get("video", "quality")
        cpu_preset      = self.config.get("video", "preset")
        file_extension  = self.config.get("video", "extension")

        input_path = Path(self.path_line_edit.text())
        if not input_path.is_file():
            self.console.appendPlainText("Invalid target video path.")
            QApplication.beep()
            return

        output_path = get_output_path(input_path.with_suffix(""), file_extension)

        self.start_time = self.start_time_line_edit.text()
        self.end_time = self.end_time_line_edit.text()

        try:
            self.duration = parse_timecode(self.end_time) - parse_timecode(self.start_time)
        except ValueError as error:
            self.console.appendPlainText(f"Invalid timecode: {error}")
            QApplication.beep()
            return

        video_args = (
            ["-c:v", "copy"]
            if video_codec == "copy"
            else ["-c:v", video_codec, "-preset", cpu_preset, "-crf", video_quality]
        )

        audio_args = (
            ["-c:a", "copy"]
            if audio_codec == "copy"
            else ["-c:a", audio_codec, "-b:a", audio_quality]
        )

        container_args = (
            ["-movflags", "+faststart"]
            if file_extension.lower() in ("mp4", "mov", "m4a")
            else []
        )

        args = [
            "-i", str(input_path),
            "-ss", self.start_time,
            "-t", str(self.duration),
            *video_args,
            *audio_args,
            *container_args,
            "-progress", "pipe:1",
            output_path
        ]

        self.ffmpeg_process.start(
            str(FFMPEG_PATH), args
        )

    def parse_progress(self):
        self.stdout_buffer += (
            self.ffmpeg_process
            .readAllStandardOutput()
            .data()
            .decode("utf-8", errors="replace")
        )

        while "\n" in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split("\n", 1)
            if line.startswith("out_time="):
                out_time = parse_timecode(line.replace("out_time=", ""))
                current_progress = out_time - parse_timecode(self.start_time)
                current_progress_percent = (current_progress / self.duration) * 100
                self.progress.setValue(int(current_progress_percent))

    def ffmpeg_started(self):
        self.progress.setValue(0)
        self.start_button.setText("Stop")
        self.start_button.setEnabled(False)
        self.console.appendPlainText("ffmpeg started...\n")

    def ffmpeg_finished(self):
        QApplication.beep()
        self.progress.setValue(100)
        self.start_button.setText("Start")
        self.start_button.setEnabled(True)
        self.console.appendPlainText("ffmpeg finished.\n")

    def read_process_error(self):
        output = self.ffmpeg_process.readAllStandardError().data().decode(
            "utf-8",
            errors="replace"
        )
        self.append_console(output)

    def append_console(self, output):
        self.console.appendPlainText(output.rstrip())
        self.console.moveCursor(QTextCursor.MoveOperation.End)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"About ffmpegTrimQt {version}")

        layout = QVBoxLayout(self)

        label = QLabel(f"★ Welcome to ffmpegTrimQt {version} ★\nPowered by FFmpeg",
                       alignment=Qt.AlignmentFlag.AlignCenter)

        ok_button = QPushButton("Ok")
        ok_button.setMaximumWidth(64)
        ok_button.clicked.connect(self.accept)

        layout.addWidget(label)
        layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignCenter)

def get_output_path(temp_path, file_extension):
    i = 0

    while True:
        output_path = Path(f"{temp_path}_Trim{'' if i == 0 else i}.{file_extension}")

        if not output_path.exists():
            return str(output_path)

        i += 1

def parse_timecode(tc):
    if "." in tc:
        whole, ms = tc.split(".")
        seconds = parse_timecode(whole)
        return seconds + float("0." + str(ms))
    else:
        parts = list(map(int, tc.split(":")))
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            raise ValueError("Invalid timecode format.")

def generate_config():
    config = ConfigParser()
    config["audio"] = {
        "codec": "copy",
        "quality": "320k",
    }

    config["video"] = {
        "codec": "libx264",
        "quality": "23",
        "preset": "medium",
        "extension": "mp4",
    }

    config["qt"] = {
        "default-path": str(Path.home() / "Videos"),
        "default-theme": "win9x-dark",
    }

    with open("config.ini", "w") as f:
        config.write(f)

    return


def main():
    app = QApplication(sys.argv)

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
