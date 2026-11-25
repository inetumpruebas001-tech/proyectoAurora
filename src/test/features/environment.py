import json
import os
import re
import configparser
from datetime import datetime
from src.test.library.utils import *
from src.test.library.variables import *
from src.test.library.excel_reader import data
import src.test.library.word_generate as generateWord
from datetime import datetime
from src.test.library.util_api import UTIL_API
from behave.model_core import Status
from src.test.library.storage_connection import *
from src.test.library import config_ambiente, resultados

def before_all(context):
    context.step_messages = []
    context.newNames = []
    resultados.iniciar(context)
    context.start_time=datetime.now()
    context.hostname=os.environ.get('COMPUTERNAME','')
    formato = "%d %b %Y, %H:%M"
    context.fecha_formateada = context.start_time.strftime(formato)
    # Configuración de la conexión a la base de datos
    config = configparser.ConfigParser()
    config.read('service.properties')
    # En el pipeline se sobrescriben con variables de entorno (LOG_TABLA, PROYECTO, CICLO)
    context.log = os.environ.get('LOG_TABLA') or config.get('General', 'log')
    context.proyecto = os.environ.get('PROYECTO') or config.get('General','Proyecto')
    context.ciclo = os.environ.get('CICLO') or config.get('General','Ciclo')
    context.tipoWord = config.get('General','Word')
    log = context.log
    if log.lower()=='true':
        context.table_client = get_table_client()

    # Ambiente (config/ambientes.json): bloqueo de ambientes protegidos y "despertar" del servicio
    context.error_ambiente = False
    if not context.config.dry_run:
        try:
            context.variables_ambiente = config_ambiente.cargar_ambiente()
            config_ambiente.validar_permitido(context.variables_ambiente)
            print(f"[LOG] Ambiente: {context.variables_ambiente['ambiente']} -> {context.variables_ambiente['baseUrl']}")
            config_ambiente.despertar(context.variables_ambiente)
        except config_ambiente.ErrorAmbiente as e:
            context.error_ambiente = True   # after_all no arma reportes vacíos
            print(f"[ERROR] {e}")
            raise
    else:
        context.variables_ambiente = {}

def after_all(context):
    resultados.guardar(context, getattr(context, 'variables_ambiente', {}).get('ambiente', ''))
    if getattr(context, 'error_ambiente', False):
        print("[LOG] No se generan reportes: la ejecución se detuvo antes de empezar (ver [ERROR] arriba)")
        return
    if not hasattr(context, 'evidence_path'):
        data_json_path= os.path.join(os.getcwd(), "json.pretty.output")

        with open(data_json_path, "a") as json_file:
            json_file.write("]") 
        
        with open(data_json_path, 'r') as file:
            data = json.load(file)

        # Modificar los nombres de los steps en el JSON
        modified_data = modify_json_with_message(data, context.step_messages,context.newNames)

        # Sobrescribir el archivo JSON con los cambios
        data_json_path = os.path.join(os.getcwd(), "New.pretty.output")

        with open(data_json_path, 'w') as file:
            json.dump(modified_data, file, indent=4)

        # Generate the HTML report
        data_json_path= os.path.join(os.getcwd(), "New.pretty.output")
        data = process_data_json(data_json_path)
        total_scenarios, total_steps, scenarios_information= count_total_scenarios_and_steps(data)
        report_folder = create_report_folder(template_folder_path, report_folder_path, source_files,word_path1)

        generate_html_for_all_features(html_features_template, report_folder, data, total_scenarios, total_steps, scenarios_information)
        generate_html_for_each_feature(html_for_each_feature_template, report_folder, data)
    
        # Convertir archivo json en formato junit xml para integración con Azure DevOps
        json_to_junit('json.pretty.output', 'output.xml')
        if os.path.exists(word_path1):
            shutil.rmtree(word_path1)
            print(f"La carpeta '{word_path1}' ha sido borrada.")
        else:
            print(f"La carpeta '{word_path1}' no existe.")
    else:
        print("[LOG] EJECUCION PARALELA")


def before_feature(context, feature):
    """
    Hook to execute before each feature.
    """


def after_feature(context, feature):
    """
    Hook to execute after each feature.
    """


def before_scenario(context, scenario):
    context.start_time=datetime.now()
    context.state=None

    
def _registrar_caso(context, scenario):
    """Un registro por fila del Excel ejecutada (Xray y paquete de evidencias: tools/xray)."""
    if not hasattr(context, 'datos'):
        return
    ruta = getattr(context, 'rutaEvidencia', '')
    resultados.registrar(context, scenario, getattr(context, 'nameEscenario', scenario.name),
                         os.path.basename(ruta)[:-5] if ruta else "",
                         excel=getattr(context, 'excel', ''), hoja=getattr(context, 'hoja', ''), datos=context.datos)


def after_scenario(context, scenario):
    _registrar_caso(context, scenario)

    if context.state is not None:
        scenario.set_status("skipped")
        scenario_NewName = {
            'scenario_name': scenario.name,
            'scenario_new_name': "Escenario Skipeado"
        }
        context.newNames.append(scenario_NewName)
    else:
        if context.tipoWord=="Individual":
            generateWord.set_status_scenario(scenario.status.name,context)
        # Guardar los resultados del escenario en la base de datos  
        log = context.log
        if log.lower()=='true':     
            try:
                context.end_time = datetime.now()
                context.timer = context.end_time - context.start_time
                context.estado = str(scenario.status).split('.')[-1].capitalize()

                save_to_table(context, scenario)
            except Exception as e:
                print(f"Error al guardar datos del escenario en la base de datos: {e}")


        if hasattr(context, 'nameEscenario'):
            scenario_NewName = {
                'scenario_name': scenario.name,
                'scenario_new_name': context.nameEscenario
            }
            context.newNames.append(scenario_NewName)
            scenario.name=context.nameEscenario
    

def before_step(context, step):
    """
    Hook to execute before each step.
    """

def after_step(context, step):
    # getattr: si el Given falla antes de leer el Excel, context.ejecutar no existe
    if getattr(context, 'ejecutar', 'SI') == "NO":
        context.custom_message = "NO-EXECUTED"
        step.status = Status.skipped

    if hasattr(context, 'custom_message'):
        step_message = {
            'scenario_name': getattr(context, 'nameEscenario', ''),
            'step_name': step.name,
            'message': context.custom_message
        }
        context.step_messages.append(step_message)
        step.text=context.custom_message

    if step.status == "failed":
        # You can add code here to handle step failures
        print(f"Step failed: {step.name}")