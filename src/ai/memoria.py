import os
import re
import json
import time
import sqlite3
import threading
from datetime import datetime
from google.genai import types
from core.logger import obter_logger
log = obter_logger("memoria")  # ou "cerebro", "memoria", "modo_livre", "voz"

DIAS_RETENCAO_USUARIO = 20
MODELO_MEMORIA = "gemini-3.5-flash-lite"

GATILHOS_EVENTO = (
    "teste", "prova", "exame", "trabalho", "seminario", "seminário",
    "apresentacao", "apresentação", "entrevista", "viagem", "consulta",
    "projeto", "entrega", "campeonato", "torneio", "faculdade", "aula",
    "amanha", "amanhã", "semana que vem", "segunda", "terca", "terça",
    "quarta", "quinta", "sexta", "sabado", "sábado", "domingo",
    "vou fazer", "tenho que", "preciso entregar", "vou tentar"
)

STOPWORDS_PT = {
    "como", "para", "com", "uma", "uns", "umas", "isso", "isto", "esse", "essa",
    "aqui", "onde", "quando", "qual", "quais", "porque", "sobre", "voce", "você",
    "capri", "mais", "muito", "pode", "fazer", "quero", "esta", "está", "estou",
    "tinha", "falei", "disse", "tudo", "nada", "agora", "hoje", "ontem"
}


