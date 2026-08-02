"""Serviço Flet que abre um arquivo com o aplicativo padrão do sistema.

No Android, abrir um .apk dispara o instalador de pacotes: é o que
permite a atualização do app por dentro dele, sem navegador. O lado
nativo usa o plugin open_filex, que resolve o FileProvider sozinho.
"""

import flet as ft

__all__ = ["FletInstalador"]


@ft.control("FletInstalador")
class FletInstalador(ft.Service):
    """Abre arquivos com o app do sistema (APK dispara o instalador)."""

    async def abrir(self, caminho: str) -> str:
        """Abre ``caminho``; retorna o resultado do open_filex.

        Resultados possíveis: ``done`` (sucesso), ``fileNotFound``,
        ``noAppToOpen``, ``permissionDenied`` e ``error``.
        """
        return await self._invoke_method("abrir", {"caminho": caminho})
