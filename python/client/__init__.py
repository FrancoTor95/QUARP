try:
    from client.core import QUARPCore
    from client.cli import QUARPConsole
except ModuleNotFoundError:
    from .core import QUARPCore
    from .cli import QUARPConsole
