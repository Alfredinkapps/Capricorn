import os
import re
import sys
import json
import time
import ctypes
import threading
import winreg
import asyncio
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
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

# Importa os módulos locais dinâmicos
from abrir_apps import abrir_aplicativo, verificar_abertura_rapida
from src.fechar_apps import fechar_aplicativo, verificar_fechamento_rapido

if getattr(sys, "frozen", False):
    # Quando aberto pelo Capri.exe na raiz
    PASTA_PROJETO = os.path.dirname(sys.executable)
else:
    # Quando aberto por src/capri_core.py (sobe 1 pasta para a raiz do projeto)
    PASTA_SRC = os.path.dirname(os.path.abspath(__file__))
    if PASTA_SRC not in sys.path:
        sys.path.insert(0, PASTA_SRC)
    PASTA_PROJETO = os.path.dirname(PASTA_SRC)
ARQUIVO_CONFIG = os.path.join(PASTA_PROJETO, "capri_config.json")
VOZ_FALLBACK = "pt-BR-FranciscaNeural"

pygame.mixer.init()


# =====================================================================
# 0. GERENCIADOR DE CONFIGURAÇÕES E SCANNER COMPLETO DE APPS DO PC
# =====================================================================

def extrair_exe_de_atalho(caminho_lnk: str, nome_atalho: str) -> str:
    """Lê os bytes de um atalho .lnk do Windows para descobrir o nome real do arquivo .exe."""
    try:
        with open(caminho_lnk, "rb") as f:
            conteudo = f.read()
        texto_utf16 = conteudo.decode("utf-16-le", errors="ignore")
        achados = re.findall(r"([a-zA-Z0-9_\-\. ]+\.exe)", texto_utf16, re.IGNORECASE)
        if not achados:
            texto_ascii = conteudo.decode("latin-1", errors="ignore")
            achados = re.findall(r"([a-zA-Z0-9_\-\. ]+\.exe)", texto_ascii, re.IGNORECASE)
        
        for exe in reversed(achados):
            exe_limpo = os.path.basename(exe.strip())
            if not any(x in exe_limpo.lower() for x in ["unins", "update", "setup", "install", "crash"]):
                return exe_limpo
    except Exception:
        pass
    return f"{nome_atalho.replace(' ', '')}.exe"


def escanear_aplicativos_pc(apps_atuais: dict = None) -> dict:
    """Faz um scan no Menu Iniciar e no Registro do Windows para listar os apps instalados."""
    if apps_atuais is None:
        apps_atuais = {}

    catalogo = {}

    nativos = {
        "calculadora": {"nome": "Calculadora", "caminho_abrir": "calc.exe", "processo_fechar": "CalculatorApp.exe", "ativo": True},
        "bloco de notas": {"nome": "Bloco de Notas", "caminho_abrir": "notepad.exe", "processo_fechar": "notepad.exe", "ativo": True},
        "cmd": {"nome": "Prompt de Comando (CMD)", "caminho_abrir": "cmd.exe", "processo_fechar": "cmd.exe", "ativo": True},
        "explorador de arquivos": {"nome": "Explorador de Arquivos", "caminho_abrir": "explorer.exe", "processo_fechar": "explorer.exe", "ativo": False},
    }
    for k, v in nativos.items():
        if k in apps_atuais:
            v["ativo"] = apps_atuais[k].get("ativo", v["ativo"])
        catalogo[k] = v

    chaves_reg = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths")
    ]
    ignorar_termos = ["unins", "setup", "install", "update", "helper", "crash", "report", "uga", "dxsetup", "vcredist"]

    for raiz_reg, subchave in chaves_reg:
        try:
            with winreg.OpenKey(raiz_reg, subchave) as chave:
                num_sub = winreg.QueryInfoKey(chave)[0]
                for i in range(num_sub):
                    nome_exe = winreg.EnumKey(chave, i)
                    if not nome_exe.lower().endswith(".exe"):
                        continue
                    if any(termo in nome_exe.lower() for termo in ignorar_termos):
                        continue
                    try:
                        with winreg.OpenKey(chave, nome_exe) as sub:
                            caminho_completo, _ = winreg.QueryValueEx(sub, "")
                            caminho_completo = caminho_completo.strip('"')
                            if os.path.exists(caminho_completo):
                                nome_limpo = nome_exe[:-4].lower()
                                nome_bonito = nome_exe[:-4].replace("_", " ").replace("-", " ").title()
                                if nome_limpo == "code":
                                    nome_limpo = "visual studio code"
                                    nome_bonito = "Visual Studio Code"
                                
                                ativo_padrao = nome_limpo in ["firefox", "chrome", "visual studio code", "discord", "steam", "spotify"]
                                if nome_limpo in apps_atuais:
                                    ativo_padrao = apps_atuais[nome_limpo].get("ativo", ativo_padrao)

                                catalogo[nome_limpo] = {
                                    "nome": nome_bonito,
                                    "caminho_abrir": caminho_completo,
                                    "processo_fechar": nome_exe,
                                    "ativo": ativo_padrao
                                }
                    except Exception:
                        continue
        except Exception:
            pass

    pastas_menu = [
        os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
    ]

    for pasta in pastas_menu:
        if not os.path.exists(pasta):
            continue
        for raiz, _, arquivos in os.walk(pasta):
            for arq in arquivos:
                if arq.lower().endswith(".lnk"):
                    nome_base = arq[:-4].strip()
                    chave_app = nome_base.lower()
                    
                    if any(t in chave_app for t in ["uninstall", "desinstalar", "readme", "help", "ajuda", "website", "manual", "license"]):
                        continue
                    if chave_app in catalogo:
                        continue

                    caminho_lnk = os.path.join(raiz, arq)
                    exe_alvo = extrair_exe_de_atalho(caminho_lnk, nome_base)

                    ativo_padrao = any(fav in chave_app for fav in ["firefox", "chrome", "visual studio code", "discord", "steam", "spotify"])
                    if chave_app in apps_atuais:
                        ativo_padrao = apps_atuais[chave_app].get("ativo", ativo_padrao)

                    catalogo[chave_app] = {
                        "nome": nome_base,
                        "caminho_abrir": caminho_lnk,
                        "processo_fechar": exe_alvo,
                        "ativo": ativo_padrao
                    }

    catalogo_ordenado = dict(sorted(catalogo.items(), key=lambda item: (not item[1]["ativo"], item[1]["nome"].lower())))
    return catalogo_ordenado


def carregar_configuracoes() -> dict:
    """Lê o arquivo capri_config.json ou cria a estrutura inicial."""
    padrao = {
        "gemini_api_key": "",
        "fish_api_key": "",
        "fish_voice_id": "",
        "discord_webhook": "",
        "apps": {}
    }
    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
                padrao.update(dados)
        except Exception:
            pass

    if not padrao["apps"]:
        padrao["apps"] = escanear_aplicativos_pc()
        salvar_configuracoes(padrao)

    return padrao


