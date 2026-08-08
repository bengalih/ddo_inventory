from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    abort
)
import os
import secrets
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

DATABASE = "ddo_inventory.db"

MAX_USERNAME_LENGTH = 30
MAX_ITEM_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 2000
MAX_ATTRIBUTES_PER_ITEM = 30
MAX_ITEMS_PER_USER = 1000
MAX_REQUEST_SIZE = 100 * 1024
MAX_SEARCH_CONDITIONS = 10
MAX_SEARCH_RESULTS = 200
MIN_MINIMUM_LEVEL = 1
MAX_MINIMUM_LEVEL = 36
MAX_CHARACTER_NAME_LENGTH = 50

DDO_SERVERS = [
    "Cormyr",
    "Moonsea",
    "Shadowdale",
    "Thrane"
]

OPERATORS = {
    "gte": ">=",
    "lte": "<=",
    "eq": "=",
    "gt": ">",
    "lt": "<"
}

app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE

DEBUG_MODE = os.environ.get(
    "DDO_DEBUG", "false"
).strip().lower() == "true"


def get_or_create_secret_key():

    env_key = os.environ.get("DDO_SECRET_KEY")

    if env_key:
        return env_key

    key_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "secret_key.txt"
    )

    if os.path.exists(key_path):

        with open(key_path, "r") as key_file:
            existing_key = key_file.read().strip()

        if existing_key:
            return existing_key

    new_key = secrets.token_hex(32)

    with open(key_path, "w") as key_file:
        key_file.write(new_key)

    return new_key


app.secret_key = get_or_create_secret_key()


def get_csrf_token():

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def enforce_csrf():

    if request.method != "POST":
        return

    submitted_token = request.form.get("csrf_token", "")
    session_token = session.get("csrf_token", "")

    if not session_token or not secrets.compare_digest(
        submitted_token, session_token
    ):
        abort(400)


CHARACTER_GATE_EXEMPT_ENDPOINTS = {
    "index",
    "login",
    "logout",
    "register",
    "characters",
    "characters_add",
    "static"
}


@app.before_request
def enforce_character_gate():

    if "user_id" not in session:
        return

    if request.endpoint in CHARACTER_GATE_EXEMPT_ENDPOINTS:
        return

    if request.endpoint is None:
        return

    conn = get_db()

    character_count = conn.execute("""
        SELECT COUNT(*)
        FROM characters
        WHERE user_id = ?
    """, (session["user_id"],)).fetchone()[0]

    conn.close()

    if character_count == 0:
        return redirect(url_for("characters"))


