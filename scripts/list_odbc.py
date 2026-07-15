import pyodbc
import sys

def list_drivers():
    try:
        drivers = pyodbc.drivers()
        print("Available ODBC Drivers:")
        for d in drivers:
            print(f" - {d}")
    except Exception as e:
        print(f"Error listing ODBC drivers: {e}")

if __name__ == "__main__":
    list_drivers()