def salvar_configuracoes(dados: dict):
    """Salva as chaves e estados dos botões no arquivo capri_config.json."""
    try:
        with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        print("💾 [Configurações salvas em capri_config.json]")
    except Exception as e:
        print(f"[Erro ao salvar configurações]: {e}")


def configurar_inicializacao_windows(ativar: bool = True):
    caminho_registro = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_app = "CapriAssistant"

    if getattr(sys, "frozen", False):
        comando = f'"{sys.executable}"'
    else:
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        caminho_script = os.path.abspath(__file__)
        comando = f'"{python_exe}" "{caminho_script}"'

    try:
        chave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho_registro, 0, winreg.KEY_SET_VALUE)
        if ativar:
            winreg.SetValueEx(chave, nome_app, 0, winreg.REG_SZ, comando)
        else:
            try:
                winreg.DeleteValue(chave, nome_app)
            except FileNotFoundError:
                pass
        winreg.CloseKey(chave)
    except Exception as e:
        print(f"[Aviso de Registro]: {e}")


# =====================================================================
# 1. COMPONENTE VISUAL: BOTÃO SWITCH (VERDE ✔ / VERMELHO ✖)
# =====================================================================

class BotaoSwitchApp(tk.Canvas):
    """Botão deslizante: Verde com ✔ (Ativo) e Vermelho com ✖ (Inativo)."""
    def __init__(self, parent, estado_inicial=False, ao_mudar=None):
        super().__init__(
            parent, width=62, height=30, bg="#111827", 
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self.estado = estado_inicial
        self.ao_mudar = ao_mudar
        self.bind("<Button-1>", self.alternar)
        self.desenhar()

    def desenhar(self):
        self.delete("all")
        cor_fundo = "#22C55E" if self.estado else "#EF4444"

        self.create_oval(2, 2, 28, 28, fill=cor_fundo, outline="")
        self.create_oval(34, 2, 60, 28, fill=cor_fundo, outline="")
        self.create_rectangle(15, 2, 47, 28, fill=cor_fundo, outline="")

        if self.estado:
            self.create_text(16, 15, text="✔", fill="#FFFFFF", font=("Segoe UI Symbol", 10, "bold"))
            self.create_oval(35, 5, 57, 25, fill="#FFFFFF", outline="")
        else:
            self.create_oval(5, 5, 27, 25, fill="#FFFFFF", outline="")
            self.create_text(45, 15, text="✖", fill="#FFFFFF", font=("Segoe UI Symbol", 10, "bold"))

    def alternar(self, event=None):
        self.estado = not self.estado
        self.desenhar()
        if self.ao_mudar:
            self.ao_mudar(self.estado)


# =====================================================================
# 2. JANELA DE CONFIGURAÇÕES E SCANNER DE APLICATIVOS (COM AUTO-SAVE)
# =====================================================================

class JanelaConfiguracoes:
    def __init__(self, hud_pai, primeiro_uso=False):
        self.hud = hud_pai
        self.primeiro_uso = primeiro_uso
        self.dados = carregar_configuracoes()

        self.win = tk.Toplevel(self.hud.root)
        self.win.title("CAPRI // CONFIGURAÇÕES DO SISTEMA")
        self.win.geometry("560x640")
        self.win.minsize(520, 520)
        self.win.configure(bg="#090A0F")
        self.win.attributes("-topmost", True)

        # Se o usuário fechar a janela no [X] lá em cima, também salva tudo automaticamente!
        self.win.protocol("WM_DELETE_WINDOW", self._ao_fechar_janela)

        self._montar_layout()
        self._renderizar_lista_apps()

    def _montar_layout(self):
        # 1. RODAPÉ FIXADO PRIMEIRO (side="bottom") para NUNCA sumir da tela!
        rodape = tk.Frame(self.win, bg="#090A0F")
        rodape.pack(side="bottom", fill="x", padx=12, pady=10)

        self.btn_salvar_rodape = tk.Button(
            rodape, text="💾 SALVAR CONFIGURAÇÕES E ATIVAR CAPRI", bg="#00F0FF", fg="#090A0F",
            activebackground="#22C55E", activeforeground="#FFFFFF", relief="flat",
            font=("Consolas", 11, "bold"), cursor="hand2", command=self._salvar_e_fechar
        )
        self.btn_salvar_rodape.pack(fill="x", ipady=8)

        # 2. CABEÇALHO NO TOPO (com botão rápido de Salvar adicional)
        topo = tk.Frame(self.win, bg="#111827", height=48, highlightthickness=1, highlightbackground="#00F0FF")
        topo.pack(side="top", fill="x", padx=12, pady=(10, 6))

        titulo_txt = "⚙️ CONFIGURAÇÃO INICIAL" if self.primeiro_uso else "⚙️ CENTRAL DE CONFIGURAÇÕES"
        tk.Label(
            topo, text=titulo_txt, bg="#111827", fg="#00F0FF",
            font=("Consolas", 10, "bold")
        ).pack(side="left", padx=10, pady=8)

        btn_salvar_topo = tk.Button(
            topo, text="💾 SALVAR", bg="#22C55E", fg="#FFFFFF",
            activebackground="#16A34A", activeforeground="#FFFFFF", relief="flat",
            font=("Consolas", 9, "bold"), cursor="hand2", command=self._salvar_e_fechar
        )
        btn_salvar_topo.pack(side="right", padx=10, pady=6, ipadx=8, ipady=2)

        # 3. PAINEL DE CHAVES DE API
        frame_api = tk.LabelFrame(
            self.win, text=" 🔑 CHAVES DE API (GEMINI & FISH AUDIO) ", 
            bg="#090A0F", fg="#00F0FF", font=("Consolas", 9, "bold"),
            bd=1, relief="solid"
        )
        frame_api.pack(side="top", fill="x", padx=12, pady=4)

        tk.Label(frame_api, text="Gemini API Key (Google AI Studio):", bg="#090A0F", fg="#E2E8F0", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))
        self.ent_gemini = tk.Entry(frame_api, width=64, bg="#111827", fg="#00FF66", insertbackground="#00F0FF", relief="flat", font=("Consolas", 9))
        self.ent_gemini.grid(row=1, column=0, padx=10, pady=(0, 4), ipady=3)
        self.ent_gemini.insert(0, self.dados.get("gemini_api_key", ""))

        tk.Label(frame_api, text="Fish Audio API Key (Voz Clonada):", bg="#090A0F", fg="#E2E8F0", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", padx=10, pady=(2, 2))
        self.ent_fish_key = tk.Entry(frame_api, width=64, bg="#111827", fg="#00F0FF", insertbackground="#00F0FF", relief="flat", font=("Consolas", 9))
        self.ent_fish_key.grid(row=3, column=0, padx=10, pady=(0, 4), ipady=3)
        self.ent_fish_key.insert(0, self.dados.get("fish_api_key", ""))

        tk.Label(frame_api, text="Fish Audio Voice ID (ID do Modelo da Voz):", bg="#090A0F", fg="#E2E8F0", font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", padx=10, pady=(2, 2))
        self.ent_fish_id = tk.Entry(frame_api, width=64, bg="#111827", fg="#00F0FF", insertbackground="#00F0FF", relief="flat", font=("Consolas", 9))
        self.ent_fish_id.grid(row=5, column=0, padx=10, pady=(0, 8), ipady=3)
        self.ent_fish_id.insert(0, self.dados.get("fish_voice_id", ""))

        # 4. PAINEL DE APLICATIVOS ESCANEADOS (Preenche o espaço restante no meio)
        frame_apps = tk.LabelFrame(
            self.win, text=" 🖥️ APLICATIVOS NO COMANDO DA CAPRI (AUTO-SAVE ATIVO) ", 
            bg="#090A0F", fg="#00F0FF", font=("Consolas", 9, "bold"),
            bd=1, relief="solid"
        )
        frame_apps.pack(side="top", fill="both", expand=True, padx=12, pady=4)

        barra_busca = tk.Frame(frame_apps, bg="#090A0F")
        barra_busca.pack(fill="x", padx=10, pady=6)

        tk.Label(barra_busca, text="🔍 Filtrar:", bg="#090A0F", fg="#94A3B8", font=("Segoe UI", 9)).pack(side="left")
        self.var_filtro = tk.StringVar()
        self.var_filtro.trace_add("write", lambda *args: self._renderizar_lista_apps())
        ent_filtro = tk.Entry(barra_busca, textvariable=self.var_filtro, width=28, bg="#111827", fg="#FFFFFF", insertbackground="#00F0FF", relief="flat", font=("Segoe UI", 9))
        ent_filtro.pack(side="left", padx=8, ipady=3)

        btn_scan = tk.Button(
            barra_busca, text="🔄 Escanear PC Agora", bg="#1E293B", fg="#00F0FF",
            activebackground="#00F0FF", activeforeground="#090A0F", relief="flat",
            font=("Consolas", 8, "bold"), cursor="hand2", command=self._acao_reescanear
        )
        btn_scan.pack(side="right", ipadx=6, ipady=2)

        container_scroll = tk.Frame(frame_apps, bg="#090A0F")
        container_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.canvas_apps = tk.Canvas(container_scroll, bg="#090A0F", highlightthickness=0)
        scrollbar = tk.Scrollbar(container_scroll, orient="vertical", command=self.canvas_apps.yview)
        self.frame_lista_interna = tk.Frame(self.canvas_apps, bg="#090A0F")

        self.frame_lista_interna.bind(
            "<Configure>",
            lambda e: self.canvas_apps.configure(scrollregion=self.canvas_apps.bbox("all"))
        )

        self.canvas_apps.create_window((0, 0), window=self.frame_lista_interna, anchor="nw", width=490)
        self.canvas_apps.configure(yscrollcommand=scrollbar.set)

        self.canvas_apps.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas_apps.bind_all("<MouseWheel>", self._rolar_mouse)

    def _rolar_mouse(self, event):
        try:
            if self.win.winfo_exists():
                self.canvas_apps.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _acao_reescanear(self):
        self.dados["apps"] = escanear_aplicativos_pc(self.dados.get("apps", {}))
        salvar_configuracoes(self.dados)
        self._renderizar_lista_apps()
        messagebox.showinfo("Scan Concluído", f"Foram encontrados e salvos {len(self.dados['apps'])} aplicativos do seu PC!", parent=self.win)

    def _atualizar_estado_app(self, chave_app: str, novo_estado: bool):
        """Salva no arquivo JSON imediatamente a cada clique no botão Verde/Vermelho."""
        if chave_app in self.dados["apps"]:
            self.dados["apps"][chave_app]["ativo"] = novo_estado
            # Também aproveita para capturar as chaves digitadas nos campos
            self.dados["gemini_api_key"] = self.ent_gemini.get().strip()
            self.dados["fish_api_key"] = self.ent_fish_key.get().strip()
            self.dados["fish_voice_id"] = self.ent_fish_id.get().strip()
            salvar_configuracoes(self.dados)

    def _renderizar_lista_apps(self):
        for widget in self.frame_lista_interna.winfo_children():
            widget.destroy()

        termo = self.var_filtro.get().lower().strip()
        apps = self.dados.get("apps", {})

        for chave, info in apps.items():
            nome_exibicao = info.get("nome", chave)
            if termo and termo not in nome_exibicao.lower() and termo not in chave:
                continue

            linha = tk.Frame(self.frame_lista_interna, bg="#111827", pady=6, padx=10)
            linha.pack(fill="x", pady=3)

            # 1º POSICIONA O BOTÃO NA DIREITA PRIMEIRO (Garante que ele NUNCA seja empurrado para fora!)
            switch = BotaoSwitchApp(
                linha,
                estado_inicial=info.get("ativo", False),
                ao_mudar=lambda est, k=chave: self._atualizar_estado_app(k, est)
            )
            switch.pack(side="right", padx=(10, 4))

            # 2º POSICIONA O TEXTO NO ESPAÇO RESTANTE DA ESQUERDA
            bloco_texto = tk.Frame(linha, bg="#111827")
            bloco_texto.pack(side="left", fill="x", expand=True)

            # Abrevia títulos e comandos muito longos para não estourar a linha
            titulo_curto = nome_exibicao if len(nome_exibicao) <= 42 else nome_exibicao[:39] + "..."
            cmd_curto = chave if len(chave) <= 24 else chave[:21] + "..."
            proc_exe = info.get("processo_fechar", "")
            proc_curto = proc_exe if len(proc_exe) <= 20 else proc_exe[:17] + "..."

            tk.Label(
                bloco_texto, text=titulo_curto, bg="#111827", fg="#FFFFFF",
                font=("Segoe UI", 9, "bold"), anchor="w"
            ).pack(fill="x")

            tk.Label(
                bloco_texto, text=f"Comando: \"{cmd_curto}\"  |  Processo: {proc_curto}",
                bg="#111827", fg="#64748B", font=("Consolas", 8), anchor="w"
            ).pack(fill="x")

    def _ao_fechar_janela(self):
        """Garante que se o usuário clicar no X da janela, ainda assim salva o que foi preenchido."""
        self.dados["gemini_api_key"] = self.ent_gemini.get().strip()
        self.dados["fish_api_key"] = self.ent_fish_key.get().strip()
        self.dados["fish_voice_id"] = self.ent_fish_id.get().strip()
        salvar_configuracoes(self.dados)
        if self.dados["gemini_api_key"]:
            self.hud.aplicar_novas_credenciais(self.dados)
        self.win.destroy()

    def _salvar_e_fechar(self):
        chave_gemini = self.ent_gemini.get().strip()
        if not chave_gemini:
            messagebox.showwarning("Chave Obrigatória", "Por favor, cole a sua Gemini API Key para ativar a Capri!", parent=self.win)
            return

        self.dados["gemini_api_key"] = chave_gemini
        self.dados["fish_api_key"] = self.ent_fish_key.get().strip()
        self.dados["fish_voice_id"] = self.ent_fish_id.get().strip()

        salvar_configuracoes(self.dados)
        self.hud.aplicar_novas_credenciais(self.dados)
        messagebox.showinfo("Configurações Salvas", "Suas chaves de API e permissões de aplicativos foram salvas com sucesso!", parent=self.win)
        self.win.destroy()


# =====================================================================
# 3. INTERFACE CYBERPUNK PRINCIPAL (HUD COM BOTÃO DE ENGRENAGEM ⚙)
# =====================================================================

class CapriHUD:
    def __init__(self):
        self.rodando = True
        self.pausada = False
        self.visivel = True
        self.reiniciar_ia = False

        self.config = carregar_configuracoes()
        self._carregar_variaveis_ambiente()

        self.status_texto = "INICIALIZANDO..."
        self.cor_atual = "#00F0FF"
        self.ultima_fala = "Aguardando comando..."
        self.nivel_voz = 0.0
        self.janela_config_aberta = None

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

        if not self.config.get("gemini_api_key"):
            self.atualizar_estado("CONFIGURAÇÃO", "#F59E0B", "Configure suas chaves API e aplicativos na janela aberta.")
            self.root.after(400, lambda: self.abrir_configuracoes(primeiro_uso=True))

    def _carregar_variaveis_ambiente(self):
        if self.config.get("gemini_api_key"):
            os.environ["GEMINI_API_KEY"] = self.config["gemini_api_key"]

    def aplicar_novas_credenciais(self, novos_dados: dict):
        self.config = novos_dados
        self._carregar_variaveis_ambiente()
        self.reiniciar_ia = True
        self.atualizar_estado("ATUALIZADA!", "#00FF66", "Configurações e lista de aplicativos salvas com sucesso!")

    def abrir_configuracoes(self, primeiro_uso=False):
        if self.janela_config_aberta and self.janela_config_aberta.win.winfo_exists():
            self.janela_config_aberta.win.lift()
            return
        self.janela_config_aberta = JanelaConfiguracoes(self, primeiro_uso=primeiro_uso)

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
        self.btn_mute.place(x=148, y=6, width=82, height=20)

        btn_cfg = tk.Button(
            self.painel, text="⚙", bg="#111827", fg="#00F0FF", bd=0,
            font=("Segoe UI Symbol", 10, "bold"), activebackground="#1F2937",
            cursor="hand2", command=lambda: self.abrir_configuracoes(primeiro_uso=False)
        )
        btn_cfg.place(x=235, y=5, width=24, height=22)

        btn_min = tk.Button(
            self.painel, text="_", bg="#090A0F", fg="#00F0FF", bd=0,
            font=("Consolas", 10, "bold"), activebackground="#1A1D2B",
            cursor="hand2", command=self.alternar_visibilidade
        )
        btn_min.place(x=263, y=5, width=22, height=22)

        btn_fechar = tk.Button(
            self.painel, text="X", bg="#090A0F", fg="#FF0055", bd=0,
            font=("Consolas", 10, "bold"), activebackground="#FF0055",
            cursor="hand2", command=self.desligar_tudo
        )
        btn_fechar.place(x=288, y=5, width=22, height=22)

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
            pystray.MenuItem("Abrir Configurações (⚙)", lambda icon, item: self.root.after(0, self.abrir_configuracoes)),
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
# 4. MÓDULO DE VOZ (VAD Inteligente + Cache na Pasta 'cache/' + Fish Audio)
# =====================================================================

import random
import subprocess
from collections import deque
from urllib.parse import quote_plus

RESPOSTAS_CHAMADA = [
    "Oi",
    "Fala",
    "Diga",
    "Tô ouvindo"
]

GATILHOS_CAPRI = [
    "capri", "cápri", "capricorn", "capricórnio",
    "cabri", "gabri", "kpri", "capricho", "capre", "cap"
]


def preparar_pausas_fala(texto: str) -> str:
    texto_pausado = texto.strip()
    texto_pausado = re.sub(r",\s*", ", ... ", texto_pausado)
    texto_pausado = re.sub(r"\.\s+", ".\n", texto_pausado)
    texto_pausado = re.sub(r"\?\s+", "?\n", texto_pausado)
    texto_pausado = re.sub(r"!\s+", "!\n", texto_pausado)
    return texto_pausado


async def _gerar_audio_nativo(texto: str, arquivo_saida: str):
    comunicador = edge_tts.Communicate(texto, VOZ_FALLBACK, rate="+2%")
    await comunicador.save(arquivo_saida)


def gerar_voz_fish_audio(hud: CapriHUD, texto: str, arquivo_saida: str) -> bool:
    chave_limpa = hud.config.get("fish_api_key", "").strip()
    id_limpo = hud.config.get("fish_voice_id", "").strip().rstrip("/").split("/")[-1]

    if not chave_limpa or not id_limpo:
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
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(arquivo_saida, "wb") as f:
                f.write(resp.content)
            return True
        else:
            print(f"❌ [Aviso Fish Audio - {resp.status_code}]: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ [Erro de conexão Fish Audio]: {e}")
        return False


def falar(hud: CapriHUD, texto: str, usar_cache: bool = False):
    print(f"\nCAPRI: {texto}\n")
    hud.atualizar_estado("FALANDO...", "#FF0055", f"CAPRI: {texto}")

    pasta_cache = os.path.join(PASTA_PROJETO, "cache")
    os.makedirs(pasta_cache, exist_ok=True)

    if usar_cache:
        nome_limpo = re.sub(r"[^a-zA-Z0-9]", "_", texto.lower())
        arquivo_audio = os.path.join(pasta_cache, f"cache_{nome_limpo}.mp3")
    else:
        arquivo_audio = os.path.join(pasta_cache, "capri_voz.mp3")

    try:
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        if not (usar_cache and os.path.exists(arquivo_audio) and os.path.getsize(arquivo_audio) > 500):
            texto_com_pausas = preparar_pausas_fala(texto)
            sucesso_clone = gerar_voz_fish_audio(hud, texto_com_pausas, arquivo_audio)
            if not sucesso_clone:
                asyncio.run(_gerar_audio_nativo(texto, arquivo_audio))

        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy() and hud.rodando:
            hud.nivel_voz = np.random.uniform(0.25, 0.75)
            pygame.time.Clock().tick(15)

        hud.nivel_voz = 0.0
        pygame.mixer.music.unload()
    except Exception as e:
        hud.nivel_voz = 0.0
        print(f"[Erro na reprodução de voz]: {e}")


def ouvir_microfone_com_hud(hud: CapriHUD, reconhecedor: sr.Recognizer, aguardando_comando: bool = False) -> str:
    taxa_amostragem = 16000
    bloco = int(taxa_amostragem * 0.1)
    limiar_voz = 380

    tempo_espera_max = 7.0 if aguardando_comando else 4.0
    blocos_espera_max = int(tempo_espera_max / 0.1)
    blocos_silencio_fim = 8 if not aguardando_comando else 10
    blocos_duracao_max = 80

    buffer_pre_fala = deque(maxlen=4)
    quadros_fala = []
    falando = False
    blocos_silencio = 0

    hud.nivel_voz = 0.0

    if aguardando_comando:
        hud.atualizar_estado("OUVINDO VOCÊ...", "#00FF66")
    else:
        hud.atualizar_estado("EM ESPERA", "#00F0FF")

    try:
        with sd.InputStream(samplerate=taxa_amostragem, channels=1, dtype='int16') as stream:
            for i in range(blocos_espera_max + blocos_duracao_max):
                if not hud.rodando or hud.pausada or hud.reiniciar_ia:
                    hud.nivel_voz = 0.0
                    return ""

                dados, _ = stream.read(bloco)
                copia = dados.copy()
                pico = int(np.max(np.abs(copia)))

                if aguardando_comando:
                    hud.nivel_voz = min(1.0, pico / 2500.0)
                else:
                    hud.nivel_voz = 0.0

                if not falando:
                    buffer_pre_fala.append(copia)
                    if pico > limiar_voz:
                        falando = True
                        quadros_fala.extend(buffer_pre_fala)
                        blocos_silencio = 0
                    elif i >= blocos_espera_max:
                        hud.nivel_voz = 0.0
                        return ""
                else:
                    quadros_fala.append(copia)
                    if pico < limiar_voz:
                        blocos_silencio += 1
                        if blocos_silencio >= blocos_silencio_fim:
                            break
                    else:
                        blocos_silencio = 0

                    if len(quadros_fala) >= blocos_duracao_max:
                        break

        hud.nivel_voz = 0.0
        if not quadros_fala:
            return ""

        gravacao = np.concatenate(quadros_fala, axis=0)

        gravacao_float = gravacao.astype(np.float32)
        pico_max = np.max(np.abs(gravacao_float))
        if pico_max > 0:
            ganho = min(3.5, 24000.0 / pico_max)
            gravacao = np.clip(gravacao_float * ganho, -32768, 32767).astype(np.int16)

        hud.atualizar_estado("TRANSCREVENDO...", "#F59E0B")
        audio_data = sr.AudioData(gravacao.tobytes(), taxa_amostragem, 2)
        return reconhecedor.recognize_google(audio_data, language="pt-BR").lower().strip()

    except sr.UnknownValueError:
        hud.nivel_voz = 0.0
        return ""
    except Exception as e:
        hud.nivel_voz = 0.0
        print(f"[Aviso de áudio]: {e}")
        return ""


# =====================================================================
# 5. FERRAMENTAS DO SISTEMA, YOUTUBE MUSIC (MESMA ABA) E VOLUME
# =====================================================================

JA_ABRIU_YOUTUBE = False
ULTIMA_MUSICA_TOCADA = ""


def _obter_titulo_janela(hwnd: int) -> str:
    tamanho = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if tamanho <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(tamanho + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
    return buffer.value.lower()


def _obter_classe_janela(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def encontrar_janela_firefox() -> int:
    """Localiza a janela principal do navegador Firefox (MozillaWindowClass)."""
    janelas_prioritarias = []
    janelas_firefox = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, lParam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            classe = _obter_classe_janela(hwnd)
            titulo = _obter_titulo_janela(hwnd)
            if classe == "MozillaWindowClass" and ("firefox" in titulo or "mozilla" in titulo):
                # Verifica se o título tem 'youtube', 'music' ou o nome da última música
                palavras_musica = [p for p in ULTIMA_MUSICA_TOCADA.split() if len(p) >= 3]
                if "youtube" in titulo or "music" in titulo or any(p in titulo for p in palavras_musica):
                    janelas_prioritarias.append(hwnd)
                else:
                    janelas_firefox.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_callback), 0)

    if janelas_prioritarias:
        return janelas_prioritarias[0]
    if janelas_firefox and JA_ABRIU_YOUTUBE:
        return janelas_firefox[0]
    return 0


def _focar_janela_firefox(hwnd: int):
    """Traz a janela do Firefox para frente sem usar a tecla Alt (evita abrir nova aba com Alt+Enter)."""
    if ctypes.windll.user32.IsIconic(hwnd):
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.22)

    # Se o usuário estava em outra aba do Firefox, procura a aba onde a música está tocando
    palavras_musica = [p for p in ULTIMA_MUSICA_TOCADA.split() if len(p) >= 3]
    for _ in range(8):
        titulo_atual = _obter_titulo_janela(hwnd)
        if "youtube" in titulo_atual or "music" in titulo_atual or any(p in titulo_atual for p in palavras_musica):
            break
        # Pressiona Ctrl + PageDown para checar a próxima aba
        ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x22, 0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(0x22, 0, 2, 0)
        ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(0.08)


def _substituir_url_na_aba_atual(hwnd: int, url_destino: str) -> bool:
    """Seleciona a barra de endereços da aba atual do Firefox (Ctrl+L) e carrega a nova música."""
    try:
        _focar_janela_firefox(hwnd)

        # Copia a URL para a área de transferência do Windows
        subprocess.run(["clip"], input=url_destino.strip(), text=True, check=True)

        # Aperta ESC (0x1B) para fechar qualquer menu aberto na página
        ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.05)

        # Ctrl + L (foca a barra de endereços da aba atual)
        ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x4C, 0, 0, 0)
        time.sleep(0.04)
        ctypes.windll.user32.keybd_event(0x4C, 0, 2, 0)
        ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(0.12)

        # Ctrl + V (cola a nova URL)
        ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
        time.sleep(0.04)
        ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
        ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(0.08)

        # Enter (navega na mesma aba)
        ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
        return True
    except Exception as e:
        print(f"[Aviso ao substituir aba no Firefox]: {e}")
        return False