def _limpar_json_bruto(texto: str) -> str:
    txt = (texto or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


class MemoriaCapri:
    """Banco de memória persistente (SQLite) para conversas de 20 dias, follow-ups e aprendizado no Reigns."""

    def __init__(self, pasta_projeto: str):
        self.caminho_db = os.path.join(pasta_projeto, "capri_memoria.db")
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.caminho_db, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._criar_tabelas()
        self.limpar_memorias_antigas()

    def _criar_tabelas(self):
        with self._lock:
            cur = self.conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_msg TEXT NOT NULL,
                    capri_msg TEXT NOT NULL,
                    criado_em REAL NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS eventos_usuario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    descricao TEXT NOT NULL,
                    citado_em REAL NOT NULL,
                    perguntar_apos REAL NOT NULL,
                    perguntado INTEGER DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS reigns_jogadas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    turno INTEGER NOT NULL,
                    carta TEXT,
                    escolha TEXT NOT NULL,
                    barras_json TEXT,
                    motivo TEXT,
                    criado_em REAL NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS reigns_licoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    turnos_sobrevividos INTEGER NOT NULL,
                    licao TEXT NOT NULL,
                    criado_em REAL NOT NULL
                )
            """)

            self.conn.commit()

    def limpar_memorias_antigas(self):
        """Remove conversas e eventos do usuário com mais de 20 dias."""
        limite_ts = time.time() - (DIAS_RETENCAO_USUARIO * 86400)
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM conversas WHERE criado_em < ?", (limite_ts,))
            cur.execute("DELETE FROM eventos_usuario WHERE citado_em < ?", (limite_ts,))
            cur.execute("""
                DELETE FROM reigns_jogadas
                WHERE id NOT IN (SELECT id FROM reigns_jogadas ORDER BY id DESC LIMIT 400)
            """)
            self.conn.commit()

    # =====================================================================
    # 1. MEMÓRIA DO USUÁRIO (20 DIAS + FOLLOW-UP PROATIVO)
    # =====================================================================
    def registrar_conversa(self, usuario_msg: str, capri_msg: str):
        u = (usuario_msg or "").strip()
        c = (capri_msg or "").strip()
        if not u or not c:
            return
        if len(c) > 900:
            c = c[:900] + "\n...[trecho longo resumido na memória]"
        with self._lock:
            self.conn.execute(
                "INSERT INTO conversas (usuario_msg, capri_msg, criado_em) VALUES (?, ?, ?)",
                (u, c, time.time()),
            )
            self.conn.commit()

    def obter_contexto_usuario(self, consulta_atual: str = "") -> str:
        self.limpar_memorias_antigas()
        partes = []

        with self._lock:
            cur = self.conn.cursor()

            # Eventos dos últimos 20 dias
            cur.execute(
                "SELECT descricao, citado_em, perguntado FROM eventos_usuario ORDER BY citado_em DESC LIMIT 8"
            )
            eventos = cur.fetchall()
            if eventos:
                linhas_ev = []
                for ev in eventos:
                    data_str = datetime.fromtimestamp(ev["citado_em"]).strftime("%d/%m")
                    status = "já perguntado" if ev["perguntado"] else "aguardando retorno"
                    linhas_ev.append(f"- [{data_str}] {ev['descricao']} ({status})")
                partes.append("Eventos e compromissos que o usuário citou recentemente:\n" + "\n".join(linhas_ev))

            # Últimas 6 interações cronológicas
            cur.execute(
                "SELECT id, usuario_msg, capri_msg, criado_em FROM conversas ORDER BY id DESC LIMIT 6"
            )
            recentes = list(reversed(cur.fetchall()))
            ids_recentes = {r["id"] for r in recentes}

            # Lembranças relacionadas por palavras-chave (até 20 dias atrás)
            termos = [
                p for p in re.findall(r"[a-zA-ZáéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ0-9]{4,}", (consulta_atual or "").lower())
                if p not in STOPWORDS_PT
            ]
            lembrancas_antigas = []
            if termos:
                vistos = set(ids_recentes)
                for termo in termos[:5]:
                    cur.execute(
                        """
                        SELECT id, usuario_msg, capri_msg, criado_em FROM conversas
                        WHERE lower(usuario_msg) LIKE ? OR lower(capri_msg) LIKE ?
                        ORDER BY criado_em DESC LIMIT 2
                        """,
                        (f"%{termo}%", f"%{termo}%"),
                    )
                    for row in cur.fetchall():
                        if row["id"] not in vistos:
                            vistos.add(row["id"])
                            lembrancas_antigas.append(row)
                            if len(lembrancas_antigas) >= 4:
                                break
                    if len(lembrancas_antigas) >= 4:
                        break

            if lembrancas_antigas:
                linhas_ant = []
                for r in sorted(lembrancas_antigas, key=lambda x: x["criado_em"]):
                    dt = datetime.fromtimestamp(r["criado_em"]).strftime("%d/%m")
                    linhas_ant.append(f"[{dt}] Usuário: {r['usuario_msg']} | Capri: {r['capri_msg'][:180]}")
                partes.append("Lembranças relevantes dos últimos 20 dias:\n" + "\n".join(linhas_ant))

            if recentes:
                linhas_rec = []
                for r in recentes:
                    dt = datetime.fromtimestamp(r["criado_em"]).strftime("%d/%m %H:%M")
                    linhas_rec.append(f"[{dt}] Usuário: {r['usuario_msg']}\n[{dt}] Capri: {r['capri_msg'][:260]}")
                partes.append("Conversa mais recente:\n" + "\n".join(linhas_rec))

        return "\n\n".join(partes)

    def analisar_e_salvar_evento_async(self, client, mensagem_usuario: str):
        msg = (mensagem_usuario or "").strip()
        if not client or len(msg) < 10:
            return

        if not any(g in msg.lower() for g in GATILHOS_EVENTO):
            return

        def _extrair():
            try:
                hoje = datetime.now().strftime("%d/%m/%Y (%A)")
                prompt = (
                    f"Hoje é {hoje}. O usuário disse para sua assistente virtual:\n"
                    f"\"{msg}\"\n\n"
                    "Avalie se o usuário mencionou algum evento pessoal, prova, teste, trabalho, "
                    "entrevista, projeto, viagem ou compromisso sobre o qual uma amiga próxima "
                    "deveria perguntar alguns dias depois para saber como foi.\n"
                    "Responda ESTRITAMENTE em JSON:\n"
                    "{\n"
                    '  "tem_evento": true | false,\n'
                    '  "descricao": "resumo curto do evento (ex: teste de cálculo na faculdade)",\n'
                    '  "dias_para_perguntar": 2\n'
                    "}\n"
                    "Regras: use entre 1 e 7 em 'dias_para_perguntar' (se for amanhã use 2; "
                    "se não houver data clara use 2 ou 3). Se for só uma pergunta genérica ou comando de PC, retorne tem_evento=false."
                )
                resp = client.models.generate_content(
                    model=MODELO_MEMORIA,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                dados = json.loads(_limpar_json_bruto(resp.text or "{}"))
                if not dados.get("tem_evento"):
                    return

                desc = str(dados.get("descricao", "")).strip()
                dias = max(1, min(14, int(dados.get("dias_para_perguntar", 2))))
                if not desc:
                    return

                agora = time.time()
                perguntar_apos = agora + (dias * 86400)

                with self._lock:
                    cur = self.conn.cursor()
                    cur.execute(
                        "SELECT id FROM eventos_usuario WHERE lower(descricao) = ? AND perguntado = 0",
                        (desc.lower(),),
                    )
                    if cur.fetchone():
                        return
                    self.conn.execute(
                        "INSERT INTO eventos_usuario (descricao, citado_em, perguntar_apos, perguntado) VALUES (?, ?, ?, 0)",
                        (desc, agora, perguntar_apos),
                    )
                    self.conn.commit()
                print(f"  [Memória Capri]: Evento salvo -> '{desc}' (vou perguntar em {dias} dia(s))")
            except Exception as e:
                print(f"  [Aviso Extração de Evento]: {e}")

        threading.Thread(target=_extrair, daemon=True).start()

    def obter_evento_para_perguntar(self) -> dict | None:
        agora = time.time()
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT id, descricao, citado_em FROM eventos_usuario
                WHERE perguntado = 0 AND perguntar_apos <= ?
                ORDER BY perguntar_apos ASC LIMIT 1
                """,
                (agora,),
            )
            row = cur.fetchone()
            if not row:
                return None
            dias_atras = max(1, int((agora - row["citado_em"]) // 86400))
            return {"id": row["id"], "descricao": row["descricao"], "dias_atras": dias_atras}

    def marcar_evento_como_perguntado(self, evento_id: int):
        with self._lock:
            self.conn.execute("UPDATE eventos_usuario SET perguntado = 1 WHERE id = ?", (evento_id,))
            self.conn.commit()

    def listar_eventos_ativos(self) -> list[str]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT descricao, citado_em FROM eventos_usuario ORDER BY citado_em DESC LIMIT 10")
            return [
                f"[{datetime.fromtimestamp(r['citado_em']).strftime('%d/%m')}] {r['descricao']}"
                for r in cur.fetchall()
            ]

    # =====================================================================
    # 2. MEMÓRIA E APRENDIZADO DO REIGNS
    # =====================================================================
    def iniciar_nova_run_reigns(self) -> int:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT MAX(m) AS max_run FROM (
                    SELECT COALESCE(MAX(run_id), 0) AS m FROM reigns_jogadas
                    UNION ALL
                    SELECT COALESCE(MAX(run_id), 0) AS m FROM reigns_licoes
                )
            """)
            row = cur.fetchone()
            return int(row["max_run"] or 0) + 1

    def registrar_jogada_reigns(self, run_id: int, turno: int, carta: str, escolha: str, barras: dict, motivo: str):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO reigns_jogadas (run_id, turno, carta, escolha, barras_json, motivo, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, turno, carta, escolha, json.dumps(barras, ensure_ascii=False), motivo, time.time()),
            )
            self.conn.commit()

    def obter_resumo_aprendizado_reigns(self, run_id_atual: int) -> str:
        partes = []
        with self._lock:
            cur = self.conn.cursor()

            cur.execute("SELECT COALESCE(MAX(turnos_sobrevividos), 0) AS recorde, COUNT(*) AS total FROM reigns_licoes")
            stats = cur.fetchone()
            if stats and stats["total"] > 0:
                partes.append(f"Estatísticas: {stats['total']} reinados encerrados | Recorde: {stats['recorde']} turnos.")

            cur.execute("SELECT run_id, turnos_sobrevividos, licao FROM reigns_licoes ORDER BY id DESC LIMIT 12")
            licoes = cur.fetchall()
            if licoes:
                linhas = [f"- [Run #{r['run_id']} | {r['turnos_sobrevividos']}t]: {r['licao']}" for r in licoes]
                partes.append("LIÇÕES APRENDIDAS EM RUNS PASSADAS (use isso para NÃO repetir os mesmos erros):\n" + "\n".join(linhas))

            cur.execute(
                """
                SELECT turno, carta, escolha, barras_json, motivo FROM reigns_jogadas
                WHERE run_id = ? ORDER BY id DESC LIMIT 6
                """,
                (run_id_atual,),
            )
            jogadas = list(reversed(cur.fetchall()))
            if jogadas:
                linhas_j = [
                    f"T{j['turno']} | Carta: {j['carta']} -> {j['escolha']} | Barras: {j['barras_json']} ({j['motivo']})"
                    for j in jogadas
                ]
                partes.append("Histórico recente desta run atual:\n" + "\n".join(linhas_j))

        return "\n\n".join(partes) if partes else "Primeira run registrada. Mantenha todas as barras perto de 50%."

    def aprender_com_morte_reigns_async(self, client, run_id: int, turnos_sobrevividos: int, causa_morte: str = ""):
        if not client or turnos_sobrevividos < 1:
            return

        def _processar_post_mortem():
            try:
                with self._lock:
                    cur = self.conn.cursor()
                    cur.execute(
                        """
                        SELECT turno, carta, escolha, barras_json, motivo FROM reigns_jogadas
                        WHERE run_id = ? ORDER BY id DESC LIMIT 6
                        """,
                        (run_id,),
                    )
                    ultimas = list(reversed(cur.fetchall()))

                resumo_run = "\n".join(
                    f"Turno {r['turno']} | Carta: {r['carta']} | Escolha: {r['escolha']} | Barras: {r['barras_json']} | Motivo: {r['motivo']}"
                    for r in ultimas
                )

                prompt = (
                    f"A Capri acabou de morrer na Run #{run_id} do jogo Reigns após {turnos_sobrevividos} turnos.\n"
                    f"Causa visível na tela: {causa_morte or 'não especificada'}\n"
                    f"Últimas jogadas antes da morte:\n{resumo_run}\n\n"
                    "Escreva EXATAMENTE 1 frase curta e prática (máx 25 palavras) como regra de aprendizado "
                    "para a Capri NÃO cometer o mesmo erro nas próximas runs."
                )
                resp = client.models.generate_content(model=MODELO_MEMORIA, contents=prompt)
                licao = (resp.text or "").strip().replace("\n", " ")
                if licao:
                    with self._lock:
                        self.conn.execute(
                            "INSERT INTO reigns_licoes (run_id, turnos_sobrevividos, licao, criado_em) VALUES (?, ?, ?, ?)",
                            (run_id, turnos_sobrevividos, licao, time.time()),
                        )
                        self.conn.commit()
                    print(f"  [Reigns Memória] Nova lição salva (Run #{run_id}): {licao}")
            except Exception as e:
                print(f"  [Aviso Post-Mortem Reigns]: {e}")

        threading.Thread(target=_processar_post_mortem, daemon=True).start()

    def limpar_memoria_reigns(self):
        with self._lock:
            self.conn.execute("DELETE FROM reigns_jogadas")
            self.conn.execute("DELETE FROM reigns_licoes")
            self.conn.commit()