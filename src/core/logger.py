import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

if getattr(sys, "frozen", False):
    _PASTA_BASE = os.path.dirname(sys.executable)
else:
    _PASTA_BASE = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

PASTA_DADOS = os.path.join(_PASTA_BASE, "data")
ARQUIVO_LOG = os.path.join(PASTA_DADOS, "capri.log")

_LOGS_CONFIGURADOS = False


def configurar_logs(nivel: int = logging.INFO) -> logging.Logger:
    """Configura o logger raiz da Capri (arquivo rotativo + console quando houver terminal)."""
    global _LOGS_CONFIGURADOS

    logger = logging.getLogger("capri")
    if _LOGS_CONFIGURADOS and logger.handlers:
        return logger

    os.makedirs(PASTA_DADOS, exist_ok=True)
    logger.setLevel(nivel)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    arquivo_handler = RotatingFileHandler(
        ARQUIVO_LOG,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    arquivo_handler.setFormatter(formatter)
    logger.addHandler(arquivo_handler)

    # Em pythonw.exe ou Capri.exe (console=False), sys.stderr pode ser None
    if sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    def _tratar_excecao(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Erro fatal não tratado",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def _tratar_excecao_thread(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "Erro não tratado na thread '%s'",
            getattr(args.thread, "name", "desconhecida"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _tratar_excecao
    threading.excepthook = _tratar_excecao_thread

    _LOGS_CONFIGURADOS = True
    logger.info("=== Sessão da Capri iniciada (log em %s) ===", ARQUIVO_LOG)
    return logger


def obter_logger(nome: str | None = None) -> logging.Logger:
    """Retorna o logger raiz da Capri ou um sub-logger (ex: 'capri.voz')."""
    if not nome:
        return logging.getLogger("capri")
    if nome.startswith("capri"):
        return logging.getLogger(nome)
    return logging.getLogger(f"capri.{nome}")