def tocar_musica_youtube_firefox(nome_musica: str) -> str:
    """Abre o YouTube Music na primeira vez e substitui na mesma aba nas próximas músicas."""
    global JA_ABRIU_YOUTUBE, ULTIMA_MUSICA_TOCADA

    termo = quote_plus(f"{nome_musica.strip()} official audio")
    url_busca_id = f"https://www.youtube.com/results?search_query={termo}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    url_final = f"https://music.youtube.com/search?q={quote_plus(nome_musica.strip())}"
    try:
        resp = requests.get(url_busca_id, headers=headers, timeout=8)
        ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
        if ids:
            url_final = f"https://music.youtube.com/watch?v={ids[0]}"
    except Exception as e:
        print(f"[Aviso busca YouTube Music]: {e}")

    hwnd_ff = encontrar_janela_firefox()
    if hwnd_ff:
        if _substituir_url_na_aba_atual(hwnd_ff, url_final):
            JA_ABRIU_YOUTUBE = True
            ULTIMA_MUSICA_TOCADA = nome_musica.lower().strip()
            return f"Trocando para {nome_musica} no YouTube Music."

    try:
        cfg = carregar_configuracoes()
        caminho_firefox = cfg.get("apps", {}).get("firefox", {}).get("caminho_abrir", "")
        
        if caminho_firefox and os.path.exists(caminho_firefox):
            subprocess.Popen([caminho_firefox, url_final])
        else:
            subprocess.Popen(f'start firefox "{url_final}"', shell=True)
            
        JA_ABRIU_YOUTUBE = True
        ULTIMA_MUSICA_TOCADA = nome_musica.lower().strip()
        return f"Colocando {nome_musica} para tocar no YouTube Music."
    except Exception as e:
        return f"Erro ao abrir o YouTube Music no Firefox: {str(e)}"


