import streamlit as st
from streamlit_ace import st_ace
import pandas as pd
import duckdb
import os
import re

# -------------------------------
# Config & Secrets
# -------------------------------
TABLE_PREVIEW_LIMIT = 20

# Check for secrets
if 'motherduck_token' not in st.secrets:
    st.error("🚨 Missing 'motherduck_token' in secrets.")
    st.stop()

ADMIN_TOKEN = st.secrets.get("ADMIN_TOKEN", "changeme")

# -------------------------------
# Backend Helpers (MotherDuck)
# -------------------------------

def get_connection():
    token = st.secrets['motherduck_token']
    return duckdb.connect(f"md:?motherduck_token={token}")

def init_db():
    conn = get_connection()
    try:
        conn.execute("CREATE SCHEMA IF NOT EXISTS system_app;")
        # Auto-timestamp added
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
    conn = get_connection()
    try:
        if not username.isalnum():
            return {"error": "Username must be alphanumeric only."}

        exists = conn.execute("SELECT 1 FROM system_app.users WHERE username=?", [username]).fetchone()
        if exists:
            return {"error": "User already exists"}
        
        # Insert (Letting DB handle created_at)
        conn.execute("INSERT INTO system_app.users (username, password) VALUES (?, ?)", [username, password])
        
        # Create Schema
        safe_schema = f"user_{username}"
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {safe_schema};")
        
        return {"message": f"User `{username}` registered successfully!"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def login_user(username, password):
    conn = get_connection()
    try:
        result = conn.execute("SELECT password FROM system_app.users WHERE username = ?;", [username]).fetchone()
        if result and result[0] == password:
            return True
    except:
        pass
    finally:
        conn.close()
    return None

def get_all_users():
    conn = get_connection()
    try:
        res = conn.execute("SELECT username FROM system_app.users").fetchall()
        return [r[0] for r in res]
    except:
        return []
    finally:
        conn.close()

def delete_user(username):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM system_app.users WHERE username=?", [username])
        conn.execute(f"DROP SCHEMA IF EXISTS user_{username} CASCADE;")
        return True
    except Exception as e:
        raise e
    finally:
        conn.close()

# -------------------------------
# 🔒 SECURITY GUARDRAILS
# -------------------------------
def validate_sql_permissions(sql, username):
    """
    Prevents schema leaks via metadata commands.
    """
    if username == "admin":
        return True, ""

    sql_lower = sql.lower()

    # 1. Block Global Metadata Lookups
    if "show all tables" in sql_lower:
        return False, "🚫 'SHOW ALL TABLES' is restricted. Use 'SHOW TABLES' to see your own tables."
    
    # 2. Block Information Schema (The "Phonebook" of the DB)
    if "information_schema" in sql_lower:
        return False, "🚫 Access to 'information_schema' is restricted for security."

    # 3. Block System App (Passwords)
    if "system_app" in sql_lower:
        return False, "🚫 Access to 'system_app' is forbidden."

    # 4. Block Other Users' Schemas
    # Regex finds: "user_something"
    schema_references = re.findall(r'\buser_(\w+)\b', sql_lower)
    for ref_user in schema_references:
        if ref_user != username.lower():
            return False, f"🚫 Security Violation: You cannot access 'user_{ref_user}' data."

    # 5. Block Schema Destruction
    if "drop schema" in sql_lower:
        return False, "🚫 Dropping schemas is not allowed."

    return True, ""

def run_sql_query(username, sql):
    # 1. Security Check
    is_valid, msg = validate_sql_permissions(sql, username)
    if not is_valid:
        return {"type": "error", "message": msg}

    conn = get_connection()
    try:
        # 2. Force Context (The "Wall")
        if username != "admin":
            safe_schema = f"user_{username}"
            conn.execute(f"USE {safe_schema};")

        # 3. Execute
        result = conn.execute(sql)
        
        if result.description:
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return {"type": "table", "columns": columns, "rows": rows}
        else:
            return {"type": "message", "message": "Query executed successfully."}
    except Exception as e:
        return {"type": "error", "message": str(e)}
    finally:
        conn.close()

# -------------------------------
# Streamlit UI (STRICTLY PRESERVED)
# -------------------------------
st.set_page_config(page_title="SQL Lab", page_icon="🔬", layout="wide")
st.title("🧪 SQL Lab")

# Initialize DB once
if "db_init_done" not in st.session_state:
    init_db()
    st.session_state["db_init_done"] = True

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
                st.rerun()
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
                st.rerun()
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
            users = [u for u in users if u != "admin"]

            if users:
                user_to_delete = st.selectbox("Select user", users)
                confirm = st.checkbox(f"Confirm delete `{user_to_delete}`")

                if st.button("Delete User"):
                    if confirm:
                        try:
                            delete_user(user_to_delete)
                            st.success(f"User `{user_to_delete}` deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting user: {str(e)}")
                    else:
                        st.warning("Please confirm deletion first.")
            else:
                st.info("No users found.")


        with tabs[2]:
            st.write("Execute SQL on admin database:")
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
                # Admin runs without strict user checks
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