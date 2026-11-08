from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


@dataclass
class Action:
    key: int
    values: list
    draft: bool = False
    preview_order: float | None = None

    @property
    def order(self):
        if self.preview_order is not None:
            return self.preview_order
        return self.values[-1] + self.key / 32

    @property
    def np(self):
        return self.key >= 21

    @property
    def slot(self):
        if self.np:
            return self.key - 20
        return self.key // 3 + 1 if self.key < 18 else 0

    @property
    def label(self):
        if self.np:
            return '寶具'
        return f'技 {self.key % 3 + 1}' if self.slot else f'御主技 {self.key - 17}'

    @property
    def name(self):
        return f'從者 {self.slot:02d}・{self.label}' if self.slot else self.label

    @property
    def step(self):
        return self.values[0], 1 if self.np else max(1, self.values[1])

    @property
    def swap(self):
        return self.key == 20 and self.values[3] != 0

    @property
    def targets(self):
        return ('預設' if self.slot else '不指定', '左側', '中間', '右側')

    def description(self):
        standby = '上場後可放・' if self.slot > 3 else ''
        if self.np:
            return f'{standby}第 {self.values[0]} 面起，寶具可用時'
        if self.swap:
            return f'換人・{self.values[2]} 號下場 → {self.values[3]} 號上場'
        target = self.values[2]
        return f'{standby}對象・{self.targets[target] if 0 <= target < 4 else self.targets[0]}'