def ajustar_volume_youtube_music(acao: str, nivel_porcentagem: int = -1) -> str:
    """
    Controla o volume interno do player do YouTube Music usando os atalhos '-' (0xBD) e '=' (0xBB).
    Cada toque altera 10% do volume apenas da música, sem diminuir a voz da Capri!
    """
    janela_anterior = ctypes.windll.user32.GetForegroundWindow()
    hwnd_ff = encontrar_janela_firefox()

    # Teclas do player do YouTube Music: 0xBD ('-') diminui 10%, 0xBB ('=') aumenta 10%
    VK_MENOS_YT = 0xBD
    VK_MAIS_YT = 0xBB

    if hwnd_ff:
        try:
            _focar_janela_firefox(hwnd_ff)
            # Fecha eventual caixa de texto focada para o atalho ir para o player
            ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.05)

            if nivel_porcentagem >= 0:
                nivel = max(0, min(100, nivel_porcentagem))
                # Zera o slider do YouTube Music (10 toques em '-') e sobe até a porcentagem pedida
                for _ in range(11):
                    ctypes.windll.user32.keybd_event(VK_MENOS_YT, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_MENOS_YT, 0, 2, 0)
                    time.sleep(0.02)
                passos_subir = round(nivel / 10)
                for _ in range(passos_subir):
                    ctypes.windll.user32.keybd_event(VK_MAIS_YT, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_MAIS_YT, 0, 2, 0)
                    time.sleep(0.02)
                msg = f"Volume do YouTube Music ajustado para {nivel} por cento."

            elif acao == "aumentar":
                for _ in range(3):  # +30% no YouTube Music
                    ctypes.windll.user32.keybd_event(VK_MAIS_YT, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_MAIS_YT, 0, 2, 0)
                    time.sleep(0.03)
                msg = "Aumentando o volume da música."

            else:  # diminuir
                for _ in range(3):  # -30% no YouTube Music
                    ctypes.windll.user32.keybd_event(VK_MENOS_YT, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_MENOS_YT, 0, 2, 0)
                    time.sleep(0.03)
                msg = "Abaixando o volume da música."

            # Devolve o foco para a janela que você estava usando antes (ex: VS Code)
            if janela_anterior and janela_anterior != hwnd_ff:
                time.sleep(0.08)
                ctypes.windll.user32.SwitchToThisWindow(janela_anterior, True)

            return msg
        except Exception as e:
            print(f"[Aviso volume YouTube Music]: {e}")

    # Fallback: se o YouTube Music não estiver aberto, ajusta o volume geral do Windows
    tecla_win = 0xAF if acao == "aumentar" else 0xAE
    for _ in range(5):
        ctypes.windll.user32.keybd_event(tecla_win, 0, 1, 0)
        ctypes.windll.user32.keybd_event(tecla_win, 0, 3, 0)
    return "Volume ajustado."