def escape_like(value):

    return (
        value.replace("\\", "\\\\")
             .replace("%", "\\%")
             .replace("_", "\\_")
    )


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    columns = conn.execute(
        "PRAGMA table_info(users)"
    ).fetchall()

    column_names = [column["name"] for column in columns]

    if "is_admin" not in column_names:

        conn.execute("""
            ALTER TABLE users
            ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0
        """)

        # One-time migration safety net: if this database
        # predates the is_admin column, promote the earliest
        # existing user so there's still a way into /admin.
        # Going forward, admin bootstrapping happens at
        # registration time instead (see register()).
        first_user = conn.execute("""
            SELECT id
            FROM users
            ORDER BY id
            LIMIT 1
        """).fetchone()

        if first_user:
            conn.execute("""
                UPDATE users
                SET is_admin = 1
                WHERE id = ?
            """, (first_user["id"],))

    if "is_public" not in column_names:
        conn.execute("""
            ALTER TABLE users
            ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            server TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (user_id)
                REFERENCES users(id),

            UNIQUE(user_id, name, server)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            value_type TEXT NOT NULL DEFAULT 'none'
        )
    """)

    attribute_columns = conn.execute(
        "PRAGMA table_info(attributes)"
    ).fetchall()

    attribute_column_names = [
        column["name"] for column in attribute_columns
    ]

    if "value_type" not in attribute_column_names:
        conn.execute("""
            ALTER TABLE attributes
            ADD COLUMN value_type TEXT NOT NULL DEFAULT 'none'
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            item_type_id INTEGER NOT NULL,
            minimum_level INTEGER,
            description TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id),

            FOREIGN KEY (item_type_id)
                REFERENCES item_types(id)
        )
    """)

    item_columns = conn.execute(
        "PRAGMA table_info(items)"
    ).fetchall()

    item_column_names = [
        column["name"] for column in item_columns
    ]

    if "character_id" not in item_column_names:
        conn.execute("""
            ALTER TABLE items
            ADD COLUMN character_id INTEGER
            REFERENCES characters(id)
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            attribute_id INTEGER NOT NULL,
            value TEXT,

            FOREIGN KEY (item_id)
                REFERENCES items(id),

            FOREIGN KEY (attribute_id)
                REFERENCES attributes(id),

            UNIQUE(item_id, attribute_id)
        )
    """)

    item_types = [
        "Helmet",
        "Necklace",
        "Trinket",
        "Cloak",
        "Belt",
        "Gloves",
        "Boots",
        "Bracers",
        "Ring",
        "Goggles",
        "Armor",
        "Shield",
        "Weapon",
        "Bow",
        "Quiver"
    ]

    for name in item_types:
        conn.execute(
            """
            INSERT OR IGNORE INTO item_types (name)
            VALUES (?)
            """,
            (name,)
        )

    attributes = [
        ("Deadly", "number"),
        ("Seeker", "number"),
        ("Accuracy", "number"),
        ("Insightful Dexterity", "number"),
        ("Ghost Touch", "none"),
        ("Ghostly", "none"),
        ("Feather Falling", "none"),
        ("Red Augment Slot", "none"),
        ("Yellow Augment Slot", "none"),
        ("Blue Augment Slot", "none")
    ]

    for name, value_type in attributes:
        conn.execute(
            """
            INSERT OR IGNORE INTO attributes (
                name,
                value_type
            )
            VALUES (?, ?)
            """,
            (name, value_type)
        )

    conn.execute("""
        UPDATE attributes
        SET value_type = 'number'
        WHERE name IN (
            'Deadly',
            'Seeker',
            'Accuracy',
            'Insightful Dexterity'
        )
    """)

    conn.execute("""
        UPDATE attributes
        SET value_type = 'none'
        WHERE name IN (
            'Ghost Touch',
            'Ghostly',
            'Feather Falling',
            'Red Augment Slot',
            'Yellow Augment Slot',
            'Blue Augment Slot'
        )
    """)

    conn.commit()
    conn.close()


def current_user_is_admin():

    user_id = session.get("user_id")

    if not user_id:
        return False

    conn = get_db()

    user = conn.execute("""
        SELECT is_admin
        FROM users
        WHERE id = ?
    """, (user_id,)).fetchone()

    conn.close()

    return bool(
        user and user["is_admin"] == 1
    )


def admin_required():
    return current_user_is_admin()


def current_user_is_public():

    user_id = session.get("user_id")

    if not user_id:
        return False

    conn = get_db()

    user = conn.execute("""
        SELECT is_public
        FROM users
        WHERE id = ?
    """, (user_id,)).fetchone()

    conn.close()

    return bool(
        user and user["is_public"] == 1
    )


def get_user_characters(conn, user_id):

    return conn.execute("""
        SELECT *
        FROM characters
        WHERE user_id = ?
        ORDER BY is_default DESC, name
    """, (user_id,)).fetchall()


def get_item_attributes(conn, item_id):

    return conn.execute("""
        SELECT
            attributes.name,
            attributes.value_type,
            item_attributes.value
        FROM item_attributes
        JOIN attributes
            ON item_attributes.attribute_id =
               attributes.id
        WHERE item_attributes.item_id = ?
        ORDER BY attributes.name
    """, (item_id,)).fetchall()


