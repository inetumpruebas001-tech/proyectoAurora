import os
from requests.structures import CaseInsensitiveDict
from src.test.library import config_ambiente, esquema_json, multipart, resultados
import json
import configparser
from openpyxl import Workbook, load_workbook
from src.test.library.excel_reader import data
import requests
from src.test.library.word_generate import *
from src.test.library.utils import *
import xml.etree.ElementTree as ET
import time

METODOS_CON_BODY = ['POST', 'PUT', 'PATCH', 'DELETE']
CLAVES_SENSIBLES = ('authorization', 'token', 'api-key', 'apikey', 'x-api-key', 'password', 'secret', 'cookie')


def ocultar_sensibles(cabeceras):
    """Copia de las cabeceras para LOG/evidencia con los valores sensibles enmascarados.
    La petición real se envía con los valores completos."""
    try:
        items = dict(cabeceras).items()
    except (TypeError, ValueError):
        return cabeceras
    return {k: ('****' if any(c in str(k).lower() for c in CLAVES_SENSIBLES) else v) for k, v in items}


CAMPOS_SENSIBLES_RESPONSE = ('token', 'password', 'secret', 'clave')


def ocultar_json(dato):
    """Copia del response para LOG/evidencia con tokens y claves enmascarados.
    Las validaciones usan siempre el response real."""
    if isinstance(dato, dict):
        return {k: ('****' if any(c in str(k).lower() for c in CAMPOS_SENSIBLES_RESPONSE) and isinstance(v, str)
                    else ocultar_json(v)) for k, v in dato.items()}
    if isinstance(dato, list):
        return [ocultar_json(x) for x in dato]
    return dato


def _timeout():
    """service.properties -> timeout_seg (60 por defecto)."""
    config = configparser.ConfigParser()
    config.read('service.properties')
    return int(config.get('General', 'timeout_seg', fallback='60'))


def _verificar_ssl():
    """service.properties -> verify_ssl (false por defecto: ambientes QA con certificado interno)."""
    config = configparser.ConfigParser()
    config.read('service.properties')
    return config.get('General', 'verify_ssl', fallback='false').strip().lower() == 'true'


