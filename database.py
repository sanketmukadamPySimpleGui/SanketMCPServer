import logging
import os
import random
import sqlite3
from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any, Dict, List

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    from bson import ObjectId
    import certifi
    PYMONGO_INSTALLED = True
except ImportError:
    PYMONGO_INSTALLED = False


class DatabaseConnector(ABC):
    """Abstract base class for all database connectors."""

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the database."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""
        pass

    @abstractmethod
    def list_tables(self) -> List[str]:
        """List all tables in the database."""
        pass

    @abstractmethod
    def get_table_schema(self, collection_name: str) -> str:
        """Get the schema of a specific table or collection."""
        pass

    @abstractmethod
    def run_sql_query(self, sql_query: str) -> dict[str, Any]:
        """Run a read-only SQL query."""
        pass

    @abstractmethod
    def find_documents(self, collection_name: str, filter: dict, projection: dict | None = None, limit: int = 50) -> dict[str, Any]:
        """Find documents in a NoSQL collection."""
        pass


class SQLiteInMemoryConnector(DatabaseConnector):
    """A connector for an in-memory SQLite database, perfect for a PoC."""

    def __init__(self) -> None:
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Creates and populates the in-memory SQLite database."""
        logging.info("Setting up in-memory SQLite database...")
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._populate_sample_data()
        logging.info("✅ In-memory SQLite database created and populated.")

    def disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            logging.info("In-memory SQLite database connection closed.")

    def _populate_sample_data(self) -> None:
        if not self.connection:
            return

        cur = self.connection.cursor()

        # Create Supply Chain Schema
        cur.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL)")
        cur.execute("CREATE TABLE suppliers (id INTEGER PRIMARY KEY, name TEXT, contact_person TEXT, phone TEXT)")
        cur.execute("CREATE TABLE warehouses (id INTEGER PRIMARY KEY, name TEXT, location TEXT)")
        cur.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY, product_id INTEGER, warehouse_id INTEGER, quantity INTEGER, reorder_level INTEGER, FOREIGN KEY(product_id) REFERENCES products(id), FOREIGN KEY(warehouse_id) REFERENCES warehouses(id))")
        cur.execute("CREATE TABLE purchase_orders (id INTEGER PRIMARY KEY, supplier_id INTEGER, order_date TEXT, expected_delivery_date TEXT, status TEXT, FOREIGN KEY(supplier_id) REFERENCES suppliers(id))")
        cur.execute("CREATE TABLE purchase_order_items (id INTEGER PRIMARY KEY, po_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price REAL, FOREIGN KEY(po_id) REFERENCES purchase_orders(id), FOREIGN KEY(product_id) REFERENCES products(id))")
        cur.execute("CREATE TABLE shipments (id INTEGER PRIMARY KEY, po_id INTEGER, warehouse_id INTEGER, shipment_date TEXT, carrier TEXT, tracking_number TEXT, status TEXT, FOREIGN KEY(po_id) REFERENCES purchase_orders(id), FOREIGN KEY(warehouse_id) REFERENCES warehouses(id))")

        # Populate Data
        product_names = [("Laptop Pro", "Electronics"), ("Wireless Mouse", "Accessories"), ("Mechanical Keyboard", "Accessories"), ("27-inch 4K Monitor", "Electronics"), ("USB-C Hub", "Accessories"), ("Gaming PC", "Electronics"), ("Office Chair", "Furniture"), ("Standing Desk", "Furniture"), ("Webcam HD", "Electronics"), ("Noise-Cancelling Headphones", "Accessories")]
        products = []
        for i in range(50):
            name, category = random.choice(product_names)
            products.append((i + 1, f"{name} v{i//10 + 1}", category, round(random.uniform(20, 2000), 2)))
        cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)

        suppliers = [(i + 1, f"Supplier {chr(65+i)} Corp", f"Contact {chr(65+i)}", f"555-010{i}") for i in range(10)]
        cur.executemany("INSERT INTO suppliers VALUES (?, ?, ?, ?)", suppliers)

        warehouses = [(1, "East Coast Hub", "New York, NY"), (2, "West Coast Hub", "Los Angeles, CA"), (3, "Midwest Center", "Chicago, IL"), (4, "Southern Depot", "Dallas, TX"), (5, "Northwest Gate", "Seattle, WA")]
        cur.executemany("INSERT INTO warehouses VALUES (?, ?, ?)", warehouses)

        inventory = []
        for i in range(150):
            inventory.append((i + 1, random.randint(1, 50), random.randint(1, 5), random.randint(10, 500), random.randint(10, 50)))
        cur.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", inventory)

        purchase_orders = []
        start_date = date(2023, 1, 1)
        for i in range(50):
            order_date = start_date + timedelta(days=random.randint(0, 500))
            delivery_date = order_date + timedelta(days=random.randint(7, 30))
            status = random.choice(["Delivered", "Shipped", "Pending"])
            purchase_orders.append((i + 1, random.randint(1, 10), order_date.isoformat(), delivery_date.isoformat(), status))
        cur.executemany("INSERT INTO purchase_orders VALUES (?, ?, ?, ?, ?)", purchase_orders)

        po_items = []
        item_id_counter = 1
        for po_id in range(1, 51):
            num_items = random.randint(1, 5)
            for _ in range(num_items):
                product_id = random.randint(1, 50)
                product_price = next((p[3] for p in products if p[0] == product_id), 100.0)
                po_items.append((item_id_counter, po_id, product_id, random.randint(10, 100), product_price))
                item_id_counter += 1
        cur.executemany("INSERT INTO purchase_order_items VALUES (?, ?, ?, ?, ?)", po_items)

        shipments = []
        for i in range(50):
            po_id = i + 1
            po_order_date_str = next((po[2] for po in purchase_orders if po[0] == po_id), date.today().isoformat())
            po_order_date = date.fromisoformat(po_order_date_str)
            shipment_date = po_order_date + timedelta(days=random.randint(1, 3))
            status = random.choice(["In Transit", "Delivered", "Delayed"])
            carrier = random.choice(["FedEx", "UPS", "DHL", "USPS"])
            tracking_number = f"{carrier[:2].upper()}{random.randint(1000000000, 9999999999)}"
            shipments.append((i + 1, po_id, random.randint(1, 5), shipment_date.isoformat(), carrier, tracking_number, status))
        cur.executemany("INSERT INTO shipments VALUES (?, ?, ?, ?, ?, ?, ?)", shipments)

        # Create Employee Schema
        cur.execute("CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT)")
        cur.execute("CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER, salary REAL, hire_date TEXT, FOREIGN KEY(department_id) REFERENCES departments(id))")

        # Populate Employee Data
        departments = [(1, "Engineering"), (2, "Sales"), (3, "Marketing"), (4, "Human Resources"), (5, "Finance")]
        cur.executemany("INSERT INTO departments VALUES (?, ?)", departments)

        employees = [
            (1, "Alice Johnson", 1, 90000, "2021-05-10"),
            (2, "Bob Smith", 1, 120000, "2020-01-15"),
            (3, "Charlie Brown", 2, 75000, "2022-03-20"),
            (4, "Diana Prince", 3, 68000, "2021-09-01"),
            (5, "Ethan Hunt", 1, 150000, "2019-07-22"),
            (6, "Fiona Glenanne", 2, 82000, "2022-06-12"),
            (7, "George Costanza", 5, 95000, "2020-11-30"),
            (8, "Hannah Montana", 3, 71000, "2023-02-18"),
            (9, "Ian Malcolm", 1, 135000, "2021-08-14"),
            (10, "Jane Doe", 4, 60000, "2022-10-05"),
        ]
        cur.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?)", employees)

        self.connection.commit()

    def list_tables(self) -> List[str]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [row[0] for row in cursor.fetchall()]

    def get_table_schema(self, collection_name: str) -> str:
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"PRAGMA table_info('{collection_name}');")
            columns = cursor.fetchall()
            if not columns:
                return f"Error: Table '{collection_name}' not found."
            schema_str = f"Schema for table '{collection_name}':\n"
            schema_str += "\n".join([f"- {col[1]} ({col[2]})" for col in columns])
            return schema_str
        except sqlite3.Error as e:
            return f"Database error: {e}"

    def run_sql_query(self, sql_query: str) -> dict[str, Any]:
        logging.info(f"Executing SQL query: {sql_query!r}")
        if not sql_query.strip().upper().startswith("SELECT"):
            error_result = {"error": "Only SELECT queries are allowed for security reasons."}
            logging.warning(f"SQL query blocked: {error_result}")
            return error_result
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql_query)
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            results = [dict(zip(column_names, row)) for row in cursor.fetchall()]
            final_result = {"result": results}
            logging.info(f"SQL query successful. Result: {final_result}")
            return final_result
        except sqlite3.Error as e:
            error_result = {"error": f"An error occurred while executing the SQL query: {e}"}
            logging.error(f"SQL query failed: {error_result}")
            return error_result

    def find_documents(self, collection_name: str, filter: dict, projection: dict | None = None, limit: int = 50) -> dict[str, Any]:
        return {"error": "This is a SQL database. Use 'run_sql_query' instead."}


class MongoDbConnector(DatabaseConnector):
    """A connector for a MongoDB database."""

    def __init__(self, uri: str, db_name: str):
        if not PYMONGO_INSTALLED:
            raise ImportError("Pymongo is not installed. Please run 'uv pip install pymongo'.")
        self.uri = uri
        self.db_name = db_name
        self.client: MongoClient | None = None
        self.db = None

    def connect(self) -> None:
        logging.info(f"Connecting to MongoDB at {self.uri}...")
        try:
            # Use certifi to provide a trusted CA bundle for TLS connections
            self.client = MongoClient(self.uri, tlsCAFile=certifi.where())
            # The ping command is cheap and does not require auth.
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self._populate_sample_data()
            logging.info("✅ MongoDB connection successful and data populated.")
        except ConnectionFailure as e:
            logging.error(f"MongoDB connection failed: {e}")
            raise

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed.")

    def _populate_sample_data(self) -> None:
        """Creates and populates a sample Retail Order-to-Cash schema."""
        if self.db is None:
            return

        logging.info("Populating MongoDB with Retail Order-to-Cash sample data...")
        # Clear existing collections
        self.db.customers.drop()
        self.db.products.drop()
        self.db.orders.drop()

        # Customers
        customers = []
        for i in range(50):
            customers.append({
                "customer_id": f"C{1001+i}",
                "name": f"Customer {chr(65+i%26)}{i//26+1}",
                "email": f"customer{i+1}@example.com",
                "address": {
                    "street": f"{100+i} Main St",
                    "city": random.choice(["New York", "Los Angeles", "Chicago"]),
                    "zip": f"{10001+i}"
                },
                "join_date": (date.today() - timedelta(days=random.randint(30, 1000))).isoformat()
            })
        self.db.customers.insert_many(customers)

        # Products
        products = []
        for i in range(50):
            products.append({
                "product_id": f"P{2001+i}",
                "name": f"Product {i+1}",
                "category": random.choice(["Apparel", "Electronics", "Home Goods"]),
                "price": round(random.uniform(10, 500), 2),
                "stock": random.randint(0, 200)
            })
        self.db.products.insert_many(products)

        # Orders
        orders = []
        for i in range(100):
            customer = random.choice(customers)
            num_items = random.randint(1, 4)
            order_items = []
            total_amount = 0
            for _ in range(num_items):
                product = random.choice(products)
                quantity = random.randint(1, 5)
                item_total = round(product['price'] * quantity, 2)
                order_items.append({
                    "product_id": product['product_id'],
                    "product_name": product['name'],
                    "quantity": quantity,
                    "unit_price": product['price'],
                    "item_total": item_total
                })
                total_amount += item_total
            
            orders.append({
                "order_id": f"O{3001+i}",
                "customer_id": customer['customer_id'],
                "order_date": (date.today() - timedelta(days=random.randint(1, 365))).isoformat(),
                "status": random.choice(["Pending", "Shipped", "Delivered", "Cancelled"]),
                "items": order_items,
                "total_amount": round(total_amount, 2)
            })
        self.db.orders.insert_many(orders)
        logging.info("✅ MongoDB sample data populated.")

    def list_tables(self) -> List[str]:
        if self.db is None:
            return []
        return self.db.list_collection_names()

    def get_table_schema(self, collection_name: str) -> str:
        if self.db is None:
            return "Error: Not connected to database."
        collection = self.db[collection_name]
        sample_doc = collection.find_one()
        if not sample_doc:
            return f"Collection '{collection_name}' is empty or does not exist."
        
        schema_str = f"Schema for collection '{collection_name}' (based on a sample document):\n"
        for key, value in sample_doc.items():
            schema_str += f"- {key} ({type(value).__name__})\n"
        return schema_str

    def run_sql_query(self, sql_query: str) -> dict[str, Any]:
        return {"error": "This is a MongoDB connection. Use 'find_documents' instead of 'run_sql_query'."}

    def find_documents(self, collection_name: str, filter: dict, projection: dict | None = None, limit: int = 50) -> dict[str, Any]:
        if self.db is None:
            return {"error": "Not connected to database."}
        try:
            if projection is not None and "_id" not in projection:
                projection["_id"] = 0
            
            documents = list(self.db[collection_name].find(filter, projection).limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for doc in documents:
                if '_id' in doc and isinstance(doc['_id'], ObjectId):
                    doc['_id'] = str(doc['_id'])

            return {"result": documents}
        except Exception as e:
            logging.error(f"MongoDB find_documents failed: {e}", exc_info=True)
            return {"error": f"An error occurred: {e}"}


class DatabaseManager:
    """Manages all configured database connections."""

    def __init__(self):
        self._connectors: Dict[str, DatabaseConnector] = {}
        self._parse_env_configs()

    def _parse_env_configs(self):
        """Parses environment variables to find database connection definitions."""
        db_configs: Dict[str, Dict[str, str]] = {}
        for key, value in os.environ.items():
            if key.startswith("DB_CONN_"):
                # e.g., DB_CONN_RETAIL_OTC_TYPE -> retail_otc, TYPE
                suffix = key.rsplit('_', 1)[-1]
                conn_name_parts = key.removeprefix("DB_CONN_").removesuffix(f"_{suffix}")
                conn_name = conn_name_parts.lower()
                
                if conn_name not in db_configs:
                    db_configs[conn_name] = {}
                
                db_configs[conn_name][suffix.lower()] = value

        for conn_name, config in db_configs.items():
            db_type = config.get("type")
            if db_type == "sqlite_in_memory":
                self._connectors[conn_name] = SQLiteInMemoryConnector()
            elif db_type == "mongodb":
                if not PYMONGO_INSTALLED:
                    logging.error(f"MongoDB connector '{conn_name}' configured, but 'pymongo' is not installed. Please run 'uv pip install pymongo'.")
                    continue
                uri = config.get("uri")
                dbname = config.get("dbname", conn_name) # Default db name to connection name
                if not uri:
                    logging.warning(f"MongoDB connection '{conn_name}' is missing a URI (DB_CONN_{conn_name.upper()}_URI).")
                    continue
                self._connectors[conn_name] = MongoDbConnector(uri=uri, db_name=dbname)
            else:
                if db_type:
                    logging.warning(f"Unsupported database type '{db_type}' for connection '{conn_name}'.")

    def connect_all(self):
        """Establishes connections for all configured databases."""
        for name, connector in self._connectors.items():
            try:
                connector.connect()
            except Exception as e:
                logging.error(f"Failed to connect to database '{name}': {e}")

    def get_connector(self, name: str) -> DatabaseConnector | None:
        """Gets a specific connector by name."""
        return self._connectors.get(name)

    def list_connections(self) -> List[str]:
        """Returns a list of names of all available database connections."""
        return list(self._connectors.keys())