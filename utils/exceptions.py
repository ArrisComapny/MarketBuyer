

class ScenarioWarning(Exception):
    """
    Базовое предупреждение сценария.
    Это НЕ системная ошибка, а бизнес-состояние.
    """
    pass


class NoProductsWarning(ScenarioWarning):
    """На странице нет товаров."""
    pass


class RequeueWarning(ScenarioWarning):
    """Нужно повторить выполнение (например, IP не сменился)."""
    pass