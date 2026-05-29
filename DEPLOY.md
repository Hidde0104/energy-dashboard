# Deploying to Streamlit Cloud + embedding in WordPress

## What changed in the app

The app now resolves its data source in this order:

1. **Local file** — `all_countries.csv` next to `app.py` (fastest, for local dev)
2. **Ember's public zip** — downloaded automatically from
   `files.ember-energy.org`, unzipped in memory, cached for 24 hours
3. **Manual upload** — sidebar uploader, accepts CSV or zip (final fallback)

For Streamlit Cloud deployment, **path 2 is what runs** — you do not need to
commit the data file to GitHub.

---

## Step 1 — Push to GitHub

1. Create a free GitHub account if you don't have one.
2. Create a new **public** repository (e.g. `energy-dashboard`).
3. From PowerShell, in your `Energy_dashboard` folder:

   ```powershell
   cd "C:\Users\HiddeHolwerda\Impulse\Impulse Team - Documenten\1. Backbone\3. Personal Maps\21. Hidde\Energy_dashboard"

   git init
   git add app.py requirements.txt README.md .gitignore .streamlit/ fonts/
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/energy-dashboard.git
   git push -u origin main
   ```

   ⚠️ The `.gitignore` is set up to **exclude `all_countries.csv`** from the
   commit, so the data file stays off GitHub. Good — that's what we want.

   ⚠️ Make sure `fonts/guida-bold.otf` IS committed. The app needs it.
   If you're not allowed to redistribute Guida (check your licence), don't
   commit it — the app will gracefully fall back to a serif system font.

---

## Step 2 — Deploy on Streamlit Cloud

1. Go to <https://share.streamlit.io>.
2. Sign in with your GitHub account.
3. Click **New app**, point it at:
   - Repository: `<your-username>/energy-dashboard`
   - Branch: `main`
   - Main file path: `app.py`
4. Click **Deploy**.

The first run takes a few minutes — Streamlit Cloud installs the packages and
then your app downloads the Ember zip on first visit (one-time cost,
cached for 24h after).

You'll get a URL like `https://<your-app-name>.streamlit.app`.

---

## Step 3 — Embed in WordPress

1. In WordPress, edit the page where you want the dashboard.
2. Add a **Custom HTML** block (in the block editor: `/html`).
3. Paste this, replacing the URL with yours:

   ```html
   <iframe
     src="https://your-app-name.streamlit.app/?embed=true"
     width="100%"
     height="950"
     frameborder="0"
     style="border: none; border-radius: 8px;"
     allow="fullscreen">
   </iframe>
   ```

   Notes:
   - `?embed=true` hides Streamlit's top/bottom chrome for a cleaner look.
   - `height="950"` is a starting value — adjust to fit your content. Streamlit
     apps don't auto-size in iframes, so you'll need to pick a height that
     accommodates the tallest view (the country ranking, usually).
   - The dashboard is dark; the rounded corner + your page's background will
     decide how it blends in.

4. **Preview** the page. If the iframe shows a "refused to connect" error,
   that means a security header is blocking it — see the troubleshooting
   section below.

---

## Troubleshooting

### "Refused to connect" in the iframe

Streamlit Cloud sometimes serves apps with strict X-Frame-Options. If you see
this, add this to your `.streamlit/config.toml`:

```toml
[server]
enableXsrfProtection = false
enableCORS = false
```

Push the change and redeploy.

### App is slow on first load

That's the one-time Ember download. The `@st.cache_data(ttl=24h)` means the
next 24 hours of visitors all hit the cached copy. Streamlit Cloud also
spins your app down after periods of inactivity, so the first visit after a
quiet period will be slow.

If this bothers you, upgrade to Streamlit Cloud's paid tier or move to
Render/Railway with an always-on plan.

### Ember changes the download URL

The current URL is hard-coded in `app.py` as `EMBER_ZIP_URL`. If it breaks,
search the file for that constant and update it. The app will then show the
manual uploader as a fallback, so visitors still get a usable error path.

---

## Attribution is already in the app

The sidebar's "ℹ️ About the data" expander and the page footer both credit
Ember under CC BY 4.0. You're licensing-compliant out of the box.
