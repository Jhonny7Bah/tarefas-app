import flet as ft

from flet_instalador import FletInstalador


def main(page: ft.Page):
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    page.add(

                ft.Container(height=150, width=300, alignment = ft.Alignment.CENTER, bgcolor=ft.Colors.PURPLE_200, content=FletInstalador(
                    tooltip="My new FletInstalador Control tooltip",
                    value = "My new FletInstalador Flet Control",
                ),),

    )


ft.run(main)
