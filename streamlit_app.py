import streamlit as st
from streamlit_ace import st_ace
import pandas as pd
import duckdb

# -------------------------------
# 1. Config & Connection Setup
# -------------------------------
st.set_page_config(page_title="SQL Lab (Cloud)", page_icon="☁️", layout="wide")

# Check for secrets to prevent crashing if not configured
if 'motherduck_token' not in st.secrets:
    st.error("🚨 Missing 'motherduck_token' in Streamlit Secrets. Please configure it in your app settings.")
    st.stop()

ADMIN_TOKEN = st.secrets.get("ADMIN_TOKEN")

# -------------------------------
# 2. Database Helper Functions
# -------------------------------

def get_connection():
    """Establishes a connection to MotherDuck using the secret token."""
    try:
        token = st.secrets['motherduck_token']
        # The 'md:' prefix tells DuckDB to connect to MotherDuck
        return duckdb.connect(f"md:?motherduck_token={token}")
    except Exception as e:
        st.error(f"Connection failed: {e}")
        return None

def init_db():
    """
    Initializes the system schema and users table in the cloud.
    This runs once per session start to ensure infrastructure exists.
    """
    conn = get_connection()
    if not conn: return

    try:
        # Create a special schema for system-level data (users, logs)
        conn.execute("CREATE SCHEMA IF NOT EXISTS system_app;")
        
        # Create the users table inside that schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_app.users (
                username VARCHAR PRIMARY KEY, 
                password VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    except Exception as e:
        st.error(f"DB Init Error: {e}")
    finally:
        conn.close()

def register_user(username, password):
    """Registers a new user and creates their private schema."""
    conn = get_connection()
    if not conn: return {"error": "No DB Connection"}

    try:
        # 1. Sanitize input (basic check)
        if not username.isalnum():
            return {"error": "Username must be alphanumeric only."}

        # 2. Check if user exists
        exists = conn.execute("SELECT 1 FROM system_app.users WHERE username=?", [username]).fetchone()
        if exists:
            return {"error": "User already exists"}
        
        # 3. Add to system table
        conn.execute("INSERT INTO system_app.users (username, password) VALUES (?, ?)", [username, password])
        
        # 4. Create User's Private Schema
        # In MotherDuck, a Schema acts like a folder/database for that user
        safe_schema = f"user_{username}"
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {safe_schema};")
        
        return {"message": f"User `{username}` registered successfully! Schema `{safe_schema}` created."}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def login_user(username, password):
    """Verifies credentials."""
    conn = get_connection()
    if not conn: return False

    try:
        res = conn.execute("SELECT password FROM system_app.users WHERE username=?", [username]).fetchone()
        if res and res[0] == password:
            return True
    except:
        pass
    finally:
        conn.close()
    return False

def get_all_users():
    """Admin helper to list all registered users."""
    conn = get_connection()
    if not conn: return []
    try:
        res = conn.execute("SELECT username FROM system_app.users").fetchall()
        return [r[0] for r in res]
    except:
        return []
    finally:
        conn.close()

def run_sql_query(username, sql, is_admin=False):
    """
    Executes SQL. 
    If standard user: Enforces execution inside their own schema.
    If admin: Can query anything.
    """
    conn = get_connection()
    if not conn: return {"type": "error", "message": "Connection Failed"}

    try:
        # CONTEXT SWITCHING
        if not is_admin:
            # Force user into their own schema
            safe_schema = f"user_{username}"
            # This ensures 'CREATE TABLE x' -> 'user_john.x'
            conn.execute(f"USE {safe_schema};") 
        
        # Execute the User's Query
        result = conn.execute(sql)
        
        # Handle SELECT vs INSERT/UPDATE/CREATE
        if result.description:
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return {"type": "table", "columns": columns, "rows": rows}
        else:
            return {"type": "message", "message": "Query executed successfully."}
            
    except Exception as e:
        return {"type": "error", "message": f"SQL Error: {str(e)}"}
    finally:
        conn.close()

# -------------------------------
# 3. Session State Initialization
# -------------------------------
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

if "username" not in st.session_state:
    st.session_state["username"] = None
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "query_history" not in st.session_state:
    st.session_state["query_history"] = []

# -------------------------------
# 4. Sidebar: Authentication
# -------------------------------
st.sidebar.title("🔐 Access")

