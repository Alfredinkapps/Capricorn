import os
import sys

PASTA_SRC = os.path.dirname(os.path.abspath(__file__))
if PASTA_SRC not in sys.path:
    sys.path.insert(0, PASTA_SRC)

from core.logger import configurar_logs
from core.engine import iniciar_capri


if __name__ == "__main__":
    configurar_logs()
    iniciar_capri()