class UTIL_API:
    def __init__(self, context):
        self.context = context
        self.verify = _verificar_ssl()
        self.timeout = _timeout()
    
    def get_data(self):
        return data(self.context.excel,self.context.hoja)
    
    def get_ejecucion(self,datos):
        return self.get_data()[int(datos)-1]["Ejecucion"]

    def fila(self, datos):
        """Fila del Excel con los {{...}} resueltos (una sola vez por escenario).
        Orden: variables globales -> variables del ambiente -> dinámicas ({{hoy+30}}, {{uuid}})."""
        cache = getattr(self.context, "fila_resuelta", None)
        clave = (self.context.excel, self.context.hoja, str(datos))
        if cache and cache[0] == clave:
            return cache[1]
        cruda = self.get_data()[int(datos)-1]
        if str(cruda.get("Ejecucion", "")).upper() == "NO":
            return cruda
        globales = dict(self.context.config.userdata)
        ambiente = getattr(self.context, "variables_ambiente", {}) or {}
        resuelta, faltantes = {}, []
        for col, valor in cruda.items():
            resuelta[col], f = config_ambiente.resolver(valor, globales, ambiente)
            faltantes += [f"{col}: {{{{{n}}}}}" for n in f]
        if faltantes:
            raise AssertionError("Variables sin valor en la fila " + str(datos) + ": " + "; ".join(faltantes) +
                                 ". Defínelas en config/ambientes.json o guárdalas antes con GlobalVariables.")
        self.context.fila_resuelta = (clave, resuelta)
        return resuelta

    def lectura_excel(self,datos):
        try:
            self.context.endpoint = self.fila(datos)["Endpoint"]
            self.context.nameEscenario = self.fila(datos)["Escenario"]
            self.context.iteracion = self.fila(datos)["Iteracion"]
            self.context.nameApi = self.fila(datos)["Api"]
            self.context.aditionalHeaders = self.fila(datos)["AditionalHeaders"]
            self.context.aditionalBody = self.fila(datos)["aditionalBody"]

            if self.fila(datos)["Headers"]:
                self.context.headers_string = self.fila(datos)["Headers"]
                headers_list = self.context.headers_string.split('\n')
                # Asegurarse de que cada línea dividida tenga exactamente dos elementos
                split_headers = [header.split(': ', 1) if ': ' in header else [header, ''] for header in headers_list]
                self.context.headers = dict(split_headers)
            else:
                self.context.headers_string=''
                self.context.headers=''
            if self.fila(datos)["Params"]:
                self.context.params = dict(p.split(':', 1) for p in self.fila(datos)["Params"].split('\n') if ':' in p)
                self.context.params = {k.strip(): v.strip() for k, v in self.context.params.items()}
            else:
                self.context.params=''
            if self.fila(datos)["Body"]:
                self.context.body=self.fila(datos)["Body"]
            else:
                self.context.body=''
            if self.fila(datos)["Expected Headers Response"]:
                self.context.expected_headers= self.fila(datos)["Expected Headers Response"]
            else:
                self.context.expected_headers=''
            if self.fila(datos)["Expected Response"]:
                self.context.expected_response= self.fila(datos)["Expected Response"]
            else:
                self.context.expected_response=''
            self.context.expected_schema = self.fila(datos).get("Expected Schema", "")   # columna opcional
            self.context.request_type = self.fila(datos)["Request Type"]
            self.context.expected_status_code = self.fila(datos)["Expected Status Code"]
            self.context.expected_content = self.fila(datos)["Expected Content_1"]
            self.context.custom_message = f"Se extrae: \nEndpoint: {self.context.endpoint}"
            # Un Word por caso (Api + Iteracion). Antes era un Word por Api que se renombraba al
            # terminar cada escenario: la fila siguiente partía de un Word vacío y en Windows
            # os.rename fallaba al existir ya "<Api>-PASSED.docx" (se perdía evidencia).
            # Si el Escenario empieza con la clave de Xray (TAP-4234 - ...), el Word se llama TAP-4234
            nombre = resultados.nombre_evidencia(self.context.nameEscenario, f"{self.context.nameApi}-{self.context.iteracion}")
            self.context.rutaEvidencia = os.path.join(os.getcwd(), "Evidencias", f"{nombre}.docx")
            if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                print("[LOG] No se generará Word")
            else:
                es_nuevo = not os.path.exists(self.context.rutaEvidencia)
                self.context.xdoc= start_up_word(self.context.rutaEvidencia)
                if es_nuevo:
                    crear_tabla_inicio(self.context.xdoc,context=self.context)
        except Exception as e:            
            print(f"Ocurrio un error inesperado en lectura_excel() {e}")
            self.context.custom_message=f"Ocurrio un error inesperado en lectura_excel() {e}"
            raise AssertionError(f"Ocurrio un error inesperado en lectura_excel() {e}")

    
    def enviar_peticion(self, endpoint='', method='GET', headers='', params='', body='', anidadoB=None, anidadoH=None, log=True, logWord=True):
        aditional_headers_raw = ''
        aditional_body_raw = ''
        faltantes = []
        try:
            if not endpoint:
                endpoint = self.context.endpoint
                headers = self.context.headers
                params = self.context.params
                body = self.context.body
                method = self.context.request_type
                aditional_headers_raw = self.context.aditionalHeaders
                aditional_body_raw = self.context.aditionalBody
                print(method)

            method = str(method or 'GET').strip().upper()
            print("[LOG] Se envia la peticion")

            # Asegurar que headers sea un diccionario
            if not isinstance(headers, dict):
                headers = {}

            # Agregar headers desde AditionalHeaders si están definidos en el Excel
            try:                
                print(f"[LOG] Aditional Header {aditional_headers_raw}")
                if aditional_headers_raw and aditional_headers_raw.strip():
                    aditional_keys = [key.strip() for key in aditional_headers_raw.split(",") if key.strip()]
                    for key in aditional_keys:
                        value = self.context.config.userdata.get(key)
                        if value:
                            if key == "access_token":
                                headers["Authorization"] = f"Bearer {value}"
                                print("[LOG] Header agregado desde AditionalHeaders: Authorization = Bearer ****")
                            else:
                                headers[key] = value
                                print(f"[LOG] Header agregado desde AditionalHeaders: {key}")
                        else:
                            faltantes.append(f"AditionalHeaders:{key}")
            except Exception as e:
                raise AssertionError(f"Error al procesar AditionalHeaders: {e}") from e

            # Procesar AditionalBody si está definido en el Excel
            try:
                print(f"[LOG] Aditional Body {aditional_body_raw}")
                if aditional_body_raw and aditional_body_raw.strip():
                    if not isinstance(body, dict):
                        body = json.loads(body) if body else {}

                    aditional_body_keys = [key.strip() for key in aditional_body_raw.split(",") if key.strip()]
                    for key in aditional_body_keys:
                        value = self.context.config.userdata.get(key)
                        if value is not None:
                            body[key] = value
                            print(f"[LOG] Body agregado desde AditionalBody: {key}")
                        else:
                            faltantes.append(f"aditionalBody:{key}")
            except Exception as e:
                raise AssertionError(f"Error al procesar AditionalBody: {e}") from e

            # Antes solo se imprimía un WARN y la petición salía sin token: el fallo aparecía
            # después como un 401 difícil de entender. Ahora se detiene con un mensaje claro.
            if faltantes:
                raise AssertionError(
                    "Variables globales no encontradas: " + ", ".join(faltantes) +
                    ". Revise que un escenario anterior las guarde en la columna GlobalVariables.")

            # Agregar headers anidados si existen
            if anidadoH:
                for key, value in anidadoH.items():
                    headers[key] = value

            # Envío de la petición
            if method == 'GET':
                if body:
                    responseData = requests.get(endpoint, headers=headers, data=body, params=params, verify=self.verify, timeout=self.timeout)
                else:
                    responseData = requests.get(endpoint, headers=headers, params=params, verify=self.verify, timeout=self.timeout)

            elif method in METODOS_CON_BODY and multipart.es_multipart(headers):
                # Subida de archivos: Body = líneas 'campo: valor' / 'campo: @archivo' (ver multipart.py)
                archivos, body = multipart.preparar(body)
                responseData = requests.request(
                    method,
                    endpoint,
                    headers=multipart.sin_content_type(headers),
                    params=params,
                    files=archivos,
                    verify=self.verify,
                    timeout=self.timeout
                )

            elif method in METODOS_CON_BODY:
                if body:
                    if str(body).strip().startswith('<'):
                        responseData = requests.request(
                            method,
                            endpoint,
                            headers=headers,
                            params=params,
                            data=body,
                            verify=self.verify,
                            timeout=self.timeout
                        )
                    else:
                        if not isinstance(body, dict):
                            body = json.loads(body)
                        if anidadoB:
                            for key, value in anidadoB.items():
                                body[key] = value

                        content_type = headers.get("Content-Type", "").lower()
                        if "application/x-www-form-urlencoded" in content_type:
                            responseData = requests.request(
                                method,
                                endpoint,
                                headers=headers,
                                params=params,
                                data=body,
                                verify=self.verify,
                            timeout=self.timeout
                            )
                        else:
                            responseData = requests.request(
                                method,
                                endpoint,
                                headers=headers,
                                params=params,
                                json=body,
                                verify=self.verify,
                            timeout=self.timeout
                            )
                else:
                    responseData = requests.request(
                        method,
                        endpoint,
                        headers=headers,
                        params=params,
                        verify=self.verify,
                            timeout=self.timeout
                    )
            else:
                raise ValueError(f"Request Type no soportado: {method}. Use GET, POST, PUT, PATCH o DELETE")

            # Logging y evidencia
            if log:
                log_messages = "\n<strong>REQUEST:</strong>\n"
                log_messages += f"{method} {responseData.url}\n"
                log_messages += f"Request Headers: {pretty_print_headers(ocultar_sensibles(responseData.request.headers))}\n"
                self.context.custom_message = log_messages
                if params:
                    log_messages += f"Params: {pretty_print_headers(params)}\n"
                if body:
                    print(self.context.body)
                    if str(body).strip().startswith('<'):
                        log_messages += f"Body: {pretty_print_xml(body)}"
                        bodyWord = pretty_print_xml(body)
                    else:
                        log_messages += f"Body: {pretty_print_headers(body)}"
                        bodyWord = pretty_print_headers(body)
                else:
                    bodyWord = ""

                self.context.custom_message = log_messages
                log_messages += "\n\n<strong>RESPONSE:</strong>\n"
                log_messages += f"{responseData.request.method} - Code: {responseData.status_code} {responseData.reason}\n"
                self.context.custom_message = log_messages
                log_messages += f"Headers: {pretty_print_headers(responseData.headers)}\n"
                self.context.custom_message = log_messages
                log_messages += f"Elapsed Time: {responseData.elapsed}\n"
                if responseData.text.strip() == "":
                    log_messages += "Response Empty\n"
                    responseWord = "Response Empty"
                else:
                    if 'json' in responseData.headers.get('Content-Type', ''):
                        log_messages += f"{pretty_print_headers(ocultar_json(responseData.json()))}\n"
                        responseWord = pretty_print_headers(ocultar_json(responseData.json()))
                    elif "text/xml" in responseData.headers.get('Content-Type', ''):
                        log_messages += f"{pretty_print_xml2(responseData.text)}\n"
                        responseWord = pretty_print_xml2(responseData.text)
                    else:
                        log_messages += f"{responseData.text}\n"
                        responseWord = responseData.text

                self.context.custom_message = log_messages
                if hasattr(self.context, 'evidence_path') and self.context.tipoWord != "Individual":
                    print("[LOG] No se generará Word")
                else:
                    if logWord:
                        header_formateado = json.dumps(ocultar_sensibles(headers), indent=4)
                        crear_tabla_response(self.context.xdoc, self.context.iteracion, self.context.nameEscenario, method, endpoint, str(responseData.status_code), responseData.reason, str(header_formateado), bodyWord, responseWord, str(responseData.elapsed))
                        guardarWord(self.context.xdoc, self.context.rutaEvidencia)

            return responseData

        except Exception as e:
            print("[LOG] Error realizar la peticion:", e)
            self.context.custom_message = f"Error realizar la peticion:{e}{self.context.custom_message}"
            raise AssertionError(f"Error al realizar la peticion: {e}") from e


    def validacion_status_code(self,responseData):
        try:
            self.context.custom_message =""
            print("[LOG] Se valida el status Code")
            print(f"Expected Status Code: {self.context.expected_status_code}")
            print(f"Actual Status Code: {responseData.status_code}")
            log_messages = ""
            log_messages += "[LOG] Se valida el status Code\n"
            log_messages += f"Expected Status Code: {self.context.expected_status_code}\n"
            log_messages += f"Actual Status Code: {responseData.status_code}\n"
            self.context.custom_message = log_messages
            assert str(responseData.status_code) == str(self.context.expected_status_code)
            if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                print("[LOG] No se generará Word")
            else:
                crear_tabla_validacion(self.context.xdoc,self.context.iteracion,"PASSED",str(self.context.expected_status_code),str(responseData.status_code))
                guardarWord(self.context.xdoc,self.context.rutaEvidencia)
            
                
        except Exception as e:
            if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                print("[LOG] No se generará Word")
            else:
                crear_tabla_validacion(self.context.xdoc,self.context.iteracion,"FAILED",str(self.context.expected_status_code),str(responseData.status_code))
                guardarWord(self.context.xdoc,self.context.rutaEvidencia)
            print("[LOG] Error al validar el estado del response")
            log_messages += f"\nError al validar el estado del response:{e}"
            self.context.custom_message = log_messages
            raise AssertionError("[LOG] Error al validar el estado del response")

    def validacion_texto_response(self,responseData,datos):
        try:
            self.context.custom_message =""
            validacion=" "
            print("[LOG] Se valida el contenido del response")
            log_messages = ""
            if self.fila(datos)["Expected Content_1"]:
                log_messages += "\n[LOG] Se valida el contenido del response\n\n"
                if 'json' in responseData.headers.get('Content-Type', ''):
                    actual_content = pretty_print_headers(ocultar_json(responseData.json()))
                elif 'text/xml' in responseData.headers.get('Content-Type', ''):
                    actual_content = responseData.text
                print(f"Actual Content: {actual_content}")
                log_messages += f"<strong>Actual Content:</strong> {actual_content}\n\n\n" 
                for i in range(1, 7, 1):
                    vString=f"Expected Content_{i}"
                    print(vString)
                    if self.fila(datos)[vString]:
                        self.context.expected_content= self.fila(datos)[vString]
                        print(f"Expected Content: {self.context.expected_content}")
                        log_messages += f"Expected Content {i}: {self.context.expected_content}\n"
                        texto_busqueda = responseData.text + "\n" + json.dumps(responseData.json(), ensure_ascii=False, indent=4)
                        if self.context.expected_content in texto_busqueda:
                            log_messages+="<strong>PASSED</strong>\n\n"
                            validacion+="PASSED "
                            if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                                print("[LOG] No se generará Word")
                            else:
                                crear_tabla_validacion(self.context.xdoc,self.context.iteracion,"FOUND",str(self.context.expected_content),title="Validación de texto del Response")
                                guardarWord(self.context.xdoc,self.context.rutaEvidencia)
                        else:
                            log_messages+="<strong>FAILED</strong>\n\n"
                            validacion+="FAILED "
                            if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                                print("[LOG] No se generará Word")
                            else:
                                crear_tabla_validacion(self.context.xdoc,self.context.iteracion,"NOT FOUND",str(self.context.expected_content),title="Validación de texto del Response")
                                guardarWord(self.context.xdoc,self.context.rutaEvidencia)
                    else:
                        break    
                if validacion != " ":
                    print(validacion)
                    assert "FAILED" not in validacion
                    print("[LOG] Se realizo la validación del contenido correctamente!")
            else:
                log_messages="No hay validaciones"                
            
            self.context.custom_message = log_messages
        except Exception as e:
                self.context.custom_message =f"Error al validar el contenido del response:{log_messages}{e}"
                print("[LOG] Error al validar el contenido del response")
                raise AssertionError("[LOG] Error al validar el contenido del response")


    def guardar_variables_response(self, responseData, datos):
        try:
            print("[LOG] Se inicia el guardado de variables globales")

            global_vars_raw = self.fila(datos).get("GlobalVariables", "")
            if not global_vars_raw:
                print("[LOG] No se encontraron variables globales para guardar")
                return
            # Verifica que el response sea JSON
            if 'json' not in responseData.headers.get('Content-Type', ''):
                raise AssertionError("El response no es JSON: no se pueden extraer las variables de GlobalVariables")
            json_data = responseData.json()

            # Formatos: "id" (se guarda como id), "cotizacionId=id" (alias), "token=data.auth.token" (ruta)
            global_vars = [var.strip() for var in global_vars_raw.split(",") if var.strip()]
            no_encontradas = []
            for var in global_vars:
                alias, ruta = (p.strip() for p in var.split("=", 1)) if "=" in var else (var, var)
                value = valor_en_ruta(json_data, ruta)
                if value is not None:
                    self.context.config.userdata[alias] = value
                    print(f"[LOG] Variable global guardada: {alias}")  # el valor puede ser un token: no se imprime
                else:
                    no_encontradas.append(ruta)
            if no_encontradas:
                # Antes solo era un WARN: los escenarios siguientes fallaban sin token y sin pista
                raise AssertionError(f"Variables no encontradas en el response: {', '.join(no_encontradas)}")

        except Exception as e:
            print(f"[ERROR] Error al guardar variables globales: {e}")
            raise AssertionError(f"Error al guardar variables globales: {e}") from e

    def validacion_header_response(self,reponseData):
        try:
            print("[LOG] Se valida los Headers Response")
            if self.context.expected_headers:
                actual_headers_response = reponseData.headers
 
                # Convertir los encabezados esperados y reales a diccionarios
                expected_headers_dict = json.loads(self.context.expected_headers)
                actual_headers_dict = CaseInsensitiveDict(actual_headers_response)
    
                # Convertir los diccionarios a cadenas formateadas para la comparación
                expected_headers_str = json.dumps(expected_headers_dict, indent=4)
                actual_headers_str = json.dumps(dict(actual_headers_dict), indent=4)
    
                print(f"Expected Headers Response: {expected_headers_str}")
                print(f"Actual Headers Response: {actual_headers_str}")
                log_messages = ""
                log_messages += "[LOG] Se valida los Headers Response\n"
                log_messages += f"Expected Headers Response: {expected_headers_str}\n"
                log_messages += f"Actual Headers Response: {actual_headers_str}\n\n"
                self.context.custom_message = log_messages
                contador=0
                validacion=" "
                # Validar que los encabezados esperados estén en los encabezados reales, omitiendo Content-Length y Date
                for key, value in expected_headers_dict.items():
                    contador+=1
                    log_messages+=f"<strong>Validacion Header {contador}</strong>\n"
                    log_messages+=f"Header Esperado: {key}\n"
                    if key in actual_headers_dict:
                        log_messages+=f'<span style="color: green;"><strong>PASSED</strong></span>'
                        validacion+="PASSED "
                        if value!="*":
                            log_messages+=f"\nValor Esperado: {value}\n"
                            log_messages+=f"Valor Obtenido: {actual_headers_dict[key]}\n"
                            if actual_headers_dict[key]==value:
                                log_messages+=f'<span style="color: green;"><strong>PASSED</strong></span>\n\n'
                                validacion+="PASSED "
                            else:
                                log_messages+=f'<span style="color: red;"><strong>FAILED</strong></span>\n\n'
                                validacion+="FAILED "
                        else:
                            log_messages+="\nSolo se valida la existencia del header\n\n"
                    else:
                        validacion+="FAILED "
                        log_messages+=f'<span style="color: red;"><strong>FAILED</strong></span> - No existe el header en el response\n\n'
                        #assert key in actual_headers_dict and actual_headers_dict[key] == value
                self.context.custom_message = log_messages
                if validacion != " ":
                    print(validacion)
                    assert "FAILED" not in validacion
                    print("[LOG] Se realizo la validación del contenido correctamente!")
                    if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                        print("[LOG] No se generará Word")
                    else:
                        crear_tabla_validacion_header(self.context.xdoc, expected_headers_str, actual_headers_str, "PASSED")
                        guardarWord(self.context.xdoc, self.context.rutaEvidencia)
            else:
                log_messages="No hay validaciones"
                self.context.custom_message = log_messages
        except Exception as e:
            if hasattr(self.context,'evidence_path') and self.context.tipoWord!="Individual":
                print("[LOG] No se generará Word")
            else:
                crear_tabla_validacion_header(self.context.xdoc, expected_headers_str, actual_headers_str, "FAILED")
                guardarWord(self.context.xdoc, self.context.rutaEvidencia)
            print("[LOG] Error al validar los headers del response")
            log_messages += f"\nError al validar los headers del response: {e}"
            self.context.custom_message = log_messages
            raise AssertionError("[LOG] Error al validar los headers del response")
    
    def validacion_estructura_response(self,reponseData):
        try:
            print("[LOG] Se valida la estructura del Response")
            if self.context.expected_response:
                actual_response = reponseData.text
 
                # Convertir los encabezados esperados y reales a diccionarios
                expected_response_dict = json.loads(self.context.expected_response)
                actual_response_dict = json.loads(actual_response)
                # Convertir los diccionarios a cadenas formateadas para la comparación
                # expected_reponse_str = json.dumps(expected_response_dict, indent=4, ensure_ascii=False)
                # actual_response_str = json.dumps(actual_response_dict, indent=4, ensure_ascii=False)
                log_messages = ""
                log_messages += "[LOG] Se valida la estructura del Response\n"
                if (len(str(actual_response_dict))<10000):
                    #log_messages += f"Expected Response: {pretty_print_headers(expected_response_dict)}\n"
                    log_messages += f"Actual Response: {pretty_print_headers(ocultar_json(actual_response_dict))}\n\n"
                self.context.custom_message = log_messages
                contador=0
                validacion=" "
                log_messages=""
                log_messages=validate_keys_and_values(self.context,expected_response_dict,actual_response_dict,log=log_messages)
                self.context.custom_message += log_messages
                assert "FAILED" not in log_messages
            else:
                log_messages="No hay validaciones"
        except Exception as e:
            #crear_tabla_validacion_header(self.context.xdoc, expected_headers_str, actual_headers_str, "FAILED")
            #guardarWord(self.context.xdoc, self.context.rutaEvidencia)
            differences = highlight_differences(self.context.expected_response, pretty_print_headers(reponseData.json()))
            log_messages += f"Differences:\n{differences}\n"
            print("[LOG] Error al validar la estructura del response")
            log_messages += f"\n Error al validar la estructura del response: {e}"
            self.context.custom_message = log_messages
            raise AssertionError("[LOG] Error al validar la estructura del response")
        self.validacion_schema_response(reponseData)

    def validacion_schema_response(self, reponseData):
        """Columna opcional 'Expected Schema': valida TODO el response contra un JSON Schema
        (en línea, archivo de data/schemas o parte de un contrato OpenAPI)."""
        valor = getattr(self.context, "expected_schema", "")
        if not valor:
            return
        print("[LOG] Se valida el response contra el JSON Schema")
        previo = self.context.custom_message if self.context.custom_message not in (None, "-") else ""
        try:
            schema = esquema_json.cargar(valor)
            try:
                dato = reponseData.json()
            except ValueError as e:
                raise esquema_json.ErrorSchema("El response no es JSON: no se puede validar contra el schema") from e
            errores = esquema_json.validar(schema, dato)
        except esquema_json.ErrorSchema as e:
            self.context.custom_message = previo + f"\nJSON Schema ({valor}): {e}"
            raise AssertionError(f"[LOG] Error al validar el JSON Schema del response: {e}") from e
        if errores:
            self.context.custom_message = previo + f"\nJSON Schema ({valor}): FAILED\n" + "\n".join(errores)
            raise AssertionError("[LOG] El response no cumple el JSON Schema: " + "; ".join(errores[:3]))
        self.context.custom_message = previo + f"\nJSON Schema ({valor}): PASSED"


