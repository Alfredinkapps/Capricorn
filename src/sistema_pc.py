import os
import re
import winreg
import ctypes
import threading
from datetime import datetime
from hud import CapriHUD
from abrir_apps import verificar_abertura_rapida
from fechar_apps import verificar_fechamento_rapido
from spotify_control import ajustar_volume_spotify, controlar_midia_windows
from dicionario_comandos import (
    COMANDOS_MIDIA,
    COMANDOS_VOLUME,
    COMANDOS_ENERGIA,
    COMANDOS_INTERFACE,
    normalizar_frase
)

_REGEX_NUMERO_VOLUME = re.compile(r"\b(\d{1,3})\b")


def mudar_tema_windows(modo: str) -> str:
    valor = 0 if modo.lower() == "escuro" else 1
    caminho_registro = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    try:
        chave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho_registro, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(chave, "AppsUseLightTheme", 0, winreg.REG_DWORD, valor)
        winreg.SetValueEx(chave, "SystemUsesLightTheme", 0, winreg.REG_DWORD, valor)
        winreg.CloseKey(chave)
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 100, 0)
        return f"Tema do Windows alterado para o modo {modo}."
    except Exception as e:
        return f"Erro ao modificar o tema: {str(e)}"


def controlar_energia_pc(acao: str) -> str:
    acao_limpa = acao.lower().strip()
    try:
        if acao_limpa == "bloquear":
            threading.Timer(1.5, ctypes.windll.user32.LockWorkStation).start()
            return "Bloqueando a tela."
        elif acao_limpa == "suspender":
            threading.Timer(2.0, lambda: ctypes.windll.powrprof.SetSuspendState(0, 1, 0)).start()
            return "Colocando o computador em modo de suspensão."
        elif acao_limpa == "cancelar":
            os.system("shutdown /a")
            return "Desligamento cancelado. O computador continuará ligado."
        elif acao_limpa == "desligar":
            os.system("shutdown /s /t 10")
            return "Desligando o computador em 10 segundos."
        elif acao_limpa == "reiniciar":
            os.system("shutdown /r /t 10")
            return "Reiniciando o computador em 10 segundos."
        return f"Comando {acao} não reconhecido."
    except Exception as e:
        return f"Erro no comando de energia: {str(e)}"


def tentar_execucao_instantanea(frase: str, hud: CapriHUD) -> str:
    frase_norm = normalizar_frase(frase)

    # 1. Volume do Spotify
    if any(ctx in frase_norm for ctx in COMANDOS_VOLUME["Contexto"]):
        if any(p in frase_norm for p in COMANDOS_VOLUME["maximo"]):
            return ajustar_volume_spotify("aumentar", 100)
        if any(p in frase_norm for p in COMANDOS_VOLUME["minimo"]):
            return ajustar_volume_spotify("diminuir", 10)

        numeros = _REGEX_NUMERO_VOLUME.findall(frase_norm)
        if numeros:
            return ajustar_volume_spotify("definir", int(numeros[0]))

        if any(p in frase_norm for p in COMANDOS_VOLUME["aumentar"]):
            return ajustar_volume_spotify("aumentar")
        if any(p in frase_norm for p in COMANDOS_VOLUME["diminuir"]):
            return ajustar_volume_spotify("diminuir")

    # 2. Reprodução de mídia (Pause / Play / Próxima / Anterior)
    for acao_midia, gatilhos in COMANDOS_MIDIA.items():
        if any(cmd in frase_norm for cmd in gatilhos):
            return controlar_midia_windows(acao_midia)

    # 3. Energia, Bloqueio e Suspensão
    if any(p in frase_norm for p in COMANDOS_ENERGIA["cancelar"]):
        return controlar_energia_pc("cancelar")

    if any(v in frase_norm for v in COMANDOS_ENERGIA["bloquear"]) and "desbloquear" not in frase_norm:
        return controlar_energia_pc("bloquear")

    if any(v in frase_norm for v in COMANDOS_ENERGIA["suspender"]):
        return controlar_energia_pc("suspender")

    if any(v in frase_norm for v in COMANDOS_ENERGIA["verbos_desligar"]) and any(a in frase_norm for a in COMANDOS_ENERGIA["alvos_pc"]):
        return controlar_energia_pc("desligar")

    if any(v in frase_norm for v in COMANDOS_ENERGIA["verbos_reiniciar"]) and any(a in frase_norm for a in COMANDOS_ENERGIA["alvos_pc"]):
        return controlar_energia_pc("reiniciar")

    # 4. Interface, Mute, Horas e Tema
    if any(cmd in frase_norm for cmd in COMANDOS_INTERFACE["configuracoes"]):
        hud.root.after(0, hud.abrir_configuracoes)
        return "Abrindo a central de configurações."

    if any(cmd in frase_norm for cmd in COMANDOS_INTERFACE["mutar"]):
        if not hud.pausada:
            hud.root.after(0, hud.alternar_pausa)
        return "Microfone silenciado."

    if any(p in frase_norm for p in COMANDOS_INTERFACE["horas"]):
        agora = datetime.now()
        return f"Agora são {agora.strftime('%H horas e %M minutos')}."

    if any(p in frase_norm for p in ("tema", "modo", "cor")):
        if any(t in frase_norm for t in ("escuro", "noturno", "dark")):
            return mudar_tema_windows("escuro")
        elif any(t in frase_norm for t in ("claro", "light", "dia")):
            return mudar_tema_windows("claro")

    # 5. Fechar ou Abrir Aplicativos
    resposta_fechar = verificar_fechamento_rapido(frase_norm)
    if resposta_fechar:
        return resposta_fechar

    resposta_abrir = verificar_abertura_rapida(frase_norm)
    if resposta_abrir:
        return resposta_abrir

    return ""