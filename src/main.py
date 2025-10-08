import sys
import os
import textwrap

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QPushButton, QWidget, QFileDialog, QMessageBox, QLabel
)

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class PdfWorker(QThread):
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, files_to_process, styles, output_path):
        super().__init__()
        self.files = files_to_process
        self.styles = styles
        self.output_path = output_path  
        self.is_running = True

    def run(self):
        try:
            MAX_FILE_SIZE_MB = 10
            MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
            
            BINARY_FILE_EXTENSIONS = [
                '.bin', '.pkl', '.exe', '.dll', '.so', '.a', 
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
                '.zip', '.rar', '.7z', '.gz', '.tar',
                '.mp3', '.wav', '.mp4', '.mov', '.avi',
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.pyc', '.ico', '.svg'
            ]
            
            doc = SimpleDocTemplate(self.output_path, pagesize=A4)
            story = [Paragraph("Отчёт по выбранным файлам", self.styles["RussianHeading"]), Spacer(1, 20)]
            total_files = len(self.files)

            for i, file_path in enumerate(self.files):
                if not self.is_running:
                    self.status_updated.emit("Генерация отменена.")
                    return

                filename = os.path.basename(file_path)
                self.status_updated.emit(f"Обработка ({i+1}/{total_files}): {filename}")
                
                _, file_extension = os.path.splitext(file_path)
                if file_extension.lower() in BINARY_FILE_EXTENSIONS:
                    print(f"Пропущен бинарный файл (по расширению): {file_path}")
                    continue

                if os.path.getsize(file_path) > MAX_FILE_SIZE_BYTES:
                    print(f"Пропущен слишком большой файл (> {MAX_FILE_SIZE_MB} МБ): {file_path}")
                    continue
                
                try:
                    with open(file_path, 'rb') as raw_file:
                        raw_data = raw_file.read()

                    content = None
                    if file_extension.lower() == '.txt':
                        try:
                            content = raw_data.decode('utf-8')
                        except UnicodeDecodeError:
                            try:
                                content = raw_data.decode('utf-16')
                            except UnicodeDecodeError:
                                content = raw_data.decode('cp1251', errors='replace')
                    else:
                        try:
                            content = raw_data.decode('utf-8')
                        except UnicodeDecodeError:
                            content = raw_data.decode('cp1251', errors='replace')
                    
                    wrapped_content = self.wrap_text(content)
                    story.append(Paragraph(f"Файл: {file_path}", self.styles["RussianHeading"]))
                    story.append(Preformatted(wrapped_content, self.styles["RussianMono"]))
                    story.append(Spacer(1, 15))

                except Exception as e:
                    story.append(Paragraph(f"Не удалось прочитать файл {file_path} ({e})", self.styles["Russian"]))
            
            self.status_updated.emit("Почти готово... Создание PDF-файла.")
            doc.build(story)
            self.finished.emit(True, f"PDF создан: {self.output_path}")

        except Exception as e:
            self.finished.emit(False, f"Критическая ошибка: {e}")

    def wrap_text(self, text, width=100):
        wrapped_lines = []
        for line in text.splitlines():
            wrapped_lines.extend(textwrap.wrap(line, width=width, replace_whitespace=False) or [""])
        return "\n".join(wrapped_lines)
        
    def stop(self):
        self.is_running = False

class DirectorySelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Выбор директорий для PDF")
        self.resize(600, 500)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Файлы и папки"])
        self.tree.itemChanged.connect(self.handle_item_changed)
        self.tree.itemExpanded.connect(self.on_item_expanded)

        self.btn_choose = QPushButton("Выбрать директорию")
        self.btn_generate = QPushButton("Сгенерировать PDF")
        
        self.status_label = QLabel("Готов к работе.")
        self.status_label.setStyleSheet("color: #555;")

        layout = QVBoxLayout()
        layout.addWidget(self.tree)
        layout.addWidget(self.btn_choose)
        layout.addWidget(self.btn_generate)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.btn_choose.clicked.connect(self.choose_directory)
        self.btn_generate.clicked.connect(self.start_pdf_generation)
        
        self.pdf_worker = None


        def resource_path(relative_path):
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")

            return os.path.join(base_path, relative_path)

        try:
            font_path = resource_path(os.path.join("assets", "JetBrainsMono.ttf"))
            pdfmetrics.registerFont(TTFont("JetBrainsMono", font_path))
            base_font = "JetBrainsMono"
        except Exception:
            print("Шрифт JetBrainsMono.ttf не найден. Используется стандартный шрифт.")
            base_font = "Helvetica"

        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(name="Russian", fontName=base_font, fontSize=9, leading=11))
        self.styles.add(ParagraphStyle(name="RussianHeading", fontName=base_font, fontSize=12, leading=14, spaceAfter=6))
        self.styles.add(ParagraphStyle(name="RussianMono", fontName=base_font, fontSize=8, leading=10))

    def start_pdf_generation(self):
        if self.tree.topLevelItemCount() == 0:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите директорию")
            return

        root_item = self.tree.topLevelItem(0)
        root_path = root_item.text(0)
        selected_files = sorted(list(set(self.collect_selected_files_recursive(root_item, root_path))))
        
        if not selected_files:
            QMessageBox.warning(self, "Ошибка", "Не выбраны файлы")
            return
        
        default_filename = os.path.join(os.path.expanduser("~"), "selected_report.pdf")
        
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить PDF как...",
            default_filename,
            "PDF Files (*.pdf);;All Files (*)"
        )

        if not output_path:
            self.status_label.setText("Генерация отменена пользователем.")
            return

        self.btn_generate.setEnabled(False)
        self.btn_choose.setEnabled(False)
        self.status_label.setText("Подготовка к генерации...")
        
        self.pdf_worker = PdfWorker(
            files_to_process=selected_files, 
            styles=self.styles, 
            output_path=output_path
        )
        self.pdf_worker.status_updated.connect(self.update_status)
        self.pdf_worker.finished.connect(self.generation_finished)
        self.pdf_worker.start()

    def update_status(self, message):
        self.status_label.setText(message)

    def generation_finished(self, success, message):
        self.status_label.setText(message)
        if success:
            QMessageBox.information(self, "Готово", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)
        
        self.btn_generate.setEnabled(True)
        self.btn_choose.setEnabled(True)

    def closeEvent(self, event):
        if self.pdf_worker and self.pdf_worker.isRunning():
            self.pdf_worker.stop()
            self.pdf_worker.wait()
        event.accept()

    def add_child(self, parent, path, name):
        child = QTreeWidgetItem(parent, [name])
        child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
        child.setCheckState(0, Qt.CheckState.Unchecked)
        if os.path.isdir(os.path.join(path, name)):
            QTreeWidgetItem(child, ["..."])
        return child

    def populate_tree(self, parent, path):
        try:
            for entry in os.listdir(path):
                self.add_child(parent, path, entry)
        except PermissionError:
            pass

    def on_item_expanded(self, item):
        if item.childCount() == 1 and item.child(0).text(0) == "...":
            item.removeChild(item.child(0))
            self.populate_tree(item, self.get_item_path(item))

    def get_item_path(self, item):
        parts = []
        while item:
            parts.insert(0, item.text(0))
            item = item.parent()
        return os.path.join(*parts)

    def choose_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Выбрать директорию")
        if dir_path:
            self.tree.clear()
            root = QTreeWidgetItem(self.tree, [dir_path])
            root.setFlags(root.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            root.setCheckState(0, Qt.CheckState.Unchecked)
            self.populate_tree(root, dir_path)
            root.setExpanded(True)

    def handle_item_changed(self, item, column):
        if column != 0: return
        state = item.checkState(0)
        self.tree.blockSignals(True)
        for i in range(item.childCount()):
            child = item.child(i)
            if child.text(0) != "...":
                child.setCheckState(0, state)
        self.update_parent_state(item)
        self.tree.blockSignals(False)

    def update_parent_state(self, item):
        parent = item.parent()
        if not parent: return
        checked_count, unchecked_count = 0, 0
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.text(0) == "...": continue
            state = child.checkState(0)
            if state == Qt.CheckState.Checked: checked_count += 1
            elif state == Qt.CheckState.Unchecked: unchecked_count += 1
        
        if checked_count > 0 and unchecked_count > 0: parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
        elif checked_count == 0: parent.setCheckState(0, Qt.CheckState.Unchecked)
        else: parent.setCheckState(0, Qt.CheckState.Checked)
        
        self.update_parent_state(parent)

    def collect_selected_files_recursive(self, item, path):
        selected = []
        state = item.checkState(0)
        EXCLUDED_DIRS = ['.git', '__pycache__', 'venv', '.vscode', '.next', 'node_modules']
        
        if state == Qt.CheckState.Checked:
            if os.path.isdir(path):
                for dirpath, dirnames, filenames in os.walk(path):
                    dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
                    for f in filenames: selected.append(os.path.join(dirpath, f))
            else: selected.append(path)
        elif state == Qt.CheckState.PartiallyChecked:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.text(0) == "...": continue
                if os.path.isdir(os.path.join(path, child.text(0))) and child.text(0) in EXCLUDED_DIRS:
                    continue
                child_path = os.path.join(path, child.text(0))
                selected.extend(self.collect_selected_files_recursive(child, child_path))
        return selected

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DirectorySelector()
    window.show()
    sys.exit(app.exec())