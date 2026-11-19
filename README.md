# ⚡ CAPRI — Assistente Virtual Cyberpunk (`v0.1.5`)

![Versão](https://img.shields.io/badge/versão-0.1.5%20pre--alpha-F06A82?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11%2B-54F2F2?style=for-the-badge&logo=python&logoColor=white)
![Plataforma](https://img.shields.io/badge/Windows-10%20%2F%2011-9B72FF?style=for-the-badge&logo=windows&logoColor=white)
![Vosk Offline](https://img.shields.io/badge/Voz%20STT-100%25%20Offline%20(Vosk)-A3E635?style=for-the-badge)

**Capri** (Projeto *Capricorn*) é uma assistente virtual pessoal para Windows inspirada na estética Cyberpunk. Ela combina controle local instantâneo do computador, reconhecimento de voz **100% offline**, sprites dinâmicos com sincronia labial em tempo real e integração com múltiplos provedores de Inteligência Artificial.

---

## ✨ Novidades da Versão `0.1.5`

- **🎨 Novo HUD Cyberpunk Limpo & Monitor CRT:** Interface remodelada com linhas de varredura (*scanlines*), cantoneiras em lilás, emblema dinâmico de estado (`CAPRI // ...`) e card de telemetria com barra animada de atividade vocal. Os controles essenciais (**`MIC ON`/`MUTADA`**, **`⚙ CONFIG`** e minimizar para bandeja) ficam acessíveis diretamente no card e na barra inferior.
- **💬 Barra de Pesquisa & Chat Funcional (`Conversar com Capri...`):** Digite comandos locais (ex: *"abrir spotify"*, *"que horas são"*) ou perguntas abertas para a IA diretamente pela interface — funcionando inclusive quando o microfone estiver silenciado.
- **🎭 Motor Completo de Sprites Animados (`GerenciadorSpritesCapri`):**
  - **Introdução animada** ao iniciar (`01-signal` até `07-ready`).
  - **Sincronia labial (Lip-Sync)** em tempo real acompanhando a cadência da fala (`mouth_small`, `mouth_round`, `mouth_wide`).
  - **Piscadas naturais e micro-expressões** enquanto em espera, além de reações contextuais (*pensando*, *ouvindo*, *dormindo*, *aceno* e *modo música* com notas flutuantes).
  - **Interação de carinho (*Headpat*):** clicar na personagem exibe animação de carinho com efeito de coração.
  - **Seletor de Poses & Modo Mascote:** escolha entre 8 poses padrão ou ative o recorte transparente direto na aba *Sistema*.
- **🎙️ Reconhecimento de Voz 100% Offline (Vosk):** Transcrição local via **Vosk** (`vosk-model-small-pt-0.3`, baixado automaticamente na 1ª execução para `cache/`), com análise de múltiplas hipóteses, corretor fonético expandido em `dicionario_comandos.py` e fallback automático para reconhecimento online.
- **🧠 Suporte Multi-IA & Prioridade `gemini-3.5-flash-lite`:** Alterne facilmente entre **Google Gemini** (com busca na web e fallback automático entre os modelos `3.5-flash-lite`, `3.5-flash`, `3.0-flash-lite`, `3.0-flash`, `2.5-flash`, `2.5-flash-lite`, `2.0-flash` e `flash-latest`), **Claude** e **DeepSeek**.
- **🔊 Cache Permanente de Voz:** Todas as falas geradas via **Fish Audio** ou **Edge-TTS** ficam armazenadas permanentemente na pasta `cache/` por ID de voz, garantindo resposta imediata e economia de requisições.
- **📦 Compilação Otimizada com Pasta `bin/`:** Executável `Capri.exe` empacotado em modo `--onedir` com dependências isoladas em `bin/`, mantendo o executável leve, rápido para abrir e dentro dos limites nativos do GitHub.

---

## 🛠️ Funcionalidades Principais

| Módulo | Recursos |
| :--- | :--- |
| **Controle do PC** | Abrir e fechar programas nativos, jogos e executáveis personalizados (`.exe`, `.lnk`, `.bat`) cadastrados por voz ou via interface. |
| **Spotify & Mídia** | Tocar/trocar músicas diretamente no Spotify Desktop, pausar, retomar, avançar/voltar faixas e ajustar volume do sistema. |
| **Energia & Sistema** | Bloquear tela, suspender, reiniciar, desligar (com cancelamento), consultar horas e iniciar automaticamente com o Windows. |
| **Central de Configurações** | Painel temático com 3 abas (**Aplicativos**, **APIs & Voz**, **Sistema**), scanner automático do Menu Iniciar e registro rápido de novos `.exe`. |
| **Bandeja do Sistema** | Execução discreta em segundo plano via ícone na bandeja do Windows (`pystray`). |

---

## 📂 Estrutura do Projeto

```text
Capricorn/
├── Capri.exe                 # Executável principal (requer as pastas bin/ e assets/ ao lado)
├── bin/                      # Bibliotecas e dependências compiladas (PyInstaller --contents-directory)
├── assets/                   # Sprites animados (capri/, default/, fonts/) e ícones do HUD
├── cache/                    # Criado automaticamente: modelo Vosk offline e cache permanente de falas (.mp3)
├── capri_config.json         # Configurações locais, chaves de API e lista de aplicativos ativos
├── src/
│   ├── capri_core.py         # Núcleo principal (loop de voz + fila da barra de pesquisa)
│   ├── hud.py                # Interface Cyberpunk, motor de sprites, bandeja e configurações
│   ├── voz.py                # Captura de áudio, Vosk offline, Fish Audio / Edge-TTS e Lip-Sync
│   ├── cerebro_ia.py         # Integração Gemini / Claude / DeepSeek e roteamento de comandos
│   ├── dicionario_comandos.py# Gatilhos de voz, intenções e corretor fonético para Vosk
│   ├── sistema_pc.py         # Execução instantânea de comandos locais do Windows
│   ├── abrir_apps.py         # Gerenciamento e execução de aplicativos mapeados
│   └── spotify_control.py    # Automação de reprodução no Spotify Desktop
└── README.md
```

---

## 🚀 Como Usar

### Opção 1: Executar diretamente pelo `Capri.exe` (Recomendado)
1. Clone ou baixe o repositório mantendo juntos na mesma pasta o **`Capri.exe`**, a pasta **`bin/`** e a pasta **`assets/`**.
2. Dê um duplo clique em **`Capri.exe`**.
3. Na primeira execução:
   - A Capri baixará automaticamente o modelo offline em português do Vosk (~31 MB) para a pasta `cache/`.
   - A **Central de Configurações** abrirá automaticamente caso nenhuma chave de API esteja configurada. Insira sua chave (**Gemini**, **Claude** ou **DeepSeek**) e, opcionalmente, suas credenciais do **Fish Audio** na aba **APIs & Voz**.
4. Pronto! Chame **"Capri"** no microfone ou digite qualquer comando/pergunta na barra **"Conversar com Capri..."**.

### Opção 2: Rodar a partir do código-fonte (Python)
1. Crie e ative um ambiente virtual:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Instale as dependências necessárias:
   ```powershell
   pip install google-genai vosk sounddevice numpy pygame edge-tts SpeechRecognition requests pillow pystray pyinstaller
   ```
3. Inicie a assistente:
   ```powershell
   python src/capri_core.py
   ```

---

## ⚙️ Compilando uma Nova Build (`Capri.exe` + `bin/`)

Caso faça alterações no código-fonte e queira atualizar o executável mantendo o tamanho reduzido para o GitHub:

```powershell
taskkill /F /IM Capri.exe /T 2>$null
Remove-Item -Recurse -Force build, dist, bin -ErrorAction SilentlyContinue
Remove-Item -Force Capri.exe, Capri.spec -ErrorAction SilentlyContinue

$icone = if (Test-Path "assets\default\app.ico") { "assets/default/app.ico" } else { "assets/icone.ico" }
pyinstaller --noconfirm --onedir --noconsole --clean --name "Capri" --contents-directory "bin" --icon="$icone" --paths "src" --collect-all vosk --distpath "dist" src/capri_core.py

Move-Item -Path "dist\Capri\Capri.exe" -Destination "." -Force
Move-Item -Path "dist\Capri\bin" -Destination "." -Force
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
```

> **Nota:** Mantenha sempre `Capri.exe`, `bin/` e `assets/` no mesmo diretório ao mover ou distribuir a aplicação.

---

## 🧠 Desempenho & Uso de Memória

- **Uso basal:** ~120 MB a 280 MB de RAM em espera com sprites cacheados e modelo compacto do Vosk.
- **Teto elástico:** liberado para utilizar até ~1 GB de RAM sob demanda caso modelos maiores de transcrição local sejam ativados em `src/voz.py`, com coleta de lixo automática (`gc.collect()`).

---

## 📄 Notas de Privacidade

- O arquivo `capri_config.json` armazena suas chaves de API localmente. Certifique-se de mantê-lo no `.gitignore` antes de publicar atualizações em repositórios públicos.