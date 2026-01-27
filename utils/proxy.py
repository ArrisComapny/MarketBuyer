from database.models import Proxy


def proxy_title(p: Proxy) -> str:
    """Формирует человекочитаемую строку прокси для отображения в UI."""

    return f"{p.proxy_scheme}://{p.host}:{p.port}"
