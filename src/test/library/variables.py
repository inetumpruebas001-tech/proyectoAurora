import os

# Usar os.path.join para construir las rutas de manera que sean compatibles con cualquier sistema operativo
html_features_template = os.path.join(os.getcwd(), "src", "test", "resources", "template", "overview-features.html")
html_for_each_feature_template = os.path.join(os.getcwd(), "src", "test", "resources", "template", "report-feature.html")
report_folder_path = os.path.join(os.getcwd(), "src", "test", "reports")
template_folder_path = os.path.join(os.getcwd(), "src", "test", "resources", "template")
source_files = ["logo.png", "main.js", "style.css", "icon.ico"]
word_path1 = os.path.join(os.getcwd(), "Evidencias")


# Azure (opcional, solo si service.properties -> log=true). Nada de esto va escrito en el código:
# se configura con variables de entorno (en el pipeline, un grupo de variables vinculado a Key Vault).
account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME', '')        # cuenta de Storage
table_name = os.environ.get('AZURE_TABLE_NAME', 'ResultadosAutomatizacion')
key_vault_name = os.environ.get('AZURE_KEY_VAULT_NAME', '')            # Key Vault con la clave del Storage
secret_storage_account_key = os.environ.get('AZURE_KEY_VAULT_SECRET', 'storage-account-key')
account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY', '')