def controlar_midia_windows(acao: str) -> str:
    acao_limpa = acao.lower().strip()
    try:
        if acao_limpa == "pausar":
            tecla_vk = 0xB3
            msg = "Reprodução pausada."
        elif acao_limpa == "continuar":
            tecla_vk = 0xB3
            msg = "Retomando a música."
        elif acao_limpa == "proxima":
            tecla_vk = 0xB0
            msg = "Pulando para a próxima faixa."
        elif acao_limpa == "anterior":
            tecla_vk = 0xB1
            msg = "Voltando para a faixa anterior."
        else:
            return "Comando de mídia não reconhecido."

        ctypes.windll.user32.keybd_event(tecla_vk, 0, 1, 0)
        ctypes.windll.user32.keybd_event(tecla_vk, 0, 3, 0)
        return msg
    except Exception as e:
        return f"Erro ao controlar mídia: {str(e)}"


def consultar_relogio_sistema() -> str:
    agora = datetime.now()
    return f"Agora são {agora.strftime('%H:%M')} do dia {agora.strftime('%d/%m/%Y')}."


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


def enviar_mensagem_discord(mensagem: str) -> str:
    cfg = carregar_configuracoes()
    webhook_url = cfg.get("discord_webhook", "")
    if not webhook_url:
        return f"Simulação do Discord concluída para a mensagem: {mensagem}."
    try:
        resposta = requests.post(webhook_url, json={"content": mensagem, "username": "CAPRI"})
        if resposta.status_code in [200, 204]:
            return "Mensagem transmitida ao Discord com sucesso."
        return f"Falha ao enviar para o Discord. Código {resposta.status_code}."
    except Exception as e:
        return f"Erro de conexão com o Discord: {str(e)}"


