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
from tkinter import filedialog
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
from fechar_apps import fechar_aplicativo, verificar_fechamento_rapido
from abrir_apps import abrir_aplicativo, verificar_abertura_rapida

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
        self.janela_config = None
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

    def salvar_executavel_personalizado(self, caminho_arquivo: str, nome_chamada: str) -> bool:
        """Salva o executável escolhido manualmente e gera variações de voz (ex: 'CS2' -> 'cs 2', 'c s 2')."""
        if not caminho_arquivo or not nome_chamada.strip():
            return False

        apelido_limpo = nome_chamada.strip()
        chave = apelido_limpo.lower()

        # Cria variações automáticas caso tenha letras + números (ex: CS2 -> cs 2, c s 2)
        variacoes = {chave, chave.replace(" ", "")}
        com_espaco_num = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", chave)
        variacoes.add(com_espaco_num)
        if len(chave) <= 5:
            variacoes.add(" ".join(list(chave.replace(" ", ""))))

        nome_exe = os.path.basename(caminho_arquivo)
        if not nome_exe.lower().endswith(".exe"):
            nome_exe = ""

        if "apps" not in self.config:
            self.config["apps"] = {}

        self.config["apps"][chave] = {
            "nome": f"{apelido_limpo.upper()} ({ os.path.basename(caminho_arquivo) })",
            "caminho_abrir": caminho_arquivo,
            "executavel": nome_exe,
            "ativo": True,
            "personalizado": True,
            "apelidos": list(variacoes)
        }
        salvar_configuracoes(self.config)
        return True

    def adicionar_executavel_manual(self, callback_atualizar_lista=None):
        """Abre o explorador de arquivos do Windows para escolher um .exe e pergunta como chamá-lo."""
        caminho = filedialog.askopenfilename(
            parent=self.janela_config if (self.janela_config and self.janela_config.winfo_exists()) else self.root,
            title="Selecione o Executável ou Atalho do Programa",
            filetypes=[
                ("Executáveis e Atalhos", "*.exe *.lnk *.url *.bat *.cmd"),
                ("Todos os arquivos", "*.*")
            ]
        )
        if not caminho:
            return

        # Janela Cyberpunk perguntando: "Como você vai chamar este executável?"
        dialogo = tk.Toplevel(self.root)
        dialogo.title("CAPRI // NOMEAR EXECUTÁVEL")
        dialogo.geometry("420x210")
        dialogo.configure(bg="#090D16")
        dialogo.attributes("-topmost", True)
        dialogo.resizable(False, False)

        tk.Label(
            dialogo, text="EXECUTÁVEL SELECIONADO:",
            fg="#00F0FF", bg="#090D16", font=("Consolas", 10, "bold")
        ).pack(pady=(15, 2))

        tk.Label(
            dialogo, text=os.path.basename(caminho),
            fg="#94A3B8", bg="#090D16", font=("Consolas", 9)
        ).pack(pady=(0, 12))

        tk.Label(
            dialogo, text="Como você quer chamar este aplicativo por voz?\n(Ex: CS2, Valorant, Photoshop)",
            fg="#FFFFFF", bg="#090D16", font=("Consolas", 9, "bold"), justify="center"
        ).pack(pady=4)

        entrada_nome = tk.Entry(
            dialogo, bg="#131B2E", fg="#00FF66", insertbackground="#00FF66",
            font=("Consolas", 12, "bold"), relief="flat", justify="center", width=28
        )
        entrada_nome.pack(pady=8, ipady=4)
        sugestao = os.path.splitext(os.path.basename(caminho))[0]
        entrada_nome.insert(0, sugestao)
        entrada_nome.select_range(0, tk.END)
        entrada_nome.focus_set()

        def _confirmar(event=None):
            nome_escolhido = entrada_nome.get().strip()
            if nome_escolhido:
                self.salvar_executavel_personalizado(caminho, nome_escolhido)
                dialogo.destroy()
                if callback_atualizar_lista:
                    callback_atualizar_lista()

        entrada_nome.bind("<Return>", _confirmar)

        tk.Button(
            dialogo, text="✔ SALVAR COMANDO DE VOZ", bg="#00FF66", fg="#090D16",
            font=("Consolas", 10, "bold"), relief="flat", cursor="hand2",
            command=_confirmar
        ).pack(pady=8, ipadx=12, ipady=3)

    def abrir_configuracoes(self, aviso_inicial: bool = False):
        if not hasattr(self, "janela_config"):
            self.janela_config = None
        
        if self.janela_config is not None and self.janela_config.winfo_exists():
            self.janela_config.lift()
            return

        self.config = carregar_configuracoes()

        win = tk.Toplevel(self.root)
        self.janela_config = win
        win.title("CAPRI // CONFIGURAÇÕES E APLICATIVOS")
        win.geometry("540x650")
        win.configure(bg="#090D16")
        win.attributes("-topmost", True)

        tk.Label(
            win, text="⚙ CENTRAL DE CONFIGURAÇÕES CAPRI",
            fg="#00F0FF", bg="#090D16", font=("Consolas", 12, "bold")
        ).pack(pady=(12, 4))

        frame_chaves = tk.Frame(win, bg="#0F172A", padx=12, pady=10)
        frame_chaves.pack(fill="x", padx=15, pady=6)

        def criar_campo(rotulo, chave_cfg, ocultar=False):
            tk.Label(frame_chaves, text=rotulo, fg="#E2E8F0", bg="#0F172A", font=("Consolas", 9, "bold")).pack(anchor="w")
            ent = tk.Entry(
                frame_chaves, bg="#1E293B", fg="#00FF66", insertbackground="#00FF66",
                font=("Consolas", 9), relief="flat", show="*" if ocultar else ""
            )
            ent.insert(0, self.config.get(chave_cfg, ""))
            ent.pack(fill="x", pady=(2, 8), ipady=3)
            return ent

        ent_gemini = criar_campo("GEMINI API KEY (Obrigatória):", "gemini_api_key", ocultar=True)
        ent_fish_key = criar_campo("FISH AUDIO API KEY (Opcional - Voz Clonada):", "fish_api_key", ocultar=True)
        ent_fish_id = criar_campo("FISH AUDIO VOICE ID (Ex: 802e3bc2b27e49c2995d23ef70e6ac89):", "fish_voice_id")

        def salvar_chaves(*_):
            self.config["gemini_api_key"] = ent_gemini.get().strip()
            self.config["fish_api_key"] = ent_fish_key.get().strip()
            self.config["fish_voice_id"] = ent_fish_id.get().strip()
            salvar_configuracoes(self.config)

        for entry_widget in (ent_gemini, ent_fish_key, ent_fish_id):
            entry_widget.bind("<KeyRelease>", salvar_chaves)

        # Cabeçalho de Aplicativos + Botão para Adicionar Executável Manualmente
        frame_topo_apps = tk.Frame(win, bg="#090D16")
        frame_topo_apps.pack(fill="x", padx=15, pady=(8, 4))

        tk.Label(
            frame_topo_apps, text="APLICATIVOS AUTORIZADOS (VERDE = ATIVO):",
            fg="#00F0FF", bg="#090D16", font=("Consolas", 9, "bold")
        ).pack(side="left")

        container_lista = tk.Frame(win, bg="#0F172A")
        container_lista.pack(fill="both", expand=True, padx=15, pady=6)

        canvas_apps = tk.Canvas(container_lista, bg="#0F172A", highlightthickness=0)
        scrollbar = tk.Scrollbar(container_lista, orient="vertical", command=canvas_apps.yview)
        frame_interno = tk.Frame(canvas_apps, bg="#0F172A")

        frame_interno.bind("<Configure>", lambda e: canvas_apps.configure(scrollregion=canvas_apps.bbox("all")))
        canvas_apps.create_window((0, 0), window=frame_interno, anchor="nw", width=485)
        canvas_apps.configure(yscrollcommand=scrollbar.set)

        canvas_apps.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        def renderizar_lista_apps():
            for widget in frame_interno.winfo_children():
                widget.destroy()

            apps_ordenados = sorted(
                self.config.get("apps", {}).items(),
                key=lambda item: (not item[1].get("personalizado", False), item[1].get("nome", item[0]).lower())
            )

            for chave_app, dados_app in apps_ordenados:
                linha = tk.Frame(frame_interno, bg="#1E293B", pady=4, padx=8)
                linha.pack(fill="x", pady=2)

                prefixo = "⭐ " if dados_app.get("personalizado") else ""
                lbl_nome = tk.Label(
                    linha, text=f"{prefixo}{dados_app.get('nome', chave_app)}",
                    fg="#FFFFFF", bg="#1E293B", font=("Consolas", 9, "bold"), anchor="w"
                )
                lbl_nome.pack(side="left", fill="x", expand=True)

                btn_toggle = tk.Button(linha, width=4, font=("Consolas", 9, "bold"), relief="flat", cursor="hand2")

                def atualizar_cor_botao(b=btn_toggle, k=chave_app):
                    ativo = self.config["apps"][k].get("ativo", False)
                    b.configure(
                        text="✔" if ativo else "✖",
                        bg="#00FF66" if ativo else "#FF0055",
                        fg="#090D16" if ativo else "#FFFFFF"
                    )

                def alternar_app(k=chave_app, b=btn_toggle):
                    estado_atual = self.config["apps"][k].get("ativo", False)
                    self.config["apps"][k]["ativo"] = not estado_atual
                    salvar_configuracoes(self.config)
                    atualizar_cor_botao(b, k)

                btn_toggle.configure(command=alternar_app)
                atualizar_cor_botao()
                btn_toggle.pack(side="right")

        # Botão para selecionar executável manualmente (igual às Configurações Gráficas do Windows)
        tk.Button(
            win, text="➕ ADICIONAR EXECUTÁVEL (.EXE) MANUALMENTE",
            bg="#00F0FF", fg="#090D16", font=("Consolas", 9, "bold"),
            relief="flat", cursor="hand2",
            command=lambda: self.adicionar_executavel_manual(callback_atualizar_lista=renderizar_lista_apps)
        ).pack(fill="x", padx=15, pady=(2, 6), ipady=4)

        renderizar_lista_apps()

        def concluir_e_fechar():
            salvar_chaves()
            self.reiniciar_ia = True
            win.destroy()

        tk.Button(
            win, text="SALVAR E APLICAR", bg="#00FF66", fg="#090D16",
            font=("Consolas", 10, "bold"), relief="flat", cursor="hand2",
            command=concluir_e_fechar
        ).pack(fill="x", padx=15, pady=(4, 12), ipady=5)

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

    def atualizar_estado(self, novo_estado: str, cor: str = "#00F0FF", legenda: str = ""):
        """Atualiza o status e mantém o aviso 'Diga Capri' fixo, sem exibir legendas de fala."""
        self.estado_atual = novo_estado
        self.cor_atual = cor

        def _atualizar_ui():
            # 1. Atualiza o estado principal (EM ESPERA, OUVINDO VOCÊ, FALANDO...)
            if hasattr(self, "lbl_estado"):
                self.lbl_estado.configure(text=novo_estado, fg=cor)
            elif hasattr(self, "lbl_status"):
                self.lbl_status.configure(text=novo_estado, fg=cor)

            # 2. Mantém apenas o "Diga, CAPRI" fixo (ignora as legendas de "CAPRI:" e "Você:")
            texto_fixo = "Diga, CAPRI"
            for attr in ("lbl_legenda", "lbl_subtitulo", "lbl_fala", "lbl_info"):
                if hasattr(self, attr):
                    getattr(self, attr).configure(text=texto_fixo)

        try:
            self.root.after(0, _atualizar_ui)
        except Exception:
            pass

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
