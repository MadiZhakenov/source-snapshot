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

# =====================================================================
# === ПОТОК-ВОРКЕР ===
# =====================================================================
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
            
            # Extensions that are definitely binary/media files
            BINARY_FILE_EXTENSIONS = [
                '.bin', '.pkl', '.exe', '.dll', '.so', '.a', 
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.ico', '.svg',
                '.zip', '.rar', '.7z', '.gz', '.tar', '.bz2',
                '.mp3', '.wav', '.mp4', '.mov', '.avi', '.mkv', '.flac', '.ogg', '.wma',
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt',
                '.pyc', '.pyo', '.class', '.jar', '.war',
                '.db', '.sqlite', '.sqlite3', '.mdb',
                '.woff', '.woff2', '.ttf', '.eot', '.otf',
                '.min.js', '.min.css'
            ]
            
            # Extensions that are likely clean text/code files
            TEXT_FILE_EXTENSIONS = [
                '.py', '.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs',
                '.html', '.htm', '.css', '.scss', '.sass', '.less', '.styl',
                '.java', '.kt', '.scala', '.groovy',
                '.c', '.cpp', '.h', '.hpp', '.cc', '.cxx', '.cs',
                '.go', '.rs', '.swift', '.rb', '.php', '.pl', '.sh', '.bash', '.zsh',
                '.sql', '.r', '.lua', '.vim', '.el', '.clj', '.erl', '.ex', '.exs',
                '.hs', '.ml', '.fs', '.fsx',
                '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
                '.md', '.rst', '.txt', '.log', '.csv',
                '.env', '.gitignore', '.dockerfile', '.makefile', '.cmake',
                '.vue', '.svelte', '.astro',
                '.graphql', '.gql', '.proto', '.thrift',
                '.tf', '.tfvars', '.hcl',
                '.ps1', '.bat', '.cmd', '.vbs',
                '.asm', '.s', '.S',
                '.dart', '.flutter',
                '.nim', '.zig', '.v', '.vy',
                '.jl', '.m', '.mx',
                '.awk', '.sed',
                '.ipynb', '.rmd',
                '.adoc', '.org', '.wiki',
                '.prisma', '.graphql',
            ]
            
            doc = SimpleDocTemplate(self.output_path, pagesize=A4)
            story = [Paragraph("Отчёт по выбранным файлам", self.styles["RussianHeading"]), Spacer(1, 20)]
            total_files = len(self.files)

            for i, file_path in enumerate(self.files):
                if not self.is_running:
                    self.status_updated.emit("Генерация отменена.")
                    return

                filename = os.path.basename(file_path)
                _, file_extension = os.path.splitext(file_path)
                ext_lower = file_extension.lower()
                
                # Skip known binary extensions
                if ext_lower in BINARY_FILE_EXTENSIONS:
                    print(f"Пропущен бинарный файл (по расширению): {file_path}")
                    continue
                
                # For unknown extensions, check if file appears to be binary
                if ext_lower not in TEXT_FILE_EXTENSIONS:
                    # Try to detect if it's binary by checking for null bytes
                    try:
                        with open(file_path, 'rb') as f:
                            chunk = f.read(8192)
                            if b'\x00' in chunk:
                                print(f"Пропущен бинарный файл (обнаружены null-байты): {file_path}")
                                continue
                    except Exception:
                        print(f"Пропущен файл (не удалось прочитать): {file_path}")
                        continue
                
                self.status_updated.emit(f"Обработка ({i+1}/{total_files}): {filename}")

                if os.path.getsize(file_path) > MAX_FILE_SIZE_BYTES:
                    print(f"Пропущен слишком большой файл (> {MAX_FILE_SIZE_MB} МБ): {file_path}")
                    continue
                
                try:
                    with open(file_path, 'rb') as raw_file:
                        raw_data = raw_file.read()

                    content = None
                    if ext_lower == '.txt':
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
                    
                    # Count lines
                    line_count = len(content.splitlines())
                    
                    wrapped_content = self.wrap_text(content)
                    story.append(Paragraph(f"Файл: {file_path} ({line_count} строк)", self.styles["RussianHeading"]))
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

# =====================================================================
# === GUI ===
# =====================================================================
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

        # Функция для поиска ресурсов (шрифта) в .exe и в обычном режиме
        def resource_path(relative_path):
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)

        try:
            # Ищем шрифт в папке assets
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
            
            # Если папка была отмечена, отмечаем и загруженные элементы
            if item.checkState(0) == Qt.CheckState.Checked:
                for i in range(item.childCount()):
                    item.child(i).setCheckState(0, Qt.CheckState.Checked)

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
        # Распространяем выбор на дочерние элементы
        for i in range(item.childCount()):
            child = item.child(i)
            if child.text(0) != "...":
                child.setCheckState(0, state)
        self.update_parent_state(item)
        self.tree.blockSignals(False)

    def update_parent_state(self, item):
        parent = item.parent()
        if not parent: return
        
        checked_count = 0
        unchecked_count = 0
        partially_checked_count = 0
        
        child_count = parent.childCount()
        for i in range(child_count):
            child = parent.child(i)
            if child.text(0) == "...": continue
            
            state = child.checkState(0)
            if state == Qt.CheckState.Checked:
                checked_count += 1
            elif state == Qt.CheckState.Unchecked:
                unchecked_count += 1
            else:
                partially_checked_count += 1
        
        # Логика определения состояния родителя
        if checked_count == child_count:
            parent.setCheckState(0, Qt.CheckState.Checked)
        elif checked_count == 0 and partially_checked_count == 0:
            parent.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            # Если есть хоть один выбранный или частично выбранный - родитель частично выбран
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
        
        self.update_parent_state(parent)

    def collect_selected_files_recursive(self, item, path):
        selected = []
        state = item.checkState(0)
        EXCLUDED_DIRS = ['.git', '__pycache__', 'venv', '.vscode', '.next', 'node_modules', '.idea']
        
        # Если папка полностью выбрана
        if state == Qt.CheckState.Checked:
            if os.path.isdir(path):
                for dirpath, dirnames, filenames in os.walk(path):
                    # Фильтруем папки
                    dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
                    for f in filenames:
                        selected.append(os.path.join(dirpath, f))
            else:
                selected.append(path)
        
        # Если папка частично выбрана, идем внутрь
        elif state == Qt.CheckState.PartiallyChecked:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.text(0) == "...": continue
                
                # Пропускаем исключенные папки
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