def agendar_compromisso(titulo: str, data_hora: str) -> str:
    return f"Compromisso {titulo} agendado para {data_hora}."


def controlar_energia_pc(acao: str) -> str:
    acao_limpa = acao.lower().strip()
    try:
        if "bloquear" in acao_limpa or "trancar" in acao_limpa:
            threading.Timer(2.0, ctypes.windll.user32.LockWorkStation).start()
            return "Bloqueando a estação de trabalho."
        elif "cancelar" in acao_limpa:
            os.system("shutdown /a")
            return "Sequência de desligamento abortada. O computador permanecerá ligado."
        elif "desligar" in acao_limpa:
            os.system("shutdown /s /t 10")
            return "Protocolo de encerramento confirmado. Desligando o computador em 10 segundos."
        elif "reiniciar" in acao_limpa:
            os.system("shutdown /r /t 10")
            return "Reiniciando o computador em 10 segundos."
        elif "suspender" in acao_limpa or "hibernar" in acao_limpa:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "Colocando o notebook em modo de suspensão."
        return f"Comando de energia {acao} não reconhecido."
    except Exception as e:
        return f"Erro ao executar comando de energia: {str(e)}"


def tentar_execucao_instantanea(frase: str, hud: CapriHUD) -> str:
    # 1. CONTROLE DE VOLUME DO YOUTUBE MUSIC
    if "volume" in frase or "som" in frase or "música está muito" in frase:
        if any(p in frase for p in ["máximo", "maximo", "tudo", "100"]):
            return ajustar_volume_youtube_music("aumentar", 100)
        if any(p in frase for p in ["mínimo", "minimo", "baixinho"]):
            return ajustar_volume_youtube_music("diminuir", 10)

        # Verifica se você falou um número (ex: "volume em 30%", "volume para 50")
        numeros = re.findall(r"\b(\d{1,3})\b", frase)
        if numeros:
            return ajustar_volume_youtube_music("definir", int(numeros[0]))

        if any(p in frase for p in ["aumentar", "aumenta", "aumente", "subir", "sobe", "mais alto"]):
            return ajustar_volume_youtube_music("aumentar")
        if any(p in frase for p in ["abaixar", "abaixa", "abaixe", "diminuir", "diminui", "diminua", "baixar", "baixa", "muito alta", "muito alto"]):
            return ajustar_volume_youtube_music("diminuir")

    # 2. CONTROLE DE REPRODUÇÃO (PAUSE / PLAY / FAIXAS)
    if any(cmd in frase for cmd in [
        "pausar música", "pausa a música", "pause a música", "pausar o vídeo",
        "pausar reprodução", "pausar youtube", "parar música", "para a música"
    ]):
        return controlar_midia_windows("pausar")

    if any(cmd in frase for cmd in [
        "continuar música", "continue a música", "continua a música", "retomar música",
        "voltar a música", "despausar", "dar play", "continuar vídeo"
    ]):
        return controlar_midia_windows("continuar")

    if any(cmd in frase for cmd in ["próxima música", "pular música", "passar música", "próxima faixa"]):
        return controlar_midia_windows("proxima")

    if any(cmd in frase for cmd in ["música anterior", "voltar faixa", "faixa anterior"]):
        return controlar_midia_windows("anterior")

    # 3. ENERGIA E SISTEMA
    if any(cmd in frase for cmd in ["cancelar desligamento", "cancele o desligamento", "abortar desligamento", "não desligar"]):
        return controlar_energia_pc("cancelar")

    if any(cmd in frase for cmd in [
        "desligar o computador", "desligar computador", "desligue o computador",
        "desligar o pc", "desligar pc", "desligue o pc",
        "desligar o notebook", "desligar notebook", "desligue o notebook"
    ]):
        return controlar_energia_pc("desligar")

    if any(cmd in frase for cmd in ["reiniciar o computador", "reiniciar o pc", "reiniciar o notebook", "reinicie o computador"]):
        return controlar_energia_pc("reiniciar")

    if any(cmd in frase for cmd in ["suspender o computador", "suspender o pc", "suspender notebook", "modo suspensão"]):
        return controlar_energia_pc("suspender")

    if any(cmd in frase for cmd in [
        "bloquear tela", "bloqueie a tela", "bloquear a tela",
        "bloquear computador", "bloquear o pc", "trancar tela", "trancar o pc"
    ]):
        return controlar_energia_pc("bloquear")

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


