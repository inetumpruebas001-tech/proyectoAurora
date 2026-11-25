# Escenario de ejemplo: muestra la estructura. Los escenarios de cada historia los crea el QE
# con Copilot (/de-historia-a-automatizacion) en su propio .feature y su propio Excel.
Feature: Ejemplo - la API está disponible

  Datos en src/test/resources/data/excel/plantilla_api.xlsx, hoja Ejemplo (la hoja Leeme explica cada columna).
  Ejecutar:  $env:AMBIENTE="dev"; .\venv\Scripts\python.exe -m behave --tags=@Ejemplo

  @Ejemplo @xc-plantilla_api @pg-Ejemplo
  Scenario Outline: Estado de la API "<datos>"
    Given se extrae los datos del servicio del excel "<datos>"
    When cuando envio una peticion al servicio "<datos>"
    Then se valida el status code obtenido con el status code esperado "<datos>"
    And se valida la estructura del response obtenido con el response esperado "<datos>"
    And se valida el response obtenido con el response esperado "<datos>"
    And se valida los headers del response obtenido con los headers esperados "<datos>"

    Examples:
      | datos |
      |     1 |
