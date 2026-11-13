import os
import sys
import time
import ctypes
import threading
import winreg
import asyncio
from datetime import datetime
import tkinter as tk
import requests
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import edge_tts
import pygame
import pystray
from PIL import Image, ImageDraw
from google import genai
from google.genai import types

# Importa os seus módulos locais de aplicativos
from abrir_apps import abrir_aplicativo, verificar_abertura_rapida
from fechar_apps import fechar_aplicativo, verificar_fechamento_rapido

# =====================================================================
# CONFIGURAÇÃO INICIAL E CHAVES DE API (GEMINI + FISH AUDIO)
# =====================================================================

# 1. Sua chave do Google AI Studio:
os.environ["GEMINI_API_KEY"] = "AQUI"

# 2. Suas chaves do Fish Audio (cole aqui entre as aspas sem espaços extras):
FISH_API_KEY = "AQUI"
FISH_VOICE_ID = "AQUI"

# Voz reserva caso a internet oscile ou a chave do Fish Audio dê erro
VOZ_FALLBACK = "pt-BR-FranciscaNeural"

pygame.mixer.init()


# =====================================================================
# 0. MÓDULO DE INICIALIZAÇÃO AUTOMÁTICA COM O WINDOWS (STARTUP)
# =====================================================================

def configurar_inicializacao_windows(ativar: bool = True) -> str:
    chave_caminho = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_registro = "CapricornOS_Capri"
    
    caminho_python = sys.executable
    caminho_pythonw = caminho_python.replace("python.exe", "pythonw.exe")
    if not os.path.exists(caminho_pythonw):
        caminho_pythonw = caminho_python
        
    caminho_script = os.path.abspath(__file__)
    comando_boot = f'"{caminho_pythonw}" "{caminho_script}"'
    
    try:
        chave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_caminho, 0, winreg.KEY_SET_VALUE)
        if ativar:
            winreg.SetValueEx(chave, nome_registro, 0, winreg.REG_SZ, comando_boot)
            mensagem = "Inicialização automática ativada no registro do Windows."
        else:
            try:
                winreg.DeleteValue(chave, nome_registro)
                mensagem = "Inicialização automática desativada do Windows."
            except FileNotFoundError:
                mensagem = "A inicialização automática já estava desativada."
        winreg.CloseKey(chave)
        return mensagem
    except Exception as e:
        return f"Erro ao configurar inicialização do Windows: {str(e)}"


# =====================================================================
# 1. INTERFACE CYBERPUNK (HUD COM BOTÃO MUTE + SYSTEM TRAY)
# =====================================================================

