import pandas as pd
import re
import unicodedata

import streamlit as st
from supabase import create_client

# ---------- À PERSONNALISER ----------
TITRE = "🎂 Anniversaire de Mémé"
INFOS = "Date, heure et lieu : à compléter"  # mets "" pour ne rien afficher
CATEGORIES = [
    "🥜 Apéro",
    "🧀 Fromage",
    "🥤 Boisson",
    "🥗 Entrée",
    "🍝 Plat",
    "🍰 Dessert",
    "➕ Autre",
]
# -------------------------------------

TABLE = "invites"
MAX_PERSONNES = 10

st.set_page_config(page_title="Anniversaire", page_icon="🎂", layout="centered")

# Gros textes, gros champs, gros boutons (public âgé)
st.markdown(
    """
    <style>
    .stApp p, .stApp li, .stApp label p { font-size: 22px !important; }
    .stTextInput input, .stNumberInput input { font-size: 22px !important; min-height: 3.2rem; }
    .stButton > button, .stDownloadButton > button {
        font-size: 24px; min-height: 3.5rem; width: 100%; border-radius: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def base():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


@st.cache_data(ttl=15)
def tous():
    return base().table(TABLE).select("*").order("created_at").execute().data


# ---------- Outils ----------
def normaliser(texte):
    """Minuscules, sans accents ni ponctuation : 'Éloïse ' == 'eloise'."""
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def cle(prenom, nom):
    return f"{normaliser(prenom)}|{normaliser(nom)}"


def propre(texte):
    return " ".join(texte.split()).title()


def affichage(prenom, nom):
    return f"{propre(prenom)} {propre(nom)}"


def aller(page):
    st.session_state.page = page
    st.rerun()


def champs_personnes(prefixe, n):
    personnes = []
    for i in range(int(n)):
        st.markdown(f"**Personne {i + 1}**")
        p = st.text_input("Prénom", key=f"{prefixe}_p{i}")
        q = st.text_input("Nom de famille", key=f"{prefixe}_q{i}")
        personnes.append((p, q))
    return personnes


def incomplet(personnes):
    return any(not p.strip() or not q.strip() for p, q in personnes)


def deja_pris():
    """{catégorie: ['Romain : chips', ...]} pour les personnes qui viennent."""
    pris = {}
    for r in tous():
        if r["vient"]:
            for a in r.get("apports") or []:
                pris.setdefault(a["categorie"], []).append(f'{r["prenom"]} : {a["detail"]}')
    return pris


def texte_apports(r):
    return " ; ".join(f'{a["categorie"]} : {a["detail"]}' for a in r.get("apports") or [])


# ---------- Enregistrement ----------
def enregistrer(personnes, vient, apports=None):
    """personnes : liste de (prénom, nom). La première est la personne principale."""
    if incomplet(personnes):
        st.error("Merci d'écrire le prénom et le nom de chaque personne.")
        return False

    cles = [cle(p, q) for p, q in personnes]
    if len(set(cles)) != len(cles):
        st.error("Deux personnes ont le même nom. Merci de vérifier.")
        return False

    try:
        existants = (
            base().table(TABLE).select("cle,prenom,nom").in_("cle", cles).execute().data
        )
    except Exception:
        st.error("Un problème est survenu. Merci de réessayer dans un instant.")
        return False
    if existants:
        noms = ", ".join(sorted({affichage(r["prenom"], r["nom"]) for r in existants}))
        st.error(
            f"⚠️ {noms} : déjà inscrit(e) dans la liste. "
            "Pour changer la réponse, utilisez d'abord « Je me désiste », "
            "puis inscrivez-vous de nouveau."
        )
        return False

    lignes = [
        {
            "cle": k,
            "prenom": propre(p),
            "nom": propre(q),
            "vient": vient,
            "apports": (apports or []) if i == 0 else [],
            "groupe": cles[0],
        }
        for i, (k, (p, q)) in enumerate(zip(cles, personnes))
    ]
    try:
        base().table(TABLE).insert(lignes).execute()
    except Exception:
        st.error("Un problème est survenu. Merci de réessayer dans un instant.")
        return False
    tous.clear()
    return True


# ---------- Pages ----------
def page_accueil():
    st.title(TITRE)
    if INFOS:
        st.write(INFOS)
    st.write("### Que souhaitez-vous faire ?")
    if st.button("✅ Je viens"):
        aller("oui")
    if st.button("❌ Je ne peux pas venir"):
        aller("non")
    if st.button("↩️ Je me désiste"):
        aller("desistement")
    if st.button("📋 Voir qui vient et ce qu'on apporte"):
        aller("liste")
    st.write("")
    espace_organisateur()


def page_oui():
    st.header("✅ Je viens !")
    prenom = st.text_input("Votre prénom", key="oui_prenom")
    nom = st.text_input("Votre nom de famille", key="oui_nom")

    st.write("### Que souhaitez-vous apporter ?")
    st.write("Cochez une ou plusieurs catégories. Ce qui est déjà pris est indiqué.")
    pris = deja_pris()
    apports, manque = [], []
    for cat in CATEGORIES:
        coche = st.checkbox(cat, key=f"cat_{cat}")
        if pris.get(cat):
            st.markdown("👀 *Déjà pris — " + " · ".join(pris[cat]) + "*")
        if coche:
            detail = st.text_input(
                f"Quoi exactement ? ({cat})",
                key=f"detail_{cat}",
                placeholder="ex : chips, saucisson...",
            )
            if detail.strip():
                apports.append({"categorie": cat, "detail": detail.strip()})
            else:
                manque.append(cat)

    n = st.number_input(
        "Combien de personnes viennent avec vous ?",
        min_value=0, max_value=MAX_PERSONNES, value=0, step=1, key="oui_n",
    )
    accompagnants = champs_personnes("oui", n)

    if st.button("📨 Envoyer ma réponse", type="primary"):
        if manque:
            st.error("Précisez ce que vous apportez pour : " + ", ".join(manque))
        elif enregistrer([(prenom, nom)] + accompagnants, True, apports):
            total = 1 + len(accompagnants)
            st.session_state.merci = {
                "titre": "C'est enregistré, merci !",
                "texte": f"Nous avons bien noté {total} personne(s). À bientôt !",
            }
            aller("merci")
    if st.button("⬅️ Retour"):
        aller("accueil")


def page_non():
    st.header("❌ Je ne peux pas venir")
    prenom = st.text_input("Votre prénom", key="non_prenom")
    nom = st.text_input("Votre nom de famille", key="non_nom")
    if st.button("📨 Envoyer ma réponse", type="primary"):
        if enregistrer([(prenom, nom)], False):
            st.session_state.merci = {
                "titre": "C'est noté, merci de nous avoir prévenus.",
                "texte": "Dommage, vous nous manquerez !",
            }
            aller("merci")
    if st.button("⬅️ Retour"):
        aller("accueil")


def page_desistement():
    st.header("↩️ Je me désiste")
    st.write(
        "Écrivez votre nom, puis ajoutez les autres personnes qui ne viennent plus "
        "(vos enfants, par exemple)."
    )
    prenom = st.text_input("Votre prénom", key="des_prenom")
    nom = st.text_input("Votre nom de famille", key="des_nom")
    n = st.number_input(
        "Combien d'autres personnes ne viennent plus ?",
        min_value=0, max_value=MAX_PERSONNES, value=0, step=1, key="des_n",
    )
    autres = champs_personnes("des", n)

    if st.button("Confirmer mon désistement", type="primary"):
        personnes = [(prenom, nom)] + autres
        if incomplet(personnes):
            st.error("Merci d'écrire le prénom et le nom de chaque personne.")
        else:
            cles = [cle(p, q) for p, q in personnes]
            try:
                supprimes = base().table(TABLE).delete().in_("cle", cles).execute().data
            except Exception:
                st.error("Un problème est survenu. Merci de réessayer dans un instant.")
                return
            tous.clear()
            trouves = {r["cle"] for r in supprimes}
            retires = [affichage(p, q) for (p, q), k in zip(personnes, cles) if k in trouves]
            absents = [affichage(p, q) for (p, q), k in zip(personnes, cles) if k not in trouves]
            if not retires:
                st.error(
                    "Je n'ai trouvé personne avec ce nom dans la liste. "
                    "Vérifiez l'orthographe."
                )
            else:
                st.session_state.merci = {
                    "titre": "Désistement enregistré.",
                    "texte": "Retiré(s) de la liste : " + ", ".join(retires) + ".",
                    "alerte": (
                        "Non trouvé(s) dans la liste : " + ", ".join(absents) + "."
                        if absents
                        else ""
                    ),
                }
                aller("merci")
    if st.button("⬅️ Retour"):
        aller("accueil")


def page_liste():
    st.header("📋 Qui vient et qu'apporte-t-il ?")
    lignes = [r for r in tous() if r["vient"]]
    if not lignes:
        st.info("Personne ne s'est encore inscrit.")
    else:
        st.write(f"**{len(lignes)} personne(s) viennent.**")
        accomp = {}
        for r in lignes:
            if r["groupe"] != r["cle"]:
                accomp.setdefault(r["groupe"], []).append(r)
        principaux = [r for r in lignes if r["groupe"] == r["cle"]]

        for r in principaux:
            avec = accomp.get(r["cle"], [])
            titre = f'**{r["prenom"]} {r["nom"]}**'
            if avec:
                titre += " (avec " + ", ".join(a["prenom"] for a in avec) + ")"
            apports = r.get("apports") or []
            if apports:
                detail = "\n".join(f'- {a["categorie"]} : {a["detail"]}' for a in apports)
            else:
                detail = "- *rien de précisé*"
            st.markdown(f"{titre}\n\n{detail}")

        cles_principaux = {r["cle"] for r in principaux}
        for groupe, avec in accomp.items():
            if groupe not in cles_principaux:
                noms = ", ".join(f'{a["prenom"]} {a["nom"]}' for a in avec)
                st.markdown(f"**{noms}**\n\n- *rien de précisé*")
    if st.button("⬅️ Retour"):
        aller("accueil")


def page_merci():
    m = st.session_state.get("merci", {})
    st.success(m.get("titre", "Merci !"))
    st.write(m.get("texte", ""))
    if m.get("alerte"):
        st.warning(m["alerte"])
    if st.button("🏠 Retour à l'accueil"):
        aller("accueil")


def espace_organisateur():
    with st.expander("🔒 Espace organisateur"):
        mdp = st.text_input("Mot de passe", type="password", key="admin_mdp")
        if not mdp:
            return
        if mdp != st.secrets["ADMIN_PASSWORD"]:
            st.error("Mot de passe incorrect.")
            return

        lignes = tous()
        if not lignes:
            st.info("Personne ne s'est encore inscrit.")
            return

        noms = {r["cle"]: f'{r["prenom"]} {r["nom"]}' for r in lignes}
        df = pd.DataFrame(
            {
                "Personne": [f'{r["prenom"]} {r["nom"]}' for r in lignes],
                "Vient": [r["vient"] for r in lignes],
                "Avec": [
                    "" if r["groupe"] == r["cle"] else "avec " + noms.get(r["groupe"], "(désisté)")
                    for r in lignes
                ],
                "Apporte": [texte_apports(r) for r in lignes],
            }
        )
        st.metric("Personnes qui viennent", int(df["Vient"].sum()))
        st.write("**Ne viennent pas**")
        st.dataframe(df[~df["Vient"]][["Personne"]], hide_index=True)
        st.download_button(
            "Télécharger la liste (CSV)",
            df.to_csv(index=False).encode("utf-8-sig"),
            "invites.csv",
            "text/csv",
        )


PAGES = {
    "accueil": page_accueil,
    "oui": page_oui,
    "non": page_non,
    "desistement": page_desistement,
    "liste": page_liste,
    "merci": page_merci,
}

if "page" not in st.session_state:
    st.session_state.page = "accueil"
PAGES[st.session_state.page]()
