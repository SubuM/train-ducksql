import streamlit as st
from streamlit_ace import st_ace
import pandas as pd
import duckdb
import os
import re

# -------------------------------
# Config
# -------------------------------
DB_FOLDER = "user_databases"
TABLE_PREVIEW_LIMIT = 20
ADMIN_TOKEN = st.secrets.get("ADMIN_TOKEN", "changeme")  # Admin token/password

if not os.path.exists(DB_FOLDER):
    os.makedirs(DB_FOLDER)

# -------------------------------
# Helpers
# -------------------------------
def get_user_db_path(username):
    return os.path.join(DB_FOLDER, f"{username}.duckdb")

def register_user(username, password):
    db_path = get_user_db_path(username)
    if os.path.exists(db_path):
        return {"error": "User already exists"}
    # Store password in simple table
    conn = duckdb.connect(db_path)
    conn.execute(f"CREATE TABLE users(username TEXT, password TEXT);")
    conn.execute("INSERT INTO users VALUES (?, ?);", [username, password])
    conn.close()
    return {"message": f"User `{username}` registered successfully!"}

def login_user(username, password):
    db_path = get_user_db_path(username)
    if not os.path.exists(db_path):
        return None
    conn = duckdb.connect(db_path)
    try:
        result = conn.execute("SELECT password FROM users WHERE username = ?;", [username]).fetchone()
        conn.close()
        if result and result[0] == password:
            return True
    except:
        pass
    return None

def run_sql_query(username, sql):
    db_path = get_user_db_path(username)
    conn = duckdb.connect(db_path)
    try:
        result = conn.execute(sql)
        if result.description:  # SELECT query
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return {"type": "table", "columns": columns, "rows": rows}
        else:
            return {"type": "message", "message": f"{conn.total_changes} rows affected."}
    except Exception as e:
        return {"type": "error", "message": str(e)}
    finally:
        conn.close()

def get_all_users():
    return [f.split(".duckdb")[0] for f in os.listdir(DB_FOLDER) if f.endswith(".duckdb") and f != "admin.duckdb"]

# -------------------------------
# Streamlit UI
# -------------------------------
st.set_page_config(page_title="SQL Lab", page_icon="🔬", layout="wide")
st.title("🧪 SQL Lab")

# -------------------------------
# Session state
# -------------------------------
if "username" not in st.session_state:
    st.session_state["username"] = None
if "token" not in st.session_state:
    st.session_state["token"] = None
if "query_history" not in st.session_state:
    st.session_state["query_history"] = []
if "last_executed_sql" not in st.session_state:
    st.session_state["last_executed_sql"] = ""

# -------------------------------
# Sidebar: Login/Register/Admin
# -------------------------------
if st.session_state["token"] is None:
    st.sidebar.subheader("Authentication")
    login_option = st.sidebar.radio("Select Option", ["User Login", "New User Registration", "Admin Login"])

    if login_option == "User Login":
        username = st.sidebar.text_input("Username", key="login_user")
        password = st.sidebar.text_input("Password", type="password", key="login_pass")
        if st.sidebar.button("Login"):
            if login_user(username, password):
                st.session_state["username"] = username
                st.session_state["token"] = True
                st.success(f"Logged in as {username}")
            else:
                st.error("Invalid credentials")

    elif login_option == "New User Registration":
        new_user = st.sidebar.text_input("Username", key="reg_user")
        new_password = st.sidebar.text_input("Password", type="password", key="reg_pass")
        if st.sidebar.button("Register"):
            result = register_user(new_user, new_password)
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(result.get("message"))
                st.info("You can now login from the sidebar.")

    elif login_option == "Admin Login":
        admin_token = st.sidebar.text_input("Admin Token", type="password", key="admin_token")
        if st.sidebar.button("Admin Login"):
            if admin_token == ADMIN_TOKEN:
                st.session_state["username"] = "admin"
                st.session_state["token"] = True
                st.success("Admin logged in successfully!")
            else:
                st.error("Invalid admin token")

# -------------------------------
# Main Dashboard
# -------------------------------
if st.session_state["token"]:
    username = st.session_state["username"]
    st.sidebar.success(f"Logged in as {username}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    # ---------------- Admin Dashboard ----------------
    if username == "admin":
        st.subheader("Admin Dashboard")
        tabs = st.tabs(["List Users", "Manage Users", "SQL Console"])
        with tabs[0]:
            st.write("All users:")
            users = get_all_users()
            st.write(users)

        with tabs[1]:
            st.write("Delete a user:")
            users = get_all_users()
            if users:
                user_to_delete = st.selectbox("Select user", [u for u in users if u != "admin"])
                if st.button("Delete User"):
                    if user_to_delete:
                        confirm = st.checkbox(f"Confirm delete `{user_to_delete}`")
                        if confirm:
                            try:
                                os.remove(get_user_db_path(user_to_delete))
                                st.success(f"User `{user_to_delete}` deleted successfully!")
                            except Exception as e:
                                st.error(f"Error deleting user: {str(e)}")
            else:
                st.info("No users found.")

        with tabs[2]:
            st.write("Execute SQL on admin database:")
            # Admin SQL DB
            if not os.path.exists(get_user_db_path("admin")):
                conn = duckdb.connect(get_user_db_path("admin"))
                conn.close()
            ace_themes = ["dracula", "monokai", "github", "tomorrow", "twilight", "xcode", "solarized_dark", "solarized_light", "terminal"]
            selected_theme = st.selectbox("Select ACE Editor Theme", ace_themes)
            sql_query = st_ace(
                value="",
                language="sql",
                theme=selected_theme,
                height=300,
                key="admin_sql_editor",
                font_size=14,
                tab_size=4,
                show_gutter=True,
                show_print_margin=False,
                wrap=True,
                placeholder="Write SQL here..."
            )
            if sql_query.strip() and sql_query != st.session_state.get("last_executed_sql"):
                result = run_sql_query("admin", sql_query)
                st.session_state["last_executed_sql"] = sql_query
                if result["type"] == "table":
                    df = pd.DataFrame(result["rows"], columns=result["columns"])
                    st.dataframe(df, use_container_width=True)
                elif result["type"] == "message":
                    st.success(result["message"])
                else:
                    st.error(result["message"])

    # ---------------- User Dashboard ----------------
    else:
        st.subheader(f"User Dashboard - {username}")
        st.write(f"Hello {username}! Practice SQL below:")

        # ACE editor for SQL queries
        ace_themes = ["dracula", "monokai", "github", "tomorrow", "twilight", "xcode", "solarized_dark", "solarized_light", "terminal"]
        selected_theme = st.selectbox("Select ACE Editor Theme", ace_themes)
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
            placeholder="Write your SQL query here...",
        )

        if sql_query.strip() and sql_query != st.session_state.get("last_executed_sql"):
            result = run_sql_query(username, sql_query)
            st.session_state["last_executed_sql"] = sql_query
            st.session_state["query_history"].append(sql_query)

            if result["type"] == "table":
                df = pd.DataFrame(result["rows"], columns=result["columns"])
                st.dataframe(df, use_container_width=True)
            elif result["type"] == "message":
                st.success(result["message"])
            else:
                st.error(result["message"])

        # Query history
        if st.session_state.get("query_history"):
            st.subheader("Query History")
            for i, q in enumerate(reversed(st.session_state["query_history"]), 1):
                st.code(f"{i}: {q}", language="sql")
