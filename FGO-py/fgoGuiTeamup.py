import ast
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QListView, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

import fgoKernel
from fgoTeamupParser import IniParser
from fgoTeamupPlan import TeamupPlan

logger = fgoKernel.getLogger('Teamup')
TEAMUP_FILE = Path(__file__).with_name('fgoTeamup.ini')


class Teamup(QDialog):
    def __init__(self, parent=None, team='DEFAULT'):
        super().__init__(parent)
        self.setup_editor_ui()

        self.teamup = IniParser(str(TEAMUP_FILE))
        self.current_team = None
        self.CBB_TEAM.addItems(self.teamup.sections())
        self.CBB_TEAM.textActivated.connect(self.load)

        names = self.teamup.sections()
        if names:
            selected = team if team in names else names[0]
            self.CBB_TEAM.setCurrentText(selected)
            self.load(selected)
        else:
            self.CBB_TEAM.setCurrentIndex(-1)
            self.reset()
        self.BTN_DUPLICATE.setEnabled(bool(self.current_team))

    def setup_editor_ui(self):
        font_file = Path('C:/Windows/Fonts/NotoSansTC-VF.ttf')
        if font_file.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                self.setFont(QFont(families[0], 10))
        self.setWindowTitle('FGO-py 編隊設定')
        available = self.screen().availableGeometry()
        width = max(1, available.width() - 48)
        height = max(1, available.height() - 80)
        self.setMinimumSize(min(900, width), min(640, height))
        self.resize(min(1200, width), min(860, height))
        self.setStyleSheet('''
            QDialog { background: #0f172a; color: #f8fafc; font-size: 14px; }
            QLabel { color: #e2e8f0; }
            QLabel#title { font-size: 22px; font-weight: bold; color: #93c5fd; }
            QLabel#hint { color: #94a3b8; }
            QFrame#card { background: #1e293b; border: 1px solid #334155;
                          border-radius: 12px; }
            QFrame#skill { background: #172235; border: 1px solid #334155;
                           border-radius: 8px; }
            QWidget#scrollPage { background: #0f172a; }
            QComboBox, QSpinBox { background: #0f172a; color: #f8fafc;
                                 border: 1px solid #475569; border-radius: 6px;
                                 padding: 5px; min-height: 24px; }
            QSpinBox::up-button, QSpinBox::down-button {
                background: #334155; border: 0; }
            QComboBox::drop-down { border: 0; width: 24px; }
            QComboBox QAbstractItemView { background: #1e293b; color: #f8fafc;
                                         border: 1px solid #475569;
                                         selection-background-color: #2563eb;
                                         selection-color: #ffffff; }
            QListView::item { padding: 5px 8px; }
            QListView::item:selected { background: #2563eb; color: #ffffff; }
            QPushButton { background: #334155; color: #f8fafc; border: 0;
                          border-radius: 7px; padding: 8px 13px; }
            QPushButton:hover { background: #475569; }
            QPushButton:checked { background: #164e63; border: 1px solid #7dd3fc; }
            QPushButton:disabled { color: #94a3b8; background: #1e293b; }
            QPushButton#primary { background: #2563eb; font-weight: bold; }
            QPushButton#primary:hover { background: #3b82f6; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 8px; }
            QTabBar::tab { background: #1e293b; color: #cbd5e1;
                           padding: 10px 24px; border-radius: 6px; margin-right: 4px; }
            QTabBar::tab:selected { background: #2563eb; color: white; }
            QScrollArea { border: 0; background: #0f172a; }
        ''')
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(13)
        title = QLabel('編隊自動化設定')
        title.setObjectName('title')
        root.addWidget(title)
        hint = QLabel('按「使用」套用目前編隊設定；需要保留修改時，請按「儲存」或「儲存並使用」。')
        hint.setObjectName('hint')
        root.addWidget(hint)

        formation_row = QHBoxLayout()
        formation_row.addWidget(QLabel('遊戲內編隊'))
        self.TXT_TEAM = QSpinBox(self)
        self.TXT_TEAM.setObjectName('TXT_TEAM')
        self.TXT_TEAM.setRange(0, 15)
        self.TXT_TEAM.setSpecialValueText('0（不切換）')
        self.TXT_TEAM.setToolTip('遊戲內隊伍編成畫面的位置，從左到右 1–15；0 表示不切換編隊。')
        outer_team = getattr(self.parentWidget(), 'TXT_TEAM', None)
        self.TXT_TEAM.setValue(outer_team.value() if outer_team is not None else fgoKernel.Main.teamIndex)
        formation_row.addWidget(self.TXT_TEAM)
        formation_hint = QLabel('按「使用」或「儲存並使用」時同步至主視窗。')
        formation_hint.setObjectName('hint')
        formation_row.addWidget(formation_hint)
        formation_row.addStretch()
        root.addLayout(formation_row)

        team_row = QHBoxLayout()
        team_row.addWidget(QLabel('目前隊伍'))
        self.CBB_TEAM = QComboBox(self)
        team_list = QListView(self.CBB_TEAM)
        palette = team_list.palette()
        palette.setColor(QPalette.Base, QColor('#1e293b'))
        palette.setColor(QPalette.Text, QColor('#f8fafc'))
        palette.setColor(QPalette.Highlight, QColor('#2563eb'))
        palette.setColor(QPalette.HighlightedText, QColor('#ffffff'))
        team_list.setPalette(palette)
        team_list.viewport().setPalette(palette)
        self.CBB_TEAM.setView(team_list)
        self.CBB_TEAM.setMinimumWidth(220)
        team_row.addWidget(self.CBB_TEAM, 1)
        for label, callback in (
            ('＋ 新增', self.add_team), ('改名', self.rename_team), ('刪除', self.delete_team),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            team_row.addWidget(button)
        self.BTN_DUPLICATE = QPushButton('複製並新建')
        self.BTN_DUPLICATE.setToolTip('複製目前畫面上的編隊設定，建立另一個名稱')
        self.BTN_DUPLICATE.clicked.connect(self.duplicate_team)
        team_row.insertWidget(3, self.BTN_DUPLICATE)
        root.addLayout(team_row)

        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel('快速設定'))
        for label, callback in (
            ('全部設為第 1 面', lambda: self.global_reset(False)),
            ('依位置設為第 1–6 面', lambda: self.global_reset(True)),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            quick_row.addWidget(button)
        quick_row.addStretch()
        reset_button = QPushButton('恢復預設值')
        reset_button.clicked.connect(self.reset)
        quick_row.addWidget(reset_button)
        self.tabs = QTabWidget(self)
        self.plan_page = TeamupPlan(self._values, self._show_values)
        self.tabs.addTab(self.plan_page, '點擊編排')
        numeric_page = QWidget()
        numeric_layout = QVBoxLayout(numeric_page)
        numeric_layout.addLayout(quick_row)
        numeric_tabs = QTabWidget()
        for start, label in ((0, '前排 · 1–3 號'), (3, '後備 · 4–6 號')):
            page = QWidget()
            column = QVBoxLayout(page)
            column.setSpacing(12)
            column.setContentsMargins(14, 14, 14, 14)
            for index in range(start, start + 3):
                column.addWidget(self._servant_card(index))
            column.addStretch()
            numeric_tabs.addTab(self._scroll_page(page), label)
        numeric_tabs.addTab(self._master_page(), '御主技能 · 換人')
        numeric_layout.addWidget(numeric_tabs, 1)
        self.tabs.addTab(numeric_page, '數值設定')
        self.tabs.addTab(self._help_page(), '欄位說明')
        self.tabs.currentChanged.connect(self._refresh_plan)
        root.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.BTN_USE = buttons.addButton('使用', QDialogButtonBox.ActionRole)
        self.BTN_USE.setToolTip('套用目前設定並關閉視窗，不儲存編隊檔案')
        self.BTN_USE.clicked.connect(self.use)
        buttons.button(QDialogButtonBox.Save).setText('儲存')
        buttons.button(QDialogButtonBox.Ok).setText('儲存並使用')
        buttons.button(QDialogButtonBox.Ok).setObjectName('primary')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.button(QDialogButtonBox.Save).clicked.connect(self.save)
        buttons.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        buttons.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        root.addWidget(buttons)

    def _scroll_page(self, page):
        page.setObjectName('scrollPage')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _card(self):
        card = QFrame()
        card.setObjectName('card')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(10)
        return card, layout

    def _heading(self, text):
        label = QLabel(text)
        label.setStyleSheet('font-weight: bold; font-size: 16px; color: #f8fafc;')
        return label

    def _field(self, name, maximum, tip, widget_name):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(name)
        label.setObjectName('hint')
        label.setToolTip(tip)
        spin = QSpinBox()
        spin.setRange(0, maximum)
        spin.setAlignment(Qt.AlignCenter)
        spin.setToolTip(tip)
        spin.setObjectName(widget_name)
        setattr(self, widget_name, spin)
        layout.addWidget(label)
        layout.addWidget(spin)
        return box

    def _skill_row(self, prefix, name, fields):
        row = QFrame()
        row.setObjectName('skill')
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 7, 12, 9)
        title = QLabel(name)
        title.setMinimumWidth(84)
        title.setStyleSheet('font-weight: bold; color: #c4b5fd;')
        layout.addWidget(title)
        for index, (label, maximum, tip) in enumerate(fields):
            layout.addWidget(self._field(label, maximum, tip, f'{prefix}_{index}'), 1)
        return row

    def _servant_card(self, index):
        card, column = self._card()
        header = QHBoxLayout()
        position = '前排' if index < 3 else '後備 · 換上場後讀取此處設定'
        header.addWidget(self._heading(f'從者 {index + 1} 號位  ·  {position}'))
        header.addStretch()
        quick = QPushButton('此從者設為第 1 面')
        quick.clicked.connect(lambda: self._set_servant(index, 1))
        header.addWidget(quick)
        column.addLayout(header)
        skill_fields = (
            ('面數', 9, '第幾波開始施放；0 表示不施放'),
            ('回合', 9, '指定面數最早可施放的回合，0 表示從該面一開始就可施放'),
            ('對象', 3, '場上左至右為 1、2、3'),
            ('順序', 15, '數字越小越先施放'),
        )
        for skill in range(3):
            column.addWidget(self._skill_row(f'TXT_SKILL_{index}_{skill}',
                                              f'技能 {skill + 1}', skill_fields))
        column.addWidget(self._skill_row(f'TXT_HOUGU_{index}', '寶具 NP', (
            ('面數', 9, '從指定面數起，出卡時若寶具可用就會選用。面數 0 表示停用'),
            ('順序', 15, '同回合有多個寶具時，數字越小越先出'),
        )))
        return card

    def _master_page(self):
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(14, 14, 14, 14)
        column.setSpacing(12)
        note = QLabel('御主技能 3 為一般技能時，後備換上填 0。換人時，填場上換下位置 1–3 與後備換上位置 4–6。')
        note.setObjectName('hint')
        column.addWidget(note)
        for index in range(3):
            card, content = self._card()
            content.addWidget(self._heading(f'御主技能 {index + 1}'))
            fields = [
                ('面數', 9, '最早可施放的面數，0 表示停用'),
                ('回合', 9, '指定面數最早可施放的回合，0 表示從該面一開始就可施放'),
                ('對象／場上換下' if index == 2 else '對象', 6 if index == 2 else 3,
                 '場上位置 1–3' if index == 2 else '場上左至右為 1、2、3'),
            ]
            if index == 2:
                fields.append(('後備換上', 6, '後備位置 4–6；不用換人則填 0'))
            fields.append(('順序', 15, '數字越小越先施放'))
            row = QHBoxLayout()
            for field, (label, maximum, tip) in enumerate(fields):
                row.addWidget(self._field(label, maximum, tip,
                                          f'TXT_MASTER_{index}_{field}'), 1)
            content.addLayout(row)
            column.addWidget(card)
        column.addStretch()
        return self._scroll_page(page)

    def _help_page(self):
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(22, 22, 22, 22)
        column.setSpacing(14)
        for title, body in (
            ('面數與回合', '面數 0 表示停用。面數超過關卡總波數時，程式按最後一面判斷。技能的回合欄位限制指定面數最早何時施放，後續面數只要技能可用仍可能施放。'),
            ('對象', '場上由左到右為 1、2、3。全體或自身技能可填任一對象。'),
            ('順序', '同回合要施放多個技能時，數字越小越先施放，0 排在 1 前面。'),
            ('寶具', '從指定面數起，出卡時若寶具可用就會選用。同回合有多個寶具時，數字越小越先出。敵方目標由程式選擇剩餘 HP 最高的敵人。'),
            ('後備從者', '後備 4–6 號換上場後，程式讀取該號位的技能與寶具設定。技能對象仍按場上位置填 1–3。'),
            ('換人技能', '御主技能 3：場上換下填 1–3，後備換上填 4–6。例如把 3 號換成 5 號，分別填 3 和 5。'),
        ):
            card, content = self._card()
            content.addWidget(self._heading(title))
            description = QLabel(body)
            description.setWordWrap(True)
            content.addWidget(description)
            column.addWidget(card)
        column.addStretch()
        return self._scroll_page(page)

    def _values(self):
        return {
            'skillInfo': [[[getattr(self, f'TXT_SKILL_{i}_{j}_{k}').value()
                            for k in range(4)] for j in range(3)] for i in range(6)],
            'houguInfo': [[getattr(self, f'TXT_HOUGU_{i}_{j}').value()
                           for j in range(2)] for i in range(6)],
            'masterSkill': [[getattr(self, f'TXT_MASTER_{i}_{j}').value()
                             for j in range(4 + (i == 2))] for i in range(3)],
        }

    def _show_values(self, values):
        for i in range(6):
            for j in range(3):
                for k in range(4):
                    getattr(self, f'TXT_SKILL_{i}_{j}_{k}').setValue(values['skillInfo'][i][j][k])
            for j in range(2):
                getattr(self, f'TXT_HOUGU_{i}_{j}').setValue(values['houguInfo'][i][j])
        for i in range(3):
            for j in range(4 + (i == 2)):
                getattr(self, f'TXT_MASTER_{i}_{j}').setValue(values['masterSkill'][i][j])

    def _read_team(self, name):
        values = {key: ast.literal_eval(self.teamup[name][key])
                  for key in ('skillInfo', 'houguInfo', 'masterSkill')}
        master_skills = values['masterSkill']
        if len(master_skills[2]) == 4:
            wave, turn, target, priority = master_skills[2]
            values['masterSkill'] = [*master_skills[:2], [wave, turn, target, 0, priority]]
        return values

    def _remember_current(self):
        if self.current_team:
            self.teamup[self.current_team] = {
                key: json.dumps(value, separators=(',', ':'))
                for key, value in self._values().items()
            }

    def load(self, team):
        if not team or team not in self.teamup:
            return
        if team != self.current_team:
            self._remember_current()
        try:
            values = self._read_team(team)
            self._show_values(values)
        except (KeyError, ValueError, SyntaxError, IndexError, TypeError) as error:
            QMessageBox.warning(self, '編隊設定', f'無法讀取「{team}」：{error}')
            if self.current_team:
                self.CBB_TEAM.setCurrentText(self.current_team)
            return
        self.current_team = team
        self.plan_page.reset()
        self.BTN_DUPLICATE.setEnabled(True)

    def save(self):
        self._remember_current()
        try:
            with TEAMUP_FILE.open('w', encoding='utf-8') as output:
                self.teamup.write(output)
        except OSError as error:
            QMessageBox.critical(self, '編隊設定', f'無法儲存設定：{error}')
            return False
        return True

    def reset(self):
        self._show_values(self._read_team('DEFAULT'))
        self.plan_page.reset()

    def add_team(self):
        name, ok = QInputDialog.getText(self, '新增編隊', '編隊名稱：')
        name = name.strip()
        if not ok or not self._valid_name(name):
            return
        self._remember_current()
        self.teamup[name] = {
            key: json.dumps(value, separators=(',', ':'))
            for key, value in self._read_team('DEFAULT').items()
        }
        self.CBB_TEAM.addItem(name)
        self.CBB_TEAM.setCurrentText(name)
        self.load(name)

    def duplicate_team(self):
        source = self.current_team
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, '複製編隊', f'複製「{source}」為新編隊：', text=f'{source} - 複製'
        )
        name = name.strip()
        if not ok or not self._valid_name(name):
            return
        self._remember_current()
        self.teamup[name] = dict(self.teamup[source])
        self.CBB_TEAM.addItem(name)
        self.CBB_TEAM.setCurrentText(name)
        self.load(name)

    def rename_team(self):
        old = self.current_team
        if not old:
            return
        name, ok = QInputDialog.getText(self, '編隊改名', '新名稱：', text=old)
        name = name.strip()
        if not ok or name == old or not self._valid_name(name):
            return
        self._remember_current()
        self.teamup[name] = dict(self.teamup[old])
        del self.teamup[old]
        self.CBB_TEAM.setItemText(self.CBB_TEAM.currentIndex(), name)
        self.current_team = name

    def delete_team(self):
        name = self.current_team
        if not name:
            return
        if QMessageBox.question(self, '刪除編隊', f'確定刪除「{name}」？') != QMessageBox.StandardButton.Yes:
            return
        del self.teamup[name]
        self.current_team = None
        self.CBB_TEAM.removeItem(self.CBB_TEAM.currentIndex())
        if self.CBB_TEAM.count():
            self.load(self.CBB_TEAM.currentText())
        else:
            self.reset()
            self.BTN_DUPLICATE.setEnabled(False)

    def _valid_name(self, name):
        if not name or any(char in name for char in '[]\n\r') or name.upper() == 'DEFAULT':
            QMessageBox.warning(self, '編隊名稱', '請輸入有效且非 DEFAULT 的編隊名稱。')
            return False
        if name in self.teamup:
            QMessageBox.warning(self, '編隊名稱', '已有同名編隊。')
            return False
        return True

    def reset_servant(self):
        position, ok = QInputDialog.getInt(self, '單位快速設定', '從者位置 (1–6)：', 1, 1, 6)
        if ok:
            self._set_servant(position - 1, 1)

    def _set_servant(self, index, stage):
        target = index % 3 + 1
        for skill in range(3):
            for field, value in enumerate((stage, 1, target, 1)):
                getattr(self, f'TXT_SKILL_{index}_{skill}_{field}').setValue(value)
        for field, value in enumerate((stage, 1)):
            getattr(self, f'TXT_HOUGU_{index}_{field}').setValue(value)

    def global_reset(self, by_position):
        for index in range(6):
            self._set_servant(index, index + 1 if by_position else 1)
        self.plan_page.reset()

    def _refresh_plan(self):
        if self.tabs.currentWidget() is self.plan_page:
            self.plan_page.refresh()

    def accept(self):
        if not self.save():
            return
        self.use()

    def use(self):
        values = self._values()
        fgoKernel.ClassicTurn.skillInfo = values['skillInfo']
        fgoKernel.ClassicTurn.houguInfo = values['houguInfo']
        fgoKernel.ClassicTurn.masterSkill = values['masterSkill']
        outer_team = getattr(self.parentWidget(), 'TXT_TEAM', None)
        if outer_team is not None:
            outer_team.setValue(self.TXT_TEAM.value())
        fgoKernel.Main.teamIndex = self.TXT_TEAM.value()
        super().accept()
