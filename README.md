# CAPRI (Capricorn) — v0.3.1

![Versão](https://img.shields.io/badge/vers%C3%A3o-v0.3.1-00FF99?style=for-the-badge)
![Plataforma](https://img.shields.io/badge/plataforma-Windows-0078D6?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)

> **Sua assistente virtual para ações do dia a dia.**  
> Interface HUD cyberpunk com sprites animados, reconhecimento de voz offline, visão de tela, busca na web, controle do Windows e personalidade própria.

---

## Novidades da v0.3.1

- **Inicialização Silenciosa em Segundo Plano (`--startup`):** ao iniciar junto com o Windows, a Capri sobe direto na bandeja do sistema via `Capri.exe` ou `pythonw.exe`, sem abrir janela de terminal e sem disparar falas automáticas no boot.
- **Controle de Energia do Windows:** novos comandos por voz, texto e *Function Calling* (`controlar_energia_pc`) para **desligar**, **reiniciar**, **bloquear a tela**, **suspender** e **cancelar desligamento agendado** (com suporte a tempo personalizado, ex.: *"desligar o PC em 10 minutos"*).
- **Atalhos Globais do Windows:**
  - `Alt + Espaço` — ativa a escuta de voz imediatamente (*Push-to-Talk*, sem precisar dizer *"Capri"*).
  - `Alt + C` — traz o HUD à frente (mesmo minimizado na bandeja) e já foca a barra de texto.
- **Personalidade Aprimorada:** novo perfil de conversa mais solto, afiado e natural, com temperatura dinâmica (`0.95` no papo livre e `0.78` ao acionar ferramentas) e ajustes de filtros aplicados também no modo fallback do Gemini.
- **Estabilidade e Correções:**
  - Logger adaptado para execução sem console (`sys.stderr` seguro em `pythonw.exe` e executáveis com `console=False`).
  - Correção no encerramento por comando de voz (*"encerrar Capri"*).
  - Ajuste do estado de inicialização do motor para respostas instantâneas na caixa de texto.
  - Correção das URLs padrão do callback do Spotify e do download do modelo Vosk offline.

---

## Principais Recursos

- **Voz Natural & Escuta Offline:** detecção local de voz na RAM com **Vosk** (com fallback para Google Speech) e síntese de voz via **Fish Audio API** (com fallback automático para **Edge TTS** e cache LRU de áudios).
- **IA Multimodal & Function Calling:** suporte a **Google Gemini** (com execução automática de ferramentas do PC), **Claude** e **DeepSeek**, além de modo dedicado para geração de código copiável no balão lateral.
- **Visão de Tela & Modo Observador:** analisa a tela atual sob demanda ou acompanha jogos e atividades em tempo real fazendo comentários.
- **Busca Web Integrada:** pesquisa informações atualizadas na internet diretamente pelo comando de voz ou texto.
- **Controle do PC & Spotify:** abre e fecha aplicativos cadastrados, controla volume e reprodução de mídia, integra com o Spotify e gerencia a energia do Windows.
- **Memória Persistente (20 dias):** banco SQLite local (`data/`) que salva lembretes, contexto de conversas e acompanha eventos recentes citados por você.
- **HUD Cyberpunk & Modo Livre:** janela flutuante personalizável com sprites animados, bandeja do sistema e modo livre na área de trabalho.
- **Agente Autônomo (Reigns):** módulo experimental que lê a tela e joga *Reigns* automaticamente (segure `ESC` para parar).

---

## Instalação Rápida (Windows — Recomendada)

Não é necessário instalar Python para usar a versão compilada:

1. Acesse a aba **[Releases](../../releases)** deste repositório e baixe o arquivo **`Capricorn-v0.3.1-Windows.zip`**.
2. Extraia o conteúdo em uma pasta de sua preferência (ex.: `C:\Capri\`).
3. Execute **`Capri.exe`**.
4. Na primeira execução, clique no ícone de engrenagem (**CONFIG**) e insira sua chave de API (Gemini, Claude ou DeepSeek) e, opcionalmente, suas credenciais do Fish Audio e Spotify.

> **Dica:** Em **CONFIG → SISTEMA**, ative **"Iniciar com o Windows"** para que a Capri inicie silenciosamente na bandeja sempre que você ligar o PC.

---

## Executando pelo Código-Fonte (Desenvolvimento)

### Pré-requisitos
- Windows 10 ou 11
- Python 3.11+
- Microfone configurado no sistema

### Passo a passo

```powershell
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
cd Capricorn

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instale as dependências
pip install google-genai pygame pystray pillow vosk SpeechRecognition sounddevice edge-tts requests mss pyautogui pytweening spotipy pyinstaller

# 4. Execute normalmente (com HUD visível)
python src/main.py

# 5. (Opcional) Execute silenciosamente em segundo plano, sem terminal
Start-Process .\.venv\Scripts\pythonw.exe -ArgumentList 'src/main.py', '--startup'
```

---

## Atalhos e Exemplos de Comandos

| Ação / Recurso | Atalho ou Exemplo de Comando |
| :--- | :--- |
| Falar direto (Push-to-Talk) | `Alt + Espaço` |
| Abrir HUD e focar chat | `Alt + C` |
| Chamar por voz | *"Capri, ..."* / *"Cap, ..."* / *"Capricórnio, ..."* |
| Controlar energia do PC | *"Desligar o PC em 5 minutos"*, *"Cancelar desligamento"*, *"Bloquear tela"*, *"Reiniciar o computador"* |
| Abrir / fechar apps | *"Abre o Spotify"*, *"Fecha o navegador"* |
| Mídia e volume | *"Pausa a música"*, *"Próxima música"*, *"Aumenta o volume"* |
| Visão de tela | *"Olha a minha tela"* / *"Ativa o modo observador"* |
| Busca na web | *"Pesquisa na internet as notícias de hoje"* |
| Encerrar a assistente | *"Encerrar Capri"* |

---

## Estrutura do Projeto

```text
Capricorn/
├── src/
│   ├── main.py              # Ponto de entrada (suporte à flag --startup)
│   ├── core/
│   │   ├── config.py        # Configurações persistentes e registro de boot do Windows
│   │   ├── engine.py        # Loop principal, threads de voz/texto e atalhos globais
│   │   └── logger.py        # Log rotativo em data/capri.log (seguro para pythonw)
│   ├── ai/
│   │   ├── cerebro.py       # Roteador de comandos, prompts, safety settings e LLMs
│   │   ├── ferramentas.py   # Ferramentas de Function Calling (apps, web, energia, visão)
│   │   ├── memoria.py       # Memória persistente em SQLite (20 dias)
│   │   └── visao.py         # Captura de tela (MSS) e Modo Observador
│   ├── audio/
│   │   ├── comandos.py      # Normalização de fala e detecção de wake-words
│   │   └── voz.py           # Vosk offline, Fish Audio API, Edge TTS e cache de áudio
│   ├── system/
│   │   ├── apps.py          # Varredura e execução de aplicativos instalados
│   │   ├── atalhos.py       # Atalhos globais Win32 (Alt+Espaço e Alt+C)
│   │   └── spotify.py       # Integração com Spotify (PKCE e atalhos nativos)
│   ├── ui/
│   │   ├── hud.py           # Interface HUD cyberpunk, bandeja e painel de configurações
│   │   └── modo_livre.py    # Modo livre na área de trabalho
│   └── agents/
│       └── reigns.py        # Agente autônomo para o jogo Reigns
├── assets/                  # Sprites, ícones e recursos visuais
├── bin/                     # Modelo Vosk offline (vosk-model-small-pt-0.3)
└── data/                    # Configurações locais, chaves, memória e logs (ignorado pelo Git)
```

---

## Privacidade

Todas as suas chaves de API, histórico de conversas, lembretes e logs ficam salvos **exclusivamente na pasta local `data/`** da sua máquina (ignorada pelo Git e excluída dos pacotes de release).