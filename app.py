from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "development-secret-change-later"

DATABASE = "ddo_inventory.db"

MAX_USERNAME_LENGTH = 30
MAX_ITEM_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 2000
MAX_ATTRIBUTES_PER_ITEM = 30
MAX_ITEMS_PER_USER = 1000
MAX_REQUEST_SIZE = 100 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE


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

    admin_count = conn.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE is_admin = 1
    """).fetchone()[0]

    if admin_count == 0:

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

                conn.commit()

                session.clear()

                session["user_id"] = cursor.lastrowid
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
            item_types.name AS item_type
        FROM items
        JOIN item_types
            ON items.item_type_id =
               item_types.id
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

    conn.close()

    return render_template(
        "inventory.html",
        username=session["username"],
        items=items,
        item_attributes=item_attributes,
        current_sort=sort,
        current_direction=direction,
        is_admin=current_user_is_admin()
    )


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

    if request.method == "POST":

        name = request.form["name"].strip()

        item_type_id = request.form["item_type"]

        minimum_level = request.form[
            "minimum_level"
        ].strip()

        description = request.form[
            "description"
        ].strip()

        if not name:

            conn.close()

            return render_template(
                "new_item.html",
                item_types=item_types,
                attributes=attributes,
                error="Item name is required."
            )

        if len(name) > MAX_ITEM_NAME_LENGTH:

            conn.close()

            return render_template(
                "new_item.html",
                item_types=item_types,
                attributes=attributes,
                error=(
                    f"Item name must be "
                    f"{MAX_ITEM_NAME_LENGTH} "
                    "characters or fewer."
                )
            )

        if len(description) > MAX_DESCRIPTION_LENGTH:

            conn.close()

            return render_template(
                "new_item.html",
                item_types=item_types,
                attributes=attributes,
                error=(
                    f"Description must be "
                    f"{MAX_DESCRIPTION_LENGTH} "
                    "characters or fewer."
                )
            )

        item_count = conn.execute("""
            SELECT COUNT(*)
            FROM items
            WHERE user_id = ?
        """, (
            session["user_id"],
        )).fetchone()[0]

        if item_count >= MAX_ITEMS_PER_USER:

            conn.close()

            return render_template(
                "new_item.html",
                item_types=item_types,
                attributes=attributes,
                error=(
                    "Your inventory has reached the "
                    f"maximum of {MAX_ITEMS_PER_USER} "
                    "items."
                )
            )

        item_type = conn.execute("""
            SELECT id
            FROM item_types
            WHERE id = ?
        """, (
            item_type_id,
        )).fetchone()

        if not item_type:

            conn.close()

            return render_template(
                "new_item.html",
                item_types=item_types,
                attributes=attributes,
                error="Invalid item type."
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

            conn.close()

            return render_template(
                "new_item.html",
                item_types=item_types,
                attributes=attributes,
                error=(
                    "Too many attributes. "
                    f"The maximum is "
                    f"{MAX_ATTRIBUTES_PER_ITEM}."
                )
            )

        seen_attribute_ids = set()
        validated_attributes = []

        for attribute_id, value in submitted_attributes:

            if attribute_id in seen_attribute_ids:

                conn.close()

                return render_template(
                    "new_item.html",
                    item_types=item_types,
                    attributes=attributes,
                    error=(
                        "The same attribute cannot "
                        "be added more than once."
                    )
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

                conn.close()

                return render_template(
                    "new_item.html",
                    item_types=item_types,
                    attributes=attributes,
                    error="Invalid attribute."
                )

            if attribute["value_type"] == "number":

                if not value:

                    conn.close()

                    return render_template(
                        "new_item.html",
                        item_types=item_types,
                        attributes=attributes,
                        error=(
                            f"{attribute['name']} "
                            "requires a numeric value."
                        )
                    )

                try:

                    numeric_value = int(value)

                except ValueError:

                    conn.close()

                    return render_template(
                        "new_item.html",
                        item_types=item_types,
                        attributes=attributes,
                        error=(
                            f"{attribute['name']} "
                            "requires a whole number."
                        )
                    )

                if numeric_value <= 0:

                    conn.close()

                    return render_template(
                        "new_item.html",
                        item_types=item_types,
                        attributes=attributes,
                        error=(
                            f"{attribute['name']} "
                            "must have a value greater than zero."
                        )
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
                description
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            name,
            item_type_id,
            minimum_level or None,
            description
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
        attributes=attributes
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
        debug=True,
        host="127.0.0.1",
        port=5000
    )