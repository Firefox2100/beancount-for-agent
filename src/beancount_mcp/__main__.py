import uvicorn

from beancount_mcp.api.app import create_app
from beancount_mcp.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