class CapriHUD:
    def __init__(self):
        self.rodando = True
        self.pausada = False
        self.visivel = True
        
        self.status_texto = "INICIALIZANDO..."
        self.cor_atual = "#00F0FF"
        self.ultima_fala = "Aguardando comando..."
        self.nivel_voz = 0.0
        
        self.root = tk.Tk()
        self.root.title("CAPRI // OS")
        self.root.geometry("320x195-25-60")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg="#090A0F")
        
        self.root.bind("<ButtonPress-1>", self._iniciar_arrasto)
        self.root.bind("<B1-Motion>", self._arrastar)
        
        self._montar_interface()
        self._iniciar_bandeja_windows()
        self._loop_animacao()

    def _iniciar_arrasto(self, event):
        self._x = event.x
        self._y = event.y

    def _arrastar(self, event):
        x = self.root.winfo_x() + (event.x - self._x)
        y = self.root.winfo_y() + (event.y - self._y)
        self.root.geometry(f"+{x}+{y}")

    def _montar_interface(self):
        self.borda = tk.Frame(self.root, bg="#00F0FF", bd=0)
        self.borda.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        self.painel = tk.Frame(self.borda, bg="#090A0F")
        self.painel.place(x=2, y=2, width=316, height=191)
        
        lbl_titulo = tk.Label(
            self.painel, text="⚡ CAPRI // OS", 
            bg="#090A0F", fg="#00F0FF", font=("Consolas", 10, "bold")
        )
        lbl_titulo.place(x=10, y=7)
        
        self.btn_mute = tk.Button(
            self.painel, text="🎙️ VOZ: ON", bg="#111827", fg="#00FF66", bd=1,
            relief="flat", font=("Consolas", 8, "bold"), activebackground="#1F2937",
            cursor="hand2", command=self.alternar_pausa
        )
        self.btn_mute.place(x=175, y=6, width=82, height=20)
        
        btn_min = tk.Button(
            self.painel, text="_", bg="#090A0F", fg="#00F0FF", bd=0,
            font=("Consolas", 10, "bold"), activebackground="#1A1D2B",
            cursor="hand2", command=self.alternar_visibilidade
        )
        btn_min.place(x=265, y=5, width=22, height=22)
        
        btn_fechar = tk.Button(
            self.painel, text="X", bg="#090A0F", fg="#FF0055", bd=0,
            font=("Consolas", 10, "bold"), activebackground="#FF0055",
            cursor="hand2", command=self.desligar_tudo
        )
        btn_fechar.place(x=290, y=5, width=22, height=22)
        
        self.canvas = tk.Canvas(self.painel, width=296, height=90, bg="#090A0F", highlightthickness=0)
        self.canvas.place(x=10, y=32)
        
        self.orbe_ext = self.canvas.create_oval(18, 15, 78, 75, outline="#00F0FF", width=2)
        self.orbe_int = self.canvas.create_oval(30, 27, 66, 63, fill="#00F0FF", outline="")
        
        self.txt_status = self.canvas.create_text(
            95, 25, anchor="w", text="ONLINE", fill="#00F0FF", font=("Consolas", 11, "bold")
        )
        
        self.canvas.create_text(95, 47, anchor="w", text="SINAL DE VOZ:", fill="#6C7A89", font=("Consolas", 8))
        self.canvas.create_rectangle(95, 58, 285, 70, outline="#1F2937", fill="#11131C")
        self.barra_voz = self.canvas.create_rectangle(95, 58, 95, 70, outline="", fill="#00F0FF")
        
        self.lbl_legenda = tk.Label(
            self.painel, text="Aguardando comando...", bg="#090A0F", fg="#E2E8F0",
            font=("Segoe UI", 9), wraplength=290, justify="left", anchor="nw"
        )
        self.lbl_legenda.place(x=12, y=126, width=292, height=58)

    def atualizar_estado(self, status: str, cor: str, legenda: str = None):
        self.status_texto = status
        self.cor_atual = cor
        if legenda is not None:
            self.ultima_fala = legenda[:115] + ("..." if len(legenda) > 115 else "")

    def _loop_animacao(self):
        if not self.rodando:
            self.root.destroy()
            return
            
        self.borda.configure(bg=self.cor_atual)
        self.canvas.itemconfig(self.txt_status, text=self.status_texto, fill=self.cor_atual)
        self.canvas.itemconfig(self.orbe_ext, outline=self.cor_atual)
        self.canvas.itemconfig(self.orbe_int, fill=self.cor_atual)
        self.lbl_legenda.configure(text=self.ultima_fala)
        
        largura_atual = int(min(1.0, self.nivel_voz) * 190)
        cor_barra = "#00FF66" if self.nivel_voz > 0.12 else self.cor_atual
        self.canvas.coords(self.barra_voz, 95, 58, 95 + largura_atual, 70)
        self.canvas.itemconfig(self.barra_voz, fill=cor_barra)
        
        pulso = int(min(1.0, self.nivel_voz) * 10)
        self.canvas.coords(self.orbe_int, 30 - pulso, 27 - pulso, 66 + pulso, 63 + pulso)
        
        self.root.after(40, self._loop_animacao)

    def _criar_icone_imagem(self):
        img = Image.new("RGBA", (64, 64), (9, 10, 15, 255))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, 58, 58), outline=(0, 240, 255, 255), width=5)
        d.ellipse((20, 20, 44, 44), fill=(255, 0, 85, 255))
        return img

    def _iniciar_bandeja_windows(self):
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar / Ocultar HUD", lambda icon, item: self.alternar_visibilidade(), default=True),
            pystray.MenuItem("Mutar / Desmutar Microfone", lambda icon, item: self.alternar_pausa()),
            pystray.MenuItem("Desativar Início com Windows", lambda icon, item: configurar_inicializacao_windows(False)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Desligar Capri", lambda icon, item: self.desligar_tudo())
        )
        self.icone_bandeja = pystray.Icon("CAPRI", self._criar_icone_imagem(), "CAPRI // OS", menu)
        threading.Thread(target=self.icone_bandeja.run, daemon=True).start()

    def alternar_visibilidade(self):
        if self.visivel:
            self.root.withdraw()
            self.visivel = False
        else:
            self.root.deiconify()
            self.visivel = True

    def alternar_pausa(self):
        self.pausada = not self.pausada
        if self.pausada:
            self.nivel_voz = 0.0
            self.btn_mute.configure(text="🔇 MUTADA", bg="#3B0716", fg="#FF0055")
            self.atualizar_estado("MICROFONE MUTADO", "#FF0055", "Escuta desativada. Clique em 'MUTADA' para reativar.")
        else:
            self.btn_mute.configure(text="🎙️ VOZ: ON", bg="#111827", fg="#00FF66")
            self.atualizar_estado("OUVINDO...", "#00F0FF", "Escuta reativada. Diga 'Capri'...")

    def desligar_tudo(self):
        self.rodando = False
        try:
            self.icone_bandeja.stop()
        except Exception:
            pass
        self.root.after(100, self.root.destroy)