class TeamupPlan(QWidget):
    def __init__(self, read_values, write_values):
        super().__init__()
        self.read_values = read_values
        self.write_values = write_values
        self.drafts = []
        self.extra_steps = set()
        self.current = (1, 1)
        self.selected = None
        self.cards = {}
        self.buttons = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)
        hint = QLabel('分段表示最早施放時間。同一招只會儲存一筆，額外加入的項目會標為「僅預覽」。')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        root.addWidget(hint)
        columns = QHBoxLayout()
        columns.setSpacing(12)
        root.addLayout(columns, 1)
        roster = QWidget()
        roster_layout = QVBoxLayout(roster)
        roster_layout.setContentsMargins(0, 0, 6, 0)
        roster_layout.setSpacing(9)
        for start, title in ((0, '前排'), (3, '後備')):
            roster_layout.addWidget(QLabel(title))
            row = QHBoxLayout()
            roster_layout.addLayout(row)
            for i in range(start, start + 3):
                card = QFrame()
                card.setObjectName('card')
                grid = QGridLayout(card)
                grid.setContentsMargins(7, 7, 7, 7)
                grid.setHorizontalSpacing(4)
                label = QLabel(f'從者 {i + 1:02d}')
                label.setAlignment(Qt.AlignCenter)
                label.setWordWrap(True)
                label.setStyleSheet('background: #173659; border-radius: 6px; padding: 7px; font-weight: bold;')
                self.cards[i + 1] = label
                grid.addWidget(label, 0, 0, 1, 3)
                for offset, key in enumerate((3 * i, 3 * i + 1, 3 * i + 2, 21 + i)):
                    action = Action(key, [])
                    button = self._button(action.label, partial(self.toggle, key), checkable=True)
                    button.setAccessibleName(action.name)
                    button.setStyleSheet('padding: 8px 4px;')
                    self.buttons[key] = button
                    if action.np:
                        grid.addWidget(button, 2, 0, 1, 3)
                    else:
                        grid.addWidget(button, 1, offset)
                        grid.setColumnStretch(offset, 1)
                row.addWidget(card, 1)
        roster_layout.addWidget(QLabel('御主技能'))
        row = QHBoxLayout()
        roster_layout.addLayout(row)
        for key in range(18, 21):
            button = self._button(Action(key, []).name, partial(self.toggle, key), checkable=True)
            self.buttons[key] = button
            row.addWidget(button)
        roster_layout.addStretch()
        columns.addWidget(self._scroll(roster), 5)

        queue_card = QFrame()
        queue_card.setObjectName('card')
        queue_panel = QVBoxLayout(queue_card)
        queue_panel.setContentsMargins(10, 8, 10, 8)
        columns.addWidget(queue_card, 4)
        title = QHBoxLayout()
        title.addWidget(QLabel('施放順序'))
        title.addStretch()
        self.clear_button = self._button('清空設定', self.clear)
        title.addWidget(self.clear_button)
        queue_panel.addLayout(title)
        queue = QWidget()
        self.queue_layout = QVBoxLayout(queue)
        self.queue_layout.setContentsMargins(0, 0, 4, 0)
        self.queue_layout.setAlignment(Qt.AlignTop)
        self.queue = self._scroll(queue)
        queue_panel.addWidget(self.queue, 1)

        bottom_card = QFrame()
        bottom_card.setObjectName('card')
        bottom = QHBoxLayout(bottom_card)
        bottom.setContentsMargins(12, 8, 12, 8)
        self.detail = QVBoxLayout()
        bottom.addLayout(self.detail, 1)
        self.next_turn = self._button('下個回合', partial(self.add_step, False))
        self.next_wave = self._button('下一面', partial(self.add_step, True))
        bottom.addWidget(self.next_turn, 0, Qt.AlignBottom)
        bottom.addWidget(self.next_wave, 0, Qt.AlignBottom)
        root.addWidget(bottom_card)

    @staticmethod
    def _button(text, callback, checkable=False):
        button = QPushButton(text)
        button.setAutoDefault(False)
        button.setCheckable(checkable)
        button.clicked.connect(lambda checked: callback())
        return button

    @staticmethod
    def _scroll(widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    @staticmethod
    def _empty(layout):
        while layout.count():
            item = layout.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()

    def reset(self):
        self.drafts.clear()
        self.extra_steps.clear()
        self.current = (1, 1)
        self.selected = None
        self.refresh()

    def refresh(self):
        self.data = self.read_values()
        values = [skill for servant in self.data['skillInfo'] for skill in servant]
        values += self.data['masterSkill'] + self.data['houguInfo']
        self.actions = [Action(key, fields) for key, fields in enumerate(values)]
        max_turns = {1: 1}
        for wave, turn in self.extra_steps | {action.step for action in self._entries() if action.values[0]}:
            max_turns[wave] = max(max_turns.get(wave, 1), turn)
        self.steps = [(wave, turn) for wave in range(1, max(max_turns) + 1)
                      for turn in range(1, max_turns.get(wave, 1) + 1)]
        if self.current not in self.steps:
            self.current = self.steps[0]
            self.selected = None
        self._render()

    def _entries(self):
        return [*self.actions, *self.drafts]

    def _rows(self, step):
        return sorted((action for action in self._entries() if action.step == step),
                      key=lambda action: (action.np, action.order))

    def _current_action(self, key, draft=None):
        wave, turn = self.current
        step = (wave, 1 if self.actions[key].np else turn)
        return next((action for action in self._rows(step)
                     if action.key == key and (draft is None or action.draft == draft)), None)

    def _commit(self):
        self.write_values(self.data)
        self.refresh()

    def toggle(self, key):
        existing = self._current_action(key)
        if existing:
            self.remove(existing)
            return
        source = self.actions[key]
        wave, turn = self.current
        draft = source.values[0] != 0
        action = Action(key, source.values.copy(), True) if draft else source
        if draft:
            self.drafts.append(action)
        action.values[0] = wave
        if not action.np:
            action.values[1] = turn
        ranks = [row.values[-1] for row in self._entries()
                 if row is not action and row.values[0] and row.np == action.np]
        action.values[-1] = min(15, max(ranks, default=-1) + 1)
        self.selected = (key, draft)
        self._commit()

    def choose(self, step, action=None):
        self.current = step
        self.selected = (action.key, action.draft) if action else None
        self._render()

    def _disable(self, action):
        if action.draft:
            self.drafts.remove(action)
        else:
            action.values[0] = 0
        if self.selected == (action.key, action.draft):
            self.selected = None

    def remove(self, action):
        self._disable(action)
        self._commit()

    def use_draft(self, action):
        source = self.actions[action.key]
        previous = source.values.copy()
        source.values[:] = action.values
        if previous[0]:
            action.values[:] = previous
            action.preview_order = None
        else:
            self.drafts.remove(action)
        self.selected = (action.key, False)
        self._commit()

    def move(self, action, neighbor):
        if action.draft or neighbor.draft:
            draft, anchor = (action, neighbor) if action.draft else (neighbor, action)
            rows = self._rows(draft.step)
            offset = 1 if rows.index(draft) < rows.index(anchor) else -1
            index = rows.index(anchor) + offset
            if 0 <= index < len(rows) and rows[index].np == draft.np:
                draft.preview_order = (anchor.order + rows[index].order) / 2
            else:
                draft.preview_order = anchor.order + offset
            self._render()
            return
        rows = sorted((row for row in self._entries() if row.values[0] and
                       row.np == action.np and row.draft == action.draft),
                      key=lambda row: (row.values[-1], row.key))
        first, second = rows.index(action), rows.index(neighbor)
        rows[first], rows[second] = rows[second], rows[first]
        rank = 0
        ranks = [rank]
        for previous, current in zip(rows, rows[1:]):
            rank += current.key <= previous.key
            ranks.append(rank)
        if rank > 15:
            QMessageBox.information(self, '施放順序', '這個順序超過優先值 0–15 的範圍。')
            return
        for row, rank in zip(rows, ranks):
            row.values[-1] = rank
        self._commit()

    def add_step(self, next_wave):
        wave, turn = self.steps[-1]
        self.current = (wave + 1, 1) if next_wave else (wave, turn + 1)
        self.extra_steps.add(self.current)
        self.selected = None
        self.refresh()
        self.queue.ensureWidgetVisible(self.last_heading)

    def remove_step(self, step):
        wave, turn = step
        retained = [other for other in self.steps if other != step]
        same_wave = any(other[0] == wave for other in retained)

        def shifted(other):
            other_wave, other_turn = other
            return (other_wave - int(not same_wave and other_wave > wave),
                    other_turn - int(other_wave == wave and other_turn > turn))

        for action in self._entries():
            action_wave, action_turn = action.step
            if action_wave == wave and (not same_wave or (not action.np and action_turn == turn)):
                self._disable(action)
            elif action_wave:
                new_wave, new_turn = shifted(action.step)
                action.values[0] = new_wave
                if not action.np and action_turn != new_turn:
                    action.values[1] = new_turn
        self.extra_steps = {shifted(other) for other in retained}
        self.current = shifted(self.current) if self.current != step else (
            shifted(retained[min(self.steps.index(step), len(retained) - 1)]) if retained else (1, 1)
        )
        self.selected = None
        self._commit()

    def clear(self):
        if QMessageBox.question(self, '清空設定', '確定清空此隊伍的技能、寶具和回合設定嗎？') != QMessageBox.Yes:
            return
        for action in self.actions:
            action.values[0] = 0
        self.write_values(self.data)
        self.reset()

    def _render(self):
        swap = next((action for action in self._rows(self.current) if action.swap), None)
        for slot, card in self.cards.items():
            text = f'從者 {slot:02d}'
            if swap and swap.values[2] == slot:
                text += f'\n換人後：從者 {swap.values[3]:02d}'
            if swap and swap.values[3] == slot:
                text += f'\n換到場上 {swap.values[2]} 號位'
            card.setText(text)
        for key, button in self.buttons.items():
            button.setChecked(self._current_action(key) is not None)
        self.clear_button.setEnabled(len(self.steps) > 1 or any(action.values[0] for action in self._entries()))
        self.next_turn.setEnabled(self.steps[-1][1] < 9)
        self.next_wave.setEnabled(self.steps[-1][0] < 9)
        scroll = self.queue.verticalScrollBar()
        scroll_value = scroll.value()
        self._empty(self.queue_layout)
        for step in self.steps:
            self._render_step(step)
        self.queue.widget().layout().activate()
        scroll.setValue(scroll_value)
        self._render_detail()

    def _render_step(self, step):
        wave, turn = step
        section = QFrame()
        section.setObjectName('card')
        layout = QVBoxLayout(section)
        header = QHBoxLayout()
        heading = self._button(f'第 {wave} 面・第 {turn} 回合', partial(self.choose, step), checkable=True)
        heading.setChecked(step == self.current)
        self.last_heading = heading
        header.addWidget(heading)
        header.addStretch()
        header.addWidget(self._button('移除回合', partial(self.remove_step, step)))
        layout.addLayout(header)
        rows = self._rows(step)
        if not rows:
            layout.addWidget(QLabel('尚未加入施放設定'))
        for index, action in enumerate(rows):
            row = QHBoxLayout()
            text = f'{index + 1}. {action.name}' + ('・僅預覽' if action.draft else '')
            summary = action.description()
            if action.slot > 3 and not action.np and any(
                later.swap and later.values[3] == action.slot for later in rows[index + 1:]
            ):
                summary += '\n要換人後接這招，請把換人往前移'
            labels = QVBoxLayout()
            labels.setSpacing(3)
            button = self._button(text, partial(self.choose, step, action))
            button.setStyleSheet('text-align: left; padding: 5px;')
            labels.addWidget(button)
            description = QLabel(summary)
            description.setWordWrap(True)
            description.setObjectName('hint')
            labels.addWidget(description)
            row.addLayout(labels, 1)
            for direction, arrow in ((-1, '↑'), (1, '↓')):
                other = index + direction
                valid = 0 <= other < len(rows) and rows[other].np == action.np
                neighbor = rows[other] if valid else action
                button = self._button(arrow, partial(self.move, action, neighbor))
                button.setStyleSheet('padding: 5px 7px;')
                button.setEnabled(valid)
                button.setAccessibleName(('上移 ' if direction < 0 else '下移 ') + action.name)
                row.addWidget(button)
            remove = self._button('移除', partial(self.remove, action))
            remove.setStyleSheet('padding: 5px 7px;')
            row.addWidget(remove)
            layout.addLayout(row)
        self.queue_layout.addWidget(section)

    def _choice(self, layout, label, options, value, callback):
        layout.addWidget(QLabel(label))
        combo = QComboBox()
        for text, key in options:
            combo.addItem(text, key)
        combo.setCurrentIndex(combo.findData(value))
        combo.activated.connect(lambda index: callback(combo.itemData(index)))
        layout.addWidget(combo)

    def _set_field(self, action, index, value):
        action.values[index] = value
        self._commit()

    def _set_swap(self, action, enabled):
        if enabled and action.values[2] not in (1, 2, 3):
            action.values[2] = 1
        self._set_field(action, 3, (action.values[3] or 4) if enabled else 0)

    def _render_detail(self):
        self._empty(self.detail)
        action = self._current_action(*self.selected) if self.selected else None
        if not action:
            self.detail.addWidget(QLabel('點選清單項目可調整對象'))
            return
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        layout.addLayout(header, 0, 0)
        header.addWidget(QLabel(action.name + ('・僅預覽' if action.draft else '')))
        if action.key == 20:
            self._choice(header, '類型', [('一般技能', False), ('換人', True)],
                         action.swap, partial(self._set_swap, action))
        if action.draft:
            header.addWidget(self._button('改用此筆設定', partial(self.use_draft, action)))
        header.addStretch()
        fields = QHBoxLayout()
        layout.addLayout(fields, 1, 0)
        if action.swap:
            self._choice(fields, '場上換下', [(str(n), n) for n in (1, 2, 3)],
                         action.values[2], partial(self._set_field, action, 2))
            self._choice(fields, '後備換上', [(str(n), n) for n in (4, 5, 6)],
                         action.values[3], partial(self._set_field, action, 3))
        elif not action.np:
            self._choice(fields, '對象', [(text, i) for i, text in enumerate(action.targets)],
                         action.values[2], partial(self._set_field, action, 2))
        fields.addStretch()
        self.detail.addWidget(panel)
