import os
import sys
import logging
import threading
from logging.handlers import RotatingFileHandler

from core.config import PASTA_DATA

ARQUIVO_LOG = os.path.join(PASTA_DATA, "capri.log")
_CONFIGURADO = False


def configurar_logs(nivel: int = logging.INFO) -> logging.Logger:
    """Configura o sistema global de logs da Capri (arquivo rotativo + terminal)."""
    global _CONFIGURADO
    logger_raiz = logging.getLogger("capri")

    if _CONFIGURADO:
        return logger_raiz

    os.makedirs(PASTA_DATA, exist_ok=True)
    logger_raiz.setLevel(nivel)
    logger_raiz.propagate = False

    formato = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Saída em arquivo rotativo (máx 2 MB por arquivo, até 3 backups)
    handler_arquivo = RotatingFileHandler(
        ARQUIVO_LOG,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler_arquivo.setLevel(nivel)
    handler_arquivo.setFormatter(formato)
    logger_raiz.addHandler(handler_arquivo)

    # 2. Saída no terminal (protegido para builds .exe sem console)
    if sys.stdout is not None:
        handler_console = logging.StreamHandler(sys.stdout)
        handler_console.setLevel(nivel)
        handler_console.setFormatter(formato)
        logger_raiz.addHandler(handler_console)

    # 3. Reduz ruído de bibliotecas externas
    for lib_ruidosa in ("urllib3", "httpx", "httpcore", "PIL", "google", "comtypes"):
        logging.getLogger(lib_ruidosa).setLevel(logging.WARNING)

    # 4. Captura crashes inesperados na thread principal e em threads secundárias
    def _tratar_excecao_global(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger_raiz.critical("Erro fatal não tratado", exc_info=(exc_type, exc_value, exc_traceback))

    def _tratar_excecao_thread(args):
        logger_raiz.critical(
            f"Erro não tratado na thread '{args.thread.name}'",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _tratar_excecao_global
    threading.excepthook = _tratar_excecao_thread

    _CONFIGURADO = True
    logger_raiz.info("=== Sessão da Capri iniciada (log em %s) ===", ARQUIVO_LOG)
    return logger_raiz


def obter_logger(nome_modulo: str) -> logging.Logger:
    """Retorna um logger filho padronizado (ex: 'capri.engine', 'capri.reigns')."""
    if not _CONFIGURADO:
        configurar_logs()
    return logging.getLogger(f"capri.{nome_modulo}")