"""MockProvider: proveedor de IA determinista, sin red ni costo.

Sirve para desarrollar y correr los tests automatizados sin necesitar una
ANTHROPIC_API_KEY ni gastar créditos. Usa reglas simples por palabra clave
para decidir si debe llamar una tool o responder directo. No pretende ser
inteligente — solo ejercitar el flujo completo del Orchestrator.
"""
from __future__ import annotations

import re

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolCall, ToolSchema

_APP_ALIASES = ["vscode", "vs code", "notepad", "bloc de notas", "chrome", "explorer"]


class MockProvider(AIProvider):
    def chat(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> AIResponse:
        available = {t.name for t in (tools or [])}

        # Si el último mensaje es un resultado de tool, ya no volvemos a
        # llamar una tool: generamos la respuesta final en texto.
        if messages and messages[-1].role == "tool":
            return AIResponse(text=self._final_answer(messages))

        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        text = (last_user.content if last_user else "").lower()

        if "get_current_time" in available and any(k in text for k in ["hora", "fecha"]):
            return AIResponse(tool_calls=[ToolCall(id="mock-1", name="get_current_time", arguments={})])

        if "get_system_info" in available and any(
            k in text for k in ["ram", "cpu", "memoria ram", "disco", "estado del sistema", "sistema"]
        ):
            return AIResponse(tool_calls=[ToolCall(id="mock-1", name="get_system_info", arguments={})])

        if "open_application" in available and any(k in text for k in ["abre", "abrir", "abreme"]):
            app = next((a for a in _APP_ALIASES if a in text), "notepad")
            return AIResponse(
                tool_calls=[ToolCall(id="mock-1", name="open_application", arguments={"application_name": app})]
            )

        if "search_memory" in available and ("recuerdas" in text or "recuerda" in text and "qué" in text):
            m = re.search(r"sobre (.+)", text)
            query = m.group(1).strip("? ") if m else ""
            return AIResponse(
                tool_calls=[ToolCall(id="mock-1", name="search_memory", arguments={"query": query})]
            )

        if "create_memory" in available and any(k in text for k in ["anota", "recuerda que", "guarda que"]):
            return AIResponse(
                tool_calls=[
                    ToolCall(
                        id="mock-1",
                        name="create_memory",
                        arguments={"content": last_user.content, "category": "personal"},
                    )
                ]
            )

        if "search_files" in available and "busca" in text and "archivo" in text:
            m = re.search(r"archivos? (?:que contengan |llamados? )?(.+)", text)
            query = m.group(1).strip() if m else ""
            return AIResponse(
                tool_calls=[ToolCall(id="mock-1", name="search_files", arguments={"query": query})]
            )

        if "list_files" in available and "lista" in text and "archivo" in text:
            return AIResponse(
                tool_calls=[ToolCall(id="mock-1", name="list_files", arguments={"path": "."})]
            )

        return AIResponse(text="Entendido. (respuesta simulada — configura AI_PROVIDER=anthropic para IA real)")

    def _final_answer(self, messages: list[AIMessage]) -> str:
        tool_msg = messages[-1]
        return f"Listo. Resultado de {tool_msg.name}: {tool_msg.content}"
