"""Utilidad manual para borrar un registro del log de ejecuciones en Azure Table Storage.

Uso (desde la raíz del proyecto, con AZURE_STORAGE_ACCOUNT_KEY definida o acceso al Key Vault):
    python -m src.test.library.eliminarlog <partition_key> <row_key>
"""
import sys

from src.test.library.storage_connection import get_table_client


def delete_log(table_client, partition_key, row_key):
    table_client.delete_entity(partition_key=partition_key, row_key=row_key)
    print(f"El registro {partition_key},{row_key} se ha eliminado")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    delete_log(get_table_client(), sys.argv[1], sys.argv[2])
