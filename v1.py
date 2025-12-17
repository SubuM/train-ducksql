import streamlit as st
from streamlit_ace import st_ace
import pandas as pd
import duckdb
import re
import os

# ------------------------------- Config -------------------------------
st.set_page_config(page_title="SQL Lab", page_icon="🔬", layout="wide")
st.title("🧪 SQL Lab")

TABLE_PREVIEW_LIMIT = 20  # Number of rows to show by default
DB_DIR = "user_databases"  # folder to store DuckDB files
os.makedirs(DB_DIR, exist_ok=True)

# ------------------------------- Session State -------------------------------
if "token" not in st.session_state:
    st.session_state["token"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None
if "query_history" not in st.session_state:
    st.session_state["query_history"] = []
if "login_mode" not in st.session_state:
    st.session_state["login_mode"] = None

# ------------------------------- Helper Functions -------------------------------
def get_user_db_path(username):
    """Return path to user's DuckDB database file"""
    return os.path.join(DB_DIR, f"{username}.duckdb")

def run_sql_query(username, sql):
    """Execute SQL in user's DuckDB and return results"""
    try:
        conn = duckdb.connect(database=get_user_db_path(username), read_only=False)
        result = conn.execute(sql)
        if result.description:  # query returned rows
            df = result.df()
            return {"type": "table", "data": df}
        else:
            return {"type": "message", "message": f"{result.rowcount} rows affected."}
    except Exception as e:
        return {"type": "error", "message": str(e)}

def list_tables(username):
    try:
        conn = duckdb.connect(database=get_user_db_path(username), read_only=False)
        return [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
    except:
        return []

def list_columns(username, table):
    try:
        conn = duckdb.connect(database=get_user_db_path(username), read_only=False)
        return [row[0] for row in conn.execute(f"DESCRIBE {table}").fetchall()]
    except:
        return []

# ------------------------------- Login/Register UI -------------------------------
st.sidebar.subheader("Login Options")
if st.sidebar.button("User Login"):
    st.session_state["login_mode"] = "user"
if st.sidebar.button("New User Registration"):
    st.session_state["login_mode"] = "register"
if st.sidebar.button("Admin Login"):
    st.session_state["login_mode"] = "admin"

mode = st.session_state.get("login_mode")

if mode == "user":
    st.subheader("User Login")
    username_input = st.text_input("Username", key="login_user")
    password_input = st.text_input("Password", type="password", key="login_pass")
    if st.button("Login"):
        # For simplicity in DuckDB demo, password check is skipped
        if username_input.strip():
            st.session_state["username"] = username_input.strip()
            st.session_state["token"] = "user_authenticated"
            st.success(f"Logged in as {st.session_state['username']}")
        else:
            st.error("Enter a valid username")

elif mode == "register":
    st.subheader("Register a New User")
    new_user = st.text_input("Username", key="reg_user")
    new_password = st.text_input("Password", type="password", key="reg_pass")
    if st.button("Register"):
        if new_user.strip():
            # Simply create a new DuckDB file for the user
            conn = duckdb.connect(database=get_user_db_path(new_user.strip()), read_only=False)
            conn.close()
            st.success(f"User `{new_user}` registered successfully!")
            st.info("You can now login using User Login.")
        else:
            st.error("Enter a valid username")

elif mode == "admin":
    st.subheader("Admin Login")
    admin_token_input = st.text_input("Admin Token", type="password", key="admin_token")
    if st.button("Login as Admin"):
        if admin_token_input == st.secrets.get("ADMIN_TOKEN", "admin123"):
            st.session_state["username"] = "admin"
            st.session_state["token"] = "admin_token_authenticated"
            st.success("Logged in as Admin")
        else:
            st.error("Invalid Admin Token")

# ------------------------------- Dashboard -------------------------------
if st.session_state.get("token"):
    username = st.session_state["username"]
    st.sidebar.success(f"Logged in as {username}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    is_admin = username == "admin"

    if not is_admin:
        st.subheader("User Dashboard")
        st.write(f"Hello {username}! Practice SQL in your private DuckDB.")

        # ------------------ ACE Editor Theme Selector ------------------
        ace_themes = [
            "dracula", "monokai", "github", "tomorrow", 
            "twilight", "xcode", "solarized_dark", "solarized_light", "terminal"
        ]
        selected_theme = st.selectbox("Select ACE Editor Theme", ace_themes, index=0)

        # SQL editor
        sql_query = st_ace(
            value="",
            language="sql",
            theme=selected_theme,
            height=300,
            key="sql_editor",
            font_size=14,
            tab_size=4,
            show_gutter=True,
            show_print_margin=False,
            wrap=True,
            placeholder="Write your SQL query here..."
        )

        # Execute query
        if sql_query.strip() and sql_query != st.session_state.get("last_executed_sql"):
            result = run_sql_query(username, sql_query)
            st.session_state["last_executed_sql"] = sql_query
            st.session_state["query_history"].append(sql_query)

            if result["type"] == "table":
                st.dataframe(result["data"], use_container_width=True)
            elif result["type"] == "message":
                st.success(result["message"])
            else:
                st.error(result["message"])

        # Query History
        if st.session_state.get("query_history"):
            st.subheader("Query History")
            for i, q in enumerate(reversed(st.session_state["query_history"]), 1):
                st.code(f"{i}: {q}", language="sql")

        # Database Schema Explorer
        st.subheader("Database Schema Explorer")
        tables = list_tables(username)
        if tables:
            selected_table = st.selectbox("Select Table", tables)
            if selected_table:
                columns = list_columns(username, selected_table)
                st.write(f"Columns in `{selected_table}`: {columns}")
                # Preview table
                df_preview = run_sql_query(username, f"SELECT * FROM {selected_table} LIMIT {TABLE_PREVIEW_LIMIT}")
                if df_preview["type"] == "table":
                    st.dataframe(df_preview["data"], use_container_width=True)
                else:
                    st.error(df_preview.get("message", "Could not preview table"))

    else:
        # ---------------- Admin Dashboard ----------------
        st.subheader("Admin Dashboard")
        st.write("Manage all users and view their DuckDB files.")
        users = [f.replace(".duckdb","") for f in os.listdir(DB_DIR) if f.endswith(".duckdb")]
        st.write("Registered Users:", users)

        selected_user = st.selectbox("Select User to Inspect", users)
        if selected_user:
            st.write(f"Inspecting `{selected_user}`'s database")
            user_tables = list_tables(selected_user)
            st.write("Tables:", user_tables)
            if user_tables:
                table_to_preview = st.selectbox("Select Table", user_tables, key="admin_table_select")
                if table_to_preview:
                    columns = list_columns(selected_user, table_to_preview)
                    st.write(f"Columns: {columns}")
                    df_preview = run_sql_query(selected_user, f"SELECT * FROM {table_to_preview} LIMIT {TABLE_PREVIEW_LIMIT}")
                    if df_preview["type"] == "table":
                        st.dataframe(df_preview["data"], use_container_width=True)
                    else:
                        st.error(df_preview.get("message", "Could not preview table"))