def valor_en_ruta(dato, ruta):
    """Valor en una ruta con puntos: 'id', 'data.token', 'items.0.id'. None si no existe."""
    actual = dato
    for parte in str(ruta).split("."):
        if isinstance(actual, dict) and parte in actual:
            actual = actual[parte]
        elif isinstance(actual, list) and parte.isdigit() and int(parte) < len(actual):
            actual = actual[int(parte)]
        else:
            return None
    return actual


def _registrar(context, estado, esperado, obtenido="", titulo="Valor"):
    if hasattr(context, 'evidence_path') and context.tipoWord != "Individual":
        return
    if obtenido == "":
        crear_tabla_validacion(context.xdoc, context.iteracion, estado, str(esperado), title=titulo)
    else:
        crear_tabla_validacion(context.xdoc, context.iteracion, estado, str(esperado), str(obtenido), title=titulo)
    guardarWord(context.xdoc, context.rutaEvidencia)


def _comparar_lista(context, expected, actual, ruta, log):
    """Listas: cada elemento esperado se compara con el de la misma posición.
    Si el esperado es ["*"], solo se valida que sea una lista."""
    if not isinstance(actual, list):
        log += f'\n{ruta}: se esperaba una lista y se obtuvo {type(actual).__name__}\n<span style="color: red;"><strong>FAILED</strong></span>\n'
        _registrar(context, "FAILED", f"{ruta} (lista)", type(actual).__name__)
        return log
    if expected == ["*"]:
        return log + f"\n{ruta}: es una lista ({len(actual)} elementos)\n"
    if len(actual) < len(expected):
        log += f'\n{ruta}: se esperaban al menos {len(expected)} elementos y hay {len(actual)}\n<span style="color: red;"><strong>FAILED</strong></span>\n'
        _registrar(context, "FAILED", f"{ruta} ({len(expected)} elementos)", len(actual))
        return log
    for i, item in enumerate(expected):
        sub = f"{ruta}[{i}]"
        if isinstance(item, dict):
            log = validate_keys_and_values(context, item, actual[i], sub, log=log)
        elif isinstance(item, list):
            log = _comparar_lista(context, item, actual[i], sub, log)
        elif item != "*":
            ok = item == actual[i]
            log += f"\n{sub}: esperado {item} / obtenido {actual[i]}\n" + \
                   ('<span style="color: green;"><strong>PASSED</strong></span>\n' if ok else '<span style="color: red;"><strong>FAILED</strong></span>\n')
            _registrar(context, "PASSED" if ok else "FAILED", item, actual[i])
    return log


