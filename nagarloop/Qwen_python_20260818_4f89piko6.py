import brand
from flask import session, request

@app.context_processor
def i18n():
    lang = session.get("lang", "en")
    return {"lang": lang, "BRAND": brand.BRAND, "CITY": brand.CITY,
            "SLOGAN": brand.SLOGAN, "SUPPORT_EMAIL": brand.SUPPORT_EMAIL,
            "tr": lambda k: brand.T.get(k, {}).get(lang, k)}

@app.post("/set-lang")
def set_lang():
    session["lang"] = request.form.get("lang", "en")
    return redirect(request.referrer or "/")

@app.get("/")
def home(): return render_template("home.html")

@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ("citizen", "driver", "admin"): abort(404)
    error = None
    if request.method == "POST":
        u = query("SELECT * FROM users WHERE username=? AND role=?",
                  (request.form["username"], role), one=True)
        if u and u["password"] == request.form["password"]:
            session.update(role=role, user_id=u["id"], name=u["name"])
            return redirect({"citizen": "/book", "driver": "/driver", "admin": "/admin"}[role])
        error = "Wrong username or password"
    return render_template("login.html", role=role, error=error)

@app.get("/logout")
def logout():
    session.clear(); return redirect("/")

@app.get("/privacy")
def privacy(): return render_template("legal.html", page="privacy", title="Privacy Policy")
@app.get("/rewards")
def rewards(): return render_template("legal.html", page="rewards", title="Reward Policy")
@app.get("/help")
def help_pg(): return render_template("legal.html", page="help", title="Help & Support")