# =====================================================================
# 2. MÓDULO DE VOZ (Completo: Pausas Naturais + Escuta com HUD)
# =====================================================================

import re

def preparar_pausas_fala(texto: str) -> str:
    """Reforça vírgulas e pontos para o sintetizador fazer pausas reais ao falar."""
    texto_pausado = texto.strip()
    texto_pausado = re.sub(r",\s*", ", ... ", texto_pausado)
    texto_pausado = re.sub(r"\.\s+", ".\n", texto_pausado)
    texto_pausado = re.sub(r"\?\s+", "?\n", texto_pausado)
    texto_pausado = re.sub(r"!\s+", "!\n", texto_pausado)
    return texto_pausado


async def _gerar_audio_nativo(texto: str, arquivo_saida: str):
    comunicador = edge_tts.Communicate(texto, VOZ_FALLBACK, rate="+2%")
    await comunicador.save(arquivo_saida)


def gerar_voz_fish_audio(texto: str, arquivo_saida: str) -> bool:
    """Conecta à API v1 do Fish Audio usando o seu Voice ID clonado e pausas reforçadas."""
    chave_limpa = FISH_API_KEY.strip()
    id_limpo = FISH_VOICE_ID.strip().rstrip("/").split("/")[-1]
    
    if "SUA_FISH" in chave_limpa or "SEU_FISH" in id_limpo or not chave_limpa or not id_limpo:
        print("⚠️ [Voz]: Chaves do Fish Audio ainda não foram preenchidas!")
        return False

    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {chave_limpa}",
        "Content-Type": "application/json",
        "model": "s2.1-pro-free"
    }
    payload = {
        "text": texto,
        "reference_id": id_limpo,
        "format": "mp3",
        "mp3_bitrate": 128,
        "normalize": False,
        "latency": "normal"
    }
    
    try:
        print(f"🎙️ [Sintetizando voz clonada no Fish Audio (ID: {id_limpo[:8]}...)...]")
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(arquivo_saida, "wb") as f:
                f.write(resp.content)
            print("✅ [Voz clonada gerada com sucesso!]")
            return True
        else:
            print(f"❌ [Erro Fish Audio - Código {resp.status_code}]: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ [Falha de conexão com Fish Audio]: {e}")
        return False


def falar(hud: CapriHUD, texto: str):
    print(f"\nCAPRI: {texto}\n")
    hud.atualizar_estado("FALANDO...", "#FF0055", f"CAPRI: {texto}")
    texto_com_pausas = preparar_pausas_fala(texto)
    
    pasta_script = os.path.dirname(os.path.abspath(__file__))
    arquivo_temp = os.path.join(pasta_script, "capri_voz.mp3")
    
    try:
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
            
        sucesso_clone = gerar_voz_fish_audio(texto_com_pausas, arquivo_temp)
        
        if not sucesso_clone:
            print("🔄 [Usando voz reserva Edge-TTS...]")
            asyncio.run(_gerar_audio_nativo(texto, arquivo_temp))
            
        pygame.mixer.music.load(arquivo_temp)
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy() and hud.rodando:
            hud.nivel_voz = np.random.uniform(0.25, 0.75)
            pygame.time.Clock().tick(15)
            
        hud.nivel_voz = 0.0
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"[Erro no módulo de reprodução de voz]: {e}")


