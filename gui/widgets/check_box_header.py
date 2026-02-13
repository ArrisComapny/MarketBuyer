from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QMouseEvent
from PySide6.QtWidgets import QStyleOptionButton, QStyle, QWidget, QHeaderView


class CheckBoxHeader(QHeaderView):
    """
    Заголовок таблицы с checkbox в первой колонке (Select All).
    Позволяет выделять/снимать выделение со всех строк одним кликом.
    """
    clicked = Signal(Qt.CheckState)

    CHECK_COLUMN = 0

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)

        self._checkbox_rect = QRect()
        self._state = Qt.CheckState.Unchecked

        self.setSectionsClickable(True)

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        """Рисует стандартный заголовок и добавляет checkbox в первой колонке (logical_index == CHECK_COLUMN)."""
        super().paintSection(painter, rect, logical_index)

        if logical_index != self.CHECK_COLUMN:
            return

        option = self._create_checkbox_option(rect)
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Клик по checkbox заголовка переключает состояние и emit сигнал."""
        if self._checkbox_rect.contains(event.pos()):
            self._toggle_state()
            self.clicked.emit(self._state)
            return

        super().mousePressEvent(event)

    def setState(self, state: Qt.CheckState) -> None:
        """Принудительно устанавливает состояние checkbox в заголовке."""
        if self._state == state:
            return

        self._state = state
        self.viewport().update()

    def _toggle_state(self) -> None:
        """Переключает состояние чекбокса Checked / Unchecked."""
        self._state = (
            Qt.CheckState.Unchecked
            if self._state == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        self.viewport().update()

    def _create_checkbox_option(self, section_rect: QRect) -> QStyleOptionButton:
        """Создаёт и настраивает QStyleOptionButton для чекбокса."""
        option = QStyleOptionButton()
        option.state = QStyle.StateFlag.State_Enabled

        if self._state == Qt.CheckState.Checked:
            option.state |= QStyle.StateFlag.State_On
        elif self._state == Qt.CheckState.PartiallyChecked:
            option.state |= QStyle.StateFlag.State_NoChange
        else:
            option.state |= QStyle.StateFlag.State_Off

        size = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
        x = section_rect.x() + (section_rect.width() - size) // 2
        y = section_rect.y() + (section_rect.height() - size) // 2

        self._checkbox_rect = QRect(x, y, size, size)
        option.rect = self._checkbox_rect

        return option
