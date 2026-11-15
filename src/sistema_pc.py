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


def mudar_tema_windows(modo: str) -> str:
    valor = 0 if modo.lower() == "escuro" else 1
    caminho_registro = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    try:
        chave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho_registro, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(chave, "AppsUseLightTheme", 0, winreg.REG_DWORD, valor)
        winreg.SetValueEx(chave, "SystemUsesLightTheme", 0, winreg.REG_DWORD, valor)
        winreg.CloseKey(chave)
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 100, 0)
        return f"Interface visual do sistema alterada para o modo {modo}."
    except Exception as e:
        return f"Erro ao modificar o tema: {str(e)}"


def controlar_energia_pc(acao: str) -> str:
    acao_limpa = acao.lower().strip()
    try:
        if acao_limpa == "bloquear":
            threading.Timer(2.0, ctypes.windll.user32.LockWorkStation).start()
            return "Bloqueando a estação de trabalho."
        elif acao_limpa == "suspender":
            threading.Timer(2.5, lambda: ctypes.windll.powrprof.SetSuspendState(0, 1, 0)).start()
            return "Colocando o computador em modo de suspensão."
        elif acao_limpa == "cancelar":
            os.system("shutdown /a")
            return "Sequência de desligamento abortada. O computador permanecerá ligado."
        elif acao_limpa == "desligar":
            os.system("shutdown /s /t 10")
            return "Protocolo de encerramento confirmado. Desligando o computador em 10 segundos."
        elif acao_limpa == "reiniciar":
            os.system("shutdown /r /t 10")
            return "Reiniciando o computador em 10 segundos."
        return f"Comando de energia {acao} não reconhecido."
    except Exception as e:
        return f"Erro ao executar comando de energia: {str(e)}"


def tentar_execucao_instantanea(frase: str, hud: CapriHUD) -> str:
    # 1. Volume do Spotify
    if "volume" in frase or "som" in frase or "música está muito" in frase:
        if any(p in frase for p in ["máximo", "maximo", "tudo", "100"]):
            return ajustar_volume_spotify("aumentar", 100)
        if any(p in frase for p in ["mínimo", "minimo", "baixinho"]):
            return ajustar_volume_spotify("diminuir", 10)

        numeros = re.findall(r"\b(\d{1,3})\b", frase)
        if numeros:
            return ajustar_volume_spotify("definir", int(numeros[0]))

        if any(p in frase for p in ["aumentar", "aumenta", "aumente", "subir", "sobe", "mais alto"]):
            return ajustar_volume_spotify("aumentar")
        if any(p in frase for p in ["abaixar", "abaixa", "abaixe", "diminuir", "diminui", "diminua", "baixar", "baixa", "muito alta", "muito alto"]):
            return ajustar_volume_spotify("diminuir")

    # 2. Reprodução de mídia
    if any(cmd in frase for cmd in ["pausar música", "pausa a música", "pause a música", "pausar spotify", "pausar reprodução", "parar música", "para a música"]):
        return controlar_midia_windows("pausar")

    if any(cmd in frase for cmd in ["continuar música", "continue a música", "continua a música", "retomar música", "voltar a música", "despausar", "dar play", "continuar spotify"]):
        return controlar_midia_windows("continuar")

    if any(cmd in frase for cmd in ["próxima música", "pular música", "passar música", "próxima faixa"]):
        return controlar_midia_windows("proxima")

    if any(cmd in frase for cmd in ["música anterior", "voltar faixa", "faixa anterior"]):
        return controlar_midia_windows("anterior")

    # 3. Energia, Bloqueio e Suspensão
    if any(p in frase for p in ["cancelar desligamento", "cancele o desligamento", "abortar desligamento", "não desligar", "nao desligar"]):
        return controlar_energia_pc("cancelar")

    if any(v in frase for v in ["bloquear", "bloqueia", "bloqueie", "trancar", "tranca", "tranque"]) and "desbloquear" not in frase:
        return controlar_energia_pc("bloquear")

    if any(v in frase for v in ["suspender", "suspende", "suspenda", "suspensão", "suspensao", "hibernar", "hiberna", "dormir"]):
        return controlar_energia_pc("suspender")

    alvos_pc = ["computador", "pc", "p c", "notebook", "máquina", "maquina", "sistema"]
    if any(v in frase for v in ["desligar", "desliga", "desligue"]) and any(a in frase for a in alvos_pc):
        return controlar_energia_pc("desligar")

    if any(v in frase for v in ["reiniciar", "reinicia", "reinicie"]) and any(a in frase for a in alvos_pc):
        return controlar_energia_pc("reiniciar")

    # 4. Interface, Mute, Horas e Tema
    if any(cmd in frase for cmd in ["abrir configurações", "abra as configurações", "configurar capri", "configurações"]):
        hud.root.after(0, hud.abrir_configuracoes)
        return "Abrindo a central de configurações e aplicativos."

    if any(cmd in frase for cmd in ["mutar", "silenciar", "modo silencioso", "fique quieta", "pausar escuta"]):
        if not hud.pausada:
            hud.root.after(0, hud.alternar_pausa)
        return "Microfone silenciado. Clique no botão da interface quando quiser me chamar novamente."

    if any(p in frase for p in ["que horas são", "que hora é", "horário", "que dia é hoje", "horas"]):
        agora = datetime.now()
        return f"Agora são {agora.strftime('%H horas e %M minutos')}."

    if "tema" in frase or "modo" in frase or "cor" in frase:
        if "escuro" in frase or "noturno" in frase or "dark" in frase:
            return mudar_tema_windows("escuro")
        elif "claro" in frase or "light" in frase:
            return mudar_tema_windows("claro")

    resposta_fechar = verificar_fechamento_rapido(frase)
    if resposta_fechar:
        return resposta_fechar

    resposta_abrir = verificar_abertura_rapida(frase)
    if resposta_abrir:
        return resposta_abrir

    return ""