def validate_keys_and_values(context,expected, actual, parent_key='',log=''):
    if isinstance(expected, list):  # el response completo es una lista (p. ej. catálogos)
        return _comparar_lista(context, expected, actual, parent_key or "response", log)
    for key in expected:
        log+=f"\nLlave esperada: {str(key)}\n"
        full_key = f"{parent_key}.{key}" if parent_key else key
        if key in actual:
            log+=f'<span style="color: green;"><strong>PASSED</strong></span>\n'
            if hasattr(context,'evidence_path') and context.tipoWord!="Individual":
                print("[LOG] No se generará Word")
            else:
                crear_tabla_validacion(context.xdoc,context.iteracion,"FOUND",str(key),title="Llaves")
                guardarWord(context.xdoc,context.rutaEvidencia)
            if isinstance(expected[key], dict):
                log=validate_keys_and_values(context,expected[key], actual[key], full_key,log=log)
            elif isinstance(expected[key], list):
                log=_comparar_lista(context, expected[key], actual[key], full_key, log)
            else:
                if expected[key]!="*":
                    log+=f"Valor esperado: {str(expected[key])}\n"
                    log+=f"Valor Obtenido: {str(actual[key])}\n"
                    if expected[key] == actual[key]:
                        log+=f'<span style="color: green;"><strong>PASSED</strong></span>\n'
                        if hasattr(context,'evidence_path') and context.tipoWord!="Individual":
                            print("[LOG] No se generará Word")
                        else:
                            crear_tabla_validacion(context.xdoc,context.iteracion,"PASSED",str(expected[key]),str(actual[key]),title="Valor")
                            guardarWord(context.xdoc,context.rutaEvidencia)
                    else:
                        log+=f'<span style="color: red;"><strong>FAILED</strong></span>\n'
                        if hasattr(context,'evidence_path') and context.tipoWord!="Individual":
                            print("[LOG] No se generará Word")
                        else:
                            crear_tabla_validacion(context.xdoc,context.iteracion,"FAILED",str(expected[key]),str(actual[key]),title="Valor")
                            guardarWord(context.xdoc,context.rutaEvidencia)
                else:
                    log+="Solo se valida la existencia de la llave\n\n"
        else:
            log+=f'<span style="color: red;"><strong>FAILED</strong></span> - No existe la llave en el response\n\n'
            if hasattr(context,'evidence_path') and context.tipoWord!="Individual":
                print("[LOG] No se generará Word")
            else:
                crear_tabla_validacion(context.xdoc,context.iteracion,"NOT FOUND",str(key),title="Llaves")
                guardarWord(context.xdoc,context.rutaEvidencia)
            print(f"Clave faltante en actual_response: {full_key}")
    return log