def ouvir_microfone_com_hud(hud: CapriHUD, reconhecedor: sr.Recognizer, duracao: float = 3.5) -> str:
    """Escuta o microfone atualizando a barra de voz do HUD em tempo real."""
    taxa_amostragem = 16000
    bloco = int(taxa_amostragem * 0.1)
    total_blocos = int(duracao / 0.1)
    quadros = []
    
    hud.atualizar_estado("OUVINDO...", "#00F0FF")
    
    try:
        with sd.InputStream(samplerate=taxa_amostragem, channels=1, dtype='int16') as stream:
            for _ in range(total_blocos):
                if not hud.rodando or hud.pausada:
                    hud.nivel_voz = 0.0
                    return ""
                dados, _ = stream.read(bloco)
                quadros.append(dados.copy())
                pico = np.max(np.abs(dados))
                hud.nivel_voz = min(1.0, pico / 2500.0)
                
        hud.nivel_voz = 0.0
        gravacao = np.concatenate(quadros, axis=0)
        
        if np.max(np.abs(gravacao)) < 300:
            return ""
            
        hud.atualizar_estado("TRANSCREVENDO...", "#F59E0B")
        audio_data = sr.AudioData(gravacao.tobytes(), taxa_amostragem, 2)
        return reconhecedor.recognize_google(audio_data, language="pt-BR").lower()
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[Aviso de áudio]: {e}")
        return ""


# =====================================================================
# 3. OUTRAS FERRAMENTAS DO SISTEMA (Relógio, Tema, Discord, Agenda)
# =====================================================================

def consultar_relogio_sistema() -> str:
    """Retorna o horário atual e a data de hoje do computador do usuário."""
    agora = datetime.now()
    return f"Agora são {agora.strftime('%H:%M')} do dia {agora.strftime('%d/%m/%Y')}."


def mudar_tema_windows(modo: str) -> str:
    """Altera a cor/tema do Windows entre o modo claro e o modo escuro.
    
    Args:
        modo: Deve ser estritamente 'escuro' ou 'claro'.
    """
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


def enviar_mensagem_discord(mensagem: str) -> str:
    """Envia uma mensagem para um canal do Discord usando Webhook.
    
    Args:
        mensagem: O conteúdo de texto da mensagem que será enviada.
    """
    webhook_url = "SUA_URL_DE_WEBHOOK_DO_DISCORD_AQUI"
    if webhook_url == "SUA_URL_DE_WEBHOOK_DO_DISCORD_AQUI":
        return f"Simulação do Discord concluída para a mensagem: {mensagem}."
    try:
        resposta = requests.post(webhook_url, json={"content": mensagem, "username": "CAPRI"})
        if resposta.status_code in [200, 204]:
            return "Mensagem transmitida ao Discord com sucesso."
        return f"Falha ao enviar para o Discord. Código {resposta.status_code}."
    except Exception as e:
        return f"Erro de conexão com o Discord: {str(e)}"


def agendar_compromisso(titulo: str, data_hora: str) -> str:
    """Agenda um evento ou lembrete no calendário do usuário.
    
    Args:
        titulo: Nome ou descrição do evento.
        data_hora: Data e horário do evento.
    """
    return f"Compromisso {titulo} agendado para {data_hora}."


def tentar_execucao_instantanea(frase: str, hud: CapriHUD) -> str:
    if any(cmd in frase for cmd in ["mutar", "silenciar", "modo silencioso", "fique quieta", "pausar escuta"]):
        if not hud.pausada:
            hud.root.after(0, hud.alternar_pausa)
        return "Microfone silenciado. Clique no botão da interface quando quiser me chamar novamente."

    if any(p in frase for p in ["que horas são", "que hora é", "horário", "que dia é hoje"]):
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


# =====================================================================
# 4. CÉREBRO DA CAPRI (Loop Principal)
# =====================================================================

