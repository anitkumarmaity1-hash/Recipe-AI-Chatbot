"""NOSH - Your Intelligent Recipe Assistant (Streamlit entry point).

Run from the project root:   streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from recipebot import config
from ui import navigation, sidebar, styles
from ui.engine import get_engine
from ui.errors import friendly_message
from ui.pages import about, analytics, chat, home, ingredient_finder, recipe_details, substitution

SETUP_HELP = """
**Set up the data once**, then press *Retry*.

Windows PowerShell, from the project folder with the virtual environment active:

```powershell
python scripts/fetch_prebuilt.py
```

or the full build (about 50 minutes, see the README):

```powershell
python scripts/download_data.py
python -m recipebot.build_db
python -m recipebot.build_normalized
python -m recipebot.build_indexes bm25
python -m recipebot.build_indexes embeddings
```
"""


def show_startup_failure(exc: BaseException) -> None:
    logging.getLogger(__name__).exception("The app could not start")
    title, advice = friendly_message(exc)
    st.error(
        f"**NOSH could not start: {title}.** {advice}", icon=":material/error:")
    st.markdown(SETUP_HELP)
    with st.expander("Technical details"):
        st.code(f"{type(exc).__name__}: {exc}", language="text")
    if st.button("Retry", icon=":material/refresh:"):
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="NOSH – Recipe Assistant", page_icon="🍽️", layout="wide",
                       initial_sidebar_state="expanded")
    config.setup_logging(logging.WARNING)
    styles.inject()

    def page(module, title, icon, path, default=False):
        return st.Page(lambda: module.render(engine), title=title, icon=icon, url_path=path, default=default)

    try:
        engine = get_engine()
    except Exception as exc:                      # noqa: BLE001 - explained on screen and logged
        # the navigation still has to exist, so show the failure inside a single page
        nav = st.navigation([st.Page(lambda: show_startup_failure(
            exc), title="Setup", icon=":material/build:")])
        nav.run()
        return

    pages = {
        "home": page(home, "Home", ":material/home:", "home", default=True),
        "chat": page(chat, "AI Recipe Chat", ":material/chat:", "chat"),
        "finder": page(ingredient_finder, "Find by Ingredients", ":material/kitchen:", "ingredients"),
        "substitution": page(substitution, "Ingredient Substitution", ":material/swap_horiz:", "substitution"),
        "analytics": page(analytics, "Recipe Analytics", ":material/bar_chart:", "analytics"),
        "recipe": page(recipe_details, "Recipe Details", ":material/menu_book:", "recipe"),
        "about": page(about, "About", ":material/info:", "about"),
    }
    navigation.register(pages)
    nav = st.navigation(list(pages.values()))
    sidebar.render(engine)
    nav.run()


main()