# =====================================================================
# 6. CÉREBRO DA CAPRI (Pesquisa Google Gemini + Comandos Locais)
# =====================================================================

def obter_lista_modelos_rapidos(client) -> list:
    preferidos = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]
    try:
        for m in client.models.list():
            nome = m.name.replace("models/", "")
            if "gemini" in nome and "flash" in nome:
                if not any(x in nome for x in ["thinking", "vision", "tts", "image", "audio", "embedding", "8b"]):
                    if nome not in preferidos:
                        preferidos.append(nome)
    except Exception:
        pass
    return preferidos


def limpar_resposta_ia(texto: str) -> str:
    limpo = re.sub(r"\*+", "", texto)
    limpo = re.sub(r"#+\s*", "", limpo)
    limpo = re.sub(r"\[.*?\]", "", limpo)
    limpo = re.sub(r"https?://\S+", "", limpo)
    limpo = re.sub(r"\s{2,}", " ", limpo)
    return limpo.strip()


def extrair_comando_apos_nome(frase: str) -> tuple[bool, str]:
    palavras_saudacao = ["oi", "olá", "ola", "ei", "hey", "aí", "ai", "ô", "o"]
    for gatilho in GATILHOS_CAPRI:
        if gatilho in frase:
            resto = frase.replace(gatilho, "").strip(" ,.!?")
            palavras_resto = [p for p in resto.split() if p not in palavras_saudacao]
            comando_limpo = " ".join(palavras_resto).strip()
            return True, comando_limpo
    return False, ""


