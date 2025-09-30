import logging

import uvicorn

from booking.api.app import create_app
from booking.config import get_settings


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8000, proxy_headers=True)


if __name__ == "__main__":
    main()
