"""Check connectivity to the configured PostgreSQL database."""

from app.database import test_database_connection


if __name__ == "__main__":
    test_database_connection()
    print("PostgreSQL connection successful")