def perguntar_gemini_com_pesquisa(pergunta: str, client, modelos: list, historico: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    instrucao_pesquisa = (
        f"Você é Capri (projeto Capricorn), assistente virtual pessoal do usuário inspirada em Cyberpunk. "
        f"A data atual é {hoje}. "
        f"Use a ferramenta de busca do Google sempre que precisar confirmar fatos atuais, cargos políticos, "
        f"notícias, clima ou informações em tempo real. "
        f"Responda SEMPRE em português do Brasil, em no máximo 1 ou 2 frases curtas, diretas e sem usar asteriscos ou emojis."
    )

    conteudos = list(historico[-6:]) + [pergunta]

    for modelo in modelos:
        try:
            config_busca = types.GenerateContentConfig(
                system_instruction=instrucao_pesquisa,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            )
            resposta = client.models.generate_content(
                model=modelo,
                contents=conteudos,
                config=config_busca
            )
            if resposta and resposta.text:
                texto_final = limpar_resposta_ia(resposta.text)
                historico.append(pergunta)
                historico.append(texto_final)
                return texto_final
        except Exception:
            try:
                config_simples = types.GenerateContentConfig(
                    system_instruction=instrucao_pesquisa,
                    temperature=0.3,
                )
                resposta = client.models.generate_content(
                    model=modelo,
                    contents=conteudos,
                    config=config_simples
                )
                if resposta and resposta.text:
                    texto_final = limpar_resposta_ia(resposta.text)
                    historico.append(pergunta)
                    historico.append(texto_final)
                    return texto_final
            except Exception:
                continue

    return ""


def processar_comando_usuario(comando: str, hud: CapriHUD, reconhecedor: sr.Recognizer, client, modelos: list, historico: list):
    if any(cmd in comando for cmd in ["desligar sistema", "encerrar sistema", "pode desligar"]):
        falar(hud, "Desligando os sistemas locais. Até logo.")
        hud.desligar_tudo()
        return

    if any(cmd in comando for cmd in ["deixa pra lá", "nada não", "esquece", "cancelar"]):
        falar(hud, "Beleza, qualquer coisa é só chamar.")
        return

    # 1. MODO MÚSICA EM 2 ETAPAS (Troca na mesma aba do YouTube Music)
    gatilhos_pedir_musica = [
        "coloque uma música", "coloca uma música", "colocar uma música",
        "toque uma música", "toca uma música", "tocar uma música",
        "bota uma música", "coloca música", "coloque música", "tocar música",
        "coloque outra música", "coloca outra música", "bota outra música", "outra música",
        "trocar música", "troque a música", "troca a música",
        "mudar música", "mude a música", "muda a música"
    ]
    if any(g in comando for g in gatilhos_pedir_musica):
        hwnd_existente = encontrar_janela_firefox()
        if hwnd_existente and JA_ABRIU_YOUTUBE:
            falar(hud, "Para qual música você quer trocar?", usar_cache=True)
        else:
            falar(hud, "Qual música você quer ouvir?", usar_cache=True)

        hud.atualizar_estado("QUAL MÚSICA?...", "#00FF66", "Diga o nome da música ou artista...")
        
        nome_musica = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=True)
        if nome_musica:
            print(f"🎵 Música solicitada: '{nome_musica}'")
            hud.atualizar_estado("CARREGANDO MÚSICA...", "#00FF66", f"Tocando: \"{nome_musica}\"")
            resposta_yt = tocar_musica_youtube_firefox(nome_musica)
            falar(hud, resposta_yt)
        else:
            falar(hud, "Não consegui ouvir o nome da música. Quando quiser é só pedir de novo.")
        return

    for prefixo in [
        "coloque a música ", "coloca a música ", "toque a música ", "toca a música ",
        "tocar a música ", "troque para a música ", "mude para a música "
    ]:
        if prefixo in comando:
            nome_direto = comando.split(prefixo, 1)[1].strip()
            if nome_direto:
                hud.atualizar_estado("CARREGANDO MÚSICA...", "#00FF66", f"Tocando: \"{nome_direto}\"")
                falar(hud, tocar_musica_youtube_firefox(nome_direto))
                return

    # 2. Comandos locais do PC (Volume, Mídia, Abrir/Fechar Apps, Horas, Tema, Energia)
    resposta_local = tentar_execucao_instantanea(comando, hud)
    if resposta_local:
        falar(hud, resposta_local)
        return

    # 3. Pesquisa na Gemini API + Google Search
    hud.atualizar_estado("PESQUISANDO IA...", "#A855F7", f"Você: \"{comando}\"")
    print(f"🔎 [Pesquisando na Gemini API]: '{comando}'...")

    resposta_ia = perguntar_gemini_com_pesquisa(comando, client, modelos, historico)

    if resposta_ia:
        falar(hud, resposta_ia)
    else:
        falar(hud, "Não consegui conectar aos servidores de pesquisa agora. Verifique sua chave da Gemini nas configurações.")


def loop_cerebro_capri(hud: CapriHUD):
    os.chdir(PASTA_PROJETO)
    configurar_inicializacao_windows(True)
    reconhecedor = sr.Recognizer()

    while hud.rodando and not hud.config.get("gemini_api_key"):
        time.sleep(0.5)

    if not hud.rodando:
        return

    while hud.rodando:
        try:
            hud.reiniciar_ia = False
            os.environ["GEMINI_API_KEY"] = hud.config.get("gemini_api_key", "")
            client = genai.Client(http_options={'timeout': 20000})

            modelos = obter_lista_modelos_rapidos(client)
            historico_conversa = []

            falar(hud, "Sistemas da Capri online. Módulos de controle e pesquisa carregados.")
            hud.atualizar_estado("EM ESPERA", "#00F0FF", "Diga 'Capri' para me chamar...")

            while hud.rodando and not hud.reiniciar_ia:
                if hud.pausada:
                    time.sleep(0.2)
                    continue

                frase_ouvida = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=False)

                if not frase_ouvida or not hud.rodando or hud.pausada or hud.reiniciar_ia:
                    continue

                print(f"🗣️ Ouvido: '{frase_ouvida}'")
                chamou_capri, comando_embutido = extrair_comando_apos_nome(frase_ouvida)

                if chamou_capri:
                    if len(comando_embutido) < 3:
                        saudacao = random.choice(RESPOSTAS_CHAMADA)
                        falar(hud, saudacao, usar_cache=True)

                        hud.atualizar_estado("OUVINDO VOCÊ...", "#00FF66", "Pode falar sua pergunta ou comando...")
                        comando_direto = ouvir_microfone_com_hud(hud, reconhecedor, aguardando_comando=True)

                        if comando_direto:
                            print(f"🎯 Pergunta/Comando recebido: '{comando_direto}'")
                            hud.atualizar_estado("COMANDO DETECTADO", "#00FF66", f"Você: \"{comando_direto}\"")
                            processar_comando_usuario(comando_direto, hud, reconhecedor, client, modelos, historico_conversa)
                        else:
                            hud.atualizar_estado("EM ESPERA", "#00F0FF", "Nenhum comando detectado. Diga 'Capri'...")
                    else:
                        hud.atualizar_estado("VOZ DETECTADA", "#00FF66", f"Você: \"{comando_embutido}\"")
                        processar_comando_usuario(comando_embutido, hud, reconhecedor, client, modelos, historico_conversa)

                    hud.atualizar_estado("EM ESPERA", "#00F0FF", "Diga 'Capri' para me chamar...")

        except Exception as e:
            print(f"[Erro no Loop Principal]: {e}")
            time.sleep(2)


if __name__ == "__main__":
    app_hud = CapriHUD()
    thread_ia = threading.Thread(target=loop_cerebro_capri, args=(app_hud,), daemon=True)
    thread_ia.start()
    app_hud.root.mainloop()