import requests
from behave import given, when, then
from src.test.library.excel_reader import data
import json
import urllib3
from src.test.library.word_generate import *
from src.test.library.utils import *
from src.test.library.util_api import UTIL_API
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import re

@given('se extrae los datos del servicio del excel "{datos}"')
def step_given_api_endpoint(context,datos):
    context.excel = get_tag_value(context.tags, "xc-") + ".xlsx"
    context.hoja = get_tag_value(context.tags, "pg-")
    context.datos = str(datos)   # fila del Excel: identifica el caso al publicar en Xray
    # context.excel="test_data.xlsx"
    # context.hoja="Hoja1"
    context.utilapi= UTIL_API(context)
    context.ejecutar =context.utilapi.get_ejecucion(datos)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    context.custom_message ="-"
    if context.ejecutar=="SI":
        context.state=None
        context.utilapi.lectura_excel(datos)
    else:
        context.state="NO-EXECUTED"
        context.custom_message = "NO-EXECUTED"     
      

@when('cuando envio una peticion al servicio "{datos}"')
def step_when_send_request(context,datos):
        context.utilapi= UTIL_API(context)
        context.custom_message ="-"
        if context.ejecutar=="SI":
            context.response=context.utilapi.enviar_peticion()
        else:
            context.state="NO-EXECUTED"
            context.custom_message = "NO-EXECUTED"  

@then('se valida el status code obtenido con el status code esperado "{datos}"')
def step_then_response_status_code(context,datos):
    context.custom_message ="-"
    context.utilapi= UTIL_API(context)
    if context.ejecutar=="SI":
        context.utilapi.validacion_status_code(context.response)
    else:
        context.state="NO-EXECUTED"
        context.custom_message = "NO-EXECUTED"

@then('se valida el response obtenido con el response esperado "{datos}"')
def step_then_response_contains_expected_content(context,datos):
    context.custom_message ="-"
    context.utilapi= UTIL_API(context)
    if context.ejecutar=="SI":
        context.utilapi.validacion_texto_response(context.response,datos)
    else:
        context.state="NO-EXECUTED"
        context.custom_message = "NO-EXECUTED"


@then('se guarda como globales las variables del response "{datos}"')
def step_then_response_contains_expected_content(context,datos):
    context.custom_message ="-"
    context.utilapi= UTIL_API(context)
    if context.ejecutar=="SI":
        context.utilapi.guardar_variables_response(context.response,datos)
    else:
        context.state="NO-EXECUTED"
        context.custom_message = "NO-EXECUTED"

@when('se muestran todas las variables globales guardadas')
def step_mostrar_variables_globales(context):
    if getattr(context, 'ejecutar', 'SI') != "SI":
        return
    print("\n[LOG] Variables globales guardadas:")
    if context.config.userdata:
        for key in context.config.userdata:
            print(f"  {key}: ****")  # solo el nombre: los valores suelen ser tokens
    else:
        print("[LOG] No hay variables globales guardadas.")

    
@then('se valida los headers del response obtenido con los headers esperados "{datos}"')
def step_then_response_contains_expected_content(context,datos):
    context.custom_message ="-"
    context.utilapi= UTIL_API(context)
    if context.ejecutar=="SI":
        context.utilapi.validacion_header_response(context.response)
    else:
        context.state="NO-EXECUTED"
        context.custom_message = "NO-EXECUTED"
        context.midato = "1233"

@then('se valida la estructura del response obtenido con el response esperado "{datos}"')
def step_then_response_contains_expected_content(context,datos):
    context.custom_message ="-"
    context.utilapi= UTIL_API(context)
    if context.ejecutar=="SI":
        context.utilapi.validacion_estructura_response(context.response)
    else:
        context.state="NO-EXECUTED"
        context.custom_message = "NO-EXECUTED"
