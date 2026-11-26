import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
import os

load_dotenv()

url= os.getenv("DATABASE_URL")
url_vector = os.getenv("URL_VECTOR")

conexion_memoria = psycopg.connect(url, autocommit=True, row_factory=dict_row)
conexion = psycopg.connect(url, autocommit=True, row_factory=dict_row)