@app.route("/")
def index():

    if "user_id" in session:
        return redirect(url_for("inventory"))

    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    error = None

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:

            error = "Username and password are required."

        elif len(username) > MAX_USERNAME_LENGTH:

            error = (
                f"Username must be {MAX_USERNAME_LENGTH} "
                "characters or fewer."
            )

        elif len(password) < 8:

            error = "Password must be at least 8 characters."

        else:

            conn = get_db()

            try:

                existing_user_count = conn.execute("""
                    SELECT COUNT(*)
                    FROM users
                """).fetchone()[0]

                cursor = conn.execute("""
                    INSERT INTO users (
                        username,
                        password_hash
                    )
                    VALUES (?, ?)
                """, (
                    username,
                    generate_password_hash(password)
                ))

                new_user_id = cursor.lastrowid

                if existing_user_count == 0:
                    conn.execute("""
                        UPDATE users
                        SET is_admin = 1
                        WHERE id = ?
                    """, (new_user_id,))

                conn.commit()

                session.clear()

                session["user_id"] = new_user_id
                session["username"] = username

                return redirect(
                    url_for("inventory")
                )

            except sqlite3.IntegrityError:

                error = "That username is already taken."

            finally:

                conn.close()

    return render_template(
        "register.html",
        error=error
    )