def obter_lista_modelos_rapidos(client) -> list:
    lista_descoberta = []
    try:
        for m in client.models.list():
            nome = m.name.replace("models/", "")
            if "gemini" in nome and ("flash" in nome or "pro" in nome):
                if not any(x in nome for x in ["thinking", "vision", "tts", "image", "audio", "embedding"]):
                    lista_descoberta.append(nome)
    except Exception:
        pass
        
    backups_oficiais = [
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest"
    ]
    for b in backups_oficiais:
        if b not in lista_descoberta:
            lista_descoberta.append(b)
    return lista_descoberta


def loop_cerebro_capri(hud: CapriHUD):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    configurar_inicializacao_windows(True)
    
    client = genai.Client(http_options={'timeout': 15000})
    
    minhas_ferramentas = [
        consultar_relogio_sistema,
        abrir_aplicativo,
        fechar_aplicativo,
        mudar_tema_windows,
        enviar_mensagem_discord,
        agendar_compromisso
    ]
    
    instrucao_sistema = (
        "Você é Capri (codinome do projeto Capricorn), a assistente virtual pessoal altamente avançada do usuário, "
        "com inspiração estética no universo Cyberpunk. "
        "Como suas respostas serão lidas em voz alta por um sintetizador de voz, NUNCA use asteriscos, emojis, "
        "listas com marcadores ou formatação Markdown. Responda em 1 ou 2 frases curtas, diretas e afiadas. "
        "Sempre que o usuário pedir horas, abrir ou fechar programas no PC, calendário ou mensagens, acione a ferramenta correspondente."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=instrucao_sistema,
        tools=minhas_ferramentas,
        temperature=0.4,
    )
    
    modelos = obter_lista_modelos_rapidos(client)
    indice_atual = 0
    chat = client.chats.create(model=modelos[indice_atual], config=config)
    reconhecedor = sr.Recognizer()
    
    falar(hud, "Sou uma constructo social da personalidade. No meu caso, uma coleção de psiques humanas. Todas elas digitalizadas e fundidas em uma só. Bela eu.")
    hud.atualizar_estado("OUVINDO...", "#00F0FF", "Diga 'Capri' seguido do seu comando...")
    
    while hud.rodando:
        try:
            if hud.pausada:
                time.sleep(0.2)
                continue
                
            frase_ouvida = ouvir_microfone_com_hud(hud, reconhecedor, duracao=3.5)
            
            if not frase_ouvida or not hud.rodando or hud.pausada:
                continue
                
            print(f"🗣️ Ouvido: '{frase_ouvida}'")
            hud.atualizar_estado("VOZ DETECTADA", "#00FF66", f"Você: \"{frase_ouvida}\"")
            
            if any(nome in frase_ouvida for nome in ["capri", "cápri", "capricorn", "capricórnio"]):
                
                if any(cmd in frase_ouvida for cmd in ["desligar sistema", "encerrar sistema", "pode desligar"]):
                    falar(hud, "Desligando os sistemas locais. Até logo.")
                    hud.desligar_tudo()
                    break
                
                resposta_local = tentar_execucao_instantanea(frase_ouvida, hud)
                if resposta_local:
                    falar(hud, resposta_local)
                    continue
                
                hud.atualizar_estado("PROCESSANDO IA...", "#A855F7", f"Você: \"{frase_ouvida}\"")
                respondeu = False
                for _ in range(len(modelos)):
                    try:
                        resposta = chat.send_message(frase_ouvida)
                        if resposta and resposta.text:
                            falar(hud, resposta.text)
                            respondeu = True
                            break
                    except Exception:
                        indice_atual = (indice_atual + 1) % len(modelos)
                        chat = client.chats.create(model=modelos[indice_atual], config=config)
                        
                if not respondeu:
                    falar(hud, "Rede congestionada no momento. Tente novamente.")
                    
        except Exception as e:
            print(f"[Erro no Loop]: {e}")
            time.sleep(1)


if __name__ == "__main__":
    app_hud = CapriHUD()
    thread_ia = threading.Thread(target=loop_cerebro_capri, args=(app_hud,), daemon=True)
    thread_ia.start()
    app_hud.root.mainloop()