if not st.session_state["logged_in"]:
    menu = st.sidebar.radio("Menu", ["Login", "Register", "Admin Login"])

    if menu == "Register":
        st.sidebar.subheader("Create Account")
        new_u = st.sidebar.text_input("New Username")
        new_p = st.sidebar.text_input("New Password", type="password")
        if st.sidebar.button("Register"):
            if new_u and new_p:
                with st.spinner("Creating cloud resources..."):
                    res = register_user(new_u, new_p)
                if "error" in res:
                    st.sidebar.error(res["error"])
                else:
                    st.sidebar.success(res["message"])
            else:
                st.sidebar.warning("Fill all fields.")

    elif menu == "Login":
        st.sidebar.subheader("User Login")
        u = st.sidebar.text_input("Username")
        p = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if login_user(u, p):
                st.session_state["username"] = u
                st.session_state["logged_in"] = True
                st.session_state["is_admin"] = False
                st.rerun()
            else:
                st.sidebar.error("Invalid credentials.")

    elif menu == "Admin Login":
        st.sidebar.subheader("Admin Access")
        token = st.sidebar.text_input("Admin Token", type="password")
        if st.sidebar.button("Enter as Admin"):
            if token == ADMIN_TOKEN:
                st.session_state["username"] = "admin"
                st.session_state["logged_in"] = True
                st.session_state["is_admin"] = True
                st.rerun()
            else:
                st.sidebar.error("Invalid Token.")

else:
    # Logout Button
    st.sidebar.success(f"Logged in: {st.session_state['username']}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

# -------------------------------
# 5. Main Dashboard
# -------------------------------

if st.session_state["logged_in"]:
    
    # --- ADMIN VIEW ---
    if st.session_state["is_admin"]:
        st.title("🛡️ Admin Dashboard")
        
        tab1, tab2 = st.tabs(["User Management", "Global SQL Console"])
        
        with tab1:
            st.subheader("Registered Users")
            users = get_all_users()
            if users:
                st.table(pd.DataFrame(users, columns=["Usernames"]))
            else:
                st.info("No users found.")
        
        with tab2:
            st.subheader("Execute SQL (Global Access)")
            st.info("⚠️ Admin queries run against the entire MotherDuck instance.")
            admin_sql = st_ace(language='sql', theme='monokai', height=200, key="admin_ace")
            
            if st.button("Run Admin Query"):
                if admin_sql:
                    res = run_sql_query("admin", admin_sql, is_admin=True)
                    if res['type'] == 'table':
                        st.dataframe(pd.DataFrame(res['rows'], columns=res['columns']), use_container_width=True)
                    elif res['type'] == 'message':
                        st.success(res['message'])
                    else:
                        st.error(res['message'])

    # --- USER VIEW ---
    else:
        user = st.session_state["username"]
        st.title(f"🧪 SQL Lab: {user}")
        st.caption(f"Connected to Cloud Schema: `user_{user}`")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("SQL Editor")
            sql_code = st_ace(
                language='sql', 
                theme='monokai', 
                height=300, 
                placeholder="CREATE TABLE test (id INT, name VARCHAR);\nINSERT INTO test VALUES (1, 'Alice');\nSELECT * FROM test;",
                key="user_ace"
            )
            
            if st.button("Run Query", type="primary"):
                if sql_code.strip():
                    # Save to history
                    st.session_state["query_history"].append(sql_code)
                    
                    with st.spinner("Running on MotherDuck Cloud..."):
                        res = run_sql_query(user, sql_code, is_admin=False)
                        
                    if res['type'] == 'table':
                        df = pd.DataFrame(res['rows'], columns=res['columns'])
                        st.dataframe(df, use_container_width=True)
                        st.success(f"Returned {len(df)} rows.")
                    elif res['type'] == 'message':
                        st.success(res['message'])
                    else:
                        st.error(res['message'])
                else:
                    st.warning("Please enter a query.")

        with col2:
            st.subheader("Session History")
            if st.session_state["query_history"]:
                for i, q in enumerate(reversed(st.session_state["query_history"])):
                    with st.expander(f"Query {len(st.session_state['query_history']) - i}"):
                        st.code(q, language="sql")
            else:
                st.info("No queries run yet in this session.")

else:
    # --- LANDING PAGE ---
    st.title("Welcome to SQL Lab 🚀")
    st.markdown("""
    This is a persistent SQL playground powered by **DuckDB** and **MotherDuck**.
    
    1. **Register** a new account in the sidebar.
    2. A private cloud database (Schema) will be created for you.
    3. Login and start writing SQL! 
    
    *Data is saved automatically to the cloud.*
    """)