@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE username = ?
        """, (username,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(
                url_for("inventory")
            )

        error = "Invalid username or password."

    return render_template(
        "login.html",
        error=error
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


@app.route("/inventory")
def inventory():

    if "user_id" not in session:
        return redirect(url_for("login"))

    sort = request.args.get("sort", "name")
    direction = request.args.get("direction", "asc")

    allowed_sorts = {
        "name": "items.name",
        "type": "item_types.name",
        "minimum_level": "items.minimum_level"
    }

    if sort not in allowed_sorts:
        sort = "name"

    if direction not in ("asc", "desc"):
        direction = "asc"

    conn = get_db()

    items = conn.execute(
        f"""
        SELECT
            items.id,
            items.name,
            items.minimum_level,
            items.description,
            item_types.name AS item_type,
            characters.name AS character_name,
            characters.server AS character_server
        FROM items
        JOIN item_types
            ON items.item_type_id =
               item_types.id
        LEFT JOIN characters
            ON items.character_id =
               characters.id
        WHERE items.user_id = ?
        ORDER BY
            {allowed_sorts[sort]}
            {direction},
            items.name
        """,
        (session["user_id"],)
    ).fetchall()

    item_attributes = {}

    for item in items:
        item_attributes[item["id"]] = (
            get_item_attributes(
                conn,
                item["id"]
            )
        )

    user_characters = get_user_characters(
        conn, session["user_id"]
    )

    conn.close()

    return render_template(
        "inventory.html",
        username=session["username"],
        items=items,
        item_attributes=item_attributes,
        current_sort=sort,
        current_direction=direction,
        is_admin=current_user_is_admin(),
        is_public=current_user_is_public(),
        user_characters=user_characters
    )


@app.route("/settings/visibility", methods=["POST"])
def toggle_visibility():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute("""
        UPDATE users
        SET is_public = CASE
            WHEN is_public = 1 THEN 0
            ELSE 1
        END
        WHERE id = ?
    """, (session["user_id"],))

    conn.commit()
    conn.close()

    return redirect(url_for("inventory"))


@app.route("/items/reassign", methods=["POST"])
def reassign_items():

    if "user_id" not in session:
        return redirect(url_for("login"))

    item_ids = request.form.getlist("item_ids")
    character_id = request.form.get("character_id", "").strip()

    if not item_ids:
        return redirect(url_for("inventory"))

    conn = get_db()

    destination = None

    if character_id:

        character = conn.execute("""
            SELECT id
            FROM characters
            WHERE id = ?
            AND user_id = ?
        """, (
            character_id,
            session["user_id"]
        )).fetchone()

        if not character:
            conn.close()
            return redirect(url_for("inventory"))

        destination = character_id

    placeholders = ",".join("?" for _ in item_ids)

    conn.execute(
        f"""
        UPDATE items
        SET character_id = ?
        WHERE user_id = ?
        AND id IN ({placeholders})
        """,
        [destination, session["user_id"]] + item_ids
    )

    conn.commit()
    conn.close()

    return redirect(url_for("inventory"))


@app.route("/item/new", methods=["GET", "POST"])
def new_item():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    item_types = conn.execute("""
        SELECT *
        FROM item_types
        ORDER BY name
    """).fetchall()

    attributes = conn.execute("""
        SELECT *
        FROM attributes
        ORDER BY name
    """).fetchall()

    user_characters = get_user_characters(
        conn, session["user_id"]
    )

    def render_error(error):
        conn.close()
        return render_template(
            "new_item.html",
            item_types=item_types,
            attributes=attributes,
            user_characters=user_characters,
            error=error
        )

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        item_type_id = request.form.get("item_type", "")

        character_id = request.form.get(
            "character_id", ""
        ).strip()

        minimum_level_raw = request.form.get(
            "minimum_level", ""
        ).strip()

        description = request.form.get(
            "description", ""
        ).strip()

        minimum_level = None

        if minimum_level_raw:

            try:
                minimum_level = int(minimum_level_raw)

            except ValueError:
                return render_error(
                    "Minimum level must be a whole number."
                )

            if (
                minimum_level < MIN_MINIMUM_LEVEL
                or minimum_level > MAX_MINIMUM_LEVEL
            ):
                return render_error(
                    "Minimum level must be between "
                    f"{MIN_MINIMUM_LEVEL} and "
                    f"{MAX_MINIMUM_LEVEL}."
                )

        if not name:
            return render_error("Item name is required.")

        if len(name) > MAX_ITEM_NAME_LENGTH:
            return render_error(
                f"Item name must be "
                f"{MAX_ITEM_NAME_LENGTH} "
                "characters or fewer."
            )

        if len(description) > MAX_DESCRIPTION_LENGTH:
            return render_error(
                f"Description must be "
                f"{MAX_DESCRIPTION_LENGTH} "
                "characters or fewer."
            )

        item_count = conn.execute("""
            SELECT COUNT(*)
            FROM items
            WHERE user_id = ?
        """, (
            session["user_id"],
        )).fetchone()[0]

        if item_count >= MAX_ITEMS_PER_USER:
            return render_error(
                "Your inventory has reached the "
                f"maximum of {MAX_ITEMS_PER_USER} "
                "items."
            )

        item_type = conn.execute("""
            SELECT id
            FROM item_types
            WHERE id = ?
        """, (
            item_type_id,
        )).fetchone()

        if not item_type:
            return render_error("Invalid item type.")

        character = None

        if character_id:
            character = conn.execute("""
                SELECT id
                FROM characters
                WHERE id = ?
                AND user_id = ?
            """, (
                character_id,
                session["user_id"]
            )).fetchone()

        if not character:
            return render_error(
                "Please choose which character has this item."
            )

        # The HTML now sends one attribute_id field
        # and one attribute_value field for each row.
        #
        # getlist() retrieves all of those independent rows.
        attribute_ids = request.form.getlist(
            "attribute_id"
        )

        attribute_values = request.form.getlist(
            "attribute_value"
        )

        submitted_attributes = []

        for index, attribute_id in enumerate(
            attribute_ids
        ):

            if not attribute_id:
                continue

            value = ""

            if index < len(attribute_values):
                value = attribute_values[index].strip()

            submitted_attributes.append(
                (
                    attribute_id,
                    value
                )
            )

        if len(submitted_attributes) > MAX_ATTRIBUTES_PER_ITEM:
            return render_error(
                "Too many attributes. "
                f"The maximum is "
                f"{MAX_ATTRIBUTES_PER_ITEM}."
            )

        seen_attribute_ids = set()
        validated_attributes = []

        for attribute_id, value in submitted_attributes:

            if attribute_id in seen_attribute_ids:
                return render_error(
                    "The same attribute cannot "
                    "be added more than once."
                )

            seen_attribute_ids.add(attribute_id)

            attribute = conn.execute("""
                SELECT *
                FROM attributes
                WHERE id = ?
            """, (
                attribute_id,
            )).fetchone()

            if not attribute:
                return render_error("Invalid attribute.")

            if attribute["value_type"] == "number":

                if not value:
                    return render_error(
                        f"{attribute['name']} "
                        "requires a numeric value."
                    )

                try:

                    numeric_value = int(value)

                except ValueError:
                    return render_error(
                        f"{attribute['name']} "
                        "requires a whole number."
                    )

                if numeric_value <= 0:
                    return render_error(
                        f"{attribute['name']} "
                        "must have a value greater than zero."
                    )

                value = str(numeric_value)

            else:

                value = None

            validated_attributes.append(
                (
                    attribute["id"],
                    value
                )
            )

        cursor = conn.execute("""
            INSERT INTO items (
                user_id,
                name,
                item_type_id,
                minimum_level,
                description,
                character_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            name,
            item_type_id,
            minimum_level,
            description,
            character_id
        ))

        item_id = cursor.lastrowid

        for attribute_id, value in validated_attributes:

            conn.execute("""
                INSERT INTO item_attributes (
                    item_id,
                    attribute_id,
                    value
                )
                VALUES (?, ?, ?)
            """, (
                item_id,
                attribute_id,
                value
            ))

        conn.commit()
        conn.close()

        return redirect(
            url_for("inventory")
        )

    conn.close()

    return render_template(
        "new_item.html",
        item_types=item_types,
        attributes=attributes,
        user_characters=user_characters
    )


