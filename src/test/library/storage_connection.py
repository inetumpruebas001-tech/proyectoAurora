from datetime import datetime
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureNamedKeyCredential
from azure.keyvault.secrets import SecretClient
from azure.data.tables import TableServiceClient
from azure.data.tables import TableEntity
from src.test.library.variables import *
from azure.core.pipeline.transport import RequestsTransport
import requests

def get_key_secrets():
    """Lee la clave del Storage desde Azure Key Vault con la identidad del usuario/pipeline."""
    KVUri = f"https://{key_vault_name}.vault.azure.net"
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=KVUri, credential=credential)
    retrieved_account_key = client.get_secret(secret_storage_account_key)
    return account_name, retrieved_account_key.value, table_name


def _obtener_account_key():
    """Prioridad: variable de entorno AZURE_STORAGE_ACCOUNT_KEY -> Key Vault."""
    if account_key:
        return account_key
    _, clave, _ = get_key_secrets()
    return clave


def get_table_client():
    try:
        credential = AzureNamedKeyCredential(name=account_name, key=_obtener_account_key())

        # TLS verificado. Con proxy corporativo: REQUESTS_CA_BUNDLE con su certificado.
        session = requests.Session()
        transport = RequestsTransport(session=session)

        service_client = TableServiceClient(
            endpoint=f"https://{account_name}.table.core.windows.net",
            credential=credential,
            transport=transport
        )
        table_client = service_client.get_table_client(table_name=table_name)
        print("Connection to Azure Table Storage established")
    except Exception as e:
        print(f"Error creating table client: {e}")
        raise

    return table_client

def save_to_table(context, scenario):
    try:
        table_client = context.table_client
        scenario_name = context.nameEscenario # Diferente a web
        fecha = datetime.now().strftime("%Y-%m-%d")
        hora = datetime.now().strftime("%H:%M:%S")
        framework = "Servicios"
        hostname = context.hostname
        partition_key = "TestResults"
        row_key = str(datetime.now().timestamp()).replace('.', '')

        # Datos a guardar en la tabla
        row_data = TableEntity()
        row_data['PartitionKey'] = partition_key
        row_data['RowKey'] = row_key
        row_data['Escenario'] = scenario_name
        row_data['Fecha'] = fecha
        row_data['Hora'] = hora
        row_data['Duracion'] = context.timer.total_seconds()
        row_data['Estado'] = context.estado
        row_data['Framework'] = framework
        row_data['Hostname'] = hostname
        row_data['Proyecto'] = context.proyecto
        row_data['Ambiente'] = getattr(context, 'variables_ambiente', {}).get('ambiente', '')

        print(f"Row data to insert: {row_data}")

        # Insertar los datos en la tabla
        table_client.create_entity(entity=row_data)
        print("Data inserted successfully")
    except Exception as e:
        print(f"Error al conectar o ejecutar la consulta en la base de datos: {e}")
        raise