@app.route("/search")
def search():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    item_types = conn.execute("""
        SELECT *
        FROM item_types
        ORDER BY name
    """).fetchall()

    attributes = conn.execute("""
        SELECT *
        FROM attributes
        ORDER BY name
    """).fetchall()

    attribute_lookup = {
        str(attribute["id"]): attribute
        for attribute in attributes
    }

    error = None
    results = []
    result_attributes = {}

    if request.args:

        name = request.args.get("name", "").strip()
        item_type_id = request.args.get("item_type", "").strip()
        level_min = request.args.get("level_min", "").strip()
        level_max = request.args.get("level_max", "").strip()
        server = request.args.get("server", "").strip()
        character_name = request.args.get(
            "character_name", ""
        ).strip()

        conditions = [
            "(items.user_id = ? OR users.is_public = 1)"
        ]
        params = [session["user_id"]]

        if not error and name:

            if len(name) > MAX_ITEM_NAME_LENGTH:
                error = (
                    f"Item name must be "
                    f"{MAX_ITEM_NAME_LENGTH} "
                    "characters or fewer."
                )
            else:
                conditions.append(
                    "items.name LIKE ? ESCAPE '\\'"
                )
                params.append(f"%{escape_like(name)}%")

        if not error and item_type_id:

            item_type = conn.execute("""
                SELECT id
                FROM item_types
                WHERE id = ?
            """, (item_type_id,)).fetchone()

            if not item_type:
                error = "Invalid item type."
            else:
                conditions.append(
                    "items.item_type_id = ?"
                )
                params.append(item_type_id)

        if not error and server:

            if server not in DDO_SERVERS:
                error = "Invalid server."
            else:
                conditions.append(
                    "characters.server = ?"
                )
                params.append(server)

        if not error and character_name:

            if len(character_name) > MAX_CHARACTER_NAME_LENGTH:
                error = (
                    "Character name must be "
                    f"{MAX_CHARACTER_NAME_LENGTH} "
                    "characters or fewer."
                )
            else:
                conditions.append(
                    "characters.name LIKE ? ESCAPE '\\'"
                )
                params.append(
                    f"%{escape_like(character_name)}%"
                )

        if not error and level_min:

            try:
                level_min_value = int(level_min)
                conditions.append(
                    "items.minimum_level >= ?"
                )
                params.append(level_min_value)

            except ValueError:
                error = "Minimum level must be a whole number."

        if not error and level_max:

            try:
                level_max_value = int(level_max)
                conditions.append(
                    "items.minimum_level <= ?"
                )
                params.append(level_max_value)

            except ValueError:
                error = "Maximum level must be a whole number."

        attribute_ids = request.args.getlist("attribute_id")
        operators = request.args.getlist("operator")
        values = request.args.getlist("value")

        if not error and len(attribute_ids) > MAX_SEARCH_CONDITIONS:
            error = (
                "Too many attribute filters. "
                f"The maximum is {MAX_SEARCH_CONDITIONS}."
            )

        if not error:

            for index, attribute_id in enumerate(attribute_ids):

                if not attribute_id:
                    continue

                attribute = attribute_lookup.get(attribute_id)

                if not attribute:
                    error = "Invalid attribute filter."
                    break

                operator = (
                    operators[index]
                    if index < len(operators)
                    else ""
                )

                value = (
                    values[index].strip()
                    if index < len(values)
                    else ""
                )

                if attribute["value_type"] == "number":

                    if operator not in OPERATORS:
                        error = (
                            f"Invalid comparison for "
                            f"{attribute['name']}."
                        )
                        break

                    if not value:
                        error = (
                            f"{attribute['name']} filter "
                            "requires a value."
                        )
                        break

                    try:
                        numeric_value = int(value)

                    except ValueError:
                        error = (
                            f"{attribute['name']} filter "
                            "requires a whole number."
                        )
                        break

                    conditions.append(f"""
                        EXISTS (
                            SELECT 1
                            FROM item_attributes ia
                            WHERE ia.item_id = items.id
                            AND ia.attribute_id = ?
                            AND CAST(ia.value AS INTEGER)
                                {OPERATORS[operator]} ?
                        )
                    """)
                    params.append(attribute_id)
                    params.append(numeric_value)

                else:

                    conditions.append("""
                        EXISTS (
                            SELECT 1
                            FROM item_attributes ia
                            WHERE ia.item_id = items.id
                            AND ia.attribute_id = ?
                        )
                    """)
                    params.append(attribute_id)

        if not error:

            where_clause = " AND ".join(conditions)

            results = conn.execute(
                f"""
                SELECT
                    items.id,
                    items.name,
                    items.minimum_level,
                    items.description,
                    item_types.name AS item_type,
                    users.username AS owner,
                    characters.name AS character_name,
                    characters.server AS character_server
                FROM items
                JOIN item_types
                    ON items.item_type_id = item_types.id
                JOIN users
                    ON items.user_id = users.id
                LEFT JOIN characters
                    ON items.character_id = characters.id
                WHERE {where_clause}
                ORDER BY items.name
                LIMIT {MAX_SEARCH_RESULTS}
                """,
                params
            ).fetchall()

            for item in results:
                result_attributes[item["id"]] = (
                    get_item_attributes(conn, item["id"])
                )

    conn.close()

    return render_template(
        "search.html",
        item_types=item_types,
        attributes=attributes,
        results=results,
        result_attributes=result_attributes,
        error=error,
        filters=request.args,
        servers=DDO_SERVERS
    )


@app.route("/items/delete", methods=["POST"])
def delete_multiple_items():

    if "user_id" not in session:
        return redirect(url_for("login"))

    item_ids = request.form.getlist(
        "item_ids"
    )

    if not item_ids:
        return redirect(
            url_for("inventory")
        )

    conn = get_db()

    placeholders = ",".join(
        "?" for _ in item_ids
    )

    owned_items = conn.execute(
        f"""
        SELECT id
        FROM items
        WHERE user_id = ?
        AND id IN ({placeholders})
        """,
        [session["user_id"]] + item_ids
    ).fetchall()

    owned_ids = [
        str(item["id"])
        for item in owned_items
    ]

    if owned_ids:

        placeholders = ",".join(
            "?" for _ in owned_ids
        )

        conn.execute(
            f"""
            DELETE FROM item_attributes
            WHERE item_id IN ({placeholders})
            """,
            owned_ids
        )

        conn.execute(
            f"""
            DELETE FROM items
            WHERE user_id = ?
            AND id IN ({placeholders})
            """,
            [session["user_id"]] + owned_ids
        )

        conn.commit()

    conn.close()

    return redirect(
        url_for("inventory")
    )


@app.route("/characters")
def characters():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    user_characters = get_user_characters(
        conn, session["user_id"]
    )

    conn.close()

    return render_template(
        "characters.html",
        characters=user_characters,
        servers=DDO_SERVERS
    )


@app.route("/characters/add", methods=["POST"])
def characters_add():

    if "user_id" not in session:
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    server = request.form.get("server", "").strip()

    conn = get_db()

    def render_error(error):
        user_characters = get_user_characters(
            conn, session["user_id"]
        )
        conn.close()
        return render_template(
            "characters.html",
            characters=user_characters,
            servers=DDO_SERVERS,
            error=error
        )

    if not name:
        return render_error("Character name is required.")

    if len(name) > MAX_CHARACTER_NAME_LENGTH:
        return render_error(
            "Character name must be "
            f"{MAX_CHARACTER_NAME_LENGTH} "
            "characters or fewer."
        )

    if server not in DDO_SERVERS:
        return render_error("Invalid server.")

    existing_count = conn.execute("""
        SELECT COUNT(*)
        FROM characters
        WHERE user_id = ?
    """, (session["user_id"],)).fetchone()[0]

    is_first_character = existing_count == 0

    try:

        cursor = conn.execute("""
            INSERT INTO characters (
                user_id,
                name,
                server,
                is_default
            )
            VALUES (?, ?, ?, ?)
        """, (
            session["user_id"],
            name,
            server,
            1 if is_first_character else 0
        ))

        new_character_id = cursor.lastrowid

        if is_first_character:

            # Bootstrap: attach any items this user created
            # before characters existed to their first one.
            conn.execute("""
                UPDATE items
                SET character_id = ?
                WHERE user_id = ?
                AND character_id IS NULL
            """, (
                new_character_id,
                session["user_id"]
            ))

        conn.commit()

    except sqlite3.IntegrityError:
        return render_error(
            "You already have a character with that "
            "name on that server."
        )

    conn.close()

    return redirect(url_for("characters"))


@app.route(
    "/characters/<int:character_id>/default",
    methods=["POST"]
)
def characters_set_default(character_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    character = conn.execute("""
        SELECT id
        FROM characters
        WHERE id = ?
        AND user_id = ?
    """, (
        character_id,
        session["user_id"]
    )).fetchone()

    if character:

        conn.execute("""
            UPDATE characters
            SET is_default = 0
            WHERE user_id = ?
        """, (session["user_id"],))

        conn.execute("""
            UPDATE characters
            SET is_default = 1
            WHERE id = ?
        """, (character_id,))

        conn.commit()

    conn.close()

    return redirect(url_for("characters"))


@app.route(
    "/characters/<int:character_id>/delete",
    methods=["POST"]
)
def characters_delete(character_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    character = conn.execute("""
        SELECT *
        FROM characters
        WHERE id = ?
        AND user_id = ?
    """, (
        character_id,
        session["user_id"]
    )).fetchone()

    if not character:
        conn.close()
        return redirect(url_for("characters"))

    reassign_to = request.form.get(
        "reassign_to", ""
    ).strip()

    destination = None

    if reassign_to:

        destination_character = conn.execute("""
            SELECT id
            FROM characters
            WHERE id = ?
            AND user_id = ?
            AND id != ?
        """, (
            reassign_to,
            session["user_id"],
            character_id
        )).fetchone()

        if not destination_character:

            user_characters = get_user_characters(
                conn, session["user_id"]
            )
            conn.close()

            return render_template(
                "characters.html",
                characters=user_characters,
                servers=DDO_SERVERS,
                error="Invalid destination character."
            )

        destination = reassign_to

    conn.execute("""
        UPDATE items
        SET character_id = ?
        WHERE character_id = ?
    """, (destination, character_id))

    was_default = character["is_default"] == 1

    conn.execute("""
        DELETE FROM characters
        WHERE id = ?
    """, (character_id,))

    if was_default:

        remaining = conn.execute("""
            SELECT id
            FROM characters
            WHERE user_id = ?
            ORDER BY id
            LIMIT 1
        """, (session["user_id"],)).fetchone()

        if remaining:
            conn.execute("""
                UPDATE characters
                SET is_default = 1
                WHERE id = ?
            """, (remaining["id"],))

    conn.commit()
    conn.close()

    return redirect(url_for("characters"))


@app.route("/admin")
def admin():

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    conn = get_db()

    attributes = conn.execute("""
        SELECT
            attributes.id,
            attributes.name,
            attributes.value_type,
            COUNT(item_attributes.id)
                AS usage_count
        FROM attributes
        LEFT JOIN item_attributes
            ON attributes.id =
               item_attributes.attribute_id
        GROUP BY attributes.id
        ORDER BY attributes.name
    """).fetchall()

    item_types = conn.execute("""
        SELECT
            item_types.id,
            item_types.name,
            COUNT(items.id)
                AS usage_count
        FROM item_types
        LEFT JOIN items
            ON item_types.id =
               items.item_type_id
        GROUP BY item_types.id
        ORDER BY item_types.name
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        attributes=attributes,
        item_types=item_types
    )


@app.route(
    "/admin/attribute/add",
    methods=["POST"]
)
def admin_add_attribute():

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    name = request.form[
        "name"
    ].strip()

    value_type = request.form.get(
        "value_type",
        "none"
    )

    if value_type not in (
        "none",
        "number"
    ):
        value_type = "none"

    if name:

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO attributes (
                    name,
                    value_type
                )
                VALUES (?, ?)
            """, (
                name,
                value_type
            ))

            conn.commit()

        except sqlite3.IntegrityError:
            pass

        finally:
            conn.close()

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/attribute/edit/<int:attribute_id>",
    methods=["POST"]
)
def admin_edit_attribute(attribute_id):

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    name = request.form[
        "name"
    ].strip()

    value_type = request.form.get(
        "value_type",
        "none"
    )

    if value_type not in (
        "none",
        "number"
    ):
        value_type = "none"

    if name:

        conn = get_db()

        try:

            conn.execute("""
                UPDATE attributes
                SET
                    name = ?,
                    value_type = ?
                WHERE id = ?
            """, (
                name,
                value_type,
                attribute_id
            ))

            conn.commit()

        except sqlite3.IntegrityError:
            pass

        finally:
            conn.close()

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/attribute/delete/<int:attribute_id>",
    methods=["POST"]
)
def admin_delete_attribute(attribute_id):

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    conn = get_db()

    usage = conn.execute("""
        SELECT COUNT(*)
        FROM item_attributes
        WHERE attribute_id = ?
    """, (
        attribute_id,
    )).fetchone()[0]

    if usage == 0:

        conn.execute("""
            DELETE FROM attributes
            WHERE id = ?
        """, (
            attribute_id,
        ))

        conn.commit()

    conn.close()

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/item-type/add",
    methods=["POST"]
)
def admin_add_item_type():

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    name = request.form[
        "name"
    ].strip()

    if name:

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO item_types (
                    name
                )
                VALUES (?)
            """, (
                name,
            ))

            conn.commit()

        except sqlite3.IntegrityError:
            pass

        finally:
            conn.close()

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/item-type/edit/<int:item_type_id>",
    methods=["POST"]
)
def admin_edit_item_type(item_type_id):

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    name = request.form[
        "name"
    ].strip()

    if name:

        conn = get_db()

        try:

            conn.execute("""
                UPDATE item_types
                SET name = ?
                WHERE id = ?
            """, (
                name,
                item_type_id
            ))

            conn.commit()

        except sqlite3.IntegrityError:
            pass

        finally:
            conn.close()

    return redirect(
        url_for("admin")
    )


@app.route(
    "/admin/item-type/delete/<int:item_type_id>",
    methods=["POST"]
)
def admin_delete_item_type(item_type_id):

    if not admin_required():
        return redirect(
            url_for("inventory")
        )

    conn = get_db()

    usage = conn.execute("""
        SELECT COUNT(*)
        FROM items
        WHERE item_type_id = ?
    """, (
        item_type_id,
    )).fetchone()[0]

    if usage == 0:

        conn.execute("""
            DELETE FROM item_types
            WHERE id = ?
        """, (
            item_type_id,
        ))

        conn.commit()

    conn.close()

    return redirect(
        url_for("admin")
    )


if __name__ == "__main__":

    init_db()

    app.run(
        debug=DEBUG_MODE,
        host="127.0.0.1",
        port=5000
    )